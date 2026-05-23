"""Web-tool callables for the Verifier stage agent loop.

Submodule layout (subject to extension in ar-4):
  - web_search.py — Tavily search/extract, Brave fallback, cascade factory
"""
from __future__ import annotations

from .web_search import (
    brave_search,
    make_web_search_with_fallback,
    tavily_extract,
    tavily_search,
)

__all__ = [
    "brave_search",
    "make_web_search_with_fallback",
    "tavily_extract",
    "tavily_search",
]
