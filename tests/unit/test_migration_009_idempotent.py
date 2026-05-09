"""Unit tests for ``migrations/009_skip_reason_version.py``.

Pins the v3.5 quick-260509-s29 Wave 2 migration contract:

  * **Idempotent**: running twice is a no-op on the second pass.
  * **Adds column**: ``skip_reason_version INTEGER NOT NULL DEFAULT 0`` on
    ``ingestions``.
  * **Backfills 0**: all pre-existing rows post-ALTER have
    ``skip_reason_version = 0``.
  * **Preserves rows**: row count + status breakdown unchanged.
  * **--dry-run** prints SQL without mutating the DB.
  * **CLI exit codes**: 0 on success, 1 on missing DB / verification fail,
    2 on unknown flag.

Tests use a tmp-path SQLite file with a freshly-built post-008 schema
(matches production state after migration 008 has applied — that is, the
``ingestions`` table has the ``source`` column). No external DB needed.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = REPO_ROOT / "migrations" / "009_skip_reason_version.py"


def _import_migration():
    """Dynamic import (the migrations dir is not a package)."""
    spec = importlib.util.spec_from_file_location("mig009", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_post_008_db(path: Path, rows: int = 5) -> None:
    """Create a SQLite DB matching the production post-008 schema:
       ingestions(article_id INT, source TEXT CHECK, status TEXT CHECK,
                  ingested_at, enrichment_id, UNIQUE(article_id, source))."""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE ingestions (
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
        CREATE INDEX idx_ingestions_article_source
            ON ingestions(article_id, source);
        """
    )
    statuses = ['ok', 'failed', 'skipped', 'skipped_ingested', 'skipped_graded']
    for i in range(rows):
        conn.execute(
            "INSERT INTO ingestions(article_id, source, status, enrichment_id) "
            "VALUES(?, 'wechat', ?, ?)",
            (i + 1, statuses[i % len(statuses)], f"enrich-{i}"),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Core idempotency + correctness tests
# ---------------------------------------------------------------------------


def test_migration_first_run_adds_column(tmp_path):
    """1st run: skip_reason_version column added; existing rows backfilled to 0."""
    db = tmp_path / "test.db"
    _build_post_008_db(db, rows=5)

    mig = _import_migration()
    assert mig.migrate(str(db), dry_run=False) is True

    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ingestions)")}
    assert "skip_reason_version" in cols

    # All 5 existing rows must have value 0 (the DEFAULT).
    n_zero = conn.execute(
        "SELECT COUNT(*) FROM ingestions WHERE skip_reason_version = 0"
    ).fetchone()[0]
    assert n_zero == 5, f"all 5 rows must be backfilled to 0; got {n_zero}"

    # Row count preserved.
    n_total = conn.execute("SELECT COUNT(*) FROM ingestions").fetchone()[0]
    assert n_total == 5
    conn.close()


def test_migration_second_run_is_skip(tmp_path):
    """2nd run: detects column already present, no-op (idempotent)."""
    db = tmp_path / "test.db"
    _build_post_008_db(db, rows=3)

    mig = _import_migration()
    assert mig.migrate(str(db), dry_run=False) is True

    # Snapshot before 2nd run.
    conn = sqlite3.connect(str(db))
    before = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT id, skip_reason_version FROM ingestions ORDER BY id"
        )
    ]
    conn.close()

    # 2nd run.
    assert mig.migrate(str(db), dry_run=False) is True

    conn = sqlite3.connect(str(db))
    after = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT id, skip_reason_version FROM ingestions ORDER BY id"
        )
    ]
    conn.close()
    assert before == after, "2nd run must be a no-op; rows must be identical"


def test_migration_second_run_does_not_overwrite_nonzero(tmp_path):
    """If a row was bumped to skip_reason_version=1 between runs, the 2nd
    invocation must NOT reset it to 0. Idempotency means "no work", not
    "re-backfill"."""
    db = tmp_path / "test.db"
    _build_post_008_db(db, rows=2)

    mig = _import_migration()
    assert mig.migrate(str(db), dry_run=False) is True

    # Manually bump one row's version to simulate an INSERT under
    # SKIP_REASON_VERSION_CURRENT=1.
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE ingestions SET skip_reason_version = 1 WHERE id = 1"
    )
    conn.commit()
    conn.close()

    # 2nd run.
    assert mig.migrate(str(db), dry_run=False) is True

    conn = sqlite3.connect(str(db))
    v = conn.execute(
        "SELECT skip_reason_version FROM ingestions WHERE id = 1"
    ).fetchone()[0]
    conn.close()
    assert v == 1, (
        f"2nd run must preserve the bumped value; expected 1, got {v}"
    )


def test_migration_default_value_zero_on_subsequent_inserts(tmp_path):
    """Post-migration: an INSERT that omits skip_reason_version gets the
    DEFAULT (0). This is the schema contract, not a migration concern, but
    we pin it here to catch a regression if someone changes the DEFAULT."""
    db = tmp_path / "test.db"
    _build_post_008_db(db, rows=1)

    mig = _import_migration()
    assert mig.migrate(str(db), dry_run=False) is True

    conn = sqlite3.connect(str(db))
    # Insert a row WITHOUT specifying skip_reason_version.
    conn.execute(
        "INSERT INTO ingestions(article_id, source, status) "
        "VALUES (999, 'wechat', 'ok')"
    )
    conn.commit()
    v = conn.execute(
        "SELECT skip_reason_version FROM ingestions WHERE article_id = 999"
    ).fetchone()[0]
    conn.close()
    assert v == 0, (
        f"DEFAULT must be 0 for omitted skip_reason_version; got {v}"
    )


def test_migration_column_is_not_null(tmp_path):
    """Schema CHECK: skip_reason_version is NOT NULL — INSERT with explicit
    NULL must raise IntegrityError. This pins the NOT NULL constraint so a
    future migration that relaxes it is caught."""
    db = tmp_path / "test.db"
    _build_post_008_db(db, rows=1)

    mig = _import_migration()
    assert mig.migrate(str(db), dry_run=False) is True

    conn = sqlite3.connect(str(db))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO ingestions(article_id, source, status, "
            "skip_reason_version) VALUES (1234, 'wechat', 'ok', NULL)"
        )
    conn.close()


def test_migration_preserves_row_count_and_status(tmp_path):
    """Row count + status distribution unchanged across the migration."""
    db = tmp_path / "test.db"
    _build_post_008_db(db, rows=10)

    conn = sqlite3.connect(str(db))
    before_status = dict(conn.execute(
        "SELECT status, COUNT(*) FROM ingestions GROUP BY status"
    ).fetchall())
    conn.close()

    mig = _import_migration()
    assert mig.migrate(str(db), dry_run=False) is True

    conn = sqlite3.connect(str(db))
    after_status = dict(conn.execute(
        "SELECT status, COUNT(*) FROM ingestions GROUP BY status"
    ).fetchall())
    conn.close()
    assert before_status == after_status


def test_migration_dry_run_no_mutation(tmp_path):
    """--dry-run prints the ALTER but does NOT mutate the DB."""
    db = tmp_path / "test.db"
    _build_post_008_db(db, rows=2)

    mig = _import_migration()
    assert mig.migrate(str(db), dry_run=True) is True

    # Schema must still be the pre-009 form (no skip_reason_version column).
    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ingestions)")}
    assert "skip_reason_version" not in cols, (
        "dry-run must not add skip_reason_version column"
    )
    conn.close()


def test_migration_missing_db_path_returns_false(tmp_path):
    """migrate() returns False if the DB path doesn't exist."""
    mig = _import_migration()
    nonexistent = tmp_path / "does-not-exist.db"
    assert mig.migrate(str(nonexistent), dry_run=False) is False


# ---------------------------------------------------------------------------
# CLI behavior (subprocess invocation — pins exit codes + arg parsing)
# ---------------------------------------------------------------------------


def test_cli_unknown_flag_exits_2(tmp_path):
    """Unknown CLI flag → exit code 2."""
    db = tmp_path / "test.db"
    _build_post_008_db(db, rows=1)

    proc = subprocess.run(
        [sys.executable, str(MIGRATION_PATH), str(db), "--bogus-flag"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2


def test_cli_dry_run_exits_0_without_mutation(tmp_path):
    """CLI --dry-run exit 0 + DB unchanged."""
    db = tmp_path / "test.db"
    _build_post_008_db(db, rows=2)

    proc = subprocess.run(
        [sys.executable, str(MIGRATION_PATH), str(db), "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"

    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ingestions)")}
    assert "skip_reason_version" not in cols
    conn.close()


def test_cli_normal_run_exits_0_with_column_added(tmp_path):
    """CLI normal run: exit 0 + skip_reason_version column added."""
    db = tmp_path / "test.db"
    _build_post_008_db(db, rows=2)

    proc = subprocess.run(
        [sys.executable, str(MIGRATION_PATH), str(db)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"

    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ingestions)")}
    assert "skip_reason_version" in cols
    conn.close()


def test_cli_missing_db_exits_1(tmp_path):
    """Missing DB path → migrate returns False → CLI exit 1."""
    nonexistent = tmp_path / "does-not-exist.db"
    proc = subprocess.run(
        [sys.executable, str(MIGRATION_PATH), str(nonexistent)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "not found" in proc.stderr.lower() or "not found" in proc.stdout.lower()
