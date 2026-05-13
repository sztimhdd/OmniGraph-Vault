---
phase: kb-2-topic-pillar-entity-pages
plan: 09
type: execute
wave: 4
depends_on: ["kb-2-04-query-functions", "kb-2-05-topic-template", "kb-2-06-entity-template", "kb-2-07-homepage-extension", "kb-2-08-article-aside"]
files_modified:
  - kb/export_knowledge_base.py
requirements: [TOPIC-01, TOPIC-03, ENTITY-01, ENTITY-03, LINK-01, LINK-02, LINK-03]
---

# kb-2-09 — Export Driver Extension Plan Summary

## Objective
Extend kb-1's `kb/export_knowledge_base.py` SSG driver to render kb-2 pages: 5 topic pillars + N entity pages (≥50 on Hermes prod) + extended homepage context (topics + featured_entities) + extended article detail context (related_entities + related_topics).

## Tasks
2 tasks (helpers + main-loop wiring). Surgical extension of kb-1 driver — no kb-1 functions modified.

## Skills (per kb/docs/10-DESIGN-DISCIPLINE.md)
This plan invokes the required Python Skill literally in task `<action>` blocks:

- **Skill(skill="python-patterns", args="...")** — extend driver with two render loops + entity discovery helper using single SQL aggregation (no Python-side bucketing). Idempotent ordering (sort by name ASC) for deterministic output. Read-only preserved.

This literal `Skill(skill=...)` string is embedded in `kb-2-09-export-driver-extension-PLAN.md` Task 1 and Task 2 `<action>` blocks for kb/docs/10-DESIGN-DISCIPLINE.md Check 1 regex match.

## Dependency graph
- **Depends on:** kb-2-04 (query functions), kb-2-05 (topic.html), kb-2-06 (entity.html), kb-2-07 (index.html extended), kb-2-08 (article.html extended)
- **Consumed by:** kb-2-10-integration-test (Wave 5) — runs full driver against fixture, asserts UI-SPEC §8 acceptance grep results

## Tech-stack notes
- 3 new helper functions: `_discover_qualifying_entities` (single aggregation SQL), `_render_topic_pages` (loop over KB2_TOPICS), `_render_entity_pages` (loop over qualifying entities, idempotent name-sort)
- Module constants: `KB2_TOPICS`, `TOPIC_SLUG_MAP`, `KB_ENTITY_MIN_FREQ` (env-overridable, default 5)
- Sitemap auto-extends: kb-1's `Path.rglob("*")` discovers new topics/ + entities/ paths on its own — no _write_sitemap modification needed
- Read-only preserved: driver imports only read-only query functions; no INSERT/UPDATE/DELETE
- Idempotency preserved: entity loop sorted by name ASC; per-lang output deterministic

## Acceptance signal
- 3 new functions present (AST verification)
- main() wiring detected (qualifying_entities + topic + entity loops)
- Homepage context has topics + featured_entities
- Article context has related_entities + related_topics
- Read-only grep returns 0 INSERT/UPDATE/DELETE
- kb-1 baseline preserved (existing renders still execute correctly)
