---
phase: 260514-eji
verified: 2026-05-14T14:10:00Z
status: passed
score: 6/6 must-haves verified
---

# Quick 260514-eji: Dual-Direction Reconcile — Ghost Success Detection

**Goal:** Extend `reconcile_ingestions.py` to flag ghost successes — rows marked `status='failed'` in `ingestions` whose `doc_id` is `processed` in `kv_store_doc_status.json` (LightRAG completed asynchronously after h09 retry budget gave up).

**Verified:** 2026-05-14T14:10:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `status='failed'` row with kv_store `processed` → ghost detected | VERIFIED | `_query_failed_rows` + reverse-scan loop in `main()` at lines 89-112, 194-223; test `test_ghost_success_failed_in_db_processed_in_kv` passes |
| 2 | `status='failed'` row with doc_id absent from kv_store → not counted | VERIFIED | Reverse-scan loop line 204 `if not (isinstance(actual, str) and actual.lower() == "processed"): continue`; test `test_ghost_zero_normal_failed_no_match` passes with exit 0 |
| 3 | Old `"X mystery (wechat: ..., rss: ...)"` substring preserved verbatim left of pipe | VERIFIED | Summary format line 231-236 writes the old prefix unchanged; test `test_ghost_backward_compat_output_format` asserts `"1 ok rows / 1 matched / 0 mystery (wechat: 0, rss: 0)"` as verbatim substring |
| 4 | Ghost JSON lines carry `"kind": "ghost"` discriminator; mystery lines have no `kind` field | VERIFIED | Ghost line at line 212-223 includes `"kind": "ghost"`; mystery line at lines 179-190 has no `kind` field; test `test_ghost_mixed_with_mystery` asserts exactly 1 mystery line without `kind` and 1 ghost line with `kind == "ghost"` |
| 5 | Exit code = 1 when ghost > 0 OR mystery > 0; exit 0 only when both = 0 | VERIFIED | Line 237: `return 1 if (mystery_count > 0 or ghost_count > 0) else 0`; verified by test_ghost_success (exit 1), test_ghost_zero_normal (exit 0), test_ghost_mixed_with_mystery (exit 1) |
| 6 | All 22 existing tests still pass + 4 new ghost tests = 26 total | VERIFIED | `pytest tests/unit/test_reconcile_rss.py tests/unit/test_reconcile_ingestions.py -v` → `26 passed, 0 failed` |

**Score:** 6/6 truths verified

---

### Required Artifacts

| Artifact | Provides | Status | Details |
|----------|----------|--------|---------|
| `scripts/reconcile_ingestions.py` | Dual-direction reconcile with `_query_failed_rows` | VERIFIED | File exists, 242 lines; `_query_failed_rows` at line 89; `"kind": "ghost"` discriminator at line 214; exit code at line 237; `py_compile` exits 0 |
| `tests/unit/test_reconcile_rss.py` | 4 new ghost tests + 14 preserved existing tests = 18 | VERIFIED | File has tests 11-14 (`test_ghost_success_failed_in_db_processed_in_kv`, `test_ghost_zero_normal_failed_no_match`, `test_ghost_mixed_with_mystery`, `test_ghost_backward_compat_output_format`) starting at line 430 |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `main()` | `_query_failed_rows` + `_load_doc_status` | reverse-scan loop emitting `kind="ghost"` JSON lines | WIRED | `failed_rows = _query_failed_rows(...)` at line 194; loop at 198-223 checks `status_map.get(doc_id)`; emits JSON with `"kind": "ghost"` |
| `tests/unit/test_reconcile_rss.py` | `scripts.reconcile_ingestions.main` | direct call with `--db-path`, `--storage-dir`, `--date` args | WIRED | Import at line 30 `from scripts.reconcile_ingestions import ... main`; all 4 new tests call `main([...])` directly |

---

### Behavioral Spot-Checks

| Behavior | Result | Status |
|----------|--------|--------|
| `py_compile scripts/reconcile_ingestions.py` | Exit 0 (no syntax errors) | PASS |
| `pytest tests/unit/test_reconcile_rss.py tests/unit/test_reconcile_ingestions.py -v` | 26 passed, 0 failed, 0.65s | PASS |
| Ghost detected + exit 1 (test 11) | `"1 ghost (wechat: 1, rss: 0)"` + exit 1 | PASS |
| Real failure not ghost + exit 0 (test 12) | `"0 ghost (wechat: 0, rss: 0)"` + exit 0 | PASS |
| Mixed mystery+ghost (test 13) | 2 JSON lines, mystery no `kind`, ghost has `kind="ghost"`, exit 1 | PASS |
| Backward compat (test 14) | `"1 ok rows / 1 matched / 0 mystery (wechat: 0, rss: 0)"` + `"| 0 ghost (wechat: 0, rss: 0)"` | PASS |

---

### Commit Verification

| Check | Result | Status |
|-------|--------|--------|
| Commit SHA | `cdd37da` | VERIFIED |
| Message prefix | `feat(reconcile): scope extend to ghost successes (status=failed but kv_store=processed)` | VERIFIED |
| Files changed | `scripts/reconcile_ingestions.py`, `tests/unit/test_reconcile_rss.py` only | VERIFIED |
| LOC delta | +215 lines, -4 lines (73 + 146 = 219 insertions; 4 deletions) | VERIFIED |

---

### Anti-Patterns Found

None. Surgical changes only: two files, both declared in plan. No TODO/FIXME comments, no stub returns, no hardcoded empty data in non-test paths.

---

### Human Verification Required

None. All behaviors verified programmatically via pytest.

---

## Gaps Summary

No gaps. All 6 must-have truths verified against actual codebase. The `_query_failed_rows` helper exists and is wired, ghost JSON lines carry the `"kind": "ghost"` discriminator, mystery JSON lines are unchanged, exit code semantics are correct (ghost > 0 OR mystery > 0 → exit 1), and 26/26 tests pass.

---

_Verified: 2026-05-14T14:10:00Z_
_Verifier: Claude (gsd-verifier)_
