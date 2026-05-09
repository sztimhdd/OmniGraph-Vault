"""LF-1.9 + LF-2.8 unit tests for lib.article_filter Layer 1 / Layer 2.

Layer 1 (LF-1.9) test mapping (REQUIREMENTS § LF-1.9):

    a) test_layer1_batch_of_30_persists_all
       — happy path: 30-article batch, all verdicts returned, persisted to DB
    b) test_layer1_timeout_all_null
       — asyncio.TimeoutError → all results have verdict=None, reason='timeout'
    c) test_layer1_partial_json_all_null
       — LLM returns truncated JSON → all results NULL, reason='non_json'
    d) test_layer1_row_count_mismatch_all_null
       — LLM returns 29 entries for 30 inputs → all NULL, reason='row_count_mismatch'
    e) test_layer1_prompt_version_bump_invalidates_prior
       — _build_topic_filter_query SQL re-selects rows whose layer1_prompt_version
         differs from the current PROMPT_VERSION_LAYER1 constant

Layer 2 (LF-2.8) test mapping (REQUIREMENTS § LF-2.8):

    a) test_layer2_batch_of_5_persists_all
       — happy path: 5-article batch spanning all 4 spike buckets;
         decision rule (relevant && depth>=2 → 'ok', else 'reject')
         applied; verdicts persisted to articles.layer2_*
    b) test_layer2_timeout_all_null
       — asyncio.TimeoutError → all results verdict=None reason='timeout'
    c) test_layer2_partial_json_all_null
       — LLM returns truncated JSON → all NULL reason='non_json'
    d) test_layer2_row_count_mismatch_all_null
       — LLM returns 4 entries for 5 inputs → all NULL reason='row_count_mismatch'
    e) test_layer2_prompt_version_bump_invalidates_prior
       — bumping PROMPT_VERSION_LAYER2 in test fixture forces re-eval semantics
         (verified via persist round-trip + manual SQL re-select)
    f) test_layer2_reject_writes_skipped_via_persist_round_trip
       — persist_layer2_verdicts writes verdict='reject' correctly; downstream
         ingest-loop wiring (ir-2-01 _drain_layer2_queue) performs the
         ingestions(status='skipped') INSERT — that wiring is covered by close-out
         smoke; this test pins only the persistence contract for reject.

Plus one structural test for the FilterResult dataclass (frozen + 3-field shape)
and two regressions per layer (empty batch / over-max raises).

These supersede the 7 placeholder tests committed by V35-FOUND-01 (260507-lai)
which pinned the now-removed ``passed: bool`` shape.

Tests use pytest-asyncio mode='auto' (configured in pyproject.toml) so plain
``async def test_...`` is auto-discovered. Layer 1 LLM monkeypatched at
lib.vertex_gemini_complete.vertex_gemini_model_complete; Layer 2 LLM
monkeypatched at lib.llm_deepseek.deepseek_model_complete. No network, no
credentials beyond DEEPSEEK_API_KEY=dummy needed for module import.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import FrozenInstanceError

import pytest

from lib.article_filter import (
    ArticleMeta,
    ArticleWithBody,
    FilterResult,
    LAYER1_BATCH_SIZE,
    LAYER2_BATCH_SIZE,
    PROMPT_VERSION_LAYER1,
    PROMPT_VERSION_LAYER2,
    layer1_pre_filter,
    layer2_full_body_score,
    persist_layer1_verdicts,
    persist_layer2_verdicts,
)


# ----------------------------- helpers -------------------------------------

def _meta(i: int, source: str = "wechat") -> ArticleMeta:
    return ArticleMeta(
        id=i,
        source=source,  # type: ignore[arg-type]
        title=f"article {i}",
        summary=f"summary {i}",
        content_length=None,
    )


def _fake_llm_factory(
    *,
    response: str | None = None,
    raise_exc: BaseException | None = None,
):
    """Return an async function suitable for monkeypatching the LLM call."""
    async def _fake(prompt, **kwargs):  # noqa: ANN001
        if raise_exc is not None:
            raise raise_exc
        return response

    return _fake


def _setup_articles_table(conn: sqlite3.Connection) -> None:
    """Create the minimal articles + rss_articles schema needed for persistence
    tests. Mirrors data/kol_scan.db column subset relevant to layer1_*."""
    conn.executescript(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            title TEXT,
            layer1_verdict TEXT NULL,
            layer1_reason TEXT NULL,
            layer1_at TEXT NULL,
            layer1_prompt_version TEXT NULL
        );
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            title TEXT,
            layer1_verdict TEXT NULL,
            layer1_reason TEXT NULL,
            layer1_at TEXT NULL,
            layer1_prompt_version TEXT NULL
        );
        """
    )


# ------------------ structural test (dataclass) ----------------------------

def test_filter_result_is_frozen_three_field() -> None:
    """FilterResult is frozen and has the post-ir-1 3-field shape."""
    r = FilterResult(verdict="candidate", reason="ok", prompt_version="v")
    assert r.verdict == "candidate"
    assert r.reason == "ok"
    assert r.prompt_version == "v"
    with pytest.raises(FrozenInstanceError):
        r.verdict = "reject"  # type: ignore[misc]


# ----------------- LF-1.9.a — happy-path 30-batch --------------------------

async def test_layer1_batch_of_30_persists_all(monkeypatch) -> None:
    arts = [_meta(i) for i in range(1, LAYER1_BATCH_SIZE + 1)]

    response = json.dumps([
        {"id": i, "source": "wechat",
         "verdict": "candidate" if i % 3 == 0 else "reject",
         "reason": "test_reason"}
        for i in range(1, LAYER1_BATCH_SIZE + 1)
    ], ensure_ascii=False)

    monkeypatch.setattr(
        "lib.vertex_gemini_complete.vertex_gemini_model_complete",
        _fake_llm_factory(response=response),
    )

    results = await layer1_pre_filter(arts)
    assert len(results) == LAYER1_BATCH_SIZE
    assert all(r.verdict in ("candidate", "reject") for r in results)
    assert all(r.prompt_version == PROMPT_VERSION_LAYER1 for r in results)

    # Persist + verify rows in :memory: DB
    conn = sqlite3.connect(":memory:")
    _setup_articles_table(conn)
    for a in arts:
        conn.execute(
            "INSERT INTO articles(id, title) VALUES (?, ?)",
            (a.id, a.title),
        )
    conn.commit()

    persist_layer1_verdicts(conn, arts, results)

    rows = conn.execute(
        "SELECT id, layer1_verdict, layer1_prompt_version FROM articles"
    ).fetchall()
    assert len(rows) == LAYER1_BATCH_SIZE
    for _id, verdict, pv in rows:
        assert verdict in ("candidate", "reject")
        assert pv == PROMPT_VERSION_LAYER1


# ----------------- LF-1.9.b — timeout → all NULL ---------------------------

async def test_layer1_timeout_all_null(monkeypatch) -> None:
    arts = [_meta(i) for i in range(1, 6)]

    monkeypatch.setattr(
        "lib.vertex_gemini_complete.vertex_gemini_model_complete",
        _fake_llm_factory(raise_exc=asyncio.TimeoutError()),
    )

    results = await layer1_pre_filter(arts)
    assert len(results) == 5
    assert all(r.verdict is None for r in results)
    assert all(r.reason == "timeout" for r in results)
    assert all(r.prompt_version == PROMPT_VERSION_LAYER1 for r in results)


# ----------------- LF-1.9.c — partial JSON → all NULL ----------------------

async def test_layer1_partial_json_all_null(monkeypatch) -> None:
    arts = [_meta(i) for i in range(1, 11)]

    truncated_response = '[{"id": 1, "source": "wechat", "verdict": "candidate"'
    monkeypatch.setattr(
        "lib.vertex_gemini_complete.vertex_gemini_model_complete",
        _fake_llm_factory(response=truncated_response),
    )

    results = await layer1_pre_filter(arts)
    assert len(results) == 10
    assert all(r.verdict is None for r in results)
    assert all(r.reason == "non_json" for r in results)


# ----------------- LF-1.9.d — row count mismatch → all NULL ----------------

async def test_layer1_row_count_mismatch_all_null(monkeypatch) -> None:
    arts = [_meta(i) for i in range(1, LAYER1_BATCH_SIZE + 1)]  # 30 articles

    short_response = json.dumps([
        {"id": i, "source": "wechat", "verdict": "candidate", "reason": "x"}
        for i in range(1, LAYER1_BATCH_SIZE)  # 29 entries — one missing
    ], ensure_ascii=False)
    monkeypatch.setattr(
        "lib.vertex_gemini_complete.vertex_gemini_model_complete",
        _fake_llm_factory(response=short_response),
    )

    results = await layer1_pre_filter(arts)
    assert len(results) == LAYER1_BATCH_SIZE
    assert all(r.verdict is None for r in results)
    assert all(r.reason == "row_count_mismatch" for r in results)


# ----------------- LF-1.9.e — prompt_version bump re-selects ---------------

def test_layer1_prompt_version_bump_invalidates_prior() -> None:
    """Candidate SQL re-selects rows whose layer1_prompt_version != current."""
    from batch_ingest_from_spider import _build_topic_filter_query

    sql, params = _build_topic_filter_query([])
    assert "layer1_verdict IS NULL" in sql
    assert "layer1_prompt_version" in sql
    assert params[0] == PROMPT_VERSION_LAYER1

    # Behavioral check: simulate a row with stale prompt_version is still
    # candidate-selected (prompt_version mismatch path).
    # ir-4 dual-source: SQL also queries rss_articles + rss_feeds, so the
    # fixture must declare them (empty is fine — UNION ALL of zero RSS
    # rows + KOL rows still returns KOL rows).
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            account_id INTEGER REFERENCES accounts(id),
            title TEXT, url TEXT, body TEXT, digest TEXT,
            layer1_verdict TEXT NULL, layer1_reason TEXT NULL,
            layer1_at TEXT NULL, layer1_prompt_version TEXT NULL
        );
        CREATE TABLE rss_feeds (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY, feed_id INTEGER NOT NULL,
            title TEXT, url TEXT, body TEXT, summary TEXT,
            layer1_verdict TEXT NULL, layer1_prompt_version TEXT NULL
        );
        CREATE TABLE ingestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'wechat'
                CHECK (source IN ('wechat', 'rss')),
            status TEXT NOT NULL,
            UNIQUE (article_id, source)
        );
        INSERT INTO accounts VALUES (1, 'acct');
        INSERT INTO articles(id, account_id, title, url, body, digest,
                             layer1_verdict, layer1_prompt_version)
            VALUES (10, 1, 't', 'u', '', 'd',
                    'candidate', 'old_prompt_version_v0');
        INSERT INTO articles(id, account_id, title, url, body, digest)
            VALUES (11, 1, 't2', 'u2', '', 'd2');
        """
    )
    rows = list(conn.execute(sql, params))
    ids = sorted(r[0] for r in rows)
    # Both rows are candidates: id=10 because prompt_version differs;
    # id=11 because layer1_verdict is NULL.
    # rss_articles is empty so the RSS UNION branch contributes 0 rows.
    assert ids == [10, 11]


# ----------------- regression — empty batch returns [] ---------------------

async def test_layer1_empty_batch_no_op() -> None:
    results = await layer1_pre_filter([])
    assert results == []


# ----------------- regression — over-size batch raises ---------------------

async def test_layer1_over_max_raises() -> None:
    arts = [_meta(i) for i in range(LAYER1_BATCH_SIZE + 5)]
    with pytest.raises(ValueError, match="Layer 1 batch size"):
        await layer1_pre_filter(arts)


# ============================================================================
# LF-2.8 — Layer 2 unit tests
# ============================================================================

# ----------------------------- Layer 2 helpers -----------------------------

def _with_body(i: int, body: str | None = None, source: str = "wechat") -> ArticleWithBody:
    return ArticleWithBody(
        id=i,
        source=source,  # type: ignore[arg-type]
        title=f"article {i}",
        body=body if body is not None else f"Body content for article {i}.",
    )


def _setup_articles_with_layer2(conn: sqlite3.Connection) -> None:
    """Schema with both layer1_* and layer2_* columns for round-trip tests."""
    conn.executescript(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            title TEXT,
            layer1_verdict TEXT NULL, layer1_reason TEXT NULL,
            layer1_at TEXT NULL, layer1_prompt_version TEXT NULL,
            layer2_verdict TEXT NULL, layer2_reason TEXT NULL,
            layer2_at TEXT NULL, layer2_prompt_version TEXT NULL
        );
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            title TEXT,
            layer1_verdict TEXT NULL, layer1_reason TEXT NULL,
            layer1_at TEXT NULL, layer1_prompt_version TEXT NULL,
            layer2_verdict TEXT NULL, layer2_reason TEXT NULL,
            layer2_at TEXT NULL, layer2_prompt_version TEXT NULL
        );
        """
    )


# ----------------- LF-2.8.a — happy-path 5-article batch -------------------

async def test_layer2_batch_of_5_persists_all(monkeypatch) -> None:
    arts = [
        _with_body(383, body="架构源码解读 + 推理算法详解 + 数学推导..."),
        _with_body(336, body="我用 DeepSeek + Claude Code 写了个工具,分享体验..."),
        _with_body(535, body="QT5 + OpenCV4.8 + 深度学习路线图..."),
        _with_body(625, body="CLAUDE.md 最佳实践指南:实战配置 + 案例拆解..."),
        _with_body(693, body="读完 Kimi 新论文:MoE 路由 + KV cache 优化深度解读..."),
    ]

    # LLM returns: ok / reject / reject / ok / ok per spike-style decision rule
    response = json.dumps([
        {"id": 383, "depth_score": 3, "relevant": True,  "reason": "架构深度解读"},
        {"id": 336, "depth_score": 1, "relevant": True,  "reason": "工具体验软文,无机制"},
        {"id": 535, "depth_score": 1, "relevant": False, "reason": "CV路线图,命中视觉规则"},
        {"id": 625, "depth_score": 2, "relevant": True,  "reason": "实战配置指南"},
        {"id": 693, "depth_score": 3, "relevant": True,  "reason": "MoE推理深度解读"},
    ], ensure_ascii=False)

    monkeypatch.setattr(
        "lib.llm_deepseek.deepseek_model_complete",
        _fake_llm_factory(response=response),
    )

    results = await layer2_full_body_score(arts)
    assert len(results) == 5
    expected_verdicts = ["ok", "reject", "reject", "ok", "ok"]
    actual_verdicts = [r.verdict for r in results]
    assert actual_verdicts == expected_verdicts, (
        f"expected {expected_verdicts}, got {actual_verdicts}"
    )
    assert all(r.prompt_version == PROMPT_VERSION_LAYER2 for r in results)

    # Persist + verify
    conn = sqlite3.connect(":memory:")
    _setup_articles_with_layer2(conn)
    for a in arts:
        conn.execute("INSERT INTO articles(id, title) VALUES (?, ?)", (a.id, a.title))
    conn.commit()

    persist_layer2_verdicts(conn, arts, results)

    rows = conn.execute(
        "SELECT id, layer2_verdict, layer2_prompt_version FROM articles ORDER BY id"
    ).fetchall()
    persisted = {r[0]: (r[1], r[2]) for r in rows}
    for a, expected_verdict in zip(arts, expected_verdicts):
        v, pv = persisted[a.id]
        assert v == expected_verdict, f"id={a.id}: persisted {v} != expected {expected_verdict}"
        assert pv == PROMPT_VERSION_LAYER2


# ----------------- LF-2.8.b — timeout → all NULL ---------------------------

async def test_layer2_timeout_all_null(monkeypatch) -> None:
    arts = [_with_body(i) for i in range(1, 4)]

    monkeypatch.setattr(
        "lib.llm_deepseek.deepseek_model_complete",
        _fake_llm_factory(raise_exc=asyncio.TimeoutError()),
    )

    results = await layer2_full_body_score(arts)
    assert len(results) == 3
    assert all(r.verdict is None for r in results)
    assert all(r.reason == "timeout" for r in results)
    assert all(r.prompt_version == PROMPT_VERSION_LAYER2 for r in results)


# ----------------- LF-2.8.c — partial / non-JSON → all NULL ---------------

async def test_layer2_partial_json_all_null(monkeypatch) -> None:
    arts = [_with_body(i) for i in range(1, 6)]

    truncated_response = '[{"id": 1, "depth_score": 2, "relevant": true'
    monkeypatch.setattr(
        "lib.llm_deepseek.deepseek_model_complete",
        _fake_llm_factory(response=truncated_response),
    )

    results = await layer2_full_body_score(arts)
    assert len(results) == 5
    assert all(r.verdict is None for r in results)
    assert all(r.reason == "non_json" for r in results)


# ----------------- LF-2.8.d — row count mismatch → all NULL ----------------

async def test_layer2_row_count_mismatch_all_null(monkeypatch) -> None:
    arts = [_with_body(i) for i in range(1, LAYER2_BATCH_SIZE + 1)]  # 5

    short_response = json.dumps([
        {"id": i, "depth_score": 2, "relevant": True, "reason": "x"}
        for i in range(1, LAYER2_BATCH_SIZE)  # 4 entries — one short
    ], ensure_ascii=False)
    monkeypatch.setattr(
        "lib.llm_deepseek.deepseek_model_complete",
        _fake_llm_factory(response=short_response),
    )

    results = await layer2_full_body_score(arts)
    assert len(results) == LAYER2_BATCH_SIZE
    assert all(r.verdict is None for r in results)
    assert all(r.reason == "row_count_mismatch" for r in results)


# ----------------- LF-2.8.e — prompt_version bump invalidates -------------

def test_layer2_prompt_version_bump_invalidates_prior() -> None:
    """Persisting with current PROMPT_VERSION_LAYER2 + then re-reading shows
    that an older row (different prompt_version) would be re-selected by an
    SQL predicate of the form layer2_verdict IS NULL OR layer2_prompt_version
    IS NOT current. This pins the persist + read invariant."""
    conn = sqlite3.connect(":memory:")
    _setup_articles_with_layer2(conn)

    arts = [_with_body(10), _with_body(11)]
    for a in arts:
        conn.execute("INSERT INTO articles(id, title) VALUES (?, ?)", (a.id, a.title))
    conn.commit()

    # Manually simulate a row tagged with an OLD prompt version.
    conn.execute(
        "UPDATE articles SET layer2_verdict = 'ok', layer2_prompt_version = 'old_v0' WHERE id = 10"
    )
    conn.commit()

    # Persist BOTH rows with the CURRENT version (overwrites id=10 stale row too).
    results = [
        FilterResult(verdict="ok", reason="x", prompt_version=PROMPT_VERSION_LAYER2),
        FilterResult(verdict="reject", reason="y", prompt_version=PROMPT_VERSION_LAYER2),
    ]
    persist_layer2_verdicts(conn, arts, results)

    # After persist, both rows should have current version. Verify selection
    # rule on a hypothetical NEW stale row would catch only stale prompt_version.
    conn.execute(
        "INSERT INTO articles(id, title, layer2_verdict, layer2_prompt_version) "
        "VALUES (12, 't12', 'ok', 'older_v0')"
    )
    conn.execute(
        "INSERT INTO articles(id, title) VALUES (13, 't13')"  # NULL verdict
    )
    conn.commit()

    re_eval_sql = """
        SELECT id FROM articles
        WHERE layer2_verdict IS NULL
           OR layer2_prompt_version IS NOT ?
        ORDER BY id
    """
    re_eval_ids = [r[0] for r in conn.execute(re_eval_sql, (PROMPT_VERSION_LAYER2,))]
    # id=12 (stale prompt_version) + id=13 (NULL verdict) selected for re-eval.
    # id=10, 11 were just persisted with current version → NOT re-selected.
    assert re_eval_ids == [12, 13]


# ----------------- LF-2.8.f — reject persists correctly --------------------

def test_layer2_reject_writes_skipped_via_persist_round_trip() -> None:
    """persist_layer2_verdicts writes verdict='reject' to articles.layer2_verdict.
    Downstream wiring (ir-2-01 _drain_layer2_queue) reads the persisted verdict
    and writes ingestions(status='skipped'). This unit test pins ONLY the
    persistence contract for reject-shape FilterResults."""
    conn = sqlite3.connect(":memory:")
    _setup_articles_with_layer2(conn)
    arts = [_with_body(20), _with_body(21)]
    for a in arts:
        conn.execute("INSERT INTO articles(id, title) VALUES (?, ?)", (a.id, a.title))
    conn.commit()

    results = [
        FilterResult(verdict="reject", reason="软文,无机制",
                     prompt_version=PROMPT_VERSION_LAYER2),
        FilterResult(verdict="ok", reason="架构解读",
                     prompt_version=PROMPT_VERSION_LAYER2),
    ]
    persist_layer2_verdicts(conn, arts, results)

    rows = conn.execute(
        "SELECT id, layer2_verdict, layer2_reason FROM articles ORDER BY id"
    ).fetchall()
    assert rows[0] == (20, "reject", "软文,无机制")
    assert rows[1] == (21, "ok", "架构解读")


# ----------------- regression — empty batch returns [] ---------------------

async def test_layer2_empty_batch_no_op() -> None:
    results = await layer2_full_body_score([])
    assert results == []


# ----------------- regression — over-size batch raises ---------------------

async def test_layer2_over_max_raises() -> None:
    arts = [_with_body(i) for i in range(LAYER2_BATCH_SIZE + 2)]  # 7
    with pytest.raises(ValueError, match="Layer 2 batch size"):
        await layer2_full_body_score(arts)
