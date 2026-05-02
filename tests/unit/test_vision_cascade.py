"""Unit tests for lib/vision_cascade.py -- Phase 13 CASC-01..05.

All HTTP is mocked at the `lib.vision_cascade.requests.post` boundary and
Gemini is mocked at `lib.generate_sync`. No real API calls.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from lib.vision_cascade import (
    AllProvidersExhausted429Error,
    AttemptRecord,
    CascadeResult,
    CIRCUIT_FAILURE_THRESHOLD,
    DEFAULT_PROVIDERS,
    RECOVERY_PROBE_INTERVAL,
    RESULT_HTTP_4XX_AUTH,
    RESULT_HTTP_429,
    RESULT_HTTP_503,
    RESULT_SUCCESS,
    RESULT_TIMEOUT,
    VisionCascade,
)


pytestmark = pytest.mark.unit


def _resp(status_code: int = 200, content: str = "stub") -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = {"choices": [{"message": {"content": content}}]}
    r.text = content if status_code == 200 else f"HTTP {status_code}"
    return r


@pytest.fixture
def sf_env(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test-sf")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-or")
    monkeypatch.setenv("OMNIGRAPH_GEMINI_KEY", "sk-test-gm")


# ----------------------------------------------------------- contracts (Task 1)


def test_contracts_construct_default_order(tmp_path, sf_env):
    """Test 1+3: default providers in exact CASC-01 order."""
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    assert cascade.providers == ["siliconflow", "openrouter", "gemini"]
    for p in cascade.providers:
        s = cascade.status[p]
        assert s["failures"] == 0
        assert s["circuit_open"] is False
        assert s["total_attempts"] == 0
        assert s["total_successes"] == 0
        assert s["total_failures"] == 0
        assert s["last_error"] is None
        assert s["next_retry_at"] is None


def test_contracts_dataclasses_frozen():
    """Test 2: frozen dataclasses."""
    rec = AttemptRecord(
        provider="siliconflow", result_code=RESULT_SUCCESS, latency_ms=100
    )
    with pytest.raises(Exception):
        rec.provider = "openrouter"  # type: ignore[misc]
    res = CascadeResult(
        description="d", provider_used="siliconflow", attempts=[rec]
    )
    with pytest.raises(Exception):
        res.description = "x"  # type: ignore[misc]


def test_contracts_status_path(tmp_path, sf_env):
    """Test 4: provider_status.json path."""
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    expected = tmp_path / "_batch" / "provider_status.json"
    assert cascade._status_path == expected


def test_contracts_fresh_dir_no_raise(tmp_path, sf_env):
    """Test 5: no existing status file -> defaults, no raise."""
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    assert not (tmp_path / "_batch" / "provider_status.json").exists()
    assert cascade.status["siliconflow"]["failures"] == 0


def test_contracts_existing_json_loaded(tmp_path, sf_env):
    """Test 6: existing provider_status.json is loaded."""
    batch_dir = tmp_path / "_batch"
    batch_dir.mkdir()
    existing = {
        "siliconflow": {
            "failures": 2,
            "circuit_open": True,
            "total_attempts": 5,
            "total_successes": 3,
            "total_failures": 2,
            "last_error": "prior",
            "next_retry_at": None,
        },
        "openrouter": {
            "failures": 0,
            "circuit_open": False,
            "total_attempts": 0,
            "total_successes": 0,
            "total_failures": 0,
            "last_error": None,
            "next_retry_at": None,
        },
        "gemini": {
            "failures": 0,
            "circuit_open": False,
            "total_attempts": 0,
            "total_successes": 0,
            "total_failures": 0,
            "last_error": None,
            "next_retry_at": None,
        },
    }
    (batch_dir / "provider_status.json").write_text(json.dumps(existing))
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    assert cascade.status["siliconflow"]["failures"] == 2
    assert cascade.status["siliconflow"]["circuit_open"] is True


# ------------------------------------------------------------ describe() flows


def test_siliconflow_success_records_attempt(tmp_path, sf_env, mocker):
    """Test 7: single SF 200 -> provider_used='siliconflow'."""
    mocker.patch(
        "lib.vision_cascade.requests.post", return_value=_resp(200, "desc sf")
    )
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    result = cascade.describe("img_001", b"bytes")
    assert result.provider_used == "siliconflow"
    assert result.description == "desc sf"
    assert len(result.attempts) == 1
    assert cascade.status["siliconflow"]["total_successes"] == 1


def test_siliconflow_503_falls_through_to_openrouter(tmp_path, sf_env, mocker):
    """Test 8: SF 503 + OR 200 -> provider_used='openrouter', SF failures=1."""

    def side(url, *a, **kw):
        if "siliconflow" in url:
            return _resp(503)
        return _resp(200, "openrouter desc")

    mocker.patch("lib.vision_cascade.requests.post", side_effect=side)
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    result = cascade.describe("img_002", b"bytes")
    assert result.provider_used == "openrouter"
    assert result.description == "openrouter desc"
    assert len(result.attempts) == 2
    assert result.attempts[0].result_code == RESULT_HTTP_503
    assert result.attempts[1].result_code == RESULT_SUCCESS
    assert cascade.status["siliconflow"]["failures"] == 1


def test_three_consecutive_503_opens_circuit(tmp_path, sf_env, mocker):
    """Test 9: 3 consecutive 503 on SF -> circuit_open=True, failures=3."""

    def side(url, *a, **kw):
        if "siliconflow" in url:
            return _resp(503)
        return _resp(200, "or ok")

    mocker.patch("lib.vision_cascade.requests.post", side_effect=side)
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    for i in range(3):
        cascade.describe(f"img_{i:03d}", b"x")
    assert cascade.status["siliconflow"]["failures"] == 3
    assert cascade.status["siliconflow"]["circuit_open"] is True


def test_circuit_open_recovery_probe_after_10_skipped(tmp_path, sf_env, mocker):
    """Test 10+11: circuit open -> 10 skipped, probe on 11th, success resets."""
    call_ct = {"sf": 0}

    def side(url, *a, **kw):
        if "siliconflow" in url:
            call_ct["sf"] += 1
            if call_ct["sf"] <= 3:
                return _resp(503)
            return _resp(200, "sf recovered")
        return _resp(200, "or ok")

    mocker.patch("lib.vision_cascade.requests.post", side_effect=side)
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    # Trip the circuit
    for i in range(3):
        cascade.describe(f"img_{i:03d}", b"x")
    assert cascade.status["siliconflow"]["circuit_open"] is True

    # 10 images should skip SF (served by OR). The 10th skip triggers recovery probe.
    for i in range(3, 13):
        res = cascade.describe(f"img_{i:03d}", b"x")
        # Image at skip_count==RECOVERY_PROBE_INTERVAL triggers probe
        # On that probe success, SF returns 200 and is used.
        # All earlier skips go to OR.
    # After 10 skips, the probe fired on the 13th describe call and succeeded.
    assert cascade.status["siliconflow"]["circuit_open"] is False
    assert cascade.status["siliconflow"]["failures"] == 0
    assert cascade.skipped_since_last_probe["siliconflow"] == 0


def test_401_auth_not_counted_as_circuit_failure(tmp_path, sf_env, mocker):
    """Test 12: SF 401 -> does NOT increment failures, cascades to OR."""

    def side(url, *a, **kw):
        if "siliconflow" in url:
            return _resp(401)
        return _resp(200, "or")

    mocker.patch("lib.vision_cascade.requests.post", side_effect=side)
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    result = cascade.describe("img_auth", b"x")
    assert result.provider_used == "openrouter"
    assert cascade.status["siliconflow"]["failures"] == 0
    assert cascade.status["siliconflow"]["circuit_open"] is False
    assert result.attempts[0].result_code == RESULT_HTTP_4XX_AUTH


def test_all_providers_429_raises_stop_batch(tmp_path, sf_env, mocker):
    """Test 13: SF 429 + OR 429 + Gemini 429-like -> AllProvidersExhausted429Error."""
    mocker.patch("lib.vision_cascade.requests.post", return_value=_resp(429))
    # Gemini: patch lib.generate_sync (called inside _call_gemini)
    mocker.patch(
        "lib.generate_sync",
        side_effect=RuntimeError("429 quota exhausted"),
    )
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    with pytest.raises(AllProvidersExhausted429Error, match="img_429"):
        cascade.describe("img_429", b"x")


def test_timeout_counts_as_circuit_failure(tmp_path, sf_env, mocker):
    """Test 14: requests.Timeout -> RESULT_TIMEOUT, counts toward circuit."""

    def side(url, *a, **kw):
        if "siliconflow" in url:
            raise requests.Timeout("deadline exceeded")
        return _resp(200, "or")

    mocker.patch("lib.vision_cascade.requests.post", side_effect=side)
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    result = cascade.describe("img_t", b"x")
    assert result.provider_used == "openrouter"
    assert result.attempts[0].result_code == RESULT_TIMEOUT
    assert cascade.status["siliconflow"]["failures"] == 1


def test_persist_writes_atomic_json_on_disk(tmp_path, sf_env, mocker):
    """Test 15: after describe, provider_status.json on disk matches cascade.status."""
    mocker.patch(
        "lib.vision_cascade.requests.post", return_value=_resp(200, "d")
    )
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    cascade.describe("img_persist", b"x")
    status_file = tmp_path / "_batch" / "provider_status.json"
    assert status_file.exists()
    on_disk = json.loads(status_file.read_text(encoding="utf-8"))
    assert on_disk["siliconflow"]["total_successes"] == 1


def test_per_image_log_lines_emitted(tmp_path, sf_env, mocker, caplog):
    """Test 16: structured log lines per attempt."""
    import logging

    mocker.patch(
        "lib.vision_cascade.requests.post", return_value=_resp(200, "d")
    )
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    caplog.set_level(logging.INFO, logger="lib.vision_cascade")
    cascade.describe("img_log", b"x")
    messages = [r.message for r in caplog.records]
    assert any(
        "image_id=img_log" in m and "provider=siliconflow" in m for m in messages
    )


def test_cascade_order_is_siliconflow_first():
    """Belt-and-braces: DEFAULT_PROVIDERS[0] == 'siliconflow' (CASC-01 lock)."""
    assert DEFAULT_PROVIDERS[0] == "siliconflow"
    assert DEFAULT_PROVIDERS[1] == "openrouter"
    assert DEFAULT_PROVIDERS[2] == "gemini"
    assert CIRCUIT_FAILURE_THRESHOLD == 3
    assert RECOVERY_PROBE_INTERVAL == 10
