"""Phase 5-00b R2 regression guard — asserts production LLMs meet RPD floor.

Background: A Phase 7 lib/models.py edit silently swapped INGESTION_LLM and
VISION_LLM from gemini-3.1-flash-lite-preview (1500+ RPD) to
gemini-2.5-flash-lite (20 RPD). The mistake was single-line, undetected by
the existing test suite, and killed the first 5-hr Phase 5-00b batch on the
5th article when flash-lite's 20-RPD cap exhausted. See
docs/phase5-00b-architecture-review.md § R2.

This test closes that class of bug: any future edit that points a production
ingestion/vision model at something below PRODUCTION_RPD_FLOOR fails CI.
"""
from __future__ import annotations

import os

# lib/__init__.py eagerly imports llm_deepseek which requires DEEPSEEK_API_KEY
# at module load (documented Phase 5 cross-coupling — CLAUDE.md). setdefault
# ensures the test suite works without a real key; the test only reads pure
# constants from lib.models and never calls DeepSeek.
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-used")

import pytest

from lib.models import (
    INGESTION_LLM,
    VISION_LLM,
    PRODUCTION_RPD_FLOOR,
    RATE_LIMITS_RPD,
)


@pytest.mark.parametrize(
    "role, model",
    [
        ("INGESTION_LLM", INGESTION_LLM),
        ("VISION_LLM", VISION_LLM),
    ],
)
def test_production_llm_meets_rpd_floor(role: str, model: str) -> None:
    assert model in RATE_LIMITS_RPD, (
        f"{role}={model!r} missing from RATE_LIMITS_RPD. Add its free-tier RPD "
        f"to lib/models.py so this guard can verify it."
    )
    rpd = RATE_LIMITS_RPD[model]
    assert rpd >= PRODUCTION_RPD_FLOOR, (
        f"{role}={model!r} has free-tier RPD={rpd}, below "
        f"PRODUCTION_RPD_FLOOR={PRODUCTION_RPD_FLOOR}. Using this model on the "
        f"ingestion hot path will exhaust daily quota within the first few "
        f"articles of a batch run. See docs/phase5-00b-architecture-review.md § R2."
    )


def test_rpd_floor_is_nonzero() -> None:
    """Sanity check — guard is only useful if the floor is positive."""
    assert PRODUCTION_RPD_FLOOR > 0
