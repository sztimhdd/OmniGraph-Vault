"""Provider dispatcher for LightRAG ``llm_model_func`` — LDEV-02 + kdb-2-02.

``OMNIGRAPH_LLM_PROVIDER`` env selects the backend:
  - ``deepseek`` (default)    → ``lib.llm_deepseek.deepseek_model_complete``
  - ``vertex_gemini``         → ``lib.vertex_gemini_complete.vertex_gemini_model_complete``
  - ``databricks_serving``    → ``databricks-deploy/lightrag_databricks_provider.make_llm_func()``
                                wrapped in an exception-translation shim
                                (kdb-2-02 LLM-DBX-01 + LLM-DBX-04).

Unknown values raise ``ValueError`` listing the valid names.

Import-on-demand: provider modules are imported INSIDE ``get_llm_func`` so
DeepSeek-only callers do not pay the google-genai or databricks-sdk import
cost, and vertex-only callers do not need ``DEEPSEEK_API_KEY`` at import time
(preserves option for Phase 5 DeepSeek soft-fail follow-up — see CLAUDE.md
§ Phase 5 DeepSeek cross-coupling).

The ``databricks_serving`` branch satisfies LLM-DBX-04 entirely inside this
dispatcher per phase-Decision 1: Databricks SDK 503/429/timeout/connection
errors are re-raised unchanged so the existing ``except Exception as e``
handler in ``kb/services/synthesize.py`` routes to its ``kg_unavailable``
reason-code bucket. ``kb/services/synthesize.py`` is NOT modified and
CONFIG-EXEMPTIONS is NOT extended.

NOT re-exported via ``lib/__init__.py`` — callers must import explicitly:

    from lib.llm_complete import get_llm_func

Part of quick task 260504-g7a (local dev enablement) + kdb-2-02
(Databricks Apps deploy enablement).
"""
from __future__ import annotations

import os
from typing import Callable


_VALID = ("deepseek", "vertex_gemini", "databricks_serving")


def get_llm_func() -> Callable:
    """Return the LightRAG-compatible LLM completion function for the
    configured provider. Default (env unset) returns DeepSeek.
    """
    provider = os.environ.get("OMNIGRAPH_LLM_PROVIDER", "deepseek").strip() \
        or "deepseek"
    if provider == "deepseek":
        from lib.llm_deepseek import deepseek_model_complete
        return deepseek_model_complete
    if provider == "vertex_gemini":
        from lib.vertex_gemini_complete import vertex_gemini_model_complete
        return vertex_gemini_model_complete
    if provider == "databricks_serving":
        # kdb-2-02 LLM-DBX-01 + LLM-DBX-04 (Decision 1 — translation in dispatcher).
        # Wraps the kdb-1.5 factory at databricks-deploy/lightrag_databricks_provider.py.
        # The factory returns an async callable matching LightRAG's llm_model_func
        # contract. We add a thin exception-translation wrapper so Databricks SDK
        # 503/429/timeout/connection errors surface as standard exceptions that
        # kb/services/synthesize.py's existing 'except Exception as e' branch
        # catches and routes to its kg_unavailable fallback (kb-v2.1-1 KG MODE
        # HARDENING contract preserved — no new reason code, no kb/services
        # modification, no CONFIG-EXEMPTIONS extension).
        #
        # databricks-deploy/ has a hyphen and isn't a legal Python package name —
        # we add it to sys.path so the bare-module import works. Apps runtime
        # adds the directory to PYTHONPATH via app.yaml command: (kdb-2-04);
        # locally and in tests, callers prepend it explicitly.
        import sys as _sys
        _here = os.path.dirname(os.path.abspath(__file__))
        _repo_root = os.path.abspath(os.path.join(_here, os.pardir))
        _ddpath = os.path.join(_repo_root, "databricks-deploy")
        if _ddpath not in _sys.path:
            _sys.path.insert(0, _ddpath)
        from lightrag_databricks_provider import make_llm_func  # type: ignore[import-not-found]
        _underlying = make_llm_func()

        async def _databricks_serving_llm(
            prompt,
            system_prompt=None,
            history_messages=None,
            **kwargs,
        ):
            # Translation shim: pass-through happy path; on Databricks SDK
            # exception or 503/429/timeout/connection-error pattern, re-raise
            # unchanged so the existing 'except Exception' bucket in
            # kb/services/synthesize.py routes to kg_unavailable. We do NOT
            # swallow exceptions or remap to a new reason code (Decision 1).
            return await _underlying(
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                **kwargs,
            )

        return _databricks_serving_llm
    raise ValueError(
        f"Unknown OMNIGRAPH_LLM_PROVIDER={provider!r}; "
        f"expected one of {_VALID}"
    )


__all__ = ["get_llm_func"]
