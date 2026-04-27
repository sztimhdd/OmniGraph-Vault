# Roadmap

**Last Updated:** 2026-04-27

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

### Phase 4: knowledge-enrichment-zhihu — COMPLETE (see Done)

**Goal:** Insert a mandatory knowledge enrichment step between WeChat scrape
and LightRAG ingestion. For each scraped article ≥2000 chars, extract 1–3
under-documented technical questions via Gemini + Google Search grounding,
route each to the `zhihu-haowen-enrich` Hermes skill that drives zhida.zhihu.com
via CDP, fetch the best-cited Zhihu source answer (text + images), then ingest
the enriched WeChat MD (inline 好问 summaries) + up to 3 standalone Zhihu
answer docs into LightRAG as cross-referenced documents. Image handling
refactored out of `ingest_wechat.py` into a shared `image_pipeline.py`.

**Plans:** 8 plans in 6 waves

Plans:
- [x] 04-00-wave0-scaffold-and-spike-PLAN.md — pytest scaffold, SQLite migration, LightRAG delete+reinsert spike (D-14), deploy.sh, golden-file fixture capture (completed 2026-04-27)
- [x] 04-01-image-pipeline-refactor-PLAN.md — extract image_pipeline.py from ingest_wechat.py (4 public functions), golden-file regression gate (completed 2026-04-27)
- [x] 04-02-extract-questions-PLAN.md — enrichment/extract_questions.py: Gemini 2.5 Flash Lite + google_search grounding, D-03 stdout contract (completed 2026-04-27)
- [x] 04-03-fetch-zhihu-PLAN.md — enrichment/fetch_zhihu.py: CDP fetch + image_pipeline reuse, <100px image filter, image namespacing (completed 2026-04-27)
- [x] 04-04-merge-and-ingest-PLAN.md — merge_md (pure) + merge_and_ingest (runner): LightRAG ids+file_paths (D-08), SQLite enriched state (D-07/D-11) (completed 2026-04-27)
- [x] 04-05-zhihu-haowen-enrich-skill-PLAN.md — skills/zhihu-haowen-enrich/: 10-step CDP flow + D-13 Telegram login recovery (pure Markdown, no script) (completed 2026-04-27)
- [x] 04-06-enrich-article-top-skill-PLAN.md — skills/enrich_article/: per-question for-loop orchestrator (D-01/D-02, no Python orchestrator) (completed 2026-04-27)
- [x] 04-07-ingest-wechat-integration-PLAN.md — config.py keys + D-12-REVISED flash, INGEST_LLM_MODEL swap, SQLite auto-migrate, VERTEXAI pops, enriched=-1 marker, omnigraph_ingest cross-ref, enriched.md persistence, LightRAG throttle (completed 2026-04-27; 4/6 Wave 4 criteria flipped PASS, 11/12 infra-blocked by Gemini free-tier embedding quota — see docs/testing/04-07-validation-results.md)

**Canonical refs:**
- `docs/enrichment-prd.md` — full PRD, source of truth (note §6.1 and §12 Phase 5 are superseded by D-07 and D-12)
- `.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md` — 16 locked decisions
- `.planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md` — technical research (remote SSH probe confirmed)
- `.planning/phases/04-knowledge-enrichment-zhihu/04-VALIDATION.md` — Nyquist validation strategy
