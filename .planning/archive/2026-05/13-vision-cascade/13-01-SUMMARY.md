---
phase: 13-vision-cascade
plan: 01
subsystem: siliconflow-balance
status: complete
completed: "2026-05-02"
requirements_delivered: [CASC-06]
absorbs: "v3.1 closure Finding 2 (D-BENCH-PRECHECK)"
tests_added: 18
---

# Phase 13 Plan 01: SiliconFlow Balance Summary

Lightweight balance API wrapper, cost estimation, and OpenRouter-switch thresholds in `lib/siliconflow_balance.py`. Plus: bench precheck refactor that delegates to the lib module, removing the v3.1 Finding 2 env-read bug by construction.

## Public API

```python
from lib.siliconflow_balance import (
    check_siliconflow_balance,        # () -> Decimal  (raises MissingKeyError | BalanceCheckError)
    estimate_cost,                    # (remaining_articles, avg_images) -> Decimal (CNY)
    should_warn,                      # (balance, estimated_cost) -> bool
    should_switch_to_openrouter,      # (balance) -> bool  (strict < CNY 0.05)
    BalanceCheckError,                # base exception
    MissingKeyError,                  # subclass of BalanceCheckError
    SILICONFLOW_PRICE_PER_IMAGE,      # Decimal("0.0013")
    OPENROUTER_SWITCH_THRESHOLD,      # Decimal("0.05")
)
```

## Locked Constants (CASC-06)

| Constant                       | Value          | Rationale                                               |
| ------------------------------ | -------------- | ------------------------------------------------------- |
| `SILICONFLOW_PRICE_PER_IMAGE`  | CNY 0.0013     | Qwen3-VL-32B-Instruct published rate                    |
| `OPENROUTER_SWITCH_THRESHOLD`  | CNY 0.05       | Avoid half-batch split between providers                |
| `BALANCE_API_TIMEOUT_SECS`     | 5.0            | Fast precheck; caller proceeds on failure               |

## Example Caller Snippet (for Plan 13-02)

```python
from lib.siliconflow_balance import (
    BalanceCheckError,
    check_siliconflow_balance,
    should_switch_to_openrouter,
)

try:
    balance = check_siliconflow_balance()
except BalanceCheckError as e:
    logger.warning("pre-batch balance check failed (%s); proceeding", e)
    balance = None

if balance is not None and should_switch_to_openrouter(balance):
    providers = ["openrouter", "gemini"]  # skip SiliconFlow
else:
    providers = ["siliconflow", "openrouter", "gemini"]
```

## D-BENCH-PRECHECK Fix (absorbs v3.1 Finding 2)

- `lib/siliconflow_balance.py` imports `config` at module load, guaranteeing `~/.hermes/.env` is sourced into `os.environ` before any `SILICONFLOW_API_KEY` read.
- `scripts/bench_ingest_fixture.py::_balance_precheck()` now delegates to `check_siliconflow_balance()`. The four output branches (`balance_precheck_skipped`, `balance_warning status=ok`, `balance_warning status=insufficient_for_batch`, `balance_precheck_failed`) are preserved as a thin mapper -- `benchmark_result.json` schema is untouched.
- Regression grep-test in `tests/unit/test_bench_precheck_delegation.py` enforces that no `os.environ.get("SILICONFLOW_API_KEY"...)` remains in `_balance_precheck`'s body.

## Test count

**18 tests, all passing:**

- `tests/unit/test_siliconflow_balance.py` (13 tests): happy path, missing key, HTTP 500, timeout, malformed JSON, network error, Bearer header, cost math, should_warn variants, boundary conditions, locked constants.
- `tests/unit/test_bench_precheck_delegation.py` (5 tests): regression grep, 4 mocked branches (warning/insufficient/skipped/failed).

## R4 Environment Notes

- **Cisco Umbrella proxy blocks `api.siliconflow.cn` TLS on this dev machine.** All tests mock `lib.siliconflow_balance.requests.get` at the HTTP boundary. A live balance probe from this workstation would fail at the TLS layer, not in our code.

## Deviations from Plan

None. Plan executed exactly as written, including the locked constants and branch semantics.

## Files

- `lib/siliconflow_balance.py` (128 lines)
- `tests/unit/test_siliconflow_balance.py` (155 lines, 13 tests)
- `scripts/bench_ingest_fixture.py` (precheck refactored; unused `SILICONFLOW_URL` + `BALANCE_TIMEOUT_S` constants retained because other bench code may reference them)
- `tests/unit/test_bench_precheck_delegation.py` (103 lines, 5 tests)

## Self-Check: PASSED

- `lib/siliconflow_balance.py` importable
- `scripts/bench_ingest_fixture.py` importable with dummy DeepSeek key
- 18 tests pass
- grep confirms `from lib.siliconflow_balance import` present in bench; `os.environ.get("SILICONFLOW_API_KEY"` absent from _balance_precheck body
