"""v1.1.P2-3-perf-fix-B SC#4 unit: lib.vertex_gemini_rerank._parse_scores contract.

Mirrors tests/unit/test_llm_rerank_parse_scores.py (A's helper) exactly —
same 6 tests, only the import target differs. Verifies the JSON parse-
fail / partial-scores / valid-output ladder WITHOUT Vertex SDK
network dependency. Pure-function, deterministic in CI.

The two _parse_scores functions are byte-equivalent (option a — duplicate
per CONTEXT.md decision); these tests provide a regression net against
drift between the two copies.

NB: no SDK-skip guard is needed here. T1's lazy-import discipline
guarantees ``from lib.vertex_gemini_rerank import _parse_scores``
succeeds even when google.genai is absent — google.genai is imported
INSIDE ``_make_client()`` and ``make_rerank_func()``, not at module top.
_parse_scores is pure stdlib (json + str).
"""
from __future__ import annotations

import pytest


@pytest.fixture
def parse():
    from lib.vertex_gemini_rerank import _parse_scores
    return _parse_scores


@pytest.mark.unit
def test_parse_scores_garbage_returns_none(parse) -> None:
    assert parse("definitely not json", n_docs=3) is None


@pytest.mark.unit
def test_parse_scores_empty_object_returns_none(parse) -> None:
    assert parse("{}", n_docs=3) is None


@pytest.mark.unit
def test_parse_scores_partial_below_threshold_returns_none(parse) -> None:
    # n_docs=10, only 2 scored (20% < 50% threshold) → None to trigger retry
    raw = '{"scores": [{"i": 0, "s": 0.9}, {"i": 1, "s": 0.7}]}'
    assert parse(raw, n_docs=10) is None


@pytest.mark.unit
def test_parse_scores_partial_above_threshold_returns_sorted(parse) -> None:
    # n_docs=4, 3 scored (75% ≥ 50%) → accept + sort
    raw = '{"scores": [{"i": 0, "s": 0.3}, {"i": 1, "s": 0.9}, {"i": 2, "s": 0.6}]}'
    result = parse(raw, n_docs=4)
    assert result is not None
    assert [r["index"] for r in result] == [1, 2, 0]
    assert result[0]["relevance_score"] == pytest.approx(0.9)


@pytest.mark.unit
def test_parse_scores_full_returns_descending(parse) -> None:
    raw = '{"scores": [{"i": 0, "s": 0.1}, {"i": 1, "s": 0.5}, {"i": 2, "s": 0.9}]}'
    result = parse(raw, n_docs=3)
    assert result is not None
    assert [r["index"] for r in result] == [2, 1, 0]


@pytest.mark.unit
def test_parse_scores_markdown_fence_stripped(parse) -> None:
    # Vertex Gemini's response_schema=JSON enforcement should prevent
    # markdown fences, but the parse ladder must still recover defensively
    # in case schema enforcement falls back (unlikely but cheap to defend).
    raw = '```json\n{"scores": [{"i": 0, "s": 0.5}, {"i": 1, "s": 0.5}]}\n```'
    result = parse(raw, n_docs=2)
    assert result is not None
    assert len(result) == 2
