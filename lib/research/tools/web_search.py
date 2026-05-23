"""Web-tool callables for the Verifier stage agent loop.

Three live HTTP callables + a cascade factory:
  - tavily_search(query, *, api_key, top_k) -> list[dict]   (TOOL-01 search)
  - tavily_extract(url, *, api_key) -> str                  (TOOL-01 extract)
  - brave_search(query, *, api_key, top_k) -> list[dict]    (TOOL-02 fallback)
  - make_web_search_with_fallback(primary, fallback)        (TOOL-02 cascade)

Hardcoded 15.0s timeout per call. No env reads in this module — keys are
bound via functools.partial in from_env() (Axis 3).
"""
from __future__ import annotations

from typing import Awaitable, Callable
from urllib.parse import urlencode

import httpx

_TAVILY_TIMEOUT_S = 15.0


async def tavily_search(
    query: str,
    *,
    api_key: str,
    top_k: int = 10,
) -> list[dict]:
    """POST https://api.tavily.com/search and return list[dict] results.

    Body: {"api_key", "query", "max_results", "search_depth": "basic"}.
    Each returned dict has keys {"title", "url", "content", "score"}.
    Raises httpx.HTTPError / TimeoutException / ValueError on any failure.
    """
    body = {
        "api_key": api_key,
        "query": query,
        "max_results": top_k,
        "search_depth": "basic",
    }
    async with httpx.AsyncClient(timeout=_TAVILY_TIMEOUT_S) as client:
        response = await client.post(
            "https://api.tavily.com/search", json=body
        )
        response.raise_for_status()
        data = response.json()
    results = data.get("results", [])
    return [
        {
            "title": str(r.get("title", "")),
            "url": str(r.get("url", "")),
            "content": str(r.get("content", "")),
            "score": float(r.get("score", 0.0)),
        }
        for r in results
    ]


async def tavily_extract(
    url: str,
    *,
    api_key: str,
) -> str:
    """POST https://api.tavily.com/extract and return joined raw_content as str.

    Body: {"api_key", "urls": [url]}. Multiple results are joined with "\n\n".
    Raises on any failure.
    """
    body = {"api_key": api_key, "urls": [url]}
    async with httpx.AsyncClient(timeout=_TAVILY_TIMEOUT_S) as client:
        response = await client.post(
            "https://api.tavily.com/extract", json=body
        )
        response.raise_for_status()
        data = response.json()
    results = data.get("results", [])
    return "\n\n".join(str(r.get("raw_content", "")) for r in results)


async def brave_search(
    query: str,
    *,
    api_key: str,
    top_k: int = 10,
) -> list[dict]:
    """GET https://api.search.brave.com/res/v1/web/search and return list[dict].

    Header: X-Subscription-Token: <api_key>. Each returned dict has keys
    {"title", "url", "content"} — Brave's "description" is normalized to
    "content" so callers see the same shape as Tavily. Raises on any failure.
    """
    params = urlencode({"q": query, "count": top_k})
    url = f"https://api.search.brave.com/res/v1/web/search?{params}"
    headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=_TAVILY_TIMEOUT_S) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
    web_results = data.get("web", {}).get("results", [])
    return [
        {
            "title": str(r.get("title", "")),
            "url": str(r.get("url", "")),
            "content": str(r.get("description", "")),
        }
        for r in web_results
    ]


def make_web_search_with_fallback(
    primary: Callable[..., Awaitable[list[dict]]],
    fallback: Callable[..., Awaitable[list[dict]]] | None,
) -> Callable[..., Awaitable[list[dict]]]:
    """Pair primary + fallback into a single async cascade callable.

    Semantics:
      1. Invoke primary(query).
      2. On ANY exception from primary, invoke fallback(query) exactly once.
      3. Whatever fallback returns (or raises) is returned/raised.
      4. If fallback is None and primary raises, the exception propagates.

    Per-call independent: failure on call N does NOT disable primary on call
    N+1 (no module/closure state — each invocation is fresh). The Verifier
    loop may decide to retry the cascade as a whole on subsequent iterations
    — that is loop-level retry, not cascade-level retry.
    """
    async def cascade(query: str) -> list[dict]:
        try:
            return await primary(query)
        except Exception:  # noqa: BLE001 — cascade-level catch, intentional
            if fallback is None:
                raise
            return await fallback(query)
    return cascade


__all__ = [
    "brave_search",
    "make_web_search_with_fallback",
    "tavily_extract",
    "tavily_search",
]
