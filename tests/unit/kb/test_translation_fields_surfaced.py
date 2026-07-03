"""kb-v2.2-7 Wave 1: ArticleRecord + API surface translation fields.

Validates that:
  1. ArticleRecord exposes title_translated / body_translated / translated_lang
     (kb-v2.2-7 A9 — site-language-driven rendering reads these directly).
  2. _record_to_list_item emits title_translated + translated_lang in the
     /api/articles JSON response.
  3. Tightened DATA-07 (A6) excludes L1='candidate' L2 IS NULL rows.
  4. _row_to_record_kol/_rss tolerate older SELECT lists (defensive _row_get).
"""
from __future__ import annotations

import sqlite3
from dataclasses import fields

import pytest

from kb.api_routers.articles import _record_to_list_item
from kb.data.article_query import (
    ArticleRecord,
    _row_to_record_kol,
    _row_to_record_rss,
    list_articles,
)


# ---- ArticleRecord shape ----------------------------------------------------


def test_article_record_exposes_translation_fields():
    """ArticleRecord has title_translated, body_translated, translated_lang."""
    field_names = {f.name for f in fields(ArticleRecord)}
    assert "title_translated" in field_names
    assert "body_translated" in field_names
    assert "translated_lang" in field_names


def test_article_record_translation_fields_default_to_none():
    """Translation fields default to None (untranslated state)."""
    rec = ArticleRecord(
        id=1, source="wechat", title="t", url="u", body="b",
        content_hash="abcd012345", lang="zh-CN", update_time="2026-01-01",
    )
    assert rec.title_translated is None
    assert rec.body_translated is None
    assert rec.translated_lang is None


def test_article_record_carries_translation_when_populated():
    rec = ArticleRecord(
        id=1, source="wechat", title="标题", url="u", body="正文",
        content_hash="abcd012345", lang="zh-CN", update_time="2026-01-01",
        title_translated="Title", body_translated="Body", translated_lang="en",
    )
    assert rec.title_translated == "Title"
    assert rec.body_translated == "Body"
    assert rec.translated_lang == "en"


# ---- _record_to_list_item API surface --------------------------------------


def test_list_item_emits_translation_fields_when_populated():
    rec = ArticleRecord(
        id=1, source="wechat", title="标题", url="u", body="b",
        content_hash="abcd012345", lang="zh-CN", update_time="2026-01-01",
        title_translated="Title", translated_lang="en",
    )
    item = _record_to_list_item(rec)
    assert item["title_translated"] == "Title"
    assert item["translated_lang"] == "en"


def test_list_item_emits_null_translation_when_not_translated():
    rec = ArticleRecord(
        id=1, source="wechat", title="标题", url="u", body="b",
        content_hash="abcd012345", lang="zh-CN", update_time="2026-01-01",
    )
    item = _record_to_list_item(rec)
    assert item["title_translated"] is None
    assert item["translated_lang"] is None


# ---- Tightened DATA-07 (A6) -------------------------------------------------


@pytest.fixture
def tightened_fixture_conn():
    """Schema-complete fixture with one L2='ok' positive + one L2 IS NULL negative."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            body TEXT,
            content_hash TEXT,
            lang TEXT,
            update_time TEXT,
            layer1_verdict TEXT,
            layer2_verdict TEXT,
            body_translated TEXT,
            title_translated TEXT,
            translated_lang VARCHAR(5),
            translated_at DATETIME,
            body_cleaned TEXT,
            body_repositioned TEXT,
            body_rewritten TEXT,
            rewritten_at DATETIME
        );
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            body TEXT,
            content_hash TEXT,
            lang TEXT,
            published_at TEXT,
            fetched_at TEXT,
            layer1_verdict TEXT,
            layer2_verdict TEXT,
            body_translated TEXT,
            title_translated TEXT,
            translated_lang VARCHAR(5),
            translated_at DATETIME,
            body_cleaned TEXT,
            body_rewritten TEXT,
            rewritten_at DATETIME
        );
        """
    )
    # KOL: 1 positive (L2='ok'), 1 negative (L2 IS NULL — tightened-excluded)
    conn.execute(
        "INSERT INTO articles VALUES "
        "(1, 'positive', 'u/1', 'real body', 'hashpos001', 'zh-CN', '2026-05-01', "
        "'candidate', 'ok', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)"
    )
    conn.execute(
        "INSERT INTO articles VALUES "
        "(2, 'l2_null_neg', 'u/2', 'real body', 'hashneg001', 'zh-CN', '2026-05-02', "
        "'candidate', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)"
    )
    # RSS: same shape
    conn.execute(
        "INSERT INTO rss_articles VALUES "
        "(10, 'rss_positive', 'r/10', 'rss body', "
        "'10101010101010101010101010101010', 'en', '2026-05-03', '2026-05-03', "
        "'candidate', 'ok', NULL, NULL, NULL, NULL, NULL, NULL, NULL)"
    )
    conn.execute(
        "INSERT INTO rss_articles VALUES "
        "(11, 'rss_l2_null_neg', 'r/11', 'rss body', "
        "'11111111111111111111111111111111', 'en', '2026-05-04', '2026-05-04', "
        "'candidate', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)"
    )
    conn.commit()
    return conn


def test_tightened_data07_excludes_l2_null_kol(tightened_fixture_conn):
    """A6: L1='candidate' AND L2 IS NULL → excluded under tightened rule."""
    results = list_articles(source="wechat", conn=tightened_fixture_conn, limit=100)
    ids = {r.id for r in results}
    assert 1 in ids, "L2='ok' KOL row must be visible"
    assert 2 not in ids, "L2 IS NULL KOL row must be EXCLUDED under tightened DATA-07"


def test_tightened_data07_excludes_l2_null_rss(tightened_fixture_conn):
    results = list_articles(source="rss", conn=tightened_fixture_conn, limit=100)
    ids = {r.id for r in results}
    assert 10 in ids, "L2='ok' RSS row must be visible"
    assert 11 not in ids, "L2 IS NULL RSS row must be EXCLUDED under tightened DATA-07"


def test_tightened_data07_combined_both_sources_only_l2_ok(tightened_fixture_conn):
    """list_articles() merged across both sources returns only L2='ok' rows."""
    results = list_articles(conn=tightened_fixture_conn, limit=100)
    assert len(results) == 2
    assert {r.id for r in results} == {1, 10}


# ---- Defensive _row_get on legacy SELECT lists -----------------------------


def test_row_to_record_kol_tolerates_legacy_select_without_translation_cols():
    """Older SELECT lists that don't include translation columns must still produce
    a valid ArticleRecord (translation fields fall back to None).
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Schema HAS translation cols but SELECT does NOT include them
    conn.executescript(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY, title TEXT, url TEXT, body TEXT,
            content_hash TEXT, lang TEXT, update_time TEXT,
            title_translated TEXT, body_translated TEXT, translated_lang TEXT
        );
        INSERT INTO articles VALUES (1, 't', 'u', 'b', 'h', 'en', '2026-01-01',
            'TT', 'BT', 'zh-CN');
        """
    )
    row = conn.execute(
        "SELECT id, title, url, body, content_hash, lang, update_time FROM articles"
    ).fetchone()
    rec = _row_to_record_kol(row)
    assert rec.title_translated is None  # legacy SELECT didn't read translation columns
    assert rec.body_translated is None
    assert rec.translated_lang is None
    conn.close()
