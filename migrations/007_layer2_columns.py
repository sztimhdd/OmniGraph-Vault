#!/usr/bin/env python3
"""Apply migration 007: add layer2_* columns to articles + rss_articles.

Usage:  python3 migrations/007_layer2_columns.py [path/to/kol_scan.db]
Default: data/kol_scan.db (relative to repo root)

REQ: LF-2.5 (v3.5 Ingest Refactor — Phase ir-2)
Idempotent via PRAGMA table_info guard. Safe to run multiple times.
"""
from __future__ import annotations

import os
import sqlite3
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO_ROOT, "data", "kol_scan.db")

LAYER2_COLUMNS: tuple[str, ...] = (
    "layer2_verdict",
    "layer2_reason",
    "layer2_at",
    "layer2_prompt_version",
)
TABLES: tuple[str, ...] = ("articles", "rss_articles")


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(db_path: str) -> bool:
    if not os.path.exists(db_path):
        print(f"ERROR: db not found: {db_path}", file=sys.stderr)
        return False

    applied = 0
    skipped = 0
    conn = sqlite3.connect(db_path)
    try:
        for table in TABLES:
            existing = _existing_columns(conn, table)
            if not existing:
                print(
                    f"ERROR: '{table}' table not found in {db_path}",
                    file=sys.stderr,
                )
                return False
            for col in LAYER2_COLUMNS:
                if col in existing:
                    print(f"SKIP {table}.{col} (already present)")
                    skipped += 1
                else:
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {col} TEXT NULL"
                    )
                    print(f"ADD  {table}.{col}")
                    applied += 1
        conn.commit()
    finally:
        conn.close()

    print(
        f"\nmigration 007: applied {applied} column(s); "
        f"skipped {skipped} (already present)"
    )
    return True


if __name__ == "__main__":
    ok = migrate(DB_PATH)
    sys.exit(0 if ok else 1)
