"""Gemini API key loading, rotation, and Cognee propagation.

D-04: GEMINI_API_KEY_BACKUP is folded into OMNIGRAPH_GEMINI_KEYS pool.
Amendment 4 (Hermes review): rotate_key() writes os.environ["COGNEE_LLM_API_KEY"]
  inline as the entire propagation mechanism — no formal cognee_bridge module,
  no observer pattern. Two lines of business logic, not 35.
refresh_cognee(): long-running processes call this after rotate_key() to
  invalidate Cognee's @lru_cache'd config singleton.
"""
from __future__ import annotations

import itertools
import logging
import os
from typing import Callable, Iterator

logger = logging.getLogger(__name__)

_cycle: Iterator[str] | None = None
_current: str | None = None
_rotation_listeners: list[Callable[[str], None]] = []


def load_keys() -> list[str]:
    """Return the list of Gemini API keys to use in rotation.

    Precedence:
    1. OMNIGRAPH_GEMINI_KEYS (comma-separated pool) if set
    2. OMNIGRAPH_GEMINI_KEY and/or GEMINI_API_KEY_BACKUP combined (D-04 fold)
    3. GEMINI_API_KEY (single-key fallback)
    4. RuntimeError with remediation message
    """
    pool = os.environ.get("OMNIGRAPH_GEMINI_KEYS", "").strip()
    if pool:
        keys = [k.strip() for k in pool.split(",") if k.strip()]
        if keys:
            return keys

    # D-04: Fold OMNIGRAPH_GEMINI_KEY + GEMINI_API_KEY_BACKUP into combined pool
    primary = os.environ.get("OMNIGRAPH_GEMINI_KEY", "").strip()
    backup = os.environ.get("GEMINI_API_KEY_BACKUP", "").strip()
    if primary or backup:
        combined = [k for k in (primary, backup) if k]
        return combined

    # Single-key fallback
    single = os.environ.get("GEMINI_API_KEY", "").strip()
    if single:
        return [single]

    raise RuntimeError(
        "No Gemini API key found. Set OMNIGRAPH_GEMINI_KEY (preferred), "
        "GEMINI_API_KEY, or OMNIGRAPH_GEMINI_KEYS (comma-separated pool for rotation). "
        "Rotation only helps across different Google accounts/projects."
    )


def _init_cycle() -> None:
    global _cycle, _current
    if _cycle is None:
        _cycle = itertools.cycle(load_keys())
        _current = next(_cycle)
        os.environ["COGNEE_LLM_API_KEY"] = _current  # seed env for Cognee on first use


def current_key() -> str:
    """Return the currently active API key (lazy-initialises the pool on first call)."""
    _init_cycle()
    assert _current is not None
    return _current


def rotate_key() -> str:
    """Advance to next key in pool. Propagates to Cognee via env var for new imports.

    Amendment 4: no formal cognee_bridge module. ``os.environ[...]`` write is the
    entire propagation mechanism — short-lived scripts see fresh env on import;
    long-running processes must additionally call refresh_cognee() to invalidate
    Cognee's @lru_cache.
    """
    global _current
    _init_cycle()
    _current = next(_cycle)  # type: ignore[arg-type]
    os.environ["COGNEE_LLM_API_KEY"] = _current
    for fn in _rotation_listeners:
        try:
            fn(_current)
        except Exception as e:
            logger.warning("rotation listener failed: %s", e)
    return _current


def on_rotate(fn: Callable[[str], None]) -> None:
    """Register a callback fired after rotate_key(). Optional — most code doesn't need it."""
    _rotation_listeners.append(fn)


def refresh_cognee() -> None:
    """Invalidate Cognee's @lru_cache'd LLM config so a rotated key propagates.

    Call at the top of long-running loops (kg_synthesize.py processing loop,
    cognee_batch_processor.py poll cycle) after rotate_key(). Short-lived scripts
    don't need it — they import Cognee after os.environ is already fresh.

    Amendment 4: 5-line helper, not a module with observer scaffolding.
    """
    try:
        from cognee.infrastructure.llm.config import get_llm_config
        get_llm_config.cache_clear()
    except ImportError:
        logger.debug("Cognee not installed; refresh_cognee() is a no-op.")
    except Exception as e:
        logger.warning("refresh_cognee failed: %s", e)
