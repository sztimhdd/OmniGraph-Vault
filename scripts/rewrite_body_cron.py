"""Post-ingest body-rewrite cron (kb-v2.3 readability upgrade).

Rewrites ~N displayed articles per run into a clean display-only version
stored in ``body_rewritten`` (migration 009). The rewrite INPUT is the
D-14-resolved DISPLAY content — exactly what ``get_article_body()`` would
surface BEFORE image-path rewriting:

    {KB_IMAGES_DIR}/{url_hash}/final_content.enriched.md   (fs)
    {KB_IMAGES_DIR}/{url_hash}/final_content.md            (fs, ~70% land here)
    body_cleaned or body                                    (db fallback)

NOT raw DB ``body`` — DB body carries WeChat CDN URLs (mmbiz.qpic.cn), never
the ``http://localhost:8765/`` URLs the display content carries; feeding it
would make lib/rewrite.py's URL-set valve inert AND regress images for the
~70% fs-resident majority. See memory
``decision_rewrite_display_only_kg_uses_original.md`` (CRITICAL CORRECTION)
and ``kb_v2_3_aliyun_db_paths.md``.

KG safety (Decision A): this cron NEVER touches ``body`` — LightRAG ingest
keeps reading the original. ``body_rewritten`` is display-layer only.

Behavior:
  - SELECT from articles + rss_articles (UNION ALL) where DATA-07 displayed
    (layer1='candidate' AND layer2='ok' AND body present) AND
    body_rewritten IS NULL (idempotency guard).
  - Per row: resolve display content from fs/db, skip if oversize
    (> MAX_REWRITE_CHARS), else rewrite via lib.rewrite (DeepSeek + URL-set
    diff valve). Valve-reject / LLM failure leaves the row NULL — the D-14
    chain falls back to today's behavior, no regression.
  - Serial, commit-per-row; a per-row failure never crashes the run.

Logs to both stdout AND .scratch/rewrite-body-cron-YYYYMMDD.log

CLI:
    venv/bin/python scripts/rewrite_body_cron.py                # production
    venv/bin/python scripts/rewrite_body_cron.py --dry-run      # SELECT only, no LLM, no UPDATE
    venv/bin/python scripts/rewrite_body_cron.py --limit 100    # backfill batch

Aliyun manual invocation MUST export the pins first (systemd Environment=
is not inherited over SSH; see kb_v2_3_aliyun_db_paths.md):
    set -a; source /root/.hermes/.env; set +a
    export KB_DB_PATH=/root/OmniGraph-Vault/data/kol_scan.db
    export KB_IMAGES_DIR=/root/.hermes/omonigraph-vault/images
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import sqlite3
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

# Phase 5 cross-coupling defense: ensure DEEPSEEK_API_KEY is set before any
# lib.* import chain pulls in lib.llm_deepseek (which raises at import-time
# if key is unset). config.load_env() will populate from ~/.hermes/.env.
import os
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")

# Make repo root importable when running as a script
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config import BASE_DIR  # noqa: E402
from kb import config as kb_config  # noqa: E402  (KB_IMAGES_DIR — same dir get_article_body reads)

DEFAULT_LIMIT = 10
# MEASURED constraint: the 154K-char article (id=29) timed out at 300s in real
# testing. Oversize rows are SKIPPED (left NULL -> body fallback), not truncated.
# Chunking is a filed follow-up, not built here.
MAX_REWRITE_CHARS = 30000
LOG_DIR = _REPO_ROOT / ".scratch"


def _resolve_db_path() -> Path:
    """Locate the SQLite DB.

    Priority: explicit ``KB_DB_PATH`` env (how kb-api pins the canonical
    ``/root/OmniGraph-Vault/data/kol_scan.db`` on Aliyun — the copied
    BASE_DIR heuristic below resolves to a 38-byte stub there when only
    ~/.hermes/.env is sourced; see memory kb_v2_3_aliyun_db_paths).
    Fallback mirrors translate_body_cron: ``$BASE_DIR/data/kol_scan.db``
    then ``$BASE_DIR/kol_scan.db``.
    """
    env_path = os.environ.get("KB_DB_PATH")
    if env_path:
        return Path(env_path)
    base = Path(BASE_DIR)
    nested = base / "data" / "kol_scan.db"
    if nested.exists():
        return nested
    return base / "kol_scan.db"


def _setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"rewrite-body-cron-{date.today():%Y%m%d}.log"
    fmt = "%(asctime)s %(levelname)s %(message)s"
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
        force=True,
    )
    return logging.getLogger("rewrite_body_cron")


def _resolve_url_hash(source: str, content_hash: Optional[str], url: str) -> str:
    """Pure url-hash resolution (DATA-06) — mirrors article_query.resolve_url_hash.

    - wechat + content_hash present -> content_hash (already 10 chars)
    - wechat + content_hash NULL    -> md5(url)[:10]   (e.g. articles id=861)
    - rss    + content_hash present -> content_hash[:10]
    - rss    + content_hash NULL    -> ValueError (RSS rows always have a hash)
    """
    if source == "wechat":
        if content_hash:
            return content_hash
        return hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
    if source == "rss":
        if content_hash:
            return content_hash[:10]
        raise ValueError(f"rss row url={url!r} has NULL content_hash (unexpected)")
    raise ValueError(f"unknown source: {source}")


def _resolve_display_content(
    source: str,
    content_hash: Optional[str],
    url: str,
    body_cleaned: Optional[str],
    body: Optional[str],
) -> str:
    """The D-14 display content, RAW (localhost:8765 URLs kept intact).

    Mirrors get_article_body()'s read order but does NOT apply
    _rewrite_image_paths — the rewrite input must keep raw localhost:8765
    URLs so the URL-set valve has real URLs to diff and images survive.
    """
    try:
        url_hash = _resolve_url_hash(source, content_hash, url)
    except ValueError:
        return body_cleaned or body or ""
    images_dir = Path(kb_config.KB_IMAGES_DIR)
    for fname in ("final_content.enriched.md", "final_content.md"):
        p = images_dir / url_hash / fname
        if p.exists():
            return p.read_text(encoding="utf-8")
    return body_cleaned or body or ""


def _select_candidate_rows(
    conn: sqlite3.Connection, limit: int
) -> list[tuple[int, str, str, str, str, Optional[str], Optional[str], str]]:
    """Return displayed rows lacking body_rewritten (idempotency guard).

    Tuple shape: ``(id, table_name, source, title, url, content_hash,
    body_cleaned, body)`` — everything _resolve_display_content needs,
    including the id=861 content_hash-NULL case (url for md5 fallback).
    """
    sql = """
        SELECT id, table_name, source, title, url, content_hash, body_cleaned, body
          FROM (
            SELECT id, 'articles' AS table_name, 'wechat' AS source, title, url,
                   content_hash, body_cleaned, body, layer2_at
              FROM articles
             WHERE layer1_verdict = 'candidate'
               AND layer2_verdict = 'ok'
               AND body IS NOT NULL AND body != ''
               AND body_rewritten IS NULL
            UNION ALL
            SELECT id, 'rss_articles' AS table_name, 'rss' AS source, title, url,
                   content_hash, body_cleaned, body, layer2_at
              FROM rss_articles
             WHERE layer1_verdict = 'candidate'
               AND layer2_verdict = 'ok'
               AND body IS NOT NULL AND body != ''
               AND body_rewritten IS NULL
          )
         ORDER BY layer2_at ASC, id ASC
         LIMIT ?
    """
    return list(conn.execute(sql, (limit,)))


async def _rewrite_one_row(
    row: tuple[int, str, str, str, str, Optional[str], Optional[str], str],
    conn: sqlite3.Connection,
    dry_run: bool,
    logger: logging.Logger,
) -> str:
    """Rewrite one row's display content and UPDATE body_rewritten.

    Outcomes: 'ok' | 'fail' (LLM error / valve-reject / empty content) |
    'skipped_oversize' | 'dry_run'. Never raises — a per-row failure leaves
    body_rewritten NULL (D-14 falls back to today's behavior).
    """
    art_id, table, source, title, url, content_hash, body_cleaned, body = row

    display = _resolve_display_content(source, content_hash, url, body_cleaned, body)

    if dry_run:
        logger.info(
            "[dry-run] WOULD rewrite id=%s table=%s title=%s display_len=%d",
            art_id, table, (title or "")[:80], len(display),
        )
        return "dry_run"

    if len(display) > MAX_REWRITE_CHARS:
        logger.warning(
            "skipped_oversize id=%s table=%s len=%d (> %d)",
            art_id, table, len(display), MAX_REWRITE_CHARS,
        )
        return "skipped_oversize"

    if not display.strip():
        logger.warning("empty display content id=%s table=%s — leaving NULL", art_id, table)
        return "fail"

    # Lazy import inside the per-row loop so --dry-run never imports the
    # DeepSeek chain (mirrors translate_body_cron).
    from lib.rewrite import rewrite_body_with_deepseek

    try:
        result = await rewrite_body_with_deepseek(title or "", display)
    except Exception as e:
        logger.warning(
            "rewrite raised (id=%s table=%s): %s — leaving NULL", art_id, table, e,
        )
        result = None

    if result:
        conn.execute(
            f"UPDATE {table} SET body_rewritten = ?, rewritten_at = ? WHERE id = ?",  # noqa: S608 (table is a fixed literal from SELECT)
            (result, datetime.now(timezone.utc).isoformat(), art_id),
        )
        conn.commit()
        logger.info(
            "rewrite ok id=%s table=%s in=%d out=%d",
            art_id, table, len(display), len(result),
        )
        return "ok"

    logger.info(
        "rewrite returned None (id=%s table=%s) — valve-reject or LLM failure, leaving NULL",
        art_id, table,
    )
    return "fail"


async def _run(args: argparse.Namespace, logger: logging.Logger) -> int:
    db_path = _resolve_db_path()
    if not db_path.exists():
        logger.error("DB not found: %s", db_path)
        return 1
    logger.info(
        "rewrite_body_cron starting (limit=%d dry_run=%s db=%s images_dir=%s)",
        args.limit, args.dry_run, db_path, kb_config.KB_IMAGES_DIR,
    )

    conn = sqlite3.connect(str(db_path))
    try:
        rows = _select_candidate_rows(conn, args.limit)
        if not rows:
            logger.info("0 candidates — nothing to rewrite")
            return 0
        logger.info("selected %d candidate(s) for rewrite", len(rows))

        start = time.time()
        tally = {"ok": 0, "fail": 0, "skipped_oversize": 0, "dry_run": 0}
        for row in rows:
            outcome = await _rewrite_one_row(row, conn, args.dry_run, logger)
            tally[outcome] = tally.get(outcome, 0) + 1
        elapsed = time.time() - start
        logger.info(
            "summary attempted=%d ok=%d fail=%d skipped_oversize=%d dry_run=%d elapsed=%.1fs",
            len(rows), tally["ok"], tally["fail"],
            tally["skipped_oversize"], tally["dry_run"], elapsed,
        )
        return 0
    finally:
        conn.close()


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Rewrite ~N displayed article bodies into clean display "
                    "versions (body_rewritten) via DeepSeek.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print SELECT result + resolved display lengths; no LLM, no UPDATE.",
    )
    p.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT,
        help=f"Max articles per run (default {DEFAULT_LIMIT}).",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    logger = _setup_logging()
    return asyncio.run(_run(args, logger))


if __name__ == "__main__":
    raise SystemExit(main())
