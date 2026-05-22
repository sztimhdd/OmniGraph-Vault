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
    poison module load. Each stage is wrapped best-effort in ar-1-02 (Axis 3).
    """
    cfg = config if config is not None else from_env()
    state = ResearchState(query=query, timestamp_start=time.time())

    # Stages wired in ar-1-02:
    # from .stages.web_baseline import run as run_web_baseline
    # state.web_baseline = await run_web_baseline(query, cfg)
    # from .stages.retriever import run as run_retriever
    # state.retrieved = await run_retriever(query, cfg)
    # ... (Reasoner, Verifier, Synthesizer)
    _ = (cfg, state)  # silence unused warnings until ar-1-02 wires the stages

    raise NotImplementedError("Stage wiring lands in ar-1-02")


async def research_stream(
    query: str, config: ResearchConfig | None = None
) -> AsyncIterator[dict]:
    """Streaming peer of research(). Body lands in ar-4 with telemetry.

    Signature exists in ar-1 to lock the API rule (Axis 5: streaming peer).
    """
    raise NotImplementedError("ar-4")
    yield {}  # unreachable; kept so type-checker accepts AsyncIterator return
