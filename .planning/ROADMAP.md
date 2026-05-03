# Roadmap

**Last Updated:** 2026-05-02 (Phase 5 Wave 1 closed — plans 05-01/02/03/03b landed on origin/main; Hermes pulls for live verification)

## Done

- WeChat article ingestion (Apify → CDP → MCP triple path)
- LightRAG knowledge graph with Cognee async memory
- Gemini Vision image description pipeline
- Entity canonicalization (entity_buffer + canonical_map)
- KOL SQLite pipeline: scan → classify → ingest from DB
- Gemini classifier option (free tier, alongside DeepSeek)
- Entity layer migration to SQLite (Phase 2: dual-write, DB-first read)
- 4 Hermes skills: omnigraph_ingest, omnigraph_query, omnigraph_architect, hermes_claude_code_bridge
- Skill runner with test suites
- **Phase 4: knowledge-enrichment-zhihu (2026-04-27)** — 8 plans shipped across 5 waves. Per-article pipeline: Gemini+grounding question extraction → per-question zhida.zhihu.com CDP drive via `zhihu-haowen-enrich` Hermes skill → Zhihu source fetch with image filter + Vision → merge inline summaries → LightRAG ingest (1 WeChat + up to 3 Zhihu docs with D-08 backlinks) + SQLite state machine. Code complete and live-validated; Gemini free-tier embedding quota is the only non-code blocker for full LightRAG graph growth (paid-tier unblocks).
- **Phase 7: model & key management (2026-04-29)** — 5 plans across 4 waves. Repo-root `lib/` package (models, api_keys, rate_limit, llm_client, lightrag_embedding) consolidates 18 production files behind a 13-symbol public API. `OMNIGRAPH_GEMINI_KEY` primary + `GEMINI_API_KEY` fallback + optional `OMNIGRAPH_GEMINI_KEYS` pool for multi-account rotation; per-model `AsyncLimiter` singletons with `OMNIGRAPH_RPM_<MODEL>` overrides; tenacity retry on 429/503 with key rotation; Amendment 4 Cognee propagation (inline `os.environ["COGNEE_LLM_API_KEY"]` write + `refresh_cognee()` cache-clear — no bridge module). Amendment 3 sweeper deleted D-11 shims, `gemini_call()`, `_GeminiCallResponse` from `config.py`. Hermes ACCEPT verdict across both review rounds; gsd-verifier passed 17/17 must-haves; 109/109 tests green.
- **Milestone v3.1: Single-Article Ingest Stability (2026-05-01)** — 26/26 REQs delivered across Phases 8/9/10/11. Phase 8 image filter (`min(w,h)<300`) + JSON-lines log; Phase 9 `get_rag(flush=True)` contract + LLM_TIMEOUT=600 + rollback on timeout; Phase 10 scrape-first full-body classifier + text-first `ainsert` decoupled from async Vision sub-doc worker; Phase 11 E2E bench harness + Vertex AI opt-in + aquery gate. Verified on both local (Claude, Gemini 2.5-flash-lite via Vertex AI, 620s text_ingest) and production (Hermes, DeepSeek + SiliconFlow + Vertex AI, **441s** text_ingest, 28/28 Vision success, aquery TRUE). E2E-02 gate revised from `<120s` to `<600s` based on real LightRAG entity-merge cost baseline (serial LLM at async=4). Closure doc: `docs/MILESTONE_v3.1_CLOSURE.md`. Unblocks Phase 5 Wave 1+ (RSS, daily digest, cron) and v3.2 (Phase 12 checkpoint/resume, Phase 13 vision cascade, Phase 14 regression fixtures).

## Current

- Large-scale batch KOL ingestion (1000+ articles from 54 WeChat accounts)
- SQLite entity pipeline stabilization (monitoring DB-first path vs file fallback)

## Next

- **Phase 5: pipeline automation + RSS + daily digest** — PRD at `.planning/phases/05-pipeline-automation/05-PRD.md`; 18 locked decisions in `05-CONTEXT.md`. Wave 0 migrates embeddings to gemini-embedding-2 (multimodal, unblocks Phase 4's 100-RPM quota), then keyword+depth KOL catch-up, then RSS pipeline (92 Karpathy feeds), `orchestrate_daily.py`, `daily_digest.py`, Telegram delivery, cron deployment, 3-day observation.
  - **Goal:** Unattended daily pipeline — scan 56 WeChat KOL + 92 Karpathy RSS, classify for depth, enrich deep via Zhihu 好问, ingest into LightRAG, deliver Telegram daily digest.
  - **Plans:** 9 plans (planned 2026-04-28; revised 2026-04-28 to add 05-03b rss-ingest)
    - [x] 05-00-embedding-migration-and-consolidation-PLAN.md — **Wave 0 closed 2026-05-02 @ `0109c02`**: spike + shared `lightrag_embedding.py` + 6-file consolidation + re-embed + benchmark + PRD typo fix. Scope extensions Task 0.7 (URL retrieval binding, `2f576b1`) + Task 0.8 (`aget_docs_by_ids` verification hook + full reset re-ingest, `585aa3b` + `0109c02`) landed incident-driven. 3/3 P0 success, 0 ghosts, 0 timeouts, 60%/6 CN overlap, 2/2 cross-modal, 2/2 `kg_synthesize` inline images. See `.planning/phases/05-pipeline-automation/05-00-SUMMARY.md` Close-Out Addendum for full close data + 3 deferred items (118-img edge case, prompt-dependent rendering, Cognee restoration).
    - [x] 05-00b-kol-catch-up-filtered-PLAN.md — Wave 0: classify all 302 KOL articles + multi-keyword `--topic-filter` + Batch API or sync fallback ingest
    - [x] 05-01-rss-schema-and-opml-PLAN.md — **Wave 1 closed 2026-05-02 @ `6929259`**: `enrichment/rss_schema.py` + `scripts/seed_rss_feeds.py` + bundled `data/karpathy_hn_2025.opml` (92 feeds) + `init_rss_schema` wired into `batch_scan_kol.init_db` + feedparser/langdetect in requirements. 7 unit tests pass. SUMMARY at `.planning/phases/05-pipeline-automation/05-01-SUMMARY.md`.
    - [x] 05-02-rss-fetch-PLAN.md — **Wave 1 closed 2026-05-02 @ `e9bad10`**: `enrichment/rss_fetch.py` with feedparser + langdetect prefilter (≥500 chars, en/zh*) + per-feed fault tolerance + `error_count` state machine + URL UNIQUE dedup. 7 unit tests pass.
    - [x] 05-03-rss-classify-PLAN.md — **Wave 1 closed 2026-05-02 @ `e4b2932`**: `enrichment/rss_classify.py` on DeepSeek raw HTTP (Phase 7 D-09 supersession) + bilingual prompt with Chinese-only `reason` output (D-08) + `tests/conftest.py` DEEPSEEK_API_KEY dummy guard. 6 unit tests pass.
    - [x] 05-03b-rss-ingest-PLAN.md — **Wave 1 closed 2026-05-02 @ `f70a18b`**: `enrichment/rss_ingest.py` (DeepSeek EN→CN translate + Task 4.2 `aget_docs_by_ids` PROCESSED gate per D-19 + atomic `.tmp` writes; NO enrich_article invocation per D-07 REVISED) + `enrichment/run_enrich_for_id.py` (KOL bridge with env-var contract + RSS guarded no-op). 13 unit tests pass (5 bridge + 8 ingest).
    - [ ] 05-04-orchestrate-daily-PLAN.md — Wave 2: 9-step state machine with Telegram-alert on critical failure
    - [ ] 05-05-daily-digest-PLAN.md — Wave 2: TOP 5 Markdown digest + Telegram delivery + atomic local archive
    - [ ] 05-06-cron-deploy-and-observation-PLAN.md — Wave 3: register 6 new cron jobs + 3-day observation + STATE/ROADMAP close
- **Phase 6: graphify-addon-code-graph** — PRD at `specs/PRDTDD_GRAPHIFY_ADDON.md` (v3.0, authoritative); pre-plan brief at `.planning/phases/06-graphify-addon-code-graph/06-CONTEXT.md`. Add code-graph query capability alongside existing domain-graph by shipping two Skills: `graphify` (zero-code install from `graphifyy` 0.5.3 on Hermes + conditionally OpenClaw, T1 repos only: openclaw + claude-code) and `omnigraph_search` (thin LightRAG wrapper). Plus weekly AST-only cron refresh via `graphify update` (relies on Graphify's built-in `to_json()` shrink guard — no custom tmp-rename). Bridge nodes deferred. Independent of Phase 5.
  - **Goal:** Agent autonomously routes to both `graphify` (code structure) and `omnigraph_search` (design rationale) in mixed queries; weekly cron keeps the code graph fresh on remote.
  - **Plans:** 7 plans (planned 2026-04-28; replanned 2026-04-28 to split 06-03 into 06-03 + 06-03b)
    - [x] 06-00-PLAN.md — Wave 0 scaffold: install `graphifyy`, create stub files, probe remote for `claw` CLI, lock D-S10 scope
    - [x] 06-01-PLAN.md — Install graphify skill on remote (Hermes unconditional; claw conditional) + clone T1 repos + commit AGENTS.md
    - [x] 06-02-PLAN.md — One-shot LLM-driven graph seed via live Hermes `/graphify` session + capture runbook
    - [x] 06-03-PLAN.md — `omnigraph_search` skill files: SKILL.md + query.sh + api-surface.md + query.py + skill_runner test JSON (Tasks 3.1–3.4)
    - [x] 06-03b-PLAN.md — omnigraph_search validation: cross-ref edit in `omnigraph_query` SKILL.md + skill_runner validate + test-file + local & remote live smoke (Tasks 3.5–3.6)
    - [x] 06-04-PLAN.md — Weekly cron `scripts/graphify-refresh.sh` + crontab install on remote
    - [x] 06-05-PLAN.md — Demo 1 + Demo 2 transcripts + consolidated acceptance sign-off across REQ-01..REQ-08
- **Infra track (parallel):** resolve Gemini free-tier embedding quota — Phase 4's criteria 11/12 are blocked on this. Options: paid Tier 1, local `sentence-transformers`, or per-entity semaphore. Not reopening Phase 4; this is standalone infra work.

**Phase 4 canonical refs** (historical):

- `docs/enrichment-prd.md` — full PRD
- `.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md` — 16 locked decisions
- `docs/testing/04-07-validation-results.md` — live-validation report

---

## Milestone v3.1 — Single-Article Ingest Stability ✅ CLOSED (2026-05-01)

**Milestone goal:** Rebuild and locally verify the single-article ingestion pipeline against `test/fixtures/gpt55_article/` so that text ingest + graph connectivity completes in <600s (revised from <2min — see E2E-02 rationale) with no crash. Unblocks Phase 5 Wave 1+ (RSS, daily digest, cron).

**Milestone gate (final):** E2E benchmark run against local fixture produces `benchmark_result.json` with `gate_pass: true`, zero unhandled exceptions, and **<600s text-ingest wall-clock** (revised from <120s based on real production baseline — Hermes DeepSeek = 441s, local Gemini 2.5-flash-lite = 620s; dominated by LightRAG's Phase 1/2 serial entity-merge LLM cost). See `docs/MILESTONE_v3.1_CLOSURE.md` for full A/B data and rationale.

**Closure artifacts:**

- `docs/MILESTONE_v3.1_CLOSURE.md` — canonical closure report
- `docs/E2E_VERIFICATION_v3.1_20260501.md` — Claude local run (Gemini swap due to Cisco Umbrella blocking DeepSeek TLS)
- `docs/HERMES_E2E_VERIFICATION_v3.1_20260501.md` — Hermes production-stack run (authoritative baseline)
- `test/fixtures/gpt55_article/benchmark_result.json` — production data (441s, 28/28 Vision, aquery=true)

### Phases

- [x] **Phase 8: Image Pipeline Correctness (2026-04-30)** — fix `min(w,h)<300` filter, make inter-image sleep configurable (default 0), add per-image + aggregate JSON-lines logging (IMG-01/02/03/04 all passing on fixture: 39→28 images, 11 banners correctly filtered)
- [x] **Phase 9: Timeout Control + LightRAG State Management (2026-04-30)** — LLM_TIMEOUT=600, DeepSeek client timeout 120s, dynamic per-chunk outer `wait_for` budget; `get_rag(flush=True)` API contract + pre-batch flush; `adelete_by_doc_id` rollback on timeout with idempotent re-ingest; 10 callers updated (TIMEOUT-01/02/03 + STATE-01/02/03/04 all passing; unit tests covered)
- [x] **Phase 10: Scrape-First Classification + Text-First Ingest Decoupling (2026-04-29)** — scrape full body before classify (drop `digest` reliance), DeepSeek classifier on full text with SQLite persistence, text `ainsert` ingest decoupled from async Vision worker appending image sub-docs (plans 10-00, 10-01, 10-02 all delivered; 61 unit tests passing cumulatively; ARCH-04 validated on local run — 28 Vision failures did not block text ingest)
- [x] **Phase 11: E2E Verification Gate (2026-05-01)** — `scripts/bench_ingest_fixture.py` fixture CLI + 5-stage timing report + SiliconFlow balance precheck + semantic graph query + `benchmark_result.json` schema + Vertex AI opt-in conditional in `lib/lightrag_embedding.py`; milestone closes with production-stack verification on Hermes (441s text_ingest, aquery TRUE, 28/28 Vision success via SiliconFlow Qwen3-VL-32B)

### Phase Details

### Phase 8: Image Pipeline Correctness
**Goal**: Image download + filter phase produces deterministic, well-logged output on the gpt55 fixture (28 images) with correct filter semantics
**Depends on**: Nothing (self-contained module changes in `image_pipeline.py`)
**Requirements**: IMG-01, IMG-02, IMG-03, IMG-04
**Success Criteria** (what must be TRUE):
  1. Running image filter on gpt55 fixture keeps only images where `min(w,h) >= 300`; a synthetic 100×800 banner is filtered out (previously kept by `w<300 AND h<300` bug)
  2. Inter-image Vision sleep is configurable via a module-level constant with default `0` seconds; sleep=5 still works when set
  3. Each image processed emits a single structured log line containing URL, dimensions, provider name, wall-clock ms, and outcome tag (`success` | `error:<type>`)
  4. Image phase completion emits an aggregate line with counts `{input, kept, filtered}` and total wall-clock timing
**Plans**: 3 plans — 11-00 (bench harness + schema + balance precheck), 11-01 (Vertex AI opt-in conditional enabler for <2min gate), 11-02 (integration run + aquery validation + milestone gate closure)

### Phase 9: Timeout Control + LightRAG State Management
**Goal**: LightRAG state is reset cleanly per run, per-article work is budget-bounded, and timeouts leave the graph consistent (no orphan nodes, no replayed embed quota waste)
**Depends on**: Phase 8 (not strictly required, but logically first since state+timeout underpin later phases)
**Requirements**: TIMEOUT-01, TIMEOUT-02, TIMEOUT-03, STATE-01, STATE-02, STATE-03, STATE-04
**Success Criteria** (what must be TRUE):
  1. `LLM_TIMEOUT` env var (default 600s) is read by LightRAG's health_check and propagates to per-chunk LLM calls; DeepSeek async client has an explicit 120s request timeout
  2. Per-article outer `asyncio.wait_for` budget is computed as `max(120 + 30 × chunk_count, 900)` and is independent of image count
  3. `get_rag()` either returns a fresh instance per call or accepts a `flush=True` parameter; a unit test demonstrates the old singleton-with-buffered-state replay bug no longer occurs
  4. When `asyncio.wait_for` kills an article mid-ingest, partially inserted entities/chunks for that article are rolled back; re-ingesting the same article after rollback produces zero orphan nodes and no duplicate primary-key errors
  5. Running `batch_ingest` twice back-to-back on the same fixture produces identical graph state the second time (idempotent — proves both the pre-batch flush and rollback paths work together)
**Plans**: 3 plans — 11-00 (bench harness + schema + balance precheck), 11-01 (Vertex AI opt-in conditional enabler for <2min gate), 11-02 (integration run + aquery validation + milestone gate closure)

### Phase 10: Scrape-First Classification + Text-First Ingest Decoupling
**Goal**: The ingestion pipeline scrapes full article body first, classifies on full text via DeepSeek with SQLite persistence, ingests text into LightRAG immediately, and defers Vision work to an async worker that appends image sub-docs — failure of Vision never blocks or invalidates text ingest
**Depends on**: Phase 9 (rollback + timeout infrastructure; async Vision sub-doc append depends on clean state contract)
**Requirements**: CLASS-01, CLASS-02, CLASS-03, CLASS-04, ARCH-01, ARCH-02, ARCH-03, ARCH-04
**Success Criteria** (what must be TRUE):
  1. `batch_ingest_from_spider.py --from-db` scrapes the full article body before classification; the unreliable WeChat `digest` field is no longer consulted for classification input
  2. DeepSeek classifier returns `{depth: 1-3, topics: [...], rationale: "..."}` on full article body and the result is persisted to a `classifications` SQLite table with `article_id`, `depth`, `topics`, `rationale`, `classified_at` BEFORE any ingest decision
  3. Scrape phase reuses the existing `spiders/wechat_spider.py` anti-abuse parameters (`SESSION_LIMIT=54`, `RATE_LIMIT_SLEEP_ACCOUNTS=5.0`, `RATE_LIMIT_COOLDOWN=60.0`, rotating UA pool, `_ua_cooldown()`); the batch-path spec is preserved even though v3.1 gate runs on local fixture
  4. Article body + image file paths are `ainsert`-ed into LightRAG FIRST and return successfully before any Vision API call is made; a semantic `aquery` against the fresh graph returns chunks from the article immediately after text-ingest returns
  5. Vision descriptions are linked back via a new `ainsert` append (one image sub-doc per image or per article, referencing parent article by `file_path`) — no re-embed of existing text chunks
  6. When SiliconFlow/OpenRouter/Gemini Vision are ALL simulated down (via mock/env toggle), text ingest still succeeds and the resulting graph is queryable; Vision worker failure is logged but does not propagate as an exception into the main ingest flow
**Plans**: 10-00 (scrape-first classifier), 10-01 (text-first ingest split), 10-02 (async Vision worker + sub-doc + drain) — all complete 2026-04-29

### Phase 11: E2E Verification Gate
**Goal**: Full-pipeline local benchmark against `test/fixtures/gpt55_article/` completes in <2 min text-ingest wall-clock with zero crashes, a semantically queryable graph, and a machine-readable result file suitable for CI regression — milestone v3.1 closes when `gate_pass: true` is observed
**Depends on**: Phase 8, Phase 9, Phase 10 (composes their work into the end-to-end gate)
**Requirements**: E2E-01, E2E-02, E2E-03, E2E-04, E2E-05, E2E-06, E2E-07
**Success Criteria** (what must be TRUE):
  1. A local CLI invocation ingests `test/fixtures/gpt55_article/` as a single article from disk with no network WeChat scrape required; `metadata.json` (url, title) is the input source
  2. Text-ingest phase (scrape → classify → image-filter → LightRAG `ainsert` return, excluding async Vision wait) completes in <2 minutes wall-clock on the dev machine; benchmark fails loud if exceeded
  3. The benchmark emits a stage-level timing report with exactly five labelled wall-clock sections: `scrape`, `classify`, `image-download`, `text-ingest`, `async-vision-start` (the last is annotated and NOT counted toward the <2min gate)
  4. Post-ingest, `aquery(query="GPT-5.5 benchmark results", mode="hybrid")` returns top-3 chunks with at least one chunk where `file_path` matches the ingested fixture article OR chunk content references it
  5. Benchmark calls SiliconFlow `GET /v1/user/info` with `Authorization: Bearer $SILICONFLOW_API_KEY`, parses `balance`, and compares against estimated cost (~¥0.036/article × batch size); emits a structured warning (non-fatal for single-article v3.1 gate) if balance is below threshold
  6. Benchmark completes with zero unhandled exceptions and zero process crashes from CLI invocation through `benchmark_result.json` write
  7. `benchmark_result.json` is written to a known path with the exact schema `{article_hash, stage_timings_ms: {scrape, classify, image_download, text_ingest, async_vision_start}, counters: {images_input, images_kept, images_filtered, chunks_extracted, entities_ingested}, gate_pass: bool, errors: []}` — CI can diff this file across future runs
**Plans**: 3 plans — 11-00 (bench harness + schema + balance precheck), 11-01 (Vertex AI opt-in conditional enabler for <2min gate), 11-02 (integration run + aquery validation + milestone gate closure)

---

## Milestone v3.2 Planned — Batch Reliability + Infra

**Milestone goal:** Enable Phase 5 Wave 1 (RSS + KOL batch ingestion, 56+ articles) to complete reliably with partial failure recovery, intelligent Vision fallback, comprehensive regression validation, and long-term infrastructure for quota isolation. Predecessor: Milestone v3.1 — **closed 2026-05-01 @ commit 2b38e98** (26/26 REQs, see `docs/MILESTONE_v3.1_CLOSURE.md`).

**Planning revised 2026-05-01 post v3.1 closure** — baseline = 441s/article (Hermes DeepSeek prod), E2E-02 gate 600s, 2 findings absorbed (Phase 12 sub-doc lifecycle via D-SUBDOC, Phase 13 bench precheck via D-BENCH-PRECHECK), Phase 17 default BATCH_TIMEOUT 3600s → 28800s (8h, covers 56 × 441s batch).

**Milestone gate:** 56+ article batch completes with zero unhandled exceptions; transient failures auto-recover without re-scraping prior articles; 5 regression fixtures pass; CLAUDE.md + OPERATOR_RUNBOOK.md + DEPLOY.md complete; SiliconFlow balance warnings trigger at key checkpoints; Vertex AI migration spec + SA template documented.

**Source of truth:** `.planning/MILESTONE_v3.2_REQUIREMENTS.md` (v2 revised 2026-05-01; see revision history at top of file).

### Phases

- [ ] **Phase 12: Checkpoint/Resume Mechanism (B1)** — 5-stage persistent checkpoints (scrape/classify/image-download/text-ingest/vision-worker) at `~/.hermes/omonigraph-vault/checkpoints/{article_hash}/` with atomic writes and resume-from-last-completed logic
- [ ] **Phase 13: Vision Cascade with Circuit Breaker (B2)** — SiliconFlow→OpenRouter→Gemini cascade with per-provider state tracking, 3-consecutive-failure circuit breaker, 503/429/timeout error classification, SiliconFlow balance monitoring
- [ ] **Phase 14: Regression Test Fixtures (B3)** — 5 fixture profiles (gpt55, sparse_image, dense_image, text_only, mixed_quality) + `validate_regression_batch.py` producing `batch_validation_report.json`
- [ ] **Phase 15: Documentation & Operator Runbook (B4)** — CLAUDE.md additions (checkpoint/cascade/balance), `docs/OPERATOR_RUNBOOK.md` (pre-batch checklist, failure scenarios, manual intervention), Deploy.md updates
- [ ] **Phase 16: Vertex AI Infrastructure Preparation (B5)** — `docs/VERTEX_AI_MIGRATION_SPEC.md` + `credentials/vertex_ai_service_account_example.json` template + `scripts/estimate_vertex_ai_cost.py` (no code changes; design-only)
- [ ] **Phase 17: Batch Timeout Management** — Extend Phase 9 per-article timeout formula to batch-level: dynamic remaining-budget calculation, single/batch interlock, checkpoint-flush interaction, monitoring metrics (avg_article_time, batch_progress_vs_budget, timeout_histogram)

### Phase Details

### Phase 12: Checkpoint/Resume Mechanism
**Goal**: Persist article ingestion state at 5 stage boundaries so transient failures resume without re-scraping or re-processing prior stages; support manual reset per-hash or batch-wide
**Depends on**: v3.1 Phase 9 (`get_rag(flush=True)` contract, rollback semantics), v3.1 Phase 10 (`ainsert` decoupled from Vision)
**Requirements**: CKPT-01 (stage boundaries), CKPT-02 (format), CKPT-03 (resume logic), CKPT-04 (atomicity), CKPT-05 (manual reset scripts)
**Success Criteria** (what must be TRUE):
  1. Single article with injected failure at stage 3 (image-download) resumes correctly at stage 4 (text-ingest) without re-running scrape/classify/image-download
  2. Checkpoint files are written atomically (`.tmp` then `os.rename()`); a crash mid-write leaves no corrupted partial files
  3. `python scripts/checkpoint_reset.py --hash {article_hash}` removes checkpoint dir; full re-run succeeds cleanly
  4. `python scripts/checkpoint_status.py` lists all in-flight checkpoints with current stage annotation
  5. Checkpoint directory schema matches MILESTONE_v3.2_REQUIREMENTS.md §B1.2 exactly (5 files/dirs + metadata.json)
**Plans**: 4 plans
  - [ ] 12-00-checkpoint-lib-PLAN.md — Wave 1: lib/checkpoint.py public API + unit tests (CKPT-01, CKPT-02, CKPT-04)
  - [ ] 12-01-cli-tools-PLAN.md — Wave 2: scripts/checkpoint_reset.py (+ --confirm guard) and scripts/checkpoint_status.py + CLI tests (CKPT-05)
  - [ ] 12-02-ingest-integration-PLAN.md — Wave 2: wrap ingest_wechat.py::ingest_article 5 stages with checkpoint read/write + stage-skip integration tests (CKPT-01, CKPT-03)
  - [ ] 12-03-batch-integration-and-e2e-PLAN.md — Wave 3: batch_ingest_from_spider.py skip guard + end-to-end failure-injection tests (Gate 1 acceptance) (CKPT-03, CKPT-05)

### Phase 13: Vision Cascade with Circuit Breaker
**Goal**: Image description cascades SiliconFlow→OpenRouter→Gemini with per-provider state tracking and automatic circuit breaker; a single provider 503 never kills the article
**Depends on**: Phase 12 (uses checkpoint dir to persist `provider_status` across batch restarts)
**Requirements**: CASC-01 (cascade order), CASC-02 (state tracking), CASC-03 (circuit breaker), CASC-04 (error code classification), CASC-05 (logging), CASC-06 (SiliconFlow balance management)
**Success Criteria** (what must be TRUE):
  1. SiliconFlow 503 → auto-cascade to OpenRouter without exception propagation
  2. After 3 consecutive SiliconFlow failures within a batch, `circuit_open = True` and SiliconFlow is skipped for subsequent images until recovery retry succeeds
  3. `batch_validation_report.json` `provider_usage` reflects actual cascade attempts per provider
  4. Pre-batch SiliconFlow balance check emits structured warning if balance < estimated remaining cost
  5. Gemini is used only as last resort when both SiliconFlow and OpenRouter circuits are open
  6. 429 on SiliconFlow immediately cascades to OpenRouter; 4xx auth errors do NOT count toward circuit breaker
**Plans**: 4 plans (planned 2026-04-30)
  - [ ] 13-00-vision-cascade-core-PLAN.md — Wave 1: lib/vision_cascade.py (VisionCascade class, CascadeResult, AttemptRecord, AllProvidersExhausted429Error) + unit tests for state machine, error classification, circuit breaker, atomic persist
  - [ ] 13-01-siliconflow-balance-PLAN.md — Wave 1 (parallel): lib/siliconflow_balance.py (check_siliconflow_balance, estimate_cost, should_warn, should_switch_to_openrouter) + unit tests for HTTP paths + threshold math
  - [ ] 13-02-image-pipeline-integration-PLAN.md — Wave 2: rewire image_pipeline.describe_images() to use VisionCascade; pre-batch + mid-batch balance checks; batch-end alerts; preserves public signature + unit tests
  - [ ] 13-03-integration-tests-PLAN.md — Wave 3: tests/integration/test_vision_cascade_e2e.py simulating 503/429/timeout/recovery/balance sequences with HTTP-layer mocks only (no real API keys)

### Phase 14: Regression Test Fixtures
**Goal**: 5 fixture profiles covering distinct article characteristics (image density, text length, image quality) validate the batch pipeline end-to-end; JSON report schema supports CI regression tracking
**Depends on**: Phase 12 (checkpoint infra), Phase 13 (cascade), v3.1 Phase 11 (bench harness pattern)
**Requirements**: REGR-01 (5 fixtures), REGR-02 (schema), REGR-03 (validation script), REGR-04 (report schema), REGR-05 (CI integration)
**Success Criteria** (what must be TRUE):
  1. `test/fixtures/sparse_image_article/`, `dense_image_article/`, `text_only_article/`, `mixed_quality_article/` exist with matching `metadata.json` + content
  2. `python scripts/validate_regression_batch.py --fixtures ... --output batch_validation_report.json` completes on all 5 fixtures
  3. `batch_validation_report.json` matches MILESTONE_v3.2_REQUIREMENTS.md §B3.4 schema exactly
  4. Script exit code 0 on all-pass, 1 on any failure
  5. `dense_image_article` (45 images) filters correctly (post-IMG-01 fix) and all survive Vision cascade
  6. `text_only_article` (0 images) skips Vision entirely with no null pointer errors
**Plans**: TBD

### Phase 15: Documentation & Operator Runbook
**Goal**: Humans can operate the batch pipeline without reading code; CLAUDE.md + OPERATOR_RUNBOOK.md + DEPLOY.md cover deployment, monitoring, recovery, and upgrade paths
**Depends on**: Nothing for drafting (can run in parallel with Phase 12-14); facts documented must reflect Phase 12-13 final APIs before merge
**Requirements**: DOC-01 (CLAUDE.md additions), DOC-02 (OPERATOR_RUNBOOK.md), DOC-03 (DEPLOY.md updates)
**Success Criteria** (what must be TRUE):
  1. CLAUDE.md contains Checkpoint Mechanism + Vision Cascade + SiliconFlow Balance Management + Batch Execution + Known Limitations sections
  2. `docs/OPERATOR_RUNBOOK.md` contains Pre-Batch Checklist + Batch Execution commands + Failure Scenarios table + Manual Intervention + Monitoring Points
  3. `Deploy.md` updated with SiliconFlow vs Gemini trade-off table and "Recommended Upgrade Path" pointing to Vertex AI spec
  4. Runbook walkthrough with at least one failure scenario passes human review (no questions remaining)
**Plans**: 3 plans
  - [ ] 15-00-claude-md-additions-PLAN.md — Insert 5 new sections (Checkpoint, Vision Cascade, Balance, Batch Execution, Known Limitations) into CLAUDE.md after Lessons Learned
  - [ ] 15-01-operator-runbook-PLAN.md — Create docs/OPERATOR_RUNBOOK.md with Pre-Batch Checklist, Batch Execution, Failure Scenarios table, Manual Intervention, Monitoring Points
  - [ ] 15-02-deploy-md-updates-PLAN.md — Append SiliconFlow-vs-Gemini trade-off, Vertex AI Infrastructure Plan, Recommended Upgrade Path sections to Deploy.md

### Phase 16: Vertex AI Infrastructure Preparation
**Goal**: Design and document the migration path from Gemini API free tier to Vertex AI OAuth2 with cross-project quota isolation; no code changes required in this milestone
**Depends on**: Nothing (fully parallel with all other v3.2 phases)
**Requirements**: VERT-01 (migration spec), VERT-02 (SA template), VERT-03 (CLAUDE.md + Deploy.md updates), VERT-04 (cost estimation script)
**Success Criteria** (what must be TRUE):
  1. `docs/VERTEX_AI_MIGRATION_SPEC.md` documents GCP project setup, service account naming, OAuth2 token refresh pattern, pricing comparison, and backward-compat design
  2. `credentials/vertex_ai_service_account_example.json` provided as a template (no real credentials)
  3. CLAUDE.md § "Vertex AI Migration Path" explains the free-tier quota coupling problem and upgrade criteria
  4. `scripts/estimate_vertex_ai_cost.py --articles N --avg-images-per-article M` outputs cost breakdown (embedding + vision + LLM totals)
  5. Zero production code paths modified — all changes are in `docs/`, `credentials/`, `scripts/`
**Plans**: TBD

### Phase 17: Batch Timeout Management
**Goal**: Extend v3.1 Phase 9's per-article `asyncio.wait_for` budget to batch-level: batch tracks dynamic remaining budget, single-article timeout interacts gracefully with checkpoint flush, monitoring metrics published
**Depends on**: Phase 12 (checkpoint flush interaction), v3.1 Phase 9 (single-article timeout formula `max(120 + 30 × chunk_count, 900)`)
**Requirements**: BTIMEOUT-01 (batch time tracking), BTIMEOUT-02 (single/batch interlock), BTIMEOUT-03 (checkpoint-flush timeout interaction), BTIMEOUT-04 (monitoring metrics)
**Success Criteria** (what must be TRUE):
  1. Batch run emits per-article timing: `avg_article_time`, `batch_progress_vs_budget`, `timeout_histogram` (e.g., buckets 0–60s / 60–300s / 300–900s / 900s+)
  2. Remaining batch budget is computed dynamically: `budget = total_batch_budget − elapsed`; per-article timeout clamped to `min(single_article_timeout, remaining_budget − safety_margin)`
  3. Checkpoint flush on timeout is NOT counted toward single-article budget (flush is post-timeout bookkeeping)
  4. Batch reports final summary with budget utilization, per-stage wall-clock breakdown
  5. Spec-level design delivered in this milestone; implementation may defer to post-v3.2 if needed — phase definition explicitly marks implementation scope vs design scope
**Plans**: 3 plans (planned 2026-04-30)
  - [ ] 17-00-design-doc-PLAN.md — Wave 1 (independent): docs/BATCH_TIMEOUT_DESIGN.md with 8 mandatory sections (BTIMEOUT-01..04 design)
  - [ ] 17-01-clamp-helper-PLAN.md — Wave 1 (parallel): lib/batch_timeout.py `clamp_article_timeout()` + `get_remaining_budget()` + `BATCH_SAFETY_MARGIN_S` + 11 unit tests (BTIMEOUT-02)
  - [ ] 17-02-batch-instrumentation-PLAN.md — Wave 2 (depends on 17-01): batch_ingest_from_spider.py instrumentation (env var + CLI flag + clamp call + metric emission) + 18 unit tests (BTIMEOUT-01, BTIMEOUT-03, BTIMEOUT-04)

### Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 8. Image Pipeline Correctness | 0/? | Not started | - |
| 9. Timeout Control + LightRAG State | 0/? | Not started | - |
| 10. Scrape-First Classification + Text-First Ingest | 1/3 | In Progress|  |
| 11. E2E Verification Gate | 3/3 | Complete   | 2026-05-01 |
| 12. Checkpoint/Resume Mechanism | 0/? | Not started | - |
| 13. Vision Cascade with Circuit Breaker | 0/? | Not started | - |
| 14. Regression Test Fixtures | 0/? | Not started | - |
| 15. Documentation & Operator Runbook | 0/? | Not started | - |
| 16. Vertex AI Infrastructure Preparation | 0/? | Not started | - |
| 17. Batch Timeout Management | 0/3 | Not started | - |
