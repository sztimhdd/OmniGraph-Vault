# Project State

**Project:** OmniGraph-Vault
**Milestone:** v1.1 — SkillHub-Ready Skill Packaging
**Current Phase:** 1
**Status:** executing (Plan 01-01 complete)
**Last Updated:** 2026-04-21

---

## Phase Status

- Phase 1 — Bug Fixes + Gate 6 Validation: executing (Plan 01-01 complete, Plan 01-02 pending)
- Phase 2 — SkillHub-Ready Skill Packaging: pending
- Phase 3 — Hermes Deployment + Gate 7 Validation: pending

---

## Current Focus

Phase 1: Plan 01-01 (INFRA-01..04) COMPLETE. Plan 01-02 (Gate 6 validation) pending.

**Completed in Plan 01-01:**

- ✓ INFRA-01: Added ENTITY_BUFFER_DIR and CANONICAL_MAP_FILE to config.py
- ✓ INFRA-02: Removed all hardcoded /home/sztimhdd/ paths (13 instances across 12 files)
- ✓ INFRA-03: Added missing json import in kg_synthesize.py
- ✓ INFRA-04: Changed default query mode from "naive" to "hybrid"
- ✓ Fixed bare except clauses in cognee_wrapper.py and ingest_wechat.py
- ✓ Fixed ingest_pdf() variable references and added image counter
- ✓ Removed venv path injections from 8 files

**Next: Plan 01-02 (Gate 6 validation)**

- Ingest 3 WeChat articles with shared entities
- Run cognee_batch_processor.py for entity canonicalization
- Run kg_synthesize.py with cross-article query
- Verify synthesis references entities from ≥2 articles
- Run skill_runner.py test suite

### Phase 2 skill package files

Already on disk (created ahead of Phase 1 execution):

- `skills/omnigraph_ingest/` — upgraded SKILL.md, scripts/ingest.sh, references/, evals/
- `skills/omnigraph_query/` — upgraded SKILL.md, scripts/query.sh, references/, evals/

These do not conflict with Phase 1 code fixes; skill_runner validation happens in Phase 2.

---

## Progress Bar

```
Phase 1 [==        ] 50% (Plan 01-01 INFRA fixes complete; Plan 01-02 Gate 6 validation pending)
Phase 2 [=         ] 10% (structural files created; skill_runner validation pending)
Phase 3 [          ] 0%
```

---

## Performance Metrics

- Requirements mapped: 43/43
- Phases planned: 3
- Plans written: 2 (Phase 1 plans complete; Phase 2/3 plans TBD)
- Requirements completed: 4/43 (INFRA-01, INFRA-02, INFRA-03, INFRA-04)
- Gates passed: 5 (Gates 1-5 + A-D from prior milestone)
- Plan 01-01 execution time: 15 min

---

## Accumulated Context

### Key Decisions (inherited from prior milestone)

- Cognee is always async — never block ingestion fast-path on any Cognee operation
- Atomic rename pattern for `canonical_map.json` (write `.tmp` then rename)
- `.processed` marker on entity_buffer files for batch processor idempotency
- Runtime data directory name is `omonigraph-vault` (typo baked in — do not rename)
- Two separate skills (ingest + query) rather than one unified skill

### Key Decisions (v1.1 milestone)

- Hermes must load skills via `skills.external_dirs` pointing at repo — never copy skills to `~/.hermes/skills/` (prevents drift)
- Script wrappers resolve project root from `OMNIGRAPH_ROOT` env var (fallback: `$HOME/Desktop/OmniGraph-Vault`) — not from `$(dirname "$0")` which can break on Windows paths with spaces
- SKILL.md descriptions use SkillHub pushy format (100–200 words, explicit NOT-triggers) — Claude under-triggers without this
- evals/evals.json format follows SkillHub schema for future SkillHub submission compatibility
- Repo path (`~/Desktop/OmniGraph-Vault`) and runtime path (`~/.hermes/omonigraph-vault`) must always be explicit in wrappers

### Constraints

- Windows-primary platform (Git Bash + Edge for CDP)
- Python 3.11+, LightRAG, Cognee, Gemini 2.5 Flash/Pro — no framework migrations
- All data stays local; only Gemini API + Apify make external calls
- No LLM abstraction layer — skills wrap existing pipeline, not new standalone Python scripts

### Open Questions

- Exact Hermes exec shell on Windows (Git Bash vs PowerShell vs cmd.exe) — validate in Phase 3 before other Gate 7 testing
- Whether `metadata.openclaw.requires.config` is enforced by Hermes or advisory only — do not rely on it; shell wrapper must always perform env pre-flight independently
- Exact `skills.external_dirs` config file location and format in Hermes — validate before Phase 3 planning

---

## Session Continuity

Last session: 2026-04-21T14:00:00Z — Plan 01-01 executed: all 4 INFRA bugs fixed, 12 files updated, 15 min elapsed.

- ✓ Config-based path constants added (ENTITY_BUFFER_DIR, CANONICAL_MAP_FILE)
- ✓ All /home/sztimhdd/ hardcoded paths removed
- ✓ json import added, default mode changed to hybrid
- ✓ Exception handling improved, venv injections removed
- ✓ SUMMARY.md created and committed

Next action: Execute Plan 01-02 (Gate 6 validation) with manual script testing + skill_runner verification.
