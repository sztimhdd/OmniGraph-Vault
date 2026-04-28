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

- **Phase 5: pipeline automation + RSS + daily digest** — PRD at `.planning/phases/05-pipeline-automation/05-PRD.md`. RSS module (Karpathy HN 2025, 92 feeds), `orchestrate_daily.py`, `daily_digest.py`, Telegram delivery. Depends on Phase 4 (closed) and working embedding capacity.
- **Infra track (parallel):** resolve Gemini free-tier embedding quota — Phase 4's criteria 11/12 are blocked on this. Options: paid Tier 1, local `sentence-transformers`, or per-entity semaphore. Not reopening Phase 4; this is standalone infra work.

**Phase 4 canonical refs** (historical):

- `docs/enrichment-prd.md` — full PRD
- `.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md` — 16 locked decisions
- `docs/testing/04-07-validation-results.md` — live-validation report
