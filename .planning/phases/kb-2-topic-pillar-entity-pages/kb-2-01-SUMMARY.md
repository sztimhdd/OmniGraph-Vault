---
phase: kb-2-topic-pillar-entity-pages
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/integration/kb/conftest.py
  - tests/integration/kb/test_export.py
requirements: [TOPIC-02, ENTITY-01, ENTITY-03, LINK-01, LINK-02]
---

# kb-2-01 — Fixture Extension Plan Summary

## Objective
Build shared `fixture_db` (Hermes-prod-shape SQLite) consumed by every kb-2 query / integration test.

## Tasks
1 task — purely additive test infra. No production code modified.

## Dependency graph
- **Depends on:** none (Wave 1 root, parallel with plans 02 + 03)
- **Consumed by:** plans 04 (query function unit tests), 09 (integration test)

## Tech-stack notes
- Pure pytest fixture extension. No new deps.
- Mirrors Hermes prod schema verified via SSH 2026-05-13: classifications has 3945 rows / 5 topics; extracted_entities has 5257 rows / 91 entities at ≥5-article freq.
- Fixture downscale: 8 articles + 22 entity rows (6 above + 2 below threshold). Exercises every code path without prod-volume bloat.

## Skills (per kb/docs/10-DESIGN-DISCIPLINE.md)
None — pure test data, no UI surface, no business logic. The `python-patterns` rule applies (PEP 8 + type hints + dataclass-like constants), but the rule is loaded automatically — no `Skill()` invocation required for non-UI test infra.

## Acceptance signal
`pytest tests/integration/kb/test_export.py -v` returns 6/6 PASS after fixture refactor (kb-1 baseline preserved via assertion-number bumps only — no test logic change).
