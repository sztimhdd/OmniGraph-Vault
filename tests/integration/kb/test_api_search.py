"""Integration tests for /api/search + /api/search/{job_id} — kb-3-06.

Coverage matrix:
    1. GET /api/search?q=&mode=fts → 200 + {items, total, mode}
    2. lang filter excludes non-matching rows (SEARCH-03)
    3. limit clamps result count
    4. empty q → 422 (validation_error)
    5. default mode is fts when omitted
    6. mode=kg → 202 + {job_id, status='running', mode='kg'}
    7. /api/search/{job_id} initial state == 'running'
    8. /api/search/<unknown> → 404
    9. After kg job completes (mocked search), polling returns status='done' + result
   10. P50 FTS5 latency < 100ms (API-04 contract)
   11. DATA-07 active by default — negative-case rows excluded from FTS hits

Skill(skill="python-patterns", args="TestClient + monkeypatch.setenv + importlib.reload chain so router picks up KB_DB_PATH pointing at fixture_db AND KB_SEARCH_BYPASS_QUALITY off. monkeypatch on omnigraph_search.query.search to avoid LightRAG calls (the only mock — external HTTP / async dependency).")

Skill(skill="writing-tests", args="Real SQLite throughout for the FTS5 path. KG path mocks omnigraph_search.query.search since LightRAG storage isn't available in CI. Tests assert observable HTTP behavior (status code, body shape), not internal job_store state.")
"""
from __future__ import annotations

import importlib
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---- App-client fixture ----------------------------------------------------


@pytest.fixture
def app_client(
    fixture_db: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> TestClient:
    """TestClient pointed at fixture_db with FTS5 index pre-populated.

    Reload chain: kb.config (picks up KB_DB_PATH) -> kb.services.search_index
    (picks up KB_SEARCH_BYPASS_QUALITY) -> kb.api_routers.search
    (picks up reloaded service module) -> kb.api (picks up reloaded router).

    Same KB_DB_PATH-only-reload pattern that kb-3-05 documented (avoid reloading
    kb.data.article_query — would invalidate dataclass identity for downstream
    tests).

    kb-v2.1-1: KB_KG_GCP_SA_KEY_PATH points at a tmp dummy SA file so
    KG_MODE_AVAILABLE evaluates True, preserving the kb-3-06 dispatch tests
    that mock omnigraph_search.query.search. The dummy file is just for the
    flag's existence + readability probe; nothing here actually parses it.
    """
    sa_dummy = tmp_path / "kg-sa-dummy.json"
    sa_dummy.write_text('{"type":"service_account"}')
    monkeypatch.setenv("KB_KG_GCP_SA_KEY_PATH", str(sa_dummy))
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    monkeypatch.setenv("KB_SEARCH_BYPASS_QUALITY", "off")
    monkeypatch.delenv("KB_CONTENT_QUALITY_FILTER", raising=False)

    # Populate FTS index against the fixture DB BEFORE the app reload so the
    # API queries see real rows. We open our own writable connection here (the
    # data layer connects read-only at request time).
    import kb.services.search_index as si

    importlib.reload(si)
    conn = sqlite3.connect(str(fixture_db))
    try:
        si.ensure_fts_table(conn)
        # KOL: hash = content_hash (10 chars in fixtures); some are 11 chars
        #      but resolve_url_hash(rec) returns them verbatim — match that.
        for row in conn.execute(
            "SELECT content_hash, title, body, lang FROM articles"
        ):
            ch, title, body, lang = row
            if ch is None:
                continue  # skip null-hash KOL rows (not in this fixture)
            conn.execute(
                f"INSERT INTO {si.FTS_TABLE_NAME} (hash,title,body,lang,source) "
                "VALUES (?,?,?,?,?)",
                (ch, title or "", body or "", lang, "wechat"),
            )
        # RSS: hash = substr(content_hash, 1, 10)
        for row in conn.execute(
            "SELECT substr(content_hash,1,10), title, body, lang FROM rss_articles"
        ):
            ch, title, body, lang = row
            conn.execute(
                f"INSERT INTO {si.FTS_TABLE_NAME} (hash,title,body,lang,source) "
                "VALUES (?,?,?,?,?)",
                (ch, title or "", body or "", lang, "rss"),
            )
        conn.commit()
    finally:
        conn.close()

    # Reload app stack so router uses the freshly-configured service module.
    # kb-v2.1-1: kb.services.synthesize MUST be reloaded so KG_MODE_AVAILABLE
    # is recomputed against the just-set KB_KG_GCP_SA_KEY_PATH; the search
    # router imports the flag from there.
    import kb.config
    import kb.services.synthesize
    import kb.api_routers.search
    import kb.api

    importlib.reload(kb.config)
    importlib.reload(kb.services.synthesize)
    importlib.reload(kb.api_routers.search)
    importlib.reload(kb.api)
    from tests.integration.kb.conftest import _stub_app_state
    _stub_app_state(kb.api.app)
    return TestClient(kb.api.app)


# ---- FTS mode tests --------------------------------------------------------


def test_search_fts_basic_shape(app_client: TestClient) -> None:
    r = app_client.get("/api/search?q=agent&mode=fts")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "fts"
    assert "items" in body and "total" in body
    assert isinstance(body["items"], list)
    if body["items"]:
        for key in ("hash", "title", "snippet", "lang", "source"):
            assert key in body["items"][0]


def test_search_lang_filter(app_client: TestClient) -> None:
    r = app_client.get("/api/search?q=agent&mode=fts&lang=zh-CN")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items, "expected at least one zh-CN hit in fixture"
    for item in items:
        assert item["lang"] == "zh-CN"


def test_search_limit(app_client: TestClient) -> None:
    r = app_client.get("/api/search?q=agent&mode=fts&limit=2")
    assert r.status_code == 200
    assert len(r.json()["items"]) <= 2


def test_search_empty_q_is_422(app_client: TestClient) -> None:
    r = app_client.get("/api/search?q=&mode=fts")
    assert r.status_code == 422


def test_search_default_mode_is_kg(app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Default mode is now 'kg' (kb-v2.2-3 F8'). No mode= param → KG path."""

    async def fake_search(q, mode="hybrid"):
        return f"KG:{q}"

    monkeypatch.setattr("omnigraph_search.query.search", fake_search)
    r = app_client.get("/api/search?q=agent")
    assert r.status_code in (200, 202)
    body = r.json()
    assert body["mode"] == "kg"
    assert "job_id" in body


def test_search_kg_unavailable_returns_503(app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """KG_MODE_AVAILABLE=False → 503 + Retry-After header (kb-v2.2-3 F8')."""
    import kb.services.synthesize as svc

    monkeypatch.setattr(svc, "KG_MODE_AVAILABLE", False)
    monkeypatch.setattr(svc, "KG_MODE_UNAVAILABLE_REASON", "test: credentials missing")
    r = app_client.get("/api/search?q=test")  # default mode=kg
    assert r.status_code == 503
    assert r.headers.get("retry-after") == "60"
    detail = r.json()["detail"]
    assert detail["kg_unavailable"] is True
    assert detail["mode"] == "kg"


def test_search_data07_filter_active_by_default(app_client: TestClient) -> None:
    """KB_SEARCH_BYPASS_QUALITY=off (default) — fixture's negative-case rows
    (KOL id=98 layer2='reject', RSS id=96 layer1='reject') must NOT appear.
    """
    r = app_client.get("/api/search?q=body&mode=fts&limit=100")
    assert r.status_code == 200
    items = r.json()["items"]
    titles = [i["title"] for i in items]
    assert all("REJECTED" not in t for t in titles)
    assert all("LAYER2 REJECTED" not in t for t in titles)
    assert all("LAYER1 REJECT" not in t for t in titles)


def test_search_p50_fts_latency_under_100ms(app_client: TestClient) -> None:
    durs: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        r = app_client.get("/api/search?q=agent&mode=fts")
        durs.append(time.perf_counter() - t0)
        assert r.status_code == 200
    durs.sort()
    p50 = durs[2]
    assert p50 < 0.1, f"P50 = {p50 * 1000:.1f}ms (API-04 budget 100ms)"


# ---- KG (async) mode tests -------------------------------------------------


def test_search_kg_returns_job_id(app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """KG mode dispatches a BackgroundTask and returns 202 + job_id."""

    async def fake_search(q, mode="hybrid"):
        return f"KG:{q}"

    monkeypatch.setattr("omnigraph_search.query.search", fake_search)
    r = app_client.get("/api/search?q=hello&mode=kg")
    assert r.status_code in (200, 202)
    body = r.json()
    assert body["mode"] == "kg"
    assert body["status"] == "running"
    assert "job_id" in body
    assert len(body["job_id"]) == 12


def test_search_kg_unknown_job_id_404(app_client: TestClient) -> None:
    r = app_client.get("/api/search/zzzzzzzzzzzz")
    assert r.status_code == 404


def test_search_kg_job_completes(app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Polling returns status='done' + result once the BackgroundTask finishes."""

    async def fake_search(q, mode="hybrid", **_kw):
        return f"KG result for {q!r}"

    # v1.1.P5: search KG worker uses kg_synthesize.synthesize_response;
    # patch that boundary (search router no longer routes through
    # omnigraph_search.query.search for the production KG path).
    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_search)
    r = app_client.get("/api/search?q=test&mode=kg")
    assert r.status_code in (200, 202)
    jid = r.json()["job_id"]
    # Poll up to 2 seconds for completion.
    for _ in range(20):
        time.sleep(0.1)
        status = app_client.get(f"/api/search/{jid}").json()
        if status["status"] == "done":
            assert status["result"] == "KG result for 'test'"
            return
    pytest.fail(f"kg job {jid} did not complete within 2s")


# ---- F1 sanitizer integration tests (AUDIT.md F1 — P0) ---------------------
#
# Pre-F1 these queries hit kb/services/search_index.py:fts_query and bubbled
# `fts5: syntax error near "?"` / `near "AND"` etc. up as a 500 from
# /api/search?mode=fts. Post-F1 the sanitizer wraps every query as a phrase
# literal, so MATCH parses cleanly and the endpoint returns 200 with an empty
# items list when no trigram matches.


def test_search_fts_question_mark_suffix_no_500(app_client: TestClient) -> None:
    """AUDIT.md F1 root-cause repro: ?-suffix query MUST NOT 500."""
    r = app_client.get("/api/search?q=hello?&mode=fts")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "fts"
    assert isinstance(body["items"], list)


def test_search_fts_and_keyword_no_500(app_client: TestClient) -> None:
    """Bare FTS5 boolean keyword MUST be defanged to a literal phrase token."""
    r = app_client.get("/api/search?q=AND&mode=fts")
    assert r.status_code == 200
    assert r.json()["mode"] == "fts"


def test_search_fts_metachar_barrage_no_500(app_client: TestClient) -> None:
    """Mixed FTS5 metachars (paren, colon, wildcard, quote) MUST NOT 500."""
    r = app_client.get('/api/search?q=(title:agent* OR "x")&mode=fts')
    assert r.status_code == 200


# ---- NEVER-500 invariant probe (AUDIT.md F1 — P0) --------------------------


@pytest.mark.parametrize(
    "q",
    [
        "hello?",
        "agent design?",
        "AND",
        "OR",
        "NEAR",
        "foo*",
        "(a OR b)",
        "title:agent",
        'she said "hi"',
        "智能体",
        "智能体 agent?",
        "?*+-^",
        '""',
        "a:b:c",
    ],
    ids=[
        "qmark-suffix", "phrase-qmark", "and-kw", "or-kw", "near-kw",
        "wildcard", "paren-or", "colon-prefix", "embedded-quote",
        "unicode-zh", "mixed-script-qmark", "metachar-only",
        "empty-quote-pair", "multi-colon",
    ],
)
def test_search_fts_never_500_invariant(app_client: TestClient, q: str) -> None:
    """QA-05 NEVER-500 invariant: every q reaches MATCH defanged → status != 500."""
    r = app_client.get("/api/search", params={"q": q, "mode": "fts"})
    assert r.status_code != 500, (
        f"FTS5 syntax leak — q={q!r} returned 500 (pre-F1 bug regression)"
    )
    # Endpoint contract: anything that's not 500 MUST return a JSON body.
    assert r.headers["content-type"].startswith("application/json")


# ---- arx-3 K1: KG search FTS fallback when no /article/ citations ---------


def test_kg_search_fts_fallback_when_markdown_lacks_citations(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """arx-3 RED — POST /api/search/kg with C1 returning non-empty markdown
    without /article/ refs MUST surface FTS5 fallback rows in the poll result.

    Pre-fix: ``_kg_local_worker`` parses zero hashes from the markdown,
    commits ``results=[]``, and the UI sees an empty kg-search response —
    even when the query trivially matches FTS index entries.

    Post-fix: when the citation loop yields no rows AND the markdown is
    substantive, the worker queries ``search_index.fts_query(query)`` and
    appends those rows to ``results`` so the user sees article cards.

    Uses the app_client fixture's pre-populated articles_fts table — query
    'agent' matches several KOL fixture rows ('agent' appears in titles +
    bodies of ids 1, 3, 4, 5). Pre-fix this asserts an empty results list;
    post-fix this asserts >=1 result.
    """

    async def fake_c1(query_text, mode="local", **_kw):
        # Substantive markdown, no /article/{hash} citations.
        return (
            "# What is an agent?\n\n"
            "An agent is an autonomous LLM-driven system. Detailed prose, "
            "no citations because the LLM forgot to follow the citation "
            "directive in the wrapped query."
        )

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_c1)

    r = app_client.post("/api/search/kg", json={"query": "agent"})
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]

    # Poll up to 3 seconds for completion.
    final: dict = {}
    for _ in range(60):
        time.sleep(0.05)
        poll = app_client.get(f"/api/search/kg/{jid}")
        assert poll.status_code == 200, (
            f"poll returned {poll.status_code} (kb-3-09 NEVER-500): {poll.text}"
        )
        body = poll.json()
        if "results" in body:  # done
            final = body
            break
    else:
        pytest.fail(f"kg-search job {jid} did not complete within 3s")

    results = final["results"]
    assert isinstance(results, list)
    assert len(results) >= 1, (
        "K1: non-empty markdown without /article/ citations must trigger "
        f"FTS fallback. Pre-fix results=[]. final={final}"
    )
    # Sanity: fallback rows must include the contract shape kb-3-06 expects.
    for item in results:
        for key in ("hash", "title", "snippet", "lang", "source"):
            assert key in item, f"missing key {key!r} in fallback row {item!r}"
