"""Quick 260517-rgd-2: DeepSeek 402 graceful-degrade unit tests.

Targets ``ingest_wechat._ainsert_with_402_fallback`` — a small helper that
wraps ``rag.ainsert`` with selective handling for DeepSeek 402 (insufficient
balance) errors. On 402, the helper:

  - writes the body to LightRAG kv_store_full_docs (text search still finds it)
  - writes a sidecar marker at ``checkpoints/{ckpt_hash}/degraded.json``
  - logs a WARNING line and returns False (caller should still mark stage done)

Non-402 RuntimeErrors propagate so the outer batch try/except can mark the
article failed and the operator gets visibility on a real failure.

Marker mechanism (executor's choice per spec): sidecar JSON file on disk.
Reconcile distinguishes a degraded article via the presence of this file —
the article appears as "ok" in ingestions and "pending" or absent in
kv_store_doc_status.json, but the marker file proves it was a deliberate
degraded path, not a ghost-failure. (Test 3 reads the marker directly to
keep Patch 2 independent of Patch 1's reconcile changes.)

Audit: ARCHITECTURE-AUDIT-Ingest-Pipeline-v1.md §3 Patch 2.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# DEEPSEEK_API_KEY=dummy satisfies the eager import at lib/__init__.py
# (Phase 5 cross-coupling FLAG 2). Set via fixture rather than top-level
# os.environ to keep test isolation explicit.
@pytest.fixture(autouse=True)
def _deepseek_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")


@pytest.fixture
def helper_fn(monkeypatch, tmp_path):
    """Yield the _ainsert_with_402_fallback helper.

    Imported lazily so the autouse env fixture runs first. Also redirects the
    checkpoint BASE_DIR to a tmp_path so the sidecar marker writes don't
    pollute the real ~/.hermes/omonigraph-vault/checkpoints tree.
    """
    monkeypatch.setenv("OMNIGRAPH_CHECKPOINT_BASE_DIR", str(tmp_path))
    # Reload lib.checkpoint so its module-level BASE_DIR picks up the env
    # override (fixture-time monkeypatch happens after module import).
    import importlib
    import lib.checkpoint as ckpt_mod
    importlib.reload(ckpt_mod)
    # ingest_wechat.py imports get_article_hash etc. from lib.checkpoint at
    # import time, but the helper we're testing reaches into lib.checkpoint
    # at call time via get_checkpoint_dir(...). The reload above updates
    # the canonical module reference; the helper resolves through that.

    from ingest_wechat import _ainsert_with_402_fallback
    return _ainsert_with_402_fallback


def _mk_rag(side_effect):
    """Build a MagicMock rag whose ``ainsert`` is an AsyncMock with given side_effect."""
    rag = MagicMock()
    rag.ainsert = AsyncMock(side_effect=side_effect)
    return rag


# ---------------------------------------------------------------------------
# Test 1 — 402 RuntimeError → text-only degrade, no propagation
# ---------------------------------------------------------------------------


async def test_402_falls_back_to_text_only(helper_fn, tmp_path):
    """A DeepSeek 402 RuntimeError inside ainsert degrades gracefully.

    Setup:
      - rag.ainsert mocked to raise the canonical DeepSeek 402 RuntimeError
        message ("Error code: 402 - {... 'Insufficient Balance' ...}")
      - tmp_path checkpoint BASE_DIR (set by helper_fn fixture)

    Expected:
      - Helper returns False (degraded path taken)
      - Sidecar marker file exists at checkpoints/{ckpt_hash}/degraded.json
      - Marker payload contains doc_id + reason + timestamp
      - No exception propagates
    """
    rag = _mk_rag([
        RuntimeError(
            "Error code: 402 - {'error':{'message':'Insufficient Balance',"
            "'type':'unknown_error','param':null,'code':'invalid_request_error'}}"
        )
    ])

    doc_id = "wechat_402_degrade_aaa"
    ckpt_hash = "0123456789abcdef"
    body = "x" * 1000  # >= MIN_INGEST_BODY_LEN guard (handled by caller, not helper)

    result = await helper_fn(rag, doc_id, body, ckpt_hash)

    assert result is False  # degraded path
    rag.ainsert.assert_awaited_once_with(body, ids=[doc_id])

    # Sidecar marker present
    marker = tmp_path / "checkpoints" / ckpt_hash / "degraded.json"
    assert marker.exists()
    payload = json.loads(marker.read_text())
    assert payload["doc_id"] == doc_id
    assert payload["reason"] == "402_insufficient_balance"
    assert isinstance(payload["timestamp"], (int, float))


# ---------------------------------------------------------------------------
# Test 2 — non-402 RuntimeError still propagates
# ---------------------------------------------------------------------------


async def test_non_402_runtime_error_still_propagates(helper_fn, tmp_path):
    """A non-402 RuntimeError must propagate so the outer batch loop sees the failure.

    Setup:
      - rag.ainsert raises RuntimeError("Connection timed out") (no '402'
        substring, no 'insufficient' substring case-insensitive)

    Expected:
      - RuntimeError raised by helper (caller's outer try/except catches and
        marks article failed)
      - No degraded marker created (this is a real failure, not a graceful
        degrade case — operator must see it)
    """
    rag = _mk_rag([RuntimeError("Connection timed out")])

    doc_id = "wechat_real_fail_bbb"
    ckpt_hash = "fedcba9876543210"
    body = "y" * 1000

    with pytest.raises(RuntimeError, match="Connection timed out"):
        await helper_fn(rag, doc_id, body, ckpt_hash)

    rag.ainsert.assert_awaited_once_with(body, ids=[doc_id])

    # No marker should exist for non-402 failures
    marker = tmp_path / "checkpoints" / ckpt_hash / "degraded.json"
    assert not marker.exists()


# ---------------------------------------------------------------------------
# Test 3 — degraded marker is reconcile-distinguishable from ghost / normal-ok
# ---------------------------------------------------------------------------


async def test_402_marker_visible_to_reconcile(helper_fn, tmp_path):
    """The degraded marker is a distinct on-disk artifact reconcile can detect.

    Distinguisher: a degraded article has the sidecar ``degraded.json`` file
    under ``checkpoints/{ckpt_hash}/``, while a normal-ok article has none
    and a ghost article (whichever direction) also has none. Reconcile can
    grep these sidecars to count degraded articles separately from mystery
    or ghost categories.

    To keep Patches 1 and 2 independent (so a Patch 1 rollback doesn't
    invalidate Patch 2 tests), we verify the marker contents directly here
    rather than threading it through reconcile_ingestions.main. The marker
    file IS the distinguisher; how reconcile chooses to surface it is a
    separate concern (future v1.x work, not part of this patch).
    """
    rag = _mk_rag([
        RuntimeError(
            "Error code: 402 - Insufficient Balance"
        )
    ])

    doc_id = "wechat_marker_visible_ccc"
    ckpt_hash = "abcd1234ef567890"
    body = "z" * 1000

    await helper_fn(rag, doc_id, body, ckpt_hash)

    # The marker is the distinguishing artifact
    marker = tmp_path / "checkpoints" / ckpt_hash / "degraded.json"
    assert marker.exists()

    payload = json.loads(marker.read_text())
    # Required fields for reconcile to attribute the degrade reason
    assert payload["doc_id"] == doc_id
    assert payload["reason"] == "402_insufficient_balance"
    # Timestamp is a sortable scalar so reconcile can window the degrade rate
    assert isinstance(payload["timestamp"], (int, float))
    assert payload["timestamp"] > 0

    # And the marker is the ONLY new artifact under checkpoints/{ckpt_hash}/
    # (no kv_store collision, no shared marker with ghost / normal-ok paths).
    files = sorted(p.name for p in marker.parent.iterdir())
    assert files == ["degraded.json"]
