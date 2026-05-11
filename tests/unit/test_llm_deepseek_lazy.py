"""Pin the lazy-import contract for lib.llm_deepseek (Defect D — quick 260510-l14).

Pre-fix state: ``lib/__init__.py:34`` eagerly re-exports
``deepseek_model_complete``, and ``lib/llm_deepseek.py`` calls
``_require_api_key()`` at module import. This means ``import lib`` raises
RuntimeError when ``DEEPSEEK_API_KEY`` is unset — even for Gemini/Vertex-only
workloads (the documented "Phase 5 DeepSeek cross-coupling" / Hermes FLAG 2 in
CLAUDE.md).

Post-fix state:
  - ``lib/__init__.py`` no longer re-exports ``deepseek_model_complete``.
    Callers MUST import via ``from lib.llm_deepseek import ...`` (full path).
  - ``lib/llm_deepseek.py`` defers the key check + AsyncOpenAI client
    construction to first call (lazy ``_get_client()`` helper).

These tests pin both invariants so the regression cannot return silently.
"""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _purge_modules(names: list[str]) -> None:
    """Force-remove modules from sys.modules so next import re-evaluates."""
    for n in names:
        sys.modules.pop(n, None)


def _make_chat_response(text: str) -> MagicMock:
    """Build a MagicMock shaped like an openai ChatCompletion."""
    choice = MagicMock()
    choice.message.content = text
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_import_lib_without_deepseek_key_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """``import lib`` must NOT raise when DEEPSEEK_API_KEY is unset (Defect D).

    Pre-fix: lib/__init__.py:34 eagerly imports lib.llm_deepseek which calls
    _require_api_key() at module load → RuntimeError.
    Post-fix: deepseek_model_complete is no longer in lib/__init__.py;
    lib.llm_deepseek defers key check.
    """
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    # Block ~/.hermes/.env auto-load by redirecting HOME so config.load_env
    # doesn't repopulate the env from disk.
    monkeypatch.setenv("HOME", "/nonexistent-home-for-test")
    monkeypatch.setenv("USERPROFILE", "Z:\\nonexistent-home-for-test")
    _purge_modules(["lib", "lib.llm_deepseek", "lightrag_llm"])

    import lib  # noqa: F401 — must not raise


def test_calling_deepseek_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling deepseek_model_complete without the key MUST raise RuntimeError.

    The check is deferred from import to first call, but the diagnostic must
    remain clear and actionable — same message as the existing
    ``_require_api_key()``.
    """
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("HOME", "/nonexistent-home-for-test")
    monkeypatch.setenv("USERPROFILE", "Z:\\nonexistent-home-for-test")
    _purge_modules(["lib", "lib.llm_deepseek", "lightrag_llm"])

    from lib.llm_deepseek import deepseek_model_complete

    import asyncio

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(deepseek_model_complete("hi"))
    assert "DEEPSEEK_API_KEY" in str(exc_info.value)


def test_calling_deepseek_with_key_uses_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """With DEEPSEEK_API_KEY set, the first call constructs the AsyncOpenAI
    client and dispatches the request normally."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    _purge_modules(["lib", "lib.llm_deepseek", "lightrag_llm"])

    import lib.llm_deepseek as ld

    # Force a fresh lazy-init by clearing the cached client.
    ld._client = None

    mock_create = AsyncMock(return_value=_make_chat_response("hello back"))
    # Patch AsyncOpenAI so no real client is constructed (and no real network).
    fake_client = MagicMock()
    fake_client.chat.completions.create = mock_create
    with patch.object(ld, "AsyncOpenAI", return_value=fake_client):
        import asyncio
        result = asyncio.run(ld.deepseek_model_complete("hi"))

    assert result == "hello back"
    mock_create.assert_awaited_once()


def test_lib_init_does_not_export_deepseek_anymore(monkeypatch: pytest.MonkeyPatch) -> None:
    """``import lib`` must NOT expose ``deepseek_model_complete``.

    Callers must use the full path ``from lib.llm_deepseek import ...``. Pinning
    this contract prevents the eager re-export from sneaking back into
    lib/__init__.py.
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    _purge_modules(["lib", "lib.llm_deepseek", "lightrag_llm"])

    import lib

    assert not hasattr(lib, "deepseek_model_complete"), (
        "lib.deepseek_model_complete must not be re-exported (Defect D). "
        "Callers should use 'from lib.llm_deepseek import deepseek_model_complete'."
    )
    assert "deepseek_model_complete" not in getattr(lib, "__all__", [])


def test_default_timeout_is_300(monkeypatch: pytest.MonkeyPatch) -> None:
    """AsyncOpenAI client must be constructed with timeout=300.0 by default.

    Pins DSTO-01: _DEEPSEEK_TIMEOUT_S reads from OMNIGRAPH_DEEPSEEK_TIMEOUT
    with a default of 300 (raised from 120).
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.delenv("OMNIGRAPH_DEEPSEEK_TIMEOUT", raising=False)
    _purge_modules(["lib", "lib.llm_deepseek", "lightrag_llm"])

    import lib.llm_deepseek as ld

    ld._client = None

    captured_timeout = None

    def mock_ctor(**kwargs):
        nonlocal captured_timeout
        captured_timeout = kwargs.get("timeout")
        return MagicMock()

    with patch.object(ld, "AsyncOpenAI", side_effect=mock_ctor):
        ld._get_client()

    assert captured_timeout == 300.0, f"Expected 300.0, got {captured_timeout}"


def test_env_override_changes_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """OMNIGRAPH_DEEPSEEK_TIMEOUT env var overrides the default at construction time.

    Pins DSTO-01: setting the env var to '60' results in timeout=60.0.
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("OMNIGRAPH_DEEPSEEK_TIMEOUT", "60")
    _purge_modules(["lib", "lib.llm_deepseek", "lightrag_llm"])

    import lib.llm_deepseek as ld

    ld._client = None

    captured_timeout = None

    def mock_ctor(**kwargs):
        nonlocal captured_timeout
        captured_timeout = kwargs.get("timeout")
        return MagicMock()

    with patch.object(ld, "AsyncOpenAI", side_effect=mock_ctor):
        ld._get_client()

    assert captured_timeout == 60.0, f"Expected 60.0, got {captured_timeout}"
