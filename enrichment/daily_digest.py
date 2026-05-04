"""Daily digest: TOP N deep articles (KOL + RSS) → Markdown → Telegram + local archive.

Per PRD §3.3.2 format. SQL + Markdown templating only; NO LLM synthesis pass
(confirmed in 05-05 plan). Empty-state policy (CONTEXT Claude's Discretion §4):
zero candidates → log "no candidates" + skip Telegram + skip archive; return 0.

Asymmetric UNION ALL per D-07 REVISED 2026-05-02 + D-19:
  - KOL branch: `articles JOIN classifications` requires `a.enriched = 2` per
    Phase 4 contract (KOL must pass enrichment to qualify as "deep")
  - RSS branch: `rss_articles JOIN rss_classifications` has NO `enriched`
    filter — RSS is never enriched (D-07 REVISED); gating on enriched would
    produce zero RSS candidates forever
Both branches filter `date(fetched_at) = date('now','localtime') AND
c.depth_score >= 2`. Sort: depth DESC, content_length DESC, classified_at DESC.

Schema reality (verified 2026-05-03): `articles` has `scanned_at` (not
`fetched_at`) and no `content_length` column; we alias `a.scanned_at AS
fetched_at` and `LENGTH(COALESCE(a.digest,'')) AS content_length` for the
KOL branch. RSS branch uses native columns.

Usage:
    venv/bin/python enrichment/daily_digest.py                # today, deliver
    venv/bin/python enrichment/daily_digest.py --dry-run      # print Markdown
    venv/bin/python enrichment/daily_digest.py --date 2026-05-03
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path

import requests

from config import BASE_DIR

DB = Path(os.environ.get("KOL_SCAN_DB_PATH", "data/kol_scan.db"))
DIGEST_DIR = BASE_DIR / "digests"
TOP_N = 5
TELEGRAM_API = "https://api.telegram.org"
TELEGRAM_TIMEOUT_SECONDS = 15
EXCERPT_MAX_CHARS = 120

logger = logging.getLogger("daily_digest")

# Asymmetric UNION ALL: KOL branch requires enriched=2, RSS branch has no
# enriched filter. Both branches filter today's date + depth_score >= 2.
# Three `?` placeholders: date(KOL), date(RSS), LIMIT.
CANDIDATE_SQL = """
SELECT 'kol' AS src, a.id, a.title, a.url,
       acc.name AS source,
       COALESCE(a.digest, '') AS body,
       c.topic, c.depth_score, c.classified_at,
       a.scanned_at AS fetched_at,
       LENGTH(COALESCE(a.digest, '')) AS content_length
FROM articles a
JOIN classifications c ON c.article_id = a.id
JOIN accounts acc ON acc.id = a.account_id
WHERE date(a.scanned_at) = ?
  AND c.depth_score >= 2
  AND a.enriched = 2
UNION ALL
SELECT 'rss' AS src, a.id, a.title, a.url,
       f.name AS source,
       COALESCE(a.summary, '') AS body,
       c.topic, c.depth_score, c.classified_at,
       a.fetched_at,
       a.content_length
FROM rss_articles a
JOIN rss_classifications c ON c.article_id = a.id
JOIN rss_feeds f ON f.id = a.feed_id
WHERE date(a.fetched_at) = ?
  AND c.depth_score >= 2
ORDER BY depth_score DESC, content_length DESC, classified_at DESC
LIMIT ?
"""

STATS_SQL_KOL_TOTAL = (
    "SELECT COUNT(*) FROM articles WHERE date(scanned_at) = ?"
)
STATS_SQL_RSS_TOTAL = (
    "SELECT COUNT(*) FROM rss_articles WHERE date(fetched_at) = ?"
)
STATS_SQL_DEEP_TOTAL = """
SELECT
  (SELECT COUNT(DISTINCT a.id) FROM articles a
   JOIN classifications c ON c.article_id = a.id
   WHERE date(a.scanned_at) = ? AND c.depth_score >= 2)
  +
  (SELECT COUNT(DISTINCT a.id) FROM rss_articles a
   JOIN rss_classifications c ON c.article_id = a.id
   WHERE date(a.fetched_at) = ? AND c.depth_score >= 2)
"""
STATS_SQL_INGESTED_TOTAL = """
SELECT
  (SELECT COUNT(*) FROM articles
   WHERE date(scanned_at) = ? AND enriched = 2)
  +
  (SELECT COUNT(*) FROM rss_articles
   WHERE date(fetched_at) = ? AND enriched = 2)
"""


def _excerpt(body: str, max_chars: int = EXCERPT_MAX_CHARS) -> str:
    flat = re.sub(r"\s+", " ", (body or "").strip())
    if len(flat) <= max_chars:
        return flat
    return flat[:max_chars].rstrip() + "…"


def gather(
    date: str, top_n: int = TOP_N, db_path: Path | None = None
) -> tuple[list[dict], dict]:
    conn = sqlite3.connect(db_path if db_path is not None else DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(CANDIDATE_SQL, (date, date, top_n)).fetchall()
    kol_total = conn.execute(STATS_SQL_KOL_TOTAL, (date,)).fetchone()[0]
    rss_total = conn.execute(STATS_SQL_RSS_TOTAL, (date,)).fetchone()[0]
    deep_total = conn.execute(STATS_SQL_DEEP_TOTAL, (date, date)).fetchone()[0]
    ingested = conn.execute(STATS_SQL_INGESTED_TOTAL, (date, date)).fetchone()[0]
    conn.close()
    candidates = [dict(r) for r in rows]
    stats = {
        "kol_total": kol_total,
        "rss_total": rss_total,
        "deep_total": deep_total,
        "ingested_total": ingested,
    }
    return candidates, stats


def render(date: str, candidates: list[dict], stats: dict) -> str:
    header = f"# OmniGraph-Vault today's quality picks — {date}\n"
    lines: list[str] = [header]
    for i, c in enumerate(candidates, start=1):
        src_tag = "KOL" if c["src"] == "kol" else "RSS"
        channel = "WeChat" if c["src"] == "kol" else "RSS"
        lines.append(
            f"**{i}. [{c['topic']}] {c['title']}** [[{src_tag}]]"
        )
        lines.append(f"- 来源: {c['source']} · {channel}")
        lines.append(f"- 摘要: {_excerpt(c['body'])}")
        lines.append(f"- [阅读原文]({c['url']})")
        lines.append("")
    footer = (
        f"---\n"
        f"Scanned today: {stats['kol_total']} KOL + {stats['rss_total']} RSS "
        f"| Deep: {stats['deep_total']} | Ingested: {stats['ingested_total']}\n"
    )
    lines.append(footer)
    return "\n".join(lines)


def deliver_telegram(markdown: str) -> bool:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        logger.error(
            "Telegram creds missing (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID); "
            "archive was still written"
        )
        return False
    try:
        resp = requests.post(
            f"{TELEGRAM_API}/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": markdown,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=TELEGRAM_TIMEOUT_SECONDS,
        )
    except Exception as ex:
        logger.error("delivery_error: %s", ex)
        return False
    if not (200 <= resp.status_code < 300):
        logger.error(
            "delivery_error: status=%s body=%s",
            resp.status_code,
            resp.text[:300],
        )
        return False
    return True


def archive(date: str, markdown: str, digest_dir: Path | None = None) -> Path:
    target_dir = digest_dir if digest_dir is not None else DIGEST_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{date}.md"
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(markdown, encoding="utf-8")
    os.replace(tmp, target)
    return target


def run(
    date: str,
    dry_run: bool,
    db_path: Path | None = None,
    digest_dir: Path | None = None,
    top_n: int = TOP_N,
) -> int:
    candidates, stats = gather(date, top_n=top_n, db_path=db_path)
    if not candidates:
        logger.info(
            "no candidates for %s (KOL total=%d, RSS total=%d); "
            "skipping digest delivery + archive",
            date,
            stats["kol_total"],
            stats["rss_total"],
        )
        return 0
    markdown = render(date, candidates, stats)
    if dry_run:
        print(markdown)
        return 0
    delivery_ok = deliver_telegram(markdown)
    archived = archive(date, markdown, digest_dir=digest_dir)
    logger.info(
        "digest delivered=%s archived=%s candidates=%d",
        delivery_ok,
        archived,
        len(candidates),
    )
    return 0 if delivery_ok else 1


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    p = argparse.ArgumentParser()
    p.add_argument(
        "--date",
        default=dt.date.today().isoformat(),
        help="YYYY-MM-DD (default: today, localtime)",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--top-n", type=int, default=TOP_N)
    args = p.parse_args()
    sys.exit(run(args.date, args.dry_run, top_n=args.top_n))


if __name__ == "__main__":
    main()
