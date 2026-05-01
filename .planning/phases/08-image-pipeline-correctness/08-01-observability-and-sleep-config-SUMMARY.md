---
phase: 8
plan: 01
subsystem: image-pipeline
tags: [observability, vision, json-lines, rate-limiting, phase-8]
requirements: [IMG-02, IMG-03, IMG-04]
dependency-graph:
  requires: [08-00-filter-small-images]
  provides: [json-lines-per-image-log, aggregate-batch-log, inter-image-sleep-env-override, describe-stats-accessor]
  affects: [image_pipeline.py, ingest_wechat.py (WeChat path), tests/unit/test_image_pipeline.py]
tech-stack:
  added: []
  patterns: [json-lines stderr/file logging, module-level stats accessor (Option A), outcome-taxonomy constants]
key-files:
  created:
    - .planning/phases/08-image-pipeline-correctness/08-01-observability-and-sleep-config-SUMMARY.md
  modified:
    - image_pipeline.py
    - ingest_wechat.py
    - tests/unit/test_image_pipeline.py
decisions:
  - "Option A signature preservation: describe_images(paths: list[Path]) -> dict[Path, str] UNCHANGED; stats via get_last_describe_stats() accessor. All 3 callers (WeChat:651, PDF:778, Zhihu:249) untouched."
  - "Inter-image sleep default 0s (down from 2s); VISION_INTER_IMAGE_SLEEP env override."
  - "6 outcome constants per D-08.05: success, download_failed, filtered_too_small, size_read_failed, vision_error, timeout."
  - "TimeoutError detection: string 'timeout' in msg OR isinstance(TimeoutError) OR isinstance(requests.Timeout) — all three checks to catch all shapes of timeout across providers."
  - "Stage ownership of per-image events (D-08.02 ms rule): download_images owns download_failed only; filter_small_images owns filtered_too_small + size_read_failed; describe_images owns success + vision_error + timeout. Successful downloads emit NO event (ownership passes to next stage)."
  - "emit_batch_complete wired into WeChat path only (ingest_wechat.py:~641); PDF path at line 780 + Zhihu path at enrichment/fetch_zhihu.py:249 unchanged — aggregate-log coverage for those paths is out of Phase 8 scope."
  - "Test to distinguish timeout vs vision_error pins VISION_PROVIDER=gemini to prevent the auto-cascade from masking the original exception with later provider errors."
metrics:
  duration: ~35min
  completed: 2026-04-30
  tasks: 6
  commits: 5
---

# Phase 8 Plan 01: JSON-lines Observability + Inter-image Sleep Config Summary

JSON-lines per-image observability on every pipeline stage + WeChat-batch aggregate event + inter-image Vision sleep config (default 0s + env override), all behind a signature-preserving `describe_images()` contract so none of the 3 call sites need editing.

## Objective

Make the image pipeline observable without breaking any callers. Emit one `image_processed` JSON-lines event per image (to stderr by default, or `VISION_LOG_PATH` file), one `image_batch_complete` aggregate event per WeChat ingest. Cut the 2-second inter-image sleep (56s wasted on the 28-image gpt55 fixture) to 0 by default, with an env escape hatch for providers that grow RPM caps later.

## Requirements Delivered

- **IMG-02** Inter-image sleep is 0s by default; `VISION_INTER_IMAGE_SLEEP=1.5` env switches to 1.5s. Sleep call is skipped entirely when `sleep_secs <= 0`.
- **IMG-03** Every image that touches the pipeline emits exactly one JSON-lines event with 10 fields (event, ts, url, local_path, dims, bytes, provider, ms, outcome, error). 6 outcome taxonomy constants.
- **IMG-04** `emit_batch_complete()` fires once per WeChat article with 8-subkey counts block, total_ms, provider_mix. Stats gathered via `get_last_describe_stats()` accessor — public `describe_images()` signature preserved (Option A).

## Tasks Executed

| # | Task | Commit |
|---|---|---|
| 1 | `_emit_log` helper + 6 outcome constants + `_last_describe_stats` + `get_last_describe_stats()` accessor; default sleep 2 → 0 | `7c3017e` |
| 2 | Instrument `download_images` (failure-only) + `filter_small_images` (filtered/size-failed only) with per-image JSON-lines | `85507d2` |
| 3 | `_describe_one` returns `(desc, provider_used)` tuple — 6 return points updated; `describe_images` body rewritten with per-image events, timeout-vs-error taxonomy, stats accumulator; `VISION_INTER_IMAGE_SLEEP` env read | `ffdaee7` |
| 4 | `emit_batch_complete()` helper + wire into `ingest_wechat.py` WeChat path (PDF + Zhihu unchanged) | `5b2ae77` |
| 5 | Fix pre-existing stale test `test_describe_images_batch_calls_sleep_between` (was `sleep(4)`, now `assert_not_called`) + add 9 new tests | `ff1df96` |
| 6 | Golden-file structural invariant check on 3 cached articles (baseline recorded) | — (no production code change) |

## Architectural Invariant Upheld

`describe_images(paths: list[Path]) -> dict[Path, str]` signature **unchanged** (Option A). Verified via grep at the 3 call sites:

```
ingest_wechat.py:645     descriptions = describe_images(list(url_to_path.values()))
ingest_wechat.py:780     description = describe_images([Path(img_path)]).get(Path(img_path), "")
enrichment/fetch_zhihu.py:249   descriptions = describe_images(list(url_to_path.values()))
```

All 3 continue to compile and run without signature edits. The WeChat site gained 2 extra lines (`describe_stats = get_last_describe_stats()` + `emit_batch_complete(...)`); PDF + Zhihu sites are byte-identical to pre-plan state.

## Test Results

**Baseline (post 08-00):** 12 pass / 1 fail (stale `sleep(4)` assertion in `test_describe_images_batch_calls_sleep_between`)

**Post plan:** 22 pass / 0 fail

**New tests added (9):**

1. `test_describe_images_respects_vision_inter_image_sleep_env` — VISION_INTER_IMAGE_SLEEP=1.5 → sleep(1.5)
2. `test_emit_log_writes_jsonlines_to_stderr` — default stderr path, one JSON line
3. `test_emit_log_writes_to_file_when_env_set` — VISION_LOG_PATH file sink
4. `test_filter_small_images_emits_filtered_too_small_log` — dropped image emits event with dims
5. `test_filter_small_images_emits_size_read_failed_log` — PIL OSError emits event with error
6. `test_describe_images_outcome_timeout_vs_vision_error` — taxonomy distinguishes TimeoutError vs RuntimeError
7. `test_get_last_describe_stats_populated_after_call` — accessor None → populated dict with vision_success + provider_mix
8. `test_emit_batch_complete_aggregate_shape` — 3 top-level keys + 8 counts subkeys match D-08.02 exactly
9. `test_emit_batch_complete_handles_none_describe_stats` — None → zero counts + empty provider_mix

**Previously failing now passing:** `test_describe_images_batch_calls_sleep_between` (fixed by replacing `assert_called_once_with(4)` with `assert_not_called()` to match default=0).

## Deviations from Plan

### None

Plan executed exactly as written. One minor in-task refinement:

**[Minor — Test refinement, not Rule deviation] `test_describe_images_outcome_timeout_vs_vision_error` needed VISION_PROVIDER=gemini pin**

- **Found during:** Task 5 first pytest run
- **Issue:** Test assumed TimeoutError would propagate out of `_describe_one` directly, but with default VISION_PROVIDER=auto the cascade catches the TimeoutError and tries SiliconFlow (fails on missing API key) then OpenRouter (same), and the final exception at `describe_images` level is the last provider's error, not the original TimeoutError.
- **Fix:** Added `monkeypatch.setenv("VISION_PROVIDER", "gemini")` to bypass cascade.
- **Commit:** `ff1df96`

This is test-level refinement, not a production code deviation. Plan-level taxonomy is correct — the cascade is working as designed; the test was imprecise.

## Golden-File Structural Baseline (Task 6)

Three cached articles were inspected for structural invariants (title present, image count, local URL format):

| Hash | Title line | Images (`[Image N Reference]:`) | `http://localhost:8765/<hash>/` URL matches |
|---|---|---|---|
| `0b9ebc8cab` | present | 35 | 35 |
| `3738bfe579` | present | 2 | 5 (includes 3 extra path matches — benign) |
| `4486577a6a` | present | 2 | 5 (includes 3 extra path matches — benign) |

Full Vision-API re-run diff belongs on the remote Hermes PC after merge (per Plan Task 6 step 2). Local baseline captured; no code change in this task.

## Authentication Gates

None. All work was code + test changes; no secrets, no external service calls.

## Deferred Issues

None. Plan scope achieved fully within scope boundary. Out-of-scope items (per plan) remain deferred as documented:

- `image_batch_complete` emission from PDF and Zhihu paths — future phase
- Per-image Vision cache (`cache_hit` outcome) — v3.2
- Image cost tracking field — deferred
- OTel/structlog shipper integration — deferred

## Self-Check: PASSED

**Files verified:**
- FOUND: image_pipeline.py (added helpers, constants, accessor, emit_batch_complete; modified 3 functions)
- FOUND: ingest_wechat.py (updated import, wrapped WeChat batch with perf_counter + emit_batch_complete)
- FOUND: tests/unit/test_image_pipeline.py (fixed stale test + 9 new tests, all passing)

**Commits verified (5):**
- FOUND: `7c3017e` feat(08-01): add _emit_log helper + outcome taxonomy + describe stats accessor
- FOUND: `85507d2` feat(08-01): emit per-image JSON-lines in download + filter stages (IMG-03)
- FOUND: `ffdaee7` feat(08-01): describe_images emits per-image events + exposes stats (IMG-02/04)
- FOUND: `5b2ae77` feat(08-01): emit image_batch_complete aggregate from WeChat path (IMG-04)
- FOUND: `ff1df96` test(08-01): fix stale sleep test + 9 new observability tests
