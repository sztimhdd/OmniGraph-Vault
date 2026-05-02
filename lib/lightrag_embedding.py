"""Shared embedding function for LightRAG — Phase 7 D-09 absorption.

Moved from repo-root ``lightrag_embedding.py`` per D-09. The root module is
now a 2-line shim that re-exports this function for backward compat.

Single source of truth for Phase 5 D-01/D-03/D-04/D-05. All ingestion and
query scripts import ``embedding_func`` from this module instead of defining
their own.

D-09 changes (surgical only):
- api_key: was ``os.environ.get("GEMINI_API_KEY")`` → now ``current_key()``
  (rotation-aware; uses lib.api_keys)
- model: was ``os.environ.get("EMBEDDING_MODEL", _DEFAULT_MODEL)`` → now
  ``EMBEDDING_MODEL`` (constant from lib.models; default = "gemini-embedding-2")
- ``_DEFAULT_MODEL`` constant removed (now in lib.models as EMBEDDING_MODEL)

Plan 05-00c Task 0c.2 changes (surgical only):
- Per-text rotation loop: on 429 the same text is retried against the next
  key in the pool via ``rotate_key()``. All keys 429 -> RuntimeError.
  Non-429 errors propagate immediately (no rotation on 5xx / network).
- Happy-path round-robin: after each successful embed, ``rotate_key()``
  advances the cursor so successive texts spread across the pool. When
  keys live on separate GCP projects this effectively doubles the
  per-minute embed budget.
- ``_ROTATION_HITS`` counter tracks per-key successful call count — used
  by smoke tests to assert both keys were exercised.

Design highlights (see ``.planning/phases/05-pipeline-automation/05-RESEARCH.md``
for full derivation):

- Uses ``gemini-embedding-2`` with ``output_dimensionality=3072`` — the native
  full-capacity dim. At 3072 the API auto-normalizes vectors; we still L2-norm
  client-side so behavior is identical across any ``_OUTPUT_DIM`` choice.
  Changing this dim requires wiping NanoVectorDB storage.
- Distinguishes query calls from document upsert calls via the LightRAG-internal
  ``_priority=5`` kwarg (Pattern 1 / Pitfall 5). ``_priority`` is popped so it
  never leaks to the Gemini client.
- In-band multimodal: text chunks that contain
  ``http://localhost:8765/<hash>/<n>.jpg`` have the image bytes fetched and
  sent as ``types.Part.from_bytes`` in the same ``contents`` list. Gemini
  returns one aggregated 3072-dim vector per item (cookbook Cell 22).
- Applies task prefixes per D-05: ``"title: none | text: "`` for documents,
  ``"task: search result | query: "`` for queries.

Asymmetric wrapping note (lib/__init__.py docstring): LLM calls are wrapped
from outside LightRAG (via lib.generate). Embeddings are owned here because
LightRAG's embedding contract requires in-band multimodal logic that cannot be
layered externally.
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


def _fetch_image_part(url: str) -> types.Part | None:
    """Fetch an image URL and wrap it as a ``types.Part``.

    Returns ``None`` on any error so the caller can degrade gracefully to
    text-only embedding.
    """
    try:
        resp = requests.get(url, timeout=_IMAGE_FETCH_TIMEOUT_S)
        resp.raise_for_status()
    except Exception:
        return None

    mime = "image/png" if url.lower().endswith(".png") else "image/jpeg"
    try:
        return types.Part.from_bytes(data=resp.content, mime_type=mime)
    except Exception:
        return None


def _build_contents(text: str, is_query: bool) -> list:
    """Build the ``contents`` payload for a single text chunk.

    Finds ALL image URLs in the chunk, fetches each, and sends them as
    ``types.Part`` sidecars. Capped at ``_MAX_IMAGES_PER_REQUEST`` (Gemini
    hard limit). Gemini produces one aggregated embedding per chunk.
    """
    prefix = _QUERY_PREFIX if is_query else _DOC_PREFIX
    urls = _IMAGE_URL_PATTERN.findall(text)
    if not urls:
        return [prefix + text]

    clean_text = _IMAGE_URL_PATTERN.sub("", text).strip()
    parts: list = []
    for url in urls[:_MAX_IMAGES_PER_REQUEST]:
        part = _fetch_image_part(url)
        if part is not None:
            parts.append(part)

    if not parts:
        # Fall through to text-only on fetch failure — keep retrieval working.
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
    before. Location defaults to ``us-central1`` when
    ``GOOGLE_CLOUD_LOCATION`` is unset.
    """
    if _is_vertex_mode():
        return genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    return genai.Client(api_key=api_key, vertexai=False)


def _resolve_model(base_model: str) -> str:
    """Map the free-tier model name to its Vertex AI equivalent (D-11.08).

    Memory ref: ``vertex_ai_smoke_validated.md`` — ``gemini-embedding-2``
    returns 404 on Vertex AI; ``gemini-embedding-2-preview`` is the working
    multimodal model name. Only applied in Vertex mode AND only for the
    exact free-tier name; all other model names pass through unchanged so
    future callers can pin a specific Vertex-native model.
    """
    # 2026-05-02: gemini-embedding-2-preview deprecated by Vertex AI
    return base_model


async def _embed_once(contents: list, model: str) -> np.ndarray:
    """Place ONE embed_content call against the current rotation key OR Vertex SA.

    Plan 05-00c Task 0c.2: wraps the physical API call so ``embedding_func``
    can retry on 429 with the next key. On a successful call in free-tier
    mode, records the key in ``_ROTATION_HITS`` for smoke-test telemetry.

    D-11.08 (Plan 11-01): when ``_is_vertex_mode()``, constructs a Vertex AI
    client (SA JSON auth) and resolves the model name to its -preview
    variant; rotation telemetry is skipped in Vertex mode to avoid
    polluting ``_ROTATION_HITS`` with spurious entries against a key the
    client does not use.

    Propagates ClientError and any other exception to the caller — the
    rotation loop in ``embedding_func`` decides whether to rotate (429) or
    re-raise (everything else).
    """
    use_vertex = _is_vertex_mode()
    api_key = "" if use_vertex else current_embedding_key()
    client = _make_client(api_key)
    resolved_model = _resolve_model(model)
    response = await client.aio.models.embed_content(
        model=resolved_model,
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
        contents = _build_contents(text, is_query)

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
