"""Async/sync LLM and embedding entry points with retry and rate limiting.

Amendment 5 (Hermes review): generate() and generate_sync() accept `contents`
as a str OR a list of parts (text + types.Part.from_bytes for images). The
google-genai SDK handles both natively — there is no fall-back to a direct
genai.Client path. One code path through lib/, rate limit + retry + rotation
apply uniformly.

Retry nesting: @retry is OUTSIDE async with get_limiter(model). This means:
  1. Limiter slot acquired
  2. API call attempted (may raise APIError)
  3. On retriable error, key is rotated and tenacity schedules a retry
  4. Retry re-acquires a new limiter slot for the new key's quota window
This ordering is verified against aiolimiter 1.2.1 semantics.
"""
from __future__ import annotations

import asyncio
import logging

from google import genai
from google.genai.errors import APIError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .api_keys import current_key, rotate_key
from .rate_limit import get_limiter

logger = logging.getLogger(__name__)

_client: genai.Client | None = None
_client_key: str | None = None


def _get_client() -> genai.Client:
    """Return a cached genai.Client. Rebuilds on key change (after rotate_key())."""
    global _client, _client_key
    key = current_key()
    if _client is None or _client_key != key:
        _client = genai.Client(api_key=key)
        _client_key = key
    return _client


def _is_retriable(exc: BaseException) -> bool:
    """Return True only for transient API errors (429 quota, 503 unavailable)."""
    return isinstance(exc, APIError) and getattr(exc, "code", None) in {429, 503}


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception(_is_retriable),
    reraise=True,
)
async def generate(model: str, contents, **kwargs) -> str:
    """Async LLM call. ``contents`` is a string OR a list of parts.

    google-genai SDK accepts both natively (Amendment 5) — no fall-back path.
    """
    async with get_limiter(model):
        try:
            response = await _get_client().aio.models.generate_content(
                model=model, contents=contents, **kwargs
            )
            return response.text
        except APIError as e:
            if _is_retriable(e):
                rotate_key()
            raise


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception(_is_retriable),
    reraise=True,
)
async def aembed(model: str, texts: list[str], **kwargs) -> list[list[float]]:
    """Async embedding call. Returns a list of float vectors."""
    async with get_limiter(model):
        try:
            response = await _get_client().aio.models.embed_content(
                model=model, contents=texts, **kwargs
            )
            return [e.values for e in response.embeddings]
        except APIError as e:
            if _is_retriable(e):
                rotate_key()
            raise


def generate_sync(model: str, contents, **kwargs) -> str:
    """Sync wrapper around generate(). Same multimodal contract — ``contents`` may be str or list."""
    return asyncio.run(generate(model, contents, **kwargs))
