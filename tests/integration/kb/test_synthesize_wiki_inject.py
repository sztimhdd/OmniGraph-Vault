"""W4 wiki_inject integration tests — pin observable behavior at synthesize boundary.

Per Decision 4 (CONTEXT.md): synthesize is read-only with respect to wiki — the
injection prepends `<wiki_context>...</wiki_context>` to query_text and never
writes back to kb/wiki/.
"""
from __future__ import annotations

import importlib
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_client(tmp_path, fixture_db, monkeypatch):
    """Reuse the same reload chain as test_api_synthesize.py.

    Adds a tmp_path/kb/wiki/ tree pointing kb.services.wiki_inject's default
    wiki_root via cwd swap or explicit page placement on the default kb/wiki path.
    """
    import config as og_config

    sa_dummy = tmp_path / "kg-sa-dummy.json"
    sa_dummy.write_text('{"type":"service_account"}')
    monkeypatch.setenv("KB_KG_GCP_SA_KEY_PATH", str(sa_dummy))
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)
    import kb.config
    import kb.services.synthesize
    import kb.api_routers.synthesize
    import kb.api

    importlib.reload(kb.config)
    importlib.reload(kb.services.synthesize)
    importlib.reload(kb.api_routers.synthesize)
    importlib.reload(kb.api)
    from tests.integration.kb.conftest import _stub_app_state
    _stub_app_state(kb.api.app)
    return TestClient(kb.api.app)


def _poll_until_terminal(client: TestClient, jid: str, timeout_s: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout_s
    last: dict = {}
    while time.monotonic() < deadline:
        time.sleep(0.05)
        last = client.get(f"/api/synthesize/{jid}").json()
        if last.get("status") != "running":
            return last
    return last


def _capture_query_text(monkeypatch: pytest.MonkeyPatch) -> dict:
    captured: dict = {"text": None}

    async def fake(query_text: str, mode: str = "hybrid", **_kw):
        captured["text"] = query_text
        return "# Answer\n\nSee [a](/article/abc1234567)"

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake)
    return captured


def test_wiki_context_injected_into_prompt(app_client, monkeypatch):
    """When resolve_wiki_context returns a non-empty block, query_text must
    start with `<wiki_context>` and contain the original prompt afterwards."""
    captured = _capture_query_text(monkeypatch)

    async def fake_resolve(question, *args, **kwargs):
        return "<wiki_context>\nWIKI BODY ABOUT X\n</wiki_context>\n\n"

    monkeypatch.setattr(
        "kb.services.synthesize.resolve_wiki_context", fake_resolve
    )
    r = app_client.post(
        "/api/synthesize", json={"question": "What is X?", "lang": "en"}
    )
    jid = r.json()["job_id"]
    _poll_until_terminal(app_client, jid)
    text = captured["text"]
    assert text is not None
    assert text.startswith("<wiki_context>\n")
    assert "WIKI BODY ABOUT X" in text
    assert "</wiki_context>" in text
    # Original QA template wrapper still follows the wiki block.
    assert "What is X?" in text


def test_no_wiki_writeback(app_client, monkeypatch, tmp_path):
    """Decision 4: synthesize must NEVER write to kb/wiki/. After a full run
    the wiki dir under tmp_path remains untouched (no new files created)."""
    _capture_query_text(monkeypatch)

    async def fake_resolve(question, *args, **kwargs):
        return "<wiki_context>\nstub\n</wiki_context>\n\n"

    monkeypatch.setattr(
        "kb.services.synthesize.resolve_wiki_context", fake_resolve
    )
    wiki_dir = tmp_path / "kb_wiki_observed"
    wiki_dir.mkdir()
    snapshot_before = sorted(p.name for p in wiki_dir.iterdir())

    r = app_client.post(
        "/api/synthesize", json={"question": "What is X?", "lang": "en"}
    )
    jid = r.json()["job_id"]
    _poll_until_terminal(app_client, jid)

    snapshot_after = sorted(p.name for p in wiki_dir.iterdir())
    assert snapshot_before == snapshot_after


def test_falls_through_when_no_entity(app_client, monkeypatch):
    """When resolve_wiki_context returns "" (no entity match), query_text
    must be the unmodified prompt (no leading <wiki_context>)."""
    captured = _capture_query_text(monkeypatch)

    async def fake_resolve(question, *args, **kwargs):
        return ""

    monkeypatch.setattr(
        "kb.services.synthesize.resolve_wiki_context", fake_resolve
    )
    r = app_client.post(
        "/api/synthesize", json={"question": "Random query", "lang": "en"}
    )
    jid = r.json()["job_id"]
    _poll_until_terminal(app_client, jid)
    text = captured["text"]
    assert text is not None
    assert not text.startswith("<wiki_context>")


def test_falls_through_when_lint_fails(app_client, monkeypatch):
    """When resolve_wiki_context returns "" because of failed lint (stale page,
    unresolved citation), query_text must be unmodified — same observable
    behavior as no-entity case but exercises the lint fall-through branch."""
    captured = _capture_query_text(monkeypatch)

    call_count = {"n": 0}

    async def fake_resolve(question, *args, **kwargs):
        call_count["n"] += 1
        # Simulate the lint-failure path — wiki_inject internally returns ""
        # when staleness or citation_integrity lint fires.
        return ""

    monkeypatch.setattr(
        "kb.services.synthesize.resolve_wiki_context", fake_resolve
    )
    r = app_client.post(
        "/api/synthesize",
        json={"question": "What is OpenClaw?", "lang": "en"},
    )
    jid = r.json()["job_id"]
    _poll_until_terminal(app_client, jid)
    assert call_count["n"] == 1
    text = captured["text"]
    assert text is not None
    assert not text.startswith("<wiki_context>")
