"""Unit tests for kb.data.article_query — DATA-04, DATA-05, DATA-06, EXPORT-04, EXPORT-05.

Tests are organized by task:
  Task 1: ArticleRecord dataclass + resolve_url_hash (6 tests)
  Task 2: list_articles + get_article_by_hash with SQL (10 tests)
  Task 3: get_article_body D-14 fallback + EXPORT-05 rewrite (7 tests)
"""
from __future__ import annotations

import hashlib

import pytest

from kb.data.article_query import ArticleRecord, resolve_url_hash


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
