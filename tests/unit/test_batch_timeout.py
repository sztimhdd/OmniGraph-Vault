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
