# Phase 7: model-key-management — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `07-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-04-28
**Phase:** 07-model-key-management
**Areas discussed:** Cross-phase coordination, Model config pattern, Rollout strategy, Key management (BACKUP handling), ingest_github drift, Test mocking, SKILL.md scope, RPM override

---

## Cross-Phase Coordination (Phase 5/7 overlap)

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 7 lands first, P5 Wave 0 shrinks | P5 drops its D-01/D-02 work and just edits lib/models.py:EMBEDDING_MODEL. Phase 7 is a prerequisite for P5 build. | ✓ |
| Phase 5 lands first, P7 absorbs later | P5 creates its own lightrag_embedding.py + env var. P7 later migrates those into lib/. Two module locations coexist during the gap. | |
| Merge P5 Wave 0 into Phase 7 | P7 ships lib/ AND the embedding-2 migration + 18-doc re-embed + 6-file consolidation. P5 Wave 0 disappears. Phase 7 grows ~2 days. | |
| Independent, accept coexistence | Both phases ship separately; P5 uses env var for EMBEDDING_MODEL, P7 uses constants for LLM models. Two patterns in codebase. | |

**User's choice:** Phase 7 lands first.
**Notes:** Simplest world post-land. Accepting Phase 7 as blocking prerequisite for Phase 5 build mode; Phase 5's Wave 0 plan file needs replanning.

---

## Model Config Pattern (constants vs env var)

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: constant default + env override | lib/models.py holds greppable defaults; OMNIGRAPH_MODEL_* env vars override at runtime. | ✓ |
| Constants only (strict Phase 7) | lib/models.py is the only source of truth. Model change = code edit + commit + deploy. | |
| Env vars only (strict Phase 5) | All model names in .env; lib/models.py becomes thin os.environ reader. | |

**User's choice:** Hybrid.
**Notes:** Satisfies both Phase 5 D-02's rollback-without-deploy intent and Phase 7 §3 D7's grep-source-of-truth intent.

---

## Rollout Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Per-file commits with green tests between (5 waves) | Wave 0: lib + tests. Wave 1: ingest_wechat.py ref. Wave 2: remaining P0. Wave 3: P1 (cognee + enrichment). Wave 4: P2 + SKILL.md + docs. | ✓ |
| Atomic single-commit migration | One big commit touching all 25 files. Faster to "done"; harder to bisect. | |
| Feature flag (OMNIGRAPH_USE_LIB=1) | Old and new code paths coexist; flag controls selection. Double-maintenance window; Phase 8 removes. | |

**User's choice:** Per-file commits, 5 waves.
**Notes:** Any single file revertable independently. No feature-flag complexity.

---

## GEMINI_API_KEY_BACKUP Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Fold into OMNIGRAPH_GEMINI_KEYS pool immediately | api_keys.py treats BACKUP as second entry in pool. One migration step. | ✓ |
| Keep as legacy shim for one release | Phase 7 honors both old and new forms; Phase 8 removes shim. | |
| Error with migration message | Raise on BACKUP usage post-Phase-7. Forces clean migration; zero stale-behavior risk. | |

**User's choice:** Fold immediately.
**Notes:** No deprecation window; migration docs will show the OMNIGRAPH_GEMINI_KEYS=... single-variable form as the target.

---

## ingest_github.py Model Drift

| Option | Description | Selected |
|--------|-------------|----------|
| Lock to canonical (gemini-2.5-flash-lite) | Change ingest_github.py to use lib.models.INGESTION_LLM. Removes preview-model footgun. Research doc recommended this. | |
| Keep preview via dedicated constant (GITHUB_INGEST_LLM) | Add GITHUB_INGEST_LLM = "gemini-3.1-flash-lite-preview" to lib/models.py. Preserves whatever reasoning advantage preview gives on GitHub metadata. | ✓ |
| Defer — Phase 7 doesn't touch this | ingest_github.py keeps its hardcoded string; future phase reconciles. | |

**User's choice:** Keep preview via dedicated constant.
**Notes:** Research doc had recommended locking to canonical, but user preserved the preview-model usage. Drift risk now explicit: a single constant to audit, not a hardcoded string. Planner must wire ingest_github.py to lib.models.GITHUB_INGEST_LLM, not INGESTION_LLM.

---

## Test Mocking Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Mock at lib level | One monkeypatch of lib.llm_client.generate covers every consumer. Simpler tests; SDK changes don't require test edits. | ✓ |
| Keep per-call-site mocks | Don't touch existing test patches. Phase 7's test migration becomes purely mechanical. | |
| Both — lib-level for new tests, leave old alone | Gradual convergence. New tests use lib mocks; existing untouched. | |

**User's choice:** Mock at lib level.
**Notes:** Existing per-call-site mocks in tests/verify_gate_*.py and tests/unit/*.py migrate as part of Wave 4. New tests written during Phase 7 must mock at the lib level.

---

## SKILL.md Frontmatter Updates

| Option | Description | Selected |
|--------|-------------|----------|
| Update in Phase 7 | All 3 Hermes skills (ingest, query, architect) get required_environment_variables updated to OMNIGRAPH_GEMINI_KEY. OpenClaw metadata added. Wave 4 scope. | ✓ |
| Defer to Phase 8 | Skills keep declaring GEMINI_API_KEY; Phase 7 only touches Python. Lower blast radius; two deploys. | |

**User's choice:** Update in Phase 7.
**Notes:** One-phase deploy story preferred over Python-only + separate SKILL.md phase.

---

## RPM Override Mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Ship the override | lib/rate_limit.py reads OMNIGRAPH_RPM_<MODEL> env vars first. Paid-tier upgrade = env change. | ✓ |
| Defer — free tier only for now | lib/rate_limit.py uses constants verbatim. Phase 8 adds the override. | |

**User's choice:** Ship the override.
**Notes:** ~20 lines of code; user is free-tier today but forward-compatible with paid upgrade.

---

## Claude's Discretion

The user explicitly opted not to discuss:
- Deploy.md update depth — recommend full table of all OMNIGRAPH_* vars
- cognee_bridge observer sync-vs-async — recommend sync (research doc's reference impl)
- config.py refactor depth — keep file; delegate key/model concerns to lib/
- CLAUDE.md (project-level) new-env-var paragraph — recommend yes
- File ordering within waves 2 and 3
- Pytest fixture structure
- Whether to fix LightRAG's mixed-SDK bug upstream (recommend: separate issue, not Phase 7 scope)

## Deferred Ideas

- Multi-vendor LLM abstraction (OpenAI, Anthropic, DeepSeek) — future phase
- Encrypted key storage — hosts handle
- Per-skill scoping workaround — blocked on Hermes #410
- Fix for LightRAG's deprecated-SDK exception import — upstream concern
- Removal of GEMINI_API_KEY fallback — keep indefinitely for dev ergonomics
- Cognee LLM calls routed through Phase 7's retry layer — bridge handles key propagation only
