"""W5B Task 6 tests: historical bootstrap discovery + exact coverage accounting.

Behavior anchors from docs/superpowers/plans/2026-08-12-omnigraph-wiki-v2-w5b-autonomous-evolution.md
Task 6 (lines 842-997) and the W5B design doc:

- denominator = ``ingestions.status='ok'`` AND LightRAG ``doc_status``
  ``processed``, keyed by the canonical article key ``(source, ref)`` where
  ``ref = md5(url)[:10]`` — never content_hash / buffer file count / wiki
  pages / top-N entities as identity;
- final accounting invariant ``eligible == represented + no_wiki_entity +
  retry_unresolved`` (no row may vanish between phase counters); uncovered
  is a placeholder bucket that the fallback resolves;
- buffer-first mapping from canonical ``<ref>_entities.json`` (first
  ``DEFAULT_BUFFER_DIRS``-style dir wins, dedupe per article by slug);
  malformed buffers fail safe: no mapping, never a crash, never silently
  represented;
- graph fallback via ``vdb_entities.json`` / ``vdb_relationships.json``
  chunk ids -> ``build_chunk_article_map`` with the W1 ``source_id`` split
  semantics, NO top-N cutoff, only for articles with no usable buffer
  mapping;
- repeated-entity noise control: a seedable entity needs >=2 DISTINCT
  eligible article keys; articles with only singleton local entities are
  uncovered and MUST reach the fallback (mapped != represented);
- bootstrap-only DeepSeek fallback: exactly one call per uncovered article,
  local title+text only, strict ``{"entities": [...]}`` JSON contract
  (0-3 string names; >3 names / malformed JSON / provider error ->
  ``retry_unresolved`` with NO truncation; empty list -> ``no_wiki_entity``;
  a singleton fallback entity may represent its article, the >=2 threshold
  does not re-apply);
- ``--bootstrap-existing`` dry-run: denominator+buffer+graph+grouping+
  uncovered only, NO fallback calls, NO writes, reports
  ``would_need_llm_fallback``;
- exit codes: bootstrap normal 0 (exact accounting, retry_unresolved==0) /
  2 (exact accounting, retry_unresolved>0) / 1 (integrity/runtime failure
  or accounting mismatch); bootstrap dry-run 0 (completed) / 1 (failure).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from kb.wiki_articles import lightrag_doc_id
from kb.wiki_compiler.models import page_digest
from scripts.wiki_evolve import (
    bootstrap_existing_discovery,
    parse_fallback_entities,
)

REPORT_KEYS = (
    "eligible_processed_ingestions",
    "mapped_via_entity_buffer",
    "mapped_via_lightrag_graph",
    "unmapped_needing_llm_fallback",
    "seeded_entity_jobs",
    "no_wiki_entity",
    "retry_unresolved",
)


def _ref(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:10]


def _open_db_file(path: Path) -> sqlite3.Connection:
    """Open a fixture DB (file or ``:memory:``) with production-shaped
    article + ingestion tables."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE ingestions ("
        "id INTEGER PRIMARY KEY, article_id INTEGER NOT NULL, "
        "source TEXT NOT NULL, status TEXT NOT NULL, "
        "ingested_at TEXT, enrichment_id TEXT)"
    )
    conn.execute(
        "CREATE TABLE articles ("
        "id INTEGER PRIMARY KEY, url TEXT, title TEXT, "
        "title_translated TEXT, body TEXT, summary TEXT, content_hash TEXT)"
    )
    conn.execute(
        "CREATE TABLE rss_articles ("
        "id INTEGER PRIMARY KEY, url TEXT, title TEXT, "
        "summary TEXT, content_hash TEXT)"
    )
    return conn


@pytest.fixture
def conn() -> sqlite3.Connection:
    """In-memory DB with production-shaped article + ingestion tables."""
    return _open_db_file(Path(":memory:"))


def _add_article(
    conn: sqlite3.Connection,
    *,
    source: str,
    article_id: int,
    url: str,
    title: str = "",
    body: str = "",
    summary: str = "",
) -> None:
    table = "articles" if source == "wechat" else "rss_articles"
    if source == "wechat":
        conn.execute(
            f"INSERT INTO {table} (id, url, title, title_translated, body, summary, content_hash)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (article_id, url, title, title, body, summary, "x" * 32),
        )
    else:
        conn.execute(
            f"INSERT INTO {table} (id, url, title, summary, content_hash)"
            " VALUES (?, ?, ?, ?, ?)",
            (article_id, url, title, summary, "x" * 32),
        )


def _add_ingestion(
    conn: sqlite3.Connection,
    *,
    ingestion_id: int,
    article_id: int,
    source: str,
    status: str,
) -> None:
    conn.execute(
        "INSERT INTO ingestions (id, article_id, source, status, ingested_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (ingestion_id, article_id, source, status, "2026-08-01 10:00:00"),
    )


def _make_lightrag_dir(
    tmp_path: Path, *, doc_status: dict[str, str] | None = None
) -> Path:
    """Synthetic LightRAG storage dir (flat doc_id -> entry status map)."""
    d = tmp_path / "lightrag"
    d.mkdir(parents=True, exist_ok=True)
    if doc_status is not None:
        (d / "kv_store_doc_status.json").write_text(
            json.dumps({doc_id: {"status": st} for doc_id, st in doc_status.items()}),
            encoding="utf-8",
        )
    return d


def _write_buffer(buf_dir: Path, ref: str, entities: list) -> Path:
    """Write a canonical ``<ref>_entities.json`` buffer file."""
    buf_dir.mkdir(parents=True, exist_ok=True)
    path = buf_dir / f"{ref}_entities.json"
    path.write_text(
        json.dumps({"raw_entities": entities}, ensure_ascii=False), encoding="utf-8"
    )
    return path


def _make_wiki(tmp_path: Path) -> Path:
    """Task 7 fixture: a wiki root with an ``entities/`` directory."""
    wiki = tmp_path / "wiki"
    (wiki / "entities").mkdir(parents=True, exist_ok=True)
    return wiki


_RICH_PAGE = """---
title: "Hermes"
created: "2026-05-20"
last_updated: "2026-05-20"
sources:
  - type: article
    ref: "deadbeef01"
    title: "deadbeef01"
    provenance: w3-entity-buffer
  - type: article
    ref: "deadbeef02"
    title: "deadbeef02"
    provenance: w3-entity-buffer
confidence_level: medium
---

# Hermes

## Definition / Overview

A detailed pre-existing synthesis paragraph with citations. [^1][^2]

## References

[^1]: **deadbeef01** — deadbeef01 (w3-entity-buffer)
[^2]: **deadbeef02** — deadbeef02 (w3-entity-buffer)
"""


# ---------------------------------------------------------------------------
# 6.1 denominator + accounting skeleton
# ---------------------------------------------------------------------------


def test_s1_denominator_processed_only_and_accounting_invariant(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """Denominator = ok+processed rows only; the final report reconciles.

    Mixed historical rows: wechat A ok+processed, rss B ok+processed,
    wechat C ok+LightRAG-failed, rss D failed+processed. Only A and B are
    eligible; C and D must never appear in any accounting bucket.
    """
    a_url = "https://mp.weixin.qq.com/s/aaaa"
    b_url = "https://example.com/rss/bbbb"
    c_url = "https://mp.weixin.qq.com/s/cccc"
    d_url = "https://example.com/rss/dddd"
    _add_article(conn, source="wechat", article_id=1, url=a_url,
                 title="A Title", body="A body.")
    _add_article(conn, source="rss", article_id=2, url=b_url,
                 title="B Title", body="B body.")
    _add_article(conn, source="wechat", article_id=3, url=c_url,
                 title="C Title", body="C body.")
    _add_article(conn, source="rss", article_id=4, url=d_url,
                 title="D Title", body="D body.")
    _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
    _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
    _add_ingestion(conn, ingestion_id=3, article_id=3, source="wechat", status="ok")
    _add_ingestion(conn, ingestion_id=4, article_id=4, source="rss", status="failed")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={
            lightrag_doc_id("wechat", a_url): "processed",
            lightrag_doc_id("rss", b_url): "processed",
            lightrag_doc_id("wechat", c_url): "failed",
            lightrag_doc_id("rss", d_url): "processed",
        },
    )

    calls: list[str] = []

    async def fake_complete(prompt: str) -> str:
        calls.append(prompt)
        return '{"entities": []}'

    report = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[tmp_path / "buf"],
            complete=fake_complete,
        )
    )

    for key in REPORT_KEYS:
        assert key in report, key
    assert report["eligible_processed_ingestions"] == 2
    assert report["unmapped_needing_llm_fallback"] == 2
    assert f"wechat/{_ref(a_url)}" in report["articles"]
    assert f"rss/{_ref(b_url)}" in report["articles"]
    assert f"wechat/{_ref(c_url)}" not in report["articles"]
    assert f"rss/{_ref(d_url)}" not in report["articles"]
    # the fallback resolved every uncovered article: no placeholder survives
    assert report["articles"][f"wechat/{_ref(a_url)}"] == "no_wiki_entity"
    assert report["articles"][f"rss/{_ref(b_url)}"] == "no_wiki_entity"
    assert len(calls) == 2, "one fallback call per uncovered article"
    represented = sum(1 for v in report["articles"].values() if v == "represented")
    assert report["eligible_processed_ingestions"] == (
        represented + report["no_wiki_entity"] + report["retry_unresolved"]
    ), "invariant: eligible == represented + no_wiki_entity + retry_unresolved"


# ---------------------------------------------------------------------------
# 6.2 buffer-first mapping
# ---------------------------------------------------------------------------


def test_s2_buffer_first_mapping_not_graph_or_fallback(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """Canonical ``<ref>_entities.json`` maps the article via the buffer.

    The article must be counted under ``mapped_via_entity_buffer`` and NOT
    graph-scanned or fallback-scanned first — even when the graph fixtures
    WOULD map the article if the implementation scanned buffer-mapped
    articles too.
    """
    a_url = "https://mp.weixin.qq.com/s/bufa"
    b_url = "https://example.com/rss/bufb"
    _add_article(conn, source="wechat", article_id=1, url=a_url,
                 title="A Title", body="A body.")
    _add_article(conn, source="rss", article_id=2, url=b_url,
                 title="B Title", body="B body.")
    _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
    _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={
            lightrag_doc_id("wechat", a_url): "processed",
            lightrag_doc_id("rss", b_url): "processed",
        },
    )
    buf = tmp_path / "buf"
    _write_buffer(buf, _ref(a_url), [{"name": "Shared Entity"}])
    _write_buffer(buf, _ref(b_url), ["Shared Entity"])  # str entry form
    # graph fixtures that WOULD map both articles if the implementation
    # scanned buffer-mapped articles — the assertions must still show 0
    (lightrag / "vdb_entities.json").write_text(
        json.dumps({"data": [{"entity_name": "Shared Entity", "source_id": "chunk-c1"}]}),
        encoding="utf-8",
    )
    (lightrag / "vdb_relationships.json").write_text(
        json.dumps({"data": []}), encoding="utf-8"
    )
    (lightrag / "kv_store_text_chunks.json").write_text(
        json.dumps({"chunk-c1": {"full_doc_id": lightrag_doc_id("wechat", a_url)}}),
        encoding="utf-8",
    )
    (lightrag / "kv_store_full_docs.json").write_text(
        json.dumps({lightrag_doc_id("wechat", a_url): {"content": f"URL: {a_url}"}}),
        encoding="utf-8",
    )

    calls: list[str] = []

    async def fake_complete(prompt: str) -> str:
        calls.append(prompt)
        return '{"entities": []}'

    report = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[buf],
            complete=fake_complete,
        )
    )

    assert report["mapped_via_entity_buffer"] == 2
    assert report["mapped_via_lightrag_graph"] == 0, (
        "graph must not be scanned for buffer-mapped articles"
    )
    assert report["unmapped_needing_llm_fallback"] == 0
    assert calls == [], "buffer-mapped articles must never reach the fallback"
    assert report["articles"][f"wechat/{_ref(a_url)}"] == "represented"
    assert report["articles"][f"rss/{_ref(b_url)}"] == "represented"
    assert "shared-entity" in report["seeded_entity_jobs"]


def test_s2_malformed_buffer_fails_safe(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """Malformed buffer files never crash the bootstrap and never map.

    Bad JSON, a document missing ``raw_entities``, a non-dict document, and
    junk list items all fail safe: the article is NOT counted as
    buffer-mapped (or represented) and stays for graph/fallback resolution.
    """
    urls = [
        "https://mp.weixin.qq.com/s/badjson",
        "https://mp.weixin.qq.com/s/noraw",
        "https://mp.weixin.qq.com/s/nondict",
        "https://mp.weixin.qq.com/s/junkitem",
    ]
    for i, url in enumerate(urls, start=1):
        _add_article(conn, source="wechat", article_id=i, url=url,
                     title=f"Title {i}", body=f"Body {i}.")
        _add_ingestion(conn, ingestion_id=i, article_id=i, source="wechat", status="ok")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={lightrag_doc_id("wechat", u): "processed" for u in urls},
    )
    buf = tmp_path / "buf"
    buf.mkdir(parents=True, exist_ok=True)
    (buf / f"{_ref(urls[0])}_entities.json").write_text(
        "{not json", encoding="utf-8"
    )
    _write_buffer(buf, _ref(urls[1]), [{"name": "X"}])
    (buf / f"{_ref(urls[1])}_entities.json").write_text(
        json.dumps({"no_raw_entities": [{"name": "X"}]}), encoding="utf-8"
    )
    (buf / f"{_ref(urls[2])}_entities.json").write_text(
        json.dumps([{"name": "X"}]), encoding="utf-8"
    )
    _write_buffer(buf, _ref(urls[3]), [42])

    calls: list[str] = []

    async def fake_complete(prompt: str) -> str:
        calls.append(prompt)
        return '{"entities": []}'

    report = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[buf],
            complete=fake_complete,
        )
    )

    assert report["mapped_via_entity_buffer"] == 0
    assert report["unmapped_needing_llm_fallback"] == 4
    assert len(calls) == 4, "every malformed-buffer article must reach the fallback"
    for url in urls:
        assert report["articles"][f"wechat/{_ref(url)}"] == "no_wiki_entity"
    assert report["seeded_entity_jobs"] == []
    represented = sum(1 for v in report["articles"].values() if v == "represented")
    assert report["eligible_processed_ingestions"] == (
        represented + report["no_wiki_entity"] + report["retry_unresolved"]
    )


# ---------------------------------------------------------------------------
# 6.3 graph fallback mapping (no top-N cutoff)
# ---------------------------------------------------------------------------


def test_s3_graph_fallback_maps_entity_and_relationship_rows_no_top_n_cutoff(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """vdb entity + relationship rows map eligible articles via chunk ids.

    - entity row: ``entity_name -> source_id`` chunks (W1 split semantics);
    - relationship row: ``source_id`` chunks attach to BOTH ``src_id`` and
      ``tgt_id`` entity names;
    - chunks -> source-aware articles via ``build_chunk_article_map``;
    - no top-N cutoff: the only mapping entity sits beyond a synthetic
      top-50 ordering and is still discovered;
    - graph discovery ignores non-eligible articles (a ghost entity whose
      chunk resolves to a LightRAG-failed article never maps or seeds).
    """
    a_url = "https://mp.weixin.qq.com/s/grapha"
    b_url = "https://example.com/rss/graphb"
    c_url = "https://mp.weixin.qq.com/s/ghostc"
    _add_article(conn, source="wechat", article_id=1, url=a_url,
                 title="A Title", body="A body.")
    _add_article(conn, source="rss", article_id=2, url=b_url,
                 title="B Title", body="B body.")
    _add_article(conn, source="wechat", article_id=3, url=c_url,
                 title="C Title", body="C body.")
    _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
    _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
    _add_ingestion(conn, ingestion_id=3, article_id=3, source="wechat", status="ok")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={
            lightrag_doc_id("wechat", a_url): "processed",
            lightrag_doc_id("rss", b_url): "processed",
            lightrag_doc_id("wechat", c_url): "failed",
        },
    )
    doc_a = lightrag_doc_id("wechat", a_url)
    doc_b = lightrag_doc_id("rss", b_url)
    doc_c = lightrag_doc_id("wechat", c_url)
    # 50 noise rows occupy the first positions; the only mapping entity is
    # at index 50 — a top-50 cutoff would miss it.
    rows = [
        {"entity_name": f"Noise Entity {i}", "source_id": f"chunk-noise-{i}"}
        for i in range(50)
    ]
    rows.append({"entity_name": "Graph Star", "source_id": "chunk-c1|chunk-c2"})
    rows.append({"entity_name": "Ghost Entity", "source_id": "chunk-c3"})
    (lightrag / "vdb_entities.json").write_text(
        json.dumps({"data": rows}), encoding="utf-8"
    )
    # relationship row: its source chunks attach to BOTH src_id and tgt_id
    (lightrag / "vdb_relationships.json").write_text(
        json.dumps(
            {
                "data": [
                    {
                        "src_id": "Rel Source",
                        "tgt_id": "Rel Target",
                        "description": "links the pair",
                        "source_id": "chunk-c2 chunk-c1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (lightrag / "kv_store_text_chunks.json").write_text(
        json.dumps(
            {
                "chunk-c1": {"full_doc_id": doc_a},
                "chunk-c2": {"full_doc_id": doc_b},
                "chunk-c3": {"full_doc_id": doc_c},
            }
        ),
        encoding="utf-8",
    )
    (lightrag / "kv_store_full_docs.json").write_text(
        json.dumps(
            {
                doc_a: {"content": f"URL: {a_url}"},
                doc_b: {"content": f"URL: {b_url}"},
                doc_c: {"content": f"URL: {c_url}"},
            }
        ),
        encoding="utf-8",
    )

    calls: list[str] = []

    async def fake_complete(prompt: str) -> str:
        calls.append(prompt)
        return '{"entities": []}'

    report = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[tmp_path / "buf"],
            complete=fake_complete,
        )
    )

    assert report["mapped_via_lightrag_graph"] == 2
    assert report["articles"][f"wechat/{_ref(a_url)}"] == "represented"
    assert report["articles"][f"rss/{_ref(b_url)}"] == "represented"
    for slug in ("graph-star", "rel-source", "rel-target"):
        assert slug in report["seeded_entity_jobs"], slug
    assert "ghost-entity" not in report["seeded_entity_jobs"]
    assert report["unmapped_needing_llm_fallback"] == 0
    assert calls == [], "graph-mapped articles must never reach the fallback"
    represented = sum(1 for v in report["articles"].values() if v == "represented")
    assert report["eligible_processed_ingestions"] == (
        represented + report["no_wiki_entity"] + report["retry_unresolved"]
    )


# ---------------------------------------------------------------------------
# 6.4 repeated-entity grouping + article coverage
# ---------------------------------------------------------------------------


def test_s4_singleton_entities_uncovered_reach_fallback(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """Only >=2-key entity groups are seedable; singleton-mapped articles
    stay uncovered and MUST reach the fallback (mapped != represented)."""
    a_url = "https://mp.weixin.qq.com/s/singlea"
    b_url = "https://example.com/rss/singleb"
    _add_article(conn, source="wechat", article_id=1, url=a_url,
                 title="A Title", body="A body.")
    _add_article(conn, source="rss", article_id=2, url=b_url,
                 title="B Title", body="B body.")
    _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
    _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={
            lightrag_doc_id("wechat", a_url): "processed",
            lightrag_doc_id("rss", b_url): "processed",
        },
    )
    buf = tmp_path / "buf"
    _write_buffer(buf, _ref(a_url), [{"name": "Only In A"}])
    _write_buffer(buf, _ref(b_url), [{"name": "Only In B"}])

    calls: list[str] = []

    async def fake_complete(prompt: str) -> str:
        calls.append(prompt)
        return '{"entities": []}'

    report = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[buf],
            complete=fake_complete,
        )
    )

    assert report["mapped_via_entity_buffer"] == 2, "both WERE buffer-mapped"
    assert report["mapped_via_lightrag_graph"] == 0
    assert report["seeded_entity_jobs"] == [], "no >=2 entity group exists"
    assert report["unmapped_needing_llm_fallback"] == 2
    assert report["articles"][f"wechat/{_ref(a_url)}"] == "no_wiki_entity"
    assert report["articles"][f"rss/{_ref(b_url)}"] == "no_wiki_entity"
    assert len(calls) == 2, "singleton-mapped articles must reach the fallback"
    represented = sum(1 for v in report["articles"].values() if v == "represented")
    assert represented == 0, "mapped != represented: coverage comes from groups"
    assert report["eligible_processed_ingestions"] == (
        represented + report["no_wiki_entity"] + report["retry_unresolved"]
    )


def test_s4_buffer_and_graph_groups_merge_for_coverage(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """A shared slug seen via buffer (A) and graph (B) forms ONE >=2 group."""
    a_url = "https://mp.weixin.qq.com/s/shareda"
    b_url = "https://example.com/rss/sharedb"
    _add_article(conn, source="wechat", article_id=1, url=a_url,
                 title="A Title", body="A body.")
    _add_article(conn, source="rss", article_id=2, url=b_url,
                 title="B Title", body="B body.")
    _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
    _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={
            lightrag_doc_id("wechat", a_url): "processed",
            lightrag_doc_id("rss", b_url): "processed",
        },
    )
    buf = tmp_path / "buf"
    _write_buffer(buf, _ref(a_url), [{"name": "Shared Entity"}])
    # graph side: the SAME slug resolves to article B only
    (lightrag / "vdb_entities.json").write_text(
        json.dumps(
            {"data": [{"entity_name": "Shared Entity", "source_id": "chunk-c1"}]}
        ),
        encoding="utf-8",
    )
    (lightrag / "vdb_relationships.json").write_text(
        json.dumps({"data": []}), encoding="utf-8"
    )
    (lightrag / "kv_store_text_chunks.json").write_text(
        json.dumps({"chunk-c1": {"full_doc_id": lightrag_doc_id("rss", b_url)}}),
        encoding="utf-8",
    )
    (lightrag / "kv_store_full_docs.json").write_text(
        json.dumps({lightrag_doc_id("rss", b_url): {"content": f"URL: {b_url}"}}),
        encoding="utf-8",
    )

    calls: list[str] = []

    async def fake_complete(prompt: str) -> str:
        calls.append(prompt)
        return '{"entities": []}'

    report = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[buf],
            complete=fake_complete,
        )
    )

    assert report["mapped_via_entity_buffer"] == 1
    assert report["mapped_via_lightrag_graph"] == 1
    assert "shared-entity" in report["seeded_entity_jobs"]
    assert report["unmapped_needing_llm_fallback"] == 0
    assert report["articles"][f"wechat/{_ref(a_url)}"] == "represented"
    assert report["articles"][f"rss/{_ref(b_url)}"] == "represented"
    assert calls == [], "grouped articles must never reach the fallback"
    represented = sum(1 for v in report["articles"].values() if v == "represented")
    assert report["eligible_processed_ingestions"] == (
        represented + report["no_wiki_entity"] + report["retry_unresolved"]
    )


# ---------------------------------------------------------------------------
# 6.5 bootstrap-only DeepSeek fallback: strict {"entities": [...]} contract
# ---------------------------------------------------------------------------


def test_s5_parse_fallback_entities_rejects_over_three_names() -> None:
    """The strict contract allows 0-3 names; MORE than 3 is invalid (None ->
    ``retry_unresolved``), never silently truncated to the first 3."""
    assert parse_fallback_entities('{"entities": []}') == []
    assert parse_fallback_entities('{"entities": ["a", "b", "c"]}') == ["a", "b", "c"]
    assert parse_fallback_entities('{"entities": ["a", "b", "c", "d"]}') is None
    assert parse_fallback_entities("{not json") is None
    assert parse_fallback_entities('{"entities": "nope"}') is None


def test_s5_fallback_over_three_names_retries_unresolved_and_seeds_nothing(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """A >3-name payload is a contract violation: the article retries and no
    entity is seeded — the model's extra names never leak into the jobs."""
    a_url = "https://mp.weixin.qq.com/s/overthree"
    _add_article(conn, source="wechat", article_id=1, url=a_url,
                 title="A Title", body="A body.")
    _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={lightrag_doc_id("wechat", a_url): "processed"},
    )

    calls: list[str] = []

    async def fake_complete(prompt: str) -> str:
        calls.append(prompt)
        return '{"entities": ["Alpha", "Beta", "Gamma", "Delta"]}'

    report = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[tmp_path / "buf"],
            complete=fake_complete,
        )
    )

    assert len(calls) == 1, "exactly one fallback call per uncovered article"
    assert report["articles"][f"wechat/{_ref(a_url)}"] == "retry_unresolved"
    assert report["retry_unresolved"] == 1
    assert report["no_wiki_entity"] == 0
    assert report["seeded_entity_jobs"] == [], "no truncation-seeded entities"
    represented = sum(1 for v in report["articles"].values() if v == "represented")
    assert report["eligible_processed_ingestions"] == (
        represented + report["no_wiki_entity"] + report["retry_unresolved"]
    )


def test_s5_fallback_provider_error_retries_unresolved(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """Provider timeout/error -> ``retry_unresolved`` with exactly one call."""
    a_url = "https://mp.weixin.qq.com/s/proverr"
    _add_article(conn, source="wechat", article_id=1, url=a_url,
                 title="A Title", body="A body.")
    _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={lightrag_doc_id("wechat", a_url): "processed"},
    )

    calls: list[str] = []

    async def fake_complete(prompt: str) -> str:
        calls.append(prompt)
        raise RuntimeError("provider boom")

    report = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[tmp_path / "buf"],
            complete=fake_complete,
        )
    )

    assert len(calls) == 1
    assert report["articles"][f"wechat/{_ref(a_url)}"] == "retry_unresolved"
    assert report["retry_unresolved"] == 1
    assert report["seeded_entity_jobs"] == []
    represented = sum(1 for v in report["articles"].values() if v == "represented")
    assert report["eligible_processed_ingestions"] == (
        represented + report["no_wiki_entity"] + report["retry_unresolved"]
    )


def test_s5_fallback_valid_singleton_entity_represents_and_seeds(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One LLM-chosen wiki-worthy entity represents its article (the >=2
    grouping threshold does not re-apply to fallback entities). The single
    call receives local title+text only and the strict JSON instruction —
    and the other network modules are poisoned (any import would raise)."""
    a_url = "https://mp.weixin.qq.com/s/singlefall"
    _add_article(conn, source="wechat", article_id=1, url=a_url,
                 title="A Title", body="A body.")
    _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={lightrag_doc_id("wechat", a_url): "processed"},
    )

    calls: list[str] = []

    async def fake_complete(prompt: str) -> str:
        calls.append(prompt)
        return '{"entities": ["Wiki Worthy Name"]}'

    for _mod in ("tavily", "openai", "httpx", "requests"):
        monkeypatch.setitem(sys.modules, _mod, None)

    report = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[tmp_path / "buf"],
            complete=fake_complete,
        )
    )

    assert len(calls) == 1
    assert "Title: A Title" in calls[0], "local title only"
    assert "A body." in calls[0], "local text only"
    assert '"entities": [' in calls[0], "strict JSON instruction"
    assert report["articles"][f"wechat/{_ref(a_url)}"] == "represented"
    assert "wiki-worthy-name" in report["seeded_entity_jobs"]
    assert report["retry_unresolved"] == 0
    represented = sum(1 for v in report["articles"].values() if v == "represented")
    assert report["eligible_processed_ingestions"] == (
        represented + report["no_wiki_entity"] + report["retry_unresolved"]
    )


# ---------------------------------------------------------------------------
# 6.6/6.7 bootstrap CLI: dry-run + exit-code contract
# ---------------------------------------------------------------------------


def _run_cli(*args: str, cwd: Path):
    """Run the script in a subprocess (same interpreter as pytest)."""
    import subprocess

    script = Path(__file__).resolve().parents[2] / "scripts" / "wiki_evolve.py"
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def test_s6_cli_bootstrap_dry_run_no_fallback_no_writes_exit_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--bootstrap-existing --dry-run``: denominator+buffer+graph+uncovered
    only. The provider module is poisoned (any import would raise) — the run
    must still exit 0 and report ``would_need_llm_fallback`` with zero
    terminal classes; DB and LightRAG files stay byte-identical."""
    from scripts.wiki_evolve import main

    db_path = tmp_path / "kol_scan.db"
    a_url = "https://mp.weixin.qq.com/s/drya"
    b_url = "https://example.com/rss/dryb"
    conn = _open_db_file(db_path)
    try:
        _add_article(conn, source="wechat", article_id=1, url=a_url,
                     title="A Title", body="A body.")
        _add_article(conn, source="rss", article_id=2, url=b_url,
                     title="B Title", body="B body.")
        _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
        _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
        conn.commit()
    finally:
        conn.close()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={
            lightrag_doc_id("wechat", a_url): "processed",
            lightrag_doc_id("rss", b_url): "processed",
        },
    )
    before_db = db_path.read_bytes()
    before_lightrag = {p.name: p.read_bytes() for p in sorted(lightrag.glob("*"))}

    monkeypatch.setitem(sys.modules, "lib.llm_deepseek", None)
    rc = main([
        "--bootstrap-existing", "--dry-run",
        "--db-path", str(db_path),
        "--lightrag-dir", str(lightrag),
    ])

    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["eligible_processed_ingestions"] == 2
    assert report["mapped_via_entity_buffer"] == 0
    assert report["mapped_via_lightrag_graph"] == 0
    assert report["unmapped_needing_llm_fallback"] == 2
    assert report["would_need_llm_fallback"] == 2
    assert report["retry_unresolved"] == 0
    assert report["no_wiki_entity"] == 0
    assert report["seeded_entity_jobs"] == []
    assert db_path.read_bytes() == before_db, "DB must stay byte-identical"
    assert {p.name: p.read_bytes() for p in sorted(lightrag.glob("*"))} == (
        before_lightrag
    ), "LightRAG files must stay byte-identical"


def test_s6_cli_bootstrap_normal_all_covered_exits_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Normal bootstrap with full graph coverage: no fallback needed, exact
    accounting, retry_unresolved == 0 -> exit 0 (provider poisoned: any
    fallback attempt would fail the run instead of hitting the network)."""
    from scripts.wiki_evolve import main

    db_path = tmp_path / "kol_scan.db"
    a_url = "https://mp.weixin.qq.com/s/covera"
    b_url = "https://example.com/rss/coverb"
    conn = _open_db_file(db_path)
    try:
        _add_article(conn, source="wechat", article_id=1, url=a_url,
                     title="A Title", body="A body.")
        _add_article(conn, source="rss", article_id=2, url=b_url,
                     title="B Title", body="B body.")
        _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
        _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
        conn.commit()
    finally:
        conn.close()
    doc_a = lightrag_doc_id("wechat", a_url)
    doc_b = lightrag_doc_id("rss", b_url)
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={doc_a: "processed", doc_b: "processed"},
    )
    (lightrag / "vdb_entities.json").write_text(
        json.dumps({
            "data": [{"entity_name": "Graph Star", "source_id": "chunk-c1|chunk-c2"}]
        }),
        encoding="utf-8",
    )
    (lightrag / "vdb_relationships.json").write_text(
        json.dumps({"data": []}), encoding="utf-8"
    )
    (lightrag / "kv_store_text_chunks.json").write_text(
        json.dumps({
            "chunk-c1": {"full_doc_id": doc_a},
            "chunk-c2": {"full_doc_id": doc_b},
        }),
        encoding="utf-8",
    )
    (lightrag / "kv_store_full_docs.json").write_text(
        json.dumps({
            doc_a: {"content": f"URL: {a_url}"},
            doc_b: {"content": f"URL: {b_url}"},
        }),
        encoding="utf-8",
    )

    monkeypatch.setitem(sys.modules, "lib.llm_deepseek", None)
    wiki = _make_wiki(tmp_path)
    rc = main([
        "--bootstrap-existing",
        "--db-path", str(db_path),
        "--lightrag-dir", str(lightrag),
        "--wiki-root", str(wiki),
    ])

    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mapped_via_lightrag_graph"] == 2
    assert report["unmapped_needing_llm_fallback"] == 0
    assert report["retry_unresolved"] == 0
    assert "graph-star" in report["seeded_entity_jobs"]
    assert report["articles"][f"wechat/{_ref(a_url)}"] == "represented"
    assert report["articles"][f"rss/{_ref(b_url)}"] == "represented"


def test_s6_cli_bootstrap_normal_provider_failure_exits_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """retry_unresolved > 0 with exact accounting -> exit 2 (retryable/
    incomplete coverage); the fallback flows through the REAL lazy
    ``lib.llm_deepseek`` seam — exactly one call per uncovered article."""
    import types

    from scripts.wiki_evolve import main

    db_path = tmp_path / "kol_scan.db"
    a_url = "https://mp.weixin.qq.com/s/retrya"
    b_url = "https://example.com/rss/retryb"
    conn = _open_db_file(db_path)
    try:
        _add_article(conn, source="wechat", article_id=1, url=a_url,
                     title="A Title", body="A body.")
        _add_article(conn, source="rss", article_id=2, url=b_url,
                     title="B Title", body="B body.")
        _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
        _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
        conn.commit()
    finally:
        conn.close()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={
            lightrag_doc_id("wechat", a_url): "processed",
            lightrag_doc_id("rss", b_url): "processed",
        },
    )

    calls: list[str] = []

    async def fake_complete(prompt: str) -> str:
        calls.append(prompt)
        raise RuntimeError("provider boom")

    monkeypatch.setitem(
        sys.modules,
        "lib.llm_deepseek",
        types.SimpleNamespace(deepseek_model_complete=fake_complete),
    )

    rc = main([
        "--bootstrap-existing",
        "--db-path", str(db_path),
        "--lightrag-dir", str(lightrag),
    ])

    assert rc == 2
    assert len(calls) == 2, "exactly one fallback call per uncovered article"
    report = json.loads(capsys.readouterr().out)
    assert report["retry_unresolved"] == 2
    represented = sum(1 for v in report["articles"].values() if v == "represented")
    assert report["eligible_processed_ingestions"] == (
        represented + report["no_wiki_entity"] + report["retry_unresolved"]
    )


def test_s6_cli_bootstrap_missing_db_exits_one_never_creates_db(
    tmp_path: Path,
) -> None:
    """Bootstrap (normal AND dry-run) with a missing ``--db-path`` exits 1
    with the standard fail-closed message and never creates the DB file."""
    missing_db = tmp_path / "no-such.db"
    for extra in ((), ("--dry-run",)):
        proc = _run_cli(
            "--bootstrap-existing", *extra,
            "--db-path", str(missing_db),
            cwd=tmp_path,
        )
        assert proc.returncode == 1, proc.stderr
        assert "database not found" in proc.stderr
        assert not missing_db.exists(), "sqlite3.connect must never create the DB"


def test_s6_cli_help_lists_bootstrap_options(tmp_path: Path) -> None:
    """``--help`` exits 0 and documents the bootstrap options."""
    proc = _run_cli("--help", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    for option in ("--bootstrap-existing", "--lightrag-dir", "--dry-run",
                   "--db-path", "--wiki-root"):
        assert option in proc.stdout, option


def test_s6_cli_bootstrap_normal_seeds_via_wiki_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Normal CLI bootstrap threads ``--wiki-root`` into the seeding phase:
    discover -> fallback -> seed -> recompute. The graph-covered job lands
    the canonical page + follow-up suggestion under the GIVEN wiki root,
    ``seeding`` exposes the engine result, and exact accounting with
    retry_unresolved == 0 exits 0."""
    from scripts.wiki_evolve import main

    db_path = tmp_path / "kol_scan.db"
    a_url = "https://mp.weixin.qq.com/s/seedwra"
    b_url = "https://example.com/rss/seedwrb"
    conn = _open_db_file(db_path)
    try:
        _add_article(conn, source="wechat", article_id=1, url=a_url,
                     title="A Title", body="A body.")
        _add_article(conn, source="rss", article_id=2, url=b_url,
                     title="B Title", body="B body.")
        _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
        _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
        conn.commit()
    finally:
        conn.close()
    doc_a = lightrag_doc_id("wechat", a_url)
    doc_b = lightrag_doc_id("rss", b_url)
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={doc_a: "processed", doc_b: "processed"},
    )
    (lightrag / "vdb_entities.json").write_text(
        json.dumps({
            "data": [{"entity_name": "Seed Star", "source_id": "chunk-c1|chunk-c2"}]
        }),
        encoding="utf-8",
    )
    (lightrag / "vdb_relationships.json").write_text(
        json.dumps({"data": []}), encoding="utf-8"
    )
    (lightrag / "kv_store_text_chunks.json").write_text(
        json.dumps({
            "chunk-c1": {"full_doc_id": doc_a},
            "chunk-c2": {"full_doc_id": doc_b},
        }),
        encoding="utf-8",
    )
    (lightrag / "kv_store_full_docs.json").write_text(
        json.dumps({
            doc_a: {"content": f"URL: {a_url}"},
            doc_b: {"content": f"URL: {b_url}"},
        }),
        encoding="utf-8",
    )
    wiki = _make_wiki(tmp_path)

    monkeypatch.setitem(sys.modules, "lib.llm_deepseek", None)
    rc = main([
        "--bootstrap-existing",
        "--db-path", str(db_path),
        "--lightrag-dir", str(lightrag),
        "--wiki-root", str(wiki),
    ])

    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    seeding = report["seeding"]
    assert seeding["seed-star"]["status"] == "suggestion"
    assert seeding["seed-star"]["suggestion_path"] and Path(
        seeding["seed-star"]["suggestion_path"]
    ).exists()
    assert (wiki / "entities" / "seed-star.md").exists(), (
        "the missing page must be created under the --wiki-root wiki"
    )
    assert report["retry_unresolved"] == 0
    assert report["articles"][f"wechat/{_ref(a_url)}"] == "represented"
    assert report["articles"][f"rss/{_ref(b_url)}"] == "represented"


def test_s6_cli_bootstrap_dry_run_wiki_root_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--bootstrap-existing --dry-run`` with ``--wiki-root`` set: the
    Task 7 seeding phase NEVER runs in dry-run — a graph-covered job
    exists (it WOULD seed in normal mode) yet the wiki root gains no
    page and no ``_suggestions`` dir, the report carries no ``seeding``
    key, and DB + LightRAG files stay byte-identical."""
    from scripts.wiki_evolve import main

    db_path = tmp_path / "kol_scan.db"
    a_url = "https://mp.weixin.qq.com/s/drywra"
    b_url = "https://example.com/rss/drywrb"
    conn = _open_db_file(db_path)
    try:
        _add_article(conn, source="wechat", article_id=1, url=a_url,
                     title="A Title", body="A body.")
        _add_article(conn, source="rss", article_id=2, url=b_url,
                     title="B Title", body="B body.")
        _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
        _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
        conn.commit()
    finally:
        conn.close()
    doc_a = lightrag_doc_id("wechat", a_url)
    doc_b = lightrag_doc_id("rss", b_url)
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={doc_a: "processed", doc_b: "processed"},
    )
    (lightrag / "vdb_entities.json").write_text(
        json.dumps({
            "data": [{"entity_name": "Dry Star", "source_id": "chunk-c1|chunk-c2"}]
        }),
        encoding="utf-8",
    )
    (lightrag / "vdb_relationships.json").write_text(
        json.dumps({"data": []}), encoding="utf-8"
    )
    (lightrag / "kv_store_text_chunks.json").write_text(
        json.dumps({
            "chunk-c1": {"full_doc_id": doc_a},
            "chunk-c2": {"full_doc_id": doc_b},
        }),
        encoding="utf-8",
    )
    (lightrag / "kv_store_full_docs.json").write_text(
        json.dumps({
            doc_a: {"content": f"URL: {a_url}"},
            doc_b: {"content": f"URL: {b_url}"},
        }),
        encoding="utf-8",
    )
    wiki = _make_wiki(tmp_path)
    before_db = db_path.read_bytes()
    before_lightrag = {p.name: p.read_bytes() for p in sorted(lightrag.glob("*"))}

    monkeypatch.setitem(sys.modules, "lib.llm_deepseek", None)
    rc = main([
        "--bootstrap-existing", "--dry-run",
        "--db-path", str(db_path),
        "--lightrag-dir", str(lightrag),
        "--wiki-root", str(wiki),
    ])

    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert "seeding" not in report, "seeding must never run in dry-run"
    assert report["would_need_llm_fallback"] == 0, "fully graph-covered"
    assert not list((wiki / "entities").glob("*.md")), (
        "no page written under the wiki root in dry-run"
    )
    assert not (wiki / "_suggestions").exists(), (
        "no suggestion dir created under the wiki root in dry-run"
    )
    assert db_path.read_bytes() == before_db, "DB must stay byte-identical"
    assert {p.name: p.read_bytes() for p in sorted(lightrag.glob("*"))} == (
        before_lightrag
    ), "LightRAG files must stay byte-identical"


# ---------------------------------------------------------------------------
# 7.1 W5B Task 7: job_sources — every discovered job carries its article keys
# ---------------------------------------------------------------------------


def test_s7_job_sources_cover_seedable_groups_and_fallback_singletons(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """``job_sources`` exposes slug -> sorted [(source, ref)] for ALL
    discovered jobs: >=2-key seedable groups AND fallback-selected
    singleton associations (plain dict of sorted lists, no classes)."""
    a_url = "https://mp.weixin.qq.com/s/grpa"
    b_url = "https://example.com/rss/grpb"
    c_url = "https://mp.weixin.qq.com/s/fallc"
    _add_article(conn, source="wechat", article_id=1, url=a_url,
                 title="A Title", body="A body.")
    _add_article(conn, source="rss", article_id=2, url=b_url,
                 title="B Title", body="B body.")
    _add_article(conn, source="wechat", article_id=3, url=c_url,
                 title="C Title", body="C body.")
    _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
    _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
    _add_ingestion(conn, ingestion_id=3, article_id=3, source="wechat", status="ok")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={
            lightrag_doc_id("wechat", a_url): "processed",
            lightrag_doc_id("rss", b_url): "processed",
            lightrag_doc_id("wechat", c_url): "processed",
        },
    )
    buf = tmp_path / "buf"
    _write_buffer(buf, _ref(a_url), [{"name": "Group Star"}])
    _write_buffer(buf, _ref(b_url), [{"name": "Group Star"}])

    calls: list[str] = []

    async def fake_complete(prompt: str) -> str:
        calls.append(prompt)
        return '{"entities": ["Fallback Pick"]}'

    report = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[buf],
            complete=fake_complete,
        )
    )

    key_a = ("wechat", _ref(a_url))
    key_b = ("rss", _ref(b_url))
    key_c = ("wechat", _ref(c_url))
    assert report["job_sources"]["group-star"] == sorted([key_a, key_b])
    # fallback-selected singleton association is a job too
    assert report["job_sources"]["fallback-pick"] == [key_c]
    assert sorted(report["seeded_entity_jobs"]) == ["fallback-pick", "group-star"]
    assert calls and len(calls) == 1, "only article C reaches the fallback"
    # existing report shape untouched: every legacy key still present
    for key in REPORT_KEYS:
        assert key in report, key


# ---------------------------------------------------------------------------
# 7.2 W5B Task 7: existing-page job -> structured suggestion (no page write)
# ---------------------------------------------------------------------------


def test_s7_existing_page_job_seeds_suggestion_page_untouched(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """An existing-page historical job flows through the shared compiler:
    build_w3_pack_from_records -> propose_w3_patch -> apply_patch(default)
    -> deterministic structured suggestion JSON. The page body/digest never
    changes; the suggestion serializes the full WikiPatch with the
    historical trigger and real source-aware refs/titles."""
    a_url = "https://mp.weixin.qq.com/s/hermesa"
    b_url = "https://example.com/rss/hermesb"
    _add_article(conn, source="wechat", article_id=1, url=a_url,
                 title="A Title", body="A body.")
    _add_article(conn, source="rss", article_id=2, url=b_url,
                 title="B Title", body="B body.")
    _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
    _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={
            lightrag_doc_id("wechat", a_url): "processed",
            lightrag_doc_id("rss", b_url): "processed",
        },
    )
    buf = tmp_path / "buf"
    _write_buffer(buf, _ref(a_url), [{"name": "Hermes"}])
    _write_buffer(buf, _ref(b_url), [{"name": "Hermes"}])
    wiki = _make_wiki(tmp_path)
    page = wiki / "entities" / "hermes.md"
    page.write_text(_RICH_PAGE, encoding="utf-8")
    before = page_digest(page.read_text(encoding="utf-8"))

    async def fake_complete(prompt: str) -> str:
        raise AssertionError("no uncovered article: fallback must not run")

    report = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[buf],
            complete=fake_complete,
            wiki_root=wiki,
        )
    )

    # Job seeded via the existing suggestion writer: page untouched.
    res = report["seeding"]["hermes"]
    assert res["status"] == "suggestion"
    assert page_digest(page.read_text(encoding="utf-8")) == before
    assert "Definition / Overview" in page.read_text(encoding="utf-8"), (
        "page BODY unchanged"
    )
    assert res["suggestion_path"] and Path(res["suggestion_path"]).exists()

    payload = json.loads(Path(res["suggestion_path"]).read_text(encoding="utf-8"))
    assert "patch" in payload, "full serialized WikiPatch, not a reduced subset"
    assert payload["patch"]["trigger"] == "w3_historical_bootstrap"
    assert payload["patch"]["target_slug"] == "hermes"
    ops = {o["op"] for o in payload["patch"]["operations"]}
    assert {"MERGE_SOURCES", "UPSERT_SECTION", "SET_METADATA"} <= ops
    evidence = payload["patch"]["evidence"]
    ev_by_ref = {ev["ref"]: ev for ev in evidence}
    assert _ref(a_url) in ev_by_ref and _ref(b_url) in ev_by_ref
    assert ev_by_ref[_ref(a_url)]["title"] == "A Title"
    assert ev_by_ref[_ref(b_url)]["title"] == "B Title"
    assert ev_by_ref[_ref(a_url)]["metadata"] == {"source": "wechat"}
    assert ev_by_ref[_ref(b_url)]["metadata"] == {"source": "rss"}

    # Coverage: the job's articles are represented, accounting exact.
    assert report["articles"][f"wechat/{_ref(a_url)}"] == "represented"
    assert report["articles"][f"rss/{_ref(b_url)}"] == "represented"
    assert report["retry_unresolved"] == 0 and report["no_wiki_entity"] == 0

    # Rerunning the same discovery hits the same deterministic suggestion
    # path and preserves the written suggestion (no duplicate files).
    rerun = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[buf],
            complete=fake_complete,
            wiki_root=wiki,
        )
    )
    assert rerun["seeding"]["hermes"]["suggestion_path"] == res["suggestion_path"]
    jsons = sorted((wiki / "_suggestions").glob("hermes-wpatch-*.json"))
    assert len(jsons) == 1, "no timestamp-spam duplicates"
    assert jsons[0].read_bytes() == Path(res["suggestion_path"]).read_bytes()


# ---------------------------------------------------------------------------
# 7.3 W5B Task 7: missing page -> create-then-evolve (canonical page +
#      follow-up structured suggestion)
# ---------------------------------------------------------------------------


def test_s7_missing_page_create_then_evolve_canonical_page_and_suggestion(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """A missing-page job lands the canonical CREATE_PAGE, then the fresh
    page is re-read and a second proposal produces the deterministic
    existing-page suggestion: BOTH the entity page and the structured
    suggestion JSON must exist — a bare create without the follow-up
    suggestion is not a successful seeding."""
    a_url = "https://mp.weixin.qq.com/s/createa"
    b_url = "https://example.com/rss/createb"
    _add_article(conn, source="wechat", article_id=1, url=a_url,
                 title="A Title", body="A body.")
    _add_article(conn, source="rss", article_id=2, url=b_url,
                 title="B Title", body="B body.")
    _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
    _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={
            lightrag_doc_id("wechat", a_url): "processed",
            lightrag_doc_id("rss", b_url): "processed",
        },
    )
    buf = tmp_path / "buf"
    _write_buffer(buf, _ref(a_url), [{"name": "Test Entity"}])
    _write_buffer(buf, _ref(b_url), [{"name": "Test Entity"}])
    wiki = _make_wiki(tmp_path)

    async def fake_complete(prompt: str) -> str:
        raise AssertionError("no uncovered article: fallback must not run")

    report = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[buf],
            complete=fake_complete,
            wiki_root=wiki,
        )
    )

    page = wiki / "entities" / "test-entity.md"
    assert page.exists(), "CREATE_PAGE must auto-apply for a missing page"
    text = page.read_text(encoding="utf-8")
    assert "    type: article" in text, "canonical typed sources[] frontmatter"
    assert 'ref: "' + _ref(a_url) + '"' in text
    assert 'ref: "' + _ref(b_url) + '"' in text
    assert " [^1]" in text and "## References" in text
    assert "^[article:" not in text, "no legacy output for new pages"
    assert 'confidence_level: "medium"' in text

    # The create-then-evolve completion signal: the follow-up existing-page
    # patch produced a deterministic structured suggestion.
    res = report["seeding"]["test-entity"]
    assert res["status"] == "suggestion", (
        "create without follow-up suggestion must NOT count as seeded"
    )
    assert res["suggestion_path"] and Path(res["suggestion_path"]).exists()
    suggs = sorted((wiki / "_suggestions").glob("test-entity-wpatch-*.json"))
    assert len(suggs) == 1
    payload = json.loads(suggs[0].read_text(encoding="utf-8"))
    assert payload["patch"]["trigger"] == "w3_historical_bootstrap"
    assert payload["patch"]["base_digest"] == page_digest(text)
    assert report["articles"][f"wechat/{_ref(a_url)}"] == "represented"
    assert report["articles"][f"rss/{_ref(b_url)}"] == "represented"
    assert report["retry_unresolved"] == 0 and report["no_wiki_entity"] == 0


def test_s7_create_without_follow_up_suggestion_fails(
    conn: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A create whose follow-up evolution patch fails is NOT a successful
    seeding: the page exists but the job reports the failure and its
    articles are NOT represented (recompute maps them to retry_unresolved)."""
    import scripts.wiki_evolve as we_mod

    a_url = "https://mp.weixin.qq.com/s/nofollowa"
    b_url = "https://example.com/rss/nofollowb"
    _add_article(conn, source="wechat", article_id=1, url=a_url,
                 title="A Title", body="A body.")
    _add_article(conn, source="rss", article_id=2, url=b_url,
                 title="B Title", body="B body.")
    _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
    _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={
            lightrag_doc_id("wechat", a_url): "processed",
            lightrag_doc_id("rss", b_url): "processed",
        },
    )
    buf = tmp_path / "buf"
    _write_buffer(buf, _ref(a_url), [{"name": "Test Entity"}])
    _write_buffer(buf, _ref(b_url), [{"name": "Test Entity"}])
    wiki = _make_wiki(tmp_path)

    apply_calls: list = []
    real_apply = we_mod.apply_patch

    def failing_follow_up(patch, root, **kwargs):
        apply_calls.append(patch)
        if len(apply_calls) == 2:
            # The CREATE_PAGE applied; the follow-up evolution patch fails
            # BEFORE the engine runs (no suggestion is ever persisted).
            return {
                "status": "conflict",
                "patch_id": patch.patch_id,
                "error": "injected follow-up failure",
                "suggestion_path": None,
                "warnings": [],
            }
        return real_apply(patch, root, **kwargs)

    monkeypatch.setattr(we_mod, "apply_patch", failing_follow_up)

    async def fake_complete(prompt: str) -> str:
        raise AssertionError("no uncovered article: fallback must not run")

    report = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[buf],
            complete=fake_complete,
            wiki_root=wiki,
        )
    )

    assert (wiki / "entities" / "test-entity.md").exists(), "the create applied"
    assert len(apply_calls) == 2, "create + one follow-up attempt"
    assert report["seeding"]["test-entity"]["status"] == "conflict"
    assert not list((wiki / "_suggestions").glob("*.json")), (
        "no follow-up suggestion was persisted"
    )
    assert report["articles"][f"wechat/{_ref(a_url)}"] == "retry_unresolved"
    assert report["articles"][f"rss/{_ref(b_url)}"] == "retry_unresolved"
    assert report["retry_unresolved"] == 2


# ---------------------------------------------------------------------------
# 7.4 W5B Task 7 (S6a): seeding idempotency — a full rerun never duplicates,
#      never timestamp-spams, never resets carried evolution state
# ---------------------------------------------------------------------------


def test_s6a_seeding_idempotent_full_rerun_no_duplicates_no_drift(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """The full bootstrap seeding run executed TWICE against the same temp
    wiki (temp DB + temp lightrag_dir + temp buffer dirs + temp wiki_root).

    The second run must: keep the entity page a single file with identical
    bytes; keep the suggestion dir at exactly one deterministic file (same
    ``<slug>-<patch-id>.json`` path, no timestamp-spam growth); preserve a
    worker-written terminal evolution state EXACTLY (design §7 carry-
    forward, never reset by a compiler rerun); and reproduce identical
    accounting (eligible / represented / no_wiki_entity / retry_unresolved).
    """
    a_url = "https://mp.weixin.qq.com/s/idema"
    b_url = "https://example.com/rss/idemb"
    _add_article(conn, source="wechat", article_id=1, url=a_url,
                 title="A Title", body="A body.")
    _add_article(conn, source="rss", article_id=2, url=b_url,
                 title="B Title", body="B body.")
    _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
    _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={
            lightrag_doc_id("wechat", a_url): "processed",
            lightrag_doc_id("rss", b_url): "processed",
        },
    )
    buf = tmp_path / "buf"
    _write_buffer(buf, _ref(a_url), [{"name": "Idem Entity"}])
    _write_buffer(buf, _ref(b_url), [{"name": "Idem Entity"}])
    wiki = _make_wiki(tmp_path)

    async def fake_complete(prompt: str) -> str:
        raise AssertionError("no uncovered article: fallback must not run")

    async def run() -> dict:
        return await bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[buf],
            complete=fake_complete,
            wiki_root=wiki,
        )

    report1 = asyncio.run(run())
    page = wiki / "entities" / "idem-entity.md"
    assert page.exists(), "run 1 must create the page (create-then-evolve)"
    page_bytes1 = page.read_bytes()
    suggs1 = sorted((wiki / "_suggestions").glob("idem-entity-wpatch-*.json"))
    assert len(suggs1) == 1, "run 1 leaves exactly one suggestion"
    path1 = Path(report1["seeding"]["idem-entity"]["suggestion_path"])
    assert path1 == suggs1[0]
    payload1 = json.loads(path1.read_text(encoding="utf-8"))
    stable1 = {k: v for k, v in payload1.items() if k != "evolution"}
    accounting1 = (
        report1["eligible_processed_ingestions"],
        sum(1 for v in report1["articles"].values() if v == "represented"),
        report1["no_wiki_entity"],
        report1["retry_unresolved"],
    )

    # A worker already processed the suggestion into a TERMINAL state:
    # rerunning the compiler must carry it forward, never reset it.
    terminal = {
        "status": "rejected",
        "attempts": 3,
        "next_retry_at": None,
        "last_evaluated_at": "2026-08-10T09:00:00+00:00",
        "last_decision": "rejected",
        "last_reason": "worker verdict",
        "applied_patch_id": None,
    }
    payload1["evolution"] = terminal
    path1.write_text(
        json.dumps(payload1, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    report2 = asyncio.run(run())

    # no duplicate page: single file, byte-identical content
    assert (wiki / "entities" / "idem-entity.md").exists()
    assert page.read_bytes() == page_bytes1, "page content must not drift"
    # no timestamp-spam: same deterministic suggestion path, no growth
    suggs2 = sorted((wiki / "_suggestions").glob("idem-entity-wpatch-*.json"))
    assert len(suggs2) == len(suggs1) == 1, "suggestion dir must not grow"
    path2 = Path(report2["seeding"]["idem-entity"]["suggestion_path"])
    assert path2 == path1, "deterministic suggestion path across reruns"
    payload2 = json.loads(path2.read_text(encoding="utf-8"))
    assert {k: v for k, v in payload2.items() if k != "evolution"} == stable1, (
        "suggestion payload must be byte-deterministic across reruns"
    )
    # terminal/retry evolution state preserved exactly
    assert payload2["evolution"] == terminal, (
        "carried evolution must not be reset by a rerun"
    )
    # exact accounting unchanged between runs
    accounting2 = (
        report2["eligible_processed_ingestions"],
        sum(1 for v in report2["articles"].values() if v == "represented"),
        report2["no_wiki_entity"],
        report2["retry_unresolved"],
    )
    assert accounting2 == accounting1


# ---------------------------------------------------------------------------
# 7.5 W5B Task 7 CORRECTIVE (variable-shadowing defect): the seeding loop's
#     local ``keys = sorted(job_sources[slug])`` shadowed the outer eligible
#     ``keys`` list, so the post-persistence recompute loop and
#     ``_check_accounting`` saw ONLY the last job's keys. Multi-job runs
#     broke: (A) 2 groups both seed -> eligible 2 != represented 4 ->
#     BootstrapAccountingError (CLI exit 1 instead of 0); (B) first group
#     fails / second seeds -> exit 1 instead of 2, failed job's articles
#     stay falsely "represented"; (C) 1 group + 1 no_wiki_entity -> exit 1
#     instead of 0. These tests pin the FIXED contract: the recompute
#     visits every eligible key and accounting is exact.
# ---------------------------------------------------------------------------


def test_s7_shadow_fix_two_groups_both_seed_accounting_exact(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """Scenario A: two seedable groups (4 articles, 2 existing pages) BOTH
    seed through the real compiler. Every eligible article must stay
    represented and accounting must be exact (eligible == represented == 4).
    Pre-fix: the seeding-loop local shadowed the eligible ``keys`` list, the
    recompute visited only the LAST job's keys, and ``_check_accounting``
    saw ``eligible 2 != represented 4`` -> BootstrapAccountingError (CLI
    exit 1 instead of 0)."""
    a_url = "https://mp.weixin.qq.com/s/twogrpa"
    b_url = "https://example.com/rss/twogrb"
    c_url = "https://mp.weixin.qq.com/s/twogrc"
    d_url = "https://example.com/rss/twogrd"
    _add_article(conn, source="wechat", article_id=1, url=a_url,
                 title="A Title", body="A body.")
    _add_article(conn, source="rss", article_id=2, url=b_url,
                 title="B Title", body="B body.")
    _add_article(conn, source="wechat", article_id=3, url=c_url,
                 title="C Title", body="C body.")
    _add_article(conn, source="rss", article_id=4, url=d_url,
                 title="D Title", body="D body.")
    for i, url in enumerate((a_url, b_url, c_url, d_url), start=1):
        _add_ingestion(conn, ingestion_id=i, article_id=i,
                       source="wechat" if i % 2 else "rss", status="ok")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={
            lightrag_doc_id("wechat", a_url): "processed",
            lightrag_doc_id("rss", b_url): "processed",
            lightrag_doc_id("wechat", c_url): "processed",
            lightrag_doc_id("rss", d_url): "processed",
        },
    )
    buf = tmp_path / "buf"
    _write_buffer(buf, _ref(a_url), [{"name": "Hermes"}])
    _write_buffer(buf, _ref(b_url), [{"name": "Hermes"}])
    _write_buffer(buf, _ref(c_url), [{"name": "Alpha"}])
    _write_buffer(buf, _ref(d_url), [{"name": "Alpha"}])
    wiki = _make_wiki(tmp_path)
    (wiki / "entities" / "hermes.md").write_text(_RICH_PAGE, encoding="utf-8")
    (wiki / "entities" / "alpha.md").write_text(
        _RICH_PAGE.replace("Hermes", "Alpha"), encoding="utf-8"
    )

    async def fake_complete(prompt: str) -> str:
        raise AssertionError("no uncovered article: fallback must not run")

    report = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[buf],
            complete=fake_complete,
            wiki_root=wiki,
        )
    )

    # Both jobs seeded through the real compiler: two suggestion JSONs.
    assert set(report["seeding"]) == {"alpha", "hermes"}
    assert report["seeding"]["hermes"]["status"] == "suggestion"
    assert report["seeding"]["alpha"]["status"] == "suggestion"
    for slug in ("alpha", "hermes"):
        path = Path(report["seeding"][slug]["suggestion_path"])
        assert path.exists(), f"{slug} suggestion must exist"

    # Every eligible article represented — the recompute must visit ALL
    # eligible keys, not just the last job's.
    assert report["eligible_processed_ingestions"] == 4
    assert report["articles"][f"wechat/{_ref(a_url)}"] == "represented"
    assert report["articles"][f"rss/{_ref(b_url)}"] == "represented"
    assert report["articles"][f"wechat/{_ref(c_url)}"] == "represented"
    assert report["articles"][f"rss/{_ref(d_url)}"] == "represented"
    assert report["no_wiki_entity"] == 0
    assert report["retry_unresolved"] == 0
    represented = sum(1 for v in report["articles"].values() if v == "represented")
    assert report["eligible_processed_ingestions"] == (
        represented + report["no_wiki_entity"] + report["retry_unresolved"]
    )


def test_s7_shadow_fix_two_groups_first_fails_exit_two_truthful(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Scenario B: two graph-covered groups where the FIRST job fails
    (compiler raises) and the SECOND seeds. The failed job's articles must
    be truthfully demoted to ``retry_unresolved`` (CLI exit 2), never left
    falsely "represented". Pre-fix: the recompute loop visited only the LAST
    job's keys, so the failed group's articles stayed "represented" and the
    shadowed ``len(keys)`` broke accounting — CLI exit 1 instead of 2."""
    from scripts.wiki_evolve import main

    db_path = tmp_path / "kol_scan.db"
    urls = {
        "a": "https://mp.weixin.qq.com/s/failgrpa",
        "b": "https://example.com/rss/failgrpb",
        "c": "https://mp.weixin.qq.com/s/winfgrpc",
        "d": "https://example.com/rss/winfgrpd",
    }
    conn = _open_db_file(db_path)
    try:
        for i, url in enumerate(urls.values(), start=1):
            source = "wechat" if i % 2 else "rss"
            _add_article(conn, source=source, article_id=i, url=url,
                         title=f"Title {i}", body=f"Body {i}.")
            _add_ingestion(conn, ingestion_id=i, article_id=i,
                           source=source, status="ok")
        conn.commit()
    finally:
        conn.close()
    doc_a = lightrag_doc_id("wechat", urls["a"])
    doc_b = lightrag_doc_id("rss", urls["b"])
    doc_c = lightrag_doc_id("wechat", urls["c"])
    doc_d = lightrag_doc_id("rss", urls["d"])
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={
            doc_a: "processed", doc_b: "processed",
            doc_c: "processed", doc_d: "processed",
        },
    )
    (lightrag / "vdb_entities.json").write_text(
        json.dumps({
            "data": [
                {"entity_name": "Alpha Fail", "source_id": "chunk-a1|chunk-a2"},
                {"entity_name": "Beta Win", "source_id": "chunk-b1|chunk-b2"},
            ]
        }),
        encoding="utf-8",
    )
    (lightrag / "vdb_relationships.json").write_text(
        json.dumps({"data": []}), encoding="utf-8"
    )
    (lightrag / "kv_store_text_chunks.json").write_text(
        json.dumps({
            "chunk-a1": {"full_doc_id": doc_a},
            "chunk-a2": {"full_doc_id": doc_b},
            "chunk-b1": {"full_doc_id": doc_c},
            "chunk-b2": {"full_doc_id": doc_d},
        }),
        encoding="utf-8",
    )
    (lightrag / "kv_store_full_docs.json").write_text(
        json.dumps({
            doc_a: {"content": f"URL: {urls['a']}"},
            doc_b: {"content": f"URL: {urls['b']}"},
            doc_c: {"content": f"URL: {urls['c']}"},
            doc_d: {"content": f"URL: {urls['d']}"},
        }),
        encoding="utf-8",
    )
    wiki = _make_wiki(tmp_path)

    def fake_apply(patch, root):
        # Short-circuit BEFORE the real engine: fail the first job, seed
        # the second — the recompute/accounting is what these tests pin.
        assert patch.target_slug in ("alpha-fail", "beta-win"), patch.target_slug
        if patch.target_slug == "alpha-fail":
            raise RuntimeError("simulated compiler failure")
        return {
            "status": "suggestion",
            "patch_id": f"w3-{patch.target_slug}-fake",
            "suggestion_path": str(
                wiki / "_suggestions" / f"{patch.target_slug}.json"
            ),
            "warnings": [],
            "error": None,
        }

    monkeypatch.setattr("scripts.wiki_evolve.apply_patch", fake_apply)
    rc = main([
        "--bootstrap-existing",
        "--db-path", str(db_path),
        "--lightrag-dir", str(lightrag),
        "--wiki-root", str(wiki),
    ])

    assert rc == 2, "failed job's articles retry_unresolved -> exit 2 (pre-fix: 1)"
    report = json.loads(capsys.readouterr().out)
    assert report["eligible_processed_ingestions"] == 4
    assert report["seeding"]["alpha-fail"]["status"] == "failed"
    assert "simulated compiler failure" in report["seeding"]["alpha-fail"]["error"]
    assert report["seeding"]["beta-win"]["status"] == "suggestion"
    # Truthful recompute: the FAILED group's articles are retry_unresolved,
    # never left falsely represented; the seeded group's are represented.
    assert report["articles"][f"wechat/{_ref(urls['a'])}"] == "retry_unresolved"
    assert report["articles"][f"rss/{_ref(urls['b'])}"] == "retry_unresolved"
    assert report["articles"][f"wechat/{_ref(urls['c'])}"] == "represented"
    assert report["articles"][f"rss/{_ref(urls['d'])}"] == "represented"
    assert report["retry_unresolved"] == 2
    assert report["no_wiki_entity"] == 0
    represented = sum(1 for v in report["articles"].values() if v == "represented")
    assert report["eligible_processed_ingestions"] == (
        represented + report["no_wiki_entity"] + report["retry_unresolved"]
    )


def test_s7_shadow_fix_group_plus_no_wiki_entity_accounting_exact(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """Scenario C: one seedable group (2 articles, existing page) PLUS one
    fallback article with NO wiki entity (empty ``entities`` list). The
    no_wiki_entity article is terminal and the group's articles are
    represented: eligible 3 == represented 2 + no_wiki_entity 1 -> exact
    accounting, run completes. Pre-fix: the shadowed ``keys`` list made the
    accounting see only the group's 2 keys (``2 != 2 + 1 + 0``) ->
    BootstrapAccountingError (CLI exit 1 instead of 0)."""
    a_url = "https://mp.weixin.qq.com/s/nwegrpa"
    b_url = "https://example.com/rss/nwegrpb"
    c_url = "https://example.com/rss/nwegrc"
    _add_article(conn, source="wechat", article_id=1, url=a_url,
                 title="A Title", body="A body.")
    _add_article(conn, source="rss", article_id=2, url=b_url,
                 title="B Title", body="B body.")
    _add_article(conn, source="rss", article_id=3, url=c_url,
                 title="C Title", body="C body.")
    _add_ingestion(conn, ingestion_id=1, article_id=1, source="wechat", status="ok")
    _add_ingestion(conn, ingestion_id=2, article_id=2, source="rss", status="ok")
    _add_ingestion(conn, ingestion_id=3, article_id=3, source="rss", status="ok")
    conn.commit()
    lightrag = _make_lightrag_dir(
        tmp_path,
        doc_status={
            lightrag_doc_id("wechat", a_url): "processed",
            lightrag_doc_id("rss", b_url): "processed",
            lightrag_doc_id("rss", c_url): "processed",
        },
    )
    buf = tmp_path / "buf"
    _write_buffer(buf, _ref(a_url), [{"name": "Omega"}])
    _write_buffer(buf, _ref(b_url), [{"name": "Omega"}])
    wiki = _make_wiki(tmp_path)
    (wiki / "entities" / "omega.md").write_text(
        _RICH_PAGE.replace("Hermes", "Omega"), encoding="utf-8"
    )

    calls: list[str] = []

    async def fake_complete(prompt: str) -> str:
        calls.append(prompt)
        return '{"entities": []}'

    report = asyncio.run(
        bootstrap_existing_discovery(
            conn,
            lightrag_dir=lightrag,
            buffer_dirs=[buf],
            complete=fake_complete,
            wiki_root=wiki,
        )
    )

    assert len(calls) == 1, "exactly the singleton article reaches the fallback"
    assert set(report["job_sources"]) == {"omega"}, (
        "no job exists for the no_wiki_entity article"
    )
    assert report["seeding"]["omega"]["status"] == "suggestion"
    assert report["seeded_entity_jobs"] == ["omega"]
    assert report["eligible_processed_ingestions"] == 3
    assert report["articles"][f"wechat/{_ref(a_url)}"] == "represented"
    assert report["articles"][f"rss/{_ref(b_url)}"] == "represented"
    assert report["articles"][f"rss/{_ref(c_url)}"] == "no_wiki_entity"
    assert report["no_wiki_entity"] == 1
    assert report["retry_unresolved"] == 0
    represented = sum(1 for v in report["articles"].values() if v == "represented")
    assert report["eligible_processed_ingestions"] == (
        represented + report["no_wiki_entity"] + report["retry_unresolved"]
    )
