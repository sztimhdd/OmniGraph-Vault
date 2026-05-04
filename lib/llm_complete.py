"""Provider dispatcher for LightRAG ``llm_model_func`` — LDEV-02.

``OMNIGRAPH_LLM_PROVIDER`` env selects the backend:
  - ``deepseek`` (default)  → ``lib.llm_deepseek.deepseek_model_complete``
  - ``vertex_gemini``       → ``lib.vertex_gemini_complete.vertex_gemini_model_complete``

Unknown values raise ``ValueError`` listing the valid names.

Import-on-demand: provider modules are imported INSIDE ``get_llm_func`` so
DeepSeek-only callers do not pay the google-genai import cost, and vertex-only
callers do not need ``DEEPSEEK_API_KEY`` at import time (preserves option for
Phase 5 DeepSeek soft-fail follow-up — see CLAUDE.md § Phase 5 DeepSeek
cross-coupling).

NOT re-exported via ``lib/__init__.py`` — callers must import explicitly:

    from lib.llm_complete import get_llm_func

Part of quick task 260504-g7a (local dev enablement).
"""
from __future__ import annotations

import os
from typing import Callable


_VALID = ("deepseek", "vertex_gemini")


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
    raise ValueError(
        f"Unknown OMNIGRAPH_LLM_PROVIDER={provider!r}; "
        f"expected one of {_VALID}"
    )


__all__ = ["get_llm_func"]
