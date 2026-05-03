"""Unit tests for batch_ingest_from_spider._build_topic_filter_query.

Day-1 cron blocker fix (2026-05-03 sd7): DeepSeek classifier writes
capitalized topics (Agent / LLM / RAG / NLP / CV); cron passes lowercase
tokens. SQL must be case-insensitive on both sides.
"""
import pytest
from batch_ingest_from_spider import _build_topic_filter_query


def test_sql_uses_lower_on_topic_column():
    sql, _ = _build_topic_filter_query(["agent", "hermes"])
    assert "LOWER(c.topic) IN (" in sql


def test_params_are_stripped_and_lowercased():
    _, params = _build_topic_filter_query(["Agent", " LLM ", "openClaw", "  HERMES"])
    assert params == ("agent", "llm", "openclaw", "hermes")


def test_case_equivalence():
    sql_a, params_a = _build_topic_filter_query(["Agent", "LLM", "openclaw"])
    sql_b, params_b = _build_topic_filter_query(["agent", "llm", "OPENCLAW"])
    assert sql_a == sql_b
    assert params_a == params_b


def test_null_branch_preserved():
    sql, _ = _build_topic_filter_query(["agent"])
    assert "c.topic IS NULL OR " in sql


def test_order_by_a_id_preserved():
    sql, _ = _build_topic_filter_query(["agent"])
    assert "ORDER BY a.id" in sql


@pytest.mark.parametrize("n", [1, 3, 5])
def test_placeholder_count_matches_topics_count(n):
    topics = ["t" + str(i) for i in range(n)]
    sql, params = _build_topic_filter_query(topics)
    assert len(params) == n
    # Count ? placeholders inside the LOWER(c.topic) IN (...) group
    head = sql.split("LOWER(c.topic) IN (", 1)[1]
    in_group = head.split(")", 1)[0]
    assert in_group.count("?") == n


def test_return_types():
    sql, params = _build_topic_filter_query(["agent"])
    assert isinstance(sql, str)
    assert isinstance(params, tuple)
    assert all(isinstance(p, str) for p in params)
