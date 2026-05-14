---
phase: kb-3-fastapi-bilingual-api
plan: 04
subsystem: api-skeleton
tags: [fastapi, uvicorn, asgi, lifecycle, static-files]
type: execute
wave: 2
depends_on: ["kb-3-01"]
files_modified:
  - kb/api.py
  - tests/integration/kb/test_api_skeleton.py
  - requirements.txt
autonomous: true
requirements:
  - API-01
  - API-08
  - CONFIG-02

must_haves:
  truths:
    - "uvicorn kb.api:app --port 8766 boots successfully against a fixture DB"
    - "GET /health returns 200 with {status: 'ok', kb_db_path, kb_images_dir}"
    - "GET /static/img/{hash}/<file> serves the same bytes as the legacy :8765 server (API-08)"
    - "Port overridable via KB_PORT env (API-01)"
    - "App reads kb.config (CONFIG-01 already shipped) — adds zero new env vars (CONFIG-02)"
    - "Importing kb.api does NOT trigger DB connection or filesystem writes (lazy init)"
  artifacts:
    - path: "kb/api.py"
      provides: "FastAPI app instance, /health endpoint, /static/img mount"
      exports: ["app"]
      min_lines: 60
    - path: "tests/integration/kb/test_api_skeleton.py"
      provides: "TestClient-based smoke tests (no live uvicorn needed)"
      min_lines: 80
    - path: "requirements.txt"
      provides: "fastapi>=0.110 + uvicorn[standard]>=0.27 pinned (per PROJECT-KB-v2 § Tech Stack)"
  key_links:
    - from: "kb/api.py"
      to: "kb.config (KB_DB_PATH, KB_IMAGES_DIR, KB_PORT)"
      via: "from kb import config"
      pattern: "from kb import config|kb\\.config"
    - from: "kb/api.py app.mount"
      to: "{KB_IMAGES_DIR}/ as /static/img"
      via: "fastapi.staticfiles.StaticFiles"
      pattern: "StaticFiles.*directory.*KB_IMAGES_DIR|app\\.mount.*\"/static/img\""
---

<objective>
Create the FastAPI app skeleton that subsequent plans (kb-3-05 articles, kb-3-06 search, kb-3-08 synthesize) extend with route handlers. Includes lifecycle, /health endpoint, and the `/static/img` mount that replaces the legacy `python -m http.server 8765` (D-15).

Purpose: Without a working app boot + StaticFiles mount, downstream plans can't add routes. This plan ships the minimum viable FastAPI app so the rest of Wave 2 / Wave 3 can iterate against it. Smoke tests use FastAPI's `TestClient` — no live uvicorn process needed for test execution.

Output: Single `kb/api.py` (~60 lines), TestClient-based integration tests, requirements.txt extension.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md
@kb/config.py
@kb/docs/06-KB3-API-QA.md
@kb/docs/10-DESIGN-DISCIPLINE.md
@requirements.txt
@CLAUDE.md

<interfaces>
Existing kb.config exports (DO NOT modify; only consume):

```python
# kb/config.py (kb-1 — already shipped)
KB_DB_PATH: Path        # default ~/.hermes/data/kol_scan.db
KB_IMAGES_DIR: Path     # default ~/.hermes/omonigraph-vault/images
KB_OUTPUT_DIR: Path     # default kb/output
KB_PORT: int            # default 8766
KB_DEFAULT_LANG: str    # default zh-CN
```

FastAPI minimum-viable app shape (from API-01 + API-08 + CONFIG-02 contract):

```python
# kb/api.py
from __future__ import annotations
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from kb import config

app = FastAPI(
    title="OmniGraph KB v2",
    version="2.0.0",
    description="Bilingual Agent-tech content site backend",
)

# /static/img mount — D-15 replaces standalone :8765 image server
app.mount(
    "/static/img",
    StaticFiles(directory=str(config.KB_IMAGES_DIR), check_dir=False),
    name="static_img",
)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "kb_db_path": str(config.KB_DB_PATH),
        "kb_images_dir": str(config.KB_IMAGES_DIR),
        "version": "2.0.0",
    }
```

Test pattern (FastAPI TestClient — no live uvicorn):

```python
from fastapi.testclient import TestClient
from kb.api import app

client = TestClient(app)
def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
```

requirements.txt addition (per PROJECT-KB-v2 § Tech Stack — likely already present from kb-1; verify and add if missing):

```
fastapi>=0.110
uvicorn[standard]>=0.27
python-multipart>=0.0.6
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Invoke python-patterns Skill + create kb/api.py with /health + /static/img mount + TestClient tests</name>
  <read_first>
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md (kb-3-01 output — endpoint shapes + status codes)
    - kb/config.py (read existing exports — KB_DB_PATH, KB_IMAGES_DIR, KB_PORT)
    - requirements.txt (verify which fastapi/uvicorn versions are pinned; add if missing)
    - .planning/REQUIREMENTS-KB-v2.md API-01 + API-08 + CONFIG-02 (exact REQ wordings)
  </read_first>
  <files>kb/api.py, tests/integration/kb/test_api_skeleton.py, requirements.txt</files>
  <behavior>
    - Test 1: `from kb.api import app` succeeds without raising (no DB connect at import time).
    - Test 2: `TestClient(app).get("/health")` returns 200 with JSON `{"status": "ok", "kb_db_path": str, "kb_images_dir": str, "version": str}`.
    - Test 3: `TestClient(app).get("/static/img/{hash}/dummy.txt")` for an existing fixture image directory returns 200 and the file bytes.
    - Test 4: `TestClient(app).get("/static/img/nonexistent/missing.png")` returns 404.
    - Test 5: KB_PORT env override is read at import time — `KB_PORT=9999 python -c "from kb import config; print(config.KB_PORT)"` outputs `9999`. (This tests CONFIG-01 still works — kb-3 does NOT add new env vars, so verify config.py behavior preserved.)
    - Test 6: App imports zero new LLM provider env vars — `grep -E "DEEPSEEK|VERTEX|OPENAI|GEMINI" kb/api.py` returns 0 (CONFIG-02).
  </behavior>
  <action>
    Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1, this plan invokes python-patterns Skill before writing code:

    Skill(skill="python-patterns", args="Idiomatic minimal FastAPI app skeleton: single app.py with FastAPI() instance, lifecycle handled by uvicorn (no @app.on_event needed for this scope — DB conn is lazy per-request). app.mount('/static/img', StaticFiles(directory=..., check_dir=False)) so import does not fail when KB_IMAGES_DIR doesn't exist (e.g. CI). Single /health endpoint returning {status, kb_db_path, kb_images_dir, version}. Type hints throughout. Module is import-safe — no DB connect, no filesystem writes at import time.")

    **Step 1 — Verify/extend `requirements.txt`** with FastAPI + uvicorn + python-multipart pins. If already present from kb-1, just verify the versions meet `fastapi>=0.110`, `uvicorn[standard]>=0.27`, `python-multipart>=0.0.6`. If absent, append.

    **Step 2 — Create `kb/api.py`** (the FastAPI app skeleton):

    ```python
    """kb/api.py — FastAPI application entry for kb-3 (port 8766).

    Per kb-3-API-CONTRACT.md (kb-3-01 output): single `app` instance, /health endpoint,
    /static/img mount (D-15 replaces standalone :8765 image server). Subsequent plans
    (kb-3-05 articles, kb-3-06 search, kb-3-08 synthesize) extend this app with route
    handlers via `from kb.api import app` import.

    Booted by uvicorn:
        uvicorn kb.api:app --host 127.0.0.1 --port 8766 --workers 1

    KB_PORT env override (CONFIG-01) controls the launch port; the app object itself
    is port-agnostic.

    NO new env vars introduced (CONFIG-02 — REQ verbatim).
    """
    from __future__ import annotations

    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    from kb import config

    # Skill(skill="python-patterns", args="Idiomatic minimal FastAPI app...")

    app = FastAPI(
        title="OmniGraph KB v2",
        version="2.0.0",
        description="Bilingual Agent-tech content site backend (FTS5 + KG Q&A wrap)",
    )

    # API-08: replace standalone http://localhost:8765 image server.
    # check_dir=False so import doesn't fail in CI / fresh checkouts where KB_IMAGES_DIR
    # may not exist yet — runtime requests then 404 cleanly.
    app.mount(
        "/static/img",
        StaticFiles(directory=str(config.KB_IMAGES_DIR), check_dir=False),
        name="static_img",
    )


    @app.get("/health")
    async def health() -> dict:
        """Liveness + config-summary endpoint. Used by smoke tests + monitoring."""
        return {
            "status": "ok",
            "kb_db_path": str(config.KB_DB_PATH),
            "kb_images_dir": str(config.KB_IMAGES_DIR),
            "version": "2.0.0",
        }
    ```

    **Step 3 — Create `tests/integration/kb/test_api_skeleton.py`** with TestClient-based tests:

    ```python
    """API skeleton smoke tests (no live uvicorn needed — uses fastapi.testclient)."""
    from __future__ import annotations

    import re
    from pathlib import Path

    import pytest
    from fastapi.testclient import TestClient


    @pytest.fixture
    def client():
        from kb.api import app
        return TestClient(app)


    def test_app_imports_without_db_connect(monkeypatch):
        """kb.api import must NOT touch the DB or filesystem (lazy init)."""
        # If kb.api eagerly opened SQLite, importing here would fail when KB_DB_PATH
        # points at a non-existent file. Force a bogus path and verify import works.
        monkeypatch.setenv("KB_DB_PATH", "/no/such/path/should-not-error.db")
        # Reload kb.config + kb.api so the new env is read
        import importlib
        import kb.config
        import kb.api
        importlib.reload(kb.config)
        importlib.reload(kb.api)
        # If we get here, import succeeded without DB connection
        assert kb.api.app is not None


    def test_health_endpoint(client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "kb_db_path" in body
        assert "kb_images_dir" in body
        assert "version" in body


    def test_static_img_existing_file(tmp_path, monkeypatch):
        """Create a fake image file under KB_IMAGES_DIR and verify /static/img serves it."""
        monkeypatch.setenv("KB_IMAGES_DIR", str(tmp_path))
        # Reload config + api so the mount points to tmp_path
        import importlib
        import kb.config
        import kb.api
        importlib.reload(kb.config)
        importlib.reload(kb.api)
        # Create a dummy file
        hash_dir = tmp_path / "abc1234567"
        hash_dir.mkdir()
        f = hash_dir / "dummy.txt"
        f.write_text("hello image", encoding="utf-8")
        # Hit the endpoint
        c = TestClient(kb.api.app)
        r = c.get("/static/img/abc1234567/dummy.txt")
        assert r.status_code == 200
        assert r.text == "hello image"


    def test_static_img_missing_returns_404(client):
        r = client.get("/static/img/nonexistent/missing.png")
        assert r.status_code == 404


    def test_no_new_llm_env_vars_in_api(monkeypatch):
        """CONFIG-02: kb/api.py introduces zero new LLM provider env vars."""
        text = Path("kb/api.py").read_text(encoding="utf-8")
        # The legacy LLM env vars (DEEPSEEK_API_KEY etc) MUST NOT appear in kb/api.py.
        # They live in lib/llm_complete.py, which is a downstream import — kb/api itself
        # references kb/services/synthesize (kb-3-08) which then imports lib/llm_complete.
        forbidden = ["DEEPSEEK_API_KEY", "VERTEX_AI_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
                     "OMNIGRAPH_LLM_PROVIDER"]
        for var in forbidden:
            assert var not in text, f"CONFIG-02 violation: kb/api.py references {var}"


    def test_kb_port_env_still_honored(monkeypatch):
        """KB_PORT is read by kb.config (kb-1 already shipped); verify behavior preserved."""
        monkeypatch.setenv("KB_PORT", "9999")
        import importlib
        import kb.config
        importlib.reload(kb.config)
        assert int(kb.config.KB_PORT) == 9999
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/integration/kb/test_api_skeleton.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `kb/api.py` exists with ≥60 lines
    - `grep -q "from fastapi import FastAPI" kb/api.py`
    - `grep -q 'app.mount.*"/static/img"' kb/api.py`
    - `grep -q "@app.get..\"/health\"" kb/api.py`
    - `grep -q "Skill(skill=\"python-patterns\"" kb/api.py` (literal in module docstring or comment for discipline regex)
    - `grep -E "DEEPSEEK|VERTEX|OPENAI_API|GEMINI_API|OMNIGRAPH_LLM_PROVIDER" kb/api.py` returns 0 (CONFIG-02)
    - `pytest tests/integration/kb/test_api_skeleton.py -v` exits 0 with ≥6 tests passing
    - `python -c "from kb.api import app; print(app.title)"` outputs `OmniGraph KB v2`
    - `requirements.txt` contains `fastapi>=0.110` AND `uvicorn[standard]>=0.27` AND `python-multipart>=0.0.6`
  </acceptance_criteria>
  <done>FastAPI app boots; /health returns 200; /static/img serves; ≥6 tests pass; downstream plans can `from kb.api import app`.</done>
</task>

</tasks>

<verification>
- `kb/api.py` is the FastAPI app entry (per kb-3-API-CONTRACT.md spec)
- /static/img mount works for existing files + 404s for missing
- /health endpoint returns config summary
- python-patterns Skill invocation literal in code or summary
- No new LLM env vars (CONFIG-02 satisfied)
</verification>

<success_criteria>
- API-01: app boots, KB_PORT env honored
- API-08: /static/img replaces :8765 standalone server
- CONFIG-02: zero new LLM provider env vars
- Subsequent plans can `from kb.api import app` to register routes
</success_criteria>

<output>
Create `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-04-SUMMARY.md` documenting:
- kb/api.py created with /health + /static/img mount
- ≥6 TestClient tests passing
- requirements.txt extended (fastapi + uvicorn + python-multipart)
- Skill invocation: `Skill(skill="python-patterns", ...)` literal for discipline regex match
- Foundation for kb-3-05/06/08 to extend
</output>
</content>
</invoke>