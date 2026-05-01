---
phase: 11-e2e-verification-gate
plan: 00
subsystem: testing
tags: [benchmark, pytest, fixture, siliconflow, urllib, atomic-write, asyncio, cli, argparse]

requires:
  - phase: 10-classification-and-ingest-decoupling
    provides: text-first ingest split; Vision worker shape; 61+ green unit tests baseline
provides:
  - "scripts/bench_ingest_fixture.py — CLI entry point + 5-stage timing scaffold"
  - "Pure helpers: _read_fixture, _compute_article_hash, _utc_now_iso, _build_result_json, _write_result, _balance_precheck, _time_stage"
  - "SiliconFlow balance precheck via GET /v1/user/info with 4 structured-warning branches"
  - "Atomic JSON writer (tmp + os.rename) matching canonical_map.json pattern"
  - "PRD-exact benchmark_result.json schema (9 top-level keys)"
  - "16 unit tests covering every helper, every branch, CLI end-to-end"
affects: [11-02 integration run, 11-01 Vertex AI opt-in (regression gate)]

tech-stack:
  added: []
  patterns:
    - "CLI module with main(argv=None) signature for testable entry points"
    - "Context-manager stage timer (_time_stage) — uniform perf_counter wrapping"
    - "Atomic write: tmp path + os.rename, with on-failure tmp cleanup"
    - "Structured-warning-as-dict pattern for balance_warning / balance_precheck_skipped / balance_precheck_failed"

key-files:
  created:
    - "scripts/bench_ingest_fixture.py (451 LOC) — benchmark harness scaffold"
    - "tests/unit/test_bench_harness.py (402 LOC) — 16 unit tests"
  modified: []

key-decisions:
  - "SiliconFlow HTTP client uses stdlib urllib (no new requests dependency per D-11.05)"
  - "Balance precheck catches URLError, HTTPError, JSONDecodeError, ValueError, TimeoutError, OSError — emits balance_precheck_failed for all (non-fatal)"
  - "Stub stages (classify, image_download, text_ingest, async_vision_start) use asyncio.sleep(0) — near-zero timing in stub mode, Plan 11-02 replaces with real work"
  - "Counters populated from fixture metadata (images_input / images_kept / images_filtered); chunks_extracted + entities_ingested zero-filled (Plan 11-02 populates from LightRAG state)"
  - "_USE_VERTEX / Vertex AI concerns explicitly out of scope for 11-00 (owned by Plan 11-01 per D-11.08)"
  - "Exit 1 in stub mode is EXPECTED and TESTED — gate_pass=false because text_ingest is a no-op"
  - "Module-level constants DEFAULT_FIXTURE + DEFAULT_OUTPUT as pathlib.Path for cross-platform correctness"

patterns-established:
  - "stdlib-first for small HTTP: urllib.request + json, not requests"
  - "Atomic JSON write idiom matches canonical_map.json convention (project-wide)"
  - "Balance precheck returns always a dict — never raises — caller appends to warnings[]"
  - "main(argv=None) — testable CLI entry without subprocess invocation"

requirements-completed: [E2E-01, E2E-03, E2E-05, E2E-07]

duration: 18min
completed: 2026-04-29
---

# Phase 11 Plan 00: Benchmark Harness + Schema + SiliconFlow Balance Precheck Summary

**Pure-helper CLI harness that reads a pre-scraped fixture from disk, runs a 5-stage timing scaffold with stubbed classify/ingest stages, calls SiliconFlow /v1/user/info for a balance precheck, and writes a PRD-exact benchmark_result.json atomically — no network scrape, no LightRAG invocation (Plan 11-02 owns the real run).**

## Performance

- **Duration:** ~18 min
- **Tasks:** 1 (TDD RED → GREEN, no REFACTOR needed)
- **Files created:** 2
- **Files modified:** 0
- **Test delta:** +16 tests (162 → 178 passing, zero new regressions; 10 pre-existing failures unchanged)

## Accomplishments

- CLI entry point at `scripts/bench_ingest_fixture.py` with `--fixture` + `--output` args (defaults: `test/fixtures/gpt55_article/` and `<fixture>/benchmark_result.json`).
- 5-stage timing scaffold (`scrape`, `classify`, `image_download`, `text_ingest`, `async_vision_start`) — stub mode in this plan, real invocations in Plan 11-02.
- SiliconFlow balance precheck (D-11.05) covering 4 branches:
  1. `SILICONFLOW_API_KEY` unset → `balance_precheck_skipped`
  2. balance >= `ESTIMATED_COST_CNY` (0.036) → `balance_warning` with `status=ok`
  3. balance < estimated cost → `balance_warning` with `status=insufficient_for_batch`
  4. urlopen/JSON/timeout error → `balance_precheck_failed`
- Atomic JSON writer (`_write_result`) with tmp path + `os.rename` + on-failure tmp cleanup — matches `canonical_map.json` convention.
- PRD-exact schema: 9 top-level keys; 5 `stage_timings_ms`; 5 `counters`; 3 `gate` flags; `gate_pass = all(gate_flags.values())`.
- 16 unit tests covering CLI end-to-end, fixture reader with network-call assertions, article_hash determinism, schema shape + gate_pass logic, atomic write success + mid-write failure, all 4 balance branches, stage timing context manager, and ISO 8601 Z-suffix timestamp helper.

## Task Commits

TDD workflow (RED → GREEN, no REFACTOR needed):

1. **Task 1 RED: failing tests for benchmark harness scaffold** — `b42721b` (test)
2. **Task 1 GREEN: implement benchmark harness scaffold + SiliconFlow balance precheck** — `0405a68` (feat)

**Plan metadata commit:** pending (this SUMMARY + STATE.md + ROADMAP.md).

## Files Created/Modified

- `scripts/bench_ingest_fixture.py` — CLI entry point, 5-stage scaffold, pure helpers, SiliconFlow balance precheck, atomic JSON writer. 451 LOC.
- `tests/unit/test_bench_harness.py` — 16 pytest unit tests covering every public surface of the bench module. 402 LOC.

## Decisions Made

- **HTTP client for balance precheck:** stdlib `urllib.request` + `json` (per D-11.05 — no new `requests` dependency).
- **Balance response field path:** `data.balance` (coerced to `float`) — documented with a TODO to reconfirm against the live SiliconFlow response shape in Plan 11-02's live run. Falls back to `balance_precheck_failed` if the field is missing or non-numeric (covered by `test_balance_precheck_json_decode_error`).
- **`chunks_extracted` / `entities_ingested` counters:** zero-filled in this plan; Plan 11-02 populates from LightRAG state post-ainsert.
- **Vertex AI rotation behavior (D-11.08):** explicitly deferred to Plan 11-01 — this plan touches nothing in `lib/lightrag_embedding.py`.
- **Stage stub durations:** `asyncio.sleep(0)` (near-zero) — stub timings are near zero in ms; real timings populate in Plan 11-02.
- **Test fixture strategy:** synthetic minimal fixture generated in `tmp_path` per test for reader unit tests; real `test/fixtures/gpt55_article/` used only for the manual integration verification (no direct dependency in tests, so CI remains hermetic).

## Deviations from Plan

None - plan executed exactly as written.

(No auto-fixes, no scope adjustments, no architectural surprises. The PRD schema and CONTEXT decisions were precise enough to implement directly from.)

## Issues Encountered

- **Pre-existing test failures unrelated to this plan (10 tests):**
  `tests/unit/test_lightrag_embedding.py::test_embedding_func_reads_current_key` (1), `test_lightrag_embedding_rotation.py` (6), `test_models.py` (3). Verified pre-existing by stashing all uncommitted changes and running baseline — same failures appear on clean tree. **Out of scope for 11-00** per CLAUDE.md scope boundary rule. These are likely addressed by Plan 11-01 (Vertex AI opt-in touches `lib/lightrag_embedding.py`) or belong to earlier Phase 7 / Phase 10 follow-up work. Logged here for visibility; not fixed by this plan.
- **Windows `/tmp` path in verification:** running the script with `--output /tmp/bench_out.json` on Windows bash writes to `C:\Users\huxxha\AppData\Local\Temp\bench_out.json` (Git Bash translates `/tmp`). Verification still succeeded via Windows-native path inspection. No code change required — this is a shell behavior, not a bug.

## Verification

All plan-level verification gates from `11-00-PLAN.md` passed:

1. **`python scripts/bench_ingest_fixture.py --help`** → prints usage with `--fixture` and `--output` args ✅
2. **Real-fixture run** → `scripts/bench_ingest_fixture.py --fixture test/fixtures/gpt55_article/ --output <path>` exits 1 (stub mode expected), writes valid JSON with all 9 PRD keys, `article_hash=7d500c2dd9`, `counters.images_input=39`, `counters.images_kept=28`, `counters.images_filtered=11`, `warnings=[{event: balance_precheck_skipped, ...}]`, `gate.zero_crashes=true`, `errors=[]` ✅
3. **JSON key-set equality to PRD schema** → verified via assertion in Test 1 and manual inspection ✅
4. **New unit tests:** `pytest tests/unit/test_bench_harness.py -v` → **16/16 passing** in 0.57s ✅
5. **Zero regression:** full suite: **178 passed, 10 failed** (baseline: 162 passed, 10 failed). Pre-existing failures unchanged ✅

## Self-Check: PASSED

Verified via filesystem + git log:
- `FOUND: scripts/bench_ingest_fixture.py` ✅
- `FOUND: tests/unit/test_bench_harness.py` ✅
- `FOUND: commit b42721b` (test RED) ✅
- `FOUND: commit 0405a68` (feat GREEN) ✅

## Next Phase Readiness

- **Plan 11-02 (Wave 2) ready to proceed:** the harness scaffold, schema builder, atomic writer, and balance precheck are all in place. Plan 11-02 replaces the 4 stub stages (classify / image_download / text_ingest / async_vision_start) with real LightRAG invocations, populates `chunks_extracted` and `entities_ingested` from LightRAG internal state, implements the `aquery_returns_fixture_chunk` gate evaluation, and runs the integration benchmark against the real fixture.
- **Plan 11-01 (Wave 1 parallel) independent:** zero shared file edits with 11-00 (11-01 touches only `lib/lightrag_embedding.py`; 11-00 touches only `scripts/` and `tests/unit/`). Safe to merge in any order.
- **No blockers.** The SiliconFlow balance precheck field path (`data.balance`) has a TODO note to reconfirm against the live response in Plan 11-02; if the live shape differs, the fallback `balance_precheck_failed` branch catches it gracefully (non-fatal).

---
*Phase: 11-e2e-verification-gate*
*Completed: 2026-04-29*
