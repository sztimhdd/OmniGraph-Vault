---
phase: kb-2-topic-pillar-entity-pages
plan: 05
type: execute
wave: 3
depends_on: ["kb-2-02-locale-keys", "kb-2-03-svg-icons", "kb-2-04-query-functions"]
files_modified:
  - kb/templates/topic.html
  - kb/static/style.css
requirements: [TOPIC-01, TOPIC-04, TOPIC-05]
---

# kb-2-05 — Topic Pillar Template Plan Summary

## Objective
Build `kb/templates/topic.html` (NEW) per `kb-2-UI-SPEC.md §3.1` verbatim — gradient h1 + article list (.article-card reuse) + cooccurring entities sidebar (.chip--entity composition) + CollectionPage JSON-LD. Append topic-pillar CSS to kb/static/style.css with ZERO new :root tokens.

## Tasks
2 tasks (template authoring + CSS authoring). Pure additive — base.html, articles_index.html, kb-1 templates untouched.

## Skills (per kb/docs/10-DESIGN-DISCIPLINE.md)
This plan invokes both required UI Skills literally in task `<action>` blocks:

- **Skill(skill="ui-ux-pro-max", args="...")** — translate UI-SPEC §3.1 into template structure verifying 6 design constraints (gradient on h1 only, no card variants, chip-toggle filter not native select, entity sidebar composes .chip--entity, responsive grid, empty-state reuse).
- **Skill(skill="frontend-design", args="...")** — implement UI-SPEC §3.1 verbatim into Jinja2 template + CSS. Reuse kb-1 redesigned tokens exclusively. .article-card markup copied verbatim from articles_index.html — NO re-design.

These literal `Skill(skill=...)` strings are embedded in `kb-2-05-topic-template-PLAN.md` Task 1 + Task 2 `<action>` blocks for regex match per kb/docs/10-DESIGN-DISCIPLINE.md Check 1.

## Dependency graph
- **Depends on:** kb-2-02 (i18n keys topic.{slug}.name/desc, breadcrumb.topics, topic.cooccurring_entities_title, topic.empty_title/hint), kb-2-03 (icons users + tag + chevron-right + home + articles + wechat + rss + inbox), kb-2-04 (query functions consumed at render time by export driver)
- **Consumed by:** kb-2-09-export-driver-extension (Wave 4) — driver loops over 5 topics, populates render context, calls `template.render()` against this template

## Tech-stack notes
- Token discipline ZERO-new — all CSS composes kb-1 :root vars only (UI-SPEC §2.1 hard gate)
- Article-card markup copied verbatim from kb-1 articles_index.html — no new card variant
- Sub-source filter chips use aria-pressed + role="group" (UI-SPEC §7 a11y)
- JSON-LD CollectionPage emitted via `{% block extra_head %}` per UI-SPEC §6
- Responsive: 3 breakpoints (1024+ / 768-1023 / <768) per UI-SPEC §3.1 layout table

## Acceptance signal
- `kb/templates/topic.html` parses Jinja2 (verify command exits 0)
- All 8 UI-SPEC §8 accept patterns for topic page satisfied (#3-7, #8 CollectionPage, #30 output later in plan 10)
- CSS LOC under 1937-line budget (UI-SPEC accept #35)
