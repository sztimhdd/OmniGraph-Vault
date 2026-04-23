# Requirements

**Project:** OmniGraph-Vault  
**Version:** v2.0 (Knowledge Infrastructure MVP milestone)  
**Last Updated:** 2026-04-23

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

---

### Phase 2 — SkillHub-Ready Skill Packaging

**Description and trigger quality:**

- [x] **PKG-01**: Both `SKILL.md` descriptions are 100–200 words in SkillHub pushy format: starts with "Use this skill when...", includes 3–5 quoted trigger phrases, ends with explicit "Do NOT use when..." redirects to the correct alternative skill
- [x] **PKG-02**: Both `SKILL.md` bodies are ≤500 lines; any heavy reference content (API docs, full examples, troubleshooting tables) moved to `references/`

**Script wrapper contract:**

- [x] **PKG-03**: Both `scripts/` wrappers resolve project root from `OMNIGRAPH_ROOT` env var (fallback: `$HOME/Desktop/OmniGraph-Vault`), activate the correct venv, validate `GEMINI_API_KEY` before running, and work correctly from any calling working directory
- [x] **PKG-04**: Repo-root `README.md` covers install, env setup, Hermes `skills.external_dirs` configuration, and `skill_runner.py` + eval invocation — per SkillHub spec §7 ("README.md in repo root, not in skill/")
- [x] **SKILL-01**: `scripts/ingest.sh` announces "Starting ingestion — 30–120 seconds..." before calling `python ingest_wechat.py "<url>"` or `python multimodal_ingest.py "<path>"` based on input type; exits non-zero with human-readable message when GEMINI_API_KEY unset or venv missing
- [x] **SKILL-07**: `scripts/query.sh` announces "Querying — 15–60 seconds..." before calling `python kg_synthesize.py "<query>" <mode>`; exits non-zero with human-readable message when GEMINI_API_KEY unset or venv missing

**Ingest skill (`skills/omnigraph_ingest/`):**

- [x] **SKILL-02**: `SKILL.md` frontmatter has `name: omnigraph_ingest`, 100–200 word pushy `description` (see PKG-01), no `triggers:` block (description does the work)
- [x] **SKILL-03**: `SKILL.md` body contains decision tree: WeChat URL (→ `ingest.sh <url>`), PDF path (→ `ingest.sh <path>`), no URL (ask first), missing GEMINI_API_KEY (configuration error message), non-WeChat URL (guard/reject: ask to confirm or provide WeChat URL)
- [x] **SKILL-04**: `SKILL.md` body contains explicit "When NOT to Use" section: query intent → `omnigraph_query`, synthesis report → `omnigraph_synthesize`, graph health → `omnigraph_status`, manage entities → `omnigraph_manage`
- [x] **SKILL-05**: `references/api-surface.md` covers `scripts/ingest.sh` CLI args, required/optional env vars, dispatch logic (WeChat vs PDF), output format, exit codes, error messages, and image server dependency

**Query skill (`skills/omnigraph_query/`):**

- [x] **SKILL-08**: `SKILL.md` frontmatter with `name: omnigraph_query`, 100–200 word pushy `description`
- [x] **SKILL-09**: `SKILL.md` body contains: image server warning (port 8765, for inline images), decision tree with mode dispatch, empty KB response (advise to ingest first), destructive-action guard (→ `omnigraph_manage`), and distinct failure messages
- [x] **SKILL-10**: `SKILL.md` body contains "When NOT to Use" section: ingest intent → `omnigraph_ingest`, synthesis report → `omnigraph_synthesize`, graph health → `omnigraph_status`, manage entities → `omnigraph_manage`, general web search → leave to agent default
- [x] **SKILL-11**: `references/api-surface.md` covers `scripts/query.sh` CLI args, required/optional env vars, query modes table, output file location, exit codes, error messages

**Eval suites (SkillHub format):**

- [x] **EVAL-01**: `skills/omnigraph_ingest/evals/evals.json` in SkillHub eval schema with ≥3 test cases: WeChat URL golden path, non-WeChat URL guard, missing GEMINI_API_KEY guard
- [x] **EVAL-02**: `skills/omnigraph_query/evals/evals.json` in SkillHub eval schema with ≥3 test cases: natural-language query golden path, mode selection, empty-KB response

**Local test harness (skill_runner):**

- [x] **TEST-01**: `tests/skills/test_omnigraph_ingest.json` covers: trigger phrase matching (2+ phrases), WeChat URL guard, non-WeChat URL guard (9th case), missing key guard, wrong-skill redirect
- [x] **TEST-02**: `tests/skills/test_omnigraph_query.json` covers: trigger phrase matching, empty KB response, successful synthesis output format, wrong-skill redirect
- [ ] **TEST-03**: `python skill_runner.py skills/omnigraph_ingest --test-file tests/skills/test_omnigraph_ingest.json` exits 0 (all cases pass)
- [ ] **TEST-04**: `python skill_runner.py skills/omnigraph_query --test-file tests/skills/test_omnigraph_query.json` exits 0

---

### Phase 3 — Hermes Deployment + Gate 7 Validation

**Deployment contract:**

- [ ] **DRIFT-01**: Hermes is configured via `skills.external_dirs` to load skills directly from `~/Desktop/OmniGraph-Vault/skills/`; no skill files are copied into `~/.hermes/skills/` (prevents drift between repo and runtime)
- [ ] **GATE7-10**: `hermes skills list` output confirms `omnigraph_ingest` and `omnigraph_query` are sourced from `~/Desktop/OmniGraph-Vault/skills/`, not from `~/.hermes/skills/`

**Shell wrapper portability:**

- [ ] **GATE7-01**: Both `scripts/ingest.sh` and `scripts/query.sh` execute successfully when invoked from `/tmp` (working directory is NOT the project root)
- [ ] **GATE7-02**: Shell wrappers work on Windows in Git Bash; no PowerShell-only syntax

**Trigger dispatch:**

- [ ] **GATE7-03**: Skills are visible in `hermes skills list` after `skills.external_dirs` is configured
- [ ] **GATE7-04**: Ingest trigger dispatch — Hermes correctly routes "add this article to my knowledge base" to `omnigraph_ingest` (not another skill)
- [ ] **GATE7-05**: Query trigger dispatch — Hermes correctly routes "what do I know about LightRAG?" to `omnigraph_query`

**Cross-article synthesis (Gate 7):**

- [ ] **GATE7-06**: Cross-article synthesis — query returns multi-source answer referencing the 3 Gate 6 articles when executed through real Hermes

**Guard clauses:**

- [ ] **GATE7-07**: Wrong-trigger rejection — "search the web for LightRAG tutorials" does NOT fire `omnigraph_query`
- [ ] **GATE7-08**: Missing-key guard — `scripts/ingest.sh` with `GEMINI_API_KEY` unset prints human-readable error and exits non-zero — no Python traceback visible
- [ ] **GATE7-09**: CDP-not-running guard — ingest with Apify disabled and CDP unreachable surfaces clear failure message via SKILL.md error handling

---

---

## v2.0 Requirements

### Foundation (prerequisites — must land before KB population)

- [ ] **FOUND-01**: `config.py` adds two constants: `GITHUB_TOKEN` (env var, optional but required at batch scale) and `ENTITY_REGISTRY_FILE` (absolute path to `entity_registry.json` at project root) — follows existing constants pattern; no other changes
- [ ] **FOUND-02**: New `ingest_github.py` script using the **GitHub REST API** (via existing `requests` library — Graphify MCP does not exist and is not used): accepts a GitHub repo URL, fetches README via `api.github.com` with authenticated headers (`GITHUB_TOKEN`), strips badge images and `pip install` boilerplate, prepends `# Source: github.com/org/repo` header, calls `rag.ainsert()`, and atomically updates `entity_registry.json` with `{url: entity_id}` entry; exits non-zero with human-readable message on rate-limit or auth failure
- [ ] **FOUND-03**: `kg_synthesize.py` canonical_map replacement uses `re.sub` with `\b` word-boundary anchors (replace current `str.replace`) to prevent spurious replacements during bulk ingestion

### Rules Engine

- [ ] **RULES-01**: `rules_engine.json` at project root contains 20–30 rules; each rule has fields: `id` (string), `condition` (string, when this rule applies), `recommendation` (string), `dont_use` (list of strings), `weight` (int 0–10), `tags` (list: `solo-dev` / `startup` / `researcher`), `test_scenario` (string describing a test case for this rule)
- [ ] **RULES-02**: Quality gate before `/architect` SKILL.md authoring: manual spot-check confirms rules look plausible, cover distinct scenarios (not duplicates of each other), and are not obviously generic advice; all 20–30 rules have `test_scenario` populated

### Knowledge Source Integration Model

> **How GitHub content and KOL content integrate in LightRAG — read this before KB population.**

Both `ingest_github.py` and `ingest_wechat.py` call `rag.ainsert(markdown_text)` against the **same LightRAG instance** (storage: `~/.hermes/omonigraph-vault/lightrag_storage/`). There is no separate Graphify graph — all knowledge lives in one graph.

**Integration mechanism:**

1. **Shared entity namespace** — LightRAG uses Gemini to extract entities and relationships from every inserted document. When "LangChain" appears in a GitHub README and also in a KOL WeChat article, LightRAG links them as the same entity node (or adjacent nodes) in the knowledge graph.

2. **Chinese↔English normalization** — `cognee_batch_processor.py` runs after ingestion and writes `canonical_map.json` (entity alias map). At query time, `kg_synthesize.py` normalizes the query using `canonical_map.json` before calling LightRAG — so searching "LangChain" also hits content that used "LangChain框架" or other alias forms.

3. **Hybrid retrieval across both sources** — `rag.aquery(mode=hybrid)` runs dense vector search AND graph traversal simultaneously. A query about "best practices for building AI agents" will retrieve relevant chunks from both GitHub READMEs and KOL articles in one call, ranked by relevance.

4. **Source provenance** — `ingest_github.py` prepends `# Source: github.com/org/repo` to each document before insertion. KOL articles retain their URL metadata from `ingest_wechat.py`. LightRAG stores this provenance in node metadata, so synthesis responses can cite both source types.

5. **No separate query paths** — There is no "Graphify query" and "LightRAG query" running in parallel. All queries go through `kg_synthesize.py` → `rag.aquery()`. The GitHub data and KOL data are integrated at insertion time, not at query time.

**Duplicate prevention:**

- GitHub repos: `entity_registry.json` (keyed by GitHub URL, written by `ingest_github.py`) — re-running on an already-indexed URL is a no-op
- KOL articles: `entity_buffer/` + `.processed` marker (written by `ingest_wechat.py`) — idempotent by design

---

### KB Population

- [ ] **GATE6-PREREQ**: Gate 6 manual checkpoint must pass before KB population begins — complete GATE6-01 through GATE6-04 from v1.1 (ingest 3 WeChat articles with shared entities, run `cognee_batch_processor.py`, confirm cross-article synthesis response references entities from ≥2 articles); validates that multi-document retrieval is functional before adding 50+ more documents to the graph

- [ ] **KB-01**: 50+ GitHub AI tool repositories indexed in LightRAG using `ingest_github.py`; duplicate detection works via `entity_registry.json` (re-running on already-indexed URL is a no-op)
- [ ] **KB-02**: `entity_registry.json` maps each ingested GitHub repo URL to its LightRAG entity ID; populated atomically after each repo ingestion; used for duplicate detection in Ingest mode
- [ ] **KB-03**: 5–10 KOL articles (WeChat, GitHub issue discussions, or Zhihu Q&A) ingested via `ingest_wechat.py`; topics cover AI agent architecture, tool selection, and engineering best practices
- [ ] **KB-04**: Integration gate — `python query_lightrag.py "best practices for building AI agents" hybrid` returns a response referencing entities from ≥2 distinct source repositories; confirms multi-source retrieval before `/architect` phase begins

### /architect Skill

- [ ] **ARCH-01**: `.planning/GSD_DISCUSS_PATTERN.md` documents the 4-step Propose conversation flow: Default Guess → Q1 (team size + project type) → Q2 (primary constraint) → Output (stack recommendation + `dont_use` list + TDD template hint); `skills/omnigraph_architect/SKILL.md` frontmatter `description` is **100–200 words in SkillHub pushy format** (starts with "Use this skill when...", includes 3–5 quoted trigger phrases, ends with explicit "Do NOT use when..." redirects); SKILL.md body has 3-mode decision tree (Propose / Query / Ingest); GSD:DISCUSS protocol in `references/discuss-protocol.md` (Level 2 loading)
- [ ] **ARCH-02**: `skills/omnigraph_architect/scripts/architect.sh` accepts `propose`, `query`, or `ingest` as positional arg 1; resolves project root from `OMNIGRAPH_ROOT` env var (fallback: `$HOME/Desktop/OmniGraph-Vault`); validates `GEMINI_API_KEY`; exits non-zero with human-readable message on missing env or missing venv; works from any working directory

### Testing

- [ ] **TEST-05**: `skill_runner.py` supports multi-turn conversations: `TestCase` dataclass gains `inputs: list[str]` field alongside (not replacing) existing `input: str` field; `call_gemini()` accepts growing `contents` list; `expect_final` assertions checked only on last turn's response; fresh `contents = []` per `TestCase` (no context leakage between cases); all 19 existing test cases continue to pass unchanged
- [ ] **TEST-06**: `tests/skills/test_omnigraph_architect.json` contains ≥9 test cases: ≥3 Propose mode (multi-turn, exercises GSD:DISCUSS 4-step flow), ≥3 Query mode (single-turn KB queries, verifies routing to `query.sh`), ≥3 Ingest mode (URL routing, guard clause on non-WeChat URL)
- [ ] **TEST-07**: `python skill_runner.py skills/ --test-all` exits 0 on 1 clean run; all tests across all 3 skills pass (minimum: 9 ingest + 10 query + 9 architect = 28 cases)

---

## v2.x Requirements (Deferred to future milestone)

- Duplicate URL detection before ingestion (check existing image hash dirs)
- Streaming progress feedback during long-running ingestion
- `omnigraph_synthesize` skill (dedicated report generation, separate from query)
- `omnigraph_status` skill (graph stats, image server health, queue depth)
- `omnigraph_manage` skill (list/delete/reindex entities)
- Batch ingestion (multiple URLs in one call)
- Multi-source ingestion: RSS feeds, Zhihu
- Trigger eval optimization loop (Section 6 of SKILLHUB_REQUIREMENTS.md)
- `evals/benchmark.json` with aggregated timing/token results
- Persona-tag filtering in rules engine (solo-dev / startup / researcher)
- Ingest mode duplicate guard via entity_registry.json in architect.sh

---

## Out of Scope

- Hermes deployment via `skills.external_dirs` + Gate 7 validation — deferred until after v2.0 completes
- Multi-source batch ingestion (RSS, Zhihu scraping) — v2.x vision
- Cross-validation and confidence scoring layer — future
- Self-completing knowledge graph (gap detection, auto-fill) — future
- REST API for remote agent calls — future
- Webhook-based ingestion (Telegram → OmniGraph-Vault) — future
- Multi-user / team sharing — intentionally single-user, out of scope permanently
- Openclaw-first skill packaging — secondary to Hermes; same SKILL.md format, different deployment path
- LLM model abstraction layer (`llm_interface.py`) — not applicable; skills wrap existing pipeline

---

## Traceability

| REQ-ID | Phase | Maps to Roadmap Phase | Status |
| ------ | ----- | --------------------- | ------ |
| INFRA-01 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| INFRA-02 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| INFRA-03 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| INFRA-04 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| GATE6-01 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| GATE6-02 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| GATE6-03 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| GATE6-04 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| GATE6-05 | 1 | Phase 1: Bug Fixes + Gate 6 Validation | Pending |
| PKG-01 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| PKG-02 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| PKG-03 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| PKG-04 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| SKILL-01 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| SKILL-02 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| SKILL-03 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| SKILL-04 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| SKILL-05 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| SKILL-07 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| SKILL-08 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| SKILL-09 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| SKILL-10 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| SKILL-11 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| EVAL-01 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| EVAL-02 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| TEST-01 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| TEST-02 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Done |
| TEST-03 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Pending |
| TEST-04 | 2 | Phase 2: SkillHub-Ready Skill Packaging | Pending |
| DRIFT-01 | 3 | Phase 3: Hermes Deployment + Gate 7 Validation | Pending |
| GATE7-01 | 3 | Phase 3: Hermes Deployment + Gate 7 Validation | Pending |
| GATE7-02 | 3 | Phase 3: Hermes Deployment + Gate 7 Validation | Pending |
| GATE7-03 | 3 | Phase 3: Hermes Deployment + Gate 7 Validation | Pending |
| GATE7-04 | 3 | Phase 3: Hermes Deployment + Gate 7 Validation | Pending |
| GATE7-05 | 3 | Phase 3: Hermes Deployment + Gate 7 Validation | Pending |
| GATE7-06 | 3 | Phase 3: Hermes Deployment + Gate 7 Validation | Pending |
| GATE7-07 | 3 | Phase 3: Hermes Deployment + Gate 7 Validation | Pending |
| GATE7-08 | 3 | Phase 3: Hermes Deployment + Gate 7 Validation | Pending |
| GATE7-09 | 3 | Phase 3: Hermes Deployment + Gate 7 Validation | Pending |
| GATE7-10 | 3 | Phase 3: Hermes Deployment + Gate 7 Validation | Pending |
| FOUND-01 | 4 | Phase 4: Foundation Patch + Rules Bootstrap | Pending |
| FOUND-02 | 4 | Phase 4: Foundation Patch + Rules Bootstrap | Pending |
| FOUND-03 | 4 | Phase 4: Foundation Patch + Rules Bootstrap | Pending |
| RULES-01 | 4 | Phase 4: Foundation Patch + Rules Bootstrap | Pending |
| RULES-02 | 5 | Phase 5: KB Population + Rules Quality Gate | Pending |
| GATE6-PREREQ | 5 | Phase 5: KB Population + Rules Quality Gate (gate at phase start) | Pending |
| KB-01 | 5 | Phase 5: KB Population + Rules Quality Gate | Pending |
| KB-02 | 5 | Phase 5: KB Population + Rules Quality Gate | Pending |
| KB-03 | 5 | Phase 5: KB Population + Rules Quality Gate | Pending |
| KB-04 | 5 | Phase 5: KB Population + Rules Quality Gate | Pending |
| ARCH-01 | 6 | Phase 6: /architect Skill + Multi-Turn Testing | Pending |
| ARCH-02 | 6 | Phase 6: /architect Skill + Multi-Turn Testing | Pending |
| TEST-05 | 6 | Phase 6: /architect Skill + Multi-Turn Testing | Pending |
| TEST-06 | 6 | Phase 6: /architect Skill + Multi-Turn Testing | Pending |
| TEST-07 | 6 | Phase 6: /architect Skill + Multi-Turn Testing | Pending |
