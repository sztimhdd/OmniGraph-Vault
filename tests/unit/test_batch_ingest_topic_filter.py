"""Unit tests for ``batch_ingest_from_spider`` topic-filter handling.

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

    v3.5 foundation follow-up (Quick 260507-lai patch, this file's last
    two tests): when Hermes ran the cleaned-up cron command per
    HERMES-DEPLOY.md Step 2 (``--topic-filter`` removed), main() still
    rejected the invocation at lines 1645-1648 with
    "--topic-filter is required with --from-db". The runtime check was
    obsolete after V35-FOUND-03 (topics no longer affect the SELECT).
    The fix deletes the check and coalesces ``topic_keywords`` to ``[]``
    at the call site, matching the v3.5 canonical "no filter" representation.
    Lesson #6 (production-shape simulation) recurrence: the f1a963b smoke
    used ``--topic-filter agent --dry-run`` and never exercised the
    no-flag path; these regression tests pin the production-shape route.

These tests pin the v3.5 contract:
    - SQL selects (a.id, a.title, a.url, acc.name, a.body, a.digest)
    - SQL JOINs accounts but does NOT JOIN classifications
    - SQL anti-joins ingestions WHERE status='ok'
    - SQL has ORDER BY a.id (FIFO)
    - params is always ()
    - the function accepts any iterable of strings without raising
    - ``main()`` does NOT sys.exit(1) when ``--from-db`` is given without
      ``--topic-filter`` (path a) or with a normalising-to-None filter
      (path b: empty / comma-only)
"""
import sys

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


# ---------------------------------------------------------------------------
# main() runtime-check regression — Quick 260507-lai patch
#
# These two tests pin the production-shape Hermes invocation path that the
# original f1a963b smoke missed (it used --topic-filter agent --dry-run, which
# kept topic_keywords non-None and never reached the runtime check). The
# Hermes deploy smoke (HERMES-DEPLOY.md Step 4) runs without --topic-filter
# per Step 2's cleaned-up cron command — both paths must now flow into
# ingest_from_db with an empty list, not sys.exit(1).
# ---------------------------------------------------------------------------


def _run_main_capture_topics(monkeypatch, argv_extra: list[str]) -> list[str] | None:
    """Drive ``batch_ingest_from_spider.main()`` with mocked downstream.

    Captures the first positional argument passed to ``ingest_from_db``
    (the topic_keywords value as it lands inside the called coroutine).

    Returns whatever was captured. The test asserts on this value.
    Raises ``SystemExit`` if main() rejects the invocation, which is the
    pre-fix behaviour that this regression catches.
    """
    import batch_ingest_from_spider as bi

    captured: dict[str, object] = {}

    async def fake_ingest_from_db(topic, *args, **kwargs):  # noqa: ANN001
        captured["topic"] = topic

    monkeypatch.setattr(bi, "ingest_from_db", fake_ingest_from_db)
    monkeypatch.setattr(
        sys, "argv",
        ["batch_ingest_from_spider.py", "--from-db", "--dry-run", "--max-articles", "1"]
        + argv_extra,
    )

    bi.main()  # must not raise SystemExit(1)

    return captured.get("topic")  # type: ignore[return-value]


def test_main_no_topic_filter_does_not_sys_exit(monkeypatch):
    """Path a: argparse without --topic-filter → topic_keywords is None.

    Hermes cron command per HERMES-DEPLOY.md Step 2 omits --topic-filter
    entirely. main() must NOT sys.exit(1); it must call ingest_from_db
    with an empty list (the v3.5 canonical "no filter" representation).
    """
    captured = _run_main_capture_topics(monkeypatch, argv_extra=[])
    assert captured == [], (
        f"ingest_from_db must receive [] when --topic-filter is absent "
        f"(got {captured!r}); pre-fix main() raised SystemExit(1) here"
    )


@pytest.mark.parametrize("topic_filter_arg", ["", ","])
def test_main_normalised_to_none_topic_filter_does_not_sys_exit(
    monkeypatch, topic_filter_arg
):
    """Path b: --topic-filter "" or "," → strip+filter normalises to None.

    argparse's split-and-strip pipeline at lines 1640-1643 turns these
    inputs into topic_keywords=None, the same effective state as path a.
    Both must flow through to ingest_from_db with [] post-fix.
    """
    captured = _run_main_capture_topics(
        monkeypatch, argv_extra=["--topic-filter", topic_filter_arg]
    )
    assert captured == [], (
        f"--topic-filter {topic_filter_arg!r} normalises to None and must "
        f"reach ingest_from_db as [] (got {captured!r}); pre-fix main() "
        f"raised SystemExit(1) here"
    )
