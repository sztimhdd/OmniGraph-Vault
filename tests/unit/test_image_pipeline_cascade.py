"""Unit tests for image_pipeline cascade integration -- Phase 13 CASC-01/05/06.

All patches are at the image_pipeline module scope (the import site), not
lib.*, so assertions reflect the actual integration wiring.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lib.siliconflow_balance import BalanceCheckError
from lib.vision_cascade import (
    AllProvidersExhausted429Error,
    AttemptRecord,
    CascadeResult,
)


pytestmark = pytest.mark.unit


def _ok_result(desc: str = "stub desc", provider: str = "siliconflow") -> CascadeResult:
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
        "siliconflow": {"circuit_open": False, "total_successes": 0},
        "openrouter": {"circuit_open": False, "total_successes": 0},
        "gemini": {"circuit_open": False, "total_successes": 0},
    }
    mock_instance.providers = ["siliconflow", "openrouter", "gemini"]
    mock_cls = mocker.patch("image_pipeline.VisionCascade")
    mock_cls.return_value = mock_instance
    return mock_cls, mock_instance


def _write_img(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"fakeimg")
    return p


# -----------------------------------------------------------


def test_describe_images_uses_VisionCascade(tmp_path, mocker, monkeypatch):
    """Test 1: describe_images instantiates VisionCascade + returns its descriptions."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    _mock_cascade(mocker, describe_return=_ok_result("stub desc"))
    from image_pipeline import describe_images

    p1 = _write_img(tmp_path, "a.jpg")
    result = describe_images([p1])
    assert result[p1] == "stub desc"


def test_cascade_order_is_siliconflow_first(tmp_path, mocker, monkeypatch):
    """Test 2: VisionCascade is instantiated with providers starting with siliconflow."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    mock_cls, _ = _mock_cascade(mocker)
    from image_pipeline import describe_images

    p1 = _write_img(tmp_path, "a.jpg")
    describe_images([p1])

    kwargs = mock_cls.call_args.kwargs
    providers = kwargs.get("providers") or mock_cls.call_args.args[0]
    assert providers[0] == "siliconflow"
    assert providers == ["siliconflow", "openrouter", "gemini"]


def test_balance_check_skipped_with_env_flag(tmp_path, mocker, monkeypatch):
    """Test 3: OMNIGRAPH_VISION_SKIP_BALANCE_CHECK=1 means no balance call."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    _mock_cascade(mocker)
    mock_balance = mocker.patch(
        "image_pipeline.check_siliconflow_balance",
        side_effect=AssertionError("should not be called"),
    )
    from image_pipeline import describe_images

    p1 = _write_img(tmp_path, "a.jpg")
    describe_images([p1])
    mock_balance.assert_not_called()


def test_balance_warning_emitted_when_insufficient(
    tmp_path, mocker, monkeypatch, caplog
):
    """Test 4: balance < estimated -> WARNING with 'insufficient'."""
    monkeypatch.delenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", raising=False)
    _mock_cascade(mocker)
    mocker.patch(
        "image_pipeline.check_siliconflow_balance",
        return_value=Decimal("0.01"),
    )
    from image_pipeline import describe_images

    paths = [_write_img(tmp_path, f"{i}.jpg") for i in range(100)]
    caplog.set_level(logging.WARNING, logger="image_pipeline")
    describe_images(paths)
    assert any("insufficient" in r.message for r in caplog.records)


def test_low_balance_switches_to_openrouter_primary(
    tmp_path, mocker, monkeypatch
):
    """Test 5: balance < 0.05 -> cascade built with providers=[openrouter, gemini]."""
    monkeypatch.delenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", raising=False)
    mock_cls, _ = _mock_cascade(mocker)
    mocker.patch(
        "image_pipeline.check_siliconflow_balance",
        return_value=Decimal("0.03"),
    )
    from image_pipeline import describe_images

    p1 = _write_img(tmp_path, "a.jpg")
    describe_images([p1])
    kwargs = mock_cls.call_args.kwargs
    providers = kwargs.get("providers") or mock_cls.call_args.args[0]
    assert "siliconflow" not in providers
    assert providers == ["openrouter", "gemini"]


def test_balance_error_does_not_crash(tmp_path, mocker, monkeypatch, caplog):
    """Test 6: BalanceCheckError -> logged warning, proceed with default cascade."""
    monkeypatch.delenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", raising=False)
    mock_cls, _ = _mock_cascade(mocker)
    mocker.patch(
        "image_pipeline.check_siliconflow_balance",
        side_effect=BalanceCheckError("timeout"),
    )
    from image_pipeline import describe_images

    p1 = _write_img(tmp_path, "a.jpg")
    caplog.set_level(logging.WARNING, logger="image_pipeline")
    result = describe_images([p1])
    assert p1 in result
    kwargs = mock_cls.call_args.kwargs
    providers = kwargs.get("providers") or mock_cls.call_args.args[0]
    assert providers == ["siliconflow", "openrouter", "gemini"]


def test_all_providers_429_stops_batch(tmp_path, mocker, monkeypatch):
    """Test 7: AllProvidersExhausted429Error on 2nd image -> 3rd image not processed."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")

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


def test_empty_paths_list_skips_balance_check(mocker, monkeypatch):
    """Test 8: describe_images([]) -> {} + no balance call."""
    monkeypatch.delenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", raising=False)
    mock_balance = mocker.patch(
        "image_pipeline.check_siliconflow_balance",
        side_effect=AssertionError("should not be called"),
    )
    from image_pipeline import describe_images

    result = describe_images([])
    assert result == {}
    mock_balance.assert_not_called()


def test_batch_end_alert_if_gemini_share_high(
    tmp_path, mocker, monkeypatch, caplog
):
    """Test 9: gemini used on >5% of images -> WARNING."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    # 3 gemini successes out of 10 = 30%
    results = []
    for i in range(10):
        provider = "gemini" if i < 3 else "siliconflow"
        results.append(_ok_result(f"d{i}", provider=provider))
    _mock_cascade(mocker, describe_side_effect=results)
    from image_pipeline import describe_images

    paths = [_write_img(tmp_path, f"{i}.jpg") for i in range(10)]
    caplog.set_level(logging.WARNING, logger="image_pipeline")
    describe_images(paths)
    assert any("gemini used for" in r.message for r in caplog.records)


def test_batch_end_alert_if_circuit_open(tmp_path, mocker, monkeypatch, caplog):
    """Test 10: circuit still open at batch end -> WARNING."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    _, mock_instance = _mock_cascade(mocker)
    # After the batch, cascade reports siliconflow circuit open
    mock_instance.status = {
        "siliconflow": {"circuit_open": True, "total_successes": 0},
        "openrouter": {"circuit_open": False, "total_successes": 1},
        "gemini": {"circuit_open": False, "total_successes": 0},
    }
    mock_instance.describe.return_value = _ok_result(provider="openrouter")
    from image_pipeline import describe_images

    p1 = _write_img(tmp_path, "a.jpg")
    caplog.set_level(logging.WARNING, logger="image_pipeline")
    describe_images([p1])
    assert any("circuits still open" in r.message for r in caplog.records)


def test_get_last_describe_stats_has_new_keys(tmp_path, mocker, monkeypatch):
    """Test 11: stats dict contains circuit_opens, gemini_share, batch_stopped_429."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    _mock_cascade(mocker)
    from image_pipeline import describe_images, get_last_describe_stats

    p1 = _write_img(tmp_path, "a.jpg")
    describe_images([p1])
    stats = get_last_describe_stats()
    assert isinstance(stats["circuit_opens"], list)
    assert isinstance(stats["gemini_share"], float)
    assert isinstance(stats["batch_stopped_429"], bool)


def test_mid_batch_balance_recheck_every_10_images(
    tmp_path, mocker, monkeypatch
):
    """Test 12: mid-batch at i=10 removes siliconflow from cascade.providers."""
    monkeypatch.delenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", raising=False)
    _, mock_instance = _mock_cascade(mocker)

    # pre-batch (i=0) returns high; mid-batch (i=10) returns low -> switch
    balance_values = iter(
        [Decimal("1.00")] + [Decimal("0.03")] * 10
    )
    mocker.patch(
        "image_pipeline.check_siliconflow_balance",
        side_effect=lambda: next(balance_values),
    )
    from image_pipeline import describe_images

    paths = [_write_img(tmp_path, f"{i}.jpg") for i in range(25)]
    describe_images(paths)
    # After the run, mid-batch check at i=10 should have removed siliconflow
    assert "siliconflow" not in mock_instance.providers
