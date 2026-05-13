---
phase: kb-2-topic-pillar-entity-pages
plan: 02
type: execute
wave: 1
depends_on: []
files_modified: [kb/locale/zh-CN.json, kb/locale/en.json]
requirements: [TOPIC-03, ENTITY-03, LINK-03]
---

# kb-2-02 — Locale Keys Plan Summary

## Objective
Ship 26 new bilingual i18n keys per UI-SPEC §5 verbatim table. Pure additive change.

## Tasks
1 task — JSON merge.

## Dependency graph
- **Depends on:** none (Wave 1, parallel with plans 01 + 03)
- **Consumed by:** plans 06 (topic.html + entity.html), 07 (index.html + article.html extensions)

## Tech-stack notes
- No code, no test, no Skill invocation. Localization data only.
- Keys are dot-strings (kb-1 i18n convention) — flat object structure preserved.
- Existing `validate_key_parity()` from kb-1's `kb/i18n.py` enforces zh ↔ en parity at SSG build time (already wired into export driver Task 2 of kb-1-09).

## Skills (per kb/docs/10-DESIGN-DISCIPLINE.md)
None — text values originate from kb-2-UI-SPEC.md §5 which was authored by ui-ux-pro-max + frontend-design Skills at UI-SPEC time. Mechanically copying values verbatim does NOT need a fresh invocation.

## Acceptance signal
`validate_key_parity()` exits 0 + all 26 keys present in both locales with verbatim values.
