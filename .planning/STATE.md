---
gsd_state_version: 1.0
milestone: v3.1
milestone_name: — Single-Article Ingest Stability ✅ CLOSED
status: phase-complete
stopped_at: "Phase 19 shipped — lib/scraper.py + KOL line-940 hotfix + SHA-256 hash + rss_articles ALTER. Hermes operator runbook in 19-DEPLOY.md (SSH verify pending-operator)."
last_updated: "2026-05-05T19:35:00Z"
last_activity: 2026-05-05 — Completed quick task 260505-m9e: bump OMNIGRAPH_LLM_TIMEOUT_SEC default 600→1800 + persist scraped body before classify (eliminates SCR-06-class data loss); 4 new mock-only unit tests GREEN
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 4
  completed_plans: 4
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-03)

**Core value:** Local, graph-based personal knowledge base that gives Hermes/OpenClaw persistent memory — WeChat scan → classify → LightRAG ingest → synthesis.
**Current focus:** Phase 19 complete (pending operator SSH verify) — Phase 20 is NEXT; v3.4 execute gate remains BLOCKED until Day-1/2/3 KOL baseline complete (~2026-05-06 ADT).

## Current Position

Milestone: v3.4 (RSS-KOL Alignment)
Phase: 20 (RSS Full-Body Classify + Multimodal Ingest + Cognee Fix) — NEXT; Phase 19 complete
Plan: — (Phase 19 shipped 4 plans; next is `/gsd:plan-phase 20`)
Status: Phase 19 shipped (pending operator Hermes SSH verify per 19-DEPLOY.md). Phase 20 execute BLOCKED until Day-1/2/3 KOL baseline complete (~2026-05-06 ADT).
Execute gate: BLOCKED until Day-1/2/3 KOL baseline observation complete (~2026-05-06 ADT)
Last activity: 2026-05-05 — Completed quick task 260505-s1h: read-only audit of CDP/MCP/UA scraper-layer return shapes vs `lib/scraper.py:_scrape_wechat` consumer. Found 1🔴 silent data loss (UA `img_urls` vs consumer `images`) + 2🟡 (Apify markdown image regex absent in new consumer; CDP `body` fallback noise). Report at `docs/research/scraper_layer_shape_audit_2026_05_05.md`; zero source-code changes

### Immediate next step

Operator (user) runs `.planning/phases/19-generic-scraper-schema-kol-hotfix/19-DEPLOY.md` on Hermes:
  1. SSH per `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_ssh.md`
  2. `cd ~/OmniGraph-Vault && git pull --ff-only`
  3. `source venv/bin/activate` (Linux layout — NOT `venv/Scripts/`)
  4. `pip install -r requirements.txt`
  5. `python scripts/checkpoint_reset.py --all --confirm` (one-time SHA-256 migration)
  6. `python -m pytest tests/ -q` (expect ≈ 464 passed / ≤ 13 pre-existing failed; all 8 Phase-19 tests GREEN)
  7. `python batch_ingest_from_spider.py --from-db --topic-filter Agent --min-depth 2 --max-articles 1 --dry-run` (expect CLI parse, exit 0)

After operator reports back with verdict (`approved` / `issues: <...>`):
  - If approved → wait for Day-1/2/3 KOL baseline (~2026-05-04 → 2026-05-06 ADT) to complete, then resume with `/gsd:plan-phase 20`
  - If issues → open a follow-up `/gsd:quick` or revision plan; do NOT advance to Phase 20

**Execute gate rationale:**

- Tuning decisions (subprocess timeout, max-articles cap, concurrency) require real cron data from Day-1/2/3 runs
- Must verify Day-1 KOL pipeline is stable on the Vertex-corrected code path before RSS alignment amplifies any instability
- No code changes in phases 19-22 until gate lifts

### v3.4 Phase Overview

| Phase | Goal | REQs | Execute gate |
|-------|------|------|--------------|
| 19 | Generic scraper module + KOL line-940 hotfix + schema ALTER + hash migration | SCR-01..07, SCH-01..02 (9) | BLOCKED ~2026-05-06 |
| 20 | RSS full-body classify port + rss_ingest.py 5-stage rewrite | RCL-01..03, RIN-01..06 (9) | BLOCKED + depends Phase 19 |
| 21 | STK-01 NanoVectorDB spike (30min, first task) + CLI tool + RSS E2E fixture + bench harness | STK-01..03, E2R-01..02 (5) | BLOCKED + depends Phase 20 |
| 22 | 1020-article backlog re-ingest + cross-arm smoke + stuck-doc isolation test + cron cutover | BKF-01..03, E2R-03..04, CUT-01..03 (10) | BLOCKED + depends Phase 21 |

### Parallel: Day-1/2/3 KOL cron observation (NOT v3.4 execute scope)

Day-1 fires 2026-05-04 06:00 ADT with KOL-only cron body.
Day-2 RSS cutover DEFERRED until v3.4 Phase 22 (CUT-01) completes.
Observation only — no active intervention during Day-1/2/3 window.
After Day-3 verdict: lift execute gate, begin `/gsd:plan-phase 19`.

### v3.3 closed state (retained for history)

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
| Phase 19 P00 | 5min | 3 tasks | 5 files |
| Phase 19 P01 | 6min | 3 tasks | 2 files |
| Phase 19 P02 | 23min | 4 tasks | 7 files |
| Phase 19 P03 | 5min | 3 tasks (3.3 pending-operator) | 3 files |

## Accumulated Context

### Roadmap Evolution

- 2026-05-03 — Milestone v3.4 RSS-KOL Alignment started. 31 requirements across 8 categories (SCR/SCH/RCL/RIN/STK/BKF/E2R/CUT). Roadmap derived: 4 phases (19-22) structured as Wave 1 (scraper+schema) / Wave 2 (classify+ingest rewrite) / Wave 3a (spike+CLI+fixture) / Wave 3b (backlog+smoke+cutover). Wave 3 split into 2 phases because STK-01 diagnostic spike must complete before STK-02/03 CLI code is written, and BKF/CUT cannot run until E2R validates end-to-end correctness.
- 2026-04-30 — Milestone v3.1 started. 26 requirements drafted (v1 after Hermes review pass). Roadmap derived: 4 phases (8-11) grouped as image-pipeline / state+timeout / ingest-decoupling / E2E-gate. Phase 11 is the milestone-close gate (<2min text ingest + `benchmark_result.json`).
- 2026-04-28 — Phase 6 added: graphify-addon-code-graph. PRD v3.0 at `specs/PRDTDD_GRAPHIFY_ADDON.md`; pre-plan brief at `.planning/phases/06-graphify-addon-code-graph/06-CONTEXT.md`. Invariants D-G01..D-S10 locked. Independent of Phase 5.

### Decisions

Decisions are logged in PROJECT.md Key Decisions table and `.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md`.
Recent decisions affecting current work:

- **[v3.4] D-RSS-SCRAPER-SCOPE = Option A** — `lib/scraper.py::scrape_url()` serves both KOL and RSS arms; patches `batch_ingest_from_spider.py:940` UA-only bug; 2:1 researcher consensus + user preference. Stack.md Option B rejected (incorrectly assumed KOL path not broken; Day-1 pre-flight disproved this).
- **[Phase 19 complete, 2026-05-04]** lib/scraper.py shipped with 4-layer WeChat cascade (apify → cdp → mcp → ua) + generic trafilatura cascade + 429 backoff + login-wall gate. batch_ingest_from_spider.py:940 SCR-06 hotfix landed (scrape_url, site_hint="wechat"). batch_ingest_from_spider.py:275 hash unified to get_article_hash (SHA-256 first 16). rss_articles ALTER added 5 nullable columns for Phase 20. 8 new unit tests GREEN; full regression 464 passed / 13 pre-existing failed / 0 new regressions. Hermes post-pull: `checkpoint_reset.py --all --confirm` wipes legacy MD5-10 dirs (see 19-DEPLOY.md). Task 3.3 operator SSH verify PENDING — STATE marks phase complete pre-emptively on dev-box green gate; operator runs 19-DEPLOY.md steps 1-5 and reports back `approved` or `issues: <...>`.
- **[v3.4] D-STUCK-DOC-IDEMPOTENCY = CLI tool** — `scripts/cleanup_stuck_docs.py`; NOT cron pre-hook. LightRAG self-heals FAILED docs on next `ainsert`; cron pre-hook would delete retryable docs. Wave 3 Phase 21 Task 1 = 30-min NanoVectorDB spike to resolve Delta 2 confidence gap before building CLI.
- **[v3.4] Wave 3 split into Phase 21 + Phase 22** — STK-01 spike outcome may change STK-02/03 design; BKF backlog and CUT cutover must not run before E2R validates full pipeline. Phase 21 = spike + tools + fixtures; Phase 22 = operational bulk work + cutover.
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
- [Phase 19]: [Phase 19-00]: Wave 0 scaffolding complete — trafilatura 2.0.0 + lxml 5.4.0 pinned, 3 RED test files (8 pytest.fail stubs) wired to SCR-01..06 + SCH-01..02 task-IDs
- [Phase 19]: [Phase 19-00]: lxml pinned <6 per SCR-07 authoritative spec; 19-RESEARCH.md Pitfall 5 relaxation deferred to v3.5 follow-up
- [Phase 19]: Layer 3 of generic cascade (CDP/MCP) deferred to Phase 20 — falls through to summary_only fallback rather than raising (D-RSS-SCRAPER-SCOPE Option A)
- [Phase 19]: ScrapeResult.content_html preserved on WeChat path so batch_ingest_from_spider.py:940 consumer keeps working — zero API break for existing code
- [Phase 19]: scrape_url never raises — returns summary_only=True on cascade exhaustion so callers decide to skip (graceful cascade semantics)
- [Phase 19]: Plan 19-02: SCH-02 hash unification required a Rule 1 auto-fix in ingest_wechat.py — the _pending_doc_ids tracker key was switched from article_hash (MD5[:10]) to ckpt_hash (SHA-256[:16]) across 4 call sites. The image-dir namespace (BASE_IMAGE_DIR/{article_hash}) and LightRAG doc_id (wechat_{article_hash}) still use MD5[:10] — only the in-memory tracker registry KEY changed. This preserves STATE-02/03 rollback semantics.
- [Phase 19]: Plan 19-02: batch_ingest_from_spider.py:940 KOL hotfix (SCR-06) now routes via lib.scraper.scrape_url(url, site_hint='wechat') which runs the full 4-layer WeChat cascade (apify → cdp → mcp → ua). Closes Day-1 06:00 ADT regression where UA-only path was the sole fallback when Apify/CDP were misconfigured.
- [Phase 19]: Plan 19-02: enrichment/rss_schema.py::_ensure_rss_columns uses PRAGMA table_info pre-check + conditional ALTER (not try/except OperationalError). Produces zero SQL on second call, idempotent, idiomatic SQLite pattern. Adds 5 nullable columns to rss_articles: body, body_scraped_at, depth, topics, classify_rationale — Phase 20 RCL-03 prerequisite.

### Pending Todos

None tracked.

### Blockers/Concerns

- **Execute gate (primary blocker):** All v3.4 phase execution blocked until Day-1/2/3 KOL cron baseline (~2026-05-06 ADT). After gate lifts, run `/gsd:plan-phase 19` to begin.
- **STK-01 diagnostic spike (Wave 3 constraint):** NanoVectorDB cleanup completeness for `adelete_by_doc_id` has a MEDIUM-confidence open question from the Pitfalls research. The 30-min spike in Phase 21 must run before any CLI code is written. Spike outcome may adjust STK-02/03 scope.
- **SCR-06 KOL regression risk:** The line-940 hotfix (Phase 19) touches a live KOL code path. E2R-04 cross-arm smoke in Phase 22 is the designated regression gate before CUT-01 cron cutover. Do not cut over cron before cross-arm smoke passes.
- **SiliconFlow balance for 1020-article backlog:** ~2,630 images at ¥0.0013/image ≈ ¥3.42 minimum; budget ≥¥10 before starting Phase 22 BKF backlog. Operator pre-flight item, not a code blocker.
- Phase 4 runtime depends on remote Edge CDP (`localhost:9223`) being available for Zhihu fetch integration tests; integration tests in wave 2+ may be stubbed until a live CDP is reachable.
- **Gemini free-tier quotas (environmental, phase-4 exit blocker for LightRAG full graph ingest)**: `gemini-embedding-*` 100 RPM per project. LightRAG's entity upsert stage fires bursts of ~60+ embeddings per doc; even with `embedding_func_max_async=1` + `embedding_batch_num=20` throttle (committed in `0faab0c`), per-doc bursts still saturate the window. Code path PROVEN CORRECT — LLM entity extraction + caching succeeds; only the downstream embedding upsert 429s. Documented in `docs/testing/04-07-validation-results.md`. Resolution: Gemini paid Tier 1 (removes RPM limits) OR swap to local `sentence-transformers` OR add per-entity semaphore. All out of Phase 4 scope.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260429-got | Extend `batch_ingest_from_spider.py` --topic-filter to comma-separated multi-keyword (D-11) | 2026-04-29 | `4bf1613` | [260429-got-extend-batch-ingest-from-spider-py-to-su](./quick/260429-got-extend-batch-ingest-from-spider-py-to-su/) |
| 260503-lq7 | Wave 1 post-E2E hygiene: RSS classify env cap + step_6 fetched_at/scanned_at fix | 2026-05-03 | `16f05ae` | [260503-lq7-wave-1-post-e2e-hygiene-rss-classify-env](./quick/260503-lq7-wave-1-post-e2e-hygiene-rss-classify-env/) |
| 260503-m4q | Vertex embedding correction — remove preview alias, embrace GA global endpoint (pre-06:00 ADT Day-1 cron fix) | 2026-05-03 | `f6be225` | [260503-m4q-vertex-embedding-correction-remove-previ](./quick/260503-m4q-vertex-embedding-correction-remove-previ/) |
| 260503-sd7 | fix batch_ingest_from_spider topic filter case-sensitivity (Day-1 cron hard blocker) | 2026-05-03 | `e59bc42` | [260503-sd7-fix-batch-ingest-from-spider-topic-filte](./quick/260503-sd7-fix-batch-ingest-from-spider-topic-filte/) |
| 260503-v9z | Hotfix: gate Cognee inline `remember_article` behind `OMNIGRAPH_COGNEE_INLINE` (default off) — unblocks Day-1 KOL cron from LiteLLM→AI Studio 422 loop on `gemini-embedding-2` | 2026-05-04 | `3f6d065` | [260503-v9z-hotfix-disable-cognee-inline-call-blocki](./quick/260503-v9z-hotfix-disable-cognee-inline-call-blocki/) |
| 260504-g7a | Local dev enablement — 9 atomic fixes + MCP scraper tool rename (10 total): Vertex Gemini LLM provider, `llm_complete` dispatcher, `OMNIGRAPH_BASE_DIR` override, Vision skip-list, LOCAL_DEV_SETUP runbook, bootstrap scripts, 27 mock-only tests. Hermes zero breaking change (default provider still DeepSeek). | 2026-05-04 | `7a9d6c4` | [260504-g7a-enablement-local-testing-blockers-infras](./quick/260504-g7a-enablement-local-testing-blockers-infras/) |
| 260504-lt2 | KOL_SCAN_DB_PATH env override propagated to 11 remaining DB-path call sites (classify / scan / synthesize / cognee / 6× enrichment). Mirrors af6f5bc pattern from Quick 260504-g7a/e2e. 23 new mock-only tests (subprocess-isolated, all green); smoke re-run confirms core ingest path unchanged. Hermes production zero breaking change. | 2026-05-04 | `0674eb5` | [260504-lt2-propagate-kol-scan-db-path-env-override-](./quick/260504-lt2-propagate-kol-scan-db-path-env-override-/) |
| 260504-x9l | Local 5-article cold-graph pilot for new 5-knob LightRAG config (`e833206`). 2394 s wall-clock / 222.43 s avg-per-article / 5 ok / 23 skipped / 0 failed; graph 0→253 nodes / 309 edges. Apify scrape success rate 18% in this slice (D-10.04 path). D-10.09 async-drain hang surfaced again. Report neutral, no rollback recommendation. | 2026-05-05 | `ade536d` | [260504-x9l-5-article-batch-ingest-pilot-new-lightra](./quick/260504-x9l-5-article-batch-ingest-pilot-new-lightra/) |
| 260505-m9e | Bump `OMNIGRAPH_LLM_TIMEOUT_SEC` default 600→1800 (60-image articles 100% timeout at prior default); persist scraped body atomically before `_classify_full_body` so downstream classify/ingest failures no longer lose body content (eliminates SCR-06-class data loss). 4 new mock-only unit tests GREEN. Honors hard scope: untouched `lib/scraper.py`, `lib/lightrag_embedding.py`, LightRAG config, async-drain hang, graded probe. | 2026-05-05 | `239f4a0` | [260505-m9e-fix-llm-timeout-default-and-persist-body](./quick/260505-m9e-fix-llm-timeout-default-and-persist-body/) |
| 260505-s1h | Read-only audit of CDP/MCP/UA scraper-layer return shapes vs `lib/scraper.py:_scrape_wechat` consumer — find SCR-06-class latent bugs before 06:00 ADT cron. Report at `docs/research/scraper_layer_shape_audit_2026_05_05.md`. Findings: **1🔴** silent data loss (UA returns `img_urls` but consumer reads `images`; every UA-fallback article loses pre-HTML image list vs legacy `ingest_article` line 951 merge), **2🟡** (Apify markdown image regex absent in new consumer; CDP `body` fallback noise). All recommendations DEFERRED — zero source-code changes per audit-only scope. Side-commit `e15c17a` (CLAUDE.md afternoon lessons) authorized post-hoc by user. | 2026-05-05 | `ece03ae` | [260505-s1h-scraper-layer-return-shape-audit-cdp-mcp](./quick/260505-s1h-scraper-layer-return-shape-audit-cdp-mcp/) |

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

Last session: 2026-05-04T02:43:16Z
Stopped at: Completed 19-03-PLAN.md (Wave 3: regression gate + 19-DEPLOY.md + STATE close-out; Task 3.3 Hermes SSH verify pending operator)
Resume file: None
Next command: Operator runs `19-DEPLOY.md` on Hermes → reports verdict; then wait for Day-1/2/3 KOL baseline (~2026-05-06 ADT) to lift execute gate → resume with `/gsd:plan-phase 20`

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
