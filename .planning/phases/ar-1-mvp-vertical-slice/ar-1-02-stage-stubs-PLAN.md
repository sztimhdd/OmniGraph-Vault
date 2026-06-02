---
phase: ar-1-mvp-vertical-slice
plan: 02
type: execute
wave: 2
depends_on:
  - ar-1-01
files_modified:
  - lib/research/stages/web_baseline.py
  - lib/research/stages/retriever.py
  - lib/research/stages/reasoner.py
  - lib/research/stages/verifier.py
  - lib/research/stages/synthesizer.py
  - lib/research/orchestrator.py
  - tests/unit/research/test_stages_stubs.py
  - tests/unit/research/test_orchestrator.py
autonomous: true
requirements:
  - ORCH-01
  - ORCH-02
  - ORCH-06
  - ORCH-07
  - ORCH-09

must_haves:
  truths:
    - "All 5 stages implement `async def run(query, cfg) -> <StageOutput>` and never raise — exceptions caught and converted to status='failed' + reason=str(e)"
    - "Pipeline order is strict sequential WebBaseline → Retriever → Reasoner → Verifier → Synthesizer (Axis 1)"
    - "Retriever calls `omnigraph_search.query.search(query_text, mode='hybrid')` directly — only allowed KG-side import (CONTRACT-01)"
    - "Synthesizer is terminal: NO status field on output; degradation surfaces via `note_lines` (Axis 8)"
    - "Synthesizer language detection uses CJK char ratio ≥ 0.3 heuristic (Axis 10 ar-1 scope)"
    - "ResearchState mutates one field at a time as the pipeline advances; orchestrator never raises out (best-effort failure handling, Axis 3)"
  artifacts:
    - path: "lib/research/stages/web_baseline.py"
      provides: "ar-1 stub: status='skipped' if web_search returns [] or callable is sentinel"
      contains: "async def run(query, cfg) -> WebBaseline"
    - path: "lib/research/stages/retriever.py"
      provides: "Calls omnigraph_search.query.search; globs RetrievedImage candidates from BASE_IMAGE_DIR"
      contains: "async def run(query, cfg) -> RetrieverOutput"
    - path: "lib/research/stages/reasoner.py"
      provides: "ar-1 stub: status='skipped', iter_count=0, additional_chunks=[], analyzed_images=[]"
      contains: "async def run(query, cfg, retrieved) -> ReasonerOutput"
    - path: "lib/research/stages/verifier.py"
      provides: "ar-1 stub: status='skipped', iter_count=0, confidence=0.0, external_citations=[]"
      contains: "async def run(query, cfg, reasoned) -> VerifierOutput"
    - path: "lib/research/stages/synthesizer.py"
      provides: "Minimal markdown synth + CJK language detection + degradation note_lines"
      contains: "async def run(query, cfg, state) -> SynthesizerOutput"
    - path: "lib/research/orchestrator.py"
      provides: "Wired research() body — calls all 5 stages in order, mutates ResearchState"
  key_links:
    - from: "lib/research/orchestrator.py"
      to: "lib.research.stages.{web_baseline,retriever,reasoner,verifier,synthesizer}"
      via: "from .stages.<name> import run as run_<name>"
      pattern: "from \\.stages\\.\\w+ import run"
    - from: "lib/research/stages/retriever.py"
      to: "omnigraph_search.query.search"
      via: "from omnigraph_search.query import search"
      pattern: "from omnigraph_search\\.query import search"
---

<objective>
Implement all 5 stages as ar-1-scoped modules + wire them into the orchestrator. WebBaseline / Reasoner / Verifier are deterministic stubs that return `status="skipped"` with a clear reason. Retriever wires the live `omnigraph_search.query.search()` call (real KG retrieval works in ar-1) and globs candidate images from `BASE_IMAGE_DIR`. Synthesizer emits a minimal markdown answer using a CJK heuristic for language detection (Axis 10 ar-1 scope) and appends degradation notes for any skipped/failed upstream stage.

Purpose: After this plan, `await research(query, cfg)` returns a valid `ResearchResult` end-to-end without raising. The full pipeline shape is locked; ar-2/3/4 swap in real LLM-driven bodies for the stub stages.

Output: 5 stage modules + filled-in orchestrator body + 2 test files (≥10 stage stub tests, ≥3 orchestrator integration tests).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md
@docs/design/agentic_rag_internal_api.md
@.planning/REQUIREMENTS-Agentic-RAG-v1.md
@lib/research/types.py
@lib/research/config.py
@lib/research/orchestrator.py
@omnigraph_search/query.py

<interfaces>
**Stage signatures (uniform shape — every stage is `async def run(...)`):**

```python
# lib/research/stages/web_baseline.py
async def run(query: str, cfg: ResearchConfig) -> WebBaseline: ...

# lib/research/stages/retriever.py
async def run(query: str, cfg: ResearchConfig) -> RetrieverOutput: ...

# lib/research/stages/reasoner.py
async def run(query: str, cfg: ResearchConfig, retrieved: RetrieverOutput) -> ReasonerOutput: ...

# lib/research/stages/verifier.py
async def run(query: str, cfg: ResearchConfig, reasoned: ReasonerOutput) -> VerifierOutput: ...

# lib/research/stages/synthesizer.py
async def run(query: str, cfg: ResearchConfig, state: ResearchState) -> SynthesizerOutput: ...
```

**Best-effort failure pattern (Axis 3 — every stage):**

```python
async def run(query, cfg, *args) -> StageOutput:
    try:
        # real work
        return StageOutput(...)
    except Exception as e:
        return StageOutput(
            # all-defaults except:
            status="failed",
            reason=str(e),
        )
```

**Synthesizer is terminal — NO status field, NO try/except wraps the whole thing.** Synthesizer instead appends a degradation note_line for any upstream stage with `status != "ok"` (or `note_lines.extend(...)` for a sub-step that fails internally).

**WebBaseline ar-1 stub** (status='skipped' default since web_search is the `_skipped_web_search` callable from config.py):

```python
async def run(query, cfg) -> WebBaseline:
    snippets = []
    queries_used = [query]
    try:
        results = cfg.web_search(query)  # _skipped_web_search returns []
    except Exception as e:
        return WebBaseline(queries_used=queries_used, snippets=[], status="failed", reason=str(e))

    if not results:
        return WebBaseline(
            queries_used=queries_used,
            snippets=[],
            status="skipped",
            reason="web_search returned [] (TAVILY_API_KEY unset — ar-1 stub mode)",
        )

    # Live results path — ar-3 lands real Tavily; ar-1 falls through if web_search returns dicts
    for r in results:
        snippets.append(Source(
            kind="web",
            uri=r.get("url", ""),
            title=r.get("title"),
            snippet=r.get("content"),
        ))
    return WebBaseline(queries_used=queries_used, snippets=snippets)
```

**Retriever ar-1 — live KG call + image globbing:**

```python
import re
from pathlib import Path
from omnigraph_search.query import search as kg_search
from ..types import RetrieverOutput, RetrievedImage, Source

ARTICLE_HASH_RE = re.compile(r"\b[0-9a-f]{10}\b")

async def run(query, cfg) -> RetrieverOutput:
    try:
        kg_text = await kg_search(query, mode="hybrid")
    except Exception as e:
        return RetrieverOutput(chunks=[], image_candidates=[], status="failed", reason=str(e))

    if not kg_text or not kg_text.strip():
        return RetrieverOutput(
            chunks=[], image_candidates=[],
            status="skipped",
            reason="omnigraph_search.query.search returned empty",
        )

    # Single chunk wrapping the full KG response — Reasoner in ar-2 will replace
    # with proper chunk-by-chunk extraction.
    chunks = [Source(kind="kg_chunk", uri="omnigraph_search.query.search", snippet=kg_text)]

    # Glob image candidates from BASE_IMAGE_DIR for any 10-char hash mentioned in kg_text
    base_image_dir = cfg.rag_working_dir.parent / "images"  # rag_working_dir = base_dir/lightrag_storage
    image_candidates: list[RetrievedImage] = []
    if base_image_dir.exists():
        for hash_match in set(ARTICLE_HASH_RE.findall(kg_text)):
            article_dir = base_image_dir / hash_match
            if article_dir.is_dir():
                for img in sorted(article_dir.glob("*.jpg")):
                    image_candidates.append(RetrievedImage(article_hash=hash_match, image_path=img))

    return RetrieverOutput(chunks=chunks, image_candidates=image_candidates)
```

**Reasoner ar-1 stub:**

```python
async def run(query, cfg, retrieved) -> ReasonerOutput:
    return ReasonerOutput(
        inferences_md="",
        additional_chunks=[],
        analyzed_images=[],
        iter_count=0,
        status="skipped",
        reason="ar-1 stub — agent loop lands in ar-2",
    )
```

**Verifier ar-1 stub:**

```python
async def run(query, cfg, reasoned) -> VerifierOutput:
    return VerifierOutput(
        fact_check_summary_md="",
        confidence=0.0,
        external_citations=[],
        discrepancies=[],
        iter_count=0,
        status="skipped",
        reason="ar-1 stub — verifier loop lands in ar-3",
    )
```

**Synthesizer ar-1 — minimal markdown + CJK heuristic + degradation notes:**

```python
def _detect_language(query: str) -> str:
    """CJK char ratio ≥ 0.3 → 'zh'; else 'en' (Axis 10 ar-1 heuristic)."""
    if not query:
        return "en"
    cjk = sum(1 for c in query if "一" <= c <= "鿿")
    return "zh" if cjk / len(query) >= 0.3 else "en"


async def run(query, cfg, state) -> SynthesizerOutput:
    lang = _detect_language(query)
    note_lines: list[str] = []
    sources: list[Source] = []
    embedded_images: list[Path] = []

    # Collect sources from upstream
    if state.retrieved and state.retrieved.status == "ok":
        sources.extend(state.retrieved.chunks)
        for img in state.retrieved.image_candidates[:5]:  # cap at 5 for ar-1
            embedded_images.append(img.image_path)

    # Degradation notes for skipped/failed stages
    for name, st in [
        ("WebBaseline", state.web_baseline),
        ("Retriever", state.retrieved),
        ("Reasoner", state.reasoned),
        ("Verifier", state.verified),
    ]:
        if st is None:
            note_lines.append(f"> ⚠️ {name} did not run.")
        elif st.status != "ok":
            emoji = "ℹ️" if st.status == "skipped" else "❌"
            note_lines.append(f"> {emoji} {name} {st.status}: {st.reason or '(no reason)'}")

    # Minimal markdown body (real LLM synthesis lands in ar-2)
    if lang == "zh":
        title = f"# 关于「{query}」的研究答复"
        body = f"\n## 知识图谱检索结果\n\n"
    else:
        title = f"# Research Answer: {query}"
        body = f"\n## Knowledge Graph Retrieval\n\n"

    if state.retrieved and state.retrieved.chunks:
        body += state.retrieved.chunks[0].snippet or "(empty)"
    else:
        body += "(no chunks retrieved)\n"

    # Inline images
    if embedded_images:
        body += "\n\n## Retrieved Images\n\n"
        for img in embedded_images:
            body += f"![{img.name}](http://localhost:8765/{img.parent.name}/{img.name})\n"

    # Append degradation notes
    if note_lines:
        body += "\n\n---\n\n" + "\n".join(note_lines) + "\n"

    markdown = title + body
    confidence = 0.5 if (state.retrieved and state.retrieved.status == "ok") else 0.0

    return SynthesizerOutput(
        markdown=markdown,
        confidence=confidence,
        sources=sources,
        embedded_images=embedded_images,
        note_lines=note_lines,
    )
```

**Orchestrator wired body (replaces NotImplementedError from ar-1-01):**

```python
async def research(query: str, config: ResearchConfig | None = None) -> ResearchResult:
    cfg = config if config is not None else from_env()
    state = ResearchState(query=query, timestamp_start=time.time())

    from .stages.web_baseline import run as run_web_baseline
    from .stages.retriever import run as run_retriever
    from .stages.reasoner import run as run_reasoner
    from .stages.verifier import run as run_verifier
    from .stages.synthesizer import run as run_synthesizer

    state.web_baseline = await run_web_baseline(query, cfg)
    state.retrieved = await run_retriever(query, cfg)
    state.reasoned = await run_reasoner(query, cfg, state.retrieved)
    state.verified = await run_verifier(query, cfg, state.reasoned)
    state.synthesized = await run_synthesizer(query, cfg, state)

    return ResearchResult(
        markdown=state.synthesized.markdown,
        confidence=state.synthesized.confidence,
        sources=state.synthesized.sources,
        images_embedded=state.synthesized.embedded_images,
        state=state,
    )
```

Note: `research()` itself does NOT try/except — every stage is best-effort internally, so the orchestrator never sees a raise. If an unexpected exception still escapes, let it propagate (it's a real bug, not a stage degradation).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement 4 stub stages (web_baseline, reasoner, verifier) + retriever live KG call</name>
  <read_first>
    - lib/research/types.py (StageOutput shapes)
    - lib/research/config.py (ResearchConfig fields)
    - omnigraph_search/query.py (search() signature confirmed at line 35)
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md § "Module layout"
  </read_first>
  <files>lib/research/stages/web_baseline.py, lib/research/stages/retriever.py, lib/research/stages/reasoner.py, lib/research/stages/verifier.py, tests/unit/research/test_stages_stubs.py</files>
  <behavior>
    Test file `test_stages_stubs.py` covers 4 stages (synthesizer in next task):
    - Test 1: web_baseline with `cfg.web_search` returning [] → `status="skipped"`, `reason` mentions TAVILY
    - Test 2: web_baseline with `cfg.web_search` raising → `status="failed"`, `reason=str(exception)`
    - Test 3: web_baseline with `cfg.web_search` returning [{"url":"http://x","title":"t","content":"c"}] → `status="ok"`, len(snippets)=1, snippets[0].kind=="web"
    - Test 4: retriever with mocked `omnigraph_search.query.search` returning "" → `status="skipped"`, reason mentions empty
    - Test 5: retriever with mocked search raising → `status="failed"`, reason=str(e)
    - Test 6: retriever with mocked search returning text containing two 10-char hex hashes; tmp_path BASE_IMAGE_DIR has matching subdirs with `1.jpg`/`2.jpg` → image_candidates len ≥ 2
    - Test 7: retriever with no BASE_IMAGE_DIR (path doesn't exist) → returns ok with empty image_candidates (no raise)
    - Test 8: reasoner stub → `status="skipped"`, `iter_count=0`, `additional_chunks=[]`, `analyzed_images=[]`, reason mentions ar-2
    - Test 9: verifier stub → `status="skipped"`, `iter_count=0`, `confidence=0.0`, `external_citations=[]`, `discrepancies=[]`, reason mentions ar-3
    - Test 10: All 4 stages return correctly-typed dataclass instances (assert isinstance checks)
  </behavior>
  <action>
    1. Create the 4 stage files per `<interfaces>` above (web_baseline.py, retriever.py, reasoner.py, verifier.py). Each file has a module docstring naming the stage and its ar-1 status. PEP 8, type hints, `from __future__ import annotations`.

    2. retriever.py imports ONLY `from omnigraph_search.query import search` (CONTRACT-01). Confirm with grep after write.

    3. Create `tests/unit/research/test_stages_stubs.py` with 10 tests above. Use `pytest-asyncio` (already configured via `asyncio_mode = "auto"` in pyproject.toml). Mock omnigraph_search via `monkeypatch.setattr("lib.research.stages.retriever.kg_search", mock_fn)` (note: import alias). For BASE_IMAGE_DIR tests, build `tmp_path / "lightrag_storage"` so `cfg.rag_working_dir.parent / "images"` resolves to `tmp_path / "images"`.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/test_stages_stubs.py -v &amp;&amp; bash scripts/check_contract.sh</automated>
  </verify>
  <acceptance_criteria>
    - All 4 stage files exist and import without error
    - `pytest tests/unit/research/test_stages_stubs.py -v` exits 0 with ≥10 tests passing
    - `bash scripts/check_contract.sh` exits 0 (CONTRACT-01 still clean — only `omnigraph_search.query` imported)
    - retriever.py contains literal `from omnigraph_search.query import search` (allowed pattern)
    - No stage file contains literal `~/.hermes` or `omonigraph-vault` (CONTRACT-02 — paths derived via `cfg.rag_working_dir`)
  </acceptance_criteria>
  <done>4 stage files + 10 stub tests passing; CONTRACT-01 + CONTRACT-02 still clean.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement synthesizer (terminal stage with CJK heuristic + degradation notes)</name>
  <read_first>
    - lib/research/types.py (SynthesizerOutput — NO status field)
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md § "Output language matches query language (Axis 10)"
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md § "Best-effort failure handling (Axis 3)" — synthesizer terminal exception
  </read_first>
  <files>lib/research/stages/synthesizer.py, tests/unit/research/test_stages_stubs.py (extend)</files>
  <behavior>
    Append synthesizer tests to existing `test_stages_stubs.py`:
    - Test 11: `_detect_language("什么是 Hermes Harness")` returns "zh" (≥30% CJK)
    - Test 12: `_detect_language("What is Hermes Harness")` returns "en" (no CJK)
    - Test 13: `_detect_language("")` returns "en" (empty case)
    - Test 14: `_detect_language("Hermes 的深度解析方法和原理")` returns "zh" (CJK ratio ≈ 11/24 ≈ 45.8% ≥ 30% threshold). Assert form: `assert _detect_language(q) == "zh"` AND `assert (sum(1 for c in q if "一" <= c <= "鿿") / len(q)) >= 0.3` to make the threshold explicit.
    - Test 15: Synthesizer with all-stubbed state (web_baseline=skipped, retrieved=ok with 1 chunk, reasoned=skipped, verified=skipped) returns markdown containing the chunk snippet, ≥1 note_line, confidence=0.5
    - Test 16: Synthesizer with retrieved=None (retriever never ran) → confidence=0.0, note_lines includes "Retriever did not run"
    - Test 17: Synthesizer with retrieved.image_candidates of 7 items → embedded_images is exactly 5 (cap)
    - Test 18: Synthesizer with Chinese query → markdown title starts with "# 关于「"
    - Test 19: Synthesizer with English query → markdown title starts with "# Research Answer:"
    - Test 20: Synthesizer never raises — call with a state where `retrieved.chunks[0].snippet is None` and assert it returns valid output (handle None snippet gracefully)
  </behavior>
  <action>
    1. Create `lib/research/stages/synthesizer.py` per `<interfaces>` above. Module-level helper `_detect_language(query)` is testable independently (export it for test imports).

       Required imports (enumerated so the executor doesn't have to infer): `from __future__ import annotations`, `from pathlib import Path` (synthesizer body uses `embedded_images: list[Path]` and `img.name` / `img.parent.name`), `from ..types import ResearchState, SynthesizerOutput, RetrievedContext`, plus stdlib as needed (`typing.Iterable`, etc.).

    2. Append tests 11-20 to `test_stages_stubs.py`. Test 14 must pick a query string that genuinely has ≥30% CJK ratio. Use `assert ratio_check >= 0.3` form in the test to make the threshold explicit.

    3. Synthesizer contains zero `try`/`except` around the orchestrator-visible body — the design says terminal stage should never need to (Axis 8). It DOES handle None-snippet edge cases gracefully via `or ""` / conditional checks.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/test_stages_stubs.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/stages/synthesizer.py` exists; defines `async def run(...)` and module-level `_detect_language`
    - `pytest tests/unit/research/test_stages_stubs.py -v` exits 0 with ≥20 tests passing (10 from task 1 + 10 from this task)
    - `SynthesizerOutput` has no status — re-verify via `dataclasses.fields(SynthesizerOutput)` test from ar-1-01 still passing
    - Markdown output for Chinese query contains "关于" or "研究答复"; English contains "Research Answer"
  </acceptance_criteria>
  <done>Synthesizer with CJK heuristic + degradation notes; ≥10 new tests passing.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Wire orchestrator and add end-to-end orchestrator integration tests</name>
  <read_first>
    - lib/research/orchestrator.py (current skeleton from ar-1-01)
    - All 5 stage modules (just created)
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md § "Strict pipeline order (Axis 1)"
  </read_first>
  <files>lib/research/orchestrator.py, tests/unit/research/test_orchestrator.py</files>
  <behavior>
    - Test 1: `await research("test query", cfg_with_all_stubs)` returns `ResearchResult` instance; `result.state.web_baseline.status in {"ok","skipped"}`; `result.state.retrieved.status in {"ok","skipped"}`; `result.state.reasoned.status == "skipped"`; `result.state.verified.status == "skipped"`; `result.state.synthesized` exists (no status field).
    - Test 2: With mocked `omnigraph_search.query.search` returning a small KG response, `result.markdown` contains the response text, `result.confidence == 0.5`, `len(result.sources) >= 1`.
    - Test 3: With mocked search raising `RuntimeError("KG down")`, `result.state.retrieved.status == "failed"`, orchestrator does NOT raise, synthesizer note_lines contains "Retriever failed: KG down".
    - Test 4: Pipeline order — patch each stage's `run` to append its name to a shared list; assert list is exactly `["web_baseline", "retriever", "reasoner", "verifier", "synthesizer"]` (Axis 1 strict order).
    - Test 5: `research_stream("query")` raises `NotImplementedError("ar-4")` — confirms ar-4 deferral marker still in place.
  </behavior>
  <action>
    1. Replace the `research()` body in `lib/research/orchestrator.py` per `<interfaces>` above. Keep the lazy stage imports inside the function body (NOT at module scope) — preserves clean module load even if a stage has init-time issues.

    2. Leave `research_stream()` untouched (still raises `NotImplementedError("ar-4")`).

    3. Create `tests/unit/research/test_orchestrator.py` with 5 tests above. Build a minimal `ResearchConfig` instance for tests directly (don't go through `from_env()` to avoid environment coupling) — pass mock callables for all required fields.

    4. Confirm ResearchState mutation: after `research()` returns, `result.state.web_baseline is not None`, `result.state.retrieved is not None`, etc. — all 5 fields populated.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/test_orchestrator.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/orchestrator.py` `research()` body is fully wired (no NotImplementedError)
    - `pytest tests/unit/research/test_orchestrator.py -v` exits 0 with ≥5 tests passing
    - Pipeline order test (test 4) confirms strict sequential `web_baseline → retriever → reasoner → verifier → synthesizer`
    - `research_stream` still raises `NotImplementedError("ar-4")` (LIB-08 split holds)
    - Full test suite: `pytest tests/unit/research/ -v` exits 0 with ≥35 tests passing (≥18 from ar-1-01 + ≥10 stages stubs + ≥10 stages synthesizer + ≥5 orchestrator)
  </acceptance_criteria>
  <done>Orchestrator wired; ≥5 e2e orchestrator tests passing; full ar-1 unit suite ≥35 tests green.</done>
</task>

</tasks>

<verification>
- All 3 tasks pass their automated checks
- `venv/Scripts/python.exe -m pytest tests/unit/research/ -v` exits 0 with ≥35 tests passing
- `bash scripts/check_contract.sh` exits 0 (CONTRACT-01 + CONTRACT-02 clean)
- Programmatic e2e smoke:
  ```bash
  venv/Scripts/python.exe -c "import asyncio; from lib.research import research, from_env; r = asyncio.run(research('test query', from_env())); print(type(r).__name__, len(r.markdown))"
  ```
  Should print `ResearchResult <int>` with `<int> > 0`.
- All 5 ResearchState fields populated after `research()` call
- Pipeline order is exactly `web_baseline → retriever → reasoner → verifier → synthesizer` (verified by orchestrator test 4)
- No stage raises out of the orchestrator (best-effort failure — Axis 3)
- Synthesizer has no status field; degradation surfaces only via note_lines
</verification>

<success_criteria>

- 5 stage modules under `lib/research/stages/` with uniform `async def run(...)` signature
- Retriever wires live `omnigraph_search.query.search()` (CONTRACT-01 enforced)
- Synthesizer terminal stage with CJK heuristic + degradation note_lines (Axis 8/10)
- Orchestrator strict-sequential pipeline (Axis 1) — never raises (Axis 3)
- ≥35 unit tests across 3 test files all passing
- `research_stream` still raises `NotImplementedError("ar-4")` (LIB-08 split)
- CONTRACT-01 + CONTRACT-02 grep hooks both pass
</success_criteria>

<output>
After completion, create `.planning/phases/ar-1-mvp-vertical-slice/ar-1-02-SUMMARY.md` documenting:
- Files created (count + list)
- Test count + pass status (`pytest tests/unit/research/ -v` excerpt)
- CONTRACT-01 + CONTRACT-02 grep result
- Programmatic e2e smoke output (markdown length, ResearchState field counts)
- Pipeline order verification (test 4 result)
- Any deviations from plan (with reason)
</output>
