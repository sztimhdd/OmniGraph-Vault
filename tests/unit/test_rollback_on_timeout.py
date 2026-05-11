"""D-09.05 / D-09.06 (STATE-02 / STATE-03): rollback-on-timeout + idempotency.

All tests mock LightRAG so no real embeddings or LLM calls occur. Exercises the
observable contract: on ``asyncio.TimeoutError`` in the outer ``wait_for``, the
orchestrator calls ``rag.adelete_by_doc_id(doc_id)`` exactly once.

Phase 19 SCH-02: tracker key unified to SHA-256[:16] via lib.checkpoint.get_article_hash
(matches batch_ingest_from_spider.py:275 canonical hash). The doc_id VALUE stored in
the tracker is still f"wechat_{md5_hash}" (LightRAG / image-dir namespace unchanged).
"""
from __future__ import annotations

import asyncio
import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _deepseek_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")


@pytest.fixture
def _fake_rag():
    rag = MagicMock()
    rag.ainsert = AsyncMock()
    rag.adelete_by_doc_id = AsyncMock()
    return rag


@pytest.mark.asyncio
async def test_timeout_triggers_adelete_by_doc_id(monkeypatch, _fake_rag):
    """STATE-02: asyncio.wait_for timeout → rag.adelete_by_doc_id called once."""
    from lib.checkpoint import get_article_hash

    url = "https://test.example/abc123"
    # Phase 19 SCH-02: tracker key is SHA-256[:16]; doc_id value keeps MD5[:10].
    tracker_hash = get_article_hash(url)
    md5_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    expected_doc_id = f"wechat_{md5_hash}"

    # Mock ingest_wechat.ingest_article so it simulates in-flight ainsert
    # that the orchestrator will cancel via wait_for. The mock registers the
    # pending doc_id (matching what the real implementation does) then sleeps
    # beyond the budget. The real implementation clears the tracker only on
    # success, so on cancellation the orchestrator's error path can read it.
    import ingest_wechat

    async def _slow_ingest(_url, *, source="wechat", rag=None):
        ingest_wechat._register_pending_doc_id(tracker_hash, expected_doc_id)
        await asyncio.sleep(10)

    monkeypatch.setattr(ingest_wechat, "ingest_article", _slow_ingest)

    # Short budget to force TimeoutError.
    import batch_ingest_from_spider as bi

    monkeypatch.setattr(bi, "_SINGLE_CHUNK_FLOOR_S", 0.1)

    # Phase 17: ingest_article now returns (success, wall_clock_seconds).
    ok, _wall = await bi.ingest_article(source='wechat', url=url, dry_run=False, rag=_fake_rag)

    assert ok is False
    _fake_rag.adelete_by_doc_id.assert_awaited_once_with(expected_doc_id)


@pytest.mark.asyncio
async def test_successful_ingest_does_not_call_adelete(monkeypatch, _fake_rag):
    """Happy path: ainsert completes → no rollback."""
    from lib.checkpoint import get_article_hash

    url = "https://test.example/ok"
    import ingest_wechat

    async def _fast_ingest(_url, *, source="wechat", rag=None):
        # Simulate successful ainsert — register AND clear.
        tracker_hash = get_article_hash(_url)
        md5_hash = hashlib.md5(_url.encode()).hexdigest()[:10]
        doc_id = f"wechat_{md5_hash}"
        ingest_wechat._register_pending_doc_id(tracker_hash, doc_id)
        await asyncio.sleep(0)
        ingest_wechat._clear_pending_doc_id(tracker_hash)

    monkeypatch.setattr(ingest_wechat, "ingest_article", _fast_ingest)

    import batch_ingest_from_spider as bi

    # Phase 17: ingest_article now returns (success, wall_clock_seconds).
    ok, _wall = await bi.ingest_article(source='wechat', url=url, dry_run=False, rag=_fake_rag)

    assert ok is True
    _fake_rag.adelete_by_doc_id.assert_not_called()


@pytest.mark.asyncio
async def test_rollback_failure_is_logged_not_raised(monkeypatch, _fake_rag, caplog):
    """STATE-02 defensive: if adelete_by_doc_id raises, orchestrator logs + returns False."""
    import logging
    from lib.checkpoint import get_article_hash

    caplog.set_level(logging.ERROR, logger="batch_ingest_from_spider")

    url = "https://test.example/fail-rollback"
    tracker_hash = get_article_hash(url)
    md5_hash = hashlib.md5(url.encode()).hexdigest()[:10]

    import ingest_wechat

    async def _slow_ingest(_url, *, source="wechat", rag=None):
        ingest_wechat._register_pending_doc_id(tracker_hash, f"wechat_{md5_hash}")
        await asyncio.sleep(10)

    monkeypatch.setattr(ingest_wechat, "ingest_article", _slow_ingest)
    _fake_rag.adelete_by_doc_id.side_effect = RuntimeError("storage corrupt")

    import batch_ingest_from_spider as bi

    monkeypatch.setattr(bi, "_SINGLE_CHUNK_FLOOR_S", 0.1)

    # No exception should propagate.
    # Phase 17: ingest_article now returns (success, wall_clock_seconds).
    ok, _wall = await bi.ingest_article(source='wechat', url=url, dry_run=False, rag=_fake_rag)
    assert ok is False
    # And log message contains the diagnostic.
    assert any("Rollback FAILED" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_idempotent_reingest_after_rollback(monkeypatch, _fake_rag):
    """STATE-03: rollback + re-ingest is idempotent — ainsert called, same doc_id."""
    from lib.checkpoint import get_article_hash

    url = "https://test.example/retry"
    tracker_hash = get_article_hash(url)
    md5_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    expected_doc_id = f"wechat_{md5_hash}"

    import ingest_wechat

    call_count = {"n": 0}

    async def _first_slow_then_fast(_url, *, source="wechat", rag=None):
        call_count["n"] += 1
        ingest_wechat._register_pending_doc_id(tracker_hash, expected_doc_id)
        if call_count["n"] == 1:
            await asyncio.sleep(10)  # forced timeout
        else:
            # Second call: simulate successful ainsert.
            await rag.ainsert(f"# {_url}\n...", ids=[expected_doc_id])
            ingest_wechat._clear_pending_doc_id(tracker_hash)

    monkeypatch.setattr(ingest_wechat, "ingest_article", _first_slow_then_fast)

    import batch_ingest_from_spider as bi

    monkeypatch.setattr(bi, "_SINGLE_CHUNK_FLOOR_S", 0.1)

    # First call: timeout → rollback.
    # Phase 17: ingest_article now returns (success, wall_clock_seconds).
    ok1, _wall1 = await bi.ingest_article(source='wechat', url=url, dry_run=False, rag=_fake_rag)
    assert ok1 is False
    _fake_rag.adelete_by_doc_id.assert_awaited_once_with(expected_doc_id)

    # Reset budget for the second call — fast path.
    monkeypatch.setattr(bi, "_SINGLE_CHUNK_FLOOR_S", 30)

    # Second call: succeeds.
    ok2, _wall2 = await bi.ingest_article(source='wechat', url=url, dry_run=False, rag=_fake_rag)
    assert ok2 is True

    # adelete_by_doc_id was called EXACTLY once (from the first timeout only).
    # ainsert was called EXACTLY once with ids=[expected_doc_id] (from the second call).
    assert _fake_rag.adelete_by_doc_id.await_count == 1
    _fake_rag.ainsert.assert_awaited_once()
    kwargs = _fake_rag.ainsert.await_args.kwargs
    assert kwargs.get("ids") == [expected_doc_id]
