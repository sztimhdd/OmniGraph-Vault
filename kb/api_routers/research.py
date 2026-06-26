"""API: POST /api/research — SSE stream wrapping the 5-stage Agentic-RAG pipeline.

Per REQ-1.1-B-1 / B-2 (Agentic-RAG-v1.1 milestone arx-2-http):
    POST /api/research {query, max_iterations} -> 200 + text/event-stream

The stream emits five named stage events (web_baseline, retriever, reasoner,
verifier, synthesizer) followed by a terminal ``done`` event carrying the
``ResearchResult`` JSON payload. Each stage event is built from the
orchestrator's ``stage_end`` event (the matching ``stage_start`` markers and
the surrounding ``pipeline_start`` / ``pipeline_end`` envelope events are
filtered out — REQ asks for 5 stages, not 12 raw orchestrator events).

Wraps :func:`lib.research.orchestrator.research_stream_with_result` — does
NOT mutate the public ``research_stream()`` contract (test_research_stream.py
8 contract-pinning assertions stay green).

QA-03: single-uvicorn-worker (`--workers 1`) — the per-request async
generator owns its own ``ResearchState`` instance via the orchestrator's
closure-capture pattern, no shared mutable state across concurrent requests.
"""
from __future__ import annotations

import dataclasses
import asyncio
import json
import logging
from typing import Any, AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from lib.research import from_env, research_stream_with_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["research"])

# Stage events the SSE stream surfaces (REQ-1.1-B-2). The orchestrator emits
# stage_start + stage_end for each plus pipeline_start / pipeline_end; we
# forward only the stage_end events because they carry the per-stage result
# payload (status, duration, counts). Order is fixed by the pipeline itself
# (Axis 1 strict sequential).
_STAGE_EVENT_NAMES = frozenset(
    {"web_baseline", "retriever", "reasoner", "verifier", "synthesizer"}
)


class ResearchRequest(BaseModel):
    """POST /api/research body — REQ-1.1-B-1.

    `query`: 1..2000 chars (defensive bound matching synthesize endpoint).
    `max_iterations`: 1..10. Maps to ``ResearchConfig.max_iter_verifier``
        (the Verifier's agentic re-query loop cap). Default 3 matches the
        :class:`ResearchConfig` field default.
    """

    query: str = Field(..., min_length=1, max_length=2000)
    # Default 1 (was 3): Databricks Apps enforces a HARD ~300s HTTP connection
    # cap. Each reasoner/verifier agent-loop iteration is a cross-border LLM call
    # (~30-60s) plus kg_search; a 393s run was observed timing out mid-reasoner
    # (ERR_HTTP2_PROTOCOL_ERROR). max_iterations now caps BOTH loops (see
    # research_endpoint), so default 1 keeps a full run (~web+retr+reason1+verif1
    # +synth) comfortably under 300s. Users may raise it, accepting timeout risk.
    max_iterations: int = Field(1, ge=1, le=10)


def _format_sse(event_name: str, data: dict[str, Any]) -> str:
    """Serialize one SSE frame: ``event: <name>\\ndata: <json>\\n\\n``.

    JSON encoder must handle ``Path``-typed values that the orchestrator's
    stage_end payloads do not contain today, but the terminal ``done``
    event's ``images_embedded`` field (already coerced to ``str`` inside
    :func:`research_stream_with_result`) does — keep the default encoder.
    """
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# SSE heartbeat interval (seconds). The reasoner/verifier agent-loops run for
# 60-180s+ with NO stage_end frame in between; Databricks Apps HTTP/2 ingress
# resets a stream that emits zero bytes for too long (observed 2026-06-23:
# ERR_HTTP2_PROTOCOL_ERROR mid-verifier while the server pipeline kept running).
# We emit an SSE comment line (`: keepalive\n\n`) every _SSE_HEARTBEAT_SEC of
# producer silence to keep the stream warm. Comment frames carry no event:/data:
# line, so research.js parseFrame ignores them (dataLines empty -> early return).
_SSE_HEARTBEAT_SEC = 15.0
_QUEUE_SENTINEL = object()  # producer-done marker on the queue


async def _sse_event_stream(
    query: str, max_iterations: int, rag: object | None = None
) -> AsyncIterator[str]:
    """Adapt the orchestrator's event dicts to SSE frames, with heartbeats.

    Filters orchestrator events to the 5 named ``stage_end`` events plus the
    terminal ``done`` payload from :func:`research_stream_with_result`. Drops
    pipeline_start, pipeline_end, and stage_start markers (REQ-1.1-B-2 asks
    for 5 stage events + 1 done event, not the raw 12-event stream).

    A background producer task drains the orchestrator into a queue; the
    consumer races each queue-get against ``_SSE_HEARTBEAT_SEC`` and emits a
    ``: keepalive`` comment on timeout so the HTTP/2 stream never goes idle
    long enough for the Databricks ingress to reset it (the agent-loops between
    stage frames can run minutes). The heartbeat timeout NEVER cancels the
    producer — it only injects a comment and loops back to wait again.

    Errors raised inside the orchestrator propagate as a synthetic
    ``event: error`` SSE frame instead of a 500 — once the response has
    started streaming we can no longer change the HTTP status code.
    """
    # Cap BOTH agent-loops with the UI value. Previously only max_iter_verifier
    # was wired, so the reasoner ALWAYS ran its default 5 iterations (each a
    # cross-border LLM call) — the dominant cost that pushed runs past the
    # Databricks ~300s HTTP cap. Capping reasoner too is the load-bearing fix.
    # arx-4 #64/#65: thread the lifespan LightRAG (with rerank_model_func) into
    # cfg so the retriever/reasoner reuse it (mix-mode vector chunks + rerank)
    # instead of building a fresh reranker-less instance. rag=None (CLI) keeps
    # the from_env default and the omnigraph_search fresh-rag fallback.
    cfg = dataclasses.replace(
        from_env(),
        max_iter_reasoner=max_iterations,
        max_iter_verifier=max_iterations,
        rag=rag,
    )
    queue: asyncio.Queue[Any] = asyncio.Queue()

    async def _producer() -> None:
        try:
            async for ev in research_stream_with_result(query, cfg):
                if ev.get("event") == "done":
                    await queue.put(_format_sse("done", ev["result"]))
                elif ev.get("event_type") == "stage_end":
                    stage = ev.get("stage")
                    if stage in _STAGE_EVENT_NAMES:
                        payload = {k: v for k, v in ev.items() if k != "event_type"}
                        await queue.put(_format_sse(stage, payload))
        except Exception as exc:  # noqa: BLE001 — surface on SSE channel, never 500 mid-stream
            logger.exception("research_stream failed: query=%r", query)
            await queue.put(
                _format_sse("error", {"message": str(exc), "type": type(exc).__name__})
            )
        finally:
            await queue.put(_QUEUE_SENTINEL)

    producer = asyncio.create_task(_producer())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=_SSE_HEARTBEAT_SEC)
            except asyncio.TimeoutError:
                # Producer still working (slow agent-loop) — keep stream warm.
                yield ": keepalive\n\n"
                continue
            if item is _QUEUE_SENTINEL:
                break
            yield item
    finally:
        if not producer.done():
            producer.cancel()
            try:
                await producer
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass


@router.post("/research")
async def research_endpoint(body: ResearchRequest, request: Request) -> StreamingResponse:
    """REQ-1.1-B-1: POST /api/research returns a text/event-stream.

    Streams 5 stage events as the pipeline progresses, then a terminal
    ``done`` event with the full ``ResearchResult`` JSON. On internal
    failure mid-stream a synthetic ``error`` event is emitted (cannot
    change the HTTP status once headers flushed).
    """
    return StreamingResponse(
        # arx-4 #64/#65: pass the lifespan LightRAG (with reranker) so the
        # retriever uses mix-mode vector chunks + rerank instead of a fresh
        # reranker-less hybrid instance. getattr guards CLI/test where state unset.
        _sse_event_stream(
            body.query,
            body.max_iterations,
            rag=getattr(request.app.state, "lightrag", None),
        ),
        media_type="text/event-stream",
        headers={
            # Defeat proxy/ingress response buffering so stage frames + the
            # `: keepalive` heartbeat reach the browser immediately (without
            # these, an HTTP/2 ingress may buffer the whole stream and the
            # client sees nothing until it resets). Standard SSE hardening.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
