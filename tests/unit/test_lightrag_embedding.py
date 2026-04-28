"""Unit tests for ``lightrag_embedding`` — the Phase 5 D-01/D-04/D-05 shared module.

All tests run locally with mocks (no network). Verifies:

1. Document path returns a (N, 768) float32 np.ndarray.
2. Query path (``_priority=5``) applies the query prefix but keeps the shape.
3. ``_priority`` is popped from kwargs and NOT forwarded to the Gemini client.
4. An ``http://localhost:8765/.../x.jpg`` URL in the text triggers
   ``requests.get`` and a ``types.Part.from_bytes`` in the ``contents`` list.
5. Output is L2-normalized (row norm ≈ 1.0).
"""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _gemini_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    # Keep the module's default model unless a test overrides it.
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)


def _fake_embed_response(num: int, dim: int = 768) -> MagicMock:
    """Build a response shaped like ``client.aio.models.embed_content``'s output."""
    response = MagicMock()
    embeddings = []
    for i in range(num):
        e = MagicMock()
        # Non-trivial values so L2-normalization is meaningful.
        e.values = [float((i + 1) * (j + 1)) for j in range(dim)]
        embeddings.append(e)
    response.embeddings = embeddings
    return response


def _patched_client(embed_response: MagicMock) -> MagicMock:
    """Return a mock ``genai.Client`` whose ``aio.models.embed_content`` is an AsyncMock."""
    client = MagicMock()
    client.aio.models.embed_content = AsyncMock(return_value=embed_response)
    return client


@pytest.mark.unit
async def test_document_path_returns_correct_shape() -> None:
    """Test 1: embedding_func(["hello"]) with no _priority returns (1, 768) float32."""
    import lightrag_embedding

    mock_client = _patched_client(_fake_embed_response(1))
    with patch.object(lightrag_embedding.genai, "Client", return_value=mock_client):
        out = await lightrag_embedding.embedding_func(["hello"])

    assert isinstance(out, np.ndarray)
    assert out.shape == (1, 768)
    assert out.dtype == np.float32


@pytest.mark.unit
async def test_query_path_applies_query_prefix() -> None:
    """Test 2: _priority=5 applies query prefix, still returns (1, 768)."""
    import lightrag_embedding

    mock_client = _patched_client(_fake_embed_response(1))
    with patch.object(lightrag_embedding.genai, "Client", return_value=mock_client):
        out = await lightrag_embedding.embedding_func(["hello"], _priority=5)

    assert out.shape == (1, 768)
    # Inspect the call to verify the query prefix was prepended.
    call = mock_client.aio.models.embed_content.call_args_list[0]
    contents = call.kwargs["contents"]
    assert isinstance(contents, list)
    assert contents[0].startswith("task: search result | query: "), contents[0]


@pytest.mark.unit
async def test_priority_kwarg_is_not_forwarded_to_gemini() -> None:
    """Test 3: _priority is popped from kwargs and never reaches the Gemini client."""
    import lightrag_embedding

    mock_client = _patched_client(_fake_embed_response(1))
    with patch.object(lightrag_embedding.genai, "Client", return_value=mock_client):
        await lightrag_embedding.embedding_func(["hello"], _priority=5)

    call = mock_client.aio.models.embed_content.call_args_list[0]
    # All kwargs passed to embed_content
    forwarded_kwargs = call.kwargs
    assert "_priority" not in forwarded_kwargs
    # Also ensure it's not smuggled into the config object.
    config = forwarded_kwargs["config"]
    # EmbedContentConfig is a dataclass/pydantic-ish object; inspect its attrs.
    if hasattr(config, "model_dump"):
        assert "_priority" not in config.model_dump()
    else:
        assert not hasattr(config, "_priority")


@pytest.mark.unit
async def test_image_url_triggers_inline_part_fetch() -> None:
    """Test 4: text with http://localhost:8765/*.jpg triggers requests.get + Part.from_bytes."""
    import lightrag_embedding

    mock_client = _patched_client(_fake_embed_response(1))
    fake_img_bytes = b"\xff\xd8\xff\xe0" + b"0" * 100  # minimal JPEG-ish
    mock_response = MagicMock()
    mock_response.content = fake_img_bytes
    mock_response.raise_for_status = MagicMock()

    with patch.object(lightrag_embedding.genai, "Client", return_value=mock_client), \
         patch.object(lightrag_embedding.requests, "get", return_value=mock_response) as mock_get:
        await lightrag_embedding.embedding_func(
            ["See diagram http://localhost:8765/abc/0.jpg here"]
        )

    # requests.get called exactly once with the URL.
    assert mock_get.call_count == 1
    assert "http://localhost:8765/abc/0.jpg" in mock_get.call_args.args[0]

    # The contents list sent to Gemini must include a Part (not just a string).
    call = mock_client.aio.models.embed_content.call_args_list[0]
    contents = call.kwargs["contents"]
    assert len(contents) >= 2  # text + Part
    # First element is the stripped text (URL removed).
    assert "http://localhost:8765" not in contents[0]
    # Second element is a Part-shaped object (has inline_data or equivalent).
    part = contents[1]
    # google.genai.types.Part has inline_data attribute
    assert hasattr(part, "inline_data") or hasattr(part, "data") or part.__class__.__name__ == "Part"


@pytest.mark.unit
async def test_output_is_l2_normalized() -> None:
    """Test 5: Each row of the returned ndarray has L2 norm ≈ 1.0."""
    import lightrag_embedding

    mock_client = _patched_client(_fake_embed_response(3))
    with patch.object(lightrag_embedding.genai, "Client", return_value=mock_client):
        out = await lightrag_embedding.embedding_func(["a", "b", "c"])

    assert out.shape == (3, 768)
    norms = np.linalg.norm(out, axis=1)
    for n in norms:
        assert abs(n - 1.0) < 1e-5, f"row norm {n} not close to 1.0"
