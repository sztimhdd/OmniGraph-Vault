"""End-to-end orchestrator integration tests.

Exercises ``lib.research.orchestrator.research()`` with a minimal hand-rolled
``ResearchConfig`` (no env coupling) and verifies:

- All 5 ResearchState fields populate
- Stage status alphabet holds (ok|skipped) for ar-1
- Strict sequential pipeline order (Axis 1)
- Best-effort failure handling (Axis 3) — orchestrator never raises out
- ``research_stream()`` raises ``NotImplementedError("ar-4")`` (LIB-08 split)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lib.research.orchestrator import research, research_stream
from lib.research.types import (
    ResearchConfig,
    ResearchResult,
    ResearchState,
)


def _make_cfg(rag_working_dir: Path, web_search=None) -> ResearchConfig:
    """Build a minimal ResearchConfig for tests (no env coupling)."""

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
        web_search=web_search if web_search is not None else _stub_web_search,
    )


# ---------------------------------------------------------------------------
# Test 1: full pipeline returns ResearchResult with all 5 state fields populated
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_research_returns_result_all_state_populated(
    tmp_path, monkeypatch
):
    async def _empty_search(q, mode="hybrid", **kwargs):
        return ""

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _empty_search
    )
    cfg = _make_cfg(tmp_path / "lightrag_storage")

    result = await research("test query", cfg)
    assert isinstance(result, ResearchResult)
    assert isinstance(result.state, ResearchState)
    # All 5 stage fields populated
    assert result.state.web_baseline is not None
    assert result.state.retrieved is not None
    assert result.state.reasoned is not None
    assert result.state.verified is not None
    assert result.state.synthesized is not None
    # Status alphabet for ar-1 (ar-2 update: reasoner is no longer a stub —
    # with the dummy stub llm_complete in _make_cfg the loop body raises and
    # surfaces as status="failed" via Axis 3 best-effort. Either "ok" or
    # "failed" is acceptable here; the orchestrator MUST NOT raise out.)
    assert result.state.web_baseline.status in {"ok", "skipped"}
    assert result.state.retrieved.status in {"ok", "skipped"}
    assert result.state.reasoned.status in {"ok", "failed"}
    # ar-3-02 update: Verifier is no longer a stub — with the dummy stub
    # llm_complete in _make_cfg the loop body raises and surfaces as
    # status="failed" via Axis 3 best-effort. Either "ok" or "failed" is
    # acceptable here; the orchestrator MUST NOT raise out.
    assert result.state.verified.status in {"ok", "failed"}
    # Synthesizer has NO status field (Axis 8)
    assert not hasattr(result.state.synthesized, "status")


# ---------------------------------------------------------------------------
# Test 2: with mocked KG search returning text, markdown contains it
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_research_with_live_kg_response(tmp_path, monkeypatch):
    kg_response = "LightRAG is a hybrid knowledge graph engine."

    async def _live_search(q, mode="hybrid", **kwargs):
        return kg_response

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _live_search
    )
    cfg = _make_cfg(tmp_path / "lightrag_storage")

    result = await research("What is LightRAG?", cfg)
    assert kg_response in result.markdown
    assert result.confidence == 0.5
    assert len(result.sources) >= 1


# ---------------------------------------------------------------------------
# Test 3: with mocked KG search raising, retriever fails but orchestrator OK
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_research_orchestrator_does_not_raise_on_kg_failure(
    tmp_path, monkeypatch
):
    async def _boom(q, mode="hybrid", **kwargs):
        raise RuntimeError("KG down")

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _boom
    )
    cfg = _make_cfg(tmp_path / "lightrag_storage")

    # MUST NOT raise — best-effort failure handling (Axis 3)
    result = await research("test query", cfg)
    assert result.state.retrieved is not None
    assert result.state.retrieved.status == "failed"
    assert result.state.retrieved.reason == "KG down"
    # Synthesizer notes the failure
    joined = "\n".join(result.state.synthesized.note_lines)
    assert "Retriever failed: KG down" in joined


# ---------------------------------------------------------------------------
# Test 4: pipeline order is strictly web_baseline -> retriever -> reasoner -> verifier -> synthesizer
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_research_pipeline_order(tmp_path, monkeypatch):
    """Patch each stage's run to append to a shared list; assert strict order."""
    call_order: list[str] = []

    # Save originals so we can wrap them.
    from lib.research.stages import (
        reasoner as reasoner_stage,
        retriever as retriever_stage,
        synthesizer as synthesizer_stage,
        verifier as verifier_stage,
        web_baseline as web_baseline_stage,
    )

    orig_wb = web_baseline_stage.run
    orig_rt = retriever_stage.run
    orig_rs = reasoner_stage.run
    orig_vf = verifier_stage.run
    orig_sn = synthesizer_stage.run

    async def _wrap_wb(*a, **kw):
        call_order.append("web_baseline")
        return await orig_wb(*a, **kw)

    async def _wrap_rt(*a, **kw):
        call_order.append("retriever")
        return await orig_rt(*a, **kw)

    async def _wrap_rs(*a, **kw):
        call_order.append("reasoner")
        return await orig_rs(*a, **kw)

    async def _wrap_vf(*a, **kw):
        call_order.append("verifier")
        return await orig_vf(*a, **kw)

    async def _wrap_sn(*a, **kw):
        call_order.append("synthesizer")
        return await orig_sn(*a, **kw)

    monkeypatch.setattr(web_baseline_stage, "run", _wrap_wb)
    monkeypatch.setattr(retriever_stage, "run", _wrap_rt)
    monkeypatch.setattr(reasoner_stage, "run", _wrap_rs)
    monkeypatch.setattr(verifier_stage, "run", _wrap_vf)
    monkeypatch.setattr(synthesizer_stage, "run", _wrap_sn)

    # Also stub out kg_search so retriever doesn't try to hit live KG.
    async def _empty_search(q, mode="hybrid", **kwargs):
        return ""

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _empty_search
    )

    cfg = _make_cfg(tmp_path / "lightrag_storage")
    await research("test query", cfg)

    assert call_order == [
        "web_baseline",
        "retriever",
        "reasoner",
        "verifier",
        "synthesizer",
    ]


# ---------------------------------------------------------------------------
# Test 5: research_stream yields events (post ar-4-01 — body landed; LIB-08
# closed). This test pinned the ar-1 stub `raise NotImplementedError("ar-4")`;
# ar-4-01 fills the body so the assertion flips: the iterator must produce at
# least pipeline_start as its first event. Detailed iterator-order coverage
# lives in test_research_stream.py.
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_research_stream_yields_events_after_ar4(tmp_path, monkeypatch):
    async def _empty_search(q, mode="hybrid", **kwargs):
        return ""

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _empty_search
    )
    cfg = _make_cfg(tmp_path / "lightrag_storage")
    events = []
    async for evt in research_stream("test query", cfg):
        events.append(evt)
    assert len(events) >= 1
    assert events[0]["event_type"] == "pipeline_start"
    assert events[-1]["event_type"] == "pipeline_end"
