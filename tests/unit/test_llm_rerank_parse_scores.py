"""v1.1.P2-3-perf-fix-A SC#4 unit: _parse_scores pure-function contract.

Verifies the JSON parse-fail / partial-scores / valid-output ladder
WITHOUT Databricks-SDK dependency (T5 plan-checker rec #1: extract
contract verification from integration test that requires real HTTP).
"""
from __future__ import annotations

import os
import sys

import pytest

_DD = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                   "databricks-deploy"))
if _DD not in sys.path:
    sys.path.insert(0, _DD)


@pytest.fixture
def parse():
    import lightrag_databricks_rerank as ldr
    return ldr._parse_scores


@pytest.mark.unit
def test_parse_scores_garbage_returns_none(parse) -> None:
    assert parse("definitely not json", n_docs=3) is None


@pytest.mark.unit
def test_parse_scores_empty_object_returns_none(parse) -> None:
    assert parse("{}", n_docs=3) is None


@pytest.mark.unit
def test_parse_scores_partial_below_threshold_returns_none(parse) -> None:
    raw = '{"scores": [{"i": 0, "s": 0.9}, {"i": 1, "s": 0.7}]}'
    assert parse(raw, n_docs=10) is None


@pytest.mark.unit
def test_parse_scores_partial_above_threshold_returns_sorted(parse) -> None:
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
    raw = '```json\n{"scores": [{"i": 0, "s": 0.5}, {"i": 1, "s": 0.5}]}\n```'
    result = parse(raw, n_docs=2)
    assert result is not None
    assert len(result) == 2
