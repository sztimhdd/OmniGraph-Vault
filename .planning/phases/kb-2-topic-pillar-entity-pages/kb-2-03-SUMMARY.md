---
phase: kb-2-topic-pillar-entity-pages
plan: 03
type: execute
wave: 1
depends_on: []
files_modified: [kb/templates/_icons.html]
requirements: [TOPIC-05, LINK-02, LINK-03]
---

# kb-2-03 — SVG Icons Plan Summary

## Objective
Append `folder-tag` + `users` SVG icon clauses to existing kb/templates/_icons.html macro. Verbatim paths from UI-SPEC §3.5.

## Tasks
1 task — Jinja2 macro extension.

## Dependency graph
- **Depends on:** none (Wave 1, parallel with plans 01 + 02)
- **Consumed by:** plans 06 (topic.html `users` for sidebar; entity.html may use), 07 (article.html `folder-tag` for related-topics; index.html `folder-tag` for Browse by Topic)

## Tech-stack notes
- No new files. No CSS. Pure inline-SVG as per kb-1 convention (no icon font, no CDN).
- 24×24 viewBox + 1.5px stroke + currentColor — exact same SVG contract as 19 existing icons.

## Skills (per kb/docs/10-DESIGN-DISCIPLINE.md)
None — SVG paths originate from kb-2-UI-SPEC.md §3.5 which was authored with `Skill(skill="ui-ux-pro-max", ...)` + `Skill(skill="frontend-design", ...)` discipline at UI-SPEC time. Mechanical verbatim copy of locked SVG paths does NOT need a fresh invocation.

## Acceptance signal
Jinja2 macro renders both new icon names without error; verify command in PLAN exits 0.
