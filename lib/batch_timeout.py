"""Phase 17 (BTIMEOUT-02): batch-level timeout interlock helpers.

Small, pure, side-effect-free utilities for composing v3.1 Phase 9's
per-article timeout formula with a batch-level remaining-budget bound.
See `docs/BATCH_TIMEOUT_DESIGN.md` for the full design.
"""
from __future__ import annotations

import time

# Seconds reserved for checkpoint flush + final metrics emission at batch end.
# Per design: flush is small JSON writes expected to complete in <5s. 60s is a
# conservative safety buffer. See docs/BATCH_TIMEOUT_DESIGN.md § Checkpoint-Flush Interaction.
BATCH_SAFETY_MARGIN_S: int = 60


def clamp_article_timeout(
    single_timeout: int,
    remaining_budget: float,
    safety_margin: int = BATCH_SAFETY_MARGIN_S,
) -> int:
    """Clamp per-article timeout so total batch budget is respected.

    Composes with v3.1 Phase 9's single-article formula
    ``max(120 + 30 * chunk_count, 900)``; does NOT replace it.

    Rules (BTIMEOUT-02):
      * If ``remaining_budget - safety_margin > 0`` → return
        ``min(single_timeout, int(effective_budget))``.
      * Else (batch out of budget) → return
        ``max(60, int(single_timeout * 0.5))`` so the next article still has
        a viable 60s floor; if it times out, checkpoint captures state for a
        later re-run.

    Args:
        single_timeout: Phase 9 per-article budget in seconds.
        remaining_budget: Batch budget remaining in seconds; MAY be a float
            (from ``time.time()`` subtraction).
        safety_margin: Seconds reserved for post-batch bookkeeping (default
            ``BATCH_SAFETY_MARGIN_S`` = 60).

    Returns:
        Effective per-article timeout in integer seconds.
    """
    effective_budget = remaining_budget - safety_margin
    if effective_budget <= 0:
        # Batch out of budget; article gets half-timeout fallback.
        return max(60, int(single_timeout * 0.5))
    return min(single_timeout, int(effective_budget))


def get_remaining_budget(batch_start: float, total_batch_budget: int) -> float:
    """Compute remaining batch budget in seconds (floored at 0).

    Args:
        batch_start: ``time.time()`` value captured at batch start.
        total_batch_budget: Total batch budget in seconds (from
            ``OMNIGRAPH_BATCH_TIMEOUT_SEC`` or ``--batch-timeout``).

    Returns:
        ``max(0, total_batch_budget - elapsed)``.
    """
    elapsed = time.time() - batch_start
    return max(0.0, float(total_batch_budget) - elapsed)
