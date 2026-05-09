#!/usr/bin/env python3
"""Apply migration 008: ingestions table dual-source rebuild.

Usage:  python3 migrations/008_ingestions_dual_source.py [path/to/kol_scan.db] [--dry-run]
Default: data/kol_scan.db (relative to repo root)

REQ: LF-4.4 (v3.5 Ingest Refactor — Phase ir-4 RSS integration)

Idempotency: checks for the ``source`` column in ``PRAGMA table_info(ingestions)``
before doing any work. If ``source`` already present, skips all 5 ops cleanly
with a "skipping" log line. Safe to re-run any number of times.

Verifications run AFTER the rebuild:
  * row count preserved (before == after)
  * all migrated rows are source='wechat'
  * ``PRAGMA integrity_check`` returns ('ok',)
  * ``PRAGMA foreign_key_check`` returns empty list

Any check failure → exit 1 without further side-effects (the rebuild
already committed, so the DB stays in the post-rebuild state — operator
must restore from backup if recovery is needed).

--dry-run: prints the rebuild SQL without executing. Useful for CI gating
and review.
"""
from __future__ import annotations

import os
import sqlite3
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _parse_args(argv: list[str]) -> tuple[str, bool]:
    """Return (db_path, dry_run) from sys.argv-style list (without argv[0])."""
    db_path: str | None = None
    dry_run = False
    for a in argv:
        if a == "--dry-run":
            dry_run = True
        elif a.startswith("--"):
            print(f"ERROR: unknown flag: {a}", file=sys.stderr)
            sys.exit(2)
        else:
            if db_path is not None:
                print("ERROR: extra positional arg", file=sys.stderr)
                sys.exit(2)
            db_path = a
    if db_path is None:
        db_path = os.path.join(REPO_ROOT, "data", "kol_scan.db")
    return db_path, dry_run


REBUILD_SQL = """
CREATE TABLE ingestions_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'wechat'
        CHECK (source IN ('wechat', 'rss')),
    status TEXT NOT NULL CHECK (status IN (
        'ok', 'failed', 'skipped', 'skipped_ingested',
        'dry_run', 'skipped_graded'
    )),
    ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
    enrichment_id TEXT,
    UNIQUE (article_id, source)
);

INSERT INTO ingestions_new (id, article_id, source, status, ingested_at, enrichment_id)
    SELECT id, article_id, 'wechat', status, ingested_at, enrichment_id
    FROM ingestions;

DROP TABLE ingestions;

ALTER TABLE ingestions_new RENAME TO ingestions;

CREATE INDEX idx_ingestions_article_source ON ingestions(article_id, source);
"""


def _has_source_column(conn: sqlite3.Connection) -> bool:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ingestions)")}
    return "source" in cols


def migrate(db_path: str, dry_run: bool) -> bool:
    if not os.path.exists(db_path):
        print(f"ERROR: db not found: {db_path}", file=sys.stderr)
        return False

    conn = sqlite3.connect(db_path)
    try:
        if _has_source_column(conn):
            print("SKIP: source column already exists, skipping all 5 ops")
            return True

        if dry_run:
            print("DRY-RUN: would execute the following rebuild SQL:")
            print(REBUILD_SQL)
            return True

        before_count = conn.execute(
            "SELECT COUNT(*) FROM ingestions"
        ).fetchone()[0]
        print(f"pre-rebuild row count: {before_count}")

        # Execute rebuild atomically (executescript handles BEGIN/COMMIT
        # internally; if any statement fails, the partial work is the
        # caller's recovery problem — backup from operator runbook).
        conn.executescript(REBUILD_SQL)
        conn.commit()

        # Verifications.
        after_count = conn.execute(
            "SELECT COUNT(*) FROM ingestions"
        ).fetchone()[0]
        if before_count != after_count:
            print(
                f"ERROR: row count mismatch (before={before_count}, "
                f"after={after_count})",
                file=sys.stderr,
            )
            return False

        wechat_count = conn.execute(
            "SELECT COUNT(*) FROM ingestions WHERE source='wechat'"
        ).fetchone()[0]
        if wechat_count != after_count:
            print(
                f"ERROR: source='wechat' count {wechat_count} != "
                f"total {after_count} (some rows lost source field)",
                file=sys.stderr,
            )
            return False

        ic = conn.execute("PRAGMA integrity_check").fetchall()
        if ic != [("ok",)]:
            print(f"ERROR: integrity_check failed: {ic}", file=sys.stderr)
            return False

        fkc = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fkc:
            print(f"ERROR: foreign_key_check failed: {fkc}", file=sys.stderr)
            return False

        print(f"applied: {before_count} rows migrated, all source='wechat'")
        print(f"  CHECK status preserved (6 values)")
        print(f"  CHECK source added: ('wechat', 'rss')")
        print(f"  FK to articles(id) dropped (dual-source semantics at app layer)")
        print(f"  UNIQUE(article_id) replaced with UNIQUE(article_id, source)")
        print(f"  index idx_ingestions_article_source created")
        print(f"  integrity_check: ok; foreign_key_check: clean")
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    db_path, dry_run = _parse_args(sys.argv[1:])
    ok = migrate(db_path, dry_run)
    sys.exit(0 if ok else 1)
