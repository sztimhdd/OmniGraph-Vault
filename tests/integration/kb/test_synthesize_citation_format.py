"""Integration tests for kb-v2.2-4 QA citation format enforcement (FU-1).

Root cause fixed: QA mode sent bare question to LightRAG, which returned
Chinese "(来源:Entity X)" citations. _SOURCE_HASH_PATTERN couldn't extract
them → sources=[] → confidence='no_results' even with real content.

Fix verified here: QA prompt template instructs /article/{hash}.html format,
so when C1 returns citations in that format, _resolve_sources_from_markdown
extracts them and confidence='kg'.

Behaviors covered:
    1. QA mode + C1 returns /article/{hash} citations → confidence='kg', sources>0
    2. QA mode + C1 returns Chinese '来源:' format → confidence='kg' (G-remove,
       markdown is substantive even though sources=[]), no crash
    3. long_form mode unaffected (regression guard)
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from kb.services import job_store
from kb.services import synthesize as kb_synth_mod


# ---- helpers (mirror test_synthesize_wrapper.py patterns) ------------------


@pytest.fixture
def captured_query() -> dict:
    return {"text": None, "mode": None}


def _patch_c1_returns(
    monkeypatch: pytest.MonkeyPatch,
    captured: dict,
    output: str,
) -> None:
    async def fake_synthesize(query_text: str, mode: str = "hybrid"):
        captured["text"] = query_text
        captured["mode"] = mode
        return output

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_synthesize)


def _patch_base_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import config as og_config

    sa_dummy = tmp_path / "kg-sa-dummy.json"
    sa_dummy.write_text('{"type":"service_account"}')
    monkeypatch.setenv("KB_KG_GCP_SA_KEY_PATH", str(sa_dummy))
    monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(kb_synth_mod, "KG_MODE_AVAILABLE", True)
    monkeypatch.setattr(kb_synth_mod, "KG_MODE_UNAVAILABLE_REASON", "")


def _reload_synthesize(monkeypatch: pytest.MonkeyPatch) -> object:
    import importlib

    import kb.config
    import kb.services.synthesize as sm

    importlib.reload(kb.config)
    importlib.reload(sm)
    return sm


# ---- tests -----------------------------------------------------------------


def test_qa_mode_url_citations_resolve_to_kg_confidence(
    tmp_path, fixture_db, monkeypatch, captured_query
):
    """FU-1 happy path: C1 returns /article/{hash}.html citations in QA mode
    → _resolve_sources_from_markdown extracts them → confidence='kg', sources≥1.

    fixture_db has KOL hash 'abc1234567' (id=1, '测试文章一', zh-CN).
    """
    _patch_base_dir(tmp_path, monkeypatch)
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    _patch_c1_returns(
        monkeypatch,
        captured_query,
        output=(
            "## Answer\n\n"
            "Agent frameworks include LangChain [/article/abc1234567.html] "
            "and AutoGen [/article/kol3000003a.html]."
        ),
    )
    sm = _reload_synthesize(monkeypatch)
    # Re-apply KG_MODE_AVAILABLE after reload
    monkeypatch.setattr(sm, "KG_MODE_AVAILABLE", True)
    monkeypatch.setattr(sm, "KG_MODE_UNAVAILABLE_REASON", "")

    jid = job_store.new_job(kind="synthesize")
    asyncio.run(sm.kb_synthesize("Agent 框架有哪些?", "zh", jid, mode="qa"))

    job = job_store.get_job(jid)
    assert job is not None
    assert job["status"] == "done"
    assert job["confidence"] == "kg", (
        f"FU-1: QA mode with URL citations should produce confidence='kg', got {job}"
    )
    assert job["fallback_used"] is False
    sources = job["result"]["sources"]
    assert len(sources) >= 1, "At least 1 source chip should resolve from DB"
    hashes = [s["hash"] for s in sources]
    assert "abc1234567" in hashes


def test_qa_mode_chinese_citation_format_returns_kg_confidence(
    tmp_path, monkeypatch, captured_query
):
    """G-remove contract: substantive markdown without /article/{hash} URL
    citations now returns confidence='kg' (was 'no_results' pre-G-remove).
    The Chinese '(来源:...)' prose is real content the LLM produced — under
    the bug 2c gate it was hidden behind a no_results banner; post-G-remove
    the markdown surfaces under confidence='kg' and the empty sources chip
    set is shown alongside (no crash, NEVER-500 still holds).

    See DECISION.md G-remove section + commit a0b0038 (RED tests fixing
    this contract forward) + the structurally-identical pin update in
    test_synthesize_structured.py:test_kg_success_markdown_present_no_sources_returns_kg_confidence.
    """
    _patch_base_dir(tmp_path, monkeypatch)
    _patch_c1_returns(
        monkeypatch,
        captured_query,
        output=(
            "LangChain 是一个 Agent 框架。(来源:LangChain Agent 描述)"
            "\n\nAutoGen 也是常用框架。(来源:AutoGen 介绍)"
        ),
    )
    sm = _reload_synthesize(monkeypatch)
    monkeypatch.setattr(sm, "KG_MODE_AVAILABLE", True)
    monkeypatch.setattr(sm, "KG_MODE_UNAVAILABLE_REASON", "")

    jid = job_store.new_job(kind="synthesize")
    asyncio.run(sm.kb_synthesize("Agent 框架有哪些?", "zh", jid, mode="qa"))

    job = job_store.get_job(jid)
    assert job is not None
    assert job["status"] == "done", "NEVER-500: Chinese citations should degrade, not crash"
    assert job["confidence"] == "kg"
    assert job["fallback_used"] is False
    assert job["result"]["markdown"]
    assert job["result"]["sources"] == []


def test_long_form_mode_unaffected_by_qa_template_change(
    tmp_path, fixture_db, monkeypatch, captured_query
):
    """Regression: long_form mode still wraps question in research template,
    C1 query_text contains 1500-3000 word-count instruction, not QA template text.
    """
    _patch_base_dir(tmp_path, monkeypatch)
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    _patch_c1_returns(
        monkeypatch,
        captured_query,
        output="# Research\n\n[/article/abc1234567.html]",
    )
    sm = _reload_synthesize(monkeypatch)
    monkeypatch.setattr(sm, "KG_MODE_AVAILABLE", True)
    monkeypatch.setattr(sm, "KG_MODE_UNAVAILABLE_REASON", "")

    jid = job_store.new_job(kind="synthesize")
    asyncio.run(sm.kb_synthesize("RAG 发展趋势", "zh", jid, mode="long_form"))

    # long_form template has word-count "1500-3000" instruction; QA template does not
    assert captured_query["text"] is not None
    assert "1500-3000" in captured_query["text"], (
        "long_form mode must use _LONG_FORM_PROMPT_TEMPLATE_ZH, not QA template"
    )
    assert "200-400" not in captured_query["text"], (
        "QA template word-count must NOT appear in long_form mode"
    )
    job = job_store.get_job(jid)
    assert job["status"] == "done"
    assert job["confidence"] == "kg"
