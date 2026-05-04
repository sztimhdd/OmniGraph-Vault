"""Unit tests for OMNIGRAPH_VISION_SKIP_PROVIDERS filter (LDEV-06).

Mock-only — patches image_pipeline.VisionCascade + check_siliconflow_balance
so no outbound HTTP is attempted. Verifies the providers= list passed to
VisionCascade is filtered per env.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lib.vision_cascade import AttemptRecord, CascadeResult, DEFAULT_PROVIDERS


pytestmark = pytest.mark.unit


def _ok_result() -> CascadeResult:
    return CascadeResult(
        description="stub",
        provider_used="gemini",  # any provider the cascade is using
        attempts=[
            AttemptRecord(
                provider="gemini",
                result_code="success",
                latency_ms=1,
                desc_chars=4,
            )
        ],
        failed=False,
    )


def _mock_cascade(mocker) -> MagicMock:
    """Patch image_pipeline.VisionCascade; return the ctor mock."""
    instance = MagicMock()
    instance.describe.return_value = _ok_result()
    instance.status = {
        "siliconflow": {"circuit_open": False, "total_successes": 0},
        "openrouter": {"circuit_open": False, "total_successes": 0},
        "gemini": {"circuit_open": False, "total_successes": 0},
    }
    instance.providers = list(DEFAULT_PROVIDERS)
    ctor = mocker.patch("image_pipeline.VisionCascade")
    ctor.return_value = instance
    return ctor


def _write_img(tmp_path: Path, name: str = "a.jpg") -> Path:
    p = tmp_path / name
    p.write_bytes(b"fake")
    return p


def _get_providers_kwarg(ctor: MagicMock) -> list[str]:
    """Extract the providers= list from the (mocked) VisionCascade ctor call."""
    kwargs = ctor.call_args.kwargs
    if "providers" in kwargs:
        return list(kwargs["providers"])
    return list(ctor.call_args.args[0])


# --- Tests -----------------------------------------------------------------


def test_skip_siliconflow_only(tmp_path, mocker, monkeypatch) -> None:
    """env=siliconflow → providers == ['openrouter','gemini']."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_PROVIDERS", "siliconflow")
    ctor = _mock_cascade(mocker)
    from image_pipeline import describe_images

    describe_images([_write_img(tmp_path)])
    assert _get_providers_kwarg(ctor) == ["openrouter", "gemini"]


def test_skip_siliconflow_and_openrouter(tmp_path, mocker, monkeypatch) -> None:
    """env=siliconflow,openrouter → providers == ['gemini']."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    monkeypatch.setenv(
        "OMNIGRAPH_VISION_SKIP_PROVIDERS", "siliconflow,openrouter"
    )
    ctor = _mock_cascade(mocker)
    from image_pipeline import describe_images

    describe_images([_write_img(tmp_path)])
    assert _get_providers_kwarg(ctor) == ["gemini"]


def test_skip_all_leaves_empty_list(tmp_path, mocker, monkeypatch) -> None:
    """env=siliconflow,openrouter,gemini → providers == [] (cascade will fail
    fast; documented in LOCAL_DEV_SETUP.md)."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    monkeypatch.setenv(
        "OMNIGRAPH_VISION_SKIP_PROVIDERS", "siliconflow,openrouter,gemini"
    )
    ctor = _mock_cascade(mocker)
    from image_pipeline import describe_images

    describe_images([_write_img(tmp_path)])
    assert _get_providers_kwarg(ctor) == []


def test_env_unset_preserves_default_providers(tmp_path, mocker, monkeypatch) -> None:
    """env unset → providers == list(DEFAULT_PROVIDERS)."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    monkeypatch.delenv("OMNIGRAPH_VISION_SKIP_PROVIDERS", raising=False)
    ctor = _mock_cascade(mocker)
    from image_pipeline import describe_images

    describe_images([_write_img(tmp_path)])
    assert _get_providers_kwarg(ctor) == list(DEFAULT_PROVIDERS)


def test_whitespace_and_empty_tokens_tolerated(tmp_path, mocker, monkeypatch) -> None:
    """env=' siliconflow , ,openrouter ' → providers == ['gemini']."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    monkeypatch.setenv(
        "OMNIGRAPH_VISION_SKIP_PROVIDERS", " siliconflow , ,openrouter "
    )
    ctor = _mock_cascade(mocker)
    from image_pipeline import describe_images

    describe_images([_write_img(tmp_path)])
    assert _get_providers_kwarg(ctor) == ["gemini"]


def test_unknown_token_is_harmless(tmp_path, mocker, monkeypatch) -> None:
    """env='foo,siliconflow' → providers == ['openrouter','gemini'] (unknown
    tokens just don't match anything)."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_BALANCE_CHECK", "1")
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_PROVIDERS", "foo,siliconflow")
    ctor = _mock_cascade(mocker)
    from image_pipeline import describe_images

    describe_images([_write_img(tmp_path)])
    assert _get_providers_kwarg(ctor) == ["openrouter", "gemini"]
