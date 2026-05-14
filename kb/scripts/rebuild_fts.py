"""SEARCH-02: rebuild articles_fts virtual table from DATA-07-filtered article list.

Invoked daily by cron (kb/scripts/daily_rebuild.sh — kb-4 plan):

    python -m kb.scripts.rebuild_fts

Drops + recreates articles_fts (via kb.services.search_index.ensure_fts_table),
then populates from kb.data.article_query.list_articles() — which already applies
the DATA-07 content-quality filter via QUALITY_FILTER_ENABLED. Row count is the
UNION of KOL `articles` + RSS `rss_articles` rows that pass the 3-condition
filter (body present, layer1='candidate', layer2 != 'reject').

On Hermes prod (~2300 visible rows after DATA-07): completes in < 5s per
SEARCH-02 timing assertion. Idempotent — second invocation produces identical
state because the DROP+CREATE cycle starts from scratch each run.

Skill(skill="python-patterns", args="Idiomatic Python CLI script: argparse with --db override + --quiet flag, main(argv) returning exit code, `if __name__ == '__main__': sys.exit(main())` boilerplate. Open a single sqlite3 connection (RW for INSERT) — rebuild is one of the few WRITE paths in kb/. Wrap in try/finally for close. Use perf_counter for timing. Print one-line summary unless --quiet. NO new env vars. Reuse FTS_TABLE_NAME constant from search_index.")

Skill(skill="writing-tests", args="Unit tests against shared fixture_db. Each test invokes main(['--db', str(fixture_db), '--quiet']) and asserts on the populated articles_fts table via direct sqlite3 query. Tests cover: success path + row count match, idempotency (call twice, second is fresh DROP+CREATE not append), DATA-07 inheritance (negative rows absent), stdout (capsys) for summary line, timing budget. Real SQLite throughout — no mocks for the data layer.")
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from typing import Optional

from kb import config
from kb.data import article_query
from kb.services import search_index


def _rebuild(db_path: str) -> int:
    """Drop + recreate articles_fts; populate from list_articles. Returns row count.

    Reuses kb.services.search_index.FTS_TABLE_NAME + ensure_fts_table — no schema
    duplication. Iterates list_articles(limit=100000, conn=conn) which inherits
    the DATA-07 filter (no extra filter logic in this script).
    """
    conn = sqlite3.connect(db_path)
    try:
        # 1. DROP existing FTS table (idempotent — first run no-ops on absent table).
        conn.execute(f"DROP TABLE IF EXISTS {search_index.FTS_TABLE_NAME}")
        # 2. CREATE virtual table fresh (delegates to kb-3-06 helper).
        search_index.ensure_fts_table(conn)
        # 3. Populate from DATA-07-filtered list_articles (UNION of KOL + RSS).
        records = article_query.list_articles(limit=100000, conn=conn)
        n = 0
        for rec in records:
            h = article_query.resolve_url_hash(rec)
            conn.execute(
                f"INSERT INTO {search_index.FTS_TABLE_NAME} "
                "(hash, title, body, lang, source) VALUES (?, ?, ?, ?, ?)",
                (h, rec.title or "", rec.body or "", rec.lang, rec.source),
            )
            n += 1
        conn.commit()
        return n
    finally:
        conn.close()


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point. Returns POSIX exit code."""
    parser = argparse.ArgumentParser(description="SEARCH-02: rebuild FTS5 index")
    parser.add_argument(
        "--db",
        default=str(config.KB_DB_PATH),
        help="SQLite path (default: kb.config.KB_DB_PATH)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress summary line (cron-friendly).",
    )
    args = parser.parse_args(argv)
    t0 = time.perf_counter()
    n = _rebuild(args.db)
    dur = time.perf_counter() - t0
    if not args.quiet:
        print(f"[rebuild_fts] indexed {n} rows in {dur:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
