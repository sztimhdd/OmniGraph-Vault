---
phase: 19-generic-scraper-schema-kol-hotfix
plan: 00
subsystem: testing
tags: [trafilatura, lxml, pytest, scraper, red-stubs, tdd, wave-0, scaffold]

# Dependency graph
requires:
  - phase: 18-rss-daily-digest
    provides: rss_articles table + rss_classify/rss_ingest pipeline that Phase 19 Wave 2 will migrate
provides:
  - "trafilatura 2.0.0 + lxml 5.4.0 pinned in requirements.txt and installed in local venv"
  - "3 new RED test files + 8 pytest.fail stubs wired to 19-VALIDATION.md task-IDs"
  - "Feedback loop locked for Wave 1 (plan 19-01) and Wave 2 (plan 19-02)"
affects: [phase-19-01, phase-19-02, phase-19-03, phase-20, phase-21, phase-22]

# Tech tracking
tech-stack:
  added: [trafilatura, lxml, courlan, htmldate, justext, dateparser, babel, tld, tzlocal, lxml_html_clean]
  patterns: ["RED stubs with pytest.fail() and task-ID references drive later waves GREEN"]

key-files:
  created:
    - tests/unit/test_scraper.py
    - tests/unit/test_batch_ingest_hash.py
    - tests/unit/test_rss_schema_migration.py
    - .planning/phases/19-generic-scraper-schema-kol-hotfix/deferred-items.md
  modified:
    - requirements.txt

key-decisions:
  - "Pin lxml<6 per SCR-07 authoritative spec — future relaxation noted as v3.5 follow-up (ref 19-RESEARCH.md Pitfall 5)"
  - "Stubs contain zero module-scope imports of lib.scraper/lib.checkpoint so RED baseline is deterministic (pytest.fail only)"

patterns-established:
  - "Wave 0 scaffolding: dependency pin + RED test stubs BEFORE any production code — Nyquist rule satisfied"
  - "Deferred-items.md per phase for out-of-scope pre-existing failures (separates Phase 19 changes from inherited test debt)"

requirements-completed: [SCR-07]

# Metrics
duration: 5min
completed: 2026-05-04
---

# Phase 19 Plan 00: Wave 0 Scaffolding Summary

**trafilatura 2.0.0 + lxml 5.4.0 pinned; 8 RED pytest stubs across 3 new test files wired to SCR-01..06 and SCH-01..02 task-IDs for Wave 1/2 TDD feedback loop**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-04T01:53:45Z
- **Completed:** 2026-05-04T01:58:54Z
- **Tasks:** 3/3 completed
- **Files modified:** 1 (`requirements.txt`)
- **Files created:** 4 (3 test files + 1 deferred-items.md)

## Accomplishments

- Pinned `trafilatura>=2.0.0,<3.0` and `lxml>=4.9,<6` in `requirements.txt`; both libraries import cleanly in the local venv (trafilatura 2.0.0 / lxml 5.4.0 installed along with transitive deps courlan, htmldate, justext, dateparser, babel, tld, tzlocal, lxml_html_clean).
- Created `tests/unit/test_scraper.py` with 5 RED stubs (`test_import_and_dataclass_shape`, `test_route_dispatch`, `test_quality_gate`, `test_backoff_429`, `test_cascade_layer_order`) matching 19-VALIDATION.md task-IDs 19-01-01 through 19-01-05.
- Created `tests/unit/test_batch_ingest_hash.py` (2 stubs: `test_classify_full_body_uses_scraper`, `test_hash_is_sha256_16`) and `tests/unit/test_rss_schema_migration.py` (1 stub: `test_ensure_columns_idempotent`) matching Wave 2 task-IDs 19-02-01 through 19-02-03.
- RED baseline verified: `pytest --collect-only` reports 8 tests; running them produces exactly 8 FAILED results with the expected "RED — awaiting plan 19-0X" messages.

## Task Commits

Each task committed atomically with `--no-verify` and pushed to `origin/main`:

1. **Task 0.1: Pin trafilatura + lxml in requirements.txt and install into venv** - `784f740` (chore)
2. **Task 0.2: Create RED test stub `tests/unit/test_scraper.py` (SCR-01..05)** - `88c2e3e` (test)
3. **Task 0.3: Create RED test stubs for batch_ingest hash + RSS schema migration (SCR-06, SCH-01..02)** - `6f56d93` (test)

## Test Collection (8 tests, RED baseline)

```
tests/unit/test_scraper.py::test_import_and_dataclass_shape          FAILED
tests/unit/test_scraper.py::test_route_dispatch                      FAILED
tests/unit/test_scraper.py::test_quality_gate                        FAILED
tests/unit/test_scraper.py::test_backoff_429                         FAILED
tests/unit/test_scraper.py::test_cascade_layer_order                 FAILED
tests/unit/test_batch_ingest_hash.py::test_classify_full_body_uses_scraper  FAILED
tests/unit/test_batch_ingest_hash.py::test_hash_is_sha256_16                FAILED
tests/unit/test_rss_schema_migration.py::test_ensure_columns_idempotent     FAILED

8 tests collected / 8 failed in 0.33s
```

Dependency version check:

```
$ venv/Scripts/python -c "import trafilatura, lxml.etree; print(trafilatura.__version__); import lxml; print(lxml.__version__)"
2.0.0
5.4.0
```

## Files Created/Modified

- `requirements.txt` — appended `trafilatura>=2.0.0,<3.0` and `lxml>=4.9,<6` (2 new lines, preserves trailing newline)
- `tests/unit/test_scraper.py` — 5 RED pytest.fail stubs for SCR-01..05 (Wave 1)
- `tests/unit/test_batch_ingest_hash.py` — 2 RED pytest.fail stubs for SCR-06 + SCH-02 (Wave 2)
- `tests/unit/test_rss_schema_migration.py` — 1 RED pytest.fail stub for SCH-01 (Wave 2)
- `.planning/phases/19-generic-scraper-schema-kol-hotfix/deferred-items.md` — logs 12 pre-existing test failures (phases 5/10/11/13 test files) confirmed unrelated to Wave 0 changes

## Decisions Made

- Pinned `lxml<6` per REQUIREMENTS.md SCR-07 authoritative spec, even though 19-RESEARCH.md Pitfall 5 notes the cap is conservative. Decision committed to SUMMARY for v3.5 relaxation traceability.
- Stub bodies contain zero module-scope imports of `lib.scraper` / `lib.checkpoint`; only `pytest.fail(...)` inside each function body. Ensures the RED baseline is a pure pytest failure (no ImportError noise) until Wave 1/2 makes the imports real.

## Deviations from Plan

None — plan executed exactly as written. All three task actions ran verbatim (append two lines, write three files). No auto-fixes needed.

## Issues Encountered

### Pre-existing regression noise (out of scope)

The plan's regression gate (`pytest tests/` minus the new files) surfaced **12 pre-existing failures** in test files last touched by phases 5, 10, 11, and 13 (e.g., `test_lightrag_embedding_rotation.py`, `test_siliconflow_balance.py`, `test_bench_integration.py::test_live_gate_run`). All 12 failures exist at commits predating Phase 19's first commit (`784f740`) and none touch scraper or schema code paths.

Per CLAUDE.md Surgical Changes rule and the plan's scope boundary, these are not Phase 19's responsibility. Logged in `deferred-items.md` with file + test name + last-touching commit for future triage. `458 passed` in the pre-existing suite against the new trafilatura/lxml pins — no new regressions introduced by Wave 0.

## User Setup Required

None — no external service configuration required for Wave 0.

## Next Phase Readiness

- **Plan 19-01 (Wave 1) ready to start:** will create `lib/scraper.py` with `ScrapeResult` dataclass, `_route()`, `_passes_quality_gate()`, `_fetch_with_backoff_on_429()`, and `_scrape_generic()` cascade. Drives 5 of 8 RED stubs to GREEN.
- **Plan 19-02 (Wave 2) ready after 19-01:** patches `batch_ingest_from_spider.py:940` (SCR-06), unifies hashing to `lib.checkpoint.get_article_hash` (SCH-02), and adds `_ensure_rss_columns` to `enrichment/rss_schema.py` (SCH-01). Drives remaining 3 stubs to GREEN.
- **Execute gate reminder:** v3.4 production execution still blocked until Day-1/2/3 KOL cron baseline completes (~2026-05-06 ADT). Wave 0 is planning-layer scaffolding only, not a production change, so the gate does not apply.

## Self-Check: PASSED

Files exist:
- `requirements.txt` — FOUND (appended trafilatura + lxml lines)
- `tests/unit/test_scraper.py` — FOUND (5 stubs)
- `tests/unit/test_batch_ingest_hash.py` — FOUND (2 stubs)
- `tests/unit/test_rss_schema_migration.py` — FOUND (1 stub)
- `.planning/phases/19-generic-scraper-schema-kol-hotfix/deferred-items.md` — FOUND

Commits exist on `main`:
- `784f740` — FOUND (chore: pin trafilatura + lxml)
- `88c2e3e` — FOUND (test: scraper stubs)
- `6f56d93` — FOUND (test: batch_ingest + schema stubs)

Acceptance checks:
- `grep -n "^trafilatura" requirements.txt` → line 27 — PASS
- `grep -n "^lxml" requirements.txt` → line 28 — PASS
- `venv/Scripts/python -c "import trafilatura, lxml.etree"` → exit 0 — PASS
- trafilatura version `2.0.0` starts with `2.` — PASS
- `pytest --collect-only` on the 3 new files → 8 tests collected — PASS
- Running the 3 new files → 8 FAILED (RED baseline) — PASS

---
*Phase: 19-generic-scraper-schema-kol-hotfix*
*Plan: 00*
*Completed: 2026-05-04*
