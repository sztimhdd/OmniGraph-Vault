---
phase: quick-260629-gvl
verified: 2026-06-29T17:35:00Z
status: passed
score: 7/7 must-haves verified
re_verification: false
---

# Quick 260629-gvl: KOL Dead-Account Prune and Guard — Verification Report

**Task Goal:** Fix ISSUES #73 — add accounts.last_scanned_at (idempotent migration), stamp on every SUCCESSFUL scan attempt (ok=True incl. 0-article), NOT on failure; re-order the --max-accounts staleness SELECT to sort by last_scanned_at (NULL-first, oldest-attempted, name) so empty-but-healthy accounts rotate to the back after one attempt instead of pinning the staleness head.

**Verified:** 2026-06-29T17:35:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                         | Status     | Evidence                                                                                                     |
| --- | --------------------------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------ |
| 1   | accounts.last_scanned_at column added idempotently (PRAGMA-guarded ALTER, safe on re-run)    | VERIFIED   | `batch_scan_kol.py:142` — `_ensure_column(conn, "accounts", "last_scanned_at", "TEXT")`; inside the existing PRAGMA-guarded migration block alongside the other 3 `_ensure_column` calls |
| 2   | Every SUCCESSFUL scan attempt (ok=True) stamps last_scanned_at — INCLUDING 0-article accounts | VERIFIED   | `batch_scan_kol.py:308-316` — `if ok:` branch contains `UPDATE accounts SET last_scanned_at = datetime('now','localtime') WHERE name = ?` + `conn.commit()`. test_stamp_on_success_even_zero_articles PASSED |
| 3   | A FAILED attempt (ok=False / cookie-dead) does NOT stamp last_scanned_at                     | VERIFIED   | `batch_scan_kol.py:319` — `else:` branch contains only `failed_count += 1` and optional JSON append. No UPDATE. test_no_stamp_on_failure PASSED (asserts all NULL after all-failure run) |
| 4   | Staleness ordering (max_accounts path) sorts by (last_scanned_at IS NULL) DESC, last_scanned_at ASC, name ASC | VERIFIED   | `batch_scan_kol.py:263-266` — query reads directly from `accounts` with `ORDER BY (last_scanned_at IS NULL) DESC, last_scanned_at ASC, name ASC`. No LEFT JOIN/GROUP BY. No NULLS FIRST keyword. |
| 5   | A just-scanned empty account rotates to the BACK of the staleness queue                      | VERIFIED   | test_just_scanned_rotates_to_back PASSED — VeryRecent (2026-06-29 12:00:00) excluded when max_accounts=2; OlderA + OlderB selected |
| 6   | Default path (max_accounts is None) stays byte-behavior-identical: SELECT ORDER BY name + random.shuffle | VERIFIED   | `batch_scan_kol.py:250-257` — `SELECT name, fakeid FROM accounts ORDER BY name` + `random.shuffle(rows)`. Unchanged. test_default_path_no_truncation PASSED |
| 7   | The 4 existing tests in test_scan_max_accounts.py still pass (no regression)                 | VERIFIED   | All 4 existing tests PASSED: test_staleness_selection_null_first_then_oldest, test_default_path_no_truncation, test_argparse_max_accounts_int, test_argparse_max_accounts_absent_is_none |

**Score:** 7/7 truths verified

---

### Required Artifacts

| Artifact                                  | Expected                                              | Status     | Details                                                                                     |
| ----------------------------------------- | ----------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------- |
| `batch_scan_kol.py`                       | last_scanned_at column + stamp-on-success + staleness re-ordering | VERIFIED   | All 3 changes present: line 142 (column), lines 312-316 (stamp), lines 263-266 (SELECT). File is 382 lines, substantive. |
| `tests/unit/test_scan_last_scanned.py`    | Behavior-anchor tests for stamp + ordering + no-stamp-on-failure | VERIFIED   | 270 lines, 4 real test functions, all with concrete assertions on DB state and call_args[1] ordering. |

---

### Key Link Verification

| From                                  | To                         | Via                                                              | Status  | Details                                                                                      |
| ------------------------------------- | -------------------------- | ---------------------------------------------------------------- | ------- | -------------------------------------------------------------------------------------------- |
| run() scan loop                       | accounts.last_scanned_at   | UPDATE ... SET last_scanned_at = datetime('now','localtime') WHERE name = ? when ok is True | WIRED   | `batch_scan_kol.py:312-316` inside `if ok:` block. Pattern `last_scanned_at\s*=\s*datetime` confirmed. |
| staleness SELECT (max_accounts path)  | accounts.last_scanned_at   | ORDER BY (last_scanned_at IS NULL) DESC, last_scanned_at ASC, name ASC | WIRED   | `batch_scan_kol.py:263-266`. Pattern `last_scanned_at IS NULL` confirmed at line 265. |

---

### Behavioral Spot-Checks (pytest)

| Behavior                                              | Command                                                              | Result       | Status |
| ----------------------------------------------------- | -------------------------------------------------------------------- | ------------ | ------ |
| stamp on 0-article success                            | pytest test_scan_last_scanned.py::test_stamp_on_success_even_zero_articles | PASSED       | PASS   |
| no stamp on failure (cookie-dead, sys.exit(2))        | pytest test_scan_last_scanned.py::test_no_stamp_on_failure           | PASSED       | PASS   |
| staleness SELECT orders by last_scanned_at (NULL-first, oldest, name) | pytest test_scan_last_scanned.py::test_staleness_orders_by_last_scanned_at | PASSED | PASS   |
| just-scanned account rotates to back                  | pytest test_scan_last_scanned.py::test_just_scanned_rotates_to_back  | PASSED       | PASS   |
| existing staleness selection (null-first-then-oldest) | pytest test_scan_max_accounts.py::test_staleness_selection_null_first_then_oldest | PASSED | PASS |
| existing default path no truncation                   | pytest test_scan_max_accounts.py::test_default_path_no_truncation    | PASSED       | PASS   |
| existing argparse max_accounts int                    | pytest test_scan_max_accounts.py::test_argparse_max_accounts_int     | PASSED       | PASS   |
| existing argparse max_accounts absent is none         | pytest test_scan_max_accounts.py::test_argparse_max_accounts_absent_is_none | PASSED | PASS |

Full run: `8 passed in 2.28s` — confirmed on main branch, in-repo files (not worktree).

---

### Scope Boundary Check

`git diff 5762cea..4683c9a --name-only` output:
```
batch_scan_kol.py
tests/unit/test_scan_last_scanned.py
```

Exactly 2 files. No scope creep.

---

### Anti-Patterns Found

None. No TODO/FIXME/placeholder markers in either modified file. No empty return stubs. The stamp UPDATE is inside a real `if ok:` conditional backed by the actual `ok` boolean from `scan_account()`.

---

### Human Verification Required

None. All must-haves are programmatically verifiable and confirmed.

---

### Gaps Summary

No gaps. All 7 must-have truths verified, both artifacts substantive and wired, 8/8 tests pass on main branch, scope boundary clean.

Operator Phase 2 (Aliyun DB delete of 5 CV accounts + ~371 articles) is explicitly out of scope for this verification per the task prompt.

---

_Verified: 2026-06-29T17:35:00Z_
_Verifier: Claude (gsd-verifier)_
