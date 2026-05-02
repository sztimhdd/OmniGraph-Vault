"""Phase 17 unit tests for batch_ingest_from_spider.py instrumentation helpers.

Tests the three pure helpers added in plan 17-02:
  - _bucket_article_time
  - _resolve_batch_timeout (env override behavior)
  - _build_batch_timeout_metrics (output schema shape)
"""
import time

import pytest

import batch_ingest_from_spider as b


# --- _bucket_article_time ---------------------------------------------------

@pytest.mark.parametrize("seconds,expected", [
    (0, "0-60s"),
    (30, "0-60s"),
    (59.9, "0-60s"),
    (60, "60-300s"),
    (200, "60-300s"),
    (299.9, "60-300s"),
    (300, "300-900s"),
    (500, "300-900s"),
    (899.9, "300-900s"),
    (900, "900s+"),
    (5000, "900s+"),
])
def test_bucket_article_time(seconds: float, expected: str) -> None:
    assert b._bucket_article_time(seconds) == expected


# --- _resolve_batch_timeout -------------------------------------------------

def test_resolve_batch_timeout_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMNIGRAPH_BATCH_TIMEOUT_SEC", raising=False)
    assert b._resolve_batch_timeout(None) == 28800  # 8h — v3.1 closure §3 Hermes baseline × 56 + headroom


def test_resolve_batch_timeout_cli_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMNIGRAPH_BATCH_TIMEOUT_SEC", raising=False)
    assert b._resolve_batch_timeout(7200) == 7200


def test_resolve_batch_timeout_env_wins_over_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIGRAPH_BATCH_TIMEOUT_SEC", "1800")
    assert b._resolve_batch_timeout(7200) == 1800


def test_resolve_batch_timeout_invalid_env_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIGRAPH_BATCH_TIMEOUT_SEC", "not-an-int")
    assert b._resolve_batch_timeout(None) == 28800
    assert b._resolve_batch_timeout(5400) == 5400


# --- _build_batch_timeout_metrics -------------------------------------------

_EXPECTED_KEYS = {
    "total_batch_budget_sec",
    "total_elapsed_sec",
    "batch_progress_vs_budget",
    "total_articles",
    "completed_articles",
    "timed_out_articles",
    "not_started_articles",
    "avg_article_time_sec",
    "timeout_histogram",
    "clamped_timeouts",
    "safety_margin_triggered",
}


def test_metrics_has_all_11_top_level_keys() -> None:
    metrics = b._build_batch_timeout_metrics(
        total_budget=3600,
        batch_start=time.time() - 100,
        completed_times=[50.0, 60.0, 70.0],
        total_articles=5,
        timed_out=1,
        clamped_count=2,
        safety_margin_triggered=False,
        histogram={"0-60s": 1, "60-300s": 2, "300-900s": 0, "900s+": 0},
    )
    assert set(metrics.keys()) == _EXPECTED_KEYS


def test_metrics_avg_article_time_is_null_when_zero_completed() -> None:
    metrics = b._build_batch_timeout_metrics(
        total_budget=3600,
        batch_start=time.time() - 10,
        completed_times=[],
        total_articles=5,
        timed_out=0,
        clamped_count=0,
        safety_margin_triggered=False,
        histogram={"0-60s": 0, "60-300s": 0, "300-900s": 0, "900s+": 0},
    )
    assert metrics["avg_article_time_sec"] is None
    assert metrics["completed_articles"] == 0


def test_metrics_avg_article_time_matches_mean() -> None:
    metrics = b._build_batch_timeout_metrics(
        total_budget=3600,
        batch_start=time.time() - 100,
        completed_times=[50.0, 60.0, 70.0],
        total_articles=3,
        timed_out=0,
        clamped_count=0,
        safety_margin_triggered=False,
        histogram={"0-60s": 1, "60-300s": 2, "300-900s": 0, "900s+": 0},
    )
    assert metrics["avg_article_time_sec"] == 60.0
    assert metrics["completed_articles"] == 3
    assert metrics["not_started_articles"] == 0


def test_metrics_not_started_computed_correctly() -> None:
    # 10 total, 5 completed, 2 timed out → 3 not_started
    metrics = b._build_batch_timeout_metrics(
        total_budget=3600,
        batch_start=time.time() - 100,
        completed_times=[10.0] * 5,
        total_articles=10,
        timed_out=2,
        clamped_count=0,
        safety_margin_triggered=False,
        histogram={"0-60s": 5, "60-300s": 0, "300-900s": 0, "900s+": 2},
    )
    assert metrics["not_started_articles"] == 3


def test_metrics_safety_margin_triggered_flag_preserved() -> None:
    metrics = b._build_batch_timeout_metrics(
        total_budget=3600,
        batch_start=time.time() - 100,
        completed_times=[50.0],
        total_articles=1,
        timed_out=0,
        clamped_count=1,
        safety_margin_triggered=True,
        histogram={"0-60s": 1, "60-300s": 0, "300-900s": 0, "900s+": 0},
    )
    assert metrics["safety_margin_triggered"] is True
    assert metrics["clamped_timeouts"] == 1
