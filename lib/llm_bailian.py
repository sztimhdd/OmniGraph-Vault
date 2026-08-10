"""Bailian (阿里百炼) OpenAI-compatible LLM completion for LightRAG.

Mirrors ``lib.llm_deepseek.py`` structure (same OpenAI-compatible contract):
- Endpoint: ``BAILIAN_BASE_URL`` env, default ``https://api.dashscope.aliyuncs.com/compatible-mode/v1``
  (dedicated gateway overrides via ``openAiCompatible`` URL from the key CSV).
- Model: ``BAILIAN_MODEL`` env, default ``qwen3.7-flash``.
- Key: ``BAILIAN_API_KEY`` env (canonical). Loaded via ``config.load_env()``
  like the DeepSeek loader — single source of truth for ~/.hermes/.env.

Selection rationale (2026-08-11, quick bailian-1):
- 37ms first-token vs DeepSeek 1.2s on the dedicated gateway; qwen3.7-flash
  is cheap and fast for entity extraction; qwen3.7-max available for harder
  synthesis if needed.
- Key validation deferred to first call (same pattern as DeepSeek Defect D
  fix) so Gemini/DeepSeek-only workloads never require a Bailian key.

IMPORTANT: mirrors deepseek_model_complete's signature so the LightRAG
``llm_model_func`` contract is satisfied — async, takes a single prompt
string, returns plain text (not a stream).
"""
from __future__ import annotations

import os

from openai import AsyncOpenAI

from config import load_env

load_env()

_BAILIAN_BASE_URL = os.environ.get(
    "BAILIAN_BASE_URL",
    "https://api.dashscope.aliyuncs.com/compatible-mode/v1",
).strip()
_DEFAULT_MODEL = os.environ.get("BAILIAN_MODEL", "qwen3.7-flash").strip()


def _require_api_key() -> str:
    key = os.environ.get("BAILIAN_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "BAILIAN_API_KEY is not set. Add it to ~/.hermes/.env; "
            "see docs/LOCAL_DEV_SETUP.md for the Bailian provider.",
        )
    return key


def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=_require_api_key(),
        base_url=_BAILIAN_BASE_URL,
        timeout=float(os.environ.get("OMNIGRAPH_BAILIAN_TIMEOUT", "300")),
        max_retries=1,
    )


async def bailian_model_complete(
    prompt: str,
    system_prompt: str | None = None,
    model: str | None = None,
    **kwargs,
) -> str:
    """Complete a single prompt via Bailian. OpenAI-compatible, non-streaming."""
    client = _get_client()
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    resp = await client.chat.completions.create(
        model=model or _DEFAULT_MODEL,
        messages=messages,
        max_tokens=int(os.environ.get("OMNIGRAPH_BAILIAN_MAX_TOKENS", "8192")),
        **kwargs,
    )
    return resp.choices[0].message.content or ""


async def bailian_embedding(texts: list[str], **kwargs) -> list[list[float]]:
    """Bailian embedding (qwen3.7-text-embedding, 1024-dim)."""
    client = _get_client()
    resp = await client.embeddings.create(
        model=os.environ.get("BAILIAN_EMBED_MODEL", "qwen3.7-text-embedding"),
        input=texts,
        **kwargs,
    )
    # Sort by index to preserve input order (OpenAI returns unordered).
    return [e.embedding for e in sorted(resp.data, key=lambda x: x.index)]
