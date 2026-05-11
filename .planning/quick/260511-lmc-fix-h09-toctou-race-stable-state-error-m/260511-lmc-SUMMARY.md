---
phase: quick-260511-lmc
plan: 01
subsystem: ingest_wechat
tags: [bug-fix, toctou, lightrag, processed-gate, deepseek-402]
requirements: [H09-RACE-FIX]
key-files:
  modified:
    - ingest_wechat.py
    - tests/unit/test_ingest_article_processed_gate.py
decisions:
  - "Combined Option C guard: error_msg guard (Option B) before stable re-poll (Option A)"
  - "stable_delay_s defaults to 5.0s, env-overridable via OMNIGRAPH_STABLE_VERIFY_DELAY"
  - "Updated 3 existing tests to reflect stable re-poll behavior (Tests 1, 2, 5 now expect 2/4/3 calls)"
metrics:
  duration: "~25 minutes"
  completed: "2026-05-11"
  tasks: 1
  files: 2
---

# Phase quick-260511-lmc Plan 01: h09 TOCTOU Race Fix Summary

**One-liner:** Combined error_msg guard + stable-state re-poll in `_verify_doc_processed_or_raise` to eliminate 2026-05-11 mystery rows where `ingestions.status='ok'` was written despite LightRAG `doc_status='failed'` from DeepSeek 402 partial-failure.

## What Was Built

### Problem

2026-05-11 mystery rows (art_id=154/155/157/184): the `_verify_doc_processed_or_raise` helper returned `True` (and caller set `ingestions.status='ok'`) despite LightRAG's `doc_status` being `'failed'` with `error_msg='Insufficient Balance'` from DeepSeek 402. Root cause: two TOCTOU races:

1. **TOCTOU Race A (stale processed window):** LightRAG briefly writes `PROCESSED` (at `lightrag.py:2158`) before writing `FAILED+error_msg` (at `lightrag.py:2232` on merge failure). The helper polled during the brief PROCESSED window and returned immediately.

2. **TOCTOU Race B (overlapping state from prior successful ingest):** A prior ingest left `doc_status='processed'`; a new ingest started with `PROCESSING → FAILED+error_msg` but the stale `'processed'` was still readable when the helper polled.

In both cases, a genuinely failed doc appeared `'processed'` to the poller.

### Fix: Combined Option C Guard

**Changes to `ingest_wechat.py`:**

1. Added `STABLE_VERIFY_DELAY_S` constant (line 63):
   ```python
   STABLE_VERIFY_DELAY_S = float(os.getenv("OMNIGRAPH_STABLE_VERIFY_DELAY", "5.0"))
   ```

2. Added `stable_delay_s` parameter to `_verify_doc_processed_or_raise` signature (line 82):
   ```python
   stable_delay_s: float = STABLE_VERIFY_DELAY_S,
   ```

3. Replaced the single-line `return` in the `_status_is_processed` branch with two sequential guards:

   - **Option B (error_msg guard):** If `status='processed'` AND `error_msg` non-empty → update `last_status_val` to `"processed-with-error: ..."` and continue retry loop. Works for both dict and dataclass-like entries.

   - **Option A (stable re-poll):** If `status='processed'` AND no `error_msg` → `asyncio.sleep(stable_delay_s)`, call `aget_docs_by_ids` again, check both `status` and `error_msg` of the re-poll result. Only return `True` if re-poll also shows `'processed'` + no `error_msg`. Otherwise continue retry loop with `last_status_val="unstable-processed: ..."`.

**Changes to `tests/unit/test_ingest_article_processed_gate.py`:**

- Added 5 new TOCTOU race tests (Tests 7-11):
  - `test_processed_with_error_msg_continues_retry` — error_msg guard fires on `'processed' + error_msg`
  - `test_processed_stable_recheck_confirms_ok` — stable re-poll happy path (2 calls)
  - `test_processed_stable_recheck_sees_failed` — stable re-poll sees `'failed'`, 6 total calls
  - `test_processed_stable_recheck_sees_error_msg` — stable re-poll sees `'processed' + error_msg`, 6 total calls
  - `test_processed_enum_member_with_error_msg` — enum member (not string) + error_msg guard

- Updated 3 existing tests to account for new stable re-poll call:
  - Test 1: 1 mock entry → 2 entries (initial + stable re-poll); `await_count == 1` → `== 2`
  - Test 2: 3 mock entries → 4 entries (added stable re-poll after the `processed`); `await_count == 3` → `== 4`
  - Test 5: 2 mock entries → 3 entries (added stable re-poll after the `processed`); `await_count == 2` → `== 3`

## Test Results

**TDD sequence confirmed:**

- RED run: 8 tests failed (Tests 1, 2, 5 + 5 new), 3 passed — see `.scratch/h09race-pytest-red-20260511-154759.log`
- GREEN run: 11/11 tests passed — see `.scratch/h09race-pytest-green-20260511-160944.log`

Full output (GREEN):
```
collected 11 items
test_processed_verification_passes_first_try PASSED
test_processed_promotes_after_retry PASSED
test_never_promotes_raises_runtime_error PASSED
test_doc_missing_from_status_raises PASSED
test_aget_docs_raises_then_recovers PASSED
test_outer_catches_inner_runtime_error_returns_failed PASSED
test_processed_with_error_msg_continues_retry PASSED
test_processed_stable_recheck_confirms_ok PASSED
test_processed_stable_recheck_sees_failed PASSED
test_processed_stable_recheck_sees_error_msg PASSED
test_processed_enum_member_with_error_msg PASSED
11 passed in 5.14s
```

**Regression check:** 23 pre-existing failures in other unit test files; verified they exist on base HEAD before my changes (confirmed via `git stash` + re-run). My changes caused zero new failures.

## Commits

| Commit | Description |
|--------|-------------|
| `8adbfd0` | fix(ingest-260511-h09r): h09 TOCTOU race — verify processed is stable + error_msg empty before returning, eliminates 2026-05-11 mystery rows from DeepSeek 402 partial-failure |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Updated 3 existing tests to reflect stable re-poll behavior**

- **Found during:** Step 2 (writing tests) / Step 4 (GREEN verification)
- **Issue:** Tests 1, 2, and 5 were written when `_verify_doc_processed_or_raise` had no stable re-poll. After the fix, every successful `'processed'` observation requires a stable re-poll call. Existing test mocks with N entries would raise `StopAsyncIteration` on the N+1 stable re-poll call. Their `await_count` assertions were also wrong.
- **Fix:** Added stable re-poll entries to mock `side_effect` lists and updated `await_count` assertions in Tests 1 (1→2), 2 (3→4), and 5 (2→3). Added `stable_delay_s=0.0` kwarg to keep tests fast.
- **Files modified:** `tests/unit/test_ingest_article_processed_gate.py`
- **Impact:** All 11 tests pass; test semantics preserved (each test still verifies its intended scenario)

## Self-Check

- [x] `STABLE_VERIFY_DELAY_S` present in `ingest_wechat.py` at line 63
- [x] `stable_delay_s` parameter in `_verify_doc_processed_or_raise` at line 82
- [x] `error_msg` guard precedes stable re-poll in the processed branch (lines 141-145 before line 152)
- [x] Commit `8adbfd0` exists: `git log --oneline -1` shows `8adbfd0 fix(ingest-260511-h09r): ...`
- [x] pytest log at `.scratch/h09race-pytest-green-20260511-160944.log` cited in commit body
- [x] No changes to `batch_ingest_from_spider.py`, `PROCESSED_VERIFY_MAX_RETRIES`, `PROCESSED_VERIFY_BACKOFF_S`, `MIN_INGEST_BODY_LEN`, or `lib/` files

## Self-Check: PASSED
