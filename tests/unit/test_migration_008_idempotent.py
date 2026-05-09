"""Unit tests for ``migrations/008_ingestions_dual_source.py``.

Pins the v3.5 ir-4 (LF-4.4) migration contract:

  * **Idempotent**: running twice is a no-op on the second pass.
  * **Preserves rows**: row count + status breakdown unchanged across rebuild.
  * **Stamps source='wechat'**: all pre-existing rows assumed KOL.
  * **Drops FK**: post-rebuild table has no FK to articles(id).
  * **Adds source CHECK**: source must be in ('wechat', 'rss').
  * **Replaces UNIQUE**: UNIQUE(article_id) → UNIQUE(article_id, source).
  * **Preserves enrichment_id col + status CHECK + ingested_at default**.
  * **--dry-run** prints SQL without mutating the DB.

Tests use a tmp-path SQLite file with a freshly-built pre-008 schema (matches
production state circa migration 007). No external DB needed.
"""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = REPO_ROOT / "migrations" / "008_ingestions_dual_source.py"


def _import_migration():
    """Dynamic import (the migrations dir is not a package)."""
    spec = importlib.util.spec_from_file_location("mig008", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_pre_008_db(path: Path, rows: int = 5) -> None:
    """Create a SQLite DB matching the production pre-008 schema:
       ingestions(article_id INT PK FK→articles, status TEXT CHECK, ingested_at,
                  enrichment_id TEXT, UNIQUE(article_id))."""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE articles (id INTEGER PRIMARY KEY);
        CREATE TABLE ingestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL REFERENCES articles(id),
            status TEXT NOT NULL CHECK(status IN (
                'ok', 'failed', 'skipped', 'skipped_ingested',
                'dry_run', 'skipped_graded'
            )),
            ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
            enrichment_id TEXT,
            UNIQUE(article_id)
        );
        """
    )
    statuses = ['ok', 'failed', 'skipped', 'skipped_ingested', 'skipped_graded']
    for i in range(rows):
        conn.execute("INSERT INTO articles(id) VALUES(?)", (i + 1,))
        conn.execute(
            "INSERT INTO ingestions(article_id, status, enrichment_id) "
            "VALUES(?, ?, ?)",
            (i + 1, statuses[i % len(statuses)], f"enrich-{i}"),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Core idempotency + correctness tests
# ---------------------------------------------------------------------------


def test_migration_first_run_applies_changes(tmp_path):
    """1st run: source col added, all rows stamped 'wechat', counts preserved."""
    db = tmp_path / "test.db"
    _build_pre_008_db(db, rows=5)

    mig = _import_migration()
    assert mig.migrate(str(db), dry_run=False) is True

    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ingestions)")}
    assert "source" in cols
    n = conn.execute("SELECT COUNT(*) FROM ingestions").fetchone()[0]
    assert n == 5
    wechat_n = conn.execute(
        "SELECT COUNT(*) FROM ingestions WHERE source='wechat'"
    ).fetchone()[0]
    assert wechat_n == 5, "all migrated rows must be source='wechat'"
    conn.close()


def test_migration_second_run_is_skip(tmp_path):
    """2nd run: detects source col already present, skips entire rebuild."""
    db = tmp_path / "test.db"
    _build_pre_008_db(db, rows=3)

    mig = _import_migration()
    assert mig.migrate(str(db), dry_run=False) is True
    # Snapshot row order and count before 2nd run.
    conn = sqlite3.connect(str(db))
    before_rowids = [r[0] for r in conn.execute("SELECT id FROM ingestions ORDER BY id")]
    conn.close()

    # 2nd run.
    assert mig.migrate(str(db), dry_run=False) is True

    conn = sqlite3.connect(str(db))
    after_rowids = [r[0] for r in conn.execute("SELECT id FROM ingestions ORDER BY id")]
    conn.close()
    assert before_rowids == after_rowids, (
        "2nd run must be a no-op; row ids should be identical"
    )


def test_migration_preserves_status_values(tmp_path):
    """All 6 status enum values must remain valid post-rebuild (CHECK preserved)."""
    db = tmp_path / "test.db"
    _build_pre_008_db(db, rows=5)
    mig = _import_migration()
    assert mig.migrate(str(db), dry_run=False) is True

    conn = sqlite3.connect(str(db))
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='ingestions'"
    ).fetchone()[0]
    for v in ('ok', 'failed', 'skipped', 'skipped_ingested', 'dry_run', 'skipped_graded'):
        assert f"'{v}'" in schema, f"status CHECK must include {v!r}"
    conn.close()


def test_migration_drops_fk_to_articles(tmp_path):
    """Post-rebuild ingestions has NO FK to articles(id) — dual-source semantics
    enforced at the application layer."""
    db = tmp_path / "test.db"
    _build_pre_008_db(db, rows=2)
    mig = _import_migration()
    assert mig.migrate(str(db), dry_run=False) is True

    conn = sqlite3.connect(str(db))
    fks = conn.execute("PRAGMA foreign_key_list(ingestions)").fetchall()
    assert fks == [], (
        f"ingestions must have no FK after migration 008; got {fks!r}"
    )
    conn.close()


def test_migration_adds_source_check(tmp_path):
    """source column has CHECK (source IN ('wechat', 'rss'))."""
    db = tmp_path / "test.db"
    _build_pre_008_db(db, rows=2)
    mig = _import_migration()
    assert mig.migrate(str(db), dry_run=False) is True

    conn = sqlite3.connect(str(db))
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='ingestions'"
    ).fetchone()[0]
    assert "'wechat'" in schema and "'rss'" in schema
    # Try to insert an invalid source - must raise.
    conn.execute("INSERT INTO articles(id) VALUES(999)")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO ingestions(article_id, source, status) "
            "VALUES (999, 'invalid_source', 'ok')"
        )
    conn.close()


def test_migration_replaces_unique_with_composite(tmp_path):
    """UNIQUE(article_id) replaced with UNIQUE(article_id, source) — KOL id=42
    and RSS id=42 can co-exist as separate ingestion rows."""
    db = tmp_path / "test.db"
    _build_pre_008_db(db, rows=2)
    mig = _import_migration()
    assert mig.migrate(str(db), dry_run=False) is True

    conn = sqlite3.connect(str(db))
    # Same article_id with DIFFERENT source must be allowed.
    conn.execute(
        "INSERT INTO ingestions(article_id, source, status) VALUES (1, 'rss', 'ok')"
    )
    conn.commit()
    n = conn.execute(
        "SELECT COUNT(*) FROM ingestions WHERE article_id=1"
    ).fetchone()[0]
    assert n == 2, (
        "article_id=1 should now have 2 rows (one per source) post-rebuild"
    )
    # But (article_id=1, source='wechat') must still be unique — re-insert raises.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO ingestions(article_id, source, status) "
            "VALUES (1, 'wechat', 'ok')"
        )
    conn.close()


def test_migration_creates_index(tmp_path):
    """idx_ingestions_article_source index created for query performance."""
    db = tmp_path / "test.db"
    _build_pre_008_db(db, rows=2)
    mig = _import_migration()
    assert mig.migrate(str(db), dry_run=False) is True

    conn = sqlite3.connect(str(db))
    idx_names = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name='ingestions'"
        )
    }
    assert "idx_ingestions_article_source" in idx_names
    conn.close()


def test_migration_dry_run_no_mutation(tmp_path):
    """--dry-run prints SQL but does NOT mutate the DB."""
    db = tmp_path / "test.db"
    _build_pre_008_db(db, rows=2)
    mig = _import_migration()

    # Dry-run.
    assert mig.migrate(str(db), dry_run=True) is True

    # Schema must still be the pre-008 form (no source column).
    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ingestions)")}
    assert "source" not in cols, "dry-run must not add source column"
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
    """Unknown CLI flag → exit code 2 (per argparse-like convention)."""
    db = tmp_path / "test.db"
    _build_pre_008_db(db, rows=1)

    proc = subprocess.run(
        [sys.executable, str(MIGRATION_PATH), str(db), "--bogus-flag"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2


def test_cli_dry_run_exits_0_without_mutation(tmp_path):
    """CLI --dry-run exit code 0 + DB unchanged."""
    db = tmp_path / "test.db"
    _build_pre_008_db(db, rows=2)

    proc = subprocess.run(
        [sys.executable, str(MIGRATION_PATH), str(db), "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"

    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ingestions)")}
    assert "source" not in cols
    conn.close()


def test_cli_normal_run_exits_0_with_source_added(tmp_path):
    """CLI normal run: exit 0 + source column added."""
    db = tmp_path / "test.db"
    _build_pre_008_db(db, rows=2)

    proc = subprocess.run(
        [sys.executable, str(MIGRATION_PATH), str(db)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"

    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ingestions)")}
    assert "source" in cols
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
