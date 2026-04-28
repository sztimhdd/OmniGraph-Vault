"""Tests for lightrag_llm.deepseek_model_complete — Plan 05-00c Task 0c.1.

Scope: contract tests against LightRAG's `llm_model_func` signature.
NO live API calls — all tests mock openai.AsyncOpenAI.chat.completions.create.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _ensure_deepseek_key(monkeypatch):
    """All tests in this module assume DEEPSEEK_API_KEY is present."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    # Force re-import so module-level _client is rebuilt against patched env.
    import sys
    for mod in ("lib.llm_deepseek", "lightrag_llm"):
        sys.modules.pop(mod, None)


def _make_chat_response(text: str) -> MagicMock:
    """Build a MagicMock shaped like an openai ChatCompletion."""
    choice = MagicMock()
    choice.message.content = text
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# Test 1: Bare prompt -> single user message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bare_prompt_sends_single_user_message():
    """A plain `deepseek_model_complete('hi')` call sends [user:'hi'] to default model."""
    import lib.llm_deepseek as ld

    mock_create = AsyncMock(return_value=_make_chat_response("hello back"))
    with patch.object(ld._client.chat.completions, "create", mock_create):
        result = await ld.deepseek_model_complete("hi")

    assert result == "hello back"
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["model"] == "deepseek-v4-flash"
    assert call_kwargs["messages"] == [{"role": "user", "content": "hi"}]
    assert call_kwargs["stream"] is False


# ---------------------------------------------------------------------------
# Test 2: System prompt prepended
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_system_prompt_prepends_system_role():
    """system_prompt='sys' -> [system:'sys', user:'hi']."""
    import lib.llm_deepseek as ld

    mock_create = AsyncMock(return_value=_make_chat_response("ok"))
    with patch.object(ld._client.chat.completions, "create", mock_create):
        await ld.deepseek_model_complete("hi", system_prompt="sys")

    messages = mock_create.call_args.kwargs["messages"]
    assert messages == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]


# ---------------------------------------------------------------------------
# Test 3: History messages interleave between system and current user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_messages_ordering():
    """Order is: [system?, *history_messages, user=current_prompt]."""
    import lib.llm_deepseek as ld

    history = [
        {"role": "user", "content": "prev"},
        {"role": "assistant", "content": "prev-reply"},
    ]
    mock_create = AsyncMock(return_value=_make_chat_response("ok"))
    with patch.object(ld._client.chat.completions, "create", mock_create):
        await ld.deepseek_model_complete(
            "hi", system_prompt="sys", history_messages=history
        )

    messages = mock_create.call_args.kwargs["messages"]
    assert messages == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "prev"},
        {"role": "assistant", "content": "prev-reply"},
        {"role": "user", "content": "hi"},
    ]


# ---------------------------------------------------------------------------
# Test 4: Response extraction returns plain string
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_plain_string_from_choices():
    """response.choices[0].message.content is returned verbatim — no streaming, no wrapping."""
    import lib.llm_deepseek as ld

    mock_create = AsyncMock(return_value=_make_chat_response("plain content"))
    with patch.object(ld._client.chat.completions, "create", mock_create):
        result = await ld.deepseek_model_complete("hi")

    assert result == "plain content"
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Test 5: DEEPSEEK_MODEL env var override
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deepseek_model_env_override(monkeypatch):
    """DEEPSEEK_MODEL env var overrides the default model."""
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    # Re-import to pick up env change at module init
    import sys
    sys.modules.pop("lib.llm_deepseek", None)
    import lib.llm_deepseek as ld

    mock_create = AsyncMock(return_value=_make_chat_response("ok"))
    with patch.object(ld._client.chat.completions, "create", mock_create):
        await ld.deepseek_model_complete("hi")

    assert mock_create.call_args.kwargs["model"] == "deepseek-v4-pro"


# ---------------------------------------------------------------------------
# Test 6: Missing DEEPSEEK_API_KEY raises at module import
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_runtime_error(monkeypatch):
    """If DEEPSEEK_API_KEY is absent, module import raises RuntimeError."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    import sys
    sys.modules.pop("lib.llm_deepseek", None)

    with pytest.raises(RuntimeError) as exc_info:
        import lib.llm_deepseek  # noqa: F401

    assert "DEEPSEEK_API_KEY" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Bonus contract tests — keyword_extraction kwarg swallowed, root shim parity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keyword_extraction_kwarg_is_swallowed():
    """LightRAG passes keyword_extraction=True for some calls; we don't forward it."""
    import lib.llm_deepseek as ld

    mock_create = AsyncMock(return_value=_make_chat_response("ok"))
    with patch.object(ld._client.chat.completions, "create", mock_create):
        await ld.deepseek_model_complete("hi", keyword_extraction=True)

    # Neither messages nor the outer create() kwargs leak keyword_extraction.
    assert "keyword_extraction" not in mock_create.call_args.kwargs


def test_root_shim_reexports_same_object():
    """Root lightrag_llm.deepseek_model_complete IS lib.llm_deepseek.deepseek_model_complete."""
    from lightrag_llm import deepseek_model_complete as shim_ref
    from lib.llm_deepseek import deepseek_model_complete as lib_ref
    assert shim_ref is lib_ref
