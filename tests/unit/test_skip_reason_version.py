"""Behavior tests for skip_reason_version cohort gate (quick-260509-s29 Wave 2).

Pins the application-side semantics of the new column:

  * The module-level constant ``SKIP_REASON_VERSION_CURRENT`` exists on
    ``batch_ingest_from_spider`` and is a positive int.
  * ``_build_topic_filter_query`` returns a 4-tuple of params binding
    ``(SKIP_REASON_VERSION_CURRENT, PROMPT_VERSION_LAYER1)`` once per
    UNION branch (KOL + RSS).
  * The candidate SQL excludes ``status='skipped'`` rows whose
    ``skip_reason_version`` equals the current value (permanently dead
    URLs stay excluded).
  * Rows with ``status='skipped'`` but ``skip_reason_version`` ≠ current
    re-enter the candidate pool (taxonomy-bump re-evaluation).
  * Rows with ``status='ok'`` are ALWAYS excluded regardless of version
    (guardrail against the regression where 'ok' rows leak back in).
  * The ``CREATE TABLE IF NOT EXISTS ingestions`` block exposed by
    ``ingest_from_db`` includes the column with NOT NULL DEFAULT 0
    (fresh-DB bootstrap path — no migration 009 needed for new DBs).

Tests are SQL-level: they seed an in-memory SQLite that mirrors the
post-mig-009 schema and run the actual SQL returned by
``_build_topic_filter_query``. No mocks, no LLM calls, no network.
"""
from __future__ import annotations

import sqlite3

import pytest

from batch_ingest_from_spider import (
    SKIP_REASON_VERSION_CURRENT,
    _build_topic_filter_query,
)
from lib.article_filter import PROMPT_VERSION_LAYER1


# ---------------------------------------------------------------------------
# Constant contract
# ---------------------------------------------------------------------------


def test_skip_reason_version_current_is_positive_int():
    """The constant must be a positive int — version=0 is reserved for the
    legacy backfill applied by mig 009 and must NEVER be the current
    cohort. If a future maintainer accidentally sets CURRENT=0 the
    candidate SELECT degenerates to the pre-version semantics (every
    skipped row stays excluded forever)."""
    assert isinstance(SKIP_REASON_VERSION_CURRENT, int)
    assert SKIP_REASON_VERSION_CURRENT >= 1, (
        "SKIP_REASON_VERSION_CURRENT must be ≥ 1; "
        f"got {SKIP_REASON_VERSION_CURRENT!r} — "
        "version=0 is reserved for the legacy backfill"
    )


# ---------------------------------------------------------------------------
# Params shape
# ---------------------------------------------------------------------------


def test_params_is_four_tuple():
    """Params is now (SKIP_REASON_VERSION_CURRENT, PROMPT_VERSION_LAYER1,
    SKIP_REASON_VERSION_CURRENT, PROMPT_VERSION_LAYER1) — one binding for
    each of (anti-join cohort gate, layer1 prompt-version) per UNION
    branch."""
    _, params = _build_topic_filter_query([])
    assert len(params) == 4
    assert params == (
        SKIP_REASON_VERSION_CURRENT,
        PROMPT_VERSION_LAYER1,
        SKIP_REASON_VERSION_CURRENT,
        PROMPT_VERSION_LAYER1,
    )


def test_params_independent_of_topics_arg():
    """Topics arg is silently accepted (Quick 260507-lai); params shape
    must NOT depend on it."""
    _, params_a = _build_topic_filter_query([])
    _, params_b = _build_topic_filter_query(["agent", "hermes"])
    assert params_a == params_b


# ---------------------------------------------------------------------------
# SQL surface — anti-join must reference skip_reason_version on both branches
# ---------------------------------------------------------------------------


def test_sql_anti_join_references_skip_reason_version():
    """Both UNION branches' anti-joins must compare skip_reason_version
    against a placeholder. A regression that drops this would let
    permanent dead URLs cycle back into the pool."""
    sql, _ = _build_topic_filter_query([])
    # Two anti-joins, each with skip_reason_version = ? clause.
    assert sql.count("skip_reason_version = ?") == 2, (
        "Both UNION branches' anti-joins must bind "
        "skip_reason_version = ?; expected 2 occurrences in SQL"
    )


def test_sql_anti_join_keeps_status_ok_unconditional():
    """status='ok' must remain unconditionally excluded — the cohort gate
    only applies to status='skipped' rows. Regression guard for the
    semantics: a future refactor that gates 'ok' on version too would
    re-ingest already-completed articles."""
    sql, _ = _build_topic_filter_query([])
    # Both UNION branches contain `status = 'ok'` un-AND'd to the
    # version clause. The structure is:
    #   AND (status = 'ok' OR (status = 'skipped' AND skip_reason_version = ?))
    # — so 'status = ok' must appear before the 'OR (status = skipped'.
    assert sql.count("status = 'ok'") == 2, (
        "status='ok' must be present unconditionally on both branches"
    )
    assert sql.count("status = 'skipped'") == 2, (
        "status='skipped' must be the ONLY status guarded by version"
    )


# ---------------------------------------------------------------------------
# Behavior tests — seed an in-memory post-mig-009 schema and run the SQL.
# ---------------------------------------------------------------------------


def _seed_post_009_db():
    """Build an in-memory SQLite mimicking the post-mig-009 schema."""
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
        -- 4 KOL articles available as candidates.
        INSERT INTO articles(id, account_id, title, url) VALUES (1, 1, 'A1', 'u1');
        INSERT INTO articles(id, account_id, title, url) VALUES (2, 1, 'A2', 'u2');
        INSERT INTO articles(id, account_id, title, url) VALUES (3, 1, 'A3', 'u3');
        INSERT INTO articles(id, account_id, title, url) VALUES (4, 1, 'A4', 'u4');

        INSERT INTO rss_feeds(id, name) VALUES (1, 'feed-A');
        INSERT INTO rss_articles(id, feed_id, title, url) VALUES (10, 1, 'R10', 'r10');
        INSERT INTO rss_articles(id, feed_id, title, url) VALUES (11, 1, 'R11', 'r11');
        """
    )
    return c


def test_status_ok_row_always_excluded():
    """Article 1 is status='ok' (already ingested). Must NOT appear in
    candidates regardless of skip_reason_version value."""
    conn = _seed_post_009_db()
    conn.execute(
        "INSERT INTO ingestions(article_id, source, status, skip_reason_version) "
        "VALUES (1, 'wechat', 'ok', ?)",
        (SKIP_REASON_VERSION_CURRENT,),
    )
    conn.commit()

    sql, params = _build_topic_filter_query([])
    rows = conn.execute(sql, params).fetchall()
    kol_ids = [r[0] for r in rows if r[1] == "wechat"]
    assert 1 not in kol_ids, (
        f"status='ok' row must always be excluded; got KOL ids {kol_ids}"
    )


def test_status_skipped_at_current_version_excluded():
    """Article 2 is status='skipped' with version=CURRENT (permanently
    dead URL under current taxonomy). Must NOT appear."""
    conn = _seed_post_009_db()
    conn.execute(
        "INSERT INTO ingestions(article_id, source, status, skip_reason_version) "
        "VALUES (2, 'wechat', 'skipped', ?)",
        (SKIP_REASON_VERSION_CURRENT,),
    )
    conn.commit()

    sql, params = _build_topic_filter_query([])
    rows = conn.execute(sql, params).fetchall()
    kol_ids = [r[0] for r in rows if r[1] == "wechat"]
    assert 2 not in kol_ids, (
        f"status='skipped' at version=CURRENT must stay excluded; "
        f"got KOL ids {kol_ids}"
    )


def test_status_skipped_at_legacy_version_re_enters_pool():
    """Article 3 is status='skipped' with version=0 (legacy / pre-mig-009
    backfill). Since 0 ≠ SKIP_REASON_VERSION_CURRENT (which is 1+), this
    row MUST re-enter the candidate pool."""
    conn = _seed_post_009_db()
    conn.execute(
        "INSERT INTO ingestions(article_id, source, status, skip_reason_version) "
        "VALUES (3, 'wechat', 'skipped', 0)"
    )
    conn.commit()

    sql, params = _build_topic_filter_query([])
    rows = conn.execute(sql, params).fetchall()
    kol_ids = [r[0] for r in rows if r[1] == "wechat"]
    assert 3 in kol_ids, (
        "status='skipped' at version=0 (legacy) must re-enter the "
        f"candidate pool; got KOL ids {kol_ids}. The cohort gate is "
        f"how taxonomy bumps re-trigger evaluation of older skipped "
        f"rows; this assertion is the foundational behavior."
    )


def test_status_skipped_at_older_nonzero_version_re_enters_pool():
    """Article 4 is status='skipped' at version=99 (e.g. a hypothetical
    older taxonomy version after several bumps). 99 ≠ CURRENT, so the
    row must re-enter the pool — the gate is "exactly equal to current",
    not "greater than or equal"."""
    conn = _seed_post_009_db()
    older_nonzero_version = SKIP_REASON_VERSION_CURRENT + 99  # guaranteed != current
    conn.execute(
        "INSERT INTO ingestions(article_id, source, status, skip_reason_version) "
        "VALUES (4, 'wechat', 'skipped', ?)",
        (older_nonzero_version,),
    )
    conn.commit()

    sql, params = _build_topic_filter_query([])
    rows = conn.execute(sql, params).fetchall()
    kol_ids = [r[0] for r in rows if r[1] == "wechat"]
    assert 4 in kol_ids, (
        f"version mismatch should re-enter pool; got KOL ids {kol_ids}"
    )


def test_rss_branch_obeys_same_cohort_gate():
    """RSS id=10 with status='skipped' version=CURRENT excluded; RSS id=11
    with version=0 re-enters. Pins symmetric behavior across UNION
    branches."""
    conn = _seed_post_009_db()
    # RSS 10 → permanent skip
    conn.execute(
        "INSERT INTO ingestions(article_id, source, status, skip_reason_version) "
        "VALUES (10, 'rss', 'skipped', ?)",
        (SKIP_REASON_VERSION_CURRENT,),
    )
    # RSS 11 → legacy skip (must re-enter)
    conn.execute(
        "INSERT INTO ingestions(article_id, source, status, skip_reason_version) "
        "VALUES (11, 'rss', 'skipped', 0)"
    )
    conn.commit()

    sql, params = _build_topic_filter_query([])
    rows = conn.execute(sql, params).fetchall()
    rss_ids = [r[0] for r in rows if r[1] == "rss"]
    assert 10 not in rss_ids, (
        f"RSS id=10 at version=CURRENT must stay excluded; got {rss_ids}"
    )
    assert 11 in rss_ids, (
        f"RSS id=11 at version=0 (legacy) must re-enter; got {rss_ids}"
    )


# ---------------------------------------------------------------------------
# Fresh-DB bootstrap: ingest_from_db's CREATE TABLE IF NOT EXISTS must
# include the column so a brand-new DB doesn't need to run mig 009.
# ---------------------------------------------------------------------------


def test_create_table_block_includes_column(tmp_path, monkeypatch):
    """The inline CREATE TABLE IF NOT EXISTS in ``ingest_from_db`` must
    include skip_reason_version so a fresh-DB bootstrap doesn't require
    mig 009 to land first.

    We don't run the full ingest_from_db (it does too much). We carve
    out the CREATE TABLE statement by paren-counting (regex can't handle
    nested parens — the CHECK clause has its own ``IN ('wechat', 'rss')``)
    and exec it on a fresh DB.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "batch_ingest_from_spider.py").read_text(encoding="utf-8")

    # Find the start of the block.
    start_idx = src.find("CREATE TABLE IF NOT EXISTS ingestions (")
    assert start_idx != -1, "CREATE TABLE IF NOT EXISTS ingestions not found"

    # Walk forward, counting parens until we close the outer one.
    depth = 0
    end_idx = -1
    for i in range(start_idx, len(src)):
        ch = src[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end_idx = i + 1
                break
    assert end_idx != -1, "could not find matching ')' for CREATE TABLE block"

    block = src[start_idx:end_idx]

    # Must reference the new column.
    assert "skip_reason_version INTEGER NOT NULL DEFAULT 0" in block, (
        f"CREATE TABLE IF NOT EXISTS ingestions must declare "
        f"skip_reason_version INTEGER NOT NULL DEFAULT 0; "
        f"got block:\n{block}"
    )

    # Sanity: the block exec'd against a fresh DB produces a table whose
    # PRAGMA table_info lists skip_reason_version.
    db = tmp_path / "fresh.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(block)
        conn.commit()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(ingestions)")}
        assert "skip_reason_version" in cols
    finally:
        conn.close()
