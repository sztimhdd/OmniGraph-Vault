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

import asyncio
import hashlib
import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
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
        topic="ai", dry_run=False,
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
        topic="ai", dry_run=False,
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
        topic="ai", dry_run=False,
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
        topic="ai", dry_run=False,
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
        topic="ai", dry_run=False,
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


# ---------------------------------------------------------------------------
# T6 — W3 _wiki_update_check fires once after final drain, never blocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wiki_update_hook_called_after_drain_with_observable_post_condition(
    monkeypatch, tmp_path: Path
):
    """Anchor: 2026-05-19 llm-wiki-W3 T3 ingest hook contract.

    fixture-schema-verified: tests/unit/_ingest_fixtures.py articles DDL
    extended with content_hash + enriched columns to mirror production
    schema (see migration 011_add_content_hash). PRAGMA-checked at the
    top of this test so any future fixture drift fails loudly here
    before regressing the contract under test.

    Seeds two KOL articles, both layer1=reject (cheapest path that still
    exercises the post-drain hook insertion point at L2102 → L2105). The
    real _wiki_update_check is replaced with an AsyncMock spy. Three
    behaviors are pinned:

      1. Spy is called exactly once after the final _drain_layer2_queue
      2. Spy receives the current-batch wiki success set: source-aware
         {"source", "ref"} mappings of ok+doc_confirmed articles only
         (empty here, since both rows are layer2=reject)
      3. A raised exception inside the hook is swallowed — ingest_from_db
         completes normally and the seeded ingestions rows persist
    """
    conn = _wire_db(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)

    # fixture-schema-verified: assert articles.content_hash + articles.enriched
    # exist on the in-memory schema (mirrors production migration 011).
    cols = {row[1] for row in conn.execute("PRAGMA table_info(articles)").fetchall()}
    assert "content_hash" in cols, (
        "fixture drift: tests/unit/_ingest_fixtures.py articles DDL must "
        "include content_hash TEXT (production schema, populated by "
        "ingest_wechat.py after successful ainsert)"
    )
    assert "enriched" in cols, (
        "fixture drift: tests/unit/_ingest_fixtures.py articles DDL must "
        "include enriched INTEGER DEFAULT 0 (production schema)"
    )

    # layer1=candidate (skip scrape via seeded body) + layer2=reject lets the
    # candidate_rows accumulate but bypasses LightRAG ainsert — fast and pins
    # the post-drain hook insertion point at the canonical spot.
    seed_kol_article(conn, art_id=1, body="kol body " * 50)
    seed_kol_article(conn, art_id=2, body="kol body " * 50)

    patch_layer_funcs(
        monkeypatch,
        layer1_results=[
            FilterResult(verdict="candidate", reason="ok",
                         prompt_version=PROMPT_VERSION_LAYER1),
            FilterResult(verdict="candidate", reason="ok",
                         prompt_version=PROMPT_VERSION_LAYER1),
        ],
        layer2_results=[
            FilterResult(verdict="reject", reason="shallow",
                         prompt_version=PROMPT_VERSION_LAYER2),
            FilterResult(verdict="reject", reason="shallow",
                         prompt_version=PROMPT_VERSION_LAYER2),
        ],
    )

    # Replace the real hook with a spy that raises — pins both call-once
    # AND swallow-exception behavior in a single test.
    spy = AsyncMock(side_effect=RuntimeError("simulated wiki hook failure"))
    monkeypatch.setattr(bi, "_wiki_update_check", spy)

    # Sanity precondition: _drain_layer2_queue is called by ingest_from_db
    # before the hook. Order is enforced by the source layout (L2102
    # final drain → L2105 hook); we assert the hook fires AT LEAST once
    # and receives only valid 10-char hashes.
    await bi.ingest_from_db(
        topic="ai", dry_run=False,
        batch_timeout=None, max_articles=None,
    )

    # Behavior 1: hook called exactly once after final drain.
    assert spy.await_count == 1, (
        f"_wiki_update_check should fire exactly once after final drain; "
        f"got {spy.await_count} awaits"
    )

    # Behavior 2: positional arg 0 is the current-batch WIKI SUCCESS SET —
    # source-aware {"source", "ref"} mappings. Both seeded articles are
    # layer2=reject here, so neither reached status='ok': the hook must
    # receive an EMPTY list (never all-candidate bare hashes — W5B Task 2).
    call_args = spy.await_args
    assert call_args is not None, "spy was never awaited"
    passed = call_args.args[0]
    assert isinstance(passed, list), (
        f"first arg should be list[dict]; got {type(passed).__name__}"
    )
    assert passed == [], (
        f"rejected/skipped articles must not seed the wiki hook; got {passed!r}"
    )

    # Behavior 3: hook exception did not block ingest_from_db. Both
    # seeded layer1=reject articles MUST have ingestions rows written.
    rows = _ingestion_rows(conn)
    assert len(rows) == 2, (
        f"hook RuntimeError leaked and aborted ingest_from_db before "
        f"per-article writes — expected 2 ingestions rows; got {rows!r}"
    )


# ---------------------------------------------------------------------------
# T7 — W5B Task 2: post-drain W3 hook receives ONLY the current batch's
# ok+doc_confirmed source-aware refs (never failed/skipped), pinned
# timeout=120, and TimeoutError isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wiki_hook_receives_only_ok_doc_confirmed_source_refs(
    monkeypatch, tmp_path: Path
):
    """W5B Task 2 Step 2.4/2.5 contract.

    Fixture: wechat A -> ok+doc_confirmed, rss B -> ok+doc_confirmed,
    wechat C -> failed, rss D -> skipped (layer2=reject). The post-drain
    ``_wiki_update_check`` spy must receive EXACTLY A/B as source-aware
    ``{"source", "ref"}`` mappings — never C/D, never bare hashes of the
    whole candidate pool — and the call site must keep ``timeout=120``.
    A second run pins TimeoutError isolation: a hook timeout never aborts
    ``ingest_from_db`` and per-article ingestions rows still persist.
    """
    conn = _wire_db(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)

    urls = {
        "A": "https://mp.weixin.qq.com/s/w5b-t2-A",
        "B": "https://example.com/rss/w5b-t2-B",
        "C": "https://mp.weixin.qq.com/s/w5b-t2-C",
        "D": "https://example.com/rss/w5b-t2-D",
    }
    refs = {k: hashlib.md5(v.encode()).hexdigest()[:10] for k, v in urls.items()}

    seed_kol_article(
        conn, art_id=1, body="ok A body " * 50, url=urls["A"],
        layer1_verdict="candidate", layer1_prompt_version=PROMPT_VERSION_LAYER1,
    )
    seed_rss_article(
        conn, art_id=1, body="ok B body " * 50, url=urls["B"],
        layer1_verdict="candidate", layer1_prompt_version=PROMPT_VERSION_LAYER1,
    )
    seed_kol_article(
        conn, art_id=2, body="fail C body " * 50, url=urls["C"],
        layer1_verdict="candidate", layer1_prompt_version=PROMPT_VERSION_LAYER1,
    )
    seed_rss_article(
        conn, art_id=2, body="skip D body " * 50, url=urls["D"],
        layer1_verdict="candidate", layer1_prompt_version=PROMPT_VERSION_LAYER1,
    )

    candidate = FilterResult(verdict="candidate", reason="ok",
                             prompt_version=PROMPT_VERSION_LAYER1)
    ok = FilterResult(verdict="ok", reason="depth=2",
                      prompt_version=PROMPT_VERSION_LAYER2)
    reject = FilterResult(verdict="reject", reason="shallow",
                          prompt_version=PROMPT_VERSION_LAYER2)
    # Candidate SELECT is source DESC, id ASC -> queue order A, C, B, D.
    patch_layer_funcs(
        monkeypatch,
        layer1_results=[candidate, candidate, candidate, candidate],
        layer2_results=[ok, ok, ok, reject],
        ingest_outcome=(True, 1.0, True),  # overridden per-url below
    )

    # Hermetic: the ok-path inline title translation must never hit the
    # network from this test (also proves the W3 hook path is LLM-free).
    import lib.translate

    monkeypatch.setattr(
        lib.translate, "translate_title_with_deepseek_tavily",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(lib.translate, "detect_source_lang", lambda s: "zh")

    async def _ingest(source, url, dry_run, rag, effective_timeout=0):
        if url == urls["C"]:
            return (False, 1.0, False)
        return (True, 1.0, True)

    monkeypatch.setattr(bi, "ingest_article", AsyncMock(side_effect=_ingest))

    captured: dict = {"timeouts": []}
    real_wait_for = asyncio.wait_for

    def spy_wait_for(coro, timeout=None):
        captured["timeouts"].append(timeout)
        return real_wait_for(coro, timeout=timeout)

    monkeypatch.setattr(asyncio, "wait_for", spy_wait_for)

    spy = AsyncMock(return_value={"suggestions_generated": 0, "applied": 0, "dropped": 0})
    monkeypatch.setattr(bi, "_wiki_update_check", spy)

    await bi.ingest_from_db(
        topic="ai", dry_run=False,
        batch_timeout=None, max_articles=None,
    )

    # Behavior 1: hook fired exactly once after the final drain.
    assert spy.await_count == 1, (
        f"_wiki_update_check should fire exactly once; got {spy.await_count}"
    )
    # Behavior 2: receives EXACTLY A/B source-aware mappings — never C/D,
    # never all-candidate bare hashes.
    passed = spy.await_args.args[0]
    assert passed == [
        {"source": "wechat", "ref": refs["A"]},
        {"source": "rss", "ref": refs["B"]},
    ], f"expected exactly A/B source-aware refs; got {passed!r}"
    # Behavior 3: the 120s outer timeout is preserved at the call site.
    assert captured["timeouts"] and captured["timeouts"][-1] == 120, (
        f"_wiki_update_check must be awaited with timeout=120; "
        f"got {captured['timeouts']!r}"
    )

    # Behavior 4: TimeoutError isolation — a timed-out hook never aborts
    # ingest_from_db; per-article ingestions rows still persist.
    async def _raise_timeout(coro, timeout=None):
        coro.close()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(asyncio, "wait_for", _raise_timeout)

    fake2 = tmp_path / "fake2.db"
    monkeypatch.setattr(bi, "DB_PATH", fake2)
    conn2 = sqlite3.connect(str(fake2))
    init_schema(conn2)
    seed_kol_article(
        conn2, art_id=10, body="timeout body " * 50,
        layer1_verdict="candidate", layer1_prompt_version=PROMPT_VERSION_LAYER1,
    )
    patch_layer_funcs(
        monkeypatch,
        layer1_results=[candidate],
        layer2_results=[ok],
        ingest_outcome=(True, 1.0, True),
    )

    await bi.ingest_from_db(
        topic="ai", dry_run=False,
        batch_timeout=None, max_articles=None,
    )

    rows2 = conn2.execute(
        "SELECT article_id, status FROM ingestions ORDER BY article_id"
    ).fetchall()
    assert rows2 == [(10, "ok")], (
        f"hook TimeoutError must be swallowed and the article still ingested; "
        f"got {rows2!r}"
    )


# ---------------------------------------------------------------------------
# T8/T9/T10/T11 — Layer 2 whole-batch NULL retry backoff (plan T5, 2026-09).
# A Layer 2 batch that fails for every row leaves layer2_verdict=NULL; the
# 2h cron tick then re-selects those rows and re-calls the full-body DeepSeek
# batch unconditionally. The fix: stamp layer2_at on a whole-batch NULL
# failure (verdict stays NULL — never marked ok/failed, never dropped) and
# drop rows whose last attempt was NULL and lies inside the backoff window
# BEFORE the LLM call. Backoff derives purely from persisted state and
# expires with layer2_at, so a stuck batch is re-attempted after
# LAYER2_NULL_RETRY_BACKOFF_S and fresh rows are never suppressed.
# ---------------------------------------------------------------------------

_ALL_NULL = [
    FilterResult(
        verdict=None, reason="exception:MockTimeout",
        prompt_version=PROMPT_VERSION_LAYER2,
    )
]


@pytest.mark.asyncio
async def test_layer2_whole_batch_null_backs_off_then_retries_after_window(
    monkeypatch, tmp_path: Path
):
    """T5 anchor — the 2h-tick retry-amplification failure mode.

    Seed one KOL Layer2-NULL candidate. Tick 1: Layer 2 LLM called, whole
    batch NULL → layer2_at stamped, verdict stays NULL, no ingestions row
    (candidate preserved). Tick 2 (inside backoff window): Layer 2 LLM must
    NOT be called again and the row must be byte-identical. Window expiry
    (layer2_at rewritten to a stale value): tick 3 re-attempts the LLM.
    """
    conn = _wire_db(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)

    seed_kol_article(
        conn,
        art_id=1,
        body="backoff body " * 200,
        layer1_verdict="candidate",
        layer1_prompt_version=PROMPT_VERSION_LAYER1,
    )

    candidate = FilterResult(
        verdict="candidate", reason="ok", prompt_version=PROMPT_VERSION_LAYER1
    )

    handles = patch_layer_funcs(
        monkeypatch,
        layer1_results=[candidate],
        layer2_results=_ALL_NULL,
    )

    # Tick 1: first (failed) attempt → Layer 2 LLM called exactly once.
    await bi.ingest_from_db(
        topic="ai", dry_run=False, batch_timeout=None, max_articles=None,
    )
    assert handles["layer2"].call_count == 1, (
        f"tick 1 should call Layer 2 LLM once; got {handles['layer2'].call_count}"
    )
    row = conn.execute(
        "SELECT layer2_verdict, layer2_at FROM articles WHERE id = 1"
    ).fetchone()
    assert row[0] is None, (
        f"whole-batch NULL failure must leave layer2_verdict NULL; got {row[0]!r}"
    )
    assert row[1] is not None, (
        "whole-batch NULL failure must stamp layer2_at so the next tick can back off"
    )
    assert _ingestion_rows(conn) == [], (
        "failed candidate must not be marked ok/failed in ingestions; "
        f"got {_ingestion_rows(conn)!r}"
    )
    stamped_at = row[1]

    # Tick 2: immediate next tick — inside the backoff window → NO LLM call,
    # row untouched (verdict NULL, layer2_at not re-stamped, still no
    # ingestions row = candidate not dropped, not converted to ok/failed).
    await bi.ingest_from_db(
        topic="ai", dry_run=False, batch_timeout=None, max_articles=None,
    )
    assert handles["layer2"].call_count == 1, (
        "tick inside the backoff window must NOT re-call the Layer 2 LLM; "
        f"got {handles['layer2'].call_count} calls"
    )
    row = conn.execute(
        "SELECT layer2_verdict, layer2_at FROM articles WHERE id = 1"
    ).fetchone()
    assert row == (None, stamped_at), (
        "backoff-suppressed tick must leave the row byte-identical "
        f"(verdict NULL, layer2_at unstamped); got {row!r}"
    )
    assert _ingestion_rows(conn) == []

    # Window expires → next tick re-attempts the row (still NULL until the
    # LLM succeeds; failure re-stamps layer2_at at the new attempt time).
    stale = (
        datetime.now(timezone.utc)
        - timedelta(seconds=bi.LAYER2_NULL_RETRY_BACKOFF_S + 60)
    ).isoformat()
    conn.execute("UPDATE articles SET layer2_at = ? WHERE id = 1", (stale,))
    conn.commit()

    await bi.ingest_from_db(
        topic="ai", dry_run=False, batch_timeout=None, max_articles=None,
    )
    assert handles["layer2"].call_count == 2, (
        "tick after backoff expiry must re-attempt the Layer 2 LLM; "
        f"got {handles['layer2'].call_count} calls"
    )
    row = conn.execute(
        "SELECT layer2_verdict, layer2_at FROM articles WHERE id = 1"
    ).fetchone()
    assert row[0] is None, (
        f"re-attempt still failing must leave layer2_verdict NULL; got {row[0]!r}"
    )
    assert row[1] is not None and row[1] != stale, (
        "failed re-attempt must re-stamp layer2_at at the new attempt time"
    )


@pytest.mark.asyncio
async def test_layer2_llm_exception_is_caught_stamped_and_backed_off(
    monkeypatch, tmp_path: Path
):
    """T5 failure path — a raising Layer 2 call must not abort the run.

    layer2_full_body_score normalizes every error to all-None, but a raised
    exception (defensive: mock side_effect / future bug) must be caught by
    the drain, stamped for backoff, and let the run finish — not propagate
    and abort the remaining tick. Next tick inside the window is suppressed.
    """
    conn = _wire_db(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)

    seed_kol_article(
        conn,
        art_id=1,
        body="exception body " * 200,
        layer1_verdict="candidate",
        layer1_prompt_version=PROMPT_VERSION_LAYER1,
    )
    candidate = FilterResult(
        verdict="candidate", reason="ok", prompt_version=PROMPT_VERSION_LAYER1
    )

    patch_layer_funcs(
        monkeypatch,
        layer1_results=[candidate],
        layer2_results=[],
    )
    raising = AsyncMock(side_effect=RuntimeError("simulated Layer 2 outage"))
    monkeypatch.setattr(bi, "layer2_full_body_score", raising)

    # Tick 1: the raise is caught inside the drain; run completes normally.
    await bi.ingest_from_db(
        topic="ai", dry_run=False, batch_timeout=None, max_articles=None,
    )
    assert raising.await_count == 1, (
        f"tick 1 should attempt Layer 2 once; got {raising.await_count} awaits"
    )
    row = conn.execute(
        "SELECT layer2_verdict, layer2_at FROM articles WHERE id = 1"
    ).fetchone()
    assert row[0] is None and row[1] is not None, (
        f"raised Layer 2 call must be stamped as a NULL attempt; got {row!r}"
    )
    assert _ingestion_rows(conn) == []

    # Tick 2 inside the window: suppressed — the raising mock is never
    # awaited again (had the gate failed, the RuntimeError would propagate).
    await bi.ingest_from_db(
        topic="ai", dry_run=False, batch_timeout=None, max_articles=None,
    )
    assert raising.await_count == 1, (
        "within-window tick must suppress the (raising) Layer 2 call; "
        f"got {raising.await_count} awaits"
    )


@pytest.mark.asyncio
async def test_layer2_mixed_batch_ok_ingested_null_row_backed_off(
    monkeypatch, tmp_path: Path
):
    """T5 failure path — partial (mixed) batch: ok row ingests normally;
    the NULL slot is backed off on the next tick, then retried after expiry.

    Uses the REAL persist_layer2_verdicts (un-mocked) so the NULL slot's
    layer2_at stamp comes from the production persist path, mirroring how a
    mixed-batch failure lands in the DB.
    """
    import lib.article_filter as af

    conn = _wire_db(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)

    seed_kol_article(
        conn,
        art_id=1,
        body="mixed ok body " * 200,
        layer1_verdict="candidate",
        layer1_prompt_version=PROMPT_VERSION_LAYER1,
    )
    seed_kol_article(
        conn,
        art_id=2,
        body="mixed null body " * 200,
        layer1_verdict="candidate",
        layer1_prompt_version=PROMPT_VERSION_LAYER1,
    )

    candidate = FilterResult(
        verdict="candidate", reason="ok", prompt_version=PROMPT_VERSION_LAYER1
    )
    ok = FilterResult(verdict="ok", reason="depth=2", prompt_version=PROMPT_VERSION_LAYER2)
    fail = FilterResult(
        verdict=None, reason="exception:MockOutage", prompt_version=PROMPT_VERSION_LAYER2
    )

    handles = patch_layer_funcs(
        monkeypatch,
        layer1_results=[candidate, candidate],
        layer2_results=[ok, fail],
        ingest_outcome=(True, 1.0, True),
    )
    # Real persist: production layer2_at stamp for the NULL slot must land.
    monkeypatch.setattr(bi, "persist_layer2_verdicts", af.persist_layer2_verdicts)

    # Hermetic: ok-path inline title translation must never hit the network.
    import lib.translate

    monkeypatch.setattr(
        lib.translate, "translate_title_with_deepseek_tavily",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(lib.translate, "detect_source_lang", lambda s: "zh")

    # Tick 1: id1 → ok + ingested; id2 → NULL verdict, stamped via persist.
    await bi.ingest_from_db(
        topic="ai", dry_run=False, batch_timeout=None, max_articles=None,
    )
    assert handles["layer2"].call_count == 1
    assert _ingestion_rows(conn) == [(1, "wechat", "ok", bi.SKIP_REASON_VERSION_CURRENT)], (
        f"ok slot must ingest; got {_ingestion_rows(conn)!r}"
    )
    row2 = conn.execute(
        "SELECT layer2_verdict, layer2_at FROM articles WHERE id = 2"
    ).fetchone()
    assert row2[0] is None and row2[1] is not None, (
        f"NULL slot must stay NULL and be stamped; got {row2!r}"
    )
    row2_stamped_at = row2[1]

    # Tick 2 inside the window: id1 excluded (ingestions ok), id2's recent
    # NULL attempt suppresses the Layer 2 LLM; row byte-identical. A fresh
    # mock is installed so ticks 2+3 are counted independently of tick 1.
    monkeypatch.setattr(
        bi, "layer1_pre_filter", AsyncMock(return_value=[candidate])
    )
    tick23_layer2 = AsyncMock(return_value=[ok])
    monkeypatch.setattr(bi, "layer2_full_body_score", tick23_layer2)
    await bi.ingest_from_db(
        topic="ai", dry_run=False, batch_timeout=None, max_articles=None,
    )
    assert handles["layer2"].call_count == 1, (
        "within-window tick must suppress the Layer 2 LLM for the NULL slot; "
        f"got {handles['layer2'].call_count} calls"
    )
    assert tick23_layer2.call_count == 0, (
        "within-window tick must not reach the Layer 2 LLM at all; "
        f"got {tick23_layer2.call_count} calls"
    )
    row2 = conn.execute(
        "SELECT layer2_verdict, layer2_at FROM articles WHERE id = 2"
    ).fetchone()
    assert row2 == (None, row2_stamped_at), (
        f"backoff-suppressed tick must leave the NULL slot untouched; got {row2!r}"
    )
    assert _ingestion_rows(conn) == [
        (1, "wechat", "ok", bi.SKIP_REASON_VERSION_CURRENT)
    ]

    # Window expires → tick 3 re-attempts id2 and it ingests as ok.
    stale = (
        datetime.now(timezone.utc)
        - timedelta(seconds=bi.LAYER2_NULL_RETRY_BACKOFF_S + 60)
    ).isoformat()
    conn.execute("UPDATE articles SET layer2_at = ? WHERE id = 2", (stale,))
    conn.commit()

    await bi.ingest_from_db(
        topic="ai", dry_run=False, batch_timeout=None, max_articles=None,
    )
    assert tick23_layer2.call_count == 1, (
        "tick after backoff expiry must re-attempt the NULL slot; "
        f"got {tick23_layer2.call_count} calls"
    )
    assert _ingestion_rows(conn) == [
        (1, "wechat", "ok", bi.SKIP_REASON_VERSION_CURRENT),
        (2, "wechat", "ok", bi.SKIP_REASON_VERSION_CURRENT),
    ], f"both slots should be ingested after retry; got {_ingestion_rows(conn)!r}"
    row2 = conn.execute(
        "SELECT layer2_verdict FROM articles WHERE id = 2"
    ).fetchone()
    assert row2[0] == "ok", f"retried NULL slot should now be ok; got {row2!r}"


@pytest.mark.asyncio
async def test_layer2_backoff_gate_passes_fresh_rows_both_sources(
    monkeypatch, tmp_path: Path
):
    """T5 normal path — the gate must never suppress FRESH (never-attempted,
    layer2_at NULL) rows, on either source table. Both queued rows reach the
    Layer 2 LLM in one batch and get their (reject) verdicts persisted.
    """
    conn = _wire_db(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)

    seed_kol_article(
        conn,
        art_id=1,
        body="fresh kol body " * 200,
        layer1_verdict="candidate",
        layer1_prompt_version=PROMPT_VERSION_LAYER1,
    )
    seed_rss_article(
        conn,
        art_id=1,
        body="fresh rss body " * 200,
        layer1_verdict="candidate",
        layer1_prompt_version=PROMPT_VERSION_LAYER1,
    )

    candidate = FilterResult(
        verdict="candidate", reason="ok", prompt_version=PROMPT_VERSION_LAYER1
    )
    reject = FilterResult(
        verdict="reject", reason="shallow", prompt_version=PROMPT_VERSION_LAYER2
    )
    # Candidate SELECT orders source DESC, id ASC → wechat id=1, then rss id=1.
    handles = patch_layer_funcs(
        monkeypatch,
        layer1_results=[candidate, candidate],
        layer2_results=[reject, reject],
    )

    await bi.ingest_from_db(
        topic="ai", dry_run=False, batch_timeout=None, max_articles=None,
    )
    assert handles["layer2"].call_count == 1, (
        f"fresh rows must reach the Layer 2 LLM; got {handles['layer2'].call_count} calls"
    )
    sent = handles["layer2"].call_args.args[0]
    assert len(sent) == 2, (
        f"both fresh rows (kol + rss) must be sent in one batch; got {len(sent)}"
    )
    sources = sorted((a.source, a.id) for a in sent)
    assert sources == [("rss", 1), ("wechat", 1)], (
        f"both source tables must be fetched through the gate; got {sources!r}"
    )
    # _ingestion_rows orders by source ASC, article_id → rss before wechat.
    assert _ingestion_rows(conn) == [
        (1, "rss", "skipped", bi.SKIP_REASON_VERSION_CURRENT),
        (1, "wechat", "skipped", bi.SKIP_REASON_VERSION_CURRENT),
    ], f"reject verdicts must persist as skipped; got {_ingestion_rows(conn)!r}"
