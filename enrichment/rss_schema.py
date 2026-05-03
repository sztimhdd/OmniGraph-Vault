"""RSS schema migration — idempotent CREATE TABLE IF NOT EXISTS for three RSS tables.

PRD §3.1.4 is the source of truth for the DDL. Called from batch_scan_kol.init_db.
"""
from __future__ import annotations

import sqlite3

_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS rss_feeds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        xml_url TEXT NOT NULL UNIQUE,
        html_url TEXT,
        category TEXT,
        active INTEGER DEFAULT 1,
        last_fetched_at TEXT,
        error_count INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rss_articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        feed_id INTEGER NOT NULL REFERENCES rss_feeds(id),
        title TEXT NOT NULL,
        url TEXT NOT NULL UNIQUE,
        author TEXT,
        summary TEXT,
        content_hash TEXT,
        published_at TEXT,
        fetched_at TEXT DEFAULT (datetime('now', 'localtime')),
        enriched INTEGER DEFAULT 0,
        content_length INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rss_classifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER NOT NULL REFERENCES rss_articles(id),
        topic TEXT NOT NULL,
        depth_score INTEGER CHECK(depth_score BETWEEN 1 AND 3),
        relevant INTEGER DEFAULT 0,
        excluded INTEGER DEFAULT 0,
        reason TEXT,
        classified_at TEXT DEFAULT (datetime('now', 'localtime')),
        UNIQUE(article_id, topic)
    )
    """,
)


def init_rss_schema(conn: sqlite3.Connection) -> None:
    """Create RSS tables if they don't exist. Idempotent."""
    cur = conn.cursor()
    for ddl in _DDL:
        cur.execute(ddl)
    conn.commit()
