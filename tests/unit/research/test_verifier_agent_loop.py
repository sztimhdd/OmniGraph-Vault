"""TEST-04 Verifier-half — mock-based test of the bounded LLM agent loop.

Covers ORCH-04 observable behaviors:
- Test 1 ``test_verifier_finalizes_after_one_turn``: turn 1 = final answer
  → ``iter_count == 1``, ``status == "ok"``, no tool dispatch.
- Test 2 ``test_verifier_calls_web_search_tool``: turn 1 = web_search call,
  turn 2 = final → ``cfg.web_search`` awaited, citations populated.
- Test 3 ``test_verifier_calls_web_extract_tool``: turn 1 = web_extract,
  turn 2 = final → ``cfg.web_extract`` awaited, extract URL recorded.
- Test 4 ``test_verifier_omits_grounding_tool_when_grounding_none``: tool
  list ``== ["web_search", "web_extract"]`` exactly; prompt does NOT mention
  grounding.
- Test 5 ``test_verifier_includes_grounding_tool_when_set``: grounding tool
  appears in registry when ``cfg.google_search_grounding`` is set.
- Test 6 ``test_verifier_includes_reasoned_inferences_md_in_prompt``: unique
  marker in ``reasoned.inferences_md`` appears in captured prompt.
- Test 7 ``test_verifier_returns_failed_on_llm_exception``: ``cfg.llm_complete``
  raises → ``status="failed"`` with empty lists (Hard requirement #2).
- Test 8 ``test_verifier_clamps_confidence_to_0_100``: ``confidence=150.0``
  → ``result.confidence == 100.0``; negative case → ``0.0``.
- Test 9 ``test_verifier_records_parse_failure_as_discrepancy``: unparseable
  confidence → ``confidence=0.0`` + discrepancy line + ``status="ok"``
  (Hard requirement #4).

The internal protocol types ``_LLMDecision`` / ``_ToolCall`` are imported
from ``lib.research.stages.verifier`` — mocks construct them directly.

Tool wire-format chosen: ``list[dict]`` with ``"name"`` + ``"fn"`` keys,
matching the Reasoner pattern from ar-2-01. Tests verify the tool list by
extracting ``[t["name"] for t in tools]``.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from lib.research.stages.verifier import _LLMDecision, _ToolCall
from lib.research.stages.verifier import run as run_verifier
from lib.research.types import (
    ReasonerOutput,
    ResearchConfig,
    Source,
    VerifierOutput,
)


def _make_cfg(llm_complete, **overrides) -> ResearchConfig:
    """Build a minimal ResearchConfig for tests — bypasses ``from_env()``."""
    base = dict(
        rag_working_dir=Path("/tmp/_test_rag"),
        llm_complete=llm_complete,
        embedding_func=AsyncMock(),
        vision_cascade=MagicMock(),
        web_search=AsyncMock(
            return_value=[
                {"title": "T", "url": "https://e.com/x", "content": "c"},
            ]
        ),
        web_extract=AsyncMock(return_value="extracted body"),
        web_search_fallback=None,
        google_search_grounding=None,
    )
    base.update(overrides)
    return ResearchConfig(**base)


def _make_reasoned(inferences: str = "Mock Reasoner inferences.") -> ReasonerOutput:
    return ReasonerOutput(
        inferences_md=inferences,
        additional_chunks=[],
        analyzed_images=[],
        iter_count=1,
        status="ok",
    )


# ---------------------------------------------------------------------------
# Test 1 — final on turn 1: iter_count == 1, no tool dispatch
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_verifier_finalizes_after_one_turn():
    web_search_mock = AsyncMock(return_value=[])

    async def mock_llm(prompt, tools):
        return _LLMDecision(is_final=True, content="Verified.", confidence=85.0)

    cfg = _make_cfg(mock_llm, web_search=web_search_mock)
    result = await run_verifier("q", cfg, _make_reasoned())

    assert isinstance(result, VerifierOutput)
    assert result.iter_count == 1
    assert result.status == "ok"
    assert result.fact_check_summary_md == "Verified."
    assert result.confidence == 85.0
    assert web_search_mock.await_count == 0


# ---------------------------------------------------------------------------
# Test 2 — turn 1 web_search, turn 2 final → cfg.web_search awaited
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_verifier_calls_web_search_tool():
    web_search_mock = AsyncMock(
        return_value=[
            {
                "title": "Result",
                "url": "https://example.com/found",
                "content": "snippet text",
            }
        ]
    )

    call_count = {"n": 0}

    async def mock_llm(prompt, tools):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _LLMDecision(
                is_final=False,
                tool_calls=(
                    _ToolCall(name="web_search", args={"query": "subq"}),
                ),
            )
        return _LLMDecision(is_final=True, content="Done.", confidence=70.0)

    cfg = _make_cfg(mock_llm, web_search=web_search_mock)
    result = await run_verifier("q", cfg, _make_reasoned())

    assert result.status == "ok"
    assert result.iter_count == 2
    assert web_search_mock.await_count >= 1
    # Citations populated from web_search result
    web_citations = [c for c in result.external_citations if c.kind == "web"]
    assert len(web_citations) >= 1
    assert any(c.uri == "https://example.com/found" for c in web_citations)


# ---------------------------------------------------------------------------
# Test 3 — turn 1 web_extract, turn 2 final → cfg.web_extract awaited
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_verifier_calls_web_extract_tool():
    web_extract_mock = AsyncMock(return_value="extracted markdown body")

    call_count = {"n": 0}

    async def mock_llm(prompt, tools):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _LLMDecision(
                is_final=False,
                tool_calls=(
                    _ToolCall(
                        name="web_extract",
                        args={"url": "https://example.com/article"},
                    ),
                ),
            )
        return _LLMDecision(is_final=True, content="Done.", confidence=60.0)

    cfg = _make_cfg(mock_llm, web_extract=web_extract_mock)
    result = await run_verifier("q", cfg, _make_reasoned())

    assert result.status == "ok"
    assert web_extract_mock.await_count >= 1
    extract_citations = [
        c for c in result.external_citations
        if c.uri == "https://example.com/article"
    ]
    assert len(extract_citations) == 1
    assert extract_citations[0].snippet == "extracted markdown body"


# ---------------------------------------------------------------------------
# Test 4 — grounding=None → tool list omits grounding; prompt doesn't mention it
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_verifier_omits_grounding_tool_when_grounding_none():
    captured_tools: list[list[str]] = []
    captured_prompts: list[str] = []

    async def mock_llm(prompt, tools):
        captured_tools.append([t["name"] for t in tools])
        captured_prompts.append(prompt)
        return _LLMDecision(is_final=True, content="Done.", confidence=50.0)

    cfg = _make_cfg(mock_llm, google_search_grounding=None)
    await run_verifier("q", cfg, _make_reasoned())

    assert captured_tools[0] == ["web_search", "web_extract"]
    assert "google_search_grounding" not in captured_prompts[0]


# ---------------------------------------------------------------------------
# Test 5 — grounding set → tool list includes "google_search_grounding"
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_verifier_includes_grounding_tool_when_set():
    captured_tools: list[list[str]] = []

    async def mock_llm(prompt, tools):
        captured_tools.append([t["name"] for t in tools])
        return _LLMDecision(is_final=True, content="Done.", confidence=50.0)

    grounding_mock = AsyncMock(return_value="grounded result")
    cfg = _make_cfg(mock_llm, google_search_grounding=grounding_mock)
    await run_verifier("q", cfg, _make_reasoned())

    assert "google_search_grounding" in captured_tools[0]
    # Order: web_search, web_extract, google_search_grounding
    assert captured_tools[0] == [
        "web_search",
        "web_extract",
        "google_search_grounding",
    ]


# ---------------------------------------------------------------------------
# Test 6 — prompt includes reasoned.inferences_md verbatim
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_verifier_includes_reasoned_inferences_md_in_prompt():
    captured_prompts: list[str] = []

    async def mock_llm(prompt, tools):
        captured_prompts.append(prompt)
        return _LLMDecision(is_final=True, content="Done.", confidence=50.0)

    cfg = _make_cfg(mock_llm)
    reasoned = _make_reasoned(inferences="UNIQUE-INFERENCE-MARKER-12345")
    await run_verifier("q", cfg, reasoned)

    assert len(captured_prompts) == 1
    assert "UNIQUE-INFERENCE-MARKER-12345" in captured_prompts[0]


# ---------------------------------------------------------------------------
# Test 7 — cfg.llm_complete raises → status="failed", empty lists, no raise out
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_verifier_returns_failed_on_llm_exception():
    async def mock_llm_raises(prompt, tools):
        raise RuntimeError("LLM provider down")

    cfg = _make_cfg(mock_llm_raises)
    result = await run_verifier("q", cfg, _make_reasoned())

    # Hard requirement #2 — empty lists, NOT partial.
    assert result.status == "failed"
    assert "LLM provider down" in (result.reason or "")
    assert result.confidence == 0.0
    assert result.fact_check_summary_md == ""
    assert result.external_citations == []
    assert result.discrepancies == []


# ---------------------------------------------------------------------------
# Test 8 — confidence clamped to [0.0, 100.0]
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_verifier_clamps_confidence_to_0_100():
    # High side: 150.0 → 100.0
    async def mock_llm_high(prompt, tools):
        return _LLMDecision(is_final=True, content="Done.", confidence=150.0)

    cfg_high = _make_cfg(mock_llm_high)
    result_high = await run_verifier("q", cfg_high, _make_reasoned())
    assert result_high.confidence == 100.0
    assert result_high.status == "ok"

    # Low side: -5.0 → 0.0
    async def mock_llm_low(prompt, tools):
        return _LLMDecision(is_final=True, content="Done.", confidence=-5.0)

    cfg_low = _make_cfg(mock_llm_low)
    result_low = await run_verifier("q", cfg_low, _make_reasoned())
    assert result_low.confidence == 0.0
    assert result_low.status == "ok"


# ---------------------------------------------------------------------------
# Test 9 — unparseable confidence → confidence=0.0 + discrepancy + status=ok
# (Hard requirement #4)
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_verifier_records_parse_failure_as_discrepancy():
    async def mock_llm_bad_conf(prompt, tools):
        # confidence is a non-numeric, non-coercible value → float() raises
        # TypeError. The loop should clamp to 0.0 + append a discrepancy and
        # leave status = "ok" (parse issue is observation, not stage failure).
        return _LLMDecision(
            is_final=True,
            content="Done.",
            confidence=object(),  # type: ignore[arg-type]
        )

    cfg = _make_cfg(mock_llm_bad_conf)
    result = await run_verifier("q", cfg, _make_reasoned())

    assert result.status == "ok"
    assert result.confidence == 0.0
    assert any(
        "failed to parse confidence" in d for d in result.discrepancies
    )
