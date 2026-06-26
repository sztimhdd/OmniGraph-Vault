"""Unit tests for lib.research.stages.* (ar-1 stage stubs + retriever live wiring).

Covers:
- web_baseline.run (tests 1-3)
- retriever.run (tests 4-7)
- reasoner.run (test 8)
- verifier.run (test 9)
- typed-return-shape sanity (test 10)
- synthesizer._detect_language (tests 11-14)
- synthesizer.run (tests 15-20)

Mocks ``omnigraph_search.query.search`` via the import alias
``lib.research.stages.retriever.kg_search`` (the local name inside the module).
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from unittest import mock

import pytest

from lib.research.stages import (
    reasoner as reasoner_stage,
    retriever as retriever_stage,
    synthesizer as synthesizer_stage,
    verifier as verifier_stage,
    web_baseline as web_baseline_stage,
)
from lib.research.stages.synthesizer import _detect_language
from lib.research.types import (
    ReasonerOutput,
    ResearchConfig,
    ResearchState,
    RetrievedImage,
    RetrieverOutput,
    Source,
    SynthesizerOutput,
    VerifierOutput,
    WebBaseline,
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
# Test 1: web_baseline returns skipped when web_search returns []
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_web_baseline_skipped_when_empty(tmp_path):
    cfg = _make_cfg(tmp_path / "lightrag_storage", web_search=lambda q: [])
    out = await web_baseline_stage.run("hello", cfg)
    assert isinstance(out, WebBaseline)
    assert out.status == "skipped"
    assert "TAVILY" in (out.reason or "")
    assert out.snippets == []
    assert out.queries_used == ["hello"]


# ---------------------------------------------------------------------------
# Test 2: web_baseline returns failed when web_search raises
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_web_baseline_failed_when_raises(tmp_path):
    def boom(_q: str) -> list[dict]:
        raise RuntimeError("net down")

    cfg = _make_cfg(tmp_path / "lightrag_storage", web_search=boom)
    out = await web_baseline_stage.run("hello", cfg)
    assert isinstance(out, WebBaseline)
    assert out.status == "failed"
    assert out.reason == "net down"
    assert out.snippets == []


# ---------------------------------------------------------------------------
# Test 3: web_baseline returns ok when web_search returns live results
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_web_baseline_ok_with_live_results(tmp_path):
    cfg = _make_cfg(
        tmp_path / "lightrag_storage",
        web_search=lambda q: [
            {"url": "http://x", "title": "t", "content": "c"},
        ],
    )
    out = await web_baseline_stage.run("hello", cfg)
    assert isinstance(out, WebBaseline)
    assert out.status == "ok"
    assert len(out.snippets) == 1
    assert out.snippets[0].kind == "web"
    assert out.snippets[0].uri == "http://x"
    assert out.snippets[0].title == "t"
    assert out.snippets[0].snippet == "c"


# ---------------------------------------------------------------------------
# Test 4: retriever skipped when search returns ""
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_retriever_skipped_when_empty(tmp_path, monkeypatch):
    async def _empty_search(q, mode="hybrid", **kwargs):
        return ""

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _empty_search
    )
    cfg = _make_cfg(tmp_path / "lightrag_storage")
    out = await retriever_stage.run("hello", cfg)
    assert isinstance(out, RetrieverOutput)
    assert out.status == "skipped"
    assert "empty" in (out.reason or "").lower()
    assert out.chunks == []
    assert out.image_candidates == []


# ---------------------------------------------------------------------------
# Test 4b (arx-4 #64/#65 behavior anchor): retriever forwards mode="mix" and
# cfg.rag to kg_search. Pins the contract that #64 (vector chunks need mix mode)
# and #65 (rerank needs the lifespan rag) depend on — a regression here silently
# reverts to hybrid + fresh reranker-less instance (the 0-vector-chunks +
# "no rerank model" deployed symptom).
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_retriever_forwards_mix_mode_and_lifespan_rag(tmp_path, monkeypatch):
    captured: dict = {}

    async def _capturing_search(q, mode="hybrid", **kwargs):
        captured["mode"] = mode
        captured["rag"] = kwargs.get("rag", "MISSING")
        captured["only_context"] = kwargs.get("only_context", "MISSING")
        return ""  # empty → skipped; we only assert the call shape

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _capturing_search
    )
    sentinel_rag = object()
    cfg = dataclasses.replace(
        _make_cfg(tmp_path / "lightrag_storage"), rag=sentinel_rag
    )
    await retriever_stage.run("hello", cfg)

    assert captured["mode"] == "mix", "retriever must use mix mode for vector chunks (#64)"
    assert captured["rag"] is sentinel_rag, "retriever must forward cfg.rag (lifespan reranker, #65)"
    assert captured["only_context"] is True


# ---------------------------------------------------------------------------
# Test 5: retriever failed when search raises
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_retriever_failed_when_raises(tmp_path, monkeypatch):
    async def _boom(q, mode="hybrid", **kwargs):
        raise RuntimeError("KG down")

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _boom
    )
    cfg = _make_cfg(tmp_path / "lightrag_storage")
    out = await retriever_stage.run("hello", cfg)
    assert isinstance(out, RetrieverOutput)
    assert out.status == "failed"
    assert out.reason == "KG down"


# ---------------------------------------------------------------------------
# Test 6: retriever globs images from BASE_IMAGE_DIR for hashes in kg_text
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_retriever_globs_images_from_base_image_dir(
    tmp_path, monkeypatch
):
    base_dir = tmp_path
    images_root = base_dir / "images"
    h1 = "abcdef0123"
    h2 = "1234567890"
    for h in (h1, h2):
        d = images_root / h
        d.mkdir(parents=True)
        (d / "1.jpg").write_bytes(b"")
        (d / "2.jpg").write_bytes(b"")

    kg_text = (
        f"Paragraph mentioning hash {h1} and another hash {h2} embedded."
    )

    async def _live_search(q, mode="hybrid", **kwargs):
        return kg_text

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _live_search
    )
    cfg = _make_cfg(base_dir / "lightrag_storage")
    out = await retriever_stage.run("hello", cfg)
    assert isinstance(out, RetrieverOutput)
    assert out.status == "ok"
    assert len(out.chunks) == 1
    assert out.chunks[0].kind == "kg_chunk"
    assert len(out.image_candidates) >= 2
    assert all(isinstance(ic, RetrievedImage) for ic in out.image_candidates)
    hashes_seen = {ic.article_hash for ic in out.image_candidates}
    assert h1 in hashes_seen
    assert h2 in hashes_seen


# ---------------------------------------------------------------------------
# Test 7: retriever ok with empty image_candidates when BASE_IMAGE_DIR missing
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_retriever_ok_with_no_images_dir(tmp_path, monkeypatch):
    async def _live_search(q, mode="hybrid", **kwargs):
        return "Some text mentioning hash abcdef0123 but no dir on disk."

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _live_search
    )
    cfg = _make_cfg(tmp_path / "lightrag_storage")
    out = await retriever_stage.run("hello", cfg)
    assert isinstance(out, RetrieverOutput)
    assert out.status == "ok"
    assert out.image_candidates == []


# ---------------------------------------------------------------------------
# arx-1 retriever tests: paragraph split, cross-paragraph hash dedup,
# multi-extension case-insensitive glob, top-10 lex truncation.
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_retriever_splits_paragraphs_into_multiple_chunks(
    tmp_path, monkeypatch
):
    kg_text = (
        "First paragraph about topic A.\n\n"
        "Second paragraph about topic B with hash abcdef0123.\n\n"
        "Third paragraph closing thoughts."
    )

    async def _live_search(q, mode="hybrid", **kwargs):
        return kg_text

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _live_search
    )
    cfg = _make_cfg(tmp_path / "lightrag_storage")
    out = await retriever_stage.run("hello", cfg)
    assert out.status == "ok"
    assert len(out.chunks) == 3
    assert all(c.kind == "kg_chunk" for c in out.chunks)
    assert "First paragraph" in out.chunks[0].snippet
    assert "Second paragraph" in out.chunks[1].snippet
    assert "Third paragraph" in out.chunks[2].snippet


@pytest.mark.unit
async def test_retriever_dedups_hashes_across_paragraphs(
    tmp_path, monkeypatch
):
    base_dir = tmp_path
    images_root = base_dir / "images"
    h = "abcdef0123"
    d = images_root / h
    d.mkdir(parents=True)
    (d / "1.jpg").write_bytes(b"")
    (d / "2.jpg").write_bytes(b"")

    kg_text = (
        f"Para 1 mentioning {h}.\n\n"
        f"Para 2 mentioning {h} again.\n\n"
        f"Para 3 mentioning {h} once more."
    )

    async def _live_search(q, mode="hybrid", **kwargs):
        return kg_text

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _live_search
    )
    cfg = _make_cfg(base_dir / "lightrag_storage")
    out = await retriever_stage.run("hello", cfg)
    assert out.status == "ok"
    # Hash appears in 3 paragraphs but glob runs once → exactly 2 images.
    assert len(out.image_candidates) == 2
    assert {ic.image_path.name for ic in out.image_candidates} == {"1.jpg", "2.jpg"}


@pytest.mark.unit
async def test_retriever_globs_multiple_extensions_case_insensitive(
    tmp_path, monkeypatch
):
    base_dir = tmp_path
    images_root = base_dir / "images"
    h = "abcdef0123"
    d = images_root / h
    d.mkdir(parents=True)
    (d / "a.jpg").write_bytes(b"")
    (d / "b.JPEG").write_bytes(b"")
    (d / "c.PNG").write_bytes(b"")
    (d / "d.webp").write_bytes(b"")
    (d / "skip.txt").write_bytes(b"")  # Non-image: must be filtered out.

    kg_text = f"Para mentioning {h}."

    async def _live_search(q, mode="hybrid", **kwargs):
        return kg_text

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _live_search
    )
    cfg = _make_cfg(base_dir / "lightrag_storage")
    out = await retriever_stage.run("hello", cfg)
    assert out.status == "ok"
    names = {ic.image_path.name for ic in out.image_candidates}
    assert names == {"a.jpg", "b.JPEG", "c.PNG", "d.webp"}


@pytest.mark.unit
async def test_retriever_caps_image_candidates_at_10(tmp_path, monkeypatch):
    base_dir = tmp_path
    images_root = base_dir / "images"
    # 3 hashes × 4 images each = 12 candidates; expect cap of 10.
    hashes = ["aaaaaaaaaa", "bbbbbbbbbb", "cccccccccc"]
    for h in hashes:
        d = images_root / h
        d.mkdir(parents=True)
        for i in range(4):
            (d / f"{i}.jpg").write_bytes(b"")

    kg_text = (
        f"Para 1 mentions {hashes[0]}.\n\n"
        f"Para 2 mentions {hashes[1]}.\n\n"
        f"Para 3 mentions {hashes[2]}."
    )

    async def _live_search(q, mode="hybrid", **kwargs):
        return kg_text

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _live_search
    )
    cfg = _make_cfg(base_dir / "lightrag_storage")
    out = await retriever_stage.run("hello", cfg)
    assert out.status == "ok"
    assert len(out.image_candidates) == 10
    # Deterministic lex order: hash then filename.
    sorted_keys = [
        (ic.article_hash, ic.image_path.name) for ic in out.image_candidates
    ]
    assert sorted_keys == sorted(sorted_keys)
    # First 10 in (hash, name) lex order: all 4 of aaaa, all 4 of bbbb, first 2 of cccc.
    assert all(ic.article_hash == hashes[0] for ic in out.image_candidates[:4])
    assert all(ic.article_hash == hashes[1] for ic in out.image_candidates[4:8])
    assert all(ic.article_hash == hashes[2] for ic in out.image_candidates[8:10])


# ---------------------------------------------------------------------------
# Test 8: reasoner — ar-2 replaces the ar-1 stub with a real bounded LLM
# agent loop. With a mock cfg.llm_complete that returns a final-on-turn-1
# decision, the loop terminates after one turn with empty output lists.
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_reasoner_returns_ok_on_immediate_final(tmp_path):
    from lib.research.stages.reasoner import _LLMDecision

    async def _final_llm(prompt, tools):
        return _LLMDecision(is_final=True, content="")

    cfg = _make_cfg(tmp_path / "lightrag_storage")
    cfg = dataclasses.replace(cfg, llm_complete=_final_llm)
    retrieved = RetrieverOutput(chunks=[], image_candidates=[])
    out = await reasoner_stage.run("hello", cfg, retrieved)
    assert isinstance(out, ReasonerOutput)
    assert out.status == "ok"
    assert out.iter_count == 1
    assert out.additional_chunks == []
    assert out.analyzed_images == []


# ---------------------------------------------------------------------------
# Test 9: verifier — real bounded loop with deterministic final-answer mock
# (ar-3-02 update: ar-1 stub replaced; injecting an immediate-final
# llm_complete keeps this test deterministic without exercising the live
# loop body, which is covered in test_verifier_agent_loop.py.)
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_verifier_returns_typed_output(tmp_path):
    from lib.research.stages.verifier import _LLMDecision

    async def _final_llm(prompt, tools):
        return _LLMDecision(is_final=True, content="", confidence=0.0)

    cfg = _make_cfg(tmp_path / "lightrag_storage")
    cfg = dataclasses.replace(cfg, llm_complete=_final_llm)
    reasoned = ReasonerOutput(
        inferences_md="",
        additional_chunks=[],
        analyzed_images=[],
        iter_count=0,
    )
    out = await verifier_stage.run("hello", cfg, reasoned)
    assert isinstance(out, VerifierOutput)
    assert out.status in {"ok", "failed"}
    assert out.iter_count >= 0
    assert out.confidence == 0.0
    assert out.external_citations == []
    assert out.discrepancies == []


# ---------------------------------------------------------------------------
# Test 10: all 4 stages return correctly-typed dataclass instances
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_all_stages_return_typed_dataclasses(tmp_path, monkeypatch):
    async def _empty_search(q, mode="hybrid", **kwargs):
        return ""

    monkeypatch.setattr(
        "lib.research.stages.retriever.kg_search", _empty_search
    )
    cfg = _make_cfg(tmp_path / "lightrag_storage")

    wb = await web_baseline_stage.run("q", cfg)
    rt = await retriever_stage.run("q", cfg)
    rs = await reasoner_stage.run("q", cfg, rt)
    vf = await verifier_stage.run("q", cfg, rs)

    assert isinstance(wb, WebBaseline)
    assert isinstance(rt, RetrieverOutput)
    assert isinstance(rs, ReasonerOutput)
    assert isinstance(vf, VerifierOutput)


# ---------------------------------------------------------------------------
# Test 11-14: _detect_language CJK heuristic
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_detect_language_chinese():
    # CJK ratio ≥ 0.3 → "zh". Use a query with ≥30% CJK chars (the plan's
    # original example "什么是 Hermes Harness" was 3/19 ≈ 15.8% — below the
    # 0.3 threshold and inconsistent with the heuristic spec). This string
    # is 9 CJK / 18 = 50%, comfortably above threshold.
    assert _detect_language("什么是 Hermes 深度解析方法") == "zh"


@pytest.mark.unit
def test_detect_language_english():
    assert _detect_language("What is Hermes Harness") == "en"


@pytest.mark.unit
def test_detect_language_empty():
    assert _detect_language("") == "en"


@pytest.mark.unit
def test_detect_language_chinese_long_form():
    q = "Hermes 的深度解析方法和原理"
    cjk_count = sum(1 for c in q if "一" <= c <= "鿿")
    ratio = cjk_count / len(q)
    # Make threshold explicit per plan
    assert ratio >= 0.3
    assert _detect_language(q) == "zh"


# ---------------------------------------------------------------------------
# Test 15: synthesizer with stubbed state, retrieved=ok with one chunk
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_synthesizer_with_one_chunk(tmp_path):
    cfg = _make_cfg(tmp_path / "lightrag_storage")
    state = ResearchState(query="hello", timestamp_start=0.0)
    state.web_baseline = WebBaseline(
        queries_used=["hello"],
        snippets=[],
        status="skipped",
        reason="stub",
    )
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="The KG content here.")],
        image_candidates=[],
    )
    state.reasoned = ReasonerOutput(
        inferences_md="",
        additional_chunks=[],
        analyzed_images=[],
        iter_count=0,
        status="skipped",
        reason="stub",
    )
    state.verified = VerifierOutput(
        fact_check_summary_md="",
        confidence=0.0,
        external_citations=[],
        discrepancies=[],
        iter_count=0,
        status="skipped",
        reason="stub",
    )

    # arx-2-finish GAP A: synthesizer now synthesizes via get_llm_func() instead
    # of echoing chunks[0].snippet verbatim. Pin the NEW contract: the chunk
    # content flows into the LLM PROMPT (not verbatim into markdown), the real
    # LLM prose becomes the markdown, and confidence/notes invariants hold.
    captured = {}

    async def _capture_llm(prompt, **kw):
        captured["prompt"] = prompt
        return "# Synthesized\n\nReal answer prose."

    with mock.patch(
        "lib.research.stages.synthesizer.get_llm_func",
        return_value=_capture_llm,
        create=True,
    ):
        out = await synthesizer_stage.run("hello", cfg, state)
    assert isinstance(out, SynthesizerOutput)
    assert "The KG content here." in captured["prompt"]  # chunk → prompt
    assert "Real answer prose." in out.markdown  # LLM prose → markdown
    assert len(out.note_lines) >= 1
    assert out.confidence == 0.5


# ---------------------------------------------------------------------------
# Test 16: synthesizer with retrieved=None → "did not run" note
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_synthesizer_with_no_retrieved(tmp_path):
    cfg = _make_cfg(tmp_path / "lightrag_storage")
    state = ResearchState(query="hello", timestamp_start=0.0)
    # All None — none of the upstream stages ran.

    out = await synthesizer_stage.run("hello", cfg, state)
    assert isinstance(out, SynthesizerOutput)
    assert out.confidence == 0.0
    joined = "\n".join(out.note_lines)
    assert "Retriever did not run" in joined


# ---------------------------------------------------------------------------
# Test 17: synthesizer caps embedded_images at 5
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_synthesizer_caps_embedded_images(tmp_path):
    cfg = _make_cfg(tmp_path / "lightrag_storage")
    state = ResearchState(query="hello", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="body")],
        image_candidates=[
            RetrievedImage(article_hash="a", image_path=Path(f"/tmp/{i}.jpg"))
            for i in range(7)
        ],
    )
    out = await synthesizer_stage.run("hello", cfg, state)
    assert len(out.embedded_images) == 5


# ---------------------------------------------------------------------------
# Test 18: synthesizer Chinese query — title contains "关于「"
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_synthesizer_chinese_title(tmp_path):
    cfg = _make_cfg(tmp_path / "lightrag_storage")
    state = ResearchState(query="什么是 Hermes 的深度解析", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="内容")],
        image_candidates=[],
    )

    # arx-2-finish GAP A: the hardcoded Chinese title is now the GRACEFUL-DEGRADE
    # title (LLM-failure fallback). Force the degrade path to assert the language
    # routing still selects the Chinese fallback heading.
    async def _failing_llm(prompt, **kw):
        raise RuntimeError("forced degrade")

    with mock.patch(
        "lib.research.stages.synthesizer.get_llm_func",
        return_value=_failing_llm,
        create=True,
    ):
        out = await synthesizer_stage.run("什么是 Hermes 的深度解析", cfg, state)
    assert out.markdown.startswith("# 关于「")


# ---------------------------------------------------------------------------
# Test 19: synthesizer English query — title starts with "# Research Answer:"
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_synthesizer_english_title(tmp_path):
    cfg = _make_cfg(tmp_path / "lightrag_storage")
    state = ResearchState(query="What is Hermes Harness", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="body")],
        image_candidates=[],
    )

    # arx-2-finish GAP A: the hardcoded English title is now the GRACEFUL-DEGRADE
    # title. Force the degrade path to assert language routing selects it.
    async def _failing_llm(prompt, **kw):
        raise RuntimeError("forced degrade")

    with mock.patch(
        "lib.research.stages.synthesizer.get_llm_func",
        return_value=_failing_llm,
        create=True,
    ):
        out = await synthesizer_stage.run("What is Hermes Harness", cfg, state)
    assert out.markdown.startswith("# Research Answer:")


# ---------------------------------------------------------------------------
# Test 20: synthesizer never raises with None snippet
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_synthesizer_handles_none_snippet(tmp_path):
    cfg = _make_cfg(tmp_path / "lightrag_storage")
    state = ResearchState(query="hello", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet=None)],
        image_candidates=[],
    )
    out = await synthesizer_stage.run("hello", cfg, state)
    assert isinstance(out, SynthesizerOutput)
    assert isinstance(out.markdown, str)
    assert len(out.markdown) > 0
