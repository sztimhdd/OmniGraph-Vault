"""Unit tests for enrichment.rss_fetch."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from enrichment import rss_fetch
from enrichment.rss_schema import init_rss_schema


EN_BODY_LONG = (
    "This is a deliberately long English body about software engineering and "
    "artificial intelligence systems so that langdetect returns 'en' and the "
    "body exceeds MIN_CONTENT_CHARS. " * 20
)
ZH_BODY_LONG = (
    "这是一篇关于人工智能与软件工程的中文技术博客文章。我们主要讨论大语言模型的最新架构" * 20
)
RU_BODY_LONG = (
    "Это длинный текст на русском языке о программировании и искусственном интеллекте. " * 20
)


def _fake_feedparser_result(entries: list[SimpleNamespace], bozo: int = 0,
                             bozo_exception: Exception | None = None) -> SimpleNamespace:
    return SimpleNamespace(entries=entries, bozo=bozo, bozo_exception=bozo_exception)


def _entry(link: str, title: str, body: str, author: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        link=link,
        title=title,
        summary=body,
        description=body,
        author=author,
        published="2026-05-02T00:00:00Z",
    )


@pytest.fixture
def fresh_db():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "t.db"
        conn = sqlite3.connect(db)
        init_rss_schema(conn)
        conn.execute(
            "INSERT INTO rss_feeds (name, xml_url, active) VALUES (?, ?, 1)",
            ("Feed A", "https://a.example/rss"),
        )
        conn.commit()
        conn.close()
        yield db


def test_insert_three_entries(fresh_db: Path) -> None:
    entries = [
        _entry(f"https://a.example/p/{i}", f"Post {i}", EN_BODY_LONG)
        for i in range(3)
    ]
    with patch("enrichment.rss_fetch.feedparser.parse",
               return_value=_fake_feedparser_result(entries)), \
         patch("enrichment.rss_fetch.time.sleep", return_value=None):
        stats = rss_fetch.run(max_feeds=None, dry_run=False, db_path=fresh_db)
    assert stats["articles_inserted"] == 3
    assert stats["feeds_ok"] == 1
    conn = sqlite3.connect(fresh_db)
    n = conn.execute("SELECT COUNT(*) FROM rss_articles").fetchone()[0]
    conn.close()
    assert n == 3


def test_rerun_is_dedup_noop(fresh_db: Path) -> None:
    entries = [
        _entry("https://a.example/p/1", "Post 1", EN_BODY_LONG)
    ]
    fake = _fake_feedparser_result(entries)
    with patch("enrichment.rss_fetch.feedparser.parse", return_value=fake), \
         patch("enrichment.rss_fetch.time.sleep", return_value=None):
        rss_fetch.run(max_feeds=None, dry_run=False, db_path=fresh_db)
        stats2 = rss_fetch.run(max_feeds=None, dry_run=False, db_path=fresh_db)
    # Second run must insert 0 (URL UNIQUE dedup)
    assert stats2["articles_inserted"] == 0


def test_skips_too_short(fresh_db: Path) -> None:
    entries = [_entry("https://a.example/p/1", "Short", "too short body")]
    with patch("enrichment.rss_fetch.feedparser.parse",
               return_value=_fake_feedparser_result(entries)), \
         patch("enrichment.rss_fetch.time.sleep", return_value=None):
        stats = rss_fetch.run(max_feeds=None, dry_run=False, db_path=fresh_db)
    assert stats["articles_inserted"] == 0


def test_skips_unsupported_language(fresh_db: Path) -> None:
    entries = [_entry("https://a.example/p/1", "Ru", RU_BODY_LONG)]
    with patch("enrichment.rss_fetch.feedparser.parse",
               return_value=_fake_feedparser_result(entries)), \
         patch("enrichment.rss_fetch.time.sleep", return_value=None):
        stats = rss_fetch.run(max_feeds=None, dry_run=False, db_path=fresh_db)
    assert stats["articles_inserted"] == 0


def test_feed_level_fault_tolerance_and_error_count(fresh_db: Path) -> None:
    conn = sqlite3.connect(fresh_db)
    conn.execute(
        "INSERT INTO rss_feeds (name, xml_url, active) VALUES (?, ?, 1)",
        ("Feed B", "https://b.example/rss"),
    )
    conn.commit()
    conn.close()

    def fake_parse(url: str, agent: str | None = None) -> SimpleNamespace:
        if "a.example" in url:
            return _fake_feedparser_result(
                [], bozo=1, bozo_exception=RuntimeError("fake 404")
            )
        return _fake_feedparser_result(
            [_entry("https://b.example/p/1", "B1", EN_BODY_LONG)]
        )

    with patch("enrichment.rss_fetch.feedparser.parse", side_effect=fake_parse), \
         patch("enrichment.rss_fetch.time.sleep", return_value=None):
        stats = rss_fetch.run(max_feeds=None, dry_run=False, db_path=fresh_db)

    assert stats["feeds_ok"] == 1
    assert stats["feeds_fail"] == 1
    assert stats["articles_inserted"] == 1

    conn = sqlite3.connect(fresh_db)
    err_a = conn.execute(
        "SELECT error_count FROM rss_feeds WHERE xml_url=?",
        ("https://a.example/rss",),
    ).fetchone()[0]
    err_b = conn.execute(
        "SELECT error_count FROM rss_feeds WHERE xml_url=?",
        ("https://b.example/rss",),
    ).fetchone()[0]
    conn.close()
    assert err_a == 1, "failing feed must have error_count incremented"
    assert err_b == 0, "successful feed must reset error_count to 0"


def test_last_fetched_at_set_on_success(fresh_db: Path) -> None:
    entries = [_entry("https://a.example/p/1", "P1", EN_BODY_LONG)]
    with patch("enrichment.rss_fetch.feedparser.parse",
               return_value=_fake_feedparser_result(entries)), \
         patch("enrichment.rss_fetch.time.sleep", return_value=None):
        rss_fetch.run(max_feeds=None, dry_run=False, db_path=fresh_db)
    conn = sqlite3.connect(fresh_db)
    ts = conn.execute(
        "SELECT last_fetched_at FROM rss_feeds WHERE xml_url=?",
        ("https://a.example/rss",),
    ).fetchone()[0]
    conn.close()
    assert ts is not None and len(ts) > 0


def test_dry_run_writes_nothing(fresh_db: Path) -> None:
    entries = [_entry("https://a.example/p/1", "P1", EN_BODY_LONG)]
    with patch("enrichment.rss_fetch.feedparser.parse",
               return_value=_fake_feedparser_result(entries)), \
         patch("enrichment.rss_fetch.time.sleep", return_value=None):
        stats = rss_fetch.run(max_feeds=None, dry_run=True, db_path=fresh_db)
    assert stats["feeds_ok"] == 1
    assert stats["articles_inserted"] == 0
    conn = sqlite3.connect(fresh_db)
    n = conn.execute("SELECT COUNT(*) FROM rss_articles").fetchone()[0]
    last = conn.execute(
        "SELECT last_fetched_at FROM rss_feeds WHERE xml_url=?",
        ("https://a.example/rss",),
    ).fetchone()[0]
    conn.close()
    assert n == 0
    assert last is None
