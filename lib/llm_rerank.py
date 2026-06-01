"""Provider dispatcher for LightRAG ``rerank_model_func`` — v1.1.P2-3-perf-fix-A/B.

OMNIGRAPH_LLM_RERANK_PROVIDER env selects the backend:
  - ``databricks_serving`` (default for Databricks Apps deploy) →
    ``databricks-deploy/lightrag_databricks_rerank.make_rerank_func()``
  - ``vertex_gemini`` (default for Aliyun ECS deploy) →
    ``lib.vertex_gemini_rerank.make_rerank_func()``
  - ``disabled`` → returns (None, False); KG paths fall back to mode='hybrid'

Mirrors lib/llm_complete.py dispatcher pattern.
"""
from __future__ import annotations

import os
from typing import Callable

_VALID = ("databricks_serving", "vertex_gemini", "disabled")


def get_rerank_func() -> tuple[Callable[..., object] | None, bool]:
    """Return (rerank_func, ok_flag). ok=False signals graceful degrade."""
    provider = os.environ.get("OMNIGRAPH_LLM_RERANK_PROVIDER", "databricks_serving").strip() \
        or "databricks_serving"
    if provider == "disabled":
        return None, False
    if provider == "databricks_serving":
        try:
            import sys as _sys
            _here = os.path.dirname(os.path.abspath(__file__))
            _repo_root = os.path.abspath(os.path.join(_here, os.pardir))
            _ddpath = os.path.join(_repo_root, "databricks-deploy")
            if _ddpath not in _sys.path:
                _sys.path.insert(0, _ddpath)
            from lightrag_databricks_rerank import make_rerank_func  # type: ignore
            return make_rerank_func(), True
        except Exception:  # noqa: BLE001 — graceful degrade
            return None, False
    if provider == "vertex_gemini":
        try:
            from lib.vertex_gemini_rerank import make_rerank_func  # type: ignore
            return make_rerank_func(), True
        except Exception:  # noqa: BLE001 — graceful degrade
            return None, False
    raise ValueError(
        f"Unknown OMNIGRAPH_LLM_RERANK_PROVIDER={provider!r}; "
        f"expected one of {_VALID}"
    )


__all__ = ["get_rerank_func"]
