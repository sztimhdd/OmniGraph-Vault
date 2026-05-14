"""Tests for kb/services/synthesize.py (the QA-01 wrapper around C1).

Skill discipline (per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):

    Skill(skill="writing-tests", args="Unit tests for the wrapper module. test_lang_directive_for: 3 cases (zh/en/unsupported). test_kb_synthesize_*: monkeypatch kg_synthesize.synthesize_response with an async stub that captures query_text args; monkeypatch the synthesis_output.md file by writing to a temp BASE_DIR; verify job_store before/after state via get_job(jid). Use asyncio.run to drive the async wrapper from sync tests.")

Behaviors covered (8):
    1. lang_directive_for('zh') == '请用中文回答。\\n\\n'
    2. lang_directive_for('en') == 'Please answer in English.\\n\\n'
    3. lang_directive_for('fr') == '' (defensive — unsupported lang)
    4. kb_synthesize prepends EN directive before C1 query_text
    5. kb_synthesize prepends ZH directive before C1 query_text
    6. kb_synthesize reads synthesis_output.md after C1, populates job result
    7. kb_synthesize on C1 exception → job status='failed' with error
    8. kb_synthesize on success → confidence='kg', fallback_used=False
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
    _patch_base_dir(tmp_path, monkeypatch)

    async def fake_fail(*a, **kw):
        raise RuntimeError("LightRAG storage missing")

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_fail)
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(kb_synth_mod.kb_synthesize("q", "zh", jid))
    job = job_store.get_job(jid)
    assert job is not None
    assert job["status"] == "failed"
    assert "LightRAG storage missing" in job["error"]
    # kb-3-09 will replace this branch with status='done' + confidence='fts5_fallback'.


def test_kb_synthesize_success_sets_kg_confidence(tmp_path, monkeypatch, captured_query):
    _patch_base_dir(tmp_path, monkeypatch)
    _patch_c1(monkeypatch, captured_query)
    jid = job_store.new_job(kind="synthesize")
    asyncio.run(kb_synth_mod.kb_synthesize("q", "zh", jid))
    job = job_store.get_job(jid)
    assert job["confidence"] == "kg"
    assert job["fallback_used"] is False
