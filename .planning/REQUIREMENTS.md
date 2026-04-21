# Requirements

**Project:** OmniGraph-Vault  
**Version:** v1 (Phase 2 — Skill Packaging)  
**Last Updated:** 2026-04-21

---

## v1 Requirements

### Phase 1 — Bug Fixes + Gate 6 Validation

**Infrastructure fixes (prerequisites for everything else):**

- [ ] **INFRA-01**: Add `ENTITY_BUFFER_DIR` and `CANONICAL_MAP_FILE` constants to `config.py`
- [ ] **INFRA-02**: Replace all hardcoded `/home/sztimhdd/` paths across `ingest_wechat.py`, `kg_synthesize.py`, `cognee_batch_processor.py`, `cognee_wrapper.py`, `init_cognee.py`, `list_entities.py`, `query_lightrag.py`, and all `tests/verify_gate_*.py` files with `config.py` constants
- [ ] **INFRA-03**: Add missing `import json` to `kg_synthesize.py` (Gate 6 blocker — crashes on first cross-article query when `canonical_map.json` exists)
- [ ] **INFRA-04**: Change default query mode from `"naive"` to `"hybrid"` in `kg_synthesize.py`

**Gate 6 validation:**

- [ ] **GATE6-01**: User can ingest 3 WeChat articles with shared named entities into LightRAG
- [ ] **GATE6-02**: `cognee_batch_processor.py` runs after ingestion and produces `canonical_map.json`
- [ ] **GATE6-03**: `kg_synthesize.py` produces a cross-article synthesis response that references entities from at least 2 of the 3 ingested articles
- [ ] **GATE6-04**: Manual script run confirms no crash: `ingest_wechat.py` on 3 URLs exits clean, `kg_synthesize.py` produces synthesis output without `NameError` or path errors
- [ ] **GATE6-05**: `skill_runner.py` LLM routing test passes for the ingest skill (confirms SKILL.md decision tree routes correctly before Phase 2 packaging begins)

### Phase 2 — Skill Packaging

**Ingest skill (`skills/omnigraph-ingest/`):**

- [ ] **SKILL-01**: `scripts/run-ingest.sh` shell wrapper resolves project root from `$(dirname "$0")`, activates venv (checks both `venv/Scripts/activate` and `venv/bin/activate`), verifies `GEMINI_API_KEY` is set, then calls `python ingest_wechat.py "<url>"`
- [ ] **SKILL-02**: `SKILL.md` frontmatter has `name: omnigraph_ingest`, accurate `description`, trigger phrases covering "add this to my KB / ingest / save this article / add to knowledge base" patterns
- [ ] **SKILL-03**: `SKILL.md` body contains decision tree: WeChat URL validation, pre-exec announcement ("Starting ingestion — 30–120 seconds"), success format (title + hash + method + "entity extraction queued"), and distinct failure messages for missing key, non-WeChat URL, and scrape failure
- [ ] **SKILL-04**: `SKILL.md` body contains explicit "when NOT to trigger" section (PDF redirect to multimodal_ingest, query intent → omnigraph_query)
- [ ] **SKILL-05**: `references/api-surface.md` covers script args, env vars, output format, and image server dependency
- [ ] **SKILL-06**: `README.md` covers install, env setup, and test invocation

**Query skill (`skills/omnigraph-query/`):**

- [ ] **SKILL-07**: `scripts/run-query.sh` shell wrapper with same venv/cwd/env pre-flight pattern, calls `python kg_synthesize.py "<query>" hybrid`
- [ ] **SKILL-08**: `SKILL.md` frontmatter with `name: omnigraph_query`, description, triggers covering "what do I know about / search my KB / tell me about" patterns
- [ ] **SKILL-09**: `SKILL.md` body contains: image server warning (port 8765 check), pre-exec announcement ("Querying — 15–60 seconds"), synthesis output rendered as Markdown + file path, empty KB detection response, and distinct failure messages
- [ ] **SKILL-10**: `SKILL.md` body contains "when NOT to trigger" section (ingest intent → omnigraph_ingest, web search intent → leave to agent default)
- [ ] **SKILL-11**: `references/api-surface.md` covers query modes (naive/local/global/hybrid/mix), optional mode keyword, output file location
- [ ] **SKILL-12**: `README.md` covers install, env setup, and test invocation

**Local testing harness:**

- [ ] **TEST-01**: `tests/skills/test_omnigraph_ingest.json` covers trigger phrase matching, WeChat URL guard, non-WeChat URL guard, missing key guard, and wrong-skill redirect
- [ ] **TEST-02**: `tests/skills/test_omnigraph_query.json` covers trigger phrase matching, empty KB response, successful synthesis output format, and wrong-skill redirect
- [ ] **TEST-03**: `python skill_runner.py skills/omnigraph-ingest --test-file tests/skills/test_omnigraph_ingest.json` exits 0
- [ ] **TEST-04**: `python skill_runner.py skills/omnigraph-query --test-file tests/skills/test_omnigraph_query.json` exits 0

### Phase 3 — Deploy + Gate 7 Validation

- [ ] **GATE7-01**: Both `run-ingest.sh` and `run-query.sh` execute successfully when invoked from `/tmp` (working directory is NOT the project root)
- [ ] **GATE7-02**: Shell wrappers work on Windows (confirmed in Git Bash; fallback Python launcher if PowerShell is Hermes's exec shell)
- [ ] **GATE7-03**: Skills are deployed to `<hermes-workspace>/skills/` and appear in `hermes skills list`
- [ ] **GATE7-04**: Ingest trigger dispatch — Hermes correctly routes "add this article to my knowledge base" to `omnigraph_ingest` (not another skill)
- [ ] **GATE7-05**: Query trigger dispatch — Hermes correctly routes "what do I know about LightRAG?" to `omnigraph_query`
- [ ] **GATE7-06**: Cross-article synthesis — query returns multi-source answer referencing the 3 Gate 6 articles
- [ ] **GATE7-07**: Wrong-trigger rejection — "search the web for LightRAG tutorials" does NOT fire `omnigraph_query`
- [ ] **GATE7-08**: Missing-key guard — `run-ingest.sh` with `GEMINI_API_KEY` unset exits with human-readable error, not a Python traceback
- [ ] **GATE7-09**: CDP-not-running guard — ingest with Apify disabled and CDP unreachable surfaces clear failure message

---

## v2 Requirements (Deferred)

- Duplicate URL detection before ingestion (check existing image hash dirs)
- Streaming progress feedback during long-running ingestion
- `omnigraph_synthesize` skill (dedicated report generation, separate from query)
- `omnigraph_status` skill (graph stats, image server health, queue depth)
- `omnigraph_manage` skill (list/delete/reindex entities)
- Batch ingestion (multiple URLs in one call)
- Multi-source ingestion: RSS feeds, GitHub repos, Zhihu

---

## Out of Scope

- Multi-source batch ingestion (RSS, GitHub API, Zhihu scraping) — Phase 3+ vision
- Cross-validation and confidence scoring layer — Phase 3+ vision
- Self-completing knowledge graph (gap detection, auto-fill) — Phase 4 vision
- REST API for remote agent calls — future
- Webhook-based ingestion (Telegram → OmniGraph-Vault) — future
- Multi-user / team sharing — intentionally single-user, out of scope permanently
- Openclaw-first skill packaging — secondary to Hermes; same SKILL.md format, different deployment path

---

## Traceability

| REQ-ID | Phase | Maps to Roadmap Phase | Status |
|--------|-------|-----------------------|--------|
| INFRA-01 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| INFRA-02 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| INFRA-03 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| INFRA-04 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| GATE6-01 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| GATE6-02 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| GATE6-03 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| GATE6-04 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| SKILL-01 | 2 | Phase 2: Skill Packaging | Pending |
| SKILL-02 | 2 | Phase 2: Skill Packaging | Pending |
| SKILL-03 | 2 | Phase 2: Skill Packaging | Pending |
| SKILL-04 | 2 | Phase 2: Skill Packaging | Pending |
| SKILL-05 | 2 | Phase 2: Skill Packaging | Pending |
| SKILL-06 | 2 | Phase 2: Skill Packaging | Pending |
| SKILL-07 | 2 | Phase 2: Skill Packaging | Pending |
| SKILL-08 | 2 | Phase 2: Skill Packaging | Pending |
| SKILL-09 | 2 | Phase 2: Skill Packaging | Pending |
| SKILL-10 | 2 | Phase 2: Skill Packaging | Pending |
| SKILL-11 | 2 | Phase 2: Skill Packaging | Pending |
| SKILL-12 | 2 | Phase 2: Skill Packaging | Pending |
| TEST-01 | 2 | Phase 2: Skill Packaging | Pending |
| TEST-02 | 2 | Phase 2: Skill Packaging | Pending |
| TEST-03 | 2 | Phase 2: Skill Packaging | Pending |
| TEST-04 | 2 | Phase 2: Skill Packaging | Pending |
| GATE7-01 | 3 | Phase 3: Deploy + Gate 7 Validation | Pending |
| GATE7-02 | 3 | Phase 3: Deploy + Gate 7 Validation | Pending |
| GATE7-03 | 3 | Phase 3: Deploy + Gate 7 Validation | Pending |
| GATE7-04 | 3 | Phase 3: Deploy + Gate 7 Validation | Pending |
| GATE7-05 | 3 | Phase 3: Deploy + Gate 7 Validation | Pending |
| GATE7-06 | 3 | Phase 3: Deploy + Gate 7 Validation | Pending |
| GATE7-07 | 3 | Phase 3: Deploy + Gate 7 Validation | Pending |
| GATE7-08 | 3 | Phase 3: Deploy + Gate 7 Validation | Pending |
| GATE7-09 | 3 | Phase 3: Deploy + Gate 7 Validation | Pending |
