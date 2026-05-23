"""TEST-04 Verifier-half cap enforcement test.

Wave 3 may absorb this into test_caps_consolidated.py and remove this
standalone file. Self-contained (no cross-file fixture imports) for
trivial migration.

Asserts: when the LLM never emits a final answer (always emits a
``web_search`` tool call), the loop terminates exactly at
``cfg.max_iter_verifier`` (default 3) with ``status="ok"`` (the cap is a
budget, not an error — Hard requirement #3).
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
    VerifierOutput,
)


def _make_cfg(llm_complete, **overrides) -> ResearchConfig:
    """Self-contained minimal ResearchConfig — duplicated from
    test_verifier_agent_loop.py so Wave 3 can absorb this file without
    cross-file fixture imports."""
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


def _make_reasoned() -> ReasonerOutput:
    return ReasonerOutput(
        inferences_md="Mock inferences.",
        additional_chunks=[],
        analyzed_images=[],
        iter_count=1,
        status="ok",
    )


@pytest.mark.unit
async def test_verifier_cap_enforcement():
    """LLM never emits final → loop terminates at iter_count == max_iter_verifier."""

    async def mock_llm_never_final(prompt, tools):
        return _LLMDecision(
            is_final=False,
            tool_calls=(_ToolCall(name="web_search", args={"query": "subq"}),),
        )

    cfg = _make_cfg(mock_llm_never_final)  # default max_iter_verifier=3
    reasoned = _make_reasoned()
    result = await run_verifier("test query", cfg, reasoned)

    assert isinstance(result, VerifierOutput)
    assert result.iter_count == cfg.max_iter_verifier  # exactly the cap (=3)
    assert result.status == "ok"  # cap is a budget, not an error
