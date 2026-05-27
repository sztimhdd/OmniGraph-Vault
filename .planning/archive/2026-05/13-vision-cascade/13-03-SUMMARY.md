---
phase: 13-vision-cascade
plan: 03
subsystem: integration-tests
status: complete
completed: "2026-05-02"
requirements_delivered: [CASC-01, CASC-02, CASC-03, CASC-04, CASC-05, CASC-06]
tests_added: 9
tests_updated: 4
---

# Phase 13 Plan 03: Integration Tests Summary

End-to-end integration tests for the full Phase 13 vision cascade + balance + image pipeline stack. All HTTP is mocked at the `requests`/`generate_sync` boundary; no real API calls anywhere.

## Test count + coverage mapping

**9 tests in `tests/integration/test_vision_cascade_e2e.py`, all passing.**

| Test                                              | Covers                                                 |
| ------------------------------------------------- | ------------------------------------------------------ |
| `test_circuit_opens_after_3_siliconflow_503s`     | CASC-03 (circuit trip + on-disk persistence)           |
| `test_all_providers_429_raises_stop_batch`        | CASC-04 (all-429 batch-stop rule)                      |
| `test_siliconflow_timeout_falls_through_to_openrouter` | CASC-04 (timeout classification + fallthrough)    |
| `test_recovery_after_10_skipped_images`           | CASC-03 (recovery probe + circuit re-close)            |
| `test_auth_error_does_not_open_circuit`           | CASC-04 (4xx auth does not count)                      |
| `test_provider_status_persists_across_instances`  | CASC-02 (cross-instance persistence)                   |
| `test_image_pipeline_e2e_happy_path`              | CASC-01 (end-to-end, cascade is SiliconFlow-first)     |
| `test_mid_batch_switch_to_openrouter_below_floor` | CASC-06 (mid-batch balance switch at CNY 0.05)         |
| `test_gemini_alert_at_batch_end`                  | CASC-05 (gemini > 5% alert)                            |

## How to run

```bash
# All integration tests for Phase 13
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/integration/test_vision_cascade_e2e.py -v

# Full unit + integration Phase 13 suite
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest \
  tests/unit/test_vision_cascade.py \
  tests/unit/test_siliconflow_balance.py \
  tests/unit/test_bench_precheck_delegation.py \
  tests/unit/test_image_pipeline_cascade.py \
  tests/integration/test_vision_cascade_e2e.py -v
```

## Flaky-test risk flags

- **None identified.** All tests mock deterministically. The recovery test assumes exact call-count ordering (trip-then-probe) which is deterministic because cascade iterates providers in fixed order.
- Windows AV/indexer: mitigated by the `_persist` retry loop in `lib/vision_cascade.py`.

## R4 Environment Ceiling

- Cisco Umbrella proxy blocks `api.siliconflow.cn` and `openrouter.ai` TLS on this dev machine. All tests mock at the HTTP boundary. No test requires real provider network traffic.

## Cross-cutting fixes applied during 13-03

- **Rule 2 (correctness):** Added session-scope autouse fixture `_isolate_vision_checkpoint_dir` in `tests/conftest.py` that redirects `OMNIGRAPH_VISION_CHECKPOINT_DIR` to a per-session tmp directory. Prevents test runs from polluting `~/.hermes/omonigraph-vault/checkpoints/_batch/provider_status.json` (discovered when integration tests initially failed due to persisted circuit-open state from a prior run).
- **Rule 3 (correctness):** Added `OMNIGRAPH_VISION_CHECKPOINT_DIR` env-var test seam to `image_pipeline.describe_images()`. Production usage unchanged (env var unset -> BASE_DIR). Tests use the conftest fixture to redirect.
- **Rule 1 (bug):** Updated 4 pre-existing tests in `tests/unit/test_bench_harness.py` (`test_balance_precheck_ok_branch`, `_insufficient_branch`, `_url_error_branch`, `_json_decode_error`) to patch at the new `lib.siliconflow_balance.check_siliconflow_balance` boundary instead of the removed `urllib.request.urlopen` path. These were the legacy callers of `_balance_precheck` made obsolete by the 13-01 refactor.

## Handoff to Phase 14

Phase 14 (regression fixtures) will add real-fixture-based regression tests that exercise the full pipeline with persisted article + image fixtures. These integration tests are purely mock-based and validate the state machine; Phase 14 adds end-to-end signal on golden fixtures.

Important interface contracts for Phase 14:
- `OMNIGRAPH_VISION_CHECKPOINT_DIR` is the canonical test seam for redirecting cascade state.
- `OMNIGRAPH_VISION_SKIP_BALANCE_CHECK=1` disables pre/mid-batch balance checks for offline runs.
- Patch `lib.vision_cascade.requests.post` and `lib.generate_sync` at the HTTP + Gemini boundary; patch `image_pipeline.check_siliconflow_balance` at the image_pipeline import site.

## Deferred Items

See `.planning/phases/13-vision-cascade/deferred-items.md` — 9 pre-existing failures in unrelated modules (test_models.py, test_lightrag_embedding*.py) were not fixed per the scope boundary.

## Files

- `tests/integration/test_vision_cascade_e2e.py` (255 lines, 9 tests)
- `tests/integration/__init__.py` (pre-existing)
- `tests/conftest.py` (+ 18 lines for autouse fixture)
- `image_pipeline.py` (+ 7 lines for checkpoint_dir test seam)
- `tests/unit/test_bench_harness.py` (4 tests updated to new patch target)

## Self-Check: PASSED

- All 9 integration tests pass
- Legacy test suite still passes (bench_harness tests updated + passing)
- No test writes to production `~/.hermes/omonigraph-vault/checkpoints`
- Conftest isolation fixture in place
