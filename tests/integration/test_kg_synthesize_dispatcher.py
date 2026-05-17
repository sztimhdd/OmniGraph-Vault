"""Integration tests for kg_synthesize / kb_synthesize → dispatcher path.

kdb-2-03 verification:
  - test_dispatcher_path_databricks_serving (LLM-DBX-02)
  - test_llm_dbx_04_serving_unavailable_falls_back_to_fts5 (LLM-DBX-04 via Decision 1)

Mocked end-to-end (no real Model Serving calls). Decision 1 — translation
in dispatcher — means the LLM-DBX-04 test exercises the kdb-2-02 shim through
the EXISTING kb/services/synthesize.py exception path, NOT a new reason code.

Full-stack kb_synthesize integration (mocking LightRAG + invoking the
``/api/synthesize`` entry point + asserting ``job.confidence=='fts5_fallback'``)
is deferred to kdb-3 UAT for two reasons:
  (a) heavyweight LightRAG mocking inflates test time/maintenance;
  (b) the existing kb-v2.1-1 KG MODE HARDENING tests already cover the
      ``except Exception as e`` fallback path for any underlying exception
      type — the only new contract this milestone owns is the dispatcher-
      layer translation, which is exactly what the second test pins.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DDPATH = str(REPO_ROOT / "databricks-deploy")


def _purge(names: list[str]) -> None:
    """Force-remove modules from sys.modules so next import re-evaluates."""
    for n in names:
        sys.modules.pop(n, None)


@pytest.mark.integration
async def test_dispatcher_path_databricks_serving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM-DBX-02: setting OMNIGRAPH_LLM_PROVIDER=databricks_serving causes
    kg_synthesize.synthesize_response → LightRAG construction at line 106 →
    get_llm_func() to enter the kdb-2-02 databricks_serving branch and call
    lightrag_databricks_provider.make_llm_func(). We mock make_llm_func to
    return a sentinel async callable that records its invocation; assert the
    sentinel was constructed AND that the wrapped callable produced by the
    translation shim invokes the sentinel on the happy path.
    """
    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "databricks_serving")
    if DDPATH not in sys.path:
        sys.path.insert(0, DDPATH)
    _purge(["lib.llm_complete", "lightrag_databricks_provider"])

    sentinel_calls: list[str] = []

    async def sentinel_llm(
        prompt,
        system_prompt=None,
        history_messages=None,
        **kwargs,
    ) -> str:
        sentinel_calls.append(prompt)
        return "sentinel-llm-response"

    fake_mod = types.ModuleType("lightrag_databricks_provider")
    called = {"make": False}

    def fake_make():
        called["make"] = True
        return sentinel_llm

    fake_mod.make_llm_func = fake_make  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lightrag_databricks_provider", fake_mod)

    # Resolve the dispatcher; this should hit the new branch.
    from lib.llm_complete import get_llm_func

    fn = get_llm_func()
    assert called["make"] is True, (
        "make_llm_func was never invoked — dispatcher branch not exercised"
    )

    # Invoke the wrapped callable; sentinel should record the call.
    result = await fn("trigger-prompt")
    assert "sentinel-llm-response" in result
    assert "trigger-prompt" in sentinel_calls


@pytest.mark.integration
async def test_llm_dbx_04_serving_unavailable_falls_back_to_fts5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM-DBX-04 via Decision 1: when make_llm_func's returned callable
    raises a 503-equivalent RuntimeError, the kdb-2-02 translation shim
    re-raises unchanged and kb/services/synthesize.py's existing
    ``except Exception as e`` handler routes to FTS5 fallback. We assert
    the get_llm_func()-returned wrapper raises the original error type
    when invoked, which confirms the translation contract (no swallowing,
    no remap to a new reason code).

    Full-stack kb_synthesize integration is verified at higher level via
    the existing kb-v2.1-1 KG MODE HARDENING tests; this test pins the
    dispatcher-layer behavior that makes them work for the
    databricks_serving provider.
    """
    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "databricks_serving")
    if DDPATH not in sys.path:
        sys.path.insert(0, DDPATH)
    _purge(["lib.llm_complete", "lightrag_databricks_provider"])

    async def boom(
        prompt,
        system_prompt=None,
        history_messages=None,
        **kwargs,
    ):
        raise RuntimeError("HTTP 503 Service Unavailable: model_overloaded")

    fake_mod = types.ModuleType("lightrag_databricks_provider")
    fake_mod.make_llm_func = lambda: boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lightrag_databricks_provider", fake_mod)

    from lib.llm_complete import get_llm_func

    fn = get_llm_func()
    with pytest.raises(RuntimeError, match="503"):
        await fn("trigger-503")

    # Decision 1 contract: dispatcher's translation shim re-raises unchanged;
    # this means kb/services/synthesize.py's 'except Exception as e' branch
    # (line ~448) catches it, and the EXISTING reason-code path then routes
    # to 'fts5_fallback' confidence + the existing kg_unavailable bucket.
    # No new reason code was introduced anywhere in the codebase.
