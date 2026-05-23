"""WebBaseline stage — ar-1 stub.

ar-1 status: stubbed. Returns ``status="skipped"`` whenever ``cfg.web_search``
returns an empty list (the default ``_skipped_web_search`` callable from
``config.py`` always returns ``[]``). Live Tavily integration lands in ar-3.

If a live (non-stub) ``web_search`` is injected via ``ResearchConfig`` and
returns a list of dicts shaped like ``{"url": str, "title": str, "content": str}``,
this stage will normalize them into ``Source(kind="web", ...)`` entries. Per
Axis 3 (best-effort failure), any exception from ``cfg.web_search`` is caught
and surfaced as ``status="failed"`` with ``reason=str(e)``.
"""
from __future__ import annotations

import inspect

from ..types import ResearchConfig, Source, WebBaseline


async def run(query: str, cfg: ResearchConfig) -> WebBaseline:
    """Run the WebBaseline stage.

    Returns a frozen ``WebBaseline`` with ``status`` in
    ``{"ok", "skipped", "failed"}``. Never raises.

    Accepts both sync (``_skipped_web_search`` stub) and async (Tavily/Brave
    cascade from ar-3 Wave 1) ``cfg.web_search`` callables — awaits if the
    return value is awaitable.
    """
    queries_used = [query]
    try:
        results = cfg.web_search(query)
        if inspect.isawaitable(results):
            results = await results
    except Exception as e:  # noqa: BLE001 — Axis 3 best-effort
        return WebBaseline(
            queries_used=queries_used,
            snippets=[],
            status="failed",
            reason=str(e),
        )

    if not results:
        return WebBaseline(
            queries_used=queries_used,
            snippets=[],
            status="skipped",
            reason="web_search returned [] (TAVILY_API_KEY unset — ar-1 stub mode)",
        )

    snippets: list[Source] = []
    for r in results:
        snippets.append(
            Source(
                kind="web",
                uri=r.get("url", ""),
                title=r.get("title"),
                snippet=r.get("content"),
            )
        )
    return WebBaseline(queries_used=queries_used, snippets=snippets)
