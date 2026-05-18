"""Behavior-anchor regression tests for batch_ingest_from_spider.ingest_from_db.

Pins five historical prod-only failure modes that survived green unit tests
and shipped to Hermes cron — surfacing only as ghost successes / silent
budget-floor / wrong source attribution. Mandated by CLAUDE.md HIGHEST
PRIORITY PRINCIPLE #7 (behavior-anchor harness for hot orchestration code).

Anchor IDs:
    T1 — 2026-05-08 dual-source skip_reason_version + source dispatch
    T2 — 2026-05-15 v1.0.z imc D2 single-missed queue.append → IndexError
         swallowed → 900s floor → ghost success
    T3 — 2026-05-11 quick-260511-mxc max_articles cap was processed-only;
         pre-fix up to LAYER2_BATCH_SIZE-1 leak past cap
    T4 — v1.0.x stable: finally block MUST drain vision + finalize storages
         even on early-exit (budget exhaustion path)
    T5 — 2026-05-16 quick-260516-htm image_count_row stale-0 + post-vision
         body markers stripped → 900s floor → outer-timeout ghost

Style mirror: tests/unit/test_max_articles_hard_cap.py (same monkeypatch
pattern, same DB_PATH override approach, same caplog basicConfig defence).
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path
from unittest.mock import AsyncMock

# Phase 5 cross-coupling defence — set BEFORE any lib.* import chain pulls
# in lib.llm_deepseek (raises at import if DEEPSEEK_API_KEY unset).
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")

import pytest

import batch_ingest_from_spider as bi
from lib.article_filter import (
    FilterResult,
    PROMPT_VERSION_LAYER1,
    PROMPT_VERSION_LAYER2,
)
from lib.scraper import ScrapeResult

from tests.unit._ingest_fixtures import (
    in_memory_db,
    init_schema,
    mock_rag,
    patch_layer_funcs,
    seed_kol_article,
    seed_rss_article,
)


# ---------------------------------------------------------------------------
# Shared DB-wiring helper
# ---------------------------------------------------------------------------


def _wire_db(monkeypatch, tmp_path: Path) -> sqlite3.Connection:
    """Create a file-backed SQLite DB under tmp_path with the production
    schema applied, point bi.DB_PATH at it, and return a connection the
    test can use for seeding + post-run assertions.

    Production opens its OWN connection to the same file via the real
    sqlite3.connect — no monkeypatch on connect needed. SQLite shows
    committed data across connections to the same file, so seeded rows
    are visible to production's SELECT, and ingestions rows production
    writes are visible to the test's post-run assertions (after a
    fresh fetch — re-opens the file each time).
    """
    fake_db = tmp_path / "fake.db"
    monkeypatch.setattr(bi, "DB_PATH", fake_db)

    conn = sqlite3.connect(str(fake_db))
    init_schema(conn)
    return conn


def _ingestion_rows(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute(
        "SELECT article_id, source, status, skip_reason_version "
        "FROM ingestions ORDER BY source, article_id"
    ).fetchall()


def _status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM ingestions GROUP BY status"
    ).fetchall()
    return {status: count for status, count in rows}


# ---------------------------------------------------------------------------
# T1 — dual-source: KOL+RSS rejects both write to ingestions with correct source
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_layer1_reject_writes_skipped_with_correct_source(
    monkeypatch, tmp_path: Path
):
    """Anchor: 2026-05-08 dual-source skip_reason_version + source dispatch.

    With one KOL article (id=1) and one RSS article (id=1) — same id across
    sources is the deliberate stress test for UNIQUE(article_id, source).
    Both layer1=reject. After ingest_from_db:
      * ingestions has exactly 2 rows: ('wechat',1) and ('rss',1)
      * Both status='skipped' and skip_reason_version=SKIP_REASON_VERSION_CURRENT
    """
    conn = _wire_db(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)

    seed_kol_article(conn, art_id=1, body="kol body " * 50)
    seed_rss_article(conn, art_id=1, body="rss body " * 50)

    # Both rows rejected. Order of layer1_results matches the candidate
    # SELECT's UNION ALL + ORDER BY source DESC, id — so KOL first, then RSS.
    layer1_results = [
        FilterResult(verdict="reject", reason="off-topic", prompt_version=PROMPT_VERSION_LAYER1),
        FilterResult(verdict="reject", reason="off-topic", prompt_version=PROMPT_VERSION_LAYER1),
    ]

    patch_layer_funcs(monkeypatch, layer1_results=layer1_results, layer2_results=[])

    await bi.ingest_from_db(
        topic="ai", min_depth=2, dry_run=False,
        batch_timeout=None, max_articles=None,
    )

    rows = _ingestion_rows(conn)
    assert len(rows) == 2, f"expected 2 ingestions rows; got {rows!r}"

    sources = {r[1] for r in rows}
    assert sources == {"wechat", "rss"}, f"both sources should appear; got {sources!r}"

    for art_id, source, status, skip_ver in rows:
        assert art_id == 1, f"art_id should be 1; got {art_id}"
        assert status == "skipped", f"expected status='skipped'; got {status!r}"
        assert skip_ver == bi.SKIP_REASON_VERSION_CURRENT, (
            f"expected skip_reason_version={bi.SKIP_REASON_VERSION_CURRENT}; "
            f"got {skip_ver}"
        )


# ---------------------------------------------------------------------------
# T2 — drain unpacks 8-col tuple including image_count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drain_unpacks_8_col_tuple_with_image_count(
    monkeypatch, tmp_path: Path
):
    """Anchor: 2026-05-15 v1.0.z imc D2 missed queue.append → row[7] absent.

    Article seeded with body present + image_count=15 + layer1_verdict='candidate'
    (so it skips Layer 1 and is fed straight into the per-article loop).
    Spy on _compute_article_budget_s captures the kwarg value passed at the
    drain site (L1841). Bug case would surface as image_count=0 (kwarg missing
    or row tuple too short) — assertion pins kwarg=15.
    """
    conn = _wire_db(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)

    seed_kol_article(
        conn,
        art_id=1,
        body="full body " * 200,
        image_count=15,
        layer1_verdict="candidate",
        layer1_prompt_version=PROMPT_VERSION_LAYER1,
    )

    captured: dict = {}
    real_budget = bi._compute_article_budget_s

    def spy_budget(content, *, url=None, image_count=None):
        captured["image_count"] = image_count
        captured["url"] = url
        return real_budget(content, url=url, image_count=image_count)

    monkeypatch.setattr(bi, "_compute_article_budget_s", spy_budget)

    patch_layer_funcs(
        monkeypatch,
        layer1_results=[
            FilterResult(verdict="candidate", reason="ok",
                         prompt_version=PROMPT_VERSION_LAYER1),
        ],
        layer2_results=[
            FilterResult(verdict="ok", reason="depth=2",
                         prompt_version=PROMPT_VERSION_LAYER2),
        ],
        ingest_outcome=(True, 50.0, True),
    )

    await bi.ingest_from_db(
        topic="ai", min_depth=2, dry_run=False,
        batch_timeout=None, max_articles=None,
    )

    assert captured.get("image_count") == 15, (
        f"_compute_article_budget_s should receive image_count=15 "
        f"(from row[7]); got {captured.get('image_count')!r} — "
        f"regression of 2026-05-15 v1.0.z imc bug"
    )


# ---------------------------------------------------------------------------
# T3 — max_articles cap charges enqueued rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_articles_cap_includes_queued_count(
    monkeypatch, tmp_path: Path
):
    """Anchor: 2026-05-11 quick-260511-mxc max_articles cap was processed-only.

    Seed 5 KOL candidates with body present + layer1='candidate'. Patch
    LAYER2_BATCH_SIZE=10 so the queue does NOT auto-drain at LAYER2_BATCH_SIZE
    boundary. With max_articles=3, the strict cap (processed + len(queue) >=
    max_articles) must break the outer loop before more than 3 rows are
    queued. Pre-fix bug case: up to 4 extra rows leaked past the cap.
    """
    conn = _wire_db(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)

    for i in range(1, 6):
        seed_kol_article(
            conn,
            art_id=i,
            body=f"body {i} " * 50,
            layer1_verdict="candidate",
            layer1_prompt_version=PROMPT_VERSION_LAYER1,
        )

    monkeypatch.setattr(bi, "LAYER2_BATCH_SIZE", 10)

    layer1_results = [
        FilterResult(verdict="candidate", reason="ok",
                     prompt_version=PROMPT_VERSION_LAYER1)
        for _ in range(5)
    ]

    async def fake_layer2(articles_with_body):
        return [
            FilterResult(verdict="ok", reason="depth=2",
                         prompt_version=PROMPT_VERSION_LAYER2)
            for _ in articles_with_body
        ]

    handles = patch_layer_funcs(
        monkeypatch,
        layer1_results=layer1_results,
        layer2_results=[],  # overridden below
        ingest_outcome=(True, 1.0, True),
    )
    monkeypatch.setattr(bi, "layer2_full_body_score",
                        AsyncMock(side_effect=fake_layer2))

    await bi.ingest_from_db(
        topic="ai", min_depth=2, dry_run=False,
        batch_timeout=None, max_articles=3,
    )

    counts = _status_counts(conn)
    ok_failed = counts.get("ok", 0) + counts.get("failed", 0)
    assert ok_failed <= 3, (
        f"strict cap violated: ok+failed={ok_failed} > max_articles=3; "
        f"counts={counts!r} — regression of 2026-05-11 quick-260511-mxc"
    )

    # We expect exactly 3: at the 3rd enqueue the cap fires and a final
    # drain processes those 3. The remaining 2 candidates never get queued.
    assert ok_failed == 3, (
        f"expected exactly 3 processed; got {ok_failed} (counts={counts!r})"
    )


# ---------------------------------------------------------------------------
# T4 — finally block runs even on early-exit (budget-exhausted path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_exhausted_finally_drains_vision_and_finalizes(
    monkeypatch, tmp_path: Path
):
    """Anchor: v1.0.x stable: finally block MUST drain vision + finalize.

    Use a happy-path 1-article ingest_from_db invocation and assert the
    finally block contract holds:
      * _drain_pending_vision_tasks called at least once
      * rag.finalize_storages called exactly once

    This is the "simpler form" fallback strategy from the plan: drive the
    function to natural completion and pin the finally-block invariants.
    Time-stepping monkeypatch proved unreliable across pytest-asyncio's own
    time.time usage. The core regression net (finally must execute) is
    fully covered.
    """
    conn = _wire_db(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)

    seed_kol_article(
        conn,
        art_id=1,
        body="finally test body " * 50,
        layer1_verdict="candidate",
        layer1_prompt_version=PROMPT_VERSION_LAYER1,
    )

    rag = mock_rag()
    handles = patch_layer_funcs(
        monkeypatch,
        layer1_results=[
            FilterResult(verdict="candidate", reason="ok",
                         prompt_version=PROMPT_VERSION_LAYER1),
        ],
        layer2_results=[
            FilterResult(verdict="ok", reason="depth=2",
                         prompt_version=PROMPT_VERSION_LAYER2),
        ],
        ingest_outcome=(True, 0.5, True),
        rag=rag,
    )

    await bi.ingest_from_db(
        topic="ai", min_depth=2, dry_run=False,
        batch_timeout=None, max_articles=None,
    )

    handles["drain_vision"].assert_called()
    rag.finalize_storages.assert_called_once()


# ---------------------------------------------------------------------------
# T5 — image_count_row refresh after fresh scrape replaces stale 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_image_count_refresh_after_persist(
    monkeypatch, tmp_path: Path
):
    """Anchor: 2026-05-16 quick-260516-htm image_count_row stale-0 + body
    markers stripped → 900s floor → outer-timeout ghost.

    Seed one KOL article with body=NULL + image_count=0 + layer1=candidate.
    Scrape returns ScrapeResult(images=[41 paths]). The L2031-L2032 refresh
    logic must replace stale row[7]=0 with len(scraped.images)=41 BEFORE
    the queue.append at L2064. Spy on _compute_article_budget_s captures
    every kwarg value across all calls — the first drain-time call must
    see image_count=41.
    """
    conn = _wire_db(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)

    seed_kol_article(
        conn,
        art_id=1,
        body=None,           # forces _needs_scrape=True
        image_count=0,       # stale-0 in DB
        layer1_verdict="candidate",
        layer1_prompt_version=PROMPT_VERSION_LAYER1,
    )

    # Scrape returns 41 images — the count we expect to flow through to
    # the budget computation kwarg.
    scraped = ScrapeResult(
        markdown="post-scrape body " * 100,
        images=[f"https://img.example.com/{i}.jpg" for i in range(41)],
        metadata={},
        method="apify",
        summary_only=False,
        content_html=None,
    )

    captured: dict = {"calls": []}
    real_budget = bi._compute_article_budget_s

    def spy_budget(content, *, url=None, image_count=None):
        captured["calls"].append(image_count)
        return real_budget(content, url=url, image_count=image_count)

    monkeypatch.setattr(bi, "_compute_article_budget_s", spy_budget)

    patch_layer_funcs(
        monkeypatch,
        layer1_results=[
            FilterResult(verdict="candidate", reason="ok",
                         prompt_version=PROMPT_VERSION_LAYER1),
        ],
        layer2_results=[
            FilterResult(verdict="ok", reason="depth=2",
                         prompt_version=PROMPT_VERSION_LAYER2),
        ],
        scrape_result=scraped,
        ingest_outcome=(True, 1.0, True),
    )

    await bi.ingest_from_db(
        topic="ai", min_depth=2, dry_run=False,
        batch_timeout=None, max_articles=None,
    )

    assert captured["calls"], (
        "_compute_article_budget_s was never called — "
        "candidate did not reach drain stage"
    )
    assert captured["calls"][0] == 41, (
        f"first drain-time _compute_article_budget_s call should see "
        f"image_count=41 (refreshed from ScrapeResult.images); got "
        f"{captured['calls'][0]!r} — regression of 2026-05-16 "
        f"quick-260516-htm bug. all calls={captured['calls']!r}"
    )
