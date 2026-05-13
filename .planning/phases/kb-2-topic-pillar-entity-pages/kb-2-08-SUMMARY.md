---
phase: kb-2-topic-pillar-entity-pages
plan: 08
type: execute
wave: 3
depends_on: ["kb-2-02-locale-keys", "kb-2-03-svg-icons", "kb-2-04-query-functions"]
files_modified:
  - kb/templates/article.html
  - kb/static/style.css
requirements: [LINK-01, LINK-02]
---

# kb-2-08 — Article Aside (Related Entities + Related Topics) Plan Summary

## Objective
Extend `kb/templates/article.html` per `kb-2-UI-SPEC.md §3.4` — wrap existing `.article-body` in `.article-detail-layout` grid + add `.article-aside` sibling with conditional related_entities (3-5 chips) + related_topics (1-3 chips) sections. Sticky on desktop ≥1024px, stacked on mobile. Append article-aside CSS.

## Tasks
2 tasks (template extension + CSS authoring). Surgical changes — kb-1 .article-footer Ask AI CTA untouched.

## Skills (per kb/docs/10-DESIGN-DISCIPLINE.md)
This plan invokes both required UI Skills literally in task `<action>` blocks:

- **Skill(skill="ui-ux-pro-max", args="...")** — translate UI-SPEC §3.4 verifying 7 design constraints (sibling not nested, restraint .glow stays footer, empty-section guard, sticky desktop ≥1024px, stacked mobile, .chip--topic green hue semantic, prefers-reduced-motion compliance).
- **Skill(skill="frontend-design", args="...")** — implement UI-SPEC §3.4 verbatim, surgical wrap of existing `.article-body`, ZERO modifications to JSON-LD/breadcrumb/footer, .chip--topic minor variant only adds hover hue.

These literal `Skill(skill=...)` strings are embedded in `kb-2-08-article-aside-PLAN.md` Task 1 + Task 2 `<action>` blocks for kb/docs/10-DESIGN-DISCIPLINE.md Check 1 regex match.

## Dependency graph
- **Depends on:** kb-2-02 (i18n keys article.related_aria, article.related_entities, article.related_topics), kb-2-03 (icons folder-tag + tag), kb-2-04 (related_entities_for_article + related_topics_for_article query functions consumed at render time by plan 09)
- **Consumed by:** kb-2-09-export-driver-extension — driver populates `related_entities` + `related_topics` in article render context

## Tech-stack notes
- Position rule honored: aside is SIBLING to .article-body inside .article-detail-layout (NOT nested in body, NOT in footer)
- Sticky on desktop ≥1024px (top: 88px = kb-1 64px nav + 24px breathing); max-height: calc(100vh - 104px) with overflow-y: auto
- Mobile <1024px: stacked single column; aside-list switches to flex-wrap row
- Empty-section guard: `{% if related_entities %}` / `{% if related_topics %}` — no orphan headings
- Outer guard: `{% if related_entities or related_topics %}` — entire aside skipped if both empty
- .chip--topic is a NEW minor variant: ONLY hover hue (accent-green border + text) — semantic distinction from .chip--entity blue
- Topic chip uses `folder-tag` icon (12px in chip, 14px in heading); entity chip uses `tag` icon

## Acceptance signal
- `kb/templates/article.html` parses Jinja2
- All 4 UI-SPEC §8 accept patterns for article extensions (#19-22) satisfied
- kb-1 .article-footer Ask AI CTA still present (regression)
- CSS LOC under 1937-line budget
