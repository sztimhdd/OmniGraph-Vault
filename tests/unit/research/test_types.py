"""Unit tests for lib.research.types — verbatim dataclass shapes from CONTEXT.md."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import get_args

import pytest

from lib.research.types import (
    ReasonerOutput,
    ResearchConfig,
    ResearchResult,
    ResearchState,
    RetrievedImage,
    RetrieverOutput,
    Source,
    Status,
    SynthesizerOutput,
    VerifierOutput,
    WebBaseline,
)


@pytest.mark.unit
def test_source_constructs_and_is_frozen():
    s = Source(kind="web", uri="http://x")
    assert s.uri == "http://x"
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.uri = "y"  # type: ignore[misc]


@pytest.mark.unit
def test_source_kind_literal_alphabet():
    # Under `from __future__ import annotations`, all annotations are strings
    # at runtime; resolve them with typing.get_type_hints to get the real
    # Literal back for get_args().
    from typing import get_type_hints

    hints = get_type_hints(Source)
    kind_anno = hints["kind"]
    args = get_args(kind_anno)
    assert set(args) == {"kg_chunk", "kg_image", "web", "grounding"}


@pytest.mark.unit
def test_status_literal_alphabet():
    args = get_args(Status)
    assert args == ("ok", "skipped", "failed")


@pytest.mark.unit
def test_web_baseline_defaults():
    wb = WebBaseline(queries_used=[], snippets=[])
    assert wb.status == "ok"
    assert wb.reason is None


@pytest.mark.unit
def test_synthesizer_output_has_no_status_field():
    field_names = {f.name for f in dataclasses.fields(SynthesizerOutput)}
    assert "status" not in field_names
    # Sanity check: required fields are present
    assert {"markdown", "confidence", "sources", "embedded_images", "note_lines"} <= field_names


@pytest.mark.unit
def test_research_state_is_mutable():
    state = ResearchState(query="x", timestamp_start=0.0)
    wb = WebBaseline(queries_used=["q"], snippets=[])
    state.web_baseline = wb  # must not raise
    assert state.web_baseline is wb


@pytest.mark.unit
def test_research_config_is_frozen():
    cfg = ResearchConfig(
        rag_working_dir=Path("/tmp/rag"),
        llm_complete=lambda *a, **k: None,
        embedding_func=lambda *a, **k: None,
        vision_cascade=object(),
        web_search=lambda q: [],
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.max_iter_reasoner = 99  # type: ignore[misc]


@pytest.mark.unit
def test_research_config_defaults():
    cfg = ResearchConfig(
        rag_working_dir=Path("/tmp/rag"),
        llm_complete=lambda *a, **k: None,
        embedding_func=lambda *a, **k: None,
        vision_cascade=object(),
        web_search=lambda q: [],
    )
    assert cfg.max_iter_reasoner == 5
    assert cfg.max_iter_verifier == 3
    assert cfg.web_search_fallback is None
    assert cfg.output_dir is None
    assert cfg.telemetry_jsonl is None


@pytest.mark.unit
def test_required_fields_raise_typeerror_when_omitted():
    with pytest.raises(TypeError):
        Source()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        RetrievedImage()  # type: ignore[call-arg]


@pytest.mark.unit
def test_dataclass_count_and_shapes():
    """Confirm 7 stage dataclasses + ResearchState + ResearchResult + ResearchConfig = 10."""
    classes = [
        Source,
        WebBaseline,
        RetrievedImage,
        RetrieverOutput,
        ReasonerOutput,
        VerifierOutput,
        SynthesizerOutput,
        ResearchState,
        ResearchResult,
        ResearchConfig,
    ]
    for c in classes:
        assert dataclasses.is_dataclass(c), f"{c.__name__} is not a dataclass"
    # All except ResearchState must be frozen
    for c in classes:
        if c is ResearchState:
            continue
        # Frozen dataclasses set __dataclass_params__.frozen = True
        assert c.__dataclass_params__.frozen, f"{c.__name__} should be frozen"
