"""Quick task 260506-en4: topic_filter wiring assertions (mock-only).

Verifies the 4-link wiring chain for the CV-tag regression fix:

  ingest_from_db(topic=...) -> _classify_full_body(topic_filter=...)
                              -> _build_fullbody_prompt(topic_filter=...)
                              -> prompt contains user-specified keyword hint

All tests are mock-only: no live network, no live DB, no real LightRAG init.
Tests 1 + 2 use the REAL ``_build_fullbody_prompt`` so they assert on actual
prompt-text behavior. Tests 3 + 4 mock ``_classify_full_body`` to capture
kwargs without exercising scrape / DB / ingest paths.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Topic-hint marker text used by ``batch_classify_kol._build_fullbody_prompt``
# when ``topic_filter`` is non-empty. Source: batch_classify_kol.py:247.
TOPIC_HINT_MARKER = "filtering by topics:"


@pytest.fixture(autouse=True)
def _deepseek_key(monkeypatch):
    """Satisfy module-level DEEPSEEK_API_KEY checks."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")


def _seed_classify_db(tmp_path: Path) -> Path:
    """Minimal schema + seeded rows for ``ingest_from_db`` SELECT.

    The SELECT (``_build_topic_filter_query``) joins articles -> accounts,
    LEFT JOINs classifications, anti-joins ingestions. We seed enough rows
    so the SELECT returns exactly 1 article whose classification topic is
    NULL (so the IS NULL branch matches and topic_filter is irrelevant
    for selection — what we're testing is the THREADING into _classify_full_body,
    not the SELECT itself).
    """
    db_path = tmp_path / "test_topic_hint.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY,
            name TEXT
        );
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            account_id INTEGER,
            url TEXT,
            title TEXT,
            body TEXT,
            digest TEXT
        );
        CREATE TABLE classifications (
            article_id INTEGER,
            topic TEXT,
            depth_score INTEGER,
            depth INTEGER,
            topics TEXT,
            rationale TEXT,
            reason TEXT,
            relevant INTEGER,
            classified_at TEXT
        );
        CREATE TABLE ingestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER,
            status TEXT,
            ingested_at TEXT
        );
        INSERT INTO accounts (id, name) VALUES (1, 'kol_acct');
        INSERT INTO articles (id, account_id, url, title, body, digest)
        VALUES (1, 1, 'https://mp.weixin.qq.com/s/test', 'Test article',
                'non-empty body', 'a digest');
        """
    )
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Test 1 + 2: _classify_full_body -> _build_fullbody_prompt wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_topic_filter_none_no_hint_in_prompt(monkeypatch):
    """Test 1: topic_filter=None (default) => no keyword hint in prompt.

    Backward-compatibility check. Uses the REAL ``_build_fullbody_prompt`` so
    the assertion exercises the actual prompt-builder code path.
    """
    import batch_ingest_from_spider as bi

    captured: dict = {}

    def fake_call(prompt, _api_key):
        captured["prompt"] = prompt
        return {"depth": 2, "topics": ["X"], "rationale": "ok"}

    monkeypatch.setattr(
        "batch_classify_kol._call_deepseek_fullbody", fake_call
    )

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE articles (id INTEGER PRIMARY KEY, body TEXT);
        CREATE TABLE classifications (
            article_id INTEGER, topic TEXT, depth_score INTEGER,
            depth INTEGER, topics TEXT, rationale TEXT, relevant INTEGER,
            PRIMARY KEY (article_id, topic)
        );
        INSERT INTO articles (id, body) VALUES (1, 'sample body');
        """
    )

    result = await bi._classify_full_body(
        conn=conn,
        article_id=1,
        url="https://mp.weixin.qq.com/s/test",
        title="t",
        body="sample body",
        api_key="dummy",
    )

    assert result is not None
    assert "prompt" in captured
    assert TOPIC_HINT_MARKER not in captured["prompt"]


@pytest.mark.asyncio
async def test_topic_filter_list_injects_hint_into_prompt(monkeypatch):
    """Test 2: topic_filter=['agent','harness'] => hint text + keywords in prompt."""
    import batch_ingest_from_spider as bi

    captured: dict = {}

    def fake_call(prompt, _api_key):
        captured["prompt"] = prompt
        return {"depth": 3, "topics": ["agent"], "rationale": "deep"}

    monkeypatch.setattr(
        "batch_classify_kol._call_deepseek_fullbody", fake_call
    )

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE articles (id INTEGER PRIMARY KEY, body TEXT);
        CREATE TABLE classifications (
            article_id INTEGER, topic TEXT, depth_score INTEGER,
            depth INTEGER, topics TEXT, rationale TEXT, relevant INTEGER,
            PRIMARY KEY (article_id, topic)
        );
        INSERT INTO articles (id, body) VALUES (1, 'sample body');
        """
    )

    result = await bi._classify_full_body(
        conn=conn,
        article_id=1,
        url="https://mp.weixin.qq.com/s/test",
        title="t",
        body="sample body",
        api_key="dummy",
        topic_filter=["agent", "harness"],
    )

    assert result is not None
    assert "prompt" in captured
    assert TOPIC_HINT_MARKER in captured["prompt"]
    assert '"agent"' in captured["prompt"]
    assert '"harness"' in captured["prompt"]


# ---------------------------------------------------------------------------
# Tests 3+4 removed in Quick 260507-lai (v3.5 Ingest Refactor foundation).
#
# They asserted that ``ingest_from_db`` routes the topic argument into
# ``_classify_full_body(topic_filter=...)``. The v3.5 foundation removes that
# call from the ingest loop entirely (placeholder Layer 1/2 filters in
# ``lib.article_filter`` replace the classify gate). The remaining tests in
# this file still validate the ``_classify_full_body`` function's own
# behaviour (signature + prompt construction); the function body is retained
# even though the ingest loop no longer calls it.
# ---------------------------------------------------------------------------
