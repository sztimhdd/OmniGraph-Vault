"""Integration test — rotate_key() sets COGNEE_LLM_API_KEY; refresh_cognee() clears cache.

Hermes amendment 4: no bridge module, no observer pattern. Test the actual surface area:
the env-var write side-effect in rotate_key() and the cache-invalidation in refresh_cognee().
"""
from __future__ import annotations

import os
import sys

import pytest


def test_rotate_sets_env_and_refresh_clears_cache(monkeypatch, reset_lib_state):
    """End-to-end Amendment 4 contract: rotate_key() propagates to COGNEE_LLM_API_KEY."""
    monkeypatch.delenv("COGNEE_LLM_API_KEY", raising=False)
    monkeypatch.setenv("OMNIGRAPH_GEMINI_KEYS", "key-alpha,key-beta")

    from lib import current_key, rotate_key, refresh_cognee

    # First current_key() call seeds COGNEE_LLM_API_KEY
    assert current_key() == "key-alpha"
    assert os.environ.get("COGNEE_LLM_API_KEY") == "key-alpha"

    # rotate_key() advances cycle AND updates COGNEE_LLM_API_KEY inline
    new = rotate_key()
    assert new == "key-beta"
    assert os.environ.get("COGNEE_LLM_API_KEY") == "key-beta"


def test_refresh_cognee_calls_cache_clear(mocker):
    """refresh_cognee() invokes Cognee's @lru_cache cache_clear()."""
    mock_clear = mocker.patch(
        "cognee.infrastructure.llm.config.get_llm_config.cache_clear"
    )
    from lib import refresh_cognee
    refresh_cognee()
    mock_clear.assert_called_once()


def test_refresh_cognee_swallows_import_error(monkeypatch):
    """If cognee config module is unimportable, refresh_cognee() is a no-op (no raise)."""
    # Temporarily hide the cognee config module
    monkeypatch.setitem(sys.modules, "cognee.infrastructure.llm.config", None)  # type: ignore[arg-type]
    from lib import refresh_cognee
    refresh_cognee()  # must not raise
