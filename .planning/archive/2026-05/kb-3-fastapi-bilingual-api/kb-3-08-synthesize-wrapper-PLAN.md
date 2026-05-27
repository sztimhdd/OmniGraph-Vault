---
phase: kb-3-fastapi-bilingual-api
plan: 08
subsystem: synthesize-wrapper
tags: [fastapi, async, background-tasks, kg-synthesize, c1-contract]
type: execute
wave: 3
depends_on: ["kb-3-01", "kb-3-04", "kb-3-06"]
files_modified:
  - kb/services/synthesize.py
  - kb/api_routers/synthesize.py
  - kb/api.py
  - tests/integration/kb/test_api_synthesize.py
  - tests/integration/kb/test_synthesize_wrapper.py
autonomous: true
requirements:
  - I18N-07
  - QA-01
  - QA-02
  - QA-03
  - API-06
  - API-07

must_haves:
  truths:
    - "kb/services/synthesize.py wraps kg_synthesize.synthesize_response (~50 LOC) — C1 signature unchanged (QA-01)"
    - "Language directive prepended verbatim per I18N-07 + QA-02: lang='zh' → '请用中文回答。\\n\\n', lang='en' → 'Please answer in English.\\n\\n'"
    - "POST /api/synthesize {question, lang} → 202 + job_id (API-06)"
    - "BackgroundTasks runs the synthesize call asynchronously (QA-03 — single uvicorn worker)"
    - "GET /api/synthesize/{job_id} returns {status, result?, fallback_used, confidence} (API-07)"
    - "Job-store reused from kb-3-06 (kb/services/job_store.py)"
    - "CONFIG-02 transitively satisfied: KB layer adds zero new LLM env vars; uses lib.llm_complete.get_llm_func() inside kg_synthesize"
  artifacts:
    - path: "kb/services/synthesize.py"
      provides: "wrapper module: kb_synthesize(question, lang, job_id) — calls kg_synthesize.synthesize_response after lang prepend"
      exports: ["kb_synthesize", "lang_directive_for"]
      min_lines: 60
    - path: "kb/api_routers/synthesize.py"
      provides: "APIRouter /api/synthesize POST + /api/synthesize/{job_id} GET"
      exports: ["router"]
      min_lines: 80
    - path: "kb/api.py"
      provides: "extended to include synthesize_router"
    - path: "tests/integration/kb/test_synthesize_wrapper.py"
      provides: "unit-level tests for lang_directive_for + kb_synthesize wrapper logic"
      min_lines: 80
    - path: "tests/integration/kb/test_api_synthesize.py"
      provides: "integration tests for POST /api/synthesize + GET /api/synthesize/{job_id}"
      min_lines: 100
  key_links:
    - from: "kb/services/synthesize.py"
      to: "kg_synthesize.synthesize_response (C1 contract)"
      via: "import + await — signature `synthesize_response(query_text, mode='hybrid')` UNCHANGED"
      pattern: "from kg_synthesize import|kg_synthesize\\.synthesize_response"
    - from: "kb/api_routers/synthesize.py"
      to: "kb.services.job_store (reused from kb-3-06)"
      via: "new_job + update_job + get_job"
      pattern: "from kb.services.job_store|from kb.services import job_store"
---

<objective>
Implement the Q&A backend wrapper: POST /api/synthesize accepts {question, lang} → returns 202 + job_id; BackgroundTasks calls kg_synthesize.synthesize_response (C1 signature unchanged) with the language directive prepended; GET /api/synthesize/{job_id} polls. The fallback path (FTS5 top-3 on synthesize failure) is plan kb-3-09.

Purpose: This is THE D-04 promise: "Q&A 复用 kg_synthesize.synthesize_response (~50 LOC HTTP 包装)". The wrapper is small and focused — the only logic added on top of C1 is the language directive prefix and the BackgroundTasks orchestration. Plan kb-3-09 adds the never-500 fallback; this plan establishes the happy path.

Output: 2 new modules (services/synthesize.py + api_routers/synthesize.py), tests, kb/api.py extended.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-06-SUMMARY.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-04-SUMMARY.md
@kb/api.py
@kb/services/job_store.py
@kg_synthesize.py
@kb/docs/06-KB3-API-QA.md
@kb/docs/02-DECISIONS.md
@kb/docs/10-DESIGN-DISCIPLINE.md
@CLAUDE.md

<interfaces>
C1 contract (read-only, DO NOT MODIFY):

```python
# kg_synthesize.py:105
async def synthesize_response(query_text: str, mode: str = "hybrid"):
    """Async LightRAG hybrid synthesis. Writes to disk + returns awaitable."""
```

Language directive strings (verbatim from I18N-07 + QA-02 — exact copy):

```python
DIRECTIVE_ZH = "请用中文回答。\n\n"
DIRECTIVE_EN = "Please answer in English.\n\n"
```

Wrapper signature (NEW — kb layer):

```python
# kb/services/synthesize.py
def lang_directive_for(lang: str) -> str:
    """Return prepended directive for given lang ('zh' or 'en'). Other → ''."""

async def kb_synthesize(question: str, lang: str, job_id: str) -> None:
    """Background-task entry: prepend directive, call C1, parse result, update job_store.
    Catches ALL exceptions and updates job to status='failed' with error.
    Plan kb-3-09 will replace the 'failed' branch with FTS5-fallback path."""
```

API surface (from kb-3-API-CONTRACT.md):

```python
# POST /api/synthesize  →  202
# Request: {"question": str, "lang": "zh" | "en"}
# Response: {"job_id": "abc123def456", "status": "running"}

# GET /api/synthesize/{job_id}  →  200
# Response: {"status": "running" | "done" | "failed",
#            "result": {markdown, sources, entities} | None,
#            "fallback_used": bool, "confidence": "kg" | "fts5_fallback"}
```

Pydantic request model:

```python
from pydantic import BaseModel, Field
from typing import Literal

class SynthesizeRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    lang: Literal["zh", "en"] = "zh"
```

Job-store reuse (from kb-3-06):

```python
# kb/services/job_store.py
def new_job(kind: str = "search") -> str: ...   # 12-char hex
def update_job(jid, **kw) -> None: ...
def get_job(jid) -> Optional[dict]: ...
```

The job dict has fields: `job_id, kind, status, result, error, fallback_used, confidence, started_at`.

Result parsing — kg_synthesize writes synthesis to `~/.hermes/omonigraph-vault/synthesis_archive/{ts}_{slug}.md`. The wrapper needs to either:
(a) capture the result via a custom callback (intrusive — C1 changes)
(b) read the latest file in synthesis_archive after the call returns

**Decision: option (b)**. Read `synthesis_output.md` (canonical file written by kg_synthesize alongside the archive) after the call returns. This preserves C1.

```python
from kg_synthesize import synthesize_response
import config as og_config  # OmniGraph config — has BASE_DIR

# After awaiting synthesize_response, read:
result_path = og_config.BASE_DIR / "synthesis_output.md"
markdown = result_path.read_text(encoding="utf-8") if result_path.exists() else ""
```

Sources + entities extraction from markdown — the synthesize output Markdown contains a "## Sources" or "## 参考来源" section with hash links. Parse via regex:

```python
import re
_SOURCE_PATTERN = re.compile(r'/article/([a-f0-9]{10})')
sources = list({m for m in _SOURCE_PATTERN.findall(markdown)})
```

For v2.0 minimum-viable: result.sources = list of distinct article hashes found in the markdown; result.entities = []. Plan kb-3-09 may extend.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Invoke python-patterns + writing-tests Skills + create kb/services/synthesize.py wrapper + unit tests</name>
  <read_first>
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md POST /api/synthesize section (response shape)
    - kg_synthesize.py:105 (C1 — copy signature into wrapper docstring as "DO NOT MODIFY")
    - kb/services/job_store.py (kb-3-06 — reuse new_job + update_job + get_job)
    - .planning/REQUIREMENTS-KB-v2.md I18N-07 + QA-01 + QA-02 + QA-03 (exact REQ wordings)
    - kb/docs/06-KB3-API-QA.md (kb-3 exec spec)
    - config.py (OmniGraph BASE_DIR for synthesis_output.md path)
  </read_first>
  <files>kb/services/synthesize.py, tests/integration/kb/test_synthesize_wrapper.py</files>
  <behavior>
    - Test 1: `lang_directive_for("zh")` returns exactly `"请用中文回答。\n\n"`.
    - Test 2: `lang_directive_for("en")` returns exactly `"Please answer in English.\n\n"`.
    - Test 3: `lang_directive_for("fr")` (unsupported) returns `""` (empty — defensive).
    - Test 4: kb_synthesize concatenates directive + question before calling C1: when patched `kg_synthesize.synthesize_response` is invoked, `query_text` argument starts with the directive prefix.
    - Test 5: kb_synthesize reads synthesis_output.md after C1 returns and updates job result with markdown content.
    - Test 6: kb_synthesize extracts source hashes from markdown via regex; updates job with `result["sources"] = [hash1, hash2, ...]`.
    - Test 7: kb_synthesize on C1 exception: job status set to "failed" with error string (kb-3-09 will replace with fallback).
    - Test 8: kb_synthesize on success: job status set to "done", confidence="kg", fallback_used=False.
  </behavior>
  <action>
    Skill(skill="python-patterns", args="Idiomatic async wrapper module: lang_directive_for is a pure dispatcher (return string from dict-of-string OR if/elif). kb_synthesize is async — awaits C1 directly, then reads synthesis_output.md, parses sources via regex, updates job_store. ALL exceptions caught at top level and translated to job_store.update_job(jid, status='failed', error=str(e)) — this stub is replaced by kb-3-09 with FTS5 fallback. Type hints throughout. NO new env vars. Module is import-safe (no DB or LLM at import time).")

    Skill(skill="writing-tests", args="Unit tests for the wrapper module. test_lang_directive_for: 3 cases (zh/en/unsupported). test_kb_synthesize_*: monkeypatch kg_synthesize.synthesize_response with an async stub that captures query_text args; monkeypatch the synthesis_output.md file by writing to a temp BASE_DIR; verify job_store before/after state via get_job(jid). Use asyncio.run to drive the async wrapper from sync tests, OR pytest-asyncio if already configured.")

    **Step 1 — Create `kb/services/synthesize.py`**:

    ```python
    """QA-01 + QA-02 + I18N-07: Q&A wrapper around kg_synthesize.synthesize_response (C1).

    Per D-04 (kb/docs/02-DECISIONS.md): KB layer wraps the existing synthesize function
    in ~50 LOC; signature C1 unchanged. Language directive prepended to query_text per
    I18N-07 — no other prompt manipulation per QA-02.

    Failure path: this plan ships the basic 'failed' branch. Plan kb-3-09 replaces it
    with FTS5-fallback so /api/synthesize NEVER returns 500.

    Skill(skill="python-patterns", args="...")
    Skill(skill="writing-tests", args="...")
    """
    from __future__ import annotations

    import re
    import traceback
    from pathlib import Path
    from typing import Optional

    # OmniGraph BASE_DIR — synthesis_output.md is written here by kg_synthesize
    # (see kg_synthesize.py — output path is config.BASE_DIR / "synthesis_output.md").
    import config as og_config

    from kb.services import job_store

    # Directive strings — VERBATIM per I18N-07 / QA-02 REQ wording.
    DIRECTIVE_ZH = "请用中文回答。\n\n"
    DIRECTIVE_EN = "Please answer in English.\n\n"
    _DIRECTIVES = {"zh": DIRECTIVE_ZH, "en": DIRECTIVE_EN}

    _SOURCE_HASH_PATTERN = re.compile(r"/article/([a-f0-9]{10})")


    def lang_directive_for(lang: str) -> str:
        """Return the language directive string for the given lang code.

        Per I18N-07 + QA-02:
            'zh' -> '请用中文回答。\\n\\n'
            'en' -> 'Please answer in English.\\n\\n'
            other -> ''  (defensive — empty so query passes through unchanged)
        """
        return _DIRECTIVES.get(lang, "")


    def _read_synthesis_output() -> str:
        """Read kg_synthesize's canonical output file (config.BASE_DIR/synthesis_output.md).

        Returns empty string if the file doesn't exist (treat as 'C1 produced no output').
        """
        p = Path(og_config.BASE_DIR) / "synthesis_output.md"
        if not p.exists():
            return ""
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            return ""


    def _extract_source_hashes(markdown: str) -> list[str]:
        """Extract distinct /article/{hash} references from synthesis markdown."""
        return sorted({m for m in _SOURCE_HASH_PATTERN.findall(markdown)})


    async def kb_synthesize(question: str, lang: str, job_id: str) -> None:
        """Background-task entry. Prepends lang directive, calls C1, updates job_store.

        Args:
            question: the user's question (unprefixed)
            lang: 'zh' | 'en' (other accepted but no directive applied)
            job_id: pre-allocated job id (caller invoked job_store.new_job(kind='synthesize'))

        On success: job status='done', result={markdown, sources, entities},
                    confidence='kg', fallback_used=False.
        On failure: job status='failed', error=traceback.

        Plan kb-3-09 will replace the failure branch with FTS5-fallback path.
        """
        try:
            # C1 import deferred to avoid cycle / heavy LightRAG init at module import
            from kg_synthesize import synthesize_response

            directive = lang_directive_for(lang)
            query_text = f"{directive}{question}"
            await synthesize_response(query_text, mode="hybrid")

            markdown = _read_synthesis_output()
            sources = _extract_source_hashes(markdown)
            job_store.update_job(
                job_id,
                status="done",
                result={
                    "markdown": markdown,
                    "sources": sources,
                    "entities": [],  # v2.0 minimum-viable; v2.1 may extend via canonicalization
                },
                fallback_used=False,
                confidence="kg",
            )
        except Exception as e:
            # kb-3-09 will replace this branch with FTS5-fallback
            job_store.update_job(
                job_id,
                status="failed",
                error=f"{type(e).__name__}: {e}",
            )
    ```

    **Step 2 — Create `tests/integration/kb/test_synthesize_wrapper.py`** with the 8 behaviors:

    ```python
    """Tests for kb/services/synthesize.py (the QA-01 wrapper around C1)."""
    from __future__ import annotations

    import asyncio
    from pathlib import Path
    from typing import Any

    import pytest

    from kb.services import job_store, synthesize as kb_synth_mod


    def test_lang_directive_zh():
        assert kb_synth_mod.lang_directive_for("zh") == "请用中文回答。\n\n"


    def test_lang_directive_en():
        assert kb_synth_mod.lang_directive_for("en") == "Please answer in English.\n\n"


    def test_lang_directive_unsupported():
        assert kb_synth_mod.lang_directive_for("fr") == ""
        assert kb_synth_mod.lang_directive_for("") == ""


    @pytest.fixture
    def captured_query() -> dict:
        return {"text": None, "mode": None}


    def _patch_c1(monkeypatch, captured: dict, output: str = "# Answer\n\n[link](/article/abcd012345)"):
        async def fake_synthesize(query_text: str, mode: str = "hybrid"):
            captured["text"] = query_text
            captured["mode"] = mode
            # Simulate kg_synthesize writing synthesis_output.md
            import config as og_config
            (Path(og_config.BASE_DIR) / "synthesis_output.md").write_text(output, encoding="utf-8")
        monkeypatch.setattr("kg_synthesize.synthesize_response", fake_synthesize)


    def _patch_base_dir(tmp_path: Path, monkeypatch):
        """Redirect config.BASE_DIR to a temp directory for output capture."""
        monkeypatch.setenv("BASE_DIR_OVERRIDE", str(tmp_path))
        import config as og_config
        monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)


    def test_kb_synthesize_prepends_lang_directive(tmp_path, monkeypatch, captured_query):
        _patch_base_dir(tmp_path, monkeypatch)
        _patch_c1(monkeypatch, captured_query)
        jid = job_store.new_job(kind="synthesize")
        asyncio.run(kb_synth_mod.kb_synthesize("What is LangChain?", "en", jid))
        assert captured_query["text"].startswith("Please answer in English.\n\n"), captured_query["text"]
        assert "What is LangChain?" in captured_query["text"]


    def test_kb_synthesize_zh_directive(tmp_path, monkeypatch, captured_query):
        _patch_base_dir(tmp_path, monkeypatch)
        _patch_c1(monkeypatch, captured_query)
        jid = job_store.new_job(kind="synthesize")
        asyncio.run(kb_synth_mod.kb_synthesize("LangGraph 是什么?", "zh", jid))
        assert captured_query["text"].startswith("请用中文回答。\n\n")


    def test_kb_synthesize_reads_output_file(tmp_path, monkeypatch, captured_query):
        _patch_base_dir(tmp_path, monkeypatch)
        _patch_c1(monkeypatch, captured_query, output="# Hello\n\n[a](/article/1234567890)")
        jid = job_store.new_job(kind="synthesize")
        asyncio.run(kb_synth_mod.kb_synthesize("q", "zh", jid))
        job = job_store.get_job(jid)
        assert job["status"] == "done"
        assert "Hello" in job["result"]["markdown"]
        assert "1234567890" in job["result"]["sources"]


    def test_kb_synthesize_failure_branch(tmp_path, monkeypatch):
        _patch_base_dir(tmp_path, monkeypatch)
        async def fake_fail(*a, **kw):
            raise RuntimeError("LightRAG storage missing")
        monkeypatch.setattr("kg_synthesize.synthesize_response", fake_fail)
        jid = job_store.new_job(kind="synthesize")
        asyncio.run(kb_synth_mod.kb_synthesize("q", "zh", jid))
        job = job_store.get_job(jid)
        assert job["status"] == "failed"
        assert "LightRAG storage missing" in job["error"]


    def test_kb_synthesize_success_sets_kg_confidence(tmp_path, monkeypatch, captured_query):
        _patch_base_dir(tmp_path, monkeypatch)
        _patch_c1(monkeypatch, captured_query)
        jid = job_store.new_job(kind="synthesize")
        asyncio.run(kb_synth_mod.kb_synthesize("q", "zh", jid))
        job = job_store.get_job(jid)
        assert job["confidence"] == "kg"
        assert job["fallback_used"] is False
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/integration/kb/test_synthesize_wrapper.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `kb/services/synthesize.py` exists with ≥60 lines
    - `grep -q "DIRECTIVE_ZH" kb/services/synthesize.py`
    - `grep -q "DIRECTIVE_EN" kb/services/synthesize.py`
    - `grep -q "请用中文回答" kb/services/synthesize.py`
    - `grep -q "Please answer in English" kb/services/synthesize.py`
    - `grep -q "from kg_synthesize import" kb/services/synthesize.py`
    - `grep -q "Skill(skill=\"python-patterns\"" kb/services/synthesize.py`
    - `grep -q "Skill(skill=\"writing-tests\"" kb/services/synthesize.py` OR in test file
    - `pytest tests/integration/kb/test_synthesize_wrapper.py -v` exits 0 with ≥8 tests passing
    - C1 contract preserved: `grep -q "synthesize_response(query_text" kb/services/synthesize.py` (no kwargs renamed)
  </acceptance_criteria>
  <done>kb_synthesize wrapper + lang_directive_for + 8 unit tests pass; C1 signature unchanged.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Create kb/api_routers/synthesize.py with POST /api/synthesize + GET /api/synthesize/{job_id} + integration tests</name>
  <read_first>
    - kb/services/synthesize.py (Task 1 — kb_synthesize, lang_directive_for)
    - kb/services/job_store.py (kb-3-06 — new_job + get_job)
    - kb/api.py (kb-3-04 — extend include_router)
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md POST /api/synthesize + GET /api/synthesize/{job_id}
    - .planning/REQUIREMENTS-KB-v2.md API-06 + API-07
  </read_first>
  <files>kb/api_routers/synthesize.py, kb/api.py, tests/integration/kb/test_api_synthesize.py</files>
  <behavior>
    - Test 1: POST /api/synthesize with `{"question": "What is X?", "lang": "en"}` returns 202 with body containing `job_id` (12-char hex) and `status: "running"`.
    - Test 2: POST with missing `question` → 422.
    - Test 3: POST with empty `question` (`""`) → 422 (min_length=1).
    - Test 4: POST with `lang: "fr"` → 422 (Literal["zh", "en"] enforced).
    - Test 5: POST with `question` > 2000 chars → 422.
    - Test 6: GET /api/synthesize/nonexistent_jobid → 404.
    - Test 7: After POST returns job_id, GET /api/synthesize/{job_id} initially returns `{status: "running"}`.
    - Test 8: With patched C1 (instantaneous success), POST + poll → eventually `{status: "done", result: {markdown, sources, entities}, confidence: "kg", fallback_used: false}`.
    - Test 9: With patched C1 raising → POST + poll → eventually `{status: "failed", error: "..."}`. (Plan kb-3-09 will turn this into fts5_fallback success.)
  </behavior>
  <action>
    Skill(skill="python-patterns", args="POST endpoint accepts Pydantic request model, allocates job_id via job_store.new_job(kind='synthesize'), schedules kb_synthesize via FastAPI BackgroundTasks (NOT asyncio.create_task — BackgroundTasks ensure response is sent before task runs), returns 202 + job_id. GET endpoint is dict lookup on job_store. Use status_code=202 directly on the route decorator: `@router.post('/synthesize', status_code=202)`. Type hints + Pydantic for request validation; FastAPI auto-generates OpenAPI from these.")

    Skill(skill="writing-tests", args="TestClient integration tests. Cover validation paths (422 on missing/empty/invalid lang/too-long question), 404 on missing job, full happy path with monkeypatched C1, full failure path with monkeypatched C1 raising. For polling, do NOT block forever — poll up to 1s with 100ms sleep, fail test if not terminal. Reuse the _patch_c1 + _patch_base_dir helpers from test_synthesize_wrapper.py.")

    **Step 1 — Create `kb/api_routers/synthesize.py`**:

    ```python
    """API-06 + API-07: POST /api/synthesize + GET /api/synthesize/{job_id}.

    Async wrapper around kg_synthesize.synthesize_response (C1 unchanged) — see
    kb/services/synthesize.py for the wrapper module.

    Skill(skill="python-patterns", args="...")
    Skill(skill="writing-tests", args="...")
    """
    from __future__ import annotations

    from typing import Any, Literal

    from fastapi import APIRouter, BackgroundTasks, HTTPException, status
    from pydantic import BaseModel, Field

    from kb.services import job_store
    from kb.services.synthesize import kb_synthesize

    router = APIRouter(prefix="/api", tags=["synthesize"])


    class SynthesizeRequest(BaseModel):
        question: str = Field(..., min_length=1, max_length=2000)
        lang: Literal["zh", "en"] = "zh"


    @router.post("/synthesize", status_code=status.HTTP_202_ACCEPTED)
    async def synthesize_endpoint(
        body: SynthesizeRequest,
        background: BackgroundTasks,
    ) -> dict[str, Any]:
        """API-06: enqueue a Q&A synthesis job. Returns 202 + job_id; poll via GET."""
        jid = job_store.new_job(kind="synthesize")
        background.add_task(kb_synthesize, body.question, body.lang, jid)
        return {"job_id": jid, "status": "running"}


    @router.get("/synthesize/{job_id}")
    async def synthesize_status(job_id: str) -> dict[str, Any]:
        """API-07: poll a synthesis job. 404 on unknown id."""
        job = job_store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"job {job_id!r} not found")
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "result": job["result"],
            "fallback_used": job["fallback_used"],
            "confidence": job["confidence"],
            "error": job["error"],
        }
    ```

    **Step 2 — Extend `kb/api.py`** to include the router:

    ```python
    from kb.api_routers.synthesize import router as synthesize_router
    app.include_router(synthesize_router)
    ```

    **Step 3 — Create `tests/integration/kb/test_api_synthesize.py`** with the 9 behaviors. Reuse helpers:

    ```python
    """Integration tests for /api/synthesize + /api/synthesize/{job_id} (API-06/07)."""
    from __future__ import annotations

    import asyncio
    import importlib
    import time
    from pathlib import Path

    import pytest
    from fastapi.testclient import TestClient


    @pytest.fixture
    def app_client(tmp_path, monkeypatch):
        # Redirect OmniGraph BASE_DIR so synthesis_output.md goes to tmp_path
        import config as og_config
        monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)
        # Reload kb.api so the new env / config is picked up
        import kb.config, kb.api_routers.synthesize, kb.api
        importlib.reload(kb.config)
        importlib.reload(kb.api_routers.synthesize)
        importlib.reload(kb.api)
        return TestClient(kb.api.app)


    def _patch_c1_success(monkeypatch, output: str = "# Answer\n\nSee [a](/article/abcd012345)"):
        async def fake(query_text: str, mode: str = "hybrid"):
            import config as og_config
            (Path(og_config.BASE_DIR) / "synthesis_output.md").write_text(output, encoding="utf-8")
        monkeypatch.setattr("kg_synthesize.synthesize_response", fake)


    def _patch_c1_failure(monkeypatch):
        async def fake(*a, **kw):
            raise RuntimeError("LightRAG unavailable")
        monkeypatch.setattr("kg_synthesize.synthesize_response", fake)


    def test_synthesize_post_202_with_job_id(app_client, monkeypatch):
        _patch_c1_success(monkeypatch)
        r = app_client.post("/api/synthesize", json={"question": "What is X?", "lang": "en"})
        assert r.status_code == 202
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
        r = app_client.post("/api/synthesize", json={"question": "x" * 3000, "lang": "zh"})
        assert r.status_code == 422


    def test_synthesize_get_unknown_job_404(app_client):
        r = app_client.get("/api/synthesize/zzzzzzzzzzzz")
        assert r.status_code == 404


    def test_synthesize_full_happy_path(app_client, monkeypatch):
        _patch_c1_success(monkeypatch)
        r = app_client.post("/api/synthesize", json={"question": "What is X?", "lang": "en"})
        jid = r.json()["job_id"]
        # Poll up to 2s for completion
        for _ in range(20):
            time.sleep(0.1)
            status = app_client.get(f"/api/synthesize/{jid}").json()
            if status["status"] == "done":
                assert status["confidence"] == "kg"
                assert status["fallback_used"] is False
                assert status["result"] is not None
                assert "markdown" in status["result"]
                assert "sources" in status["result"]
                assert "abcd012345" in status["result"]["sources"]
                return
        pytest.fail(f"job did not complete; last status={status}")


    def test_synthesize_failure_path_basic(app_client, monkeypatch):
        """Basic failure path — kb-3-09 will replace this with fts5_fallback success."""
        _patch_c1_failure(monkeypatch)
        r = app_client.post("/api/synthesize", json={"question": "q", "lang": "zh"})
        jid = r.json()["job_id"]
        for _ in range(20):
            time.sleep(0.1)
            status = app_client.get(f"/api/synthesize/{jid}").json()
            if status["status"] in ("done", "failed"):
                # Pre-kb-3-09: status='failed' with error
                # Post-kb-3-09: status='done' with confidence='fts5_fallback'
                # Either is acceptable for this test (both are terminal)
                assert status["status"] in ("failed", "done")
                if status["status"] == "failed":
                    assert "LightRAG unavailable" in (status.get("error") or "")
                return
        pytest.fail(f"job did not become terminal; last status={status}")


    def test_synthesize_zh_lang_directive_used(app_client, monkeypatch):
        captured = {"text": None}
        async def fake(query_text: str, mode: str = "hybrid"):
            captured["text"] = query_text
            import config as og_config
            (Path(og_config.BASE_DIR) / "synthesis_output.md").write_text("ok", encoding="utf-8")
        monkeypatch.setattr("kg_synthesize.synthesize_response", fake)
        r = app_client.post("/api/synthesize", json={"question": "问题", "lang": "zh"})
        jid = r.json()["job_id"]
        for _ in range(20):
            time.sleep(0.1)
            if app_client.get(f"/api/synthesize/{jid}").json()["status"] != "running":
                break
        assert captured["text"].startswith("请用中文回答。\n\n")
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/integration/kb/test_api_synthesize.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `kb/api_routers/synthesize.py` exists with ≥60 lines
    - `grep -q "@router.post..\"/synthesize\"" kb/api_routers/synthesize.py`
    - `grep -q "@router.get..\"/synthesize/{job_id}\"" kb/api_routers/synthesize.py`
    - `grep -q "BackgroundTasks" kb/api_routers/synthesize.py`
    - `grep -q "SynthesizeRequest" kb/api_routers/synthesize.py`
    - `grep -q "include_router.*synthesize_router" kb/api.py`
    - `grep -q "Skill(skill=\"python-patterns\"" kb/api_routers/synthesize.py`
    - `grep -q "Skill(skill=\"writing-tests\"" kb/api_routers/synthesize.py`
    - `pytest tests/integration/kb/test_api_synthesize.py -v` exits 0 with ≥9 tests passing
    - kb-3-04/05/06 regression: `pytest tests/integration/kb/ -v` exits 0
  </acceptance_criteria>
  <done>POST /api/synthesize + GET /api/synthesize/{job_id} live; 202 + job_id pattern; ≥9 integration tests; C1 unchanged.</done>
</task>

</tasks>

<verification>
- API-06 + API-07 endpoints live + tested
- I18N-07 + QA-01 + QA-02: lang directive correctly prepended (test_synthesize_zh_lang_directive_used asserts the directive in C1's query_text arg)
- QA-03: BackgroundTasks single-worker pattern, in-memory job_store
- C1 contract preserved (signature `synthesize_response(query_text, mode='hybrid')` unchanged)
- python-patterns + writing-tests Skills literal in code AND will appear in SUMMARY
- ≥17 tests pass (8 wrapper + 9 endpoint)
</verification>

<success_criteria>
- API-06: POST /api/synthesize 202 + job_id
- API-07: GET /api/synthesize/{job_id} returns job state
- I18N-07: lang directive prepended verbatim
- QA-01: wrapper module ≤ 50 LOC active code (excluding docstring + Skill comments)
- QA-02: only directive prepended; no other prompt manipulation
- QA-03: BackgroundTasks + in-memory job_store
</success_criteria>

<output>
Create `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-08-SUMMARY.md` documenting:
- 2 endpoints + wrapper module + Pydantic request model
- ≥17 tests passing (8 wrapper + 9 endpoint)
- Skill invocation strings literal: `Skill(skill="python-patterns", ...)` AND `Skill(skill="writing-tests", ...)`
- C1 contract preserved
- Failure path is BASIC (status='failed') — kb-3-09 replaces with fts5_fallback success
</output>
</content>
</invoke>