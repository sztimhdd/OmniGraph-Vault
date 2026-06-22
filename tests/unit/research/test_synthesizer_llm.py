"""GAP-A real-LLM synthesis behavioral tests (arx-2-finish Wave 0 — RED floor).

These 3 tests pin the observable behavior that arx-2-finish Wave 1 must deliver:
the synthesizer calls a real plain-text LLM provider via ``get_llm_func()`` and
synthesizes prose from ALL retrieved chunks, instead of returning
``state.retrieved.chunks[0].snippet`` verbatim under a hardcoded heading.

RED at Wave 0 (synthesizer.run still returns the stub) → GREEN at Wave 1.
The failures MUST be assertion failures (the tests run against the real run()),
NOT collection/import errors.

Test bodies are RESEARCH.md §Risk C lines 436-493 verbatim. The import block
and ``_make_minimal_cfg`` helper mirror test_synthesizer_caption_embeds.py:39-59.
Each test installs its own ``mock.patch`` on
``lib.research.stages.synthesizer.get_llm_func`` (overrides the autouse conftest
baseline) so the synthesizer awaits the test's mock provider.
"""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from lib.research.stages.synthesizer import run as run_synthesizer
from lib.research.types import (
    ResearchConfig,
    ResearchState,
    RetrieverOutput,
    Source,
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


@pytest.mark.unit
async def test_synthesizer_uses_all_chunks_in_prompt(tmp_path):
    """Prompt contains ALL chunk snippets, not just chunks[0]."""
    chunks = [
        Source(kind="kg_chunk", uri=f"x{i}", snippet=f"chunk-{i}")
        for i in range(3)
    ]
    state = ResearchState(query="q", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(chunks=chunks, image_candidates=[])

    captured_prompt = {}

    async def mock_llm(prompt, **kw):
        captured_prompt['prompt'] = prompt
        return "# Real answer\n\nSome prose [1]."

    # Patch get_llm_func to return mock_llm. create=True so the patch is valid
    # at Wave 0 (synthesizer not yet importing get_llm_func) — the test then
    # fails on the ASSERTION (RED), not at patch setup. At Wave 1 the attribute
    # exists (module-level import) and create=True is a harmless no-op.
    with mock.patch('lib.research.stages.synthesizer.get_llm_func', return_value=mock_llm, create=True):
        result = await run_synthesizer("q", _make_minimal_cfg(tmp_path), state)

    for i in range(3):
        assert f"chunk-{i}" in captured_prompt['prompt']


@pytest.mark.unit
async def test_synthesizer_degrades_gracefully_on_llm_failure(tmp_path):
    """LLM exception → note_line added + markdown non-empty (no raise)."""
    state = ResearchState(query="q", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="text")],
        image_candidates=[]
    )

    async def failing_llm(prompt, **kw):
        raise RuntimeError("LLM timeout")

    with mock.patch('lib.research.stages.synthesizer.get_llm_func', return_value=failing_llm, create=True):
        result = await run_synthesizer("q", _make_minimal_cfg(tmp_path), state)

    assert result.markdown  # non-empty
    assert any("failed" in ln.lower() or "error" in ln.lower() for ln in result.note_lines)


@pytest.mark.unit
async def test_synthesizer_real_prose_not_chunks0_verbatim(tmp_path):
    """Real LLM response replaces the stub chunks[0].snippet verbatim."""
    state = ResearchState(query="q", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="THE_STUB_SNIPPET")],
        image_candidates=[]
    )

    async def mock_llm(prompt, **kw):
        return "# Real LLM Answer\n\nThis is synthesized prose, not a snippet."

    with mock.patch('lib.research.stages.synthesizer.get_llm_func', return_value=mock_llm, create=True):
        result = await run_synthesizer("q", _make_minimal_cfg(tmp_path), state)

    # The new real-LLM path must NOT return chunks[0].snippet verbatim
    assert "THE_STUB_SNIPPET" not in result.markdown
    assert "Real LLM Answer" in result.markdown
