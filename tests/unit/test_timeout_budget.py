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


def test_drain_layer2_queue_call_site_uses_dynamic_budget() -> None:
    """2026-05-08 regression: per-article timeout in _drain_layer2_queue
    MUST compute budget from body length, not hardcode _SINGLE_CHUNK_FLOOR_S.

    Pre-fix:
        effective_timeout = clamp_article_timeout(
            _SINGLE_CHUNK_FLOOR_S, remaining, BATCH_SAFETY_MARGIN_S
        )
    → 50-chunk articles (~1620s real need) all hit 900s timeout.

    Post-fix:
        article_budget = _compute_article_budget_s(body or "")
        effective_timeout = clamp_article_timeout(
            article_budget, remaining, BATCH_SAFETY_MARGIN_S
        )
    """
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent.parent / "batch_ingest_from_spider.py"
    content = src.read_text(encoding="utf-8")

    # Locate _drain_layer2_queue body
    drain_marker = "async def _drain_layer2_queue"
    drain_start = content.index(drain_marker)
    # End at the for-loop that starts the candidate iteration
    drain_end = content.index("# v3.5 ir-1 (LF-3.1): iterate over candidate_rows", drain_start)
    drain_body = content[drain_start:drain_end]

    # Must call _compute_article_budget_s on the body
    assert "_compute_article_budget_s(body" in drain_body, (
        "_drain_layer2_queue must compute article budget from body length. "
        "Without this, large articles (50+ chunks) timeout at hardcoded 900s. "
        "See 2026-05-08 Hermes manual smoke (3/3 large articles failed)."
    )

    # Must NOT pass _SINGLE_CHUNK_FLOOR_S literal as the timeout arg to
    # clamp_article_timeout (the bug we just fixed). The constant may still
    # appear elsewhere as the formula's floor — that's fine.
    # Specifically check the clamp_article_timeout call uses article_budget.
    clamp_call_idx = drain_body.index("clamp_article_timeout(")
    # Read the next ~100 chars after the call opening
    clamp_call_snippet = drain_body[clamp_call_idx:clamp_call_idx + 200]
    assert "article_budget" in clamp_call_snippet, (
        "clamp_article_timeout in _drain_layer2_queue must receive "
        "article_budget (dynamic), not _SINGLE_CHUNK_FLOOR_S (hardcoded 900s)."
    )
