"""Unit tests for ``batch_ingest_from_spider`` topic-filter / dual-source SQL.

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

    v3.5 ir-1 (Quick — Real Layer 1 + KOL ingest wiring): the candidate SQL
    gains a Layer 1 verdict predicate
    ``(a.layer1_verdict IS NULL OR a.layer1_prompt_version IS NOT ?)``
    bound to ``lib.article_filter.PROMPT_VERSION_LAYER1``. params is now
    a 1-tuple, not (). topics arg remains silently accepted.

    v3.5 ir-4 (LF-4.4): dual-source UNION ALL combining ``articles``
    (KOL/WeChat) and ``rss_articles`` (RSS feeds). Returns 7 columns:
    (id, source, title, url, source_name, body, summary). Anti-joins are
    source-aware so KOL id=42 and RSS id=42 do NOT cross-exclude each
    other. ORDER BY ``source DESC, id`` (KOL first, then RSS, FIFO within
    each source). params is a 2-tuple — one PROMPT_VERSION_LAYER1
    binding per UNION branch.

    Quick 260509-s29 Wave 2 (skip_reason_version cohort gate): the anti-
    join predicate gains a reject-cohort clause —
    ``status='skipped' AND skip_reason_version = ?`` — so permanently
    dead URLs stay excluded but a taxonomy bump puts older skipped rows
    back in the candidate pool. params expands from 2-tuple to 4-tuple,
    binding (SKIP_REASON_VERSION_CURRENT, PROMPT_VERSION_LAYER1) per
    UNION branch in that order.

These tests pin the post-Wave-2 contract:
    - SQL is a UNION ALL of two SELECTs (articles + rss_articles)
    - Output columns are (id, source, title, url, source_name, body, summary)
    - KOL UNION branch: JOIN accounts, anti-joins ``ingestions WHERE
      source='wechat' AND (status='ok' OR (status='skipped' AND
      skip_reason_version=?))``, layer1 predicate on ``a.*``
    - RSS UNION branch: JOIN rss_feeds, anti-joins ``ingestions WHERE
      source='rss' AND (status='ok' OR (status='skipped' AND
      skip_reason_version=?))``, layer1 predicate on ``r.*``
    - source column is the literal 'wechat' / 'rss'
    - KOL aliases ``a.digest`` to ``summary``; RSS uses ``r.summary`` directly
    - ORDER BY ``source DESC, id`` (KOL first then RSS, FIFO within each)
    - params is (SKIP_REASON_VERSION_CURRENT, PROMPT_VERSION_LAYER1,
      SKIP_REASON_VERSION_CURRENT, PROMPT_VERSION_LAYER1) — 4-tuple
    - the function accepts any iterable of strings without raising
    - no LIKE / classifications JOIN remain
    - ``main()`` does NOT sys.exit(1) when ``--from-db`` is given without
      ``--topic-filter`` (path a) or with a normalising-to-None filter
      (path b: empty / comma-only)
"""
import sys

import pytest

from batch_ingest_from_spider import _build_topic_filter_query


# ---------------------------------------------------------------------------
# Source-aware UNION structure (v3.5 ir-4)
# ---------------------------------------------------------------------------


def test_sql_unions_both_tables():
    """Dual-source: SQL must include UNION ALL combining articles + rss_articles."""
    sql, _ = _build_topic_filter_query([])
    upper = sql.upper()
    assert "UNION ALL" in upper, "ir-4 dual-source requires UNION ALL"
    assert "FROM ARTICLES" in upper or "FROM articles" in sql.lower().upper().replace(
        "ARTICLES", "ARTICLES"
    )  # tolerant of casing
    assert "FROM articles" in sql, "KOL branch must SELECT FROM articles"
    assert "FROM rss_articles" in sql, "RSS branch must SELECT FROM rss_articles"


def test_sql_kol_branch_selects_seven_named_columns():
    """KOL UNION branch returns: id, source='wechat', title, url, source_name (acc.name), body, summary (digest aliased)."""
    sql, _ = _build_topic_filter_query([])
    assert "a.id" in sql
    assert "'wechat'" in sql
    assert "a.title" in sql
    assert "a.url" in sql
    assert "acc.name" in sql
    assert "a.body" in sql
    assert "a.digest" in sql
    # KOL aliases digest to summary so UNION column count matches RSS.
    assert "a.digest AS summary" in sql, "KOL must alias digest to summary"


def test_sql_rss_branch_selects_seven_named_columns():
    """RSS UNION branch returns: id, source='rss', title, url, source_name (f.name), body, summary."""
    sql, _ = _build_topic_filter_query([])
    assert "r.id" in sql
    assert "'rss'" in sql
    assert "r.title" in sql
    assert "r.url" in sql
    assert "r.body" in sql
    assert "r.summary" in sql
    assert "f.name" in sql
    assert "rss_feeds f" in sql, "RSS must JOIN rss_feeds (alias f)"


def test_sql_returns_seven_top_level_column_names():
    """The first SELECT (KOL) defines the UNION ALL column names. Verify
    the alias chain produces exactly 7 named columns: id, source, title,
    url, source_name, body, summary."""
    sql, _ = _build_topic_filter_query([])
    # Each AS clause appears in the KOL branch (alias targets):
    for alias in (
        "AS id",
        "AS source",
        "AS title",
        "AS url",
        "AS source_name",
        "AS body",
        "AS summary",
    ):
        assert alias in sql, (
            f"KOL UNION branch must explicitly alias to {alias!r} so the "
            f"output column ordering / naming is unambiguous"
        )


def test_sql_anti_join_source_aware():
    """Each UNION branch's anti-join must be scoped by source. Without
    source-awareness, KOL id=42 and RSS id=42 would cross-exclude each
    other through the shared ingestions table.

    Wave 2 contract:
      KOL: NOT IN (SELECT article_id FROM ingestions WHERE source='wechat'
              AND (status='ok' OR (status='skipped' AND skip_reason_version=?)))
      RSS: NOT IN (SELECT article_id FROM ingestions WHERE source='rss'
              AND (status='ok' OR (status='skipped' AND skip_reason_version=?)))
    """
    sql, _ = _build_topic_filter_query([])
    # The source-scope predicates must still be present on each branch.
    assert "source = 'wechat'" in sql, (
        "KOL anti-join must scope by source='wechat'"
    )
    assert "source = 'rss'" in sql, (
        "RSS anti-join must scope by source='rss'"
    )
    # Wave 2: the anti-join now has a compound predicate. status='ok' is
    # unconditional; status='skipped' is gated by skip_reason_version.
    assert sql.count("status = 'ok'") == 2, (
        "Both branches must keep status='ok' as an unconditional exclusion"
    )
    assert sql.count("status = 'skipped'") == 2, (
        "Both branches must guard status='skipped' by skip_reason_version"
    )
    assert sql.count("skip_reason_version = ?") == 2, (
        "Both branches must bind skip_reason_version = ? in their anti-join"
    )


def test_sql_kol_joins_accounts_for_source_name():
    """KOL branch JOINs accounts so source_name = acc.name."""
    sql, _ = _build_topic_filter_query([])
    assert "JOIN accounts acc" in sql
    assert "a.account_id = acc.id" in sql


def test_sql_rss_joins_rss_feeds_for_source_name():
    """RSS branch JOINs rss_feeds (NOT 'feeds' — table is named rss_feeds in
    the actual schema, see W0 audit). Source name comes from f.name."""
    sql, _ = _build_topic_filter_query([])
    assert "JOIN rss_feeds f" in sql
    assert "r.feed_id = f.id" in sql


def test_sql_orders_by_source_desc_then_id():
    """ir-4 FIFO replacement: 'wechat' DESC > 'rss' so KOL rows come
    first, then RSS rows, FIFO within each source group.

    Pure ORDER BY a.id from ir-1 era is not expressible across UNION ALL
    (UNION strips table prefixes); the alias approach uses the output
    column ``source`` and ``id``."""
    sql, _ = _build_topic_filter_query([])
    assert "ORDER BY source DESC, id" in sql


def test_sql_layer1_predicate_present_on_both_branches():
    """Each UNION branch must carry the layer1 verdict + prompt_version
    re-evaluation predicate. KOL uses ``a.layer1_*``; RSS uses ``r.layer1_*``.

    Bucket 'candidate' is also explicitly accepted on both branches so
    cron runs after Layer 1 stamps verdicts can resume per-article ingest
    (2026-05-08 fix from ir-1 carried into ir-4)."""
    sql, _ = _build_topic_filter_query([])
    assert "a.layer1_verdict IS NULL" in sql
    assert "a.layer1_prompt_version IS NOT ?" in sql
    assert "a.layer1_verdict = 'candidate'" in sql
    assert "r.layer1_verdict IS NULL" in sql
    assert "r.layer1_prompt_version IS NOT ?" in sql
    assert "r.layer1_verdict = 'candidate'" in sql


# ---------------------------------------------------------------------------
# Params + return-type contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("topics", [["agent"], ["agent", "hermes"], []])
def test_params_four_tuple_one_pair_per_union_branch(topics):
    """Wave 2: params is (SKIP_REASON_VERSION_CURRENT, PROMPT_VERSION_LAYER1,
    SKIP_REASON_VERSION_CURRENT, PROMPT_VERSION_LAYER1) — one binding pair
    per UNION branch (cohort gate + layer1 prompt-version). topics arg is
    silently accepted for API compat but does not affect the query."""
    from batch_ingest_from_spider import SKIP_REASON_VERSION_CURRENT
    from lib.article_filter import PROMPT_VERSION_LAYER1

    _, params = _build_topic_filter_query(topics)
    assert params == (
        SKIP_REASON_VERSION_CURRENT,
        PROMPT_VERSION_LAYER1,
        SKIP_REASON_VERSION_CURRENT,
        PROMPT_VERSION_LAYER1,
    )
    assert len(params) == 4


def test_topics_arg_accepted_silently():
    """The function accepts arbitrary topic lists without raising; SQL +
    params are identical regardless of the topics list contents."""
    from batch_ingest_from_spider import SKIP_REASON_VERSION_CURRENT
    from lib.article_filter import PROMPT_VERSION_LAYER1

    sql_a, params_a = _build_topic_filter_query(["agent"])
    sql_b, params_b = _build_topic_filter_query(["completely", "different", "list"])
    assert sql_a == sql_b
    assert params_a == params_b == (
        SKIP_REASON_VERSION_CURRENT,
        PROMPT_VERSION_LAYER1,
        SKIP_REASON_VERSION_CURRENT,
        PROMPT_VERSION_LAYER1,
    )


def test_return_types():
    sql, params = _build_topic_filter_query(["agent"])
    assert isinstance(sql, str)
    assert isinstance(params, tuple)


# ---------------------------------------------------------------------------
# Negative assertions: legacy v3.4 patterns must NOT appear
# ---------------------------------------------------------------------------


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


def test_sql_no_pre_ir4_simple_anti_join():
    """ir-4 regression guard: the pre-ir-4 SQL had
    ``SELECT article_id FROM ingestions WHERE status = 'ok'`` (no source
    scope). After ir-4 every anti-join must scope by source. This test
    catches reverts."""
    sql, _ = _build_topic_filter_query([])
    # Must NOT have status='ok' WITHOUT a source clause adjacent.
    # We guard by asserting status='ok' only co-occurs with source=...
    # Simpler test: count pure status='ok' (no surrounding source) — must be 0.
    # The two valid forms are "source = 'wechat' AND status = 'ok'" and
    # "source = 'rss' AND status = 'ok'". A pre-ir-4 leak would be
    # "ingestions WHERE status = 'ok'" without the source clause.
    bad = "ingestions\n                   WHERE status = 'ok'"
    assert bad not in sql, (
        "pre-ir-4 anti-join leaked: must scope by source. Use "
        "'source = ''wechat'' AND status = ''ok''' (or 'rss')."
    )


# ---------------------------------------------------------------------------
# Integration: dual-source SQL executes against an in-memory DB with both
# articles + rss_articles seeded; both branches must yield rows.
# ---------------------------------------------------------------------------


def _seed_dual_source_db():
    """Build an in-memory SQLite mimicking the real schema for dual-source
    tests. Returns the open connection. Schema kept minimal — only what
    _build_topic_filter_query references."""
    import sqlite3
    c = sqlite3.connect(":memory:")
    c.executescript(
        """
        CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            title TEXT, url TEXT, body TEXT, digest TEXT,
            layer1_verdict TEXT, layer1_prompt_version TEXT
        );
        CREATE TABLE rss_feeds (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            feed_id INTEGER NOT NULL,
            title TEXT, url TEXT, body TEXT, summary TEXT,
            layer1_verdict TEXT, layer1_prompt_version TEXT
        );
        CREATE TABLE ingestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'wechat'
                CHECK (source IN ('wechat', 'rss')),
            status TEXT NOT NULL,
            skip_reason_version INTEGER NOT NULL DEFAULT 0,
            UNIQUE(article_id, source)
        );

        INSERT INTO accounts(id, name) VALUES (1, 'kol-account-A');
        INSERT INTO articles(id, account_id, title, url, body, digest)
            VALUES (10, 1, 'KOL article 10', 'https://mp.weixin.qq.com/s/A', NULL, 'kol-digest');
        INSERT INTO articles(id, account_id, title, url, body, digest)
            VALUES (11, 1, 'KOL article 11', 'https://mp.weixin.qq.com/s/B', 'body11', 'kol-digest-2');

        INSERT INTO rss_feeds(id, name) VALUES (1, 'simonwillison.net');
        INSERT INTO rss_articles(id, feed_id, title, url, body, summary)
            VALUES (10, 1, 'RSS article 10', 'https://example.com/rss10', NULL, 'rss-summary');
        INSERT INTO rss_articles(id, feed_id, title, url, body, summary)
            VALUES (11, 1, 'RSS article 11', 'https://example.com/rss11', 'rss-body11', 'rss-summary-2');
        """
    )
    return c


def test_dual_source_sql_executes_both_branches():
    """Integration: seed minimal articles + rss_articles in memory, run
    the SQL; verify both KOL and RSS rows appear with their literal
    source value."""
    conn = _seed_dual_source_db()
    sql, params = _build_topic_filter_query([])
    rows = conn.execute(sql, params).fetchall()

    # 2 KOL + 2 RSS = 4 candidates (no Layer 1 verdicts written, so all
    # match the layer1_verdict IS NULL bucket).
    assert len(rows) == 4, f"expected 4 rows (2 KOL + 2 RSS), got {len(rows)}: {rows}"

    sources = [r[1] for r in rows]
    assert "wechat" in sources and "rss" in sources, (
        f"Both source literals must appear in the result. Got: {sources}"
    )

    # ORDER BY source DESC, id → 'wechat' rows first (DESC), then 'rss' rows.
    # Within each source, FIFO by id ascending.
    assert sources == ["wechat", "wechat", "rss", "rss"], (
        f"FIFO order broken; expected KOL-then-RSS by id, got: {sources}"
    )


def test_dual_source_sql_anti_join_isolates_by_source():
    """KOL id=10 is in ingestions WHERE source='wechat' AND status='ok'.
    RSS id=10 is the SAME numeric id but different source — must NOT be
    excluded by the KOL anti-join."""
    conn = _seed_dual_source_db()
    # Mark KOL id=10 as already-ingested.
    conn.execute(
        "INSERT INTO ingestions(article_id, source, status) VALUES (10, 'wechat', 'ok')"
    )
    conn.commit()

    sql, params = _build_topic_filter_query([])
    rows = conn.execute(sql, params).fetchall()
    ids_by_source = {r[1]: [] for r in rows}
    for r in rows:
        ids_by_source[r[1]].append(r[0])

    # KOL id=10 excluded (was status='ok' with source='wechat').
    assert 10 not in ids_by_source.get("wechat", []), (
        f"KOL id=10 should be excluded. KOL ids: {ids_by_source.get('wechat')}"
    )
    # RSS id=10 NOT excluded (different source — same numeric id).
    assert 10 in ids_by_source.get("rss", []), (
        f"RSS id=10 must NOT be excluded by KOL anti-join. "
        f"RSS ids: {ids_by_source.get('rss')}"
    )


def test_dual_source_sql_seven_columns_runtime():
    """Runtime introspection: cursor.description should report 7 named
    columns matching the contract."""
    conn = _seed_dual_source_db()
    sql, params = _build_topic_filter_query([])
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    assert cols == ["id", "source", "title", "url", "source_name", "body", "summary"], (
        f"Column shape changed; got {cols}"
    )


def test_dual_source_sql_kol_aliases_digest_to_summary():
    """Last column is named ``summary`` for both branches. KOL row's
    summary value comes from ``a.digest``; RSS row's from ``r.summary``."""
    conn = _seed_dual_source_db()
    sql, params = _build_topic_filter_query([])
    rows = conn.execute(sql, params).fetchall()
    by_id_src = {(r[0], r[1]): r for r in rows}

    kol_10 = by_id_src.get((10, "wechat"))
    assert kol_10 is not None
    assert kol_10[6] == "kol-digest", (
        f"KOL row[6] (summary) should equal articles.digest; got {kol_10[6]!r}"
    )

    rss_10 = by_id_src.get((10, "rss"))
    assert rss_10 is not None
    assert rss_10[6] == "rss-summary", (
        f"RSS row[6] (summary) should equal rss_articles.summary; got {rss_10[6]!r}"
    )


# ---------------------------------------------------------------------------
# main() runtime-check regression — Quick 260507-lai patch (preserved)
#
# These two tests pin the production-shape Hermes invocation path that the
# original f1a963b smoke missed. The Hermes deploy smoke runs without
# --topic-filter — both paths must flow into ingest_from_db with [], not
# sys.exit(1).
# ---------------------------------------------------------------------------


def _run_main_capture_topics(monkeypatch, argv_extra: list[str]) -> list[str] | None:
    """Drive ``batch_ingest_from_spider.main()`` with mocked downstream.

    Captures the first positional argument passed to ``ingest_from_db``
    (the topic_keywords value as it lands inside the called coroutine).

    Returns whatever was captured. The test asserts on this value.
    Raises ``SystemExit`` if main() rejects the invocation.
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
