"""Back-compat shim — Phase 7 D-09.

The real implementation lives in ``lib/lightrag_embedding.py``.
This module re-exports ``embedding_func`` so existing importers keep working
without code changes until they are migrated in Waves 1-2.

Amendment 2: ``from lightrag_embedding import embedding_func`` yields the same
object as ``from lib import embedding_func`` (identity check in tests).
"""
from lib.lightrag_embedding import embedding_func  # noqa: F401

__all__ = ["embedding_func"]
