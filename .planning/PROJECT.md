# OmniGraph-Vault

## What This Is

A local, graph-based personal knowledge base that gives Hermes Agent (and Openclaw) persistent memory over articles and documents. You drop in a WeChat article URL or PDF; the vault scrapes it, extracts entities and images, indexes everything into LightRAG, and surfaces it back on demand via two skills: one to ingest content, one to answer questions.

## Core Value

When Hermes sees "add this to my KB" or "what do I know about X?" it calls the right script and gets a useful answer back.

## Current Milestone: v2.0 Knowledge Infrastructure MVP

**Goal:** Build a rules engine, populate the KB with GitHub tools and KOL content, and design the `/architect` skill — giving the vault structured architecture guidance on demand.

**Target features:**
- Rules engine: 20–30 structured rules in `rules_engine.json` (bootstrapped via Copilot GPT-5.4)
- KB population: 50+ GitHub AI tools + 5–10 KOL articles indexed in OmniGraph-Vault
- `/architect` skill (`omnigraph_architect`): `SKILL.md` + `scripts/architect.sh` with Propose/Query/Ingest modes
- `skill_runner.py` enhanced for multi-turn conversation support
- 9+ test cases for `/architect`; all 3 skills green in `skill_runner.py`

---

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
- ✓ `omnigraph_ingest` skill package: SKILL.md (100–200 words pushy), `scripts/ingest.sh`, `references/`, `evals/evals.json` — v1.1 Phase 2
- ✓ `omnigraph_query` skill package: SKILL.md, `scripts/query.sh`, `references/`, `evals/evals.json` — v1.1 Phase 2
- ✓ `skill_runner.py`: local simulator passing 9/9 ingest + 10/10 query test cases — v1.1 Phase 2
- ✓ `scripts/install-for-hermes.sh`: venv auto-setup, pip install, smoke test — v1.1 Phase 2
- ✓ KG-RAG embedding strategy: keep Method A (Vision describe + text embed; LightRAG has no multimodal vector support) — v1.1 Phase 2

### Active (v2.0)

- [ ] Gate 6: Ingest 3 articles, run cross-article synthesis query, confirm multi-document answer *(carry-over from v1.1 — prerequisite for Phase 4)*
- [ ] Rules engine: `rules_engine.json` with 20–30 structured rules (bootstrapped via Copilot GPT-5.4 researcher mode)
- [ ] KB population: 50+ GitHub AI tools indexed in OmniGraph-Vault (via `ingest_github.py` — GitHub REST API)
- [ ] `entity_registry.json`: GitHub URL → entity ID mapping
- [ ] KB population: 5–10 KOL articles (WeChat, GitHub issues, Zhihu) indexed
- [ ] `/architect` skill (`omnigraph_architect`): `SKILL.md` with Propose/Query/Ingest decision tree (100–200 words, SkillHub pushy format)
- [ ] `scripts/architect.sh`: CWD-independent wrapper for `/architect` skill
- [ ] GSD:DISCUSS pattern documented (`.planning/GSD_DISCUSS_PATTERN.md`)
- [ ] `skill_runner.py` enhanced: multi-turn support (`inputs: list[str]`, conversation context across turns)
- [ ] `tests/skills/test_omnigraph_architect.json`: 9+ test cases (3 per mode: Propose, Query, Ingest)
- [ ] All 3 skills passing: `python skill_runner.py skills/ --test-all`

### Out of Scope

- Hermes deployment via `skills.external_dirs` + Gate 7 validation — deferred until after v2.0 completion
- Multi-source batch ingestion (RSS, GitHub API, Zhihu scraping) — parking the vision for now
- Cross-validation and confidence scoring layer — future
- Self-completing knowledge graph (gap detection, auto-fill) — future
- REST API for remote agent calls — future
- Webhook-based ingestion (Telegram → OmniGraph-Vault) — future
- Multi-user / team sharing — intentionally single-user

## Context

- **v1.1 Phase 2 complete**: Both skill packages (omnigraph_ingest, omnigraph_query) are production-grade with CWD-independent wrappers, eval suites, and passing skill_runner test suites (9/9, 10/10)
- **v1.1 Gate 6 pending**: Cross-article synthesis manual checkpoint not yet validated — required before Phase 4 KB population work
- **v1.1 Phase 3 deferred**: Hermes deployment via `skills.external_dirs` deferred until after v2.0 completion
- **Runtime data path has a typo**: directory is `omonigraph-vault` (not `omnigraph-vault`) — baked into config.py and deployed; do not change without coordinated migration
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
| KG-RAG Architecture: Image Embedding Strategy | Choice between Vision API description + Gemini Embeddings vs. embedding-2 multimodal | ✓ Keep Method A (LightRAG has no multimodal vector support) |
| Hermes deployment deferred to post-v2.0 | Knowledge Infrastructure (rules engine + /architect skill) is higher priority than Hermes wiring | — Deferred |

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
*Last updated: 2026-04-23 — Milestone v2.0 started*
