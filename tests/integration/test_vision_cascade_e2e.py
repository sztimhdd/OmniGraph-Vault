"""Integration tests for Vision Cascade + Circuit Breaker (CASC-01 single provider).

All HTTP is mocked at the requests boundary -- no real API keys needed.
Exercises multi-step state-machine sequences that unit tests can't cover well.

The cascade is pure Bailian qwen3-vl-flash; SiliconFlow / OpenRouter / Gemini
and the balance-switch logic were removed 2026-08-11.

Patch sites:
  - lib.vision_cascade.requests.post          HTTP for the bailian adapter
  - image_pipeline.VisionCascade             class reference inside image_pipeline
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lib.vision_cascade import AllProvidersExhausted429Error, VisionCascade


pytestmark = pytest.mark.integration


# ----------------------------------------------------------------- helpers


def make_post_response(status_code: int = 200, content: str = "stub description"):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = {"choices": [{"message": {"content": content}}]}
    r.text = content if status_code == 200 else f"HTTP {status_code}"
    return r


@pytest.fixture
def cascade_env(monkeypatch, tmp_path):
    """Set fake API keys + redirect checkpoint dir to tmp so tests don't
    pollute ~/.hermes/omonigraph-vault/checkpoints/_batch/provider_status.json.
    """
    monkeypatch.setenv("BAILIAN_API_KEY", "sk-test-bl")
    monkeypatch.setenv("BAILIAN_BASE_URL", "https://bailian.test/v1")
    # Redirect any VisionCascade(checkpoint_dir=None) inside image_pipeline to tmp.
    monkeypatch.setenv("OMNIGRAPH_VISION_CHECKPOINT_DIR", str(tmp_path))
    return tmp_path


# ================================================================ Tests


def test_circuit_opens_after_3_bailian_503s(cascade_env, mocker):
    """Test 1: 3 x 503 -> circuit open + persisted on disk."""
    mocker.patch(
        "lib.vision_cascade.requests.post",
        return_value=make_post_response(503, "upstream unavailable"),
    )
    cascade = VisionCascade(checkpoint_dir=cascade_env)
    for i in range(3):
        res = cascade.describe(f"img_{i:03d}", b"imgbytes")
        assert res.failed is True
        assert res.provider_used is None
    assert cascade.status["bailian"]["circuit_open"] is True
    assert cascade.status["bailian"]["failures"] == 3

    status_path = cascade_env / "_batch" / "provider_status.json"
    assert status_path.exists()
    persisted = json.loads(status_path.read_text(encoding="utf-8"))
    assert persisted["bailian"]["circuit_open"] is True


def test_all_providers_429_raises_stop_batch(cascade_env, mocker):
    """Test 2: all-429 (sole provider) -> AllProvidersExhausted429Error."""
    mocker.patch(
        "lib.vision_cascade.requests.post",
        return_value=make_post_response(429, "quota"),
    )
    cascade = VisionCascade(checkpoint_dir=cascade_env)
    with pytest.raises(AllProvidersExhausted429Error, match="img_stop"):
        cascade.describe("img_stop", b"x")


def test_timeout_fails_image(cascade_env, mocker):
    """Test 3: timeout -> RESULT_TIMEOUT; bailian.failures=1."""
    import requests

    mocker.patch(
        "lib.vision_cascade.requests.post",
        side_effect=requests.Timeout("deadline exceeded"),
    )
    cascade = VisionCascade(checkpoint_dir=cascade_env)
    res = cascade.describe("img_t", b"x")
    assert res.provider_used is None
    assert res.failed is True
    assert len(res.attempts) == 1
    assert res.attempts[0].result_code == "timeout"
    assert cascade.status["bailian"]["failures"] == 1


def test_recovery_after_10_skipped_images(cascade_env, mocker):
    """Test 4: 3x503 -> trip; 10 skips; probe on 10th skip succeeds and
    closes circuit. Image at skip==10 gets bailian (the probe)."""
    call_count = {"bailian": 0}

    def bl_side(url, *a, **kw):
        call_count["bailian"] += 1
        if call_count["bailian"] <= 3:
            return make_post_response(503)
        return make_post_response(200, "recovered bailian")

    mocker.patch("lib.vision_cascade.requests.post", side_effect=bl_side)
    cascade = VisionCascade(checkpoint_dir=cascade_env)
    # Trip circuit (3 x 503)
    for i in range(3):
        cascade.describe(f"img_{i:03d}", b"x")
    assert cascade.status["bailian"]["circuit_open"] is True

    # Next 9 images: bailian skipped (skipped_since_last_probe climbs 1..9),
    # no fallback -> failed results, no HTTP calls.
    for i in range(3, 12):
        res = cascade.describe(f"img_{i:03d}", b"x")
        assert res.failed is True, f"image {i} -> {res.provider_used}"
    assert call_count["bailian"] == 3

    # 10th skip triggers probe on bailian. Mock returns 200 -> circuit closes.
    res = cascade.describe("img_probe", b"x")
    assert res.provider_used == "bailian"
    assert cascade.status["bailian"]["circuit_open"] is False
    assert cascade.status["bailian"]["failures"] == 0


def test_auth_error_does_not_open_circuit(cascade_env, mocker):
    """Test 5: 3 x 401 on bailian -> failures stays 0."""
    mocker.patch(
        "lib.vision_cascade.requests.post",
        return_value=make_post_response(401, "bad api key"),
    )
    cascade = VisionCascade(checkpoint_dir=cascade_env)
    for i in range(3):
        res = cascade.describe(f"img_{i:03d}", b"x")
        assert res.failed is True
    assert cascade.status["bailian"]["failures"] == 0
    assert cascade.status["bailian"]["circuit_open"] is False


def test_provider_status_persists_across_instances(cascade_env, mocker):
    """Test 6: circuit state persists to disk and reloads in new instance."""
    mocker.patch(
        "lib.vision_cascade.requests.post",
        return_value=make_post_response(503),
    )
    c1 = VisionCascade(checkpoint_dir=cascade_env)
    for i in range(3):
        c1.describe(f"img_{i:03d}", b"x")
    assert c1.status["bailian"]["circuit_open"] is True

    c2 = VisionCascade(checkpoint_dir=cascade_env)
    assert c2.status["bailian"]["circuit_open"] is True
    assert c2.status["bailian"]["failures"] == 3


def test_image_pipeline_e2e_happy_path(cascade_env, mocker, tmp_path):
    """Test 7: image_pipeline.describe_images end-to-end with mocked HTTP."""
    mocker.patch(
        "lib.vision_cascade.requests.post",
        return_value=make_post_response(200, "bailian describes"),
    )
    from image_pipeline import describe_images, get_last_describe_stats

    p1 = tmp_path / "a.jpg"
    p1.write_bytes(b"imgdata")
    p2 = tmp_path / "b.jpg"
    p2.write_bytes(b"imgdata")
    result = describe_images([p1, p2])
    assert result[p1] == "bailian describes"
    assert result[p2] == "bailian describes"
    stats = get_last_describe_stats()
    assert stats["provider_mix"] == {"bailian": 2}


def test_bailian_alert_at_batch_end(cascade_env, mocker, tmp_path, caplog):
    """Test 8: 10 images all served by bailian -> WARNING 'vision fallback active'."""
    mocker.patch(
        "lib.vision_cascade.requests.post",
        return_value=make_post_response(200, "bailian describes"),
    )
    from image_pipeline import describe_images

    paths = [tmp_path / f"{i}.jpg" for i in range(10)]
    for p in paths:
        p.write_bytes(b"imgdata")
    caplog.set_level(logging.WARNING)
    describe_images(paths)
    messages = [r.message for r in caplog.records]
    assert any("vision fallback active" in m for m in messages), (
        f"expected bailian alert, got: {messages}"
    )
