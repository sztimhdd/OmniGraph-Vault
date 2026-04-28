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

import re
from typing import Any

import numpy as np
import requests
from google import genai
from google.genai import types
from lightrag.utils import wrap_embedding_func_with_attrs

from google.genai.errors import ClientError

from .api_keys import current_key, load_keys, rotate_key
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

    Strips up to one image URL from the text and replaces it with a
    ``types.Part`` sidecar so Gemini produces one aggregated embedding.
    """
    prefix = _QUERY_PREFIX if is_query else _DOC_PREFIX
    match = _IMAGE_URL_PATTERN.search(text)
    if match is None:
        return [prefix + text]

    url = match.group(0)
    part = _fetch_image_part(url)
    clean_text = _IMAGE_URL_PATTERN.sub("", text).strip()
    if part is None:
        # Fall through to text-only on fetch failure — keep retrieval working.
        return [prefix + clean_text]
    return [prefix + clean_text, part]


async def _embed_once(contents: list, model: str) -> np.ndarray:
    """Place ONE embed_content call against the current rotation key.

    Plan 05-00c Task 0c.2: wraps the physical API call so ``embedding_func``
    can retry on 429 with the next key. On a successful call, records the
    key in ``_ROTATION_HITS`` for smoke-test telemetry.

    Propagates ClientError and any other exception to the caller — the
    rotation loop in ``embedding_func`` decides whether to rotate (429) or
    re-raise (everything else).
    """
    api_key = current_key()
    client = genai.Client(api_key=api_key)
    response = await client.aio.models.embed_content(
        model=model,
        contents=contents,
        config=types.EmbedContentConfig(output_dimensionality=_OUTPUT_DIM),
    )
    # Record successful call for telemetry; only counts successes so a
    # partially-exhausted key doesn't mask the fact that the OTHER key is
    # doing all the real work.
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
    pool_size = len(load_keys())

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
                    rotate_key()  # advance to next key and retry SAME text
                    continue
                raise  # non-429 — propagate immediately

        if vec is None:
            raise RuntimeError(
                f"All {pool_size} Gemini keys exhausted (429)"
            ) from last_err

        vectors.append(vec)

        # Successful embed: advance rotation cursor for the NEXT text so
        # load spreads across keys even in the happy-path (round-robin).
        if pool_size > 1:
            rotate_key()

    out = np.vstack(vectors)

    # L2-normalize rows. At ``_OUTPUT_DIM=3072`` Gemini already returns
    # unit-norm vectors, so this is idempotent; keeping it makes the function
    # correct for any chosen ``_OUTPUT_DIM``.
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return out / norms
