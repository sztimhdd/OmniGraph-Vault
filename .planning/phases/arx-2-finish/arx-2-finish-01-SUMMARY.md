---
phase: arx-2-finish
plan: 01
wave: 2
status: complete
completed: 2026-06-12
requirements: [REQ-1.1-B-1, REQ-1.1-B-2, REQ-1.1-B-3]
commit: de39f44
---

# Wave 2 (plan 01) — GAP A: real LLM synthesis — SUMMARY

## What was built

Replaced the ar-1 synthesizer stub (`synthesizer.py`, old lines 99-127 returning
`state.retrieved.chunks[0].snippet` verbatim under a hardcoded heading) with real
LLM synthesis. This is the single change that turns "endpoint returns a template"
into "endpoint returns a real cited report."

### Task 1 — synthesizer.py real-synthesis block

- **Module-level import** `from lib.llm_complete import get_llm_func` (NOT
  function-body). This is the load-bearing correction surfaced in the Wave 0
  SUMMARY: the 4-site patch target `lib.research.stages.synthesizer.get_llm_func`
  only intercepts if the name is bound in the synthesizer module namespace. A
  function-body re-import would read the source module each call and the
  patch-where-used tests would call the real provider. Module-level is cheap —
  the heavy DeepSeek/Vertex import is deferred *inside* `get_llm_func()`
  (llm_complete.py:47-49). Reconciles plan 01's "lazy" wording: lazy w.r.t. the
  provider, eager w.r.t. the dispatcher.
- **All-chunk prompt:** `chunks_text` numbers EVERY source `[i+1]` via
  `enumerate(sources)`, not just chunks[0].
- **Reasoner/verifier summaries:** `state.reasoned.inferences_md` +
  `state.verified.fact_check_summary_md` (field names verified against
  types.py:54,64), defensively guarded for None.
- **Bilingual prompt** branched on `lang` (zh/en). The RESEARCH sketch's Chinese
  prompt used ASCII `"{query}"` inside a `"`-delimited f-string (a Python syntax
  error if copied literally) — used 「{query}」 corner brackets instead (matches
  the file's existing degrade-title convention).
- **`await get_llm_func()(prompt)`** in a `try/except Exception … # noqa: BLE001`
  — terminal stage MUST NOT raise. On failure (or empty response) appends a
  `❌ LLM synthesis failed: …` note_line and falls back to the ar-1 template body.
- **Images woven AFTER prose** (success OR degrade) preserving the
  `/static/img/{parent}/{name}` pattern (REQ-1.1-A-4).
- Updated the stale module docstring ("real LLM synthesis lands in ar-2" → "lands
  here now"). Did NOT touch `_detect_language` (deferred per locked decision).

### Task 2 — local CLI confidence check + forward-only commit

Local direct-`run()` confidence check (corp network blocks DeepSeek + no local KG,
so a graceful-degrade demonstration is the acceptable confidence signal per plan):

```
# Research Answer: What is an AI agent?
## Knowledge Graph Retrieval
REAL_CHUNK_BODY_marker
---
> ⚠️ WebBaseline did not run.   > ⚠️ Reasoner did not run.   > ⚠️ Verifier did not run.
> ❌ LLM synthesis failed: Connection error.
confidence: 0.5 | sources: 1
```

The `❌ LLM synthesis failed: Connection error.` note proves the real-LLM code path
EXECUTED (built prompt → called real provider → hit corp block → degraded
gracefully without raising) — NOT the bare ar-1 stub (which had no try/except +
note). Real prose lands on Aliyun/Databricks where the provider is reachable
(Waves 4/5 prove it).

## Deviation (recorded — contract-shape audit)

**Plan 01 acceptance under-scoped the test impact.** It named only
`test_synthesizer_llm.py` + `test_synthesizer_caption_embeds.py` +
`test_research_router.py`. The synthesizer output-contract change orphaned **4
tests that pinned the OLD stub behavior**:

| Test | Old (stub) assertion | New (GAP-A) assertion |
|------|----------------------|------------------------|
| `test_stages_stubs::test_synthesizer_with_one_chunk` | `"The KG content here." in markdown` | chunk → **prompt**; real prose → markdown; confidence/notes intact |
| `test_stages_stubs::test_synthesizer_chinese_title` | title `# 关于「` always | force degrade → assert language-routed fallback title |
| `test_stages_stubs::test_synthesizer_english_title` | title `# Research Answer:` always | force degrade → assert language-routed fallback title |
| `test_orchestrator::test_research_with_live_kg_response` | `kg_response in markdown` | `kg_response in result.sources[*].snippet` |

Per memory `feedback_contract_shape_change_full_audit` (grep ALL read-write sites)
+ `feedback_test_mirrors_impl` (pin verifiable contract values, not impl echo), I
updated these to pin the NEW contract rather than re-pin obsolete stub behavior.
The autouse conftest mock (Wave 0) makes them deterministic.

## Verification

| Check | Result |
|-------|--------|
| `grep "from lib.llm_complete import get_llm_func"` | OK |
| `grep "enumerate(sources)"` | OK |
| `grep "noqa: BLE001"` | OK |
| `grep "/static/img/"` | OK |
| 3 GAP-A tests (test_synthesizer_llm.py) | RED → **GREEN** ✅ |
| 10 caption tests | still GREEN ✅ |
| 4 contract-orphaned tests | updated → GREEN ✅ |
| `pytest tests/unit/research/ tests/integration/test_research_router.py` | **186 passed, 0 failed** ✅ |
| Local CLI confidence | real-LLM path executed (graceful-degrade note) ✅ |

## Key files

- modified: `lib/research/stages/synthesizer.py` (module import + real-synthesis block + docstring)
- modified: `tests/unit/research/test_stages_stubs.py` (3 contract-orphan fixes)
- modified: `tests/unit/research/test_orchestrator.py` (1 contract-orphan fix)
- commit: `de39f44`

## Self-Check: PASS

Synthesizer emits real LLM prose using all chunks with [n] + woven images; LLM
failure degrades gracefully (note_line + fallback) without raising; all research
unit + transport tests green (186); forward-only commit with explicit git add.
