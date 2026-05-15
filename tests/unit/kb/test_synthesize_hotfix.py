"""Unit tests for the 4 helpers added in the 260515-cvh hotfix.

Covers: _ENTITY_HINTS / _dedupe / _fallback_search_terms / _entity_candidates.

No monkeypatching required — all 4 helpers are pure functions (no DB, no LLM,
no filesystem). _source_hashes_from_fts is NOT tested here because it requires
a live FTS DB; it is covered indirectly by the integration suite.
"""
from __future__ import annotations

from kb.services.synthesize import (
    _ENTITY_HINTS,
    _dedupe,
    _entity_candidates,
    _fallback_search_terms,
)


# ---------------------------------------------------------------------------
# _ENTITY_HINTS (1 test)
# ---------------------------------------------------------------------------


def test_entity_hints_is_immutable_tuple_with_min_length():
    """_ENTITY_HINTS must be an immutable tuple with >=8 entries."""
    assert isinstance(_ENTITY_HINTS, tuple), "_ENTITY_HINTS must be a tuple"
    assert len(_ENTITY_HINTS) >= 8, (
        f"_ENTITY_HINTS has only {len(_ENTITY_HINTS)} items; expected >=8"
    )


# ---------------------------------------------------------------------------
# _dedupe (2 tests)
# ---------------------------------------------------------------------------


def test_dedupe_case_insensitive():
    """_dedupe treats 'Agent' and 'agent' as the same key; keeps first occurrence."""
    result = _dedupe(["Agent", "agent", "AGENT"])
    assert result == ["Agent"], f"Expected ['Agent'], got {result}"


def test_dedupe_preserves_order_and_handles_empty():
    """_dedupe preserves insertion order and handles empty list."""
    assert _dedupe([]) == []
    assert _dedupe(["RAG", "MCP", "RAG", "Claude"]) == ["RAG", "MCP", "Claude"]


# ---------------------------------------------------------------------------
# _fallback_search_terms (2 tests)
# ---------------------------------------------------------------------------


def test_fallback_search_terms_includes_question():
    """First term is always the question itself (for precise FTS match)."""
    terms = _fallback_search_terms("What is LangChain?")
    assert terms[0] == "What is LangChain?", f"First term must be the question, got {terms}"


def test_fallback_search_terms_edge_cases_and_ai_agent():
    """Empty/None question returns []; 'AI Agent' compound added when both words present."""
    assert _fallback_search_terms("") == []
    assert _fallback_search_terms("   ") == []
    assert _fallback_search_terms(None) == []
    terms = _fallback_search_terms("Tell me about AI Agent frameworks")
    assert "AI Agent" in terms, f"Expected 'AI Agent' in terms, got {terms}"


# ---------------------------------------------------------------------------
# _entity_candidates (2 tests)
# ---------------------------------------------------------------------------


def test_entity_candidates_matches_question_and_markdown():
    """Entities pulled from both question and markdown haystacks."""
    result_q = _entity_candidates("What is LightRAG?", "")
    assert "LightRAG" in result_q

    result_md = _entity_candidates("", "DeepSeek model performance compared to Claude")
    assert "DeepSeek" in result_md
    assert "Claude" in result_md


def test_entity_candidates_capped_at_8():
    """Result is capped at 8 items even if many hints match."""
    long_question = " ".join(_ENTITY_HINTS)
    result = _entity_candidates(long_question, long_question)
    assert len(result) <= 8, f"Expected <=8 entities, got {len(result)}"
