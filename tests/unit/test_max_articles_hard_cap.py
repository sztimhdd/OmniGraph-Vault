"""Unit tests for ``batch_ingest_from_spider.ingest_from_db`` strict
``--max-articles`` hard cap (Quick 260511-lmx).

History:
    Quick 260503-jn6 (JN6-02) introduced ``--max-articles`` as a soft cap on
    SUCCESSFULLY-processed rows. The check was placed at the top of each
    per-article loop iteration (L1776) and was re-checked post-drain at
    L1930. ``processed`` is incremented only INSIDE
    ``_drain_layer2_queue()``, which runs only when the queue hits
    ``LAYER2_BATCH_SIZE`` (=5) or once at end-of-loop.

    Result: between drains, ``processed`` is stale. With
    ``--max-articles 2`` and 6 layer2-OK candidates the loop enqueued 5
    rows before the queue hit the drain boundary; the drain bumped
    ``processed`` to 5; only THEN did the post-drain cap check fire — but
    by then 5 ingestions rows had been written. Three smoke runs at
    cap=5 produced 7, 14, 7 rows. The 2026-05-10 smoke was destroyed by
    the unpredictable wall-clock budget that follows.

    Quick 260511-lmx (this fix) tightens the per-iter check to charge the
    in-flight queue against the cap budget at enqueue time:

        processed + len(layer2_queue) >= max_articles

    Skipped statuses (skipped, skipped_ingested, skipped_graded) ``continue``
    BEFORE enqueue, so they correctly do not consume cap budget. Layer 2
    'reject' verdicts write a 'skipped' ingestion inside the drain WITHOUT
    incrementing ``processed`` — also correctly excluded.

These tests pin the post-fix contract:
    1. Skipped layer1 rejects do NOT consume cap budget.
    2. The cap fires after the Nth ok-eligible row is enqueued and the
       loop exits cleanly with one log line containing
       'max-articles cap reached'.
    3. A mid-loop ``failed`` ingestion still counts toward the cap (it
       writes a 'failed' ingestions row and increments ``processed``).
    4. Pool-exhaustion before the cap exits naturally with NO cap-reached
       log line.

The tests are deterministic and offline:
    * ``layer1_pre_filter`` / ``layer2_full_body_score`` mocked (no
      DeepSeek HTTP).
    * ``ingest_article`` mocked (no LightRAG ainsert).
    * ``ingest_wechat.get_rag`` mocked (no LightRAG initialisation).
    * Vision drain mocked (no asyncio task scan).
    * ``DB_PATH`` patched to a tmp file so the function's own
      ``sqlite3.connect(str(DB_PATH))`` call points to a seeded fixture
      DB. The test pre-creates the schema (subset matching production)
      with the columns that ``persist_layer1_verdicts`` /
      ``persist_layer2_verdicts`` and the candidate SELECT touch.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# Import setup -- DEEPSEEK_API_KEY must be set before lib.* import chain
# eagerly loads deepseek_model_complete (Phase 5 cross-coupling defence).
import os
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")

import batch_ingest_from_spider as bi
from lib.article_filter import FilterResult, PROMPT_VERSION_LAYER1


PROMPT_VERSION_LAYER2 = "v1.0"  # not exported from lib.article_filter; literal is fine


# ---------------------------------------------------------------------------
# Fixtures: minimal production-shaped schema seeded into a tmp SQLite file
# ---------------------------------------------------------------------------


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create the subset of the production schema that ``ingest_from_db``
    and the persist helpers touch. Mirrors the shape used by
    ``test_batch_ingest_topic_filter._seed_dual_source_db`` plus the
    ``layer1_*`` / ``layer2_*`` columns that ``persist_*_verdicts``
    update."""
    conn.executescript(
        """
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL
        );
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            title TEXT, url TEXT, body TEXT, digest TEXT,
            layer1_verdict TEXT, layer1_reason TEXT, layer1_at TEXT,
            layer1_prompt_version TEXT,
            layer2_verdict TEXT, layer2_reason TEXT, layer2_at TEXT,
            layer2_prompt_version TEXT
        );
        CREATE TABLE rss_feeds (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL
        );
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            feed_id INTEGER NOT NULL,
            title TEXT, url TEXT, body TEXT, summary TEXT,
            layer1_verdict TEXT, layer1_reason TEXT, layer1_at TEXT,
            layer1_prompt_version TEXT,
            layer2_verdict TEXT, layer2_reason TEXT, layer2_at TEXT,
            layer2_prompt_version TEXT
        );
        CREATE TABLE classifications (
            article_id INTEGER, topic TEXT, depth_score INTEGER, reason TEXT,
            depth INTEGER, topics TEXT, rationale TEXT,
            PRIMARY KEY (article_id, topic)
        );
        INSERT INTO accounts(id, name) VALUES (1, 'kol-account-A');
        """
    )


def _seed_kol_articles(conn: sqlite3.Connection, n: int, start_id: int = 100) -> None:
    """Seed ``n`` KOL article rows with a non-empty body (so
    ``_needs_scrape('wechat', body)`` returns False and the per-article
    scrape branch is skipped — keeps the test offline)."""
    for i in range(n):
        art_id = start_id + i
        conn.execute(
            "INSERT INTO articles(id, account_id, title, url, body, digest) "
            "VALUES (?, 1, ?, ?, ?, ?)",
            (
                art_id,
                f"KOL article {art_id}",
                f"https://mp.weixin.qq.com/s/test-{art_id}",
                f"prepopulated body content for article {art_id} " * 20,
                f"digest-{art_id}",
            ),
        )
    conn.commit()


@pytest.fixture
def seeded_db(tmp_path: Path) -> Path:
    """Create a tmp DB file with the production schema and 6 KOL
    candidates seeded. Tests mutate further in-line if needed."""
    db_path = tmp_path / "kol_scan.db"
    conn = sqlite3.connect(str(db_path))
    _create_schema(conn)
    _seed_kol_articles(conn, n=6)
    conn.close()
    return db_path


def _patch_downstream(
    mocker,
    db_path: Path,
    layer1_verdicts: list[str],
    layer2_verdicts: list[str] | None,
    ingest_outcomes: list[tuple[bool, float, bool]] | None,
):
    """Apply the downstream mock stack:

      * DB_PATH → seeded tmp file.
      * env loaders / api-key fetch → no-op.
      * layer1_pre_filter → returns ``layer1_verdicts`` mapped to
        FilterResult per-row (verdict order matches the candidate row
        order from the candidate SELECT).
      * layer2_full_body_score → returns ``layer2_verdicts`` (None means
        no layer2 candidates expected; raises if called).
      * ingest_article → AsyncMock returning successive items from
        ``ingest_outcomes`` (None means no ok candidates expected).
      * ingest_wechat.get_rag → AsyncMock returning fake rag with
        AsyncMock finalize_storages.
      * _drain_pending_vision_tasks → AsyncMock no-op.
      * SLEEP_BETWEEN_ARTICLES → 0 to keep tests fast.
    """
    mocker.patch.object(bi, "DB_PATH", db_path)
    mocker.patch.object(bi, "_load_hermes_env", lambda: None)
    mocker.patch.object(bi, "get_deepseek_api_key", lambda: "dummy")
    mocker.patch.object(bi, "SLEEP_BETWEEN_ARTICLES", 0)

    async def fake_layer1(articles_meta):
        # layer1 receives all candidate rows in a single batch
        # (LAYER1_BATCH_SIZE=30; tests stay below). Pair verdicts to
        # incoming rows by position.
        n = len(articles_meta)
        verdicts = layer1_verdicts[:n]
        # Pad with 'reject' if the test undersupplied (defence).
        verdicts += ["reject"] * (n - len(verdicts))
        return [
            FilterResult(verdict=v, reason="ok", prompt_version=PROMPT_VERSION_LAYER1)
            for v in verdicts
        ]

    mocker.patch.object(bi, "layer1_pre_filter", AsyncMock(side_effect=fake_layer1))

    if layer2_verdicts is None:
        async def explode_layer2(*a, **kw):
            raise AssertionError(
                "layer2_full_body_score should not be called — "
                "test pool yields no candidates"
            )
        mocker.patch.object(
            bi, "layer2_full_body_score", AsyncMock(side_effect=explode_layer2)
        )
    else:
        # Track how many layer2 verdicts have been consumed.
        verdict_iter = iter(layer2_verdicts)

        async def fake_layer2(articles_with_body):
            return [
                FilterResult(
                    verdict=next(verdict_iter),
                    reason="ok",
                    prompt_version=PROMPT_VERSION_LAYER2,
                )
                for _ in articles_with_body
            ]

        mocker.patch.object(
            bi, "layer2_full_body_score", AsyncMock(side_effect=fake_layer2)
        )

    if ingest_outcomes is None:
        async def explode_ingest(*a, **kw):
            raise AssertionError(
                "ingest_article should not be called — "
                "test pool yields no ok-verdict candidates"
            )
        mocker.patch.object(bi, "ingest_article", AsyncMock(side_effect=explode_ingest))
    else:
        outcome_iter = iter(ingest_outcomes)

        async def fake_ingest_article(*a, **kw):
            return next(outcome_iter)

        mocker.patch.object(
            bi, "ingest_article", AsyncMock(side_effect=fake_ingest_article)
        )

    fake_rag = MagicMock()
    fake_rag.finalize_storages = AsyncMock(return_value=None)

    async def fake_get_rag(flush=True):
        return fake_rag

    fake_iw = MagicMock(get_rag=fake_get_rag)
    mocker.patch.dict("sys.modules", {"ingest_wechat": fake_iw})

    async def fake_drain_vision():
        return None

    mocker.patch.object(
        bi, "_drain_pending_vision_tasks",
        AsyncMock(side_effect=fake_drain_vision),
    )

    # ingest_from_db calls ``logging.basicConfig(force=True)`` after
    # LightRAG init (production line ~1607) to restore log format. The
    # ``force=True`` removes ALL root-logger handlers, including pytest's
    # caplog handler — which is why captured INFO records get truncated
    # mid-run. Patch to a no-op for the duration of the test so
    # caplog.records sees the cap-reached log line. This is a pure test
    # accommodation; production behaviour is unchanged.
    mocker.patch.object(logging, "basicConfig", lambda *a, **kw: None)


def _ingestion_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM ingestions GROUP BY status"
    ).fetchall()
    conn.close()
    return {status: count for status, count in rows}


# ---------------------------------------------------------------------------
# The 4 contract tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cap_excludes_skipped_layer1_rejects(
    mocker, caplog, seeded_db: Path
):
    """max_articles=3, 5 candidates: 2 layer1=reject + 3 layer2=ok.

    Expected: 2 'skipped' ingestions (layer1) + 3 'ok' ingestions; loop
    exits naturally at end-of-pool (cap met by ok rows, not exceeded).

    We seed 5 KOL articles total — drop the last from the seeded fixture
    to make the candidate pool exactly 5. Layer 1 rejects rows 1-2;
    layer 2 verdicts ok-ok-ok for rows 3-5.
    """
    # Trim the fixture down to 5 by deleting article 105.
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("DELETE FROM articles WHERE id = ?", (105,))
    conn.commit()
    conn.close()

    _patch_downstream(
        mocker, seeded_db,
        layer1_verdicts=["reject", "reject", "candidate", "candidate", "candidate"],
        layer2_verdicts=["ok", "ok", "ok"],
        ingest_outcomes=[(True, 1.0, True)] * 3,
    )

    caplog.set_level(logging.INFO, logger=bi.logger.name)

    await bi.ingest_from_db(
        topic="ai", min_depth=2, dry_run=False,
        batch_timeout=None, max_articles=3,
    )

    counts = _ingestion_counts(seeded_db)
    assert counts.get("ok", 0) == 3, f"expected 3 ok; got {counts}"
    assert counts.get("failed", 0) == 0, f"expected 0 failed; got {counts}"
    assert counts.get("skipped", 0) == 2, f"expected 2 skipped (layer1 reject); got {counts}"

    # Cap-reached log: optional here. The pool produces exactly 3 ok rows
    # and the loop exits naturally at end-of-pool. Either zero or one
    # cap-reached log line is acceptable — what matters is ok+failed == 3.
    cap_log_count = sum(
        1 for r in caplog.records
        if "max-articles cap reached" in r.getMessage()
    )
    assert cap_log_count <= 1, (
        f"cap-reached log fired {cap_log_count} times; expected at most 1"
    )


@pytest.mark.asyncio
async def test_cap_break_on_third_ok(mocker, caplog, seeded_db: Path):
    """max_articles=3, 6 candidates ALL layer2=ok.

    Expected: exactly 3 'ok' ingestions; rows 4-6 untouched
    (no ingestions row written). Cap-reached log appears once.
    """
    _patch_downstream(
        mocker, seeded_db,
        layer1_verdicts=["candidate"] * 6,
        layer2_verdicts=["ok"] * 3,  # only 3 reach layer2
        ingest_outcomes=[(True, 1.0, True)] * 3,
    )

    caplog.set_level(logging.INFO, logger=bi.logger.name)

    await bi.ingest_from_db(
        topic="ai", min_depth=2, dry_run=False,
        batch_timeout=None, max_articles=3,
    )

    counts = _ingestion_counts(seeded_db)
    assert counts.get("ok", 0) == 3, f"expected exactly 3 ok; got {counts}"
    assert counts.get("failed", 0) == 0, f"expected 0 failed; got {counts}"
    assert counts.get("skipped", 0) == 0, f"expected 0 skipped; got {counts}"

    cap_logs = [
        r.getMessage() for r in caplog.records
        if "max-articles cap reached" in r.getMessage()
    ]
    assert len(cap_logs) == 1, (
        f"expected exactly 1 cap-reached log; got {len(cap_logs)}: {cap_logs}"
    )
    # New log shape includes processed + queued breakdown.
    assert "queued=" in cap_logs[0], (
        f"cap-reached log missing 'queued=' breakdown: {cap_logs[0]}"
    )


@pytest.mark.asyncio
async def test_cap_with_mid_loop_failure_counts(
    mocker, caplog, seeded_db: Path
):
    """max_articles=3, 5 candidates layer2=ok; ingest_article side_effect:
    row1→ok, row2→failed, row3→ok, rows 4-5 not reached.

    Expected: ok=2, failed=1 (total ok+failed=3); cap reached.
    """
    # Trim to 5.
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("DELETE FROM articles WHERE id = ?", (105,))
    conn.commit()
    conn.close()

    _patch_downstream(
        mocker, seeded_db,
        layer1_verdicts=["candidate"] * 5,
        layer2_verdicts=["ok"] * 3,  # only 3 reach layer2 before cap
        ingest_outcomes=[
            (True, 1.0, True),    # row1 → ok (success=True, doc_confirmed=True)
            (False, 1.0, False),  # row2 → failed (success=False)
            (True, 1.0, True),    # row3 → ok
        ],
    )

    caplog.set_level(logging.INFO, logger=bi.logger.name)

    await bi.ingest_from_db(
        topic="ai", min_depth=2, dry_run=False,
        batch_timeout=None, max_articles=3,
    )

    counts = _ingestion_counts(seeded_db)
    assert counts.get("ok", 0) == 2, f"expected 2 ok; got {counts}"
    assert counts.get("failed", 0) == 1, f"expected 1 failed; got {counts}"
    assert counts.get("ok", 0) + counts.get("failed", 0) == 3, (
        f"strict cap: ok+failed must equal max_articles=3; got {counts}"
    )

    cap_logs = [
        r.getMessage() for r in caplog.records
        if "max-articles cap reached" in r.getMessage()
    ]
    assert len(cap_logs) >= 1, (
        f"expected cap-reached log; got {len(cap_logs)}"
    )


@pytest.mark.asyncio
async def test_cap_pool_exhausted_before_reached(
    mocker, caplog, seeded_db: Path
):
    """max_articles=3, 2 candidates BOTH layer1=reject.

    Expected: 2 'skipped' ingestions; loop exits via natural pool
    exhaustion (no cap-reached log). ingest_article and
    layer2_full_body_score MUST NOT be called.
    """
    # Trim to 2.
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("DELETE FROM articles WHERE id IN (102, 103, 104, 105)")
    conn.commit()
    conn.close()

    _patch_downstream(
        mocker, seeded_db,
        layer1_verdicts=["reject", "reject"],
        layer2_verdicts=None,    # explodes if called
        ingest_outcomes=None,    # explodes if called
    )

    caplog.set_level(logging.INFO, logger=bi.logger.name)

    await bi.ingest_from_db(
        topic="ai", min_depth=2, dry_run=False,
        batch_timeout=None, max_articles=3,
    )

    counts = _ingestion_counts(seeded_db)
    assert counts.get("skipped", 0) == 2, (
        f"expected 2 skipped layer1 rejects; got {counts}"
    )
    assert counts.get("ok", 0) == 0, f"expected 0 ok; got {counts}"
    assert counts.get("failed", 0) == 0, f"expected 0 failed; got {counts}"

    cap_logs = [
        r.getMessage() for r in caplog.records
        if "max-articles cap reached" in r.getMessage()
    ]
    assert cap_logs == [], (
        f"pool-exhaustion path must NOT emit cap-reached log; got {cap_logs}"
    )
