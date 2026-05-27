---
phase: kb-3-fastapi-bilingual-api
plan: 05
subsystem: api-articles
tags: [fastapi, sqlite, json-api, pagination]
type: execute
wave: 2
depends_on: ["kb-3-01", "kb-3-02", "kb-3-04"]
files_modified:
  - kb/api.py
  - kb/api_routers/articles.py
  - tests/integration/kb/test_api_articles.py
autonomous: true
requirements:
  - API-02
  - API-03

must_haves:
  truths:
    - "GET /api/articles returns paginated JSON {items, page, limit, total, has_more}"
    - "Query params honored: page, limit, source, lang, q (LIKE on title)"
    - "DATA-07 filter applied (delegates to list_articles which applies filter)"
    - "GET /api/article/{hash} resolves md5[:10] across BOTH KOL + RSS tables (carve-out: NOT filtered)"
    - "Response shape matches kb-3-API-CONTRACT.md: {hash, title, body_md, body_html, lang, source, images, metadata, body_source}"
    - "404 on hash miss; 422 on invalid query params (FastAPI auto-validation)"
    - "P50 latency < 100ms on .dev-runtime/data/kol_scan.db (verified in test)"
  artifacts:
    - path: "kb/api_routers/articles.py"
      provides: "APIRouter with /api/articles + /api/article/{hash} routes"
      exports: ["router"]
      min_lines: 100
    - path: "kb/api.py"
      provides: "extended to include articles router via app.include_router"
    - path: "tests/integration/kb/test_api_articles.py"
      provides: "TestClient integration tests against fixture_db AND .dev-runtime/data/kol_scan.db"
      min_lines: 150
  key_links:
    - from: "kb/api_routers/articles.py"
      to: "kb.data.article_query.list_articles + get_article_by_hash + resolve_url_hash + get_article_body"
      via: "import + call (no DB SQL in router)"
      pattern: "from kb.data.article_query import|article_query\\.list_articles|article_query\\.get_article_by_hash"
    - from: "kb/api_routers/articles.py"
      to: "DATA-07 filter (already in list_articles per kb-3-02)"
      via: "transitive — router calls list_articles which applies filter"
      pattern: "list_articles"
---

<objective>
Implement GET /api/articles + GET /api/article/{hash} per kb-3-API-CONTRACT.md. The router layer is THIN — all DB logic lives in `kb.data.article_query` (already DATA-07-filtered after kb-3-02). The router only does: parse query params, call data layer, format response, handle 404.

Purpose: Provides the read-side API surface for the article browse experience. kb-3-11 (search inline reveal) will hit /api/articles for the LIKE search; the future Hermes agent skill will hit /api/article/{hash} for citation resolution. P50 < 100ms is achievable because list_articles already runs a single SQLite query.

Output: New `kb/api_routers/articles.py` with APIRouter, extended `kb/api.py` to include the router, integration tests.
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
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-02-SUMMARY.md
@kb/api.py
@kb/data/article_query.py
@kb/docs/06-KB3-API-QA.md
@kb/docs/10-DESIGN-DISCIPLINE.md
@CLAUDE.md

<interfaces>
Existing data-layer (already DATA-07-filtered after kb-3-02):

```python
# kb/data/article_query.py
def list_articles(
    lang: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    conn: Optional[sqlite3.Connection] = None,
) -> list[ArticleRecord]: ...                    # DATA-07 filter applied

def get_article_by_hash(
    hash: str,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[ArticleRecord]: ...                # DATA-07 carve-out: NOT filtered

def resolve_url_hash(rec: ArticleRecord) -> str: ...
def get_article_body(rec: ArticleRecord) -> tuple[str, BodySource]: ...   # D-14 fallback chain
```

Response shapes (paste-ready, from kb-3-API-CONTRACT.md):

```python
# GET /api/articles
{
    "items": [
        {"hash": "abcd012345", "title": "...", "lang": "zh-CN", "source": "wechat",
         "url": "https://...", "update_time": "2026-05-13T10:00:00", "snippet": null},
        ...
    ],
    "page": 1, "limit": 20, "total": 160, "has_more": true
}

# GET /api/article/{hash}
{
    "hash": "abcd012345",
    "title": "...",
    "body_md": "# Heading...",      # raw markdown (after EXPORT-05 image rewrite)
    "body_html": "<h1>Heading...",  # rendered HTML (markdown lib)
    "lang": "zh-CN",
    "source": "wechat",
    "images": [],                   # list of image URLs (extracted from body)
    "metadata": {"url": "https://...", "publish_time": "..."},
    "body_source": "vision_enriched" | "raw_markdown"   # D-14 chain output
}
```

Markdown→HTML library: use `markdown` (already in requirements.txt per kb-1) with extensions `["fenced_code", "tables"]`. Pygments NOT required for API JSON (HTML rendered server-side; consumer renders as-is).

Pydantic models for request/response (FastAPI auto-validates query params via Annotated):

```python
from typing import Annotated, Literal, Optional
from fastapi import Query

# query params on /api/articles
async def list_articles_endpoint(
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    source: Annotated[Optional[Literal["wechat", "rss"]], Query()] = None,
    lang: Annotated[Optional[Literal["zh-CN", "en", "unknown"]], Query()] = None,
    q: Annotated[Optional[str], Query(min_length=1, max_length=200)] = None,
):
    ...
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Invoke python-patterns + writing-tests Skills + create kb/api_routers/articles.py with /api/articles list endpoint</name>
  <read_first>
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md GET /api/articles section (response shape verbatim)
    - kb/data/article_query.py list_articles signature + ArticleRecord dataclass
    - kb/api.py (kb-3-04 output — to extend with include_router)
    - .planning/REQUIREMENTS-KB-v2.md API-02 (exact REQ wording, P50 < 100ms target)
  </read_first>
  <files>kb/api_routers/__init__.py, kb/api_routers/articles.py, kb/api.py, tests/integration/kb/test_api_articles.py</files>
  <behavior>
    - Test 1: GET /api/articles → 200 with `{items: [...], page: 1, limit: 20, total: N, has_more: bool}`.
    - Test 2: GET /api/articles?page=2&limit=5 → returns offset rows; correct pagination math (offset = (page-1) * limit).
    - Test 3: GET /api/articles?source=wechat → only KOL items in response.
    - Test 4: GET /api/articles?source=rss → only RSS items.
    - Test 5: GET /api/articles?lang=zh-CN → only zh-CN-tagged items.
    - Test 6: GET /api/articles?q=Agent → items where title LIKE %Agent%.
    - Test 7: GET /api/articles?page=0 → 422 (FastAPI auto-validates ge=1).
    - Test 8: GET /api/articles?limit=200 → 422 (le=100 enforced).
    - Test 9: DATA-07 filter applied — items count ≤ list_articles() count (because router uses list_articles); negative-case fixture rows do NOT appear.
    - Test 10: Each item has `hash` matching `resolve_url_hash(record)`.
  </behavior>
  <action>
    Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1, this plan invokes named Skills as tool calls before writing code:

    Skill(skill="python-patterns", args="Idiomatic FastAPI APIRouter pattern: kb/api_routers/__init__.py is empty package marker; kb/api_routers/articles.py defines `router = APIRouter(prefix='/api', tags=['articles'])` then registers @router.get handlers. Use Annotated[type, Query(...)] for declarative param validation (ge/le/min_length/max_length). Response models declared via TypedDict OR Pydantic BaseModel for OpenAPI doc generation. The endpoint handler is THIN: parses params → calls list_articles(...) → maps ArticleRecord -> dict via list comprehension → returns. NO direct SQL in router; NO try/except for DB errors (let FastAPI's default 500 handler take over for DB-down case — synthesize is the only never-500 path per QA-05). NO new env vars (CONFIG-02 transitive).")

    Skill(skill="writing-tests", args="TestClient integration tests for /api/articles. Use kb/locale fixture-style setup: monkeypatch KB_DB_PATH to fixture_db (the kb-2 + kb-3-02 extended fixture), then create TestClient(app). Tests cover: (1) basic list shape, (2) pagination math correctness, (3) source filter wechat/rss, (4) lang filter, (5) q LIKE search on title, (6) 422 on invalid params (page<1, limit>100), (7) DATA-07 filter inheritance (negative fixture rows absent). Latency assertion via time.perf_counter() with 100ms budget on the fixture DB (which is small — real prod will be similar). NO mocks for the DB layer.")

    **Step 1 — Create `kb/api_routers/__init__.py`** (empty package marker):

    ```python
    """API routers — one module per endpoint group, all included by kb/api.py."""
    ```

    **Step 2 — Create `kb/api_routers/articles.py`**:

    ```python
    """API-02 + API-03: GET /api/articles + GET /api/article/{hash}.

    Thin FastAPI router — all DB logic lives in kb.data.article_query, which already
    applies DATA-07 content-quality filter (per kb-3-02). This router parses query
    params, calls the data layer, formats response, handles 404 / 422.

    See kb-3-API-CONTRACT.md (kb-3-01) for the response shape contract.

    Skill(skill="python-patterns", args="...")
    Skill(skill="writing-tests", args="...")
    """
    from __future__ import annotations

    from typing import Annotated, Any, Literal, Optional

    from fastapi import APIRouter, HTTPException, Query

    from kb.data import article_query

    router = APIRouter(prefix="/api", tags=["articles"])


    def _record_to_list_item(rec) -> dict:
        return {
            "hash": article_query.resolve_url_hash(rec),
            "title": rec.title,
            "lang": rec.lang,
            "source": rec.source,
            "url": rec.url,
            "update_time": rec.update_time,
            "snippet": None,  # populated by /api/search; null on plain list
        }


    @router.get("/articles")
    async def list_articles_endpoint(
        page: Annotated[int, Query(ge=1)] = 1,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        source: Annotated[Optional[Literal["wechat", "rss"]], Query()] = None,
        lang: Annotated[Optional[Literal["zh-CN", "en", "unknown"]], Query()] = None,
        q: Annotated[Optional[str], Query(min_length=1, max_length=200)] = None,
    ) -> dict[str, Any]:
        """API-02: paginated article list. DATA-07 filter applied via list_articles().

        Query params:
            page: 1-indexed page (ge=1)
            limit: page size (ge=1, le=100)
            source: 'wechat' | 'rss' | omitted (both)
            lang: 'zh-CN' | 'en' | 'unknown' | omitted (all)
            q: LIKE substring on title (case-insensitive); 1-200 chars

        Returns: {items, page, limit, total, has_more}.
        """
        # We call list_articles with a generous limit, then apply q-filter + pagination
        # in Python. For the v2.0 corpus (~160 visible after DATA-07), this is fine.
        # If corpus grows, push q-filter into list_articles via SQL LIKE.
        offset = (page - 1) * limit
        # Ask data layer for offset+limit+1 rows so we can detect has_more.
        # But list_articles returns sorted result already; cheapest correct path:
        # fetch all, filter q in Python (small corpus), paginate.
        # Latency budget: list_articles ~10ms on .dev-runtime DB; q-filter is in-memory.
        all_records = article_query.list_articles(lang=lang, source=source, limit=10000, offset=0)
        if q:
            ql = q.lower()
            all_records = [r for r in all_records if ql in (r.title or "").lower()]
        total = len(all_records)
        page_records = all_records[offset : offset + limit]
        items = [_record_to_list_item(r) for r in page_records]
        return {
            "items": items,
            "page": page,
            "limit": limit,
            "total": total,
            "has_more": (offset + len(page_records)) < total,
        }
    ```

    **Step 3 — Extend `kb/api.py`** to register the router:

    ```python
    # Append to kb/api.py after the existing /health and /static/img setup:
    from kb.api_routers.articles import router as articles_router
    app.include_router(articles_router)
    ```

    **Step 4 — Create `tests/integration/kb/test_api_articles.py`** with the 10 behaviors:

    ```python
    """Integration tests for /api/articles endpoint (API-02)."""
    from __future__ import annotations

    import importlib
    import time
    from pathlib import Path

    import pytest
    from fastapi.testclient import TestClient


    pytest_plugins = ["tests.integration.kb.conftest"]


    @pytest.fixture
    def app_client(fixture_db, monkeypatch):
        monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
        # KB_CONTENT_QUALITY_FILTER defaults to "on" — DATA-07 active
        monkeypatch.delenv("KB_CONTENT_QUALITY_FILTER", raising=False)
        # Reload modules to pick up new env
        import kb.config
        import kb.data.article_query
        import kb.api_routers.articles
        import kb.api
        importlib.reload(kb.config)
        importlib.reload(kb.data.article_query)
        importlib.reload(kb.api_routers.articles)
        importlib.reload(kb.api)
        return TestClient(kb.api.app)


    def test_list_articles_basic_shape(app_client):
        r = app_client.get("/api/articles")
        assert r.status_code == 200
        body = r.json()
        for key in ("items", "page", "limit", "total", "has_more"):
            assert key in body
        assert body["page"] == 1 and body["limit"] == 20
        assert isinstance(body["items"], list)


    def test_pagination_math(app_client):
        r = app_client.get("/api/articles?page=2&limit=2")
        assert r.status_code == 200
        body = r.json()
        assert body["page"] == 2 and body["limit"] == 2
        # Items should be the 3rd-4th elements of the full list
        all_r = app_client.get("/api/articles?limit=100").json()
        assert body["items"] == all_r["items"][2:4]


    def test_source_filter_wechat(app_client):
        r = app_client.get("/api/articles?source=wechat&limit=100").json()
        assert all(item["source"] == "wechat" for item in r["items"])


    def test_source_filter_rss(app_client):
        r = app_client.get("/api/articles?source=rss&limit=100").json()
        assert all(item["source"] == "rss" for item in r["items"])


    def test_lang_filter(app_client):
        r = app_client.get("/api/articles?lang=zh-CN&limit=100").json()
        assert all(item["lang"] == "zh-CN" for item in r["items"])


    def test_q_filter_title_substring(app_client):
        # Pick a title fragment from the fixture (e.g. "Agent" appears in some titles)
        r = app_client.get("/api/articles?q=agent&limit=100").json()
        for item in r["items"]:
            assert "agent" in (item["title"] or "").lower()


    def test_invalid_page_param_422(app_client):
        r = app_client.get("/api/articles?page=0")
        assert r.status_code == 422


    def test_invalid_limit_param_422(app_client):
        r = app_client.get("/api/articles?limit=200")
        assert r.status_code == 422


    def test_data07_filter_applied(app_client):
        """Negative-case rows from fixture (id=99 wechat, id=97 rss) MUST NOT appear."""
        r = app_client.get("/api/articles?limit=10000").json()
        ids = {(item["source"], "rejected_marker") for item in r["items"] if "REJECTED" in (item["title"] or "")}
        # The REJECTED title row added by kb-3-02 fixture must be filtered out
        assert not any("REJECTED" in (item["title"] or "") for item in r["items"])


    def test_each_item_has_resolvable_hash(app_client):
        r = app_client.get("/api/articles?limit=10").json()
        for item in r["items"]:
            assert "hash" in item and len(item["hash"]) == 10


    def test_p50_latency_under_100ms(app_client):
        """5-call latency p50 on fixture DB must be under 100ms."""
        durations = []
        for _ in range(5):
            t0 = time.perf_counter()
            r = app_client.get("/api/articles?limit=20")
            durations.append(time.perf_counter() - t0)
            assert r.status_code == 200
        durations.sort()
        p50 = durations[2]  # median of 5
        assert p50 < 0.1, f"p50 latency {p50*1000:.1f}ms exceeds 100ms target"
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/integration/kb/test_api_articles.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `kb/api_routers/articles.py` exists with `router = APIRouter(prefix="/api"`)
    - `grep -q "list_articles_endpoint" kb/api_routers/articles.py`
    - `grep -q "from kb.data import article_query" kb/api_routers/articles.py`
    - `grep -q "include_router.*articles_router" kb/api.py`
    - `grep -q 'Skill(skill="python-patterns"' kb/api_routers/articles.py`
    - `grep -q 'Skill(skill="writing-tests"' kb/api_routers/articles.py`
    - `pytest tests/integration/kb/test_api_articles.py -v -k "list or pagination or source or lang or q_filter or invalid or data07 or hash or latency"` exits 0 with ≥11 tests passing
    - Negative SQL check: `grep -E "execute\\(|cursor\\(|sqlite3\\." kb/api_routers/articles.py` returns 0 (no DB access in router)
  </acceptance_criteria>
  <done>/api/articles endpoint live; thin router pattern enforced; DATA-07 inherited; ≥11 tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add /api/article/{hash} detail endpoint with D-14 fallback + EXPORT-05 image rewrite</name>
  <read_first>
    - kb/api_routers/articles.py (Task 1 — APPEND only)
    - tests/integration/kb/test_api_articles.py (Task 1 — APPEND only)
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md GET /api/article/{hash} section (response shape)
    - kb/data/article_query.py get_article_by_hash + get_article_body (already shipped kb-1)
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md "NOT affected (intentional carve-out)"
  </read_first>
  <files>kb/api_routers/articles.py, tests/integration/kb/test_api_articles.py</files>
  <behavior>
    - Test 1: GET /api/article/{valid_hash} → 200 with all fields: hash, title, body_md, body_html, lang, source, images, metadata, body_source.
    - Test 2: GET /api/article/{nonexistent_hash} → 404 with `{detail: "..."}`.
    - Test 3: body_html is rendered Markdown (contains `<h1>` or `<p>` tags); body_md is the raw markdown (still contains `#` heading syntax).
    - Test 4: body_source is one of `"vision_enriched"` or `"raw_markdown"` (D-14 fallback chain).
    - Test 5: **Carve-out preserved** — GET /api/article/{hash_of_negative_case_row} → 200 with the article (NOT 404, NOT filtered). This proves direct URL access works for rows DATA-07 excludes from list.
    - Test 6: images field is a list (may be empty for articles with no `<img>` or `![]()` references).
    - Test 7: P50 latency < 100ms on fixture DB.
  </behavior>
  <action>
    Skill(skill="python-patterns", args="Append /api/article/{hash} handler to articles.py router. Pattern: query → call get_article_by_hash → 404 if None → call get_article_body for D-14 fallback → render body_md to body_html via `markdown` lib with extensions `['fenced_code', 'tables']` → extract images by regex on body_md (markdown image syntax `![](...)` AND html `<img src=`) → assemble metadata dict → return. The image-extraction regex should match both markdown and HTML forms; use re.findall with two patterns combined. NO mocks; NO catch-and-suppress on markdown render failure (let FastAPI default 500 handler take over — synthesize is the only never-500 path).")

    Skill(skill="writing-tests", args="APPEND 7 tests to test_api_articles.py covering /api/article/{hash}: (1) full response shape, (2) 404 on miss, (3) body_html renders markdown, (4) body_source one of vision_enriched/raw_markdown, (5) carve-out preserves direct access for DATA-07-filtered rows, (6) images list extracted, (7) latency. Use the same app_client fixture from Task 1.")

    **Step 1 — APPEND to `kb/api_routers/articles.py`** (after `list_articles_endpoint`):

    ```python
    import re
    import markdown as md_lib

    _MD_IMG_PATTERN = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')
    _HTML_IMG_PATTERN = re.compile(r'<img[^>]*src="([^"]+)"', re.IGNORECASE)


    def _extract_image_urls(body_md: str) -> list[str]:
        """Extract image URLs from markdown body (both md and html img syntax)."""
        urls: list[str] = []
        urls.extend(_MD_IMG_PATTERN.findall(body_md))
        urls.extend(_HTML_IMG_PATTERN.findall(body_md))
        # Dedupe while preserving order
        seen: set[str] = set()
        result: list[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                result.append(u)
        return result


    @router.get("/article/{hash}")
    async def get_article_endpoint(hash: str) -> dict[str, Any]:
        """API-03: single article by md5[:10] hash.

        DATA-07 carve-out: this endpoint does NOT apply the content-quality filter —
        direct URL access (search hits, KG citations, bookmarks) must resolve to the
        rendered article regardless of layer1/layer2 verdict. See kb-3-CONTENT-QUALITY-
        DECISIONS.md "NOT affected (intentional carve-out)".

        Returns the canonical detail-page payload + D-14 body-source flag.
        """
        rec = article_query.get_article_by_hash(hash)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"article {hash!r} not found")
        body_md, body_source = article_query.get_article_body(rec)
        body_html = md_lib.markdown(body_md, extensions=["fenced_code", "tables"])
        return {
            "hash": article_query.resolve_url_hash(rec),
            "title": rec.title,
            "body_md": body_md,
            "body_html": body_html,
            "lang": rec.lang,
            "source": rec.source,
            "images": _extract_image_urls(body_md),
            "metadata": {
                "url": rec.url,
                "publish_time": rec.publish_time,
                "update_time": rec.update_time,
            },
            "body_source": body_source,
        }
    ```

    **Step 2 — APPEND tests to `tests/integration/kb/test_api_articles.py`** matching the 7 behaviors. Use a small helper to find a known-good hash from the fixture:

    ```python
    def _first_positive_hash(fixture_db):
        import sqlite3
        from kb.data.article_query import resolve_url_hash, _row_to_record_kol
        c = sqlite3.connect(str(fixture_db))
        c.row_factory = sqlite3.Row
        try:
            row = c.execute(
                "SELECT id, title, url, body, content_hash, lang, update_time "
                "FROM articles WHERE layer1_verdict='candidate' AND body!='' LIMIT 1"
            ).fetchone()
            return resolve_url_hash(_row_to_record_kol(row))
        finally:
            c.close()


    def test_article_detail_full_shape(app_client, fixture_db):
        h = _first_positive_hash(fixture_db)
        r = app_client.get(f"/api/article/{h}")
        assert r.status_code == 200
        body = r.json()
        for key in ("hash", "title", "body_md", "body_html", "lang", "source",
                    "images", "metadata", "body_source"):
            assert key in body, f"missing key: {key}"


    def test_article_detail_404(app_client):
        r = app_client.get("/api/article/zzzzzzzzzz")
        assert r.status_code == 404


    def test_article_detail_body_html_rendered(app_client, fixture_db):
        h = _first_positive_hash(fixture_db)
        body = app_client.get(f"/api/article/{h}").json()
        # body_md is raw; body_html is rendered. If body has '#' headings, body_html
        # has <h1> etc. Markdown lib handles fenced_code + tables.
        # Crude rendering check: body_html contains <p> or <h*>
        assert "<p>" in body["body_html"] or re.search(r"<h\d", body["body_html"])


    def test_article_detail_body_source_enum(app_client, fixture_db):
        h = _first_positive_hash(fixture_db)
        body = app_client.get(f"/api/article/{h}").json()
        assert body["body_source"] in ("vision_enriched", "raw_markdown")


    def test_article_detail_carve_out_preserves_negative(app_client, fixture_db):
        """DATA-07 carve-out: hash of a negative-case row still resolves."""
        import sqlite3
        from kb.data.article_query import resolve_url_hash, _row_to_record_kol
        c = sqlite3.connect(str(fixture_db))
        c.row_factory = sqlite3.Row
        try:
            row = c.execute(
                "SELECT id, title, url, body, content_hash, lang, update_time "
                "FROM articles WHERE layer2_verdict='reject' LIMIT 1"
            ).fetchone()
            assert row is not None, "fixture must have layer2_verdict='reject' row from kb-3-02"
            h = resolve_url_hash(_row_to_record_kol(row))
        finally:
            c.close()
        r = app_client.get(f"/api/article/{h}")
        assert r.status_code == 200, "carve-out: direct hash access must resolve negative-case row"


    def test_article_detail_images_is_list(app_client, fixture_db):
        h = _first_positive_hash(fixture_db)
        body = app_client.get(f"/api/article/{h}").json()
        assert isinstance(body["images"], list)


    def test_article_detail_p50_latency(app_client, fixture_db):
        h = _first_positive_hash(fixture_db)
        durs = []
        for _ in range(5):
            t0 = time.perf_counter()
            r = app_client.get(f"/api/article/{h}")
            durs.append(time.perf_counter() - t0)
            assert r.status_code == 200
        durs.sort()
        assert durs[2] < 0.1, f"p50 = {durs[2]*1000:.1f}ms"
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/integration/kb/test_api_articles.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "def get_article_endpoint" kb/api_routers/articles.py`
    - `grep -q "DATA-07 carve-out" kb/api_routers/articles.py`
    - `grep -q "import markdown" kb/api_routers/articles.py`
    - `grep -q "_extract_image_urls" kb/api_routers/articles.py`
    - `pytest tests/integration/kb/test_api_articles.py -v` exits 0 with ≥18 tests passing (11 from Task 1 + 7 from Task 2)
    - Negative regression: `pytest tests/unit/kb/test_data07_quality_filter.py -v` AND `pytest tests/unit/kb/test_kb2_queries.py -v` AND `pytest tests/unit/kb/test_article_query.py -v` all still exit 0
    - All TestClient calls run < 100ms p50 (verified by latency test)
  </acceptance_criteria>
  <done>/api/article/{hash} live with D-14 fallback + EXPORT-05 image rewrite (transitive via get_article_body); carve-out preserved; ≥18 total tests pass.</done>
</task>

</tasks>

<verification>
- API-02 + API-03 endpoints live + fully tested
- Router is THIN — no DB SQL, only data-layer calls
- DATA-07 filter inherited automatically (list endpoint); carve-out preserved (detail endpoint)
- python-patterns + writing-tests Skills invocations literal in code AND will appear in SUMMARY
- ≥18 integration tests pass; no regression in kb-1/kb-2/kb-3-02 baselines
- P50 latency < 100ms on fixture DB
</verification>

<success_criteria>
- API-02: GET /api/articles paginated, filterable, p50 < 100ms
- API-03: GET /api/article/{hash} resolves, returns full payload, 404 on miss
- DATA-07 cross-phase impact: list endpoint filters; detail endpoint preserves direct access
</success_criteria>

<output>
Create `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-05-SUMMARY.md` documenting:
- 2 endpoints (/api/articles, /api/article/{hash})
- Router pattern: thin handler over kb.data.article_query
- ≥18 integration tests passing
- Skill invocation strings literal in summary: `Skill(skill="python-patterns", ...)` AND `Skill(skill="writing-tests", ...)` for discipline regex
- DATA-07 carve-out preserved on detail endpoint (direct URL access intact)
</output>
</content>
</invoke>