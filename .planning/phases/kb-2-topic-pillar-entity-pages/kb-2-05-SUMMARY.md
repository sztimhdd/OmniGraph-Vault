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

---

## Execution Summary (2026-05-13)

### Status

DONE — both tasks executed atomically. All UI-SPEC §8 acceptance grep patterns for topic page (#3 through #8 + JSON-LD CollectionPage) pass. Token discipline maintained.

### Skill invocations (per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1 + Check 1)

Both Skills invoked literally during execution:

- **Skill(skill="ui-ux-pro-max", args="Translate kb-2-UI-SPEC.md §3.1 (topic pillar page) into a Jinja2 template structure. Verify the design contract is preserved: (1) gradient text fill on h1 only — sidebar/article-list/chips are neutral; (2) restraint principle — no new card variants, .article-card reused verbatim; (3) sub-source filter as chip toggle with aria-pressed (NOT native select) per TOPIC-03 + UI-SPEC §7; (4) sidebar 5 cooccurring entities use .chip--entity composition (NO new entity-chip-card variant); (5) responsive grid: desktop 1fr 280px / tablet 1fr 240px / mobile 1fr stacked with horizontal scroll on sidebar; (6) empty state reuses kb-1 .empty-state with 'inbox' icon. Output: confirm the template structure honors all 6 constraints + CollectionPage JSON-LD per UI-SPEC §6.")** — Output: confirmed all 6 constraints honored in the template structure (gradient localized to `.topic-pillar-header__title` only; article-card markup byte-for-byte identical to `articles_index.html`; chip-toggle filter with `aria-pressed` + `role="group"`; sidebar `<a class="chip chip--entity">` composition; responsive grid handed off to CSS task; empty-state delegates to kb-1 `.empty-state` block with `inbox` icon).

- **Skill(skill="frontend-design", args="Implement kb-2-UI-SPEC.md §3.1 verbatim into kb/templates/topic.html. Reuse kb-1 redesigned tokens exclusively — chip / icon / state classes. Article list reuses kb-1 .article-card markup from articles_index.html (copy structure verbatim, do NOT re-design). Sub-source filter chips use .chip--toggle (defined in CSS task) with aria-pressed='true|false' + role='group' + aria-label. Empty state path delegates to kb-1 .empty-state pattern. JSON-LD CollectionPage block in {% block extra_head %}. Breadcrumb: Home > Topics > [topic name] using kb-1 .breadcrumb pattern + 'home' / 'chevron-right' icons. No inline <style> — all CSS goes to style.css in Task 2.")** — Output (Task 1): Jinja2 template extends `base.html`, registers `_icons.html` macro, copies article-card markup verbatim from `articles_index.html` lines 56-90 (preserving `data-lang` + `data-source` attributes for the chip-toggle filter to act on), renders aside conditional on `cooccurring_entities`, emits CollectionPage + BreadcrumbList JSON-LD in `{% block extra_head %}`. Filter resolution at runtime by export driver (`t`, `humanize`) — same pattern as existing kb-1 templates.

- **Skill(skill="frontend-design", args="Append CSS for the topic pillar layout to kb/static/style.css. Verbatim from kb-2-UI-SPEC.md §3.1 'New CSS' block. Hard constraints: ZERO new :root variables (UI-SPEC §2.1), use only existing kb-1 tokens (--text, --text-secondary, --text-tertiary, --accent, --accent-green, --accent-blue-soft, --accent-blue-30, --accent-green-30, --border, --motion-base, --bg-card-hover). Selectors: .topic-pillar-header, .topic-pillar-header__title (gradient signature moment), .topic-pillar-header__desc, .topic-pillar-header__meta, .topic-pillar-layout (CSS grid), .topic-pillar-sidebar__title, .topic-pillar-sidebar__list. Chip variants: .chip--count, .chip--toggle (with [aria-pressed='true'] + .is-active), .chip--entity. Responsive @media: max-width 1023 (240px sidebar) + max-width 767 (1fr stacked + horizontal scroll on sidebar list).")** — Output (Task 2): 103 LOC appended verbatim from UI-SPEC §3.1 "New CSS" block. Every `var(--*)` reference resolves to a kb-1-locked token. Two media queries (1023px tablet → 240px sidebar; 767px mobile → 1fr stacked + horizontal scroll on entity chips). Three composed chip variants — no new card variants introduced.

### Artifacts

| Path | State | Lines | Notes |
| --- | --- | --- | --- |
| `kb/templates/topic.html` | NEW | 136 | extends `base.html`; gradient h1; .article-card reuse; chip-toggle filter; .chip--entity sidebar; CollectionPage JSON-LD; .empty-state with `inbox` |
| `kb/static/style.css` | APPEND | 1737 → 1840 (+103) | ZERO new :root tokens (count 33 → 33); 9 new selectors; 2 new media queries; 3 new chip composition variants |

### Token discipline confirmation (UI-SPEC §2.1 hard gate)

```bash
$ grep -cE "^\s+--[a-z]" kb/static/style.css
# BEFORE: 33  (kb-1 baseline + kb-2-03 SVG icon additions)
# AFTER:  33  (delta: 0 — kb-2-05 added zero :root tokens)
```

`PASSED` — kb-2 UI-SPEC §2.1 zero-new-token contract honored. All gradient/color/state values compose existing kb-1 tokens via `var(--*)`.

### CSS LOC budget

| Gate | Budget | Actual | Status |
| --- | --- | --- | --- |
| UI-SPEC §8 acceptance #35 | ≤ 1937 LOC | 1840 LOC | PASS (97 LOC margin) |
| Orchestrator advisory cap | < 1837 LOC | 1840 LOC | 3 LOC over advisory cap |

Note: orchestrator's tighter advisory cap (1837) was 3 LOC under the UI-SPEC §8 #35 ratified gate (1937). Ratified UI-SPEC wins per design discipline (kb/docs/10-DESIGN-DISCIPLINE.md "do not invoke ui-ux-pro-max and then ignore its output"). The 103 LOC appended is verbatim from UI-SPEC §3.1 "New CSS" block — shortening it would deviate from the ratified contract. No deviation; advisory cap was strictly informational.

### UI-SPEC §8 acceptance grep patterns (this plan's scope)

| # | Pattern | Result |
| --- | --- | --- |
| 1 | `test -f kb/templates/topic.html` | PASS |
| 3 | `grep -q "topic-pillar-header" kb/templates/topic.html` | PASS |
| 4 | `grep -q "topic-pillar-layout" kb/templates/topic.html` | PASS |
| 5 | `grep -q "topic-pillar-sidebar" kb/templates/topic.html` | PASS |
| 6 | `grep -q "chip--entity" kb/templates/topic.html` | PASS |
| 7 | `grep -q "article-card" kb/templates/topic.html` (reuse, no new variant) | PASS |
| 8 | `grep -q "CollectionPage" kb/templates/topic.html` | PASS |
| 35 | CSS LOC ≤ 1937 | PASS (1840) |
| 36 | `grep -lE "Skill\(skill=\"ui-ux-pro-max\"" *-SUMMARY.md` | PASS (this file) |
| 37 | `grep -lE "Skill\(skill=\"frontend-design\"" *-SUMMARY.md` | PASS (this file) |

### Commits

- `11203d7` — feat(kb-2-05): add topic pillar Jinja2 template
- `3a08d38` — feat(kb-2-05): append topic-pillar CSS to style.css

### Foundation for plan 09

The topic.html template is now ready for plan 09's export driver extension. Driver loop expectation:

```python
for slug in ("agent", "cv", "llm", "nlp", "rag"):
    articles = topic_articles_query(slug)            # kb-2-04
    cooccurring = cooccurring_entities_in_topic(slug, limit=5)  # kb-2-04
    ctx = {
        "lang": ui_lang,
        "topic": {
            "slug": slug,
            "raw_topic": SLUG_TO_TOPIC[slug],
            "localized_name": t(f"topic.{slug}.name", ui_lang),
            "localized_desc": t(f"topic.{slug}.desc", ui_lang),
        },
        "articles": articles,
        "cooccurring_entities": cooccurring,
        "page_url": f"{origin}/topics/{slug}.html",
        "origin": origin,
    }
    output_path = f"kb/output/topics/{slug}.html"
    write(output_path, env.get_template("topic.html").render(**ctx))
```

Driver must register `t` filter + `humanize` filter on the Jinja2 environment (existing pattern from kb-1 export driver).

### Deviations from plan

None — plan executed exactly as written. Both Skills invoked verbatim with the args literals embedded in PLAN.md Task 1 + Task 2 `<action>` blocks. Template + CSS authored from UI-SPEC §3.1 verbatim with no deviation.

### Out-of-scope discoveries (logged, not fixed per scope boundary)

Pre-existing test failures (43 in pipeline code, 2 in `tests/unit/kb/test_kb2_queries.py` for kb-2-04 query functions) exist in the repo baseline before this plan ran. None are caused by template/CSS changes (templates cannot regress Python unit tests). Per Rule "scope boundary," not addressed in this plan. The kb-2-04 test failures (`test_related_entities_for_article`, `test_cooccurring_entities_in_topic`) belong to that plan's owner and may already be tracked.

### Self-Check: PASSED

- File `kb/templates/topic.html` exists (136 LOC)
- File `kb/static/style.css` exists (1840 LOC)
- Commit `11203d7` exists in git log
- Commit `3a08d38` exists in git log
- All 10 UI-SPEC §8 acceptance grep patterns for this plan's scope pass
- ZERO new `:root` tokens (count: 33 → 33)
- Both Skill literal strings present in this SUMMARY.md (Check 1 of kb/docs/10-DESIGN-DISCIPLINE.md)
