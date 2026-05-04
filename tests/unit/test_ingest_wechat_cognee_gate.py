"""Unit tests for OMNIGRAPH_COGNEE_INLINE gate in ingest_wechat.

2026-05-03 hotfix (quick 260503-v9z): cognee_wrapper.remember_article is gated
behind OMNIGRAPH_COGNEE_INLINE env var (default "0" = OFF) to unblock the KOL
ingest fast-path from Cognee's LiteLLM -> AI Studio 422 NOT_FOUND loop on
gemini-embedding-2. Root fix: v3.4 Phase 20/21.

All tests are mock-only: no real cognee/LiteLLM/HTTP.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


# ---------- Predicate-level tests (_cognee_inline_enabled) ----------

def test_unset_returns_false(monkeypatch):
    monkeypatch.delenv("OMNIGRAPH_COGNEE_INLINE", raising=False)
    import ingest_wechat
    assert ingest_wechat._cognee_inline_enabled() is False


def test_zero_returns_false(monkeypatch):
    monkeypatch.setenv("OMNIGRAPH_COGNEE_INLINE", "0")
    import ingest_wechat
    assert ingest_wechat._cognee_inline_enabled() is False


def test_one_returns_true(monkeypatch):
    monkeypatch.setenv("OMNIGRAPH_COGNEE_INLINE", "1")
    import ingest_wechat
    assert ingest_wechat._cognee_inline_enabled() is True


def test_empty_string_returns_false(monkeypatch):
    monkeypatch.setenv("OMNIGRAPH_COGNEE_INLINE", "")
    import ingest_wechat
    assert ingest_wechat._cognee_inline_enabled() is False


@pytest.mark.parametrize("val", ["true", "yes", "TRUE", "True", "YES", "y", "on"])
def test_truthy_strings_return_false(monkeypatch, val):
    """Strict == "1" only — no truthy-string parsing."""
    monkeypatch.setenv("OMNIGRAPH_COGNEE_INLINE", val)
    import ingest_wechat
    assert ingest_wechat._cognee_inline_enabled() is False


# ---------- Call-level tests (gate wiring) ----------

async def _exercise_gate_snippet() -> None:
    """Execute the same predicate + call pattern ingest_article uses.

    Mirrors the wrapped block at ingest_wechat.py:~1102. The predicate is
    resolved via the production module so any drift in the helper's body is
    caught here, not just in the predicate tests above.
    """
    import ingest_wechat
    if ingest_wechat._cognee_inline_enabled():
        try:
            await ingest_wechat.cognee_wrapper.remember_article(
                title="t",
                url="u",
                entities=["e"],
                summary_gist="g",
            )
        except Exception:
            pass


async def test_gate_off_skips_remember_article(monkeypatch, mocker):
    monkeypatch.delenv("OMNIGRAPH_COGNEE_INLINE", raising=False)
    m = mocker.patch(
        "ingest_wechat.cognee_wrapper.remember_article",
        new_callable=AsyncMock,
    )
    await _exercise_gate_snippet()
    assert m.call_count == 0


async def test_gate_zero_skips_remember_article(monkeypatch, mocker):
    monkeypatch.setenv("OMNIGRAPH_COGNEE_INLINE", "0")
    m = mocker.patch(
        "ingest_wechat.cognee_wrapper.remember_article",
        new_callable=AsyncMock,
    )
    await _exercise_gate_snippet()
    assert m.call_count == 0


@pytest.mark.parametrize("val", ["true", "yes", "TRUE"])
async def test_gate_truthy_string_skips_remember_article(monkeypatch, mocker, val):
    monkeypatch.setenv("OMNIGRAPH_COGNEE_INLINE", val)
    m = mocker.patch(
        "ingest_wechat.cognee_wrapper.remember_article",
        new_callable=AsyncMock,
    )
    await _exercise_gate_snippet()
    assert m.call_count == 0


async def test_gate_one_invokes_remember_article(monkeypatch, mocker):
    monkeypatch.setenv("OMNIGRAPH_COGNEE_INLINE", "1")
    m = mocker.patch(
        "ingest_wechat.cognee_wrapper.remember_article",
        new_callable=AsyncMock,
    )
    await _exercise_gate_snippet()
    assert m.call_count == 1
    kwargs = m.call_args.kwargs
    assert set(kwargs.keys()) == {"title", "url", "entities", "summary_gist"}
