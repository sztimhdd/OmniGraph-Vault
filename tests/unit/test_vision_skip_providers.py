"""Unit tests for OMNIGRAPH_VISION_SKIP_PROVIDERS filter (LDEV-06).

Mock-only — patches image_pipeline.VisionCascade so no outbound HTTP is
attempted. Verifies the providers= list passed to VisionCascade is filtered
per env. The cascade is single-provider (bailian); skip tokens for providers
that no longer exist are simply harmless.
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
        provider_used="bailian",  # any provider the cascade is using
        attempts=[
            AttemptRecord(
                provider="bailian",
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
        "bailian": {"circuit_open": False, "total_successes": 0},
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


def test_skip_legacy_tokens_are_harmless(tmp_path, mocker, monkeypatch) -> None:
    """env='siliconflow,openrouter' → providers == ['bailian'] (legacy tokens
    no longer match anything)."""
    monkeypatch.setenv(
        "OMNIGRAPH_VISION_SKIP_PROVIDERS", "siliconflow,openrouter"
    )
    ctor = _mock_cascade(mocker)
    from image_pipeline import describe_images

    describe_images([_write_img(tmp_path)])
    assert _get_providers_kwarg(ctor) == ["bailian"]


def test_skip_bailian_leaves_empty_list(tmp_path, mocker, monkeypatch) -> None:
    """env='bailian' → providers == [] (cascade will fail fast; documented in
    LOCAL_DEV_SETUP.md)."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_PROVIDERS", "bailian")
    ctor = _mock_cascade(mocker)
    from image_pipeline import describe_images

    describe_images([_write_img(tmp_path)])
    assert _get_providers_kwarg(ctor) == []


def test_env_unset_preserves_default_providers(tmp_path, mocker, monkeypatch) -> None:
    """env unset → providers == list(DEFAULT_PROVIDERS)."""
    monkeypatch.delenv("OMNIGRAPH_VISION_SKIP_PROVIDERS", raising=False)
    ctor = _mock_cascade(mocker)
    from image_pipeline import describe_images

    describe_images([_write_img(tmp_path)])
    assert _get_providers_kwarg(ctor) == list(DEFAULT_PROVIDERS)


def test_whitespace_and_empty_tokens_tolerated(tmp_path, mocker, monkeypatch) -> None:
    """env=' bailian , , ' → providers == []."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_PROVIDERS", " bailian , , ")
    ctor = _mock_cascade(mocker)
    from image_pipeline import describe_images

    describe_images([_write_img(tmp_path)])
    assert _get_providers_kwarg(ctor) == []


def test_unknown_token_is_harmless(tmp_path, mocker, monkeypatch) -> None:
    """env='foo' → providers == ['bailian'] (unknown tokens just don't match
    anything)."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_PROVIDERS", "foo")
    ctor = _mock_cascade(mocker)
    from image_pipeline import describe_images

    describe_images([_write_img(tmp_path)])
    assert _get_providers_kwarg(ctor) == ["bailian"]


def test_mixed_known_and_unknown_tokens(tmp_path, mocker, monkeypatch) -> None:
    """env='foo,bailian' → providers == [] (unknown ignored, bailian skipped)."""
    monkeypatch.setenv("OMNIGRAPH_VISION_SKIP_PROVIDERS", "foo,bailian")
    ctor = _mock_cascade(mocker)
    from image_pipeline import describe_images

    describe_images([_write_img(tmp_path)])
    assert _get_providers_kwarg(ctor) == []
