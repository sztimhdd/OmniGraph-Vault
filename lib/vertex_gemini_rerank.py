"""LightRAG <-> Vertex Gemini rerank factory — v1.1.P2-3-perf-fix-B.

Provides ``make_rerank_func()`` returning a LightRAG-compatible
``rerank_model_func`` callable that wraps Vertex Gemini (default
gemini-2.5-flash-lite) for batch JSON relevance scoring on Aliyun ECS.

Mirrors the contract of databricks-deploy/lightrag_databricks_rerank.py
(A's Databricks Haiku helper) — same async signature, same identity-
degrade behavior, same JSON output shape. Differs in:
  - Async-native: ``await client.aio.models.generate_content(...)``
    (no loop.run_in_executor bridge — Vertex SDK is async-native).
  - JSON enforcement: types.GenerateContentConfig(response_mime_type=
    "application/json", response_schema=_RESPONSE_SCHEMA) (Vertex's
    native structured-output mode; A relies on prompt discipline +
    temperature=0.0 since Databricks SDK has no schema knob).

Lazy-import discipline:
  - ``from google import genai`` and ``from google.genai import types``
    live INSIDE ``_make_client()`` / ``make_rerank_func()`` (NOT at
    module top) — mirrors A's databricks-deploy/lightrag_databricks_rerank.py
    lazy-import of ``databricks.sdk.service.serving`` inside
    ``make_rerank_func()``.
  - This lets CI import ``_parse_scores`` (used by the unit tests)
    without google.genai installed. ``_parse_scores`` is pure-stdlib
    json + str manipulation — no SDK dep.

Contract:
    async def rerank_func(query: str, documents: list[str],
                          top_n: int | None = None) -> list[dict]
        # returns [{"index": int, "relevance_score": float}, ...]

Design (matches A):
  - Cap input documents to OMNIGRAPH_LLM_RERANK_TOP_K (default 30).
  - Single batch JSON call with response_schema enforced.
  - On JSON parse fail OR empty/partial scores: retry 1× with stricter
    prompt. On second fail OR endpoint timeout
    (OMNIGRAPH_LLM_RERANK_TIMEOUT, default 20s): return identity-order list.
  - On Vertex 503 / ServerError: identity-degrade (no retry loop —
    rerank is short and skippable; do not introduce wall-time
    variance into mode='mix' path). Diverges from
    lib/vertex_gemini_complete.py's 503 retry — that module is for
    long, expensive LLM completion; rerank is short + replaceable.

Env vars consumed:
  - GOOGLE_APPLICATION_CREDENTIALS (SA JSON path; required)
  - GOOGLE_CLOUD_PROJECT (required — raises RuntimeError at call-time)
  - GOOGLE_CLOUD_LOCATION (default: "global")
  - OMNIGRAPH_LLM_RERANK_MODEL (default: "gemini-2.5-flash-lite")
  - OMNIGRAPH_LLM_RERANK_TOP_K (default: 30)
  - OMNIGRAPH_LLM_RERANK_TIMEOUT (default: 20)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

# NOTE: ``from google import genai`` and ``from google.genai import types``
# are deliberately NOT imported at module top. They are imported INSIDE
# ``_make_client()`` and ``make_rerank_func()`` instead, mirroring A's
# databricks-deploy/lightrag_databricks_rerank.py:75-77 pattern.
# Rationale: keep ``from lib.vertex_gemini_rerank import _parse_scores``
# working in CI without the google.genai SDK installed (T4 unit tests).

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.5-flash-lite"
_DEFAULT_LOCATION = "global"
_RERANK_MODEL = os.environ.get("OMNIGRAPH_LLM_RERANK_MODEL", _DEFAULT_MODEL).strip() \
    or _DEFAULT_MODEL
_TOP_K = int(os.environ.get("OMNIGRAPH_LLM_RERANK_TOP_K", "30"))
_TIMEOUT = float(os.environ.get("OMNIGRAPH_LLM_RERANK_TIMEOUT", "20"))

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "s": {"type": "number"},
                },
                "required": ["i", "s"],
            },
        },
    },
    "required": ["scores"],
}

_SYSTEM_PROMPT = (
    "You are a relevance ranker. For each numbered passage, score how well "
    "it answers the user's QUERY on a 0.0-1.0 scale. Output ONLY JSON in "
    'the form: {"scores": [{"i": <passage_number>, "s": <float 0-1>}, ...]}. '
    "Include EVERY passage. No prose, no markdown."
)


def _require_project() -> str:
    """Return GOOGLE_CLOUD_PROJECT; raise RuntimeError if unset.

    REPLICATED from lib/vertex_gemini_complete.py:66-81. Evaluated at
    CALL time so local-dev imports succeed before env file is loaded.
    """
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if not project:
        raise RuntimeError(
            "GOOGLE_CLOUD_PROJECT is not set. Vertex Gemini rerank path "
            "requires SA auth (GOOGLE_APPLICATION_CREDENTIALS + "
            "GOOGLE_CLOUD_PROJECT). See docs/LOCAL_DEV_SETUP.md."
        )
    return project


def _make_client():
    """Construct a Vertex-mode genai.Client (SA-only path).

    REPLICATED from lib/vertex_gemini_complete.py:84-94. Surgical
    Changes: do not import-couple B's rerank helper to A's LLM
    completion helper.

    google.genai is imported HERE (not at module top) so CI can
    ``from lib.vertex_gemini_rerank import _parse_scores`` without
    the SDK installed (T4 unit tests). Mirrors A's lazy-import at
    databricks-deploy/lightrag_databricks_rerank.py:75-77.
    """
    from google import genai  # lazy: keeps _parse_scores SDK-free in CI
    project = _require_project()
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", _DEFAULT_LOCATION) \
        or _DEFAULT_LOCATION
    return genai.Client(vertexai=True, project=project, location=location)


def _identity(docs: list[str]) -> list[dict]:
    return [{"index": i, "relevance_score": 0.0} for i in range(len(docs))]


def _parse_scores(raw: str, n_docs: int) -> list[dict] | None:
    """Parse Vertex Gemini JSON output. Returns None when retry should fire.

    BYTE-EQUIVALENT to databricks-deploy/lightrag_databricks_rerank._parse_scores
    (A's helper). Acceptance contract:
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
        if len(result) < n_docs * 0.5:
            return None
        return sorted(result, key=lambda r: r["relevance_score"], reverse=True)
    except (json.JSONDecodeError, ValueError, TypeError, KeyError):
        return None


def make_rerank_func():
    """Build a LightRAG-compatible async rerank closure over Vertex Gemini.

    Constructs the Vertex client at factory-call time (lifespan boot);
    the closure reuses it for the process lifetime. Read-only after init.

    google.genai.types is imported HERE (not at module top), matching
    the lazy-import discipline in ``_make_client()`` — see module docstring.
    """
    from google.genai import types  # lazy: keeps _parse_scores SDK-free in CI
    client = _make_client()

    async def _vertex_batch_rerank(
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

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
            temperature=0.0,
            max_output_tokens=2048,
            system_instruction=_SYSTEM_PROMPT,
            http_options=types.HttpOptions(timeout=int(_TIMEOUT * 1000)),
        )
        try:
            resp = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=_RERANK_MODEL,
                    contents=[types.Content(
                        role="user", parts=[types.Part(text=user_prompt)],
                    )],
                    config=config,
                ),
                timeout=_TIMEOUT,
            )
        except (asyncio.TimeoutError, Exception) as e:  # noqa: BLE001
            logger.warning("vertex_rerank_endpoint_fail err=%r", e)
            return _identity(documents)

        raw = getattr(resp, "text", "") or ""
        parsed = _parse_scores(raw, n)
        if parsed is None:
            # Retry 1× with stricter prompt
            strict_config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
                temperature=0.0,
                max_output_tokens=2048,
                system_instruction=_SYSTEM_PROMPT
                    + " STRICT: JSON only, no markdown fences.",
                http_options=types.HttpOptions(timeout=int(_TIMEOUT * 1000)),
            )
            try:
                resp2 = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=_RERANK_MODEL,
                        contents=[types.Content(
                            role="user", parts=[types.Part(text=user_prompt)],
                        )],
                        config=strict_config,
                    ),
                    timeout=_TIMEOUT,
                )
                parsed = _parse_scores(getattr(resp2, "text", "") or "", n)
            except Exception as e:  # noqa: BLE001
                logger.warning("vertex_rerank_retry_fail err=%r", e)
                parsed = None
        if parsed is None:
            logger.warning("vertex_rerank_parse_fail_returning_identity n=%d", n)
            return _identity(documents)

        filtered = [r for r in parsed if 0 <= r["index"] < len(documents)]
        return filtered[:top_n] if top_n else filtered

    return _vertex_batch_rerank


__all__ = ["make_rerank_func", "_parse_scores"]
