"""Per-model async rate limiter using aiolimiter (leaky-bucket).

D-08: OMNIGRAPH_RPM_<MODEL_UPPER_UNDERSCORED> env var overrides the
RATE_LIMITS_RPM constant for that model — forward-compat with paid-tier upgrade.
Example: OMNIGRAPH_RPM_GEMINI_2_5_FLASH_LITE=150 bumps flash-lite from
free-tier 15 RPM to Tier 1's 150 RPM without a code change.

Limiters are singletons per model — the first get_limiter(model) call creates
and caches the instance; subsequent calls return the same object.
"""
from __future__ import annotations

import os

from aiolimiter import AsyncLimiter

from .models import RATE_LIMITS_RPM

_DEFAULT_RPM = 4
_limiters: dict[str, AsyncLimiter] = {}


def _env_rpm(model: str) -> int | None:
    """Look up OMNIGRAPH_RPM_<MODEL_UPPER_UNDERSCORE> env var."""
    key = "OMNIGRAPH_RPM_" + model.upper().replace("-", "_").replace(".", "_")
    val = os.environ.get(key)
    if val:
        try:
            return int(val)
        except ValueError:
            return None
    return None


def get_limiter(model: str) -> AsyncLimiter:
    """Return the AsyncLimiter singleton for *model*.

    Rate (RPM) is resolved by: env override > RATE_LIMITS_RPM registry > _DEFAULT_RPM.
    """
    if model not in _limiters:
        rpm = _env_rpm(model) or RATE_LIMITS_RPM.get(model, _DEFAULT_RPM)
        _limiters[model] = AsyncLimiter(max_rate=rpm, time_period=60)
    return _limiters[model]
