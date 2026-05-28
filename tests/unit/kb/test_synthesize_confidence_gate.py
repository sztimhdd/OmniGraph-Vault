"""Unit tests for arx-3 G-remove: ``confidence`` gate decoupled from sources.

Pre-fix (kb/services/synthesize.py:552):
    confidence = "kg" if sources else "no_results"

Post-fix:
    confidence = "kg" if markdown.strip() else "no_results"

The C1 LightRAG can return a substantive markdown answer that omits the
``/article/{hash}.html`` citation pattern (LLM forgot to cite, or the prompt
template fell off). Pre-fix, that empties ``sources`` and the response is
flagged ``no_results`` despite carrying a real long-form answer. Post-fix, the
gate keys off ``markdown`` directly and only ``sources``/``entities`` may be
empty — the answer itself is preserved with confidence='kg'.

These three tests are unit-scope: they monkeypatch ``kg_synthesize.synthesize_response``
and ``kb.services.synthesize._resolve_sources_from_markdown`` to remove the DB
dependency, leaving the confidence-gate branch as the sole behavior under test.

Skill(skill="writing-tests", args="Unit-isolated tests for the confidence-gate decision. No DB, no fixture_db — patch the source-resolver and the C1 stub directly. Driver runs an event loop on the async kb_synthesize wrapper. Test 1 is the RED case — fails pre-fix because sources=[] forces no_results despite non-empty markdown.")
"""
from __future__ import annotations

import asyncio
import importlib

import pytest


@pytest.fixture
def synth_mod(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Reload kb.services.synthesize with KG mode enabled and BASE_DIR isolated.

    KG_MODE_AVAILABLE must be True so kb_synthesize does NOT short-circuit into
    the FTS5 fallback before it reaches the confidence-gate line we're pinning.
    """
    sa_dummy = tmp_path / "kg-sa-dummy.json"
    sa_dummy.write_text('{"type":"service_account"}')
    monkeypatch.setenv("KB_KG_GCP_SA_KEY_PATH", str(sa_dummy))

    import config as og_config
    monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)

    import kb.config
    import kb.services.synthesize as svc

    importlib.reload(kb.config)
    importlib.reload(svc)
    return svc


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if asyncio.get_event_loop().is_running() is False else asyncio.run(coro)


def test_confidence_kg_when_markdown_nonempty_without_citations(
    synth_mod, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED — non-empty markdown without /article/ refs MUST yield confidence='kg'.

    Pre-fix this asserts False (sources=[] → 'no_results').
    Post-fix this asserts True (markdown.strip() truthy → 'kg').

    The arx-3 root cause: a long-form answer ('Here is a detailed explanation
    ...') with zero citations is a real product result, not a no-result. The
    UI must show it under confidence='kg', not the fts5_fallback 'no_results'
    chip set (which suppresses the markdown render in qa.js).
    """
    async def fake_c1(query_text, mode="hybrid", **_kw):
        return "# Long-form answer\n\nDetailed prose, no citations."

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_c1)
    # Stub source/entity resolvers so no DB is hit.
    monkeypatch.setattr(synth_mod, "_resolve_sources_from_markdown", lambda md: [])
    monkeypatch.setattr(synth_mod, "_resolve_entities_for_sources", lambda hs: [])
    # Skip wiki context lookup (network/DB).
    async def _no_wiki(_q):
        return ""
    monkeypatch.setattr(synth_mod, "resolve_wiki_context", _no_wiki)

    jid = synth_mod.job_store.new_job(kind="synthesize")
    asyncio.run(synth_mod.kb_synthesize("anything", "en", jid, "qa"))

    job = synth_mod.job_store.get_job(jid)
    assert job is not None
    assert job["status"] == "done", job
    assert job["fallback_used"] is False, "C1 succeeded — no fallback should fire"
    assert job["confidence"] == "kg", (
        "G-remove: non-empty markdown w/o citations must be 'kg', not "
        f"'no_results'. job={job}"
    )
    assert job["result"]["markdown"].startswith("# Long-form answer")


def test_confidence_no_results_when_markdown_empty(
    synth_mod, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty markdown MUST yield confidence='no_results' (passes pre AND post fix).

    Defensive regression — the post-fix gate must still gate empty markdown to
    'no_results'. If a future change inverts the truthiness check, this test
    catches it.
    """
    async def fake_c1(query_text, mode="hybrid", **_kw):
        return ""

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_c1)
    monkeypatch.setattr(synth_mod, "_resolve_sources_from_markdown", lambda md: [])
    monkeypatch.setattr(synth_mod, "_resolve_entities_for_sources", lambda hs: [])
    async def _no_wiki(_q):
        return ""
    monkeypatch.setattr(synth_mod, "resolve_wiki_context", _no_wiki)

    jid = synth_mod.job_store.new_job(kind="synthesize")
    asyncio.run(synth_mod.kb_synthesize("q", "en", jid, "qa"))

    job = synth_mod.job_store.get_job(jid)
    assert job is not None
    assert job["status"] == "done", job
    assert job["confidence"] == "no_results", job


def test_confidence_kg_preserved_when_markdown_has_citations(
    synth_mod, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path — citations resolve to ArticleSource — passes pre AND post fix.

    Defensive regression: the post-fix change must NOT break the case where
    sources DO resolve. confidence stays 'kg' and sources are non-empty.
    """
    async def fake_c1(query_text, mode="hybrid", **_kw):
        return "# Answer\n\nSee [a](/article/abc1234567)."

    fake_source = synth_mod.ArticleSource(
        hash="abc1234567", title="Test", lang="en",
    )
    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_c1)
    monkeypatch.setattr(
        synth_mod, "_resolve_sources_from_markdown", lambda md: [fake_source]
    )
    monkeypatch.setattr(synth_mod, "_resolve_entities_for_sources", lambda hs: [])
    async def _no_wiki(_q):
        return ""
    monkeypatch.setattr(synth_mod, "resolve_wiki_context", _no_wiki)

    jid = synth_mod.job_store.new_job(kind="synthesize")
    asyncio.run(synth_mod.kb_synthesize("q", "en", jid, "qa"))

    job = synth_mod.job_store.get_job(jid)
    assert job is not None
    assert job["status"] == "done", job
    assert job["confidence"] == "kg", job
    assert len(job["result"]["sources"]) == 1
    assert job["result"]["sources"][0]["hash"] == "abc1234567"
