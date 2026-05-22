---
phase: ar-2-reasoner-vision-deepening
plan: 02
type: execute
wave: 2
depends_on:
  - ar-2-01
files_modified:
  - lib/research/stages/synthesizer.py
  - tests/unit/research/test_synthesizer_caption_embeds.py
autonomous: true
requirements:
  - ORCH-05
  - TEST-03

must_haves:
  truths:
    - "Synthesizer emits inline images of the form `![<vision-caption>](http://localhost:8765/<hash>/<N>.jpg)` where the caption comes from `state.reasoned.analyzed_images[i].caption` (NOT the bare filename)"
    - "Image URL is derived from `image_path.parent.name` (article hash) + `image_path.name` (filename like `5.jpg`) — unchanged URL format from ar-1"
    - "Fallback to `state.retrieved.image_candidates` with `img.name` as alt text when `state.reasoned is None` OR `state.reasoned.analyzed_images` is empty (Reasoner skipped/failed) — preserves ar-1 behavior under degradation (Axis 3)"
    - "Synthesizer remains a terminal stage: NO `status` field; degradation note_lines mechanism unchanged from ar-1 (Axis 8)"
    - "CJK language-detection heuristic from ar-1 is preserved (Axis 10 ar-1 scope — LLM-driven detection lands in ar-4)"
    - "ar-1 regression guard: with `state.reasoned is None` and non-empty `state.retrieved.image_candidates`, alt text falls back to `img.name` exactly as ar-1 emitted"
    - "TEST-03 Synthesizer-half asserts: a fixture state with `reasoned.analyzed_images` containing `caption='<MOCK_CAPTION>'` produces markdown containing literal `![<MOCK_CAPTION>](http://localhost:8765/...)`"
  artifacts:
    - path: "lib/research/stages/synthesizer.py"
      provides: "Caption-anchored image embeds (replaces ar-1 filename-placeholder embeds)"
      contains: "async def run(query, cfg, state) -> SynthesizerOutput, _detect_language helper unchanged from ar-1"
    - path: "tests/unit/research/test_synthesizer_caption_embeds.py"
      provides: "TEST-03 Synthesizer-half + ar-1 regression guard for filename-fallback path"
      contains: "test_synthesizer_uses_reasoned_caption, test_synthesizer_falls_back_to_filename_when_reasoned_none, test_synthesizer_falls_back_when_analyzed_images_empty, test_synthesizer_url_format_unchanged, test_synthesizer_no_status_field"
  key_links:
    - from: "lib/research/stages/synthesizer.py"
      to: "state.reasoned.analyzed_images[i].caption"
      via: "iterate state.reasoned.analyzed_images, emit ![{img.caption}](http://localhost:8765/{hash}/{name})"
      pattern: "state\\.reasoned\\.analyzed_images"
    - from: "lib/research/stages/synthesizer.py"
      to: "state.retrieved.image_candidates (fallback path)"
      via: "fall back to img.name as alt text when state.reasoned is None or analyzed_images is empty"
      pattern: "state\\.retrieved\\.image_candidates"
---

<objective>
Modify `lib/research/stages/synthesizer.py` to source image alt text from `state.reasoned.analyzed_images[i].caption` (delivered by ar-2-01's Reasoner agent loop) instead of the ar-1 filename-placeholder. Preserve the ar-1 fallback behavior when Reasoner produced no analyzed_images (skipped, failed, or empty result) — fall back to `state.retrieved.image_candidates` with `img.name` as alt text.

Purpose:
- ORCH-05: Synthesizer's emitted markdown must contain inline `![desc](http://localhost:8765/...)` references where `desc` is the vision-generated caption from `ReasonerOutput.analyzed_images`. After ar-2-02 lands, `desc` is no longer a filename placeholder.
- TEST-03 (Synthesizer half): assert that a fixture `ResearchState` with a `reasoned.analyzed_images` entry whose `caption == "<MOCK_CAPTION>"` produces a `SynthesizerOutput.markdown` containing the literal substring `![<MOCK_CAPTION>](http://localhost:8765/.../5.jpg)`. This closes TEST-03 begun in ar-2-01.

Output:
- One file modified: `lib/research/stages/synthesizer.py` (signature unchanged: `async def run(query, cfg, state) -> SynthesizerOutput`).
- One new test file: `tests/unit/research/test_synthesizer_caption_embeds.py` (≥5 tests: caption path, fallback path, URL format, terminal-no-status, ar-1 regression).
- ar-1 regression suite still green; total `tests/unit/research/` count after ar-2-02 ≥ 47 (ar-1 baseline ≥35 + ar-2-01 ≥7 + this plan ≥5).

This plan does NOT touch the Reasoner, the orchestrator, the CLI, the URL format, or any non-Synthesizer file. The `_detect_language` heuristic from ar-1 remains unchanged. The degradation note_lines mechanism (the `> ❌`, `> ℹ️`, `> ⚠️` lines for failed/skipped/missing upstream stages) remains unchanged. The terminal-stage discipline (no `status` field, no try/except wrap) remains unchanged.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/ar-2-reasoner-vision-deepening/ar-2-CONTEXT.md
@.planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md
@.planning/REQUIREMENTS-Agentic-RAG-v1.md
@docs/design/agentic_rag_internal_api.md
@lib/research/types.py
@lib/research/stages/synthesizer.py
@lib/research/stages/reasoner.py
@.planning/phases/ar-2-reasoner-vision-deepening/ar-2-01-reasoner-agent-loop-PLAN.md

<interfaces>
**Synthesizer.run() signature is UNCHANGED from ar-1:**

```python
async def run(
    query: str,
    cfg: ResearchConfig,
    state: ResearchState,
) -> SynthesizerOutput:
    ...
```

**Existing ar-1 image-emission code block** (in `synthesizer.py` lines 56-58 + 89-95, current verbatim shape):

```python
# ar-1 source path
if state.retrieved is not None and state.retrieved.status == "ok":
    sources.extend(state.retrieved.chunks)
    for img in state.retrieved.image_candidates[:5]:  # cap at 5 for ar-1
        embedded_images.append(img.image_path)

# ar-1 emission path
if embedded_images:
    body += "\n\n## Retrieved Images\n\n"
    for img in embedded_images:
        body += (
            f"![{img.name}](http://localhost:8765/"
            f"{img.parent.name}/{img.name})\n"
        )
```

Note: `embedded_images` is a `list[Path]` (from the `SynthesizerOutput.embedded_images: list[Path]` contract — frozen, do NOT change shape). The ar-1 emission loop iterates `Path` objects directly, using `img.name` for alt text.

**ar-2 image-emission shape** (replacement):

```python
# ar-2 source path: prefer reasoned.analyzed_images (caption-anchored),
# fall back to retrieved.image_candidates (filename alt text — ar-1 behavior).
image_entries: list[tuple[Path, str]] = []  # (image_path, alt_text)

if state.reasoned is not None and state.reasoned.analyzed_images:
    # Caption-anchored path (ar-2 happy path)
    for img in state.reasoned.analyzed_images[:5]:  # cap at 5 (preserves ar-1 cap)
        alt_text = img.caption or img.image_path.name  # safety: caption SHOULD be non-None,
                                                       # but fall back to filename if it's None for any reason
        image_entries.append((img.image_path, alt_text))
elif state.retrieved is not None and state.retrieved.status == "ok":
    # Fallback path (Reasoner skipped/failed, OR analyzed_images is empty)
    for img in state.retrieved.image_candidates[:5]:
        image_entries.append((img.image_path, img.image_path.name))

# embedded_images for the SynthesizerOutput contract — Path-only, no captions
embedded_images = [path for path, _alt in image_entries]

# ar-2 emission path
if image_entries:
    body += "\n\n## Retrieved Images\n\n"
    for path, alt in image_entries:
        body += (
            f"![{alt}](http://localhost:8765/"
            f"{path.parent.name}/{path.name})\n"
        )
```

Key invariants:
1. The URL format is **byte-for-byte identical** to ar-1: `http://localhost:8765/<path.parent.name>/<path.name>`. Only the alt text changes.
2. The `embedded_images: list[Path]` field on `SynthesizerOutput` contains the same `Path` objects as before — only the alt-text source has changed. (Captions live in `ReasonerOutput.analyzed_images[i].caption`, NOT in `SynthesizerOutput`. The Synthesizer threads them into the markdown body string but does NOT add a new field to its output dataclass.)
3. The `[:5]` cap is preserved in BOTH paths — preserves the ar-1 image-count behavior under both branches.
4. The `_detect_language` helper, the title/body templates, the degradation-note-lines block, and the confidence calculation are all UNCHANGED from ar-1.

**Sources collection** (also touched, minor):

The ar-1 `sources` list collects from `state.retrieved.chunks`. ar-2 should ALSO collect from `state.reasoned.additional_chunks` if the Reasoner produced any (otherwise the inline KG chunks the Reasoner found via `kg_search` tool calls would be invisible to the Synthesizer's `sources` list). Add:

```python
if state.reasoned is not None and state.reasoned.additional_chunks:
    sources.extend(state.reasoned.additional_chunks)
```

This is a small but principled add — the Reasoner's `additional_chunks` are conceptually KG sources, identical in shape to `state.retrieved.chunks`. The ar-2 CONTEXT.md does not explicitly mandate this, but it's the natural complement to caption-anchoring (without it, `result.sources` would silently lose the Reasoner's KG-tool findings). Document the choice in the SUMMARY.md.

**Confidence calculation:**

ar-1: `0.5 if state.retrieved is ok else 0.0`. Preserve this. (Real confidence — Verifier's `confidence: float` — lands in ar-3. Synthesizer mapping into the final result confidence is also ar-3+.)

**TEST-03 Synthesizer-half (this plan):**

```python
@pytest.mark.asyncio
async def test_synthesizer_uses_reasoned_caption(tmp_path):
    """ORCH-05 + TEST-03: caption from analyzed_images flows into markdown alt text."""
    image_path = tmp_path / "deadbeef00" / "5.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"")

    state = ResearchState(
        query="test query",
        timestamp_start=0.0,
        retrieved=RetrieverOutput(
            chunks=[Source(kind="kg_chunk", uri="x", snippet="seed")],
            image_candidates=[],
        ),
        reasoned=ReasonerOutput(
            inferences_md="(inferences)",
            additional_chunks=[],
            analyzed_images=[RetrievedImage(
                article_hash="deadbeef00",
                image_path=image_path,
                caption="<MOCK_CAPTION>",
            )],
            iter_count=2,
            status="ok",
        ),
        verified=None,
        web_baseline=None,
    )

    cfg = _make_minimal_cfg()
    result = await run_synthesizer("test query", cfg, state)

    assert "![<MOCK_CAPTION>](http://localhost:8765/deadbeef00/5.jpg)" in result.markdown


@pytest.mark.asyncio
async def test_synthesizer_falls_back_to_filename_when_reasoned_none(tmp_path):
    """ar-1 regression guard: state.reasoned=None → alt text falls back to img.name."""
    image_path = tmp_path / "abc1234567" / "3.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"")

    state = ResearchState(
        query="test",
        timestamp_start=0.0,
        retrieved=RetrieverOutput(
            chunks=[Source(kind="kg_chunk", uri="x", snippet="text")],
            image_candidates=[RetrievedImage(article_hash="abc1234567", image_path=image_path)],
        ),
        reasoned=None,  # Reasoner never ran
        verified=None,
        web_baseline=None,
    )

    cfg = _make_minimal_cfg()
    result = await run_synthesizer("test", cfg, state)

    assert "![3.jpg](http://localhost:8765/abc1234567/3.jpg)" in result.markdown


@pytest.mark.asyncio
async def test_synthesizer_falls_back_when_analyzed_images_empty(tmp_path):
    """Reasoner ran but found no images → fall back to retrieved.image_candidates."""
    image_path = tmp_path / "abc1234567" / "3.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"")

    state = ResearchState(
        query="test",
        timestamp_start=0.0,
        retrieved=RetrieverOutput(
            chunks=[Source(kind="kg_chunk", uri="x", snippet="text")],
            image_candidates=[RetrievedImage(article_hash="abc1234567", image_path=image_path)],
        ),
        reasoned=ReasonerOutput(
            inferences_md="reasoner ran but no vision_analyze calls",
            additional_chunks=[],
            analyzed_images=[],  # empty — Reasoner produced no captions
            iter_count=1,
            status="ok",
        ),
        verified=None,
        web_baseline=None,
    )

    cfg = _make_minimal_cfg()
    result = await run_synthesizer("test", cfg, state)

    assert "![3.jpg](http://localhost:8765/abc1234567/3.jpg)" in result.markdown


@pytest.mark.asyncio
async def test_synthesizer_url_format_unchanged(tmp_path):
    """URL format is byte-for-byte identical to ar-1 in both caption + fallback paths."""
    # Two parallel state fixtures: one caption-path, one fallback-path. Assert the URL
    # body (everything between `](` and `)`) is identical for matching image_path.
    ...


@pytest.mark.asyncio
async def test_synthesizer_no_status_field():
    """Axis 8 invariant: SynthesizerOutput has no status field even after ar-2 changes."""
    import dataclasses
    from lib.research.types import SynthesizerOutput
    field_names = {f.name for f in dataclasses.fields(SynthesizerOutput)}
    assert "status" not in field_names
    assert "reason" not in field_names


def _make_minimal_cfg() -> ResearchConfig:
    return ResearchConfig(
        rag_working_dir=Path("/tmp/_test_rag"),
        llm_complete=lambda *a, **kw: None,
        embedding_func=lambda *a, **kw: None,
        vision_cascade=object(),
        web_search=lambda q: [],
    )
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Replace synthesizer image-emission block with caption-anchored path + fallback</name>
  <read_first>
    - lib/research/stages/synthesizer.py (current ar-1 body — preserve _detect_language, title/body templates, degradation notes; replace ONLY the image-source-and-emission blocks)
    - lib/research/types.py (SynthesizerOutput shape — DO NOT modify; embedded_images stays list[Path])
    - lib/research/stages/reasoner.py (ar-2-01 just-landed body — confirms ReasonerOutput.analyzed_images shape; each entry is RetrievedImage with .caption populated by _vision_analyze_tool)
    - .planning/phases/ar-2-reasoner-vision-deepening/ar-2-CONTEXT.md § "ORCH-05: Synthesizer caption-anchored image embeds"
  </read_first>
  <files>lib/research/stages/synthesizer.py</files>
  <behavior>
    Synthesizer body MUST satisfy these observable behaviors (verified by Task 2 tests):
    - When `state.reasoned is not None AND state.reasoned.analyzed_images` is non-empty: each emitted image markdown reference uses `img.caption` (or `img.image_path.name` if caption is unexpectedly None) as alt text.
    - When `state.reasoned is None` OR `state.reasoned.analyzed_images` is empty AND `state.retrieved.status == "ok"`: each emitted image markdown reference uses `img.image_path.name` (filename) as alt text — ar-1 behavior preserved.
    - URL format is `http://localhost:8765/<path.parent.name>/<path.name>` — byte-for-byte unchanged from ar-1.
    - `embedded_images: list[Path]` field on `SynthesizerOutput` contains the resolved image_paths from whichever branch ran (caption-path OR fallback-path).
    - Image cap of 5 is preserved in BOTH branches.
    - `state.reasoned.additional_chunks` (if non-empty) extends the `sources: list[Source]` field on output — small principled add to surface Reasoner's KG findings.
    - `_detect_language`, the zh/en title/body templates, the degradation note_lines block, and the confidence calculation are UNCHANGED from ar-1.
    - Synthesizer remains terminal: no `status` field on `SynthesizerOutput`, no try/except wrap of the orchestrator-visible body.
  </behavior>
  <action>
    1. Open `lib/research/stages/synthesizer.py`. Update the module docstring header — change "ar-1 status: minimal markdown synthesis using a CJK-ratio language heuristic" to "ar-2 status: caption-anchored image embeds (alt text sourced from `state.reasoned.analyzed_images[i].caption`); CJK-ratio language heuristic preserved (Axis 10 ar-1 scope, swapped for LLM-driven detection in ar-4)."

    2. Locate the existing ar-1 source-collection block (lines ~55-58):
       ```python
       if state.retrieved is not None and state.retrieved.status == "ok":
           sources.extend(state.retrieved.chunks)
           for img in state.retrieved.image_candidates[:5]:  # cap at 5 for ar-1
               embedded_images.append(img.image_path)
       ```
       Replace with the ar-2 dual-source block per `<interfaces>`:
       ```python
       # ar-2 source collection: KG chunks always, Reasoner's additional_chunks if any.
       if state.retrieved is not None and state.retrieved.status == "ok":
           sources.extend(state.retrieved.chunks)
       if state.reasoned is not None and state.reasoned.additional_chunks:
           sources.extend(state.reasoned.additional_chunks)

       # ar-2 image collection: prefer reasoned.analyzed_images (caption-anchored),
       # fall back to retrieved.image_candidates (filename alt text — ar-1 behavior).
       image_entries: list[tuple[Path, str]] = []
       if state.reasoned is not None and state.reasoned.analyzed_images:
           for img in state.reasoned.analyzed_images[:5]:
               alt_text = img.caption or img.image_path.name
               image_entries.append((img.image_path, alt_text))
       elif state.retrieved is not None and state.retrieved.status == "ok":
           for img in state.retrieved.image_candidates[:5]:
               image_entries.append((img.image_path, img.image_path.name))

       embedded_images = [path for path, _alt in image_entries]
       ```

    3. Locate the ar-1 image-emission block (lines ~89-95):
       ```python
       if embedded_images:
           body += "\n\n## Retrieved Images\n\n"
           for img in embedded_images:
               body += (
                   f"![{img.name}](http://localhost:8765/"
                   f"{img.parent.name}/{img.name})\n"
               )
       ```
       Replace with the ar-2 form using `image_entries`:
       ```python
       if image_entries:
           body += "\n\n## Retrieved Images\n\n"
           for path, alt in image_entries:
               body += (
                   f"![{alt}](http://localhost:8765/"
                   f"{path.parent.name}/{path.name})\n"
               )
       ```

    4. Confirm UNCHANGED:
       - `_detect_language()` function body and 0.3 threshold.
       - The `lang = _detect_language(query)` line and zh/en title/body branching.
       - The degradation note_lines block (the `for name, st in (...)` loop).
       - The confidence calculation: `0.5 if (state.retrieved is not None and state.retrieved.status == "ok") else 0.0`.
       - The `return SynthesizerOutput(...)` at end with the same 5 fields.
       - NO try/except wraps the orchestrator-visible body (terminal-stage discipline).
       - NO `status` field added to SynthesizerOutput (Axis 8).

    5. Confirm CONTRACT-02 still clean: zero `~/.hermes` / `omonigraph-vault` literals in the file. Image paths flow exclusively from `state.reasoned.analyzed_images[*].image_path` or `state.retrieved.image_candidates[*].image_path` — both are populated upstream from `cfg.rag_working_dir`-derived paths.

    6. Run the smoke import: `venv/Scripts/python.exe -c "from lib.research.stages.synthesizer import run, _detect_language; print('OK')"` — both must still be importable.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -c "from lib.research.stages.synthesizer import run, _detect_language; print('synthesizer import ok')" &amp;&amp; bash scripts/check_contract.sh</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/stages/synthesizer.py` imports without error.
    - `_detect_language` is still importable as a module-level function.
    - `bash scripts/check_contract.sh` exits 0.
    - File contains the literal string `state.reasoned.analyzed_images` (caption-path proof).
    - File contains the literal string `state.retrieved.image_candidates` (fallback-path proof).
    - File contains the literal substring `f"![{alt}](http://localhost:8765/"` (or equivalent f-string with `{alt}` as the alt-text variable name) — proves caption variable threads into the URL.
    - File does NOT contain a `status=` field assignment in the `return SynthesizerOutput(...)` call (terminal-stage invariant).
    - File does NOT contain `try:` / `except` around the entire run() body (terminal-stage discipline; per-step `or ""` / `is None` guards are fine).
  </acceptance_criteria>
  <done>synthesizer.py emits caption-anchored image markdown when reasoned.analyzed_images is non-empty; falls back to filename alt text otherwise; ar-1 mechanics elsewhere preserved.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Write TEST-03 Synthesizer-half mock test suite + verify ar-1 + ar-2-01 regression suite still green</name>
  <read_first>
    - tests/unit/research/test_stages_stubs.py (ar-1 synthesizer test patterns — Tests 11-20; SOME may need surgical updates if they tested image-emission with the ar-1 filename-only alt text)
    - tests/unit/research/test_orchestrator.py (orchestrator e2e patterns — may need updates if Test 2 asserted on the exact markdown shape including alt text)
    - lib/research/stages/synthesizer.py (just-modified body)
    - lib/research/types.py (RetrievedImage with caption field, ReasonerOutput, ResearchState)
    - .planning/phases/ar-2-reasoner-vision-deepening/ar-2-CONTEXT.md § "TEST-03: Reasoner loop mock test"
  </read_first>
  <files>tests/unit/research/test_synthesizer_caption_embeds.py</files>
  <behavior>
    Test file `test_synthesizer_caption_embeds.py` covers:
    - Test 1 `test_synthesizer_uses_reasoned_caption`: state with `reasoned.analyzed_images=[RetrievedImage(article_hash="deadbeef00", image_path=tmp_path/"deadbeef00"/"5.jpg", caption="<MOCK_CAPTION>")]` produces markdown containing literal substring `![<MOCK_CAPTION>](http://localhost:8765/deadbeef00/5.jpg)`. (TEST-03 Synthesizer half — closes the data-flow assertion begun in ar-2-01 Test 1.)
    - Test 2 `test_synthesizer_falls_back_to_filename_when_reasoned_none`: state with `reasoned=None` and non-empty `retrieved.image_candidates` produces markdown containing literal substring `![3.jpg](http://localhost:8765/abc1234567/3.jpg)`. (ar-1 regression guard.)
    - Test 3 `test_synthesizer_falls_back_when_analyzed_images_empty`: state with `reasoned.analyzed_images=[]` (empty list) AND `retrieved.image_candidates` non-empty produces fallback-path markdown — same shape as Test 2.
    - Test 4 `test_synthesizer_url_format_unchanged`: assert URL body (path.parent.name + "/" + path.name) is byte-for-byte identical between caption-path and fallback-path for the same image_path.
    - Test 5 `test_synthesizer_no_status_field`: `dataclasses.fields(SynthesizerOutput)` does NOT contain a field named `status` or `reason`. (Axis 8 invariant.)
    - Test 6 `test_synthesizer_caption_path_caps_at_5`: state with `analyzed_images` of 8 entries → markdown contains exactly 5 image markdown references (cap preserved).
    - Test 7 `test_synthesizer_caption_none_falls_back_to_filename`: edge case — state with `analyzed_images=[RetrievedImage(..., caption=None)]` (caption explicitly None) → alt text falls back to `img.image_path.name` (the `or img.image_path.name` defensive fallback in the impl).
    - Test 8 `test_synthesizer_reasoned_additional_chunks_in_sources`: state with `reasoned.additional_chunks=[Source(kind="kg_chunk", uri="x", snippet="from reasoner kg_search")]` → `result.sources` contains that Source (proves the ar-2 `sources.extend(state.reasoned.additional_chunks)` add).
  </behavior>
  <action>
    1. Create `tests/unit/research/test_synthesizer_caption_embeds.py`. Imports:
       ```python
       import dataclasses
       from pathlib import Path

       import pytest

       from lib.research.stages.synthesizer import run as run_synthesizer
       from lib.research.types import (
           ReasonerOutput, ResearchConfig, ResearchState, RetrievedImage,
           RetrieverOutput, Source, SynthesizerOutput,
       )
       ```

    2. Implement `_make_minimal_cfg()` test helper per `<interfaces>` block.

    3. Implement Tests 1-8 above. All tests use real `ResearchState` instances built directly (no mocking of state — only mocking of `cfg`). For tests 1, 2, 3, 6, 7: use `tmp_path` to create real article-hash dirs + jpg files (mirrors ar-1 retriever test pattern).

    4. Test 1 specifically asserts the literal substring `"![<MOCK_CAPTION>](http://localhost:8765/deadbeef00/5.jpg)"` is in `result.markdown`. This is the TEST-03 hard requirement.

    5. Test 4 (URL format unchanged): build two parallel states (one with caption, one without) for the SAME image_path. Extract the URL body from each markdown via regex `\[.*?\]\((http://localhost:8765/[^\)]+)\)`, assert both URLs are identical.

    6. Surgical updates to ar-1 tests (if any are needed):
       - Check `tests/unit/research/test_stages_stubs.py` Tests 15-20 (synthesizer tests). Most should still pass — the ar-1 tests asserted on degradation notes, language detection, image cap of 5, and confidence — none of which changed. If Test 17 ("retrieved.image_candidates of 7 items → embedded_images is exactly 5") still passes, no edit needed. (It SHOULD pass: with `reasoned=None`, the fallback path runs, and the cap of 5 is still applied.) If it fails, update the test setup to set `reasoned=None` explicitly.
       - Check `tests/unit/research/test_orchestrator.py` Test 2 ("With mocked KG response... result.markdown contains the response text"). Should still pass — markdown still contains the chunk snippet. No edit anticipated.
       - If any ar-1 test asserts on the exact alt-text being a filename (e.g., `assert "![3.jpg](" in markdown`), verify whether the test explicitly sets `reasoned=None`. If so, the test still passes (fallback path). If the test is ambiguous, update to set `reasoned=None` for clarity.

    7. Run the new test file in isolation FIRST: `venv/Scripts/python.exe -m pytest tests/unit/research/test_synthesizer_caption_embeds.py -v`. All 8 must pass.

    8. Then run the full ar-1 + ar-2-01 regression suite: `venv/Scripts/python.exe -m pytest tests/unit/research/ -v`. Total ≥ 47 (ar-1 ≥35 + ar-2-01 ≥7 + this plan ≥5).

    9. If any ar-1 or ar-2-01 test fails (regression), STOP and analyze. The most likely failure mode is an ar-1 synthesizer test that hardcoded `![X.jpg](...)` alt text without setting `reasoned=None` — update to set `reasoned=None` explicitly (one-line edit).
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/test_synthesizer_caption_embeds.py -v &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/ -v</automated>
  </verify>
  <acceptance_criteria>
    - `tests/unit/research/test_synthesizer_caption_embeds.py` exists with ≥8 tests; all pass.
    - Full `tests/unit/research/` suite has ≥47 tests passing (ar-1 ≥35 + ar-2-01 ≥7 + this plan ≥5).
    - Test 1 specifically asserts the literal substring `![<MOCK_CAPTION>](http://localhost:8765/deadbeef00/5.jpg)` appears in `result.markdown` (TEST-03 hard requirement).
    - Test 5 specifically asserts `dataclasses.fields(SynthesizerOutput)` contains no field named `status` AND no field named `reason` (Axis 8 invariant).
    - Test 4 specifically asserts URL bodies are identical between caption and fallback paths (URL format invariance proof).
    - Any ar-1 test edits are SURGICAL — `git diff tests/unit/research/test_stages_stubs.py` shows ≤5 lines changed total; `git diff tests/unit/research/test_orchestrator.py` shows ≤3 lines changed total.
  </acceptance_criteria>
  <done>≥8 new Synthesizer caption-embed tests pass; full ar-1 + ar-2-01 regression suite still green (≥47 total tests); ar-1 synthesizer-test surgical edits documented in SUMMARY.md.</done>
</task>

</tasks>

<verification>
- Both tasks pass automated checks.
- `cd c:/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python.exe -m pytest tests/unit/research/ -v` exits 0 with ≥47 tests passing.
- CONTRACT-01 grep re-check (must return zero forbidden hits — exactly 2 allowed `from omnigraph_search.query import search` lines):
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  hits=$(grep -rE "from omnigraph_search" lib/research/ \
    --include='*.py' \
    | grep -vE "from omnigraph_search\.query " \
    | grep -vE "from omnigraph_search\.query$" \
    | grep -vE "import omnigraph_search\.query" \
    || true) && \
  if [ -n "$hits" ]; then echo "CONTRACT-01 violation:"; echo "$hits"; exit 1; fi
  ```
  Expected: 0 hits.
- CONTRACT-02 grep re-check:
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' \
    | grep -vE "config\.py|README\.md|^Binary"
  ```
  Expected: 0 hits.
- `bash scripts/check_contract.sh` exits 0.
- Smoke-check the synthesizer import + dataclass shape:
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  venv/Scripts/python.exe -c "from lib.research.stages.synthesizer import run, _detect_language; from lib.research.types import SynthesizerOutput; import dataclasses; assert 'status' not in {f.name for f in dataclasses.fields(SynthesizerOutput)}; print('Axis 8 invariant ok')"
  ```

ar-2 Layer 2 smoke test (manual, documented step — same as ar-2-01):
After ar-2-03 lands, the upgraded smoke command becomes available; this plan does NOT exercise it (CLI flags don't exist yet). Layer 2 smoke is the responsibility of ar-2-03.

End-to-end programmatic smoke (this plan's contribution to verification):
```bash
cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
venv/Scripts/python.exe -c "
import asyncio
from pathlib import Path
from lib.research.stages.synthesizer import run as run_synthesizer
from lib.research.types import ResearchConfig, ResearchState, ReasonerOutput, RetrievedImage, RetrieverOutput, Source

cfg = ResearchConfig(
    rag_working_dir=Path('/tmp/_smoke_rag'),
    llm_complete=lambda *a, **kw: None,
    embedding_func=lambda *a, **kw: None,
    vision_cascade=object(),
    web_search=lambda q: [],
)
state = ResearchState(
    query='smoke',
    timestamp_start=0.0,
    retrieved=RetrieverOutput(chunks=[Source(kind='kg_chunk', uri='x', snippet='hello')], image_candidates=[]),
    reasoned=ReasonerOutput(
        inferences_md='', additional_chunks=[],
        analyzed_images=[RetrievedImage(article_hash='deadbeef00', image_path=Path('/tmp/deadbeef00/5.jpg'), caption='SMOKE_CAP')],
        iter_count=1, status='ok',
    ),
    verified=None, web_baseline=None,
)
r = asyncio.run(run_synthesizer('smoke', cfg, state))
assert '![SMOKE_CAP](http://localhost:8765/deadbeef00/5.jpg)' in r.markdown
print('synth smoke ok')
"
```
</verification>

<success_criteria>
- ROADMAP § "Phase ar-2: Reasoner + vision deepening" Success Criterion #2: Synthesizer's emitted markdown contains inline `![desc](http://localhost:8765/...)` image references where `desc` is anchored to a vision-generated caption from `ReasonerOutput.analyzed_images`, not a placeholder. ✓ delivered by Task 1; verified by Task 2 Test 1.
- ROADMAP Success Criterion #5 (Synthesizer half): the data-flow test asserts the caption from `analyzed_images` is embedded in Synthesizer's output. ✓ delivered by Task 2 Test 1; together with ar-2-01 Test 1, this closes TEST-03's full data-flow assertion (Reasoner → state.reasoned → Synthesizer prompt input).
- REQ ORCH-05 (Synthesizer caption-anchored image embeds) ✓ delivered.
- REQ TEST-03 (Synthesizer-half) ✓ delivered.
- ar-1 fallback path still works — `state.reasoned is None` → filename alt text (Axis 3 best-effort preserved).
- Synthesizer remains terminal — no `status` field added (Axis 8 invariant preserved).
- CONTRACT-01 + CONTRACT-02 still clean.
</success_criteria>

<output>
After completion, create `.planning/phases/ar-2-reasoner-vision-deepening/ar-2-02-SUMMARY.md` documenting:
- Files modified + LOC count for each (rough proxy for plan-size sanity).
- Test count: total in `tests/unit/research/test_synthesizer_caption_embeds.py`, total in full `tests/unit/research/` suite, pass/fail summary.
- CONTRACT-01 + CONTRACT-02 grep results (paste raw output — should be 0 forbidden hits).
- Caption-path verification: a Test 1 markdown excerpt showing the literal `![<MOCK_CAPTION>](http://localhost:8765/deadbeef00/5.jpg)` substring.
- Fallback-path verification: a Test 2 markdown excerpt showing `![3.jpg](http://localhost:8765/abc1234567/3.jpg)`.
- ar-1 surgical test edits: list each test edited in `test_stages_stubs.py` / `test_orchestrator.py` with line-count delta and one-line rationale (or "no edits needed" if every ar-1 test passed unchanged).
- The principled add (sources extended with `state.reasoned.additional_chunks`) — note in SUMMARY that this was an in-plan judgment call, with rationale.
- Programmatic smoke output (`asyncio.run(run_synthesizer(...))` returns markdown containing `SMOKE_CAP`).
- Any deviations from plan (with one-line rationale).
</output>

> Operator note: ar-3 执行前需 TAVILY_API_KEY + BRAVE_SEARCH_API_KEY 注入 ~/.hermes/.env
