"""Unit tests for lib.llm_complete.get_llm_func (LDEV-02 + kdb-2-02 LLM-DBX-01).

Mock-only — zero outbound HTTP. Uses pytest monkeypatch for env scoping.
"""
from __future__ import annotations

import asyncio
import os
import sys
import types

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


# ---------------------------------------------------------------------------
# kdb-2-02 — databricks_serving provider branch (LLM-DBX-01 + LLM-DBX-04)
# ---------------------------------------------------------------------------


def test_databricks_serving_returns_factory_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OMNIGRAPH_LLM_PROVIDER=databricks_serving routes to the kdb-1.5 factory.

    Mocks lightrag_databricks_provider.make_llm_func to return a sentinel async
    callable; asserts get_llm_func() returns a callable that, when invoked,
    produces the sentinel's output (translation shim is a pass-through on
    happy path).
    """
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sys.path.insert(0, os.path.join(repo_root, "databricks-deploy"))
    _purge_modules(["lib.llm_complete", "lightrag_databricks_provider"])
    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "databricks_serving")

    async def sentinel_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        return f"sentinel:{prompt}"

    fake_mod = types.ModuleType("lightrag_databricks_provider")
    fake_mod.make_llm_func = lambda: sentinel_llm  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lightrag_databricks_provider", fake_mod)

    from lib.llm_complete import get_llm_func

    fn = get_llm_func()
    result = asyncio.run(fn("hi"))
    assert result == "sentinel:hi"


def test_unknown_provider_lists_databricks_in_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ValueError message lists 'databricks_serving' as a valid choice.

    Pins the _VALID extension; defends against accidental tuple revert.
    """
    _purge_modules(["lib.llm_complete"])
    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "nope-not-real")
    from lib.llm_complete import get_llm_func

    with pytest.raises(ValueError, match="databricks_serving"):
        get_llm_func()


def test_databricks_branch_is_lazy_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing lib.llm_complete must NOT pull lightrag_databricks_provider or databricks-sdk.

    Pins the lazy-import contract — DeepSeek-only callers should not pay
    databricks-sdk or kdb-1.5 factory import cost.
    """
    _purge_modules(
        [
            "lib.llm_complete",
            "lightrag_databricks_provider",
            "databricks.sdk",
        ]
    )
    import lib.llm_complete  # noqa: F401

    assert "lightrag_databricks_provider" not in sys.modules
    assert "databricks.sdk" not in sys.modules


def test_databricks_provider_error_path_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When factory's callable raises 503/429/timeout, dispatcher branch re-raises.

    LLM-DBX-04 contract via Decision 1 (translation in dispatcher): the wrapped
    callable surfaces an exception that kb/services/synthesize.py's existing
    'except Exception as e' handler catches and routes to kg_unavailable
    fallback. Test asserts the exception bubbles up; downstream-classification
    behavior is verified in kdb-2-03 integration test.
    """
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sys.path.insert(0, os.path.join(repo_root, "databricks-deploy"))
    _purge_modules(["lib.llm_complete", "lightrag_databricks_provider"])
    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "databricks_serving")

    async def boom(prompt, system_prompt=None, history_messages=None, **kwargs):
        raise RuntimeError("HTTP 503 Service Unavailable: model_overloaded")

    fake_mod = types.ModuleType("lightrag_databricks_provider")
    fake_mod.make_llm_func = lambda: boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lightrag_databricks_provider", fake_mod)

    from lib.llm_complete import get_llm_func

    fn = get_llm_func()
    with pytest.raises(RuntimeError, match="503"):
        asyncio.run(fn("trigger 503"))
