"""Tests for lib/api_keys.py — Phase 7 Wave 0 Task 0.2.

D-04: GEMINI_API_KEY_BACKUP folded into OMNIGRAPH_GEMINI_KEYS pool.
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


