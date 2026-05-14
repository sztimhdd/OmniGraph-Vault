"""Integration tests for /api/synthesize + /api/synthesize/{job_id} (API-06 / API-07).

Skill discipline (per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):

    Skill(skill="writing-tests", args="TestClient integration tests. Cover validation paths (422 on missing/empty/invalid lang/too-long question), 404 on missing job, full happy path with monkeypatched C1, full failure path with monkeypatched C1 raising. For polling, do NOT block forever — poll up to ~2s with 100ms sleep, fail test if not terminal. Reuse the patch-C1 + redirect-BASE_DIR helpers.")

Behaviors covered (9):
    1. POST /api/synthesize {question, lang=en} → 202 + {job_id (12-hex), status:'running'}
    2. POST missing question → 422
    3. POST empty question → 422
    4. POST lang='fr' → 422 (Literal["zh","en"])
    5. POST question >2000 chars → 422
    6. GET /api/synthesize/{unknown} → 404
    7. POST + poll happy path → status='done', result={markdown, sources, entities},
       confidence='kg', fallback_used=False
    8. POST + poll failure path (basic) → status='failed' with error
       (kb-3-09 will replace with status='done' + confidence='fts5_fallback')
    9. ZH lang directive prepended in C1's query_text arg
"""
from __future__ import annotations

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
    """
    import config as og_config

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
    """Pre-kb-3-09: status='failed' with error. Post-kb-3-09: status='done' +
    confidence='fts5_fallback'. Either is acceptable as a terminal state — this
    test just asserts the polling endpoint reaches a terminal status without 500."""
    _patch_c1_failure(monkeypatch)
    r = app_client.post("/api/synthesize", json={"question": "q", "lang": "zh"})
    jid = r.json()["job_id"]
    final = _poll_until_terminal(app_client, jid)
    assert final.get("status") in ("failed", "done"), f"not terminal; last={final}"
    if final["status"] == "failed":
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
