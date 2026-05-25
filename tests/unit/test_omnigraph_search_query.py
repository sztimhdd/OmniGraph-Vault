"""Unit tests for omnigraph_search.query.search() — only_context parameter transit.

Asserts the additive `only_context: bool = False` parameter wires through to
`QueryParam(only_need_context=...)` without breaking the pre-existing
LLM-synthesized default behavior used by kb/api_routers/search.py and
lib/research/stages/reasoner.py.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("GEMINI_API_KEY", "test-key-for-import")
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")


@pytest.mark.asyncio
async def test_search_default_only_context_false():
    """Default call (no only_context kwarg) → QueryParam.only_need_context=False."""
    from omnigraph_search import query as q

    fake_rag = MagicMock()
    fake_rag.aquery = AsyncMock(return_value="synthesized answer")
    fake_rag.initialize_storages = AsyncMock()

    with patch.object(q, "LightRAG", return_value=fake_rag), \
         patch.object(q, "get_llm_func", return_value=lambda: None), \
         patch.object(q, "GEMINI_API_KEY", "test-key"):
        result = await q.search("hello", mode="hybrid")

    assert result == "synthesized answer"
    fake_rag.aquery.assert_awaited_once()
    _, kwargs = fake_rag.aquery.call_args
    param = kwargs["param"]
    assert param.mode == "hybrid"
    assert param.only_need_context is False


@pytest.mark.asyncio
async def test_search_only_context_true_transits():
    """only_context=True → QueryParam.only_need_context=True (raw context bypass)."""
    from omnigraph_search import query as q

    fake_rag = MagicMock()
    fake_rag.aquery = AsyncMock(return_value="-----Sources-----\nfile_path: abc1234567...")
    fake_rag.initialize_storages = AsyncMock()

    with patch.object(q, "LightRAG", return_value=fake_rag), \
         patch.object(q, "get_llm_func", return_value=lambda: None), \
         patch.object(q, "GEMINI_API_KEY", "test-key"):
        result = await q.search("hello", mode="hybrid", only_context=True)

    assert "file_path" in result
    _, kwargs = fake_rag.aquery.call_args
    param = kwargs["param"]
    assert param.mode == "hybrid"
    assert param.only_need_context is True


@pytest.mark.asyncio
async def test_search_missing_gemini_key_raises():
    """Missing GEMINI_API_KEY still raises ValueError (pre-existing behavior preserved)."""
    from omnigraph_search import query as q

    with patch.object(q, "GEMINI_API_KEY", None):
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            await q.search("hello", only_context=True)
