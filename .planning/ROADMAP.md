# Roadmap

**Project:** OmniGraph-Vault
**Milestone:** Phase 2 — Skill Packaging + Gate 6/7
**Last Updated:** 2026-04-21
**Coverage:** 33/33 v1 requirements mapped

---

## Phases

- [ ] **Phase 1: Bug Fixes + Gate 6 Validation** - Fix four confirmed pipeline bugs and validate cross-article synthesis against 3 real WeChat articles
- [ ] **Phase 2: Skill Packaging** - Package ingest and query pipelines as Hermes agent skills with shell wrappers and a local LLM test harness
- [ ] **Phase 3: Deploy + Gate 7 Validation** - Deploy both skills to Hermes and validate trigger dispatch, script execution, and guard clauses end-to-end

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
- [ ] 01-01-PLAN.md — Fix all infrastructure bugs: config constants, hardcoded paths, missing import, default mode, bare excepts, ingest_pdf variables, image counter
- [ ] 01-02-PLAN.md — Gate 6 validation: update SKILL.md Case 5, add test case, run skill_runner, manual pipeline verification
**UI hint**: no

### Phase 2: Skill Packaging
**Goal**: Hermes can route "add this to my KB" and "what do I know about X" to the correct skills, which call the Python scripts with proper venv activation, working-directory setup, and human-readable error messages.
**Depends on**: Phase 1
**Requirements**: SKILL-01, SKILL-02, SKILL-03, SKILL-04, SKILL-05, SKILL-06, SKILL-07, SKILL-08, SKILL-09, SKILL-10, SKILL-11, SKILL-12, TEST-01, TEST-02, TEST-03, TEST-04
**Success Criteria** (what must be TRUE):
  1. `run-ingest.sh` and `run-query.sh` each activate the correct venv and invoke Python regardless of the caller's working directory
  2. Each skill's SKILL.md contains a decision tree with explicit "when NOT to trigger" sections covering the other skill's intent
  3. `python skill_runner.py skills/omnigraph-ingest --test-file tests/skills/test_omnigraph_ingest.json` exits 0
  4. `python skill_runner.py skills/omnigraph-query --test-file tests/skills/test_omnigraph_query.json` exits 0
**Plans**: TBD
**UI hint**: no

### Phase 3: Deploy + Gate 7 Validation
**Goal**: Both skills are deployed to the Hermes workspace and pass all trigger dispatch, guard clause, and cross-article synthesis tests in real Hermes on the target machine.
**Depends on**: Phase 2
**Requirements**: GATE7-01, GATE7-02, GATE7-03, GATE7-04, GATE7-05, GATE7-06, GATE7-07, GATE7-08, GATE7-09
**Success Criteria** (what must be TRUE):
  1. Shell wrappers executed from `/tmp` (not project root) exit 0 and produce expected output on both Git Bash and Windows
  2. Hermes routes "add this article to my knowledge base" to `omnigraph_ingest` and "what do I know about LightRAG?" to `omnigraph_query` — never to the wrong skill
  3. Running `run-ingest.sh` with `GEMINI_API_KEY` unset prints a human-readable error and exits non-zero — no Python traceback visible
  4. A cross-article synthesis query in real Hermes returns a multi-source answer referencing the 3 Gate 6 articles
**Plans**: TBD
**UI hint**: no

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Bug Fixes + Gate 6 Validation | 0/2 | Planned | - |
| 2. Skill Packaging | 0/? | Not started | - |
| 3. Deploy + Gate 7 Validation | 0/? | Not started | - |
