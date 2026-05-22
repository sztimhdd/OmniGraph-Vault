---
phase: ar-1-mvp-vertical-slice
plan: 02
subsystem: agentic-rag-v1
tags: [stages, orchestrator, retriever, synthesizer, pipeline-wiring]
requires:
  - python>=3.11
  - lib/research/types.py (ar-1-01)
  - lib/research/config.py (ar-1-01)
  - lib/research/orchestrator.py (ar-1-01 skeleton)
  - omnigraph_search/query.py search() (existing — CONTRACT-01)
provides:
  - 5 stage modules under lib/research/stages/ with uniform `async def run(...)` signature
  - Live retriever wiring to omnigraph_search.query.search (CONTRACT-01)
  - Synthesizer terminal stage with CJK heuristic (Axis 10) + degradation note_lines (Axis 8)
  - Orchestrator strict-sequential pipeline (Axis 1) — never raises (Axis 3)
  - 25 new unit tests across 2 files
affects:
  - lib/research/orchestrator.py (research() body wired; research_stream() unchanged)
tech-stack:
  added:
    - regex-based hash globbing (10-char hex match for KB image lookup)
    - CJK char ratio language heuristic
  patterns:
    - best-effort failure (try/except returning Status='failed' + reason)
    - lazy stage imports inside research() body
    - terminal stage with no try/except wrap (Axis 8)
key-files:
  created:
    - lib/research/stages/web_baseline.py
    - lib/research/stages/retriever.py
    - lib/research/stages/reasoner.py
    - lib/research/stages/verifier.py
    - lib/research/stages/synthesizer.py
    - tests/unit/research/test_stages_stubs.py
    - tests/unit/research/test_orchestrator.py
  modified:
    - lib/research/orchestrator.py
decisions:
  - "Pipeline order locked at strict-sequential web_baseline -> retriever -> reasoner -> verifier -> synthesizer (Axis 1)"
  - "Synthesizer is terminal — NO status field; degradation surfaces only via note_lines (Axis 8)"
  - "CJK char ratio >= 0.3 -> 'zh' heuristic for ar-1; ar-2 swaps in real LLM-driven detection (Axis 10)"
  - "Orchestrator never wraps stages in try/except — stages are best-effort internally (Axis 3); a propagated exception is a real bug not a degradation"
  - "Lazy stage imports inside research() body — preserves clean module load even if a stage has init-time issues"
  - "Image cap at 5 in synthesizer for ar-1 (real LLM-driven selection lands in ar-2)"
  - "Confidence 0.5 if Retriever ok else 0.0 — placeholder until Verifier produces real confidence in ar-3"
metrics:
  duration_seconds: 540
  duration_human: "~9 minutes"
  tasks_completed: 3
  files_created: 7
  files_modified: 1
  unit_tests_added: 25
  unit_tests_total: 46
  unit_test_pass_rate: "46/46 (100%)"
  completed: "2026-05-22"
requirements_satisfied:
  - ORCH-01
  - ORCH-02
  - ORCH-06
  - ORCH-07
  - ORCH-09
---

# Phase ar-1 Plan 02: Stage Stubs Summary

5-stage pipeline implementation: 4 deterministic stub stages (web_baseline,
reasoner, verifier emitting `status="skipped"`; retriever wiring live
`omnigraph_search.query.search()`) plus a terminal Synthesizer with CJK
language heuristic + degradation `note_lines`. Orchestrator's `research()`
body now drives the strict-sequential pipeline (Axis 1) and never raises out
(Axis 3). 46/46 unit tests green, both CONTRACT grep hooks clean.

## Files Created (7) + Modified (1)

| File | Role |
|---|---|
| `lib/research/stages/web_baseline.py` | ar-1 stub — `status="skipped"` when `web_search` returns `[]`; live-results path normalizes dicts into `Source(kind="web", ...)` |
| `lib/research/stages/retriever.py` | Live `omnigraph_search.query.search` call (CONTRACT-01) + glob `RetrievedImage` candidates from `cfg.rag_working_dir.parent / "images"` |
| `lib/research/stages/reasoner.py` | ar-1 stub — `status="skipped"`, `iter_count=0`; agent loop deferred to ar-2 |
| `lib/research/stages/verifier.py` | ar-1 stub — `status="skipped"`, `confidence=0.0`; verifier loop deferred to ar-3 |
| `lib/research/stages/synthesizer.py` | Terminal stage (NO status field) — minimal markdown + CJK heuristic + degradation `note_lines` |
| `tests/unit/research/test_stages_stubs.py` | 20 unit tests (5 stages × stub/failure/typed-shape coverage + 4 language heuristic tests) |
| `tests/unit/research/test_orchestrator.py` | 5 e2e integration tests — pipeline shape, live response, failure tolerance, strict order, streaming peer |
| `lib/research/orchestrator.py` | **modified** — `research()` body wired to call all 5 stages in order; `research_stream()` unchanged |

## Test Results

```
$ venv/Scripts/python.exe -m pytest tests/unit/research/ -v
========================= 46 passed in 2.82s =========================
```

Breakdown by file:
- `test_types.py` — 10/10 (carried from ar-1-01)
- `test_config.py` — 11/11 (carried from ar-1-01)
- `test_stages_stubs.py` — 20/20 (new, ar-1-02 Tasks 1+2)
- `test_orchestrator.py` — 5/5 (new, ar-1-02 Task 3)

## CONTRACT Enforcement

```
$ bash scripts/check_contract.sh
CONTRACT-01 ok
CONTRACT-02 ok
```

- **CONTRACT-01** (forbidden `omnigraph_search.*` imports): only `from omnigraph_search.query import search as kg_search` in `retriever.py` — 0 violations
- **CONTRACT-02** (`~/.hermes` / `omonigraph-vault` paths outside `config.py`): 0 hits

## Programmatic E2E Smoke

Hand-rolled `ResearchConfig` (no `from_env()`), retriever's `kg_search`
patched to return `""`:

```
ResearchResult markdown_len= 370
confidence= 0.0
all 5 state fields populated: True
note_lines count: 4
markdown preview:
# Research Answer: test query
## Knowledge Graph Retrieval

(no chunks retrieved)


---

> ℹ️ WebBaseline skipped: web_search returned [] (TAVILY_API_KEY unset — ar-1 stub mode)
> ℹ️ Retriever skipped: omnigraph_search.query.search returned empty
> ℹ️ Reasoner skipped: ar-1 stub — agent loop lands in ar-2
> ℹ️ Verifier skipped: ar-1 stub — verifier loop lands in ar-3
```

All 5 ResearchState stage fields populate; all 4 stub stages surface as
degradation `note_lines` per Axis 8; markdown is 370 chars (well above the
"non-empty" requirement).

## Pipeline Order Verification

`test_research_pipeline_order` (orchestrator test 4) wraps each stage's `run`
to append its name to a shared list, then asserts the list is exactly:

```
["web_baseline", "retriever", "reasoner", "verifier", "synthesizer"]
```

Test passed — strict sequential order (Axis 1) confirmed.

## Stage Status Alphabet (ar-1)

| Stage | ar-1 status (default cfg) | Reason |
|---|---|---|
| WebBaseline | `skipped` | `web_search` returns `[]` (TAVILY_API_KEY unset) |
| Retriever | `ok` (with KB) / `skipped` (empty KG) / `failed` (KG raises) | live LightRAG hybrid query |
| Reasoner | `skipped` | ar-1 stub — agent loop lands in ar-2 |
| Verifier | `skipped` | ar-1 stub — verifier loop lands in ar-3 |
| Synthesizer | (no status) | terminal — degradation via `note_lines` (Axis 8) |

## Commits (3)

| Hash | Message |
|---|---|
| `00bd838` | feat(ar-1-02): add 4 stage modules (web_baseline, retriever, reasoner, verifier) + 10 tests |
| `0960f3f` | feat(ar-1-02): add synthesizer terminal stage with CJK heuristic + degradation notes |
| `b994e00` | feat(ar-1-02): wire orchestrator 5-stage pipeline + 5 e2e integration tests |
| (this) | docs(ar-1-02): SUMMARY |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan's Test 11 sample string is below the 0.3 CJK threshold**

- **Found during:** Task 2 verification (first pytest run after synthesizer landed)
- **Issue:** Plan specified `_detect_language("什么是 Hermes Harness") == "zh"`,
  but mathematically this string has 3 CJK chars / 19 total = 15.8% ratio,
  which is **below** the 0.3 threshold the heuristic enforces. The test
  fails not because the heuristic is wrong but because the example query
  is internally inconsistent with the Axis 10 spec (≥0.3 CJK → zh).
- **Fix:** Replaced the test query with `"什么是 Hermes 深度解析方法"`
  (9 CJK / 18 total = 50% — comfortably above threshold). The heuristic
  itself was implemented per spec; only the failing test sample needed
  adjustment. Test 14 (which explicitly asserts the threshold check) was
  unchanged and validates the heuristic from the math side.
- **Files modified:** `tests/unit/research/test_stages_stubs.py` (test 11 only)
- **Commit:** folded into `0960f3f` (the introducing commit)

**2. [Rule 1 - Bug] CONTRACT-02 grep matched docstring text in retriever.py**

- **Found during:** Task 1 first contract check
- **Issue:** Initial `retriever.py` docstring referenced the canonical typo
  `omonigraph-vault` and `~/.hermes` literals when explaining CONTRACT-02 —
  the grep hook (which is intentionally naive — it doesn't distinguish
  string-literal usage from docstring text) flagged this as a violation.
- **Fix:** Reworded the docstring to "no hardcoded runtime-data path
  literals (those live only in config.py)" — preserving the intent without
  triggering the grep.
- **Files modified:** `lib/research/stages/retriever.py` (docstring only)
- **Commit:** folded into `00bd838` (the introducing commit)

No other deviations. All 3 tasks executed task-for-task as written.

## Self-Check: PASSED

All claimed files exist:

- `lib/research/stages/web_baseline.py`, `retriever.py`, `reasoner.py`,
  `verifier.py`, `synthesizer.py` — all present
- `tests/unit/research/test_stages_stubs.py`, `test_orchestrator.py` — present
- `lib/research/orchestrator.py` — modified (research() body wired,
  research_stream() unchanged)

All claimed commits exist in `git log --oneline`:

- `00bd838`, `0960f3f`, `b994e00` — verified

All claimed verifications pass:

- `pytest tests/unit/research/ -v` → 46 passed
- `bash scripts/check_contract.sh` → exit 0, both CONTRACT-01 + CONTRACT-02 ok
- Programmatic smoke: ResearchResult shape correct, markdown 370 chars,
  all 5 state fields populated
- Pipeline order: strict sequential per orchestrator test 4

## L1 smoke status: PASS

- 46/46 unit tests pass on first clean run
- CONTRACT-01 + CONTRACT-02 grep hooks both clean (0 hits)
- Orchestrator drives 5-stage pipeline end-to-end in <1s with all stubs
- Synthesizer emits markdown with degradation notes for every skipped/failed
  upstream stage (Axis 8)
- ar-1-03 (CLI + image server) may proceed
