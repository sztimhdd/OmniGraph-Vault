"""Regression test for the 2026-05-07 CV mass-classify bug.

Quick: 260507-ent (2026-05-07)

Bug:
    batch_classify_kol.py runs a multi-topic CLI loop:
        for topic in ["Agent", "LLM", "RAG", "NLP", "CV"]:
            INSERT INTO classifications (article_id, topic, ...) VALUES (...)

    Quick 260506-se5 changed the conflict target from
    ``ON CONFLICT(article_id, topic) DO UPDATE SET ...``
    to
    ``ON CONFLICT(article_id) DO UPDATE SET topic=excluded.topic, ...``
    and added a single-column UNIQUE INDEX on article_id (migration 004).

    This made every iteration of the loop overwrite the previous row's
    ``topic`` field instead of inserting a new (article_id, topic) row.
    Only the last topic in the loop survived — at 2026-05-07 08:29 ADT
    the cron mass-classified all 653 articles as 'CV' (the last topic in
    the production cron's --topic list), and downstream ingest filtered
    them all out.

These tests verify that under the post-migration-005 schema:
    1. Multi-topic INSERT loop creates ONE row per (article_id, topic) —
       no overwrite of the topic field.
    2. Re-running the loop on the same articles is an idempotent UPSERT
       (depth_score / reason updated, row count unchanged).

We use stdlib-only sqlite3 + :memory: so the tests run anywhere with no
DEEPSEEK_API_KEY import-time coupling and no external state. The
``classifications`` DDL is copied verbatim from
batch_scan_kol.py:101-111 (matches CLAUDE.md
"critical_findings_from_codebase" — do NOT import from batch_scan_kol.py
to avoid the DEEPSEEK_API_KEY import-time coupling).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# DDL copied verbatim from batch_scan_kol.py:101-111.
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

MIGRATION_004_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "004_classifications_unique_article_id.sql"
)
MIGRATION_005_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "005_drop_article_id_unique_index.sql"
)


# Conflict target string MUST match production. Tests in this file are
# the regression contract for the multi-topic loop.
UPSERT_SQL = """
    INSERT INTO classifications
        (article_id, topic, depth_score, relevant, excluded, reason)
    VALUES (?, ?, ?, ?, 0, ?)
    ON CONFLICT(article_id, topic) DO UPDATE SET
        depth_score=excluded.depth_score,
        relevant=excluded.relevant,
        excluded=0,
        reason=excluded.reason
"""


def _setup_db_post_migration_005() -> sqlite3.Connection:
    """Construct a DB in the schema state after migrations 004 + 005 ran.

    Migration 004 added a UNIQUE INDEX on article_id; migration 005 drops it.
    The table-level UNIQUE(article_id, topic) survives both — that constraint
    is what the new ON CONFLICT(article_id, topic) clause binds to.
    """
    conn = sqlite3.connect(":memory:")
    conn.executescript(CLASSIFICATIONS_DDL)
    conn.executescript(MIGRATION_004_PATH.read_text(encoding="utf-8"))
    conn.executescript(MIGRATION_005_PATH.read_text(encoding="utf-8"))
    for aid in (1, 2):
        conn.execute("INSERT INTO articles (id) VALUES (?)", (aid,))
    conn.commit()
    return conn


def test_multi_topic_loop_creates_one_row_per_topic() -> None:
    """Cron's --topic Agent --topic LLM ... --topic CV loop produces N rows
    per article, not 1 row with the last topic."""
    conn = _setup_db_post_migration_005()
    topics = ["Agent", "LLM", "RAG", "NLP", "CV"]

    for t in topics:
        conn.execute(UPSERT_SQL, (1, t, 2, 1, f"matches {t}"))
    conn.commit()

    rows = conn.execute(
        "SELECT topic FROM classifications WHERE article_id=1 ORDER BY topic"
    ).fetchall()
    assert len(rows) == len(topics), (
        f"multi-topic loop must create {len(topics)} rows for article_id=1, "
        f"got {len(rows)}; topics actually present: {[r[0] for r in rows]}"
    )
    assert {r[0] for r in rows} == set(topics), (
        "every topic in the loop must be present as its own row "
        f"(got {[r[0] for r in rows]})"
    )


def test_rerun_loop_is_idempotent_upsert() -> None:
    """Running the same multi-topic loop twice does not duplicate rows;
    UPSERT updates non-PK columns in place."""
    conn = _setup_db_post_migration_005()
    topics = ["Agent", "LLM", "RAG"]

    # First pass.
    for t in topics:
        conn.execute(UPSERT_SQL, (1, t, 1, 1, f"first pass {t}"))
    conn.commit()

    pre_count = conn.execute(
        "SELECT COUNT(*) FROM classifications WHERE article_id=1"
    ).fetchone()[0]
    assert pre_count == len(topics)

    # Second pass with updated depth + reason.
    for t in topics:
        conn.execute(UPSERT_SQL, (1, t, 3, 1, f"second pass {t}"))
    conn.commit()

    post_count = conn.execute(
        "SELECT COUNT(*) FROM classifications WHERE article_id=1"
    ).fetchone()[0]
    assert post_count == len(topics), (
        "second pass of same topics must UPSERT, not duplicate"
    )

    # Verify update happened: depth_score is the second-pass value.
    rows = conn.execute(
        "SELECT topic, depth_score, reason FROM classifications "
        "WHERE article_id=1 ORDER BY topic"
    ).fetchall()
    for topic, depth_score, reason in rows:
        assert depth_score == 3, f"second-pass depth_score not applied for {topic}"
        assert reason == f"second pass {topic}", (
            f"second-pass reason not applied for {topic}"
        )


def test_multi_article_multi_topic_isolation() -> None:
    """Inserting topics for article 1 must not affect article 2."""
    conn = _setup_db_post_migration_005()

    for t in ["Agent", "LLM"]:
        conn.execute(UPSERT_SQL, (1, t, 2, 1, f"a1 {t}"))
    for t in ["RAG"]:
        conn.execute(UPSERT_SQL, (2, t, 3, 1, f"a2 {t}"))
    conn.commit()

    a1_topics = sorted(
        r[0]
        for r in conn.execute(
            "SELECT topic FROM classifications WHERE article_id=1"
        ).fetchall()
    )
    a2_topics = sorted(
        r[0]
        for r in conn.execute(
            "SELECT topic FROM classifications WHERE article_id=2"
        ).fetchall()
    )
    assert a1_topics == ["Agent", "LLM"]
    assert a2_topics == ["RAG"]


def test_migration_005_idempotent() -> None:
    """Running migration 005 twice on the same DB is a no-op (DROP INDEX IF
    EXISTS makes the second run safe)."""
    conn = _setup_db_post_migration_005()
    # Re-applying migration 005 must not raise.
    conn.executescript(MIGRATION_005_PATH.read_text(encoding="utf-8"))
    indexes = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND tbl_name='classifications'"
    ).fetchall()
    assert all("idx_classifications_article_id" not in (i[0] or "") for i in indexes), (
        "migration 005 must leave no idx_classifications_article_id index behind "
        f"(got indexes: {indexes})"
    )
