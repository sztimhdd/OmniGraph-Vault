"""LOK-04: Unit tests for default_embedding_timeout kwarg propagation in kg_synthesize.

Verifies that ``synthesize_response`` passes ``default_embedding_timeout`` to
``LightRAG()`` — both the default (90) and env-override paths — without making
any real LightRAG, network, or file-system calls.

Pattern: monkeypatch-swap ``kg_synthesize.LightRAG`` with a lightweight stub
that records the kwargs it receives. Also stubs ``kg_synthesize.DB_PATH`` and
``kg_synthesize.CANONICAL_MAP_FILE`` to non-existent paths so the canonical-map
block short-circuits cleanly.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

import kg_synthesize
from config import RAG_WORKING_DIR
from lib.lightrag_embedding import embedding_func as real_embedding_func


# ---------------------------------------------------------------------------
# Shared stub infrastructure
# ---------------------------------------------------------------------------

def _make_stub_rag(captured: dict[str, Any]) -> type:
    """Return a stub LightRAG class whose __init__ writes kwargs into *captured*."""

    class _BoundStubRAG:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        async def initialize_storages(self) -> None:
            return None

        async def aquery(self, prompt: str, param: Any = None) -> str:
            return "stubbed"

    return _BoundStubRAG


# ---------------------------------------------------------------------------
# Autouse fixture: isolate env and canonical-map side-effects
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop LIGHTRAG_EMBEDDING_TIMEOUT and block filesystem side-effects."""
    monkeypatch.delenv("LIGHTRAG_EMBEDDING_TIMEOUT", raising=False)
    # Point DB_PATH and CANONICAL_MAP_FILE at non-existent paths so the
    # sqlite / JSON canonical-map block in synthesize_response short-circuits.
    monkeypatch.setattr("kg_synthesize.DB_PATH", Path("/nonexistent-path-for-test"))
    monkeypatch.setattr(
        "kg_synthesize.CANONICAL_MAP_FILE", Path("/nonexistent-path-for-test")
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_default_embedding_timeout_passed_to_lightrag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without LIGHTRAG_EMBEDDING_TIMEOUT, LightRAG receives default_embedding_timeout=90.

    LOK-01, LOK-02
    """
    captured: dict[str, Any] = {}
    monkeypatch.setattr("kg_synthesize.LightRAG", _make_stub_rag(captured))

    asyncio.run(kg_synthesize.synthesize_response("dummy query"))

    assert "default_embedding_timeout" in captured, (
        "default_embedding_timeout kwarg was not passed to LightRAG()"
    )
    assert captured["default_embedding_timeout"] == 90, (
        f"Expected 90, got {captured['default_embedding_timeout']}"
    )


def test_lightrag_embedding_timeout_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LIGHTRAG_EMBEDDING_TIMEOUT=120 overrides the default at startup.

    LOK-02
    """
    monkeypatch.setenv("LIGHTRAG_EMBEDDING_TIMEOUT", "120")
    captured: dict[str, Any] = {}
    monkeypatch.setattr("kg_synthesize.LightRAG", _make_stub_rag(captured))

    asyncio.run(kg_synthesize.synthesize_response("dummy query"))

    assert captured.get("default_embedding_timeout") == 120, (
        f"Expected 120 from env override, got {captured.get('default_embedding_timeout')}"
    )


def test_lightrag_embedding_timeout_invalid_env_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-numeric LIGHTRAG_EMBEDDING_TIMEOUT falls back to 90 without raising.

    LOK-03: defensive int() parse — non-numeric value must not crash caller.
    """
    monkeypatch.setenv("LIGHTRAG_EMBEDDING_TIMEOUT", "abc")
    captured: dict[str, Any] = {}
    monkeypatch.setattr("kg_synthesize.LightRAG", _make_stub_rag(captured))

    # Must NOT raise ValueError — defensive parse returns 90
    asyncio.run(kg_synthesize.synthesize_response("dummy query"))

    assert captured.get("default_embedding_timeout") == 90, (
        f"Invalid env should fall back to 90, got {captured.get('default_embedding_timeout')}"
    )


def test_lightrag_other_kwargs_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adding default_embedding_timeout must NOT displace existing required kwargs.

    Regression guard: working_dir, llm_model_func, embedding_func still present.
    """
    captured: dict[str, Any] = {}
    monkeypatch.setattr("kg_synthesize.LightRAG", _make_stub_rag(captured))

    asyncio.run(kg_synthesize.synthesize_response("dummy query"))

    assert "working_dir" in captured, "working_dir missing from LightRAG() call"
    assert callable(captured.get("llm_model_func")), (
        "llm_model_func missing or not callable"
    )
    assert captured.get("embedding_func") is real_embedding_func, (
        "embedding_func was replaced or is missing"
    )
