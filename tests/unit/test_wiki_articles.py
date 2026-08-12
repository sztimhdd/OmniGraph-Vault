"""W5B Task 1 tests: source-aware local article truth (kb/wiki_articles.py).

Behavior anchors from docs/superpowers/plans/2026-08-12-omnigraph-wiki-v2-w5b-autonomous-evolution.md
Task 1 and the W5B design doc (§3, §6, §8, §9, §15):

- canonical article ref = md5(url)[:10] for BOTH wechat and rss; the RSS
  32-char body content_hash is NEVER used as URL/Wiki identity;
- title fallback: title_translated (non-empty) > title > ref;
- text fallback: body (non-empty) > summary > "";
- resolver is safe when optional production columns (body, title_translated)
  are absent in fixtures — column discovery via PRAGMA table_info;
- resolve_article is source-strict; source=None only when exactly one local
  row matches the ref, ambiguity refuses;
- unsupported source raises UnsupportedArticleSource, never silent skip;
- lightrag_doc_id matches scripts/reconcile_ingestions._compute_doc_id
  semantics for both sources;
- processed_ingestions denominator = ingestions.status='ok' AND source-specific
  LightRAG doc status processed (failed/skipped/missing rows excluded);
- unknown ingestions.source blocks (raises), does not disappear;
- build_chunk_article_map maps chunk -> full-doc URL -> source-aware local
  record, retaining HTTP<->HTTPS normalization;
- known_wiki_article_refs keeps legacy valid 10-char WeChat refs and canonical
  RSS URL refs; never admits RSS 32-char body MD5;
- wiki_health accepts canonical RSS refs in the citation corpus.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from kb.wiki_articles import (
    SUPPORTED_ARTICLE_SOURCES,
    UnsupportedArticleSource,
    build_chunk_article_map,
    canonical_article_ref,
    known_wiki_article_refs,
    lightrag_doc_id,
    live_ingestion_sources,
    load_article_index,
    processed_ingestions,
    resolve_article,
)
from scripts.reconcile_ingestions import _compute_doc_id
from scripts.wiki_health import run_health


def _ref(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:10]


@pytest.fixture
def conn() -> sqlite3.Connection:
    """In-memory DB with production-shaped tables (optional cols included)."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            url TEXT,
            title TEXT,
            title_translated TEXT,
            body TEXT,
            summary TEXT,
            content_hash TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            url TEXT,
            title TEXT,
            summary TEXT,
            content_hash TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE ingestions (
            id INTEGER PRIMARY KEY,
            article_id INTEGER,
            source TEXT,
            status TEXT,
            ingested_at TEXT
        )
        """
    )
    return conn


@pytest.fixture
def minimal_conn() -> sqlite3.Connection:
    """Fixtures may lack optional columns (body, title_translated)."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, url TEXT, title TEXT, summary TEXT)"
    )
    conn.execute(
        "CREATE TABLE rss_articles (id INTEGER PRIMARY KEY, url TEXT, title TEXT, summary TEXT)"
    )
    return conn


# ---------------------------------------------------------------------------
# Identity: canonical ref derives from URL for both sources
# ---------------------------------------------------------------------------


def test_canonical_article_ref_is_lowercase_md5_url_prefix() -> None:
    url = "https://mp.weixin.qq.com/s/W5B-Test"
    ref = canonical_article_ref(url)
    assert ref == hashlib.md5(url.encode()).hexdigest()[:10]
    assert ref == ref.lower()
    assert len(ref) == 10
    assert all(c in "0123456789abcdef" for c in ref)


def test_rss_canonical_ref_comes_from_url_not_content_hash(conn) -> None:
    url = "https://example.com/rss/a"
    conn.execute(
        "INSERT INTO rss_articles(id, title, url, content_hash, summary) VALUES (1, ?, ?, ?, ?)",
        ("RSS title", url, "f" * 32, "rss summary"),
    )
    idx = load_article_index(conn)
    ref = hashlib.md5(url.encode()).hexdigest()[:10]
    assert idx[("rss", ref)]["ref"] == ref
    assert idx[("rss", ref)]["ref"] != "f" * 32


def test_wechat_canonical_ref_derived_from_url(conn) -> None:
    url = "https://mp.weixin.qq.com/s/w5b-wechat"
    conn.execute(
        "INSERT INTO articles(id, url, title, content_hash) VALUES (7, ?, ?, ?)",
        (url, "WX title", _ref(url)),
    )
    idx = load_article_index(conn)
    rec = idx[("wechat", _ref(url))]
    assert rec["source"] == "wechat"
    assert rec["article_id"] == 7
    assert rec["ref"] == _ref(url)
    assert rec["url"] == url


# ---------------------------------------------------------------------------
# Title/text fallbacks incl. missing optional columns
# ---------------------------------------------------------------------------


def test_title_translated_wins_over_title(conn) -> None:
    conn.execute(
        "INSERT INTO articles(id, url, title, title_translated, body, summary) "
        "VALUES (1, ?, ?, ?, ?, ?)",
        ("https://mp.weixin.qq.com/s/t1", "中文标题", "English title", "body text", "summary text"),
    )
    rec = load_article_index(conn)[("wechat", _ref("https://mp.weixin.qq.com/s/t1"))]
    assert rec["title"] == "English title"


def test_title_falls_back_when_translated_empty(conn) -> None:
    conn.execute(
        "INSERT INTO articles(id, url, title, title_translated) VALUES (2, ?, ?, ?)",
        ("https://mp.weixin.qq.com/s/t2", "中文标题", ""),
    )
    rec = load_article_index(conn)[("wechat", _ref("https://mp.weixin.qq.com/s/t2"))]
    assert rec["title"] == "中文标题"


def test_body_wins_over_summary(conn) -> None:
    conn.execute(
        "INSERT INTO rss_articles(id, url, title, summary) VALUES (1, ?, ?, ?)",
        ("https://example.com/rss/body", "RSS T", "short summary"),
    )
    rec = load_article_index(conn)[("rss", _ref("https://example.com/rss/body"))]
    assert rec["text"] == "short summary"


def test_rss_text_falls_back_to_summary_when_no_body_column(minimal_conn) -> None:
    minimal_conn.execute(
        "INSERT INTO rss_articles(id, url, title, summary) VALUES (1, ?, ?, ?)",
        ("https://example.com/rss/min", "RSS T", "the only text"),
    )
    rec = load_article_index(minimal_conn)[("rss", _ref("https://example.com/rss/min"))]
    assert rec["title"] == "RSS T"
    assert rec["text"] == "the only text"


def test_resolver_works_when_optional_columns_absent(minimal_conn) -> None:
    """PRAGMA table_info discovery: no body/title_translated columns at all."""
    minimal_conn.execute(
        "INSERT INTO articles(id, url, title, summary) VALUES (1, ?, ?, ?)",
        ("https://mp.weixin.qq.com/s/min", "Minimal title", "minimal summary"),
    )
    idx = load_article_index(minimal_conn)
    rec = idx[("wechat", _ref("https://mp.weixin.qq.com/s/min"))]
    assert rec["title"] == "Minimal title"
    assert rec["text"] == "minimal summary"


def test_wechat_text_falls_back_to_summary(conn) -> None:
    conn.execute(
        "INSERT INTO articles(id, url, title, body, summary) VALUES (3, ?, ?, ?, ?)",
        ("https://mp.weixin.qq.com/s/t3", "T3", "", "s3"),
    )
    rec = load_article_index(conn)[("wechat", _ref("https://mp.weixin.qq.com/s/t3"))]
    assert rec["text"] == "s3"


# ---------------------------------------------------------------------------
# Strict resolution + ambiguity
# ---------------------------------------------------------------------------


def test_resolve_article_source_scoped_lookup(conn) -> None:
    url = "https://example.com/shared/url"
    conn.execute(
        "INSERT INTO articles(id, url, title) VALUES (1, ?, ?)",
        (url, "WX record"),
    )
    conn.execute(
        "INSERT INTO rss_articles(id, url, title) VALUES (1, ?, ?)",
        (url, "RSS record"),
    )
    idx = load_article_index(conn)
    rss_rec = resolve_article(idx, _ref(url), source="rss")
    assert rss_rec is not None
    assert rss_rec["source"] == "rss"
    assert rss_rec["title"] == "RSS record"
    wx_rec = resolve_article(idx, _ref(url), source="wechat")
    assert wx_rec["source"] == "wechat"
    assert wx_rec["title"] == "WX record"


def test_resolve_article_source_none_unique_ref_succeeds(conn) -> None:
    url = "https://mp.weixin.qq.com/s/unique"
    conn.execute(
        "INSERT INTO articles(id, url, title) VALUES (1, ?, ?)",
        (url, "Only one"),
    )
    rec = resolve_article(load_article_index(conn), _ref(url))
    assert rec is not None
    assert rec["source"] == "wechat"


def test_resolve_article_source_none_ambiguous_ref_refuses(conn) -> None:
    url = "https://example.com/ambiguous"
    conn.execute(
        "INSERT INTO articles(id, url, title) VALUES (1, ?, ?)",
        (url, "WX record"),
    )
    conn.execute(
        "INSERT INTO rss_articles(id, url, title) VALUES (1, ?, ?)",
        (url, "RSS record"),
    )
    idx = load_article_index(conn)
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_article(idx, _ref(url))


def test_resolve_article_missing_ref_returns_none(conn) -> None:
    assert resolve_article({}, "deadbeef00") is None
    assert resolve_article({}, "deadbeef00", source="rss") is None


# ---------------------------------------------------------------------------
# Unsupported source
# ---------------------------------------------------------------------------


def test_unsupported_source_raises_for_doc_id() -> None:
    with pytest.raises(UnsupportedArticleSource):
        lightrag_doc_id("kol", "https://example.com/x")
    with pytest.raises(UnsupportedArticleSource):
        lightrag_doc_id("github", "https://example.com/x")


def test_unsupported_source_raises_for_resolve(conn) -> None:
    with pytest.raises(UnsupportedArticleSource):
        resolve_article({}, "0123456789", source="kol")


def test_supported_sources_tuple_explicit() -> None:
    assert SUPPORTED_ARTICLE_SOURCES == ("wechat", "rss")


# ---------------------------------------------------------------------------
# LightRAG doc-id parity with reconcile_ingestions
# ---------------------------------------------------------------------------


def test_lightrag_doc_id_matches_reconcile_semantics() -> None:
    for source in ("wechat", "rss"):
        url = f"https://example.com/{source}/doc"
        assert lightrag_doc_id(source, url) == f"{source}_{_ref(url)}"
        # byte-for-byte parity with the existing reconciliation formula
        assert lightrag_doc_id(source, url) == _compute_doc_id(url, source)


def test_live_ingestion_sources_distinct(conn) -> None:
    for i, (source, status) in enumerate(
        [("wechat", "ok"), ("rss", "ok"), ("wechat", "failed")], start=1
    ):
        conn.execute(
            "INSERT INTO ingestions(id, article_id, source, status, ingested_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (i, i, source, status, "2026-08-12T10:00:00"),
        )
    assert live_ingestion_sources(conn) == {"wechat", "rss"}


# ---------------------------------------------------------------------------
# processed_ingestions: status=ok AND LightRAG processed denominator
# ---------------------------------------------------------------------------


@pytest.fixture
def lightrag_dir(tmp_path: Path) -> Path:
    return tmp_path / "lightrag_storage"


def _write_doc_status(lightrag_dir: Path, mapping: dict) -> None:
    lightrag_dir.mkdir(parents=True, exist_ok=True)
    (lightrag_dir / "kv_store_doc_status.json").write_text(
        json.dumps(mapping), encoding="utf-8"
    )


def test_processed_ingestions_denominator_parity(conn, lightrag_dir) -> None:
    """Only status='ok' rows whose source-specific doc_status is processed."""
    wx_url = "https://mp.weixin.qq.com/s/ok-a"
    rss_b_url = "https://example.com/rss/b"
    rss_c_url = "https://example.com/rss/c"
    wx_fail_url = "https://mp.weixin.qq.com/s/failed"
    rss_skip_url = "https://example.com/rss/skipped"

    conn.execute(
        "INSERT INTO articles(id, url, title) VALUES (1, ?, ?), (4, ?, ?)",
        (wx_url, "A", wx_fail_url, "Failed WX"),
    )
    conn.execute(
        "INSERT INTO rss_articles(id, url, title) VALUES (2, ?, ?), (3, ?, ?), (5, ?, ?)",
        (rss_b_url, "B", rss_c_url, "C", rss_skip_url, "Skipped RSS"),
    )
    rows = [
        (1, 1, "wechat", "ok"),
        (2, 2, "rss", "ok"),
        (3, 3, "rss", "ok"),
        (4, 4, "wechat", "failed"),
        (5, 5, "rss", "skipped"),
    ]
    for row in rows:
        conn.execute(
            "INSERT INTO ingestions(id, article_id, source, status, ingested_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (*row, "2026-08-12T10:00:00"),
        )

    _write_doc_status(
        lightrag_dir,
        {
            lightrag_doc_id("wechat", wx_url): {"status": "processed"},
            lightrag_doc_id("rss", rss_b_url): {"status": "processed"},
            lightrag_doc_id("rss", rss_c_url): {"status": "failed"},
            # wx_fail_url and rss_skip_url intentionally absent (missing status)
        },
    )

    processed = processed_ingestions(conn, lightrag_dir)
    refs = {p["ref"] for p in processed}
    assert refs == {_ref(wx_url), _ref(rss_b_url)}
    assert {p["source"] for p in processed} == {"wechat", "rss"}
    # doc_id parity with reconcile semantics on every returned row
    for p in processed:
        assert p["doc_id"] == _compute_doc_id(p["url"], p["source"]) == lightrag_doc_id(
            p["source"], p["url"]
        )


def test_processed_ingestions_unknown_source_blocks(conn, lightrag_dir) -> None:
    conn.execute(
        "INSERT INTO rss_articles(id, url, title) VALUES (1, ?, ?)",
        ("https://example.com/rss/x", "X"),
    )
    conn.execute(
        "INSERT INTO ingestions(id, article_id, source, status, ingested_at) "
        "VALUES (1, 1, 'kol', 'ok', '2026-08-12T10:00:00')"
    )
    _write_doc_status(lightrag_dir, {})
    with pytest.raises(UnsupportedArticleSource):
        processed_ingestions(conn, lightrag_dir)


# ---------------------------------------------------------------------------
# build_chunk_article_map: chunk -> full-doc URL -> source-aware record
# ---------------------------------------------------------------------------


@pytest.fixture
def chunk_lightrag_dir(tmp_path: Path) -> Path:
    d = tmp_path / "lightrag"
    d.mkdir(parents=True)
    (d / "kv_store_text_chunks.json").write_text(
        json.dumps(
            {
                "chunk-aaa1111": {"full_doc_id": "doc-rss"},
                "chunk-bbb2222": {"full_doc_id": "doc-wechat-http"},
                "chunk-ccc3333": {"full_doc_id": "doc-missing"},
            }
        ),
        encoding="utf-8",
    )
    (d / "kv_store_full_docs.json").write_text(
        json.dumps(
            {
                "doc-rss": {"content": "Title: RSS Doc\nURL: https://example.com/rss/a\nbody..."},
                # stored with http:// while the article row uses https:// ->
                # exercises HTTP<->HTTPS normalization
                "doc-wechat-http": {
                    "content": "Title: WX Doc\nURL: http://mp.weixin.qq.com/s/w5b-wechat\nbody..."
                },
                "doc-missing": {"content": "URL: https://example.com/not-in-db"},
            }
        ),
        encoding="utf-8",
    )
    return d


def test_build_chunk_article_map_source_aware_records(conn, chunk_lightrag_dir) -> None:
    rss_url = "https://example.com/rss/a"
    wx_url = "https://mp.weixin.qq.com/s/w5b-wechat"
    conn.execute(
        "INSERT INTO rss_articles(id, url, title, summary) VALUES (1, ?, ?, ?)",
        (rss_url, "RSS Title", "rss text"),
    )
    conn.execute(
        "INSERT INTO articles(id, url, title, body) VALUES (1, ?, ?, ?)",
        (wx_url, "WX Title", "wx body"),
    )
    mapped = build_chunk_article_map(chunk_lightrag_dir, conn)

    rss_rec = mapped["chunk-aaa1111"]
    assert rss_rec["source"] == "rss"
    assert rss_rec["ref"] == _ref(rss_url)
    assert rss_rec["url"] == rss_url
    assert rss_rec["title"] == "RSS Title"
    assert rss_rec["text"] == "rss text"
    assert rss_rec["article_id"] == 1

    # http:// in the doc content resolves against https:// stored URL
    wx_rec = mapped["chunk-bbb2222"]
    assert wx_rec["source"] == "wechat"
    assert wx_rec["ref"] == _ref(wx_url)
    assert wx_rec["title"] == "WX Title"
    assert wx_rec["text"] == "wx body"

    # unresolvable full_doc_id / URL not in local index -> absent
    assert "chunk-ccc3333" not in mapped


def test_build_chunk_article_map_missing_stores_returns_empty(tmp_path) -> None:
    empty_dir = tmp_path / "no-stores"
    empty_dir.mkdir()
    assert build_chunk_article_map(empty_dir, sqlite3.connect(":memory:")) == {}


# ---------------------------------------------------------------------------
# known_wiki_article_refs: canonical refs + legacy 10-char WeChat, no 32-char MD5
# ---------------------------------------------------------------------------


def test_known_wiki_article_refs_wechat_legacy_and_rss_canonical(conn) -> None:
    wx_url = "https://mp.weixin.qq.com/s/legacy"
    rss_url = "https://example.com/rss/canonical"
    conn.execute(
        "INSERT INTO articles(id, url, title, content_hash) VALUES (1, ?, ?, ?)",
        (wx_url, "WX", _ref(wx_url)),  # legacy WeChat content_hash is 10-char
    )
    conn.execute(
        "INSERT INTO rss_articles(id, url, title, content_hash) VALUES (1, ?, ?, ?)",
        (rss_url, "RSS", "f" * 32),  # 32-char body MD5 must never be admitted
    )
    refs = known_wiki_article_refs(conn)
    assert _ref(wx_url) in refs
    assert _ref(rss_url) in refs
    assert "f" * 32 not in refs


def test_known_wiki_article_refs_never_admits_32_char_hashes(conn) -> None:
    conn.execute(
        "INSERT INTO articles(id, url, title, content_hash) VALUES (1, ?, ?, ?)",
        ("https://mp.weixin.qq.com/s/x", "WX", "a" * 32),
    )
    conn.execute(
        "INSERT INTO rss_articles(id, url, title, content_hash) VALUES (1, ?, ?, ?)",
        ("https://example.com/rss/y", "RSS", "b" * 32),
    )
    refs = known_wiki_article_refs(conn)
    assert not any(len(r) == 32 for r in refs)
    assert all(len(r) == 10 for r in refs)


# ---------------------------------------------------------------------------
# wiki_health: canonical RSS refs accepted, 32-char body MD5 rejected
# ---------------------------------------------------------------------------


def _health_wiki_page(rss_ref: str) -> str:
    return f"""---
title: RSS Cited
created: 2026-08-01
last_updated: 2026-08-12
sources:
  - id: 1
    type: article
    ref: {rss_ref}
    title: RSS Article
confidence_level: high
---

# RSS Cited

Body citing the RSS article. [^1]
"""


def test_wiki_health_accepts_canonical_rss_ref(tmp_path: Path) -> None:
    rss_url = "https://example.com/rss/health"
    db_path = tmp_path / "kol_scan.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE rss_articles (id INTEGER PRIMARY KEY, url TEXT, title TEXT, content_hash TEXT)"
        )
        conn.execute(
            "INSERT INTO rss_articles(id, url, title, content_hash) VALUES (1, ?, ?, ?)",
            (rss_url, "RSS Article", "f" * 32),
        )
    entities = tmp_path / "entities"
    entities.mkdir()
    (entities / "rss-cited.md").write_text(
        _health_wiki_page(_ref(rss_url)), encoding="utf-8"
    )

    findings = run_health(tmp_path, db_path=db_path)
    assert findings["summary"]["db_hashes_loaded"] == 1
    assert not any(
        "not in DB corpus" in e for e in findings["errors"] + findings["warns"]
    )


def test_wiki_health_rejects_rss_32_char_body_md5(tmp_path: Path) -> None:
    """A citation using the 32-char body MD5 stays foreign — never corpus."""
    rss_url = "https://example.com/rss/health"
    db_path = tmp_path / "kol_scan.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE rss_articles (id INTEGER PRIMARY KEY, url TEXT, title TEXT, content_hash TEXT)"
        )
        conn.execute(
            "INSERT INTO rss_articles(id, url, title, content_hash) VALUES (1, ?, ?, ?)",
            (rss_url, "RSS Article", "f" * 32),
        )
    entities = tmp_path / "entities"
    entities.mkdir()
    (entities / "rss-bad.md").write_text(
        _health_wiki_page("f" * 32), encoding="utf-8"
    )

    findings = run_health(tmp_path, db_path=db_path)
    assert any(
        "not in DB corpus" in w and ("f" * 32) in w for w in findings["warns"]
    )
