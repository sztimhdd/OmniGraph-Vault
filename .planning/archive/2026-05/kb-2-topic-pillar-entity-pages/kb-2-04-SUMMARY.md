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

---

# Execution Results — appended 2026-05-13

## Status
COMPLETE — all acceptance criteria green.

## Commits
- `0b73d76` feat(kb-2-04): add slugify_entity_name + topic_articles_query (Task 1)
- `6ee6cd2` feat(kb-2-04): add 4 entity/link/cooccurring queries (Task 2)

## Skill invocations (per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1)

Both Skills invoked verbatim from PLAN action blocks (PLAN lines 227, 229, 451, 453):

- `Skill(skill="python-patterns", args="...")` (Task 1 + Task 2 actions). Outputs applied: type hints on every signature; `@dataclass(frozen=True)` for immutable returns; `try/finally` close-pattern with `own_conn = conn is None`; parameterized SQL throughout (no string concat); EAFP error handling; `is None` not `== None`; comprehensions for simple list builds; explicit `for row in conn.execute(...)` loops where row mappers branch.
- `Skill(skill="writing-tests", args="...")` (Task 1 + Task 2 actions). Outputs applied: Testing Trophy — integration > E2E > unit; real SQLite via shared `fixture_db` from `tests/integration/kb/conftest.py` (no mocks); `_SpyConn` proxy class for read-only enforcement (sqlite3.Connection.execute is read-only on Py 3.13, can't monkeypatch directly); behavior assertions on returned `ArticleRecord` IDs/sources, not on private state.

## Files created / modified

| File | Change | LOC |
|---|---|---|
| `kb/data/article_query.py` | APPENDED 5 query functions + 1 helper + 2 dataclasses + 1 topic-slug map | +301 |
| `tests/unit/kb/test_kb2_queries.py` | NEW — 19 TDD tests + `_SpyConn` proxy | +231 |

kb-1 module preserved verbatim — all 5 kb-1 functions + ArticleRecord still exported.

## New exports (kb/data/article_query.py)

| Export | Type | Purpose | REQ |
|---|---|---|---|
| `EntityCount` | `@dataclass(frozen=True)` | name + slug + article_count | ENTITY-02 |
| `TopicSummary` | `@dataclass(frozen=True)` | slug + raw_topic | TOPIC-03 |
| `slugify_entity_name(name)` | function | lowercase + URL-safe slug, Unicode preserved | ENTITY-02 |
| `topic_articles_query(topic, depth_min, conn)` | function → `list[ArticleRecord]` | TOPIC-02 cohort filter UNION KOL+RSS | TOPIC-02 |
| `entity_articles_query(name, min_freq, conn)` | function → `list[ArticleRecord]` | articles mentioning entity (returns [] below threshold) | ENTITY-01, ENTITY-03 |
| `related_entities_for_article(id, source, limit, min_global_freq, conn)` | function → `list[EntityCount]` | top-N entities ranked by global freq DESC | LINK-01 |
| `related_topics_for_article(id, source, depth_min, limit, conn)` | function → `list[TopicSummary]` | 1-3 topics ranked by depth_score DESC | LINK-02 |
| `cooccurring_entities_in_topic(topic, limit, min_global_freq, depth_min, conn)` | function → `list[EntityCount]` | CTE-based cohort gate + entity rank within topic | TOPIC-05 |

## Test results

- `pytest tests/unit/kb/test_kb2_queries.py -v` → **19 passed in 0.36s**
- `pytest tests/unit/kb/test_article_query.py -v` → **26 passed in 0.16s** (kb-1 regression intact)
- Combined: **45 passed in 0.82s**

Test breakdown (19 total, exceeds plan target of ≥18):
- 5 slugify_entity_name (ASCII / space / slash / CJK / whitespace strip)
- 4 topic_articles_query (UNION + sorted DESC + depth filter + read-only)
- 1 dataclass shapes smoke
- 3 entity_articles_query (above / below / lowered threshold)
- 2 related_entities_for_article (sorted with global counts + limit honored)
- 2 related_topics_for_article (3 sorted by depth + depth_min filter)
- 1 cooccurring_entities_in_topic (rank within Agent cohort)
- 1 read-only SQL spy across the 4 Task-2 queries

## Verification

| Check | Status |
|---|---|
| `grep -q "def slugify_entity_name" kb/data/article_query.py` | PASS |
| `grep -q "def topic_articles_query" kb/data/article_query.py` | PASS |
| `grep -q "def entity_articles_query" kb/data/article_query.py` | PASS |
| `grep -q "def related_entities_for_article" kb/data/article_query.py` | PASS |
| `grep -q "def related_topics_for_article" kb/data/article_query.py` | PASS |
| `grep -q "def cooccurring_entities_in_topic" kb/data/article_query.py` | PASS |
| `grep -q "class EntityCount" kb/data/article_query.py` | PASS |
| `grep -q "class TopicSummary" kb/data/article_query.py` | PASS |
| `grep -q "WITH topic_articles AS" kb/data/article_query.py` (CTE) | PASS |
| `grep -q 'Skill(skill="python-patterns"' .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-04-query-functions-PLAN.md` | PASS |
| `grep -q 'Skill(skill="writing-tests"' .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-04-query-functions-PLAN.md` | PASS |
| `grep -E "execute\(.*(INSERT|UPDATE|DELETE)" kb/data/article_query.py` returns 0 | PASS (read-only) |
| Module imports cleanly (`python -c "from kb.data.article_query import ..."`) | PASS |
| 19 kb-2 tests pass | PASS |
| 26 kb-1 regression tests pass | PASS |

## Deviations from plan

### Auto-fixed issues

**1. [Rule 3 — Blocking issue] `monkeypatch.setattr(c, "execute", ...)` raises on Python 3.13.**
- **Found during:** Task 1 first test run (post-implementation)
- **Issue:** `sqlite3.Connection.execute` is a read-only built-in attribute on Python 3.13; pytest's `monkeypatch.setattr(conn, "execute", spy)` raises `AttributeError: 'sqlite3.Connection' object attribute 'execute' is read-only`. The plan's example code in Task 1 + Task 2 used direct monkeypatch, which would never have worked.
- **Fix:** Introduced `_SpyConn` proxy class (mirrors the existing kb-1 SpyConn pattern at `tests/unit/kb/test_article_query.py:280-299`) — wraps the real connection, captures every SQL string passed to `.execute()`, delegates other attributes via `__getattr__`. Applied to both `test_topic_articles_read_only` and `test_kb2_queries_read_only`.
- **Files modified:** `tests/unit/kb/test_kb2_queries.py` (new test file, never published with the broken monkeypatch form).
- **Commits:** `0b73d76` (Task 1, includes `_SpyConn`).

**2. [Plan structure] Task 2 commit uses 19 tests instead of "≥18".**
- The plan target was ≥18; final count is 19 because Task 1 added a `test_dataclass_shapes_importable` smoke test that was not in the plan's behavior list — it provides an early-warning if the EntityCount/TopicSummary frozen dataclass shape changes (the Task 2 functions return these). Net: more coverage, no regressions.

### Architectural changes

None — additive only; no kb-1 code modified.

## CLAUDE.md adherence

- **Simplicity First** — every changed line traces to plan acceptance criteria; no speculative abstractions; functions are 15-50 LOC each (the CTE in `cooccurring_entities_in_topic` is the only function that needed a multi-line SQL string, justified by the cohort gate requirement).
- **Surgical Changes** — kb-1 functions unmodified; only ADDED to bottom of `kb/data/article_query.py`. Test file is new (not extending kb-1's test file). No "improvements" to kb-1 code.
- **Goal-Driven Execution** — all 19 tests written before final commit; verified GREEN; read-only enforcement enforced via SQL spy.

## Foundation for downstream plans

These 5 query functions + 2 dataclasses + slugify helper are imported by:
- `kb-2-09-export-driver-extension` (driver loop iterates topics + entities, calls these functions)
- `kb-2-05-topic-template` (topic.html consumes `topic_articles_query` + `cooccurring_entities_in_topic`)
- `kb-2-06-entity-template` (entity.html consumes `entity_articles_query`)
- `kb-2-07-homepage-extension` (index.html consumes featured-entities subset)
- `kb-2-08-article-aside` (article.html consumes `related_entities_for_article` + `related_topics_for_article`)

## Self-Check: PASSED

- Created files exist: `tests/unit/kb/test_kb2_queries.py` ✓
- Modified files exist: `kb/data/article_query.py` ✓
- Commits exist in git log: `0b73d76` ✓, `6ee6cd2` ✓
- 19 kb-2 tests pass ✓ (target ≥18)
- 26 kb-1 regression tests pass ✓ (target ≥23)
- Read-only grep clean ✓
- Both Skill invocation strings present in PLAN ✓
- All 6 REQ IDs covered (TOPIC-02, TOPIC-03, TOPIC-05, ENTITY-02, LINK-01, LINK-02) ✓
