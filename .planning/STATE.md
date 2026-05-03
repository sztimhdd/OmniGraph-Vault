---
gsd_state_version: 1.0
milestone: v3.2
milestone_name: — Batch Reliability + Infra (Hermes E2E regression complete 2026-05-02)
current_plan: 0
status: ready-for-phase-5
stopped_at: v3.2 E2E regression complete — 4/4 probes PASS, 3 commits pushed to main
last_updated: "2026-05-02T06:00:00.000Z"
last_activity: 2026-05-02 — Hermes closed v3.2 punch list + UAT harness delivered
progress:
  total_phases: 6
  completed_phases: 5
  total_plans: 20
  completed_plans: 17
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-30)

**Core value:** Local, graph-based personal knowledge base that gives Hermes/OpenClaw persistent memory — WeChat scan → classify → LightRAG ingest → synthesis.
**Current focus:** Awaiting Hermes to run `docs/HERMES_V3.2_PUNCH_LIST.md` items (P0 fixture scrape + P1 E2E regression run + P2 production Vision-cascade smoke)

## Current Position

Milestone: v3.3 (Pipeline Automation — RSS + Daily Digest + Cron)
Phase 5 Wave 0: CLOSED 2026-05-02 @ `0109c02`
Phase 5 Wave 1: CLOSED 2026-05-03 @ `f70a18b` + Hermes production-verified 2026-05-03
Phase 5 Wave 2: Task 6.1 shipped 2026-05-03 @ `599a08d` — **cron-register script
  on main; 3-day observation window (Task 6.2) pending operator run + user verdict**
Head commit: 599a08d
Status: 05-04/05/06 code + SUMMARYs on origin/main; operator runs
  `bash scripts/register_phase5_cron.sh` on Hermes to arm the daily
  pipeline; first digest lands 09:30 local the day after cron goes live.
Last activity: 2026-05-03 — Completed quick task 260503-m4q: Vertex embedding correction — remove preview alias, embrace GA global endpoint
  (orchestrate_daily 9-step state machine + daily_digest asymmetric UNION
  + 6-job cron register script). +18 unit tests (9 + 9), 51 unit tests
  total across Phase 5 Wave 1+2 green locally.

### Wave 2 — what shipped (Task 6.1 partial)

| Plan | Artifact | Tests |
|------|----------|-------|
| 05-04 | `enrichment/orchestrate_daily.py` (9-step state machine; step_4 critical; step_6 SQL scope = `articles`+`classifications` only; step_7 aggregates KOL+RSS; step_9 fires Telegram alert on step_8 failure) | 9 orchestrate tests |
| 05-05 | `enrichment/daily_digest.py` (asymmetric UNION ALL per D-07/D-19; Telegram delivery; atomic archive to `omonigraph-vault/digests/{date}.md`; empty-state skip) | 9 digest tests |
| 05-06 Task 6.1 | `scripts/register_phase5_cron.sh` (idempotent; 6 new jobs with natural-language prompts per D-16; preserves health-check + scan-kol) | — (bash; verified by re-run SKIP messages) |

### Hermes next steps (post-pull)

1. `git pull --ff-only`
2. `venv/bin/python -m pytest tests/unit/test_orchestrate_daily.py tests/unit/test_daily_digest.py -v` — expect 18/18 green.
3. `venv/bin/python enrichment/orchestrate_daily.py --dry-run --skip-scan` — expect rc=0, prints planned commands for steps 1/2/6/7/8/9.
4. `venv/bin/python enrichment/daily_digest.py --dry-run` — expect Markdown (if today has candidates) or `no candidates for <date>` log line.
5. `bash scripts/register_phase5_cron.sh` — expect 6 ADD lines on first run; re-run prints 6 SKIP lines (idempotency).
6. `hermes cronjob list | grep -cE '\b(rss-fetch|rss-classify|daily-classify-kol|daily-enrich|daily-ingest|daily-digest)\b'` — expect 6.
7. Starting tomorrow at 06:00 local: cron fires; 09:30 delivers digest. Watch 3 consecutive daily digests for Task 6.2 verdict.

### Scope boundary (hard)

Task 6.2 is a 3-day observation window — user runs, not autonomous.
Task 6.3 (STATE/ROADMAP/VALIDATION finalization) runs after Task 6.2
verdict. Phase 6 and beyond remain untouched.

**Earlier v3.2 milestone status (retained for history):**

Milestone: v3.2 (Batch Reliability + Infra) — AUTONOMOUS EXECUTION COMPLETE
Phases shipped: 12, 13, 15, 16, 17 fully; 14 partial (14-02 harness ready; 14-01 + 14-03 punched to Hermes)
Head commit: 2c9d310
Status: Awaiting Hermes to close Gate 3 (fixture scrape + E2E batch run)
Last activity: 2026-05-01 -- Milestone v3.2 autonomous execution landed, pushed to origin/main

**See:**
- `docs/MILESTONE_v3.2_EXECUTION_REPORT.md` — full wave-by-wave run report
- `docs/HERMES_V3.2_PUNCH_LIST.md` — what Hermes must do to close the milestone

**Milestone v3.1 goal:** Rebuild and locally verify single-article ingestion against `test/fixtures/gpt55_article/` — text ingest + graph connectivity in <2 min with no crash; async Vision worker appends image sub-docs after ingest path returns. This unblocks Phase 5 Wave 1+ (RSS, daily digest, cron).

**v3.1 phase structure (26 REQs across 4 phases):**

- **Phase 8: Image Pipeline Correctness** — IMG-01..04 (4 REQs); self-contained module changes in `image_pipeline.py`
- **Phase 9: Timeout Control + LightRAG State Management** — TIMEOUT-01..03 + STATE-01..04 (7 REQs); foundation for rollback semantics
- **Phase 10: Scrape-First Classification + Text-First Ingest Decoupling** — CLASS-01..04 + ARCH-01..04 (8 REQs); core pipeline rebuild
- **Phase 11: E2E Verification Gate** — E2E-01..07 (7 REQs); milestone close, <2min text-ingest + `benchmark_result.json`

**Carve-outs (future milestones):**

- v3.2 Batch Reliability: checkpoint/resume, Vision cascade circuit breaker, regression fixtures, operator runbook
- v3.3 Infra: Vertex AI SA migration + GCP project isolation
- Phase 5-00b full re-run on Hermes (belongs in Phase 5, unblocked by v3.1)

## Performance Metrics

**Velocity:**

- Total plans completed: 3
- Average duration: ~55 min (range: ~25 min for 04-01 to ~2h for 04-00 with checkpoint)
- Total execution time: ~3h

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 4 | 3/8 | ~3h | ~55 min |

**Recent Trend:**

- Last 5 plans: 04-00 (~2h, checkpoint), 04-01 (~25 min, TDD), 04-05 (~25 min, markdown skill), 04-02 (~15 min), 04-03 (~25 min), 04-04 (~5 min)
- Trend: Improving — Wave 3 plan executed extremely fast (~5 min TDD)

*Updated after each plan completion*
| Phase 06-graphify-addon-code-graph P00 | 5 | 2 tasks | 11 files |
| Phase 06-graphify-addon-code-graph P01 | 25 | 3 tasks | 2 files |
| Phase 06-graphify-addon-code-graph P03 | 9 | 4 tasks | 6 files |
| Phase 06-graphify-addon-code-graph P04 | 17 | 2 tasks | 1 files |
| Phase 07-model-key-management P02 | 20m | 7 tasks | 9 files |
| Phase 07-model-key-management P03 | 25m | 7 tasks | 6 files |
| Phase 07-model-key-management P04 | 45m | 10 tasks | 19 files |
| Phase 05 P00c | 21 min | 6 tasks | 13 files |
| Phase 09 P00 | 6min | 3 tasks | 5 files |
| Phase 09 P01 | 9min | 2 tasks | 11 files |
| Phase 10 P00 | 6min | 3 tasks | 4 files |
| Phase 11 P00 | 18min | 1 tasks | 2 files |
| Phase 11 P02 | 55 | 2 tasks | 5 files |

## Accumulated Context

### Roadmap Evolution

- 2026-04-30 — Milestone v3.1 started. 26 requirements drafted (v1 after Hermes review pass). Roadmap derived: 4 phases (8-11) grouped as image-pipeline / state+timeout / ingest-decoupling / E2E-gate. Phase 11 is the milestone-close gate (<2min text ingest + `benchmark_result.json`).
- 2026-04-28 — Phase 6 added: graphify-addon-code-graph. PRD v3.0 at `specs/PRDTDD_GRAPHIFY_ADDON.md`; pre-plan brief at `.planning/phases/06-graphify-addon-code-graph/06-CONTEXT.md`. Invariants D-G01..D-S10 locked. Independent of Phase 5.

### Decisions

Decisions are logged in PROJECT.md Key Decisions table and `.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md`.
Recent decisions affecting current work:

- Phase 4: 16 locked decisions captured in 04-CONTEXT.md (D-01 through D-16)
- Phase 4: Hermes review integrated 2026-04-27 — Draft.js input method, grounding fallback, URL capture, zhimg sizing
- 04-00: Orchestrator captured golden fixtures via SSH (human-action checkpoint); all 3 remote articles had metadata.images==2, captured all 3 (acceptance criteria met)
- 04-00: LightRAG spike script created locally; remote execution is the Wave 1 gate (phase0_spike_report.md) — pending at time of this STATE update
- 04-01: TDD-first refactor; image_pipeline.py exports 4 public functions; ingest_wechat.py had two orphans cleaned (removed `from PIL import Image` and a stale `describe_image()` call in `ingest_pdf`)
- 04-05: Pure-Markdown Hermes skill (D-02); task 5.3 remote connectivity smoke-test passed; full E2E skill invocation deferred (requires interactive Hermes session after deploy)
- 04-06: enrich_article top-level skill (D-01/D-02); 208-line SKILL.md with 4-step orchestration + per-question for-loop; deployed via scp (remote has untracked zhihu-haowen-enrich blocking git checkout); `hermes skills list` confirmed `enrich_article | local | local | enabled`
- [Phase 06-graphify-addon-code-graph]: graphifyy==0.5.3 installed with tree-sitter grammars; binary invoked via python -m graphify on Windows
- [Phase 06-graphify-addon-code-graph]: D-S10 scope = hermes-only (claw absent on remote, confirmed by SSH probe)
- [Phase 06-graphify-addon-code-graph]: D-G09 honored: omnigraph_search/query.py mirrors query_lightrag.py with no Cognee, no get_rag() helper
- [Phase 06-graphify-addon-code-graph]: Added omnigraph_search/__init__.py to enable python -m invocation (required for package module)
- [Phase 06]: Use graphify update (not graphify build/refresh) for cron — build/refresh subcommands do not exist in Graphify CLI 0.5.3
- [Phase 06]: to_json() shrink guard satisfies D-G06 atomic-swap intent — no custom tmp-rename needed
- [Phase 07-model-key-management]: D-11 config.py shims landed as wrapper (not delete) — 2 remaining callers access response.text via _GeminiCallResponse back-compat
- [Phase 07-model-key-management]: enrichment/*.py files have zero direct Gemini calls — skipped source migration per Simplicity First; only D-06 test patch target updates landed
- [Phase 07-model-key-management] Wave 4 (07-04): Amendment 3 sweeper DELETED config.py D-11 shims + gemini_call + _GeminiCallResponse wrapper. lib.models is single source of truth. D-11 original "retain shims indefinitely" text officially superseded.
- [Phase 07-model-key-management] Wave 4: ingest_wechat.extract_entities was last gemini_call caller at start of Wave 4; migrated to lib.generate_sync in pre-sweep commit before Task 4.7 sweeper ran.
- [Phase 07-model-key-management] Wave 4: Hermes FLAGs (standalone Cognee rotation caveat + DEEPSEEK_API_KEY import-time coupling) landed as documentation-only in Deploy.md + CLAUDE.md per review verdict.
- [Phase 07-model-key-management] Wave 4: skill_runner._GEMINI_MODEL kept as string literal per Open Q #4 (test-harness independence from production INGESTION_LLM drift).
- [Phase 05]: Plan 05-00c: LightRAG LLM routed to DeepSeek (deepseek-v4-flash); Gemini embed now has 2-key rotation + 429 failover across GEMINI_API_KEY + GEMINI_API_KEY_BACKUP; Cognee stays on Gemini (negligible volume, Phase 7 D-04 propagation already suffices); Wave 0 runtime (05-00) is now unblocked
- [Milestone v3.1]: 26 REQs across IMG / CLASS / STATE / ARCH / TIMEOUT / E2E groups; ARCH-03 resolved as append-sub-doc (NOT re-embed) per Hermes review; STATE-04 added to change `get_rag()` API contract (root cause of STATE-01 history-debt replay); E2E-07 added to codify `benchmark_result.json` schema for CI regression
- [Milestone v3.1]: Phase boundaries derived from tight-coupling analysis — TIMEOUT+STATE together (outer wait_for triggers rollback; flush contract prevents replay), CLASS+ARCH together (scrape-first enables full-text classify which enables text-first ingest), IMG standalone (self-contained), E2E last (depends on all prior work)
- [Phase 09]: Plan 09-00: TIMEOUT-02 idiom = bare float 'timeout=120.0' (no httpx dependency); openai SDK interprets as total request timeout
- [Phase 09]: Plan 09-00: TIMEOUT-03 wrap site = CONTEXT option (c), 900s floor at url-only call site. Full chunk-count scaling deferred to Phase 10 when scrape/ingest decouple.
- [Phase 09]: Plan 09-00: _compute_article_budget_s exposed at module scope (not closure) so Plan 09-01 / Phase 10 can consume once full_content is known
- [Phase 09]: Plan 09-01: Clear-on-success-only doc_id tracker (not try/finally) — orchestrator reads tracker after TimeoutError; cleanup in orchestrator finally after rollback. Avoids race where finally clears tracker before orchestrator reads it during cooperative cancellation.
- [Phase 09]: Plan 09-01: get_rag(flush=True) is now the production contract at 7 production call sites; 3 spike scripts use flush=False for historical reuse-prior-state semantics. Source-grep test enforces no bare get_rag() calls survive.
- [Phase 10]: Plan 10-00: scrape-first classify flow locked — classification reads full body (not digest), writes classifications row BEFORE ingest decision, no fail-open on DeepSeek failure. Schema migration is ADDITIVE (D-10.04 option a): new `classifications.{depth, topics, rationale}` + `articles.body` columns coexist with legacy columns for batch-scan back-compat.
- [Phase 10]: Plan 10-00: full-body DeepSeek prompt returns a single JSON OBJECT `{depth: 1-3, topics: [...], rationale: str}` (distinguishes from legacy batch prompt's JSON array). Truncation budget `FULLBODY_TRUNCATION_CHARS=8000` per D-10.02.
- [Phase 10]: Plan 10-00: `ingest_from_db` SELECT changed from INNER JOIN to LEFT JOIN on classifications (per-article classify happens inside the loop); depth filtering moved from SQL WHERE clause to post-classify Python check.
- [Phase 11]: Plan 11-00: `scripts/bench_ingest_fixture.py` scaffolded with pure helpers (`_read_fixture`, `_compute_article_hash`, `_utc_now_iso`, `_build_result_json`, `_write_result`, `_balance_precheck`, `_time_stage`). stdlib-only HTTP for balance precheck (no new `requests` dep). Atomic write via tmp + os.rename + on-failure cleanup. PRD-exact 9-key schema. Stage stubs await `asyncio.sleep(0)` so timings are near-zero in stub mode — Plan 11-02 replaces stubs with real LightRAG invocations. 16 unit tests added; regression 162 → 178 passing.
- [Phase 11]: Plan 11-00: SiliconFlow balance precheck catches URLError, HTTPError, JSONDecodeError, ValueError, TimeoutError, OSError — always returns a dict, never raises; caller appends to `warnings[]`. Field path `data.balance` documented with TODO to reconfirm against live response in 11-02 (non-fatal if shape differs — `balance_precheck_failed` branch catches).
- [Phase 11]: Plan 11-02: real LightRAG wiring — get_rag(flush=True), rag.ainsert(full_content, ids=[wechat_<hash>]), rag.aquery(query='GPT-5.5 benchmark results', QueryParam(mode='hybrid', top_k=3)), asyncio.create_task(_vision_worker_impl(...)) with 120s drain cap. 5 unit-mocked integration tests + 1 live-skipif test.
- [Phase 11]: Plan 11-02 Rule 3 auto-fixes: (1) os.rename -> os.replace for Windows overwrite; (2) sys.path bootstrap for scripts/ direct invocation; (3) config.py + ingest_wechat.py guard GOOGLE_* env pops on GOOGLE_APPLICATION_CREDENTIALS being set (preserve D-11.08 Vertex opt-in); (4) RAG_WORKING_DIR env override for dim-mismatch isolation.
- [Phase 11]: Plan 11-02 live gate run: text_ingest_ms=18348 (6.5× under 120s budget via Vertex AI), zero_crashes=true, aquery_returns_fixture_chunk=false (dummy DEEPSEEK_API_KEY -> LightRAG synthesis returns None). gate_pass=false. Harness verified working end-to-end; gate_pass blocked only by credential gap.

### Pending Todos

None tracked.

### Blockers/Concerns

- Phase 4 runtime depends on remote Edge CDP (`localhost:9223`) being available for Zhihu fetch integration tests; integration tests in wave 2+ may be stubbed until a live CDP is reachable.
- **Gemini free-tier quotas (environmental, phase-4 exit blocker for LightRAG full graph ingest)**: `gemini-embedding-*` 100 RPM per project. LightRAG's entity upsert stage fires bursts of ~60+ embeddings per doc; even with `embedding_func_max_async=1` + `embedding_batch_num=20` throttle (committed in `0faab0c`), per-doc bursts still saturate the window. Code path PROVEN CORRECT — LLM entity extraction + caching succeeds; only the downstream embedding upsert 429s. Documented in `docs/testing/04-07-validation-results.md`. Resolution: Gemini paid Tier 1 (removes RPM limits) OR swap to local `sentence-transformers` OR add per-entity semaphore. All out of Phase 4 scope.
- **SQLite migration deployment gap RESOLVED** in `9e2a0c1`: `ingest_wechat.py` now auto-runs `batch_scan_kol.init_db(DB_PATH)` at module import (guarded by `DB_PATH.exists()`). Idempotent via `_ensure_column`.
- **Spike script async race (non-blocking)**: `scripts/phase0_delete_spike.py` doesn't await LightRAG's async entity extraction before measuring counts — its report contract passes but entity counts are vacuous. Documented in `phase0_spike_report.md`. Not blocking; ticketable refactor later.
- **Plan 05-00 COMPLETE** (2026-04-29, user-run on Hermes host). Final graph: 263 nodes / 301 edges / 29 docs / 19 chunks at 3072 dim. Dual-key rotation + Deepseek LLM swap (via Plan 05-00c) held up on real workloads. See `.planning/phases/05-pipeline-automation/05-00-SUMMARY.md` for full journey (6 attempts, key rotation bug diagnosis, Option A baseline skip, per-doc cost correction to ~300 embeds/doc).
- **Plan 05-00b PARTIAL** — 9/31 keyword-matched KOL articles ingested; 22 blocked by `subprocess.run(capture_output=True)` pipe deadlock in the user's ad-hoc batch runner (`batch_ingest_from_spider.py` itself uses `capture_output=False` and is NOT susceptible). Per user's `docs/phase5-00c-execution-report.md`. Remaining unblockers: multi-keyword `--topic-filter` (DONE — quick-task 260429-got, commit `4bf1613`); schema consistency (`digest` vs `content_preview`); and actually running the remaining 22 articles via `batch_ingest_from_spider.py --from-db --topic-filter "openclaw,hermes,agent,harness" --min-depth 2`.
- **Cognee dotenv override side-effect** — `cognee/__init__.py:11` calls `dotenv.load_dotenv(override=True)` which reads gitignored repo-root `.env` (stale leftover) and overwrites `GEMINI_API_KEY`. Patched at runtime during Attempt 6 diagnosis; permanent fix pending (delete the stale file OR re-assert env post-Cognee-import). Infra-track item, not blocking.
- **v3.1 gate is LOCAL fixture only** — CLASS-03 WeChat anti-abuse params are spec-correctness for the BATCH path Phase 5 will invoke; v3.1 tests against `test/fixtures/gpt55_article/` so WeChat rate-limiting is not exercised. Watch for temptation to "verify" CLASS-03 with a live WeChat scrape during Phase 10.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260429-got | Extend `batch_ingest_from_spider.py` --topic-filter to comma-separated multi-keyword (D-11) | 2026-04-29 | `4bf1613` | [260429-got-extend-batch-ingest-from-spider-py-to-su](./quick/260429-got-extend-batch-ingest-from-spider-py-to-su/) |
| 260503-lq7 | Wave 1 post-E2E hygiene: RSS classify env cap + step_6 fetched_at/scanned_at fix | 2026-05-03 | `16f05ae` | [260503-lq7-wave-1-post-e2e-hygiene-rss-classify-env](./quick/260503-lq7-wave-1-post-e2e-hygiene-rss-classify-env/) |
| 260503-m4q | Vertex embedding correction — remove preview alias, embrace GA global endpoint (pre-06:00 ADT Day-1 cron fix) | 2026-05-03 | `f6be225` | [260503-m4q-vertex-embedding-correction-remove-previ](./quick/260503-m4q-vertex-embedding-correction-remove-previ/) |

## Phase 4 Exit State

**Wave 5 (04-07) complete + live-validated.** Committed on `gsd/phase-04` through `0faab0c`.

**Criteria flip from `docs/testing/04-06-test-results.md §4`:**

- 7 `final_content.enriched.md` ✅ PASS — written to disk via `638a615`; 3 `### 问题 N:` inline summaries with real Zhihu content
- 8 D-03 JSON `status=ok` ✅ PASS — `{"status":"ok","enriched":2,"success_count":3,"zhihu_docs_ingested":3,"enrichment_id":"enrich_8ac04218b4"}`
- 9 `articles.enriched=2` ✅ PASS — verified via SQL (after seeding the missing article row — the test article was scraped directly, not via `batch_scan_kol`)
- 10 `ingestions.enrichment_id=enrich_8ac04218b4` ✅ PASS — verified via SQL
- 11 LightRAG graph grew ⚠️ INFRA-BLOCKED — graph at 713/820 unchanged; Gemini embedding 100 RPM hit
- 12 No new `failed` doc statuses ⚠️ INFRA-BLOCKED — cleaned post-validation; same root cause as #11

**Post-validation production graph:** 713 nodes / 820 edges / 18 docs (baseline preserved).

## Session Continuity

Last session: 2026-05-01T02:36:13.366Z
Stopped at: Completed 11-02-PLAN.md — milestone v3.1 gate harness delivered
Resume file: None
Next command: `/gsd:execute-phase 10` (execute Plan 10-01 — Text-First Ingest Split, ARCH-01 / D-10.05)

## Phase 6 Exit State

Phase 6 (graphify-addon-code-graph) — CLOSED 2026-05-03 (ROADMAP + STATE admin finalization; code + SUMMARY landed 2026-04-28 @ d59e3ae).
ACCEPT WITH PARTIALS: 7/8 REQ PASS, REQ-02 PARTIAL (claw absent per D-S10).

Shipped:

- graphify skill on Hermes (zero-code install, graphifyy 0.5.3)
- omnigraph_search SKILL.md + query.py (thin LightRAG wrapper)
- Weekly cron graphify-refresh.sh (AST-only, atomic via to_json shrink guard)
- Demo 1 + Demo 2 both passed (agent autonomously routes to both skills)

Deferred:

- REQ-02 full verification (claw install on remote)
- Bridge nodes (D-G07)
- Hermes-agent in T1 repos (would complete Demo 2 code-layer gap)
