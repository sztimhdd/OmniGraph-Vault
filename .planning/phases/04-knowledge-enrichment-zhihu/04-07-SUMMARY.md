---
phase: 04-knowledge-enrichment-zhihu
plan: 07
subsystem: infra
tags: [config, gemini, sqlite, lightrag, wechat, enrichment]

requires:
  - phase: 04-01
    provides: image_pipeline refactor used by ingest_wechat.py + enrichment/fetch_zhihu.py
  - phase: 04-04
    provides: enrichment/merge_and_ingest.py that consumes the config keys added here
  - phase: 04-06
    provides: skills/enrich_article/ that references enrichment/ modules patched here
provides:
  - 11 Phase 4 config keys in config.py (flash model default per D-12-REVISED)
  - ingest_wechat.py uses INGEST_LLM_MODEL throughout (no hardcoded flash-lite)
  - SQLite enriched + enrichment_id columns auto-migrate on every ingest_wechat import (closes Wave 3 deployment gap)
  - articles.enriched=-1 written for short articles per D-07
  - GOOGLE_GENAI_USE_VERTEXAI defensively popped in all 3 enrichment entry points
  - omnigraph_ingest SKILL.md cross-references enrich_article
affects: [04-08-and-later, phase-05, remote-deployment]

tech-stack:
  added: []
  patterns:
    - "env-driven model override: ENRICHMENT_LLM_MODEL / INGEST_LLM_MODEL read via os.environ.get() with flash default"
    - "defensive module-top env-var pop for Vertex-AI global-leak mitigation"
    - "idempotent SQLite auto-migrate at module import, guarded by DB_PATH.exists() + try/except"

key-files:
  created:
    - .planning/phases/04-knowledge-enrichment-zhihu/04-07-SUMMARY.md
  modified:
    - config.py
    - ingest_wechat.py
    - enrichment/fetch_zhihu.py
    - enrichment/merge_and_ingest.py
    - skills/omnigraph_ingest/SKILL.md

key-decisions:
  - "D-12-REVISED: gemini-2.5-flash (not flash-lite). Wave 4 E2E proved flash-lite 20-RPD quota exhausts on a single pipeline run; flash has 250 RPD. Both ENRICHMENT_LLM_MODEL and new INGEST_LLM_MODEL default to flash."
  - "New INGEST_LLM_MODEL key vs RESEARCH.md §9 — lets LightRAG entity-extraction path be tuned independently of the enrichment path."
  - "SQLite migration runs at ingest_wechat module import (not lazily) so every deploy guarantees the schema — closes STATE.md Wave 3 deployment gap."
  - "VERTEXAI pop placed at module top in fetch_zhihu + merge_and_ingest (defensive redundancy vs in-function pop in extract_questions); plan-specified."

patterns-established:
  - "Two-tier model config: ENRICHMENT_LLM_MODEL and INGEST_LLM_MODEL are independent so question-extraction and entity-extraction quotas don't starve each other"
  - "Auto-migrate on module import: any entry point that writes to kol_scan.db invokes batch_scan_kol.init_db() at import time under a DB_PATH.exists() guard"
  - "Defensive VERTEXAI pop pattern: every enrichment entry-point module pops GOOGLE_GENAI_USE_VERTEXAI at module top to neutralize the Hermes global env leak"

requirements-completed: [D-07, D-12-REVISED]

duration: 5min
completed: 2026-04-27
---

# Phase 4 Plan 07: ingest_wechat integration + 4 Wave-4 gap closures Summary

**11 new Phase 4 config keys with flash model defaults; ingest_wechat.py swapped off hardcoded flash-lite, auto-migrates SQLite on import, marks short articles enriched=-1; VERTEXAI pop defensively added to fetch_zhihu + merge_and_ingest; omnigraph_ingest skill cross-references enrich_article**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-27T21:48:36Z
- **Completed:** 2026-04-27T21:53:29Z
- **Tasks:** 4 executed (7.1, 7.2, 7.2b, 7.3); 1 deferred (7.4 to orchestrator)
- **Files modified:** 5

## Accomplishments

- **Task 7.1 (config.py):** Added 11 enrichment keys — ENRICHMENT_ENABLED, ENRICHMENT_MIN_LENGTH (2000), ENRICHMENT_MAX_QUESTIONS (3), ENRICHMENT_LLM_MODEL, INGEST_LLM_MODEL, ENRICHMENT_GROUNDING_ENABLED, ENRICHMENT_HAOWEN_TIMEOUT (120), ENRICHMENT_ZHIHU_FETCH_TIMEOUT (60), ENRICHMENT_BASE_DIR, ZHIHAO_SKILL_NAME, IMAGE_SERVER_BASE_URL. Both model keys default to `gemini-2.5-flash` per D-12-REVISED.
- **Task 7.2 (ingest_wechat.py):** Extended config import, replaced 3 hardcoded `gemini-2.5-flash-lite` strings with `INGEST_LLM_MODEL`, added SQLite auto-migrate at module import, added D-07 short-article `enriched=-1` UPDATE.
- **Task 7.2b (enrichment/fetch_zhihu.py + enrichment/merge_and_ingest.py):** Added `os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)` at module top (after imports, before functions) in both files.
- **Task 7.3 (skills/omnigraph_ingest/SKILL.md):** Added enrich_article as first bullet under Related Skills; appended one sentence to the description frontmatter clarifying this skill is the un-enriched path.

## Task Commits

Each task was committed atomically:

1. **Task 7.1: Add Phase 4 config keys to config.py (D-12-REVISED)** — `924ee6b` (feat)
2. **Task 7.2: ingest_wechat.py — INGEST_LLM_MODEL + SQLite auto-migrate + enriched=-1** — `9e2a0c1` (fix)
3. **Task 7.2b: Pop GOOGLE_GENAI_USE_VERTEXAI in fetch_zhihu + merge_and_ingest** — `1315566` (fix)
4. **Task 7.3: Cross-reference enrich_article in omnigraph_ingest SKILL.md** — `17ee797` (docs)

All 4 task commits land on branch `worktree-agent-aba3711c5fe264703`, branched from `gsd/phase-04` HEAD `e89731f`.

## Files Created/Modified

- `config.py` — +38 lines: 11 new Phase 4 config keys (flash default per D-12-REVISED).
- `ingest_wechat.py` — +25/-4 lines: INGEST_LLM_MODEL import + 3 replacements, SQLite auto-migrate block, D-07 enriched=-1 UPDATE.
- `enrichment/fetch_zhihu.py` — +6 lines: defensive VERTEXAI pop at module top.
- `enrichment/merge_and_ingest.py` — +6 lines: defensive VERTEXAI pop at module top.
- `skills/omnigraph_ingest/SKILL.md` — +2/-1 lines: enrich_article cross-reference + description clarification.

## Decisions Made

- **D-12-REVISED (inline in this plan):** Flash over flash-lite. Wave 4 test report (docs/testing/04-06-test-results.md) proved flash-lite's 20-RPD free-tier quota is exhausted by a single article's LightRAG entity extraction + image vision + question extraction pipeline. All new model keys default to `gemini-2.5-flash` (250 RPD).
- **New `INGEST_LLM_MODEL` config key (vs RESEARCH.md §9 which had only `ENRICHMENT_LLM_MODEL`):** Keeps the ingest path and the enrichment path independently tunable so one quota doesn't starve the other.
- **SQLite migration placement:** Runs at `ingest_wechat` module import time under `DB_PATH.exists()` + try/except guard. Idempotent via `batch_scan_kol._ensure_column` ALTER-TABLE guards. Closes the Wave 3 deployment gap documented in `.planning/STATE.md`.

## Deviations from Plan

None — plan executed exactly as written. All 4 task `<action>` blocks copied verbatim from the expanded plan at commit `e89731f`.

## Issues Encountered

**Pre-existing pytest collection failures (NOT caused by this plan — confirmed via `git checkout HEAD~4 -- <files>` baseline):**

- `tests/unit/test_migrations.py` collection error — `batch_scan_kol.py:24` does `import kol_config` but `kol_config.py` does not exist in the repo.
- `tests/unit/test_merge_and_ingest.py` — 3 tests fail with the same `ModuleNotFoundError: No module named 'kol_config'`.
- 34 tests pass.

Verified these 3 failures predate every commit in this plan. Logging as out-of-scope per the deviation-rules scope boundary (`kol_config` is not a file this plan modifies). Likely a separate deployment artifact that was never committed.

**Impact:** Zero on this plan's acceptance criteria. Task 7.2's migration logic is guarded with try/except, so a missing `kol_config` at runtime would log a warning and skip migration (rather than crash `ingest_wechat`). The orchestrator's Task 7.4 remote validation will surface this if it actually matters in deployment.

## Verification Output Snippets

```
=== CHECK 1: config asserts ===
config ok
=== CHECK 2: syntax ===
syntax ok
=== CHECK 3: flash-lite count in ingest_wechat.py + config.py (want 0 each) ===
0
0
=== CHECK 4: migrate import ===
migrate ok
=== CHECK 5: vertex guards ===
vertex guard ok
```

```
$ grep -c "INGEST_LLM_MODEL" ingest_wechat.py
4   # 1 import + 3 usages — matches acceptance criterion

$ python -c "import config; print(config.INGEST_LLM_MODEL)"
gemini-2.5-flash
```

## Deferred Tasks

- **Task 7.4 — Remote live-validate merge_and_ingest against Wave 4 fixtures:** Deferred to orchestrator per instructions ("Task 7.4 is orchestrator-run remote SSH validation that I'll handle after merging your worktree back to gsd/phase-04"). The executor does NOT run Task 7.4.

## Self-Check

**Commits present:**
- `924ee6b` feat(04-07): add Phase 4 enrichment config keys — FOUND
- `9e2a0c1` fix(04-07): swap flash-lite→INGEST_LLM_MODEL, add SQLite auto-migrate — FOUND
- `1315566` fix(04-07): pop GOOGLE_GENAI_USE_VERTEXAI in fetch_zhihu + merge_and_ingest — FOUND
- `17ee797` docs(04-07): cross-reference enrich_article in omnigraph_ingest SKILL.md — FOUND

**Files modified:**
- `config.py` — FOUND (contains `ENRICHMENT_LLM_MODEL`, `INGEST_LLM_MODEL`, no `flash-lite`)
- `ingest_wechat.py` — FOUND (4 `INGEST_LLM_MODEL` refs, `from batch_scan_kol import init_db`, `UPDATE articles SET enriched` block)
- `enrichment/fetch_zhihu.py` — FOUND (VERTEXAI pop present)
- `enrichment/merge_and_ingest.py` — FOUND (VERTEXAI pop present)
- `skills/omnigraph_ingest/SKILL.md` — FOUND (enrich_article cross-ref present, no `--enrich` flag)

## Self-Check: PASSED

## Next Phase Readiness

- **Ready for merge back to `gsd/phase-04`:** Worktree branch `worktree-agent-aba3711c5fe264703` contains 4 atomic task commits + 1 SUMMARY commit on top of `e89731f`.
- **Task 7.4 validation pending:** Orchestrator runs this on the remote after merging — the flash model swap + SQLite auto-migrate + VERTEXAI pops together should flip test report §4 criteria 7-12 from BLOCKED to PASS.
- **Known runtime concern:** If `kol_config.py` is also missing on the remote deployment, `batch_scan_kol` import will fail → SQLite auto-migrate will log a warning and skip (guarded). The schema migration would then need to be applied manually once, or `kol_config` would need to be deployed. Surface this to the orchestrator during 7.4 if migration is needed.

---
*Phase: 04-knowledge-enrichment-zhihu*
*Completed: 2026-04-27*
