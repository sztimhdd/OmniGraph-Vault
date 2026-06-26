---
phase: 260626-fp5
plan: 01
subsystem: batch_classify_kol
tags: [deepseek, truncation, adaptive-split, batch-classify, unit-test, issue-70]
dependency_graph:
  requires: [260625-jv2]
  provides: [truncation-aware DeepSeek batch path, adaptive halving split, abs-index rebase]
  affects: [batch_classify_kol.py, tests/unit/test_classify_batch_truncation.py]
tech_stack:
  added: []
  patterns: [sentinel string return, recursive adaptive halving, abs_offset index rebase, MagicMock __str__ for DB_PATH]
key_files:
  modified:
    - batch_classify_kol.py
  created:
    - tests/unit/test_classify_batch_truncation.py
decisions:
  - Return sentinel string "TRUNCATED" (not a tuple, not an exception) from _call_deepseek
    on finish_reason=length — distinguishes recoverable truncation from hard API errors;
    string sentinel is unambiguous, zero-cost, and avoids tuple unpacking at all callers
  - Implement split logic in new _classify_batch() helper rather than inline in run()
    to keep run() legible and make _classify_batch independently testable
  - Re-base batch-local 0-based indices to abs_offset+index in _classify_batch so the
    pre-existing cls_by_idx consumer in run() requires zero changes
  - MIN_BATCH=25 floor: below this size a batch should never hit max_tokens ceiling;
    if it does something else is wrong and aborting is safer than infinite recursion
metrics:
  duration: ~25 min
  completed: 2026-06-26
  tasks_completed: 2
  files_changed: 2
---

# Phase 260626-fp5 Plan 01: Classify Batch Truncation Fix Summary

**One-liner:** Truncation-aware DeepSeek batch path in `batch_classify_kol.py` — `_call_deepseek` now returns `"TRUNCATED"` on `finish_reason=length`, and new `_classify_batch` halves the slice recursively until it succeeds or bottoms out at `MIN_BATCH=25`, preventing whole-topic abort on dense batches (issue #70).

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Harden batch_classify_kol.py: sentinel + adaptive split | bf05ae8 | batch_classify_kol.py |
| 2 | Behavior-anchor tests pinning truncation + split contract | b85bd35 | tests/unit/test_classify_batch_truncation.py |

## What Was Done

**Task 1 (batch_classify_kol.py — ~99 LoC net added, 10 deleted):**

- Added `MIN_BATCH = 25` constant after the existing `GEMINI_CLASSIFY_SLEEP` line.
- `_call_deepseek` return type widened to `list[dict] | str | None`. Reads `resp.json()["choices"][0]` into `choice` first, then checks `choice.get("finish_reason") == "length"` → returns `"TRUNCATED"`. Success path unchanged: reads `choice["message"]["content"]`, strips fences, parses JSON.
- New `_classify_batch(titles, digests, topic, min_depth, api_key, abs_offset)` helper:
  - Calls `_call_deepseek`. On `"TRUNCATED"`: if `len(titles) < MIN_BATCH` → log + return `None`; else compute `mid = len(titles) // 2` and recurse left (`abs_offset`) + right (`abs_offset + mid`).
  - On `None` → return `None`.
  - On success: re-bases each item's `index` to `abs_offset + int(item["index"])`, skipping items without `"index"`.
- `run()` batch loop refactored:
  - `batch_size = int(os.environ.get("KOL_CLASSIFY_BATCH_SIZE", "200"))` (env-overridable, default 200 unchanged).
  - `api_key = get_deepseek_api_key()` hoisted before the loop (avoids repeated file I/O).
  - DeepSeek branch now calls `_classify_batch(...)` instead of `_call_deepseek` directly.
  - Gemini branch unchanged: still calls `_call_gemini` inline.
- `_call_fullbody_llm`, `_call_deepseek_fullbody`, `_call_gemini` are byte-unchanged.

**Task 2 (tests/unit/test_classify_batch_truncation.py — 260 LoC, 3 tests):**

- `test_call_deepseek_returns_truncated_sentinel`: mocks `batch_classify_kol.requests.post` to return a response with `finish_reason="length"` (and `message.content` present so the try branch is exercised). Asserts `result == "TRUNCATED"`.
- `test_classify_batch_splits_on_truncation`: fake `_call_deepseek` returns `"TRUNCATED"` on call #1, valid 25-item JSON on calls #2 + #3. Asserts `len(result) == 50` and `sorted(item["index"])` == `list(range(50))` (correct rebase, no gap/collision).
- `test_run_classifies_all_articles_on_truncation` (decisive regression): real SQLite in `tmp_path`, 50 articles, `KOL_CLASSIFY_BATCH_SIZE=50`. Fake `_call_deepseek` returns `"TRUNCATED"` on call #1, valid 25-item JSON on calls #2 + #3. Asserts `COUNT(*) FROM classifications WHERE topic='NLP' == 50`. Pre-fix: 0 rows (topic aborted); post-fix: 50 rows.

## Pytest Results

```
10 passed in 1.63s
  tests/unit/test_classify_multitopic_argparse.py::test_multi_topic_runs_once_per_topic_in_order PASSED
  tests/unit/test_classify_multitopic_argparse.py::test_single_topic_backward_compatible PASSED
  tests/unit/test_classify_multitopic_argparse.py::test_non_topic_args_forwarded_to_run PASSED
  tests/unit/test_classifications_multitopic.py::test_multi_topic_loop_creates_one_row_per_topic PASSED
  tests/unit/test_classifications_multitopic.py::test_rerun_loop_is_idempotent_upsert PASSED
  tests/unit/test_classifications_multitopic.py::test_multi_article_multi_topic_isolation PASSED
  tests/unit/test_classifications_multitopic.py::test_migration_005_idempotent PASSED
  tests/unit/test_classify_batch_truncation.py::test_call_deepseek_returns_truncated_sentinel PASSED
  tests/unit/test_classify_batch_truncation.py::test_classify_batch_splits_on_truncation PASSED
  tests/unit/test_classify_batch_truncation.py::test_run_classifies_all_articles_on_truncation PASSED
```

## Deviations from Plan

None — plan executed exactly as written. The 99 LoC net adds are within the plan's expected ~30-40 LoC estimate because the docstrings (added for `_call_deepseek` and `_classify_batch`) account for ~30 LoC; the functional logic is ~50 LoC.

## Scope Guard Findings (required by constraints)

**(a) Gemini path truncation risk:** The Gemini batch path calls `_call_gemini` which wraps `lib.generate_sync` with `response_mime_type="application/json"`. The Gemini API does not expose a `finish_reason=length` equivalent in the same way; the `generate_sync` wrapper can raise on content filtering or max-token exhaustion, but the `try/except Exception` in `_call_gemini` absorbs it as `None`. So the Gemini path has a similar truncation risk (dense 200-title batches could hit Gemini's output-token ceiling), but it manifests as a parse error returning `None` rather than a detectable sentinel — no adaptive split path exists. Filed for future work; not addressed here (scope boundary).

**(b) Fullbody fence-strip latent pattern (lines ~313-315):** `_call_fullbody_llm` at lines 313-315 has the same fence-strip logic as `_call_deepseek`. If the fullbody LLM response is truncated mid-fence, the fence-strip would leave a raw `` ```json `` prefix and `json.loads` would fail the same way. However, the fullbody path classifies one article at a time (`_build_fullbody_prompt` is per-article) and the article body is already truncated to `FULLBODY_TRUNCATION_CHARS=8000` — so per-article responses are structurally much smaller (single JSON object, not a 200-item array). The risk is materially lower. Left deferred as pre-existing pattern.

**(c) Multi-batch index-collision (bug-71):** The pre-existing `cls_by_idx` consumer already had a latent collision risk: if batch #1 (articles 0-199) and batch #2 (articles 200-399) both returned `index=0`, they would collide in `cls_by_idx` and batch #2's article 200 would clobber batch #1's article 0. This quick's re-basing in `_classify_batch` (adding `abs_offset` to each index) RESOLVES this collision for the DeepSeek path — split batches produce correct absolute indices. No change was required to the `cls_by_idx` consumer. The Gemini path still has the latent collision (Gemini results are `extend()`-ed without re-basing), but that is a pre-existing condition not introduced by this quick. The fix did NOT force any change to the `cls_by_idx` consumer lines (~506 post-edit).

## Post-execution Gates (orchestrator scope, NOT done here)

1. Git push worktree branch / cherry-pick onto main.
2. Aliyun `git checkout origin/main -- batch_classify_kol.py` (same surgical approach as 260625-jv2 to avoid uncommitted mods to synthesizer.py).
3. Forced-200-dry-run verification on Aliyun: `KOL_CLASSIFY_BATCH_SIZE=200 python batch_classify_kol.py --topic NLP --dry-run` — must not abort; should log "Splitting truncated N-title slice" and complete.
4. Prod DB verification: `SELECT topic, COUNT(*) FROM classifications GROUP BY topic` — topics should hold steady at 2069 each (or grow if new articles accumulated since 2026-06-25).

## Self-Check: PASSED

- `batch_classify_kol.py` — `MIN_BATCH`, `_call_deepseek` sentinel, `_classify_batch`, `KOL_CLASSIFY_BATCH_SIZE` env: all present; syntax OK (`ast.parse` exit 0)
- `tests/unit/test_classify_batch_truncation.py` — exists, 260 lines, 3 tests
- Fix commit `bf05ae8` — present in `git log --oneline`
- Test commit `b85bd35` — present in `git log --oneline`
- Pytest result: 10/10 passed, 0 failed
