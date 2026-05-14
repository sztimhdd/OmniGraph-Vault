"""Shared fixtures for kb integration tests.

`fixture_db` builds a SQLite DB matching Hermes prod schema (kb-1 articles +
rss_articles + lang column + kb-2 classifications + extracted_entities tables)
populated with kb-2-shape data: 8 articles, 5 topics × 3-5 articles, 6 entities
above ENTITY-01 threshold (>=5 articles), 2 entities below threshold for
negative-test coverage.

Scope: this fixture is consumed by both unit tests (kb-2 query functions in
plan 04) and integration tests (existing kb-1 + new kb-2 SSG end-to-end in
plan 09).

Schema source-of-truth (verified 2026-05-14 against Hermes prod via SSH +
`.dev-runtime/data/kol_scan.db` SCP from Hermes):
  - `extracted_entities`: (id, article_id, entity_name, entity_type,
    extracted_at) — NO `source` column, NO `name` column. KOL-ONLY (no rows
    reference rss_articles.id by design; rss_extracted_entities does not
    exist).
  - `classifications`: (id, article_id, topic, depth_score, relevant,
    excluded, reason, classified_at, depth, topics, rationale) — NO `source`
    column. KOL-ONLY (no rows reference rss_articles.id by design).
  - RSS classifications: stored on rss_articles.topics (JSON-encoded list)
    and rss_articles.depth columns directly. `rss_classifications` table
    exists in prod schema but is unused (0 rows on Hermes prod 2026-05-14).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


# ---- Body strings — reused by kb-1 + kb-2 tests ----

_BODY_WITH_LOCALHOST = (
    "# Test Article One\n\n"
    "Some leading paragraph with enough words to be a reasonable description "
    "for OG meta extraction so the fallback path does not trigger.\n\n"
    "![local image](http://localhost:8765/abc/img.png)\n\n"
    "More body text after the image with additional content to ensure the "
    "200-character description has plenty to work with."
)
_BODY_SHORT_FOR_OG_FALLBACK = "![](http://localhost:8765/img.png)"
_BODY_EN_PLAIN = (
    "# English Article Three\n\n"
    "This is an English-language article about agent technology and tooling. "
    "It contains a meaningful chunk of prose suitable for og:description "
    "extraction in the SSG export pipeline tests."
)
_BODY_GENERIC_ZH = "# 中文文章\n\n人工智能和大语言模型相关讨论。"
_BODY_GENERIC_EN = "# English Generic\n\nDiscussion of LangChain and OpenAI tooling for agents."


def build_kb2_fixture_db(db_path: Path) -> Path:
    """Build SQLite fixture matching Hermes prod schema with kb-2 data.

    Schema mirrors:
      - kb-1-02 post-migration `articles` + `rss_articles` (with `lang` column)
      - Hermes prod `classifications` (KOL-only) — verified via SSH 2026-05-14
      - Hermes prod `extracted_entities` (KOL-only, `entity_name`) — verified
        via SSH 2026-05-14
      - kb-2 layer1_verdict / layer2_verdict columns on both article tables
      - RSS classifications via rss_articles.topics (JSON list) + .depth

    Data shape:
      - 5 KOL + 3 RSS = 8 articles total
      - 11 classifications spanning 5 topics (Agent / CV / LLM / NLP / RAG) —
        KOL-only per prod schema
      - RSS topic membership via rss_articles.topics (JSON list) + .depth
      - 6 entities above ENTITY-01 threshold (>=5 articles each) — KOL-only
        article_id refs (extracted_entities is KOL-only per prod schema)
      - 2 entities below threshold (freq 2-3) for negative coverage
      - Every article has layer1='candidate' OR layer2='ok' (TOPIC-02 cohort gate)
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                body TEXT,
                content_hash TEXT,
                lang TEXT,
                update_time INTEGER,
                layer1_verdict TEXT,
                layer2_verdict TEXT
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
                topics TEXT,
                depth INTEGER,
                layer1_verdict TEXT,
                layer2_verdict TEXT
            );
            CREATE TABLE classifications (
                id INTEGER PRIMARY KEY,
                article_id INTEGER NOT NULL,
                topic TEXT NOT NULL CHECK(topic IN ('Agent','CV','LLM','NLP','RAG')),
                depth_score INTEGER,
                relevant INTEGER DEFAULT 0,
                excluded INTEGER DEFAULT 0,
                reason TEXT,
                classified_at TEXT,
                depth INTEGER,
                topics TEXT,
                rationale TEXT,
                UNIQUE(article_id, topic)
            );
            CREATE TABLE extracted_entities (
                id INTEGER PRIMARY KEY,
                article_id INTEGER NOT NULL,
                entity_name TEXT NOT NULL,
                entity_type TEXT,
                extracted_at TEXT
            );
            """
        )

        # 5 KOL articles (ids 1-5) — DATA-07 positive cases
        # KOL ids deliberately disjoint from RSS ids to avoid prod-shape
        # id-collision risk where the same id exists in both tables.
        # (id, title, url, body, content_hash, lang, update_time, l1, l2)
        kol_rows = [
            (1, "测试文章一", "https://mp.weixin.qq.com/s/test1", _BODY_WITH_LOCALHOST,
             "abc1234567", "zh-CN", 1778270400, "candidate", "ok"),
            (2, "Image Only Post Title For Fallback", "https://mp.weixin.qq.com/s/test2",
             _BODY_SHORT_FOR_OG_FALLBACK, None, "en", 1778180400, "candidate", None),
            (3, "Agent 框架对比", "https://mp.weixin.qq.com/s/test3", _BODY_GENERIC_ZH,
             "kol3000003a", "zh-CN", 1778090400, "candidate", "ok"),
            (4, "RAG 检索增强生成实践", "https://mp.weixin.qq.com/s/test4", _BODY_GENERIC_ZH,
             "kol4000004b", "zh-CN", 1778000400, "candidate", "ok"),
            (5, "LLM Reasoning Patterns", "https://mp.weixin.qq.com/s/test5", _BODY_GENERIC_EN,
             "kol5000005c", "en", 1777910400, "candidate", "ok"),
            # DATA-07 negative-case KOL rows — must be EXCLUDED by filter
            # id=99: body empty AND layer1='reject' (fails 2/3 conditions)
            (99, "REJECTED EMPTY BODY", "https://mp.weixin.qq.com/s/neg99", "",
             "neg9999999", "en", 1777800000, "reject", None),
            # id=98: real body, layer1 candidate, layer2='reject' (fails 1/3)
            (98, "LAYER2 REJECTED", "https://mp.weixin.qq.com/s/neg98", "real body content here",
             "neg9898989", "en", 1777700000, "candidate", "reject"),
        ]
        conn.executemany(
            "INSERT INTO articles (id,title,url,body,content_hash,lang,update_time,layer1_verdict,layer2_verdict) "
            "VALUES (?,?,?,?,?,?,?,?,?)", kol_rows,
        )

        # 3 RSS articles (ids 10, 11, 12) — DATA-07 positive cases
        # RSS topic membership via .topics JSON list + .depth (no
        # classifications table rows for RSS — KOL-only per prod).
        rss_rows = [
            (10, "English Article Three", "https://example.com/article-three", _BODY_EN_PLAIN,
             "deadbeefcafebabe1234567890abcdef", "en", "2026-05-10 08:00:00", "2026-05-10 08:01:00",
             '["Agent","LLM","RAG"]', 2, "candidate", "ok"),
            (11, "NLP Tooling Roundup", "https://example.com/nlp-roundup", _BODY_GENERIC_EN,
             "11111111111111111111111111111111", "en", "2026-05-09 08:00:00", "2026-05-09 08:01:00",
             '["Agent","NLP"]', 2, "candidate", "ok"),
            (12, "CV Multimodal Vision", "https://example.com/cv-mm", _BODY_GENERIC_EN,
             "22222222222222222222222222222222", "en", "2026-05-08 08:00:00", "2026-05-08 08:01:00",
             '["CV"]', 3, "candidate", "ok"),
            # DATA-07 negative-case RSS rows — must be EXCLUDED by filter
            # id=97: body NULL (fails body-present condition)
            (97, "NULL BODY RSS", "https://example.com/neg97", None,
             "97979797979797979797979797979797", "en", "2026-05-07 08:00:00", "2026-05-07 08:01:00",
             None, None, "candidate", "ok"),
            # id=96: real body, layer1='reject' (fails layer1 condition)
            (96, "LAYER1 REJECT RSS", "https://example.com/neg96", "real RSS body content",
             "96969696969696969696969696969696", "en", "2026-05-06 08:00:00", "2026-05-06 08:01:00",
             None, None, "reject", None),
        ]
        conn.executemany(
            "INSERT INTO rss_articles (id,title,url,body,content_hash,lang,published_at,fetched_at,"
            "topics,depth,layer1_verdict,layer2_verdict) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rss_rows,
        )

        # KOL classifications — 5 topics, depth_score >= 2 (TOPIC-02 cohort gate).
        # KOL-ONLY per prod schema (no `source` column; RSS uses rss_articles.topics).
        # (article_id, topic, depth_score)
        classifications_rows = [
            # Agent: 3 KOL articles (1, 3, 5)
            (1, "Agent", 3), (3, "Agent", 2), (5, "Agent", 2),
            # LLM: 2 KOL articles (1, 5)
            (1, "LLM", 2), (5, "LLM", 3),
            # RAG: 2 KOL articles (1, 4)
            (1, "RAG", 2), (4, "RAG", 3),
            # NLP: 2 KOL articles (2, 5)
            (2, "NLP", 2), (5, "NLP", 2),
            # CV: 1 KOL article (2) — RSS article 12 supplies the second via rss_articles.topics
            (2, "CV", 2),
        ]
        for article_id, topic, depth in classifications_rows:
            conn.execute(
                "INSERT INTO classifications (article_id,topic,depth_score,classified_at) "
                "VALUES (?,?,?,?)", (article_id, topic, depth, "2026-05-12 10:00:00"),
            )

        # Extracted entities — 6 above threshold (>=5 articles each), 2 below.
        # KOL-ONLY per prod schema (no `source` column, no `name` column;
        # extracted_entities holds entity_name; rss_extracted_entities does
        # not exist — RSS articles have no entity extraction in v1.0).
        # Entity refs frequencies tuned so 6 entities cross threshold via 5 KOL
        # articles repeated; before fix, RSS rows added a 6th data point per
        # entity. Post-fix: each above-threshold entity must hit ≥5 distinct
        # KOL article_ids — so we reuse all 5 KOL ids (1, 3, 4, 5, 2 mixed).
        above_freq_entities: dict[str, list[int]] = {
            "OpenAI":    [1, 3, 5, 4, 2],   # freq 5 (KOL ids 1, 2, 3, 4, 5)
            "LangChain": [1, 3, 4, 5, 2],   # freq 5
            "LightRAG":  [1, 4, 5, 3, 2],   # freq 5
            "Anthropic": [2, 3, 5, 1, 4],   # freq 5
            "AutoGen":   [1, 3, 5, 4, 2],   # freq 5
            "MCP":       [1, 2, 4, 3, 5],   # freq 5
        }
        for name, refs in above_freq_entities.items():
            for article_id in refs:
                conn.execute(
                    "INSERT INTO extracted_entities (article_id,entity_name,extracted_at) "
                    "VALUES (?,?,?)", (article_id, name, "2026-05-12 10:00:00"),
                )

        # Below-threshold (negative-test coverage — must NOT appear in entity pages)
        below_freq_entities: dict[str, list[int]] = {
            "ObscureLib":    [1, 2],          # freq 2
            "OneOffMention": [3, 4, 5],       # freq 3
        }
        for name, refs in below_freq_entities.items():
            for article_id in refs:
                conn.execute(
                    "INSERT INTO extracted_entities (article_id,entity_name,extracted_at) "
                    "VALUES (?,?,?)", (article_id, name, "2026-05-12 10:00:00"),
                )

        conn.commit()
    finally:
        conn.close()
    return db_path


@pytest.fixture
def fixture_db(tmp_path: Path) -> Path:
    """Hermes-prod-shape SQLite DB with 8 articles + classifications + entities."""
    return build_kb2_fixture_db(tmp_path / "fixture.db")
