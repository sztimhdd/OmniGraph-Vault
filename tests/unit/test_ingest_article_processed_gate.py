"""Quick 260510-h09: PROCESSED-gate hot-fix unit tests.

Targets the new ``ingest_wechat._verify_doc_processed_or_raise`` helper that
replaces the previously-silent log+skip verification path. The helper now
retries with backoff and RAISES ``RuntimeError`` on terminal failure so the
outer ``batch_ingest_from_spider.ingest_article`` except path catches and
marks ``ingestions.status='failed'`` (mig 009 retry pool re-queues next cron).

All tests pass ``backoff_s=0.0`` to skip real ``asyncio.sleep`` waits — keeps
the suite fast (well under 1s) and lets us assert exact call counts deterministically.

Mock-only: no live LightRAG, no live network. Mocks ``rag.aget_docs_by_ids``
directly with ``AsyncMock`` and controls returns via ``side_effect``.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest


# DEEPSEEK_API_KEY=dummy satisfies the eager import at lib/__init__.py
# (Phase 5 cross-coupling FLAG 2). Set via fixture rather than top-level
# os.environ to keep test isolation explicit.
@pytest.fixture(autouse=True)
def _deepseek_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")


# Import is lazy inside the fixture so DEEPSEEK_API_KEY is set before
# any transitive ``from lib import ...`` happens.
@pytest.fixture
def helper_and_const():
    """Yield (helper_fn, MAX_RETRIES_const) tuple.

    Imported here (not at module top) so the autouse env fixture runs first.
    """
    from ingest_wechat import (
        _verify_doc_processed_or_raise,
        PROCESSED_VERIFY_MAX_RETRIES,
    )
    return _verify_doc_processed_or_raise, PROCESSED_VERIFY_MAX_RETRIES


def _mk_rag(side_effect):
    """Build a MagicMock rag whose ``aget_docs_by_ids`` is an AsyncMock.

    side_effect can be a list of return values OR a list with mixed
    Exception instances + return values. AsyncMock with list side_effect
    consumes one entry per call.
    """
    rag = MagicMock()
    rag.aget_docs_by_ids = AsyncMock(side_effect=side_effect)
    return rag


# ---------------------------------------------------------------------------
# Test 1 — happy path, single attempt, immediate PROCESSED
# ---------------------------------------------------------------------------


async def test_processed_verification_passes_first_try(helper_and_const):
    helper, _ = helper_and_const
    doc_id = "doc-aaa"
    rag = _mk_rag([{doc_id: {"status": "PROCESSED"}}])

    # No raise expected.
    await helper(rag, doc_id, backoff_s=0.0)

    assert rag.aget_docs_by_ids.await_count == 1
    rag.aget_docs_by_ids.assert_awaited_with([doc_id])


# ---------------------------------------------------------------------------
# Test 2 — eventual promotion: pending → pending → PROCESSED
# ---------------------------------------------------------------------------


async def test_processed_promotes_after_retry(helper_and_const):
    helper, _ = helper_and_const
    doc_id = "doc-bbb"
    rag = _mk_rag([
        {doc_id: {"status": "processing"}},   # attempt 1
        {doc_id: {"status": "processing"}},   # attempt 2
        {doc_id: {"status": "processed"}},    # attempt 3 — succeeds
    ])

    await helper(rag, doc_id, max_retries=3, backoff_s=0.0)

    assert rag.aget_docs_by_ids.await_count == 3


# ---------------------------------------------------------------------------
# Test 3 — never promotes: production regression case
# ---------------------------------------------------------------------------


async def test_never_promotes_raises_runtime_error(helper_and_const):
    helper, _ = helper_and_const
    doc_id = "doc-ccc"
    rag = _mk_rag([
        {doc_id: {"status": "pending"}},
        {doc_id: {"status": "pending"}},
        {doc_id: {"status": "pending"}},
    ])

    with pytest.raises(RuntimeError, match="PROCESSED verification failed") as exc_info:
        await helper(rag, doc_id, max_retries=3, backoff_s=0.0)

    msg = str(exc_info.value)
    # Sanity-check the error message carries actionable diagnostics.
    assert "pending" in msg
    assert "3" in msg  # max_retries count
    assert doc_id in msg
    assert rag.aget_docs_by_ids.await_count == 3


# ---------------------------------------------------------------------------
# Test 4 — doc absent from status response
# ---------------------------------------------------------------------------


async def test_doc_missing_from_status_raises(helper_and_const):
    helper, _ = helper_and_const
    doc_id = "doc-ddd"
    # Empty dict means the doc is not present in the response.
    rag = _mk_rag([{}, {}, {}])

    with pytest.raises(RuntimeError, match="PROCESSED verification failed"):
        await helper(rag, doc_id, max_retries=3, backoff_s=0.0)

    assert rag.aget_docs_by_ids.await_count == 3


# ---------------------------------------------------------------------------
# Test 5 — aget_docs raises then recovers
# ---------------------------------------------------------------------------


async def test_aget_docs_raises_then_recovers(helper_and_const):
    helper, _ = helper_and_const
    doc_id = "doc-eee"
    # AsyncMock with mixed Exception+dict side_effect: Exception instances
    # raise; non-Exception values return.
    rag = _mk_rag([
        Exception("network blip"),
        {doc_id: {"status": "processed"}},
    ])

    # Expected: attempt 1 raises (caught), attempt 2 returns success → no raise.
    await helper(rag, doc_id, max_retries=3, backoff_s=0.0)

    assert rag.aget_docs_by_ids.await_count == 2


# ---------------------------------------------------------------------------
# Test 6 — outer integration contract (RuntimeError → success=False)
# ---------------------------------------------------------------------------
#
# Verifies the full outer-catches-inner contract: when the inner helper raises
# RuntimeError (post-Hot-fix behaviour), the outer
# ``batch_ingest_from_spider.ingest_article`` returns ``(False, wall)`` rather
# than letting the exception propagate. This is the load-bearing contract that
# closes the 2026-05-10 ainsert async-pipeline race — without it, mig 009
# retry pool would never re-queue.
#
# This test mocks ``ingest_wechat.ingest_article`` (the function the outer
# awaits) to raise RuntimeError, then drives the outer's wait_for path.


async def test_outer_catches_inner_runtime_error_returns_failed(monkeypatch):
    """Outer ingest_article must return (False, wall) when inner raises."""
    import batch_ingest_from_spider as bif

    async def _fake_inner_ingest(url, *, source="wechat", rag=None):
        raise RuntimeError(
            "post-ainsert PROCESSED verification failed for doc_id=test"
        )

    # Replace the inner ingest at the import location used by the outer.
    import ingest_wechat
    monkeypatch.setattr(ingest_wechat, "ingest_article", _fake_inner_ingest)
    # The outer also calls get_pending_doc_id on TimeoutError; not relevant
    # here (we raise RuntimeError, not TimeoutError) but make sure attribute
    # access in the rollback branch wouldn't crash if the wrong branch is
    # taken — None signals "no rollback needed".
    monkeypatch.setattr(
        ingest_wechat, "get_pending_doc_id", lambda h: None, raising=False
    )

    rag = MagicMock()
    rag.adelete_by_doc_id = AsyncMock()

    success, wall, doc_confirmed = await bif.ingest_article(
        source="wechat",
        url="https://example.com/test",
        dry_run=False,
        rag=rag,
        effective_timeout=60,
    )

    assert success is False
    assert wall >= 0.0  # Sanity: wall_clock recorded even on failure.
    assert doc_confirmed is False  # Inner raised RuntimeError → outer's generic Exception branch → doc_confirmed=False
