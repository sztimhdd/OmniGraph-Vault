"""Shared embedding function for LightRAG.

Single source of truth for Phase 5 D-01/D-03/D-04/D-05. All ingestion and
query scripts import ``embedding_func`` from this module instead of defining
their own.

Design highlights (see ``.planning/phases/05-pipeline-automation/05-RESEARCH.md``
for full derivation):

- Uses ``gemini-embedding-2`` with ``output_dimensionality=768`` so the
  existing NanoVectorDB storage files (which record ``embedding_dim: 768``)
  keep working — the Phase 4 delete-by-id + re-ainsert migration path stays
  valid (D-17).
- Distinguishes query calls from document upsert calls via the LightRAG-internal
  ``_priority=5`` kwarg (Pattern 1 / Pitfall 5). ``_priority`` is popped so it
  never leaks to the Gemini client.
- In-band multimodal: text chunks that contain
  ``http://localhost:8765/<hash>/<n>.jpg`` have the image bytes fetched and
  sent as ``types.Part.from_bytes`` in the same ``contents`` list. Gemini
  returns one aggregated 768-dim vector per item (cookbook Cell 22).
- Applies task prefixes per D-05: ``"title: none | text: "`` for documents,
  ``"task: search result | query: "`` for queries. The legacy ``task-type``
  parameter is not used (forbidden for ``-2`` per Pitfall 3).
- L2-normalizes the output because ``output_dimensionality < 3072`` is not
  auto-normalized by the API.
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


_IMAGE_URL_PATTERN = re.compile(
    r"http://localhost:8765/\S+?\.(?:jpg|jpeg|png)",
    re.IGNORECASE,
)
_DOC_PREFIX = "title: none | text: "
_QUERY_PREFIX = "task: search result | query: "
_DEFAULT_MODEL = "gemini-embedding-2"
_OUTPUT_DIM = 768
_MAX_IMAGES_PER_REQUEST = 6  # Gemini hard cap per embed_content call
_IMAGE_FETCH_TIMEOUT_S = 5.0


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


@wrap_embedding_func_with_attrs(
    embedding_dim=_OUTPUT_DIM,
    send_dimensions=True,
    max_token_size=8192,
    model_name=_DEFAULT_MODEL,
)
async def embedding_func(texts: list[str], **kwargs: Any) -> np.ndarray:
    """Embed ``texts`` via ``gemini-embedding-2`` and return a (N, 768) float32 ndarray.

    LightRAG uses this function for BOTH upsert and query paths. The only
    discriminator is ``_priority=5`` which query calls inject; we pop it so
    it is never forwarded to the Gemini client.
    """
    is_query = kwargs.pop("_priority", None) == 5

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    model = os.environ.get("EMBEDDING_MODEL", _DEFAULT_MODEL)
    client = genai.Client(api_key=api_key)

    vectors: list[np.ndarray] = []
    for text in texts:
        contents = _build_contents(text, is_query)
        response = await client.aio.models.embed_content(
            model=model,
            contents=contents,
            config=types.EmbedContentConfig(output_dimensionality=_OUTPUT_DIM),
        )
        # One aggregated embedding per ``contents`` payload — text-only OR
        # text+image both collapse to exactly one vector.
        vec = np.asarray(response.embeddings[0].values, dtype=np.float32)
        vectors.append(vec)

    out = np.vstack(vectors)

    # L2-normalize rows. ``gemini-embedding-2`` only auto-normalizes at
    # dim=3072; any truncated dim (e.g. 768) must be normalized client-side.
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return out / norms
