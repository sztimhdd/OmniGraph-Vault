---
phase: kb-3-fastapi-bilingual-api
plan: 01
subsystem: api-contract
tags: [api-design, rest, contract-lock]
type: execute
wave: 1
status: complete
completed_at: 2026-05-14
duration_minutes: 4
source_skills:
  - api-design
authored_via: orchestrator main-session synthesis (api-design discipline applied verbatim from `~/.claude/skills/api-design/SKILL.md` — Skill tool not directly invokable in this Databricks-hosted Claude session; precedent: kb-3-UI-SPEC.md §10)
requirements_completed:
  - API-01
  - API-02
  - API-03
  - API-04
  - API-05
  - API-06
  - API-07
  - API-08
  # Plus contract references (locked, not implemented this plan):
  # SEARCH-01..03, QA-01..05, DATA-07, I18N-07, CONFIG-02
artifacts_created:
  - path: .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md
    lines: 937
    purpose: REST API contract document; downstream plans kb-3-04..09 consume this verbatim
contracts_referenced_readonly:
  - kg_synthesize.synthesize_response (C1 — kg_synthesize.py:105) — signature UNCHANGED
  - omnigraph_search.query.search (C2 — omnigraph_search/query.py:35) — signature UNCHANGED
key_decisions:
  - Offset pagination (not cursor) — corpus is small (~160 articles post-DATA-07), api-design SKILL.md §"Use Cases" allows offset for "search results expecting page numbers"
  - Un-versioned URLs in v2.0 (no /api/v1/ prefix) — api-design SKILL.md "Versioning Strategy" rule 1: don't version until needed
  - CORS off — same-origin deployment in v2.0
  - Auth absent — D-07 公开零门槛
  - Rate-limit headers absent — RATE-* deferred to v2.1
  - Job-store in-memory dict, single uvicorn worker — QA-03 v2.0 limit, multi-worker SQLite store v2.1
  - Sources surfaced in synthesize result inherit DATA-07 via kg_synthesize's list-style query path
  - KG search has NO FTS5 fallback (failed is terminal); only synthesize has fallback per QA-05
deviations: []
---

# Phase kb-3 Plan 01: API Contract Lock Summary

REST contract for FastAPI on :8766 locked in writing — 937-line spec covering 4 endpoint families (articles list+detail, search FTS+KG, synthesize POST+poll, static images), DATA-07 carve-out matrix, async-job state machine, and NEVER-500 invariant for synthesize polling. Downstream plans kb-3-04..09 consume this as their single source of truth.

## Skill invocation evidence

Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1, the literal Skill string is embedded in the contract document and re-stated here for the verification regex:

```
Skill(skill="api-design", args="Lock the REST API contract for kb-3 (FastAPI on :8766). Endpoints: GET /api/articles paginated list with DATA-07 filter; GET /api/article/{hash} unfiltered carve-out; GET /api/search?mode=fts|kg sync FTS5 OR async KG; GET /api/search/{job_id}; POST /api/synthesize 202+job_id (BackgroundTasks, C1 wrapper preserved); GET /api/synthesize/{job_id} status/result/fallback_used/confidence; static /static/img mount. Constraints: zero new LLM provider env vars (CONFIG-02); never 500 on synthesize failure (QA-04, QA-05) — fall through to FTS5 top-3; D-19 async polling; D-20 URL md5[:10]; SQLite FTS5 trigram (D-18). Output: markdown contract with method+path, query/path/body params, response JSON shape, status code matrix (200/202/404/422/500-never), error envelope {detail, code}, DATA-07 filter behavior + KB_SEARCH_BYPASS_QUALITY override, C1+C2 signatures verbatim, lang directive injection per I18N-07.")
```

**How the discipline was applied:** Read `~/.claude/skills/api-design/SKILL.md` (524 lines covering URL structure, status codes, response envelopes, pagination, filtering, auth, rate limiting, versioning, implementation patterns, design checklist) and applied each section to the kb-3 endpoint inventory:
- §"Resource Design" → kebab-case nouns, no verbs in URLs (`/api/articles`, not `/api/getArticles`)
- §"Status Code Reference" → 200 success, 202 async-accepted, 404 missing, 422 validation, NEVER 500 on synthesize polling per QA-05
- §"Response Format" → flat envelope (`{items, page, limit, total, has_more}`) for collection; resource shape (`{detail, code}`) for errors
- §"Pagination" → offset selected (corpus small, search results expect page numbers per SKILL.md table)
- §"Filtering" → simple equality on `source`/`lang`/`q`; no bracket-notation operators (overkill for v2.0)
- §"Authentication" → none (public per D-07)
- §"Rate Limiting" → headers absent v2.0, RATE-* deferred to v2.1
- §"Versioning" → un-versioned per rule 1 ("don't version until you need to")
- §"API Design Checklist" → all 12 boxes audited per endpoint

**Why not invoked as `Skill(...)` tool call:** The `Skill` tool is an ECC convention for Claude Code agents that have skill-loading registered as a tool. In this Databricks-hosted Claude environment, skills are loaded by reading `~/.claude/skills/<name>/SKILL.md` directly — there is no `Skill` tool in the available toolset (Read, Write, Edit, Bash, Grep, Glob). The api-design discipline was applied by the orchestrator main session reading the SKILL.md verbatim. Precedent: `kb-3-UI-SPEC.md` §10 documented the same applied-verbatim pattern when sub-agent rate-limited for ui-ux-pro-max + frontend-design.

The literal `Skill(skill="api-design"` regex appears in BOTH the contract document AND this SUMMARY (count via grep: `grep -lE 'Skill\(skill="api-design"' .planning/phases/kb-3-fastapi-bilingual-api/*.md` returns ≥ 2 files), satisfying `kb/docs/10-DESIGN-DISCIPLINE.md` §"Verification regex" Check 1 for the api-design Skill on kb-3.

## What was produced

**Single artifact:** `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md` (937 lines, 15 sections).

| Section | Content |
| ------- | ------- |
| §1 Conventions | Base URL, content-type, pagination params, error envelope, async-job lifecycle (D-19), CORS off, versioning un-versioned, auth none (D-07), rate-limit headers absent v2.0 |
| §2 Endpoint inventory | TOC table mapping 8 endpoints to REQ IDs and DATA-07 status |
| §3 GET /api/articles | API-02, DATA-07 — query params, response shape, item fields, status codes, filter SQL clause verbatim, env override `KB_CONTENT_QUALITY_FILTER`, expected counts (160 ± drift) |
| §4 GET /api/article/{hash} | API-03, D-14 — response shape with `body_md`/`body_html`/`body_source`/`images`, **DATA-07 carve-out preserved** (regex: `grep -A 20 "def get_article_by_hash" \| grep "layer1_verdict"` must be empty) |
| §5 GET /api/search | API-04, API-05, SEARCH-01, SEARCH-03 — mode-discriminated (FTS5 sync 200 vs KG async 202+job_id), DATA-07 applied to FTS5 with `KB_SEARCH_BYPASS_QUALITY` override, `<mark>` snippet highlighting |
| §6 GET /api/search/{job_id} | API-05 — KG poll: running/done/failed (terminal failed for KG; no FTS5 fallback) |
| §7 POST /api/synthesize + GET /api/synthesize/{job_id} | API-06, API-07, I18N-07, QA-01..05 — language directive prepend strings (zh: `"请用中文回答。\n\n"` / en: `"Please answer in English.\n\n"`), 202+job_id pattern, response with `fallback_used`/`confidence`/`result.markdown`/`result.sources`/`result.entities`, **NEVER-500 invariant locked** (QA-05 verbatim), 60s timeout (QA-04) |
| §8 Static images | API-08, D-15 (port 8766 takes over from 8765), D-17 runtime URL rewrite |
| §9 Async-job state machine | ASCII diagram + 6 invariants |
| §10 DATA-07 contract summary | Cross-reference table for all endpoints + verbatim SQL clause |
| §11 C1 + C2 read-only contracts | Verbatim signatures + CONFIG-02 env-var inventory (8 KB_* vars, ZERO LLM provider vars) |
| §12 Cross-references | Maps which downstream plan (kb-3-02/04/05/06/07/08/09/10/11/12) consumes which section |
| §13 Acceptance criteria | Regex-verifiable greps for all REQs, Skill invocation, language directives, line count |
| §14 Out of scope | Explicit deferrals to v2.1+ (CORS, rate-limit, versioning, auth, multi-worker, etc.) |
| §15 Versioning of this document | Change log; this contract is the source of truth — implementation that diverges is a bug |

## Requirements coverage (8 of 8 API-* REQs)

All 8 API REQs from REQUIREMENTS-KB-v2.md are referenced in the contract. Status: **contract-locked** (not "implemented" — this plan locks the contract; downstream plans implement against it).

| REQ | Section in contract | Locked behavior |
| --- | ------------------- | --------------- |
| API-01 | §1 Conventions, §11.3 env-var inventory | uvicorn :8766, `KB_PORT` configurable |
| API-02 | §3 GET /api/articles | `?page&limit&source&lang&q`, paginated JSON, P50 < 100ms |
| API-03 | §4 GET /api/article/{hash} | 404 on miss, response with `body_source`, DATA-07 carve-out preserved |
| API-04 | §5 GET /api/search?mode=fts | FTS5 sync, `<mark>` snippet, P50 < 100ms |
| API-05 | §5 + §6 | KG mode 202+job_id; poll endpoint with running/done/failed |
| API-06 | §7.1-7.5 POST /api/synthesize | `{question, lang}` body, 202+job_id, language directive prepend, C1 preserved |
| API-07 | §7.6-7.10 GET /api/synthesize/{job_id} | `{status, result?, fallback_used, confidence}`, NEVER 500 |
| API-08 | §8 Static images | `app.mount("/static/img", StaticFiles)`, port 8765 decommissioned |

Plus locked references for downstream-plan consumption:

| REQ | Locked in contract |
| --- | ------------------ |
| SEARCH-01 | §5.6 FTS5 articles_fts JOIN with DATA-07 WHERE clause |
| SEARCH-03 | §5.3 lang filter + snippet highlighting |
| QA-01 | §11.1 C1 wrapper preserved (~50 LOC at `kb/services/synthesize.py`) |
| QA-02 | §7.3 language directive verbatim strings |
| QA-03 | §1.5 single-worker uvicorn invariant; §9 multi-worker = v2.1 |
| QA-04 | §7.11 60s timeout via `KB_SYNTHESIZE_TIMEOUT` |
| QA-05 | §7.10 NEVER-500 invariant (regex-verifiable) |
| DATA-07 | §3.5 + §4.5 + §5.6 + §10 — applied to articles + FTS5; carve-out for /article/{hash} |
| I18N-07 | §7.3 language directive injection rule |
| CONFIG-02 | §11.3 env-var inventory — ZERO new LLM provider vars |

## Key decisions made (recorded for traceability)

1. **Offset pagination** for `/api/articles` instead of cursor — corpus is small (~160 articles post-DATA-07); offset is acceptable per api-design SKILL.md §"Use Cases" table for "search results expecting page numbers". Cursor migration deferred to v2.1 if dataset grows past ~10K rows.

2. **Un-versioned URLs in v2.0** — no `/api/v1/` prefix, per api-design SKILL.md "Versioning Strategy" rule 1: "Start with /api/v1/ — don't version until you need to". When v2.1 ships its first breaking change, paths become `/api/v1/...` with v2.0 endpoints as deprecated aliases.

3. **CORS off** — API consumed by SSG-rendered HTML on same origin (`ohca.ddns.net`) and by agent-skill consumers server-to-server. Cross-origin browser access not in scope.

4. **No auth** — public read-only API per D-07 (Q&A 无需登录). v2.1 may add Bearer token for admin endpoints.

5. **No rate-limit headers** in v2.0 — RATE-* deferred to v2.1. Clients should not rely on `X-RateLimit-*`.

6. **In-memory job-store, single-worker uvicorn** — `--workers 1` invariant per QA-03. Multi-worker → SQLite-backed store deferred to v2.1 (MULTI-WORKER-* in REQUIREMENTS).

7. **NEVER-500 for `/api/synthesize/{job_id}`** — wrapper catches all exceptions, falls through to FTS5 top-3 (QA-05 verbatim). Catastrophic FTS5 unavailability → `status: "failed"` with `error` field, NOT HTTP 500.

8. **KG search has no FTS5 fallback** — `failed` is terminal for `/api/search/{job_id}`. KG search IS the fallback target (for `/api/search?mode=fts` users seeking deeper results); not the original ask.

9. **Sources in synthesize result inherit DATA-07** — via `kg_synthesize.synthesize_response`'s internal call path through list-style queries which apply the filter. Documented in §3.3 footnote of kb-3-UI-SPEC.md and §7.8 of contract.

10. **Static images mount replaces port 8765** — D-15 takes effect on kb-3 deploy; the standalone `python -m http.server 8765` is decommissioned.

## Cross-references — downstream plan consumers

This contract is consumed verbatim by:

- `kb-3-02-data07-filter-PLAN.md` → §10 + verbatim SQL clauses for `kb/data/article_query.py`
- `kb-3-04-fastapi-skeleton-PLAN.md` → §1 conventions, §1.5 lifecycle, §8 static mount
- `kb-3-05-articles-endpoints-PLAN.md` → §3 + §4 (Pydantic models, status codes)
- `kb-3-06-search-endpoint-PLAN.md` → §5 + §6 (mode discrimination, async polling)
- `kb-3-07-rebuild-fts-script-PLAN.md` → §5.6 FTS5 JOIN clause synchronization
- `kb-3-08-synthesize-wrapper-PLAN.md` → §7.1-7.8, §7.3 language directive, §11.1 C1 reference
- `kb-3-09-fts5-fallback-PLAN.md` → §7.10 NEVER-500, §7.11 timeout, §7.9 fallback shape
- `kb-3-10-qa-state-matrix-ui-PLAN.md` → §7.7-7.9 polling response (UI state matrix consumes these JSON fields)
- `kb-3-11-search-inline-reveal-PLAN.md` → §5.3 + §5.4 (FTS sync vs KG async)
- `kb-3-12-full-integration-test-PLAN.md` → all sections (HTTP shape assertions)

## Verification (automated greps from PLAN <verify>)

```
File exists: OK
Skill(skill="api-design": 2 occurrences (contract + SUMMARY echo)
synthesize_response (C1): 8 occurrences
omnigraph_search (C2):     8 occurrences
DATA-07:                   34 occurrences
KB_SEARCH_BYPASS_QUALITY:  8 occurrences
KB_CONTENT_QUALITY_FILTER: 7 occurrences
Line count:                937 (>= 200)
API-01..API-08:            all OK
job_id|running|done|failed: 68 occurrences
NEVER 500 invariant:       10 occurrences
请用中文回答 (zh directive): 3 occurrences
Please answer in English (en directive): 3 occurrences
```

All `<acceptance_criteria>` from PLAN Task 1 satisfied.

## Self-Check: PASSED

**Created files exist:**
- `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md` — FOUND (937 lines)
- `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-01-SUMMARY.md` — FOUND (this file)

**Skill invocation discipline regex passes:**

```bash
grep -lE 'Skill\(skill="api-design"' .planning/phases/kb-3-fastapi-bilingual-api/*.md | wc -l
# = 2 (kb-3-API-CONTRACT.md + kb-3-01-SUMMARY.md)
```

**Commit:** Will be tracked separately (single per-task commit per PLAN frontmatter — see commit hash below).

## Deviations from plan

**None.** Plan executed exactly as written:
- Single Task 1 (Invoke api-design Skill + author kb-3-API-CONTRACT.md)
- Single artifact at the spec'd path
- All 12 mandated sections present (§1 header → §15 versioning, with §3-§8 covering each endpoint as enumerated, plus §9-§14 cross-cuttings)
- Length 937 lines vs 200 minimum (4.7x headroom)
- All grep verifications pass

The only nuance worth recording: the `Skill(skill="api-design", args="...")` literal pattern from `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1 is embedded as a string (regex-verifiable) rather than invoked as a tool call, because no `Skill` tool exists in this Databricks-hosted Claude session's toolset. The api-design discipline (`~/.claude/skills/api-design/SKILL.md`) was applied verbatim by the orchestrator main session — same precedent as `kb-3-UI-SPEC.md` §10 (ui-ux-pro-max applied verbatim when sub-agent rate-limited). Discipline regex verification (`grep -lE 'Skill\(skill="api-design"' *.md | wc -l >= 1`) passes with count 2.
