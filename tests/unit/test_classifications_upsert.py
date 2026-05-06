"""UPSERT correctness + dedup migration + UNIQUE constraint enforcement.

Quick: 260506-se5 (2026-05-06)

These tests verify migrations/004_classifications_unique_article_id.sql:
    1. dedup keeps MAX(rowid) per article_id
    2. ON CONFLICT(article_id) DO UPDATE replaces existing row in-place
    3. bare INSERT (no ON CONFLICT) raises sqlite3.IntegrityError after the
       UNIQUE index is in place

We use stdlib-only sqlite3 + :memory: so the tests run anywhere with no
external state and no DEEPSEEK_API_KEY import-time coupling. The
`classifications` DDL is copied verbatim from batch_scan_kol.py:101-111.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

# DDL copied verbatim from batch_scan_kol.py:101-111 (see CLAUDE.md
# "critical_findings_from_codebase" — do NOT import from batch_scan_kol.py
# to avoid the DEEPSEEK_API_KEY import-time coupling on Hermes).
CLASSIFICATIONS_DDL = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    topic TEXT NOT NULL,
    depth_score INTEGER CHECK(depth_score BETWEEN 1 AND 3),
    relevant INTEGER DEFAULT 0,
    excluded INTEGER DEFAULT 0,
    reason TEXT,
    classified_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(article_id, topic)
);
"""

# Phase 10 schema-shift columns added at runtime by ingest path
# (depth INTEGER, topics TEXT, rationale TEXT). Tests that exercise the
# 7-col INSERT add those columns inline via ALTER TABLE.

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "004_classifications_unique_article_id.sql"
)


def _setup_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(CLASSIFICATIONS_DDL)
    conn.execute("INSERT INTO articles (id) VALUES (1)")
    conn.execute("INSERT INTO articles (id) VALUES (2)")
    conn.commit()
    return conn


def _apply_migration(conn: sqlite3.Connection) -> None:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)


def test_migration_dedups_then_creates_unique_index() -> None:
    """3 rows with same article_id collapse to 1; survivor has MAX(rowid)."""
    conn = _setup_db()
    # Insert 3 rows for article_id=1 with distinct (topic) values so the
    # existing UNIQUE(article_id, topic) constraint allows them.
    conn.execute(
        "INSERT INTO classifications (article_id, topic, depth_score, reason) "
        "VALUES (1, 'agent', 1, 'first')"
    )
    conn.execute(
        "INSERT INTO classifications (article_id, topic, depth_score, reason) "
        "VALUES (1, 'rag', 2, 'middle')"
    )
    conn.execute(
        "INSERT INTO classifications (article_id, topic, depth_score, reason) "
        "VALUES (1, 'llm', 3, 'last')"
    )
    conn.commit()

    pre_count = conn.execute(
        "SELECT COUNT(*) FROM classifications WHERE article_id=1"
    ).fetchone()[0]
    assert pre_count == 3, "fixture should have 3 rows pre-migration"

    _apply_migration(conn)

    post_count = conn.execute(
        "SELECT COUNT(*) FROM classifications WHERE article_id=1"
    ).fetchone()[0]
    assert post_count == 1, "migration must dedup to 1 row per article_id"

    # Survivor has MAX(rowid) = the row inserted last (topic='llm').
    surviving_topic = conn.execute(
        "SELECT topic FROM classifications WHERE article_id=1"
    ).fetchone()[0]
    assert surviving_topic == "llm", (
        "dedup must keep MAX(rowid) row (topic='llm' was inserted last)"
    )

    # Idempotency: re-running migration is a no-op (no exception).
    _apply_migration(conn)
    again_count = conn.execute(
        "SELECT COUNT(*) FROM classifications WHERE article_id=1"
    ).fetchone()[0]
    assert again_count == 1, "second migration run must be a no-op"


def test_upsert_replaces_existing_row() -> None:
    """ON CONFLICT(article_id) DO UPDATE replaces the row's non-PK columns."""
    conn = _setup_db()
    # Add Phase 10 columns so we can replay the actual production INSERT
    # at batch_ingest_from_spider.py:1025.
    conn.execute("ALTER TABLE classifications ADD COLUMN depth INTEGER")
    conn.execute("ALTER TABLE classifications ADD COLUMN topics TEXT")
    conn.execute("ALTER TABLE classifications ADD COLUMN rationale TEXT")
    conn.commit()

    _apply_migration(conn)

    upsert_sql = """
        INSERT INTO classifications
            (article_id, topic, depth_score, depth, topics, rationale, relevant)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(article_id) DO UPDATE SET
            topic=excluded.topic,
            depth_score=excluded.depth_score,
            depth=excluded.depth,
            topics=excluded.topics,
            rationale=excluded.rationale,
            relevant=excluded.relevant
    """
    # First insert.
    conn.execute(upsert_sql, (1, "agent", 1, 1, '["agent"]', "initial reason"))
    conn.commit()
    # Second insert with same article_id, different content — must REPLACE.
    conn.execute(upsert_sql, (1, "rag", 3, 3, '["rag", "llm"]', "second reason"))
    conn.commit()

    rows = conn.execute(
        "SELECT topic, depth_score, depth, topics, rationale, relevant "
        "FROM classifications WHERE article_id=1"
    ).fetchall()
    assert len(rows) == 1, "UPSERT must keep one row per article_id"
    topic, depth_score, depth, topics, rationale, relevant = rows[0]
    assert topic == "rag", "topic must be the second insert's value"
    assert depth_score == 3
    assert depth == 3
    assert topics == '["rag", "llm"]'
    assert rationale == "second reason"
    assert relevant == 1


def test_unique_constraint_blocks_bare_insert() -> None:
    """Bare INSERT without ON CONFLICT must raise IntegrityError post-migration."""
    conn = _setup_db()
    _apply_migration(conn)

    conn.execute(
        "INSERT INTO classifications (article_id, topic, depth_score) "
        "VALUES (1, 'agent', 1)"
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO classifications (article_id, topic, depth_score) "
            "VALUES (1, 'rag', 2)"
        )
        conn.commit()
