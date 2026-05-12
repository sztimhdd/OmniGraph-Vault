"""DATA-01: unit tests for kb.scripts.migrate_lang_column.

Tests the idempotent SQLite migration adding nullable `lang TEXT` column to
both `articles` and `rss_articles` tables. Mirrors the
`enrichment/rss_schema.py:_ensure_rss_columns` PRAGMA-table_info pattern.
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


# Module-under-test imported lazily inside tests so we can monkeypatch
# `kb.config.KB_DB_PATH` before main() reads it.
from kb.scripts.migrate_lang_column import migrate_lang_column


def _create_base_tables(conn: sqlite3.Connection) -> None:
    """Create minimal articles + rss_articles tables (no lang column)."""
    conn.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, title TEXT, body TEXT)"
    )
    conn.execute(
        "CREATE TABLE rss_articles (id INTEGER PRIMARY KEY, title TEXT, body TEXT)"
    )
    conn.commit()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


# --- Test 1: fresh migration adds lang to both tables ---


def test_migrate_adds_lang_to_both_tables():
    """On a DB with both tables created without lang, migration adds lang to each."""
    conn = sqlite3.connect(":memory:")
    _create_base_tables(conn)
    assert "lang" not in _columns(conn, "articles")
    assert "lang" not in _columns(conn, "rss_articles")

    result = migrate_lang_column(conn)

    assert result == {"articles": "added", "rss_articles": "added"}
    assert "lang" in _columns(conn, "articles")
    assert "lang" in _columns(conn, "rss_articles")
    conn.close()


# --- Test 2: idempotency — second run issues zero ALTER statements ---


def test_migrate_idempotent_zero_alters_on_second_run():
    """Second invocation makes NO ALTER TABLE calls (verified via spy wrapper).

    sqlite3.Connection.execute is read-only in CPython, so we wrap conn in
    a thin proxy class that delegates to the real conn but counts ALTERs.
    """
    real_conn = sqlite3.connect(":memory:")
    _create_base_tables(real_conn)

    # First run — adds the columns
    migrate_lang_column(real_conn)
    assert "lang" in _columns(real_conn, "articles")
    assert "lang" in _columns(real_conn, "rss_articles")

    alter_calls: list[str] = []

    class SpyConn:
        def __init__(self, c: sqlite3.Connection):
            self._c = c

        def execute(self, sql, *args, **kwargs):
            if "ALTER TABLE" in sql.upper():
                alter_calls.append(sql)
            return self._c.execute(sql, *args, **kwargs)

        def commit(self):
            return self._c.commit()

    spy = SpyConn(real_conn)
    result = migrate_lang_column(spy)  # type: ignore[arg-type]

    assert alter_calls == []
    assert result == {"articles": "already_present", "rss_articles": "already_present"}
    real_conn.close()


# --- Test 3: asymmetric pre-state (only one table has lang) ---


def test_migrate_handles_partial_prior_run():
    """When only articles has lang, migration adds it ONLY to rss_articles."""
    conn = sqlite3.connect(":memory:")
    _create_base_tables(conn)
    # Pre-populate articles with lang (simulate partial prior migration)
    conn.execute("ALTER TABLE articles ADD COLUMN lang TEXT")
    conn.commit()

    assert "lang" in _columns(conn, "articles")
    assert "lang" not in _columns(conn, "rss_articles")

    result = migrate_lang_column(conn)

    assert result == {"articles": "already_present", "rss_articles": "added"}
    assert "lang" in _columns(conn, "rss_articles")
    conn.close()


# --- Test 4: neither table exists — exit cleanly ---


def test_migrate_handles_missing_tables():
    """When neither articles nor rss_articles exists, returns table_missing for both."""
    conn = sqlite3.connect(":memory:")
    # Do NOT create any tables.

    result = migrate_lang_column(conn)

    assert result == {"articles": "table_missing", "rss_articles": "table_missing"}
    conn.close()


# --- Test 5: CLI invocation against a real temp file DB ---


def test_cli_runs_against_temp_db(tmp_path: Path, monkeypatch):
    """`python -m kb.scripts.migrate_lang_column` against a populated temp DB
    exits 0, leaves both tables migrated, second run is a no-op."""
    db_path = tmp_path / "test_kol_scan.db"
    conn = sqlite3.connect(db_path)
    _create_base_tables(conn)
    conn.close()

    # Monkeypatch config.KB_DB_PATH for the subprocess: easier to invoke the
    # function directly via main() with a patched config than to spawn
    # subprocess (cross-platform PYTHONPATH wrangling).
    from kb.scripts import migrate_lang_column as mod
    monkeypatch.setattr(mod.config, "KB_DB_PATH", db_path)

    rc1 = mod.main()
    assert rc1 == 0

    # Verify columns now exist
    conn = sqlite3.connect(db_path)
    assert "lang" in _columns(conn, "articles")
    assert "lang" in _columns(conn, "rss_articles")
    conn.close()

    # Second run should also exit 0 (idempotency)
    rc2 = mod.main()
    assert rc2 == 0


# --- Test 6 (bonus): missing DB file → exit 1 with stderr ---


def test_cli_missing_db_exits_1(tmp_path: Path, monkeypatch, capsys):
    """If KB_DB_PATH points at a nonexistent file, main() returns 1."""
    missing_db = tmp_path / "does_not_exist.db"
    from kb.scripts import migrate_lang_column as mod
    monkeypatch.setattr(mod.config, "KB_DB_PATH", missing_db)

    rc = mod.main()
    assert rc == 1
    captured = capsys.readouterr()
    assert "ERROR: DB not found" in captured.err
