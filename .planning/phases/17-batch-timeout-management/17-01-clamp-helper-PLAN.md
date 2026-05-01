---
phase: 17-batch-timeout-management
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - lib/batch_timeout.py
  - tests/unit/test_batch_timeout.py
autonomous: true
requirements: [BTIMEOUT-02]

must_haves:
  truths:
    - "clamp_article_timeout(single, remaining, margin) returns min(single, remaining-margin) when budget available"
    - "clamp_article_timeout returns max(60, int(single*0.5)) when effective_budget <= 0"
    - "clamp_article_timeout(900, 500, 60) == 440 (math check: min(900, 500-60)=440)"
    - "clamp_article_timeout(900, 30, 60) == 450 (budget out → half-timeout)"
    - "Unit tests cover: full budget, clamp kicks in, safety margin triggered, budget out, zero/negative edge cases"
  artifacts:
    - path: "lib/batch_timeout.py"
      provides: "clamp_article_timeout() + BATCH_SAFETY_MARGIN_S + get_remaining_budget()"
      exports: ["clamp_article_timeout", "get_remaining_budget", "BATCH_SAFETY_MARGIN_S"]
    - path: "tests/unit/test_batch_timeout.py"
      provides: "Unit tests gating the interlock math"
      min_lines: 60
  key_links:
    - from: "lib/batch_timeout.py::clamp_article_timeout"
      to: "docs/BATCH_TIMEOUT_DESIGN.md § Interlock Formula"
      via: "identical function body"
      pattern: "def clamp_article_timeout"
    - from: "tests/unit/test_batch_timeout.py"
      to: "lib/batch_timeout.py"
      via: "from lib.batch_timeout import clamp_article_timeout"
      pattern: "from lib\\.batch_timeout import"
---

<objective>
Implement the `clamp_article_timeout()` helper + supporting batch-budget utilities in a new
module `lib/batch_timeout.py`, with unit tests gating the interlock math. This is the
code artifact implementation plan 17-02 (batch instrumentation) will consume.

Purpose: Small, pure, well-tested helper. No side effects, no I/O. Sits alongside other
`lib/*` modules (Phase 7 pattern).

Output:
1. `lib/batch_timeout.py` — 3 public symbols (`clamp_article_timeout`,
   `get_remaining_budget`, `BATCH_SAFETY_MARGIN_S`)
2. `tests/unit/test_batch_timeout.py` — pytest unit tests covering all branches
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/17-batch-timeout-management/17-CONTEXT.md
@.planning/phases/09-timeout-state-management/09-00-SUMMARY.md
@lib/__init__.py
@lib/models.py
@tests/unit/test_timeout_budget.py

<interfaces>
From `lib/__init__.py` (Phase 7 pattern — 13-symbol public API):
```python
# lib/__init__.py currently re-exports: INGESTION_LLM, generate_sync, current_key, ...
# Phase 17 adds: clamp_article_timeout, get_remaining_budget, BATCH_SAFETY_MARGIN_S
```

From existing Phase 9 test `tests/unit/test_timeout_budget.py` (reference pytest style):
- Uses plain `def test_*` functions (no test classes)
- Uses direct import: `from batch_ingest_from_spider import _compute_article_budget_s`
- Uses simple `assert x == y` with explanatory failure messages
- No mocks needed (pure functions)

Phase 7 env var idiom from `CLAUDE.md`:
- Namespaced prefix: `OMNIGRAPH_*` (e.g., `OMNIGRAPH_GEMINI_KEY`, `OMNIGRAPH_RPM_*`)
- Phase 17 introduces `OMNIGRAPH_BATCH_TIMEOUT_SEC` — owned by plan 17-02 (consumer site)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create lib/batch_timeout.py with clamp_article_timeout + get_remaining_budget</name>
  <files>lib/batch_timeout.py</files>
  <behavior>
    - `clamp_article_timeout(900, 3600, 60) == 900` — early batch, no clamp
    - `clamp_article_timeout(900, 500, 60) == 440` — late batch, clamp to `500-60`
    - `clamp_article_timeout(900, 60, 60) == 450` — boundary: effective_budget=0 → half-timeout fallback (max(60, 450)=450)
    - `clamp_article_timeout(900, 30, 60) == 450` — budget out → half-timeout fallback
    - `clamp_article_timeout(100, 500, 60) == 100` — single_timeout < effective_budget → single_timeout wins
    - `clamp_article_timeout(100, 30, 60)` — effective_budget ≤ 0, half-timeout → max(60, 50) == 60
    - `clamp_article_timeout(60, 30, 60)` — minimum floor → max(60, 30) == 60
    - `get_remaining_budget(batch_start, total=3600)` returns non-negative float; floors at 0
    - `BATCH_SAFETY_MARGIN_S == 60` (module-level constant, importable)
  </behavior>
  <read_first>
    - .planning/phases/17-batch-timeout-management/17-CONTEXT.md § Single-Article / Batch Interlock (BTIMEOUT-02) — copy the function body verbatim
    - lib/__init__.py (to match re-export pattern)
    - lib/models.py (5 lines; Phase 7 constant-module pattern)
    - tests/unit/test_timeout_budget.py (pytest style reference; simple assert-based tests)
  </read_first>
  <action>
    Create `lib/batch_timeout.py` with the EXACT following content (preserve docstrings,
    type hints, PEP 8):

    ```python
    """Phase 17 (BTIMEOUT-02): batch-level timeout interlock helpers.

    Small, pure, side-effect-free utilities for composing v3.1 Phase 9's
    per-article timeout formula with a batch-level remaining-budget bound.
    See `docs/BATCH_TIMEOUT_DESIGN.md` for the full design.
    """
    from __future__ import annotations

    import time

    # Seconds reserved for checkpoint flush + final metrics emission at batch end.
    # Per design: flush is small JSON writes expected to complete in <5s. 60s is a
    # conservative safety buffer. See docs/BATCH_TIMEOUT_DESIGN.md § Checkpoint-Flush Interaction.
    BATCH_SAFETY_MARGIN_S: int = 60


    def clamp_article_timeout(
        single_timeout: int,
        remaining_budget: float,
        safety_margin: int = BATCH_SAFETY_MARGIN_S,
    ) -> int:
        """Clamp per-article timeout so total batch budget is respected.

        Composes with v3.1 Phase 9's single-article formula
        ``max(120 + 30 * chunk_count, 900)``; does NOT replace it.

        Rules (BTIMEOUT-02):
          * If ``remaining_budget - safety_margin > 0`` → return
            ``min(single_timeout, int(effective_budget))``.
          * Else (batch out of budget) → return
            ``max(60, int(single_timeout * 0.5))`` so the next article still has
            a viable 60s floor; if it times out, checkpoint captures state for a
            later re-run.

        Args:
            single_timeout: Phase 9 per-article budget in seconds.
            remaining_budget: Batch budget remaining in seconds; MAY be a float
                (from ``time.time()`` subtraction).
            safety_margin: Seconds reserved for post-batch bookkeeping (default
                ``BATCH_SAFETY_MARGIN_S`` = 60).

        Returns:
            Effective per-article timeout in integer seconds.
        """
        effective_budget = remaining_budget - safety_margin
        if effective_budget <= 0:
            # Batch out of budget; article gets half-timeout fallback.
            return max(60, int(single_timeout * 0.5))
        return min(single_timeout, int(effective_budget))


    def get_remaining_budget(batch_start: float, total_batch_budget: int) -> float:
        """Compute remaining batch budget in seconds (floored at 0).

        Args:
            batch_start: ``time.time()`` value captured at batch start.
            total_batch_budget: Total batch budget in seconds (from
                ``OMNIGRAPH_BATCH_TIMEOUT_SEC`` or ``--batch-timeout``).

        Returns:
            ``max(0, total_batch_budget - elapsed)``.
        """
        elapsed = time.time() - batch_start
        return max(0.0, float(total_batch_budget) - elapsed)
    ```

    Do NOT re-export these symbols from `lib/__init__.py` in this task — plan 17-02 imports
    directly (`from lib.batch_timeout import ...`) and a clean narrow API surface is
    preferred. If plan 17-02 later decides re-export is useful, it can add it.

    Do NOT import this module from any production code in this task — 17-02 does the wiring.
  </action>
  <verify>
    <automated>python -c "from lib.batch_timeout import clamp_article_timeout, get_remaining_budget, BATCH_SAFETY_MARGIN_S; assert BATCH_SAFETY_MARGIN_S == 60; assert clamp_article_timeout(900, 500, 60) == 440; assert clamp_article_timeout(900, 30, 60) == 450; assert clamp_article_timeout(900, 3600, 60) == 900; assert clamp_article_timeout(100, 500, 60) == 100; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `test -f lib/batch_timeout.py` passes
    - `grep -q 'def clamp_article_timeout' lib/batch_timeout.py` passes
    - `grep -q 'def get_remaining_budget' lib/batch_timeout.py` passes
    - `grep -q 'BATCH_SAFETY_MARGIN_S' lib/batch_timeout.py` passes
    - `python -c "from lib.batch_timeout import clamp_article_timeout; assert clamp_article_timeout(900, 500, 60) == 440"` passes
    - `python -c "from lib.batch_timeout import clamp_article_timeout; assert clamp_article_timeout(900, 30, 60) == 450"` passes
    - `python -c "from lib.batch_timeout import clamp_article_timeout; assert clamp_article_timeout(900, 3600, 60) == 900"` passes
  </acceptance_criteria>
  <done>
    `lib/batch_timeout.py` exists with 3 public symbols and passes import + math smoke tests.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Create tests/unit/test_batch_timeout.py covering all clamp branches</name>
  <files>tests/unit/test_batch_timeout.py</files>
  <behavior>
    Each branch of `clamp_article_timeout` + `get_remaining_budget` has at least one test:
    - TEST A: full budget → no clamp (single_timeout returned)
    - TEST B: late batch → clamp to effective_budget
    - TEST C: budget exhausted (effective_budget == 0) → half-timeout fallback
    - TEST D: budget overrun (remaining_budget < safety_margin) → half-timeout fallback
    - TEST E: half-timeout floor (60s minimum)
    - TEST F: single_timeout < effective_budget → single_timeout wins (not clamp)
    - TEST G: `get_remaining_budget` returns positive float when budget remains
    - TEST H: `get_remaining_budget` floors at 0 when elapsed > total
    - TEST I: constant `BATCH_SAFETY_MARGIN_S == 60`
  </behavior>
  <read_first>
    - lib/batch_timeout.py (just created — this test imports from it)
    - tests/unit/test_timeout_budget.py (Phase 9 reference style — plain assert, no pytest fixtures)
  </read_first>
  <action>
    Create `tests/unit/test_batch_timeout.py` with EXACTLY the following pytest content:

    ```python
    """Phase 17 unit tests for lib/batch_timeout.py (BTIMEOUT-02).

    Covers every branch of clamp_article_timeout and get_remaining_budget.
    Pure-function tests — no mocks, no I/O (except time.time for get_remaining_budget
    which we call directly with deterministic values).
    """
    import time

    from lib.batch_timeout import (
        BATCH_SAFETY_MARGIN_S,
        clamp_article_timeout,
        get_remaining_budget,
    )


    def test_safety_margin_constant_is_60() -> None:
        assert BATCH_SAFETY_MARGIN_S == 60


    def test_full_budget_no_clamp() -> None:
        # Early in batch: 900s single_timeout, 3600s remaining → no clamp.
        assert clamp_article_timeout(900, 3600, 60) == 900


    def test_clamp_kicks_in_late_batch() -> None:
        # Late in batch: 900s single, 500s remaining → clamp to 500-60 = 440.
        assert clamp_article_timeout(900, 500, 60) == 440


    def test_boundary_effective_budget_zero_uses_half_timeout() -> None:
        # remaining=60, safety=60 → effective=0 → half-timeout branch.
        # max(60, int(900*0.5)) = max(60, 450) = 450.
        assert clamp_article_timeout(900, 60, 60) == 450


    def test_budget_overrun_half_timeout_fallback() -> None:
        # remaining=30 < safety_margin=60 → effective negative → half-timeout branch.
        assert clamp_article_timeout(900, 30, 60) == 450


    def test_half_timeout_floors_at_60() -> None:
        # single_timeout=60, effective<=0 → max(60, int(60*0.5)) = max(60, 30) = 60.
        assert clamp_article_timeout(60, 30, 60) == 60


    def test_single_timeout_wins_when_smaller() -> None:
        # single_timeout=100, effective=500-60=440 → min(100, 440) = 100.
        assert clamp_article_timeout(100, 500, 60) == 100


    def test_custom_safety_margin() -> None:
        # safety_margin overrides the default.
        assert clamp_article_timeout(900, 500, 120) == 380  # min(900, 380)


    def test_get_remaining_budget_positive() -> None:
        # batch_start slightly in the past, budget large → positive float returned.
        start = time.time() - 10  # 10s ago
        remaining = get_remaining_budget(start, 3600)
        assert 3580 < remaining <= 3600  # allow clock-tick jitter


    def test_get_remaining_budget_floors_at_zero() -> None:
        # batch_start far in the past → elapsed > budget → floored at 0.
        start = time.time() - 10_000
        assert get_remaining_budget(start, 3600) == 0.0


    def test_get_remaining_budget_returns_float() -> None:
        start = time.time()
        remaining = get_remaining_budget(start, 3600)
        assert isinstance(remaining, float)
    ```

    Do NOT add pytest fixtures, parameterize, or mock — tests are pure assert-based.
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_batch_timeout.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `test -f tests/unit/test_batch_timeout.py` passes
    - `DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_batch_timeout.py -v` → all tests pass (11 tests)
    - `grep -c '^def test_' tests/unit/test_batch_timeout.py` returns ≥ 11 (one per behavior case above)
    - `grep -q 'from lib.batch_timeout import' tests/unit/test_batch_timeout.py` passes
  </acceptance_criteria>
  <done>
    11 unit tests in `tests/unit/test_batch_timeout.py` all pass; coverage includes: no-clamp path,
    clamp path, zero-budget boundary, negative-budget fallback, 60s floor,
    single-timeout-wins, custom safety margin, and `get_remaining_budget` positive + floor +
    return-type cases.
  </done>
</task>

</tasks>

<verification>
```bash
# Module smoke + math
python -c "from lib.batch_timeout import clamp_article_timeout, get_remaining_budget, BATCH_SAFETY_MARGIN_S; assert BATCH_SAFETY_MARGIN_S == 60; assert clamp_article_timeout(900, 500, 60) == 440; assert clamp_article_timeout(900, 30, 60) == 450"

# Unit tests
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_batch_timeout.py -v

# No existing tests broken (Phase 8 regression gate + Phase 9 timeout tests)
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_image_pipeline.py tests/unit/test_timeout_budget.py tests/unit/test_lightrag_llm.py tests/unit/test_lightrag_timeout.py -v
```
</verification>

<success_criteria>
- `lib/batch_timeout.py` exists with 3 public symbols, all documented with docstrings
- `tests/unit/test_batch_timeout.py` has ≥ 11 tests, all pass
- No pre-existing tests broken (Phase 8/9 regression gates green)
- `from lib.batch_timeout import clamp_article_timeout` works from any CWD
- No production code imports this module yet (that's plan 17-02)
</success_criteria>

<output>
After completion, create `.planning/phases/17-batch-timeout-management/17-01-SUMMARY.md`.
</output>
