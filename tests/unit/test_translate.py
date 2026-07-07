"""Unit tests for lib.translate (260520-trans-inc).

Mocks lib.llm_deepseek.deepseek_model_complete and lib.translate._tavily_search
so no real DeepSeek/Tavily network calls. Uses unittest.mock per
CLAUDE.md PRINCIPLE #7 + feedback_test_mirrors_impl.md (assertions pin
behavior, not formula echoes).
"""
from __future__ import annotations

import os
# Phase 5 cross-coupling defense — must be set BEFORE any lib.* import that
# triggers lib.llm_deepseek import chain (which raises at module load if
# DEEPSEEK_API_KEY is unset). See lib/__init__.py L35.
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")

import sqlite3
from unittest.mock import AsyncMock, patch

import pytest

from lib.translate import (
    detect_source_lang,
    translate_title_with_deepseek_tavily,
)


def test_detect_source_lang_zh():
    assert detect_source_lang("我是一个中文标题") == "zh"
    # Mixed but Chinese-dominant
    assert detect_source_lang("AI Agent 的实战经验与思考") == "zh"


def test_detect_source_lang_en():
    assert detect_source_lang("I am an English title") == "en"
    assert detect_source_lang("LLM Inference at Scale: A Survey") == "en"
    # Empty / whitespace defaults to en
    assert detect_source_lang("") == "en"
    assert detect_source_lang("   \n  ") == "en"


@pytest.mark.asyncio
async def test_translate_title_fail_returns_none():
    """LLM raise -> function swallows error, returns None, never re-raises.

    This is the user-spec invariant: "翻译失败 -> NULL,不'best-effort 写半句中文'".
    Caller leaves the DB column NULL on None.
    """
    with patch("lib.translate._tavily_search", new=AsyncMock(return_value=[])), \
         patch(
             "lib.llm_deepseek.deepseek_model_complete",
             new=AsyncMock(side_effect=RuntimeError("mock LLM error")),
         ):
        result = await translate_title_with_deepseek_tavily(
            "Some Title", source_lang="en"
        )
    assert result is None


@pytest.mark.asyncio
async def test_translate_title_returns_dict_on_success():
    """Happy path: LLM returns translated string -> function returns dict."""
    with patch("lib.translate._tavily_search", new=AsyncMock(return_value=[])), \
         patch(
             "lib.llm_deepseek.deepseek_model_complete",
             new=AsyncMock(return_value="中文标题"),
         ):
        result = await translate_title_with_deepseek_tavily(
            "English Title", source_lang="en"
        )
    assert result == {"title_translated": "中文标题", "lang": "zh-CN"}


def _make_translate_test_db(tmp_path):
    """Build an empty articles+rss_articles DB matching the cron's SELECT shape.

    Schema parity with kb/data/migrations/006 + 007 — only the columns the
    cron's SELECT/UPDATE touch. Keep this in sync if the query gains new
    column dependencies (per feedback_contract_shape_change_full_audit.md).
    """
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL DEFAULT 1,
            title TEXT, body TEXT,
            layer1_verdict TEXT, layer2_verdict TEXT, layer2_at TEXT,
            body_translated TEXT, title_translated TEXT,
            translated_lang VARCHAR(5), translated_at DATETIME,
            body_rewritten TEXT, rewritten_at DATETIME
        );
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            feed_id INTEGER NOT NULL DEFAULT 1,
            title TEXT, body TEXT,
            layer1_verdict TEXT, layer2_verdict TEXT, layer2_at TEXT,
            body_translated TEXT, title_translated TEXT,
            translated_lang VARCHAR(5), translated_at DATETIME,
            body_rewritten TEXT, rewritten_at DATETIME
        );
        """
    )
    return conn


def test_select_candidate_rows_skips_fully_translated(tmp_path):
    """SELECT excludes rows where BOTH body_translated AND title_translated are set.

    Pin the SQL on production-shape data: a fully-translated row must not
    enter the candidate pool; a row missing only body or only title must.
    """
    from scripts.translate_body_cron import _select_candidate_rows

    conn = _make_translate_test_db(tmp_path)
    # id=1 fully translated -> skip; id=2 missing body -> select;
    # id=3 missing title only -> select (260528-mi6 BL-1 case);
    # rss id=10 missing both -> select.
    conn.execute(
        "INSERT INTO articles(id, title, body, layer1_verdict, layer2_verdict, "
        "layer2_at, body_translated, title_translated) VALUES "
        "(1, 't1', 'b1', 'candidate', 'ok', '2026-01-01T00:00:00Z', 'bt1', 'tt1')"
    )
    conn.execute(
        "INSERT INTO articles(id, title, body, layer1_verdict, layer2_verdict, "
        "layer2_at, body_translated, title_translated) VALUES "
        "(2, 't2', 'b2', 'candidate', 'ok', '2026-01-02T00:00:00Z', NULL, 'tt2')"
    )
    conn.execute(
        "INSERT INTO articles(id, title, body, layer1_verdict, layer2_verdict, "
        "layer2_at, body_translated, title_translated) VALUES "
        "(3, 't3', 'b3', 'candidate', 'ok', '2026-01-03T00:00:00Z', 'bt3', NULL)"
    )
    conn.execute(
        "INSERT INTO rss_articles(id, title, body, layer1_verdict, layer2_verdict, "
        "layer2_at, body_translated, title_translated) VALUES "
        "(10, 'r1', 'rb1', 'candidate', 'ok', '2026-01-04T00:00:00Z', NULL, NULL)"
    )
    conn.commit()

    rows = _select_candidate_rows(conn, limit=10)
    ids_selected = sorted(r[0] for r in rows)
    assert len(rows) == 3, f"expected 3 candidates, got {len(rows)}: {rows}"
    assert ids_selected == [2, 3, 10]
    # Tuple shape contract: (id, table, title, body, body_translated, title_translated)
    by_id = {r[0]: r for r in rows}
    assert by_id[2][4] is None and by_id[2][5] == "tt2"
    assert by_id[3][4] == "bt3" and by_id[3][5] is None
    assert by_id[10][4] is None and by_id[10][5] is None


@pytest.mark.asyncio
async def test_translate_one_row_title_only_branch(tmp_path):
    """Row with body already translated + title NULL -> only title path runs.

    260528-mi6 BL-1 case: 8 such rows on Aliyun prod. Asserts:
      - translate_body is NOT called (body already populated)
      - translate_title IS called and its result lands in title_translated
      - body_translated is unchanged (no clobber of existing translation)
    """
    import logging

    from scripts.translate_body_cron import _translate_one_row

    conn = _make_translate_test_db(tmp_path)
    conn.execute(
        "INSERT INTO articles(id, title, body, layer1_verdict, layer2_verdict, "
        "layer2_at, body_translated, title_translated) VALUES "
        "(42, 'English Title', 'english body text', 'candidate', 'ok', "
        "'2026-01-01T00:00:00Z', 'pre-existing translated body', NULL)"
    )
    conn.commit()

    row = (42, "articles", "English Title", "english body text",
           "pre-existing translated body", None)

    body_mock = AsyncMock()
    title_mock = AsyncMock(return_value={"title_translated": "中文标题", "lang": "zh-CN"})

    with patch("lib.translate.translate_body_with_deepseek_tavily", new=body_mock), \
         patch("lib.translate.translate_title_with_deepseek_tavily", new=title_mock):
        result = await _translate_one_row(
            row, conn, dry_run=False, logger=logging.getLogger("test"),
        )

    assert result == "ok"
    assert body_mock.await_count == 0, "body translate must NOT be called"
    assert title_mock.await_count == 1
    db_row = conn.execute(
        "SELECT body_translated, title_translated FROM articles WHERE id=42"
    ).fetchone()
    assert db_row == ("pre-existing translated body", "中文标题")


@pytest.mark.asyncio
async def test_translate_one_row_body_only_branch(tmp_path):
    """Row with title already translated + body NULL -> only body path runs."""
    import logging

    from scripts.translate_body_cron import _translate_one_row

    conn = _make_translate_test_db(tmp_path)
    conn.execute(
        "INSERT INTO articles(id, title, body, layer1_verdict, layer2_verdict, "
        "layer2_at, body_translated, title_translated) VALUES "
        "(7, 'Title ZH', 'body content', 'candidate', 'ok', "
        "'2026-01-01T00:00:00Z', NULL, 'Pre-existing English Title')"
    )
    conn.commit()

    row = (7, "articles", "Title ZH", "body content",
           None, "Pre-existing English Title")

    body_mock = AsyncMock(return_value={"body_translated": "translated body", "lang": "en"})
    title_mock = AsyncMock()

    with patch("lib.translate.translate_body_with_deepseek_tavily", new=body_mock), \
         patch("lib.translate.translate_title_with_deepseek_tavily", new=title_mock):
        result = await _translate_one_row(
            row, conn, dry_run=False, logger=logging.getLogger("test"),
        )

    assert result == "ok"
    assert body_mock.await_count == 1
    assert title_mock.await_count == 0, "title translate must NOT be called"
    db_row = conn.execute(
        "SELECT body_translated, title_translated FROM articles WHERE id=7"
    ).fetchone()
    assert db_row == ("translated body", "Pre-existing English Title")


@pytest.mark.asyncio
async def test_translate_one_row_title_failure_does_not_block_body(tmp_path):
    """When both fields are NULL and title path fails, body path still commits.

    Verifies the per-path try/except isolation invariant — pre-existing
    failure-safety must extend to the new title branch (RULE-IN-STONE).
    """
    import logging

    from scripts.translate_body_cron import _translate_one_row

    conn = _make_translate_test_db(tmp_path)
    conn.execute(
        "INSERT INTO articles(id, title, body, layer1_verdict, layer2_verdict, "
        "layer2_at, body_translated, title_translated) VALUES "
        "(99, 'A Title', 'A body', 'candidate', 'ok', "
        "'2026-01-01T00:00:00Z', NULL, NULL)"
    )
    conn.commit()

    row = (99, "articles", "A Title", "A body", None, None)

    body_mock = AsyncMock(return_value={"body_translated": "ok-body", "lang": "zh-CN"})
    title_mock = AsyncMock(side_effect=RuntimeError("LLM down"))

    with patch("lib.translate.translate_body_with_deepseek_tavily", new=body_mock), \
         patch("lib.translate.translate_title_with_deepseek_tavily", new=title_mock):
        result = await _translate_one_row(
            row, conn, dry_run=False, logger=logging.getLogger("test"),
        )

    assert result == "ok", "must return 'ok' when at least one path succeeds"
    db_row = conn.execute(
        "SELECT body_translated, title_translated FROM articles WHERE id=99"
    ).fetchone()
    assert db_row[0] == "ok-body"
    assert db_row[1] is None  # title path failed -> NULL preserved
