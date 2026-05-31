"""LightRAG <-> Databricks Model Serving rerank factory — v1.1.P2-3-perf-fix-A.

Provides ``make_rerank_func()`` returning a LightRAG-compatible
``rerank_model_func`` callable that wraps the configured Mosaic chat
endpoint (default Haiku-4-5) for batch JSON relevance scoring.

Contract:
    async def rerank_func(query: str, documents: list[str],
                          top_n: int | None = None) -> list[dict]
        # returns [{"index": int, "relevance_score": float}, ...]

Design:
  - Cap input documents to OMNIGRAPH_LLM_RERANK_TOP_K (default 30) BEFORE
    the LLM call; preserves Haiku 8K context budget. Documents past TOP_K
    are excluded from scoring (apply_rerank_if_enabled at lightrag/utils.py
    iterates the returned list — anything not present falls out).
  - Single batch JSON call: prompt embeds enumerated `[i] passage`
    blocks; asks Haiku to return JSON `{"scores": [{"i": int, "s": float}]}`.
  - On JSON parse fail OR empty/partial scores: retry 1× with stricter prompt.
    On second fail OR endpoint timeout (OMNIGRAPH_LLM_RERANK_TIMEOUT, default
    20s): return identity-order list (apply_rerank_if_enabled then runs as
    if rerank were a no-op; LightRAG warns + uses original chunks).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)

_RERANK_MODEL = os.environ.get("OMNIGRAPH_LLM_RERANK_MODEL", "databricks-claude-haiku-4-5")
_TOP_K = int(os.environ.get("OMNIGRAPH_LLM_RERANK_TOP_K", "30"))
_TIMEOUT = float(os.environ.get("OMNIGRAPH_LLM_RERANK_TIMEOUT", "20"))

_SYSTEM_PROMPT = (
    "You are a relevance ranker. For each numbered passage, score how well "
    "it answers the user's QUERY on a 0.0-1.0 scale. Output ONLY JSON in "
    'the form: {"scores": [{"i": <passage_number>, "s": <float 0-1>}, ...]}. '
    "Include EVERY passage. No prose, no markdown."
)


def _identity(docs: list[str]) -> list[dict]:
    return [{"index": i, "relevance_score": 0.0} for i in range(len(docs))]


def _parse_scores(raw: str, n_docs: int) -> list[dict] | None:
    """Parse Haiku JSON output. Returns None when retry should fire.

    Acceptance contract:
      - garbage / empty object / fewer than 50% scored → None (retry)
      - ≥ 50% scored → return sorted descending by score
    """
    try:
        cleaned = raw.strip().strip("`").lstrip("json").strip()
        obj = json.loads(cleaned)
        scores = obj.get("scores", [])
        if not isinstance(scores, list) or len(scores) == 0:
            return None
        result = [
            {"index": int(s["i"]), "relevance_score": float(s["s"])}
            for s in scores
            if isinstance(s, dict) and "i" in s and "s" in s
        ]
        if len(result) < n_docs * 0.5:  # need at least half scored
            return None
        return sorted(result, key=lambda r: r["relevance_score"], reverse=True)
    except (json.JSONDecodeError, ValueError, TypeError, KeyError):
        return None


def make_rerank_func():
    """Build a LightRAG-compatible async rerank closure over a Haiku endpoint."""
    from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
    from _db_client import get_databricks_client
    w = get_databricks_client()

    async def _haiku_batch_rerank(
        query: str, documents: list[str], top_n: int | None = None,
    ) -> list[dict]:
        if not documents:
            return []
        capped = documents[:_TOP_K]
        n = len(capped)
        passages_block = "\n\n".join(
            f"[{i}] {capped[i][:2000]}" for i in range(n)
        )
        user_prompt = f"QUERY: {query}\n\nPASSAGES:\n\n{passages_block}"
        messages = [
            ChatMessage(role=ChatMessageRole.SYSTEM, content=_SYSTEM_PROMPT),
            ChatMessage(role=ChatMessageRole.USER, content=user_prompt),
        ]
        loop = asyncio.get_running_loop()
        try:
            resp = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: w.serving_endpoints.query(
                        name=_RERANK_MODEL, messages=messages,
                        temperature=0.0, max_tokens=2048,
                    ),
                ),
                timeout=_TIMEOUT,
            )
        except (asyncio.TimeoutError, Exception) as e:  # noqa: BLE001
            logger.warning("llm_rerank_endpoint_fail err=%r", e)
            return _identity(documents)

        raw = resp.choices[0].message.content
        parsed = _parse_scores(raw, n)
        if parsed is None:
            # Retry 1× with stricter prompt
            strict = ChatMessage(
                role=ChatMessageRole.SYSTEM,
                content=_SYSTEM_PROMPT + " STRICT: JSON only, no markdown fences."
            )
            try:
                resp2 = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: w.serving_endpoints.query(
                            name=_RERANK_MODEL,
                            messages=[strict, messages[1]],
                            temperature=0.0, max_tokens=2048,
                        ),
                    ),
                    timeout=_TIMEOUT,
                )
                parsed = _parse_scores(resp2.choices[0].message.content, n)
            except Exception as e:  # noqa: BLE001
                logger.warning("llm_rerank_retry_fail err=%r", e)
                parsed = None
        if parsed is None:
            logger.warning("llm_rerank_parse_fail_returning_identity n=%d", n)
            return _identity(documents)

        # Filter parsed to valid index range; apply top_n
        filtered = [r for r in parsed if 0 <= r["index"] < len(documents)]
        return filtered[:top_n] if top_n else filtered

    return _haiku_batch_rerank


__all__ = ["make_rerank_func", "_parse_scores"]
