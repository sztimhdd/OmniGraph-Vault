---
phase: kb-2-topic-pillar-entity-pages
plan: 06
type: execute
wave: 3
depends_on: ["kb-2-02-locale-keys", "kb-2-03-svg-icons", "kb-2-04-query-functions"]
files_modified:
  - kb/templates/entity.html
  - kb/static/style.css
requirements: [ENTITY-01, ENTITY-04]
---

# kb-2-06 — Entity Page Template Plan Summary

## Objective
Build `kb/templates/entity.html` (NEW) per `kb-2-UI-SPEC.md §3.2` verbatim — solid-color h1 (restraint, no gradient) + lang-distribution chip row signature moment + article list (.article-card reuse) + Thing JSON-LD. Append entity-page CSS to kb/static/style.css with ZERO new :root tokens.

## Tasks
2 tasks (template authoring + CSS authoring). Pure additive.

## Skills (per kb/docs/10-DESIGN-DISCIPLINE.md)
This plan invokes both required UI Skills literally in task `<action>` blocks:

- **Skill(skill="ui-ux-pro-max", args="...")** — translate UI-SPEC §3.2 verifying 7 design constraints (solid h1, lang-distribution as signature, lang-badge reuse, article-card reuse, zero-count chip skip, generic Thing only, word-break long names).
- **Skill(skill="frontend-design", args="...")** — implement UI-SPEC §3.2 verbatim, reuse kb-1 lang-badge color-coding via `data-lang` attribute selector, generic Thing JSON-LD with empty alternateName.

These literal `Skill(skill=...)` strings are embedded in `kb-2-06-entity-template-PLAN.md` Task 1 and Task 2 `<action>` blocks for kb/docs/10-DESIGN-DISCIPLINE.md Check 1 regex match.

## Dependency graph
- **Depends on:** kb-2-02 (i18n keys breadcrumb.entities, entity.article_count_label, entity.lang_distribution_aria, entity.empty_title/hint), kb-2-03 (icons), kb-2-04 (query functions for render-time)
- **Consumed by:** kb-2-09-export-driver-extension (Wave 4) — driver loops over qualifying entities (≥5 frequency on Hermes prod = ~91), populates render context, calls `template.render()`

## Tech-stack notes
- ZERO new :root tokens (UI-SPEC §2.1 hard gate)
- Restraint principle: entity h1 is SOLID color — gradient reserved for topic page (which is genuinely a focal landing surface)
- Lang-distribution chip row composes existing `.lang-badge` (kb-1) — no new chip variant
- JSON-LD generic Thing only (no Person/Organization/SoftwareApplication) per ENTITY-04 — `entity_canonical.entity_type` is NULL across corpus; v2.1 CANON-* / TYPED-* will populate
- alternateName always `[]` for v2.0 — populated in v2.1
- word-break: break-word on h1 — prevents long Latin names (LangChain, AutoGen, AnthropicClaude) from overflowing on narrow viewports

## Acceptance signal
- `kb/templates/entity.html` parses Jinja2
- All 5 UI-SPEC §8 accept patterns for entity page satisfied (#9-13)
- CSS LOC under 1937-line budget
