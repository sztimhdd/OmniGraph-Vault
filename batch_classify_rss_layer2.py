"""Standalone Layer 2 classifier for RSS — drains rss_articles where
layer1_verdict='candidate' AND layer2_verdict IS NULL.

Quick 260510-p1s. Wraps lib.article_filter.layer2_full_body_score
+ persist_layer2_verdicts. Reuses LAYER2_BATCH_SIZE=5 chunking.

Usage:
    python batch_classify_rss_layer2.py
    python batch_classify_rss_layer2.py --max-articles 50
    python batch_classify_rss_layer2.py --dry-run
    python batch_classify_rss_layer2.py --db-path .dev-runtime/data/kol_scan.db

Cron daily-classify-rss-layer2 @ 20 8 * * * (between
daily-classify-kol @ 08:15 and daily-enrich @ 08:30).
"""
import argparse
import asyncio
import logging
import os
import sqlite3
import sys
from pathlib import Path

from config import load_env
from lib.article_filter import (
    LAYER2_BATCH_SIZE,
    ArticleWithBody,
    layer2_full_body_score,
    persist_layer2_verdicts,
)

PROJECT_ROOT = Path(__file__).parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "kol_scan.db"
DEFAULT_DAILY_CAP_FALLBACK = 500

logger = logging.getLogger("batch_classify_rss_layer2")


def _resolve_default_max_articles() -> int:
    raw = os.environ.get("OMNIGRAPH_RSS_LAYER2_DAILY_CAP", "")
    try:
        v = int(raw)
        return v if v > 0 else DEFAULT_DAILY_CAP_FALLBACK
    except (TypeError, ValueError):
        return DEFAULT_DAILY_CAP_FALLBACK


def _check_schema(conn: sqlite3.Connection) -> bool:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(rss_articles)").fetchall()}
    required = {
        "id", "title", "url", "body",
        "layer1_verdict", "layer2_verdict",
        "layer2_reason", "layer2_at", "layer2_prompt_version",
    }
    missing = required - cols
    if missing:
        logger.error(
            "rss_articles missing required cols: %s — run migrations 006/007",
            sorted(missing),
        )
        return False
    return True


def _select_candidates(
    conn: sqlite3.Connection, limit: int
) -> list[tuple[int, str, str, str]]:
    """Return (id, url, title, body) tuples for unscored candidates."""
    rows = conn.execute(
        """SELECT id, url, COALESCE(title, ''), body
           FROM rss_articles
           WHERE layer1_verdict = 'candidate'
             AND layer2_verdict IS NULL
             AND body IS NOT NULL
           ORDER BY id ASC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


async def _classify_all(
    conn: sqlite3.Connection,
    rows: list[tuple[int, str, str, str]],
    dry_run: bool,
) -> tuple[int, int, int]:
    """Classify all rows in LAYER2_BATCH_SIZE chunks.

    Returns:
        (ok_count, reject_count, null_count)
    """
    ok = rej = nul = 0
    for chunk_start in range(0, len(rows), LAYER2_BATCH_SIZE):
        chunk = rows[chunk_start : chunk_start + LAYER2_BATCH_SIZE]
        articles = [
            ArticleWithBody(id=r[0], source="rss", title=r[2], body=r[3] or "")
            for r in chunk
        ]
        if dry_run:
            logger.info(
                "[DRY-RUN] would call layer2 on %d articles: ids=%s",
                len(articles),
                [a.id for a in articles],
            )
            continue
        try:
            results = await layer2_full_body_score(articles)
        except Exception as exc:  # noqa: BLE001
            # Defensive: layer2_full_body_score already returns _all_null on
            # internal errors, but if a callsite exception leaks out we treat
            # the chunk as all-null and continue.
            logger.warning(
                "[layer2] unexpected exception %s: %s — chunk %d-%d skipped",
                type(exc).__name__,
                str(exc)[:200],
                chunk_start,
                chunk_start + len(chunk),
            )
            nul += len(chunk)
            continue

        # LF-2.6: if ALL results are NULL, do NOT persist — leave rows
        # untouched so next tick re-evaluates.
        null_in_batch = sum(1 for r in results if r.verdict is None)
        if null_in_batch == len(results):
            logger.warning(
                "[layer2] batch all-NULL reason=%s n=%d — rows stay NULL, retry next tick",
                results[0].reason if results else "empty",
                len(results),
            )
            nul += len(results)
            continue

        persist_layer2_verdicts(conn, articles, results)

        for (rid, url, _t, _b), result in zip(chunk, results):
            if result.verdict == "ok":
                ok += 1
            elif result.verdict == "reject":
                rej += 1
            else:
                nul += 1
            logger.info(
                "  id=%d url=%s verdict=%s reason=%s",
                rid,
                url[:80],
                result.verdict,
                result.reason,
            )
    return ok, rej, nul


def run(db_path: Path, max_articles: int, dry_run: bool) -> int:
    """Core entrypoint — called by main() and by tests directly."""
    if not db_path.exists():
        logger.error("DB not found: %s", db_path)
        return 1
    conn = sqlite3.connect(str(db_path))
    try:
        if not _check_schema(conn):
            return 1
        load_env()
        rows = _select_candidates(conn, max_articles)
        if not rows:
            logger.info("No RSS candidates with NULL layer2_verdict.")
            return 0
        logger.info(
            "Loaded %d candidate rows (cap=%d, dry_run=%s).",
            len(rows),
            max_articles,
            dry_run,
        )
        ok, rej, nul = asyncio.run(_classify_all(conn, rows, dry_run))
        logger.info(
            "processed: %d (ok: %d, reject: %d, null: %d)",
            len(rows),
            ok,
            rej,
            nul,
        )
        return 0
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Layer 2 classifier for RSS articles (standalone cron)."
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=_resolve_default_max_articles(),
        help="Max rows to classify per run. Default: env "
             "OMNIGRAPH_RSS_LAYER2_DAILY_CAP or 500.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log candidates but skip LLM call + DB UPDATE.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite DB. Default: {DEFAULT_DB_PATH}",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    rc = run(args.db_path, args.max_articles, args.dry_run)
    sys.exit(rc)


if __name__ == "__main__":
    main()
