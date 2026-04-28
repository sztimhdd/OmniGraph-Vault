"""Tests for lib/llm_client.py — Phase 7 Wave 0 Task 0.4.

Amendment 5: generate() and generate_sync() accept `contents` as str OR list
  of parts — native multimodal, no fall-back to direct genai.Client.
D-06: tests mock at lib.llm_client level (_get_client or underlying calls).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai.errors import APIError
from google.genai import types


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api_error(code: int) -> APIError:
    """Create an APIError with the given HTTP status code."""
    return APIError(code=code, response_json={"error": {"code": code, "message": "test"}})


def _fake_part() -> object:
    """A fake multimodal Part object (does not need to be a real types.Part for pass-through tests)."""
    return types.Part.from_text(text="fake-image-placeholder")


# ---------------------------------------------------------------------------
# _is_retriable predicate tests
# ---------------------------------------------------------------------------

def test_is_retriable_429():
    from lib.llm_client import _is_retriable
    assert _is_retriable(_make_api_error(429)) is True


def test_is_retriable_503():
    from lib.llm_client import _is_retriable
    assert _is_retriable(_make_api_error(503)) is True


def test_is_retriable_400():
    from lib.llm_client import _is_retriable
    assert _is_retriable(_make_api_error(400)) is False


def test_is_retriable_401():
    from lib.llm_client import _is_retriable
    assert _is_retriable(_make_api_error(401)) is False


def test_is_retriable_403():
    from lib.llm_client import _is_retriable
    assert _is_retriable(_make_api_error(403)) is False


def test_is_retriable_non_api_error():
    from lib.llm_client import _is_retriable
    assert _is_retriable(ValueError("oops")) is False


# ---------------------------------------------------------------------------
# _get_client caching tests
# ---------------------------------------------------------------------------

def test_get_client_caches(monkeypatch):
    """Same Client instance returned when key unchanged."""
    monkeypatch.setenv("GEMINI_API_KEY", "stable-key")
    import lib.api_keys as k
    k._cycle = None
    k._current = None
    import lib.llm_client as lc
    lc._client = None
    lc._client_key = None

    c1 = lc._get_client()
    c2 = lc._get_client()
    assert c1 is c2


def test_get_client_rotates_on_key_change(monkeypatch):
    """After rotate_key(), _get_client() creates a new Client instance."""
    monkeypatch.setenv("OMNIGRAPH_GEMINI_KEYS", "key-a,key-b")
    import lib.api_keys as k
    k._cycle = None
    k._current = None
    import lib.llm_client as lc
    lc._client = None
    lc._client_key = None

    c1 = lc._get_client()
    k.rotate_key()
    c2 = lc._get_client()
    assert c1 is not c2


# ---------------------------------------------------------------------------
# generate() tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_text_only(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    import lib.api_keys as k
    k._cycle = None
    k._current = None
    import lib.llm_client as lc
    lc._client = None
    lc._client_key = None

    mock_response = MagicMock()
    mock_response.text = "hello"
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(lc, "_get_client", return_value=mock_client):
        result = await lc.generate("gemini-2.5-flash-lite", "say hello")

    assert result == "hello"
    mock_client.aio.models.generate_content.assert_called_once()
    call_kwargs = mock_client.aio.models.generate_content.call_args
    assert call_kwargs.kwargs["contents"] == "say hello"


@pytest.mark.asyncio
async def test_generate_multimodal_contents_list(monkeypatch):
    """Amendment 5: list contents passed through unchanged — no fall-back path."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    import lib.api_keys as k
    k._cycle = None
    k._current = None
    import lib.llm_client as lc
    lc._client = None
    lc._client_key = None

    fake_part = _fake_part()
    contents_list = ["describe this image", fake_part]

    mock_response = MagicMock()
    mock_response.text = "it is an image"
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(lc, "_get_client", return_value=mock_client):
        result = await lc.generate("gemini-2.5-flash-lite", contents_list)

    assert result == "it is an image"
    call_kwargs = mock_client.aio.models.generate_content.call_args
    assert call_kwargs.kwargs["contents"] is contents_list


def test_generate_sync_multimodal_contents_list(monkeypatch):
    """Amendment 5 covers generate_sync too."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    import lib.api_keys as k
    k._cycle = None
    k._current = None
    import lib.llm_client as lc
    lc._client = None
    lc._client_key = None

    fake_part = _fake_part()
    contents_list = ["describe", fake_part]

    mock_response = MagicMock()
    mock_response.text = "sync multimodal ok"
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(lc, "_get_client", return_value=mock_client):
        result = lc.generate_sync("gemini-2.5-flash-lite", contents_list)

    assert result == "sync multimodal ok"
    call_kwargs = mock_client.aio.models.generate_content.call_args
    assert call_kwargs.kwargs["contents"] is contents_list


def test_generate_sync_text(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    import lib.api_keys as k
    k._cycle = None
    k._current = None
    import lib.llm_client as lc
    lc._client = None
    lc._client_key = None

    mock_response = MagicMock()
    mock_response.text = "sync text ok"
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(lc, "_get_client", return_value=mock_client):
        result = lc.generate_sync("gemini-2.5-flash-lite", "hello sync")

    assert isinstance(result, str)
    assert result == "sync text ok"


@pytest.mark.asyncio
async def test_generate_does_not_retry_on_400(monkeypatch):
    """Non-retriable errors raise immediately without retry."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    import lib.api_keys as k
    k._cycle = None
    k._current = None
    import lib.llm_client as lc
    lc._client = None
    lc._client_key = None

    call_count = 0

    async def _fail_400(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise _make_api_error(400)

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = _fail_400

    with patch.object(lc, "_get_client", return_value=mock_client):
        with pytest.raises(APIError) as exc_info:
            await lc.generate("gemini-2.5-flash-lite", "test")

    assert call_count == 1  # no retries
    assert exc_info.value.code == 400


@pytest.mark.asyncio
async def test_generate_rotates_on_429(monkeypatch):
    """On 429, rotate_key() is called and the retry uses the new key."""
    monkeypatch.setenv("OMNIGRAPH_GEMINI_KEYS", "k1,k2")
    import lib.api_keys as k
    k._cycle = None
    k._current = None
    import lib.llm_client as lc
    lc._client = None
    lc._client_key = None

    keys_used: list[str] = []
    call_count = 0

    async def _generate_content(*, model, contents, **kwargs):
        nonlocal call_count
        call_count += 1
        keys_used.append(k.current_key())
        if call_count == 1:
            raise _make_api_error(429)
        mock_resp = MagicMock()
        mock_resp.text = "success"
        return mock_resp

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = _generate_content

    with patch.object(lc, "_get_client", return_value=mock_client):
        result = await lc.generate("gemini-2.5-flash-lite", "test")

    assert result == "success"
    assert call_count == 2
    # Keys used in subsequent calls must differ (rotation happened)
    assert len(set(keys_used)) == 2


# ---------------------------------------------------------------------------
# aembed() tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aembed_success(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    import lib.api_keys as k
    k._cycle = None
    k._current = None
    import lib.llm_client as lc
    lc._client = None
    lc._client_key = None

    embed_val1 = MagicMock()
    embed_val1.values = [0.1, 0.2, 0.3]
    embed_val2 = MagicMock()
    embed_val2.values = [0.4, 0.5, 0.6]
    mock_embed_response = MagicMock()
    mock_embed_response.embeddings = [embed_val1, embed_val2]

    mock_client = MagicMock()
    mock_client.aio.models.embed_content = AsyncMock(return_value=mock_embed_response)

    with patch.object(lc, "_get_client", return_value=mock_client):
        result = await lc.aembed("gemini-embedding-2", ["text1", "text2"])

    assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
