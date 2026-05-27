---
phase: 13-vision-cascade
plan: 00
subsystem: vision-cascade-core
status: complete
completed: "2026-05-02"
requirements_delivered: [CASC-01, CASC-02, CASC-03, CASC-04, CASC-05]
tests_added: 15
lines_added: 759
---

# Phase 13 Plan 00: Vision Cascade Core Summary

Stateful cascade orchestrator in `lib/vision_cascade.py` that tries SiliconFlow -> OpenRouter -> Gemini in that exact order (CASC-01 locked), with per-provider circuit-breaker (3-strike rule, 10-image recovery probe), error classification (503/429/timeout count as circuit failures; 401/403/422 do not), atomic `provider_status.json` persistence, and per-attempt structured logging.

## Public API

```python
from lib.vision_cascade import (
    VisionCascade,                      # stateful orchestrator
    CascadeResult,                      # frozen dataclass: description, provider_used, attempts, failed
    AttemptRecord,                      # frozen dataclass: provider, result_code, latency_ms, error, desc_chars
    AllProvidersExhausted429Error,      # raised when all providers 429 on same image
    DEFAULT_PROVIDERS,                  # ("siliconflow", "openrouter", "gemini")
    CIRCUIT_FAILURE_THRESHOLD,          # 3
    RECOVERY_PROBE_INTERVAL,            # 10
    RESULT_SUCCESS, RESULT_HTTP_503, RESULT_HTTP_429,
    RESULT_HTTP_4XX_AUTH, RESULT_TIMEOUT, RESULT_OTHER,
)
```

## Example Usage (for Plan 13-02 to copy)

```python
cascade = VisionCascade(checkpoint_dir=None)   # defaults to BASE_DIR/checkpoints

for image_id, image_bytes, mime in images:
    try:
        result = cascade.describe(image_id, image_bytes, mime)
    except AllProvidersExhausted429Error:
        break  # stop batch cleanly

    if result.failed:
        # all providers exhausted (non-429) for this image -- log and skip
        continue
    save(image_id, result.description, provider_used=result.provider_used)

# Batch-end aggregate
usage = cascade.total_usage()   # {"siliconflow": 245, "openrouter": 7, "gemini": 0}
```

## Behaviour matrix

| HTTP / Exception     | Counts for circuit | Cascade action         |
| -------------------- | ------------------ | ---------------------- |
| 200                  | resets failures    | return description     |
| 503                  | YES                | try next provider      |
| 429                  | YES                | try next; all-429 raises |
| Timeout              | YES                | try next provider      |
| 401 / 403 / 422      | NO                 | try next provider      |
| Other                | NO                 | try next provider      |

3 consecutive circuit failures -> `circuit_open=True` -> provider skipped for next 9 images -> 10th image triggers a single recovery probe -> success resets `failures=0` and `circuit_open=False`.

## Test count + coverage

**15 tests in `tests/unit/test_vision_cascade.py`, all passing.**

| Test                                               | Covers                              |
| -------------------------------------------------- | ----------------------------------- |
| `test_contracts_construct_default_order`           | CASC-01, CASC-02                    |
| `test_contracts_dataclasses_frozen`                | Dataclass immutability              |
| `test_contracts_status_path`                       | Persistence path                    |
| `test_contracts_fresh_dir_no_raise`                | Fresh construction                  |
| `test_contracts_existing_json_loaded`              | Resume scenario                     |
| `test_siliconflow_success_records_attempt`         | Happy path                          |
| `test_siliconflow_503_falls_through_to_openrouter` | CASC-01 fallback                    |
| `test_three_consecutive_503_opens_circuit`         | CASC-03                             |
| `test_circuit_open_recovery_probe_after_10_skipped`| CASC-03 recovery                    |
| `test_401_auth_not_counted_as_circuit_failure`     | CASC-04                             |
| `test_all_providers_429_raises_stop_batch`         | CASC-04 batch-stop                  |
| `test_timeout_counts_as_circuit_failure`           | CASC-04                             |
| `test_persist_writes_atomic_json_on_disk`          | Atomic persistence                  |
| `test_per_image_log_lines_emitted`                 | CASC-05                             |
| `test_cascade_order_is_siliconflow_first`          | CASC-01 lock assertion              |

## Deviations from Plan

- **Rule 2 (correctness):** Added small retry loop (5 attempts, 50ms-250ms backoff) to `_persist()` because Windows antivirus/indexer can hold brief locks on `os.replace` when writes happen in rapid succession (observed in the recovery-probe test). Retry is silent; final failure is logged as WARNING (non-fatal -- next call will re-persist).
- **Rule 3 (correctness):** `_load_or_init_status()` seeds state for the full set `DEFAULT_PROVIDERS | self.providers` rather than just `self.providers`, so cross-batch persistence works when a batch uses a subset of providers.

## Files

- `lib/vision_cascade.py` (462 lines)
- `tests/unit/test_vision_cascade.py` (297 lines, 15 tests)

## Self-Check: PASSED

- `lib/vision_cascade.py` present and importable
- 15 tests in test file (>= 10 required)
- All 15 tests pass
- Commit hash recorded below
