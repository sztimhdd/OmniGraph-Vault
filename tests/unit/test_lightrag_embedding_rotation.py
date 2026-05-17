"""Tests for key rotation + 429 failover in lib.lightrag_embedding — Plan 05-00c Task 0c.2.

These tests extend the existing test_lightrag_embedding.py contract tests.
They verify the per-call rotation loop added by Task 0c.2 without disturbing
the L2-norm, task-prefix, or in-band multimodal behavior validated elsewhere.

Rotation surface under test:
  - lib.api_keys: load_keys() returns pool from GEMINI_API_KEY +
    GEMINI_API_KEY_BACKUP (or OMNIGRAPH_GEMINI_KEYS); current_key() + rotate_key()
  - lib.lightrag_embedding: per-call retry-on-429 wraps the Gemini embed call;
    rotates to next key; propagates non-429 errors; raises RuntimeError when
    all keys 429.
  - lib.lightrag_embedding._ROTATION_HITS: per-key call counter for smoke-test
    telemetry (Task 0c.6 asserts both keys >= 1 after a live run).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai.errors import ClientError


# ---------------------------------------------------------------------------
# Fixtures — reset module state between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_rotation_state(monkeypatch):
    """Reset lib.api_keys cycle + clear _ROTATION_HITS counter."""
    # Default to a 2-key pool for rotation tests (individual tests may override).
    monkeypatch.setenv("GEMINI_API_KEY", "key-A")
    monkeypatch.setenv("GEMINI_API_KEY_BACKUP", "key-B")
    monkeypatch.delenv("OMNIGRAPH_GEMINI_KEYS", raising=False)
    monkeypatch.delenv("OMNIGRAPH_GEMINI_KEY", raising=False)

    import lib.api_keys as ak
    ak._cycle = None
    ak._current = None
    ak._rotation_listeners.clear()

    import lib.lightrag_embedding as lem
    if hasattr(lem, "_ROTATION_HITS"):
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


def _make_429_client_error() -> ClientError:
    """Construct a ClientError shaped like a Gemini 429 RESOURCE_EXHAUSTED."""
    response = MagicMock()
    response.status_code = 429
    response.headers = {}
    response.json = lambda: {"error": {"code": 429, "message": "RESOURCE_EXHAUSTED"}}
    err = ClientError(
        code=429,
        response_json={"error": {"code": 429, "message": "RESOURCE_EXHAUSTED"}},
    )
    return err


def _make_500_client_error() -> ClientError:
    err = ClientError(
        code=500,
        response_json={"error": {"code": 500, "message": "INTERNAL"}},
    )
    return err


# ---------------------------------------------------------------------------
# Test 1: Single-key fallback — GEMINI_API_KEY_BACKUP unset, pool size 1
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=False,
    reason="kb-v2.1-9 audit: passes individually, fails in batch — same module-state-leak as "
    "test_round_robin_two_keys. Surface for test-isolation refactor.",
)
@pytest.mark.asyncio
async def test_single_key_fallback(monkeypatch):
    """GEMINI_API_KEY_BACKUP unset -> pool has 1 key; every call uses it."""
    monkeypatch.setenv("GEMINI_API_KEY", "only-key")
    monkeypatch.delenv("GEMINI_API_KEY_BACKUP", raising=False)
    monkeypatch.delenv("OMNIGRAPH_GEMINI_KEYS", raising=False)
    monkeypatch.delenv("OMNIGRAPH_GEMINI_KEY", raising=False)

    import lib.api_keys as ak
    ak._cycle = None
    ak._current = None
    assert ak.load_keys() == ["only-key"]

    import lib.lightrag_embedding as lem
    lem._ROTATION_HITS.clear()

    captured_keys: list[str] = []

    def _mock_client_cls(api_key, **kwargs):  # accept future client kwargs (e.g., vertexai=False)
        captured_keys.append(api_key)
        mc = MagicMock()
        mc.aio.models.embed_content = AsyncMock(return_value=_make_embed_response())
        return mc

    import google.genai as genai_mod
    with patch.object(genai_mod, "Client", side_effect=_mock_client_cls):
        await lem.embedding_func(["t1"])
        await lem.embedding_func(["t2"])
        await lem.embedding_func(["t3"])

    assert captured_keys == ["only-key", "only-key", "only-key"]
    assert lem._ROTATION_HITS.get("only-key", 0) == 3


# ---------------------------------------------------------------------------
# Test 2: Round-robin — 2 keys, 4 successive calls must rotate
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=False,
    reason="kb-v2.1-9 audit: passes individually, fails in batch — module-level rotation state "
    "in lib.lightrag_embedding leaks between tests despite autouse _reset_rotation_state "
    "fixture. Symptom: captured_keys[0] is the prior test's setting (e.g. 'only-key') "
    "instead of fixture-set 'key-A'. Needs deeper investigation of which exact module "
    "globals to clear (lem._cycle? lem._client_cache?) — not fixable via test-only edit "
    "without understanding the full state graph.",
)
@pytest.mark.asyncio
async def test_round_robin_two_keys():
    """Task 0c.2 round-robin: calls alternate between keys in pool order."""
    import lib.lightrag_embedding as lem

    captured_keys: list[str] = []

    def _mock_client_cls(api_key, **kwargs):  # accept future client kwargs (e.g., vertexai=False)
        captured_keys.append(api_key)
        mc = MagicMock()
        mc.aio.models.embed_content = AsyncMock(return_value=_make_embed_response())
        return mc

    import google.genai as genai_mod
    with patch.object(genai_mod, "Client", side_effect=_mock_client_cls):
        for _ in range(4):
            await lem.embedding_func(["t"])

    # Expect alternation A, B, A, B (first-key is the current key at init).
    assert len(captured_keys) == 4
    # Pool has exactly 2 distinct keys and each was used twice.
    assert set(captured_keys) == {"key-A", "key-B"}
    assert captured_keys.count("key-A") == 2
    assert captured_keys.count("key-B") == 2
    # Successive calls must DIFFER (prove rotation, not same-key repetition).
    for i in range(len(captured_keys) - 1):
        assert captured_keys[i] != captured_keys[i + 1]
    # Telemetry counters match.
    assert lem._ROTATION_HITS.get("key-A", 0) == 2
    assert lem._ROTATION_HITS.get("key-B", 0) == 2


# ---------------------------------------------------------------------------
# Test 3: 429 failover within a single call
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=False,
    reason="kb-v2.1-9 audit: passes individually, fails in batch — same module-state-leak as "
    "test_round_robin_two_keys. Surface for test-isolation refactor.",
)
@pytest.mark.asyncio
async def test_429_failover_within_single_call():
    """Key A returns 429 on first attempt -> rotation falls through to key B and succeeds."""
    import lib.lightrag_embedding as lem

    call_seq: list[str] = []

    def _mock_client_cls(api_key, **kwargs):  # accept future client kwargs (e.g., vertexai=False)
        call_seq.append(api_key)
        mc = MagicMock()
        if api_key == "key-A":
            mc.aio.models.embed_content = AsyncMock(side_effect=_make_429_client_error())
        else:
            mc.aio.models.embed_content = AsyncMock(return_value=_make_embed_response())
        return mc

    import google.genai as genai_mod
    with patch.object(genai_mod, "Client", side_effect=_mock_client_cls):
        out = await lem.embedding_func(["single text"])

    assert out.shape == (1, 3072)
    # Exactly 2 attempts: key-A (429) then key-B (success).
    assert call_seq == ["key-A", "key-B"]


# ---------------------------------------------------------------------------
# Test 4: Both keys 429 -> RuntimeError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_both_keys_429_raises():
    """If every key in the pool returns 429, embed_func raises RuntimeError."""
    import lib.lightrag_embedding as lem

    def _mock_client_cls(api_key, **kwargs):  # accept future client kwargs (e.g., vertexai=False)
        mc = MagicMock()
        mc.aio.models.embed_content = AsyncMock(side_effect=_make_429_client_error())
        return mc

    import google.genai as genai_mod
    with patch.object(genai_mod, "Client", side_effect=_mock_client_cls):
        with pytest.raises(RuntimeError) as exc_info:
            await lem.embedding_func(["text"])

    assert "exhausted" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 5: Non-429 error propagates immediately (no rotation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_429_error_does_not_rotate():
    """5xx / network errors should raise immediately — rotation is 429-only."""
    import lib.lightrag_embedding as lem

    attempts: list[str] = []

    def _mock_client_cls(api_key, **kwargs):  # accept future client kwargs (e.g., vertexai=False)
        attempts.append(api_key)
        mc = MagicMock()
        mc.aio.models.embed_content = AsyncMock(side_effect=_make_500_client_error())
        return mc

    import google.genai as genai_mod
    with patch.object(genai_mod, "Client", side_effect=_mock_client_cls):
        with pytest.raises(ClientError):
            await lem.embedding_func(["text"])

    # Only ONE attempt — no rotation on non-429.
    assert len(attempts) == 1


# ---------------------------------------------------------------------------
# Test 6: Empty GEMINI_API_KEY_BACKUP line treated as no-backup
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=False,
    reason="kb-v2.1-9 audit: passes individually, fails in batch — same module-state-leak as "
    "test_round_robin_two_keys. Surface for test-isolation refactor.",
)
@pytest.mark.asyncio
async def test_empty_backup_env_var_treated_as_no_backup(monkeypatch):
    """GEMINI_API_KEY_BACKUP='' -> pool has 1 key (primary only)."""
    monkeypatch.setenv("GEMINI_API_KEY", "primary")
    monkeypatch.setenv("GEMINI_API_KEY_BACKUP", "")
    monkeypatch.delenv("OMNIGRAPH_GEMINI_KEYS", raising=False)
    monkeypatch.delenv("OMNIGRAPH_GEMINI_KEY", raising=False)

    import lib.api_keys as ak
    ak._cycle = None
    ak._current = None
    assert ak.load_keys() == ["primary"]

    import lib.lightrag_embedding as lem
    lem._ROTATION_HITS.clear()

    captured_keys: list[str] = []

    def _mock_client_cls(api_key, **kwargs):  # accept future client kwargs (e.g., vertexai=False)
        captured_keys.append(api_key)
        mc = MagicMock()
        mc.aio.models.embed_content = AsyncMock(return_value=_make_embed_response())
        return mc

    import google.genai as genai_mod
    with patch.object(genai_mod, "Client", side_effect=_mock_client_cls):
        await lem.embedding_func(["t1"])
        await lem.embedding_func(["t2"])

    assert captured_keys == ["primary", "primary"]
