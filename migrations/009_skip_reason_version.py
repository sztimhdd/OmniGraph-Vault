#!/usr/bin/env python3
"""Apply migration 009: ingestions.skip_reason_version column.

Usage:  python3 migrations/009_skip_reason_version.py [path/to/kol_scan.db] [--dry-run]
Default: data/kol_scan.db (relative to repo root)

Quick:  260509-s29 Wave 2
REQ:    CLAUDE.md "Lessons Learned" 2026-05-05 #6 (reject-reason versioning)

Idempotency: checks for the ``skip_reason_version`` column in
``PRAGMA table_info(ingestions)`` before doing any work. If already
present, skips with a "skipping" log line. Safe to re-run.

Why ADD COLUMN, not table-rebuild (cf. mig 008): mig 008 rebuilt to drop
an FK + replace a UNIQUE constraint, neither of which SQLite ALTER can do.
Adding a NOT NULL column with a constant DEFAULT is a one-statement ALTER
and existing rows are backfilled automatically.

Verifications run AFTER the ALTER:
  * column actually present in PRAGMA table_info
  * all existing rows have skip_reason_version = 0 (the default)
  * row count preserved
  * ``PRAGMA integrity_check`` returns ('ok',)
  * ``PRAGMA foreign_key_check`` returns empty list

--dry-run: prints the ALTER without executing.
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


ALTER_SQL = (
    "ALTER TABLE ingestions "
    "ADD COLUMN skip_reason_version INTEGER NOT NULL DEFAULT 0"
)


def _has_column(conn: sqlite3.Connection) -> bool:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ingestions)")}
    return "skip_reason_version" in cols


def migrate(db_path: str, dry_run: bool) -> bool:
    if not os.path.exists(db_path):
        print(f"ERROR: db not found: {db_path}", file=sys.stderr)
        return False

    conn = sqlite3.connect(db_path)
    try:
        if _has_column(conn):
            print("SKIP: skip_reason_version column already exists, no-op")
            return True

        if dry_run:
            print("DRY-RUN: would execute the following ALTER:")
            print(ALTER_SQL + ";")
            return True

        before_count = conn.execute(
            "SELECT COUNT(*) FROM ingestions"
        ).fetchone()[0]
        print(f"pre-alter row count: {before_count}")

        conn.execute(ALTER_SQL)
        conn.commit()

        # Verifications.
        if not _has_column(conn):
            print(
                "ERROR: ALTER appeared to succeed but PRAGMA table_info "
                "does not list skip_reason_version",
                file=sys.stderr,
            )
            return False

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

        # All pre-existing rows must have backfilled value 0.
        non_zero = conn.execute(
            "SELECT COUNT(*) FROM ingestions WHERE skip_reason_version <> 0"
        ).fetchone()[0]
        if non_zero != 0:
            print(
                f"ERROR: backfill leaked non-zero values "
                f"(rows with skip_reason_version != 0: {non_zero})",
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

        print(
            f"applied: skip_reason_version added; "
            f"{before_count} rows backfilled to 0; "
            f"integrity_check: ok; foreign_key_check: clean"
        )
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    db_path, dry_run = _parse_args(sys.argv[1:])
    ok = migrate(db_path, dry_run)
    sys.exit(0 if ok else 1)
