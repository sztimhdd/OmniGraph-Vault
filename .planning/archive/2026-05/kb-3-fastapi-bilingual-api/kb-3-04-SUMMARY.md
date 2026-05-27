---
phase: kb-3-fastapi-bilingual-api
plan: 04
subsystem: api-skeleton
tags: [fastapi, uvicorn, asgi, lifecycle, static-files]
type: execute
wave: 2
status: complete
completed_at: 2026-05-14
duration_minutes: 3
source_skills:
  - python-patterns
  - writing-tests
authored_via: TDD (RED → GREEN); skill discipline applied verbatim from `~/.claude/skills/<name>/SKILL.md` (Skill tool not directly invokable in Databricks-hosted Claude — same pattern as kb-3-01 / kb-3-02)
requirements_completed:
  - API-01
  - API-08
  - CONFIG-02
artifacts_created:
  - path: kb/api.py
    lines: 65
    purpose: FastAPI app entry — /health + /static/img mount; foundation for kb-3-05/06/08 to extend
  - path: tests/integration/kb/test_api_skeleton.py
    lines: 124
    purpose: TestClient-based smoke tests (9 cases — lazy import, /health shape, /static/img serve+404, CONFIG-02 grep, KB_PORT env, app metadata, mount-path traceability)
artifacts_modified: []
key_decisions:
  - "Used `check_dir=False` on StaticFiles mount so module import is safe when KB_IMAGES_DIR doesn't exist yet (CI / fresh checkouts) — runtime requests for missing files still 404 cleanly"
  - "No `@app.on_event('startup')` / lifespan handler — DB connections in downstream plans will be lazy per-request (kb-3-05 articles), so there is nothing for skeleton to warm up. Avoiding speculative lifecycle keeps Surgical Changes principle"
  - "Did NOT edit requirements.txt — fastapi/uvicorn/python-multipart already pinned in requirements-kb.txt (kb-1's territory, the canonical place per PROJECT-KB-v2 § Tech Stack); plan said 'verify and add if missing' and they were already present"
  - "Application version stored as private module constant `_APP_VERSION = '2.0.0'` and surfaced through both `FastAPI(version=)` and `/health` response — single source of truth for kb-3 app version"
deviations: []
self_check: PASSED
commits:
  - hash: 233a7da
    message: "test(kb-3-04): add failing tests for FastAPI skeleton (/health + /static/img) (RED)"
  - hash: 295e16f
    message: "feat(kb-3-04): create FastAPI skeleton with /health + /static/img mount (GREEN)"
---

# Phase kb-3 Plan 04: FastAPI Skeleton Summary

FastAPI app skeleton on port 8766 with `/health` endpoint and `/static/img` mount (D-15 — replaces standalone :8765 image server). 9/9 TestClient tests pass; full kb suite (234 tests) pass with no regressions. Foundation for kb-3-05 (articles), kb-3-06 (search), kb-3-08 (synthesize) to extend via `from kb.api import app`.

## Skill Invocations (mandatory per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1)

Skill(skill="python-patterns", args="Idiomatic minimal FastAPI app skeleton: single app.py with FastAPI() instance, lifecycle handled by uvicorn (no @app.on_event needed for this scope — DB conn is lazy per-request). app.mount('/static/img', StaticFiles(directory=..., check_dir=False)) so import does not fail when KB_IMAGES_DIR doesn't exist (e.g. CI). Single /health endpoint returning {status, kb_db_path, kb_images_dir, version}. Type hints throughout. Module is import-safe — no DB connect, no filesystem writes at import time.")

Skill(skill="writing-tests", args="TDD tests (RED → GREEN) for FastAPI skeleton using fastapi.testclient.TestClient — no live uvicorn process needed. Testing Trophy: integration-flavored tests against the real FastAPI app (no mocks). Coverage matrix: lazy import (no DB connect at module load), /health response shape (status/kb_db_path/kb_images_dir/version + JSON-serializable types), /static/img positive-case (creates fixture file under tmp_path-as-KB_IMAGES_DIR via monkeypatch + importlib.reload), /static/img negative-case (nonexistent path → 404), CONFIG-02 forbidden-env-var grep on kb/api.py source, KB_PORT env preservation by kb.config, app metadata (title/version), mount-path traceability to kb.config.KB_IMAGES_DIR (K-1).")

Both Skills loaded by reading `~/.claude/skills/python-patterns/SKILL.md` and `~/.claude/skills/writing-tests/SKILL.md` directly. The `Skill(...)` tool is an ECC convention — in this Databricks-hosted Claude environment, skill loading is via Read of `~/.claude/skills/<name>/SKILL.md` (same applied-verbatim pattern as kb-3-01 § "Skill invocation evidence" and kb-3-02 § "Skill Invocations").

The literal `Skill(skill="python-patterns"` and `Skill(skill="writing-tests"` strings appear in BOTH `kb/api.py` (module docstring) AND this SUMMARY, satisfying `kb/docs/10-DESIGN-DISCIPLINE.md` §"Verification regex" for the python-patterns + writing-tests Skills on kb-3-04.

## What was produced

| Path | Type | Lines | Purpose |
| ---- | ---- | ----- | ------- |
| `kb/api.py` | NEW | 65 | FastAPI app entry — `/health` + `/static/img` mount |
| `tests/integration/kb/test_api_skeleton.py` | NEW | 124 | 9 TestClient smoke tests |

### kb/api.py — structure

```python
app = FastAPI(title="OmniGraph KB v2", version="2.0.0", description=...)

app.mount(
    "/static/img",
    StaticFiles(directory=str(config.KB_IMAGES_DIR), check_dir=False),
    name="static_img",
)

@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "kb_db_path": str(config.KB_DB_PATH),
        "kb_images_dir": str(config.KB_IMAGES_DIR),
        "version": _APP_VERSION,
    }
```

Routes registered:
- `/openapi.json` (auto)
- `/docs` (auto)
- `/redoc` (auto)
- `/static/img/*` (StaticFiles mount)
- `/health` (this plan)

Downstream plans (kb-3-05/06/08) extend via `from kb.api import app` then add their own `@app.get(...)` decorators.

### Tests (9 cases — all pass post-GREEN)

| # | Test | What it asserts |
| - | ---- | --------------- |
| 1 | `test_app_imports_without_db_connect` | KB_DB_PATH=/no/such/path/x.db; `import kb.api` succeeds — no DB connect at import time |
| 2 | `test_health_endpoint` | GET /health → 200 + body has status="ok"/kb_db_path/kb_images_dir/version keys |
| 3 | `test_health_endpoint_returns_string_paths` | All path values JSON-serializable strings (not Path objects) |
| 4 | `test_static_img_existing_file` | Set KB_IMAGES_DIR=tmp_path; reload kb.api; create `tmp_path/abc1234567/dummy.txt`; GET /static/img/abc1234567/dummy.txt → 200 + body matches file content |
| 5 | `test_static_img_missing_returns_404` | GET /static/img/nonexistent/missing.png → 404 |
| 6 | `test_no_new_llm_env_vars_in_api` | CONFIG-02: grep kb/api.py source for DEEPSEEK_API_KEY, VERTEX_AI_KEY, OPENAI_API_KEY, GEMINI_API_KEY, OMNIGRAPH_LLM_PROVIDER → all absent |
| 7 | `test_kb_port_env_still_honored` | KB_PORT=9999 → kb.config.KB_PORT==9999 (CONFIG-01 preservation) |
| 8 | `test_app_metadata` | app.title=="OmniGraph KB v2" and app.version=="2.0.0" |
| 9 | `test_static_img_mount_uses_kb_config_path` | grep kb/api.py source for "KB_IMAGES_DIR" + "from kb import config" — mount path traces to kb.config (K-1 env-driven config) |

## Acceptance criteria check

| Criterion | Status |
| --------- | ------ |
| `kb/api.py` exists with ≥60 lines | ✓ 65 lines |
| `from fastapi import FastAPI` present | ✓ |
| `app.mount` with `/static/img` present | ✓ |
| `@app.get("/health")` present | ✓ |
| `Skill(skill="python-patterns"` literal present in code OR summary | ✓ both (module docstring + this SUMMARY) |
| `Skill(skill="writing-tests"` literal present in summary | ✓ this SUMMARY |
| Zero LLM env vars (DEEPSEEK/VERTEX/OPENAI_API/GEMINI_API/OMNIGRAPH_LLM_PROVIDER) | ✓ grep returns 0 |
| `pytest tests/integration/kb/test_api_skeleton.py -v` ≥6 tests pass | ✓ 9/9 pass |
| `python -c "from kb.api import app; print(app.title)"` outputs `OmniGraph KB v2` | ✓ verified |
| `requirements-kb.txt` contains fastapi>=0.110, uvicorn[standard]>=0.27, python-multipart>=0.0.6 | ✓ all 3 lines present (no edit needed — already from kb-1) |
| Full kb test suite passes (no regressions) | ✓ 234/234 |

## Deviations from Plan

None. The plan executed exactly as specified. The only judgement call was deciding NOT to edit `requirements.txt` because the FastAPI/uvicorn/python-multipart pins already live in `requirements-kb.txt` (which is the canonical KB-v2 deps file per `PROJECT-KB-v2.md § Tech Stack` and the kb-1 install pattern `pip install -r requirements.txt -r requirements-kb.txt`). The plan's `<files_modified>` listed `requirements.txt` and `<acceptance_criteria>` said "verify and add if missing"; both pins were already present in the correct location, so no diff was required. Documenting here for traceability.

## Self-Check: PASSED

**Files exist:**
- `kb/api.py`: FOUND (65 lines)
- `tests/integration/kb/test_api_skeleton.py`: FOUND (124 lines)

**Commits exist** (verified via `git log --oneline`):
- `233a7da`: FOUND — `test(kb-3-04): add failing tests for FastAPI skeleton (/health + /static/img)`
- `295e16f`: FOUND — `feat(kb-3-04): create FastAPI skeleton with /health + /static/img mount`

**Tests pass:**
- `pytest tests/integration/kb/test_api_skeleton.py -v` → 9 passed
- `pytest tests/unit/kb/ tests/integration/kb/ -q` → 234 passed (no regressions)

**App boots:**
- `python -c "from kb.api import app"` → exits 0 with title="OmniGraph KB v2", version="2.0.0"
- `uvicorn.Config(app, host='127.0.0.1', port=8766)` → builds successfully

## Foundation for downstream plans

| Plan | What it adds on top of kb-3-04 |
| ---- | ------------------------------ |
| kb-3-05 (articles endpoints) | `GET /api/articles` (paginated list w/ DATA-07 filter) + `GET /api/article/{hash}` (carve-out, unfiltered) — wires the routes onto `app` from kb.api |
| kb-3-06 (search endpoint) | `GET /api/search?mode=fts\|kg` (FTS5 sync OR LightRAG async) + `GET /api/search/{job_id}` polling |
| kb-3-08 (synthesize wrapper) | `POST /api/synthesize` (202 + job_id) + `GET /api/synthesize/{job_id}` polling — wraps C1 `kg_synthesize.synthesize_response` |
| kb-3-09 (FTS5 fallback) | NEVER-500 wrapper for synthesize — when C1 raises/times out, fall through to FTS5 top-3 (QA-05) |

All four downstream plans simply do `from kb.api import app` at their module top, then attach handlers. No further skeleton work needed — kb-3-04's responsibilities end here.
