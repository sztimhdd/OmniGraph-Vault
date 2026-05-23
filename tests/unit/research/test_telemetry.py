"""ar-4 Wave 1 — tests for the telemetry event builder + sink writer (LIB-08).

Mock-based unit tests; no live network, no LLM, no orchestrator coupling.
Covers:
    - make_event carries event_type / stage / ts / merged payload
    - write_event(None, ...) is a no-op (no exception, no file)
    - write_event writes valid JSONL on disk
    - write_event swallows OSError (Axis 3 best-effort)
    - _json_default handles Path and dataclass instances
"""
from __future__ import annotations

import json

import pytest

from lib.research.telemetry import (
    EVENT_PIPELINE_END,
    EVENT_PIPELINE_START,
    EVENT_STAGE_END,
    EVENT_STAGE_START,
    make_event,
    write_event,
)


@pytest.mark.unit
def test_make_event_carries_event_type_stage_ts() -> None:
    ev = make_event(EVENT_PIPELINE_START, "pipeline")
    assert ev["event_type"] == "pipeline_start"
    assert ev["stage"] == "pipeline"
    assert isinstance(ev["ts"], float)
    assert ev["ts"] > 0


@pytest.mark.unit
def test_make_event_event_type_constants_match_string_values() -> None:
    assert EVENT_PIPELINE_START == "pipeline_start"
    assert EVENT_STAGE_START == "stage_start"
    assert EVENT_STAGE_END == "stage_end"
    assert EVENT_PIPELINE_END == "pipeline_end"


@pytest.mark.unit
def test_make_event_merges_payload() -> None:
    ev = make_event(EVENT_STAGE_END, "verifier", iter_count=2, confidence=75.0)
    assert ev["event_type"] == "stage_end"
    assert ev["stage"] == "verifier"
    assert ev["iter_count"] == 2
    assert ev["confidence"] == 75.0


@pytest.mark.unit
def test_write_event_none_sink_is_noop(tmp_path) -> None:
    # Sink None must not raise and must not create any files.
    write_event(None, {"event_type": "x", "stage": "y", "ts": 0.0})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.unit
def test_write_event_writes_valid_jsonl(tmp_path) -> None:
    p = tmp_path / "tel.jsonl"
    write_event(
        p,
        {"event_type": "stage_end", "stage": "reasoner", "ts": 1.5, "iter_count": 3},
    )
    line = p.read_text(encoding="utf-8").strip()
    assert json.loads(line) == {
        "event_type": "stage_end",
        "stage": "reasoner",
        "ts": 1.5,
        "iter_count": 3,
    }


@pytest.mark.unit
def test_write_event_appends_multiple_lines(tmp_path) -> None:
    p = tmp_path / "tel.jsonl"
    write_event(p, {"event_type": "pipeline_start", "stage": "pipeline", "ts": 1.0})
    write_event(p, {"event_type": "pipeline_end", "stage": "pipeline", "ts": 2.0})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event_type"] == "pipeline_start"
    assert json.loads(lines[1])["event_type"] == "pipeline_end"


@pytest.mark.unit
def test_write_event_swallows_oserror(tmp_path) -> None:
    """Path-is-a-directory triggers OSError on open(append) — must be swallowed."""
    bad = tmp_path  # a directory, not a file
    # If this raises, the test fails.
    write_event(bad, {"event_type": "x", "stage": "y", "ts": 0.0})


@pytest.mark.unit
def test_json_default_handles_path_and_dataclass(tmp_path) -> None:
    from lib.research.types import Source

    src = Source(kind="kg_chunk", uri="file://x", title="t", snippet="s")
    p = tmp_path / "tel.jsonl"
    write_event(
        p,
        {
            "event_type": "stage_end",
            "stage": "retriever",
            "ts": 1.0,
            "source": src,
            "path": tmp_path,
        },
    )
    parsed = json.loads(p.read_text(encoding="utf-8").strip())
    # Source dataclass -> asdict -> dict with same fields
    assert isinstance(parsed["source"], dict)
    assert parsed["source"]["kind"] == "kg_chunk"
    assert parsed["source"]["uri"] == "file://x"
    # Path -> str
    assert isinstance(parsed["path"], str)
    assert parsed["path"] == str(tmp_path)
