"""Integration tests for translation endpoints — kb-v2.2-2 F1'.

Covers:
  1. POST /api/translate/{hash} without target_lang → 422
  2. POST /api/translate/{hash}?target_lang=en → 202 + job_id
  3. Background task runs and stores translation in DB (LLM mocked)
  4. GET /api/translate/{hash} after translation → {"status": "done"}
  5. GET /api/article/{hash}?lang=en after translation → translated fields
  6. DATA-07: layer1_verdict != 'candidate' article → POST 202 but nothing stored
  7. GET /api/translate/{hash} before any translation → {"status": "not_translated"}

Real SQLite via fixture_db. LLM mocked via monkeypatch — no actual LLM calls.
BackgroundTasks execute synchronously within TestClient's anyio event loop.
"""
from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---- Fixtures ---------------------------------------------------------------


@pytest.fixture
def app_client(fixture_db: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient against kb.api with KB_DB_PATH pointed at fixture_db."""
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    monkeypatch.delenv("KB_CONTENT_QUALITY_FILTER", raising=False)
    import kb.config
    import kb.api

    importlib.reload(kb.config)
    importlib.reload(kb.api)
    return TestClient(kb.api.app)


@pytest.fixture
def llm_mock(monkeypatch: pytest.MonkeyPatch):
    """Patch get_llm_func to return a fast fake async LLM."""
    async def fake_llm(prompt: str, **_) -> str:
        if "title" in prompt.lower():
            return "AI Technology Progress"
        return "The latest developments in large language models and their applications in practice."

    monkeypatch.setattr("lib.llm_complete.get_llm_func", lambda: fake_llm)
    return fake_llm


# ---- Helpers ----------------------------------------------------------------

# Article id=1 from fixture_db: content_hash='abc1234567', lang='zh-CN',
# layer1_verdict='candidate' — eligible for translation.
_ELIGIBLE_HASH = "abc1234567"

# Article id=99: content_hash='neg9999999', layer1_verdict='reject' — not eligible.
_REJECTED_HASH = "neg9999999"


def _read_translation(fixture_db: Path, content_hash: str):
    conn = sqlite3.connect(fixture_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT body_translated, title_translated, translated_lang FROM articles WHERE content_hash=?",
        (content_hash,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ---- Tests ------------------------------------------------------------------


def test_translate_missing_target_lang_returns_422(app_client: TestClient) -> None:
    r = app_client.post(f"/api/translate/{_ELIGIBLE_HASH}")
    assert r.status_code == 422


def test_translate_post_returns_202_and_job_id(
    app_client: TestClient, llm_mock
) -> None:
    r = app_client.post(f"/api/translate/{_ELIGIBLE_HASH}?target_lang=en")
    assert r.status_code == 202
    body = r.json()
    assert "job_id" in body
    assert body["target_lang"] == "en"


def test_translate_background_task_stores_translation(
    app_client: TestClient, fixture_db: Path, llm_mock
) -> None:
    """After POST, background task runs and writes translation to DB."""
    app_client.post(f"/api/translate/{_ELIGIBLE_HASH}?target_lang=en")
    row = _read_translation(fixture_db, _ELIGIBLE_HASH)
    assert row is not None
    assert row["translated_lang"] == "en"
    assert row["body_translated"] and len(row["body_translated"]) > 0
    assert row["title_translated"] and len(row["title_translated"]) > 0


def test_get_translate_status_before_translation(app_client: TestClient) -> None:
    r = app_client.get(f"/api/translate/{_ELIGIBLE_HASH}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "not_translated"
    assert body["translated_lang"] is None


def test_get_translate_status_after_translation(
    app_client: TestClient, fixture_db: Path, llm_mock
) -> None:
    app_client.post(f"/api/translate/{_ELIGIBLE_HASH}?target_lang=en")
    r = app_client.get(f"/api/translate/{_ELIGIBLE_HASH}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert body["translated_lang"] == "en"


def test_article_endpoint_returns_translated_fields_when_lang_matches(
    app_client: TestClient, llm_mock
) -> None:
    """GET /api/article/{hash}?lang=en returns translated title + body_html after translation."""
    app_client.post(f"/api/translate/{_ELIGIBLE_HASH}?target_lang=en")
    r = app_client.get(f"/api/article/{_ELIGIBLE_HASH}?lang=en")
    assert r.status_code == 200
    body = r.json()
    assert body["translated_lang"] == "en"
    assert body["translated_title"] is not None
    assert body["translated_body_html"] is not None
    assert "<p>" in body["translated_body_html"]  # markdown rendered to HTML


def test_article_endpoint_no_translation_fields_without_lang(
    app_client: TestClient, llm_mock
) -> None:
    """GET /api/article/{hash} without ?lang returns null translation fields."""
    r = app_client.get(f"/api/article/{_ELIGIBLE_HASH}")
    assert r.status_code == 200
    body = r.json()
    assert body["translated_lang"] is None
    assert body["translated_title"] is None
    assert body["translated_body_html"] is None


def test_data07_rejected_article_translation_not_stored(
    app_client: TestClient, fixture_db: Path, llm_mock
) -> None:
    """DATA-07: layer1_verdict='reject' article → 202 response but no translation stored."""
    r = app_client.post(f"/api/translate/{_REJECTED_HASH}?target_lang=en")
    # POST always returns 202 (job is queued regardless)
    assert r.status_code == 202
    # But translation must NOT be stored in DB
    row = _read_translation(fixture_db, _REJECTED_HASH)
    assert row is None or row["body_translated"] is None
