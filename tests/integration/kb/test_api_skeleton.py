"""API skeleton smoke tests (no live uvicorn — uses fastapi.testclient).

Covers kb-3-04-fastapi-skeleton-PLAN.md acceptance criteria:
- Test 1: kb.api imports without DB connect (lazy init)
- Test 2: /health returns 200 with required JSON keys
- Test 3: /static/img serves an existing fixture file
- Test 4: /static/img returns 404 for missing path
- Test 5: KB_PORT env override is honored by kb.config (CONFIG-01 preserved)
- Test 6: kb/api.py introduces zero new LLM provider env vars (CONFIG-02)
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    """Default TestClient against the module-level FastAPI app."""
    from kb.api import app
    return TestClient(app)


def test_app_imports_without_db_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    """kb.api import must NOT touch the DB or filesystem (lazy init).

    Pointing KB_DB_PATH at a non-existent file should not break import; it only
    matters at request time (and downstream plans handle that via their own
    SQLite open paths).
    """
    monkeypatch.setenv("KB_DB_PATH", "/no/such/path/should-not-error.db")
    import kb.config
    import kb.api
    importlib.reload(kb.config)
    importlib.reload(kb.api)
    assert kb.api.app is not None
    # And TestClient construction does not connect to DB either
    c = TestClient(kb.api.app)
    assert c is not None


def test_health_endpoint(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "kb_db_path" in body
    assert "kb_images_dir" in body
    assert "version" in body


def test_health_endpoint_returns_string_paths(client: TestClient) -> None:
    """JSON-serializable: paths must be strings, not Path objects."""
    r = client.get("/health")
    body = r.json()
    assert isinstance(body["kb_db_path"], str)
    assert isinstance(body["kb_images_dir"], str)
    assert isinstance(body["version"], str)


def test_static_img_existing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Create a fake image file under KB_IMAGES_DIR and verify /static/img serves it."""
    monkeypatch.setenv("KB_IMAGES_DIR", str(tmp_path))
    import kb.config
    import kb.api
    importlib.reload(kb.config)
    importlib.reload(kb.api)
    # Create a dummy file under tmp_path/<hash>/<filename>
    hash_dir = tmp_path / "abc1234567"
    hash_dir.mkdir()
    f = hash_dir / "dummy.txt"
    f.write_text("hello image", encoding="utf-8")
    c = TestClient(kb.api.app)
    r = c.get("/static/img/abc1234567/dummy.txt")
    assert r.status_code == 200
    assert r.text == "hello image"


def test_static_img_missing_returns_404(client: TestClient) -> None:
    r = client.get("/static/img/nonexistent/missing.png")
    assert r.status_code == 404


def test_no_new_llm_env_vars_in_api() -> None:
    """CONFIG-02: kb/api.py introduces zero new LLM provider env vars."""
    text = Path("kb/api.py").read_text(encoding="utf-8")
    forbidden = [
        "DEEPSEEK_API_KEY",
        "VERTEX_AI_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "OMNIGRAPH_LLM_PROVIDER",
    ]
    for var in forbidden:
        assert var not in text, f"CONFIG-02 violation: kb/api.py references {var}"


def test_kb_port_env_still_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    """KB_PORT is read by kb.config (kb-1 already shipped); verify behavior preserved."""
    monkeypatch.setenv("KB_PORT", "9999")
    import kb.config
    importlib.reload(kb.config)
    assert int(kb.config.KB_PORT) == 9999


def test_app_metadata(client: TestClient) -> None:
    """App has the expected title + version surfaced through FastAPI metadata."""
    from kb.api import app
    assert app.title == "OmniGraph KB v2"
    assert app.version == "2.0.0"


def test_static_img_mount_uses_kb_config_path() -> None:
    """The /static/img mount directory MUST trace back to kb.config.KB_IMAGES_DIR.

    Direct hardcoded paths would violate K-1 (env-driven config) and CONFIG-01.
    """
    src = Path("kb/api.py").read_text(encoding="utf-8")
    # Either `config.KB_IMAGES_DIR` or `KB_IMAGES_DIR` from kb.config must appear
    assert "KB_IMAGES_DIR" in src
    assert "from kb import config" in src or "from kb.config import" in src
