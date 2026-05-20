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


def test_translate_body_skip_already_translated(tmp_path):
    """The cron's SELECT excludes rows where body_translated IS NOT NULL.

    Pin the SQL behavior on production-shape data: 1 row with body_translated
    populated should NOT be selected; 1 row with NULL should be selected.
    Mirrors the production SQL in scripts/translate_body_cron.py:_select_candidate_rows.
    """
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    # Schema parity with kb/data/migrations/006 + 007 — only the columns
    # the cron's SELECT touches. Keep this in sync if the query gains
    # new column dependencies (per feedback_contract_shape_change_full_audit.md).
    conn.executescript(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL DEFAULT 1,
            title TEXT, body TEXT,
            layer1_verdict TEXT, layer2_verdict TEXT, layer2_at TEXT,
            body_translated TEXT, title_translated TEXT,
            translated_lang VARCHAR(5), translated_at DATETIME
        );
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            feed_id INTEGER NOT NULL DEFAULT 1,
            title TEXT, body TEXT,
            layer1_verdict TEXT, layer2_verdict TEXT, layer2_at TEXT,
            body_translated TEXT, title_translated TEXT,
            translated_lang VARCHAR(5), translated_at DATETIME
        );
        """
    )
    # Two rows: one already translated (must skip), one not (must pick up)
    conn.execute(
        "INSERT INTO articles(id, title, body, layer1_verdict, layer2_verdict, "
        "layer2_at, body_translated) VALUES "
        "(1, 't1', 'b1', 'candidate', 'ok', '2026-01-01T00:00:00Z', 'already done')"
    )
    conn.execute(
        "INSERT INTO articles(id, title, body, layer1_verdict, layer2_verdict, "
        "layer2_at, body_translated) VALUES "
        "(2, 't2', 'b2', 'candidate', 'ok', '2026-01-02T00:00:00Z', NULL)"
    )
    # And one rss row with NULL too — so the UNION ALL is non-trivial
    conn.execute(
        "INSERT INTO rss_articles(id, title, body, layer1_verdict, layer2_verdict, "
        "layer2_at, body_translated) VALUES "
        "(10, 'r1', 'rb1', 'candidate', 'ok', '2026-01-03T00:00:00Z', NULL)"
    )
    conn.commit()

    rows = list(
        conn.execute(
            """
            SELECT id, table_name, title, body
              FROM (
                SELECT id, 'articles' AS table_name, title, body, layer2_at
                  FROM articles
                 WHERE layer1_verdict='candidate' AND layer2_verdict='ok'
                   AND body IS NOT NULL AND body != ''
                   AND body_translated IS NULL
                UNION ALL
                SELECT id, 'rss_articles' AS table_name, title, body, layer2_at
                  FROM rss_articles
                 WHERE layer1_verdict='candidate' AND layer2_verdict='ok'
                   AND body IS NOT NULL AND body != ''
                   AND body_translated IS NULL
              )
             ORDER BY layer2_at ASC, id ASC
             LIMIT 10
            """
        )
    )
    # Only id=2 (articles) and id=10 (rss_articles) selected — id=1 has body_translated set
    ids_selected = sorted(r[0] for r in rows)
    tables_selected = sorted(r[1] for r in rows)
    assert len(rows) == 2
    assert ids_selected == [2, 10]
    assert tables_selected == ["articles", "rss_articles"]
