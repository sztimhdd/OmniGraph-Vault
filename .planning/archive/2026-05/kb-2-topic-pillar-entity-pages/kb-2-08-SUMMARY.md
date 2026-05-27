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

---

## Execution Record (2026-05-13)

### One-liner
Extended `kb/templates/article.html` with `.article-detail-layout` + `.article-aside` per UI-SPEC §3.4, AND consolidated 3 deferred CSS blocks (§3.2 entity, §3.3 homepage, §3.4 article-aside = 139 LOC) into `kb/static/style.css`.

### Skills invoked (literal — passes design-discipline Check 1 regex)

- `Skill(skill="ui-ux-pro-max", args="...")` — verbatim from PLAN Task 1 `<action>` block. 7 design constraints validated: sibling-not-nested, restraint .glow-stays-in-footer, empty-section guard, sticky-desktop math, mobile fallback, semantic chip-color distinction, prefers-reduced-motion compliance.
- `Skill(skill="frontend-design", args="...")` — verbatim from PLAN Task 1 + Task 2 `<action>` blocks. Surgical wrap of `.article-body`, ZERO modifications to `.article-footer` / JSON-LD / breadcrumb / lang-badge. Verbatim CSS from UI-SPEC §3.2 + §3.3 + §3.4 appended to style.css.

### Files modified

| File | Change | LOC delta |
|---|---|---|
| `kb/templates/article.html` | Wrapped `.article-body` + new `.article-aside` in `.article-detail-layout`; conditional related_entities + related_topics chip rows | +45 / -3 |
| `kb/static/style.css` | Appended §3.2 (entity-page) + §3.3 (homepage) + §3.4 (article-aside) verbatim | +139 |

### Selectors added by section

**§3.2 entity-page (kb-2-06 deferred):**
- `.entity-header` — padding/border-bottom shell
- `.entity-header__title` — SOLID `var(--text)` (no gradient — restraint), `clamp(1.5rem, 3vw, 2.25rem)`, `word-break: break-word` for long Latin entity names
- `.entity-header__meta` — flex-wrap row for count chip + lang-distribution
- `.entity-lang-distribution` — inline-flex container for kb-1 `.lang-badge` chips

**§3.3 homepage (kb-2-07 deferred):**
- `.article-list--topics` — 5/3/2/1 col responsive grid (≥1200 → 5, 768-1199 → 3, 480-767 → 2, <480 → 1)
- `.entity-cloud` — flex-wrap chip cloud
- `.chip--entity-cloud` — composes `.chip` with baseline-aligned `chip-label · chip-count` layout
- `.chip--entity-cloud .chip-sep` / `.chip-count` — tertiary text color for separator + count
- `.chip--entity-cloud:hover .chip-count` — count brightens to secondary on hover

**§3.4 article-aside (kb-2-08 primary):**
- `.article-detail-layout` — grid wrapper (single col default, `minmax(0, 1fr) 280px` ≥1024px). **Cascade-order override note:** kb-1 declared a stub at line 1573 (`grid-template-columns: minmax(0, 1fr) 240px`); the new ≥1024px rule appended at end of style.css overrides via cascade (same specificity, later wins for `grid-template-columns`).
- `.article-aside` (≥1024px only) — `position: sticky; top: 88px; max-height: calc(100vh - 104px); overflow-y: auto`
- `.article-aside__group + .article-aside__group` — separator (border-top + padding/margin)
- `.article-aside__heading` — uppercase tertiary mini-heading with icon + label
- `.article-aside__list` — flex-wrap row mobile, flex-col desktop with full-width chips
- `.chip--topic:hover` — minor variant (border-color + color: accent-green) — only addition vs `.chip--entity` blue hover

### Token discipline (UI-SPEC §2.1 hard gate)

| Metric | Before | After | Status |
|---|---|---|---|
| `:root` var count | 33 | 33 | UNCHANGED |
| New `:root` declarations | — | 0 | PASS |
| New SVG icons (beyond kb-2-03's 21) | — | 0 | PASS |

### CSS LOC

| Metric | Value |
|---|---|
| Before | 1840 |
| After | 1979 |
| Delta | +139 |
| Budget (UI-SPEC §8 acceptance #35) | ≤ 1937 |
| **Status** | **OVER by 42 LOC — escalated, see below** |

### Escalation: CSS LOC budget exceeded by 42

The 1937 LOC ceiling assumed §3.2 + §3.3 + §3.4 would land incrementally across kb-2-06, kb-2-07, kb-2-08. Because kb-2-06 and kb-2-07's CSS were intentionally deferred (parallel-staging conflict on style.css), all three blocks were consolidated in this plan:

| Block | LOC added |
|---|---|
| §3.2 entity-page | ~30 |
| §3.3 homepage | ~46 |
| §3.4 article-aside | ~63 |
| **Total** | **~139** |

Per executor prompt directive: "If your final LOC exceeds 1937, escalate in your response with the exact LOC count + reason; do NOT trim verbatim spec." All blocks remain verbatim from UI-SPEC. Recommend updating UI-SPEC §8 acceptance #35 to `≤ 2000` (or rebaselining against post-consolidation count of 1979) when phase verification runs.

### Key links activated

- LINK-01: article.html → entity.html via `/entities/{slug}.html` chip anchors (rendered when plan 09 driver populates `related_entities`)
- LINK-02: article.html → topic.html via `/topics/{slug}.html` chip anchors (rendered when plan 09 driver populates `related_topics`)

### Surgical regression checks (kb-1 untouched)

- `.article-footer` (Ask AI .glow CTA) — UNCHANGED, sits below new `.article-detail-layout` div
- `body_html | safe` — UNCHANGED
- JSON-LD Article schema — UNCHANGED
- Breadcrumb / lang-badge / source-chip / clock — UNCHANGED
- Existing kb-2-05 topic-pillar CSS (lines 1735-1840) — UNCHANGED (verified by diff scope)

### Tests

| Suite | Result |
|---|---|
| `pytest tests/integration/kb/` | 6 passed in 3.56s — no regression |
| Jinja2 parse of `kb/templates/article.html` | OK (with stub `t`/`humanize`/`tojson` filters) |

### Acceptance criteria (UI-SPEC §8 #19-22)

| # | Pattern | Status |
|---|---|---|
| #19 | `grep -q "article-detail-layout" kb/templates/article.html` | PASS |
| #20 | `grep -q "article-aside" kb/templates/article.html` | PASS |
| #21 | `grep -q "related_entities" kb/templates/article.html` | PASS |
| #22 | `grep -q "related_topics" kb/templates/article.html` | PASS |
| #36 | `Skill(skill="ui-ux-pro-max"` literal in this SUMMARY.md | PASS (above) |
| #37 | `Skill(skill="frontend-design"` literal in this SUMMARY.md | PASS (above) |

### Commits

| Hash | Message |
|---|---|
| `a27fa70` | feat(kb-2-08): extend article.html with .article-detail-layout + .article-aside (LINK-01/02) |
| `7af7267` | feat(kb-2-08): append consolidated kb-2 CSS blocks (UI-SPEC §3.2 + §3.3 + §3.4) |

### Foundation for plan 09

Plan 09 (`kb-2-09-export-driver-extension`) will populate `related_entities` (3-5 from `related_entities_for_article()`) and `related_topics` (1-3 from `related_topics_for_article()`) in the article render context. Until then, articles render normally (the outer `{% if related_entities or related_topics %}` guard skips the entire aside when context is empty — no broken markup).

## Self-Check: PASSED

- kb/templates/article.html — FOUND (extended)
- kb/static/style.css — FOUND (1979 LOC)
- Commit a27fa70 — FOUND
- Commit 7af7267 — FOUND
- All 4 UI-SPEC §8 #19-22 acceptance patterns — PASS
- Skills literal in SUMMARY.md (ui-ux-pro-max + frontend-design) — PASS
- :root var count unchanged (33) — PASS
- pytest kb integration tests — 6/6 PASS
