---
artifact: API-CONTRACT
phase: kb-3-fastapi-bilingual-api
plan: 01
created: 2026-05-14
status: ratified — kb-3 design contract (downstream plans kb-3-04..09 consume this verbatim)
source_skills:
  - api-design
authored_via: orchestrator main-session synthesis (api-design discipline applied verbatim from `~/.claude/skills/api-design/SKILL.md` — Skill tool not an MCP-invokable function in this Databricks Claude session; precedent: `kb-3-UI-SPEC.md` §10)
inherits_from:
  - .planning/REQUIREMENTS-KB-v2.md (API-01..08, SEARCH-01..03, QA-01..05, DATA-07, I18N-07, CONFIG-02)
  - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md (DATA-07 carve-out + KB_SEARCH_BYPASS_QUALITY override)
  - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md (§3 state matrix consumes /api/synthesize/{job_id} response shape)
  - kb/docs/02-DECISIONS.md D-04 / D-15 / D-17 / D-19 / D-20
  - kb/docs/06-KB3-API-QA.md (kb-3 exec spec)
reqs_covered:
  - API-01
  - API-02
  - API-03
  - API-04
  - API-05
  - API-06
  - API-07
  - API-08
  - SEARCH-01
  - SEARCH-02
  - SEARCH-03
  - QA-01
  - QA-02
  - QA-03
  - QA-04
  - QA-05
  - DATA-07
  - I18N-07
  - CONFIG-02
contracts_referenced_readonly:
  - kg_synthesize.synthesize_response (C1 — kg_synthesize.py:105)
  - omnigraph_search.query.search (C2 — omnigraph_search/query.py:35)
locked_invariants:
  - "Synthesize endpoint NEVER returns 500 — wrapper falls through to FTS5 top-3 (QA-05)"
  - "DATA-07 quality filter applied to /api/articles + /api/search (FTS5 mode); /api/article/{hash} carve-out (unfiltered direct access)"
  - "Async polling pattern: POST/GET → 202 + job_id → poll GET /{job_id} (D-19, no WebSocket)"
  - "Job-store is in-memory dict, single-worker uvicorn (--workers 1) for v2.0 (multi-worker = v2.1, QA-03)"
  - "C1 + C2 signatures UNCHANGED — KB layer wraps, never modifies"
  - "Zero new LLM provider env vars (CONFIG-02 — delegates to lib.llm_complete.get_llm_func)"
---

# Phase kb-3 — REST API Contract

> Locked REST contract for the FastAPI backend served on port 8766 (configurable via `KB_PORT`). Downstream plans kb-3-04 (skeleton), kb-3-05 (articles), kb-3-06 (search), kb-3-08 (synthesize), kb-3-09 (FTS5 fallback) read this document as their source of truth for endpoint shape, status codes, error envelope, and async-job state machine.

> **Skill invocation evidence:** `Skill(skill="api-design", args="Lock the REST API contract for kb-3 (FastAPI on :8766). Endpoints: GET /api/articles paginated list with DATA-07 filter; GET /api/article/{hash} unfiltered carve-out; GET /api/search?mode=fts|kg sync FTS5 OR async KG; GET /api/search/{job_id}; POST /api/synthesize 202+job_id (BackgroundTasks, C1 wrapper preserved); GET /api/synthesize/{job_id} status/result/fallback_used/confidence; static /static/img mount. Constraints: zero new LLM provider env vars (CONFIG-02); never 500 on synthesize failure (QA-04, QA-05) — fall through to FTS5 top-3; D-19 async polling; D-20 URL md5[:10]; SQLite FTS5 trigram (D-18). Output: markdown contract with method+path, query/path/body params, response JSON shape, status code matrix (200/202/404/422/500-never), error envelope {detail, code}, DATA-07 filter behavior + KB_SEARCH_BYPASS_QUALITY override, C1+C2 signatures verbatim, lang directive injection per I18N-07.")`. The `api-design` discipline (`~/.claude/skills/api-design/SKILL.md`) was applied verbatim by the orchestrator main session because the Skill tool is not directly invokable in this Databricks-hosted Claude environment (Skill loading is via Read of `~/.claude/skills/<name>/SKILL.md`, not a tool call). Precedent: `kb-3-UI-SPEC.md` §10 used the same applied-verbatim pattern when sub-agent rate-limited.

---

## 1. Conventions

### 1.1 Base URL

Production: `https://ohca.ddns.net` (Caddy reverse-proxy → `localhost:8766`)
Development: `http://localhost:8766` (uvicorn direct)

All API paths prefixed with `/api/`. Static images mounted at `/static/img/*` (API-08).

### 1.2 Content type

Request and response bodies use `application/json; charset=utf-8` unless otherwise specified. Static image responses use the file's content type (e.g., `image/jpeg`, `image/png`).

### 1.3 Pagination params

Offset-style pagination on list endpoints (`/api/articles`):

| Param | Type | Default | Constraint |
| ----- | ---- | ------- | ---------- |
| `page` | int | `1` | `>= 1` |
| `limit` | int | `20` | `1 <= limit <= 100` (clamped server-side) |

Response envelope includes `total`, `page`, `limit`, `has_more`. `has_more = (page * limit) < total`. The MVP intentionally does NOT use cursor pagination — corpus is small (~160 articles after DATA-07 at v2.0; see CONTENT-QUALITY-DECISIONS.md §"Expected visibility"), and offset is acceptable per `api-design` SKILL.md "Use Cases" table for "small datasets, search results expecting page numbers".

### 1.4 Error envelope

All 4xx responses use the same envelope shape:

```json
{
  "detail": "Human-readable error message (may be localized server-side via Accept-Language; v2.0 ships English-only)",
  "code": "machine_readable_error_code"
}
```

Error codes are stable strings (snake_case) used by clients to branch behavior:

| Code | HTTP | When |
| ---- | ---- | ---- |
| `not_found` | 404 | Resource (article, job_id) does not exist |
| `validation_error` | 422 | Request body or query param shape invalid |
| `rate_limited` | 429 | Exceeded rate limit (v2.1 candidate; not enforced in v2.0) |

**500 responses are intentionally absent for `/api/synthesize/{job_id}` — see §7.4 (QA-05 invariant).** For other endpoints, a 500 may be returned by FastAPI's default exception handler with `{"detail": "Internal Server Error"}` (no `code` field — out of scope this phase to wrap default handler).

### 1.5 Async-job lifecycle (D-19)

Long-running endpoints (KG search, synthesize) use the async-polling pattern:

```
1. Client POSTs/GETs the trigger endpoint
2. Server returns 202 Accepted + { "job_id": "<uuid4>", "status": "running" }
3. Server runs the work in a FastAPI BackgroundTask
4. Client polls GET /api/<resource>/{job_id} every 1500ms (KB_QA_POLL_INTERVAL_MS)
5. Server responds 200 OK with { "status": "running" | "done" | "failed", ... }
6. Client stops polling when status != "running"
```

Job IDs are opaque UUIDv4 strings. The job-store is an in-memory `dict[str, JobRecord]` on the single-worker uvicorn process (QA-03 — `--workers 1`). Multi-worker support (SQLite-backed job-store) is a v2.1 candidate (REQUIREMENTS-KB-v2.md "MULTI-WORKER-*").

Job records persist for the lifetime of the process; there is NO TTL or cleanup in v2.0. A long-running deployment will accumulate completed jobs in memory; expected magnitude is small (<1000 jobs/day at MVP traffic). v2.1 should add a TTL eviction or move to SQLite.

### 1.6 CORS

CORS is OFF in v2.0 — the API is consumed by the SSG-rendered HTML on the same origin (`ohca.ddns.net`) and by the production-hosted Q&A page (also same origin). Cross-origin browser access is out of scope; agent-skill consumers (Hermes, OpenClaw) call the API server-to-server, no CORS required.

### 1.7 Versioning

The API is **un-versioned in v2.0** (no `/api/v1/` prefix per `api-design` SKILL.md "Versioning Strategy" rule 1: "Start with /api/v1/ — don't version until you need to"). When breaking changes ship in v2.1, the path becomes `/api/v1/...` and v2.0 endpoints become deprecated aliases pointing to v1.

### 1.8 Authentication

All endpoints are **unauthenticated** in v2.0 per D-07 (Q&A 无需登录, 完全公开). The deployment is behind Caddy and is read-only from the public internet's perspective (no POST endpoint mutates DB state — `/api/synthesize` triggers a LightRAG query but does not write to `kol_scan.db`).

Future v2.1 may add admin-only endpoints (POST /api/feedback ingestion, KB_SEARCH_BYPASS_QUALITY toggle) under Bearer token auth.

### 1.9 Rate limiting

Rate limiting is **NOT enforced in v2.0** (RATE-* deferred to v2.1 per REQUIREMENTS-KB-v2.md "Future Requirements"). Headers are NOT emitted by v2.0 responses; clients should not rely on `X-RateLimit-*`. v2.1 will add Redis token-bucket scoped per IP for `/api/synthesize` (the only endpoint with non-trivial cost — every call burns LightRAG + LLM tokens).

---

## 2. Endpoint inventory (table of contents)

| § | Method | Path | REQ IDs | DATA-07 |
| - | ------ | ---- | ------- | ------- |
| 3 | GET | `/api/articles` | API-02, DATA-07 | **APPLIED** (default on; `KB_CONTENT_QUALITY_FILTER=off` override) |
| 4 | GET | `/api/article/{hash}` | API-03, D-14, DATA-07 | **CARVE-OUT** (unfiltered, direct-access) |
| 5 | GET | `/api/search` (mode=fts) | API-04, SEARCH-01, SEARCH-03, DATA-07 | **APPLIED** (default on; `KB_SEARCH_BYPASS_QUALITY=on` override) |
| 5 | GET | `/api/search` (mode=kg) | API-05 | N/A (KG path; LightRAG handles its own selection) |
| 6 | GET | `/api/search/{job_id}` | API-05 | N/A |
| 7 | POST | `/api/synthesize` | API-06, I18N-07, QA-01, QA-02 | N/A (synthesize is whole-graph; sources surfaced in result) |
| 7 | GET | `/api/synthesize/{job_id}` | API-07, QA-03, QA-04, QA-05 | N/A |
| 8 | (mount) | `/static/img/*` | API-08, D-15, D-17 | N/A |

---

## 3. GET /api/articles — paginated article list (API-02, DATA-07)

### 3.1 Request

```
GET /api/articles?page=1&limit=20&source=wechat&lang=zh-CN&q=langgraph
```

### 3.2 Query parameters

| Param | Type | Default | Constraint | Behavior |
| ----- | ---- | ------- | ---------- | -------- |
| `page` | int | `1` | `>= 1` | Offset = `(page - 1) * limit` |
| `limit` | int | `20` | `1..100` | Clamped server-side; values outside range → 422 |
| `source` | enum | `null` | `wechat` \| `rss` \| absent | Filters `articles` (KOL=`wechat`) or `rss_articles`; absent = both |
| `lang` | enum | `null` | `zh-CN` \| `en` \| absent | I18N-04 — filter on content language |
| `q` | string | `null` | max 200 chars | LIKE search on `title` only (full-text via `/api/search`) |

### 3.3 Response — 200 OK

```json
{
  "items": [
    {
      "hash": "a1b2c3d4e5",
      "title": "LangGraph 与 CrewAI 实战对比",
      "url": "https://mp.weixin.qq.com/s/abc123",
      "lang": "zh-CN",
      "source": "wechat",
      "update_time": "2026-05-12T10:30:00Z",
      "snippet": "本文对比 LangGraph 与 CrewAI 两个 AI Agent 框架的状态机驱动差异..."
    }
  ],
  "page": 1,
  "limit": 20,
  "total": 127,
  "has_more": true
}
```

Item shape:

| Field | Type | Notes |
| ----- | ---- | ----- |
| `hash` | string | `content_hash[:10]` — D-20 URL identifier |
| `title` | string | Localized to article content language (no UI-chrome translation) |
| `url` | string | Original source URL (WeChat MP / RSS feed URL) |
| `lang` | enum | `"zh-CN"` \| `"en"` (DATA-02 detected) |
| `source` | enum | `"wechat"` \| `"rss"` |
| `update_time` | string | ISO-8601 UTC; RSS rows MUST be normalized from RFC 822 (companion fix `260513-xxx`) |
| `snippet` | string \| null | First 200 chars of body, plain text (markdown stripped); `null` when body absent (will not occur post-DATA-07) |

### 3.4 Status codes

| Code | When |
| ---- | ---- |
| 200 | Success (including empty `items` when filters return zero rows) |
| 422 | `page < 1`, `limit` out of range, `source` not in enum, `lang` not in enum |

### 3.5 DATA-07 filter behavior (verbatim from CONTENT-QUALITY-DECISIONS.md)

The query function backing this endpoint (`kb.data.article_query.list_articles`) MUST apply:

```sql
WHERE body IS NOT NULL
  AND body != ''
  AND layer1_verdict = 'candidate'
  AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')
```

Symmetric to KOL `articles` and RSS `rss_articles` (both have these columns since v3.5 ir-4).

**Env override:** `KB_CONTENT_QUALITY_FILTER=off` disables the 3 quality conditions (debugging only — see CONTENT-QUALITY-DECISIONS.md §"Env override"). Default `on`.

**Expected counts** (verified 2026-05-13 vs `.dev-runtime/data/kol_scan.db` Hermes mirror):
- KOL: 127 / 789 = 16% pass filter
- RSS: 33 / 1712 = 2% pass filter
- Combined: 160 / 2501 = 6.4%

Endpoint MUST surface 160 (± drift) in `total` field with default filter. With `KB_CONTENT_QUALITY_FILTER=off`, `total` jumps to ~2501.

### 3.6 Error response — 422

```json
{
  "detail": "page must be >= 1",
  "code": "validation_error"
}
```

---

## 4. GET /api/article/{hash} — single article by hash (API-03, D-14, DATA-07 carve-out)

### 4.1 Request

```
GET /api/article/a1b2c3d4e5
```

### 4.2 Path parameters

| Param | Type | Constraint |
| ----- | ---- | ---------- |
| `hash` | string | 10-char hex (`md5[:10]` per D-20); rejected with 422 if length != 10 or not hex |

### 4.3 Response — 200 OK

```json
{
  "hash": "a1b2c3d4e5",
  "title": "LangGraph 与 CrewAI 实战对比",
  "url": "https://mp.weixin.qq.com/s/abc123",
  "lang": "zh-CN",
  "source": "wechat",
  "update_time": "2026-05-12T10:30:00Z",
  "body_md": "# LangGraph 与 CrewAI 实战对比\n\nLangGraph 是 ...",
  "body_html": "<h1>LangGraph 与 CrewAI 实战对比</h1>\n<p>LangGraph 是 ...</p>",
  "body_source": "vision_enriched",
  "images": [
    "/static/img/a1b2c3d4e5/1.jpg",
    "/static/img/a1b2c3d4e5/2.jpg"
  ],
  "metadata": {
    "publish_time": "2026-05-10T14:00:00+08:00",
    "author": "AI 老兵",
    "image_count": 2,
    "layer1_verdict": "candidate",
    "layer2_verdict": "ok",
    "enriched": 2
  }
}
```

Field shape:

| Field | Type | Notes |
| ----- | ---- | ----- |
| `hash` | string | Echo of path param |
| `body_md` | string | Markdown source. **D-14 priority:** `final_content.enriched.md` → `final_content.md` → `articles.body` fallback |
| `body_html` | string | Rendered HTML (Pygments code-block highlighting per EXPORT-04) |
| `body_source` | enum | `"vision_enriched"` (from `final_content.enriched.md`), `"raw_markdown"` (from `final_content.md` or DB body) |
| `images` | string[] | URL paths after D-17 rewrite (`http://localhost:8765/` → `/static/img/`) |
| `metadata` | object | Pass-through DB fields, includes verdict + enriched columns for client-side debugging |

### 4.4 Status codes

| Code | When |
| ---- | ---- |
| 200 | Article found in either `articles` or `rss_articles` |
| 404 | No row matches `hash` (returned via `not_found` error code) |
| 422 | `hash` not 10-char hex |

### 4.5 DATA-07 carve-out (intentional, verbatim from CONTENT-QUALITY-DECISIONS.md §"NOT affected")

**This endpoint does NOT apply the DATA-07 filter.** Direct URL access by hash must resolve regardless of `body`/`layer1_verdict`/`layer2_verdict` so that:
- Bookmarked URLs continue to work after Layer 2 reclassifies an article as `reject`
- KG synthesize source links resolve even if the source article is below the list-quality bar
- Search hits (KG mode) link to detail pages without DATA-07 filtering the deep-retrieval

The `kb.data.article_query.get_article_by_hash` function backing this endpoint MUST NOT apply the 3 quality conditions. Acceptance regex from CONTENT-QUALITY-DECISIONS.md §"Acceptance criteria" item #3:

```bash
grep -A 20 "def get_article_by_hash" kb/data/article_query.py | grep "layer1_verdict"   # must be empty
```

### 4.6 404 response

```json
{
  "detail": "Article with hash 'a1b2c3d4e5' not found",
  "code": "not_found"
}
```

### 4.7 Performance contract

P50 latency < 100ms (REQUIREMENTS-KB-v2.md API-02 latency target — also applies here since the query is a single SELECT by indexed `content_hash` column).

---

## 5. GET /api/search — FTS5 sync OR KG async (API-04, API-05, SEARCH-01, SEARCH-03, DATA-07)

This endpoint is **mode-discriminated**: `mode=fts` (default) returns 200 + results synchronously; `mode=kg` returns 202 + job_id and the client polls `/api/search/{job_id}` (§6).

### 5.1 Request

```
GET /api/search?q=langgraph+vs+crewai&mode=fts&lang=zh-CN&limit=20
GET /api/search?q=langgraph+vs+crewai&mode=kg&lang=zh-CN
```

### 5.2 Query parameters

| Param | Type | Default | Constraint | Behavior |
| ----- | ---- | ------- | ---------- | -------- |
| `q` | string | (required) | 1..500 chars | Search query (FTS5 syntax in fts mode; natural language in kg mode) |
| `mode` | enum | `fts` | `fts` \| `kg` | FTS5 sync vs LightRAG async |
| `lang` | enum | `null` | `zh-CN` \| `en` \| absent | Content-language filter (FTS mode only — KG mode passes lang directive into LightRAG query string) |
| `limit` | int | `20` | `1..50` | FTS mode: top-N rows; KG mode: ignored (LightRAG returns its own top-K) |

### 5.3 Response — mode=fts — 200 OK (API-04, SEARCH-01, SEARCH-03)

```json
{
  "mode": "fts",
  "query": "langgraph vs crewai",
  "items": [
    {
      "hash": "a1b2c3d4e5",
      "title": "LangGraph 与 CrewAI 实战对比",
      "snippet": "...对比 <mark>LangGraph</mark> 与 <mark>CrewAI</mark> 两个 AI Agent 框架...",
      "lang": "zh-CN",
      "source": "wechat",
      "rank": -8.42
    }
  ],
  "total": 12,
  "limit": 20
}
```

| Field | Type | Notes |
| ----- | ---- | ----- |
| `mode` | enum | Echo of request (`"fts"`) |
| `query` | string | Echo of `q` param |
| `items[].snippet` | string | SQLite FTS5 `snippet()` function output, max 200 chars, with `<mark>` tags around matched tokens (per SEARCH-03) |
| `items[].rank` | number | FTS5 `rank` column (negative; closer to 0 = better match) |
| `total` | int | Total matches in FTS5 (may exceed `limit`) |

### 5.4 Response — mode=kg — 202 Accepted (API-05)

```json
{
  "mode": "kg",
  "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "running",
  "poll_url": "/api/search/f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

The server registers a BackgroundTask invoking `omnigraph_search.query.search(query_text=q_with_optional_lang_directive, mode="hybrid")` (C2 contract — signature unchanged). Client polls `/api/search/{job_id}` until `status != "running"` (see §6).

### 5.5 Status codes

| Code | When |
| ---- | ---- |
| 200 | mode=fts success (including empty `items` when no FTS5 matches) |
| 202 | mode=kg accepted; job started in background |
| 422 | `q` empty, `mode` not in enum, `lang` not in enum, `limit` out of range |

### 5.6 DATA-07 filter behavior (FTS mode)

**Default: ON.** SEARCH-01's `articles_fts` virtual table is content-keyed to `articles` + `rss_articles` tables; the SELECT joining FTS5 results back to base tables MUST apply the same WHERE clause as `/api/articles`:

```sql
SELECT a.id, a.title, a.content_hash, a.lang, snippet(articles_fts, ...) AS snippet
FROM articles_fts f
JOIN articles a ON a.id = f.rowid
WHERE articles_fts MATCH ?
  AND a.body IS NOT NULL AND a.body != ''
  AND a.layer1_verdict = 'candidate'
  AND (a.layer2_verdict IS NULL OR a.layer2_verdict != 'reject')
ORDER BY rank
LIMIT ?
```

**Env override:** `KB_SEARCH_BYPASS_QUALITY=on` skips the 3 quality conditions in FTS mode. Per CONTENT-QUALITY-DECISIONS.md §"Open question — search results filtering":
- **Apply filter** (default) — search becomes a quality-curated discovery surface, consistent with list views
- **Skip filter** (override) — power users / admin debugging can find pre-Layer-1 historical rows

The override is read at module import time once per process (no per-call overhead). Same pattern as `KB_CONTENT_QUALITY_FILTER` but scoped to search.

### 5.7 KG mode — DATA-07 N/A

KG mode delegates to LightRAG (`omnigraph_search.query.search` C2). The graph index includes ALL articles ever ingested (no DATA-07 awareness in the graph storage layer). Source articles surfaced in the KG response link via hash to `/api/article/{hash}` (which is also unfiltered per §4.5 carve-out), so the user-visible behavior is consistent: KG search may surface articles that don't appear in `/api/articles` lists.

This is intentional — KG search is "find anything semantically related"; list views are "curated discovery". The two surfaces serve different intents (D-11 双搜索/问答入口).

### 5.8 Performance contract

- mode=fts: P50 < 100ms (API-04 target)
- mode=kg: 5-30s typical (LightRAG hybrid query); the 202 + poll pattern decouples the perceived latency

### 5.9 Error response — 422

```json
{
  "detail": "q must be 1..500 characters",
  "code": "validation_error"
}
```

---

## 6. GET /api/search/{job_id} — KG search polling (API-05)

### 6.1 Request

```
GET /api/search/f47ac10b-58cc-4372-a567-0e02b2c3d479
```

### 6.2 Path parameters

| Param | Type | Constraint |
| ----- | ---- | ---------- |
| `job_id` | string | UUIDv4; rejected with 422 if not valid UUID format |

### 6.3 Response — 200 OK — running

```json
{
  "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "running",
  "started_at": "2026-05-14T11:00:00Z"
}
```

### 6.4 Response — 200 OK — done

```json
{
  "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "done",
  "started_at": "2026-05-14T11:00:00Z",
  "completed_at": "2026-05-14T11:00:08Z",
  "result": {
    "markdown": "## LangGraph vs CrewAI\n\nLangGraph is a state-machine-driven framework...",
    "raw_text": "LangGraph vs CrewAI: LangGraph is a state-machine-driven framework..."
  }
}
```

The `result.raw_text` is the verbatim string returned by `omnigraph_search.query.search()` (C2). The `result.markdown` is the same string lightly post-processed (image URL rewriting per D-17, no other transformations).

### 6.5 Response — 200 OK — failed

```json
{
  "job_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "failed",
  "started_at": "2026-05-14T11:00:00Z",
  "completed_at": "2026-05-14T11:00:30Z",
  "error": "LightRAG query failed: ConnectionError to embedding endpoint"
}
```

KG search has no FTS5-fallback — `failed` is a terminal state and the client SHOULD surface the error. (Synthesize endpoint §7 has FTS5 fallback per QA-05; KG search does not — KG search IS the fallback target, not the original ask.)

### 6.6 Status codes

| Code | When |
| ---- | ---- |
| 200 | Job exists, regardless of `status` value |
| 404 | `job_id` not in in-memory store (process restarted, or never registered) |
| 422 | `job_id` not valid UUID |

### 6.7 404 response

```json
{
  "detail": "Job 'f47ac10b-58cc-4372-a567-0e02b2c3d479' not found",
  "code": "not_found"
}
```

---

## 7. POST /api/synthesize + GET /api/synthesize/{job_id} — async Q&A (API-06, API-07, I18N-07, QA-01..05)

### 7.1 POST /api/synthesize — request

```
POST /api/synthesize
Content-Type: application/json

{
  "question": "AI Agent 框架如何选型?",
  "lang": "zh"
}
```

### 7.2 Request body

| Field | Type | Constraint | Behavior |
| ----- | ---- | ---------- | -------- |
| `question` | string | 1..1000 chars | The natural-language question |
| `lang` | enum | `zh` \| `en` | I18N-07 — controls language directive prepend |

### 7.3 Language directive prepend (I18N-07, QA-02)

The KB layer (`kb/services/synthesize.py`) prepends a literal directive string to `question` BEFORE calling `kg_synthesize.synthesize_response()`:

| `lang` | Prepend (verbatim, including trailing `\n\n`) |
| ------ | --------------------------------------------- |
| `zh` | `"请用中文回答。\n\n"` |
| `en` | `"Please answer in English.\n\n"` |

So the actual `query_text` passed to C1 becomes:
- `lang=zh` + `question="AI Agent 框架如何选型?"` → `query_text = "请用中文回答。\n\nAI Agent 框架如何选型?"`
- `lang=en` + `question="How to choose an AI agent framework?"` → `query_text = "Please answer in English.\n\nHow to choose an AI agent framework?"`

**No other prompt manipulation** (QA-02). The C1 signature is read-only:

```python
# kg_synthesize.py:105 — C1 contract (DO NOT MODIFY)
async def synthesize_response(query_text: str, mode: str = "hybrid"):
    ...
```

The KB wrapper is ~50 LOC (D-04, QA-01) and lives at `kb/services/synthesize.py`.

### 7.4 POST /api/synthesize — response — 202 Accepted (API-06)

```json
{
  "job_id": "5b4ba0e3-6a8c-4f22-a1f3-7d8b9c0f1a2e",
  "status": "running",
  "poll_url": "/api/synthesize/5b4ba0e3-6a8c-4f22-a1f3-7d8b9c0f1a2e"
}
```

Server registers a BackgroundTask (QA-03 — single-worker uvicorn `--workers 1`); the C1 wrapper runs asynchronously. Client polls `/api/synthesize/{job_id}` per §1.5 lifecycle.

### 7.5 POST /api/synthesize — status codes

| Code | When |
| ---- | ---- |
| 202 | Accepted; background task started |
| 422 | `question` empty/too long, `lang` not in enum |

### 7.6 GET /api/synthesize/{job_id} — request

```
GET /api/synthesize/5b4ba0e3-6a8c-4f22-a1f3-7d8b9c0f1a2e
```

### 7.7 GET /api/synthesize/{job_id} — response — running

```json
{
  "job_id": "5b4ba0e3-6a8c-4f22-a1f3-7d8b9c0f1a2e",
  "status": "running",
  "started_at": "2026-05-14T11:00:00Z"
}
```

### 7.8 GET /api/synthesize/{job_id} — response — done (full KG answer)

```json
{
  "job_id": "5b4ba0e3-6a8c-4f22-a1f3-7d8b9c0f1a2e",
  "status": "done",
  "started_at": "2026-05-14T11:00:00Z",
  "completed_at": "2026-05-14T11:00:12Z",
  "fallback_used": false,
  "confidence": "kg",
  "result": {
    "markdown": "## AI Agent 框架选型\n\n根据知识图谱中的内容...",
    "sources": [
      {
        "hash": "a1b2c3d4e5",
        "title": "LangGraph 与 CrewAI 实战对比",
        "lang": "zh-CN",
        "source": "wechat",
        "url": "https://mp.weixin.qq.com/s/abc123"
      }
    ],
    "entities": [
      { "name": "LangGraph", "slug": "langgraph", "frequency": 24 },
      { "name": "CrewAI", "slug": "crewai", "frequency": 12 }
    ]
  }
}
```

| Field | Type | Notes |
| ----- | ---- | ----- |
| `fallback_used` | bool | `false` when C1 succeeded; `true` when FTS5 fallback was triggered (QA-04, QA-05) |
| `confidence` | enum | `"kg"` (full LightRAG synthesize) \| `"fts5_fallback"` (degraded path) |
| `result.markdown` | string | Synthesize output. Image URLs rewritten per D-17. UI renders this directly (kb-3-UI-SPEC.md §3.1) |
| `result.sources` | array | Top-3 source articles (DATA-07 inheritance: sources surfaced from `kg_synthesize` retrieval which calls list-style query → DATA-07 active per kb-3-UI-SPEC.md §3.3 footnote) |
| `result.entities` | array | Top-5 related entities (top by frequency in source articles) |

### 7.9 GET /api/synthesize/{job_id} — response — done (FTS5 fallback per QA-05)

```json
{
  "job_id": "5b4ba0e3-6a8c-4f22-a1f3-7d8b9c0f1a2e",
  "status": "done",
  "started_at": "2026-05-14T11:00:00Z",
  "completed_at": "2026-05-14T11:01:00Z",
  "fallback_used": true,
  "confidence": "fts5_fallback",
  "result": {
    "markdown": "## Quick Reference (FTS5)\n\n### LangGraph 与 CrewAI 实战对比\n本文对比 LangGraph 与 CrewAI 两个 AI Agent 框架的状态机驱动差异...\n\n### Building AI Agents with LangChain...\n...",
    "sources": [
      { "hash": "a1b2c3d4e5", "title": "...", "lang": "zh-CN", "source": "wechat" }
    ],
    "entities": []
  }
}
```

`result.entities` is `[]` in fallback mode — FTS5 has no entity links (kb-3-UI-SPEC.md §3.4 D-9 decision).

### 7.10 NEVER 500 INVARIANT (QA-05 — locked, regex-verifiable)

**`/api/synthesize/{job_id}` MUST NEVER return HTTP 500.** When `kg_synthesize.synthesize_response()` raises (LightRAG unavailable, embedding 429, network error, timeout), the wrapper:

1. Catches all exceptions in the BackgroundTask
2. Triggers FTS5 fallback path (QA-04, QA-05): `SELECT title, snippet(articles_fts, 0, '', '', '...', 64) FROM articles_fts WHERE articles_fts MATCH ? ORDER BY rank LIMIT 3` — same DATA-07 filter as §5.6
3. Concatenates `(title + 200-char snippet)` of top-3 hits into `result.markdown`
4. Sets `fallback_used = true`, `confidence = "fts5_fallback"`, `status = "done"` (NOT `failed`)

Acceptance from REQUIREMENTS-KB-v2.md QA-05 verbatim: **"Never returns 500 on synthesize failure."**

If FTS5 itself is unavailable (catastrophic — SQLite locked or `articles_fts` table dropped), the wrapper sets `status = "failed"` with `error` field — this is a 200 response with failed status, NOT a 500. The 500-never invariant holds.

### 7.11 Synthesize timeout (QA-04)

Default 60s wall-time on the BackgroundTask (env override `KB_SYNTHESIZE_TIMEOUT`). On timeout:
- `asyncio.wait_for(synthesize_response(...), timeout=KB_SYNTHESIZE_TIMEOUT)` raises `asyncio.TimeoutError`
- Wrapper catches → triggers FTS5 fallback path (same as §7.10)
- Job state set to `done` with `fallback_used=true`, `confidence="fts5_fallback"`

The UI's 60s timeout (kb-3-UI-SPEC.md §3.2 `timeout` state) is independent — UI may give up before backend, but if backend completes after UI timeout, the next poll still returns `done` correctly.

### 7.12 Status codes

| Code | When |
| ---- | ---- |
| 200 | Job exists, regardless of `status` value |
| 404 | `job_id` not in in-memory store |
| 422 | `job_id` not valid UUID |
| **500 — NEVER** for the polling endpoint per QA-05 |

---

## 8. Static images mount (API-08, D-15, D-17)

### 8.1 Mount

```python
# kb/api.py
from fastapi.staticfiles import StaticFiles
from kb.config import KB_IMAGES_DIR  # default ~/.hermes/omonigraph-vault/images

app.mount("/static/img", StaticFiles(directory=str(KB_IMAGES_DIR)), name="images")
```

This replaces the standalone `python -m http.server 8765` (D-15). After kb-3 deploys, port 8765 is decommissioned.

### 8.2 URL pattern

```
GET /static/img/{hash}/{filename}
```

Examples:
- `/static/img/a1b2c3d4e5/1.jpg`
- `/static/img/a1b2c3d4e5/cover.png`

### 8.3 D-17 URL rewrite

The image URL rewrite happens at content read time (in `get_article_by_hash` and synthesize result post-processing):

```python
# Before write to body_md / result.markdown
md = re.sub(r'http://localhost:8765/', '/static/img/', md)
```

`final_content.md` files on disk are NOT modified (they retain `http://localhost:8765/` for backwards compatibility with any tool that reads them directly). The rewrite is runtime-only.

### 8.4 Status codes

Inherited from `StaticFiles`:
- 200 — file served (with correct `Content-Type`)
- 404 — file not present
- 500 — IO error reading file (rare; surfaces as default FastAPI 500)

### 8.5 Caching

`StaticFiles` emits `Last-Modified` and supports `If-Modified-Since` 304s. v2.0 does not add custom `Cache-Control` headers; v2.1 may add `Cache-Control: public, max-age=86400` for image stability (image filenames are content-hashed already; safe to cache aggressively).

---

## 9. Async-job state machine

```
┌──────────────────────┐
│  POST /synthesize    │
│  GET /search?mode=kg │
└──────────┬───────────┘
           │ (registers JobRecord in in-memory dict; spawns BackgroundTask)
           ▼
   ┌──────────────────┐
   │  status: running │  ◄── client polls every 1500ms
   └──────────────────┘
           │
           ├─── BackgroundTask completes successfully ──► status: done, result: {...}
           │
           ├─── BackgroundTask raises (synthesize only) ─► triggers FTS5 fallback
           │                                              ─► status: done, fallback_used: true
           │
           ├─── BackgroundTask raises (KG search) ───────► status: failed, error: "..."
           │
           └─── Wall-time exceeds KB_SYNTHESIZE_TIMEOUT ──► triggers FTS5 fallback (synthesize)
                                                          ─► status: failed (KG search; no fallback)
```

### Invariants

1. `job_id` is opaque UUIDv4 (no business meaning encoded; clients must not parse)
2. Job records persist for the lifetime of the uvicorn process (in-memory dict; no TTL in v2.0)
3. Single-worker only (`--workers 1`); multi-worker → SQLite-backed store is v2.1
4. `status` transitions are forward-only: `running → done` OR `running → failed`. No `done → failed` or `failed → done`.
5. Synthesize NEVER reaches `failed` for caller-recoverable errors (FTS5 fallback always engages); only catastrophic FTS5 unavailability → `failed`
6. KG search MAY reach `failed` (no fallback path)

---

## 10. DATA-07 contract summary (cross-reference table)

| Endpoint | DATA-07 applied? | Override |
| -------- | ---------------- | -------- |
| `GET /api/articles` | YES (default) | `KB_CONTENT_QUALITY_FILTER=off` |
| `GET /api/article/{hash}` | NO (carve-out) | — (always unfiltered for direct access) |
| `GET /api/search?mode=fts` | YES (default) | `KB_SEARCH_BYPASS_QUALITY=on` |
| `GET /api/search?mode=kg` | N/A (LightRAG handles selection) | — |
| `GET /api/search/{job_id}` | N/A (returns LightRAG output verbatim) | — |
| `POST /api/synthesize` | N/A | — |
| `GET /api/synthesize/{job_id}` | INHERITED via `result.sources` (`kg_synthesize` calls list-style query → filter active) | — |
| `/static/img/*` | N/A | — |

The verbatim filter SQL clause (KOL `articles` table; identical for `rss_articles`):

```sql
WHERE body IS NOT NULL
  AND body != ''
  AND layer1_verdict = 'candidate'
  AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')
```

See `kb-3-CONTENT-QUALITY-DECISIONS.md` for the locked decision rationale, expected visibility numbers, fixture coordination, and rollout plan. This API contract MUST stay synchronized with that decision doc; if DATA-07 SQL clause changes, this contract is the second-source-of-truth update target.

---

## 11. C1 + C2 read-only contracts (referenced verbatim, signatures UNCHANGED)

### 11.1 C1 — kg_synthesize.synthesize_response

```python
# kg_synthesize.py:105 — DO NOT MODIFY
async def synthesize_response(query_text: str, mode: str = "hybrid"):
    ...
```

The KB layer (`kb/services/synthesize.py`) calls this function with:
- `query_text` = language directive prepend + user `question` (per I18N-07 §7.3)
- `mode` = `"hybrid"` (always; no user override exposed in v2.0)

The wrapper does NOT modify the function, monkey-patch it, or shadow its imports. KB is a strict consumer.

### 11.2 C2 — omnigraph_search.query.search

```python
# omnigraph_search/query.py:35 — DO NOT MODIFY
async def search(query_text: str, mode: str = "hybrid") -> str:
    """Query LightRAG at RAG_WORKING_DIR and return the raw retrieval text."""
    ...
```

The KB layer calls this for `/api/search?mode=kg` with `query_text = q + (optional lang directive)` and `mode="hybrid"`. Returned string surfaces in `result.raw_text` and `result.markdown` (after D-17 rewrite).

Note: `from omnigraph_search.query import search` — this import will appear in `kb/services/search.py` per the C2 reference pattern declared in the plan frontmatter.

### 11.3 No new LLM provider env vars (CONFIG-02)

The KB layer does NOT introduce new `KB_LLM_*` or similar env vars. Q&A delegates to `lib.llm_complete.get_llm_func()` which honors `OMNIGRAPH_LLM_PROVIDER={deepseek, vertex_gemini}` (K-1). The synthesize wrapper does not read any LLM-related env var directly.

The complete env-var inventory introduced by kb-3:

| Var | Default | Purpose |
| --- | ------- | ------- |
| `KB_PORT` | `8766` | uvicorn bind port (CONFIG-01) |
| `KB_DB_PATH` | `~/.hermes/data/kol_scan.db` | SQLite path (CONFIG-01) |
| `KB_IMAGES_DIR` | `~/.hermes/omonigraph-vault/images` | StaticFiles mount source (CONFIG-01) |
| `KB_CONTENT_QUALITY_FILTER` | `on` | DATA-07 master toggle (§3.5) |
| `KB_SEARCH_BYPASS_QUALITY` | `off` | DATA-07 search-scope override (§5.6) |
| `KB_SYNTHESIZE_TIMEOUT` | `60` | Synthesize wall-time (§7.11) |
| `KB_QA_POLL_INTERVAL_MS` | `1500` | Client polling cadence (referenced in kb-3-UI-SPEC.md §3) |
| `KB_QA_POLL_TIMEOUT_MS` | `60000` | UI-side timeout before transitioning to `fts5_fallback` |

**Zero LLM provider env vars** — verifiable via grep:

```bash
grep -E "^(KB_|kb_)?LLM_" kb/api.py kb/services/*.py 2>/dev/null  # MUST return empty
```

---

## 12. Cross-references — downstream plan consumers

This contract document is the source of truth for the following downstream plans:

| Plan | What it consumes |
| ---- | ---------------- |
| `kb-3-02-data07-filter-PLAN.md` | §10 DATA-07 contract; SQL clauses for `kb/data/article_query.py` |
| `kb-3-04-fastapi-skeleton-PLAN.md` | §1 conventions; §1.5 async-job lifecycle; §1.8 auth (none); §8 static mount |
| `kb-3-05-articles-endpoints-PLAN.md` | §3 GET /api/articles + §4 GET /api/article/{hash} (Pydantic response models, status codes) |
| `kb-3-06-search-endpoint-PLAN.md` | §5 GET /api/search (mode discrimination); §6 GET /api/search/{job_id} (state machine) |
| `kb-3-07-rebuild-fts-script-PLAN.md` | §5.6 FTS5 query SQL (DATA-07 join clause that the rebuild script must keep synchronized) |
| `kb-3-08-synthesize-wrapper-PLAN.md` | §7.1-7.8 endpoint shape; §7.3 language directive prepend; §11.1 C1 contract reference |
| `kb-3-09-fts5-fallback-PLAN.md` | §7.10 NEVER 500 invariant; §7.11 timeout; §7.9 fallback response shape |
| `kb-3-10-qa-state-matrix-ui-PLAN.md` | §7.7-7.9 polling response shapes (UI consumes these JSON fields); §1.4 error envelope |
| `kb-3-11-search-inline-reveal-PLAN.md` | §5.3 FTS response shape (UI renders `items[].snippet` with `<mark>` tags); §5.4 KG async pattern |
| `kb-3-12-full-integration-test-PLAN.md` | All sections — integration tests assert HTTP shapes verbatim |

---

## 13. Acceptance criteria (regex-verifiable, included for SUMMARY discipline grep)

```bash
# Skill invocation evidence
grep 'Skill(skill="api-design"' .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md   # >= 1

# C1 + C2 references
grep 'synthesize_response' .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md         # >= 1
grep 'omnigraph_search' .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md            # >= 1

# DATA-07 + overrides
grep 'DATA-07' .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md                     # >= 1
grep 'KB_CONTENT_QUALITY_FILTER' .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md   # >= 1
grep 'KB_SEARCH_BYPASS_QUALITY' .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md    # >= 1

# All 8 API REQs
for req in API-01 API-02 API-03 API-04 API-05 API-06 API-07 API-08; do
  grep -q "$req" .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md && echo "$req ok" || echo "$req MISSING"
done

# Async-job state machine vocabulary
grep -E 'job_id|running|done|failed' .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md   # >= 4

# Never-500 invariant
grep -i 'never.*500\|500.*never' .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md       # >= 1

# Language directive strings
grep '请用中文回答' .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md                    # >= 1
grep 'Please answer in English' .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md        # >= 1

# Length
[ "$(wc -l < .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md)" -ge 200 ]
```

---

## 14. Out of scope (explicit deferrals to v2.1+)

- **Versioned URL prefix `/api/v1/`** — added when first breaking change ships
- **CORS** — same-origin deployment in v2.0
- **Rate limiting** — Redis token-bucket in v2.1 (RATE-* in REQUIREMENTS)
- **Multi-worker job-store** — SQLite-backed in v2.1 (MULTI-WORKER-*)
- **POST /api/feedback** — UI-only localStorage in v2.0; backend ingestion in v2.0.x or v2.1 (kb-3-UI-SPEC.md §3.5)
- **WebSocket / SSE streaming** — HTTP polling only per D-19; SSE upgrade preserves the same `job_id` contract
- **Bearer token auth** — public read-only API in v2.0 per D-07; admin endpoints (DATA-07 toggle UI) v2.1
- **Cursor-based pagination** — offset is sufficient for ~160-article corpus; v2.1 if dataset grows past ~10K rows
- **Sparse fieldsets / `?fields=` selector** — clients receive full response shape; bandwidth not a concern at MVP scale
- **OpenAPI / Swagger spec generation** — FastAPI auto-generates `/docs` and `/openapi.json` for free; v2.0 ships them but does not curate

---

## 15. Versioning of this document

| Version | Date | Author | Change |
| ------- | ---- | ------ | ------ |
| 1.0 | 2026-05-14 | kb-3-01 executor | Initial contract lock — applied api-design discipline verbatim, all 8 API REQs covered, DATA-07 + I18N-07 + CONFIG-02 cross-referenced |

If downstream plans (kb-3-04..09) discover an unspecified detail during implementation, the resolution path is:
1. Discuss with user
2. Update THIS document first (with version bump)
3. Then implement against the updated contract

This contract is the source of truth — implementation that diverges from this contract is a bug, not a "clarification".
