---
phase: kb-2-topic-pillar-entity-pages
plan: 04
type: execute
wave: 2
depends_on: ["kb-2-01-fixture-extension"]
files_modified:
  - kb/data/article_query.py
  - tests/unit/kb/test_kb2_queries.py
requirements: [TOPIC-02, TOPIC-03, TOPIC-05, ENTITY-02, LINK-01, LINK-02]
---

# kb-2-04 — Query Functions Plan Summary

## Objective
Add 5 read-only query functions to `kb/data/article_query.py` (`topic_articles_query`, `entity_articles_query`, `related_entities_for_article`, `related_topics_for_article`, `cooccurring_entities_in_topic`) + `slugify_entity_name` helper + `EntityCount` / `TopicSummary` dataclasses.

## Tasks
2 tasks (TDD-driven). Mirror existing kb-1 module conventions: frozen dataclass returns, parameterized SQL, optional `conn=` injection, read-only enforcement.

## Skills (per kb/docs/10-DESIGN-DISCIPLINE.md)
This plan invokes both required Skills literally in task `<action>` blocks:

- **Skill(skill="python-patterns", args="...")** — idiomatic read-only sqlite3 query, frozen dataclass returns, parameterized SQL, type hints. Mirrors kb-1's `article_query.py` patterns: `_connect()` helper for ro URI, `sqlite3.Row` factory, `own_conn = conn is None` close-finally pattern. CTE-based cohort gate for `cooccurring_entities_in_topic`.
- **Skill(skill="writing-tests", args="...")** — TDD against shared `fixture_db` (no mocks, real SQLite per Testing Trophy). 18+ tests covering: 5 slugify cases, 4 topic_articles cases (UNION + sorted DESC + depth filter + read-only), 3 entity_articles cases (above/below/lowered threshold), 2 related_entities cases (sorted with global counts + limit), 2 related_topics cases (depth ordering + filter), 1 cooccurring case, 1 SQL-spy read-only test.

These literal `Skill(skill=...)` strings are embedded in `kb-2-04-query-functions-PLAN.md` Task 1 and Task 2 `<action>` blocks (regex-verifiable per kb/docs/10-DESIGN-DISCIPLINE.md Check 1).

## Dependency graph
- **Depends on:** kb-2-01-fixture-extension (Wave 1) — provides shared `fixture_db` with classifications + extracted_entities + layer verdicts
- **Consumed by:** kb-2-09-export-driver-extension (Wave 4) — driver imports all 5 new functions to drive topic + entity render loops + article-aside related-link injection

## Tech-stack notes
- 5 new functions appended to existing 5 kb-1 functions (10 total exports)
- 2 new frozen dataclasses (`EntityCount`, `TopicSummary`) + 1 helper (`slugify_entity_name`)
- Cohort gate (depth_score >= 2 AND layer verdict ok) implemented as SQL CTE in `cooccurring_entities_in_topic`
- All queries parameterized — no string concat, no SQL injection surface
- Read-only enforcement: `grep` regression test + SQL-spy test in TDD suite
- `_SLUG_TOPIC_MAP` keeps the 5 known topic slugs explicit (avoids fragile `.lower()` on every emission)

## Acceptance signal
- `pytest tests/unit/kb/test_kb2_queries.py -v` returns 18+ passing tests
- kb-1 baseline preserved: `pytest tests/unit/kb/test_article_query.py -v` ≥23 passing
- Read-only grep returns 0 INSERT/UPDATE/DELETE in kb/data/article_query.py
