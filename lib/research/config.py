"""Env-driven ResearchConfig factory — single source of env reads (Axis 3).

All env vars are read here once at construction time. The hot path (orchestrator
+ stages) uses ResearchConfig fields only. Re-exports ResearchConfig from
.types so callers can do `from lib.research.config import ResearchConfig`.

Path defaults preserve the canonical `omonigraph` typo per CLAUDE.md — do NOT
"fix" it without a coordinated migration.
"""
from __future__ import annotations

import os
from pathlib import Path

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

    # Web search — ar-1 stub (Tavily lands in ar-3). Note: even with the env
    # var set we use the stub here; the real Tavily callable is wired in ar-3.
    if os.environ.get("TAVILY_API_KEY"):
        web_search = _skipped_web_search
    else:
        web_search = _skipped_web_search

    web_search_fallback = None  # ar-3 wires Brave when BRAVE_SEARCH_API_KEY set
    web_extract = None
    google_search_grounding = None  # ar-3 wires Vertex Grounding when llm_complete is Vertex

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
