"""Unit tests for enrichment.rss_schema.init_rss_schema."""
from __future__ import annotations

import sqlite3

import pytest

from enrichment.rss_schema import init_rss_schema


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(":memory:")


def _table_columns(conn: sqlite3.Connection, table: str) -> dict[str, tuple[str, int]]:
    """Return {column_name: (type, notnull_flag)} from PRAGMA table_info."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    # row: (cid, name, type, notnull, dflt_value, pk)
    return {row[1]: (row[2].upper(), row[3]) for row in rows}


def test_creates_all_three_tables() -> None:
    conn = _conn()
    init_rss_schema(conn)
    names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"rss_feeds", "rss_articles", "rss_classifications"}.issubset(names)


def test_idempotent_double_init() -> None:
    conn = _conn()
    init_rss_schema(conn)
    init_rss_schema(conn)  # must not raise
    count = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'rss_%'"
    ).fetchone()[0]
    assert count == 3


def test_rss_feeds_columns_match_prd() -> None:
    conn = _conn()
    init_rss_schema(conn)
    cols = _table_columns(conn, "rss_feeds")
    expected = {
        "id",
        "name",
        "xml_url",
        "html_url",
        "category",
        "active",
        "last_fetched_at",
        "error_count",
        "created_at",
    }
    assert expected.issubset(cols.keys())


def test_rss_articles_columns_match_prd() -> None:
    conn = _conn()
    init_rss_schema(conn)
    cols = _table_columns(conn, "rss_articles")
    expected = {
        "id",
        "feed_id",
        "title",
        "url",
        "author",
        "summary",
        "content_hash",
        "published_at",
        "fetched_at",
        "enriched",
        "content_length",
    }
    assert expected.issubset(cols.keys())


def test_rss_classifications_columns_match_prd() -> None:
    conn = _conn()
    init_rss_schema(conn)
    cols = _table_columns(conn, "rss_classifications")
    expected = {
        "id",
        "article_id",
        "topic",
        "depth_score",
        "relevant",
        "excluded",
        "reason",
        "classified_at",
    }
    assert expected.issubset(cols.keys())


def test_unique_xml_url_on_rss_feeds() -> None:
    conn = _conn()
    init_rss_schema(conn)
    conn.execute(
        "INSERT INTO rss_feeds (name, xml_url) VALUES (?, ?)",
        ("Foo", "https://foo.example/rss"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO rss_feeds (name, xml_url) VALUES (?, ?)",
            ("Foo dup", "https://foo.example/rss"),
        )


def test_unique_article_id_topic_on_classifications() -> None:
    conn = _conn()
    init_rss_schema(conn)
    conn.execute(
        "INSERT INTO rss_feeds (name, xml_url) VALUES (?, ?)",
        ("Foo", "https://foo.example/rss"),
    )
    feed_id = conn.execute("SELECT id FROM rss_feeds WHERE xml_url = ?", ("https://foo.example/rss",)).fetchone()[0]
    conn.execute(
        "INSERT INTO rss_articles (feed_id, title, url) VALUES (?, ?, ?)",
        (feed_id, "T1", "https://foo.example/a/1"),
    )
    aid = conn.execute(
        "SELECT id FROM rss_articles WHERE url = ?", ("https://foo.example/a/1",)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO rss_classifications (article_id, topic, depth_score, relevant, excluded, reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (aid, "Agent", 2, 1, 0, "ok"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO rss_classifications (article_id, topic, depth_score, relevant, excluded, reason) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (aid, "Agent", 3, 1, 0, "dup"),
        )
