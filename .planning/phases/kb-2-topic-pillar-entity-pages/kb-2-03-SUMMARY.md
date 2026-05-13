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

---

## Execution Record (2026-05-13)

### One-liner

Appended `folder-tag` + `users` SVG icon clauses (verbatim from UI-SPEC §3.5) to `kb/templates/_icons.html`; macro now exposes 21 icons (19 kb-1 + 2 kb-2).

### Tasks completed

1. **Append folder-tag + users icon clauses** — single edit inserted between `sparkle` clause (line 69-71) and final `{%- endif -%}`. Existing 19 clauses untouched (surgical changes principle). Path data byte-identical to UI-SPEC §3.5 (D-12 ratified design).

### Files modified

- `kb/templates/_icons.html` (+9 lines: 2 new `{%- elif name == 'X' -%}` clauses, 6 SVG sub-elements)

### Verification

- PLAN verify command (Jinja2 render of both new icons): **PASSED** — printed `OK`
- All 19 existing icons render check: **PASSED** — `home`, `articles`, `ask`, `chevron-right`, `arrow-right`, `search`, `wechat`, `rss`, `web`, `inbox`, `globe-alt`, `fire`, `thumb-up`, `thumb-down`, `sources`, `tag`, `warning`, `clock`, `sparkle` all render without error
- Acceptance grep checks (6/6 PASSED):
  - `name == 'folder-tag'` present (line 72)
  - `name == 'users'` present (line 75)
  - `M3 7a2 2 0 0 1 2-2h4` verbatim (line 73)
  - `circle cx="9" cy="8" r="3.5"` verbatim (line 76)
  - `name == 'home'` preserved (line 17)
  - `name == 'sparkle'` preserved (line 69)

### Deviations from plan

None — plan executed exactly as written. SVG paths copied byte-identical from UI-SPEC §3.5.

### Downstream unlocks

- **TOPIC-05** (plan 06): topic page sidebar can render `{{ icon('users', size=16) }}` for "Related Entities" header
- **LINK-02** (plan 07): article.html related-topic chips can render `{{ icon('folder-tag', size=12) }}`
- **LINK-03** (plan 07): index.html "Browse by Topic" section header can render `{{ icon('folder-tag', size=20) }}`

### Self-Check: PASSED

- File exists: `kb/templates/_icons.html` ✓
- Both new clauses present and verbatim ✓
- All 19 kb-1 clauses preserved ✓
- Macro Jinja2-parseable + renders both new icons ✓
