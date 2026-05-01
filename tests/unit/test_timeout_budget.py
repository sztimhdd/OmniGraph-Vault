"""TIMEOUT-03: _compute_article_budget_s formula (D-09.03).

Pure-unit tests — no imports of heavy modules (lightrag, etc.). Verifies
formula is correct per PRD § TIMEOUT-03.

Formula: ``max(120 + 30 * chunk_count, 900)`` where
``chunk_count = max(1, len(full_content) // 4800)``.
"""
from __future__ import annotations


def _budget(content: str) -> int:
    # Import inside the test so a missing _compute_article_budget_s surfaces
    # as an AssertionError-shaped ImportError at call time, not collection time.
    from batch_ingest_from_spider import _compute_article_budget_s
    return _compute_article_budget_s(content)


def test_floor_for_empty_content() -> None:
    """Empty content -> chunk_count=1 -> max(120+30, 900) == 900."""
    assert _budget("") == 900


def test_floor_for_small_article() -> None:
    """Small article (<1 chunk_size) -> chunk_count=1 -> floor."""
    assert _budget("x" * 1000) == 900


def test_floor_for_mid_size() -> None:
    """20 chunks -> 120 + 600 = 720; below floor -> 900."""
    # 20 * 4800 = 96,000 chars
    assert _budget("x" * 96_000) == 900


def test_scales_above_floor() -> None:
    """50 chunks -> 120 + 1500 = 1620; above floor -> 1620."""
    # 50 * 4800 = 240,000 chars
    assert _budget("x" * 240_000) == 1620


def test_large_article() -> None:
    """100 chunks -> 120 + 3000 = 3120; above floor -> 3120."""
    # 100 * 4800 = 480,000 chars
    assert _budget("x" * 480_000) == 3120


def test_chunk_count_is_floored_at_1() -> None:
    """Content shorter than chunk_size still counts as 1 chunk."""
    # 1 char -> chunk_count = max(1, 0) = 1 -> 150 budget -> floor 900.
    assert _budget("x") == 900
