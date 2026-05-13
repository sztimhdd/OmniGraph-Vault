"""Shared fixtures for kb integration tests.

`fixture_db` builds a SQLite DB matching Hermes prod schema (kb-1 articles +
rss_articles + lang column + kb-2 classifications + extracted_entities tables)
populated with kb-2-shape data: 8 articles, 5 topics × 3-5 articles, 6 entities
above ENTITY-01 threshold (>=5 articles), 2 entities below threshold for
negative-test coverage.

Scope: this fixture is consumed by both unit tests (kb-2 query functions in
plan 04) and integration tests (existing kb-1 + new kb-2 SSG end-to-end in
plan 09).
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
      - Hermes prod `classifications` + `extracted_entities` (verified via SSH 2026-05-13)
      - kb-2 layer1_verdict / layer2_verdict columns on both article tables

    Data shape:
      - 5 KOL + 3 RSS = 8 articles total
      - 16 classifications spanning 5 topics (Agent / CV / LLM / NLP / RAG)
      - 6 entities above ENTITY-01 threshold (>=5 articles each)
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
                layer1_verdict TEXT,
                layer2_verdict TEXT
            );
            CREATE TABLE classifications (
                id INTEGER PRIMARY KEY,
                article_id INTEGER NOT NULL,
                source TEXT NOT NULL CHECK(source IN ('wechat','rss')),
                topic TEXT NOT NULL CHECK(topic IN ('Agent','CV','LLM','NLP','RAG')),
                depth_score INTEGER,
                classified_at TEXT,
                UNIQUE(article_id, source, topic)
            );
            CREATE TABLE extracted_entities (
                id INTEGER PRIMARY KEY,
                article_id INTEGER NOT NULL,
                source TEXT NOT NULL CHECK(source IN ('wechat','rss')),
                name TEXT NOT NULL,
                extracted_at TEXT
            );
            """
        )

        # 5 KOL articles (ids 1-5)
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
        ]
        conn.executemany(
            "INSERT INTO articles (id,title,url,body,content_hash,lang,update_time,layer1_verdict,layer2_verdict) "
            "VALUES (?,?,?,?,?,?,?,?,?)", kol_rows,
        )

        # 3 RSS articles (ids 10, 11, 12)
        rss_rows = [
            (10, "English Article Three", "https://example.com/article-three", _BODY_EN_PLAIN,
             "deadbeefcafebabe1234567890abcdef", "en", "2026-05-10 08:00:00", "2026-05-10 08:01:00",
             "candidate", "ok"),
            (11, "NLP Tooling Roundup", "https://example.com/nlp-roundup", _BODY_GENERIC_EN,
             "11111111111111111111111111111111", "en", "2026-05-09 08:00:00", "2026-05-09 08:01:00",
             "candidate", "ok"),
            (12, "CV Multimodal Vision", "https://example.com/cv-mm", _BODY_GENERIC_EN,
             "22222222222222222222222222222222", "en", "2026-05-08 08:00:00", "2026-05-08 08:01:00",
             "candidate", "ok"),
        ]
        conn.executemany(
            "INSERT INTO rss_articles (id,title,url,body,content_hash,lang,published_at,fetched_at,layer1_verdict,layer2_verdict) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)", rss_rows,
        )

        # Classifications — 5 topics, depth_score >= 2 (above TOPIC-02 cohort gate)
        # (article_id, source, topic, depth_score)
        classifications_rows = [
            # Agent: 5 articles (1, 3, 5 KOL + 10, 11 RSS)
            (1, "wechat", "Agent", 3), (3, "wechat", "Agent", 2), (5, "wechat", "Agent", 2),
            (10, "rss", "Agent", 2), (11, "rss", "Agent", 2),
            # LLM: 3 articles (1, 5 KOL + 10 RSS)
            (1, "wechat", "LLM", 2), (5, "wechat", "LLM", 3), (10, "rss", "LLM", 2),
            # RAG: 3 articles (1, 4 KOL + 10 RSS)
            (1, "wechat", "RAG", 2), (4, "wechat", "RAG", 3), (10, "rss", "RAG", 2),
            # NLP: 3 articles (2, 5 KOL + 11 RSS)
            (2, "wechat", "NLP", 2), (5, "wechat", "NLP", 2), (11, "rss", "NLP", 3),
            # CV: 2 articles (2 KOL + 12 RSS) — intentionally lower-density
            (2, "wechat", "CV", 2), (12, "rss", "CV", 3),
        ]
        for article_id, source, topic, depth in classifications_rows:
            conn.execute(
                "INSERT INTO classifications (article_id,source,topic,depth_score,classified_at) "
                "VALUES (?,?,?,?,?)", (article_id, source, topic, depth, "2026-05-12 10:00:00"),
            )

        # Extracted entities — 6 above threshold (>=5 articles each), 2 below
        above_freq_entities: dict[str, list[tuple[int, str]]] = {
            "OpenAI":    [(1, "wechat"), (3, "wechat"), (5, "wechat"), (10, "rss"), (11, "rss")],
            "LangChain": [(1, "wechat"), (3, "wechat"), (4, "wechat"), (10, "rss"), (11, "rss")],
            "LightRAG":  [(1, "wechat"), (4, "wechat"), (5, "wechat"), (10, "rss"), (11, "rss")],
            "Anthropic": [(2, "wechat"), (3, "wechat"), (5, "wechat"), (10, "rss"), (12, "rss")],
            "AutoGen":   [(1, "wechat"), (3, "wechat"), (5, "wechat"), (10, "rss"), (11, "rss")],
            "MCP":       [(1, "wechat"), (2, "wechat"), (4, "wechat"), (10, "rss"), (12, "rss")],
        }
        for name, refs in above_freq_entities.items():
            for article_id, source in refs:
                conn.execute(
                    "INSERT INTO extracted_entities (article_id,source,name,extracted_at) "
                    "VALUES (?,?,?,?)", (article_id, source, name, "2026-05-12 10:00:00"),
                )

        # Below-threshold (negative-test coverage — must NOT appear in entity pages)
        below_freq_entities: dict[str, list[tuple[int, str]]] = {
            "ObscureLib":    [(1, "wechat"), (2, "wechat")],                          # freq 2
            "OneOffMention": [(3, "wechat"), (10, "rss"), (11, "rss")],               # freq 3
        }
        for name, refs in below_freq_entities.items():
            for article_id, source in refs:
                conn.execute(
                    "INSERT INTO extracted_entities (article_id,source,name,extracted_at) "
                    "VALUES (?,?,?,?)", (article_id, source, name, "2026-05-12 10:00:00"),
                )

        conn.commit()
    finally:
        conn.close()
    return db_path


@pytest.fixture
def fixture_db(tmp_path: Path) -> Path:
    """Hermes-prod-shape SQLite DB with 8 articles + classifications + entities."""
    return build_kb2_fixture_db(tmp_path / "fixture.db")
