# Roadmap

**Project:** OmniGraph-Vault
**Milestone:** v1.1 — SkillHub-Ready Skill Packaging
**Last Updated:** 2026-04-23
**Coverage:** 43/43 v1 requirements mapped

---

## Phases

- [x] **Phase 1: Bug Fixes + Gate 6 Validation** - Fix four confirmed pipeline bugs (INFRA fixes done, Gate 6 validation deferred — covered by v2.0 integration tests)
- [x] **Phase 2: SkillHub-Ready Skill Packaging** - Upgrade both skills into production-grade SkillHub packages with CWD-independent wrappers, reference docs, eval suites, and a deployment-ready structure
- [ ] **Phase 3: Hermes Deployment + Gate 7 Validation** - Deploy all 3 skills to Hermes via `skills.external_dirs`, validate trigger dispatch, wrapper execution, guard clauses, and cross-article synthesis end-to-end

---

## Phase Details

### Phase 1: Bug Fixes + Gate 6 Validation

**Goal**: The core pipeline reliably ingests multiple articles and returns a cross-article synthesis on any machine without crashing or producing degraded results.
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, GATE6-01, GATE6-02, GATE6-03, GATE6-04, GATE6-05

**Success Criteria** (what must be TRUE):

1. Running `kg_synthesize.py` on a machine other than the original dev box does not raise a path error or `NameError`
2. A cross-article synthesis query returns a response that references named entities from at least 2 of the 3 ingested articles
3. `cognee_batch_processor.py` completes after ingestion and produces a valid `canonical_map.json` using only config constants (no hardcoded paths)
4. Manual script run (ingest + synthesize) exits clean with no crashes
5. `skill_runner.py` LLM routing test passes for the ingest skill decision tree

**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md — Fix all infrastructure bugs: config constants, hardcoded paths, missing import, default mode, bare excepts, ingest_pdf variables, image counter (COMPLETED 2026-04-21)
- [x] 01-02-PLAN.md — Gate 6 validation: skill_runner 9/9 automated (GATE6-05 PASS); manual synthesis covered by KOL cold-start bridge 260423-fq7 (COMPLETED 2026-04-23)

**UI hint**: no

### Phase 2: SkillHub-Ready Skill Packaging

**Goal**: Both skills satisfy the SkillHub package contract — pushy descriptions, CWD-independent wrappers, reference docs, eval suites — and pass all local skill_runner tests. No Hermes required; this phase is fully local.
**Depends on**: Phase 1
**Requirements**: PKG-01, PKG-02, PKG-03, PKG-04, SKILL-01, SKILL-02, SKILL-03, SKILL-04, SKILL-05, SKILL-07, SKILL-08, SKILL-09, SKILL-10, SKILL-11, EVAL-01, EVAL-02, TEST-01, TEST-02, TEST-03, TEST-04

**Success Criteria** (what must be TRUE):

1. Both `SKILL.md` descriptions are 100-200 words in SkillHub pushy format (starts with "Use this skill when...", ends with "Do NOT use when...")
2. `scripts/ingest.sh` and `scripts/query.sh` each work from any working directory and exit non-zero with a human-readable message when `GEMINI_API_KEY` is unset or venv is missing
3. Each skill has `evals/evals.json` with >=3 test cases in SkillHub eval schema
4. `python skill_runner.py skills/omnigraph_ingest --test-file tests/skills/test_omnigraph_ingest.json` exits 0 (9/9 cases pass)
5. `python skill_runner.py skills/omnigraph_query --test-file tests/skills/test_omnigraph_query.json` exits 0
6. `skill_runner.py` returns exit code 0 on pass, non-zero on fail (CI-compatible)
7. `scripts/install-for-hermes.sh` works from scratch on clean machine with human-readable error messages
8. Embedding strategy experiment completed and decision documented (keep current / switch / hybrid)

**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — Audit and fix all skill package files against SkillHub contract (COMPLETED 2026-04-23)
- [x] 02-02-PLAN.md — KG-RAG embedding strategy experiment and decision (COMPLETED 2026-04-23)
- [x] 02-03-PLAN.md — Run skill_runner test suites and fix until green (COMPLETED 2026-04-23)

**UI hint**: no

### Phase 3: Hermes Deployment + Gate 7 Validation

**Goal**: Both skills are deployed to Hermes via `skills.external_dirs` (repo as source of truth, no copies) and pass all trigger dispatch, guard clause, and cross-article synthesis tests in real Hermes on the target machine.
**Depends on**: Phase 2
**Requirements**: DRIFT-01, GATE7-01, GATE7-02, GATE7-03, GATE7-04, GATE7-05, GATE7-06, GATE7-07, GATE7-08, GATE7-09, GATE7-10

**Success Criteria** (what must be TRUE):

1. `hermes skills list` shows `omnigraph_ingest` and `omnigraph_query` sourced from `~/Desktop/OmniGraph-Vault/skills/` — not from `~/.hermes/skills/`
2. Shell wrappers invoked from `/tmp` exit 0 and produce expected output on Git Bash (Windows)
3. Hermes routes "add this article to my knowledge base" to `omnigraph_ingest` and "what do I know about LightRAG?" to `omnigraph_query` — never to the wrong skill
4. `scripts/ingest.sh` with `GEMINI_API_KEY` unset prints a human-readable error and exits non-zero — no Python traceback visible
5. A cross-article synthesis query in real Hermes returns a multi-source answer referencing the 3 Gate 6 articles

**Plans**: TBD

**UI hint**: no

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Bug Fixes + Gate 6 Validation | 2/2 | Complete | 2026-04-23 |
| 2. SkillHub-Ready Skill Packaging | 3/3 | Complete | 2026-04-23 |
| 3. Hermes Deployment + Gate 7 Validation | 0/? | **Next** — Deploy.md + GATE7_VALIDATION_PROMPT.md ready | - |

---

---

## Roadmap — v2.0 Knowledge Infrastructure MVP

**Milestone:** v2.0 — Knowledge Infrastructure MVP
**Last Updated:** 2026-04-23
**Coverage:** 13/13 v2.0 requirements mapped

---

## Phases (v2.0)

- [x] **Phase 4: Foundation Patch + Rules Bootstrap** - Add GitHub ingestion infrastructure to config.py and build the rules engine data artifact; unblocks all downstream work
- [x] **Phase 5: KB Population + Rules Quality Gate** - Index GitHub AI tools and 7 KOL articles, build entity_registry.json, audit rules engine to gate quality
- [x] **Phase 6: /architect Skill + Multi-Turn Testing** - Author the omnigraph_architect skill with 3-mode decision tree, extend skill_runner for multi-turn, and validate all 30 tests pass

---

## Phase Details (v2.0)

### Phase 4: Foundation Patch + Rules Bootstrap

**Goal**: The pipeline can ingest GitHub repositories without crashing, and the rules engine data artifact exists with sufficient quality to inform SKILL.md authoring.
**Depends on**: Gate 6 manual checkpoint (v1.1 carry-over prerequisite)
**Requirements**: FOUND-01, FOUND-02, FOUND-03, RULES-01

**Success Criteria** (what must be TRUE):

1. `python ingest_github.py "https://github.com/org/repo"` completes without error, adds the repo to LightRAG, and atomically writes an entry to `entity_registry.json`
2. Running `ingest_github.py` with no `GITHUB_TOKEN` set exits non-zero with a human-readable rate-limit warning (not a Python traceback)
3. `rules_engine.json` exists at project root with 20-30 rules; every rule has `id`, `condition`, `recommendation`, `dont_use`, `weight`, `tags`, and `test_scenario` fields populated
4. `kg_synthesize.py` entity normalization uses `re.sub` with `\b` word-boundary anchors — confirmed by running a synthesis query where an entity name is a substring of another word (no spurious replacement)

**Plans**: TBD

**UI hint**: no

### Phase 5: KB Population + Rules Quality Gate

**Goal**: The knowledge graph contains real-world data (50+ GitHub tools + 5-10 KOL articles) sufficient for multi-source retrieval, and the rules engine passes the quality audit needed before SKILL.md authoring begins.
**Depends on**: Phase 4 + Gate 6 manual checkpoint (GATE6-PREREQ)
**Requirements**: GATE6-PREREQ, KB-01, KB-02, KB-03, KB-04, RULES-02

**Success Criteria** (what must be TRUE):

1. 50+ GitHub AI tool repositories indexed in LightRAG; re-running `ingest_github.py` on an already-indexed URL is a no-op (duplicate detected via `entity_registry.json`)
2. `entity_registry.json` contains an entry for each ingested GitHub repo URL
3. `python query_lightrag.py "best practices for building AI agents" hybrid` returns a response referencing entities from at least 2 distinct source repositories (integration gate KB-04)
4. Rules spot-check confirms rules are plausible, cover distinct scenarios, have no obvious duplication, and all have `test_scenario` populated

**Plans**: TBD

**UI hint**: no

### Phase 6: /architect Skill + Multi-Turn Testing

**Goal**: The omnigraph_architect skill is production-ready with a 3-mode decision tree, the skill_runner supports multi-turn conversations without breaking existing tests, and all 3 skills pass their full test suites on 3 consecutive independent runs.
**Depends on**: Phase 5
**Requirements**: ARCH-01, ARCH-02, TEST-05, TEST-06, TEST-07

**Success Criteria** (what must be TRUE):

1. `skills/omnigraph_architect/SKILL.md` frontmatter `description` is 100–200 words in SkillHub pushy format (starts with "Use this skill when...", 3–5 trigger phrases, ends with "Do NOT use when..."); SKILL.md body has 3-mode decision tree (Propose / Query / Ingest); GSD:DISCUSS 4-step protocol lives in `references/discuss-protocol.md` (not inline)
2. `scripts/architect.sh propose` triggers the GSD:DISCUSS multi-turn flow; `scripts/architect.sh query "<text>"` routes to `kg_synthesize.py`; `scripts/architect.sh ingest "<url>"` routes to `ingest.sh` — all three modes work from any working directory
3. `python skill_runner.py skills/omnigraph_ingest --test-file tests/skills/test_omnigraph_ingest.json` continues to exit 0 (9/9 cases) after the `skill_runner.py` multi-turn enhancement — no regressions
4. `python skill_runner.py skills/ --test-all` exits 0 on 1 clean run with all 30 cases passing (9 ingest + 10 query + 11 architect)

**Plans**: Executed inline (no formal plan files — work done via /orchestrate Phase 2.1 and Phase 2.2)

**UI hint**: no

---

## Progress Table (v2.0)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 4. Foundation Patch + Rules Bootstrap | Done | Complete† — rules_engine.json (28 rules), ingest_github.py (Level 2) | 2026-04-23 |
| 5. KB Population + Rules Quality Gate | Done | Partial‡ — 7 KOL articles ingested, 1 GitHub repo, rules audited | 2026-04-23 |
| 6. /architect Skill + Multi-Turn Testing | Done | Complete§ — 3-mode SKILL.md, architect.sh, multi-turn skill_runner.py, 30/30 tests passing | 2026-04-23 |

† Phase 4 gaps: SC2 (`GITHUB_TOKEN` rate-limit guard not implemented — unauthenticated API only); SC4 (`kg_synthesize.py` entity normalization uses `.replace()` not `re.sub` with `\b` anchors).
‡ Phase 5 gaps: SC1/SC3 not met — only 1 GitHub repo indexed (`hermes-agent`); 50+ GitHub tool target deferred to Phase 3 v1.1 run-up or standalone batch task.
§ Phase 6 gaps: SC1 — `references/discuss-protocol.md` not created; GSD:DISCUSS protocol is inline in SKILL.md (minor — discuss-protocol.md move can be done during Phase 3 polish).

---

## What's Next

**Phase 3 (v1.1): Hermes Deployment + Gate 7 Validation** is the only remaining phase.

Deployment artifacts are ready:

- `Deploy.md` — authoritative deployment guide (3 skills, directory layout, Hermes config)
- `docs/GATE7_VALIDATION_PROMPT.md` — copy-paste kickstart prompt for remote validation (10 checks)

To execute: `git pull` on the remote Hermes PC, follow Deploy.md, paste the Gate 7 prompt.
