---
phase: 17-batch-timeout-management
plan: 01
subsystem: batch-timeout
tags: [lib, helper, pure-function, tdd, batch-timeout]
requires: [17-00]
provides: [lib/batch_timeout.py, tests/unit/test_batch_timeout.py]
affects: []
tech-stack:
  added: []
  patterns: [Pure helper module, Phase 7 lib/* structure, pytest assert-only]
key-files:
  created:
    - lib/batch_timeout.py
    - tests/unit/test_batch_timeout.py
  modified: []
decisions:
  - "No re-export from lib/__init__.py — consumers use `from lib.batch_timeout import ...` for a narrow API"
  - "safety_margin defaults to BATCH_SAFETY_MARGIN_S=60 constant; callers may override per call"
  - "get_remaining_budget floors at 0.0 (float) to keep arithmetic consistent with time.time() subtraction"
metrics:
  duration_min: 5
  tasks: 2
  files: 2
  tests_added: 11
  tests_passing: 11
  completed: 2026-05-02
commit: ccbfe57
---

# Phase 17 Plan 01: Clamp Helper Summary

One-liner: Added `lib/batch_timeout.py` with three public symbols (`clamp_article_timeout`, `get_remaining_budget`, `BATCH_SAFETY_MARGIN_S`) and 11 unit tests gating the interlock math; consumed by plan 17-02.

## What Was Built

**`lib/batch_timeout.py`** — pure helper module, no side effects, no I/O (except `time.time()` inside `get_remaining_budget`):

- `BATCH_SAFETY_MARGIN_S: int = 60` — module-level constant, importable.
- `clamp_article_timeout(single_timeout, remaining_budget, safety_margin=60) -> int` — returns `min(single, int(remaining - margin))` when effective budget is positive, else `max(60, int(single * 0.5))` (half-timeout fallback with 60s floor).
- `get_remaining_budget(batch_start, total_batch_budget) -> float` — returns `max(0.0, total - elapsed)`.

**`tests/unit/test_batch_timeout.py`** — 11 pure-function tests:

| # | Test | Covers |
|---|------|--------|
| 1 | `test_safety_margin_constant_is_60` | BATCH_SAFETY_MARGIN_S value |
| 2 | `test_full_budget_no_clamp` | early-batch path (single_timeout wins) |
| 3 | `test_clamp_kicks_in_late_batch` | primary clamp branch (900→440) |
| 4 | `test_boundary_effective_budget_zero_uses_half_timeout` | exact-zero boundary |
| 5 | `test_budget_overrun_half_timeout_fallback` | negative effective_budget |
| 6 | `test_half_timeout_floors_at_60` | 60s floor enforcement |
| 7 | `test_single_timeout_wins_when_smaller` | min() correctness |
| 8 | `test_custom_safety_margin` | non-default margin arg |
| 9 | `test_get_remaining_budget_positive` | normal case |
| 10 | `test_get_remaining_budget_floors_at_zero` | overrun flooring |
| 11 | `test_get_remaining_budget_returns_float` | type contract |

## Verification Evidence

- `DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_batch_timeout.py -v` → **11 passed in 4.40s**
- Phase 9 regression guard green: `tests/unit/test_timeout_budget.py` + `tests/unit/test_lightrag_timeout.py` → **9 passed in 3.28s**
- Import smoke: `from lib.batch_timeout import clamp_article_timeout, get_remaining_budget, BATCH_SAFETY_MARGIN_S` → OK

## Deviations from Plan

None — plan executed exactly as written. Module body and test file content verbatim from the plan's `<action>` block.

## Self-Check: PASSED

- `lib/batch_timeout.py` exists → verified via `test -f`
- `tests/unit/test_batch_timeout.py` exists → verified via `test -f`
- Commit `ccbfe57` present in `git log` → verified
- Tests pass → verified (11/11)
