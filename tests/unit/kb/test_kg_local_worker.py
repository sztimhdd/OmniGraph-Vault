"""Unit tests for arx-3 K1: ``_kg_local_worker`` FTS fallback when KG returns
non-empty markdown without ``/article/{hash}.html`` citations.

Pre-fix (kb/api_routers/search.py:_kg_local_worker, ~line 126):
    hashes = list(dict.fromkeys(_HASH_PAT.findall(markdown or "")))
    for h in hashes:
        ...resolve via get_article_by_hash...
    # No fallback when hashes == [] but markdown is substantive.
    # results stays empty → /api/search/kg/{job_id} polls back results=[]
    # and the UI shows "no results" despite a real KG answer existing.

Post-fix:
    if not results and markdown and markdown.strip():
        try:
            from kb.services import search_index as si
            for (h, t, snip, lg, src) in si.fts_query(query, lang=None, limit=10):
                results.append({...})
        except Exception as fts_err:
            logger.warning("kg-search FTS fallback failed: %s", fts_err)

These two tests are unit-scope: they monkeypatch the LightRAG entry point
(``kg_synthesize.synthesize_response``) and the data-layer accessors
(``kb.services.search_index.fts_query``, ``kb.data.article_query.get_article_by_hash``)
to remove the DB + storage dependency, leaving the citation-extraction +
fallback branch as the sole behavior under test.

Skill(skill="writing-tests", args="Unit-isolated tests for the _kg_local_worker FTS fallback. No DB, no LightRAG storage — patch the C1 stub, fts_query and get_article_by_hash directly. Driver awaits the async _kg_local_worker. Test 1 is the RED case — fails pre-fix because results=[] is committed despite non-empty markdown without citations.")
"""
from __future__ import annotations

import asyncio
import importlib

import pytest


@pytest.fixture
def search_mod(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Reload kb.api_routers.search with KG mode enabled and BASE_DIR isolated.

    KG_MODE_AVAILABLE must be True so that the route module (which the worker
    lives inside) loads cleanly. The worker function itself doesn't gate on
    KG_MODE_AVAILABLE — that's the route handler's job — but reloading the
    module forces a clean state for monkeypatching.
    """
    sa_dummy = tmp_path / "kg-sa-dummy.json"
    sa_dummy.write_text('{"type":"service_account"}')
    monkeypatch.setenv("KB_KG_GCP_SA_KEY_PATH", str(sa_dummy))

    import config as og_config
    monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)

    import kb.config
    import kb.services.synthesize
    import kb.api_routers.search as search

    importlib.reload(kb.config)
    importlib.reload(kb.services.synthesize)
    importlib.reload(search)
    return search


def test_kg_local_worker_falls_back_to_fts_when_no_citations(
    search_mod, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED — non-empty markdown without /article/ refs MUST trigger FTS fallback.

    Pre-fix this asserts an empty results list (the bug — KG answered, no
    citations parsed, FTS not consulted, UI sees "no results").

    Post-fix this asserts the fts_query fallback rows are committed to the
    job — at least 1 result, with the synthetic hash 'fbk0000001'.

    The arx-3 K1 root cause: when the LLM forgets to cite or the citation
    template falls off, the KG search endpoint silently returns 0 results —
    even when the user's query trivially matches FTS index entries. The
    fallback restores the FTS-only view for that query.
    """
    async def fake_c1(query_text, mode="hybrid", **_kw):
        return "# Long-form answer\n\nDetailed prose, no citations."

    fake_fts_rows = [
        ("fbk0000001", "Fallback Title", "Fallback snippet…", "en", "wechat"),
        ("fbk0000002", "Second Fallback", "Another snippet…", "en", "wechat"),
    ]

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_c1)
    monkeypatch.setattr(
        "kb.services.search_index.fts_query",
        lambda q, lang=None, limit=20, conn=None: fake_fts_rows,
    )

    jid = search_mod.job_store.new_job(kind="kg_search")
    asyncio.run(
        search_mod._kg_local_worker(jid, "agent", None, asyncio.Lock())
    )

    job = search_mod.job_store.get_job(jid)
    assert job is not None
    assert job["status"] == "done", job
    results = job["result"]
    assert isinstance(results, list)
    assert len(results) >= 1, (
        "K1: non-empty markdown without /article/ citations must trigger "
        f"FTS fallback. Pre-fix this is empty. results={results}"
    )
    hashes = [r["hash"] for r in results]
    assert "fbk0000001" in hashes, (
        f"K1: FTS fallback row 'fbk0000001' missing. results={results}"
    )


def test_kg_local_worker_resolves_citations_when_present(
    search_mod, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path — markdown WITH /article/ refs resolves via DATA-05.

    Defensive regression: the K1 patch must NOT break the citations-present
    path. When the LLM cites correctly, ``get_article_by_hash`` resolves each
    cited hash and the result list contains those records — FTS fallback
    must NOT fire (results was non-empty after the citation loop).
    """
    from kb.data.article_query import ArticleRecord

    async def fake_c1(query_text, mode="hybrid", **_kw):
        return (
            "# Answer\n\nSee [/article/abc1234567.html] for context."
        )

    fake_record = ArticleRecord(
        id=1,
        source="wechat",
        title="Cited Article",
        url="https://example.com/x",
        body="Body text for snippet derivation.",
        content_hash="abc1234567",
        lang="en",
        update_time="2026-01-01T00:00:00",
    )

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_c1)
    monkeypatch.setattr(
        "kb.data.article_query.get_article_by_hash",
        lambda h, conn=None: fake_record if h == "abc1234567" else None,
    )

    # FTS fallback should NOT fire here; sentinel raises if it does.
    def _fts_must_not_fire(*a, **kw):
        raise AssertionError(
            "FTS fallback fired despite citations being present + resolved"
        )

    monkeypatch.setattr(
        "kb.services.search_index.fts_query", _fts_must_not_fire
    )

    jid = search_mod.job_store.new_job(kind="kg_search")
    asyncio.run(
        search_mod._kg_local_worker(jid, "agent", None, asyncio.Lock())
    )

    job = search_mod.job_store.get_job(jid)
    assert job is not None
    assert job["status"] == "done", job
    results = job["result"]
    assert len(results) == 1, results
    assert results[0]["hash"] == "abc1234567"
    assert results[0]["title"] == "Cited Article"
    assert results[0]["lang"] == "en"
    assert results[0]["source"] == "wechat"
