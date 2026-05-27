---
phase: kb-3-fastapi-bilingual-api
plan: 01
subsystem: api-contract
tags: [api-design, rest, contract-lock]
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md
autonomous: true
requirements:
  - API-01
  - API-02
  - API-03
  - API-04
  - API-05
  - API-06
  - API-07
  - API-08

must_haves:
  truths:
    - "REST contract for /api/articles, /api/article/{hash}, /api/search, /api/synthesize, /api/synthesize/{job_id}, /api/search/{job_id} is locked in writing before any code is written"
    - "Each endpoint has documented: method, path, query params, request body, response shape, status codes (200/202/404/422), error format"
    - "C1 + C2 contracts (kg_synthesize.synthesize_response, omnigraph_search.query.search) are READ-ONLY — KB layer wraps, never modifies"
    - "Async polling pattern (D-19) locked: POST/GET → 202 + job_id, GET /{job_id} → done|running|failed"
    - "DATA-07 cross-references CONTENT-QUALITY-DECISIONS.md — list endpoints honor filter, get_article_by_hash carve-out preserved"
  artifacts:
    - path: ".planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md"
      provides: "REST API contract document; consumed by kb-3-04..09 implementation plans"
      min_lines: 200
  key_links:
    - from: "kb-3-API-CONTRACT.md"
      to: "kg_synthesize.py:105 synthesize_response signature"
      via: "C1 contract reference (signature unchanged)"
      pattern: "synthesize_response.*query_text.*mode"
    - from: "kb-3-API-CONTRACT.md"
      to: "omnigraph_search/query.py:35 search signature"
      via: "C2 contract reference (signature unchanged)"
      pattern: "from omnigraph_search"
---

<objective>
Lock the REST API contract for kb-3 BEFORE any FastAPI code is written. This plan produces a single contract document `kb-3-API-CONTRACT.md` that downstream plans (kb-3-04 app entry, kb-3-05 articles, kb-3-06 search, kb-3-08 synthesize) read as their source of truth for endpoint shape, status codes, and error format.

Purpose: Avoid the kb-1 anti-pattern of "write code, discover the contract by inspection". With a locked contract, the FastAPI implementation plans don't need to invent route shapes; they implement what's specified. Cross-AI consumers (the future Hermes agent skill, the kb-2 SSG output that may call /api/articles) get a stable interface from day 1.

Output: One `.md` file in the phase directory, sectioned per endpoint, with paste-ready Pydantic-shape JSON examples + status-code matrix.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/ROADMAP-KB-v2.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md
@kb/docs/02-DECISIONS.md
@kb/docs/06-KB3-API-QA.md
@kb/docs/10-DESIGN-DISCIPLINE.md
@kg_synthesize.py
@omnigraph_search/query.py
@CLAUDE.md

<interfaces>
C1 (read-only — DO NOT modify):
```python
# kg_synthesize.py:105
async def synthesize_response(query_text: str, mode: str = "hybrid"):
    # Returns: writes synthesis result to disk + returns awaitable
```

C2 (read-only — DO NOT modify):
```python
# omnigraph_search/query.py:35
def search(query_text: str, mode: str = "hybrid") -> str:
    # Returns: KG hybrid search result string
```

Endpoint inventory (from ROADMAP-KB-v2.md kb-3 success criteria):
- API-01: app boot, KB_PORT env, default 8766
- API-02: GET /api/articles?page&limit&source&lang&q
- API-03: GET /api/article/{hash}
- API-04: GET /api/search?q&mode=fts&lang&limit
- API-05: GET /api/search?q&mode=kg&lang → 202 + job_id; GET /api/search/{job_id}
- API-06: POST /api/synthesize {question, lang} → 202 + job_id
- API-07: GET /api/synthesize/{job_id}
- API-08: app.mount("/static/img", StaticFiles)
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Invoke api-design Skill + author kb-3-API-CONTRACT.md</name>
  <read_first>
    - .planning/REQUIREMENTS-KB-v2.md (API-01..08, SEARCH-01..03, QA-01..05, DATA-07, I18N-07, CONFIG-02 — exact REQ wordings)
    - .planning/ROADMAP-KB-v2.md lines 195-260 (kb-3 success criteria 1-8 verbatim)
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md (DATA-07 carve-out: get_article_by_hash unfiltered; /api/search filter on by default + KB_SEARCH_BYPASS_QUALITY env override)
    - kg_synthesize.py:105 (C1 signature — copy verbatim into contract doc as "DO NOT MODIFY")
    - omnigraph_search/query.py:35 (C2 signature — same)
    - kb/docs/06-KB3-API-QA.md (kb-3 exec spec)
    - kb/docs/02-DECISIONS.md D-04, D-15, D-17, D-19, D-20
  </read_first>
  <files>.planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md</files>
  <action>
    Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1, this plan invokes the api-design Skill BEFORE writing the contract:

    Skill(skill="api-design", args="Lock the REST API contract for kb-3 (FastAPI on :8766). Endpoints to design: GET /api/articles?page&limit&source&lang&q (paginated list, DATA-07 filter applied), GET /api/article/{hash} (single article by md5[:10] — DATA-07 carve-out: unfiltered for direct access), GET /api/search?q&mode=fts|kg&lang&limit (FTS5 sync OR KG async-job pattern), GET /api/search/{job_id} (poll KG search), POST /api/synthesize {question, lang} → 202 + job_id (BackgroundTasks; C1 wrapper preserved), GET /api/synthesize/{job_id} → {status, result?, fallback_used, confidence}. Constraints: zero new LLM provider env vars (CONFIG-02); never 500 on synthesize failure (QA-04, QA-05) — fall through to FTS5 top-3; D-19 async polling (no WebSocket); D-20 URL pattern md5[:10]; SQLite FTS5 trigram (D-18). Output: a markdown contract doc with one section per endpoint containing: method+path, query/path/body params with types, response JSON schema (paste-ready), status code matrix (200/202/404/422/500-never), error response shape `{detail: str, code: str}`, and explicit DATA-07 filter behavior + KB_SEARCH_BYPASS_QUALITY override. Reference C1 + C2 signatures verbatim. Note that the contract MUST list which endpoints accept the `lang` directive injection per I18N-07 + QA-02. Cross-reference REQ IDs in each section header.")

    Then author `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md` with the api-design Skill output. The document MUST contain these sections (one per endpoint group):

    1. **Header** — frontmatter: phase, status: ratified, REQs covered (list 19 IDs), C1+C2 contract refs.
    2. **Conventions** — base URL, content-type (`application/json`), pagination params naming, error envelope shape (`{detail, code}`), async-job lifecycle (202 → poll → done|failed).
    3. **GET /api/articles** (API-02, DATA-07) — query params (`page=1`, `limit=20`, `source=wechat|rss|`, `lang=zh-CN|en|`, `q=` LIKE on title), response shape (`{items: [...], page, limit, total, has_more}`), status codes, DATA-07 filter behavior verbatim from CONTENT-QUALITY-DECISIONS.md, KB_CONTENT_QUALITY_FILTER env override.
    4. **GET /api/article/{hash}** (API-03, D-14) — path param `hash` (10-char md5 prefix), response shape (`{hash, title, body_md, body_html, lang, source, images: [...], metadata, body_source}`), 404 on miss, DATA-07 carve-out: NOT filtered (direct access preserved per CONTENT-QUALITY-DECISIONS.md § "NOT affected (intentional carve-out)").
    5. **GET /api/search** (API-04, API-05, SEARCH-01, SEARCH-03, DATA-07) — query params (`q`, `mode=fts|kg`, `lang`, `limit`); FTS5 mode returns 200 + `{items: [{hash, title, snippet, lang, source}], total}` with `snippet()` 200-char highlighting; KG mode returns 202 + `{job_id, status: "running"}`; lang filter behavior; DATA-07 applied to FTS5 by default + KB_SEARCH_BYPASS_QUALITY=on env to bypass.
    6. **GET /api/search/{job_id}** (API-05) — KG search async polling.
    7. **POST /api/synthesize** (API-06, I18N-07, QA-01, QA-02) — request body `{question: str, lang: "zh"|"en"}`, language directive prepend rule (Chinese: `"请用中文回答。\n\n"` / English: `"Please answer in English.\n\n"`), 202 + job_id; explicit C1 contract reference: signature `synthesize_response(query_text: str, mode: str = "hybrid")` UNCHANGED.
    8. **GET /api/synthesize/{job_id}** (API-07, QA-04, QA-05) — response shape `{status: "running"|"done"|"failed", result?: {markdown, sources, entities}, fallback_used: bool, confidence: "kg"|"fts5_fallback"}`; **never 500** — wrapper catches all exceptions and falls through to FTS5 top-3 (QA-05 verbatim).
    9. **Static images** (API-08) — `app.mount("/static/img", StaticFiles(directory=KB_IMAGES_DIR))`; replaces `:8765` standalone server (D-15); identical bytes for `/static/img/{hash}/<file>`.
    10. **Error envelope** — `{detail: str, code: str}` for 4xx; never 500 on synthesize.
    11. **Async-job state machine** — diagram + invariants: job_id is opaque uuid4, in-memory dict, single-worker only (multi-worker deferred to v2.1 per QA-03).
    12. **DATA-07 contract** — quote the SQL clause verbatim; specify which endpoints filter and which carve-out; reference fixture coordination from CONTENT-QUALITY-DECISIONS.md.

    File MUST contain literal `Skill(skill="api-design"` string for verification regex.
    File MUST be ≥200 lines.
    File MUST end with a "Cross-references" section listing which downstream plans implement which endpoint.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && test -f .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md && grep -q 'Skill(skill="api-design"' .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md && grep -q 'synthesize_response' .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md && grep -q 'DATA-07' .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md && grep -q 'KB_SEARCH_BYPASS_QUALITY' .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md && [ "$(wc -l < .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md)" -ge 200 ]</automated>
  </verify>
  <acceptance_criteria>
    - File `kb-3-API-CONTRACT.md` exists in phase dir with ≥200 lines
    - Contains literal `Skill(skill="api-design"` (verifies invocation per discipline)
    - Contains `synthesize_response` (C1 reference)
    - Contains `from omnigraph_search` OR `omnigraph_search.query.search` (C2 reference)
    - Contains `DATA-07`, `KB_CONTENT_QUALITY_FILTER`, `KB_SEARCH_BYPASS_QUALITY`
    - Contains all 8 API REQ IDs (API-01..API-08) referenced
    - Contains async-job state machine description (`job_id`, `running`, `done`, `failed`)
    - Contains `never 500` or `Never returns 500` (QA-05 invariant)
    - Contains language-directive prepend rule strings for both lang values
  </acceptance_criteria>
  <done>API contract document committed. Downstream plans (kb-3-04..09) consume this as their source of truth for endpoint shape.</done>
</task>

</tasks>

<verification>
- `kb-3-API-CONTRACT.md` exists, ≥200 lines, all 8 API REQs referenced
- api-design Skill invocation literal in PLAN action AND will appear in SUMMARY (regex-verifiable)
- No code written this plan — pure contract lock
</verification>

<success_criteria>
- API-01..API-08 contract locked in writing
- C1 + C2 read-only contracts referenced verbatim
- DATA-07 filter behavior across endpoints documented
- Downstream plans have unambiguous reference for endpoint shape
</success_criteria>

<output>
Create `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-01-SUMMARY.md` documenting:
- Single artifact: kb-3-API-CONTRACT.md (lines, sections covered)
- Skill invocation string `Skill(skill="api-design", ...)` literal in summary for discipline regex match
- 8 API REQs covered + DATA-07 cross-reference
- Downstream plan consumers (kb-3-04, kb-3-05, kb-3-06, kb-3-08, kb-3-09)
</output>
</content>
</invoke>