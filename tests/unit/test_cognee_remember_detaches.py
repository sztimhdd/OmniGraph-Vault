"""Tests COG-02 from Phase 20 REQUIREMENTS.md.

Verifies that cognee_wrapper.remember_article() detaches from the main pipeline:
even if cognee.remember internally takes 10s, the wrapper must return in <100ms.

This test is the COG-02 merge gate per D-20.13. Currently FAILS because
cognee_wrapper.py uses asyncio.wait_for(..., timeout=5.0) which blocks ~5s.
Plan 20-03 D-20.15 refactor (asyncio.create_task wrap) makes it GREEN.
"""
from __future__ import annotations

import asyncio
import time

import pytest


@pytest.mark.asyncio
async def test_remember_returns_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """remember_article returns in <100ms even when cognee.remember sleeps 10s."""
    import cognee_wrapper

    if cognee_wrapper.cognee is None:
        pytest.skip("cognee not importable; skipping detach test")

    async def slow_remember(*args, **kwargs):
        await asyncio.sleep(10.0)
        return None

    monkeypatch.setattr(cognee_wrapper.cognee, "remember", slow_remember)

    t0 = time.perf_counter()
    result = await cognee_wrapper.remember_article(
        title="Test article",
        url="https://example.com/foo",
        entities=["AgentX", "RAG"],
        summary_gist="A short gist.",
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Pinned contract: < 100ms (D-20.13 mock test bound)
    assert elapsed_ms < 100, (
        f"remember_article blocked for {elapsed_ms:.1f}ms (>= 100ms); "
        "Plan 20-03 D-20.15 asyncio.create_task wrap not in place"
    )
    # Wrapper should still return a truthy value (task scheduled successfully)
    assert result is True, f"Expected True (task scheduled), got {result!r}"
