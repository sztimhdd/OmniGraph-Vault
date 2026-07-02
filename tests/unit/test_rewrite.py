"""Unit tests for lib.rewrite (kb-v2.3).

All 7 behavior tests use mocked LLM — no network calls.

Tests:
  RW-VALVE-PASS       — identical URL set -> valve accepts
  RW-VALVE-REJECT-DROP — output missing one URL -> valve returns None
  RW-VALVE-REJECT-ADD  — output has extra/hallucinated URL -> valve returns None
  RW-VALVE-REJECT-MUTATE — output has mutated URL -> valve returns None
  RW-EMPTY             — LLM returns empty -> function returns None
  RW-PROMPT-CONSTANTS  — prompt contains image-URL constraint + boilerplate markers
  RW-LAZY-IMPORT       — import lib.rewrite succeeds with DEEPSEEK_API_KEY unset
"""
from __future__ import annotations

import importlib
import os
# Phase 5 cross-coupling defense — must appear BEFORE any lib.* import.
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")

from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INPUT_BODY_WITH_URLS = (
    "## Introduction\n\n"
    "Some content here.\n\n"
    "![图片](http://localhost:8765/abc123/0.jpg)\n\n"
    "More content.\n\n"
    "Image 1 from article 'My Article': http://localhost:8765/abc123/0.jpg\n\n"
    "关注公众号请扫码\n\n"
    "点赞在看\n"
)

_OUTPUT_BODY_CLEAN = (
    "## Introduction\n\n"
    "Some content here.\n\n"
    "![图片](http://localhost:8765/abc123/0.jpg)\n\n"
    "More content.\n\n"
    "Image 1 from article 'My Article': http://localhost:8765/abc123/0.jpg\n"
)


# ---------------------------------------------------------------------------
# RW-VALVE-PASS
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rw_valve_pass():
    """Identical URL sets -> valve accepts; cleaned string is returned."""
    with patch(
        "lib.llm_deepseek.deepseek_model_complete",
        new=AsyncMock(return_value=_OUTPUT_BODY_CLEAN),
    ), patch(
        "lib.translate.detect_source_lang",
        return_value="zh",
    ):
        from lib.rewrite import rewrite_body_with_deepseek
        result = await rewrite_body_with_deepseek("My Article", _INPUT_BODY_WITH_URLS)

    assert result is not None
    assert result.strip() == _OUTPUT_BODY_CLEAN.strip()


# ---------------------------------------------------------------------------
# RW-VALVE-REJECT-DROP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rw_valve_reject_drop():
    """Output missing one localhost:8765 URL -> valve returns None."""
    output_with_dropped_url = (
        "## Introduction\n\n"
        "Some content here.\n\n"
        # URL dropped — not present
        "More content.\n"
    )
    with patch(
        "lib.llm_deepseek.deepseek_model_complete",
        new=AsyncMock(return_value=output_with_dropped_url),
    ), patch(
        "lib.translate.detect_source_lang",
        return_value="zh",
    ):
        from lib.rewrite import rewrite_body_with_deepseek
        result = await rewrite_body_with_deepseek("My Article", _INPUT_BODY_WITH_URLS)

    assert result is None


# ---------------------------------------------------------------------------
# RW-VALVE-REJECT-ADD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rw_valve_reject_add():
    """Output has an extra/hallucinated localhost:8765 URL -> valve returns None."""
    output_with_extra_url = (
        "## Introduction\n\n"
        "Some content here.\n\n"
        "![图片](http://localhost:8765/abc123/0.jpg)\n\n"
        "More content.\n\n"
        "Image 1 from article 'My Article': http://localhost:8765/abc123/0.jpg\n\n"
        # Hallucinated extra URL:
        "![图片](http://localhost:8765/hallucinated/99.jpg)\n"
    )
    with patch(
        "lib.llm_deepseek.deepseek_model_complete",
        new=AsyncMock(return_value=output_with_extra_url),
    ), patch(
        "lib.translate.detect_source_lang",
        return_value="zh",
    ):
        from lib.rewrite import rewrite_body_with_deepseek
        result = await rewrite_body_with_deepseek("My Article", _INPUT_BODY_WITH_URLS)

    assert result is None


# ---------------------------------------------------------------------------
# RW-VALVE-REJECT-MUTATE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rw_valve_reject_mutate():
    """Output has a mutated URL (shortened path) -> valve returns None."""
    output_with_mutated_url = (
        "## Introduction\n\n"
        "Some content here.\n\n"
        # URL shortened — abc123/0.jpg -> 0.jpg
        "![图片](http://localhost:8765/0.jpg)\n\n"
        "More content.\n\n"
        "Image 1 from article 'My Article': http://localhost:8765/0.jpg\n"
    )
    with patch(
        "lib.llm_deepseek.deepseek_model_complete",
        new=AsyncMock(return_value=output_with_mutated_url),
    ), patch(
        "lib.translate.detect_source_lang",
        return_value="zh",
    ):
        from lib.rewrite import rewrite_body_with_deepseek
        result = await rewrite_body_with_deepseek("My Article", _INPUT_BODY_WITH_URLS)

    assert result is None


# ---------------------------------------------------------------------------
# RW-EMPTY
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rw_empty():
    """LLM returns empty/whitespace -> function returns None (no crash)."""
    for empty_response in ("", "   ", "\n\n"):
        with patch(
            "lib.llm_deepseek.deepseek_model_complete",
            new=AsyncMock(return_value=empty_response),
        ), patch(
            "lib.translate.detect_source_lang",
            return_value="zh",
        ):
            from lib.rewrite import rewrite_body_with_deepseek
            result = await rewrite_body_with_deepseek("Title", "Some body text")
        assert result is None, f"expected None for empty response {repr(empty_response)}"


# ---------------------------------------------------------------------------
# RW-PROMPT-CONSTANTS
# ---------------------------------------------------------------------------

def test_rw_prompt_constants():
    """The rewrite prompt contains the image-URL constraint AND boilerplate markers."""
    from lib.rewrite import _build_rewrite_prompt

    prompt = _build_rewrite_prompt("Test Title", "Some body.", "zh")

    # Image URL verbatim constraint must be present
    assert "http://localhost:8765/" in prompt, "prompt missing image URL verbatim constraint"

    # Boilerplate marker checklist (from CONTEXT.md success gate)
    for marker in ("关注公众号", "点赞", "扫码"):
        assert marker in prompt, f"prompt missing boilerplate marker: {marker}"


# ---------------------------------------------------------------------------
# RW-LAZY-IMPORT (Pitfall 2)
# ---------------------------------------------------------------------------

def test_rw_lazy_import(monkeypatch):
    """import lib.rewrite succeeds with DEEPSEEK_API_KEY unset — no RuntimeError.

    Verifies that lib.rewrite does NOT import lib.translate or lib.llm_deepseek
    at module top (which would trigger the DEEPSEEK_API_KEY check from lib/__init__.py).
    """
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    # Force a fresh import by removing cached module from sys.modules
    import sys
    for mod_name in list(sys.modules.keys()):
        if mod_name in ("lib.rewrite",):
            del sys.modules[mod_name]

    # This must NOT raise RuntimeError("DEEPSEEK_API_KEY is not set")
    try:
        import lib.rewrite  # noqa: F401
    except RuntimeError as exc:
        pytest.fail(
            f"import lib.rewrite raised RuntimeError with DEEPSEEK_API_KEY unset: {exc}"
        )
    finally:
        # Restore for other tests
        os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")
