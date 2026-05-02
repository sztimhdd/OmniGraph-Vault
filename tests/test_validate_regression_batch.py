"""Unit tests for scripts/validate_regression_batch.py pure helpers."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validate_regression_batch as v  # noqa: E402


# --- within_tolerance ------------------------------------------------------


@pytest.mark.parametrize(
    "actual,expected,pct,want",
    [
        (100, 100, 0.10, True),
        (109, 100, 0.10, True),
        (91, 100, 0.10, True),
        (110, 100, 0.10, True),  # boundary
        (90, 100, 0.10, True),   # boundary
        (111, 100, 0.10, False),
        (89, 100, 0.10, False),
        (0, 0, 0.10, True),
        (1, 0, 0.10, False),
    ],
)
def test_within_tolerance(actual, expected, pct, want):
    assert v.within_tolerance(actual, expected, pct) is want


# --- build_report ----------------------------------------------------------


def test_build_report_shape_empty_articles():
    r = v.build_report(articles=[], provider_usage={"siliconflow": 0}, total_wall_time_s=0.0)
    assert set(r.keys()) >= {"batch_id", "timestamp", "articles", "aggregate", "provider_usage"}
    assert set(r["aggregate"].keys()) >= {
        "total_articles",
        "passed",
        "failed",
        "total_wall_time_s",
        "batch_pass",
    }
    # Empty articles cannot be a pass
    assert r["aggregate"]["batch_pass"] is False


def test_build_report_batch_pass_true_when_all_pass():
    articles = [
        {"fixture": "a", "status": "PASS", "timings_ms": {}, "counters": {}, "errors": []},
        {"fixture": "b", "status": "PASS", "timings_ms": {}, "counters": {}, "errors": []},
    ]
    r = v.build_report(articles=articles, provider_usage={}, total_wall_time_s=1.0)
    assert r["aggregate"]["batch_pass"] is True
    assert r["aggregate"]["passed"] == 2
    assert r["aggregate"]["failed"] == 0


def test_build_report_batch_pass_false_on_fail():
    articles = [
        {"fixture": "a", "status": "PASS", "timings_ms": {}, "counters": {}, "errors": []},
        {"fixture": "b", "status": "FAIL", "timings_ms": {}, "counters": {}, "errors": [{"type": "x"}]},
    ]
    r = v.build_report(articles=articles, provider_usage={}, total_wall_time_s=1.0)
    assert r["aggregate"]["batch_pass"] is False
    assert r["aggregate"]["failed"] == 1


def test_build_report_batch_pass_false_on_timeout():
    articles = [
        {"fixture": "a", "status": "TIMEOUT", "timings_ms": {}, "counters": {}, "errors": []},
    ]
    r = v.build_report(articles=articles, provider_usage={}, total_wall_time_s=1.0)
    assert r["aggregate"]["batch_pass"] is False


# --- evaluate_status -------------------------------------------------------


def test_evaluate_status_pass():
    counters = {"images_input": 10, "images_kept": 8, "chunks": 5, "entities": 20}
    meta = {
        "total_images_raw": 10,
        "images_after_filter": 8,
        "expected_chunks": 5,
        "expected_entities": 20,
    }
    assert v.evaluate_status(counters, meta, errors=[], timed_out=False) == "PASS"


def test_evaluate_status_fail_exact_miss():
    counters = {"images_input": 11, "images_kept": 8, "chunks": 5, "entities": 20}
    meta = {
        "total_images_raw": 10,
        "images_after_filter": 8,
        "expected_chunks": 5,
        "expected_entities": 20,
    }
    assert v.evaluate_status(counters, meta, errors=[], timed_out=False) == "FAIL"


def test_evaluate_status_fail_tolerance_miss():
    counters = {"images_input": 10, "images_kept": 8, "chunks": 5, "entities": 100}
    meta = {
        "total_images_raw": 10,
        "images_after_filter": 8,
        "expected_chunks": 5,
        "expected_entities": 20,
    }
    assert v.evaluate_status(counters, meta, errors=[], timed_out=False) == "FAIL"


def test_evaluate_status_timeout_wins():
    assert v.evaluate_status({}, {}, errors=[], timed_out=True) == "TIMEOUT"


def test_evaluate_status_errors_win_over_pass():
    counters = {"images_input": 10, "images_kept": 8, "chunks": 5, "entities": 20}
    meta = {
        "total_images_raw": 10,
        "images_after_filter": 8,
        "expected_chunks": 5,
        "expected_entities": 20,
    }
    assert v.evaluate_status(counters, meta, errors=[{"type": "x"}], timed_out=False) == "FAIL"


# --- write_report (atomic) -------------------------------------------------


def test_write_report_atomic(tmp_path):
    out = tmp_path / "report.json"
    v.write_report(out, {"foo": "bar"})
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8")) == {"foo": "bar"}
    # No .tmp residue
    assert not (tmp_path / "report.json.tmp").exists()


# --- CLI smoke test --------------------------------------------------------


def test_help_exits_zero():
    import subprocess
    script = REPO_ROOT / "scripts" / "validate_regression_batch.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "--fixtures" in result.stdout
    assert "--output" in result.stdout


def test_missing_fixture_exits_nonzero(tmp_path):
    import subprocess
    script = REPO_ROOT / "scripts" / "validate_regression_batch.py"
    out = tmp_path / "r.json"
    result = subprocess.run(
        [sys.executable, str(script), "--fixtures", str(tmp_path / "nope"), "--output", str(out)],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "DEEPSEEK_API_KEY": "dummy"},
    )
    assert result.returncode == 1
    assert out.exists()
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["aggregate"]["batch_pass"] is False
