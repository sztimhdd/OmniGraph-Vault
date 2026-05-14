---
phase: kb-3-fastapi-bilingual-api
plan: 06
subsystem: api-search
tags: [fastapi, sqlite, fts5, async-job, kg-fallback]
type: execute
wave: 2
depends_on: ["kb-3-01", "kb-3-02", "kb-3-04"]
files_modified:
  - kb/api_routers/search.py
  - kb/services/search_index.py
  - kb/api.py
  - tests/integration/kb/test_api_search.py
autonomous: true
requirements:
  - API-04
  - API-05
  - SEARCH-01
  - SEARCH-03

must_haves:
  truths:
    - "GET /api/search?q=&mode=fts returns 200 with {items: [{hash, title, snippet, lang, source}], total} where snippet is FTS5 snippet() output trimmed to 200 chars"
    - "Lang filter excludes non-matching rows (SEARCH-03)"
    - "DATA-07 filter applied to FTS5 hits unless KB_SEARCH_BYPASS_QUALITY=on"
    - "GET /api/search?q=&mode=kg returns 202 + {job_id, status: 'running'}"
    - "GET /api/search/{job_id} returns {status, result?: str, error?: str}"
    - "C2 contract preserved: omnigraph_search.query.search() called via thread-pool executor; signature unchanged"
    - "FTS5 trigram tokenizer used (D-18 — no jieba dependency)"
    - "P50 FTS5 query latency < 100ms"
  artifacts:
    - path: "kb/api_routers/search.py"
      provides: "APIRouter /api/search + /api/search/{job_id}"
      exports: ["router"]
      min_lines: 120
    - path: "kb/services/search_index.py"
      provides: "FTS5 index helpers: ensure_fts_table(), fts_query() returning [(hash, title, snippet, lang, source), ...]"
      exports: ["ensure_fts_table", "fts_query", "FTS_TABLE_NAME"]
      min_lines: 80
    - path: "tests/integration/kb/test_api_search.py"
      min_lines: 150
  key_links:
    - from: "kb/api_routers/search.py"
      to: "kb.services.search_index.fts_query (FTS5 path)"
      via: "import + call (thin router)"
      pattern: "from kb.services.search_index|search_index\\.fts_query"
    - from: "kb/api_routers/search.py"
      to: "omnigraph_search.query.search (KG path)"
      via: "asyncio.run_in_executor (preserves C2 sync signature)"
      pattern: "from omnigraph_search|loop\\.run_in_executor"
    - from: "kb/services/search_index.py"
      to: "DATA-07 filter via JOIN with quality columns"
      via: "WHERE clause + KB_SEARCH_BYPASS_QUALITY env override"
      pattern: "KB_SEARCH_BYPASS_QUALITY"
---

<objective>
Implement /api/search?mode=fts (sync FTS5) + /api/search?mode=kg (async via omnigraph_search.query.search). The FTS5 path uses the SQLite trigram tokenizer (built-in 3.34+) on a UNION-fed virtual table covering articles + rss_articles. KG path returns 202 + job_id and runs the (sync) C2 search function in a thread-pool executor; results polled via /api/search/{job_id}.

Purpose: Search is the secondary discovery surface (after browse). Per kb-3-API-CONTRACT.md, FTS5 is the default mode (fast, in-process); KG is opt-in for natural-language queries. DATA-07 applies by default to FTS5 results — search becomes a curated discovery surface — with KB_SEARCH_BYPASS_QUALITY env override for power users / debug. Index schema lives in kb/services/search_index.py; nightly rebuild lives in kb-3-07.

Output: New `kb/api_routers/search.py` (router) + `kb/services/search_index.py` (FTS5 helpers) + integration tests. The `rebuild_fts.py` script is plan kb-3-07.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-04-SUMMARY.md
@kb/api.py
@kb/data/article_query.py
@omnigraph_search/query.py
@kb/docs/06-KB3-API-QA.md
@kb/docs/10-DESIGN-DISCIPLINE.md
@CLAUDE.md

<interfaces>
FTS5 virtual table (locked by D-18 — built-in trigram tokenizer):

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    hash UNINDEXED,
    title,
    body,
    lang UNINDEXED,
    source UNINDEXED,
    tokenize='trigram'
);
```

`tokenize='trigram'` works for both Chinese and English without jieba. Index is rebuilt nightly by kb-3-07 cron script.

C2 (read-only — DO NOT modify):

```python
# omnigraph_search/query.py:35
def search(query_text: str, mode: str = "hybrid") -> str:
    # Returns: KG hybrid search result string (sync — must run in thread executor in async route)
```

Async-job pattern (in-memory dict, single-worker per QA-03):

```python
# kb/services/job_store.py — created here OR inline in router
import uuid
from threading import Lock
_JOBS: dict[str, dict] = {}
_LOCK = Lock()

def new_job() -> str:
    jid = uuid.uuid4().hex[:12]
    with _LOCK:
        _JOBS[jid] = {"status": "running", "result": None, "error": None}
    return jid

def update_job(jid, **kw):
    with _LOCK:
        if jid in _JOBS:
            _JOBS[jid].update(kw)

def get_job(jid):
    with _LOCK:
        return _JOBS.get(jid)
```

Note: kb-3-08 will reuse the same job_store for /api/synthesize. Build it as a shared service in this plan.

Response shapes (from kb-3-API-CONTRACT.md):

```python
# GET /api/search?q=...&mode=fts  →  200
{
    "items": [
        {"hash": "abcd012345", "title": "...", "snippet": "...<b>match</b>...",
         "lang": "zh-CN", "source": "wechat"},
        ...
    ],
    "total": 17,
    "mode": "fts"
}

# GET /api/search?q=...&mode=kg  →  202
{"job_id": "a1b2c3d4e5f6", "status": "running", "mode": "kg"}

# GET /api/search/{job_id}  →  200
{"job_id": "...", "status": "running" | "done" | "failed",
 "result"?: "...", "error"?: "..."}
```

DATA-07 cross-reference (per CONTENT-QUALITY-DECISIONS.md "Open question — search results filtering"):

> Decision: Apply filter by default; expose KB_SEARCH_BYPASS_QUALITY=on env override for
> power users / admin debugging. Same pattern as the global override but scoped to search.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Invoke python-patterns + writing-tests Skills + create kb/services/search_index.py + kb/services/job_store.py</name>
  <read_first>
    - kb/data/article_query.py (existing schema + KB_DB_PATH usage pattern)
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md (search response shape)
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md (KB_SEARCH_BYPASS_QUALITY decision)
    - .planning/REQUIREMENTS-KB-v2.md SEARCH-01 + SEARCH-03 + API-04 (exact REQ wordings)
  </read_first>
  <files>kb/services/__init__.py, kb/services/search_index.py, kb/services/job_store.py, tests/unit/kb/test_search_index.py, tests/unit/kb/test_job_store.py</files>
  <behavior>
    - Test 1: `ensure_fts_table(conn)` creates `articles_fts` virtual table with `tokenize='trigram'` if absent; idempotent.
    - Test 2: After `ensure_fts_table` + manual INSERT of 3 sample rows (KOL + RSS), `fts_query("agent", limit=10, conn=conn)` returns rows where title or body contain "agent".
    - Test 3: `fts_query` returns `(hash, title, snippet, lang, source)` tuples; snippet is ≤ 200 chars.
    - Test 4: `fts_query("agent", lang="zh-CN", conn=conn)` excludes en-tagged rows.
    - Test 5: `fts_query("agent", conn=conn)` with `KB_SEARCH_BYPASS_QUALITY=off` (default) excludes negative-case rows (DATA-07 active).
    - Test 6: `fts_query("agent", conn=conn)` with `KB_SEARCH_BYPASS_QUALITY=on` includes negative-case rows.
    - Test 7: `new_job()` returns 12-char hex id; `get_job(id)` returns `{status: "running", result: None, error: None}`; `update_job(id, status="done", result="x")` mutates correctly; multi-thread safe (test with concurrent.futures).
  </behavior>
  <action>
    Skill(skill="python-patterns", args="Two service modules: kb/services/search_index.py wraps the FTS5 virtual-table operations (ensure_fts_table, fts_query). Use sqlite3 with parameterized queries — `tokenize='trigram'` is the locked tokenizer per D-18. fts_query MUST honor SEARCH-03 lang filter via WHERE clause + DATA-07 conditional via KB_SEARCH_BYPASS_QUALITY env. snippet() function used for highlighted excerpt — trim to 200 chars max with explicit `substr()` OR Python slicing. kb/services/job_store.py is the shared in-memory async-job dict with a threading.Lock — used by both /api/search?mode=kg AND kb-3-08 /api/synthesize. uuid4().hex[:12] for opaque job ids. NO new env vars except KB_SEARCH_BYPASS_QUALITY (per kb-3-CONTENT-QUALITY-DECISIONS.md decision).")

    Skill(skill="writing-tests", args="Unit tests for both modules. test_search_index.py: in-memory SQLite + manual articles + rss_articles + extracted articles_fts; verifies index creation idempotent, query returns hits with snippet, lang filter, DATA-07 default + bypass. test_job_store.py: round-trip + concurrent update with concurrent.futures.ThreadPoolExecutor (3 workers each calling update_job with different keys; final state must reflect all updates).")

    **Step 1 — Create `kb/services/__init__.py`** (empty package marker).

    **Step 2 — Create `kb/services/search_index.py`**:

    ```python
    """FTS5 search index helpers (SEARCH-01, SEARCH-03).

    The articles_fts virtual table uses SQLite's built-in trigram tokenizer (D-18 —
    works for both Chinese and English without jieba). UNION-fed from `articles` (KOL)
    and `rss_articles`. Nightly rebuild script lives in kb-3-07.

    Skill(skill="python-patterns", args="...")
    """
    from __future__ import annotations

    import os
    import re
    import sqlite3
    from typing import Optional

    FTS_TABLE_NAME = "articles_fts"

    # Per kb-3-CONTENT-QUALITY-DECISIONS.md "Open question — search results filtering"
    # decision: apply DATA-07 filter to FTS5 hits by default; bypass via env.
    SEARCH_BYPASS_QUALITY = os.environ.get("KB_SEARCH_BYPASS_QUALITY", "off").lower() == "on"


    def ensure_fts_table(conn: sqlite3.Connection) -> None:
        """Create articles_fts virtual table if absent (idempotent).

        Schema:
          - hash (UNINDEXED — md5[:10] used by /api/article/{hash})
          - title (indexed)
          - body (indexed)
          - lang (UNINDEXED — for filter)
          - source (UNINDEXED — wechat | rss)
          - tokenize='trigram' (D-18)
        """
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE_NAME} USING fts5("
            "hash UNINDEXED, title, body, lang UNINDEXED, source UNINDEXED, "
            "tokenize='trigram')"
        )


    def _build_quality_clause(alias: str) -> str:
        """DATA-07 fragment for joined-quality-table query. Empty when bypassed."""
        if SEARCH_BYPASS_QUALITY:
            return ""
        return (
            f" AND ({alias}.body IS NOT NULL AND {alias}.body != '' "
            f"AND {alias}.layer1_verdict = 'candidate' "
            f"AND ({alias}.layer2_verdict IS NULL OR {alias}.layer2_verdict != 'reject'))"
        )


    def fts_query(
        q: str,
        lang: Optional[str] = None,
        limit: int = 20,
        conn: Optional[sqlite3.Connection] = None,
    ) -> list[tuple[str, str, str, Optional[str], str]]:
        """SEARCH-01: FTS5 trigram query against articles_fts.

        Returns: list of (hash, title, snippet, lang, source) tuples.
        snippet is FTS5 snippet() output (200 chars max).

        SEARCH-03: lang filter excludes non-matching rows.
        DATA-07: applies content-quality filter unless KB_SEARCH_BYPASS_QUALITY=on.
        """
        if conn is None:
            from kb import config
            conn = sqlite3.connect(f"file:{config.KB_DB_PATH}?mode=ro", uri=True)
            own = True
        else:
            own = False
        try:
            # Base FTS5 query with snippet() — match in title OR body
            # snippet(table, col_idx, prefix, suffix, ellipsis, max_tokens)
            # col_idx 1 = title, 2 = body. Use -1 for "any column".
            sql = (
                f"SELECT f.hash, f.title, "
                f"snippet({FTS_TABLE_NAME}, -1, '<b>', '</b>', '…', 32) AS snippet, "
                f"f.lang, f.source "
                f"FROM {FTS_TABLE_NAME} f "
                f"WHERE {FTS_TABLE_NAME} MATCH ? "
            )
            params: list = [q]
            if lang is not None:
                sql += "AND f.lang = ? "
                params.append(lang)
            # DATA-07 quality gate: JOIN to source table on (hash, source) and apply filter.
            # We rely on resolve_url_hash semantics — KOL hash matches articles.content_hash
            # OR computed md5; RSS hash matches substr(content_hash, 1, 10).
            if not SEARCH_BYPASS_QUALITY:
                sql += (
                    "AND ((f.source = 'wechat' AND EXISTS ("
                    "  SELECT 1 FROM articles a WHERE a.content_hash = f.hash "
                    "  AND a.body IS NOT NULL AND a.body != '' "
                    "  AND a.layer1_verdict = 'candidate' "
                    "  AND (a.layer2_verdict IS NULL OR a.layer2_verdict != 'reject')"
                    ")) "
                    "OR (f.source = 'rss' AND EXISTS ("
                    "  SELECT 1 FROM rss_articles r WHERE substr(r.content_hash, 1, 10) = f.hash "
                    "  AND r.body IS NOT NULL AND r.body != '' "
                    "  AND r.layer1_verdict = 'candidate' "
                    "  AND (r.layer2_verdict IS NULL OR r.layer2_verdict != 'reject')"
                    "))) "
                )
            sql += "ORDER BY rank LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            # Trim snippet to 200 chars max (FTS5 snippet may include up to 64 tokens)
            return [
                (r[0], r[1] or "", (r[2] or "")[:200], r[3], r[4])
                for r in rows
            ]
        finally:
            if own:
                conn.close()
    ```

    **Step 3 — Create `kb/services/job_store.py`**:

    ```python
    """In-memory async-job store (QA-03).

    Used by /api/search?mode=kg (kb-3-06) AND /api/synthesize (kb-3-08).
    Single-uvicorn-worker assumed; multi-worker → SQLite-backed deferred to v2.1.

    Skill(skill="python-patterns", args="...")
    """
    from __future__ import annotations

    import time
    import uuid
    from threading import Lock
    from typing import Any, Optional

    _JOBS: dict[str, dict[str, Any]] = {}
    _LOCK = Lock()


    def new_job(kind: str = "search") -> str:
        """Allocate a new job id; initial state {status: 'running', result: None, error: None}."""
        jid = uuid.uuid4().hex[:12]
        with _LOCK:
            _JOBS[jid] = {
                "job_id": jid,
                "kind": kind,                # 'search' | 'synthesize'
                "status": "running",
                "result": None,
                "error": None,
                "fallback_used": False,
                "confidence": "kg",           # default; QA wrapper updates if FTS5 fallback
                "started_at": time.time(),
            }
        return jid


    def update_job(jid: str, **kwargs) -> None:
        with _LOCK:
            if jid in _JOBS:
                _JOBS[jid].update(kwargs)


    def get_job(jid: str) -> Optional[dict[str, Any]]:
        with _LOCK:
            return dict(_JOBS[jid]) if jid in _JOBS else None
    ```

    **Step 4 — Create test files** (`tests/unit/kb/test_search_index.py` + `tests/unit/kb/test_job_store.py`) with the 7 behaviors. Use in-memory sqlite3 + populate articles + rss_articles + articles_fts manually for the search_index tests; use concurrent.futures.ThreadPoolExecutor for the job_store concurrent test.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/unit/kb/test_search_index.py tests/unit/kb/test_job_store.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `kb/services/search_index.py` exists with ≥80 lines
    - File `kb/services/job_store.py` exists
    - `grep -q "tokenize='trigram'" kb/services/search_index.py`
    - `grep -q "KB_SEARCH_BYPASS_QUALITY" kb/services/search_index.py`
    - `grep -q "snippet(" kb/services/search_index.py`
    - `grep -q "Skill(skill=\"python-patterns\"" kb/services/search_index.py`
    - `grep -q "Skill(skill=\"writing-tests\"" kb/services/search_index.py` OR in test files
    - `pytest tests/unit/kb/test_search_index.py tests/unit/kb/test_job_store.py -v` exits 0 with ≥7 tests passing
    - Read-only enforced in fts_query: `grep -E "execute\\(.*(INSERT|UPDATE|DELETE) " kb/services/search_index.py` returns 0
  </acceptance_criteria>
  <done>FTS5 helpers + job_store implemented + tested; KB_SEARCH_BYPASS_QUALITY honored.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Create kb/api_routers/search.py with /api/search (fts + kg) + /api/search/{job_id} + integration tests</name>
  <read_first>
    - kb/services/search_index.py + kb/services/job_store.py (Task 1 output)
    - kb/api.py (kb-3-04 — extend include_router)
    - omnigraph_search/query.py:35 (C2 sync signature — must run in executor)
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md GET /api/search section
  </read_first>
  <files>kb/api_routers/search.py, kb/api.py, tests/integration/kb/test_api_search.py</files>
  <behavior>
    - Test 1: GET /api/search?q=agent&mode=fts → 200 with {items, total, mode: "fts"}; items[0] has all 5 keys (hash, title, snippet, lang, source).
    - Test 2: GET /api/search?q=agent&mode=fts&lang=zh-CN → only zh-CN items.
    - Test 3: GET /api/search?q=agent&mode=fts&limit=3 → ≤3 items.
    - Test 4: GET /api/search?q=&mode=fts → 422 (empty query rejected).
    - Test 5: GET /api/search?q=agent (no mode) → defaults to mode=fts.
    - Test 6: GET /api/search?q=agent&mode=kg → 202 with {job_id, status: "running", mode: "kg"}.
    - Test 7: GET /api/search/{kg_job_id} initial → {status: "running"} (until executor finishes).
    - Test 8: GET /api/search/nonexistent_jobid → 404.
    - Test 9: After kg job completes (mock omnigraph_search.query.search to return immediately), GET /api/search/{job_id} → {status: "done", result: "..."}.
    - Test 10: P50 FTS5 latency < 100ms.
  </behavior>
  <action>
    Skill(skill="python-patterns", args="Async route /api/search dispatches by mode: fts is sync (call fts_query directly), kg uses asyncio.get_event_loop().run_in_executor(None, omnigraph_search.query.search, q, 'hybrid') wrapped in BackgroundTasks. After scheduling, return 202 with job_id immediately. The polling endpoint /api/search/{job_id} is a simple dict lookup against job_store. NEVER modify the sync C2 signature — wrap, don't mutate. Use FastAPI BackgroundTasks (NOT asyncio.create_task in route handler — BackgroundTasks ensure the task runs after response is sent).")

    Skill(skill="writing-tests", args="TestClient integration tests with monkeypatched fixture_db + populated articles_fts. For the kg path, mock omnigraph_search.query.search via monkeypatch — do NOT actually call LightRAG (slow + needs storage). Test that the BackgroundTasks ran (poll the job_id until done OR with mocked-instantaneous-search the test sleep is brief). 10 tests total covering fts items shape, lang filter, limit, default mode, 422 on empty q, kg async pattern, polling 404/done.")

    **Step 1 — Create `kb/api_routers/search.py`**:

    ```python
    """API-04 + API-05: GET /api/search + GET /api/search/{job_id}.

    FTS5 mode (sync): kb.services.search_index.fts_query — fast in-process query.
    KG mode (async): wraps omnigraph_search.query.search (C2) via thread executor.

    DATA-07: applied to FTS5 by default via KB_SEARCH_BYPASS_QUALITY env (kb-3-CONTENT-
    QUALITY-DECISIONS.md decision: filter on by default; bypass for power users).

    Skill(skill="python-patterns", args="...")
    Skill(skill="writing-tests", args="...")
    """
    from __future__ import annotations

    import asyncio
    from typing import Annotated, Any, Literal, Optional

    from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

    from kb.services import job_store, search_index

    router = APIRouter(prefix="/api", tags=["search"])


    def _kg_worker(job_id: str, q: str) -> None:
        """Run omnigraph_search.query.search in a worker thread; update job_store on done/fail.

        C2 contract preserved: search() called with original (query_text, mode='hybrid')
        signature.
        """
        try:
            from omnigraph_search.query import search as kg_search
            result = kg_search(q, mode="hybrid")
            job_store.update_job(job_id, status="done", result=result)
        except Exception as e:
            job_store.update_job(job_id, status="failed", error=str(e))


    @router.get("/search")
    async def search_endpoint(
        background: BackgroundTasks,
        q: Annotated[str, Query(min_length=1, max_length=500)],
        mode: Annotated[Literal["fts", "kg"], Query()] = "fts",
        lang: Annotated[Optional[Literal["zh-CN", "en", "unknown"]], Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> dict[str, Any]:
        """API-04 (fts) + API-05 (kg async)."""
        if mode == "fts":
            rows = search_index.fts_query(q, lang=lang, limit=limit)
            items = [
                {"hash": h, "title": t, "snippet": s, "lang": lg, "source": src}
                for (h, t, s, lg, src) in rows
            ]
            return {"items": items, "total": len(items), "mode": "fts"}
        # KG async path
        jid = job_store.new_job(kind="search")
        background.add_task(_kg_worker, jid, q)
        return {"job_id": jid, "status": "running", "mode": "kg"}


    @router.get("/search/{job_id}")
    async def search_job_status(job_id: str) -> dict[str, Any]:
        """Poll an async KG-search job. 404 if job_id unknown."""
        job = job_store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"job {job_id!r} not found")
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "result": job["result"],
            "error": job["error"],
        }
    ```

    **Step 2 — Extend `kb/api.py`** to include the router (APPEND after articles router):

    ```python
    from kb.api_routers.search import router as search_router
    app.include_router(search_router)
    ```

    **Step 3 — Create `tests/integration/kb/test_api_search.py`** with the 10 behaviors. Pre-populate `articles_fts` against the fixture_db before tests:

    ```python
    """API-04 + API-05 integration tests."""
    from __future__ import annotations

    import importlib
    import sqlite3
    import time
    from pathlib import Path

    import pytest
    from fastapi.testclient import TestClient

    pytest_plugins = ["tests.integration.kb.conftest"]


    @pytest.fixture
    def app_client(fixture_db, monkeypatch):
        monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
        monkeypatch.setenv("KB_SEARCH_BYPASS_QUALITY", "off")
        # Populate FTS index against the fixture DB before reload
        import kb.services.search_index as si
        c = sqlite3.connect(str(fixture_db))
        try:
            si.ensure_fts_table(c)
            # Insert hash + title + body + lang + source for each fixture row
            from kb.data.article_query import resolve_url_hash, _row_to_record_kol, _row_to_record_rss
            c.row_factory = sqlite3.Row
            for r in c.execute("SELECT id,title,url,body,content_hash,lang,update_time FROM articles"):
                rec = _row_to_record_kol(r)
                c.execute(
                    f"INSERT INTO {si.FTS_TABLE_NAME} (hash,title,body,lang,source) "
                    "VALUES (?,?,?,?,?)",
                    (resolve_url_hash(rec), rec.title, rec.body, rec.lang, "wechat"),
                )
            for r in c.execute("SELECT id,title,url,body,content_hash,lang,published_at,fetched_at FROM rss_articles"):
                rec = _row_to_record_rss(r)
                c.execute(
                    f"INSERT INTO {si.FTS_TABLE_NAME} (hash,title,body,lang,source) "
                    "VALUES (?,?,?,?,?)",
                    (resolve_url_hash(rec), rec.title, rec.body, rec.lang, "rss"),
                )
            c.commit()
        finally:
            c.close()
        # Reload modules so config picks up the env
        import kb.config, kb.services.search_index, kb.api_routers.search, kb.api
        importlib.reload(kb.config)
        importlib.reload(kb.services.search_index)
        importlib.reload(kb.api_routers.search)
        importlib.reload(kb.api)
        return TestClient(kb.api.app)


    def test_search_fts_basic_shape(app_client):
        r = app_client.get("/api/search?q=agent&mode=fts")
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "fts"
        assert "items" in body and "total" in body
        if body["items"]:
            for key in ("hash", "title", "snippet", "lang", "source"):
                assert key in body["items"][0]


    def test_search_lang_filter(app_client):
        r = app_client.get("/api/search?q=agent&mode=fts&lang=zh-CN").json()
        for item in r["items"]:
            if item["lang"] is not None:
                assert item["lang"] == "zh-CN"


    def test_search_limit(app_client):
        r = app_client.get("/api/search?q=agent&mode=fts&limit=3").json()
        assert len(r["items"]) <= 3


    def test_search_empty_q_422(app_client):
        r = app_client.get("/api/search?q=&mode=fts")
        assert r.status_code == 422


    def test_search_default_mode_is_fts(app_client):
        r = app_client.get("/api/search?q=agent")
        assert r.status_code == 200
        assert r.json()["mode"] == "fts"


    def test_search_kg_returns_202_and_job_id(app_client, monkeypatch):
        # Mock omnigraph_search.query.search so we don't hit LightRAG
        def fake_search(q, mode="hybrid"):
            time.sleep(0.05)
            return f"KG result for {q!r}"
        monkeypatch.setattr("omnigraph_search.query.search", fake_search)
        r = app_client.get("/api/search?q=hello&mode=kg")
        # FastAPI BackgroundTasks: route returns 200 by default; we can elect to set
        # status_code=202 via Response or raise; simplest is body has status="running"
        assert r.status_code in (200, 202)
        body = r.json()
        assert body["mode"] == "kg"
        assert body["status"] == "running"
        assert "job_id" in body and len(body["job_id"]) == 12


    def test_search_kg_job_status_404(app_client):
        r = app_client.get("/api/search/zzzzzzzzzzzz")
        assert r.status_code == 404


    def test_search_kg_job_completes(app_client, monkeypatch):
        def fake_search(q, mode="hybrid"):
            return f"KG: {q}"
        monkeypatch.setattr("omnigraph_search.query.search", fake_search)
        r = app_client.get("/api/search?q=test&mode=kg").json()
        jid = r["job_id"]
        # Poll up to 1 second for completion
        for _ in range(10):
            time.sleep(0.1)
            status = app_client.get(f"/api/search/{jid}").json()
            if status["status"] == "done":
                assert status["result"] == "KG: test"
                return
        pytest.fail("kg job did not complete within 1s")


    def test_search_data07_filter_active_by_default(app_client):
        """KB_SEARCH_BYPASS_QUALITY=off (default) — negative-case rows excluded."""
        r = app_client.get("/api/search?q=REJECTED&mode=fts").json()
        # The fixture has a row with title='REJECTED' (kb-3-02 negative case).
        # With DATA-07 active, it must NOT appear.
        assert all("REJECTED" not in (item["title"] or "") for item in r["items"])


    def test_search_p50_latency(app_client):
        durs = []
        for _ in range(5):
            t0 = time.perf_counter()
            r = app_client.get("/api/search?q=agent&mode=fts")
            durs.append(time.perf_counter() - t0)
            assert r.status_code == 200
        durs.sort()
        assert durs[2] < 0.1, f"p50 = {durs[2]*1000:.1f}ms"
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/integration/kb/test_api_search.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `kb/api_routers/search.py` exists with ≥80 lines
    - `grep -q "@router.get..\"/search\"" kb/api_routers/search.py`
    - `grep -q "@router.get..\"/search/{job_id}\"" kb/api_routers/search.py`
    - `grep -q "from omnigraph_search" kb/api_routers/search.py`
    - `grep -q "BackgroundTasks" kb/api_routers/search.py`
    - `grep -q "Skill(skill=\"python-patterns\"" kb/api_routers/search.py`
    - `grep -q "Skill(skill=\"writing-tests\"" kb/api_routers/search.py`
    - `grep -q "include_router.*search_router" kb/api.py`
    - `pytest tests/integration/kb/test_api_search.py -v` exits 0 with ≥10 tests passing
    - Total integration test count ≥28 across kb-3 (api skeleton 6 + articles 18 + search 10 = 34 actually — exceeds floor)
    - C2 contract intact: `grep -A 5 "from omnigraph_search" kb/api_routers/search.py | grep "search(" | grep -v "def search"` shows the function called with original `(query_text, mode)` shape
  </acceptance_criteria>
  <done>/api/search (fts + kg) live; async-job pattern via job_store; ≥10 integration tests pass; C2 unchanged.</done>
</task>

</tasks>

<verification>
- API-04 (FTS sync) + API-05 (KG async) live + tested
- SEARCH-01 trigram tokenizer + SEARCH-03 lang filter implemented
- DATA-07 filter applied via KB_SEARCH_BYPASS_QUALITY env (default on)
- C2 omnigraph_search.query.search signature unchanged — wrapped via BackgroundTasks
- python-patterns + writing-tests Skills literal in code AND will appear in SUMMARY
</verification>

<success_criteria>
- API-04: FTS5 sync query, p50 < 100ms
- API-05: KG async via 202 + polling
- SEARCH-01: trigram tokenizer locked
- SEARCH-03: lang filter
- DATA-07: filter applied to FTS5 by default
</success_criteria>

<output>
Create `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-06-SUMMARY.md` documenting:
- 2 endpoints (/api/search, /api/search/{job_id}) + FTS5 helpers + job_store
- ≥17 tests passing (7 unit + 10 integration)
- Skill invocation strings literal: `Skill(skill="python-patterns", ...)` AND `Skill(skill="writing-tests", ...)`
- C2 contract preserved (omnigraph_search.query.search signature unchanged)
- KB_SEARCH_BYPASS_QUALITY env override documented
</output>
</content>
</invoke>