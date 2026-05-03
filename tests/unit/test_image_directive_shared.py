"""Unit tests for HYG-04 IMAGE_URL_DIRECTIVE constant (Phase 18-03).

Asserts the directive is defined as a module-level constant and is
referenced by name inside ``synthesize_response`` — not duplicated as
a magic string.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import kg_synthesize


def test_image_url_directive_constant_is_defined_and_non_empty():
    directive = kg_synthesize.IMAGE_URL_DIRECTIVE
    assert isinstance(directive, str)
    assert len(directive) > 50
    assert "![description](url)" in directive
    assert "http://localhost:8765/" in directive


def test_directive_is_referenced_by_name_in_synthesize_response():
    """White-box check: synthesize_response must reference the constant by name,
    not duplicate the directive text. Protects against future drift."""
    source = inspect.getsource(kg_synthesize.synthesize_response)
    assert "IMAGE_URL_DIRECTIVE" in source


def test_directive_text_appears_exactly_once_in_source():
    """The distinctive directive opening should appear exactly once in the
    source (in the constant definition)."""
    source_path = Path(kg_synthesize.__file__)
    source = source_path.read_text(encoding="utf-8")
    # The opening phrase is distinctive enough that duplicating it would
    # appear as 2+ matches.
    marker = "CRITICAL: when the context below contains image URLs"
    count = source.count(marker)
    assert count == 1, f"Expected exactly 1 occurrence of directive marker, got {count}"


def test_skill_md_cross_references_directive():
    """omnigraph_query SKILL.md must explain where image URLs come from."""
    skill_md = Path(kg_synthesize.__file__).resolve().parent / "skills" / "omnigraph_query" / "SKILL.md"
    assert skill_md.exists()
    text = skill_md.read_text(encoding="utf-8")
    assert "IMAGE_URL_DIRECTIVE" in text
    assert "How image URLs reach the synthesis output" in text
