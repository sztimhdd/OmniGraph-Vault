"""Apply kb/data/migrations/*.sql files in order. Idempotent.

Uses PRAGMA table_info to guard ALTER TABLE ADD COLUMN statements — safe
to re-run on an already-migrated DB. Follows the same pattern as
kb/scripts/migrate_lang_column.py.

Usage:
    python kb/data/migrations/run_migrations.py
    python kb/data/migrations/run_migrations.py --db /path/to/kol_scan.db
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    return column in cols


_ALTER_ADD_RE = re.compile(
    r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)",
    re.IGNORECASE,
)


def _strip_sql_comments(stmt: str) -> str:
    """Remove leading SQL line comments (-- ...) from a statement block."""
    lines = [ln for ln in stmt.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines).strip()


def _apply_sql(conn: sqlite3.Connection, sql: str) -> list[str]:
    """Apply SQL statements, skipping ALTER TABLE ADD COLUMN if column exists.

    Returns list of status strings for each statement.
    """
    statuses: list[str] = []
    for stmt in sql.split(";"):
        stmt = _strip_sql_comments(stmt)
        if not stmt:
            continue
        m = _ALTER_ADD_RE.match(stmt)
        if m:
            table, col = m.group(1), m.group(2)
            if _column_exists(conn, table, col):
                statuses.append(f"  SKIP (already exists): {table}.{col}")
                continue
        conn.execute(stmt)
        statuses.append(f"  OK: {stmt[:60].replace(chr(10), ' ')}")
    conn.commit()
    return statuses


def run_migrations(db_path: Path) -> int:
    migrations_dir = Path(__file__).parent
    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        print("No SQL migration files found.")
        return 0
    if not db_path.exists():
        print(f"ERROR: DB not found at {db_path}", file=sys.stderr)
        return 1
    with sqlite3.connect(db_path) as conn:
        for sql_file in sql_files:
            print(f"Applying {sql_file.name} ...")
            sql = sql_file.read_text(encoding="utf-8")
            for status in _apply_sql(conn, sql):
                print(status)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply kb SQL migrations")
    parser.add_argument("--db", help="Path to kol_scan.db", default=None)
    args = parser.parse_args()
    if args.db:
        db_path = Path(args.db)
    else:
        from kb import config
        db_path = config.KB_DB_PATH
    return run_migrations(db_path)


if __name__ == "__main__":
    sys.exit(main())
