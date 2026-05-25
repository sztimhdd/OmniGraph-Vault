"""Agentic-RAG-v1 orchestrator (ar-4 telemetry-wired).

Single source of stage-emit ordering: the private async generator
``_run_pipeline`` runs all 5 stages and yields one event per boundary
(pipeline_start, 5x stage_start/stage_end pairs, pipeline_end).

- ``research_stream()`` returns directly from ``_run_pipeline`` — its
  consumers see every event the pipeline emits in real time.
- ``research()`` consumes ``_run_pipeline`` and builds ``ResearchResult``
  from the closure-captured ``ResearchState`` instance.

Both surfaces honour ``cfg.telemetry_jsonl`` identically: when set, every
event is also appended via :func:`write_event`. Sink-disabled (None) does
no file I/O (Axis 4 opt-in side effect).

Pure async entrypoint (Axis 1) — no print, no argv parsing in this file.
Stage modules are imported lazily inside ``_run_pipeline`` so a stage
import-time failure doesn't poison module load.
"""
from __future__ import annotations

import time
from typing import AsyncIterator

from .config import ResearchConfig, from_env
from .telemetry import (
    EVENT_PIPELINE_END,
    EVENT_PIPELINE_START,
    EVENT_STAGE_END,
    EVENT_STAGE_START,
    make_event,
    write_event,
)
from .types import ResearchResult, ResearchState


async def _run_pipeline(
    query: str, cfg: ResearchConfig, state: ResearchState
) -> AsyncIterator[dict]:
    """Master pipeline emission generator (Pattern A).

    Yields events only; populates ``state`` in-place as a side effect.
    ``state`` is intentionally mutable — both ``research()`` and
    ``research_stream()`` capture it via closure to expose the final
    ``ResearchState`` after the generator completes.

    Order: pipeline_start, then for each of (web_baseline, retriever,
    reasoner, verifier, synthesizer) a (stage_start, stage_end) pair,
    then pipeline_end. Synthesizer's stage_end omits ``status`` per
    Axis 8 (terminal-stage rule).
    """
    sink = cfg.telemetry_jsonl

    # Lazy stage imports — preserves clean module load even if a stage
    # has init-time issues, and helps with circular-import resolution.
    from .stages.web_baseline import run as run_web_baseline
    from .stages.retriever import run as run_retriever
    from .stages.reasoner import run as run_reasoner
    from .stages.verifier import run as run_verifier
    from .stages.synthesizer import run as run_synthesizer

    ev = make_event(EVENT_PIPELINE_START, "pipeline", query=query)
    write_event(sink, ev)
    yield ev

    # WebBaseline ----------------------------------------------------------
    t0 = time.time()
    ev = make_event(EVENT_STAGE_START, "web_baseline")
    write_event(sink, ev)
    yield ev
    state.web_baseline = await run_web_baseline(query, cfg)
    ev = make_event(
        EVENT_STAGE_END,
        "web_baseline",
        status=state.web_baseline.status,
        reason=state.web_baseline.reason,
        duration_s=time.time() - t0,
        snippet_count=len(state.web_baseline.snippets),
    )
    write_event(sink, ev)
    yield ev

    # Retriever ------------------------------------------------------------
    t0 = time.time()
    ev = make_event(EVENT_STAGE_START, "retriever")
    write_event(sink, ev)
    yield ev
    state.retrieved = await run_retriever(query, cfg)
    ev = make_event(
        EVENT_STAGE_END,
        "retriever",
        status=state.retrieved.status,
        reason=state.retrieved.reason,
        duration_s=time.time() - t0,
        chunk_count=len(state.retrieved.chunks),
        image_candidate_count=len(state.retrieved.image_candidates),
    )
    write_event(sink, ev)
    yield ev

    # Reasoner -------------------------------------------------------------
    t0 = time.time()
    ev = make_event(EVENT_STAGE_START, "reasoner")
    write_event(sink, ev)
    yield ev
    state.reasoned = await run_reasoner(query, cfg, state.retrieved)
    ev = make_event(
        EVENT_STAGE_END,
        "reasoner",
        status=state.reasoned.status,
        reason=state.reasoned.reason,
        duration_s=time.time() - t0,
        iter_count=state.reasoned.iter_count,
        image_analyzed_count=len(state.reasoned.analyzed_images),
    )
    write_event(sink, ev)
    yield ev

    # Verifier -------------------------------------------------------------
    t0 = time.time()
    ev = make_event(EVENT_STAGE_START, "verifier")
    write_event(sink, ev)
    yield ev
    state.verified = await run_verifier(query, cfg, state.reasoned)
    ev = make_event(
        EVENT_STAGE_END,
        "verifier",
        status=state.verified.status,
        reason=state.verified.reason,
        duration_s=time.time() - t0,
        iter_count=state.verified.iter_count,
        confidence=state.verified.confidence,
        external_citation_count=len(state.verified.external_citations),
    )
    write_event(sink, ev)
    yield ev

    # Synthesizer (NO status — terminal stage, Axis 8) ---------------------
    t0 = time.time()
    ev = make_event(EVENT_STAGE_START, "synthesizer")
    write_event(sink, ev)
    yield ev
    state.synthesized = await run_synthesizer(query, cfg, state)
    ev = make_event(
        EVENT_STAGE_END,
        "synthesizer",
        duration_s=time.time() - t0,
        embedded_image_count=len(state.synthesized.embedded_images),
        note_line_count=len(state.synthesized.note_lines),
        confidence=state.synthesized.confidence,
    )
    write_event(sink, ev)
    yield ev

    ev = make_event(
        EVENT_PIPELINE_END,
        "pipeline",
        duration_s=time.time() - state.timestamp_start,
    )
    write_event(sink, ev)
    yield ev


async def research(query: str, config: ResearchConfig | None = None) -> ResearchResult:
    """Run the 5-stage research pipeline. Strict sequential order (Axis 1).

    Consumes ``_run_pipeline`` and builds ``ResearchResult`` from the
    closure-captured final state. Both this surface and ``research_stream``
    share one emission generator — no skew, no duplicated stage logic.
    """
    cfg = config if config is not None else from_env()
    state = ResearchState(query=query, timestamp_start=time.time())
    async for _ev in _run_pipeline(query, cfg, state):
        # Events flow through the sink writer inside _run_pipeline; we
        # discard them here. The closure-captured `state` carries the
        # final dataclass we return.
        pass
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
    """Streaming peer of :func:`research` — yields per-stage events (LIB-08).

    Pipeline order: WebBaseline -> Retriever -> Reasoner -> Verifier ->
    Synthesizer. Each event also flows through ``cfg.telemetry_jsonl``
    when set (Axis 4 opt-in side effect). Sink-disabled iteration does
    no file I/O.
    """
    cfg = config if config is not None else from_env()
    state = ResearchState(query=query, timestamp_start=time.time())
    async for ev in _run_pipeline(query, cfg, state):
        yield ev


async def research_stream_with_result(
    query: str, config: ResearchConfig | None = None
) -> AsyncIterator[dict]:
    """Streaming peer of :func:`research_stream` that also emits a terminal
    ``done`` event carrying the final ``ResearchResult`` payload.

    Yields the same 12 pipeline events as :func:`research_stream`, then a
    final dict ``{"event": "done", "result": {...}}`` whose ``result``
    mirrors :class:`ResearchResult` fields, with ``Path`` objects coerced
    to strings and ``Source`` dataclasses to plain dicts so the payload is
    JSON-serializable for HTTP/SSE consumers.

    Same closure-capture state pattern as :func:`research` — does not
    mutate the :func:`research_stream` contract (test_research_stream.py
    assertions stay green).
    """
    cfg = config if config is not None else from_env()
    state = ResearchState(query=query, timestamp_start=time.time())
    async for ev in _run_pipeline(query, cfg, state):
        yield ev
    syn = state.synthesized
    yield {
        "event": "done",
        "result": {
            "markdown": syn.markdown,
            "confidence": syn.confidence,
            "sources": [
                {"kind": s.kind, "uri": s.uri, "title": s.title, "snippet": s.snippet}
                for s in syn.sources
            ],
            "images_embedded": [str(p) for p in syn.embedded_images],
            "note_lines": list(syn.note_lines),
        },
    }
