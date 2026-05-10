---
phase: quick-260510-oxq
verified: 2026-05-10T18:30:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Quick 260510-oxq Verification Report

**Task Goal:** Eliminate outer/inner double-INSERT design smell on ingestions table — outer is sole writer, gates on doc_confirmed bool from inner
**Verified:** 2026-05-10T18:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Inner ingest_wechat.ingest_article no longer writes to the ingestions table | VERIFIED | `grep -n "INSERT OR IGNORE INTO ingestions" ingest_wechat.py` → exit code 1, zero matches |
| 2 | Outer batch_ingest_from_spider.ingest_article returns a 3-tuple (success, wall, doc_confirmed) | VERIFIED | Line 242: `) -> tuple[bool, float, bool]:` confirmed; all 4 return points emit 3-tuples (lines 270, 289, 318, 323) |
| 3 | Both main-loop call sites gate status='ok' on BOTH success AND doc_confirmed | VERIFIED | Lines 822+827 (--from-spider path) and lines 1730+1735 (--from-db path): 2 unpack sites + 2 `elif success and doc_confirmed:` gates confirmed |
| 4 | Existing pytest unit test for outer-catches-inner-RuntimeError still passes after signature change | VERIFIED | SUMMARY cites `.scratch/siw-pytest-1778447810.log`; `test_outer_catches_inner_runtime_error_returns_failed` PASSED with 3-tuple unpack + `assert doc_confirmed is False` at line 204 |
| 5 | Inner's UPDATE articles SET content_hash and UPDATE articles SET enriched statements remain unchanged | VERIFIED | Lines 1306 and 1311 of ingest_wechat.py both present; `doc_confirmed = True` at line 1298 preserved |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `ingest_wechat.py` | INSERT OR IGNORE block removed; `doc_confirmed = True` preserved | VERIFIED | Zero matches for INSERT OR IGNORE INTO ingestions; `doc_confirmed = True` at line 1298; UPDATE articles statements at lines 1306 and 1311 intact |
| `batch_ingest_from_spider.py` | Returns `tuple[bool, float, bool]`; 2 call sites unpack 3 values; 2 `elif success and doc_confirmed:` gates | VERIFIED | Annotation at line 242; 4 return points at 270/289/318/323; unpack at 822+1730; gates at 827+1735 |
| `tests/unit/test_ingest_article_processed_gate.py` | 3-tuple unpack + `assert doc_confirmed is False` | VERIFIED | Line 195: `success, wall, doc_confirmed = await bif.ingest_article(...)`; line 204: `assert doc_confirmed is False` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| ingest_wechat.ingest_article (inner) | batch_ingest_from_spider.ingest_article (outer) | inner returns cleanly → outer sets doc_confirmed=True; inner raises RuntimeError → outer's generic Exception branch → doc_confirmed=False | WIRED | Outer's return at line 289 yields `True, time.time()-t_start, True`; at lines 318+323 yields `False, wall, False`; inner no longer writes |
| batch_ingest_from_spider.ingest_article (outer) | main loop status assignment (sites #1 line 827, #2 line 1735) | `elif success and doc_confirmed: status = 'ok'` | WIRED | Both `elif success and doc_confirmed:` gates confirmed at lines 827 and 1735 |
| main loop --from-db path | ingestions table (sole writer) | INSERT OR REPLACE at line 1746 unchanged; outer is sole writer because inner's INSERT is gone | WIRED | INSERT OR REPLACE INTO ingestions present at line 1746 (--from-db path); ingest_wechat.py has zero INSERT INTO ingestions matches |

### Commit Hygiene

**Refactor commit:** `7e91235 refactor(ingest-260510-siw): eliminate outer/inner double-INSERT — outer is sole writer for ingestions, gates on doc_confirmed bool from inner`

**Diff stat (HEAD~2 → HEAD~1, i.e. the refactor commit):**
```
 .planning/STATE.md                                 |   3 +-
 .planning/quick/260510-oxq-.../260510-oxq-PLAN.md  | 404 +++++++++++++++++++++
 .planning/quick/260510-oxq-.../260510-oxq-SUMMARY.md | 133 +++++++
 batch_ingest_from_spider.py                        |  18 +-
 ingest_wechat.py                                   |   5 -
 tests/unit/test_ingest_article_processed_gate.py   |   3 +-
 6 files changed, 550 insertions(+), 16 deletions(-)
```

Only the 6 allowed paths appear. Zero matches for `ainsert_persistence_contract`, `_verify_doc_processed_or_raise`, or `migrations/` in the diff.

### Out-of-Scope Confirmed Untouched

- `tests/unit/test_ainsert_persistence_contract.py` — NOT in diff (parallel quick 260510-gkw has WIP)
- `_verify_doc_processed_or_raise` body — NOT in diff
- Pattern A poll budget — not added
- Vision sub-doc verification logic — not touched
- `ingestions` table schema / migration files — not in diff
- Outer try/except structure — unchanged; only return statement values extended

### Pre-existing Test Failures (not regressions)

The SUMMARY documents 2 failures in `test_text_first_ingest.py`:
- `test_parent_ainsert_content_has_references_not_descriptions`
- `test_vision_worker_spawn_order_after_parent_ainsert`

These call inner `ingest_wechat.ingest_article` whose signature is unchanged by this quick. The SUMMARY states these were confirmed pre-existing by running against unmodified code (git stash → run → stash pop). These are not regressions from this change.

### Anti-Patterns Found

None. The change is purely subtractive in ingest_wechat.py (5 lines removed) and minimally additive in batch_ingest_from_spider.py (3-tuple widening). No placeholders, no hardcoded data, no TODOs introduced.

## Verdict

Goal achieved. Outer `batch_ingest_from_spider.ingest_article` is the sole writer for the `ingestions` table. The inner's INSERT OR IGNORE block is gone. The `doc_confirmed` bool propagates from inner to outer via the 3-tuple return signature. Both main-loop call sites gate `status='ok'` on `success AND doc_confirmed`, eliminating the split-brain race condition. All 5 must-have truths are observable in the working tree. The refactor commit (`7e91235`) touches only the 3 production files plus planning artifacts — no scope creep.

---

_Verified: 2026-05-10T18:30:00Z_
_Verifier: Claude (gsd-verifier)_
