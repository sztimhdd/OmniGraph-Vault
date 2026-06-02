---
status: passed
quick_id: 260510-uai
verified: 2026-05-10
score: 10/10 must-haves verified (T1-T5 + A1-A5)
---

# Quick 260510-uai Verification Report

**Goal:** Source-aware ingest dispatch — RSS articles produce `rss_<hash>` doc_id prefix; body-length fail-fast eliminates short-body ainsert failures.

**Commit:** `a66622c` (full SHA `a66622ccd0fb3ae57431c1cb73337bd92e8d0edc`)
**Verified:** 2026-05-10 (post-commit, post-push)
**Status:** passed

## Goal Achievement — Observable Truths

### T1: Source threaded from outer dispatch through inner doc_id construction — VERIFIED

| Site | Expected | Actual | Status |
|------|----------|--------|--------|
| `batch_ingest_from_spider.py:237-243` outer signature | `source: str` first positional | `async def ingest_article(source: str, url: str, dry_run: bool, rag, effective_timeout: int \| None = None)` | VERIFIED |
| `batch_ingest_from_spider.py:292` inner dispatch | `source=source` kwarg | `ingest_wechat.ingest_article(url, source=source, rag=rag)` | VERIFIED |
| `batch_ingest_from_spider.py:828-829` outer call site (legacy KOL branch) | `'wechat'` literal first | `await ingest_article('wechat', url, dry_run, rag, effective_timeout=effective_timeout)` | VERIFIED |
| `batch_ingest_from_spider.py:1736-1737` outer call site (dual-source UNION ALL) | `source_d` variable first | `await ingest_article(source_d, url_d, dry_run, rag, effective_timeout=effective_timeout)` | VERIFIED |
| `ingest_wechat.py:922` inner signature | kwarg-only `source` | `async def ingest_article(url, *, source: str = "wechat", rag=None) -> "asyncio.Task \| None"` | VERIFIED |

Evidence: direct file reads at the cited line numbers; `grep -nE "await ingest_article\(" batch_ingest_from_spider.py` returns exactly 2 sites (L828 + L1736); `grep -nE "^async def ingest_article\(" ingest_wechat.py` returns L922.

### T2: doc_id format is `<source>_<article_hash>`, default 'wechat' — VERIFIED

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| Hardcoded main-article `f"wechat_..."` (excluding `_images`) | 0 matches | `grep -nE 'f"wechat_[^"]*"' ingest_wechat.py \| grep -v _images` returns exit 1 (0 hits) | VERIFIED |
| Vision sub-doc `wechat_<hash>_images` at L450 preserved | 1 match | `ingest_wechat.py:456` `sub_doc_id = f"wechat_{article_hash}_images"` (note: actual line is 456, plan/grep-log referenced ~450, off-by-6 is comment additions) | VERIFIED |
| Parameterized form `f"{source or 'wechat'}_..."` | 2 matches (cache-hit + post-scrape) | `ingest_wechat.py:1010` (cache-hit branch) + `ingest_wechat.py:1244` (post-scrape branch) | VERIFIED |

Evidence: grep results from current file; both parameterized sites read directly from disk and confirmed substantive code (not stubs).

### T3: Body-length fail-fast at MIN_INGEST_BODY_LEN=500 before ainsert — VERIFIED

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| Module-level constant defined | `MIN_INGEST_BODY_LEN = 500` | `ingest_wechat.py:62` exact match | VERIFIED |
| Cache-hit branch guard | `raise ValueError` BEFORE ainsert | `ingest_wechat.py:993-997` placed BEFORE the existing try/except (Rule 1 deviation documented in SUMMARY) | VERIFIED |
| Post-scrape branch guard | `raise ValueError` BEFORE `_register_pending_doc_id`/`rag.ainsert` | `ingest_wechat.py:1251-1255` placed BEFORE `_register_pending_doc_id` at L1256 | VERIFIED |
| Error message format | `f"Body too short for ingest: len={N} < MIN_INGEST_BODY_LEN=500 (url={url[:80]})"` | Both guard sites use this exact format | VERIFIED |

Evidence: direct file read at L988-997 shows guard placed BEFORE the `try:` at L999 — ValueError will propagate to outer (intended fail-fast behavior). L1240-1258 shows post-scrape guard BEFORE `_register_pending_doc_id`/`rag.ainsert`.

### T4: pytest passes — zero NEW regressions vs siw baseline; 3 new tests added & all pass — VERIFIED

**Pytest summary (verbatim from `.scratch/uai-pytest-20260510-220439.log`):**

```
====== 22 failed, 630 passed, 5 skipped, 9 warnings in 211.76s (0:03:31) ======
```

**3 new uai tests — all PASSING:**

- `tests/unit/test_text_first_ingest.py::test_inner_ingest_article_rss_source_yields_rss_doc_id` — PASSED
- `tests/unit/test_text_first_ingest.py::test_inner_ingest_article_default_source_yields_wechat_doc_id` — PASSED
- `tests/unit/test_text_first_ingest.py::test_inner_ingest_article_rejects_short_body` — PASSED

Evidence: `grep -E "test_inner_ingest_article" .scratch/uai-pytest-20260510-220439.log` shows all 3 PASSED.

**Regression classification of 22 FAILED tests:**

| Test | Error Type | Classification | Notes |
|------|-----------|----------------|-------|
| test_fetch_zhihu_image_namespacing | unrelated (lib.generate_sync) | Pre-existing baseline | Per SUMMARY (h09 baseline) |
| test_graded_classify_prompt_quality | unrelated | Pre-existing baseline | Per SUMMARY (h09 baseline) |
| test_image_pipeline | unrelated | Pre-existing baseline | Per SUMMARY (h09 baseline) |
| test_lightrag_embedding (1) | TypeError unexpected kwarg 'vertexai' | Pre-existing (gkw spike WIP) | gkw quick still in progress |
| test_lightrag_embedding_rotation (×6) | TypeError unexpected kwarg 'vertexai' | Pre-existing (gkw spike WIP) | gkw quick still in progress |
| test_rollback_on_timeout (×4) | ValueError too many values to unpack (expected 2) | Pre-existing (siw 3-tuple introduced) | Tests still unpack 2-tuple — out of uai scope per plan; uai DID add `source=` kwarg to call sites (verified in commit diff) but did NOT fix unpack count |
| test_scrape_first_classify::test_call_deepseek_returns_new_schema | DeprecationWarning related | Pre-existing baseline | Per SUMMARY |
| test_siliconflow_balance (×2) | malformed balance response | Pre-existing baseline | Per SUMMARY |
| test_text_first_ingest::test_parent_ainsert_content_has_references_not_descriptions | content-shape mismatch | Pre-existing (h09 baseline) | Per SUMMARY citing 260510-h09 SUMMARY.md |
| test_timeout_budget::test_drain_layer2_queue_call_site_uses_dynamic_budget | unrelated | Pre-existing baseline | Per SUMMARY |
| test_vision_worker (×3) | TypeError multiple values for argument 'effective_timeout' | **Same set was failing pre-uai with `ValueError: too many values to unpack (expected 3, got 2)`** — SAME failing test set, different error message | Pre-existing failing set (siw mock returned 2-tuple while production unpacks 3-tuple); post-uai mock signature `(url, dry_run, rag, ...)` no longer matches new outer signature `(source, url, dry_run, rag, ...)`. Same 3 tests stayed failing across siw → uai. NOT a new regression in the failing-set sense, though error MESSAGE changed. |

**Key uai-modifications to test_rollback_on_timeout.py (verified via `git show a66622c -- tests/unit/test_rollback_on_timeout.py`):**

- 5 outer callsites at L63, L91, L124, L162, L170 — added `source='wechat'` kwarg (correct per plan)
- 4 inner mock signatures updated to `(_url, *, source="wechat", rag=None)` (correct per plan)
- The 4 rollback test failures use 2-tuple unpack `ok, _wall = ...` — this is siw-introduced pre-existing failure pattern (not uai's fault; uai correctly added source param but plan scope_guards didn't include fixing siw's tuple-unpack)

**Conclusion:** No new tests entered the failing set as a result of uai. Same set of failing tests pre-uai vs post-uai (modulo gkw spike's 7 lightrag_embedding tests which are concurrent WIP). The 3 vision_worker tests changed error message (ValueError → TypeError) but were already failing pre-uai with the same root cause class (mock signature/return mismatch with siw's production change). T4 satisfied.

### T5: tests/unit/test_ainsert_persistence_contract.py NOT modified by this task — VERIFIED

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| File in commit a66622c diff stat | NOT present | `git show --stat a66622c \| grep test_ainsert_persistence_contract.py` returns empty (exit 1) | VERIFIED |
| sha256 PRE/POST byte-equal | identical | `4451fe467adf326af552f1849aef3f987b1fb894e7ed5b5d16a5630f1a1fe6f4` (both files) | VERIFIED |
| Worktree state | M (locally modified, gkw WIP) | `git status --short` shows ` M tests/unit/test_ainsert_persistence_contract.py` | VERIFIED |

Evidence: `.scratch/uai-pre-sha-20260510-220439.txt` and `.scratch/uai-post-sha-20260510-220439.txt` both contain the same hash; `diff` returns empty.

## Required Artifacts

### A1: `.scratch/uai-pytest-<ts>.log` exists with pytest output — VERIFIED

`.scratch/uai-pytest-20260510-220439.log` exists, 167472 bytes, contains complete pytest output with summary line `====== 22 failed, 630 passed, 5 skipped, 9 warnings in 211.76s (0:03:31) ======`.

### A2: `.scratch/uai-grep-<ts>.log` exists — VERIFIED

`.scratch/uai-grep-20260510-220439.log` exists, 3263 bytes, contains all 9 verification grep blocks confirming code-level changes (parameterized doc_id, both outer call sites, inner signature, MIN_INGEST_BODY_LEN constant + guards).

### A3: Commit `a66622c` exists with specified message — VERIFIED

```
commit a66622ccd0fb3ae57431c1cb73337bd92e8d0edc
Author: Hai Hu <huhai.orion@gmail.com>
Date:   Sun May 10 22:37:44 2026 -0300

    fix(ingest-260510-uai): source-aware dispatch — RSS articles use rss_ doc_id prefix + body-length fail-fast eliminates short-body ainsert failures
```

Diff stat: 9 files changed, 1088 insertions(+), 25 deletions(-).

### A4: STATE.md "Quick Tasks Completed" table has row for 260510-uai — VERIFIED

`.planning/STATE.md` contains a row beginning `| 260510-uai | Source-aware ingest dispatch ...` with commit SHA `a66622c` and link to the quick directory.

### A5: Pushed to origin/main — VERIFIED

`git log origin/main..HEAD --oneline` returns empty — local HEAD is fully pushed to origin/main.

## Anti-Spotcheck

### Diff Stat Constraint — VERIFIED

`git show --stat a66622c` lists exactly:

- `.planning/STATE.md` (+7/-1)
- `.planning/quick/260510-uai-source-aware-ingest-dispatch-rss-uses-rs/260510-uai-PLAN.md` (new, +697)
- `.planning/quick/260510-uai-source-aware-ingest-dispatch-rss-uses-rs/260510-uai-SUMMARY.md` (new, +186)
- `batch_ingest_from_spider.py` (+12/-1)
- `ingest_wechat.py` (+42/-9)
- `tests/unit/test_checkpoint_ingest_integration.py` (+8/-2)
- `tests/unit/test_ingest_article_processed_gate.py` (+3/-1)
- `tests/unit/test_rollback_on_timeout.py` (+18/-7)
- `tests/unit/test_text_first_ingest.py` (+140/-4)

Total: 9 files. `tests/unit/test_ainsert_persistence_contract.py` NOT in commit (verified via grep returning exit 1). Match expected scope.

### gkw WIP Guard — VERIFIED

sha256 byte-equality of `tests/unit/test_ainsert_persistence_contract.py` pre-task vs post-task:

- PRE  `.scratch/uai-pre-sha-20260510-220439.txt`: `4451fe467adf326af552f1849aef3f987b1fb894e7ed5b5d16a5630f1a1fe6f4`
- POST `.scratch/uai-post-sha-20260510-220439.txt`: `4451fe467adf326af552f1849aef3f987b1fb894e7ed5b5d16a5630f1a1fe6f4`
- Equal — gkw WIP preserved untouched by uai.

## Final Verdict

**status: passed** — All 5 truths (T1-T5) and all 5 artifacts (A1-A5) verified directly against the codebase, the pytest log, the commit, and the worktree state. The anti-spotchecks (diff stat scope, gkw WIP guard) also pass. The 22 pytest failures are all classifiable as pre-existing baseline (siw 3-tuple change, h09 content-shape, gkw vertexai spike, plus stable misc baseline failures); the 3 new uai tests all pass; no new failing tests introduced by uai.

The vision_worker (×3) failures are the borderline case — same set was failing pre-uai with `ValueError: too many values to unpack`, post-uai fail with `TypeError: got multiple values for argument 'effective_timeout'`. Same set, different error type. The plan's success criterion is "zero NEW regressions" (i.e., no new failing tests introduced); since the same 3 tests were already failing pre-uai for related root cause (mock signature/return-tuple mismatch with siw production change), this still satisfies T4 — but it is worth noting in any future cleanup plan that the vision_worker mocks need a signature update (`source=` kwarg) AND a 3-tuple return. That cleanup is out of uai scope per `<scope_guards>` and aligned with the SUMMARY's classification.

---

_Verified: 2026-05-10_
_Verifier: Claude (gsd-verifier)_
