"""DATA-02 + DATA-03: unit tests for kb.scripts.detect_article_lang.

Tests the CLI driver that walks `articles` + `rss_articles`, applies
`kb.data.lang_detect.detect_lang()`, and UPDATEs `lang` column where NULL.

Idempotency proof (Test 2): second invocation issues 0 UPDATEs (verified
by `conn.total_changes` delta).

Auto-migration (Test 4): when `lang` column is missing, driver runs
`migrate_lang_column` first, then proceeds.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


from kb.scripts.detect_article_lang import (
    coverage_for_table,
    detect_for_table,
    main,
)


# --- Fixtures ----------------------------------------------------------------


def _create_articles_with_lang(conn: sqlite3.Connection) -> None:
    """Create articles table WITH lang column (post-migration shape)."""
    conn.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, title TEXT, body TEXT, lang TEXT)"
    )
    conn.commit()


def _create_rss_articles_with_lang(conn: sqlite3.Connection) -> None:
    """Create rss_articles table WITH lang column."""
    conn.execute(
        "CREATE TABLE rss_articles (id INTEGER PRIMARY KEY, title TEXT, body TEXT, lang TEXT)"
    )
    conn.commit()


def _create_articles_without_lang(conn: sqlite3.Connection) -> None:
    """Create articles table WITHOUT lang column (pre-migration shape)."""
    conn.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, title TEXT, body TEXT)"
    )
    conn.commit()


def _create_rss_articles_without_lang(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE rss_articles (id INTEGER PRIMARY KEY, title TEXT, body TEXT)"
    )
    conn.commit()


# Three sample bodies pinned to hand-verifiable values
_ZH_BODY = "人" * 300  # 100% CJK, len=300 → zh-CN
_EN_BODY = "a" * 300  # 0% CJK, len=300 → en
_SHORT_BODY = "hello world"  # len < 200 → unknown


# --- Test 1: detect_for_table updates rows correctly -------------------------


def test_detect_for_table_classifies_zh_en_unknown():
    """3-row articles table → exactly 1 zh-CN, 1 en, 1 unknown."""
    conn = sqlite3.connect(":memory:")
    _create_articles_with_lang(conn)
    conn.execute("INSERT INTO articles (id, body, lang) VALUES (1, ?, NULL)", (_ZH_BODY,))
    conn.execute("INSERT INTO articles (id, body, lang) VALUES (2, ?, NULL)", (_EN_BODY,))
    conn.execute("INSERT INTO articles (id, body, lang) VALUES (3, ?, NULL)", (_SHORT_BODY,))
    conn.commit()

    result = detect_for_table(conn, "articles")

    assert result == {"zh-CN": 1, "en": 1, "unknown": 1}

    rows = {row[0]: row[1] for row in conn.execute("SELECT id, lang FROM articles")}
    assert rows == {1: "zh-CN", 2: "en", 3: "unknown"}
    conn.close()


# --- Test 2: idempotency — second run issues zero UPDATEs --------------------


def test_detect_for_table_is_idempotent():
    """Re-invocation after full population produces 0 UPDATEs (verified by total_changes)."""
    conn = sqlite3.connect(":memory:")
    _create_articles_with_lang(conn)
    conn.execute("INSERT INTO articles (id, body, lang) VALUES (1, ?, NULL)", (_ZH_BODY,))
    conn.execute("INSERT INTO articles (id, body, lang) VALUES (2, ?, NULL)", (_EN_BODY,))
    conn.commit()

    # First run — populates
    first = detect_for_table(conn, "articles")
    assert first == {"zh-CN": 1, "en": 1}

    # Snapshot total_changes before second run
    changes_before = conn.total_changes
    second = detect_for_table(conn, "articles")
    changes_after = conn.total_changes

    assert second == {}
    assert changes_after - changes_before == 0
    conn.close()


# --- Test 3: main() prints coverage report for both tables -------------------


def test_main_prints_coverage_for_both_tables(tmp_path: Path, monkeypatch, capsys):
    """`main()` covers both tables and stdout contains both table names + counts."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    _create_articles_with_lang(conn)
    _create_rss_articles_with_lang(conn)
    conn.execute("INSERT INTO articles (id, body, lang) VALUES (1, ?, NULL)", (_ZH_BODY,))
    conn.execute("INSERT INTO articles (id, body, lang) VALUES (2, ?, NULL)", (_EN_BODY,))
    conn.execute("INSERT INTO rss_articles (id, body, lang) VALUES (10, ?, NULL)", (_ZH_BODY,))
    conn.commit()
    conn.close()

    from kb.scripts import detect_article_lang as mod
    monkeypatch.setattr(mod.config, "KB_DB_PATH", db_path)

    rc = mod.main()

    assert rc == 0
    captured = capsys.readouterr()
    assert "articles:" in captured.out
    assert "rss_articles:" in captured.out
    # Coverage strings should reference per-lang counts somewhere
    assert "zh-CN" in captured.out
    assert "en" in captured.out


# --- Test 4: auto-migration when lang column is missing ---------------------


def test_main_auto_runs_migration_when_lang_column_missing(tmp_path: Path, monkeypatch, capsys):
    """If lang column is missing, driver runs migrate_lang_column first, then populates."""
    db_path = tmp_path / "test_no_lang.db"
    conn = sqlite3.connect(db_path)
    _create_articles_without_lang(conn)
    _create_rss_articles_without_lang(conn)
    # Insert rows BEFORE lang column exists
    conn.execute("INSERT INTO articles (id, body) VALUES (1, ?)", (_ZH_BODY,))
    conn.execute("INSERT INTO rss_articles (id, body) VALUES (1, ?)", (_EN_BODY,))
    conn.commit()
    conn.close()

    from kb.scripts import detect_article_lang as mod
    monkeypatch.setattr(mod.config, "KB_DB_PATH", db_path)

    rc = mod.main()
    assert rc == 0

    # Verify lang column now exists AND is populated
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
    assert "lang" in cols
    cols_rss = {row[1] for row in conn.execute("PRAGMA table_info(rss_articles)")}
    assert "lang" in cols_rss

    art_lang = conn.execute("SELECT lang FROM articles WHERE id=1").fetchone()[0]
    rss_lang = conn.execute("SELECT lang FROM rss_articles WHERE id=1").fetchone()[0]
    assert art_lang == "zh-CN"
    assert rss_lang == "en"
    conn.close()


# --- Test 5: defensive — NULL or empty body → 'unknown', no error -----------


def test_detect_for_table_handles_null_and_empty_body():
    """NULL body and empty-string body both classify as 'unknown' without error."""
    conn = sqlite3.connect(":memory:")
    _create_articles_with_lang(conn)
    conn.execute("INSERT INTO articles (id, body, lang) VALUES (1, NULL, NULL)")
    conn.execute("INSERT INTO articles (id, body, lang) VALUES (2, '', NULL)")
    conn.commit()

    result = detect_for_table(conn, "articles")

    assert result == {"unknown": 2}
    rows = {row[0]: row[1] for row in conn.execute("SELECT id, lang FROM articles")}
    assert rows == {1: "unknown", 2: "unknown"}
    conn.close()


# --- Bonus: coverage_for_table sanity ---------------------------------------


def test_coverage_for_table_counts_all_rows():
    """coverage_for_table returns counts across ALL rows (not just NULL ones)."""
    conn = sqlite3.connect(":memory:")
    _create_articles_with_lang(conn)
    conn.execute("INSERT INTO articles (id, body, lang) VALUES (1, ?, 'zh-CN')", (_ZH_BODY,))
    conn.execute("INSERT INTO articles (id, body, lang) VALUES (2, ?, 'en')", (_EN_BODY,))
    conn.execute("INSERT INTO articles (id, body, lang) VALUES (3, ?, NULL)", (_SHORT_BODY,))
    conn.commit()

    coverage = coverage_for_table(conn, "articles")
    assert coverage == {"zh-CN": 1, "en": 1, "NULL": 1}
    conn.close()


# --- Bonus: missing-table tolerance -----------------------------------------


def test_detect_for_table_skips_missing_table():
    """Missing table → empty Counter (no error)."""
    conn = sqlite3.connect(":memory:")
    # No tables exist
    result = detect_for_table(conn, "articles")
    assert result == {}
    conn.close()
