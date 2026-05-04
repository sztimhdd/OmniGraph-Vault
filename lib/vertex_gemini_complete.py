"""Vertex Gemini LLM provider — LDEV-01 (quick task 260504-g7a).

Single source of truth for Vertex AI Gemini chat completion, matching
LightRAG's ``llm_model_func`` contract so it is drop-in swappable via
``LightRAG(..., llm_model_func=vertex_gemini_model_complete, ...)``.

Why this module exists:
    Local dev runs on the user's Windows box where DeepSeek quota is risky
    and Cisco Umbrella intercepts external API traffic. Vertex AI (SA JSON
    auth, pooled quota across GCP projects) is the preferred LLM backend
    when ``OMNIGRAPH_LLM_PROVIDER=vertex_gemini`` is set. Production Hermes
    stays on DeepSeek by default (unset → ``lib.llm_deepseek`` path).

Contract (matches LightRAG source; see ``lib/llm_deepseek.deepseek_model_complete``):
    async def llm_model_func(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict] = [],
        **kwargs,
    ) -> str

    - kwargs may include: keyword_extraction (bool), stream (bool),
      hashing_kv (obj for caching). We accept + ignore them —
      LightRAG handles caching at a layer above us.
    - Returns plain string, NOT a streaming iterator.

SA auth idiom is mirrored from ``lib/lightrag_embedding._make_client`` (the
canonical in-repo Vertex client pattern):
    genai.Client(vertexai=True, project=..., location=...)

Env vars consumed:
    - GOOGLE_APPLICATION_CREDENTIALS (SA JSON path; required for Vertex mode)
    - GOOGLE_CLOUD_PROJECT (required — raises RuntimeError at call-time if unset)
    - GOOGLE_CLOUD_LOCATION (default: ``global``; differs from embedding's
      ``us-central1`` default per LDEV task spec)
    - OMNIGRAPH_LLM_MODEL (default: ``gemini-3.1-flash-lite-preview``)
    - OMNIGRAPH_LLM_TIMEOUT_SEC (default: 600, integer seconds)

On ``google.genai.errors.ServerError`` with ``code == 503``: retry up to 3
times with exponential backoff 2s / 4s / 8s; 4th failure re-raises. Any
other exception propagates immediately (no retry).

NOT re-exported from ``lib/__init__.py`` — callers must
``from lib.vertex_gemini_complete import vertex_gemini_model_complete``
explicitly. This keeps google-genai import cost off DeepSeek-only callers
and preserves the option to soft-fail DeepSeek's import-time key check in
a later Phase 5 follow-up (CLAUDE.md § Phase 5 DeepSeek cross-coupling).
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import ServerError


_DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"
_DEFAULT_LOCATION = "global"
_DEFAULT_TIMEOUT_SEC = 600
_RETRY_BACKOFFS_SEC = (2, 4, 8)  # 3 retries; total wall = 14s worst case


def _require_project() -> str:
    """Return ``GOOGLE_CLOUD_PROJECT``; raise RuntimeError if unset.

    Evaluated at CALL time (not import time) so local-dev imports succeed
    before the env file is loaded. Mirrors the fail-fast pattern of
    ``lib/llm_deepseek._require_api_key`` but at call-time instead of
    import-time.
    """
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if not project:
        raise RuntimeError(
            "GOOGLE_CLOUD_PROJECT is not set. Vertex Gemini LLM path "
            "requires SA auth (GOOGLE_APPLICATION_CREDENTIALS + "
            "GOOGLE_CLOUD_PROJECT). See docs/LOCAL_DEV_SETUP.md."
        )
    return project


def _make_client() -> "genai.Client":
    """Construct a Vertex-mode ``genai.Client`` (SA-only path).

    Mirrors ``lib/lightrag_embedding._make_client`` for the Vertex branch.
    No ``api_key`` path — this module is Vertex-only; free-tier Gemini LLM
    usage routes through the existing ``lib.generate_sync`` helper.
    """
    project = _require_project()
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", _DEFAULT_LOCATION) \
        or _DEFAULT_LOCATION
    return genai.Client(vertexai=True, project=project, location=location)


def _build_contents(
    prompt: str,
    system_prompt: str | None,
    history_messages: list[dict] | None,
) -> list:
    """Translate LightRAG-style messages into google-genai ``contents`` list.

    google-genai has no dedicated "system" role. Convention used here: if a
    ``system_prompt`` is provided, it is prepended as the first user turn
    (the genai SDK folds leading user turns into the initial instruction
    slot — semantically equivalent). Subsequent ``history_messages`` roles
    ``"assistant"`` and ``"model"`` both map to ``"model"``; ``"user"`` stays
    ``"user"``. Final user ``prompt`` is appended as the last user turn.

    Strict user/model alternation is preserved by the caller's input; this
    function does not attempt to re-order turns. A lone leading system_prompt
    plus a final user prompt yields a valid 2-turn [user, user] -> merged
    pair per genai's own handling (merge is the SDK's responsibility, not
    ours — we faithfully translate roles).
    """
    contents: list = []

    if system_prompt:
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=system_prompt)],
        ))

    for msg in (history_messages or []):
        role = msg.get("role", "user")
        if role in ("assistant", "model"):
            role = "model"
        else:
            role = "user"
        text = msg.get("content", "")
        contents.append(types.Content(
            role=role,
            parts=[types.Part(text=text)],
        ))

    contents.append(types.Content(
        role="user",
        parts=[types.Part(text=prompt)],
    ))

    return contents


def _extract_text(response: Any) -> str:
    """Return the model's text from a google-genai response.

    Prefers ``response.text``; falls back to ``response.candidates[0]
    .content.parts[0].text`` for SDK versions that don't expose the
    convenience attribute.
    """
    text = getattr(response, "text", None)
    if text:
        return text
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", None) or []
        if parts:
            return getattr(parts[0], "text", "") or ""
    return ""


async def vertex_gemini_model_complete(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict] | None = None,
    keyword_extraction: bool = False,  # LightRAG caching layer owns this; accept + ignore
    **kwargs: Any,
) -> str:
    """Match LightRAG's ``llm_model_func`` signature; return plain string.

    ``kwargs`` (e.g. ``hashing_kv``, ``stream``) is accepted and ignored —
    LightRAG handles caching at a layer above us and genai does not consume
    these knobs.
    """
    model = os.environ.get("OMNIGRAPH_LLM_MODEL", _DEFAULT_MODEL).strip() \
        or _DEFAULT_MODEL
    try:
        timeout_sec = int(os.environ.get(
            "OMNIGRAPH_LLM_TIMEOUT_SEC", _DEFAULT_TIMEOUT_SEC
        ))
    except (TypeError, ValueError):
        timeout_sec = _DEFAULT_TIMEOUT_SEC

    contents = _build_contents(prompt, system_prompt, history_messages)
    client = _make_client()

    # google-genai 1.0+ accepts per-call HTTP options via
    # ``types.GenerateContentConfig(http_options=types.HttpOptions(timeout=...))``.
    # Timeout is expressed in milliseconds on the SDK side; we convert seconds
    # → ms for the wire. Tests assert the integer that reaches
    # ``generate_content``'s ``config`` kwarg, so plumb it through config.
    config = types.GenerateContentConfig(
        http_options=types.HttpOptions(timeout=timeout_sec * 1000),
    )

    attempts = 1 + len(_RETRY_BACKOFFS_SEC)  # 4 total
    last_exc: ServerError | None = None
    for attempt in range(attempts):
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            return _extract_text(response)
        except ServerError as exc:
            code = getattr(exc, "code", None)
            if code != 503:
                raise  # non-503 ServerError → propagate immediately
            last_exc = exc
            if attempt >= len(_RETRY_BACKOFFS_SEC):
                break  # exhausted retries
            await asyncio.sleep(_RETRY_BACKOFFS_SEC[attempt])

    # All retries exhausted on 503 — re-raise the most recent.
    assert last_exc is not None  # pragma: no cover
    raise last_exc


__all__ = ["vertex_gemini_model_complete"]
