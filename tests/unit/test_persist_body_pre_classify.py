"""BODY-01 unit tests: pre-classify body persistence (quick task 260505-m9e).

Mock-only — no real Apify, no real DeepSeek, no real LightRAG. Uses sqlite3
in-memory DB plus a hand-rolled ScrapeResult instance for input.

Covers _persist_scraped_body() helper:
  - Test 1: NULL body + successful scrape → row body persisted, helper returns body
  - Test 2: body already >= 500 chars → SQL guard skips overwrite, body unchanged
  - Test 3: DB raises → returns None, exception swallowed, WARNING emitted
"""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Autouse fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _deepseek_key(monkeypatch):
    """Module-level checks in batch_ingest_from_spider's import chain require
    DEEPSEEK_API_KEY to be set (Phase 5 cross-coupling — see CLAUDE.md)."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scrape(markdown: str = "x" * 1500, content_html: str | None = None):
    """Build a real ScrapeResult instance (no mocking — frozen dataclass)."""
    from lib.scraper import ScrapeResult

    return ScrapeResult(
        markdown=markdown,
        content_html=content_html,
        method="apify",
        summary_only=False,
    )


def _make_articles_db() -> sqlite3.Connection:
    """In-memory sqlite with the minimal articles columns _persist_scraped_body
    cares about (id, url, title, body)."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE articles ("
        "id INTEGER PRIMARY KEY, url TEXT, title TEXT, body TEXT)"
    )
    return conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_persist_body_when_null():
    """NULL body + successful scrape → body persisted; helper returns body."""
    from batch_ingest_from_spider import _persist_scraped_body

    conn = _make_articles_db()
    conn.execute(
        "INSERT INTO articles(id, url, title, body) "
        "VALUES (1, 'http://x', 't', NULL)"
    )
    conn.commit()

    scrape = _make_scrape(markdown="x" * 1500)
    persisted = _persist_scraped_body(conn, 1, scrape)

    row = conn.execute("SELECT body FROM articles WHERE id=1").fetchone()
    assert persisted is not None and len(persisted) == 1500
    assert row[0] is not None and len(row[0]) == 1500


def test_persist_body_skips_existing_long_body():
    """body already >= 500 chars → SQL guard prevents overwrite."""
    from batch_ingest_from_spider import _persist_scraped_body

    conn = _make_articles_db()
    conn.execute(
        "INSERT INTO articles(id, url, title, body) "
        "VALUES (1, 'http://x', 't', ?)",
        ("y" * 600,),
    )
    conn.commit()

    scrape = _make_scrape(markdown="x" * 1500)
    _persist_scraped_body(conn, 1, scrape)

    row = conn.execute("SELECT body FROM articles WHERE id=1").fetchone()
    assert row[0] == "y" * 600  # unchanged — guard kept it


def test_persist_body_swallows_db_exception(caplog):
    """DB raises → returns None, no propagation, warning emitted."""
    from batch_ingest_from_spider import _persist_scraped_body

    conn = MagicMock()
    conn.execute.side_effect = sqlite3.OperationalError("locked")
    scrape = _make_scrape(markdown="x" * 1500)

    with caplog.at_level("WARNING"):
        result = _persist_scraped_body(conn, 1, scrape)

    assert result is None  # graceful — no raise
    # warning emitted (don't pin exact text, just that something logged at WARNING
    # mentioning persist or body)
    assert any(
        "persist" in rec.message.lower() or "body" in rec.message.lower()
        for rec in caplog.records
    )
