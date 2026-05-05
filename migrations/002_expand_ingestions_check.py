#!/usr/bin/env python3
"""Apply migration 002: expand ingestions.status CHECK constraint.

Usage:  python3 migrations/002_expand_ingestions_check.py [path/to/kol_scan.db]
Default: data/kol_scan.db (relative to repo root)

Idempotent: safe to run multiple times.
"""
import sqlite3
import sys
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO_ROOT, "data", "kol_scan.db")

def migrate(db_path: str) -> bool:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Check current state
    c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='ingestions'")
    row = c.fetchone()
    if not row:
        print("ERROR: 'ingestions' table not found in", db_path)
        return False

    schema = row[0]
    if "skipped_ingested" in schema:
        print("SKIP: already migrated")
        conn.close()
        return True

    print(f"Migrating {db_path}...")
    conn.execute("BEGIN")
    conn.execute("""
        CREATE TABLE ingestions_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL REFERENCES articles(id),
            status TEXT NOT NULL CHECK(status IN ('ok', 'failed', 'skipped', 'skipped_ingested', 'dry_run')),
            ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
            enrichment_id TEXT,
            UNIQUE(article_id)
        )
    """)
    conn.execute("INSERT INTO ingestions_new SELECT * FROM ingestions")
    conn.execute("DROP TABLE ingestions")
    conn.execute("ALTER TABLE ingestions_new RENAME TO ingestions")
    conn.commit()

    # Verify
    c.execute("SELECT status, COUNT(*) FROM ingestions GROUP BY status")
    rows = c.fetchall()
    print(f"Done. {sum(r[1] for r in rows)} rows preserved:")
    for status, count in rows:
        print(f"  {status}: {count}")

    conn.close()
    return True


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found")
        sys.exit(1)
    ok = migrate(DB_PATH)
    sys.exit(0 if ok else 1)
