---
phase: kb-2-topic-pillar-entity-pages
plan: 10
type: execute
wave: 5
depends_on: ["kb-2-01-fixture-extension", "kb-2-02-locale-keys", "kb-2-03-svg-icons", "kb-2-04-query-functions", "kb-2-05-topic-template", "kb-2-06-entity-template", "kb-2-07-homepage-extension", "kb-2-08-article-aside", "kb-2-09-export-driver-extension"]
files_modified:
  - tests/integration/kb/test_kb2_export.py
requirements: [TOPIC-01, TOPIC-02, TOPIC-03, TOPIC-04, TOPIC-05, ENTITY-01, ENTITY-02, ENTITY-03, ENTITY-04, LINK-01, LINK-02, LINK-03]
---

# kb-2-10 — Integration Test Plan Summary

## Objective
End-to-end integration test exercising the full kb-2 SSG pipeline against shared `fixture_db`. Verifies plans 04-09 wire correctly + UI-SPEC §8 acceptance regex pass against generated output.

## Tasks
1 task — single test file with 12+ test cases. Mirror kb-1 `tests/integration/kb/test_export.py` invocation pattern.

## Skills (per kb/docs/10-DESIGN-DISCIPLINE.md)
This plan invokes the required Test Skill literally in task `<action>` block:

- **Skill(skill="writing-tests", args="...")** — Testing Trophy integration test (no mocks, real SQLite + real driver invocation), 12+ cases covering topic outputs, entity outputs, homepage extensions, article aside, JSON-LD, sitemap, read-only, LOC budget, locale keys, icons. Parametrized fixtures for the 37 UI-SPEC §8 grep patterns.

This literal `Skill(skill=...)` string is embedded in `kb-2-10-integration-test-PLAN.md` Task 1 `<action>` block for kb/docs/10-DESIGN-DISCIPLINE.md Check 1 regex match.

## Dependency graph
- **Depends on:** ALL prior kb-2 plans (01-09) — this is the integrating gate
- **Consumed by:** kb-2 phase declaration (gate to milestone-level signoff)

## Tech-stack notes
- Pure pytest, no new deps
- Driver invocation via `subprocess.run` with KB_DB_PATH + KB_OUTPUT_DIR + KB_ENTITY_MIN_FREQ env override
- Read-only enforcement: md5 fixture_db before/after must match
- Parametrized over 5 topic slugs + 6 entity slugs + 18 (template, pattern) tuples + 10 (locale, key) tuples + 2 icon names — total ≥41 parametrized cases
- LOC budget guard: style.css ≤ 1937 lines (UI-SPEC §8 #35)
- Negative tests: below-threshold entities (ObscureLib, OneOffMention) MUST NOT produce pages

## Acceptance signal
- `pytest tests/integration/kb/test_kb2_export.py -v` exits 0 with all parametrized cases passing
- kb-1 regression: `pytest tests/integration/kb/test_export.py -v` still exits 0
- Read-only fixture_db md5 check passes
- All 12 kb-2 REQs covered at integration level
