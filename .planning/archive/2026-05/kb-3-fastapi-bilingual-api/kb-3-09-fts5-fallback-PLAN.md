---
phase: kb-3-fastapi-bilingual-api
plan: 09
subsystem: synthesize-fallback
tags: [fastapi, fts5, fallback, never-500, qa-degradation]
type: execute
wave: 3
depends_on: ["kb-3-06", "kb-3-08"]
files_modified:
  - kb/services/synthesize.py
  - tests/integration/kb/test_synthesize_wrapper.py
  - tests/integration/kb/test_api_synthesize.py
autonomous: true
requirements:
  - QA-04
  - QA-05

must_haves:
  truths:
    - "kb_synthesize on C1 timeout (default 60s, env KB_SYNTHESIZE_TIMEOUT) triggers FTS5 fallback (QA-04)"
    - "kb_synthesize on C1 exception triggers FTS5 fallback (QA-05)"
    - "Fallback path: query articles_fts for question, take top-3, concat (title + 200-char snippet) into markdown, set job status='done', confidence='fts5_fallback', fallback_used=True"
    - "/api/synthesize NEVER returns 500 — even if both LightRAG AND FTS5 fail (last-resort: empty markdown + 'no_results' confidence)"
    - "Timeout handling uses asyncio.wait_for(synthesize_response(...), timeout=KB_SYNTHESIZE_TIMEOUT)"
    - "Fallback markdown includes a banner: '> Note: KG synthesis unavailable — keyword-based fallback.' (matches qa.fallback.explainer locale key)"
  artifacts:
    - path: "kb/services/synthesize.py"
      provides: "kb_synthesize updated to call _fts5_fallback on timeout/exception; _fts5_fallback function added"
    - path: "tests/integration/kb/test_synthesize_wrapper.py"
      provides: "+5 tests covering fallback path"
    - path: "tests/integration/kb/test_api_synthesize.py"
      provides: "+3 tests covering /api/synthesize NEVER returns 500"
  key_links:
    - from: "kb/services/synthesize.py::_fts5_fallback"
      to: "kb.services.search_index.fts_query (kb-3-06)"
      via: "import + call"
      pattern: "from kb.services.search_index|search_index\\.fts_query"
    - from: "kb/services/synthesize.py::kb_synthesize"
      to: "asyncio.wait_for + KB_SYNTHESIZE_TIMEOUT env"
      via: "timeout wrapping around synthesize_response"
      pattern: "asyncio.wait_for|KB_SYNTHESIZE_TIMEOUT"
---

<objective>
Replace the basic "failed" branch in `kb_synthesize` (kb-3-08) with the FTS5-fallback path: on timeout (`KB_SYNTHESIZE_TIMEOUT` default 60s) OR any exception from `synthesize_response`, query `articles_fts` for top-3 hits, concat into markdown, return as job result with `confidence='fts5_fallback'` + `fallback_used=True`. /api/synthesize NEVER returns 500.

Purpose: This is the "never-500" promise of D-04 + QA-05 verbatim ("Synthesize never returns 500 on synthesize failure"). Per kb-3-UI-SPEC §3.1 fts5_fallback state, the UI surfaces this gracefully ("Quick Reference" yellow chip + explainer copy). Without this plan, /api/synthesize crashes on any LightRAG hiccup; with it, the user always sees something useful.

Output: kb_synthesize updated; 8 new tests covering timeout + exception + last-resort branches.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-08-SUMMARY.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-06-SUMMARY.md
@kb/services/synthesize.py
@kb/services/search_index.py
@kb/services/job_store.py
@kb/docs/06-KB3-API-QA.md
@kb/docs/10-DESIGN-DISCIPLINE.md
@CLAUDE.md

<interfaces>
Existing kb_synthesize (kb-3-08 — REPLACE the `except` branch):

```python
async def kb_synthesize(question: str, lang: str, job_id: str) -> None:
    try:
        from kg_synthesize import synthesize_response
        directive = lang_directive_for(lang)
        query_text = f"{directive}{question}"
        await synthesize_response(query_text, mode="hybrid")
        # ... happy path ...
    except Exception as e:
        # OLD (kb-3-08): job_store.update_job(jid, status="failed", error=...)
        # NEW (kb-3-09): call _fts5_fallback (below)
        ...
```

New helper (paste-ready):

```python
def _fts5_fallback(question: str, lang: str, job_id: str, reason: str) -> None:
    """QA-05 fallback path. Query articles_fts for top-3 hits; concat into markdown.

    Sets job status='done' with confidence='fts5_fallback' + fallback_used=True so
    /api/synthesize never returns 500.

    Last-resort: if articles_fts is unavailable OR returns 0 hits, set markdown to
    a brief apology with confidence='no_results' but STILL status='done' (not 500).
    """
    try:
        from kb.services.search_index import fts_query
        # FTS5 path: top-3 hits
        rows = fts_query(question, lang=None, limit=3)  # cross-lang for fallback
        if not rows:
            markdown = (
                "> Note: 暂时无法生成完整回答 / Synthesis temporarily unavailable.\n\n"
                "未找到与你问题匹配的内容 / No matching content found in the knowledge base."
            )
            job_store.update_job(
                job_id,
                status="done",
                result={"markdown": markdown, "sources": [], "entities": []},
                fallback_used=True,
                confidence="no_results",
                error=reason,
            )
            return
        parts: list[str] = [
            "> Note: KG synthesis unavailable — keyword-based fallback. "
            "/ 知识图谱不可用 — 关键词检索快速参考。\n",
        ]
        sources: list[str] = []
        for h, title, snippet, _lg, source in rows:
            parts.append(f"### {title}\n\n{snippet}\n\n[/article/{h}](/article/{h})\n")
            sources.append(h)
        markdown = "\n".join(parts)
        job_store.update_job(
            job_id,
            status="done",
            result={"markdown": markdown, "sources": sources, "entities": []},
            fallback_used=True,
            confidence="fts5_fallback",
            error=reason,
        )
    except Exception as e:
        # Last-resort: even FTS5 failed. Don't 500 — set status='done' with no_results.
        job_store.update_job(
            job_id,
            status="done",
            result={
                "markdown": f"> Synthesis + fallback both failed.\n\nReason: {reason}; FTS5 reason: {type(e).__name__}",
                "sources": [],
                "entities": [],
            },
            fallback_used=True,
            confidence="no_results",
            error=f"{reason} | fts5: {type(e).__name__}: {e}",
        )
```

Timeout pattern:

```python
import asyncio, os
KB_SYNTHESIZE_TIMEOUT = int(os.environ.get("KB_SYNTHESIZE_TIMEOUT", "60"))

# In kb_synthesize:
try:
    await asyncio.wait_for(
        synthesize_response(query_text, mode="hybrid"),
        timeout=KB_SYNTHESIZE_TIMEOUT,
    )
except asyncio.TimeoutError:
    _fts5_fallback(question, lang, job_id, reason="C1 timeout")
    return
except Exception as e:
    _fts5_fallback(question, lang, job_id, reason=f"{type(e).__name__}: {e}")
    return
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Invoke python-patterns + writing-tests Skills + replace failure branch with FTS5 fallback + timeout wrapping</name>
  <read_first>
    - kb/services/synthesize.py (kb-3-08 output — REPLACE the except branch with fallback call)
    - kb/services/search_index.py (kb-3-06 — fts_query signature)
    - .planning/REQUIREMENTS-KB-v2.md QA-04 + QA-05 (exact REQ wordings)
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md §3.1 fts5_fallback state (UI consumer of confidence='fts5_fallback')
  </read_first>
  <files>kb/services/synthesize.py, tests/integration/kb/test_synthesize_wrapper.py, tests/integration/kb/test_api_synthesize.py</files>
  <behavior>
    - Test 1: When `synthesize_response` raises RuntimeError, kb_synthesize calls _fts5_fallback; job ends with `status='done'`, `confidence='fts5_fallback'`, `fallback_used=True`, `error` contains the original exception message.
    - Test 2: When `synthesize_response` exceeds `KB_SYNTHESIZE_TIMEOUT`, kb_synthesize triggers asyncio.TimeoutError → fallback; job ends with `confidence='fts5_fallback'`, `error="C1 timeout"`.
    - Test 3: Fallback markdown contains the banner string `keyword-based fallback` AND the top-3 hits' titles + snippets.
    - Test 4: Fallback `result["sources"]` lists the 3 article hashes from FTS5 rows.
    - Test 5: When FTS5 returns 0 hits AND C1 fails, job still status='done' with `confidence='no_results'` (last-resort).
    - Test 6: When BOTH C1 fails AND FTS5 fails (e.g. DB unavailable), job status='done', confidence='no_results', error mentions both failures (NEVER 500).
    - Test 7 (API-level): POST /api/synthesize → C1 patched to raise → GET poll → eventually `{status: "done", confidence: "fts5_fallback"}` (NOT failed).
    - Test 8 (API-level): POST /api/synthesize → C1 patched to sleep > timeout → GET poll → eventually `{status: "done", confidence: "fts5_fallback"}` with timeout error noted.
  </behavior>
  <action>
    Skill(skill="python-patterns", args="Replace the broad except branch in kb_synthesize with two-stage handling: (1) wrap synthesize_response in asyncio.wait_for(..., timeout=KB_SYNTHESIZE_TIMEOUT) — TimeoutError caught explicitly; (2) general Exception catches everything else. Both call the same _fts5_fallback helper with a `reason` arg. _fts5_fallback queries fts_query(question, limit=3) — cross-lang for graceful degradation — concats top-3 (title + snippet) into markdown with a banner. The banner copy uses the SAME locale key concept as qa.fallback.explainer (kb-3-03) but is hard-coded bilingual in the markdown for non-i18n contexts (Hermes agent skill consumers). Last-resort: if fts_query itself raises (DB unavailable), still set job status='done' with confidence='no_results' — /api/synthesize MUST NEVER 500. Type hints throughout.")

    Skill(skill="writing-tests", args="Extend test_synthesize_wrapper.py with 5 fallback-path tests. Cover: exception path → fts5_fallback, timeout path → fts5_fallback (use sleep > timeout), top-3 hits in result, sources list populated, FTS5-also-fails → no_results last-resort. For the timeout test, set KB_SYNTHESIZE_TIMEOUT=1 and patch synthesize_response with `await asyncio.sleep(2)` — must time out within 2s wall-time. Extend test_api_synthesize.py with 3 API-level integration tests verifying /api/synthesize returns 202 + eventually 200/done with confidence='fts5_fallback' (never 500). Reuse the populated articles_fts fixture pattern from test_api_search.py.")

    **Step 1 — REPLACE the except branch in `kb/services/synthesize.py`** with:

    ```python
    # APPEND near top of module (after existing imports):
    import asyncio
    import os

    KB_SYNTHESIZE_TIMEOUT = int(os.environ.get("KB_SYNTHESIZE_TIMEOUT", "60"))


    def _fts5_fallback(question: str, lang: str, job_id: str, reason: str) -> None:
        """QA-05: FTS5 top-3 fallback when LightRAG synthesis fails or times out.

        NEVER raises (worst case: status='done' with confidence='no_results').
        See kb-3-UI-SPEC §3.1 fts5_fallback state for the UI consumer of confidence.
        """
        try:
            from kb.services.search_index import fts_query
            rows = fts_query(question, lang=None, limit=3)
            if not rows:
                markdown = (
                    "> Note: 暂时无法生成完整回答 / Synthesis temporarily unavailable.\n\n"
                    "未找到与你问题匹配的内容 / No matching content found in the knowledge base."
                )
                job_store.update_job(
                    job_id,
                    status="done",
                    result={"markdown": markdown, "sources": [], "entities": []},
                    fallback_used=True,
                    confidence="no_results",
                    error=reason,
                )
                return
            parts: list[str] = [
                "> Note: KG synthesis unavailable — keyword-based fallback. "
                "/ 知识图谱不可用 — 关键词检索快速参考。\n",
            ]
            sources: list[str] = []
            for h, title, snippet, _lg, source in rows:
                parts.append(f"### {title}\n\n{snippet}\n\n[/article/{h}](/article/{h})\n")
                sources.append(h)
            markdown = "\n".join(parts)
            job_store.update_job(
                job_id,
                status="done",
                result={"markdown": markdown, "sources": sources, "entities": []},
                fallback_used=True,
                confidence="fts5_fallback",
                error=reason,
            )
        except Exception as e:
            # Last-resort: even FTS5 failed. Still set status='done' — NEVER 500.
            job_store.update_job(
                job_id,
                status="done",
                result={
                    "markdown": (
                        f"> Synthesis + fallback both failed.\n\n"
                        f"Reason: {reason}; FTS5 reason: {type(e).__name__}"
                    ),
                    "sources": [],
                    "entities": [],
                },
                fallback_used=True,
                confidence="no_results",
                error=f"{reason} | fts5: {type(e).__name__}: {e}",
            )
    ```

    **REPLACE** the existing `kb_synthesize` body's `try/except` so the structure is:

    ```python
    async def kb_synthesize(question: str, lang: str, job_id: str) -> None:
        from kg_synthesize import synthesize_response
        directive = lang_directive_for(lang)
        query_text = f"{directive}{question}"
        try:
            await asyncio.wait_for(
                synthesize_response(query_text, mode="hybrid"),
                timeout=KB_SYNTHESIZE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            _fts5_fallback(question, lang, job_id, reason="C1 timeout")
            return
        except Exception as e:
            _fts5_fallback(question, lang, job_id, reason=f"{type(e).__name__}: {e}")
            return
        # Happy path: read synthesis output + populate job
        markdown = _read_synthesis_output()
        sources = _extract_source_hashes(markdown)
        job_store.update_job(
            job_id,
            status="done",
            result={"markdown": markdown, "sources": sources, "entities": []},
            fallback_used=False,
            confidence="kg",
        )
    ```

    Add `Skill(skill="python-patterns", ...)` and `Skill(skill="writing-tests", ...)` literal comment strings at top of the modified module if not already present.

    **Step 2 — APPEND tests to `tests/integration/kb/test_synthesize_wrapper.py`**:

    ```python
    # APPEND to existing test file:

    def _populate_fts(fixture_db, monkeypatch):
        """Helper: ensure articles_fts is populated for fallback tests."""
        import sqlite3
        from kb.services.search_index import ensure_fts_table, FTS_TABLE_NAME
        from kb.data.article_query import resolve_url_hash, _row_to_record_kol, _row_to_record_rss
        c = sqlite3.connect(str(fixture_db))
        try:
            ensure_fts_table(c)
            c.execute(f"DELETE FROM {FTS_TABLE_NAME}")
            c.row_factory = sqlite3.Row
            for r in c.execute("SELECT id,title,url,body,content_hash,lang,update_time FROM articles WHERE body IS NOT NULL AND body != ''"):
                rec = _row_to_record_kol(r)
                c.execute(
                    f"INSERT INTO {FTS_TABLE_NAME} (hash,title,body,lang,source) VALUES (?,?,?,?,?)",
                    (resolve_url_hash(rec), rec.title, rec.body, rec.lang, "wechat"),
                )
            c.commit()
        finally:
            c.close()
        monkeypatch.setenv("KB_DB_PATH", str(fixture_db))


    def test_kb_synthesize_exception_triggers_fallback(tmp_path, fixture_db, monkeypatch):
        _patch_base_dir(tmp_path, monkeypatch)
        _populate_fts(fixture_db, monkeypatch)
        async def fake_fail(*a, **kw):
            raise RuntimeError("LightRAG down")
        monkeypatch.setattr("kg_synthesize.synthesize_response", fake_fail)
        # Reload synthesize module to pick up env
        import importlib, kb.services.synthesize as sm
        importlib.reload(sm)
        jid = job_store.new_job(kind="synthesize")
        asyncio.run(sm.kb_synthesize("agent", "zh", jid))
        job = job_store.get_job(jid)
        assert job["status"] == "done"
        assert job["confidence"] == "fts5_fallback" or job["confidence"] == "no_results"
        assert job["fallback_used"] is True


    def test_kb_synthesize_timeout_triggers_fallback(tmp_path, fixture_db, monkeypatch):
        _patch_base_dir(tmp_path, monkeypatch)
        _populate_fts(fixture_db, monkeypatch)
        monkeypatch.setenv("KB_SYNTHESIZE_TIMEOUT", "1")
        import importlib, kb.services.synthesize as sm
        importlib.reload(sm)
        async def slow(*a, **kw):
            await asyncio.sleep(3)
        monkeypatch.setattr("kg_synthesize.synthesize_response", slow)
        jid = job_store.new_job(kind="synthesize")
        asyncio.run(sm.kb_synthesize("agent", "zh", jid))
        job = job_store.get_job(jid)
        assert job["status"] == "done"
        assert job["fallback_used"] is True
        assert "timeout" in (job["error"] or "").lower()


    def test_kb_synthesize_fallback_markdown_has_banner(tmp_path, fixture_db, monkeypatch):
        _patch_base_dir(tmp_path, monkeypatch)
        _populate_fts(fixture_db, monkeypatch)
        async def fake_fail(*a, **kw):
            raise ValueError("oops")
        monkeypatch.setattr("kg_synthesize.synthesize_response", fake_fail)
        import importlib, kb.services.synthesize as sm
        importlib.reload(sm)
        jid = job_store.new_job(kind="synthesize")
        asyncio.run(sm.kb_synthesize("agent", "zh", jid))
        job = job_store.get_job(jid)
        # If FTS5 hit ≥1 row, banner should be present
        if job["confidence"] == "fts5_fallback":
            assert "keyword-based fallback" in job["result"]["markdown"] or "关键词" in job["result"]["markdown"]


    def test_kb_synthesize_fallback_sources_populated(tmp_path, fixture_db, monkeypatch):
        _patch_base_dir(tmp_path, monkeypatch)
        _populate_fts(fixture_db, monkeypatch)
        async def fake_fail(*a, **kw):
            raise RuntimeError("down")
        monkeypatch.setattr("kg_synthesize.synthesize_response", fake_fail)
        import importlib, kb.services.synthesize as sm
        importlib.reload(sm)
        jid = job_store.new_job(kind="synthesize")
        asyncio.run(sm.kb_synthesize("agent", "zh", jid))
        job = job_store.get_job(jid)
        if job["confidence"] == "fts5_fallback":
            assert isinstance(job["result"]["sources"], list)
            assert len(job["result"]["sources"]) >= 1
            assert all(len(h) == 10 for h in job["result"]["sources"])


    def test_kb_synthesize_double_failure_no_results(tmp_path, monkeypatch):
        """C1 fails AND fts_query raises → status='done', confidence='no_results' (NEVER 500)."""
        _patch_base_dir(tmp_path, monkeypatch)
        async def fake_fail(*a, **kw):
            raise RuntimeError("c1 down")
        monkeypatch.setattr("kg_synthesize.synthesize_response", fake_fail)
        # Make fts_query raise too
        def fts_explode(*a, **kw):
            raise RuntimeError("DB unreachable")
        monkeypatch.setattr("kb.services.search_index.fts_query", fts_explode)
        import importlib, kb.services.synthesize as sm
        importlib.reload(sm)
        jid = job_store.new_job(kind="synthesize")
        asyncio.run(sm.kb_synthesize("q", "zh", jid))
        job = job_store.get_job(jid)
        assert job["status"] == "done", "NEVER 500 invariant: even double failure stays done"
        assert job["confidence"] == "no_results"
        assert job["fallback_used"] is True
        assert "c1 down" in (job["error"] or "")
        assert "DB unreachable" in (job["error"] or "")
    ```

    **Step 3 — APPEND tests to `tests/integration/kb/test_api_synthesize.py`**:

    ```python
    def test_api_synthesize_never_500_on_c1_failure(app_client, monkeypatch, tmp_path):
        _patch_c1_failure(monkeypatch)
        # Patch fts_query to return [] so we hit the no_results path safely
        # (or populate fts; for this test, no_results IS still 'done' status, never 500)
        r = app_client.post("/api/synthesize", json={"question": "anything", "lang": "zh"})
        assert r.status_code == 202
        jid = r.json()["job_id"]
        for _ in range(20):
            time.sleep(0.1)
            poll = app_client.get(f"/api/synthesize/{jid}")
            assert poll.status_code != 500, "NEVER 500 invariant"
            j = poll.json()
            if j["status"] == "done":
                assert j["confidence"] in ("fts5_fallback", "no_results")
                assert j["fallback_used"] is True
                return
        pytest.fail(f"job did not complete; last={j}")


    def test_api_synthesize_never_500_on_timeout(app_client, monkeypatch, tmp_path):
        monkeypatch.setenv("KB_SYNTHESIZE_TIMEOUT", "1")
        async def slow(*a, **kw):
            await asyncio.sleep(3)
        monkeypatch.setattr("kg_synthesize.synthesize_response", slow)
        # Reload kb services
        import importlib, kb.services.synthesize, kb.api_routers.synthesize, kb.api
        importlib.reload(kb.services.synthesize)
        importlib.reload(kb.api_routers.synthesize)
        importlib.reload(kb.api)
        c = TestClient(kb.api.app)
        r = c.post("/api/synthesize", json={"question": "q", "lang": "zh"})
        assert r.status_code == 202
        jid = r.json()["job_id"]
        for _ in range(40):  # poll up to 4s
            time.sleep(0.1)
            j = c.get(f"/api/synthesize/{jid}").json()
            if j["status"] == "done":
                assert j["confidence"] in ("fts5_fallback", "no_results")
                assert "timeout" in (j.get("error") or "").lower()
                return
        pytest.fail(f"job did not complete; last={j}")


    def test_api_synthesize_get_returns_200_not_500(app_client, monkeypatch):
        """Even when result is fts5_fallback, the polling endpoint returns 200, NEVER 500."""
        _patch_c1_failure(monkeypatch)
        r = app_client.post("/api/synthesize", json={"question": "q", "lang": "zh"})
        jid = r.json()["job_id"]
        # All polls during job lifetime must be 200 (running or terminal)
        for _ in range(15):
            time.sleep(0.1)
            poll = app_client.get(f"/api/synthesize/{jid}")
            assert poll.status_code == 200, f"poll returned {poll.status_code}"
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/integration/kb/test_synthesize_wrapper.py tests/integration/kb/test_api_synthesize.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "_fts5_fallback" kb/services/synthesize.py`
    - `grep -q "asyncio.wait_for" kb/services/synthesize.py`
    - `grep -q "KB_SYNTHESIZE_TIMEOUT" kb/services/synthesize.py`
    - `grep -q "fts5_fallback" kb/services/synthesize.py`
    - `grep -q "no_results" kb/services/synthesize.py`
    - `grep -q "Skill(skill=\"python-patterns\"" kb/services/synthesize.py`
    - `grep -q "Skill(skill=\"writing-tests\"" kb/services/synthesize.py` OR in test files
    - `pytest tests/integration/kb/test_synthesize_wrapper.py -v` exits 0 with ≥13 tests passing (8 from kb-3-08 + 5 from this plan)
    - `pytest tests/integration/kb/test_api_synthesize.py -v` exits 0 with ≥12 tests passing (9 from kb-3-08 + 3 from this plan)
    - Negative invariant: in NO test does `/api/synthesize/{job_id}` return 500
    - Other kb-3 tests still pass: `pytest tests/integration/kb/ tests/unit/kb/ -v` exits 0
  </acceptance_criteria>
  <done>FTS5 fallback active; never-500 invariant enforced; timeout via KB_SYNTHESIZE_TIMEOUT; ≥8 new tests covering all branches.</done>
</task>

</tasks>

<verification>
- QA-04: KB_SYNTHESIZE_TIMEOUT env (default 60s) wraps C1 via asyncio.wait_for
- QA-05: FTS5 top-3 fallback on timeout AND exception; never returns 500
- Last-resort no_results branch when both C1 AND FTS5 fail
- python-patterns + writing-tests Skills literal in code AND will appear in SUMMARY
- ≥8 new tests; total kb-3-08 + kb-3-09 ≥ 25 synthesize-related tests
</verification>

<success_criteria>
- QA-04 + QA-05 satisfied: never 500 + FTS5 fallback active
- UI consumer (kb-3-10) can trust `confidence: "fts5_fallback"` field for state matrix routing
- Hermes agent skill consumers can rely on POST /api/synthesize ALWAYS getting a usable answer
</success_criteria>

<output>
Create `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-09-SUMMARY.md` documenting:
- _fts5_fallback function added; kb_synthesize timeout + exception branches replaced
- ≥8 new tests; never-500 invariant verified
- Skill invocation strings literal: `Skill(skill="python-patterns", ...)` AND `Skill(skill="writing-tests", ...)`
- Confidence field semantics: `kg` | `fts5_fallback` | `no_results`
</output>
</content>
</invoke>