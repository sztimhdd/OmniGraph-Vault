"""Unit tests for ``batch_ingest_from_spider._build_topic_filter_query``.

History:
    Day-1 cron blocker fix (2026-05-03 sd7): DeepSeek classifier writes
    capitalized topics; cron passes lowercase tokens; SQL had to be
    case-insensitive. Quick 260504-vm9 added LIKE substring matching.

    v3.5 Ingest Refactor (Quick 260507-lai, V35-FOUND-03): the
    ``classifications`` JOIN, the LIKE/topic predicates, and the
    case-insensitive normalisation are ALL removed. Candidate filtering
    moved out of SQL and into ``lib.article_filter`` (Layer 1 pre-scrape +
    Layer 2 post-scrape placeholders). The function now returns a SQL
    statement that selects every non-ingested article in FIFO order, with
    no topic predicate at all. The ``topics`` argument is silently
    accepted for API compat but no longer affects the query.

These tests pin the v3.5 contract:
    - SQL selects (a.id, a.title, a.url, acc.name, a.body, a.digest)
    - SQL JOINs accounts but does NOT JOIN classifications
    - SQL anti-joins ingestions WHERE status='ok'
    - SQL has ORDER BY a.id (FIFO)
    - params is always ()
    - the function accepts any iterable of strings without raising
"""
import pytest

from batch_ingest_from_spider import _build_topic_filter_query


def test_sql_selects_v35_columns():
    """Returned column list matches the v3.5 row tuple shape."""
    sql, _ = _build_topic_filter_query(["agent"])
    assert "a.id" in sql
    assert "a.title" in sql
    assert "a.url" in sql
    assert "acc.name" in sql
    assert "a.body" in sql
    assert "a.digest" in sql


def test_sql_does_not_join_classifications():
    """v3.5: classifications JOIN removed — Layer 1/2 replace it."""
    sql, _ = _build_topic_filter_query(["agent"])
    assert "classifications" not in sql.lower()
    assert "c.depth_score" not in sql
    assert "c.topic" not in sql


def test_sql_does_not_use_like_predicate():
    """v3.5: no LIKE topic-substring matching in SQL."""
    sql, _ = _build_topic_filter_query(["agent", "hermes"])
    assert "LIKE" not in sql.upper()


def test_sql_joins_accounts():
    """Accounts JOIN preserved so account name is in the row tuple."""
    sql, _ = _build_topic_filter_query(["agent"])
    assert "JOIN accounts acc" in sql
    assert "a.account_id = acc.id" in sql


def test_sql_anti_joins_ingestions():
    """Anti-join against ingestions WHERE status='ok' so already-ingested
    articles are not retried."""
    sql, _ = _build_topic_filter_query(["agent"])
    assert "ingestions" in sql
    assert "status = 'ok'" in sql
    assert "NOT IN" in sql.upper()


def test_sql_orders_by_a_id():
    """FIFO ingest order preserved."""
    sql, _ = _build_topic_filter_query(["agent"])
    assert "ORDER BY a.id" in sql


@pytest.mark.parametrize("topics", [["agent"], ["agent", "hermes"], []])
def test_params_always_empty(topics):
    """v3.5: params is always () regardless of topics — topics arg is
    silently accepted for API compat but does not affect the SQL."""
    _, params = _build_topic_filter_query(topics)
    assert params == ()


def test_topics_arg_accepted_silently():
    """The function accepts arbitrary topic lists without raising."""
    sql_a, params_a = _build_topic_filter_query(["agent"])
    sql_b, params_b = _build_topic_filter_query(["completely", "different", "list"])
    # SQL is identical regardless of topics — they're silently ignored.
    assert sql_a == sql_b
    assert params_a == params_b == ()


def test_return_types():
    sql, params = _build_topic_filter_query(["agent"])
    assert isinstance(sql, str)
    assert isinstance(params, tuple)
