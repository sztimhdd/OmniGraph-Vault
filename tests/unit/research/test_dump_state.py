"""ar-4 Wave 1 — tests for the --dump-state JSONL serializer (CLI-02).

Covers:
    - _write_dump_state writes 1 header line + ≤ 5 stage lines
    - header carries schema_version='ar-4'
    - Path values inside stage objects serialize as strings (via _default)
    - Missing (None) stages are skipped silently
    - Subprocess CLI smoke (cap=0 LLM-free) — exit 0 + valid JSONL on disk
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from lib.research.__main__ import _write_dump_state
from lib.research.types import (
    ReasonerOutput,
    ResearchState,
    RetrieverOutput,
    SynthesizerOutput,
    VerifierOutput,
    WebBaseline,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def _full_state(query: str = "q") -> ResearchState:
    return ResearchState(
        query=query,
        timestamp_start=1.0,
        web_baseline=WebBaseline(queries_used=[query], snippets=[]),
        retrieved=RetrieverOutput(chunks=[], image_candidates=[]),
        reasoned=ReasonerOutput(
            inferences_md="m",
            additional_chunks=[],
            analyzed_images=[],
            iter_count=1,
        ),
        verified=VerifierOutput(
            fact_check_summary_md="s",
            confidence=80.0,
            external_citations=[],
            discrepancies=[],
            iter_count=2,
        ),
        synthesized=SynthesizerOutput(
            markdown="md",
            confidence=80.0,
            sources=[],
            embedded_images=[],
            note_lines=[],
        ),
    )


# ---------------------------------------------------------------------------
# Helper-level tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_write_dump_state_writes_header_plus_5_stages(tmp_path) -> None:
    p = tmp_path / "ds.jsonl"
    _write_dump_state(_full_state(), p)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 6  # 1 header + 5 stages


@pytest.mark.unit
def test_write_dump_state_header_has_schema_version_ar4(tmp_path) -> None:
    p = tmp_path / "ds.jsonl"
    _write_dump_state(_full_state("hello"), p)
    header = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert header["kind"] == "header"
    assert header["schema_version"] == "ar-4"
    assert header["query"] == "hello"
    assert header["timestamp_start"] == 1.0


@pytest.mark.unit
def test_write_dump_state_stage_lines_have_kind_and_stage(tmp_path) -> None:
    p = tmp_path / "ds.jsonl"
    _write_dump_state(_full_state(), p)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    stages_seen = []
    for line in lines[1:]:
        ev = json.loads(line)
        assert ev["kind"] == "stage"
        stages_seen.append(ev["stage"])
    assert stages_seen == [
        "web_baseline",
        "retrieved",
        "reasoned",
        "verified",
        "synthesized",
    ]


@pytest.mark.unit
def test_write_dump_state_serializes_path_as_str(tmp_path) -> None:
    state = _full_state()
    state.synthesized = SynthesizerOutput(
        markdown="md",
        confidence=80.0,
        sources=[],
        embedded_images=[Path("/tmp/img1.jpg"), Path("/tmp/img2.png")],
        note_lines=[],
    )
    p = tmp_path / "ds.jsonl"
    _write_dump_state(state, p)
    syn_line = json.loads(p.read_text(encoding="utf-8").splitlines()[-1])
    assert syn_line["stage"] == "synthesized"
    # Each Path inside embedded_images should round-trip as a str
    assert all(isinstance(x, str) for x in syn_line["embedded_images"])


@pytest.mark.unit
def test_write_dump_state_skips_missing_stages(tmp_path) -> None:
    """All stages None -> only the header line is written."""
    state = ResearchState(query="q", timestamp_start=1.0)
    p = tmp_path / "ds.jsonl"
    _write_dump_state(state, p)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["kind"] == "header"


@pytest.mark.unit
def test_write_dump_state_skips_some_missing_stages(tmp_path) -> None:
    """Partial state: header + 2 stage lines (others None silently skipped)."""
    state = ResearchState(
        query="q",
        timestamp_start=1.0,
        web_baseline=WebBaseline(queries_used=["q"], snippets=[]),
        retrieved=RetrieverOutput(chunks=[], image_candidates=[]),
    )
    p = tmp_path / "ds.jsonl"
    _write_dump_state(state, p)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3  # header + 2
    assert json.loads(lines[1])["stage"] == "web_baseline"
    assert json.loads(lines[2])["stage"] == "retrieved"


# ---------------------------------------------------------------------------
# Slow integration test: subprocess CLI smoke with --dump-state (cap=0 LLM-free)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_subprocess_cli_smoke_with_dump_state(tmp_path: Path) -> None:
    """Cap=0 CLI with --dump-state: exit 0 + dump-state file is valid JSONL."""
    (tmp_path / "lightrag_storage").mkdir()
    (tmp_path / "images").mkdir()
    dump_path = tmp_path / "subprocess-dumpstate.jsonl"
    env = os.environ.copy()
    env["OMNIGRAPH_BASE_DIR"] = str(tmp_path)
    env.setdefault("DEEPSEEK_API_KEY", "dummy")
    env.setdefault("GEMINI_API_KEY", "dummy")
    env["PYTHONIOENCODING"] = "utf-8"

    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "omnigraph.research",
            "--max-iter-reasoner",
            "0",
            "--max-iter-verifier",
            "0",
            "--no-grounding",
            "--dump-state",
            str(dump_path),
            "test query",
        ],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert res.returncode == 0, (
        f"CLI exited {res.returncode}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    )
    assert dump_path.exists(), "dump-state path should exist after CLI exit"
    lines = dump_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2, f"expected ≥ 2 lines (header + ≥1 stage); got {len(lines)}"
    header = json.loads(lines[0])
    assert header["kind"] == "header"
    assert header["schema_version"] == "ar-4"
    valid_stage_names = {
        "web_baseline",
        "retrieved",
        "reasoned",
        "verified",
        "synthesized",
    }
    for line in lines[1:]:
        ev = json.loads(line)
        assert ev["kind"] == "stage"
        assert ev["stage"] in valid_stage_names
