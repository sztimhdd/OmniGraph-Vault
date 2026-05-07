"""Contract tests pinning the Layer 1/2 placeholder interface.

Quick: 260507-lai (V35-FOUND-01)

These 7 tests pin the interface contract defined in
``lib/article_filter.py``. They are intentionally narrow — every
assertion ties to a single public guarantee that future quicks
introducing real filter logic must NOT break:

    1. ``layer1_pre_filter`` returns a ``FilterResult``.
    2. ``layer1_pre_filter`` passes for arbitrary input (placeholder).
    3. ``layer1_pre_filter`` reason contains the literal ``placeholder``.
    4. ``layer2_full_body_score`` returns a ``FilterResult``.
    5. ``layer2_full_body_score`` passes for arbitrary input (placeholder).
    6. ``layer2_full_body_score`` reason contains the literal ``placeholder``.
    7. ``FilterResult`` is frozen (mutating ``.passed`` raises
       ``FrozenInstanceError``).

Locked decisions:
    - The placeholder reason MUST contain the literal substring
      ``placeholder`` so ops greps can flag any cron run that's still
      relying on always-pass before real logic ships.
    - The frozen-ness check is the only structural guarantee — fields
      can grow if needed (``FilterResult`` may add fields later) but
      the existing ``passed`` / ``reason`` contract must hold.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from lib.article_filter import (
    FilterResult,
    layer1_pre_filter,
    layer2_full_body_score,
)


def test_layer1_returns_filter_result() -> None:
    result = layer1_pre_filter(
        title="Sample article",
        summary="Short digest",
        content_length=None,
    )
    assert isinstance(result, FilterResult)


def test_layer1_passes_for_arbitrary_input() -> None:
    result = layer1_pre_filter(
        title="literally anything",
        summary="even an empty-ish summary",
        content_length=12345,
    )
    assert result.passed is True


def test_layer1_reason_mentions_placeholder() -> None:
    result = layer1_pre_filter(
        title="t",
        summary="s",
        content_length=None,
    )
    assert "placeholder" in result.reason.lower()


def test_layer2_returns_filter_result() -> None:
    result = layer2_full_body_score(
        article_id=1,
        title="Sample article",
        body="# Heading\n\nSome body markdown.",
    )
    assert isinstance(result, FilterResult)


def test_layer2_passes_for_arbitrary_input() -> None:
    result = layer2_full_body_score(
        article_id=42,
        title="another title",
        body="",
    )
    assert result.passed is True


def test_layer2_reason_mentions_placeholder() -> None:
    result = layer2_full_body_score(
        article_id=1,
        title="t",
        body="b",
    )
    assert "placeholder" in result.reason.lower()


def test_filter_result_is_frozen() -> None:
    result = FilterResult(passed=True, reason="immutable")
    with pytest.raises(FrozenInstanceError):
        result.passed = False  # type: ignore[misc]
