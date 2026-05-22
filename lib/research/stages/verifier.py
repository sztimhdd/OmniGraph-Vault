"""Verifier stage — ar-1 stub.

ar-1 status: stubbed. Always returns ``status="skipped"`` with
``confidence=0.0``, ``iter_count=0``, and empty ``external_citations`` /
``discrepancies`` lists. The real verifier loop (Tavily-Brave-Grounding fact
check) lands in ar-3.
"""
from __future__ import annotations

from ..types import ReasonerOutput, ResearchConfig, VerifierOutput


async def run(
    query: str, cfg: ResearchConfig, reasoned: ReasonerOutput
) -> VerifierOutput:
    """Run the Verifier stage (ar-1 stub).

    Returns a frozen ``VerifierOutput`` with ``status="skipped"``. Never raises.
    """
    return VerifierOutput(
        fact_check_summary_md="",
        confidence=0.0,
        external_citations=[],
        discrepancies=[],
        iter_count=0,
        status="skipped",
        reason="ar-1 stub — verifier loop lands in ar-3",
    )
