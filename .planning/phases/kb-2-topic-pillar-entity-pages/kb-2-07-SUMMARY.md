---
phase: kb-2-topic-pillar-entity-pages
plan: 07
type: execute
wave: 3
depends_on: ["kb-2-02-locale-keys", "kb-2-03-svg-icons", "kb-2-04-query-functions"]
files_modified:
  - kb/templates/index.html
  - kb/static/style.css
requirements: [LINK-03]
---

# kb-2-07 — Homepage Extension Plan Summary

## Objective
Extend `kb/templates/index.html` per `kb-2-UI-SPEC.md §3.3` — insert 2 new sections (Browse by Topic + Featured Entities) BETWEEN existing Latest Articles and Ask AI CTA sections. Topic cards REUSE .article-card (no new variant). Entity cloud reuses .chip primitive. Append responsive grid CSS.

## Tasks
2 tasks (template extension + CSS authoring). Surgical changes — kb-1 sections untouched.

## Skills (per kb/docs/10-DESIGN-DISCIPLINE.md)
This plan invokes both required UI Skills literally in task `<action>` blocks:

- **Skill(skill="ui-ux-pro-max", args="...")** — translate UI-SPEC §3.3 verifying 5 design constraints (no .topic-card variant — .article-card reuse, .chip primitive reuse for entity cloud, insertion order Hero→Latest→Topics→Entities→Ask, section-header pattern reuse, responsive degradation 5→3→2→1).
- **Skill(skill="frontend-design", args="...")** — implement UI-SPEC §3.3 verbatim, surgical insertion between existing kb-1 sections, .article-card--topic modifier as no-op grid hook, ZERO new variants.

These literal `Skill(skill=...)` strings are embedded in `kb-2-07-homepage-extension-PLAN.md` Task 1 + Task 2 `<action>` blocks for kb/docs/10-DESIGN-DISCIPLINE.md Check 1 regex match.

## Dependency graph
- **Depends on:** kb-2-02 (i18n keys home.section.topics_title, home.section.entities_title, home.topic.browse, home.view_all reuse), kb-2-03 (icons folder-tag for Topics + sparkle for Entities + arrow-right + articles), kb-2-04 (query functions consumed at render time by plan 09 driver)
- **Consumed by:** kb-2-09-export-driver-extension — driver provides `topics` (5 fixed) + `featured_entities` (top 12) in homepage render context

## Tech-stack notes
- ZERO new card variants per LINK-03 hard constraint — `.article-card--topic` is a no-op modifier hook for grid override
- Topic grid uses different breakpoints than kb-1 .article-list (5/3/2/1 vs 1/2/3) because there are exactly 5 topics — fits one row at full desktop
- Entity cloud is intentionally not grid-sized — `flex-wrap` with intrinsic chip widths handles variable name lengths (MCP vs LangGraph)
- Insertion order rigorously preserved: Hero → Latest → Topics → Entities → Ask → footer
- Surgical changes: kb-1 .section--latest + .section--ask-cta UNTOUCHED

## Acceptance signal
- `kb/templates/index.html` parses Jinja2
- All 5 UI-SPEC §8 accept patterns for homepage extensions (#14-18) satisfied
- Insertion order verified by line-number grep
- kb-1 sections still present (regression check)
