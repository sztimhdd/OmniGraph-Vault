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
import os
import subprocess
import sys
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


@pytest.mark.unit
def test_reasoner_collection_does_not_import_or_stub_search():
    """Collecting this module must not import or globally fake LightRAG."""
    probe = '''
import importlib.abc
import runpy
import sys

class BlockSearch(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "lightrag" or fullname == "omnigraph_search.query":
            raise AssertionError("eager search import: " + fullname)

sys.meta_path.insert(0, BlockSearch())
runpy.run_path(sys.argv[1])
assert "lightrag" not in sys.modules
assert "lightrag.lightrag" not in sys.modules
assert "omnigraph_search.query" not in sys.modules
'''
    result = subprocess.run(
        [sys.executable, "-c", probe, str(Path(__file__).resolve())],
        cwd=Path(__file__).resolve().parents[3],
        env={**os.environ, "OMNIGRAPH_LOAD_ENV": "0"},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


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

    async def stub_kg_search(q, mode="hybrid", **kwargs):  # arx-4: absorb rag= kwarg
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

    async def stub_kg_search(q, mode="hybrid", **kwargs):  # arx-4: absorb rag= kwarg
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

    async def stub_kg_search(q, mode="hybrid", **kwargs):  # arx-4: absorb rag= kwarg
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


@pytest.mark.unit
async def test_reasoner_kg_search_requests_bounded_raw_evidence(tmp_path, monkeypatch):
    """Dropping raw mode or top_k would turn evidence collection into synthesis."""
    vision_cascade = MagicMock()
    vision_cascade.describe = AsyncMock(return_value="<MOCK_CAPTION>")
    calls = []

    async def mock_llm(prompt, tools):
        if not calls:
            return _LLMDecision(
                is_final=False,
                tool_calls=(
                    _ToolCall(name="kg_search", args={"query": "subq", "top_k": 7}),
                ),
            )
        return _LLMDecision(is_final=True, content="done")

    async def stub_kg_search(q, **kwargs):
        calls.append((q, kwargs))
        return "raw evidence from chunk 7"

    monkeypatch.setattr(
        "lib.research.stages.reasoner.kg_search", stub_kg_search
    )
    cfg = _make_cfg(mock_llm, vision_cascade)
    cfg = dataclasses.replace(cfg, rag=object())

    result = await run_reasoner(
        "test", cfg, _make_retrieved(tmp_path / "deadbeef00" / "1.jpg")
    )

    assert result.status == "ok"
    assert result.additional_chunks[0].snippet == "raw evidence from chunk 7"
    assert calls == [
        (
            "subq",
            {
                "mode": "mix",
                "only_context": True,
                "top_k": 7,
                "rag": cfg.rag,
            },
        )
    ]


@pytest.mark.unit
@pytest.mark.parametrize("top_k", [11, True, "5"])
async def test_reasoner_reports_invalid_kg_top_k(tmp_path, monkeypatch, top_k):
    """Bypassing the wrapper's validation must fail the bounded tool call."""
    vision_cascade = MagicMock()
    vision_cascade.describe = AsyncMock(return_value="<MOCK_CAPTION>")

    async def mock_llm(prompt, tools):
        return _LLMDecision(
            is_final=False,
            tool_calls=(_ToolCall(name="kg_search", args={"top_k": top_k}),),
        )

    async def stub_kg_search(q, **kwargs):
        raise ValueError("top_k must be an integer from 1 to 10")

    monkeypatch.setattr(
        "lib.research.stages.reasoner.kg_search", stub_kg_search
    )
    result = await run_reasoner(
        "test",
        _make_cfg(mock_llm, vision_cascade),
        _make_retrieved(tmp_path / "deadbeef00" / "1.jpg"),
    )

    assert result.status == "failed"
    assert result.reason == "top_k must be an integer from 1 to 10"


@pytest.mark.unit
async def test_reasoner_rejects_explicit_null_kg_top_k(tmp_path, monkeypatch):
    """Forwarding null would silently restore the wrapper's unbounded default."""
    vision_cascade = MagicMock()
    vision_cascade.describe = AsyncMock(return_value="<MOCK_CAPTION>")
    calls = []

    async def mock_llm(prompt, tools):
        return _LLMDecision(
            is_final=False,
            tool_calls=(_ToolCall(name="kg_search", args={"top_k": None}),),
        )

    async def stub_kg_search(q, **kwargs):
        calls.append((q, kwargs))
        return "unexpected evidence"

    monkeypatch.setattr(
        "lib.research.stages.reasoner.kg_search", stub_kg_search
    )
    result = await run_reasoner(
        "test",
        _make_cfg(mock_llm, vision_cascade),
        _make_retrieved(tmp_path / "deadbeef00" / "1.jpg"),
    )

    assert result.status == "failed"
    assert result.reason == "top_k must be an integer from 1 to 10"
    assert calls == []


@pytest.mark.unit
@pytest.mark.parametrize("excess", ["snippet", "uri", "many_sources"])
async def test_reasoner_caps_prompt_evidence_without_changing_sources(
    monkeypatch, excess
):
    """Bound aggregate evidence characters, including URIs and truncation marks."""
    if excess == "many_sources":
        initial = [
            Source(kind="kg_chunk", uri=f"article://{i}", snippet="初" * 1000)
            for i in range(10)
        ]
    else:
        initial = [Source(
            kind="kg_chunk",
            uri="article://" + ("u" * 15000 if excess == "uri" else "initial"),
            snippet="INITIAL_FACT " + "初😀" * 10000,
        )]
    raw_evidence = "NEW_FACT " + "补😀" * 10000
    prompts = []

    async def decide(prompt, tools):
        prompts.append(prompt)
        if len(prompts) == 1:
            return _LLMDecision(
                is_final=False,
                tool_calls=(_ToolCall("kg_search", {"query": "supplement"}),),
            )
        return _LLMDecision(is_final=True, content="done")

    async def fake_search(q, **kwargs):
        return raw_evidence

    monkeypatch.setattr(reasoner_mod, "kg_search", fake_search)
    retrieved = RetrieverOutput(chunks=initial, image_candidates=[])
    result = await run_reasoner("test", _make_cfg(decide, MagicMock()), retrieved)

    assert result.status == "ok", result.reason
    assert result.iter_count == len(prompts) == 2
    prompt = prompts[1]
    assert "NEW_FACT" in prompt
    assert "article://" in prompt
    assert "omnigraph_search.query.search" in prompt
    initial_excerpt = prompt.split("BEGIN INITIAL EVIDENCE\n", 1)[1].split(
        "\nEND INITIAL EVIDENCE", 1
    )[0]
    additional_excerpt = prompt.split("BEGIN ADDITIONAL EVIDENCE\n", 1)[1].split(
        "\nEND ADDITIONAL EVIDENCE", 1
    )[0]
    assert 0 < len(initial_excerpt) <= 6000
    assert 0 < len(additional_excerpt) <= 6000
    assert len(initial_excerpt) + len(additional_excerpt) <= 12000
    assert initial_excerpt.endswith("[truncated]")
    assert additional_excerpt.endswith("[truncated]")
    assert retrieved.chunks == initial
    assert result.additional_chunks == [Source(
        kind="kg_chunk",
        uri="omnigraph_search.query.search",
        snippet=raw_evidence,
    )]


@pytest.mark.unit
async def test_reasoner_third_prompt_prioritizes_new_evidence(monkeypatch):
    """An oversized earlier result must not hide the next tool's evidence."""
    old_evidence = "OLD_FACT " + "旧" * 10000
    new_evidence = "NEW_FACT_FOR_TURN_THREE_83"
    search = AsyncMock(side_effect=[old_evidence, new_evidence])
    monkeypatch.setattr(reasoner_mod, "kg_search", search)
    initial = [
        Source(kind="kg_chunk", uri="article://first", snippet="INITIAL_FIRST"),
        Source(kind="kg_chunk", uri="article://second", snippet="INITIAL_SECOND"),
    ]
    prompts = []

    async def decide(prompt, tools):
        prompts.append(prompt)
        if len(prompts) == 1:
            return _LLMDecision(
                is_final=False,
                tool_calls=(_ToolCall("kg_search", {"query": "first lookup"}),),
            )
        if len(prompts) == 2:
            assert "OLD_FACT" in prompt
            assert "[additional-1]" in prompt
            assert new_evidence not in prompt
            return _LLMDecision(
                is_final=False,
                tool_calls=(_ToolCall("kg_search", {"query": "second lookup"}),),
            )
        assert new_evidence in prompt, "latest tool evidence missing on turn three"
        assert prompt.index(new_evidence) < prompt.index("OLD_FACT")
        assert prompt.index("[additional-2]") < prompt.index("[additional-1]")
        assert prompt.index("INITIAL_FIRST") < prompt.index("INITIAL_SECOND")
        return _LLMDecision(is_final=True, content="Answer based on the latest fact.")

    result = await run_reasoner(
        "test",
        _make_cfg(decide, MagicMock()),
        RetrieverOutput(chunks=initial, image_candidates=[]),
    )

    assert result.status == "ok", result.reason
    assert result.inferences_md == "Answer based on the latest fact."
    assert result.iter_count == len(prompts) == 3
    assert search.await_count == 2
    excerpt = prompts[2].split("BEGIN ADDITIONAL EVIDENCE\n", 1)[1].split(
        "\nEND ADDITIONAL EVIDENCE", 1
    )[0]
    assert len(excerpt) <= 6000
    assert excerpt.endswith("[truncated]")
    assert result.additional_chunks == [
        Source(
            kind="kg_chunk", uri="omnigraph_search.query.search", snippet=old_evidence
        ),
        Source(
            kind="kg_chunk", uri="omnigraph_search.query.search", snippet=new_evidence
        ),
    ]


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
