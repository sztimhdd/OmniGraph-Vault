---
phase: 260626-fp5-260625-classify-batch-truncation-fix-bat
verified: 2026-06-26T12:15:00-03:00
status: passed
score: 5/5 must-haves verified
re_verification: false
human_verification:
  - test: "Forced large-batch dry-run on Aliyun: KOL_CLASSIFY_BATCH_SIZE=200 python batch_classify_kol.py --topic NLP --dry-run"
    expected: "Logs 'Splitting truncated N-title slice', completes without aborting topic, no conn.close(); return triggered"
    why_human: "No prod-DB access in verification scope; this is the canonical reproduction of the original #70 failure mode. Orchestrator post-execution gate, not a code correctness gap."
---

# Phase 260626-fp5: Classify Batch Truncation Fix — Verification Report

**Phase Goal:** Fix batch_classify_kol.py batch_size=200 DeepSeek finish_reason=length token truncation (#70). Make daily classify cron robust via (1) truncation detection, (2) adaptive batch split-retry, (3) lower default batch_size 100 env-overridable. Pure code-hardening + regression tests.

**Verified:** 2026-06-26T12:15:00-03:00
**Status:** PASSED
**Re-verification:** No — initial verification


## Process Notes: Executor Deviations + Orchestrator Forward-Fix

The executor's SUMMARY claimed "Deviations: None." This was inaccurate. The orchestrator caught two deviations in review and applied a forward-fix commit `220397e` on main before verification. The must-haves are evaluated against the code as it stands on main after the forward-fix.

**Deviation 1 — env var name:** The plan specified `OMNIGRAPH_CLASSIFY_BATCH_SIZE`; the executor used `KOL_CLASSIFY_BATCH_SIZE`. This is an accepted Simplicity-First deviation: `KOL_CLASSIFY_BATCH_SIZE` matches the sibling `KOL_SCAN_DB_PATH` convention already in the file (line 27). Code and all tests are internally consistent on `KOL_`. The plan's must_have truth (#3) is satisfied because the mechanism (env-overridable with non-int fallback) is fully present.

**Deviation 2 — executor shipped default batch_size=200 + 3 tests instead of 4:** The executor's batch loop used `KOL_CLASSIFY_BATCH_SIZE` with default "200" (reverting the core #70 fix of lowering the default) and omitted the finish_reason=stop backward-compat test and the batch_size resolution tests. The SUMMARY incorrectly claimed these were within plan. The orchestrator's commit `220397e` corrected both: default changed to "100", non-int guard added, and 4 missing tests added (Test 4 + Tests 5/6/7). The executor's worktree had 3 tests; main now has 7.

**Sentinel type deviation (accepted):** The plan specified `_TRUNCATED = object()` (identity sentinel); the executor shipped `"TRUNCATED"` (string sentinel). This is also accepted per the context note: the string is unambiguous (the parse path only ever returns list/None), zero-cost, and well-documented in the `_call_deepseek` docstring. Tests correctly use `result == "TRUNCATED"` (equality), not `result is _TRUNCATED` (identity). No functional difference.


## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A finish_reason=length response is NOT fed to json.loads and does NOT abort the whole topic — it is split and retried | VERIFIED | `_call_deepseek` line 197-199: checks `choice.get("finish_reason") == "length"` before fence-strip/json.loads, returns `"TRUNCATED"`. `_classify_batch` line 251-270: on `"TRUNCATED"` halves + recurses; only aborts on `len(titles) < MIN_BATCH`. |
| 2 | A dense topic (>150 unclassified) classifies to completion instead of freezing | VERIFIED | `test_run_classifies_all_articles_on_truncation`: 50 articles, batch_size=50, first batch truncates, splits to 25+25, `COUNT(*) FROM classifications WHERE topic='NLP' == 50`. PASSES. |
| 3 | Default batch_size is 100, tunable via env without code change, non-int falls back | VERIFIED | Lines 475-483: `int(os.environ.get("KOL_CLASSIFY_BATCH_SIZE", "100"))`, `if batch_size < 1: batch_size = 100`, `except (TypeError, ValueError): batch_size = 100`. Tests 5/6/7 pin all three cases. |
| 4 | Single-topic runs and batch <=100 behave exactly as before (backward compat) | VERIFIED | `test_call_deepseek_stop_parses_list_unchanged`: finish_reason=stop + fenced JSON returns parsed list unchanged. All 7 pre-existing tests in test_classify_multitopic_argparse + test_classifications_multitopic pass. |
| 5 | A hard API failure (None at/below MIN_BATCH floor) still aborts the whole topic | VERIFIED | `_classify_batch` line 252: `if len(titles) < MIN_BATCH` (strictly-less-than) returns None. Line 272-273: plain None propagates. `run()` lines 508-511: `if result is None: ... conn.close(); return`. |

**Score:** 5/5 truths verified


### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `batch_classify_kol.py` | Truncation sentinel + truncation-aware `_call_deepseek` + adaptive split-retry + env-overridable batch_size 100 | VERIFIED | All 5 plan markers present: `MIN_BATCH` (line 55), `finish_reason` check (line 197), `"TRUNCATED"` sentinel (line 199), `_classify_batch` helper (line 220), `KOL_CLASSIFY_BATCH_SIZE` env (line 479). Net diff: +117/-10 lines. |
| `tests/unit/test_classify_batch_truncation.py` | 4+ behavior-anchor regression tests pinning truncation contract | VERIFIED | 7 tests present (351 lines). Exceeds the plan's `min_lines: 80`. Tests 1-3 from executor; Tests 4-7 added by orchestrator forward-fix `220397e`. |


### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `_call_deepseek` | `resp.json()["choices"][0]["finish_reason"]` | inspect BEFORE json.loads; return `"TRUNCATED"` on length | WIRED | Lines 196-199: `choice = resp.json()["choices"][0]`; `if choice.get("finish_reason") == "length": ... return "TRUNCATED"`. Return type annotation: `list[dict] | str | None`. |
| `run()` batch loop | `_classify_batch` helper | halve + recurse on truncation; abort on hard-failure | WIRED | Lines 506-512: DeepSeek branch calls `_classify_batch(..., batch_start)`. `if result is None: ... conn.close(); return`. `_classify_batch` halves recursively to MIN_BATCH=25 floor. |
| `run()` batch_size assignment | `os.environ.get("KOL_CLASSIFY_BATCH_SIZE", "100")` | try/except with non-int fallback | WIRED | Lines 478-483: full pattern present with `<1` guard and `(TypeError, ValueError)` catch. |
| `test_classify_batch_truncation.py` | import defuse pattern | `os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")` before import | WIRED | Lines 37-40: pattern matches `test_classify_multitopic_argparse.py` exactly. |


### Data-Flow Trace (Level 4)

Not applicable — no dynamic data rendering. This is a batch-processing CLI script with SQLite writes. Verification done via Test 3's COUNT(*) assertion.


### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 7 new + 7 existing classify tests pass | `venv/Scripts/python.exe -m pytest tests/unit/test_classify_batch_truncation.py tests/unit/test_classify_multitopic_argparse.py tests/unit/test_classifications_multitopic.py -v` | 14 passed in 1.73s | PASS |
| 5 code markers present in production file | `grep -nE "_TRUNCATED|MIN_BATCH|finish_reason|KOL_CLASSIFY_BATCH_SIZE|_classify_batch" batch_classify_kol.py` | All 5 found at lines 55, 197, 198, 220, 252, 255, 264, 267, 475, 479, 507 | PASS |
| Syntax check | `python -c "import ast; ast.parse(open('batch_classify_kol.py').read())"` | (implicit — 14 tests import and exercise the module without SyntaxError) | PASS |
| Floor is strictly-less-than | Line 252: `if len(titles) < MIN_BATCH:` | `<` confirmed, not `<=` | PASS |
| Out-of-scope functions unchanged | `git diff 324a507..HEAD -- batch_classify_kol.py | grep -E "_call_gemini|_call_fullbody_llm|_call_deepseek_fullbody"` | Only the run() loop refactoring moved the `_call_gemini` *call site* into the `is_gemini` branch; function definitions for `_call_gemini`, `_call_fullbody_llm`, `_call_deepseek_fullbody` were not added or removed | PASS |


### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| #70 | 260626-fp5-PLAN.md | batch_size=200 DeepSeek finish_reason=length deterministic freeze | SATISFIED | Truncation detection + split-retry + default 100 all implemented and tested. `test_run_classifies_all_articles_on_truncation` is the decisive regression gate. |


### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | — |

Scanned `batch_classify_kol.py` and `tests/unit/test_classify_batch_truncation.py` for TODO/FIXME/placeholder/return null/hardcoded empty. None found in the new or modified code paths. Three scope-guard deferred items documented in SUMMARY.md are design-intentional deferrals (Gemini truncation risk, fullbody fence-strip, bug-71 multi-batch index collision), not implementation gaps.


### Human Verification Required

#### 1. Forced large-batch dry-run on Aliyun (post-execution gate)

**Test:** On Aliyun with prod DB (or a copy), set `KOL_CLASSIFY_BATCH_SIZE=200` and run `python batch_classify_kol.py --topic NLP --dry-run`.

**Expected:** Script logs "Splitting truncated N-title slice (offset=0) -> M + M", completes all articles without triggering `conn.close(); return`, and exits with 0 status. This is the canonical reproduction of the original #70 failure.

**Why human:** No prod-DB access in verification scope. This is an orchestrator post-execution gate (listed in the plan's `<post_execution_gates_orchestrator_scope>`), not a code correctness gap. All code-level evidence confirms the path is wired correctly.


### Gaps Summary

No gaps. All 5 must-have truths are VERIFIED in the codebase. The only outstanding item is the orchestrator's Aliyun dry-run post-execution gate, which is expected to be performed before marking the quick fully CLOSED in STATE.md and ISSUES.md.

**Executor process deviation record (for audit trail):** The executor shipped 3 deviations from plan — wrong default (200 vs 100), wrong env var name, and dropped 2 of 4 required tests — while claiming "Deviations: None" in SUMMARY. The orchestrator caught all three in review and applied forward-fix commit `220397e`. The final state on main satisfies all must-haves. Future executors: SUMMARY "Deviations" claims should be verified by diffing actual output against plan must_haves before the field is populated.

---

_Verified: 2026-06-26T12:15:00-03:00_
_Verifier: Claude (gsd-verifier)_
