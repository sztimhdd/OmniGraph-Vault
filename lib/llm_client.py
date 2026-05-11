"""Async/sync LLM and embedding entry points with retry and rate limiting.

Amendment 5 (Hermes review): generate() and generate_sync() accept ``contents``
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

D-11.08 Extension: Vertex AI opt-in shared from lib.lightrag_embedding.
When GOOGLE_APPLICATION_CREDENTIALS + GOOGLE_CLOUD_PROJECT are both set,
genai.Client is constructed in Vertex AI mode (SA auth) instead of API key
mode. Retry/rotation are no-ops in Vertex mode.
"""
from __future__ import annotations

import asyncio
import logging
import os

from google import genai
from google.genai.errors import APIError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .api_keys import current_key, rotate_key
from .lightrag_embedding import _is_vertex_mode
from .rate_limit import get_limiter

logger = logging.getLogger(__name__)

_client: genai.Client | None = None
_client_key: str | None = None


def _make_client() -> genai.Client:
    """Construct a genai.Client for the current mode.

    Vertex mode (both env vars set) uses SA JSON auth — api_key is not
    forwarded. Free-tier mode uses the rotation-managed key as before.
    """
    if _is_vertex_mode():
        # Quick 260511-n0b mirror of b3y (b1e7fc8) — Vertex 'global' endpoint pools quota
        # across projects + avoids 404 NOT_FOUND on gemini-embedding-2 / GA endpoints.
        return genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        )
    return genai.Client(api_key=current_key(), vertexai=False)


def _get_client() -> genai.Client:
    """Return a cached genai.Client. Rebuilds on key change (after rotate_key()).

    In Vertex mode the client is auth-agnostic to API keys — it caches once
    and never rebuilds (rotation is a no-op).
    """
    global _client, _client_key
    if _is_vertex_mode():
        if _client is None:
            _client = _make_client()
            _client_key = "__vertex__"
        return _client
    key = current_key()
    if _client is None or _client_key != key:
        _client = _make_client()
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
