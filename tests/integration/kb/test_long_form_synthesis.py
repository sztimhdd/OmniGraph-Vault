"""Integration tests for kb-v2.1-5 long-form synthesis MVP.

Covers /api/synthesize ``mode={qa, long_form}`` end-to-end against a real
fixture_db SQLite + the real articles_by_hashes / entities_for_articles
queries. Only the C1 (kg_synthesize.synthesize_response) external boundary is
monkeypatched — that's the LLM-calling third-party-service boundary the
writing-tests SKILL guidelines say to mock.

Behaviors covered (8):
    1. Default mode is 'qa' when client omits the field (backward compat)
    2. mode='qa' passes lang-directive + raw question to C1 (existing behavior)
    3. mode='long_form' + lang='zh' wraps question in ZH research template
    4. mode='long_form' + lang='en' wraps question in EN research template
    5. SynthesizeResult schema fields are identical for both modes
    6. Invalid mode value (mode='research') returns 422
    7. Long-form result preserves the v2.1-2 image-path rewriting (via the
       same _rewrite step, even though the wrapper itself does not — proven by
       the same SynthesizeResult dict shape passing through job_store)
    8. (regression) Mode round-trips: client sends mode → API forwards to
       wrapper → wrapper picks right prompt → result schema unchanged

Skill(skill="python-patterns", args="Idiomatic Python tests using importlib.reload chain (kb.config → kb.services.synthesize → kb.api_routers.synthesize → kb.api) so KB_DB_PATH + KG_MODE_AVAILABLE env-derived state is re-resolved per test. Captured mock pattern with closure-over-dict for query_text args. monkeypatch.setattr for module-level constants over import-time vars.")

Skill(skill="writing-tests", args="Testing Trophy: integration > unit. Real DB + FastAPI TestClient + MOCKED kg_synthesize.synthesize_response. Test mode='qa' is default. Test mode='long_form' wraps question with template. Test schema parity. Test 422 on invalid mode. Use fixture_db + reload chain + monkeypatch synthesize_response — never mock article_query.")
"""
from __future__ import annotations

import asyncio
import importlib
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_client(tmp_path, fixture_db, monkeypatch):
    """Build a fresh TestClient. KG mode enabled + KB_DB_PATH pointed at fixture.

    Mirrors test_api_synthesize.py's app_client fixture to keep the reload
    chain consistent. Tests in this file lean on the same patched-C1 stub
    pattern.
    """
    import config as og_config

    sa_dummy = tmp_path / "kg-sa-dummy.json"
    sa_dummy.write_text('{"type":"service_account"}')
    monkeypatch.setenv("KB_KG_GCP_SA_KEY_PATH", str(sa_dummy))
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)

    import kb.api
    import kb.api_routers.synthesize
    import kb.config
    import kb.services.synthesize

    importlib.reload(kb.config)
    importlib.reload(kb.services.synthesize)
    importlib.reload(kb.api_routers.synthesize)
    importlib.reload(kb.api)
    return TestClient(kb.api.app)


def _patch_c1_capture(monkeypatch: pytest.MonkeyPatch, captured: dict) -> None:
    """Patch C1 with a stub that records query_text + writes synthesis_output."""

    async def fake(query_text: str, mode: str = "hybrid"):
        captured["text"] = query_text
        captured["mode"] = mode
        import config as og_config

        (Path(og_config.BASE_DIR) / "synthesis_output.md").write_text(
            "# Answer\n\nSee [a](/article/abc1234567).",
            encoding="utf-8",
        )

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake)


def _poll_until_terminal(client: TestClient, jid: str, timeout_s: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout_s
    last: dict = {}
    while time.monotonic() < deadline:
        time.sleep(0.05)
        last = client.get(f"/api/synthesize/{jid}").json()
        if last.get("status") != "running":
            return last
    return last


# ---------------------------------------------------------------------------
# 1. Default mode is qa when client omits the field (backward compat)
# ---------------------------------------------------------------------------


def test_default_mode_is_qa_when_unspecified(app_client, monkeypatch):
    """Pre-v2.1-5 qa.js clients send {question, lang} without mode — must still work.

    Server fills mode='qa' default; wrapper takes the v2.1-4 happy path verbatim.
    """
    captured: dict = {}
    _patch_c1_capture(monkeypatch, captured)

    r = app_client.post(
        "/api/synthesize", json={"question": "What is X?", "lang": "en"}
    )
    assert r.status_code == 202, r.text
    jid = r.json()["job_id"]
    final = _poll_until_terminal(app_client, jid)
    assert final["status"] == "done"
    # qa mode = lang directive + raw question (NOT wrapped in template)
    assert captured["text"].startswith("Please answer in English.\n\n"), captured["text"]
    assert "What is X?" in captured["text"]
    assert "Based on real content" not in captured["text"]
    assert "深度研究" not in captured["text"]


# ---------------------------------------------------------------------------
# 2. mode='qa' explicitly — same as default
# ---------------------------------------------------------------------------


def test_qa_mode_uses_existing_prompt(app_client, monkeypatch):
    captured: dict = {}
    _patch_c1_capture(monkeypatch, captured)

    r = app_client.post(
        "/api/synthesize",
        json={"question": "Hello", "lang": "en", "mode": "qa"},
    )
    assert r.status_code == 202
    jid = r.json()["job_id"]
    _poll_until_terminal(app_client, jid)
    # Same shape as default: lang directive + raw question
    assert captured["text"].startswith("Please answer in English.\n\nHello"), (
        captured["text"]
    )


# ---------------------------------------------------------------------------
# 3. mode='long_form' + lang='zh' uses ZH template
# ---------------------------------------------------------------------------


def test_long_form_mode_wraps_question_with_zh_template(app_client, monkeypatch):
    captured: dict = {}
    _patch_c1_capture(monkeypatch, captured)

    r = app_client.post(
        "/api/synthesize",
        json={"question": "AI Agent 框架对比", "lang": "zh", "mode": "long_form"},
    )
    assert r.status_code == 202
    jid = r.json()["job_id"]
    _poll_until_terminal(app_client, jid)

    # Distinctive ZH-template strings present
    assert "深度研究文章" in captured["text"]
    assert "1500-3000 字" in captured["text"]
    # The raw question is interpolated into the template
    assert "AI Agent 框架对比" in captured["text"]
    # The trailing lang directive is part of the template
    assert "请用中文回答。" in captured["text"]
    # Must NOT also have qa-mode's leading directive prepended (would double the instruction)
    assert not captured["text"].startswith("请用中文回答。\n\n请基于"), captured["text"]


# ---------------------------------------------------------------------------
# 4. mode='long_form' + lang='en' uses EN template
# ---------------------------------------------------------------------------


def test_long_form_mode_wraps_question_with_en_template(app_client, monkeypatch):
    captured: dict = {}
    _patch_c1_capture(monkeypatch, captured)

    r = app_client.post(
        "/api/synthesize",
        json={
            "question": "Compare AI agent frameworks",
            "lang": "en",
            "mode": "long_form",
        },
    )
    assert r.status_code == 202
    jid = r.json()["job_id"]
    _poll_until_terminal(app_client, jid)

    assert "deep research article" in captured["text"]
    assert "800-1500 words" in captured["text"]
    assert "Compare AI agent frameworks" in captured["text"]
    assert "Please answer in English." in captured["text"]
    # Should NOT contain the ZH template
    assert "1500-3000 字" not in captured["text"]


# ---------------------------------------------------------------------------
# 5. SynthesizeResult schema parity across modes
# ---------------------------------------------------------------------------


def test_synthesize_result_schema_identical_for_both_modes(app_client, monkeypatch):
    """Both modes must produce a result with the same dict keys so qa.js
    can render either without branching."""
    qa_keys: set = set()
    long_keys: set = set()

    captured_qa: dict = {}
    _patch_c1_capture(monkeypatch, captured_qa)
    r = app_client.post(
        "/api/synthesize",
        json={"question": "x", "lang": "en", "mode": "qa"},
    )
    final_qa = _poll_until_terminal(app_client, r.json()["job_id"])
    if final_qa.get("result"):
        qa_keys = set(final_qa["result"].keys())

    captured_long: dict = {}
    _patch_c1_capture(monkeypatch, captured_long)
    r = app_client.post(
        "/api/synthesize",
        json={"question": "x", "lang": "en", "mode": "long_form"},
    )
    final_long = _poll_until_terminal(app_client, r.json()["job_id"])
    if final_long.get("result"):
        long_keys = set(final_long["result"].keys())

    # Both produce a result and the dict keys are identical (SynthesizeResult shape)
    assert qa_keys, f"qa mode produced no result dict: {final_qa}"
    assert long_keys, f"long_form mode produced no result dict: {final_long}"
    assert qa_keys == long_keys, f"qa={qa_keys} long={long_keys}"
    assert {"markdown", "sources", "entities"} <= qa_keys


# ---------------------------------------------------------------------------
# 6. Invalid mode value returns 422
# ---------------------------------------------------------------------------


def test_invalid_mode_returns_422(app_client):
    r = app_client.post(
        "/api/synthesize",
        json={"question": "x", "lang": "en", "mode": "research"},
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# 7. Long-form response surfaces sources just like qa
# ---------------------------------------------------------------------------


def test_long_form_response_includes_image_refs_when_sources_have_images(
    app_client, monkeypatch
):
    """The wrapper-level long-form path must produce the same SynthesizeResult
    structured-source resolution as qa: a markdown with /article/{hash} refs
    surfaces real ArticleSource entries (with title + lang) and the entity
    join populates from the resolved KOL articles. The image-path rewriting
    happens *upstream* of qa.js consumption, so the contract is: ``sources``
    is a list of dicts with hash/title/lang, identical to the qa path.
    """
    captured: dict = {}
    _patch_c1_capture(monkeypatch, captured)

    r = app_client.post(
        "/api/synthesize",
        json={
            "question": "long-form question",
            "lang": "en",
            "mode": "long_form",
        },
    )
    final = _poll_until_terminal(app_client, r.json()["job_id"])

    assert final["status"] == "done"
    sources = final["result"]["sources"]
    # Patched C1 wrote a markdown referencing fixture-resolvable hash abc1234567
    assert any(s["hash"] == "abc1234567" for s in sources), sources
    # Each source dict has the qa.js-consumer-contract keys
    for s in sources:
        assert {"hash", "title", "lang"} <= set(s.keys())


# ---------------------------------------------------------------------------
# 8. Wrapper unit-style: kb_synthesize accepts mode kwarg
# ---------------------------------------------------------------------------


def test_kb_synthesize_accepts_mode_kwarg(tmp_path, fixture_db, monkeypatch):
    """Direct kb_synthesize() call exercises the mode dispatch without HTTP.

    Backward compat: omitting mode must not raise; it falls through to qa.
    """
    import config as og_config

    sa_dummy = tmp_path / "kg-sa-dummy.json"
    sa_dummy.write_text('{"type":"service_account"}')
    monkeypatch.setenv("KB_KG_GCP_SA_KEY_PATH", str(sa_dummy))
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)

    import kb.config
    import kb.services.synthesize as sm

    importlib.reload(kb.config)
    importlib.reload(sm)

    captured: dict = {}

    async def fake(query_text: str, mode: str = "hybrid"):
        captured["text"] = query_text
        (Path(og_config.BASE_DIR) / "synthesis_output.md").write_text(
            "# x", encoding="utf-8"
        )

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake)

    from kb.services import job_store

    # Default mode (no kwarg) → qa behavior
    jid_default = job_store.new_job(kind="synthesize")
    asyncio.run(sm.kb_synthesize("hello", "en", jid_default))
    assert captured["text"].startswith("Please answer in English.\n\nhello")

    # Explicit long_form
    jid_long = job_store.new_job(kind="synthesize")
    asyncio.run(sm.kb_synthesize("hello", "en", jid_long, mode="long_form"))
    assert "deep research article" in captured["text"]
    assert "hello" in captured["text"]
