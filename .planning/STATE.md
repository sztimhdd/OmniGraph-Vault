# Project State

**Project:** OmniGraph-Vault
**Current Phase:** 1
**Status:** planning
**Last Updated:** 2026-04-21

---

## Phase Status

- Phase 1 — Bug Fixes + Gate 6 Validation: pending
- Phase 2 — Skill Packaging: pending
- Phase 3 — Deploy + Gate 7 Validation: pending

---

## Current Focus

Phase 1: Fix four confirmed pipeline bugs (INFRA-01..04) then validate cross-article synthesis (GATE6-01..04).

Blocking bugs (must fix before any gate testing):
- INFRA-01: `ENTITY_BUFFER_DIR` and `CANONICAL_MAP_FILE` missing from `config.py`
- INFRA-02: Hardcoded `/home/sztimhdd/` paths across 9+ files
- INFRA-03: Missing `import json` in `kg_synthesize.py` (runtime crash on cross-article query)
- INFRA-04: Default query mode `"naive"` in `kg_synthesize.py` (produces poor cross-article results)

---

## Progress Bar

```
Phase 1 [          ] 0%
Phase 2 [          ] 0%
Phase 3 [          ] 0%
```

---

## Performance Metrics

- Requirements mapped: 33/33
- Phases planned: 3
- Plans written: 0
- Gates passed: 5 (Gates 1-5 + A-D from prior milestone)

---

## Accumulated Context

### Key Decisions (inherited from prior milestone)

- Cognee is always async — never block ingestion fast-path on any Cognee operation
- Atomic rename pattern for `canonical_map.json` (write `.tmp` then rename)
- `.processed` marker on entity_buffer files for batch processor idempotency
- Runtime data directory name is `omonigraph-vault` (typo baked in — do not rename)
- Two separate skills (ingest + query) rather than one unified skill

### Constraints

- Windows-primary platform (Git Bash + Edge for CDP)
- Python 3.11+, LightRAG, Cognee, Gemini 2.5 Flash/Pro — no framework migrations
- All data stays local; only Gemini API + Apify make external calls

### Open Questions

- Exact Hermes exec shell on Windows (Git Bash vs PowerShell vs cmd.exe) — validate in Phase 3 before other Gate 7 testing
- Whether `metadata.openclaw.requires.config` is enforced by Hermes or advisory only — do not rely on it; shell wrapper must always perform env pre-flight independently

---

## Session Continuity

Last session: 2026-04-21 — roadmap initialized, no implementation started.

Next action: Begin Phase 1 with `/gsd:plan-phase 1`.
