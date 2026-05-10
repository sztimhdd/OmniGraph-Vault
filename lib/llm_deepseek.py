"""Deepseek LLM wrapper — Plan 05-00c Task 0c.1.

Single source of truth for DeepSeek chat completion. Matches LightRAG's
``llm_model_func`` contract so it can be passed directly as
``LightRAG(..., llm_model_func=deepseek_model_complete, ...)``.

Why this module exists:
    Plan 05-00's Wave 0 embedding migration is blocked by Gemini free-tier
    quota coupling: LightRAG's entity extraction + relationship summarization
    burns the generate_content pool that we also need for embeddings. Moving
    all LightRAG LLM work to DeepSeek (via this wrapper) decouples failure
    modes — Gemini quota only throttles embeddings, DeepSeek quota only
    throttles LLM — and each axis is independently tractable.

Contract (matches LightRAG source venv/Lib/site-packages/lightrag/lightrag.py):
    async def llm_model_func(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict] = [],
        **kwargs,
    ) -> str

    - kwargs may include: keyword_extraction (bool), stream (bool),
      hashing_kv (obj for caching). We ignore them — DeepSeek doesn't
      use them and LightRAG handles caching at a layer above us.
    - MUST return plain string, NOT a streaming iterator.

Endpoint: ``https://api.deepseek.com/v1`` (OpenAI-compatible).
Model: ``DEEPSEEK_MODEL`` env var, default ``deepseek-v4-flash``.

Key validation (Defect D — quick 260510-l14): the ``DEEPSEEK_API_KEY`` check is
DEFERRED to first call via ``_get_client()`` rather than at module import.
Gemini/Vertex-only workloads can ``from lib.llm_deepseek import ...`` without
needing a DeepSeek key; the key is only required when ``deepseek_model_complete``
is actually invoked. The diagnostic message is preserved verbatim.
"""
from __future__ import annotations

import os

from openai import AsyncOpenAI

# Defect C (quick 260510-l14): use the canonical loader from config.py
# instead of duplicating the .env parser. lib.llm_deepseek may import before
# CLI scripts call bootstrap_cli(), so we still need to populate the env at
# module top — but config.load_env() is now the single source of truth.
from config import load_env

load_env()


_DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
_DEFAULT_MODEL = "deepseek-v4-flash"


def _require_api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is not set. Add it to ~/.hermes/.env; "
            "required for all LightRAG LLM calls in Phase 5+."
        )
    return key


_MODEL = os.environ.get("DEEPSEEK_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL

# D-09.02 (TIMEOUT-02): 120s request timeout prevents single-chunk runaway.
# Outer per-article budget (D-09.03) scales with chunk_count; this inner
# timeout kills any ONE chat.completions.create call that exceeds 120s so the
# outer budget has room to retry or fail cleanly. Bare float form — the
# openai>=1.0 SDK accepts float as total request timeout.
_DEEPSEEK_TIMEOUT_S = 120.0

# Defect D (quick 260510-l14): client is lazily constructed on first call so
# importing this module never requires DEEPSEEK_API_KEY (Gemini/Vertex-only
# workloads previously had to set DEEPSEEK_API_KEY=dummy as a band-aid).
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """Return the cached AsyncOpenAI client, constructing it on first call.

    Reads DEEPSEEK_API_KEY lazily so any process that imports
    ``lib.llm_deepseek`` without ever calling ``deepseek_model_complete`` does
    not need the key. Raises RuntimeError with the canonical diagnostic if the
    key is missing at first-call time.
    """
    global _client
    if _client is None:
        api_key = _require_api_key()
        _client = AsyncOpenAI(
            api_key=api_key,
            base_url=_DEEPSEEK_BASE_URL,
            timeout=_DEEPSEEK_TIMEOUT_S,
        )
    return _client


async def deepseek_model_complete(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict] | None = None,
    **kwargs,
) -> str:
    """Match LightRAG's ``llm_model_func`` signature; return plain string.

    ``kwargs`` is accepted and ignored (e.g. ``keyword_extraction``,
    ``hashing_kv``). DeepSeek chat completions do not use them.
    """
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history_messages:
        messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})

    response = await _get_client().chat.completions.create(
        model=_MODEL,
        messages=messages,
        stream=False,
    )
    return response.choices[0].message.content


__all__ = ["deepseek_model_complete"]
