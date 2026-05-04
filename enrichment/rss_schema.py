"""RSS schema migration — idempotent CREATE TABLE IF NOT EXISTS for three RSS tables.

PRD §3.1.4 is the source of truth for the DDL. Called from batch_scan_kol.init_db.

Phase 19 (SCH-01): _ensure_rss_columns adds 5 nullable columns to rss_articles
on any machine where the base table was created pre-Phase-19. Idempotent.
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


# Phase 19 SCH-01: 5 new nullable columns on rss_articles. All added via
# ALTER (SQLite metadata-only, safe against the 1020-row backlog without rewrite).
_PHASE19_RSS_ARTICLES_ADDITIONS: tuple[tuple[str, str], ...] = (
    ("body", "TEXT"),
    ("body_scraped_at", "TEXT"),
    ("depth", "INTEGER"),
    ("topics", "TEXT"),
    ("classify_rationale", "TEXT"),
)


def _ensure_rss_columns(conn: sqlite3.Connection) -> None:
    """Idempotent ALTER: add 5 Phase-19 columns to rss_articles if absent.

    Uses PRAGMA table_info to detect existing columns, then ALTERs only the
    missing ones. Safe to call repeatedly — a second invocation issues zero
    ALTER statements.

    Columns added:
      - body TEXT                    full-body scrape result (Phase 20 RCL-03)
      - body_scraped_at TEXT         ISO-8601 timestamp of scrape
      - depth INTEGER                full-body classify depth 1-3
      - topics TEXT                  JSON array of classify topics
      - classify_rationale TEXT      classifier's rationale string
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(rss_articles)")}
    for col_name, col_type in _PHASE19_RSS_ARTICLES_ADDITIONS:
        if col_name not in existing:
            conn.execute(
                f"ALTER TABLE rss_articles ADD COLUMN {col_name} {col_type}"
            )
    conn.commit()


def init_rss_schema(conn: sqlite3.Connection) -> None:
    """Create RSS tables if they don't exist. Idempotent.

    Phase 19: also ensures rss_articles has the 5 Phase-19 columns via
    _ensure_rss_columns.
    """
    cur = conn.cursor()
    for ddl in _DDL:
        cur.execute(ddl)
    conn.commit()
    # Phase 19 SCH-01: add the 5 new nullable columns on rss_articles for
    # databases that predate this phase.
    _ensure_rss_columns(conn)
