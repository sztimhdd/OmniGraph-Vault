"""Unit tests for kb.data.article_query — DATA-04, DATA-05, DATA-06, EXPORT-04, EXPORT-05.

Tests are organized by task:
  Task 1: ArticleRecord dataclass + resolve_url_hash (6 tests)
  Task 2: list_articles + get_article_by_hash with SQL (10 tests)
  Task 3: get_article_body D-14 fallback + EXPORT-05 rewrite (7 tests)
"""
from __future__ import annotations

import hashlib
import sqlite3

import pytest

from kb.data.article_query import (
    ArticleRecord,
    get_article_body,
    get_article_by_hash,
    list_articles,
    resolve_url_hash,
)


# ---------- Task 1: ArticleRecord + resolve_url_hash ----------


def _make_rec(
    *,
    source: str = "wechat",
    content_hash: str | None = None,
    body: str = "",
    id: int = 1,
    title: str = "t",
    url: str = "u",
    lang: str | None = None,
    update_time: str = "2026-01-01",
    publish_time: str | None = None,
) -> ArticleRecord:
    """Build an ArticleRecord with sensible defaults for tests."""
    return ArticleRecord(
        id=id,
        source=source,  # type: ignore[arg-type]
        title=title,
        url=url,
        body=body,
        content_hash=content_hash,
        lang=lang,
        update_time=update_time,
        publish_time=publish_time,
    )


def test_article_record_is_frozen_dataclass():
    """Test 1: ArticleRecord is @dataclass(frozen=True) — assignment raises FrozenInstanceError."""
    from dataclasses import FrozenInstanceError

    rec = _make_rec()
    with pytest.raises(FrozenInstanceError):
        rec.title = "mutated"  # type: ignore[misc]


def test_resolve_url_hash_kol_with_content_hash_uses_it_directly():
    """Test 2: KOL article with content_hash present returns it verbatim."""
    rec = _make_rec(source="wechat", content_hash="abcdef0123", body="ignored")
    assert resolve_url_hash(rec) == "abcdef0123"


def test_resolve_url_hash_kol_null_falls_back_to_md5_of_body():
    """Test 3: KOL article with NULL content_hash returns md5(body)[:10]."""
    rec = _make_rec(source="wechat", content_hash=None, body="hello world")
    expected = hashlib.md5(b"hello world").hexdigest()[:10]
    assert resolve_url_hash(rec) == expected


def test_resolve_url_hash_rss_truncates_full_md5_to_10():
    """Test 4: RSS article truncates full md5 to first 10 chars."""
    full_md5 = "e2a95c834a47f0f64c8e5826b5c3b9ab"
    rec = _make_rec(source="rss", content_hash=full_md5, body="ignored")
    assert resolve_url_hash(rec) == "e2a95c834a"


def test_resolve_url_hash_unknown_source_raises_value_error():
    """Test 5: Unknown source raises ValueError."""
    # Bypass type checker — use object.__setattr__ via the dataclass constructor
    rec = ArticleRecord(
        id=1,
        source="bogus",  # type: ignore[arg-type]
        title="t",
        url="u",
        body="b",
        content_hash=None,
        lang=None,
        update_time="2026-01-01",
        publish_time=None,
    )
    with pytest.raises(ValueError):
        resolve_url_hash(rec)


def test_resolve_url_hash_is_pure_no_db_no_filesystem():
    """Test 6: resolve_url_hash is a pure function — works without DB or images dir env."""
    # Pure function check: monkey-patch config.KB_DB_PATH to a non-existent path
    # and verify the call still works.
    import importlib

    from kb import config

    saved_db = config.KB_DB_PATH
    saved_img = config.KB_IMAGES_DIR
    try:
        # Set to clearly invalid paths; resolve_url_hash must not touch them.
        config.KB_DB_PATH = "/nonexistent/db.sqlite"  # type: ignore[assignment]
        config.KB_IMAGES_DIR = "/nonexistent/images"  # type: ignore[assignment]
        rec = _make_rec(source="wechat", content_hash="0123456789", body="x")
        assert resolve_url_hash(rec) == "0123456789"
        rec2 = _make_rec(source="wechat", content_hash=None, body="abc")
        assert resolve_url_hash(rec2) == hashlib.md5(b"abc").hexdigest()[:10]
    finally:
        config.KB_DB_PATH = saved_db  # type: ignore[assignment]
        config.KB_IMAGES_DIR = saved_img  # type: ignore[assignment]
        importlib.reload(config)


# ---------- Task 2: list_articles + get_article_by_hash ----------


@pytest.fixture
def fixture_conn() -> sqlite3.Connection:
    """In-memory SQLite with both articles + rss_articles tables populated.

    Mirrors production schema columns the query layer reads. Returns a
    connection ready to be passed via the `conn=` kwarg to query functions.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            title TEXT,
            url TEXT,
            body TEXT,
            content_hash TEXT,
            lang TEXT,
            update_time TEXT
        );
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            title TEXT,
            url TEXT,
            body TEXT,
            content_hash TEXT,
            lang TEXT,
            published_at TEXT,
            fetched_at TEXT
        );
        """
    )
    # Seed KOL articles — varied lang + update_time
    kol_rows = [
        # (id, title, url, body, content_hash, lang, update_time)
        (1, "K_zh_recent", "u/1", "中文 body content one", "abcd012345", "zh-CN", "2026-05-10"),
        (2, "K_en_mid", "u/2", "english body content two", "kkkk111111", "en", "2026-05-05"),
        (3, "K_zh_old", "u/3", "中文 body content three", "kkkk222222", "zh-CN", "2026-04-01"),
        (4, "K_null_hash", "u/4", "kol body for null-hash row", None, "en", "2026-05-08"),
    ]
    conn.executemany(
        "INSERT INTO articles (id, title, url, body, content_hash, lang, update_time) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        kol_rows,
    )
    # Seed RSS articles — full md5 (32 chars) — published_at preferred over fetched_at
    rss_rows = [
        # (id, title, url, body, content_hash[32], lang, published_at, fetched_at)
        (10, "R_en_recent", "r/10", "english rss body ten",
         "e2a95c834a47f0f64c8e5826b5c3b9ab", "en", "2026-05-12", "2026-05-12"),
        (11, "R_zh_mid", "r/11", "中文 rss body eleven",
         "11111111112222222222333333333344", "zh-CN", "2026-05-07", "2026-05-07"),
        (12, "R_en_no_pub", "r/12", "english rss body twelve",
         "abcdef0000111122223333444455556666"[:32], "en", None, "2026-05-09"),
    ]
    conn.executemany(
        "INSERT INTO rss_articles (id, title, url, body, content_hash, lang, "
        "published_at, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rss_rows,
    )
    conn.commit()
    return conn


def test_list_articles_no_filter_returns_both_tables_sorted_desc(fixture_conn):
    """Test 1: list_articles() with no filters returns rows from BOTH tables sorted by update_time DESC."""
    results = list_articles(conn=fixture_conn, limit=100)
    # 4 KOL + 3 RSS = 7
    assert len(results) == 7
    # Sorted DESC by update_time
    times = [r.update_time for r in results]
    assert times == sorted(times, reverse=True)
    # Both sources represented
    sources = {r.source for r in results}
    assert sources == {"wechat", "rss"}


def test_list_articles_filter_by_lang_en(fixture_conn):
    """Test 2: list_articles(lang='en') filters BOTH tables to lang='en' only."""
    results = list_articles(lang="en", conn=fixture_conn, limit=100)
    # K_en_mid (id=2), K_null_hash (id=4), R_en_recent (id=10), R_en_no_pub (id=12) = 4
    assert len(results) == 4
    assert all(r.lang == "en" for r in results)


def test_list_articles_filter_by_source_wechat_only(fixture_conn):
    """Test 3a: source='wechat' returns only KOL articles."""
    results = list_articles(source="wechat", conn=fixture_conn, limit=100)
    assert len(results) == 4
    assert all(r.source == "wechat" for r in results)


def test_list_articles_filter_by_source_rss_only(fixture_conn):
    """Test 3b: source='rss' returns only rss_articles rows."""
    results = list_articles(source="rss", conn=fixture_conn, limit=100)
    assert len(results) == 3
    assert all(r.source == "rss" for r in results)


def test_list_articles_pagination(fixture_conn):
    """Test 4: limit + offset slice the merged sorted result."""
    full = list_articles(conn=fixture_conn, limit=100)
    page = list_articles(limit=2, offset=2, conn=fixture_conn)
    assert page == full[2:4]


def test_list_articles_combined_filters_lang_and_source(fixture_conn):
    """Test 5: lang='zh-CN' AND source='wechat' filters articles table to zh-CN."""
    results = list_articles(lang="zh-CN", source="wechat", conn=fixture_conn, limit=100)
    # K_zh_recent (id=1), K_zh_old (id=3) = 2
    assert len(results) == 2
    assert all(r.source == "wechat" and r.lang == "zh-CN" for r in results)


def test_get_article_by_hash_kol_direct_match(fixture_conn):
    """Test 6: KOL row whose content_hash exactly matches the query hash."""
    rec = get_article_by_hash("abcd012345", conn=fixture_conn)
    assert rec is not None
    assert rec.source == "wechat"
    assert rec.id == 1
    assert rec.title == "K_zh_recent"


def test_get_article_by_hash_rss_truncated_match(fixture_conn):
    """Test 7: RSS row matched on first 10 chars of full md5."""
    rec = get_article_by_hash("e2a95c834a", conn=fixture_conn)
    assert rec is not None
    assert rec.source == "rss"
    assert rec.id == 10
    assert rec.title == "R_en_recent"


def test_get_article_by_hash_missing_returns_none(fixture_conn):
    """Test 8: nonexistent hash returns None."""
    rec = get_article_by_hash("nonexistent", conn=fixture_conn)
    assert rec is None


def test_get_article_by_hash_kol_null_hash_falls_back_to_md5_body(fixture_conn):
    """Test 9: KOL row with content_hash=NULL is found by computing md5(body)[:10]."""
    body = "kol body for null-hash row"
    expected_hash = hashlib.md5(body.encode("utf-8")).hexdigest()[:10]
    rec = get_article_by_hash(expected_hash, conn=fixture_conn)
    assert rec is not None
    assert rec.source == "wechat"
    assert rec.id == 4
    assert rec.content_hash is None  # confirms the fallback path was used


def test_queries_are_read_only_no_mutation_sql(fixture_conn):
    """Test 10: All issued SQL is SELECT-only — no INSERT/UPDATE/DELETE leakage."""

    class SpyConn:
        """Proxy conn capturing every SQL string passed to .execute()."""

        def __init__(self, real: sqlite3.Connection):
            self._real = real
            self.statements: list[str] = []

        def execute(self, sql, params=()):
            self.statements.append(sql)
            return self._real.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self._real, name)

    fixture_conn.row_factory = sqlite3.Row
    spy = SpyConn(fixture_conn)
    list_articles(conn=spy, limit=100)
    get_article_by_hash("abcd012345", conn=spy)
    get_article_by_hash("e2a95c834a", conn=spy)
    get_article_by_hash("does-not-exist", conn=spy)
    assert spy.statements, "no SQL captured (test broken)"
    for stmt in spy.statements:
        first_word = stmt.strip().split()[0].upper()
        assert first_word == "SELECT", f"non-SELECT SQL leaked: {stmt!r}"


# ---------- Task 3: get_article_body D-14 fallback + EXPORT-05 image rewrite ----------


def _make_kol_rec(*, body: str, content_hash: str = "deadbeef01") -> ArticleRecord:
    """Helper to build a wechat ArticleRecord for body-resolution tests."""
    return ArticleRecord(
        id=1,
        source="wechat",
        title="t",
        url="u",
        body=body,
        content_hash=content_hash,
        lang="zh-CN",
        update_time="2026-01-01",
        publish_time=None,
    )


def test_get_article_body_prefers_enriched_md(tmp_path, monkeypatch):
    """Test 1: final_content.enriched.md exists -> read it; source='vision_enriched'."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", tmp_path)
    rec = _make_kol_rec(body="db body should NOT be used")
    article_dir = tmp_path / "deadbeef01"
    article_dir.mkdir()
    (article_dir / "final_content.enriched.md").write_text(
        "# Enriched body\n\ncontent here", encoding="utf-8"
    )
    # Also write a regular final_content.md to verify enriched wins
    (article_dir / "final_content.md").write_text("# regular body", encoding="utf-8")

    body, source = get_article_body(rec)
    assert source == "vision_enriched"
    assert "Enriched body" in body
    assert "regular body" not in body


def test_get_article_body_falls_back_to_final_content_md(tmp_path, monkeypatch):
    """Test 2: enriched absent, final_content.md present -> read it; source='vision_enriched'."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", tmp_path)
    rec = _make_kol_rec(body="db body unused")
    article_dir = tmp_path / "deadbeef01"
    article_dir.mkdir()
    (article_dir / "final_content.md").write_text("# Plain body", encoding="utf-8")

    body, source = get_article_body(rec)
    assert source == "vision_enriched"
    assert "Plain body" in body


def test_get_article_body_falls_back_to_db_body_when_files_absent(tmp_path, monkeypatch):
    """Test 3: neither file exists -> rec.body returned; source='raw_markdown'."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", tmp_path)
    rec = _make_kol_rec(body="# DB body content\n\nhello")

    body, source = get_article_body(rec)
    assert source == "raw_markdown"
    assert body == "# DB body content\n\nhello"


def test_get_article_body_returns_empty_string_when_all_sources_empty(tmp_path, monkeypatch):
    """Test 4: all 3 sources missing/empty -> ('', 'raw_markdown'), no exception."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", tmp_path)
    rec = _make_kol_rec(body="")  # empty body, no files on disk

    body, source = get_article_body(rec)
    assert body == ""
    assert source == "raw_markdown"


def test_get_article_body_rewrites_localhost_8765_image_url(tmp_path, monkeypatch):
    """Test 5: 'http://localhost:8765/' is rewritten to '/static/img/' (EXPORT-05)."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", tmp_path)
    rec = _make_kol_rec(body="# Title\n\n![](http://localhost:8765/abc/img.png)\n\nText")

    body, _source = get_article_body(rec)
    assert "/static/img/abc/img.png" in body
    assert "localhost:8765" not in body


def test_get_article_body_does_not_rewrite_unprefixed_localhost(tmp_path, monkeypatch):
    """Test 6: 'localhost:8765' without 'http://' prefix is NOT rewritten."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", tmp_path)
    raw = "see localhost:8765/path or visit our site"
    rec = _make_kol_rec(body=raw)

    body, _source = get_article_body(rec)
    # No 'http://' prefix -> regex must not match
    assert body == raw


def test_get_article_body_rewrites_all_occurrences(tmp_path, monkeypatch):
    """Test 7: multiple 'http://localhost:8765/' occurrences all get rewritten."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", tmp_path)
    raw = (
        "![a](http://localhost:8765/x/1.png)\n"
        "![b](http://localhost:8765/y/2.png)\n"
        "![c](http://localhost:8765/z/3.png)\n"
    )
    rec = _make_kol_rec(body=raw)

    body, _source = get_article_body(rec)
    assert body.count("/static/img/") == 3
    assert "localhost:8765" not in body
