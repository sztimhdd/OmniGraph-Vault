"""Unit tests for lib/vision_cascade.py -- CASC-01 (single-provider Bailian).

All HTTP is mocked at the `lib.vision_cascade.requests.post` boundary. No
real API calls. The cascade is pure Bailian qwen3-vl-flash; SiliconFlow /
OpenRouter / Gemini branches were removed 2026-08-11.
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
    RESULT_OTHER,
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
def bailian_env(monkeypatch):
    monkeypatch.setenv("BAILIAN_API_KEY", "sk-test-bl")
    monkeypatch.setenv("BAILIAN_BASE_URL", "https://bailian.test/v1")


# ----------------------------------------------------------- contracts


def test_contracts_construct_default_order(tmp_path, bailian_env):
    """Test 1+3: default providers == single-provider ['bailian']."""
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    assert cascade.providers == ["bailian"]
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
        provider="bailian", result_code=RESULT_SUCCESS, latency_ms=100
    )
    with pytest.raises(Exception):
        rec.provider = "other"  # type: ignore[misc]
    res = CascadeResult(
        description="d", provider_used="bailian", attempts=[rec]
    )
    with pytest.raises(Exception):
        res.description = "x"  # type: ignore[misc]


def test_contracts_status_path(tmp_path, bailian_env):
    """Test 4: provider_status.json path."""
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    expected = tmp_path / "_batch" / "provider_status.json"
    assert cascade._status_path == expected


def test_contracts_fresh_dir_no_raise(tmp_path, bailian_env):
    """Test 5: no existing status file -> defaults, no raise."""
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    assert not (tmp_path / "_batch" / "provider_status.json").exists()
    assert cascade.status["bailian"]["failures"] == 0


def test_contracts_existing_json_loaded(tmp_path, bailian_env):
    """Test 6: existing provider_status.json is loaded."""
    batch_dir = tmp_path / "_batch"
    batch_dir.mkdir()
    existing = {
        "bailian": {
            "failures": 2,
            "circuit_open": True,
            "total_attempts": 5,
            "total_successes": 3,
            "total_failures": 2,
            "last_error": "prior",
            "next_retry_at": None,
        },
    }
    (batch_dir / "provider_status.json").write_text(json.dumps(existing))
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    assert cascade.status["bailian"]["failures"] == 2
    assert cascade.status["bailian"]["circuit_open"] is True


# ------------------------------------------------------------ describe() flows


def test_bailian_success_records_attempt(tmp_path, bailian_env, mocker):
    """Test 7: single bailian 200 -> provider_used='bailian'."""
    mocker.patch(
        "lib.vision_cascade.requests.post", return_value=_resp(200, "desc bl")
    )
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    result = cascade.describe("img_001", b"bytes")
    assert result.provider_used == "bailian"
    assert result.description == "desc bl"
    assert len(result.attempts) == 1
    assert cascade.status["bailian"]["total_successes"] == 1


def test_bailian_503_fails_image(tmp_path, bailian_env, mocker):
    """Test 8: sole provider 503 -> failed result, failures=1."""
    mocker.patch(
        "lib.vision_cascade.requests.post", return_value=_resp(503)
    )
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    result = cascade.describe("img_002", b"bytes")
    assert result.provider_used is None
    assert result.failed is True
    assert len(result.attempts) == 1
    assert result.attempts[0].result_code == RESULT_HTTP_503
    assert cascade.status["bailian"]["failures"] == 1


def test_three_consecutive_503_opens_circuit(tmp_path, bailian_env, mocker):
    """Test 9: 3 consecutive 503 on bailian -> circuit_open=True, failures=3."""
    mocker.patch(
        "lib.vision_cascade.requests.post", return_value=_resp(503)
    )
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    for i in range(3):
        cascade.describe(f"img_{i:03d}", b"x")
    assert cascade.status["bailian"]["failures"] == 3
    assert cascade.status["bailian"]["circuit_open"] is True


def test_circuit_open_recovery_probe_after_10_skipped(
    tmp_path, bailian_env, mocker
):
    """Test 10+11: circuit open -> 10 skipped, probe on 11th, success resets."""
    call_ct = {"bailian": 0}

    def side(url, *a, **kw):
        call_ct["bailian"] += 1
        if call_ct["bailian"] <= 3:
            return _resp(503)
        return _resp(200, "bailian recovered")

    mocker.patch("lib.vision_cascade.requests.post", side_effect=side)
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    # Trip the circuit (3 x 503).
    for i in range(3):
        cascade.describe(f"img_{i:03d}", b"x")
    assert cascade.status["bailian"]["circuit_open"] is True

    # 9 images skipped (circuit open, no fallback -> failed results, no calls).
    for i in range(3, 12):
        res = cascade.describe(f"img_{i:03d}", b"x")
        assert res.failed is True
    assert call_ct["bailian"] == 3  # no calls while skipped

    # The 10th skip triggers the recovery probe; it succeeds and resets.
    res = cascade.describe("img_probe", b"x")
    assert res.provider_used == "bailian"
    assert cascade.status["bailian"]["circuit_open"] is False
    assert cascade.status["bailian"]["failures"] == 0
    assert cascade.skipped_since_last_probe["bailian"] == 0
    assert call_ct["bailian"] == 4


def test_401_auth_not_counted_as_circuit_failure(tmp_path, bailian_env, mocker):
    """Test 12: bailian 401 -> does NOT increment failures."""
    mocker.patch(
        "lib.vision_cascade.requests.post", return_value=_resp(401)
    )
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    result = cascade.describe("img_auth", b"x")
    assert result.provider_used is None
    assert result.attempts[0].result_code == RESULT_HTTP_4XX_AUTH
    assert cascade.status["bailian"]["failures"] == 0
    assert cascade.status["bailian"]["circuit_open"] is False


def test_all_providers_429_raises_stop_batch(tmp_path, bailian_env, mocker):
    """Test 13: sole provider 429 -> AllProvidersExhausted429Error."""
    mocker.patch("lib.vision_cascade.requests.post", return_value=_resp(429))
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    with pytest.raises(AllProvidersExhausted429Error, match="img_429"):
        cascade.describe("img_429", b"x")


def test_timeout_counts_as_circuit_failure(tmp_path, bailian_env, mocker):
    """Test 14: requests.Timeout -> RESULT_TIMEOUT, counts toward circuit."""
    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=requests.Timeout("deadline exceeded"),
    )
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    result = cascade.describe("img_t", b"x")
    assert result.provider_used is None
    assert result.attempts[0].result_code == RESULT_TIMEOUT
    assert cascade.status["bailian"]["failures"] == 1


def test_persist_writes_atomic_json_on_disk(tmp_path, bailian_env, mocker):
    """Test 15: after describe, provider_status.json on disk matches cascade.status."""
    mocker.patch(
        "lib.vision_cascade.requests.post", return_value=_resp(200, "d")
    )
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    cascade.describe("img_persist", b"x")
    status_file = tmp_path / "_batch" / "provider_status.json"
    assert status_file.exists()
    on_disk = json.loads(status_file.read_text(encoding="utf-8"))
    assert on_disk["bailian"]["total_successes"] == 1


def test_per_image_log_lines_emitted(tmp_path, bailian_env, mocker, caplog):
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
        "image_id=img_log" in m and "provider=bailian" in m for m in messages
    )


def test_cascade_order_is_bailian_only():
    """Belt-and-braces: DEFAULT_PROVIDERS is single-provider bailian (CASC-01)."""
    assert DEFAULT_PROVIDERS == ("bailian",)
    assert CIRCUIT_FAILURE_THRESHOLD == 3
    assert RECOVERY_PROBE_INTERVAL == 10


def test_bailian_uses_configured_base_url_and_model(tmp_path, mocker, monkeypatch):
    """Bailian adapter POSTs to BAILIAN_BASE_URL with BAILIAN_VISION_MODEL."""
    monkeypatch.setenv("BAILIAN_API_KEY", "test-key")
    monkeypatch.setenv("BAILIAN_BASE_URL", "https://bailian.test/v1")
    monkeypatch.setenv("BAILIAN_VISION_MODEL", "qwen3-vl-flash")

    mock_post = mocker.patch(
        "lib.vision_cascade.requests.post", return_value=_resp(200, "bailian desc")
    )
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    result = cascade.describe("img_b", b"bytes", mime="image/png")
    assert result.provider_used == "bailian"
    assert result.description == "bailian desc"
    url = mock_post.call_args.args[0]
    assert url == "https://bailian.test/v1/chat/completions"
    payload = mock_post.call_args.kwargs["json"]
    assert payload["model"] == "qwen3-vl-flash"
    assert payload["max_tokens"] == 512


def test_bailian_404_classified_other(tmp_path, mocker, monkeypatch):
    """bailian 404 -> RESULT_OTHER (not circuit-counted), no crash."""
    monkeypatch.setenv("BAILIAN_API_KEY", "test-key")
    monkeypatch.setenv("BAILIAN_BASE_URL", "https://bailian.test/v1")
    mocker.patch(
        "lib.vision_cascade.requests.post", return_value=_resp(404)
    )
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    result = cascade.describe("img_b2", b"bytes")
    assert result.provider_used is None
    assert result.attempts[-1].result_code == RESULT_OTHER


def test_bailian_missing_key_is_4xx_auth(tmp_path, mocker, monkeypatch):
    """bailian without key -> classified as auth (permanent, no retry loop)."""
    monkeypatch.delenv("BAILIAN_API_KEY", raising=False)
    monkeypatch.setenv("BAILIAN_BASE_URL", "https://bailian.test/v1")
    mock_post = mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=AssertionError("should not be called"),
    )
    cascade = VisionCascade(checkpoint_dir=tmp_path)
    result = cascade.describe("img_b3", b"bytes")
    assert result.attempts[-1].result_code == RESULT_HTTP_4XX_AUTH
    assert result.provider_used is None
    mock_post.assert_not_called()
