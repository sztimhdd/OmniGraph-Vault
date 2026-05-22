"""TEST-03 (Synthesizer half) + ar-1 regression guards for ar-2-02.

Covers ORCH-05: Synthesizer caption-anchored image embeds. The Synthesizer
now sources image alt text from ``state.reasoned.analyzed_images[i].caption``
when available (delivered by ar-2-01's Reasoner agent loop), with ar-1
filename-fallback when Reasoner skipped/failed/produced no images
(preserves Axis 3 best-effort).

Tests:
    1. test_synthesizer_uses_reasoned_caption — TEST-03 hard requirement
       (caption-anchored happy path).
    2. test_synthesizer_falls_back_to_filename_when_reasoned_none — ar-1
       regression guard (state.reasoned=None).
    3. test_synthesizer_falls_back_when_analyzed_images_empty — Reasoner ran
       but produced no analyzed images.
    4. test_synthesizer_url_format_unchanged — URL body byte-for-byte
       identical between caption + fallback paths.
    5. test_synthesizer_no_status_field — Axis 8 invariant.
    6. test_synthesizer_caption_path_caps_at_5 — image cap preserved on
       caption path.
    7. test_synthesizer_caption_none_falls_back_to_filename — defensive
       ``or img.image_path.name`` guard when caption is unexpectedly None.
    8. test_synthesizer_reasoned_additional_chunks_in_sources — plan-checker
       ruled extension: Reasoner's kg_search findings surface in
       ``result.sources``.
    9. test_synthesizer_failed_reasoner_does_not_leak_additional_chunks —
       gating discipline: failed Reasoner's additional_chunks NOT surfaced.
   10. test_synthesizer_path_shape_preserved — embedded_images stays
       list[Path] (regression guard for SynthesizerOutput contract).
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from lib.research.stages.synthesizer import run as run_synthesizer
from lib.research.types import (
    ReasonerOutput,
    ResearchConfig,
    ResearchState,
    RetrievedImage,
    RetrieverOutput,
    Source,
    SynthesizerOutput,
)


def _make_minimal_cfg(tmp_path: Path) -> ResearchConfig:
    """Minimal ResearchConfig — Synthesizer uses none of the callables."""
    return ResearchConfig(
        rag_working_dir=tmp_path / "lightrag_storage",
        llm_complete=lambda *a, **kw: None,
        embedding_func=lambda *a, **kw: None,
        vision_cascade=object(),
        web_search=lambda q: [],
    )


def _make_image_file(tmp_path: Path, article_hash: str, name: str) -> Path:
    """Create an empty image file at ``tmp_path/<hash>/<name>``."""
    image_path = tmp_path / article_hash / name
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"")
    return image_path


# ---------------------------------------------------------------------------
# Test 1: TEST-03 hard requirement — caption-anchored happy path
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_synthesizer_uses_reasoned_caption(tmp_path):
    """ORCH-05 + TEST-03: caption from analyzed_images flows into markdown alt text."""
    image_path = _make_image_file(tmp_path, "deadbeef00", "5.jpg")

    state = ResearchState(query="test query", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="seed")],
        image_candidates=[],
    )
    state.reasoned = ReasonerOutput(
        inferences_md="(inferences)",
        additional_chunks=[],
        analyzed_images=[
            RetrievedImage(
                article_hash="deadbeef00",
                image_path=image_path,
                caption="<MOCK_CAPTION>",
            )
        ],
        iter_count=2,
        status="ok",
    )

    cfg = _make_minimal_cfg(tmp_path)
    result = await run_synthesizer("test query", cfg, state)

    expected = "![<MOCK_CAPTION>](http://localhost:8765/deadbeef00/5.jpg)"
    assert expected in result.markdown
    # Path-shape regression guard (sealed once here per plan-checker note).
    assert isinstance(result.embedded_images[0], Path)
    assert result.embedded_images[0] == image_path


# ---------------------------------------------------------------------------
# Test 2: ar-1 regression guard — state.reasoned is None
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_synthesizer_falls_back_to_filename_when_reasoned_none(tmp_path):
    """state.reasoned=None → alt text falls back to img.name (ar-1 behavior)."""
    image_path = _make_image_file(tmp_path, "abc1234567", "3.jpg")

    state = ResearchState(query="test", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="text")],
        image_candidates=[
            RetrievedImage(article_hash="abc1234567", image_path=image_path)
        ],
    )
    state.reasoned = None  # Reasoner never ran

    cfg = _make_minimal_cfg(tmp_path)
    result = await run_synthesizer("test", cfg, state)

    expected = "![3.jpg](http://localhost:8765/abc1234567/3.jpg)"
    assert expected in result.markdown


# ---------------------------------------------------------------------------
# Test 3: fallback when analyzed_images is empty
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_synthesizer_falls_back_when_analyzed_images_empty(tmp_path):
    """Reasoner ran but selected no images → fall back to retrieved.image_candidates."""
    image_path = _make_image_file(tmp_path, "abc1234567", "3.jpg")

    state = ResearchState(query="test", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="text")],
        image_candidates=[
            RetrievedImage(article_hash="abc1234567", image_path=image_path)
        ],
    )
    state.reasoned = ReasonerOutput(
        inferences_md="reasoner ran but no vision_analyze calls",
        additional_chunks=[],
        analyzed_images=[],  # empty — Reasoner produced no captions
        iter_count=1,
        status="ok",
    )

    cfg = _make_minimal_cfg(tmp_path)
    result = await run_synthesizer("test", cfg, state)

    expected = "![3.jpg](http://localhost:8765/abc1234567/3.jpg)"
    assert expected in result.markdown


# ---------------------------------------------------------------------------
# Test 4: URL format byte-for-byte identical between caption + fallback paths
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_synthesizer_url_format_unchanged(tmp_path):
    """URL body identical between caption-path and fallback-path for same image_path."""
    image_path = _make_image_file(tmp_path, "abc1234567", "7.jpg")

    cfg = _make_minimal_cfg(tmp_path)

    # Caption-path state
    state_cap = ResearchState(query="q", timestamp_start=0.0)
    state_cap.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="t")],
        image_candidates=[],
    )
    state_cap.reasoned = ReasonerOutput(
        inferences_md="",
        additional_chunks=[],
        analyzed_images=[
            RetrievedImage(
                article_hash="abc1234567",
                image_path=image_path,
                caption="cap-text",
            )
        ],
        iter_count=1,
        status="ok",
    )

    # Fallback-path state (reasoned=None)
    state_fb = ResearchState(query="q", timestamp_start=0.0)
    state_fb.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="t")],
        image_candidates=[
            RetrievedImage(article_hash="abc1234567", image_path=image_path)
        ],
    )
    state_fb.reasoned = None

    result_cap = await run_synthesizer("q", cfg, state_cap)
    result_fb = await run_synthesizer("q", cfg, state_fb)

    pat = re.compile(r"!\[[^\]]*\]\((http://localhost:8765/[^\)]+)\)")
    url_cap = pat.search(result_cap.markdown).group(1)
    url_fb = pat.search(result_fb.markdown).group(1)
    assert url_cap == url_fb == "http://localhost:8765/abc1234567/7.jpg"


# ---------------------------------------------------------------------------
# Test 5: Axis 8 invariant — no status field on SynthesizerOutput
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_synthesizer_no_status_field():
    """Axis 8: SynthesizerOutput has no status field even after ar-2 changes."""
    field_names = {f.name for f in dataclasses.fields(SynthesizerOutput)}
    assert "status" not in field_names
    assert "reason" not in field_names


# ---------------------------------------------------------------------------
# Test 6: caption path caps at 5
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_synthesizer_caption_path_caps_at_5(tmp_path):
    """analyzed_images of 8 entries → exactly 5 inline image refs + 5 embedded paths."""
    images = []
    for i in range(8):
        p = _make_image_file(tmp_path, "h", f"{i}.jpg")
        images.append(
            RetrievedImage(article_hash="h", image_path=p, caption=f"cap{i}")
        )

    state = ResearchState(query="q", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="t")],
        image_candidates=[],
    )
    state.reasoned = ReasonerOutput(
        inferences_md="",
        additional_chunks=[],
        analyzed_images=images,
        iter_count=1,
        status="ok",
    )

    cfg = _make_minimal_cfg(tmp_path)
    result = await run_synthesizer("q", cfg, state)

    assert len(result.embedded_images) == 5
    inline_refs = re.findall(r"!\[[^\]]*\]\(http://localhost:8765/[^\)]+\)",
                             result.markdown)
    assert len(inline_refs) == 5


# ---------------------------------------------------------------------------
# Test 7: caption=None defensive fallback to filename
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_synthesizer_caption_none_falls_back_to_filename(tmp_path):
    """caption=None on analyzed_image → alt text falls back to img.image_path.name."""
    image_path = _make_image_file(tmp_path, "h", "9.jpg")

    state = ResearchState(query="q", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="t")],
        image_candidates=[],
    )
    state.reasoned = ReasonerOutput(
        inferences_md="",
        additional_chunks=[],
        analyzed_images=[
            RetrievedImage(article_hash="h", image_path=image_path, caption=None)
        ],
        iter_count=1,
        status="ok",
    )

    cfg = _make_minimal_cfg(tmp_path)
    result = await run_synthesizer("q", cfg, state)

    expected = "![9.jpg](http://localhost:8765/h/9.jpg)"
    assert expected in result.markdown


# ---------------------------------------------------------------------------
# Test 8: plan-checker ruled extension — Reasoner's additional_chunks
#         surface in result.sources when status=="ok"
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_synthesizer_reasoned_additional_chunks_in_sources(tmp_path):
    """Reasoner kg_search findings surface in result.sources."""
    extra = Source(kind="kg_chunk", uri="reasoner://1",
                   snippet="from reasoner kg_search")

    state = ResearchState(query="q", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="r://0", snippet="seed")],
        image_candidates=[],
    )
    state.reasoned = ReasonerOutput(
        inferences_md="",
        additional_chunks=[extra],
        analyzed_images=[],
        iter_count=1,
        status="ok",
    )

    cfg = _make_minimal_cfg(tmp_path)
    result = await run_synthesizer("q", cfg, state)

    assert extra in result.sources


# ---------------------------------------------------------------------------
# Test 9: gating — failed Reasoner's additional_chunks NOT surfaced
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_synthesizer_failed_reasoner_does_not_leak_additional_chunks(
    tmp_path,
):
    """Failed Reasoner → additional_chunks NOT surfaced (gating discipline)."""
    leaked = Source(kind="kg_chunk", uri="reasoner://leaked",
                    snippet="should not appear")

    state = ResearchState(query="q", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="r://0", snippet="seed")],
        image_candidates=[],
    )
    state.reasoned = ReasonerOutput(
        inferences_md="",
        additional_chunks=[leaked],
        analyzed_images=[],
        iter_count=1,
        status="failed",
        reason="LLM timeout",
    )

    cfg = _make_minimal_cfg(tmp_path)
    result = await run_synthesizer("q", cfg, state)

    assert leaked not in result.sources
    # Degradation note must surface (ar-1 mechanism preserved).
    joined = "\n".join(result.note_lines)
    assert "Reasoner failed" in joined


# ---------------------------------------------------------------------------
# Test 10: embedded_images shape preserved (list[Path])
# ---------------------------------------------------------------------------
@pytest.mark.unit
async def test_synthesizer_path_shape_preserved(tmp_path):
    """embedded_images stays list[Path] across both caption + fallback paths."""
    image_path = _make_image_file(tmp_path, "h", "1.jpg")

    # Caption path
    state_cap = ResearchState(query="q", timestamp_start=0.0)
    state_cap.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="t")],
        image_candidates=[],
    )
    state_cap.reasoned = ReasonerOutput(
        inferences_md="",
        additional_chunks=[],
        analyzed_images=[
            RetrievedImage(article_hash="h", image_path=image_path, caption="c")
        ],
        iter_count=1,
        status="ok",
    )

    # Fallback path
    state_fb = ResearchState(query="q", timestamp_start=0.0)
    state_fb.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="t")],
        image_candidates=[
            RetrievedImage(article_hash="h", image_path=image_path)
        ],
    )

    cfg = _make_minimal_cfg(tmp_path)
    r_cap = await run_synthesizer("q", cfg, state_cap)
    r_fb = await run_synthesizer("q", cfg, state_fb)

    assert all(isinstance(p, Path) for p in r_cap.embedded_images)
    assert all(isinstance(p, Path) for p in r_fb.embedded_images)
