"""Unit tests for `kg_synthesize._archive_filename`.

Regression target: prior to this fix, every synthesis run overwrote
`synthesis_output.md`, losing earlier answers. The helper now generates
a unique filename per query so every answer is preserved.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from kg_synthesize import _archive_filename


_FIXED_TS = datetime(2026, 5, 6, 15, 45, 23)


def test_filename_has_timestamp_prefix():
    """Filename always starts with YYYY-MM-DD_HHMMSS stamp."""
    name = _archive_filename("hello world", ts=_FIXED_TS)
    assert name.startswith("2026-05-06_154523_")
    assert name.endswith(".md")


def test_filename_handles_ascii_query():
    """Plain ASCII query produces readable slug."""
    assert _archive_filename("hello world", ts=_FIXED_TS) == "2026-05-06_154523_hello-world.md"


def test_filename_collapses_special_chars():
    """Punctuation/whitespace collapse into single hyphens, no dups."""
    assert _archive_filename("foo??!! bar  baz", ts=_FIXED_TS) == "2026-05-06_154523_foo-bar-baz.md"


def test_filename_preserves_cjk():
    """Chinese characters stay (UTF-8 filename safe on Linux + Windows 10+)."""
    name = _archive_filename("把Claude Code塞进微信", ts=_FIXED_TS)
    assert "把Claude-Code塞进微信" in name
    assert name.endswith(".md")


def test_filename_truncates_long_query():
    """Slug capped at 40 chars to prevent unmanageable filenames."""
    long_q = "a" * 200
    name = _archive_filename(long_q, ts=_FIXED_TS)
    # name = stamp(17) + _ + slug(<=40) + .md(3) = at most 61
    slug_part = name[len("2026-05-06_154523_"):-len(".md")]
    assert len(slug_part) <= 40


def test_filename_falls_back_to_untitled_on_empty():
    """Empty / whitespace-only query gets ``untitled`` slug, never an empty filename."""
    assert _archive_filename("", ts=_FIXED_TS) == "2026-05-06_154523_untitled.md"
    assert _archive_filename("   ", ts=_FIXED_TS) == "2026-05-06_154523_untitled.md"
    assert _archive_filename("???", ts=_FIXED_TS) == "2026-05-06_154523_untitled.md"


def test_filename_strips_leading_trailing_hyphens():
    """Leading/trailing hyphens from punctuation are removed before truncation."""
    assert _archive_filename("--hello--", ts=_FIXED_TS) == "2026-05-06_154523_hello.md"


def test_filename_default_timestamp_when_omitted():
    """Without explicit ts, helper uses datetime.now() — name is non-empty + parses."""
    name = _archive_filename("test")
    assert name.endswith("_test.md")
    # Format check: 4+1+2+1+2+1+6 = 17 char prefix before "_test"
    prefix = name[: -len("_test.md")]
    assert len(prefix) == 17
    # Year/date sanity: starts with 20 (works through 2099)
    assert prefix.startswith("20")
