"""Unit tests for batch_ingest_from_spider._build_topic_filter_query.

Day-1 cron blocker fix (2026-05-03 sd7): DeepSeek classifier writes
capitalized topics (Agent / LLM / RAG / NLP / CV); cron passes lowercase
tokens. SQL must be case-insensitive on both sides.

Fix 3 (2026-05-04 vm9): LIKE substring matching replaces exact IN so
compound classifier topics like 'Harness Engineering' match filter
keywords like 'harness'.
"""
import pytest
from batch_ingest_from_spider import _build_topic_filter_query


def test_sql_uses_lower_like_substring():
    """LIKE substring matching with LOWER() on column side."""
    sql, _ = _build_topic_filter_query(["agent", "hermes"])
    assert "LOWER(c.topic) LIKE ?" in sql
    assert "LOWER(c.topic) IN (" not in sql  # old form removed


def test_like_params_have_percent_wrapping():
    """Params wrapped with % for LIKE substring match."""
    _, params = _build_topic_filter_query(["Agent", " LLM ", "openClaw", "  HERMES"])
    assert params == ("%agent%", "%llm%", "%openclaw%", "%hermes%")


def test_case_equivalence():
    """Different case inputs produce identical (sql, params)."""
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


def test_latest_classification_subquery_present():
    """Fix 1: only join latest classification per article."""
    sql, _ = _build_topic_filter_query(["agent"])
    assert "MAX(classified_at)" in sql
    assert "c.classified_at = (" in sql


@pytest.mark.parametrize("n", [1, 3, 5])
def test_like_placeholder_count_matches_topics_count(n):
    """Count of LIKE ? clauses matches input topic count."""
    topics = ["t" + str(i) for i in range(n)]
    sql, params = _build_topic_filter_query(topics)
    assert len(params) == n
    # Count LIKE ? occurrences after LOWER(c.topic)
    assert sql.count("LOWER(c.topic) LIKE ?") == n


def test_return_types():
    sql, params = _build_topic_filter_query(["agent"])
    assert isinstance(sql, str)
    assert isinstance(params, tuple)
    assert all(isinstance(p, str) for p in params)


def test_single_topic_single_like():
    """One topic → one LIKE clause, no OR chaining."""
    sql, params = _build_topic_filter_query(["agent"])
    assert "LIKE ?" in sql
    assert "LIKE ? OR" not in sql
    assert params == ("%agent%",)


def test_multi_topic_or_chaining():
    """Multiple topics → OR-chained LIKE clauses."""
    sql, _ = _build_topic_filter_query(["agent", "harness", "openclaw"])
    assert sql.count("LOWER(c.topic) LIKE ?") == 3
    assert " OR " in sql
