"""W5A Task 4 behavior anchors: production W3 path converges on the shared compiler.

The production W3 hook (``batch_ingest_from_spider._wiki_update_check`` →
``kb.wiki_update.generate_wiki_suggestions`` + ``apply_suggestion_atomic``)
must route through ``kb.wiki_compiler.adapters.w3`` + the shared engine:

    article_hashes → build_w3_evidence_packs → propose_w3_patch → engine
    classify/apply → result accounting

The legacy bypass machinery (local ``_atomic_write`` / ``_build_page`` /
timestamped ``<slug>-<timestamp>.md`` suggestions / duplicate lint policy)
must not be invoked by the production path.
"""
from __future__ import annotations

import ast
import inspect
import json
import sqlite3
from pathlib import Path

import pytest

import kb.wiki_articles as wiki_articles_mod
import kb.wiki_compiler.assembler as assembler_mod
import kb.wiki_compiler.engine as engine_mod
import kb.wiki_compiler.models as models_mod
import kb.wiki_update as wiki_update
from kb.wiki_compiler.adapters import w3
from kb.wiki_compiler.models import page_digest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _seed_db(hashes: list[str]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE articles (content_hash TEXT PRIMARY KEY)")
    for h in hashes:
        conn.execute("INSERT INTO articles (content_hash) VALUES (?)", (h,))
    conn.commit()
    return conn


def _seed_source_db() -> sqlite3.Connection:
    """Source-aware fixture (W5B Task 2): articles + rss_articles with
    url/title; rss_articles carries a 32-char body content_hash that is
    never article identity."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE articles ("
        "id INTEGER PRIMARY KEY, title TEXT, url TEXT, content_hash TEXT)"
    )
    conn.execute(
        "CREATE TABLE rss_articles ("
        "id INTEGER PRIMARY KEY, title TEXT, url TEXT, summary TEXT, "
        "content_hash TEXT)"
    )
    return conn


def _write_buffer(buf_dir: Path, h: str, names: list[str]) -> None:
    buf_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "url": f"http://example.com/{h}",
        "raw_entities": [{"name": n} for n in names],
        "timestamp": 0.0,
    }
    (buf_dir / f"{h}_entities.json").write_text(json.dumps(payload), encoding="utf-8")


def _make_wiki(tmp_path: Path) -> Path:
    wiki = tmp_path / "wiki"
    (wiki / "entities").mkdir(parents=True, exist_ok=True)
    return wiki


_RICH_PAGE = """---
title: "Hermes"
created: "2026-05-20"
last_updated: "2026-05-20"
sources:
  - type: article
    ref: "aaaaaaaaaa"
    title: "aaaaaaaaaa"
    provenance: w3-entity-buffer
  - type: article
    ref: "bbbbbbbbbb"
    title: "bbbbbbbbbb"
    provenance: w3-entity-buffer
confidence_level: medium
---

# Hermes

## Definition / Overview

A detailed pre-existing synthesis paragraph with citations. [^1][^2]

## References

[^1]: **aaaaaaaaaa** — aaaaaaaaaa (w3-entity-buffer)
[^2]: **bbbbbbbbbb** — bbbbbbbbbb (w3-entity-buffer)
""" + ("\n\nMore pre-existing rich body text. " + ("X" * 500))


# ---------------------------------------------------------------------------
# 1. generate_wiki_suggestions routes through the W3 adapter
# ---------------------------------------------------------------------------

def test_generate_suggestions_routes_through_w3_adapter(tmp_path, monkeypatch):
    hashes = ["aaaaaaaaaa", "bbbbbbbbbb"]
    conn = _seed_db(hashes)
    buf = tmp_path / "buf"
    for h in hashes:
        _write_buffer(buf, h, ["Test Entity"])
    wiki = _make_wiki(tmp_path)

    calls = []
    real_build = w3.build_w3_evidence_packs

    def spy_build(*args, **kwargs):
        calls.append((args, kwargs))
        return real_build(*args, **kwargs)

    monkeypatch.setattr(w3, "build_w3_evidence_packs", spy_build)

    suggestions = wiki_update.generate_wiki_suggestions(
        hashes, wiki, conn, min_frequency=2, entity_buffer_dirs=[buf]
    )

    assert calls, "generate_wiki_suggestions must call w3.build_w3_evidence_packs"
    assert calls[0][0][0] == hashes
    assert calls[0][1]["db_conn"] is conn
    assert calls[0][1]["min_frequency"] == 2
    assert calls[0][1]["entity_buffer_dirs"] == [buf]
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s["entity_slug"] == "test-entity"
    assert s["type"] == "new"
    assert s["source_articles"] == ["aaaaaaaaaa", "bbbbbbbbbb"]
    # The patch is the authoritative artifact; it must be engine-ready
    # (wiki-relative target path, not the assembler's repo-relative one).
    assert "patch" in s
    assert s["patch"].target_path.startswith("entities/")
    assert not s["patch"].target_path.startswith("kb/wiki/")


# ---------------------------------------------------------------------------
# 2. New-entity W3 flow → canonical CREATE_PAGE via the shared compiler
# ---------------------------------------------------------------------------

def test_new_entity_w3_flow_creates_canonical_cited_page(tmp_path):
    hashes = ["aaaaaaaaaa", "bbbbbbbbbb"]
    conn = _seed_db(hashes)
    buf = tmp_path / "buf"
    for h in hashes:
        _write_buffer(buf, h, ["Test Entity"])
    wiki = _make_wiki(tmp_path)

    stats = wiki_update.run_wiki_update_pipeline(
        hashes, wiki, conn, min_frequency=2, entity_buffer_dirs=[buf]
    )

    assert stats["suggestions_generated"] == 1
    assert stats["applied"] == 1
    assert stats["dropped"] == 0
    assert stats["patches"][0]["status"] == "applied"

    page = wiki / "entities" / "test-entity.md"
    assert page.exists()
    text = page.read_text(encoding="utf-8")
    # canonical typed sources[] — not legacy `- article:<hex>` lines
    assert "    type: article" in text
    assert 'ref: "aaaaaaaaaa"' in text
    assert 'ref: "bbbbbbbbbb"' in text
    assert "provenance: w3-entity-buffer" in text
    # GFM [^N] citations with the mandated space separator
    # (one W3 context block → [^1]; the References section lists all sources)
    assert " [^1]" in text
    assert "[^2]:" in text
    assert "## References" in text
    assert "^[article:" not in text
    # 2 sources of the same type → medium confidence (SCHEMA.md §1)
    assert 'confidence_level: "medium"' in text


# ---------------------------------------------------------------------------
# 3. Existing rich page → suggestion_only → structured JSON, digest untouched
# ---------------------------------------------------------------------------

def test_existing_rich_page_w3_flow_suggestion_json_digest_unchanged(tmp_path):
    hashes = ["aaaaaaaaaa", "bbbbbbbbbb", "cccccccccc"]
    conn = _seed_db(hashes)
    buf = tmp_path / "buf"
    for h in hashes:
        _write_buffer(buf, h, ["Hermes"])
    wiki = _make_wiki(tmp_path)
    page = wiki / "entities" / "hermes.md"
    page.write_text(_RICH_PAGE, encoding="utf-8")
    before = page_digest(page.read_text(encoding="utf-8"))

    stats = wiki_update.run_wiki_update_pipeline(
        hashes, wiki, conn, min_frequency=2, entity_buffer_dirs=[buf]
    )

    assert stats["suggestions_generated"] == 1
    assert stats["applied"] == 0
    assert stats["dropped"] == 1
    assert stats["suggestions_persisted"] == 1
    assert stats["conflicted"] == 0
    assert stats["rejected"] == 0
    assert stats["patches"][0]["status"] == "suggestion"

    # The existing rich page is never overwritten.
    assert page_digest(page.read_text(encoding="utf-8")) == before

    # Deterministic structured suggestion: <slug>-<patch-id>.json
    sugg_dir = wiki / "_suggestions"
    assert sugg_dir.exists()
    jsons = sorted(sugg_dir.glob("hermes-wpatch-*.json"))
    assert len(jsons) == 1
    # Old timestamped <slug>-<timestamp>.md suggestions are gone under W5A.
    assert list(sugg_dir.glob("*.md")) == []
    payload = json.loads(jsons[0].read_text(encoding="utf-8"))
    assert payload["target_slug"] == "hermes"
    assert payload["patch_id"].startswith("wpatch-")
    ops = {o["op"] for o in payload["operations"]}
    assert {"MERGE_SOURCES", "UPSERT_SECTION", "SET_METADATA"} <= ops
    assert "suggested_content" in payload


# ---------------------------------------------------------------------------
# 4. Same logical input twice → same patch_id → same suggestion path
# ---------------------------------------------------------------------------

def test_same_input_twice_converges_same_patch_id_same_suggestion_path(tmp_path):
    hashes = ["aaaaaaaaaa", "bbbbbbbbbb", "cccccccccc"]
    conn = _seed_db(hashes)
    buf = tmp_path / "buf"
    for h in hashes:
        _write_buffer(buf, h, ["Hermes"])
    wiki = _make_wiki(tmp_path)
    page = wiki / "entities" / "hermes.md"
    page.write_text(_RICH_PAGE, encoding="utf-8")
    before = page_digest(page.read_text(encoding="utf-8"))

    kwargs = dict(
        article_hashes=hashes, wiki_root=wiki, db_conn=conn,
        min_frequency=2, entity_buffer_dirs=[buf],
    )
    first = wiki_update.run_wiki_update_pipeline(**kwargs)
    second = wiki_update.run_wiki_update_pipeline(**kwargs)

    assert first["patches"][0]["patch_id"] == second["patches"][0]["patch_id"]
    assert (
        first["patches"][0]["suggestion_path"]
        == second["patches"][0]["suggestion_path"]
    )
    # No timestamp-spam duplicates: exactly one suggestion file, same name.
    jsons1 = sorted(p.name for p in (wiki / "_suggestions").glob("hermes-wpatch-*.json"))
    jsons2 = sorted(p.name for p in (wiki / "_suggestions").glob("hermes-wpatch-*.json"))
    assert len(jsons1) == 1
    assert jsons1 == jsons2
    assert page_digest(page.read_text(encoding="utf-8")) == before


# ---------------------------------------------------------------------------
# 5. Engine validation/conflict outcomes reflected in W3 accounting,
#    without any direct fallback write
# ---------------------------------------------------------------------------

def test_engine_validation_failure_rejected_no_fallback_write(tmp_path, monkeypatch):
    """Legacy dict with invalid evidence → rejected via the compiler path,
    recorded in the Error Book, page never written."""
    db_path = tmp_path / "error_book.db"
    monkeypatch.setattr("kb.error_book._DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr("kb.error_book._LEGACY_JSONL", tmp_path / "nonexistent.jsonl")
    from kb.error_book import get_open_errors

    conn = _seed_db([])
    wiki = _make_wiki(tmp_path)
    page_path = wiki / "entities" / "ghost.md"
    suggestion = {
        "type": "new",
        "entity_slug": "ghost",
        "page_path": str(page_path),
        "content": "---\ntitle: Ghost\n---\n",
        "source_articles": ["not-a-valid-hash"],
    }

    result = wiki_update.apply_suggestion_atomic(suggestion, conn, wiki_root=wiki)

    assert result is False
    assert not page_path.exists()
    errors = get_open_errors(db_path=db_path)
    assert any(
        e["check_type"] == "wiki_compiler:evidence_validation" for e in errors
    )


def test_engine_conflict_reflected_without_fallback_write(tmp_path, monkeypatch):
    """A digest race (page changed after pack build) surfaces as engine
    'conflict': apply returns False, the on-disk content is preserved, and
    no suggestion or fallback write happens."""
    hashes = ["aaaaaaaaaa", "bbbbbbbbbb"]
    conn = _seed_db(hashes)
    buf = tmp_path / "buf"
    for h in hashes:
        _write_buffer(buf, h, ["Test Entity"])
    wiki = _make_wiki(tmp_path)
    page = wiki / "entities" / "test-entity.md"
    page.write_text(_RICH_PAGE, encoding="utf-8")

    # Force the race branch: policy says auto_apply, but the page changed
    # between pack build (digest capture) and apply.
    monkeypatch.setattr(
        engine_mod, "classify_patch", lambda patch, root, page_registry=None: "auto_apply"
    )
    results = []
    real_apply = wiki_update.apply_patch

    def spy_apply(patch, root, **kw):
        res = real_apply(patch, root, **kw)
        results.append(res)
        return res

    monkeypatch.setattr(wiki_update, "apply_patch", spy_apply)

    suggestions = wiki_update.generate_wiki_suggestions(
        hashes, wiki, conn, min_frequency=2, entity_buffer_dirs=[buf]
    )
    assert len(suggestions) == 1
    page.write_text(
        _RICH_PAGE + "\n\nMutated by another writer after pack build.\n",
        encoding="utf-8",
    )

    assert wiki_update.apply_suggestion_atomic(
        suggestions[0], conn, wiki_root=wiki
    ) is False
    assert results and results[0]["status"] == "conflict"
    # On-disk content preserved — no fallback/authoritative write.
    assert "Mutated by another writer after pack build." in page.read_text(
        encoding="utf-8"
    )
    assert page_digest(page.read_text(encoding="utf-8")) != page_digest(_RICH_PAGE)
    assert not (wiki / "_suggestions").exists()


# ---------------------------------------------------------------------------
# 6. Legacy bypass helpers are gone; production path cannot call them
# ---------------------------------------------------------------------------

def test_production_path_has_no_legacy_bypass_helpers():
    """W5A: _build_page / _atomic_write / _page_is_w1_rich are deleted from
    kb.wiki_update — the production W3 path cannot invoke them."""
    assert not hasattr(wiki_update, "_build_page")
    assert not hasattr(wiki_update, "_atomic_write")
    assert not hasattr(wiki_update, "_page_is_w1_rich")


# ---------------------------------------------------------------------------
# 7. No network / LLM / external provider calls in the compiler path
# ---------------------------------------------------------------------------

_BANNED_IMPORT_ROOTS = {
    "requests", "urllib", "http", "aiohttp", "httpx", "socket",
    "subprocess", "openai", "anthropic", "tavily", "databricks", "google",
}


def test_no_network_or_llm_imports_in_compiler_path():
    """Import-time scan: the W3 adapter + shared compiler + hook bridge must
    not import network/LLM/external-provider modules (W5A constraint §4.6)."""
    modules = [
        wiki_update, w3, engine_mod, assembler_mod, models_mod,
        wiki_articles_mod,
    ]
    for mod in modules:
        tree = ast.parse(inspect.getsource(mod))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert root not in _BANNED_IMPORT_ROOTS, (
                        f"{mod.__name__} imports banned module {alias.name!r}"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                assert root not in _BANNED_IMPORT_ROOTS, (
                    f"{mod.__name__} imports banned module {node.module!r}"
                )


def test_w3_flow_makes_no_network_calls(tmp_path, monkeypatch):
    """Runtime guard: the full W3 flow (discovery → proposal → apply) makes
    no socket/network calls."""
    import socket

    class _NoNetwork:
        def __init__(self, *args, **kwargs):
            raise AssertionError("network call attempted during W3 flow")

    monkeypatch.setattr(socket, "socket", _NoNetwork)

    hashes = ["aaaaaaaaaa", "bbbbbbbbbb"]
    conn = _seed_db(hashes)
    buf = tmp_path / "buf"
    for h in hashes:
        _write_buffer(buf, h, ["Test Entity"])
    wiki = _make_wiki(tmp_path)

    stats = wiki_update.run_wiki_update_pipeline(
        hashes, wiki, conn, min_frequency=2, entity_buffer_dirs=[buf]
    )
    assert stats["applied"] == 1
    assert (wiki / "entities" / "test-entity.md").exists()

    # W5B Task 2: the source-aware RSS path (mapping inputs resolving
    # through rss_articles) is equally network-free end to end.
    import hashlib

    from kb.wiki_articles import canonical_article_ref

    conn2 = _seed_source_db()
    wx_url = "https://mp.weixin.qq.com/s/w5b-t2-wx"
    rss_url = "https://example.com/rss/w5b-t2"
    wx_ref = canonical_article_ref(wx_url)
    rss_ref = canonical_article_ref(rss_url)
    conn2.execute(
        "INSERT INTO articles (id, title, url, content_hash) VALUES (1, ?, ?, ?)",
        ("WeChat Real Title", wx_url, wx_ref),
    )
    conn2.execute(
        "INSERT INTO rss_articles (id, title, url, summary, content_hash) "
        "VALUES (1, ?, ?, ?, ?)",
        (
            "RSS Real Title",
            rss_url,
            "unrelated summary",
            hashlib.md5(b"unrelated body text").hexdigest(),
        ),
    )
    conn2.commit()
    _write_buffer(buf, wx_ref, ["Test Entity"])
    _write_buffer(buf, rss_ref, ["Test Entity"])

    # Fresh wiki for the source-aware leg: part 1 already created
    # test-entity.md, and existing pages are never overwritten
    # (suggestion_only) — a fresh wiki proves the RSS mapping path
    # auto-applies end to end exactly like the legacy one.
    wiki2 = _make_wiki(tmp_path / "wiki2")
    stats2 = wiki_update.run_wiki_update_pipeline(
        [{"source": "wechat", "ref": wx_ref}, {"source": "rss", "ref": rss_ref}],
        wiki2,
        conn2,
        min_frequency=2,
        entity_buffer_dirs=[buf],
    )
    assert stats2["applied"] == 1
    assert (wiki2 / "entities" / "test-entity.md").exists()


# ---------------------------------------------------------------------------
# 8. batch_ingest_from_spider surface: unchanged shape, swallowed failures
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_batch_ingest_hook_surface_unchanged(monkeypatch, tmp_path):
    """_wiki_update_check keeps its stats shape and swallows hook exceptions."""
    import batch_ingest_from_spider as bi

    conn = _seed_db([])

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated wiki hook failure")

    monkeypatch.setattr(wiki_update, "generate_wiki_suggestions", _boom)

    result = await bi._wiki_update_check([], conn, wiki_root=tmp_path / "wiki")

    assert result == {"suggestions_generated": 0, "applied": 0, "dropped": 0}


@pytest.mark.asyncio
async def test_batch_ingest_hook_routes_through_compiler(tmp_path, monkeypatch):
    """End-to-end: the real hook call routes through the compiler — new entity
    gets created and the accounting shape is preserved (no redesign)."""
    import batch_ingest_from_spider as bi

    hashes = ["aaaaaaaaaa", "bbbbbbbbbb"]
    conn = _seed_db(hashes)
    buf = tmp_path / "buf"
    for h in hashes:
        _write_buffer(buf, h, ["Test Entity"])
    wiki = _make_wiki(tmp_path)
    monkeypatch.setattr(wiki_update, "DEFAULT_BUFFER_DIRS", [buf])

    result = await bi._wiki_update_check(hashes, conn, wiki_root=wiki)

    assert set(result) == {"suggestions_generated", "applied", "dropped"}
    assert result["suggestions_generated"] == 1
    assert result["applied"] == 1
    assert result["dropped"] == 0
    page = wiki / "entities" / "test-entity.md"
    assert page.exists()
    assert "    type: article" in page.read_text(encoding="utf-8")
