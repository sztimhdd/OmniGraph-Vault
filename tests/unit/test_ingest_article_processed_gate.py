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
    # quick-260511-lmc: two entries needed — initial poll + stable re-poll.
    # After seeing 'processed' the helper sleeps STABLE_VERIFY_DELAY_S then
    # re-polls to confirm stability before returning.
    rag = _mk_rag([
        {doc_id: {"status": "PROCESSED"}},  # initial poll
        {doc_id: {"status": "PROCESSED"}},  # stable re-poll
    ])

    # No raise expected.
    await helper(rag, doc_id, backoff_s=0.0, stable_delay_s=0.0)

    # 2 calls: initial poll + stable re-poll
    assert rag.aget_docs_by_ids.await_count == 2
    rag.aget_docs_by_ids.assert_awaited_with([doc_id])


# ---------------------------------------------------------------------------
# Test 2 — eventual promotion: pending → pending → PROCESSED
# ---------------------------------------------------------------------------


async def test_processed_promotes_after_retry(helper_and_const):
    helper, _ = helper_and_const
    doc_id = "doc-bbb"
    # quick-260511-lmc: 4th entry needed for stable re-poll after the 3rd (processed).
    rag = _mk_rag([
        {doc_id: {"status": "processing"}},  # attempt 0
        {doc_id: {"status": "processing"}},  # attempt 1
        {doc_id: {"status": "processed"}},   # attempt 2 — initial sees processed
        {doc_id: {"status": "processed"}},   # attempt 2 — stable re-poll confirms
    ])

    await helper(rag, doc_id, max_retries=3, backoff_s=0.0, stable_delay_s=0.0)

    # 4 calls: 2 processing + 1 processed (initial) + 1 processed (stable re-poll)
    assert rag.aget_docs_by_ids.await_count == 4


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
    # quick-260511-lmc: 3rd entry needed for stable re-poll after processed on attempt 1.
    rag = _mk_rag([
        Exception("network blip"),         # attempt 0 — outer try/except catches
        {doc_id: {"status": "processed"}},  # attempt 1 — initial poll returns processed
        {doc_id: {"status": "processed"}},  # attempt 1 — stable re-poll confirms
    ])

    # Expected: attempt 0 raises (caught), attempt 1 returns processed + stable re-poll confirms → no raise.
    await helper(rag, doc_id, max_retries=3, backoff_s=0.0, stable_delay_s=0.0)

    # 3 calls: 1 exception + 1 processed (initial) + 1 processed (stable re-poll)
    assert rag.aget_docs_by_ids.await_count == 3


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


# ---------------------------------------------------------------------------
# Tests 7-11 — TOCTOU race: stable-state + error_msg guard
# (quick-260511-lmc)
# ---------------------------------------------------------------------------
#
# These tests verify the combined Option C guard added in quick-260511-lmc:
#   (B) error_msg guard: if 'processed' AND error_msg non-empty → continue retry
#   (A) stable re-poll: if 'processed' AND error_msg empty → sleep STABLE_VERIFY_DELAY_S,
#       re-fetch, confirm still 'processed' + no error_msg, then return
#
# All tests pass both backoff_s=0.0 and stable_delay_s=0.0 to avoid real sleeps.
# For stable re-poll tests, the mock side_effect encodes BOTH the initial poll
# result AND the stable re-poll result as consecutive calls to aget_docs_by_ids.
# ---------------------------------------------------------------------------


@pytest.fixture
def helper_toctou():
    """Import helper + DocStatus enum for TOCTOU tests."""
    from ingest_wechat import _verify_doc_processed_or_raise
    try:
        from lightrag.base import DocStatus
    except ImportError:
        # Fallback: create a minimal enum-like for the test if lightrag not installed
        from enum import Enum
        class DocStatus(str, Enum):
            PROCESSED = "processed"
    return _verify_doc_processed_or_raise, DocStatus


async def test_processed_with_error_msg_continues_retry(helper_toctou):
    """Test A: status='processed' + error_msg non-empty → retry loop → RuntimeError.

    Covers 2026-05-11 mystery rows: DeepSeek 402 causes LightRAG to write
    FAILED+error_msg but a prior stale 'processed' was already in doc_status.
    The error_msg guard must treat this as a failure, not a success.
    """
    helper, _ = helper_toctou
    doc_id = "doc-toctou-a"
    # Every poll returns 'processed' with error_msg set — should never return True
    rag = _mk_rag([
        {doc_id: {"status": "processed", "error_msg": "Insufficient Balance"}},
        {doc_id: {"status": "processed", "error_msg": "Insufficient Balance"}},
        {doc_id: {"status": "processed", "error_msg": "Insufficient Balance"}},
    ])

    with pytest.raises(RuntimeError, match="PROCESSED verification failed") as exc_info:
        await helper(rag, doc_id, max_retries=3, backoff_s=0.0, stable_delay_s=0.0)

    msg = str(exc_info.value)
    assert "processed-with-error" in msg
    # Helper must NOT have returned True — it consumed all 3 retries
    assert rag.aget_docs_by_ids.await_count == 3


async def test_processed_stable_recheck_confirms_ok(helper_toctou):
    """Test B: 'processed' + no error_msg → stable re-poll → still 'processed' + no error_msg → return.

    Happy path for the stable-state re-poll: two consecutive calls both show
    'processed' with no error_msg, so the helper confirms stability and returns.
    """
    helper, _ = helper_toctou
    doc_id = "doc-toctou-b"
    # Call 1: initial poll → processed, no error_msg
    # Call 2: stable re-poll → still processed, no error_msg → return True
    rag = _mk_rag([
        {doc_id: {"status": "processed", "error_msg": None}},   # initial poll
        {doc_id: {"status": "processed", "error_msg": None}},   # stable re-poll
    ])

    # Must NOT raise — stable check confirms genuine success
    await helper(rag, doc_id, max_retries=3, backoff_s=0.0, stable_delay_s=0.0)

    # Exactly 2 calls: initial poll + stable re-poll
    assert rag.aget_docs_by_ids.await_count == 2


async def test_processed_stable_recheck_sees_failed(helper_toctou):
    """Test C: 'processed' + no error_msg → stable re-poll → 'failed' → retry loop → RuntimeError.

    TOCTOU flip: first poll catches a brief PROCESSED window, stable re-poll
    sees the true FAILED state. Must continue retry loop rather than returning.
    """
    helper, _ = helper_toctou
    doc_id = "doc-toctou-c"
    # Each attempt: (initial poll → processed) then (stable re-poll → failed)
    # 3 attempts × 2 calls each = 6 total
    rag = _mk_rag([
        {doc_id: {"status": "processed", "error_msg": None}},      # attempt 0 initial
        {doc_id: {"status": "failed", "error_msg": "error X"}},    # attempt 0 stable re-poll
        {doc_id: {"status": "processed", "error_msg": None}},      # attempt 1 initial
        {doc_id: {"status": "failed", "error_msg": "error X"}},    # attempt 1 stable re-poll
        {doc_id: {"status": "processed", "error_msg": None}},      # attempt 2 initial
        {doc_id: {"status": "failed", "error_msg": "error X"}},    # attempt 2 stable re-poll
    ])

    with pytest.raises(RuntimeError, match="PROCESSED verification failed"):
        await helper(rag, doc_id, max_retries=3, backoff_s=0.0, stable_delay_s=0.0)

    # Must have consumed all 6 calls (3 initial + 3 stable re-polls)
    assert rag.aget_docs_by_ids.await_count == 6


async def test_processed_stable_recheck_sees_error_msg(helper_toctou):
    """Test D: 'processed' + no error_msg → stable re-poll → 'processed' + error_msg → retry → RuntimeError.

    Combined TOCTOU: stable re-poll shows 'processed' but error_msg is now set —
    LightRAG wrote error_msg between the first poll and the stable re-poll.
    """
    helper, _ = helper_toctou
    doc_id = "doc-toctou-d"
    # Each attempt: (initial → processed, no error) → (stable → processed, with error)
    rag = _mk_rag([
        {doc_id: {"status": "processed", "error_msg": None}},                       # attempt 0 initial
        {doc_id: {"status": "processed", "error_msg": "Insufficient Balance"}},     # attempt 0 stable re-poll
        {doc_id: {"status": "processed", "error_msg": None}},                       # attempt 1 initial
        {doc_id: {"status": "processed", "error_msg": "Insufficient Balance"}},     # attempt 1 stable re-poll
        {doc_id: {"status": "processed", "error_msg": None}},                       # attempt 2 initial
        {doc_id: {"status": "processed", "error_msg": "Insufficient Balance"}},     # attempt 2 stable re-poll
    ])

    with pytest.raises(RuntimeError, match="PROCESSED verification failed"):
        await helper(rag, doc_id, max_retries=3, backoff_s=0.0, stable_delay_s=0.0)

    assert rag.aget_docs_by_ids.await_count == 6


async def test_processed_enum_member_with_error_msg(helper_toctou):
    """Test E: DocStatus.PROCESSED enum member (not string) + error_msg set → error_msg guard fires.

    Validates that the error_msg guard works with dataclass-like entries (object
    attributes) not just dict entries. Covers future LightRAG SDK versions that
    return typed DocProcessingStatus objects instead of dicts.
    """
    helper, DocStatus = helper_toctou
    doc_id = "doc-toctou-e"

    # Build a MagicMock entry that looks like a DocProcessingStatus dataclass object
    mock_entry = MagicMock()
    mock_entry.status = DocStatus.PROCESSED  # enum member, not string
    mock_entry.error_msg = "Insufficient Balance"

    rag = _mk_rag([
        {doc_id: mock_entry},
        {doc_id: mock_entry},
        {doc_id: mock_entry},
    ])

    with pytest.raises(RuntimeError, match="PROCESSED verification failed") as exc_info:
        await helper(rag, doc_id, max_retries=3, backoff_s=0.0, stable_delay_s=0.0)

    msg = str(exc_info.value)
    assert "processed-with-error" in msg
    assert rag.aget_docs_by_ids.await_count == 3
