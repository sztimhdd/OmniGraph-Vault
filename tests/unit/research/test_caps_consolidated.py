"""TEST-04 consolidated cap tests — Reasoner cap (default 5) + Verifier cap
(default 3). Absorbs and replaces tests/unit/research/test_verifier_cap.py
(removed in Wave 3 of ar-3 — see ar-3-03 PLAN Task 4).

Both halves assert the same shape: when ``cfg.llm_complete`` never finalizes
(always emits a tool call), the loop terminates exactly at the configured
cap with ``status="ok"`` (the cap is a budget, not an error).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from lib.research.types import (
    ReasonerOutput,
    ResearchConfig,
    RetrievedImage,
    RetrieverOutput,
    Source,
    VerifierOutput,
)


def _make_cfg(llm_complete, **overrides) -> ResearchConfig:
    """Build a minimal ResearchConfig — bypasses ``from_env()``."""
    base = dict(
        rag_working_dir=Path("/tmp/_test_rag"),
        llm_complete=llm_complete,
        embedding_func=AsyncMock(),
        vision_cascade=MagicMock(),
        web_search=AsyncMock(return_value=[]),
        web_extract=AsyncMock(return_value=""),
        web_search_fallback=None,
        google_search_grounding=None,
    )
    base.update(overrides)
    return ResearchConfig(**base)


def _make_retrieved() -> RetrieverOutput:
    return RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="seed", snippet="seed text")],
        image_candidates=[],
    )


def _make_reasoned() -> ReasonerOutput:
    return ReasonerOutput(
        inferences_md="Mock inferences.",
        additional_chunks=[],
        analyzed_images=[],
        iter_count=1,
        status="ok",
    )


# ---------------------------------------------------------------------------
# Reasoner-half cap test (NEW in Wave 3) — TEST-04 Reasoner half
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_reasoner_cap_enforcement(monkeypatch):
    """LLM never emits final → loop terminates at iter_count == max_iter_reasoner."""
    from lib.research.stages.reasoner import _LLMDecision, _ToolCall
    from lib.research.stages.reasoner import run as run_reasoner

    async def mock_llm_never_final(prompt, tools):
        return _LLMDecision(
            is_final=False,
            tool_calls=(_ToolCall(name="kg_search", args={"query": "subq"}),),
        )

    # Stub kg_search at the module level so it doesn't touch LightRAG.
    async def stub_kg_search(q, mode="hybrid"):
        return "stub kg result"

    monkeypatch.setattr(
        "lib.research.stages.reasoner.kg_search", stub_kg_search
    )

    cfg = _make_cfg(mock_llm_never_final)  # default max_iter_reasoner=5
    result = await run_reasoner("test query", cfg, _make_retrieved())

    assert isinstance(result, ReasonerOutput)
    assert result.iter_count == cfg.max_iter_reasoner  # exactly the cap (=5)
    assert result.status == "ok"  # cap is a budget, not an error


# ---------------------------------------------------------------------------
# Verifier-half cap test (consolidated from Wave 2's test_verifier_cap.py) —
# TEST-04 Verifier half
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_verifier_cap_enforcement_consolidated():
    """LLM never emits final → loop terminates at iter_count == max_iter_verifier."""
    from lib.research.stages.verifier import _LLMDecision, _ToolCall
    from lib.research.stages.verifier import run as run_verifier

    async def mock_llm_never_final(prompt, tools):
        return _LLMDecision(
            is_final=False,
            tool_calls=(_ToolCall(name="web_search", args={"query": "subq"}),),
        )

    cfg = _make_cfg(mock_llm_never_final)  # default max_iter_verifier=3
    result = await run_verifier("test query", cfg, _make_reasoned())

    assert isinstance(result, VerifierOutput)
    assert result.iter_count == cfg.max_iter_verifier  # exactly the cap (=3)
    assert result.status == "ok"  # cap is a budget, not an error
