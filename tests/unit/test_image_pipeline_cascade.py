"""Unit tests for image_pipeline cascade integration -- CASC-01 (single provider).

All patches are at the image_pipeline module scope (the import site), not
lib.*, so assertions reflect the actual integration wiring. The cascade is
pure Bailian qwen3-vl-flash; SiliconFlow / OpenRouter / Gemini and the
balance-switch logic were removed 2026-08-11.
"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lib.vision_cascade import (
    AllProvidersExhausted429Error,
    AttemptRecord,
    CascadeResult,
)


pytestmark = pytest.mark.unit


def _ok_result(desc: str = "stub desc", provider: str = "bailian") -> CascadeResult:
    return CascadeResult(
        description=desc,
        provider_used=provider,
        attempts=[
            AttemptRecord(
                provider=provider,
                result_code="success",
                latency_ms=100,
                desc_chars=len(desc),
            )
        ],
        failed=False,
    )


def _mock_cascade(mocker, describe_return=None, describe_side_effect=None):
    """Return (mock_cls, mock_instance) for the VisionCascade symbol as imported by image_pipeline."""
    mock_instance = MagicMock()
    if describe_side_effect is not None:
        mock_instance.describe.side_effect = describe_side_effect
    else:
        mock_instance.describe.return_value = describe_return or _ok_result()
    # Baseline status: no circuits open, no successes by default
    mock_instance.status = {
        "bailian": {"circuit_open": False, "total_successes": 0},
    }
    mock_instance.providers = ["bailian"]
    mock_cls = mocker.patch("image_pipeline.VisionCascade")
    mock_cls.return_value = mock_instance
    return mock_cls, mock_instance


def _write_img(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"fakeimg")
    return p


# -----------------------------------------------------------


def test_describe_images_uses_VisionCascade(tmp_path, mocker):
    """Test 1: describe_images instantiates VisionCascade + returns its descriptions."""
    _mock_cascade(mocker, describe_return=_ok_result("stub desc"))
    from image_pipeline import describe_images

    p1 = _write_img(tmp_path, "a.jpg")
    result = describe_images([p1])
    assert result[p1] == "stub desc"


def test_cascade_providers_is_bailian_only(tmp_path, mocker):
    """Test 2: VisionCascade is instantiated with providers=['bailian']."""
    mock_cls, _ = _mock_cascade(mocker)
    from image_pipeline import describe_images

    p1 = _write_img(tmp_path, "a.jpg")
    describe_images([p1])

    kwargs = mock_cls.call_args.kwargs
    providers = kwargs.get("providers") or mock_cls.call_args.args[0]
    assert providers == ["bailian"]


def test_all_providers_429_stops_batch(tmp_path, mocker):
    """Test 3: AllProvidersExhausted429Error on 2nd image -> 3rd image not processed."""
    def describe_side(image_id, image_bytes, mime):
        if image_id == "img_001":
            raise AllProvidersExhausted429Error(f"image_id={image_id}: all 429")
        return _ok_result()

    _mock_cascade(mocker, describe_side_effect=describe_side)
    from image_pipeline import describe_images, get_last_describe_stats

    p1 = _write_img(tmp_path, "a.jpg")
    p2 = _write_img(tmp_path, "b.jpg")
    p3 = _write_img(tmp_path, "c.jpg")
    result = describe_images([p1, p2, p3])
    assert p1 in result
    assert p2 in result  # error recorded
    assert p3 not in result  # batch stopped before
    stats = get_last_describe_stats()
    assert stats["batch_stopped_429"] is True


def test_empty_paths_list_returns_empty(tmp_path, mocker):
    """Test 4: describe_images([]) -> {} with zeroed stats."""
    _mock_cascade(mocker)
    from image_pipeline import describe_images, get_last_describe_stats

    result = describe_images([])
    assert result == {}
    stats = get_last_describe_stats()
    assert stats["provider_mix"] == {}
    assert stats["vision_success"] == 0
    assert stats["batch_stopped_429"] is False


def test_batch_end_alert_if_last_resort_share_high(tmp_path, mocker, caplog):
    """Test 5: sole provider handles >5% of images -> 'vision fallback active' WARNING."""
    # Single-provider cascade: bailian serves every image (share = 100%).
    results = [_ok_result(f"d{i}", provider="bailian") for i in range(10)]
    _mock_cascade(mocker, describe_side_effect=results)
    from image_pipeline import describe_images

    paths = [_write_img(tmp_path, f"{i}.jpg") for i in range(10)]
    caplog.set_level(logging.WARNING, logger="image_pipeline")
    describe_images(paths)
    assert any("vision fallback active" in r.message for r in caplog.records)


def test_batch_end_alert_if_circuit_open(tmp_path, mocker, caplog):
    """Test 6: circuit still open at batch end -> WARNING."""
    _, mock_instance = _mock_cascade(mocker)
    # After the batch, cascade reports bailian circuit open
    mock_instance.status = {
        "bailian": {"circuit_open": True, "total_successes": 0},
    }
    mock_instance.describe.return_value = _ok_result(provider="bailian")
    from image_pipeline import describe_images

    p1 = _write_img(tmp_path, "a.jpg")
    caplog.set_level(logging.WARNING, logger="image_pipeline")
    describe_images([p1])
    assert any("circuits still open" in r.message for r in caplog.records)


def test_get_last_describe_stats_has_new_keys(tmp_path, mocker):
    """Test 7: stats dict contains circuit_opens, last_resort_share, batch_stopped_429."""
    _mock_cascade(mocker)
    from image_pipeline import describe_images, get_last_describe_stats

    p1 = _write_img(tmp_path, "a.jpg")
    describe_images([p1])
    stats = get_last_describe_stats()
    assert isinstance(stats["circuit_opens"], list)
    assert isinstance(stats["last_resort_share"], float)
    assert isinstance(stats["batch_stopped_429"], bool)
    assert stats["provider_mix"] == {"bailian": 1}


def test_provider_mix_only_records_bailian(tmp_path, mocker):
    """Test 8: provider_mix only ever contains the bailian counter."""
    _mock_cascade(mocker)
    from image_pipeline import describe_images, get_last_describe_stats

    paths = [_write_img(tmp_path, f"{i}.jpg") for i in range(5)]
    describe_images(paths)
    stats = get_last_describe_stats()
    assert stats["provider_mix"] == {"bailian": 5}
