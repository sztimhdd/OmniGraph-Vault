"""Integration tests for POST /api/research SSE endpoint (REQ-1.1-B-1 / B-2).

Skill discipline (per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):

    Skill(skill="writing-tests", args="TestClient SSE integration tests. Patch
    research_stream_with_result + from_env on kb.api_routers.research with
    in-process stubs (no network, no LLM, no env). Assert: 200 + text/event-stream,
    5 stage events in fixed order (web_baseline → retriever → reasoner → verifier
    → synthesizer), terminal `done` event with ResearchResult JSON. 422 paths
    cover empty/too-long query and out-of-range max_iterations.")

Behaviors covered (REQ-1.1-B-1 + B-2):
    1. POST /api/research {query} → 200 + Content-Type: text/event-stream
    2. SSE stream emits exactly 5 stage events in pipeline order
    3. Each stage event carries the orchestrator's stage_end payload (status,
       duration, counts) — pipeline_start / stage_start / pipeline_end markers
       are filtered out (REQ asks for 5 stages, not 12 raw events)
    4. Terminal `done` event carries ResearchResult JSON with markdown,
       confidence, sources (list of dicts), images_embedded (list of strs),
       note_lines (list of strs)
    5. Synthesizer stage_end omits `status` (Axis 8 terminal-stage rule) — the
       SSE forwarder MUST NOT inject a synthetic status
    6. POST missing query → 422
    7. POST empty query → 422
    8. POST query > 2000 chars → 422
    9. POST max_iterations < 1 → 422
    10. POST max_iterations > 10 → 422
    11. body.max_iterations is wired through to ResearchConfig.max_iter_verifier
        (assertion via cfg-capturing stub)
    12. Mid-stream orchestrator exception → synthetic `event: error` SSE frame
        (HTTP cannot 500 once headers are flushed)
"""
from __future__ import annotations

import asyncio
import dataclasses
import importlib
import json
from typing import Any, AsyncIterator

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers — SSE frame parsing + fake event generators
# ---------------------------------------------------------------------------

def _parse_sse_frames(body: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse an SSE response body into [(event_name, data_dict), ...].

    Frame format per :func:`kb.api_routers.research._format_sse`:
        ``event: <name>\\ndata: <json>\\n\\n``
    """
    frames: list[tuple[str, dict[str, Any]]] = []
    for raw in body.split("\n\n"):
        if not raw.strip():
            continue
        # Skip SSE comment frames (heartbeats: ": keepalive") — no event:/data:
        # line; real EventSource/SSE clients ignore comment-only frames.
        if all(ln.startswith(":") or not ln.strip() for ln in raw.split("\n")):
            continue
        event_name: str | None = None
        data_json: str | None = None
        for line in raw.split("\n"):
            if line.startswith("event: "):
                event_name = line[len("event: "):].strip()
            elif line.startswith("data: "):
                data_json = line[len("data: "):]
        assert event_name is not None, f"frame missing event line: {raw!r}"
        assert data_json is not None, f"frame missing data line: {raw!r}"
        frames.append((event_name, json.loads(data_json)))
    return frames


def _make_fake_stream(captured: dict[str, Any]) -> Any:
    """Build a fake research_stream_with_result that yields the canonical 12+1
    events and captures the cfg it was called with.

    Mirrors the orchestrator's emit shape exactly (see lib/research/orchestrator.py
    _run_pipeline) so the router's filter logic is exercised against realistic
    input.
    """

    async def _fake_stream(query: str, cfg: Any) -> AsyncIterator[dict]:
        captured["query"] = query
        captured["cfg"] = cfg

        yield {"event_type": "pipeline_start", "stage": "pipeline", "ts": 0.0, "query": query}

        # web_baseline
        yield {"event_type": "stage_start", "stage": "web_baseline", "ts": 0.0}
        yield {
            "event_type": "stage_end",
            "stage": "web_baseline",
            "ts": 0.0,
            "status": "ok",
            "reason": None,
            "duration_s": 0.05,
            "snippet_count": 3,
        }

        # retriever
        yield {"event_type": "stage_start", "stage": "retriever", "ts": 0.0}
        yield {
            "event_type": "stage_end",
            "stage": "retriever",
            "ts": 0.0,
            "status": "ok",
            "reason": None,
            "duration_s": 0.10,
            "chunk_count": 7,
            "image_candidate_count": 2,
        }

        # reasoner
        yield {"event_type": "stage_start", "stage": "reasoner", "ts": 0.0}
        yield {
            "event_type": "stage_end",
            "stage": "reasoner",
            "ts": 0.0,
            "status": "ok",
            "reason": None,
            "duration_s": 0.20,
            "iter_count": 1,
            "image_analyzed_count": 1,
        }

        # verifier
        yield {"event_type": "stage_start", "stage": "verifier", "ts": 0.0}
        yield {
            "event_type": "stage_end",
            "stage": "verifier",
            "ts": 0.0,
            "status": "ok",
            "reason": None,
            "duration_s": 0.15,
            "iter_count": 2,
            "confidence": 0.82,
            "external_citation_count": 1,
        }

        # synthesizer (NO status — Axis 8 terminal-stage rule)
        yield {"event_type": "stage_start", "stage": "synthesizer", "ts": 0.0}
        yield {
            "event_type": "stage_end",
            "stage": "synthesizer",
            "ts": 0.0,
            "duration_s": 0.30,
            "embedded_image_count": 1,
            "note_line_count": 0,
            "confidence": 0.82,
        }

        yield {"event_type": "pipeline_end", "stage": "pipeline", "ts": 0.0, "duration_s": 0.85}

        # Terminal done — JSON-safe ResearchResult (orchestrator already coerced
        # Path → str / Source → dict / etc. via research_stream_with_result).
        yield {
            "event": "done",
            "result": {
                "markdown": "# Stub answer\n\nSee [a](kb://stub/1).",
                "confidence": 0.82,
                "sources": [
                    {
                        "kind": "kg_chunk",
                        "uri": "kb://stub/1",
                        "title": "Stub source",
                        "snippet": "stub snippet",
                    }
                ],
                "images_embedded": ["/static/img/abc1234567/1.jpg"],
                "note_lines": [],
            },
        }

    return _fake_stream


def _fake_from_env() -> Any:
    """Stub from_env() that returns a frozen dataclass with the same name as
    ResearchConfig and a max_iter_verifier slot, without doing any I/O.

    The router uses ``dataclasses.replace(from_env(), max_iter_verifier=...)``,
    so the returned object only needs to be a frozen dataclass with that field.
    Using a local dataclass keeps the test independent of the real ResearchConfig
    constructor's heavy dependencies (VisionCascade, lib.lightrag_embedding, etc.).
    """

    @dataclasses.dataclass(frozen=True)
    class _StubCfg:
        max_iter_verifier: int = 3
        marker: str = "stub-cfg"

    return _StubCfg()


# ---------------------------------------------------------------------------
# Fixture — fresh TestClient with stubbed research backend
# ---------------------------------------------------------------------------


@pytest.fixture
def app_client_and_capture(monkeypatch):
    """Build a TestClient with research_stream_with_result + from_env stubbed.

    Returns (client, captured_dict). The captured dict receives the query +
    cfg the stub stream was called with — tests can introspect to assert the
    body.max_iterations → cfg.max_iter_verifier wiring.
    """
    captured: dict[str, Any] = {}

    # Reload kb.api_routers.research so the freshly-bound module-level imports
    # (research_stream_with_result, from_env) can be monkeypatched cleanly.
    import kb.api_routers.research as research_router_module
    importlib.reload(research_router_module)

    monkeypatch.setattr(
        research_router_module,
        "research_stream_with_result",
        _make_fake_stream(captured),
    )
    monkeypatch.setattr(research_router_module, "from_env", _fake_from_env)

    # Re-load kb.api so the router include reuses the patched module's router.
    # (router object identity is preserved across reload because we patched
    # functions on the same module object, but the include happens at kb.api
    # import time — reload to be safe.)
    import kb.api
    importlib.reload(kb.api)

    return TestClient(kb.api.app), captured


# ---------------------------------------------------------------------------
# Happy path — REQ-1.1-B-1 / B-2
# ---------------------------------------------------------------------------


def test_post_research_returns_event_stream(app_client_and_capture):
    """REQ-1.1-B-1: POST /api/research returns 200 + text/event-stream."""
    client, _ = app_client_and_capture
    resp = client.post("/api/research", json={"query": "What is LightRAG?"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")


def test_sse_emits_five_stage_events_in_order(app_client_and_capture):
    """REQ-1.1-B-2: 5 named stage events in fixed pipeline order."""
    client, _ = app_client_and_capture
    resp = client.post("/api/research", json={"query": "What is LightRAG?"})
    frames = _parse_sse_frames(resp.text)
    stage_frames = [name for name, _ in frames if name != "done"]
    assert stage_frames == [
        "web_baseline",
        "retriever",
        "reasoner",
        "verifier",
        "synthesizer",
    ]


def test_sse_filters_out_non_stage_end_orchestrator_events(app_client_and_capture):
    """pipeline_start / stage_start / pipeline_end markers MUST be dropped.

    Orchestrator yields 12 events; SSE forwards 5 stage_end + 1 done = 6.
    """
    client, _ = app_client_and_capture
    resp = client.post("/api/research", json={"query": "What is LightRAG?"})
    frames = _parse_sse_frames(resp.text)
    assert len(frames) == 6  # 5 stage + 1 done


def test_stage_event_payload_carries_orchestrator_fields(app_client_and_capture):
    """Each stage event surface mirrors the orchestrator's stage_end payload."""
    client, _ = app_client_and_capture
    resp = client.post("/api/research", json={"query": "What is LightRAG?"})
    frames = dict(_parse_sse_frames(resp.text))
    web = frames["web_baseline"]
    assert web["stage"] == "web_baseline"
    assert web["status"] == "ok"
    assert web["snippet_count"] == 3
    # event_type is stripped — the SSE event name already carries that signal
    assert "event_type" not in web

    retr = frames["retriever"]
    assert retr["chunk_count"] == 7
    assert retr["image_candidate_count"] == 2

    verf = frames["verifier"]
    assert verf["confidence"] == pytest.approx(0.82)
    assert verf["external_citation_count"] == 1


def test_synthesizer_event_omits_status(app_client_and_capture):
    """Axis 8 terminal-stage rule: synthesizer stage_end has NO status field.

    The SSE forwarder MUST NOT inject a synthetic status — pass through the
    orchestrator's payload unchanged (minus the event_type key).
    """
    client, _ = app_client_and_capture
    resp = client.post("/api/research", json={"query": "What is LightRAG?"})
    frames = dict(_parse_sse_frames(resp.text))
    syn = frames["synthesizer"]
    assert "status" not in syn
    assert syn["confidence"] == pytest.approx(0.82)
    assert syn["embedded_image_count"] == 1


def test_terminal_done_event_carries_research_result(app_client_and_capture):
    """REQ-1.1-B-2: final ``done`` event holds the ResearchResult JSON."""
    client, _ = app_client_and_capture
    resp = client.post("/api/research", json={"query": "What is LightRAG?"})
    frames = _parse_sse_frames(resp.text)
    last_name, last_data = frames[-1]
    assert last_name == "done"
    assert last_data["markdown"].startswith("# Stub answer")
    assert last_data["confidence"] == pytest.approx(0.82)
    assert last_data["sources"] == [
        {
            "kind": "kg_chunk",
            "uri": "kb://stub/1",
            "title": "Stub source",
            "snippet": "stub snippet",
        }
    ]
    assert last_data["images_embedded"] == ["/static/img/abc1234567/1.jpg"]
    assert last_data["note_lines"] == []


def test_max_iterations_wires_to_max_iter_verifier(app_client_and_capture):
    """body.max_iterations propagates to ResearchConfig.max_iter_verifier."""
    client, captured = app_client_and_capture
    resp = client.post(
        "/api/research", json={"query": "What is LightRAG?", "max_iterations": 7}
    )
    assert resp.status_code == 200
    # Drain the stream so the stub captures the cfg
    _ = resp.text
    assert captured["cfg"].max_iter_verifier == 7


def test_default_max_iterations_is_three(app_client_and_capture):
    """ResearchRequest default for max_iterations matches ResearchConfig."""
    client, captured = app_client_and_capture
    resp = client.post("/api/research", json={"query": "anything"})
    assert resp.status_code == 200
    _ = resp.text
    assert captured["cfg"].max_iter_verifier == 3


# ---------------------------------------------------------------------------
# Validation — 422 paths
# ---------------------------------------------------------------------------


def test_missing_query_returns_422(app_client_and_capture):
    client, _ = app_client_and_capture
    resp = client.post("/api/research", json={})
    assert resp.status_code == 422


def test_empty_query_returns_422(app_client_and_capture):
    client, _ = app_client_and_capture
    resp = client.post("/api/research", json={"query": ""})
    assert resp.status_code == 422


def test_query_over_2000_chars_returns_422(app_client_and_capture):
    client, _ = app_client_and_capture
    resp = client.post("/api/research", json={"query": "x" * 2001})
    assert resp.status_code == 422


def test_max_iterations_below_one_returns_422(app_client_and_capture):
    client, _ = app_client_and_capture
    resp = client.post(
        "/api/research", json={"query": "ok", "max_iterations": 0}
    )
    assert resp.status_code == 422


def test_max_iterations_above_ten_returns_422(app_client_and_capture):
    client, _ = app_client_and_capture
    resp = client.post(
        "/api/research", json={"query": "ok", "max_iterations": 11}
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Failure path — orchestrator raises mid-stream
# ---------------------------------------------------------------------------


def test_orchestrator_exception_emits_synthetic_error_frame(monkeypatch):
    """Once headers are flushed we cannot 500 — surface as `event: error`."""
    import kb.api_routers.research as research_router_module
    importlib.reload(research_router_module)

    async def _failing_stream(query: str, cfg: Any) -> AsyncIterator[dict]:
        yield {
            "event_type": "stage_end",
            "stage": "web_baseline",
            "ts": 0.0,
            "status": "ok",
            "snippet_count": 1,
            "duration_s": 0.01,
            "reason": None,
        }
        raise RuntimeError("retriever exploded")

    monkeypatch.setattr(
        research_router_module, "research_stream_with_result", _failing_stream
    )
    monkeypatch.setattr(research_router_module, "from_env", _fake_from_env)

    import kb.api
    importlib.reload(kb.api)

    client = TestClient(kb.api.app)
    resp = client.post("/api/research", json={"query": "boom"})
    # Headers were flushed before the exception → status remains 200
    assert resp.status_code == 200
    frames = _parse_sse_frames(resp.text)
    names = [n for n, _ in frames]
    assert "web_baseline" in names
    assert "error" in names
    err_frame = next(d for n, d in frames if n == "error")
    assert err_frame["type"] == "RuntimeError"
    assert "retriever exploded" in err_frame["message"]


# ---------------------------------------------------------------------------
# Heartbeat — long inter-stage gap must emit SSE keepalive (arx-2-finish bug:
# Databricks HTTP/2 ingress reset the idle stream mid-verifier; server kept
# running but the browser saw ERR_HTTP2_PROTOCOL_ERROR). Regression guard.
# ---------------------------------------------------------------------------


def test_sse_emits_keepalive_during_slow_stage_gap(monkeypatch):
    """A stage gap longer than _SSE_HEARTBEAT_SEC emits a `: keepalive` comment,
    and all real frames still arrive intact afterward."""
    import kb.api_routers.research as research_router_module
    importlib.reload(research_router_module)
    # Shrink the heartbeat so the test is fast (default 15s).
    monkeypatch.setattr(research_router_module, "_SSE_HEARTBEAT_SEC", 0.05)

    async def _slow_stream(query: str, cfg: Any) -> AsyncIterator[dict]:
        yield {
            "event_type": "stage_end", "stage": "web_baseline", "ts": 0.0,
            "status": "ok", "reason": None, "duration_s": 0.0, "snippet_count": 0,
        }
        # Simulate a long agent-loop with NO frame emitted (> heartbeat interval).
        await asyncio.sleep(0.25)
        yield {
            "event_type": "stage_end", "stage": "retriever", "ts": 0.0,
            "status": "ok", "reason": None, "duration_s": 0.0,
            "chunk_count": 9, "image_candidate_count": 0,
        }
        yield {"event": "done", "result": {
            "markdown": "# ok", "confidence": 0.5, "sources": [],
            "images_embedded": [], "note_lines": [],
        }}

    monkeypatch.setattr(
        research_router_module, "research_stream_with_result", _slow_stream
    )
    monkeypatch.setattr(research_router_module, "from_env", _fake_from_env)

    import kb.api
    importlib.reload(kb.api)
    client = TestClient(kb.api.app)
    resp = client.post("/api/research", json={"query": "slow"})
    assert resp.status_code == 200
    raw = resp.text
    # Keepalive comment present during the slow gap.
    assert ": keepalive" in raw
    # All real frames still arrive intact (heartbeat did not drop/corrupt them).
    names = [n for n, _ in _parse_sse_frames(raw)]
    assert "web_baseline" in names
    assert "retriever" in names
    assert "done" in names
