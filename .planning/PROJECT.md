# OmniGraph-Vault

## What This Is

A local, graph-based personal knowledge base that gives Hermes Agent (and Openclaw) persistent memory over articles and documents. You drop in a WeChat article URL or PDF; the vault scrapes it, extracts entities and images, indexes everything into LightRAG, and surfaces it back on demand via two skills: one to ingest content, one to answer questions.

## Core Value

When Hermes sees "add this to my KB" or "what do I know about X?" it calls the right script and gets a useful answer back.

## Requirements

### Validated

- ✓ WeChat article ingestion via Apify SDK (primary path) — existing
- ✓ CDP/Playwright fallback when Apify fails or is blocked — existing
- ✓ Image download + Gemini Vision description embedded in content — existing
- ✓ LightRAG graph indexing (ainsert / aquery, hybrid retrieval) — existing
- ✓ Cognee async memory layer (remember / recall, decoupled from fast path) — existing
- ✓ Entity canonicalization via cognee_batch_processor + canonical_map.json (atomic write) — existing
- ✓ PDF ingestion with embedded image extraction (multimodal_ingest.py) — existing
- ✓ Synthesis engine (kg_synthesize.py) generating Markdown reports — existing
- ✓ Local image HTTP server (port 8765) for inline image URLs in reports — existing
- ✓ Telegram delivery of synthesized .md reports — existing
- ✓ Centralized config (config.py) with path constants, ~/.hermes/.env loading — existing
- ✓ Gate 1-5 + A-D: LightRAG, Cognee, image server, single-article ingestion, PDF ingestion — passed

### Active

- [ ] Gate 6: Ingest 3 articles, run cross-article synthesis query, confirm multi-document answer
- [ ] `omnigraph_ingest` Hermes skill: trigger `ingest_wechat.py` from natural language ("add this to my KB")
- [ ] `omnigraph_query` Hermes skill: trigger `kg_synthesize.py` from natural language ("what do I know about X?")
- [ ] Skills surface clear error messages when scripts fail (missing env vars, API quota, CDP not running)
- [ ] Gate 7: Hermes Agent integration demo — both skills exercised end-to-end

### Out of Scope

- Multi-source batch ingestion (RSS, GitHub API, Zhihu scraping) — parking the vision for now
- Cross-validation and confidence scoring layer — Phase 3 vision, not needed for basic KB skill
- Self-completing knowledge graph (gap detection, auto-fill) — Phase 4 vision
- REST API for remote agent calls — future
- Webhook-based ingestion (Telegram → OmniGraph-Vault) — future
- Multi-user / team sharing — intentionally single-user

## Context

- **Phase 1 complete**: Core ingestion pipeline, synthesis, Cognee memory all implemented and gate-tested
- **Runtime data path has a typo**: directory is `omonigraph-vault` (not `omnigraph-vault`) — baked into config.py and deployed; do not change without coordinated migration
- **Hermes skill interface**: Skills call Python scripts via subprocess. The skill body specifies when to trigger, how to call the script, and how to surface errors.
- **Cognee is always async**: never await or block on Cognee in the ingestion fast path
- **Image server must be running** for synthesized reports to render inline images correctly

## Constraints

- **Privacy**: All data stays local; no SaaS KB subscriptions; only Gemini API + Apify make external calls
- **Platform**: Windows-primary (Edge for CDP); Cognee requires Python 3.12 venv per wrapper
- **Single user**: No auth, no isolation required — personal tool only
- **Stack**: Python 3.11+, LightRAG, Cognee, Gemini 2.5 Flash/Pro — no framework migrations

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Cognee decoupled from ingestion fast-path | Cognee API latency / quota issues would block article ingestion — async path preserves <200ms target | ✓ Good |
| Atomic rename for canonical_map.json | Prevents corruption under concurrent access from batch processor + synthesis | ✓ Good |
| `.processed` marker on entity_buffer files | Idempotency: re-running batch processor never double-processes | ✓ Good |
| Two skills (ingest + query) not one unified skill | Clearer intent mapping, easier to test independently | — Pending validation |
| Skip Phase 2-4 vision features for now | Focus on Gate 6 + working Hermes skill before scaling the data sources | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-21 after initialization*
