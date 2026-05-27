---
phase: quick-260511-lmc
verified: 2026-05-11T17:15:00-03:00
status: passed
score: 6/6 must-haves verified
gaps: []
---

# Quick 260511-lmc: h09 TOCTOU Race Fix Verification Report

**Task Goal:** Fix h09 TOCTOU race — stable-state + error_msg guard before returning processed
**Verified:** 2026-05-11T17:15:00-03:00
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `_verify_doc_processed_or_raise` returns True only when status='processed' AND error_msg is empty/null | ✓ VERIFIED | `ingest_wechat.py:136-168`: error_msg guard at lines 141-148 fires before stable re-poll; stable re-poll at lines 152-176 checks `not stable_error_msg` before `return` |
| 2 | A 'processed' entry with error_msg set causes the helper to continue retrying | ✓ VERIFIED | `ingest_wechat.py:144-148`: `if error_msg: ... continue`. Test `test_processed_with_error_msg_continues_retry` and `test_processed_enum_member_with_error_msg` both pass — 3 retries exhausted, RuntimeError raised |
| 3 | After seeing 'processed' + no error_msg, re-poll after STABLE_VERIFY_DELAY_S and confirm still 'processed' + no error_msg before returning | ✓ VERIFIED | `ingest_wechat.py:152-168`: `await asyncio.sleep(stable_delay_s)` then second `aget_docs_by_ids` call, returns only if `_status_is_processed(stable_status_val) and not stable_error_msg`. `STABLE_VERIFY_DELAY_S = float(os.getenv("OMNIGRAPH_STABLE_VERIFY_DELAY", "5.0"))` at line 63 |
| 4 | If stable re-check sees status flipped to non-processed, continue retry loop | ✓ VERIFIED | `ingest_wechat.py:170-176`: `last_status_val = f"unstable-processed: recheck=..."` then `continue`. Test `test_processed_stable_recheck_sees_failed` passes — 6 calls, RuntimeError raised |
| 5 | 11/11 tests pass (6 original + 5 new TOCTOU race tests) | ✓ VERIFIED | Live pytest run: `11 passed in 4.64s`. Log at `.scratch/h09race-pytest-green-20260511-160944.log` |
| 6 | No changes to batch_ingest_from_spider, checkpoint, deepseek timeout, MIN_INGEST_BODY_LEN, or lib/ | ✓ VERIFIED | `git show 8adbfd0 --stat` shows only `ingest_wechat.py` and `tests/unit/test_ingest_article_processed_gate.py` modified (plus planning docs). `PROCESSED_VERIFY_MAX_RETRIES=30`, `PROCESSED_VERIFY_BACKOFF_S=2.0`, `MIN_INGEST_BODY_LEN=500` all unchanged |

**Score:** 6/6 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `ingest_wechat.py` | Updated `_verify_doc_processed_or_raise` with stable-state + error_msg guard, `STABLE_VERIFY_DELAY_S` constant | ✓ VERIFIED | `STABLE_VERIFY_DELAY_S` at line 63; `stable_delay_s` param at line 82; error_msg guard at lines 141-148; stable re-poll block at lines 152-176 |
| `tests/unit/test_ingest_article_processed_gate.py` | 5 new TOCTOU race tests, including `test_processed_with_error_msg_continues_retry` | ✓ VERIFIED | Tests 7-11 (lines 251-374): all 5 named tests present and passing |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `_verify_doc_processed_or_raise` | `rag.aget_docs_by_ids` | stable-check: re-poll after delay when first 'processed' seen | ✓ WIRED | `ingest_wechat.py:152-154`: `await asyncio.sleep(stable_delay_s)` then `stable_statuses = await rag.aget_docs_by_ids([doc_id])` |
| `_verify_doc_processed_or_raise` | `entry.error_msg / entry.get('error_msg')` | error_msg guard before returning True | ✓ WIRED | `ingest_wechat.py:141-143`: `error_msg = getattr(entry, "error_msg", None); if error_msg is None and isinstance(entry, dict): error_msg = entry.get("error_msg")` — both object and dict paths covered |

---

### Behavioral Spot-Checks

| Behavior | Result | Status |
|----------|--------|--------|
| 11/11 tests pass live | `11 passed in 4.64s` (verified live run) | ✓ PASS |
| Commit `8adbfd0` present with correct message | `fix(ingest-260511-h09r): h09 TOCTOU race — verify processed is stable + error_msg empty before returning...` | ✓ PASS |
| `STABLE_VERIFY_DELAY_S` env-overridable via `OMNIGRAPH_STABLE_VERIFY_DELAY` | `float(os.getenv("OMNIGRAPH_STABLE_VERIFY_DELAY", "5.0"))` at line 63 | ✓ PASS |
| Scratch logs cited in commit body | `.scratch/h09race-pytest-green-20260511-160944.log` present and referenced in commit body | ✓ PASS |

---

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| H09-RACE-FIX | TOCTOU race fix — stable-state + error_msg guard before returning processed | ✓ SATISFIED | Combined Option C guard implemented and tested; eliminates 2026-05-11 mystery rows from DeepSeek 402 partial-failure |

---

### Anti-Patterns Found

None. No TODO/FIXME/placeholder patterns. No empty implementations. No prohibited file changes. The 3 updated existing tests were a necessary consequence of the new stable re-poll behavior (test mocks needed an extra side_effect entry per `processed` observation).

---

### Human Verification Required

None. All checks are fully automated via pytest.

---

### Gaps Summary

No gaps. All 6 must-have truths verified against the actual codebase. The implementation exactly matches the plan's Option C specification: error_msg guard (Option B) fires first, then stable re-poll (Option A) only when no error_msg. Both dict and dataclass-like entry paths are covered. The `stable_delay_s=0.0` test injection parameter keeps the suite fast. TDD sequence confirmed via RED log at `.scratch/h09race-pytest-red-20260511-154759.log` and GREEN log at `.scratch/h09race-pytest-green-20260511-160944.log`.

---

_Verified: 2026-05-11T17:15:00-03:00_
_Verifier: Claude (gsd-verifier)_
