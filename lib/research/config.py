"""Env-driven ResearchConfig factory — single source of env reads (Axis 3).

All env vars are read here once at construction time. The hot path (orchestrator
+ stages) uses ResearchConfig fields only. Re-exports ResearchConfig from
.types so callers can do `from lib.research.config import ResearchConfig`.

Path defaults preserve the canonical `omonigraph` typo per CLAUDE.md — do NOT
"fix" it without a coordinated migration.
"""
from __future__ import annotations

import functools
import os
from pathlib import Path

from .tools.web_search import (
    brave_search,
    make_web_search_with_fallback,
    tavily_extract,
    tavily_search,
)
from .types import ResearchConfig


def _skipped_web_search(query: str) -> list[dict]:
    """Stub web_search used when TAVILY_API_KEY is unset (ar-1 default).

    Returns empty list. WebBaseline stage detects this and emits status='skipped'
    with reason='TAVILY_API_KEY unset — ar-1 stub mode'.
    """
    return []


def from_env() -> ResearchConfig:
    """Read env once and compose a ResearchConfig.

    All env reads happen here. Hot path uses ResearchConfig fields only (Axis 3).
    """
    base_dir = (
        Path(os.environ["OMNIGRAPH_BASE_DIR"])
        if os.environ.get("OMNIGRAPH_BASE_DIR")
        else Path.home() / ".hermes" / "omonigraph-vault"  # 'omonigraph' typo is canonical
    )

    rag_working_dir = base_dir / "lightrag_storage"

    # Lazy imports — keep lib.research importable even if these modules have
    # init-time side effects, and avoid eager cost for callers that mock these.
    from lib.llm_complete import get_llm_func
    llm_complete = get_llm_func()

    from lib.lightrag_embedding import embedding_func

    from lib.vision_cascade import VisionCascade
    vision_cascade = VisionCascade()

    # Web search — ar-3 Wave 1 wiring (TOOL-01 + TOOL-02 + CONFIG-03 env-half).
    tavily_key = os.environ.get("TAVILY_API_KEY")
    brave_key = os.environ.get("BRAVE_SEARCH_API_KEY")

    # Brave fallback callable — exposed regardless of Tavily presence (observability slot).
    if brave_key:
        web_search_fallback = functools.partial(brave_search, api_key=brave_key)
    else:
        web_search_fallback = None

    # Tavily extract callable — only when Tavily key set.
    if tavily_key:
        web_extract = functools.partial(tavily_extract, api_key=tavily_key)
    else:
        web_extract = None

    # Three-way cascade for web_search:
    #   - both keys → cascade-wrapped Tavily+Brave
    #   - Tavily only → bare Tavily partial
    #   - neither (or Brave-only) → ar-1 _skipped_web_search stub (cascade requires both ends)
    if tavily_key and brave_key:
        web_search = make_web_search_with_fallback(
            functools.partial(tavily_search, api_key=tavily_key),
            functools.partial(brave_search, api_key=brave_key),
        )
    elif tavily_key:
        web_search = functools.partial(tavily_search, api_key=tavily_key)
    else:
        web_search = _skipped_web_search

    google_search_grounding = None  # Wave 3 wires Vertex Grounding auto-detect

    output_dir = (
        Path(os.environ["OMNIGRAPH_RESEARCH_OUTPUT_DIR"])
        if os.environ.get("OMNIGRAPH_RESEARCH_OUTPUT_DIR")
        else None
    )
    telemetry_jsonl = (
        Path(os.environ["OMNIGRAPH_RESEARCH_TELEMETRY_JSONL"])
        if os.environ.get("OMNIGRAPH_RESEARCH_TELEMETRY_JSONL")
        else None
    )

    return ResearchConfig(
        rag_working_dir=rag_working_dir,
        llm_complete=llm_complete,
        embedding_func=embedding_func,
        vision_cascade=vision_cascade,
        web_search=web_search,
        web_search_fallback=web_search_fallback,
        web_extract=web_extract,
        google_search_grounding=google_search_grounding,
        output_dir=output_dir,
        telemetry_jsonl=telemetry_jsonl,
    )


__all__ = ["ResearchConfig", "from_env"]
