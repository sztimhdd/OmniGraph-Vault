"""Tests for lib/lightrag_embedding.py + root shim — Phase 7 Wave 0 Task 0.5.

D-09: lightrag_embedding.py absorbed into lib/; root shim re-exports for back-compat.
Amendment 2: parity assertion — root shim and lib/ must export the same object.
D-10: uses lib.models.EMBEDDING_MODEL and lib.api_keys.current_key().
"""
from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_api_keys_state(monkeypatch):
    # Plan 05-00c: isolate pool to ONE key so rotation advances don't shift
    # current_key() away from the expected test-embed-key on remote envs
    # (where ~/.hermes/.env defines GEMINI_API_KEY_BACKUP).
    monkeypatch.setenv("GEMINI_API_KEY", "test-embed-key")
    monkeypatch.delenv("GEMINI_API_KEY_BACKUP", raising=False)
    monkeypatch.delenv("OMNIGRAPH_GEMINI_KEY", raising=False)
    monkeypatch.delenv("OMNIGRAPH_GEMINI_KEYS", raising=False)
    import lib.api_keys as k
    k._cycle = None
    k._current = None
    k._rotation_listeners.clear()


def _make_embed_response(dims: int = 3072, n_texts: int = 1) -> MagicMock:
    resp = MagicMock()
    embeddings = []
    for _ in range(n_texts):
        emb = MagicMock()
        emb.values = [0.1] * dims
        embeddings.append(emb)
    resp.embeddings = embeddings
    return resp


# ---------------------------------------------------------------------------
# D-09 absorption: internal wiring tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embedding_func_reads_current_key():
    """D-09: embedding_func uses lib.api_keys.current_key(), NOT os.environ directly."""
    import lib.api_keys as k
    import lib.lightrag_embedding as lem
    import google.genai as genai_mod

    captured_api_keys: list[str] = []

    def _mock_client_cls(api_key):
        captured_api_keys.append(api_key)
        mock_c = MagicMock()
        mock_c.aio.models.embed_content = AsyncMock(return_value=_make_embed_response())
        return mock_c

    with patch.object(genai_mod, "Client", side_effect=_mock_client_cls):
        await lem.embedding_func(["hello"])

    assert len(captured_api_keys) == 1
    assert captured_api_keys[0] == k.current_key()


@pytest.mark.asyncio
async def test_embedding_func_uses_model_constant():
    """D-09/D-10: embedding_func calls embed_content with model == lib.models.EMBEDDING_MODEL."""
    from lib.models import EMBEDDING_MODEL
    import lib.lightrag_embedding as lem
    import google.genai as genai_mod

    mock_embed = AsyncMock(return_value=_make_embed_response())
    mock_client = MagicMock()
    mock_client.aio.models.embed_content = mock_embed

    with patch.object(genai_mod, "Client", return_value=mock_client):
        await lem.embedding_func(["test text"])

    call_kwargs = mock_embed.call_args
    assert call_kwargs.kwargs.get("model") == EMBEDDING_MODEL


@pytest.mark.asyncio
async def test_embedding_func_preserves_priority_pop():
    """LightRAG's _priority=5 kwarg must be popped before reaching embed_content."""
    import lib.lightrag_embedding as lem
    import google.genai as genai_mod

    mock_embed = AsyncMock(return_value=_make_embed_response())
    mock_client = MagicMock()
    mock_client.aio.models.embed_content = mock_embed

    with patch.object(genai_mod, "Client", return_value=mock_client):
        await lem.embedding_func(["text"], _priority=5)

    call_kwargs = mock_embed.call_args
    assert "_priority" not in (call_kwargs.kwargs if call_kwargs else {})


def test_embedding_func_preserves_output_dim():
    """Decorator attribute: embedding_dim must match EMBEDDING_DIM (3072 for gemini-embedding-2)."""
    from lib.lightrag_embedding import embedding_func
    from lib.models import EMBEDDING_DIM
    assert hasattr(embedding_func, "embedding_dim")
    assert embedding_func.embedding_dim == EMBEDDING_DIM


@pytest.mark.asyncio
async def test_embedding_func_preserves_task_prefix_doc():
    """Non-_priority call sends 'title: none | text: ' prefix."""
    import lib.lightrag_embedding as lem
    import google.genai as genai_mod

    received_contents: list = []

    async def _capture_embed(**kwargs):
        received_contents.extend(kwargs.get("contents", []))
        return _make_embed_response()

    mock_client = MagicMock()
    mock_client.aio.models.embed_content = _capture_embed

    with patch.object(genai_mod, "Client", return_value=mock_client):
        await lem.embedding_func(["my document text"])

    assert any("title: none | text:" in c for c in received_contents if isinstance(c, str))


@pytest.mark.asyncio
async def test_embedding_func_preserves_task_prefix_query():
    """_priority=5 call sends 'task: search result | query: ' prefix."""
    import lib.lightrag_embedding as lem
    import google.genai as genai_mod

    received_contents: list = []

    async def _capture_embed(**kwargs):
        received_contents.extend(kwargs.get("contents", []))
        return _make_embed_response()

    mock_client = MagicMock()
    mock_client.aio.models.embed_content = _capture_embed

    with patch.object(genai_mod, "Client", return_value=mock_client):
        await lem.embedding_func(["my query"], _priority=5)

    assert any("task: search result | query:" in c for c in received_contents if isinstance(c, str))


# ---------------------------------------------------------------------------
# Amendment 2: parity assertion
# ---------------------------------------------------------------------------

def test_root_shim_reexports_same_object():
    """Amendment 2: root lightrag_embedding.embedding_func IS lib.embedding_func."""
    from lightrag_embedding import embedding_func as old_ref
    from lib import embedding_func as new_ref
    assert old_ref is new_ref, (
        "Root shim must re-export the same object from lib/ "
        "(Amendment 2 parity assertion)"
    )


# ---------------------------------------------------------------------------
# Back-compat: root shim stays importable
# ---------------------------------------------------------------------------

def test_root_shim_importable():
    """Root lightrag_embedding module remains importable after D-09 absorption."""
    import lightrag_embedding  # noqa: F401
    assert hasattr(lightrag_embedding, "embedding_func")
