"""TOOL-03 + CONFIG-03 Wave-3-half tests — Vertex Grounding auto-detect.

Covers:
- Test 1 ``test_autodetect_via_env_provider_vertex``: ``OMNIGRAPH_LLM_PROVIDER=vertex_gemini``
  → ``cfg.google_search_grounding is vertex_gemini_grounding`` (identity).
- Test 2 ``test_autodetect_via_module_path_vertex``: env unset, bound
  ``llm_complete.__module__ == "lib.vertex_gemini_complete"`` → identity bind.
- Test 3 ``test_autodetect_deepseek_yields_no_grounding``: non-Vertex provider
  → ``cfg.google_search_grounding is None``.
- Test 4 ``test_no_grounding_cli_override_nullifies_autodetect``: env auto-detects
  Vertex, then ``dataclasses.replace(cfg, google_search_grounding=None)``
  (the path ``__main__.py:_amain`` takes when ``ns.no_grounding``) overrides.
- Test 5 ``test_grounding_callable_is_zero_arg_factory_compatible``: signature
  inspection only — ``inspect.iscoroutinefunction`` true; single positional
  ``query`` parameter. Does NOT call the function (would attempt real Vertex API).

All tests apply the monkeypatch.delenv discipline: every from_env() test
explicitly delenvs OMNIGRAPH_LLM_PROVIDER, TAVILY_API_KEY, BRAVE_SEARCH_API_KEY
at the top, then sets only the env vars its scenario needs.
"""
from __future__ import annotations

import dataclasses
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
def test_autodetect_via_env_provider_vertex(monkeypatch, tmp_path):
    """OMNIGRAPH_LLM_PROVIDER=vertex_gemini → cfg.google_search_grounding is non-None."""
    from lib.research.config import from_env
    from lib.research.tools.web_search import vertex_gemini_grounding

    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "vertex_gemini")
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    # llm_complete is a stub; its __module__ doesn't matter — env signal suffices.
    stub_llm = AsyncMock()
    with patch("lib.llm_complete.get_llm_func", return_value=stub_llm), \
         patch("lib.lightrag_embedding.embedding_func", new=AsyncMock()), \
         patch("lib.vision_cascade.VisionCascade", new=MagicMock()):
        cfg = from_env()

    assert cfg.google_search_grounding is vertex_gemini_grounding


@pytest.mark.unit
def test_autodetect_via_module_path_vertex(monkeypatch, tmp_path):
    """Bound llm_complete.__module__ == 'lib.vertex_gemini_complete' → grounding non-None."""
    from lib.research.config import from_env
    from lib.research.tools.web_search import vertex_gemini_grounding

    monkeypatch.delenv("OMNIGRAPH_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    # Construct a stub callable whose __module__ matches the Vertex impl module path.
    async def _stub_vertex_complete(*args, **kwargs):
        return None
    _stub_vertex_complete.__module__ = "lib.vertex_gemini_complete"

    with patch("lib.llm_complete.get_llm_func", return_value=_stub_vertex_complete), \
         patch("lib.lightrag_embedding.embedding_func", new=AsyncMock()), \
         patch("lib.vision_cascade.VisionCascade", new=MagicMock()):
        cfg = from_env()

    assert cfg.google_search_grounding is vertex_gemini_grounding


@pytest.mark.unit
def test_autodetect_deepseek_yields_no_grounding(monkeypatch, tmp_path):
    """Provider=deepseek AND llm_complete.__module__ != vertex → grounding None."""
    from lib.research.config import from_env

    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    async def _stub_deepseek_complete(*args, **kwargs):
        return None
    _stub_deepseek_complete.__module__ = "lib.deepseek_complete"

    with patch("lib.llm_complete.get_llm_func", return_value=_stub_deepseek_complete), \
         patch("lib.lightrag_embedding.embedding_func", new=AsyncMock()), \
         patch("lib.vision_cascade.VisionCascade", new=MagicMock()):
        cfg = from_env()

    assert cfg.google_search_grounding is None


@pytest.mark.unit
def test_no_grounding_cli_override_nullifies_autodetect(monkeypatch, tmp_path):
    """from_env() returns non-None grounding; --no-grounding CLI override → None."""
    from lib.research.config import from_env

    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "vertex_gemini")
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    with patch("lib.llm_complete.get_llm_func", return_value=AsyncMock()), \
         patch("lib.lightrag_embedding.embedding_func", new=AsyncMock()), \
         patch("lib.vision_cascade.VisionCascade", new=MagicMock()):
        cfg = from_env()

    assert cfg.google_search_grounding is not None  # auto-detected

    # Simulate the CLI override path from __main__.py:_amain
    overrides = {"google_search_grounding": None}
    cfg2 = dataclasses.replace(cfg, **overrides)
    assert cfg2.google_search_grounding is None  # CLI override wins


@pytest.mark.unit
def test_grounding_callable_is_zero_arg_factory_compatible():
    """Signature inspection — vertex_gemini_grounding is async (query: str) -> str.

    Does NOT call the function (would attempt real Vertex API). Pins the
    contract: matches the dataclass slot's Callable | None typing AND the
    Verifier's _grounding_tool wrapper signature.
    """
    from lib.research.tools.web_search import vertex_gemini_grounding

    assert inspect.iscoroutinefunction(vertex_gemini_grounding)
    sig = inspect.signature(vertex_gemini_grounding)
    params = list(sig.parameters.values())
    assert len(params) == 1
    assert params[0].name == "query"
    assert params[0].kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.POSITIONAL_ONLY,
    )
