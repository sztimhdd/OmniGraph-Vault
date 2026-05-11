"""Shared embedding function for LightRAG.

Model routing (2026-05-03 correction): gemini-embedding-2 is GA as of
2026-04-22 on the `global` endpoint. Use the unsuffixed name as-is;
no alias layer. gemini-embedding-2-preview is regional-only
(us-central1 etc.) and does not exist on the global endpoint; do not
rely on it for production. See 05-00-SUMMARY.md § C for the full
story of the endpoint × model naming confusion that preceded this fix.
"""
from __future__ import annotations

import os
import re
from typing import Any

import numpy as np
import requests
from google import genai
from google.genai import types
from lightrag.utils import wrap_embedding_func_with_attrs

from google.genai.errors import ClientError

from .api_keys import (
    current_embedding_key,
    load_embedding_keys,
    rotate_embedding_key,
)
from .models import EMBEDDING_MODEL, EMBEDDING_DIM, EMBEDDING_MAX_TOKENS


_IMAGE_URL_PATTERN = re.compile(
    r"http://localhost:8765/\S+?\.(?:jpg|jpeg|png)",
    re.IGNORECASE,
)
_DOC_PREFIX = "title: none | text: "
_QUERY_PREFIX = "task: search result | query: "
_OUTPUT_DIM = EMBEDDING_DIM  # native full-capacity dim (3072); change requires NanoVectorDB wipe
_MAX_IMAGES_PER_REQUEST = 6  # Gemini hard cap per embed_content call
_IMAGE_FETCH_TIMEOUT_S = 5.0

# Plan 05-00c Task 0c.2: key-pool rotation.
# The pool itself (_KEY_POOL conceptually) lives in lib.api_keys.load_keys()
# — folds GEMINI_API_KEY + GEMINI_API_KEY_BACKUP into a round-robin cycle.
# current_key() reads the head; rotate_key() advances.
# _ROTATION_HITS tracks per-key successful call count for smoke-test telemetry.
# Consumed by scripts/wave0c_smoke.py to assert both keys rotated at least once.
_ROTATION_HITS: dict[str, int] = {}

# Phase 5-00b: embedding exhaustion cooldown.
# When both keys 429 consecutively, the per-minute quota is gone.
# Without a cooldown, LightRAG's retry loop burns ~200 calls/doc on 429s
# that all fail. A single 5-minute pause lets the RPM window reset so the
# next batch of embeddings has a clean slate.
import asyncio as _asyncio
import time as _time
_GLOBAL_COOLDOWN_UNTIL = 0.0
_COOLDOWN_SECONDS = 300  # 5 min — safe margin above Gemini's per-minute reset


def _is_429(exc: BaseException) -> bool:
    """Return True for Gemini 429 / RESOURCE_EXHAUSTED. Rotation-only; 5xx/network propagate."""
    if not isinstance(exc, ClientError):
        return False
    if getattr(exc, "code", None) == 429:
        return True
    return "RESOURCE_EXHAUSTED" in str(exc)


async def _fetch_image_part(url: str) -> types.Part | None:
    """Fetch an image URL and wrap it as a ``types.Part``.

    Runs the synchronous ``requests.get`` in a thread executor so it does
    NOT block the asyncio event loop. Returns ``None`` on any error.
    """
    import asyncio as _asyncio_mod
    loop = _asyncio_mod.get_event_loop()
    try:
        resp = await loop.run_in_executor(
            None,
            lambda: requests.get(url, timeout=_IMAGE_FETCH_TIMEOUT_S),
        )
        resp.raise_for_status()
    except Exception:
        return None

    mime = "image/png" if url.lower().endswith(".png") else "image/jpeg"
    try:
        return types.Part.from_bytes(data=resp.content, mime_type=mime)
    except Exception:
        return None


async def _build_contents(text: str, is_query: bool) -> list:
    """Build the ``contents`` payload for a single text chunk.

    Finds ALL image URLs in the chunk, fetches each IN PARALLEL via
    ``asyncio.gather``, and sends them as ``types.Part`` sidecars.
    Capped at ``_MAX_IMAGES_PER_REQUEST`` (Gemini hard limit).
    """
    prefix = _QUERY_PREFIX if is_query else _DOC_PREFIX
    urls = _IMAGE_URL_PATTERN.findall(text)
    if not urls:
        return [prefix + text]

    clean_text = _IMAGE_URL_PATTERN.sub("", text).strip()
    fetched = await _asyncio.gather(
        *[_fetch_image_part(url) for url in urls[:_MAX_IMAGES_PER_REQUEST]]
    )
    parts: list = [p for p in fetched if p is not None]

    if not parts:
        return [prefix + clean_text]
    return [prefix + clean_text] + parts


def _is_vertex_mode() -> bool:
    """Return True iff BOTH Vertex AI env vars are set (non-empty).

    D-11.08 (Plan 11-01) opt-in conditional. Evaluated at CALL TIME, not
    import time — supports test monkeypatch toggling and preserves the
    v3.3-migration-deferred scope. Empty strings count as unset so callers
    can safely `monkeypatch.setenv(var, "")` to force free-tier mode.
    """
    return bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")) and \
        bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))


def _make_client(api_key: str) -> "genai.Client":
    """Construct a ``genai.Client`` for the current mode (D-11.08).

    Vertex mode (both env vars set) uses SA JSON auth — ``api_key`` is not
    forwarded. Free-tier mode uses the rotation-managed ``api_key`` as
    before. Location defaults to ``global`` when
    ``GOOGLE_CLOUD_LOCATION`` is unset (gemini-embedding-2 GA endpoint).
    """
    if _is_vertex_mode():
        return genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        )
    return genai.Client(api_key=api_key, vertexai=False)


async def _embed_once(contents: list, model: str) -> np.ndarray:
    """Place ONE embed_content call against the current rotation key OR Vertex SA.

    Plan 05-00c Task 0c.2: wraps the physical API call so ``embedding_func``
    can retry on 429 with the next key. On a successful call in free-tier
    mode, records the key in ``_ROTATION_HITS`` for smoke-test telemetry.

    D-11.08 (Plan 11-01): when ``_is_vertex_mode()``, constructs a Vertex AI
    client (SA JSON auth); rotation telemetry is skipped in Vertex mode to
    avoid polluting ``_ROTATION_HITS`` with spurious entries against a key
    the client does not use. The model name is passed through as-is — on
    the ``global`` endpoint ``gemini-embedding-2`` is GA (2026-04-22).

    Propagates ClientError and any other exception to the caller — the
    rotation loop in ``embedding_func`` decides whether to rotate (429) or
    re-raise (everything else).
    """
    use_vertex = _is_vertex_mode()
    api_key = "" if use_vertex else current_embedding_key()
    client = _make_client(api_key)
    response = await client.aio.models.embed_content(
        model=model,
        contents=contents,
        config=types.EmbedContentConfig(output_dimensionality=_OUTPUT_DIM),
    )
    # Rotation telemetry is meaningful only for the key-rotated free-tier
    # path. In Vertex mode the SA handles auth and rotation is a no-op; skip
    # the telemetry to avoid polluting _ROTATION_HITS with non-key entries.
    if not use_vertex:
        _ROTATION_HITS[api_key] = _ROTATION_HITS.get(api_key, 0) + 1
    vec = np.asarray(response.embeddings[0].values, dtype=np.float32)
    return vec


@wrap_embedding_func_with_attrs(
    embedding_dim=EMBEDDING_DIM,
    send_dimensions=True,
    max_token_size=EMBEDDING_MAX_TOKENS,
    model_name=EMBEDDING_MODEL,
)
async def embedding_func(texts: list[str], **kwargs: Any) -> np.ndarray:
    """Embed ``texts`` via ``gemini-embedding-2`` and return a (N, 3072) float32 ndarray.

    LightRAG uses this function for BOTH upsert and query paths. The only
    discriminator is ``_priority=5`` which query calls inject; we pop it so
    it is never forwarded to the Gemini client.

    Plan 05-00c Task 0c.2: each text is embedded with per-call rotation
    + 429 failover. If the current key returns 429, ``rotate_key()`` is
    called and the same text is retried with the next key. If every key in
    the pool returns 429 for a single text, RuntimeError is raised.
    Non-429 errors propagate immediately (no rotation).
    """
    is_query = kwargs.pop("_priority", None) == 5
    model = EMBEDDING_MODEL
    # D-11.08: in Vertex mode the client ignores api_key (SA auth), so key
    # rotation is a no-op at the client level. Collapse the retry loop to 1
    # attempt to avoid 2 identical retries on a spurious 429.
    pool_size = 1 if _is_vertex_mode() else len(load_embedding_keys())

    vectors: list[np.ndarray] = []
    for text in texts:
        contents = await _build_contents(text, is_query)

        # Per-text rotation loop: try up to pool_size keys. On 429, rotate
        # and retry the SAME text with the next key. On any other error,
        # propagate immediately. If every key 429s, raise RuntimeError.
        vec: np.ndarray | None = None
        last_err: BaseException | None = None
        for _ in range(pool_size):
            try:
                vec = await _embed_once(contents, model)
                break
            except Exception as exc:  # noqa: BLE001
                if _is_429(exc):
                    last_err = exc
                    rotate_embedding_key()  # advance to next key and retry SAME text
                    continue
                raise  # non-429 — propagate immediately

        if vec is None:
            # All keys exhausted — cooldown before failing so LightRAG's
            # retry doesn't immediately hit the same wall.
            global _GLOBAL_COOLDOWN_UNTIL
            now = _time.time()
            if now < _GLOBAL_COOLDOWN_UNTIL:
                wait = _GLOBAL_COOLDOWN_UNTIL - now
                await _asyncio.sleep(wait)
            _GLOBAL_COOLDOWN_UNTIL = _time.time() + _COOLDOWN_SECONDS
            raise RuntimeError(
                f"All {pool_size} Gemini keys exhausted (429)"
            ) from last_err

        vectors.append(vec)

        # Successful embed: advance rotation cursor for the NEXT text so
        # load spreads across keys even in the happy-path (round-robin).
        if pool_size > 1:
            rotate_embedding_key()

    out = np.vstack(vectors)

    # L2-normalize rows. At ``_OUTPUT_DIM=3072`` Gemini already returns
    # unit-norm vectors, so this is idempotent; keeping it makes the function
    # correct for any chosen ``_OUTPUT_DIM``.
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return out / norms
