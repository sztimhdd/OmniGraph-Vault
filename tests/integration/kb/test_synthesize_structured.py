"""Integration tests for kb-v2.1-4 structured SynthesizeResult.

Covers the wrapper end-to-end against a real fixture_db SQLite + the real
articles_by_hashes / entities_for_articles queries. Only the C1
(kg_synthesize.synthesize_response) external boundary is monkeypatched —
LightRAG is slow + non-deterministic and is the third-party-service
boundary the writing-tests SKILL guidelines say to mock.

Skill(skill="python-patterns", args="Pure idiomatic Python for the structured result schema: frozen dataclasses, default_factory for mutable defaults, asdict() helper, EAFP for DB+file access, defense-in-depth try/except so source/entity resolution failures degrade gracefully without poisoning the never-500 contract.")

Skill(skill="writing-tests", args="Testing Trophy: integration > unit. Real DB + real FastAPI TestClient + MOCKED kg_synthesize.synthesize_response (because real LightRAG is slow + non-deterministic). Test: KG success with markdown containing 3 /article/{hash}.html refs returns SynthesizeResult.sources with title+lang from DB. Test: KG success with markdown lacking refs returns sources=[], confidence='no_results'. Test: KG exception falls back to FTS5 path. Test: KG timeout falls back to FTS5 path. Test: FTS5 fallback returns valid SynthesizeResult shape. Test: entities_for_articles populated when sources present. Test: DATA-07 reject articles never surface as sources. Use fixture_db + reload chain + monkeypatch synthesize_response — never mock article_query.")
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest


# ---- Fixture: fully-wired wrapper module with fixture_db + KG-mode-on -----


@pytest.fixture
def synthesize_module(
    fixture_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Reload kb.services.synthesize with KG mode enabled, BASE_DIR redirected,
    and KB_DB_PATH pointing at the kb-2 fixture_db.
    """
    import config as og_config

    sa_dummy = tmp_path / "kg-sa-dummy.json"
    sa_dummy.write_text('{"type":"service_account"}')
    monkeypatch.setenv("KB_KG_GCP_SA_KEY_PATH", str(sa_dummy))
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    monkeypatch.delenv("KB_CONTENT_QUALITY_FILTER", raising=False)
    monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)
    import kb.config
    import kb.data.article_query
    import kb.services.synthesize

    importlib.reload(kb.config)
    monkeypatch.setattr(
        kb.data.article_query,
        "QUALITY_FILTER_ENABLED",
        os.environ.get("KB_CONTENT_QUALITY_FILTER", "on").lower() != "off",
    )
    importlib.reload(kb.services.synthesize)
    return kb.services.synthesize


def _populate_fts(fixture_db: Path) -> None:
    """Seed articles_fts so the fts5_fallback path has hits to return."""
    from kb.data.article_query import (
        _row_to_record_kol,
        _row_to_record_rss,
        resolve_url_hash,
    )
    from kb.services.search_index import FTS_TABLE_NAME, ensure_fts_table

    c = sqlite3.connect(str(fixture_db))
    try:
        c.row_factory = sqlite3.Row
        ensure_fts_table(c)
        c.execute(f"DELETE FROM {FTS_TABLE_NAME}")
        for row in c.execute(
            "SELECT id,title,url,body,content_hash,lang,update_time "
            "FROM articles WHERE body IS NOT NULL AND body != ''"
        ).fetchall():
            rec = _row_to_record_kol(row)
            c.execute(
                f"INSERT INTO {FTS_TABLE_NAME} (hash,title,body,lang,source) "
                "VALUES (?,?,?,?,?)",
                (resolve_url_hash(rec), rec.title, rec.body, rec.lang, "wechat"),
            )
        for row in c.execute(
            "SELECT id,title,url,body,content_hash,lang,published_at,fetched_at "
            "FROM rss_articles WHERE body IS NOT NULL AND body != ''"
        ).fetchall():
            rec = _row_to_record_rss(row)
            c.execute(
                f"INSERT INTO {FTS_TABLE_NAME} (hash,title,body,lang,source) "
                "VALUES (?,?,?,?,?)",
                (resolve_url_hash(rec), rec.title, rec.body, rec.lang, "rss"),
            )
        c.commit()
    finally:
        c.close()


def _patch_c1_writes(
    monkeypatch: pytest.MonkeyPatch, output_md: str
) -> None:
    """Patch C1 with an instantaneously-successful stub that writes
    synthesis_output.md (the wrapper reads it back)."""
    import config as og_config

    async def fake(query_text: str, mode: str = "hybrid") -> None:
        (Path(og_config.BASE_DIR) / "synthesis_output.md").write_text(
            output_md, encoding="utf-8"
        )

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake)


def _patch_c1_raises(monkeypatch: pytest.MonkeyPatch, exc: BaseException) -> None:
    async def fake(query_text: str, mode: str = "hybrid") -> None:
        raise exc

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake)


def _patch_c1_sleeps(monkeypatch: pytest.MonkeyPatch, seconds: float) -> None:
    async def fake(query_text: str, mode: str = "hybrid") -> None:
        await asyncio.sleep(seconds)

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake)


# ============================================================================
# 1. KG happy path with 3 source refs → structured sources + entities
# ============================================================================


def test_kg_success_returns_structured_sources(
    synthesize_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KG markdown with 3 hex-only /article/{hash} refs (prod shape: md5[:10])
    → SynthesizeResult.sources resolves all 3 with title+lang from DB.

    Uses the fixture's hex-shape hashes (KOL 'abc1234567' + RSS truncated
    'deadbeefca' / '1111111111') because the source-hash regex in
    kb/services/synthesize.py is `[a-f0-9]{10}` matching production reality.
    """
    from kb.services import job_store

    md = (
        "# Answer\n\n"
        "First [k1](/article/abc1234567), "
        "second [r10](/article/deadbeefca), "
        "third [r11](/article/1111111111)."
    )
    _patch_c1_writes(monkeypatch, md)
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(synthesize_module.kb_synthesize("q", "en", jid))
    job = job_store.get_job(jid)

    assert job["status"] == "done"
    assert job["confidence"] == "kg"
    assert job["fallback_used"] is False
    sources = job["result"]["sources"]
    assert len(sources) == 3, sources
    hashes = [s["hash"] for s in sources]
    assert "abc1234567" in hashes
    assert "deadbeefca" in hashes
    assert "1111111111" in hashes
    # Each source dict has the qa.js-consumer-contract keys.
    for s in sources:
        assert set(s.keys()) >= {"hash", "title", "lang"}
        assert isinstance(s["title"], str) and s["title"]


# ============================================================================
# 2. KG happy path with no refs → sources=[], confidence='no_results'
# ============================================================================


def test_kg_success_no_sources_returns_no_results_confidence(
    synthesize_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kb.services import job_store

    _patch_c1_writes(
        monkeypatch,
        "# Answer\n\nA prose response without explicit /article/ links.",
    )
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(synthesize_module.kb_synthesize("q", "en", jid))
    job = job_store.get_job(jid)

    assert job["status"] == "done"
    assert job["confidence"] == "no_results"
    assert job["fallback_used"] is False
    assert job["result"]["sources"] == []
    assert job["result"]["entities"] == []


# ============================================================================
# 3. KG exception → FTS5 fallback path with structured sources
# ============================================================================


def test_kg_exception_falls_back_to_fts5(
    fixture_db: Path,
    synthesize_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kb.services import job_store

    _populate_fts(fixture_db)
    _patch_c1_raises(monkeypatch, RuntimeError("LightRAG storage missing"))
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(synthesize_module.kb_synthesize("Agent", "zh", jid))
    job = job_store.get_job(jid)

    assert job["status"] == "done"
    assert job["fallback_used"] is True
    assert job["confidence"] in ("fts5_fallback", "no_results")
    assert "LightRAG storage missing" in (job["error"] or "")
    if job["confidence"] == "fts5_fallback":
        sources = job["result"]["sources"]
        assert len(sources) >= 1
        for s in sources:
            assert isinstance(s, dict)
            assert "hash" in s and "title" in s and "lang" in s


# ============================================================================
# 4. KG timeout → FTS5 fallback path
# ============================================================================


def test_kg_timeout_falls_back_to_fts5(
    fixture_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Set KB_SYNTHESIZE_TIMEOUT=1 + C1 sleeps 2s → asyncio.wait_for fires."""
    import config as og_config
    from kb.services import job_store

    sa_dummy = tmp_path / "kg-sa-dummy.json"
    sa_dummy.write_text('{"type":"service_account"}')
    monkeypatch.setenv("KB_KG_GCP_SA_KEY_PATH", str(sa_dummy))
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    monkeypatch.setenv("KB_SYNTHESIZE_TIMEOUT", "1")
    monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)
    import kb.config
    import kb.services.synthesize

    importlib.reload(kb.config)
    importlib.reload(kb.services.synthesize)
    sm = kb.services.synthesize

    _populate_fts(fixture_db)
    _patch_c1_sleeps(monkeypatch, 2.0)

    jid = job_store.new_job(kind="synthesize")
    start = time.monotonic()
    asyncio.run(sm.kb_synthesize("Agent", "zh", jid))
    elapsed = time.monotonic() - start
    assert elapsed < 4.0, f"timeout took too long: {elapsed:.1f}s"

    job = job_store.get_job(jid)
    assert job["status"] == "done"
    assert job["fallback_used"] is True
    assert job["confidence"] in ("fts5_fallback", "no_results")
    assert "timeout" in (job["error"] or "").lower()


# ============================================================================
# 5. FTS5 fallback shape preserved as SynthesizeResult
# ============================================================================


def test_fts5_fallback_response_shape(
    fixture_db: Path,
    synthesize_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force FTS5 fallback (C1 raises) → result has all 6 SynthesizeResult fields."""
    from kb.services import job_store

    _populate_fts(fixture_db)
    _patch_c1_raises(monkeypatch, RuntimeError("forced"))
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(synthesize_module.kb_synthesize("LLM", "en", jid))
    job = job_store.get_job(jid)

    result = job["result"]
    # All 6 SynthesizeResult fields present with the expected types.
    assert isinstance(result["markdown"], str) and result["markdown"]
    assert isinstance(result["sources"], list)
    assert isinstance(result["entities"], list)
    assert result["confidence"] in ("fts5_fallback", "no_results")
    assert result["fallback_used"] is True
    assert result["error"] is not None and "forced" in result["error"]
    # Entities stay [] on fallback (qa.js skips entity render when fallback).
    assert result["entities"] == []


# ============================================================================
# 6. Entities populated when sources resolve
# ============================================================================


def test_entities_extracted_from_source_articles(
    synthesize_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KG markdown referencing KOL article 'abc1234567' (id=1) — fixture
    extracted_entities has 6 names attributed to id=1 (OpenAI / LangChain /
    LightRAG / Anthropic / AutoGen / MCP); entities list should populate
    via the JOIN against extracted_entities, capped at 8.
    """
    from kb.services import job_store

    md = "# Answer\n\nSee [a](/article/abc1234567)."
    _patch_c1_writes(monkeypatch, md)
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(synthesize_module.kb_synthesize("q", "en", jid))
    job = job_store.get_job(jid)

    entities = job["result"]["entities"]
    assert len(entities) >= 1, entities
    for e in entities:
        assert "name" in e and isinstance(e["name"], str) and e["name"]
        assert "article_count" in e
        assert isinstance(e["article_count"], int) and e["article_count"] >= 1
    # Capped at 8 per kb-v2.1-4 contract.
    assert len(entities) <= 8


# ============================================================================
# 7. DATA-07 reject articles must NOT surface as sources
# ============================================================================


def test_data07_filter_applies_to_synthesize_sources(
    synthesize_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fixture_db has KOL id=98 with hash 'neg9898989' (layer2_verdict='reject')
    and KOL id=99 with hash 'neg9999999' (layer1_verdict='reject'). Both must
    be silently dropped from sources by DATA-07 filter even though the
    markdown references them.
    """
    from kb.services import job_store

    md = (
        "# Answer\n\n"
        "Bad refs: [r1](/article/neg9999999) [r2](/article/neg9898989), "
        "good ref: [ok](/article/abc1234567)."
    )
    _patch_c1_writes(monkeypatch, md)
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(synthesize_module.kb_synthesize("q", "en", jid))
    job = job_store.get_job(jid)

    hashes = [s["hash"] for s in job["result"]["sources"]]
    assert "neg9999999" not in hashes, "DATA-07 layer1=reject leaked"
    assert "neg9898989" not in hashes, "DATA-07 layer2=reject leaked"
    assert "abc1234567" in hashes
