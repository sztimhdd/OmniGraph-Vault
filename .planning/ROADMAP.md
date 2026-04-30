# Roadmap

**Last Updated:** 2026-04-30 (Milestone v3.1 phases 8-11 added)

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

## Current

- Large-scale batch KOL ingestion (1000+ articles from 54 WeChat accounts)
- SQLite entity pipeline stabilization (monitoring DB-first path vs file fallback)

## Next

- **Phase 5: pipeline automation + RSS + daily digest** — PRD at `.planning/phases/05-pipeline-automation/05-PRD.md`; 18 locked decisions in `05-CONTEXT.md`. Wave 0 migrates embeddings to gemini-embedding-2 (multimodal, unblocks Phase 4's 100-RPM quota), then keyword+depth KOL catch-up, then RSS pipeline (92 Karpathy feeds), `orchestrate_daily.py`, `daily_digest.py`, Telegram delivery, cron deployment, 3-day observation.
  - **Goal:** Unattended daily pipeline — scan 56 WeChat KOL + 92 Karpathy RSS, classify for depth, enrich deep via Zhihu 好问, ingest into LightRAG, deliver Telegram daily digest.
  - **Plans:** 9 plans (planned 2026-04-28; revised 2026-04-28 to add 05-03b rss-ingest)
    - [x] 05-00-embedding-migration-and-consolidation-PLAN.md — Wave 0: spike + shared `lightrag_embedding.py` + 6-file consolidation + 18-doc re-embed + benchmark + PRD typo fix
    - [x] 05-00b-kol-catch-up-filtered-PLAN.md — Wave 0: classify all 302 KOL articles + multi-keyword `--topic-filter` + Batch API or sync fallback ingest
    - [ ] 05-01-rss-schema-and-opml-PLAN.md — Wave 1: RSS SQLite schema + bundled Karpathy OPML + seed 92 feeds + deps
    - [ ] 05-02-rss-fetch-PLAN.md — Wave 1: `enrichment/rss_fetch.py` with pre-filter, dedup, feed-level fault tolerance
    - [ ] 05-03-rss-classify-PLAN.md — Wave 1: `enrichment/rss_classify.py` with bilingual prompt (EN→CN in-prompt per D-08)
    - [ ] 05-03b-rss-ingest-PLAN.md — Wave 1: `enrichment/rss_ingest.py` (EN→CN body translation per D-09) + `run_enrich_for_id.py` env-var bridge for `enrich_article` skill (fixes RSS ingest gap)
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
    - [ ] 06-05-PLAN.md — Demo 1 + Demo 2 transcripts + consolidated acceptance sign-off across REQ-01..REQ-08
- **Infra track (parallel):** resolve Gemini free-tier embedding quota — Phase 4's criteria 11/12 are blocked on this. Options: paid Tier 1, local `sentence-transformers`, or per-entity semaphore. Not reopening Phase 4; this is standalone infra work.

**Phase 4 canonical refs** (historical):

- `docs/enrichment-prd.md` — full PRD
- `.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md` — 16 locked decisions
- `docs/testing/04-07-validation-results.md` — live-validation report

---

## Milestone v3.1 Next — Single-Article Ingest Stability

**Milestone goal:** Rebuild and locally verify the single-article ingestion pipeline against `test/fixtures/gpt55_article/` so that text ingest + graph connectivity completes in <2 min with no crash. Unblocks Phase 5 Wave 1+ (RSS, daily digest, cron).

**Milestone gate:** E2E benchmark run against local fixture produces `benchmark_result.json` with `gate_pass: true`, zero unhandled exceptions, and <2min text-ingest wall-clock.

### Phases

- [ ] **Phase 8: Image Pipeline Correctness** — fix `min(w,h)<300` filter, make inter-image sleep configurable (default 0), add per-image + aggregate logging
- [ ] **Phase 9: Timeout Control + LightRAG State Management** — align LLM_TIMEOUT=600, DeepSeek client timeout, dynamic per-chunk outer `wait_for`; flush LightRAG buffer pre-batch; rollback partial inserts on timeout; change `get_rag()` API contract
- [ ] **Phase 10: Scrape-First Classification + Text-First Ingest Decoupling** — scrape full body before classify (drop `digest` reliance), DeepSeek classifier on full text with SQLite persistence, text `ainsert` ingest decoupled from async Vision worker appending image sub-docs
- [ ] **Phase 11: E2E Verification Gate** — fixture CLI ingest, stage-level timing report, SiliconFlow balance check, semantic graph query, `benchmark_result.json` with machine-readable schema; milestone closes here

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
**Plans**: TBD

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
**Plans**: TBD

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
**Plans**: TBD

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
**Plans**: TBD

### Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 8. Image Pipeline Correctness | 0/? | Not started | - |
| 9. Timeout Control + LightRAG State | 0/? | Not started | - |
| 10. Scrape-First Classification + Text-First Ingest | 0/? | Not started | - |
| 11. E2E Verification Gate | 0/? | Not started | - |
