"""Integration tests for Phase 13 Vision Cascade + Circuit Breaker + Balance.

All HTTP is mocked at the requests boundary -- no real API keys needed.
Exercises multi-step state-machine sequences that unit tests can't cover well.

Patch sites:
  - lib.vision_cascade.requests.post          HTTP for SF/OR adapters
  - lib.generate_sync                         Gemini last-resort
  - image_pipeline.VisionCascade              class reference inside image_pipeline
  - image_pipeline.check_siliconflow_balance  balance helper reference
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from lib.vision_cascade import (
    AllProvidersExhausted429Error,
    VisionCascade,
)
from lib.siliconflow_balance import BalanceCheckError


pytestmark = pytest.mark.integration


# ----------------------------------------------------------------- helpers


def make_post_response(status_code: int = 200, content: str = "stub description"):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = {"choices": [{"message": {"content": content}}]}
    r.text = content if status_code == 200 else f"HTTP {status_code}"
    return r


def route_by_url(siliconflow_resp, openrouter_resp):
    """Return a side_effect for requests.post that routes by URL.

    siliconflow_resp / openrouter_resp may be:
      - a plain callable (function, not MagicMock) -> invoked per request
      - an Exception instance -> raised per request
      - anything else -> returned as-is
    MagicMock instances are returned as-is (not called) because MagicMocks are
    callable but we use them as the response object themselves.
    """

    def _side_effect(url, *args, **kwargs):
        resp = siliconflow_resp if "siliconflow" in url else (
            openrouter_resp if "openrouter" in url else None
        )
        if resp is None:
            raise ValueError(f"unexpected url: {url}")
        if isinstance(resp, Exception):
            raise resp
        # Only invoke plain functions (not MagicMock instances).
        if callable(resp) and not isinstance(resp, MagicMock):
            return resp()
        return resp

    return _side_effect


@pytest.fixture
def cascade_env(monkeypatch, tmp_path):
    """Set fake API keys + redirect checkpoint dir to tmp so tests don't
    pollute ~/.hermes/omonigraph-vault/checkpoints/_batch/provider_status.json.
    """
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test-sf")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-or")
    monkeypatch.setenv("OMNIGRAPH_GEMINI_KEY", "sk-test-gm")
    # Redirect any VisionCascade(checkpoint_dir=None) inside image_pipeline to tmp.
    monkeypatch.setenv("OMNIGRAPH_VISION_CHECKPOINT_DIR", str(tmp_path))
    return tmp_path


# ================================================================ Tests


def test_circuit_opens_after_3_siliconflow_503s(cascade_env, mocker):
    """Test 1: 3 x 503 -> circuit open + persisted on disk."""
    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=route_by_url(
            siliconflow_resp=make_post_response(503, "upstream unavailable"),
            openrouter_resp=make_post_response(200, "openrouter desc"),
        ),
    )
    cascade = VisionCascade(checkpoint_dir=cascade_env)
    for i in range(3):
        res = cascade.describe(f"img_{i:03d}", b"imgbytes")
        assert res.provider_used == "openrouter"
    assert cascade.status["siliconflow"]["circuit_open"] is True
    assert cascade.status["siliconflow"]["failures"] == 3

    status_path = cascade_env / "_batch" / "provider_status.json"
    assert status_path.exists()
    persisted = json.loads(status_path.read_text(encoding="utf-8"))
    assert persisted["siliconflow"]["circuit_open"] is True


def test_all_providers_429_raises_stop_batch(cascade_env, mocker):
    """Test 2: all-429 (SF + OR + Gemini) -> AllProvidersExhausted429Error."""
    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=route_by_url(
            siliconflow_resp=make_post_response(429, "quota"),
            openrouter_resp=make_post_response(429, "quota"),
        ),
    )
    mocker.patch(
        "lib.generate_sync",
        side_effect=RuntimeError("429 quota exhausted"),
    )
    cascade = VisionCascade(checkpoint_dir=cascade_env)
    with pytest.raises(AllProvidersExhausted429Error, match="img_stop"):
        cascade.describe("img_stop", b"x")


def test_siliconflow_timeout_falls_through_to_openrouter(cascade_env, mocker):
    """Test 3: SF timeout -> OpenRouter 200; SF.failures=1."""
    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=route_by_url(
            siliconflow_resp=requests.Timeout("deadline exceeded"),
            openrouter_resp=make_post_response(200, "openrouter served"),
        ),
    )
    cascade = VisionCascade(checkpoint_dir=cascade_env)
    res = cascade.describe("img_t", b"x")
    assert res.provider_used == "openrouter"
    assert res.description == "openrouter served"
    assert len(res.attempts) == 2
    assert res.attempts[0].result_code == "timeout"
    assert res.attempts[1].result_code == "success"
    assert cascade.status["siliconflow"]["failures"] == 1


def test_recovery_after_10_skipped_images(cascade_env, mocker):
    """Test 4: 3x503 -> trip; 9 skips to OR; probe on 10th skip succeeds and
    closes circuit. Image at skip==10 gets SiliconFlow (the probe).
    """
    call_count = {"siliconflow": 0}

    def sf_side(url, *a, **kw):
        if "siliconflow" in url:
            call_count["siliconflow"] += 1
            if call_count["siliconflow"] <= 3:
                return make_post_response(503)
            return make_post_response(200, "recovered sf")
        return make_post_response(200, "openrouter")

    mocker.patch("lib.vision_cascade.requests.post", side_effect=sf_side)
    cascade = VisionCascade(checkpoint_dir=cascade_env)
    # Trip circuit (3 x 503)
    for i in range(3):
        cascade.describe(f"img_{i:03d}", b"x")
    assert cascade.status["siliconflow"]["circuit_open"] is True

    # Next 9 images: SF skipped (skipped_since_last_probe climbs 1..9), OR serves.
    for i in range(3, 12):
        res = cascade.describe(f"img_{i:03d}", b"x")
        assert res.provider_used == "openrouter", f"image {i} -> {res.provider_used}"

    # 10th skip triggers probe on SF. Mock returns 200 -> circuit closes.
    res = cascade.describe("img_probe", b"x")
    assert res.provider_used == "siliconflow"
    assert cascade.status["siliconflow"]["circuit_open"] is False
    assert cascade.status["siliconflow"]["failures"] == 0


def test_auth_error_does_not_open_circuit(cascade_env, mocker):
    """Test 5: 3 x 401 on SF -> failures stays 0, OR served."""
    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=route_by_url(
            siliconflow_resp=make_post_response(401, "bad api key"),
            openrouter_resp=make_post_response(200, "ok"),
        ),
    )
    cascade = VisionCascade(checkpoint_dir=cascade_env)
    for i in range(3):
        res = cascade.describe(f"img_{i:03d}", b"x")
        assert res.provider_used == "openrouter"
    assert cascade.status["siliconflow"]["failures"] == 0
    assert cascade.status["siliconflow"]["circuit_open"] is False


def test_provider_status_persists_across_instances(cascade_env, mocker):
    """Test 6: circuit state persists to disk and reloads in new instance."""
    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=route_by_url(
            siliconflow_resp=make_post_response(503),
            openrouter_resp=make_post_response(200),
        ),
    )
    c1 = VisionCascade(checkpoint_dir=cascade_env)
    for i in range(3):
        c1.describe(f"img_{i:03d}", b"x")
    assert c1.status["siliconflow"]["circuit_open"] is True

    c2 = VisionCascade(checkpoint_dir=cascade_env)
    assert c2.status["siliconflow"]["circuit_open"] is True
    assert c2.status["siliconflow"]["failures"] == 3


def test_image_pipeline_e2e_happy_path(
    cascade_env, mocker, tmp_path, monkeypatch
):
    """Test 7: image_pipeline.describe_images end-to-end with mocked HTTP."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    mocker.patch(
        "lib.vision_cascade.requests.post",
        return_value=make_post_response(200, "siliconflow describes"),
    )
    from image_pipeline import describe_images, get_last_describe_stats

    p1 = tmp_path / "a.jpg"
    p1.write_bytes(b"imgdata")
    p2 = tmp_path / "b.jpg"
    p2.write_bytes(b"imgdata")
    result = describe_images([p1, p2])
    assert result[p1] == "siliconflow describes"
    assert result[p2] == "siliconflow describes"
    stats = get_last_describe_stats()
    assert stats["provider_mix"].get("siliconflow", 0) == 2
    assert stats["provider_mix"].get("gemini", 0) == 0


def test_mid_batch_switch_to_openrouter_below_floor(
    cascade_env, mocker, tmp_path, monkeypatch
):
    """Test 8: 25 paths, balance drops at i=10 -> SF removed, OR takes over."""
    monkeypatch.delenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", raising=False)
    balance_seq = iter(
        [Decimal("1.00"), Decimal("0.03"), Decimal("0.03"), Decimal("0.03")]
    )
    mocker.patch(
        "image_pipeline.check_siliconflow_balance",
        side_effect=lambda: next(balance_seq),
    )
    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=route_by_url(
            siliconflow_resp=make_post_response(200, "sf"),
            openrouter_resp=make_post_response(200, "or"),
        ),
    )
    from image_pipeline import describe_images, get_last_describe_stats

    paths = [tmp_path / f"{i}.jpg" for i in range(25)]
    for p in paths:
        p.write_bytes(b"imgdata")
    describe_images(paths)
    mix = get_last_describe_stats()["provider_mix"]
    # Before i=10 balance is fine -> siliconflow. At i=10 switch -> rest openrouter.
    assert mix.get("siliconflow", 0) == 10
    assert mix.get("openrouter", 0) == 15


def test_gemini_alert_at_batch_end(
    cascade_env, mocker, tmp_path, monkeypatch, caplog
):
    """Test 9: 10 images all served by Gemini -> WARNING 'gemini used for'."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=route_by_url(
            siliconflow_resp=make_post_response(503),
            openrouter_resp=make_post_response(503),
        ),
    )
    mocker.patch("lib.generate_sync", return_value="gemini describes")
    from image_pipeline import describe_images

    paths = [tmp_path / f"{i}.jpg" for i in range(10)]
    for p in paths:
        p.write_bytes(b"imgdata")
    caplog.set_level(logging.WARNING)
    describe_images(paths)
    messages = [r.message for r in caplog.records]
    assert any("gemini used for" in m for m in messages), (
        f"expected gemini alert, got: {messages}"
    )
