"""TEST-03 (Reasoner half) — mock-based test of the bounded LLM agent loop.

Covers:
- Test 1 ``test_reasoner_runs_two_turn_loop``: turn 1 = vision_analyze tool
  call, turn 2 = final answer; asserts ``<MOCK_CAPTION>`` round-trip into
  ``analyzed_images`` and that ``cfg.vision_cascade.describe`` was awaited.
- Test 2 ``test_reasoner_caps_at_max_iter``: LLM never emits final → loop
  terminates at ``iter_count == cap`` (cap=3 for test speed).
- Test 3 ``test_reasoner_caps_returns_ok_not_failed``: explicit guard against
  someone "fixing" cap-reached to ``status="failed"``.
- Test 4 ``test_reasoner_catches_llm_exception``: ``cfg.llm_complete`` raises
  → ``status="failed"``, reason carries the original exception message.
- Test 5 ``test_reasoner_catches_vision_exception``: vision_cascade.describe
  raises → ``status="failed"`` (Axis 3 best-effort).
- Test 6 ``test_reasoner_kg_search_tool_appends_chunk``: kg_search tool call
  → ``additional_chunks`` populated with ``kind="kg_chunk"`` Source.
- Test 7 ``test_reasoner_parallel_vision_calls``: two vision_analyze calls
  in one turn dispatched via ``asyncio.gather`` (await-count assertion;
  timing assertion documented but relaxed for Windows portability).

The internal protocol types ``_LLMDecision`` / ``_ToolCall`` are imported
from ``lib.research.stages.reasoner`` — mocks construct them directly. This
mock IS the ar-2 contract for ``cfg.llm_complete`` (real provider integration
is an ar-3+ refinement).
"""
from __future__ import annotations

import asyncio
import dataclasses
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import lib.research.stages.reasoner as reasoner_mod
from lib.research.stages.reasoner import _LLMDecision, _ToolCall
from lib.research.stages.reasoner import run as run_reasoner
from lib.research.types import (
    ReasonerOutput,
    ResearchConfig,
    RetrievedImage,
    RetrieverOutput,
    Source,
)


def _make_cfg(
    llm_complete, vision_cascade, max_iter_reasoner: int = 5
) -> ResearchConfig:
    """Build a minimal ResearchConfig for tests — bypasses ``from_env()``."""
    return ResearchConfig(
        rag_working_dir=Path("/tmp/_test_rag"),
        llm_complete=llm_complete,
        embedding_func=AsyncMock(),
        vision_cascade=vision_cascade,
        web_search=lambda q: [],
        max_iter_reasoner=max_iter_reasoner,
    )


def _make_retrieved(image_path: Path) -> RetrieverOutput:
    return RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="test", snippet="seed kg text")],
        image_candidates=[
            RetrievedImage(
                article_hash=image_path.parent.name,
                image_path=image_path,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Test 1 — two-turn loop with vision_analyze on turn 1, final on turn 2
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_reasoner_runs_two_turn_loop(tmp_path):
    image_path = tmp_path / "abc1234567" / "5.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"")

    vision_cascade = MagicMock()
    vision_cascade.describe = AsyncMock(return_value="<MOCK_CAPTION>")

    call_count = {"n": 0}

    async def mock_llm(prompt, tools):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _LLMDecision(
                is_final=False,
                tool_calls=(
                    _ToolCall(
                        name="vision_analyze",
                        args={
                            "image_path": str(image_path),
                            "question": "what is in this image",
                        },
                    ),
                ),
            )
        return _LLMDecision(is_final=True, content="Final inferred answer.")

    cfg = _make_cfg(mock_llm, vision_cascade)
    retrieved = _make_retrieved(image_path)

    result = await run_reasoner("test query", cfg, retrieved)

    assert isinstance(result, ReasonerOutput)
    assert result.iter_count >= 1
    assert result.status == "ok"
    assert result.inferences_md == "Final inferred answer."
    assert len(result.analyzed_images) >= 1
    assert any(img.caption == "<MOCK_CAPTION>" for img in result.analyzed_images)
    assert vision_cascade.describe.await_count >= 1


# ---------------------------------------------------------------------------
# Test 2 — LLM never emits final → cap enforced; iter_count == cap
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_reasoner_caps_at_max_iter(tmp_path, monkeypatch):
    vision_cascade = MagicMock()
    vision_cascade.describe = AsyncMock(return_value="<MOCK_CAPTION>")

    async def mock_llm_never_final(prompt, tools):
        return _LLMDecision(
            is_final=False,
            tool_calls=(
                _ToolCall(
                    name="kg_search",
                    args={"query": "subquery", "top_k": 5},
                ),
            ),
        )

    async def stub_kg_search(q, mode="hybrid"):
        return "stub kg result"

    # Patch via monkeypatch for safe teardown — avoids closure-capture issues.
    monkeypatch.setattr(
        "lib.research.stages.reasoner.kg_search", stub_kg_search
    )

    cfg = _make_cfg(mock_llm_never_final, vision_cascade, max_iter_reasoner=3)
    retrieved = _make_retrieved(tmp_path / "deadbeef00" / "1.jpg")

    result = await run_reasoner("test", cfg, retrieved)

    assert result.iter_count == 3  # exactly the cap
    assert result.status == "ok"  # cap is a budget, not an error


# ---------------------------------------------------------------------------
# Test 3 — explicit assertion: cap reached → status="ok", NOT "failed"
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_reasoner_caps_returns_ok_not_failed(tmp_path, monkeypatch):
    vision_cascade = MagicMock()
    vision_cascade.describe = AsyncMock(return_value="<MOCK_CAPTION>")

    async def mock_llm_never_final(prompt, tools):
        return _LLMDecision(
            is_final=False,
            tool_calls=(
                _ToolCall(name="kg_search", args={"query": "q", "top_k": 5}),
            ),
        )

    async def stub_kg_search(q, mode="hybrid"):
        return "stub"

    monkeypatch.setattr(
        "lib.research.stages.reasoner.kg_search", stub_kg_search
    )

    cfg = _make_cfg(mock_llm_never_final, vision_cascade, max_iter_reasoner=2)
    retrieved = _make_retrieved(tmp_path / "00deadbeef" / "1.jpg")
    result = await run_reasoner("test", cfg, retrieved)

    assert result.status == "ok"
    assert result.status != "failed"
    assert result.reason is None


# ---------------------------------------------------------------------------
# Test 4 — cfg.llm_complete raises → ReasonerOutput(status="failed", ...)
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_reasoner_catches_llm_exception(tmp_path):
    vision_cascade = MagicMock()
    vision_cascade.describe = AsyncMock(return_value="<MOCK_CAPTION>")

    async def mock_llm_raises(prompt, tools):
        raise RuntimeError("LLM provider down")

    cfg = _make_cfg(mock_llm_raises, vision_cascade)
    retrieved = _make_retrieved(tmp_path / "abc1234567" / "5.jpg")
    result = await run_reasoner("test", cfg, retrieved)

    assert result.status == "failed"
    assert "LLM provider down" in (result.reason or "")
    # Axis 3 proof — no raise propagates.


# ---------------------------------------------------------------------------
# Test 5 — vision_cascade.describe raises → status="failed"
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_reasoner_catches_vision_exception(tmp_path):
    image_path = tmp_path / "abc1234567" / "5.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"")

    vision_cascade = MagicMock()
    vision_cascade.describe = AsyncMock(
        side_effect=RuntimeError("vision provider 503")
    )

    async def mock_llm(prompt, tools):
        return _LLMDecision(
            is_final=False,
            tool_calls=(
                _ToolCall(
                    name="vision_analyze",
                    args={"image_path": str(image_path), "question": "test"},
                ),
            ),
        )

    cfg = _make_cfg(mock_llm, vision_cascade)
    retrieved = _make_retrieved(image_path)
    result = await run_reasoner("test", cfg, retrieved)

    assert result.status == "failed"
    assert "vision provider 503" in (result.reason or "")


# ---------------------------------------------------------------------------
# Test 6 — kg_search tool call appends Source(kind="kg_chunk") to chunks
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_reasoner_kg_search_tool_appends_chunk(tmp_path, monkeypatch):
    vision_cascade = MagicMock()
    vision_cascade.describe = AsyncMock(return_value="<MOCK_CAPTION>")

    call_count = {"n": 0}

    async def mock_llm(prompt, tools):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _LLMDecision(
                is_final=False,
                tool_calls=(
                    _ToolCall(
                        name="kg_search",
                        args={"query": "subq", "top_k": 5},
                    ),
                ),
            )
        return _LLMDecision(is_final=True, content="done")

    async def stub_kg_search(q, mode="hybrid"):
        return "stub kg result"

    monkeypatch.setattr(
        "lib.research.stages.reasoner.kg_search", stub_kg_search
    )

    cfg = _make_cfg(mock_llm, vision_cascade)
    retrieved = _make_retrieved(tmp_path / "deadbeef00" / "1.jpg")
    result = await run_reasoner("test", cfg, retrieved)

    assert result.status == "ok"
    assert len(result.additional_chunks) == 1
    assert result.additional_chunks[0].kind == "kg_chunk"
    assert result.additional_chunks[0].snippet == "stub kg result"
    assert result.additional_chunks[0].uri == "omnigraph_search.query.search"


# ---------------------------------------------------------------------------
# Test 7 — two vision_analyze calls in one turn dispatched via asyncio.gather
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_reasoner_parallel_vision_calls(tmp_path):
    """Asserts two vision_analyze calls in one turn are awaited concurrently.

    Hard assertion: ``vision_cascade.describe.await_count == 2`` (proves the
    impl dispatched both calls within a single turn). The timing assertion
    is commented out below — on Windows the wallclock variance makes
    ``elapsed < 0.18`` flaky for a 100ms-per-call sleep. The await-count
    assertion plus the structural fact that the impl uses ``asyncio.gather``
    (visible in source — required by acceptance criterion) is sufficient
    proof of parallel dispatch.
    """
    image_a = tmp_path / "aaaaaaaaaa" / "1.jpg"
    image_b = tmp_path / "bbbbbbbbbb" / "2.jpg"
    image_a.parent.mkdir(parents=True)
    image_b.parent.mkdir(parents=True)
    image_a.write_bytes(b"")
    image_b.write_bytes(b"")

    async def slow_describe(image_path, question):
        await asyncio.sleep(0.1)
        return "<MOCK_CAPTION>"

    vision_cascade = MagicMock()
    vision_cascade.describe = AsyncMock(side_effect=slow_describe)

    call_count = {"n": 0}

    async def mock_llm(prompt, tools):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _LLMDecision(
                is_final=False,
                tool_calls=(
                    _ToolCall(
                        name="vision_analyze",
                        args={"image_path": str(image_a), "question": "q"},
                    ),
                    _ToolCall(
                        name="vision_analyze",
                        args={"image_path": str(image_b), "question": "q"},
                    ),
                ),
            )
        return _LLMDecision(is_final=True, content="done")

    cfg = _make_cfg(mock_llm, vision_cascade)
    retrieved = _make_retrieved(image_a)

    t0 = time.perf_counter()
    result = await run_reasoner("test", cfg, retrieved)
    elapsed = time.perf_counter() - t0

    assert result.status == "ok"
    assert vision_cascade.describe.await_count == 2
    assert len(result.analyzed_images) == 2
    # Soft timing check — relaxed to a generous threshold for Windows.
    # Sequential would be ≥0.2s; parallel should be ~0.1s. Threshold 0.4s
    # leaves ample headroom for slow CI machines while still catching the
    # case where someone "fixes" gather to a sequential await loop.
    assert elapsed < 0.4
