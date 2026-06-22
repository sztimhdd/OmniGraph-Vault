"""Verifier stage — real bounded LLM agent loop with web_search + web_extract
tools (and conditionally google_search_grounding) — ORCH-04 (ar-3-02 / Wave 2).

Replaces the ar-1 stub. The loop terminates either when ``cfg.llm_complete``
emits a final-answer decision or when ``iter_count`` reaches
``cfg.max_iter_verifier`` (default 3). Reaching the cap is NOT a failure —
``status="ok"`` with whatever was collected. Any exception inside the loop
body is caught and surfaced as ``status="failed"`` per Axis 3 (best-effort)
— never raises out.

CONTRACT-01: this module imports NOTHING from ``omnigraph_search`` — the
Verifier has no KG side; it fact-checks against external web only.
CONTRACT-02: this module hardcodes no runtime-data path literals — every
external resource flows via ``cfg.*`` callables. (Path defaults live only
in config.py per the project-wide rule.)

The ``cfg.web_search`` callable is already cascade-wrapped from Wave 1
(ar-3-01) when both ``TAVILY_API_KEY`` and ``BRAVE_SEARCH_API_KEY`` are set;
the Verifier treats it as a single async callable and does NOT implement
primary/fallback orchestration.

The internal ``_LLMDecision`` / ``_ToolCall`` dataclasses define the
protocol between ``cfg.llm_complete`` and the loop body. They are
MODULE-private (single leading underscore) and not re-exported. Test mocks
construct them directly. Real LLM-provider integration / function-calling
JSON parsing is an ar-4 refinement — the mock IS the ar-3 contract.

Hard requirements (verbatim from CONTEXT.md § ORCH-04):
  1. ``iter_count`` is the post-loop value; ``iter_count <= cfg.max_iter_verifier``
     ALWAYS holds.
  2. Any exception inside the loop → return
     ``VerifierOutput(status="failed", reason=str(e), iter_count=<current>,
     confidence=0.0, fact_check_summary_md="", external_citations=[],
     discrepancies=[])`` — empty lists, NOT partial. Rationale: the
     Synthesizer's degradation note shouldn't paste partial mid-loop
     citations as if they were final.
  3. Cap reached is NOT a failure — return ``status="ok"``.
  4. ``confidence`` clamped to ``[0.0, 100.0]``. Parse failure → ``confidence=0.0``
     + a discrepancy noting the parse issue. Status stays ``"ok"`` (parse
     issue is observation, not stage failure).
  5. Verifier prompt MUST include ``reasoned.inferences_md``. Verifier touches
     no other ``ResearchState`` field.
  6. Tool-call parallelism within one iteration via ``asyncio.gather()``
     (Axis 1 carve-out).
  7. ``cfg.web_search`` is called as the WRAPPED form (cascade-aware when
     both keys set). Verifier does NOT implement primary/fallback.
"""
from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field

from ..types import ReasonerOutput, ResearchConfig, Source, VerifierOutput


@dataclass(frozen=True)
class _ToolCall:
    """One tool call emitted by ``cfg.llm_complete`` in a non-final decision.

    ``name`` is one of:
      - ``"web_search"``               (always available)
      - ``"web_extract"``              (always registered; raises if
                                       ``cfg.web_extract is None``)
      - ``"google_search_grounding"``  (conditionally available — only if
                                       ``cfg.google_search_grounding is not
                                       None``)

    ``args`` carry tool-specific kwargs:
      - web_search:               ``{"query": str}``
      - web_extract:              ``{"url": str}``
      - google_search_grounding:  ``{"query": str}``
    """

    name: str
    args: dict[str, object]


@dataclass(frozen=True)
class _LLMDecision:
    """One turn's decision from ``cfg.llm_complete``.

    Either ``is_final=True`` (loop terminates with ``content`` as the final
    fact-check summary, ``confidence`` 0-100, optional ``discrepancies``) or
    ``is_final=False`` (loop dispatches ``tool_calls`` in parallel and
    continues to the next turn).
    """

    is_final: bool
    content: str = ""
    confidence: float = 0.0
    discrepancies: tuple[str, ...] = field(default_factory=tuple)
    tool_calls: tuple[_ToolCall, ...] = field(default_factory=tuple)


def _build_prompt(
    query: str,
    reasoned: ReasonerOutput,
    collected_citations: list[Source],
    has_grounding: bool,
) -> str:
    """Build the per-turn prompt fed to ``cfg.llm_complete``.

    Includes ``reasoned.inferences_md`` verbatim as the verification subject
    (Hard requirement #5). Mentions ``google_search_grounding`` only when
    ``has_grounding`` is True.
    """
    parts: list[str] = [
        f"Query: {query}",
        "",
        "You are the Verifier stage of an agentic-RAG pipeline. Fact-check the",
        "Reasoner's inferences against external web sources.",
        "",
        "Reasoner inferences (verification subject):",
        reasoned.inferences_md or "(empty)",
        "",
        "Available tools:",
        "  - web_search(query)",
        "  - web_extract(url)",
    ]
    if has_grounding:
        parts.append("  - google_search_grounding(query)")
    parts.append("")
    parts.append(
        "Emit a final fact-check summary (with confidence 0-100 and a list"
        " of discrepancies) when ready; otherwise emit one or more tool calls."
    )
    if collected_citations:
        parts.append("")
        parts.append(f"Citations gathered so far: {len(collected_citations)}")
    return "\n".join(parts)


async def run(
    query: str, cfg: ResearchConfig, reasoned: ReasonerOutput
) -> VerifierOutput:
    """Run the Verifier agent loop (ORCH-04).

    Returns a frozen ``VerifierOutput``. Never raises — exceptions inside the
    loop surface as ``status="failed"`` with ``reason=str(e)`` per Axis 3.
    """
    iter_count = 0
    collected_citations: list[Source] = []
    discrepancies: list[str] = []
    final_summary = ""
    final_confidence = 0.0
    has_grounding = cfg.google_search_grounding is not None

    async def _web_search_tool(q: str) -> list[dict]:
        # cfg.web_search is async when cascade-wrapped (Tavily/Brave keys set),
        # but is the SYNC _skipped_web_search stub when TAVILY_API_KEY is unset
        # (config.py:94). Awaiting the sync stub's list return raises
        # "object list can't be used in 'await' expression" — so tolerate both:
        # await only when the result is actually awaitable.
        res = cfg.web_search(q)
        return await res if inspect.isawaitable(res) else res

    async def _web_extract_tool(url: str) -> str:
        if cfg.web_extract is None:
            raise RuntimeError("web_extract not configured")
        return await cfg.web_extract(url)

    async def _grounding_tool(q: str) -> str:
        # Only invoked when has_grounding is True (registry guards the call).
        return await cfg.google_search_grounding(q)

    # Build the tool registry. Always includes web_search + web_extract;
    # appends google_search_grounding IFF cfg.google_search_grounding is set.
    tool_list: list[dict] = [
        {"name": "web_search", "fn": _web_search_tool},
        {"name": "web_extract", "fn": _web_extract_tool},
    ]
    if has_grounding:
        tool_list.append({"name": "google_search_grounding", "fn": _grounding_tool})

    async def _dispatch(tc: _ToolCall):
        if tc.name == "web_search":
            return await _web_search_tool(str(tc.args.get("query", query)))
        if tc.name == "web_extract":
            return await _web_extract_tool(str(tc.args["url"]))
        if tc.name == "google_search_grounding":
            if not has_grounding:
                raise RuntimeError(
                    "google_search_grounding tool called but not configured"
                )
            return await _grounding_tool(str(tc.args.get("query", query)))
        raise ValueError(f"unknown tool name: {tc.name!r}")

    try:
        while iter_count < cfg.max_iter_verifier:
            iter_count += 1
            decision = await cfg.llm_complete(
                prompt=_build_prompt(
                    query, reasoned, collected_citations, has_grounding
                ),
                tools=tool_list,
            )

            if decision.is_final:
                final_summary = decision.content
                try:
                    final_confidence = max(
                        0.0, min(100.0, float(decision.confidence))
                    )
                except (TypeError, ValueError):
                    final_confidence = 0.0
                    discrepancies.append(
                        "Verifier: failed to parse confidence from LLM final answer"
                    )
                discrepancies.extend(decision.discrepancies)
                break

            # Dispatch tool calls in parallel — Axis 1 carve-out.
            results = await asyncio.gather(
                *[_dispatch(tc) for tc in decision.tool_calls],
                return_exceptions=True,
            )

            for tc, result in zip(decision.tool_calls, results):
                if isinstance(result, BaseException):
                    raise result
                if tc.name == "web_search":
                    for r in result:  # list[dict]
                        collected_citations.append(
                            Source(
                                kind="web",
                                uri=str(r.get("url", "")),
                                title=(str(r.get("title", "")) or None),
                                snippet=(str(r.get("content", "")) or None),
                            )
                        )
                elif tc.name == "web_extract":
                    collected_citations.append(
                        Source(
                            kind="web",
                            uri=str(tc.args["url"]),
                            snippet=str(result),
                        )
                    )
                elif tc.name == "google_search_grounding":
                    collected_citations.append(
                        Source(
                            kind="grounding",
                            uri=str(tc.args.get("query", query)),
                            snippet=str(result),
                        )
                    )
    except Exception as e:  # noqa: BLE001 — Axis 3 best-effort
        # Hard requirement #2: empty lists, not partial.
        return VerifierOutput(
            fact_check_summary_md="",
            confidence=0.0,
            external_citations=[],
            discrepancies=[],
            iter_count=iter_count,
            status="failed",
            reason=str(e),
        )

    # Cap reached without a final answer is still "ok" — the cap is a budget,
    # not an error condition.
    return VerifierOutput(
        fact_check_summary_md=final_summary,
        confidence=final_confidence,
        external_citations=collected_citations,
        discrepancies=discrepancies,
        iter_count=iter_count,
        status="ok",
    )
