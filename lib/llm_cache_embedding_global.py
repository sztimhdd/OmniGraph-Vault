"""Global cross-article embedding cache (260606-bd-cache-async-quickwin A2).

Hot-path mitigation for ISSUES #39 (PROCESSED-gate silent drop on
embed-queue starvation): every entity description / chunk re-embedded on
every batch even if byte-identical text was embedded for a prior article.
LightRAG's existing ``llm_response_cache`` is keyed on the entity-extract
prompt (which embeds chunk text) — it does NOT cache the embedding step.

Design:

- Wraps ``lib.lightrag_embedding._embed`` at module level. Cache layer is
  opt-in via ``OMNIGRAPH_EMBEDDING_CACHE=1`` env. Default OFF preserves
  pre-A2 behavior.
- Cache key: ``(sha256(text)[:16], is_query_bool)``. Includes the entire
  text (image URLs and all) — same prefix variant + same text → same key.
- Storage: pickle dict at ``$OMNIGRAPH_BASE_DIR/embedding_cache.pkl``,
  in-memory backed. Atomic write via ``.tmp`` rename on flush.
- Bounded: 50_000 entries; FIFO eviction on overflow (oldest 5_000 dropped
  per resize). Vectors are L2-normalized float32 (3072,) → ~12 KB each →
  ~600 MB cap.

NOT a wrapper around ``embedding_func`` directly — wraps the inner
``_embed`` callable so the ``EmbeddingFunc`` dataclass + ``send_dimensions``
flag stay byte-identical to pre-A2.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import pickle
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Any, Awaitable, Callable

import numpy as np

logger = logging.getLogger(__name__)

_CACHE_MAX = 50_000
_EVICT_BATCH = 5_000
_FLUSH_EVERY_N_MISS = 50

_LOCK = asyncio.Lock()
_CACHE: "OrderedDict[tuple[str, bool], np.ndarray]" = OrderedDict()
_DIRTY_COUNT = 0
_LOADED = False


def _cache_path() -> Path:
    base = os.environ.get("OMNIGRAPH_BASE_DIR")
    if base:
        return Path(base) / "embedding_cache.pkl"
    home = Path.home() / ".hermes" / "omonigraph-vault"
    return home / "embedding_cache.pkl"


def _key(text: str, is_query: bool) -> tuple[str, bool]:
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]
    return (digest, is_query)


def _load_from_disk() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    path = _cache_path()
    if not path.exists():
        logger.info("embedding cache: no prior cache at %s; starting empty", path)
        return
    try:
        with path.open("rb") as f:
            data = pickle.load(f)
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, np.ndarray):
                    _CACHE[k] = v
        logger.info("embedding cache: loaded %d entries from %s", len(_CACHE), path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding cache: load failed (%s); starting empty", exc)


def _flush_to_disk() -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        snapshot = dict(_CACHE)
        fd, tmp_str = tempfile.mkstemp(prefix=".embcache.", dir=str(path.parent))
        tmp = Path(tmp_str)
        try:
            with os.fdopen(fd, "wb") as f:
                pickle.dump(snapshot, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        logger.info("embedding cache: flushed %d entries to %s", len(snapshot), path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding cache: flush failed (%s); will retry on next miss batch", exc)


def _evict_if_needed() -> None:
    if len(_CACHE) <= _CACHE_MAX:
        return
    drop = _EVICT_BATCH
    for _ in range(drop):
        if not _CACHE:
            break
        _CACHE.popitem(last=False)
    logger.info("embedding cache: evicted %d oldest entries (size=%d)", drop, len(_CACHE))


def is_enabled() -> bool:
    return os.environ.get("OMNIGRAPH_EMBEDDING_CACHE", "").strip() in ("1", "true", "yes", "on")


def stats() -> dict[str, int]:
    return {"entries": len(_CACHE), "max": _CACHE_MAX, "dirty": _DIRTY_COUNT}


def wrap(inner: Callable[..., Awaitable[np.ndarray]]) -> Callable[..., Awaitable[np.ndarray]]:
    """Wrap ``_embed(texts, **kwargs)`` with cache lookup + miss-only LLM call.

    Returns an awaitable callable with the same contract: ``(N, 3072)``
    L2-normalized float32. No-op (returns ``inner`` unchanged) when cache
    is disabled, so import order and module imports are byte-identical.
    """
    if not is_enabled():
        return inner

    async def cached(texts: list[str], **kwargs: Any) -> np.ndarray:
        global _DIRTY_COUNT
        is_query = kwargs.get("_priority", None) == 5
        async with _LOCK:
            _load_from_disk()
            keys = [_key(t, is_query) for t in texts]
            cached_vecs: dict[int, np.ndarray] = {}
            miss_indices: list[int] = []
            miss_texts: list[str] = []
            for i, k in enumerate(keys):
                if k in _CACHE:
                    cached_vecs[i] = _CACHE[k]
                    _CACHE.move_to_end(k)
                else:
                    miss_indices.append(i)
                    miss_texts.append(texts[i])

        if miss_texts:
            miss_vectors = await inner(miss_texts, **kwargs)
            async with _LOCK:
                for j, idx in enumerate(miss_indices):
                    vec = miss_vectors[j]
                    _CACHE[keys[idx]] = vec
                    cached_vecs[idx] = vec
                _DIRTY_COUNT += len(miss_indices)
                _evict_if_needed()
                if _DIRTY_COUNT >= _FLUSH_EVERY_N_MISS:
                    _flush_to_disk()
                    _DIRTY_COUNT = 0

        out = np.vstack([cached_vecs[i] for i in range(len(texts))])
        return out

    return cached
