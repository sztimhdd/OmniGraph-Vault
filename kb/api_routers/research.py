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
import json
import logging
from typing import Any, AsyncIterator

from fastapi import APIRouter
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
    max_iterations: int = Field(3, ge=1, le=10)


def _format_sse(event_name: str, data: dict[str, Any]) -> str:
    """Serialize one SSE frame: ``event: <name>\\ndata: <json>\\n\\n``.

    JSON encoder must handle ``Path``-typed values that the orchestrator's
    stage_end payloads do not contain today, but the terminal ``done``
    event's ``images_embedded`` field (already coerced to ``str`` inside
    :func:`research_stream_with_result`) does — keep the default encoder.
    """
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _sse_event_stream(query: str, max_iterations: int) -> AsyncIterator[str]:
    """Adapt the orchestrator's event dicts to SSE frames.

    Filters orchestrator events to the 5 named ``stage_end`` events plus the
    terminal ``done`` payload from :func:`research_stream_with_result`. Drops
    pipeline_start, pipeline_end, and stage_start markers (REQ-1.1-B-2 asks
    for 5 stage events + 1 done event, not the raw 12-event stream).

    Errors raised inside the orchestrator propagate as a synthetic
    ``event: error`` SSE frame instead of a 500 — once the response has
    started streaming we can no longer change the HTTP status code.
    """
    cfg = dataclasses.replace(from_env(), max_iter_verifier=max_iterations)
    try:
        async for ev in research_stream_with_result(query, cfg):
            if ev.get("event") == "done":
                yield _format_sse("done", ev["result"])
                continue
            if ev.get("event_type") == "stage_end":
                stage = ev.get("stage")
                if stage in _STAGE_EVENT_NAMES:
                    payload = {k: v for k, v in ev.items() if k != "event_type"}
                    yield _format_sse(stage, payload)
    except Exception as exc:  # noqa: BLE001 — surface on SSE channel, never 500 mid-stream
        logger.exception("research_stream failed: query=%r", query)
        yield _format_sse("error", {"message": str(exc), "type": type(exc).__name__})


@router.post("/research")
async def research_endpoint(body: ResearchRequest) -> StreamingResponse:
    """REQ-1.1-B-1: POST /api/research returns a text/event-stream.

    Streams 5 stage events as the pipeline progresses, then a terminal
    ``done`` event with the full ``ResearchResult`` JSON. On internal
    failure mid-stream a synthetic ``error`` event is emitted (cannot
    change the HTTP status once headers flushed).
    """
    return StreamingResponse(
        _sse_event_stream(body.query, body.max_iterations),
        media_type="text/event-stream",
    )
