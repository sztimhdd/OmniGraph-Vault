"""ar-4 Wave 1 — research_stream() async-iterator behavior tests (LIB-08).

Pins the streaming peer's emission contract:

- pipeline_start is the first event
- exactly 5 (stage_start, stage_end) pairs in pipeline order:
  web_baseline -> retriever -> reasoner -> verifier -> synthesizer
- pipeline_end is the last event, carries duration_s
- sink None -> no file I/O
- sink set -> JSONL on disk matches the events the iterator yields
- research() and research_stream() share the same emission sequence
  (Pattern A: both consume `_run_pipeline`)

Deviation from PLAN: the PLAN referenced a `stub_cfg` fixture in a
non-existent ``tests/unit/research/conftest.py``. We inline
``_make_stub_cfg`` here following the precedent in
``test_orchestrator.py`` (which uses an in-file ``_make_cfg`` helper).
This keeps the test file self-contained and avoids introducing a
package-wide fixture that other tests don't yet use.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from lib.research.orchestrator import research, research_stream
from lib.research.types import ResearchConfig


def _make_stub_cfg(rag_working_dir: Path, telemetry_jsonl: Path | None = None) -> ResearchConfig:
    """Hand-rolled no-LLM, no-network ResearchConfig for stream tests."""

    def _stub_web_search(_q: str) -> list[dict]:
        return []

    def _stub_llm_complete(_prompt: str) -> str:
        return ""

    def _stub_embedding(_texts):
        return []

    return ResearchConfig(
        rag_working_dir=rag_working_dir,
        llm_complete=_stub_llm_complete,
        embedding_func=_stub_embedding,
        vision_cascade=object(),
        web_search=_stub_web_search,
        telemetry_jsonl=telemetry_jsonl,
    )


@pytest.fixture
def stub_kg_search(monkeypatch):
    """Stub `kg_search` so the retriever doesn't try to hit a live KG."""

    async def _empty_search(q, mode="hybrid", **kwargs):  # arx-4: absorb rag= kwarg
        return ""

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _empty_search
    )


# ---------------------------------------------------------------------------
# Iterator order tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_research_stream_yields_pipeline_start_first(
    tmp_path, stub_kg_search
) -> None:
    cfg = _make_stub_cfg(tmp_path / "lightrag_storage")
    events: list[dict] = []
    async for ev in research_stream("test query", cfg):
        events.append(ev)
    assert events, "expected at least one event"
    assert events[0]["event_type"] == "pipeline_start"
    assert events[0]["stage"] == "pipeline"
    assert events[0]["query"] == "test query"


@pytest.mark.unit
async def test_research_stream_yields_5_stage_pairs_in_order(
    tmp_path, stub_kg_search
) -> None:
    cfg = _make_stub_cfg(tmp_path / "lightrag_storage")
    events: list[dict] = []
    async for ev in research_stream("q", cfg):
        events.append(ev)
    expected = ["web_baseline", "retriever", "reasoner", "verifier", "synthesizer"]
    pairs = [
        (e["event_type"], e["stage"])
        for e in events
        if e["event_type"] in ("stage_start", "stage_end")
    ]
    assert len(pairs) == 10, f"expected 10 stage events (5 pairs), got {len(pairs)}"
    for i, name in enumerate(expected):
        assert pairs[2 * i] == ("stage_start", name)
        assert pairs[2 * i + 1] == ("stage_end", name)


@pytest.mark.unit
async def test_research_stream_yields_pipeline_end_last(
    tmp_path, stub_kg_search
) -> None:
    cfg = _make_stub_cfg(tmp_path / "lightrag_storage")
    events: list[dict] = []
    async for ev in research_stream("q", cfg):
        events.append(ev)
    assert events[-1]["event_type"] == "pipeline_end"
    assert events[-1]["stage"] == "pipeline"
    assert "duration_s" in events[-1]
    assert isinstance(events[-1]["duration_s"], float)
    assert events[-1]["duration_s"] >= 0.0


@pytest.mark.unit
async def test_research_stream_synthesizer_stage_end_omits_status(
    tmp_path, stub_kg_search
) -> None:
    """Axis 8 — synthesizer is terminal; its stage_end carries no status."""
    cfg = _make_stub_cfg(tmp_path / "lightrag_storage")
    events: list[dict] = []
    async for ev in research_stream("q", cfg):
        events.append(ev)
    syn_end = next(
        e
        for e in events
        if e["event_type"] == "stage_end" and e["stage"] == "synthesizer"
    )
    assert "status" not in syn_end
    # And it carries the synth-specific payload keys
    assert "embedded_image_count" in syn_end
    assert "note_line_count" in syn_end
    assert "confidence" in syn_end


# ---------------------------------------------------------------------------
# Sink-side tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_research_stream_sink_none_no_file_io(
    tmp_path, stub_kg_search
) -> None:
    """Sink None -> no JSONL on disk anywhere."""
    cfg = _make_stub_cfg(tmp_path / "lightrag_storage", telemetry_jsonl=None)
    async for _ev in research_stream("q", cfg):
        pass
    # tmp_path may contain `lightrag_storage` if the retriever stage created
    # it; we only assert that no .jsonl file was written.
    jsonl_files = list(tmp_path.rglob("*.jsonl"))
    assert jsonl_files == []


@pytest.mark.unit
async def test_research_stream_sink_set_writes_valid_jsonl_matching_iterator(
    tmp_path, stub_kg_search
) -> None:
    p = tmp_path / "tel.jsonl"
    cfg = _make_stub_cfg(tmp_path / "lightrag_storage", telemetry_jsonl=p)
    iter_events: list[dict] = []
    async for ev in research_stream("q", cfg):
        iter_events.append(ev)
    assert p.exists(), "sink path should exist after iteration"
    file_lines = p.read_text(encoding="utf-8").strip().splitlines()
    file_events = [json.loads(line) for line in file_lines]
    assert len(iter_events) == len(file_events)
    for ie, fe in zip(iter_events, file_events):
        assert ie["event_type"] == fe["event_type"]
        assert ie["stage"] == fe["stage"]


@pytest.mark.unit
async def test_research_consumes_same_pipeline_as_stream(
    tmp_path, stub_kg_search
) -> None:
    """Pattern A invariant — research() and research_stream() share emission.

    Both surfaces route through `_run_pipeline`, so the JSONL produced by a
    blocking `research()` must contain the same event_type+stage sequence
    as the JSONL produced by walking `research_stream()` to completion.
    """
    p_blocking = tmp_path / "blocking.jsonl"
    p_streaming = tmp_path / "streaming.jsonl"
    cfg_b = _make_stub_cfg(tmp_path / "lightrag_storage", telemetry_jsonl=p_blocking)
    cfg_s = _make_stub_cfg(tmp_path / "lightrag_storage", telemetry_jsonl=p_streaming)

    await research("q", cfg_b)
    async for _ev in research_stream("q", cfg_s):
        pass

    def _seq(p: Path) -> list[str]:
        return [
            json.loads(line)["event_type"] + ":" + json.loads(line)["stage"]
            for line in p.read_text(encoding="utf-8").strip().splitlines()
        ]

    blocking = _seq(p_blocking)
    streaming = _seq(p_streaming)
    assert blocking == streaming
    # Sanity: 1 (start) + 5*2 (stage pairs) + 1 (end) = 12 events
    assert len(blocking) == 12
