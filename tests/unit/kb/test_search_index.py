"""Unit tests for kb/services/search_index.py — FTS5 trigram helpers.

Coverage matrix (kb-3-06 PLAN Task 1 behaviors):
    1. ensure_fts_table creates `articles_fts` virtual table with tokenize='trigram'
    2. fts_query returns rows where title or body contain the query
    3. fts_query returns 5-tuple (hash, title, snippet, lang, source); snippet <= 200 chars
    4. fts_query lang filter excludes non-matching rows (SEARCH-03)
    5. fts_query with KB_SEARCH_BYPASS_QUALITY=off (default) excludes DATA-07-failing rows
    6. fts_query with KB_SEARCH_BYPASS_QUALITY=on includes DATA-07-failing rows
    7. ensure_fts_table is idempotent

Skill(skill="writing-tests", args="In-memory SQLite + manual articles + rss_articles + extracted articles_fts; verifies index creation idempotent, query returns hits with snippet, lang filter, DATA-07 default + bypass. Real SQLite throughout — no mocks for the data layer.")
"""
from __future__ import annotations

import importlib
import sqlite3

import pytest


# ---- Helpers ---------------------------------------------------------------


def _make_fixture_conn() -> sqlite3.Connection:
    """Build an in-memory DB matching prod schema with positive + DATA-07-negative rows."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            title TEXT,
            url TEXT,
            body TEXT,
            content_hash TEXT,
            lang TEXT,
            update_time INTEGER,
            layer1_verdict TEXT,
            layer2_verdict TEXT
        );
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            title TEXT,
            url TEXT,
            body TEXT,
            content_hash TEXT,
            lang TEXT,
            published_at TEXT,
            fetched_at TEXT,
            layer1_verdict TEXT,
            layer2_verdict TEXT
        );
        """
    )
    # Positive KOL rows — pass DATA-07
    conn.execute(
        "INSERT INTO articles VALUES (1,'Agent Frameworks','u1','agent body about langgraph',"
        "'kolhash0001','zh-CN',1778270400,'candidate','ok')"
    )
    conn.execute(
        "INSERT INTO articles VALUES (2,'English Agent Article','u2','agent body english crewai',"
        "'kolhash0002','en',1778180400,'candidate',NULL)"
    )
    # Negative KOL row — fails DATA-07 (layer2='reject')
    conn.execute(
        "INSERT INTO articles VALUES (98,'BAD AGENT REJECTED','u98','agent body that should be hidden',"
        "'kolhash9898','en',1777700000,'candidate','reject')"
    )
    # Positive RSS row
    conn.execute(
        "INSERT INTO rss_articles VALUES (10,'RSS Agent Survey','u10','agent rss body langgraph',"
        "'rsshash0010aaaaaaaaaaaaaaaaaaaaaa','en','2026-05-10','2026-05-10','candidate','ok')"
    )
    # Negative RSS row — fails DATA-07 (layer1='reject')
    conn.execute(
        "INSERT INTO rss_articles VALUES (96,'RSS BAD AGENT','u96','agent rss body hidden',"
        "'rsshash0096bbbbbbbbbbbbbbbbbbbbbb','en','2026-05-06','2026-05-06','reject',NULL)"
    )
    conn.commit()
    return conn


def _populate_fts(conn: sqlite3.Connection, si) -> None:
    """Mirror articles + rss_articles into articles_fts (hash matches resolve_url_hash)."""
    si.ensure_fts_table(conn)
    # KOL: hash = content_hash (already 10 chars in fixtures)
    for row in conn.execute(
        "SELECT content_hash, title, body, lang FROM articles"
    ):
        conn.execute(
            f"INSERT INTO {si.FTS_TABLE_NAME} (hash,title,body,lang,source) VALUES (?,?,?,?,?)",
            (row[0], row[1], row[2], row[3], "wechat"),
        )
    # RSS: hash = substr(content_hash, 1, 10)
    for row in conn.execute(
        "SELECT substr(content_hash,1,10), title, body, lang FROM rss_articles"
    ):
        conn.execute(
            f"INSERT INTO {si.FTS_TABLE_NAME} (hash,title,body,lang,source) VALUES (?,?,?,?,?)",
            (row[0], row[1], row[2], row[3], "rss"),
        )
    conn.commit()


def _reload_si(monkeypatch: pytest.MonkeyPatch, bypass: str) -> object:
    """Reload kb.services.search_index with KB_SEARCH_BYPASS_QUALITY set to `bypass`."""
    monkeypatch.setenv("KB_SEARCH_BYPASS_QUALITY", bypass)
    import kb.services.search_index as si

    importlib.reload(si)
    return si


# ---- Tests -----------------------------------------------------------------


def test_ensure_fts_table_creates_trigram_table(monkeypatch: pytest.MonkeyPatch) -> None:
    si = _reload_si(monkeypatch, "off")
    conn = sqlite3.connect(":memory:")
    si.ensure_fts_table(conn)
    # Verify table exists and was created with trigram tokenizer
    sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = ?", (si.FTS_TABLE_NAME,)
    ).fetchone()
    assert sql_row is not None
    assert "trigram" in sql_row[0]


def test_ensure_fts_table_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    si = _reload_si(monkeypatch, "off")
    conn = sqlite3.connect(":memory:")
    si.ensure_fts_table(conn)
    # Calling twice MUST NOT raise.
    si.ensure_fts_table(conn)


def test_fts_query_returns_matches_for_query(monkeypatch: pytest.MonkeyPatch) -> None:
    si = _reload_si(monkeypatch, "off")
    conn = _make_fixture_conn()
    _populate_fts(conn, si)
    rows = si.fts_query("agent", limit=10, conn=conn)
    # Should hit the 3 positive rows (KOL id=1, KOL id=2, RSS id=10);
    # KOL id=98 + RSS id=96 are filtered out by DATA-07.
    titles = [r[1] for r in rows]
    assert any("Agent" in t for t in titles)
    assert all("BAD" not in t for t in titles)


def test_fts_query_returns_5_tuple_with_snippet_under_200(monkeypatch: pytest.MonkeyPatch) -> None:
    si = _reload_si(monkeypatch, "off")
    conn = _make_fixture_conn()
    _populate_fts(conn, si)
    rows = si.fts_query("agent", limit=10, conn=conn)
    assert rows
    for r in rows:
        assert len(r) == 5
        h, title, snippet, lang, source = r
        assert isinstance(h, str)
        assert isinstance(title, str)
        assert isinstance(snippet, str)
        assert len(snippet) <= 200
        assert source in ("wechat", "rss")


def test_fts_query_lang_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    si = _reload_si(monkeypatch, "off")
    conn = _make_fixture_conn()
    _populate_fts(conn, si)
    rows = si.fts_query("agent", lang="zh-CN", limit=10, conn=conn)
    # Only KOL id=1 (zh-CN) should remain
    assert all(r[3] == "zh-CN" for r in rows)
    assert any(r[1] == "Agent Frameworks" for r in rows)


def test_fts_query_data07_default_excludes_negative_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    si = _reload_si(monkeypatch, "off")
    conn = _make_fixture_conn()
    _populate_fts(conn, si)
    rows = si.fts_query("agent", limit=10, conn=conn)
    titles = [r[1] for r in rows]
    # KOL id=98 (layer2='reject') and RSS id=96 (layer1='reject') must be excluded.
    assert "BAD AGENT REJECTED" not in titles
    assert "RSS BAD AGENT" not in titles


def test_fts_query_bypass_quality_includes_negative_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    si = _reload_si(monkeypatch, "on")
    conn = _make_fixture_conn()
    _populate_fts(conn, si)
    rows = si.fts_query("agent", limit=10, conn=conn)
    titles = [r[1] for r in rows]
    # With bypass on, both negative rows must surface alongside positives.
    assert "BAD AGENT REJECTED" in titles
    assert "RSS BAD AGENT" in titles
