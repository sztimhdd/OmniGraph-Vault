"""Reasoner stage — ar-1 stub.

ar-1 status: stubbed. Always returns ``status="skipped"`` with
``iter_count=0``. The real agent loop (kg_search + vision_analyze tool-using
LLM) lands in ar-2.
"""
from __future__ import annotations

from ..types import ReasonerOutput, ResearchConfig, RetrieverOutput


async def run(
    query: str, cfg: ResearchConfig, retrieved: RetrieverOutput
) -> ReasonerOutput:
    """Run the Reasoner stage (ar-1 stub).

    Returns a frozen ``ReasonerOutput`` with ``status="skipped"``. Never raises.
    """
    return ReasonerOutput(
        inferences_md="",
        additional_chunks=[],
        analyzed_images=[],
        iter_count=0,
        status="skipped",
        reason="ar-1 stub — agent loop lands in ar-2",
    )
