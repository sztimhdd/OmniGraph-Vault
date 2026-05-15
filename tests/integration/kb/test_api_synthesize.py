"""Integration tests for /api/synthesize + /api/synthesize/{job_id} (API-06 / API-07).

Skill discipline (per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):

    Skill(skill="writing-tests", args="TestClient integration tests. Cover validation paths (422 on missing/empty/invalid lang/too-long question), 404 on missing job, full happy path with monkeypatched C1, full failure path with monkeypatched C1 raising. For polling, do NOT block forever — poll up to ~2s with 100ms sleep, fail test if not terminal. Reuse the patch-C1 + redirect-BASE_DIR helpers.")

    Skill(skill="writing-tests", args="kb-3-09 API-level NEVER-500 tests. Verify POST /api/synthesize → eventually GET /{job_id} returns status='done' with confidence in {'fts5_fallback','no_results'} when C1 fails or times out. EVERY poll during the job lifecycle must return HTTP 200 (NEVER 500). For the timeout test, set KB_SYNTHESIZE_TIMEOUT=1 and patch C1 with asyncio.sleep(2) — must terminate within 4s wall-time.")

Behaviors covered (9 from kb-3-08 + 3 from kb-3-09 = 12):
    1. POST /api/synthesize {question, lang=en} → 202 + {job_id (12-hex), status:'running'}
    2. POST missing question → 422
    3. POST empty question → 422
    4. POST lang='fr' → 422 (Literal["zh","en"])
    5. POST question >2000 chars → 422
    6. GET /api/synthesize/{unknown} → 404
    7. POST + poll happy path → status='done', result={markdown, sources, entities},
       confidence='kg', fallback_used=False
    8. POST + poll failure path (basic) → status terminal, NEVER 500 (post-kb-3-09:
       status='done' with confidence='fts5_fallback' OR 'no_results')
    9. ZH lang directive prepended in C1's query_text arg
    10. C1 exception → terminal status 'done', confidence in {'fts5_fallback','no_results'},
        polling endpoint NEVER 500 (kb-3-09)
    11. C1 timeout (KB_SYNTHESIZE_TIMEOUT=1, C1 sleeps 2s) → terminal 'done',
        error mentions 'timeout', NEVER 500 (kb-3-09)
    12. Every poll during job lifecycle returns 200 (NEVER 500) (kb-3-09)
"""
from __future__ import annotations

import asyncio  # noqa: F401 — used in patched C1 stubs (timeout test)
import importlib
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Build a fresh TestClient with config.BASE_DIR redirected to tmp_path.

    We reload kb.api so the synthesize router (and its wrapper module) re-resolve
    config.BASE_DIR. Same pattern as test_api_search.py — read-once-per-process
    state needs explicit reload after env mutation.

    kb-v2.1-1: KB_KG_GCP_SA_KEY_PATH points at a tmp dummy SA file so the
    KG_MODE_AVAILABLE flag in kb.services.synthesize evaluates True. These
    tests exercise the C1 happy/failure paths (with C1 monkeypatched), which
    the kb-v2.1-1 short-circuit must NOT preempt.
    """
    import config as og_config

    sa_dummy = tmp_path / "kg-sa-dummy.json"
    sa_dummy.write_text('{"type":"service_account"}')
    monkeypatch.setenv("KB_KG_GCP_SA_KEY_PATH", str(sa_dummy))
    monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)
    # Reload chain: kb.config → kb.services.synthesize → kb.api_routers.synthesize → kb.api
    import kb.config
    import kb.services.synthesize
    import kb.api_routers.synthesize
    import kb.api

    importlib.reload(kb.config)
    importlib.reload(kb.services.synthesize)
    importlib.reload(kb.api_routers.synthesize)
    importlib.reload(kb.api)
    return TestClient(kb.api.app)


def _patch_c1_success(
    monkeypatch: pytest.MonkeyPatch,
    output: str = "# Answer\n\nSee [a](/article/abcd012345)",
) -> None:
    """Patch C1 with an instantaneously-successful async stub that writes
    synthesis_output.md so the wrapper can read it back."""

    async def fake(query_text: str, mode: str = "hybrid"):
        import config as og_config

        (Path(og_config.BASE_DIR) / "synthesis_output.md").write_text(
            output, encoding="utf-8"
        )

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake)


def _patch_c1_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch C1 with an immediately-failing async stub."""

    async def fake(*a, **kw):
        raise RuntimeError("LightRAG unavailable")

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake)


def _poll_until_terminal(client: TestClient, jid: str, timeout_s: float = 2.0) -> dict:
    """Poll GET /api/synthesize/{jid} until status != 'running' or timeout.

    Per writing-tests SKILL: condition-based waiting, not bare sleep().
    """
    deadline = time.monotonic() + timeout_s
    last: dict = {}
    while time.monotonic() < deadline:
        time.sleep(0.05)
        last = client.get(f"/api/synthesize/{jid}").json()
        if last.get("status") != "running":
            return last
    return last


# ---- Validation paths (422) -----------------------------------------------


def test_synthesize_post_202_with_job_id(app_client, monkeypatch):
    _patch_c1_success(monkeypatch)
    r = app_client.post("/api/synthesize", json={"question": "What is X?", "lang": "en"})
    assert r.status_code == 202, r.text
    body = r.json()
    assert "job_id" in body and len(body["job_id"]) == 12
    assert body["status"] == "running"


def test_synthesize_post_missing_question_422(app_client):
    r = app_client.post("/api/synthesize", json={"lang": "en"})
    assert r.status_code == 422


def test_synthesize_post_empty_question_422(app_client):
    r = app_client.post("/api/synthesize", json={"question": "", "lang": "en"})
    assert r.status_code == 422


def test_synthesize_post_invalid_lang_422(app_client):
    r = app_client.post("/api/synthesize", json={"question": "q", "lang": "fr"})
    assert r.status_code == 422


def test_synthesize_post_too_long_question_422(app_client):
    r = app_client.post(
        "/api/synthesize", json={"question": "x" * 3000, "lang": "zh"}
    )
    assert r.status_code == 422


# ---- Polling endpoint -----------------------------------------------------


def test_synthesize_get_unknown_job_404(app_client):
    r = app_client.get("/api/synthesize/zzzzzzzzzzzz")
    assert r.status_code == 404


def test_synthesize_full_happy_path(app_client, monkeypatch):
    _patch_c1_success(monkeypatch)
    r = app_client.post("/api/synthesize", json={"question": "What is X?", "lang": "en"})
    jid = r.json()["job_id"]
    final = _poll_until_terminal(app_client, jid)
    assert final.get("status") == "done", f"never reached done; last={final}"
    assert final["confidence"] == "kg"
    assert final["fallback_used"] is False
    assert final["result"] is not None
    assert "markdown" in final["result"]
    assert "sources" in final["result"]
    assert "abcd012345" in final["result"]["sources"]


def test_synthesize_failure_path_basic(app_client, monkeypatch):
    """Post-kb-3-09: NEVER-500 invariant — C1 failure terminates with status='done'
    and fallback_used=True, never 'failed'. Confidence is 'fts5_fallback' (when
    FTS5 has hits) OR 'no_results' (last-resort)."""
    _patch_c1_failure(monkeypatch)
    r = app_client.post("/api/synthesize", json={"question": "q", "lang": "zh"})
    jid = r.json()["job_id"]
    final = _poll_until_terminal(app_client, jid)
    assert final.get("status") == "done", f"NEVER-500: must be done; last={final}"
    assert final["fallback_used"] is True
    assert final["confidence"] in ("fts5_fallback", "no_results")
    # Original cause preserved in error field even on fallback.
    assert "LightRAG unavailable" in (final.get("error") or "")


def test_synthesize_zh_lang_directive_used(app_client, monkeypatch):
    """I18N-07 + QA-02: ZH directive prepended verbatim in the query_text passed to C1."""
    captured = {"text": None}

    async def fake(query_text: str, mode: str = "hybrid"):
        captured["text"] = query_text
        import config as og_config

        (Path(og_config.BASE_DIR) / "synthesis_output.md").write_text(
            "ok", encoding="utf-8"
        )

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake)
    r = app_client.post("/api/synthesize", json={"question": "问题", "lang": "zh"})
    jid = r.json()["job_id"]
    _poll_until_terminal(app_client, jid)
    assert captured["text"] is not None
    assert captured["text"].startswith("请用中文回答。\n\n"), captured["text"]
    assert "问题" in captured["text"]


# ---- kb-3-09 API-level NEVER-500 tests (QA-04 + QA-05) ----------------------


def test_api_synthesize_never_500_on_c1_failure(app_client, monkeypatch):
    """C1 raises → /api/synthesize/{job_id} eventually returns status='done'
    with fallback_used=True and confidence in {'fts5_fallback','no_results'}.
    Every intermediate poll returns HTTP 200 (NEVER 500)."""
    _patch_c1_failure(monkeypatch)
    r = app_client.post("/api/synthesize", json={"question": "anything", "lang": "zh"})
    assert r.status_code == 202
    jid = r.json()["job_id"]
    deadline = time.monotonic() + 4.0
    final: dict = {}
    while time.monotonic() < deadline:
        time.sleep(0.05)
        poll = app_client.get(f"/api/synthesize/{jid}")
        # NEVER-500 invariant: every poll must be 200 regardless of inner state.
        assert poll.status_code != 500, f"poll returned 500: {poll.text}"
        assert poll.status_code == 200
        final = poll.json()
        if final["status"] == "done":
            assert final["fallback_used"] is True
            assert final["confidence"] in ("fts5_fallback", "no_results")
            return
    pytest.fail(f"job did not complete within 4s; last={final}")


def test_api_synthesize_never_500_on_timeout(tmp_path, monkeypatch):
    """C1 sleeps past KB_SYNTHESIZE_TIMEOUT → fallback fires; terminal 'done'
    with error mentioning 'timeout'. NEVER 500."""
    import config as og_config

    # kb-v2.1-1: enable KG mode so the kb_synthesize wrapper does not
    # short-circuit before the C1 timeout path is exercised.
    sa_dummy = tmp_path / "kg-sa-dummy.json"
    sa_dummy.write_text('{"type":"service_account"}')
    monkeypatch.setenv("KB_KG_GCP_SA_KEY_PATH", str(sa_dummy))
    monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)
    monkeypatch.setenv("KB_SYNTHESIZE_TIMEOUT", "1")
    # Reload chain so the new env var takes effect: kb.config first (it reads
    # KB_SYNTHESIZE_TIMEOUT into a constant), then kb.services.synthesize, then
    # the router and app modules so background.add_task binds the freshly-loaded
    # kb_synthesize.
    import importlib

    import kb.api
    import kb.api_routers.synthesize
    import kb.config
    import kb.services.synthesize

    importlib.reload(kb.config)
    importlib.reload(kb.services.synthesize)
    importlib.reload(kb.api_routers.synthesize)
    importlib.reload(kb.api)
    client = TestClient(kb.api.app)

    async def slow(*a, **kw):
        await asyncio.sleep(2)

    monkeypatch.setattr("kg_synthesize.synthesize_response", slow)

    r = client.post("/api/synthesize", json={"question": "q", "lang": "zh"})
    assert r.status_code == 202
    jid = r.json()["job_id"]
    deadline = time.monotonic() + 4.0
    final: dict = {}
    while time.monotonic() < deadline:
        time.sleep(0.05)
        poll = client.get(f"/api/synthesize/{jid}")
        assert poll.status_code != 500, f"poll returned 500: {poll.text}"
        final = poll.json()
        if final["status"] == "done":
            assert final["fallback_used"] is True
            assert final["confidence"] in ("fts5_fallback", "no_results")
            assert "timeout" in (final.get("error") or "").lower()
            return
    pytest.fail(f"timeout job did not terminate within 4s; last={final}")


def test_api_synthesize_get_returns_200_not_500(app_client, monkeypatch):
    """Even on a failing C1, every poll during the job lifetime is HTTP 200.
    Direct invariant test — no inspection of result content beyond status code."""
    _patch_c1_failure(monkeypatch)
    r = app_client.post("/api/synthesize", json={"question": "q", "lang": "zh"})
    jid = r.json()["job_id"]
    # Poll a fixed budget; assert every response is 200 regardless of state.
    for _ in range(15):
        time.sleep(0.05)
        poll = app_client.get(f"/api/synthesize/{jid}")
        assert poll.status_code == 200, (
            f"poll returned {poll.status_code} (expected 200): {poll.text}"
        )
