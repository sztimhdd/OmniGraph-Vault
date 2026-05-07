"""LF-1.9 unit tests for lib.article_filter.layer1_pre_filter.

Test mapping (REQUIREMENTS-v3.5-Ingest-Refactor.md § LF-1.9):

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

Plus one structural test for the FilterResult dataclass (frozen + 3-field shape)
and two regressions (empty batch / over-max raises).

These supersede the 7 placeholder tests committed by V35-FOUND-01 (260507-lai)
which pinned the now-removed ``passed: bool`` shape.

Tests use pytest-asyncio mode='auto' (configured in pyproject.toml) so plain
``async def test_...`` is auto-discovered. LLM dependency is monkeypatched at
its module-level symbol — no network, no credentials required.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import FrozenInstanceError

import pytest

from lib.article_filter import (
    ArticleMeta,
    FilterResult,
    LAYER1_BATCH_SIZE,
    PROMPT_VERSION_LAYER1,
    layer1_pre_filter,
    persist_layer1_verdicts,
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
        CREATE TABLE ingestions (article_id INTEGER, status TEXT);
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
