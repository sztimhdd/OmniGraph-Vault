"""Agentic-RAG-v1 orchestrator (ar-1 skeleton).

Stages are wired by ar-1-02. This file establishes the public async API:

  - async def research(query, config) -> ResearchResult
  - async def research_stream(query, config) -> AsyncIterator[dict]
    (signature only; body raises NotImplementedError("ar-4"))

Pipeline order (Axis 1, strict sequential):
    WebBaseline -> Retriever -> Reasoner -> Verifier -> Synthesizer

`research_stream` exists in ar-1 to lock the streaming-peer API rule today
(Axis 5: every async def research has a streaming peer). The body lands in
ar-4 with telemetry. LIB-08 splits this responsibility: signature here,
body in ar-4.

Pure async entrypoint (Axis 1) — no print, no file I/O, no argv parsing in
this file. Stage modules are imported lazily inside research() so a stage
import-time failure doesn't poison module load.
"""
from __future__ import annotations

import time
from typing import AsyncIterator

from .config import ResearchConfig, from_env
from .types import ResearchResult, ResearchState


async def research(query: str, config: ResearchConfig | None = None) -> ResearchResult:
    """Run the 5-stage research pipeline. Strict sequential order (Axis 1).

    Stages are imported lazily so import-time failures in any stage don't
    poison module load. Each stage is best-effort internally (Axis 3) — the
    orchestrator never sees a raise from a stage. If an unexpected exception
    escapes anyway, let it propagate (it's a real bug, not a stage degradation).
    """
    cfg = config if config is not None else from_env()
    state = ResearchState(query=query, timestamp_start=time.time())

    # Lazy stage imports — preserves clean module load even if a stage has
    # init-time issues, and helps with circular-import resolution.
    from .stages.web_baseline import run as run_web_baseline
    from .stages.retriever import run as run_retriever
    from .stages.reasoner import run as run_reasoner
    from .stages.verifier import run as run_verifier
    from .stages.synthesizer import run as run_synthesizer

    # Strict sequential pipeline (Axis 1).
    state.web_baseline = await run_web_baseline(query, cfg)
    state.retrieved = await run_retriever(query, cfg)
    state.reasoned = await run_reasoner(query, cfg, state.retrieved)
    state.verified = await run_verifier(query, cfg, state.reasoned)
    state.synthesized = await run_synthesizer(query, cfg, state)

    return ResearchResult(
        markdown=state.synthesized.markdown,
        confidence=state.synthesized.confidence,
        sources=state.synthesized.sources,
        images_embedded=state.synthesized.embedded_images,
        state=state,
    )


async def research_stream(
    query: str, config: ResearchConfig | None = None
) -> AsyncIterator[dict]:
    """Streaming peer of research(). Body lands in ar-4 with telemetry.

    Signature exists in ar-1 to lock the API rule (Axis 5: streaming peer).
    """
    raise NotImplementedError("ar-4")
    yield {}  # unreachable; kept so type-checker accepts AsyncIterator return
