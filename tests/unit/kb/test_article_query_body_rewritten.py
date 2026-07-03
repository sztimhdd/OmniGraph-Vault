"""kb-v2.3-2: body_rewritten D-14 precedence + SELECT-site coverage tests.

Behavior-anchored (per feedback_test_mirrors_impl): each test pins an OBSERVABLE
post-condition — get_article_body's returned (body, source) and the
ArticleRecord.body_rewritten surfaced by every query path — NOT the internal
call shape. The D-14 precedence test seeds BOTH body_rewritten AND a real
final_content.md on disk and asserts body_rewritten wins, which is the exact
gate CONTEXT.md Stage 1 requires.

body_rewritten is the display-only clean LLM rewrite of the D-14 display content
(final_content.md etc.), NOT a raw-body derivative — see
decision_rewrite_display_only_kg_uses_original.md.
"""
from __future__ import annotations

import sqlite3

import pytest

from kb.data.article_query import (
    ArticleRecord,
    entity_articles_query,
    get_article_by_hash,
    get_article_body,
    list_articles,
    topic_articles_query,
)


# --------------------------------------------------------------------------
# D-14 precedence tests (get_article_body) — the CONTEXT.md Stage 1 gate
# --------------------------------------------------------------------------

def _make_kol_rec(*, body: str, body_rewritten=None, content_hash="deadbeef01") -> ArticleRecord:
    return ArticleRecord(
        id=1,
        source="wechat",
        title="t",
        url="u",
        body=body,
        content_hash=content_hash,
        lang="zh-CN",
        update_time="2026-01-01",
        publish_time=None,
        body_rewritten=body_rewritten,
    )


def test_d14_body_rewritten_wins_over_final_content_md(tmp_path, monkeypatch):
    """D14-REWRITTEN-WINS: body_rewritten set + final_content.md on disk -> rewritten wins."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", tmp_path)
    rec = _make_kol_rec(
        body="raw db body",
        body_rewritten="# Clean rewritten body\n\ngreat content",
    )
    article_dir = tmp_path / "deadbeef01"
    article_dir.mkdir()
    (article_dir / "final_content.md").write_text(
        "# filesystem body should LOSE", encoding="utf-8"
    )

    body, source = get_article_body(rec)
    assert "Clean rewritten body" in body
    assert "filesystem body should LOSE" not in body
    assert "raw db body" not in body
    assert source == "raw_markdown"


def test_d14_null_rewritten_falls_through_to_final_content_md(tmp_path, monkeypatch):
    """D14-NULL-FALLTHROUGH: body_rewritten=None + final_content.md -> file wins (legacy)."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", tmp_path)
    rec = _make_kol_rec(body="db body unused", body_rewritten=None)
    article_dir = tmp_path / "deadbeef01"
    article_dir.mkdir()
    (article_dir / "final_content.md").write_text("# Plain fs body", encoding="utf-8")

    body, source = get_article_body(rec)
    assert "Plain fs body" in body
    assert source == "vision_enriched"


def test_d14_null_rewritten_no_file_falls_through_to_db(tmp_path, monkeypatch):
    """D14-NULL-NO-FILE: body_rewritten=None + no file -> rec.body (legacy raw_markdown)."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", tmp_path)
    rec = _make_kol_rec(body="# DB body content\n\nhello", body_rewritten=None)

    body, source = get_article_body(rec)
    assert body == "# DB body content\n\nhello"
    assert source == "raw_markdown"


def test_d14_rewritten_localhost_image_url_rewritten_at_read_time(tmp_path, monkeypatch):
    """IMAGE-REWRITE-APPLIED: stored body_rewritten keeps raw localhost:8765; read path
    rewrites it to /static/img/ (same treatment as final_content.md)."""
    from kb import config as kb_config

    monkeypatch.setattr(kb_config, "KB_IMAGES_DIR", tmp_path)
    rec = _make_kol_rec(
        body="raw",
        body_rewritten="# Title\n\n![](http://localhost:8765/abc/img.png)\n\nText",
    )

    body, source = get_article_body(rec)
    assert "/static/img/abc/img.png" in body
    assert "localhost:8765" not in body
    assert source == "raw_markdown"


# --------------------------------------------------------------------------
# SELECT-site coverage — prove all query paths carry body_rewritten
# --------------------------------------------------------------------------

# Schema mirrors the conftest fixtures (only the columns the SELECTs touch),
# with body_rewritten + the DATA-07 quality columns present so the lazy
# _verify_quality_columns guard passes.
_ARTICLES_DDL = """
CREATE TABLE articles (
    id INTEGER PRIMARY KEY, title TEXT, url TEXT, body TEXT, content_hash TEXT,
    lang TEXT, update_time TEXT, layer1_verdict TEXT, layer2_verdict TEXT,
    title_translated TEXT, body_translated TEXT, translated_lang TEXT,
    body_cleaned TEXT, body_repositioned TEXT, body_rewritten TEXT, rewritten_at DATETIME
);
"""
_RSS_DDL = """
CREATE TABLE rss_articles (
    id INTEGER PRIMARY KEY, title TEXT, url TEXT, body TEXT, content_hash TEXT,
    lang TEXT, published_at TEXT, fetched_at TEXT, topics TEXT, depth INTEGER,
    layer1_verdict TEXT, layer2_verdict TEXT,
    title_translated TEXT, body_translated TEXT, translated_lang TEXT,
    body_cleaned TEXT, body_rewritten TEXT, rewritten_at DATETIME
);
"""
_CLASSIF_DDL = """
CREATE TABLE classifications (
    article_id INTEGER, topic TEXT, depth_score INTEGER, classified_at TEXT
);
"""
_ENTITIES_DDL = """
CREATE TABLE extracted_entities (
    article_id INTEGER, entity_name TEXT, extracted_at TEXT
);
"""


@pytest.fixture
def seeded_conn():
    """In-memory DB with one KOL + one RSS row carrying body_rewritten, plus a
    classification + an entity row for the KOL article (freq >= min_freq via 5 refs)."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_ARTICLES_DDL + _RSS_DDL + _CLASSIF_DDL + _ENTITIES_DDL)
    conn.execute(
        "INSERT INTO articles (id,title,url,body,content_hash,lang,update_time,"
        "layer1_verdict,layer2_verdict,body_rewritten) VALUES "
        "(1,'KOL One','https://mp.weixin.qq.com/s/k1','raw kol body','kolhash0001','zh-CN',"
        "'2026-06-01 08:00:00','candidate','ok','CLEAN KOL REWRITTEN')"
    )
    conn.execute(
        "INSERT INTO rss_articles (id,title,url,body,content_hash,lang,published_at,fetched_at,"
        "topics,depth,layer1_verdict,layer2_verdict,body_rewritten) VALUES "
        "(10,'RSS Ten','https://example.com/r10','raw rss body',"
        "'rsshash00000000000000000000000000','en','2026-06-01 08:00:00','2026-06-01 08:01:00',"
        "'[\"Agent\"]',2,'candidate','ok','CLEAN RSS REWRITTEN')"
    )
    conn.execute(
        "INSERT INTO classifications (article_id,topic,depth_score,classified_at) "
        "VALUES (1,'Agent',3,'2026-06-01 10:00:00')"
    )
    # entity_articles_query gates on COUNT(DISTINCT article_id) >= min_freq.
    # One KOL article => distinct count 1; the test calls it with min_freq=1.
    conn.execute(
        "INSERT INTO extracted_entities (article_id,entity_name,extracted_at) "
        "VALUES (1,'OpenAI','2026-06-01 10:00:00')"
    )
    conn.commit()
    yield conn
    conn.close()


def test_list_articles_carries_body_rewritten(seeded_conn):
    """SELECT-ROUNDTRIP list: both KOL + RSS list SELECTs surface body_rewritten."""
    recs = list_articles(conn=seeded_conn, limit=50)
    by_id = {r.id: r for r in recs}
    assert by_id[1].body_rewritten == "CLEAN KOL REWRITTEN"
    assert by_id[10].body_rewritten == "CLEAN RSS REWRITTEN"


def test_get_article_by_hash_kol_carries_body_rewritten(seeded_conn):
    """SELECT-ROUNDTRIP hash KOL direct."""
    rec = get_article_by_hash("kolhash0001", conn=seeded_conn)
    assert rec is not None
    assert rec.body_rewritten == "CLEAN KOL REWRITTEN"


def test_get_article_by_hash_rss_carries_body_rewritten(seeded_conn):
    """SELECT-ROUNDTRIP hash RSS direct (substr(content_hash,1,10) match)."""
    rec = get_article_by_hash("rsshash000", conn=seeded_conn)
    assert rec is not None
    assert rec.body_rewritten == "CLEAN RSS REWRITTEN"


def test_topic_query_carries_body_rewritten_kol_and_rss(seeded_conn):
    """TOPIC-ROUNDTRIP: /topic/{slug} route (topic_articles_query) carries body_rewritten
    on BOTH the KOL (a.) and RSS (r.) alias-qualified SELECTs."""
    recs = topic_articles_query("Agent", conn=seeded_conn, depth_min=2)
    by_id = {r.id: r for r in recs}
    assert by_id[1].body_rewritten == "CLEAN KOL REWRITTEN"
    assert by_id[10].body_rewritten == "CLEAN RSS REWRITTEN"


def test_entity_query_carries_body_rewritten(seeded_conn):
    """ENTITY-ROUNDTRIP: /entity/{slug} route (entity_articles_query, KOL-only) carries it."""
    recs = entity_articles_query("OpenAI", conn=seeded_conn, min_freq=1)
    by_id = {r.id: r for r in recs}
    assert 1 in by_id, "entity query should return the KOL article"
    assert by_id[1].body_rewritten == "CLEAN KOL REWRITTEN"
