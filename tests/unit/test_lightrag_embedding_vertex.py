"""Tests for Vertex AI opt-in conditional (D-11.08 / Plan 11-01).

When BOTH ``GOOGLE_APPLICATION_CREDENTIALS`` and ``GOOGLE_CLOUD_PROJECT`` env
vars are set, ``lib.lightrag_embedding`` constructs ``genai.Client`` in Vertex
AI mode (``vertexai=True``) with the project + location, and calls
``embed_content`` with the model name as-is (no alias layer).

When either env var is missing, behavior is unchanged from the free-tier
key-rotated path (``vertexai=False`` + ``api_key=current_embedding_key()``).

Model-name handling: Vertex uses GA ``gemini-embedding-2`` on the ``global``
endpoint (2026-04-22 GA). See
``.planning/phases/05-pipeline-automation/05-00-SUMMARY.md`` § C for the
2026-04-30 → 05-03 correction history.

The env check must happen at CALL TIME, not import time, so that test
monkeypatch + runtime env toggling both work.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Reset rotation state + ensure Vertex env vars are not leaked in.

    Tests that want Vertex mode explicitly ``monkeypatch.setenv`` the three
    env vars; all other tests are guaranteed to see a clean (free-tier) env.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test-free-tier-key")
    monkeypatch.delenv("GEMINI_API_KEY_BACKUP", raising=False)
    monkeypatch.delenv("OMNIGRAPH_GEMINI_KEY", raising=False)
    monkeypatch.delenv("OMNIGRAPH_GEMINI_KEYS", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_LOCATION", raising=False)

    import lib.api_keys as ak
    ak._cycle = None
    ak._current = None
    ak._embedding_cycle = None
    ak._current_embedding = None
    ak._rotation_listeners.clear()

    import lib.lightrag_embedding as lem
    lem._ROTATION_HITS.clear()


def _make_embed_response(dims: int = 3072, n_texts: int = 1) -> MagicMock:
    resp = MagicMock()
    embeddings = []
    for _ in range(n_texts):
        emb = MagicMock()
        emb.values = [0.1] * dims
        embeddings.append(emb)
    resp.embeddings = embeddings
    return resp


def _install_capturing_client(monkeypatch) -> dict[str, Any]:
    """Monkeypatch ``genai.Client`` to capture kwargs and return a mock.

    Returns a dict with ``client_kwargs`` (list of per-call kwarg dicts) and
    ``embed_kwargs`` (list of per-call kwarg dicts for embed_content).
    """
    captured: dict[str, Any] = {"client_kwargs": [], "embed_kwargs": []}

    def _fake_client_cls(*args, **kwargs):
        captured["client_kwargs"].append(kwargs)
        mock_client = MagicMock()

        async def _fake_embed(**embed_kwargs):
            captured["embed_kwargs"].append(embed_kwargs)
            return _make_embed_response()

        mock_client.aio.models.embed_content = _fake_embed
        return mock_client

    import lib.lightrag_embedding as lem
    monkeypatch.setattr(lem.genai, "Client", _fake_client_cls)
    return captured


# ---------------------------------------------------------------------------
# Test 1: Default (no env vars) → free-tier path preserved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_free_tier_path_default(monkeypatch):
    """No Vertex env vars → vertexai=False + api_key=current_embedding_key + model=gemini-embedding-2."""
    captured = _install_capturing_client(monkeypatch)

    import lib.lightrag_embedding as lem
    await lem.embedding_func(["hello"])

    assert len(captured["client_kwargs"]) == 1
    ckw = captured["client_kwargs"][0]
    assert ckw.get("vertexai") is False
    assert ckw.get("api_key") == "test-free-tier-key"
    assert "project" not in ckw
    assert "location" not in ckw

    assert len(captured["embed_kwargs"]) == 1
    ekw = captured["embed_kwargs"][0]
    assert ekw.get("model") == "gemini-embedding-2"

    # Rotation telemetry still records in free-tier mode.
    assert lem._ROTATION_HITS.get("test-free-tier-key", 0) == 1


# ---------------------------------------------------------------------------
# Test 2: Both env vars set → Vertex AI mode, GA gemini-embedding-2, default location
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vertex_mode_both_env_vars_set(monkeypatch):
    """Both env vars set → genai.Client(vertexai=True, project=..., location='us-central1')."""
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/fake/sa.json")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project-123")

    captured = _install_capturing_client(monkeypatch)

    import lib.lightrag_embedding as lem
    await lem.embedding_func(["hello"])

    assert len(captured["client_kwargs"]) == 1
    ckw = captured["client_kwargs"][0]
    assert ckw.get("vertexai") is True
    assert ckw.get("project") == "my-project-123"
    assert ckw.get("location") == "us-central1"  # default when GOOGLE_CLOUD_LOCATION unset
    # In Vertex mode the SA handles auth — api_key must NOT be forwarded.
    assert "api_key" not in ckw or ckw.get("api_key") in (None, "")

    assert len(captured["embed_kwargs"]) == 1
    ekw = captured["embed_kwargs"][0]
    # GA model name passes through unchanged in Vertex mode; no alias layer.
    # ``gemini-embedding-2`` is GA on the ``global`` endpoint as of 2026-04-22.
    assert ekw.get("model") == "gemini-embedding-2"

    # Rotation telemetry is a no-op in Vertex mode (SA auth, not API keys).
    # _ROTATION_HITS must be empty (no spurious entries).
    assert lem._ROTATION_HITS == {}


# ---------------------------------------------------------------------------
# Test 3: Custom GOOGLE_CLOUD_LOCATION respected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vertex_mode_custom_location(monkeypatch):
    """GOOGLE_CLOUD_LOCATION overrides the us-central1 default."""
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/fake/sa.json")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project-123")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "europe-west4")

    captured = _install_capturing_client(monkeypatch)

    import lib.lightrag_embedding as lem
    await lem.embedding_func(["hello"])

    ckw = captured["client_kwargs"][0]
    assert ckw.get("vertexai") is True
    assert ckw.get("project") == "my-project-123"
    assert ckw.get("location") == "europe-west4"


# ---------------------------------------------------------------------------
# Test 4a: Only GOOGLE_APPLICATION_CREDENTIALS set → free-tier fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_credentials_set_falls_back(monkeypatch):
    """Only GOOGLE_APPLICATION_CREDENTIALS set (no project) → free-tier path (both required)."""
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/fake/sa.json")
    # GOOGLE_CLOUD_PROJECT deliberately unset.

    captured = _install_capturing_client(monkeypatch)

    import lib.lightrag_embedding as lem
    await lem.embedding_func(["hello"])

    ckw = captured["client_kwargs"][0]
    assert ckw.get("vertexai") is False
    assert ckw.get("api_key") == "test-free-tier-key"

    ekw = captured["embed_kwargs"][0]
    assert ekw.get("model") == "gemini-embedding-2"


# ---------------------------------------------------------------------------
# Test 4b: Only GOOGLE_CLOUD_PROJECT set → free-tier fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_project_set_falls_back(monkeypatch):
    """Only GOOGLE_CLOUD_PROJECT set (no SA credentials) → free-tier path (both required)."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project-123")
    # GOOGLE_APPLICATION_CREDENTIALS deliberately unset.

    captured = _install_capturing_client(monkeypatch)

    import lib.lightrag_embedding as lem
    await lem.embedding_func(["hello"])

    ckw = captured["client_kwargs"][0]
    assert ckw.get("vertexai") is False
    assert ckw.get("api_key") == "test-free-tier-key"

    ekw = captured["embed_kwargs"][0]
    assert ekw.get("model") == "gemini-embedding-2"


# ---------------------------------------------------------------------------
# Test 5: _is_vertex_mode() evaluated at CALL TIME, not import time
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_vertex_mode_evaluated_at_call_time(monkeypatch):
    """Flipping env vars between calls must flip the mode — no import-time capture."""
    captured = _install_capturing_client(monkeypatch)

    import lib.lightrag_embedding as lem

    # Call 1: no env vars → free-tier.
    await lem.embedding_func(["first"])
    assert captured["client_kwargs"][-1].get("vertexai") is False

    # Set both env vars.
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/fake/sa.json")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project-123")

    # Call 2: Vertex mode. GA model name is unsuffixed; passes through.
    await lem.embedding_func(["second"])
    assert captured["client_kwargs"][-1].get("vertexai") is True
    assert captured["embed_kwargs"][-1].get("model") == "gemini-embedding-2"

    # Unset both.
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

    # Call 3: back to free-tier.
    await lem.embedding_func(["third"])
    assert captured["client_kwargs"][-1].get("vertexai") is False
    assert captured["embed_kwargs"][-1].get("model") == "gemini-embedding-2"


# ---------------------------------------------------------------------------
# Test 6: Helper function `_is_vertex_mode` exposed and correct
# ---------------------------------------------------------------------------


def test_is_vertex_mode_helper_truth_table(monkeypatch):
    """_is_vertex_mode returns True iff BOTH env vars are set (not empty strings)."""
    import lib.lightrag_embedding as lem

    # Neither set.
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    assert lem._is_vertex_mode() is False

    # Only one set.
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/fake/sa.json")
    assert lem._is_vertex_mode() is False
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    assert lem._is_vertex_mode() is False

    # Both set.
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/fake/sa.json")
    assert lem._is_vertex_mode() is True

    # Empty string in either treated as unset.
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    assert lem._is_vertex_mode() is False
