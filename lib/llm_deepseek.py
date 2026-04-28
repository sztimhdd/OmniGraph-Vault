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

Key validation: reads ``DEEPSEEK_API_KEY`` at import time; raises RuntimeError
immediately if absent. This fails fast — better to blow up at startup than
silently attempt API calls with no credentials.
"""
from __future__ import annotations

import os

from openai import AsyncOpenAI


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


# Module-level singletons — read env once at import.
_API_KEY = _require_api_key()
_MODEL = os.environ.get("DEEPSEEK_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
_client: AsyncOpenAI = AsyncOpenAI(api_key=_API_KEY, base_url=_DEEPSEEK_BASE_URL)


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

    response = await _client.chat.completions.create(
        model=_MODEL,
        messages=messages,
        stream=False,
    )
    return response.choices[0].message.content


__all__ = ["deepseek_model_complete"]
