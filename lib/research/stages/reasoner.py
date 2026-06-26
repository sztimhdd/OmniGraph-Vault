"""Reasoner stage — real bounded LLM agent loop with kg_search + vision_analyze
tools (ORCH-03 + TOOL-04).

Replaces the ar-1 deterministic stub. The loop terminates either when
``cfg.llm_complete`` emits a final-answer decision or when ``iter_count``
reaches ``cfg.max_iter_reasoner`` (default 5). Reaching the cap is NOT a
failure — ``status="ok"`` with whatever was collected. Any exception inside
the loop body is caught and surfaced as ``status="failed"`` per Axis 3
(best-effort) — never raises out.

CONTRACT-01: this module adds the SECOND ``from omnigraph_search.query import
search`` line in ``lib/research/`` (the Retriever owns the first). The
grep-based contract check is an exclusion-list filter, not a count cap, so
two such lines is contract-clean. No other ``omnigraph_search.*`` import is
allowed in this file.

CONTRACT-02: image paths flow exclusively via ``Path(tc.args["image_path"])``
— the string came from the LLM tool-call args, which were built upstream from
``state.retrieved.image_candidates[*].image_path`` (already
``cfg.rag_working_dir``-derived). This file contains no hardcoded
runtime-data path literals (those live only in config.py).

The internal ``_LLMDecision`` / ``_ToolCall`` dataclasses define the protocol
between ``cfg.llm_complete`` and the loop body. They are MODULE-private
(single leading underscore) and not re-exported. Test mocks construct them
directly. Real LLM-provider integration / function-calling JSON parsing is an
ar-3+ refinement — the mock IS the ar-2 contract.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from omnigraph_search.query import search as kg_search

from ..types import (
    ReasonerOutput,
    ResearchConfig,
    RetrievedImage,
    RetrieverOutput,
    Source,
)


@dataclass(frozen=True)
class _ToolCall:
    """One tool call emitted by ``cfg.llm_complete`` in a non-final decision.

    ``name`` is one of ``"kg_search"`` or ``"vision_analyze"``. ``args`` carry
    the tool-specific keyword arguments (e.g. ``{"image_path": ..., "question": ...}``
    for ``vision_analyze``; ``{"query": ..., "top_k": ...}`` for ``kg_search``).
    """

    name: str
    args: dict[str, object]


@dataclass(frozen=True)
class _LLMDecision:
    """One turn's decision from ``cfg.llm_complete``.

    Either ``is_final=True`` (loop terminates with ``content`` as the final
    inferences markdown) or ``is_final=False`` (loop dispatches ``tool_calls``
    in parallel and continues to the next turn).
    """

    is_final: bool
    content: str = ""
    tool_calls: tuple[_ToolCall, ...] = field(default_factory=tuple)


def _build_prompt(
    query: str,
    retrieved: RetrieverOutput,
    collected_chunks: list[Source],
    collected_images: list[RetrievedImage],
) -> str:
    """Build the per-turn prompt fed to ``cfg.llm_complete``.

    Minimal in ar-2 (final tuning is ar-4). At minimum it carries the query,
    a brief tool-availability statement, and a digest of what's been collected
    so far so the LLM can decide whether to call another tool or emit a final.
    """
    parts: list[str] = [
        f"Query: {query}",
        "",
        "You are the Reasoner stage of an agentic-RAG pipeline. You have two tools:",
        "  - kg_search(query, top_k): query the local knowledge graph",
        "  - vision_analyze(image_path, question): caption an image from KG",
        "",
        "Emit a final answer when you have enough information; otherwise emit"
        " one or more tool calls.",
    ]

    if retrieved.chunks:
        parts.append("")
        parts.append(f"Initial KG chunks: {len(retrieved.chunks)}")
    if retrieved.image_candidates:
        parts.append(
            f"Image candidates available: {len(retrieved.image_candidates)}"
        )
    if collected_chunks:
        parts.append(f"Additional chunks gathered so far: {len(collected_chunks)}")
    if collected_images:
        parts.append(f"Images analyzed so far: {len(collected_images)}")

    return "\n".join(parts)


async def run(
    query: str, cfg: ResearchConfig, retrieved: RetrieverOutput
) -> ReasonerOutput:
    """Run the Reasoner agent loop (ORCH-03).

    Returns a frozen ``ReasonerOutput``. Never raises — exceptions inside the
    loop surface as ``status="failed"`` with ``reason=str(e)`` per Axis 3.
    """
    iter_count = 0
    collected_chunks: list[Source] = []
    collected_images: list[RetrievedImage] = []
    final_answer = ""

    async def _kg_search_tool(query: str, top_k: int = 10) -> str:
        # omnigraph_search.query.search is async (verified at read_first time).
        # arx-4 #64/#65 parity with the retriever: mix mode (vector chunks) +
        # cfg.rag (lifespan instance with reranker) instead of hybrid + fresh rag.
        return await kg_search(query, mode="mix", rag=cfg.rag)

    async def _vision_analyze_tool(image_path: str, question: str) -> str:
        # TOOL-04: wraps cfg.vision_cascade.describe — no new vision infra.
        return await cfg.vision_cascade.describe(image_path, question)

    async def _dispatch(tc: _ToolCall):
        if tc.name == "kg_search":
            return await _kg_search_tool(
                query=tc.args.get("query", query),
                top_k=int(tc.args.get("top_k", 10)),
            )
        if tc.name == "vision_analyze":
            return await _vision_analyze_tool(
                image_path=str(tc.args["image_path"]),
                question=str(tc.args.get("question", "")),
            )
        raise ValueError(f"unknown tool name: {tc.name!r}")

    try:
        while iter_count < cfg.max_iter_reasoner:
            iter_count += 1
            decision = await cfg.llm_complete(
                prompt=_build_prompt(
                    query, retrieved, collected_chunks, collected_images
                ),
                tools=[
                    {"name": "kg_search", "fn": _kg_search_tool},
                    {"name": "vision_analyze", "fn": _vision_analyze_tool},
                ],
            )

            if decision.is_final:
                final_answer = decision.content
                break

            # Dispatch tool calls in parallel — Axis 1 carve-out for in-stage
            # vision_analyze parallelism within a single iteration.
            tool_call_results = await asyncio.gather(
                *[_dispatch(tc) for tc in decision.tool_calls],
                return_exceptions=True,
            )

            for tc, result in zip(decision.tool_calls, tool_call_results):
                if isinstance(result, BaseException):
                    raise result
                if tc.name == "kg_search":
                    collected_chunks.append(
                        Source(
                            kind="kg_chunk",
                            uri="omnigraph_search.query.search",
                            snippet=str(result),
                        )
                    )
                elif tc.name == "vision_analyze":
                    image_path = Path(str(tc.args["image_path"]))
                    collected_images.append(
                        RetrievedImage(
                            article_hash=image_path.parent.name,
                            image_path=image_path,
                            caption=str(result),
                        )
                    )
    except Exception as e:  # noqa: BLE001 — Axis 3 best-effort
        return ReasonerOutput(
            inferences_md=final_answer,
            additional_chunks=collected_chunks,
            analyzed_images=collected_images,
            iter_count=iter_count,
            status="failed",
            reason=str(e),
        )

    # Cap reached without a final answer is still "ok" — the cap is a budget,
    # not an error condition.
    return ReasonerOutput(
        inferences_md=final_answer,
        additional_chunks=collected_chunks,
        analyzed_images=collected_images,
        iter_count=iter_count,
        status="ok",
    )
