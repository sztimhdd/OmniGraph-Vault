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
# Test 3 + 4: ingest_from_db -> _classify_full_body wiring
# ---------------------------------------------------------------------------


async def _run_ingest_with_mocked_classify(
    tmp_path: Path, monkeypatch, topic_arg
) -> MagicMock:
    """Drive ``ingest_from_db`` with all expensive paths mocked.

    Returns the MagicMock that replaced ``_classify_full_body`` so callers
    can assert on ``call_args.kwargs['topic_filter']``.
    """
    import batch_ingest_from_spider as bi

    db_path = _seed_classify_db(tmp_path)
    monkeypatch.setattr(bi, "DB_PATH", db_path)

    # Mock _classify_full_body — capture call kwargs.
    fake_classify = AsyncMock(
        return_value={"depth": 3, "topics": ["agent"], "rationale": "ok"}
    )
    monkeypatch.setattr(bi, "_classify_full_body", fake_classify)

    # Mock checkpoint helpers so the article isn't checkpoint-skipped.
    monkeypatch.setattr(bi, "has_stage", lambda *_a, **_k: False)
    monkeypatch.setattr(bi, "get_article_hash", lambda url: "deadbeef" * 2)

    # Mock LightRAG init and the ingest_article call (these come AFTER classify).
    fake_rag = MagicMock()
    fake_rag.finalize_storages = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "ingest_wechat.get_rag", AsyncMock(return_value=fake_rag)
    )
    monkeypatch.setattr(
        bi, "ingest_article", AsyncMock(return_value=(True, 0.1))
    )
    # _drain_pending_vision_tasks is awaited inside the finally block.
    monkeypatch.setattr(
        bi, "_drain_pending_vision_tasks", AsyncMock(return_value=None)
    )

    # Mock the BODY-01 pre-scrape (article body is already non-NULL in seed,
    # but defensive — scrape_url should never be reached).
    monkeypatch.setattr(
        "lib.scraper.scrape_url",
        AsyncMock(side_effect=AssertionError("scrape_url should not be called")),
    )

    # Drive ingest_from_db.
    await bi.ingest_from_db(
        topic=topic_arg,
        min_depth=1,
        dry_run=False,
        max_articles=1,
    )

    return fake_classify


@pytest.mark.asyncio
async def test_ingest_from_db_passes_list_topic_through(tmp_path, monkeypatch):
    """Test 3: ingest_from_db(topic=['agent']) reaches _classify_full_body.

    Asserts ``_classify_full_body.call_args.kwargs['topic_filter'] == ['agent']``.
    """
    fake_classify = await _run_ingest_with_mocked_classify(
        tmp_path, monkeypatch, topic_arg=["agent"]
    )

    assert fake_classify.await_count == 1
    assert fake_classify.call_args.kwargs["topic_filter"] == ["agent"]


@pytest.mark.asyncio
async def test_ingest_from_db_converts_str_topic_to_list(tmp_path, monkeypatch):
    """Test 4: ingest_from_db(topic='agent') => topic_filter=['agent'] (str -> list).

    The ingest_from_db function normalizes ``topic: str | list`` to ``topics: list``
    at line 1341; this test confirms the str input survives the normalization
    and reaches _classify_full_body as a single-element list.
    """
    fake_classify = await _run_ingest_with_mocked_classify(
        tmp_path, monkeypatch, topic_arg="agent"
    )

    assert fake_classify.await_count == 1
    assert fake_classify.call_args.kwargs["topic_filter"] == ["agent"]
