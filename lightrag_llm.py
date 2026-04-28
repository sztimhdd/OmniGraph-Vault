"""Back-compat re-export — Plan 05-00c Task 0c.1.

The real implementation lives in ``lib/llm_deepseek.py``. This module re-exports
``deepseek_model_complete`` so call sites can do
``from lightrag_llm import deepseek_model_complete`` — matching the same
top-level import pattern as ``lightrag_embedding`` (the sibling embedding
shim introduced in Phase 7 D-09).
"""
from lib.llm_deepseek import deepseek_model_complete  # noqa: F401

__all__ = ["deepseek_model_complete"]
