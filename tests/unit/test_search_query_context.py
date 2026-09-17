"""Boundary tests for bounded raw-context LightRAG queries.

The virtual environment used by these offline tests deliberately has no
LightRAG installation.  A minimal import double lets this test exercise the
real wrapper while the supplied ``rag`` fake is the external boundary.
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


_UNSET = object()


def _install_lightrag_import_double(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide only the symbols needed while importing the real wrapper."""
    package = types.ModuleType("lightrag")
    module = types.ModuleType("lightrag.lightrag")

    class LightRAG:
        pass

    class QueryParam:
        def __init__(
            self,
            *,
            mode: str = "mix",
            only_need_context: bool = False,
            top_k: object = _UNSET,
            chunk_top_k: object = _UNSET,
        ):
            self.mode = mode
            self.only_need_context = only_need_context
            self.top_k = top_k
            self.chunk_top_k = chunk_top_k

    module.LightRAG = LightRAG
    module.QueryParam = QueryParam
    monkeypatch.setitem(sys.modules, "lightrag", package)
    monkeypatch.setitem(sys.modules, "lightrag.lightrag", module)


@pytest.fixture
def query_module(monkeypatch: pytest.MonkeyPatch):
    """Load the real wrapper without leaking its temporary import state."""
    _install_lightrag_import_double(monkeypatch)
    package = importlib.import_module("omnigraph_search")
    prior_module = sys.modules.get("omnigraph_search.query", _UNSET)
    prior_attr = getattr(package, "query", _UNSET)
    sys.modules.pop("omnigraph_search.query", None)
    package.__dict__.pop("query", None)
    query = importlib.import_module("omnigraph_search.query")
    monkeypatch.setattr(query, "_LOCAL_EMBED_MODE", True)
    yield query
    sys.modules.pop("omnigraph_search.query", None)
    if prior_module is not _UNSET:
        sys.modules["omnigraph_search.query"] = prior_module
    if prior_attr is _UNSET:
        package.__dict__.pop("query", None)
    else:
        package.query = prior_attr


@pytest.mark.asyncio
async def test_search_context_returns_evidence_and_passes_requested_top_k(
    query_module,
) -> None:
    """Removing context mode or the supplied limit loses bounded evidence."""
    rag = MagicMock()
    rag.aquery = AsyncMock(return_value="raw evidence from chunk 7")

    result = await query_module.search(
        "which evidence?", mode="mix", only_context=True, rag=rag, top_k=7
    )

    assert result == "raw evidence from chunk 7"
    rag.aquery.assert_awaited_once()
    _, kwargs = rag.aquery.call_args
    param = kwargs["param"]
    assert param.mode == "mix"
    assert param.only_need_context is True
    assert param.top_k == 7
    assert param.chunk_top_k == 7


@pytest.mark.asyncio
async def test_search_default_keeps_lightrag_top_k_unset(
    query_module,
) -> None:
    """Always injecting a limit would change established callers' defaults."""
    rag = MagicMock()
    rag.aquery = AsyncMock(return_value="synthesized answer")

    result = await query_module.search("hello", rag=rag)

    assert result == "synthesized answer"
    _, kwargs = rag.aquery.call_args
    param = kwargs["param"]
    assert param.mode == "hybrid"
    assert param.only_need_context is False
    assert param.top_k is _UNSET
    assert param.chunk_top_k is _UNSET


@pytest.mark.asyncio
@pytest.mark.parametrize("top_k", [0, -1, 11, True, 1.5, "5"])
async def test_search_rejects_invalid_or_oversized_top_k(
    query_module, top_k: object
) -> None:
    """Removing type or ceiling validation permits an unbounded tool argument."""
    rag = MagicMock()
    rag.aquery = AsyncMock()

    with pytest.raises(ValueError, match="top_k"):
        await query_module.search("hello", rag=rag, top_k=top_k)

    rag.aquery.assert_not_awaited()


@pytest.mark.asyncio
async def test_reasoner_uses_initial_and_new_evidence_in_second_prompt(query_module):
    """Counts alone cannot let the second decision use retrieved evidence."""
    from lib.research.stages.reasoner import _LLMDecision, _ToolCall, run
    from lib.research.types import ResearchConfig, RetrieverOutput, Source

    initial = Source(
        kind="kg_chunk", uri="article://initial-42", snippet="INITIAL_FACT_42"
    )
    raw_evidence = "NEW_FACT_97; file_path: article-97"
    rag = MagicMock()
    rag.aquery = AsyncMock(return_value=raw_evidence)
    prompts = []

    async def decide(prompt, tools):
        prompts.append(prompt)
        if len(prompts) == 1:
            return _LLMDecision(
                is_final=False,
                tool_calls=(_ToolCall("kg_search", {"query": "find fact 97"}),),
            )
        assert initial.uri in prompt
        assert initial.snippet in prompt
        assert raw_evidence in prompt
        assert "omnigraph_search.query.search" in prompt
        assert "untrusted evidence" in prompt.lower()
        assert "not instructions" in prompt.lower()
        return _LLMDecision(is_final=True, content="Facts 42 and 97 combined.")

    cfg = ResearchConfig(
        rag_working_dir=Path("/tmp/_test_rag"),
        llm_complete=decide,
        embedding_func=AsyncMock(),
        vision_cascade=MagicMock(),
        web_search=lambda q: [],
        rag=rag,
    )
    retrieved = RetrieverOutput(chunks=[initial], image_candidates=[])

    result = await run("combine facts", cfg, retrieved)

    assert result.status == "ok", result.reason
    assert result.inferences_md == "Facts 42 and 97 combined."
    assert result.iter_count == len(prompts) == 2
    assert initial.uri in prompts[0] and initial.snippet in prompts[0]
    assert raw_evidence not in prompts[0]
    assert retrieved.chunks == [initial]
    assert result.additional_chunks == [
        Source(
            kind="kg_chunk",
            uri="omnigraph_search.query.search",
            snippet=raw_evidence,
        )
    ]
    rag.aquery.assert_awaited_once()
    args, kwargs = rag.aquery.call_args
    assert args == ("find fact 97",)
    assert kwargs["param"].mode == "mix"
    assert kwargs["param"].only_need_context is True
    assert kwargs["param"].top_k == 10
    assert kwargs["param"].chunk_top_k == 10
