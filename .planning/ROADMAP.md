# Roadmap

**Project:** OmniGraph-Vault
**Milestone:** v1.1 — SkillHub-Ready Skill Packaging
**Last Updated:** 2026-04-21
**Coverage:** 43/43 v1 requirements mapped

---

## Phases

- [x] **Phase 1: Bug Fixes + Gate 6 Validation** - Fix four confirmed pipeline bugs (50% complete: INFRA fixes done, Gate 6 validation pending)
- [ ] **Phase 2: SkillHub-Ready Skill Packaging** - Upgrade both skills into production-grade SkillHub packages with CWD-independent wrappers, reference docs, eval suites, and a deployment-ready structure
- [ ] **Phase 3: Hermes Deployment + Gate 7 Validation** - Deploy both skills to Hermes via `skills.external_dirs`, validate trigger dispatch, wrapper execution, guard clauses, and cross-article synthesis end-to-end

---

## Phase Details

### Phase 1: Bug Fixes + Gate 6 Validation
**Goal**: The core pipeline reliably ingests multiple articles and returns a cross-article synthesis on any machine without crashing or producing degraded results.
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, GATE6-01, GATE6-02, GATE6-03, GATE6-04, GATE6-05
**Success Criteria** (what must be TRUE):
  1. ✓ Running `kg_synthesize.py` on a machine other than the original dev box does not raise a path error or `NameError`
  2. A cross-article synthesis query returns a response that references named entities from at least 2 of the 3 ingested articles
  3. `cognee_batch_processor.py` completes after ingestion and produces a valid `canonical_map.json` using only config constants (no hardcoded paths)
  4. Manual script run (ingest + synthesize) exits clean with no crashes
  5. `skill_runner.py` LLM routing test passes for the ingest skill decision tree
**Plans**: 2 plans
Plans:
- [x] 01-01-PLAN.md — Fix all infrastructure bugs: config constants, hardcoded paths, missing import, default mode, bare excepts, ingest_pdf variables, image counter (COMPLETED 2026-04-21)
- [ ] 01-02-PLAN.md — Gate 6 validation: update SKILL.md Case 5, add test case, run skill_runner, manual pipeline verification
**UI hint**: no

### Phase 2: SkillHub-Ready Skill Packaging
**Goal**: Both skills satisfy the SkillHub package contract — pushy descriptions, CWD-independent wrappers, reference docs, eval suites — and pass all local skill_runner tests. No Hermes required; this phase is fully local.
**Depends on**: Phase 1
**Requirements**: PKG-01, PKG-02, PKG-03, SKILL-01, SKILL-02, SKILL-03, SKILL-04, SKILL-05, SKILL-06, SKILL-07, SKILL-08, SKILL-09, SKILL-10, SKILL-11, SKILL-12, EVAL-01, EVAL-02, TEST-01, TEST-02, TEST-03, TEST-04
**Success Criteria** (what must be TRUE):
  1. Both `SKILL.md` descriptions are 100–200 words in SkillHub pushy format (starts with "Use this skill when...", ends with "Do NOT use when...")
  2. `scripts/ingest.sh` and `scripts/query.sh` each work from any working directory and exit non-zero with a human-readable message when `GEMINI_API_KEY` is unset or venv is missing
  3. Each skill has `evals/evals.json` with ≥3 test cases in SkillHub eval schema
  4. `python skill_runner.py skills/omnigraph_ingest --test-file tests/skills/test_omnigraph_ingest.json` exits 0 (9/9 cases pass)
  5. `python skill_runner.py skills/omnigraph_query --test-file tests/skills/test_omnigraph_query.json` exits 0
**Plans**: TBD
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
| 1. Bug Fixes + Gate 6 Validation | 0/2 | Planned | - |
| 2. SkillHub-Ready Skill Packaging | 0/? | Not started | - |
| 3. Hermes Deployment + Gate 7 Validation | 0/? | Not started | - |
