# Roadmap

**Last Updated:** 2026-04-28 (Phase 7 added)

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

## Current

- Large-scale batch KOL ingestion (1000+ articles from 54 WeChat accounts)
- SQLite entity pipeline stabilization (monitoring DB-first path vs file fallback)

## Next

- **Phase 5: pipeline automation + RSS + daily digest** — PRD at `.planning/phases/05-pipeline-automation/05-PRD.md`; 18 locked decisions in `05-CONTEXT.md`. Wave 0 migrates embeddings to gemini-embedding-2 (multimodal, unblocks Phase 4's 100-RPM quota), then keyword+depth KOL catch-up, then RSS pipeline (92 Karpathy feeds), `orchestrate_daily.py`, `daily_digest.py`, Telegram delivery, cron deployment, 3-day observation.
  - **Goal:** Unattended daily pipeline — scan 56 WeChat KOL + 92 Karpathy RSS, classify for depth, enrich deep via Zhihu 好问, ingest into LightRAG, deliver Telegram daily digest.
  - **Plans:** 9 plans (planned 2026-04-28; revised 2026-04-28 to add 05-03b rss-ingest)
    - [x] 05-00-embedding-migration-and-consolidation-PLAN.md — Wave 0: spike + shared `lightrag_embedding.py` + 6-file consolidation + 18-doc re-embed + benchmark + PRD typo fix
    - [ ] 05-00b-kol-catch-up-filtered-PLAN.md — Wave 0: classify all 302 KOL articles + multi-keyword `--topic-filter` + Batch API or sync fallback ingest
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
- **Phase 7: model & key management** — REQUIREMENTS at `.planning/phases/07-model-key-management/07-REQUIREMENTS.md`. Centralize Gemini model selection, API key loading (+ optional multi-account rotation), per-model rate limiting, and 429/503 retry into a repo-root `lib/` module. Migrate all 18 production files off direct `GEMINI_API_KEY` + hardcoded model strings. Single-vendor (Gemini) scope; new SDK (`google-genai`, not deprecated `google-generativeai`).
  - **Goal:** Model change is one edit; 429s no longer crash runs; key rotation works across Google accounts/projects; `OMNIGRAPH_GEMINI_KEY` env var replaces generic `GEMINI_API_KEY` (with fallback).
  - **Sequencing note:** Phase 5 includes an embedding model switch to `embedding-002`. If Phase 7 lands first, that switch becomes a one-line change in `lib/models.py`. If Phase 5 ships first, the embedding switch is done the old way and Phase 7 absorbs it into the registry later. Independent of Phase 6.
  - **Locked decisions:** scoped env var `OMNIGRAPH_GEMINI_KEY` + fallback `GEMINI_API_KEY` + optional pool `OMNIGRAPH_GEMINI_KEYS`; `aiolimiter` + `tenacity` dependencies; repo-root `lib/` (not exposed as skill); all 18 files in one phase.

- **Infra track (parallel):** resolve Gemini free-tier embedding quota — Phase 4's criteria 11/12 are blocked on this. Options: paid Tier 1, local `sentence-transformers`, or per-entity semaphore. Not reopening Phase 4; this is standalone infra work.

**Phase 4 canonical refs** (historical):

- `docs/enrichment-prd.md` — full PRD
- `.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md` — 16 locked decisions
- `docs/testing/04-07-validation-results.md` — live-validation report
