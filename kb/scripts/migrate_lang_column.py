"""DATA-01: One-time SQLite migration adding nullable `lang TEXT` column to
`articles` and `rss_articles` tables.

Idempotent: re-running issues zero ALTER TABLE statements (uses PRAGMA table_info
pre-check, mirrors the pattern in enrichment/rss_schema.py:_ensure_rss_columns).

Schema-extending non-breaking (C3 contract preserved).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from kb import config

_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("articles", "lang", "TEXT"),
    ("rss_articles", "lang", "TEXT"),
)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    return column in cols


def migrate_lang_column(conn: sqlite3.Connection) -> dict[str, str]:
    """Add `lang TEXT` to articles + rss_articles if absent. Idempotent.

    Returns:
        dict mapping table name → action ('added' | 'already_present' | 'table_missing')
    """
    results: dict[str, str] = {}
    for table, col, col_type in _TARGETS:
        if not _table_exists(conn, table):
            results[table] = "table_missing"
            continue
        if _column_exists(conn, table, col):
            results[table] = "already_present"
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        results[table] = "added"
    conn.commit()
    return results


def main() -> int:
    db_path: Path = config.KB_DB_PATH
    if not db_path.exists():
        print(f"ERROR: DB not found at {db_path}", file=sys.stderr)
        return 1
    with sqlite3.connect(db_path) as conn:
        results = migrate_lang_column(conn)
    for table, action in results.items():
        print(f"  {table}: {action}")
    print(f"Migration complete (DB: {db_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
