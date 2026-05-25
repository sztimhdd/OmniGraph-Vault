"""Agentic-RAG-v1 research package.

Importable as `lib.research` (physical) and `omnigraph.research` (declared in
pyproject.toml namespace mapping; resolves after `pip install -e .` lands in
ar-1-03 Task 0).

Public API surface (LIB-01) — 8 names. Per-stage dataclasses
(RetrieverOutput, ReasonerOutput, etc.) are NOT re-exported here; advanced
consumers (HTTP wrapper, CLI --dump-state) import them via
`from lib.research.types import ...`.
"""
from .config import ResearchConfig, from_env  # noqa: F401
from .orchestrator import (  # noqa: F401
    research,
    research_stream,
    research_stream_with_result,
)
from .types import (  # noqa: F401
    ResearchResult,
    ResearchState,
    Source,
)

__all__ = [
    "research",
    "research_stream",
    "research_stream_with_result",
    "ResearchConfig",
    "from_env",
    "ResearchResult",
    "ResearchState",
    "Source",
]
