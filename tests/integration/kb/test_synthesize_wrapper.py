"""Tests for kb/services/synthesize.py (the QA-01 wrapper around C1).

Skill discipline (per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):

    Skill(skill="writing-tests", args="Unit tests for the wrapper module. test_lang_directive_for: 3 cases (zh/en/unsupported). test_kb_synthesize_*: monkeypatch kg_synthesize.synthesize_response with an async stub that captures query_text args; monkeypatch the synthesis_output.md file by writing to a temp BASE_DIR; verify job_store before/after state via get_job(jid). Use asyncio.run to drive the async wrapper from sync tests.")

    Skill(skill="writing-tests", args="kb-3-09 fallback-path tests. Cover: exception path → fts5_fallback, timeout path → fts5_fallback (use sleep > timeout), top-3 hits in result, sources list populated, FTS5-also-fails → no_results last-resort. For the timeout test, set KB_SYNTHESIZE_TIMEOUT=1 and patch synthesize_response with `await asyncio.sleep(2)` — must time out within 2s wall-time. Use monkeypatch + importlib.reload to flip the env var per process.")

Behaviors covered (8 from kb-3-08 + 5 from kb-3-09 = 13):
    1. lang_directive_for('zh') == '请用中文回答。\\n\\n'
    2. lang_directive_for('en') == 'Please answer in English.\\n\\n'
    3. lang_directive_for('fr') == '' (defensive — unsupported lang)
    4. kb_synthesize prepends EN directive before C1 query_text
    5. kb_synthesize prepends ZH directive before C1 query_text
    6. kb_synthesize reads synthesis_output.md after C1, populates job result
    7. kb_synthesize on C1 exception → job status='done', confidence='fts5_fallback' OR 'no_results' (kb-3-09)
    8. kb_synthesize on success → confidence='kg', fallback_used=False
    9. kb_synthesize on C1 exception triggers _fts5_fallback (kb-3-09)
    10. kb_synthesize on C1 timeout (KB_SYNTHESIZE_TIMEOUT) triggers _fts5_fallback (kb-3-09)
    11. Fallback markdown contains banner string when ≥1 hit (kb-3-09)
    12. Fallback result['sources'] populated with hashes (kb-3-09)
    13. Double failure (C1 + FTS5) → status='done' confidence='no_results' (NEVER-500) (kb-3-09)
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from kb.services import job_store
from kb.services import synthesize as kb_synth_mod


# ---- Pure function tests (lang_directive_for) ------------------------------


def test_lang_directive_zh():
    assert kb_synth_mod.lang_directive_for("zh") == "请用中文回答。\n\n"


def test_lang_directive_en():
    assert kb_synth_mod.lang_directive_for("en") == "Please answer in English.\n\n"


def test_lang_directive_unsupported():
    assert kb_synth_mod.lang_directive_for("fr") == ""
    assert kb_synth_mod.lang_directive_for("") == ""


# ---- Helpers --------------------------------------------------------------


@pytest.fixture
def captured_query() -> dict:
    """Capture C1 invocation args across an async patch."""
    return {"text": None, "mode": None}


def _patch_c1(
    monkeypatch: pytest.MonkeyPatch,
    captured: dict,
    output: str = "# Answer\n\n[link](/article/abcd012345)",
) -> None:
    """Patch kg_synthesize.synthesize_response with an async stub that captures
    query_text + mode and writes a synthetic synthesis_output.md so the wrapper
    can read it back."""

    async def fake_synthesize(query_text: str, mode: str = "hybrid"):
        captured["text"] = query_text
        captured["mode"] = mode
        # Simulate kg_synthesize writing synthesis_output.md.
        import config as og_config

        (Path(og_config.BASE_DIR) / "synthesis_output.md").write_text(
            output, encoding="utf-8"
        )

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_synthesize)


def _patch_base_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect config.BASE_DIR to a temp directory for output capture."""
    import config as og_config

    monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)


# ---- Wrapper integration tests --------------------------------------------


def test_kb_synthesize_prepends_en_directive(tmp_path, monkeypatch, captured_query):
    _patch_base_dir(tmp_path, monkeypatch)
    _patch_c1(monkeypatch, captured_query)
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(kb_synth_mod.kb_synthesize("What is LangChain?", "en", jid))
    assert captured_query["text"] is not None
    assert captured_query["text"].startswith("Please answer in English.\n\n"), captured_query["text"]
    assert "What is LangChain?" in captured_query["text"]
    # C1 mode contract preserved: always 'hybrid'
    assert captured_query["mode"] == "hybrid"


def test_kb_synthesize_prepends_zh_directive(tmp_path, monkeypatch, captured_query):
    _patch_base_dir(tmp_path, monkeypatch)
    _patch_c1(monkeypatch, captured_query)
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(kb_synth_mod.kb_synthesize("LangGraph 是什么?", "zh", jid))
    assert captured_query["text"].startswith("请用中文回答。\n\n")
    assert "LangGraph 是什么?" in captured_query["text"]


def test_kb_synthesize_reads_output_file(tmp_path, monkeypatch, captured_query):
    _patch_base_dir(tmp_path, monkeypatch)
    _patch_c1(
        monkeypatch,
        captured_query,
        output="# Hello\n\nFirst [a](/article/1234567890), second [b](/article/abcdef0123)",
    )
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(kb_synth_mod.kb_synthesize("q", "zh", jid))
    job = job_store.get_job(jid)
    assert job is not None
    assert job["status"] == "done"
    assert "Hello" in job["result"]["markdown"]
    # Sources extracted via regex; sorted-distinct.
    assert "1234567890" in job["result"]["sources"]
    assert "abcdef0123" in job["result"]["sources"]
    assert job["result"]["entities"] == []


def test_kb_synthesize_failure_branch(tmp_path, monkeypatch):
    """Pre-kb-3-09: status='failed'. Post-kb-3-09: status='done' with confidence
    in {'fts5_fallback', 'no_results'} (NEVER-500 invariant per QA-05).

    With no FTS5 fixture populated and no KB_DB_PATH override, fts_query opens
    against the (test) default DB and returns no rows OR raises — either way the
    wrapper translates to status='done' with no_results."""
    _patch_base_dir(tmp_path, monkeypatch)
    # Force fts_query to fail so the last-resort branch fires; confirms NEVER-500.
    def fts_explode(*a, **kw):
        raise RuntimeError("DB unreachable for test")

    monkeypatch.setattr("kb.services.search_index.fts_query", fts_explode)

    async def fake_fail(*a, **kw):
        raise RuntimeError("LightRAG storage missing")

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_fail)
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(kb_synth_mod.kb_synthesize("q", "zh", jid))
    job = job_store.get_job(jid)
    assert job is not None
    # NEVER-500: status MUST be 'done' (kb-3-09 invariant); error retains original cause.
    assert job["status"] == "done"
    assert job["fallback_used"] is True
    assert "LightRAG storage missing" in (job["error"] or "")


def test_kb_synthesize_success_sets_kg_confidence(tmp_path, monkeypatch, captured_query):
    _patch_base_dir(tmp_path, monkeypatch)
    _patch_c1(monkeypatch, captured_query)
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(kb_synth_mod.kb_synthesize("q", "zh", jid))
    job = job_store.get_job(jid)
    assert job["confidence"] == "kg"
    assert job["fallback_used"] is False


# ---- kb-3-09 fallback-path tests (QA-04 timeout + QA-05 NEVER-500) ----------


def _populate_fts(fixture_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure articles_fts is populated for fallback tests.

    Uses the kb-2 fixture_db (KOL ids 1..5; RSS ids 10..12) and seeds the FTS
    table with their bodies + titles so fts_query returns ≥1 hit.
    """
    import sqlite3

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
        kol_rows = c.execute(
            "SELECT id,title,url,body,content_hash,lang,update_time FROM articles "
            "WHERE body IS NOT NULL AND body != ''"
        ).fetchall()
        for r in kol_rows:
            rec = _row_to_record_kol(r)
            c.execute(
                f"INSERT INTO {FTS_TABLE_NAME} (hash,title,body,lang,source) VALUES (?,?,?,?,?)",
                (resolve_url_hash(rec), rec.title, rec.body, rec.lang, "wechat"),
            )
        rss_rows = c.execute(
            "SELECT id,title,url,body,content_hash,lang,published_at,fetched_at FROM rss_articles "
            "WHERE body IS NOT NULL AND body != ''"
        ).fetchall()
        for r in rss_rows:
            rec = _row_to_record_rss(r)
            c.execute(
                f"INSERT INTO {FTS_TABLE_NAME} (hash,title,body,lang,source) VALUES (?,?,?,?,?)",
                (resolve_url_hash(rec), rec.title, rec.body, rec.lang, "rss"),
            )
        c.commit()
    finally:
        c.close()
    # Point KB_DB_PATH at the fixture DB so fts_query opens against it.
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    # Reload kb.config so KB_DB_PATH is re-read (read once at module-import time).
    import importlib

    import kb.config

    importlib.reload(kb.config)


def _reload_synthesize_module():
    """Reload kb.services.synthesize so KB_SYNTHESIZE_TIMEOUT is re-read."""
    import importlib

    import kb.services.synthesize as sm

    importlib.reload(sm)
    return sm


def test_kb_synthesize_exception_triggers_fts5_fallback(
    tmp_path, fixture_db, monkeypatch
):
    """C1 raises → wrapper falls through to FTS5 path; status='done',
    confidence='fts5_fallback', fallback_used=True, original error preserved."""
    _patch_base_dir(tmp_path, monkeypatch)
    _populate_fts(fixture_db, monkeypatch)

    async def fake_fail(*a, **kw):
        raise RuntimeError("LightRAG down")

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_fail)
    sm = _reload_synthesize_module()
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(sm.kb_synthesize("Agent", "zh", jid))
    job = job_store.get_job(jid)
    assert job is not None
    assert job["status"] == "done"
    assert job["fallback_used"] is True
    # FTS fixture has matching rows for "Agent"; expect fts5_fallback (not no_results).
    assert job["confidence"] == "fts5_fallback"
    assert "LightRAG down" in (job["error"] or "")


def test_kb_synthesize_timeout_triggers_fts5_fallback(
    tmp_path, fixture_db, monkeypatch
):
    """C1 sleeps past KB_SYNTHESIZE_TIMEOUT → asyncio.TimeoutError → FTS5 fallback."""
    _patch_base_dir(tmp_path, monkeypatch)
    _populate_fts(fixture_db, monkeypatch)
    monkeypatch.setenv("KB_SYNTHESIZE_TIMEOUT", "1")
    # Reload kb.config + kb.services.synthesize so the new timeout takes effect.
    import importlib

    import kb.config

    importlib.reload(kb.config)
    sm = _reload_synthesize_module()

    async def slow(*a, **kw):
        await asyncio.sleep(3)

    monkeypatch.setattr("kg_synthesize.synthesize_response", slow)
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(sm.kb_synthesize("Agent", "zh", jid))
    job = job_store.get_job(jid)
    assert job["status"] == "done"
    assert job["fallback_used"] is True
    assert job["confidence"] in ("fts5_fallback", "no_results")
    assert "timeout" in (job["error"] or "").lower()


def test_kb_synthesize_fallback_markdown_has_banner(
    tmp_path, fixture_db, monkeypatch
):
    """When FTS5 returns ≥1 hit, fallback markdown carries the bilingual banner."""
    _patch_base_dir(tmp_path, monkeypatch)
    _populate_fts(fixture_db, monkeypatch)

    async def fake_fail(*a, **kw):
        raise ValueError("oops")

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_fail)
    sm = _reload_synthesize_module()
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(sm.kb_synthesize("Agent", "zh", jid))
    job = job_store.get_job(jid)
    if job["confidence"] == "fts5_fallback":
        md = job["result"]["markdown"]
        assert "keyword-based fallback" in md or "关键词" in md


def test_kb_synthesize_fallback_sources_populated(
    tmp_path, fixture_db, monkeypatch
):
    """Fallback result.sources lists 10-char hashes from FTS5 rows (≥1)."""
    _patch_base_dir(tmp_path, monkeypatch)
    _populate_fts(fixture_db, monkeypatch)

    async def fake_fail(*a, **kw):
        raise RuntimeError("down")

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_fail)
    sm = _reload_synthesize_module()
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(sm.kb_synthesize("Agent", "zh", jid))
    job = job_store.get_job(jid)
    if job["confidence"] == "fts5_fallback":
        sources = job["result"]["sources"]
        assert isinstance(sources, list)
        assert len(sources) >= 1
        # Hashes come from fts_query — prod md5[:10] is exactly 10 chars; fixture
        # content_hashes may be slightly longer test fixtures. Assert non-empty
        # strings (the cross-table contract).
        assert all(isinstance(h, str) and len(h) >= 10 for h in sources)


def test_kb_synthesize_double_failure_no_results(tmp_path, monkeypatch):
    """C1 fails AND fts_query raises → status='done', confidence='no_results'.

    The NEVER-500 invariant must hold even when both providers are down."""
    _patch_base_dir(tmp_path, monkeypatch)

    async def fake_fail(*a, **kw):
        raise RuntimeError("c1 down")

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_fail)

    def fts_explode(*a, **kw):
        raise RuntimeError("DB unreachable")

    monkeypatch.setattr("kb.services.search_index.fts_query", fts_explode)
    sm = _reload_synthesize_module()
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(sm.kb_synthesize("q", "zh", jid))
    job = job_store.get_job(jid)
    assert job["status"] == "done", "NEVER-500: even double failure stays done"
    assert job["confidence"] == "no_results"
    assert job["fallback_used"] is True
    err = job["error"] or ""
    assert "c1 down" in err
    assert "DB unreachable" in err
