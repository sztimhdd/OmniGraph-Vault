"""Tests for lib/rate_limit.py — Phase 7 Wave 0 Task 0.3.

D-08: OMNIGRAPH_RPM_<MODEL_UPPER_UNDERSCORE> env override retained (paid-tier
  forward-compat). Only this RPM override stays; model-name env overrides
  were removed in Amendment 1 (D-02 superseded).
"""
from __future__ import annotations

import os
import pytest


@pytest.fixture(autouse=True)
def _reset_rate(monkeypatch):
    """Isolate rate_limit module state between tests."""
    for var in list(os.environ):
        if var.startswith("OMNIGRAPH_RPM_"):
            monkeypatch.delenv(var, raising=False)
    import lib.rate_limit as r
    r._limiters.clear()


def test_singleton():
    """Same model returns the same AsyncLimiter instance on repeated calls."""
    from lib.rate_limit import get_limiter
    a = get_limiter("gemini-2.5-flash-lite")
    b = get_limiter("gemini-2.5-flash-lite")
    assert a is b


def test_different_models_different_limiters():
    from lib.rate_limit import get_limiter
    a = get_limiter("gemini-2.5-flash-lite")
    b = get_limiter("gemini-2.5-flash")
    assert a is not b


def test_rpm_from_registry():
    """Rate from RATE_LIMITS_RPM is used when no env override present."""
    from lib.rate_limit import get_limiter
    limiter = get_limiter("gemini-2.5-flash-lite")
    assert limiter.max_rate == 15


def test_env_override(monkeypatch):
    """D-08: OMNIGRAPH_RPM_GEMINI_2_5_FLASH_LITE overrides registry value."""
    monkeypatch.setenv("OMNIGRAPH_RPM_GEMINI_2_5_FLASH_LITE", "150")
    from lib.rate_limit import get_limiter
    limiter = get_limiter("gemini-2.5-flash-lite")
    assert limiter.max_rate == 150


def test_env_override_invalid_value_falls_back(monkeypatch):
    """D-08: Non-numeric env value falls back to registry rate."""
    monkeypatch.setenv("OMNIGRAPH_RPM_GEMINI_2_5_FLASH_LITE", "not-a-number")
    from lib.rate_limit import get_limiter
    limiter = get_limiter("gemini-2.5-flash-lite")
    assert limiter.max_rate == 15


def test_unknown_model_default():
    """Unknown models use the conservative _DEFAULT_RPM fallback."""
    from lib.rate_limit import get_limiter
    limiter = get_limiter("unknown-hypothetical-model")
    assert limiter.max_rate == 4
