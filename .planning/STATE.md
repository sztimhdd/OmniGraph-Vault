---
gsd_state_version: 1.0
milestone: v3.1
milestone_name: Next — Single-Article Ingest Stability
current_plan: "1 / Total Plans in Phase: 2"
status: executing
stopped_at: Completed 09-00-PLAN.md — Timeout layer (TIMEOUT-01/02/03). Ready for 09-01 STATE-01..04.
last_updated: "2026-05-01T00:41:09.878Z"
last_activity: 2026-04-30 — Plan 09-00 complete (TIMEOUT-01/02/03 landed; 10 new unit tests; Phase 8 regression 22/22 still green)
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 4
  completed_plans: 2
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-30)

**Core value:** Local, graph-based personal knowledge base that gives Hermes/OpenClaw persistent memory — WeChat scan → classify → LightRAG ingest → synthesis.
**Current focus:** Milestone v3.1 — Single-Article Ingest Stability (prerequisite to Phase 5 Wave 1+)

## Current Position

Phase: **Phase 9 — Timeout Control + LightRAG State Management**
Current Plan: 1 / Total Plans in Phase: 2
Plan: **09-01 — State Management (STATE-01..04)** — next, ready to execute
Status: In Progress — Plan 09-00 (TIMEOUT layer) complete
Last activity: 2026-04-30 — Plan 09-00 complete (TIMEOUT-01/02/03 landed; 10 new unit tests; Phase 8 regression 22/22 still green)

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

Last session: 2026-05-01T00:40:44.688Z
Stopped at: Completed 09-00-PLAN.md — Timeout layer (TIMEOUT-01/02/03). Ready for 09-01 STATE-01..04.
Resume file: None
Next command: `/gsd:plan-phase 8` (break down Phase 8: Image Pipeline Correctness)
