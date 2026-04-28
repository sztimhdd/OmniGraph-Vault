"""Tests for lib/api_keys.py — Phase 7 Wave 0 Task 0.2.

D-04: GEMINI_API_KEY_BACKUP folded into OMNIGRAPH_GEMINI_KEYS pool.
Amendment 4: rotate_key() writes os.environ["COGNEE_LLM_API_KEY"] inline —
  no formal cognee_bridge module, no observer pattern.
refresh_cognee(): calls cognee.infrastructure.llm.config.get_llm_config.cache_clear()
"""
from __future__ import annotations

import os
import pytest


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Isolate api_keys module state between tests."""
    for var in (
        "OMNIGRAPH_GEMINI_KEYS",
        "OMNIGRAPH_GEMINI_KEY",
        "GEMINI_API_KEY_BACKUP",
        "GEMINI_API_KEY",
        "COGNEE_LLM_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    import lib.api_keys as k
    k._cycle = None
    k._current = None
    k._rotation_listeners.clear()


def test_precedence_pool(monkeypatch):
    monkeypatch.setenv("OMNIGRAPH_GEMINI_KEYS", "a,b,c")
    from lib.api_keys import load_keys
    assert load_keys() == ["a", "b", "c"]


def test_precedence_pool_strips_whitespace(monkeypatch):
    monkeypatch.setenv("OMNIGRAPH_GEMINI_KEYS", " a , b , c ")
    from lib.api_keys import load_keys
    assert load_keys() == ["a", "b", "c"]


def test_precedence_primary_only(monkeypatch):
    monkeypatch.setenv("OMNIGRAPH_GEMINI_KEY", "x")
    from lib.api_keys import load_keys
    assert load_keys() == ["x"]


def test_precedence_backup_fold(monkeypatch):
    """D-04: OMNIGRAPH_GEMINI_KEY + GEMINI_API_KEY_BACKUP become a pool."""
    monkeypatch.setenv("OMNIGRAPH_GEMINI_KEY", "x")
    monkeypatch.setenv("GEMINI_API_KEY_BACKUP", "y")
    from lib.api_keys import load_keys
    assert load_keys() == ["x", "y"]


def test_precedence_backup_only(monkeypatch):
    """D-04: GEMINI_API_KEY_BACKUP alone creates a single-key pool."""
    monkeypatch.setenv("GEMINI_API_KEY_BACKUP", "y")
    from lib.api_keys import load_keys
    assert load_keys() == ["y"]


def test_precedence_fallback(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "z")
    from lib.api_keys import load_keys
    assert load_keys() == ["z"]


def test_precedence_raises():
    from lib.api_keys import load_keys
    with pytest.raises(RuntimeError) as exc_info:
        load_keys()
    msg = str(exc_info.value)
    assert "OMNIGRAPH_GEMINI_KEY" in msg
    assert "GEMINI_API_KEY" in msg
    assert "OMNIGRAPH_GEMINI_KEYS" in msg


def test_rotate_advances(monkeypatch):
    monkeypatch.setenv("OMNIGRAPH_GEMINI_KEYS", "k1,k2")
    from lib.api_keys import current_key, rotate_key
    assert current_key() == "k1"
    assert rotate_key() == "k2"
    assert rotate_key() == "k1"  # wraps around


def test_rotate_sets_cognee_env(monkeypatch):
    """Amendment 4: rotate_key() propagates to os.environ["COGNEE_LLM_API_KEY"]."""
    monkeypatch.setenv("OMNIGRAPH_GEMINI_KEYS", "k1,k2")
    from lib.api_keys import current_key, rotate_key
    current_key()  # init
    rotate_key()
    assert os.environ.get("COGNEE_LLM_API_KEY") == "k2"


def test_init_seeds_cognee_env(monkeypatch):
    """Amendment 4: first current_key() call seeds COGNEE_LLM_API_KEY."""
    monkeypatch.setenv("GEMINI_API_KEY", "seed-key")
    from lib.api_keys import current_key
    current_key()
    assert os.environ.get("COGNEE_LLM_API_KEY") == "seed-key"


def test_rotate_fires_listener(monkeypatch):
    monkeypatch.setenv("OMNIGRAPH_GEMINI_KEYS", "k1,k2")
    from lib.api_keys import current_key, rotate_key, on_rotate
    received: list[str] = []
    on_rotate(received.append)
    current_key()
    rotate_key()
    assert received == ["k2"]


def test_listener_exception_swallowed(monkeypatch):
    """A failing listener must not break rotate_key()."""
    monkeypatch.setenv("OMNIGRAPH_GEMINI_KEYS", "k1,k2")
    from lib.api_keys import current_key, rotate_key, on_rotate
    on_rotate(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    current_key()
    result = rotate_key()  # must not raise
    assert result == "k2"


def test_refresh_cognee_calls_cache_clear(monkeypatch, mocker):
    """Amendment 4: refresh_cognee() clears Cognee's @lru_cache on get_llm_config."""
    mock_cache_clear = mocker.patch(
        "cognee.infrastructure.llm.config.get_llm_config.cache_clear"
    )
    from lib.api_keys import refresh_cognee
    refresh_cognee()
    mock_cache_clear.assert_called_once()


def test_refresh_cognee_swallows_import_error(monkeypatch, mocker):
    """refresh_cognee() does not raise when cognee is not importable."""
    mocker.patch.dict("sys.modules", {"cognee": None, "cognee.infrastructure": None,
                                       "cognee.infrastructure.llm": None,
                                       "cognee.infrastructure.llm.config": None})
    from lib.api_keys import refresh_cognee
    # Should not raise
    refresh_cognee()
