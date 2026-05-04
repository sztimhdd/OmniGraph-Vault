"""Unit tests for lib.llm_complete.get_llm_func (LDEV-02).

Mock-only — zero outbound HTTP. Uses pytest monkeypatch for env scoping.
"""
from __future__ import annotations

import sys

import pytest


def _purge_modules(names: list[str]) -> None:
    """Force-remove modules from sys.modules so next import re-evaluates."""
    for n in names:
        sys.modules.pop(n, None)


def test_default_unset_returns_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    """With OMNIGRAPH_LLM_PROVIDER unset, dispatcher returns DeepSeek func."""
    monkeypatch.delenv("OMNIGRAPH_LLM_PROVIDER", raising=False)
    from lib.llm_complete import get_llm_func
    fn = get_llm_func()
    assert fn.__name__ == "deepseek_model_complete"


def test_explicit_deepseek_returns_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit 'deepseek' routes to DeepSeek func."""
    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "deepseek")
    from lib.llm_complete import get_llm_func
    fn = get_llm_func()
    assert fn.__name__ == "deepseek_model_complete"


def test_vertex_gemini_returns_vertex_func(monkeypatch: pytest.MonkeyPatch) -> None:
    """OMNIGRAPH_LLM_PROVIDER=vertex_gemini routes to Vertex Gemini func."""
    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "vertex_gemini")
    from lib.llm_complete import get_llm_func
    fn = get_llm_func()
    assert fn.__name__ == "vertex_gemini_model_complete"


def test_unknown_provider_raises_valueerror(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown provider value raises ValueError citing the invalid name."""
    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "nope")
    from lib.llm_complete import get_llm_func
    with pytest.raises(ValueError, match="nope"):
        get_llm_func()


def test_import_does_not_import_vertex_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing lib.llm_complete must NOT pull in lib.vertex_gemini_complete.

    Pins the lazy-import contract: provider modules are imported inside
    get_llm_func(), not at module load. This keeps DeepSeek-only callers
    from paying the google-genai import cost.
    """
    _purge_modules(["lib.llm_complete", "lib.vertex_gemini_complete"])
    import lib.llm_complete  # noqa: F401
    assert "lib.vertex_gemini_complete" not in sys.modules
