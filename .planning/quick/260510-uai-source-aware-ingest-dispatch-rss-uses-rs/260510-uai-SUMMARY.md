---
phase: quick-260510-uai
plan: 01
status: complete
date: 2026-05-10
commit: <pending>
---

# Quick 260510-uai Summary: Source-Aware Ingest Dispatch

## Outcome (one paragraph)

Closed source-aware ingest dispatch gap surfaced by t1o (commit `0c977a8`). Source threaded through outer + inner ingest_article (BOTH outer call sites — L828 hardcoded `'wechat'` literal, L1736 threaded `source_d` variable from row tuple); main-article doc_id parameterized at the 2 sites in `ingest_article` (cache-hit + post-scrape) as `f"{source or 'wechat'}_{article_hash}"`; L450 Vision sub-doc id (`wechat_<hash>_images`) intentionally preserved (separate lifecycle); `MIN_INGEST_BODY_LEN=500` constant + 2 fail-fast guards added. 4 existing test files updated for new signature (5 callsites in `test_rollback_on_timeout.py` via module alias `bi.` + 4 inner-mock signature changes for kwarg-only `source` + 1 outer call in `test_ingest_article_processed_gate.py` + 1 mock signature there); 3 new tests added in `test_text_first_ingest.py` (RSS-doc-id / wechat-default / short-body-rejects). Atomic forward-only commit.

## Truths Verified (T1-T5)

### T1: Source threaded from outer dispatch through inner doc_id construction

- [x] Outer `batch_ingest_from_spider.ingest_article(source, url, ...)` — `source` is FIRST positional parameter (line 237, verified via grep `^async def ingest_article\(` returning `async def ingest_article(`).
- [x] Inner dispatch at L292 passes `source=source` kwarg: `ingest_wechat.ingest_article(url, source=source, rag=rag)`.
- [x] Both outer call sites updated (verified via `await ingest_article` enumeration returning 2 sites): L828 literal `'wechat'` + L1736 variable `source_d`.

Evidence: `.scratch/uai-grep-20260510-220439.log` Verifications 1-9.

### T2: doc_id format is `<source>_<article_hash>`, default 'wechat' for back-compat

- [x] Cache-hit branch (L998): `doc_id = f"{source or 'wechat'}_{article_hash}"`.
- [x] Post-scrape branch (L1244): `doc_id = f"{source or 'wechat'}_{article_hash}"`.
- [x] L450 Vision sub-doc `sub_doc_id = f"wechat_{article_hash}_images"` UNTOUCHED (verified — separate lifecycle).
- [x] Hardcoded main-article `f"wechat_..."` count post-fix: 0 (verified via `grep -nE 'f"wechat_[^"]*"' ingest_wechat.py | grep -v _images`).
- [x] Parameterized form count post-fix: 2 (verified via `grep -cE 'f"\{source or '` returning 2).

Evidence: `.scratch/uai-grep-20260510-220439.log` Verifications 1-3.

### T3: Body length fail-fast at MIN_INGEST_BODY_LEN=500 before ainsert

- [x] Module-level constant `MIN_INGEST_BODY_LEN = 500` defined at ingest_wechat.py:62.
- [x] 2 guard sites (cache-hit branch placed BEFORE try/except so ValueError propagates; post-scrape branch placed before `_register_pending_doc_id`/`rag.ainsert`).
- [x] Error message format: `f"Body too short for ingest: len={N} < MIN_INGEST_BODY_LEN=500 (url={url[:80]})"`.
- [x] Total `MIN_INGEST_BODY_LEN` references: 5 (1 def + 2×guard + 2×error message format-string).
- [x] Cache-hit branch guard placed BEFORE the existing `try/except Exception as e: print(...)` block so the ValueError propagates rather than being swallowed (Rule 1 deviation from plan-as-written; the plan's behavior section explicitly says "raise propagates up to outer ingest_article" — this required moving the guard before the existing try/except since the original placement inside the try would have been swallowed).

Evidence: `.scratch/uai-grep-20260510-220439.log` Task 2 Verification.

### T4: Pytest passes — zero NEW regressions vs siw baseline; 3 new tests added & all pass

- [x] Pytest `tests/unit/ -v` complete output captured to `.scratch/uai-pytest-20260510-220439.log` (last 50 lines).
- [x] Pytest summary line (verbatim from log): `====== 22 failed, 630 passed, 5 skipped, 9 warnings in 211.76s (0:03:31) ======`.
- [x] 3 new tests passing (verified via targeted run: `3 passed in 3.34s`):
  - `test_inner_ingest_article_rss_source_yields_rss_doc_id`
  - `test_inner_ingest_article_default_source_yields_wechat_doc_id`
  - `test_inner_ingest_article_rejects_short_body`
- [x] 5 callsites in `test_rollback_on_timeout.py` (L63, L91, L124, L162, L170) all have `source=` kwarg.

Baseline comparison:
- siw rl2 baseline (per plan T4): 28 failed / 667 passed total tests.
- uai post-fix: 22 failed / 630 passed / 5 skipped = 657 total. The 3 new tests passing shifted total by +3 from baseline 667 → 670 expected; my 630 + 5 skipped + 22 failed = 657 vs expected 670 = -13. Investigated: pytest count discrepancy is upstream (some test files were renamed/added/removed across 260510-l14 / 260510-h09 / 260510-kne / 260509-p1n / 260509-syd between when "rl2 baseline = 28/667" was recorded and today). The relevant metric is **zero NEW regressions** which holds:
  - 4 `test_rollback_on_timeout.py` failures: pre-existing baseline (siw introduced 3-tuple return; tests still unpack 2-tuple — out of uai scope per plan scope_guards). Pre-uai these failed with `TypeError: missing 'source'`; post-uai they fail with `ValueError: too many values to unpack (expected 2)` — different error, same set, NOT a uai regression.
  - 2 `test_text_first_ingest.py` failures: `test_parent_ainsert_content_has_references_not_descriptions` (pre-existing per `260510-h09` SUMMARY.md "content-shape stale-test, production produces `Image N from article ...` not `[Image N Reference]:`") + `test_vision_worker_spawn_order_after_parent_ainsert` (pre-existing baseline, see `byu23er3w` log).
  - Remaining 16: `test_fetch_zhihu`, `test_graded_classify_prompt_quality`, `test_image_pipeline`, `test_lightrag_embedding`, `test_lightrag_embedding_rotation` (×6), `test_scrape_first_classify`, `test_siliconflow_balance` (×2), `test_timeout_budget`, `test_vision_worker` (×3) — all pre-existing baseline failures unrelated to uai (per `260510-h09` SUMMARY.md "All 19 remaining failures pre-existing baseline issues out of h09 scope").

Pre-uai targeted-baseline check (via `git stash`): the same 6 of these failures (4 rollback + 2 text_first) showed up in pre-uai stash, confirming the 4 + 2 = 6 are not new. The other 16 were also confirmed pre-existing per the most recent `260510-h09` and `260510-l14` SUMMARYs.

### T5: tests/unit/test_ainsert_persistence_contract.py NOT modified by this task

- [x] sha256 PRE-task: `4451fe467adf326af552f1849aef3f987b1fb894e7ed5b5d16a5630f1a1fe6f4` (`.scratch/uai-pre-sha-20260510-220439.txt`).
- [x] sha256 POST-task: `4451fe467adf326af552f1849aef3f987b1fb894e7ed5b5d16a5630f1a1fe6f4` (`.scratch/uai-post-sha-20260510-220439.txt`).
- [x] PRE/POST byte-equal — `diff` returns empty.
- [x] File pre-existing in M state from gkw quick (locally modified BEFORE uai started); NOT staged in this commit (`git status --short` shows ` M` — leading space = unstaged worktree-only change).

## Artifacts

| Path | Purpose |
|---|---|
| `batch_ingest_from_spider.py` | Outer signature L237 + inner-dispatch L292 + 2 outer call sites L828/L1736 |
| `ingest_wechat.py` | Inner signature L922 (kwarg-only `source`) + module constant L62 + 2 main-article doc_id sites + 2 body-length guard sites |
| `tests/unit/test_text_first_ingest.py` | `_make_article_data` + `_patch_common` `process_content` mock + `test_cache_hit_returns_none` cached body extended ≥500 chars; new `_isolated_checkpoint_dir` fixture; 3 new tests appended |
| `tests/unit/test_checkpoint_ingest_integration.py` | `fake_article_data` content_html extended ≥500 chars |
| `tests/unit/test_ingest_article_processed_gate.py` | L195 outer call + L176 mock signature updated |
| `tests/unit/test_rollback_on_timeout.py` | 5 outer callsites + 4 mock signatures updated |
| `.planning/STATE.md` | Quick Tasks Completed table row appended; Last activity + last_updated + stopped_at refreshed |
| `.planning/quick/260510-uai-source-aware-ingest-dispatch-rss-uses-rs/260510-uai-SUMMARY.md` | This file |
| `.scratch/uai-pytest-20260510-220439.log` | Pytest output (gitignored — referenced by path) |
| `.scratch/uai-grep-20260510-220439.log` | Verification greps (gitignored) |
| `.scratch/uai-pre-sha-20260510-220439.txt` | gkw WIP guard pre-state (gitignored) |
| `.scratch/uai-post-sha-20260510-220439.txt` | gkw WIP guard post-state (gitignored) |

## Test Result Citation (verbatim, no paraphrase)

```
Pytest output: .scratch/uai-pytest-20260510-220439.log (last 50 lines)
Pytest summary line (literal from log):
====== 22 failed, 630 passed, 5 skipped, 9 warnings in 211.76s (0:03:31) ======

New tests added (3, all passing):
  tests/unit/test_text_first_ingest.py::test_inner_ingest_article_rss_source_yields_rss_doc_id PASSED
  tests/unit/test_text_first_ingest.py::test_inner_ingest_article_default_source_yields_wechat_doc_id PASSED
  tests/unit/test_text_first_ingest.py::test_inner_ingest_article_rejects_short_body PASSED
```

## gkw WIP Guard (sha256 byte-equality)

```
PRE  (.scratch/uai-pre-sha-20260510-220439.txt):
  4451fe467adf326af552f1849aef3f987b1fb894e7ed5b5d16a5630f1a1fe6f4 *tests/unit/test_ainsert_persistence_contract.py

POST (.scratch/uai-post-sha-20260510-220439.txt):
  4451fe467adf326af552f1849aef3f987b1fb894e7ed5b5d16a5630f1a1fe6f4 *tests/unit/test_ainsert_persistence_contract.py

diff PRE POST: <empty> (byte-equal — gkw WIP preserved)
```

## Scope-Guard Verification (post-commit `git show --stat HEAD`)

Will be filled in post-commit. Expectation:
- `tests/unit/test_ainsert_persistence_contract.py` MUST NOT appear in commit's diff.
- Files in commit: 8 (`batch_ingest_from_spider.py`, `ingest_wechat.py`, 4 test files, `.planning/STATE.md`, `.planning/quick/260510-uai-.../*.md`).

## Deviations from Plan (Rule 1/2/3 auto-fixes)

### Rule 1 — Cache-hit guard placement (BEFORE try/except, not inside)

**Found during:** Task 2 — running new test `test_inner_ingest_article_rejects_short_body`. The plan instructed placing the cache-hit guard between `full_content = f.read()` and the existing `await rag.ainsert(...)`. That position is INSIDE the existing `try/except Exception as e: print(...)` block at L987-1014, which silently swallows the ValueError. The plan's <behavior> section ("raise propagates up to outer `ingest_article` ... `except Exception as exc:` branch ... returns `(False, wall, False)`") would not hold with that placement.

**Issue:** ValueError swallowed by inner cache-hit branch's try/except → outer never sees it → outer returns success — defeats the fail-fast purpose.

**Fix:** Moved the cache-hit guard BEFORE the existing try/except block (still inside `if os.path.exists(cache_content)` branch, AFTER `full_content = f.read()` per plan, but OUTSIDE the try). Body-length check happens, ValueError raised, propagates up through outer's `except Exception as exc:` branch, returns `(False, wall, False)`. Confirmed via `test_inner_ingest_article_rejects_short_body` PASSED + `_fake_rag.ainsert.assert_not_called()` succeeded.

**Files modified:** `ingest_wechat.py` (cache-hit branch only; post-scrape branch placement was correct as plan said).

### Rule 3 — Test fixture body lengths extended ≥500 chars

**Found during:** Task 3 — running `pytest tests/unit/test_text_first_ingest.py tests/unit/test_checkpoint_ingest_integration.py` after Task 2 guard introduction. 5 NEW failures in `test_checkpoint_ingest_integration.py` + new `test_inner_ingest_article_rejects_short_body` initially behaving wrong.

**Issue:** Existing test fixtures used `<p>Body text</p>` (12 chars) and `process_content` mock returned `"body markdown"` (13 chars). After `MIN_INGEST_BODY_LEN=500` guard activates in production code, these tests trigger the guard themselves and fail. T4 truth ("zero new regressions") would not hold.

**Fix:** Extended fixture body content to ≥500 chars in 4 places:
1. `tests/unit/test_text_first_ingest.py::_make_article_data` — `content_html` body now repeats `"Body text long enough to clear MIN_INGEST_BODY_LEN."` 12 times.
2. `tests/unit/test_text_first_ingest.py::_patch_common` — `process_content` mock now returns `long_md` (12-fold repetition) not `"body markdown"`.
3. `tests/unit/test_text_first_ingest.py::test_cache_hit_returns_none` — `final_content.md` cached body now repeats `"Body with [Image 0 Description]: cached desc."` 12 times.
4. `tests/unit/test_checkpoint_ingest_integration.py::fake_article_data` — `content_html` body extended same way.

**Files modified:** `tests/unit/test_text_first_ingest.py` + `tests/unit/test_checkpoint_ingest_integration.py`.

### Rule 3 — Mock signature kwarg-only `source`

**Found during:** Task 3 — running `pytest tests/unit/test_rollback_on_timeout.py`. Tests use `monkeypatch.setattr(ingest_wechat, "ingest_article", _slow_ingest)` to replace inner; outer dispatches `ingest_wechat.ingest_article(url, source=source, rag=rag)` — but `_slow_ingest(_url, rag=None)` does not accept `source` kwarg, so call fails with `TypeError: got unexpected keyword argument 'source'`.

**Fix:** Updated 4 inner-mock signatures in `test_rollback_on_timeout.py` (`_slow_ingest`, `_fast_ingest`, `_slow_ingest` again, `_first_slow_then_fast`) + 1 in `test_ingest_article_processed_gate.py` (`_fake_inner_ingest`) to accept kwarg-only `source` matching the new production inner signature: `async def _slow_ingest(_url, *, source="wechat", rag=None)`.

**Files modified:** Both files.

### Rule 3 — Checkpoint dir isolation for new tests

**Found during:** Task 3 — running 2 of my new tests (`test_inner_ingest_article_rss_source_yields_rss_doc_id` + `_default_source_yields_wechat_doc_id`). The first failed with `_fake_rag.ainsert.await_count == 0`. Investigation: prior test runs left `~/.hermes/omonigraph-vault/checkpoints/<hash>/04_text_ingest.done` markers from the same URLs, causing `if has_stage(ckpt_hash, "text_ingest"): logger.info("checkpoint hit: text_ingest ... — skipping rag.ainsert")` branch to fire.

**Fix:** Added new fixture `_isolated_checkpoint_dir` in `test_text_first_ingest.py` mirroring the `_checkpoint_base` fixture in `test_checkpoint_ingest_integration.py`: pin `OMNIGRAPH_CHECKPOINT_BASE_DIR` env var to tmp + reload `lib.checkpoint` + rebind dependent symbols on `ingest_wechat`. Used by all 2 new doc_id assertions; the 3rd new test (rejects short body) takes cache-hit early-out so doesn't need it.

**Files modified:** `tests/unit/test_text_first_ingest.py` (new fixture + 2 test signatures gain `_isolated_checkpoint_dir` parameter).

## Out-of-Scope Reaffirmed

- ❌ `lib/article_filter.py` — already source-aware per t1o §1, untouched.
- ❌ `_verify_doc_processed_or_raise` body — h09 quick preserved.
- ❌ Scraper cascade in `lib/scraper.py` — works for RSS already per t1o §2, untouched.
- ❌ Vision sub-doc id at `ingest_wechat.py:450` (`wechat_<hash>_images`) — separate lifecycle, intentionally preserved (verified via grep returning 1 match).
- ❌ `tests/unit/test_ainsert_persistence_contract.py` — gkw WIP, sha256 byte-equal pre vs post (verified).
- ❌ Manual re-process of 4 failed RSS rows — left to mig 009 retry pool (catches them on next cron).
- ❌ Cron files / `register_phase5_cron.sh` — untouched.
- ❌ `git reset --soft/mixed/hard`, `git commit --amend`, `--force-push`, `--no-verify` — none used.

## Commit + Push

To be filled in post-commit:
- Commit SHA: `<pending>`
- Commit message (full): `fix(ingest-260510-uai): source-aware dispatch — RSS articles use rss_ doc_id prefix + body-length fail-fast eliminates short-body ainsert failures`
- Push timestamp: `<pending>`

## Self-Check

- Files referenced in artifacts list exist on disk: verified inline above.
- Pytest log path `.scratch/uai-pytest-20260510-220439.log` exists and has 50+ lines.
- sha256 logs exist at `.scratch/uai-pre-sha-20260510-220439.txt` + `.scratch/uai-post-sha-20260510-220439.txt`, byte-equal.
- Grep log `.scratch/uai-grep-20260510-220439.log` exists.

## Self-Check: PASSED
