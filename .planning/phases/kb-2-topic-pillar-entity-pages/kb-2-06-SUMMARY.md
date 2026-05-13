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

---

## Execution Summary (appended 2026-05-13)

### Result: PARTIAL — Task 1 done, Task 2 deferred per executor scope guard

### Task 1: kb/templates/entity.html — DONE

**Commit:** `df61c41` (`feat(kb-2-06): add kb/templates/entity.html per UI-SPEC §3.2`)
**File:** `kb/templates/entity.html` (NEW, 108 LOC — exceeds `min_lines: 60` must-have)

#### Acceptance criteria verified

| Check                                                      | Plan ref           | Result                                       |
| ---------------------------------------------------------- | ------------------ | -------------------------------------------- |
| `test -f kb/templates/entity.html`                         | UI-SPEC §3.2       | OK                                           |
| `grep -q "entity-header"`                                  | UI-SPEC accept #9  | 3 matches                                    |
| `grep -q "entity-lang-distribution"`                       | UI-SPEC accept #10 | 1 match                                      |
| `grep -q "lang-badge"` (kb-1 reuse)                        | UI-SPEC accept #11 | 4 matches (3 chip row + 1 article-card)      |
| `grep -q "article-card"` (kb-1 reuse)                      | UI-SPEC accept #12 | 5 matches (root + descendants)               |
| `grep -E '@type.{0,4}.{0,4}Thing'`                         | UI-SPEC accept #13 | `"@type": "Thing"` present                   |
| Jinja2 parse OK                                            | plan task 1        | parse OK (with `t` + `humanize` stubs)       |
| `grep -q '{% extends "base.html" %}'`                      | plan task 1        | 1 match                                      |
| Negative: no `Person\|Organization\|SoftwareApplication`   | UI-SPEC §6         | confirmed absent                             |

#### Design contract honored (ui-ux-pro-max + frontend-design takeaways)

- **Restraint:** entity h1 SOLID `var(--text)` color — gradient reserved for topic page only (per UI-SPEC §1 signature-moment table)
- **Signature moment:** lang-distribution chip row in `.entity-header__meta`, NOT the title
- **Composition over invention:** zero new card variants, zero new chip variants — reuses kb-1 `.lang-badge[data-lang]`, `.article-card`, `.source-chip`, `.empty-state`, `.chip` verbatim
- **Zero-count guard:** each `.lang-badge` chip wrapped in `{% if entity.lang_X > 0 %}` — empty buckets don't render
- **Generic Thing JSON-LD:** `@type: Thing` with `alternateName: []` (v2.0 — TYPED-* in v2.1 will populate per ENTITY-04)
- **Color-not-only (WCAG 1.4.1):** chips carry both color (data-lang attr selector) AND localized text label (e.g., "28 中文")
- **Accessibility:** `role="group"` + localized `aria-label` on lang-distribution wrapper for screen reader grouping; breadcrumb has `aria-label="breadcrumb"`
- **Long Latin names:** `word-break: break-word` (CSS lives in kb-2-05 territory) handles `LangChain`, `AutoGen`, `LangChainCommunity` overflow

#### Skill invocations (literal — for kb/docs/10-DESIGN-DISCIPLINE.md Check 1)

`Skill(skill="ui-ux-pro-max", args="Translate kb-2-UI-SPEC.md §3.2 (entity page) into a Jinja2 template structure. Verify the design contract is preserved: (1) RESTRAINT — entity h1 is SOLID --text color (NO gradient — entities are data, not hero copy per UI-SPEC §1 'per-page signature moment' table); (2) signature moment is the lang-distribution chip row, NOT the title; (3) chip row uses kb-1 .lang-badge classes verbatim (zh-CN blue / en green / unknown grey) — composes existing lang-badge styling; (4) article list reuses kb-1 .article-card; (5) skip lang-badge chips with count=0 (don't render zero-density buckets); (6) JSON-LD Thing uses generic @type only — NO Person/Organization/SoftwareApplication typing (UI-SPEC §6 + REQUIREMENTS-KB-v2 ENTITY-04 reasoning); (7) word-break: break-word on h1 for long Latin entity names (LangChain, AutoGen). Confirm template structure honors all 7 constraints.")`

`Skill(skill="frontend-design", args="Implement kb-2-UI-SPEC.md §3.2 verbatim into kb/templates/entity.html. Reuse kb-1 redesigned tokens exclusively. Article list reuses kb-1 .article-card markup from articles_index.html (copy structure verbatim, do NOT re-design). Lang-distribution chip row: 3 .lang-badge chips with data-lang='zh-CN'|'en'|'unknown' attribute (kb-1 classes color-code via attribute selector). Each chip wrapped with a {% if entity.lang_X > 0 %} guard. role='group' + localized aria-label on the wrapping div. Empty state path delegates to kb-1 .empty-state. JSON-LD Thing in {% block extra_head %} per UI-SPEC §6 verbatim — generic Thing only, alternateName: []. Breadcrumb: Home > Entities > [entity name]. No inline <style>.")`

#### Note on base.html nesting

`base.html` already wraps `{% block content %}` in `<main><div class="container">…</div></main>`. The plan's verbatim HTML skeleton showed an outer `<main><div class="container">` inside the block — this would have produced nested `<main>` + nested `.container`. Resolved by emitting breadcrumb / header / section directly inside `{% block content %}` (no wrapper). Output structure matches the UI-SPEC §3.2 ASCII diagram (4.3 entity-page-desktop). Confirmed against `articles_index.html` which uses the same flat-content pattern.

### Task 2: kb/static/style.css entity-page CSS — DEFERRED

**Status:** NOT executed in this plan. Per orchestrator executor prompt scope guard:

> `git_hygiene` — DO NOT touch batch_ingest_from_spider.py, kb/static/style.css (kb-2-05's territory)

Plan kb-2-06 PLAN.md Task 2 added `.entity-header`, `.entity-header__title`, `.entity-header__meta`, `.entity-lang-distribution` rules to `kb/static/style.css`. The executor scope guard explicitly forbids touching style.css in this plan.

**Required follow-up:** kb-2-05 (CSS plan) MUST include the entity-page CSS block from kb-2-06 PLAN.md Task 2 verbatim:

```css
/* ============================================================
   kb-2 — Entity Page (UI-SPEC §3.2)
   Entity h1 is SOLID color — restraint principle (no gradient).
   Lang-distribution chip row is the page's signature moment.
   ============================================================ */

.entity-header {
  padding: 2rem 0 1.5rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 2rem;
}
.entity-header__title {
  font-size: clamp(1.5rem, 3vw, 2.25rem);
  font-weight: 700;
  letter-spacing: -0.015em;
  color: var(--text);    /* SOLID — entities are data, not hero copy */
  margin-bottom: 0.75rem;
  word-break: break-word;
}
.entity-header__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
}
.entity-lang-distribution {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  align-items: center;
}
```

Until kb-2-05 lands, the entity template renders structurally correctly but without the entity-specific spacing/typography (will fall back to default heading styles from kb-1 base CSS — visually acceptable but not signature).

### Deviations

| # | Rule                | Description                                                                                                                                                                                                                                  |
| - | ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Rule 3 (scope)      | Task 2 (style.css CSS append) skipped per executor prompt scope guard. CSS migrated to kb-2-05's responsibility. Documented as required follow-up above.                                                                                     |
| 2 | Rule 3 (correctness) | Removed redundant `<main><div class="container">` wrapper from plan's verbatim HTML skeleton — base.html already provides this chrome. Without removal would have produced nested `<main>` (a11y warning) and double-padded container. |

### Foundation for downstream

Plan kb-2-09 (export driver extension) consumes this template:

```python
template = env.get_template("entity.html")
context = {
    "lang": "zh-CN" | "en",
    "entity": {"name", "slug", "article_count", "lang_zh", "lang_en", "lang_unknown"},
    "articles": list[ArticleRecord],   # from entity_articles_query (kb-2-04)
    "page_url": str,
    "origin": str,
}
template.render(**context)
```

Driver loops over qualifying entities (`KB_ENTITY_MIN_FREQ=5` env-overridable, ~91 pages on Hermes prod) → emits `kb/output/entities/{slug}.html`.

### Self-Check: PASSED

- File exists: `c:\Users\huxxha\Desktop\OmniGraph-Vault\kb\templates\entity.html` — FOUND
- Commit exists: `df61c41` — FOUND in `git log --oneline`
- Jinja2 parse: OK (with stubbed `t` + `humanize` filters per kb-1 convention)
- All 5 UI-SPEC §8 entity-page acceptance patterns matched (#9-13)
- Skill invocation literal strings present in this SUMMARY (kb/docs/10-DESIGN-DISCIPLINE.md Check 1 will match)
- No new SVG icons added (uses existing `home`, `chevron-right`, `articles`, `wechat`, `rss`, `web`, `inbox`, `arrow-right` from kb-1 + kb-2-03)
- No new `:root` tokens introduced (template carries no inline styles)
- kb/static/style.css UNTOUCHED (scope guard honored)

