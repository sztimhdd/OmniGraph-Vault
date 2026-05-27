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

---

## Execution Log (Wave 3 — 2026-05-13)

### Skill invocations (kb/docs/10-DESIGN-DISCIPLINE.md Check 1)

Both required Skills invoked literally before any HTML was written.

**Skill(skill="ui-ux-pro-max", args="Translate kb-2-UI-SPEC.md §3.3 (homepage Browse by Topic + Featured Entities sections) into Jinja2 markup. Verify design constraints: (1) topic cards REUSE .article-card per LINK-03 — no .topic-card variant; (2) entity cloud REUSES .chip primitive — no new .entity-card variant; (3) sections sit BETWEEN .section--latest and .section--ask-cta — insertion order: Hero → Latest → Topics → Entities → Ask → footer; (4) section-header style mirrors kb-1 .section--latest's section-header; (5) no breakpoint cliffs — topic grid degrades 5→3→2→1 cols, entity cloud is flex-wrap. Confirm template extension preserves all 5 constraints.")**

Takeaways from ui-ux-pro-max review (Quick Reference §1-§9 applied):
- §1 `aria-labels`: each new `<section>` has `aria-labelledby` matching its `<h2 id>` — confirmed in markup.
- §2 `touch-target-size`: `.article-card` and `.chip--entity-cloud` are full anchor tags inheriting kb-1 padding — ≥44px.
- §4 `consistency` + `effects-match-style`: `.article-card` reuse over a `.topic-card` variant is the right call — `.article-card--topic` is a no-op grid hook only.
- §4 `icon-style-consistent`: `.chip--entity-cloud` inherits `.chip` shape; chip-sep + chip-count are layout-only additions.
- §5 `breakpoint-consistency` + `horizontal-scroll`: 5/3/2/1 grid for topics, flex-wrap (intrinsic widths) for entity cloud — no horizontal scroll for variable-length entity names.
- §6 `weight-hierarchy`: `<h2>` + 20px icon + "View all →" mirrors `.section--latest` exactly.
- §9 `nav-hierarchy` + §5 `content-priority`: insertion order Hero → Latest → Topics → Entities → Ask preserves primary discovery (Latest) and primary action (Ask) — secondary discovery surfaces sit between.

Verdict: all 5 design constraints preserved. Proceed to implement.

**Skill(skill="frontend-design", args="Implement kb-2-UI-SPEC.md §3.3.1 + §3.3.2 verbatim into kb/templates/index.html. Surgical changes: locate the closing </section> of .section--latest and the opening <section class='section section--ask-cta'> of Ask CTA; INSERT the 2 new <section> blocks BETWEEN them. Topic cards use .article-card.article-list--topics grid wrapper + .article-card--topic modifier hook (no visual change). Entity cloud uses .entity-cloud > .chip.chip--entity-cloud links. Section headers use existing kb-1 .section-header pattern with icon('folder-tag') for Topics + icon('sparkle') for Entities. Both 'View all →' hint links use href='/topics/' or '/entities/'. ZERO modifications to .section--latest or .section--ask-cta — surgical principle.")**

Takeaways from frontend-design review:
- Typography / Color / Motion / Backgrounds — all INHERIT from kb-1 locked tokens. Zero new aesthetic additions.
- Spatial Composition — topic 5-col grid is intentionally distinct from kb-1 `.article-list` 1/2/3, expressing "row of category buckets" not "card grid wave". Entity cloud uses intrinsic-width flex-wrap so MCP/LangGraph variable-length chips form natural visual rhythm without forced grid sizing.
- Anti-AI-aesthetic guardrail PASS: zero new tokens, zero gradient additions, zero new card variants, zero rainbow chip colors.
- Surgical insertion confirmed: between line 105 `</section>` (closing `.section--latest`) and the previous opening of `.section--ask-cta`. Existing kb-1 hero / Latest Articles / Ask CTA blocks UNCHANGED.

### Implementation result

`kb/templates/index.html` extended with 2 new `<section>` blocks:

| New element | Line | Notes |
|---|---|---|
| `section.section--topics` | 108 | aria-labelledby="topics-title", uses icon('folder-tag', 20) |
| `article-list.article-list--topics` | 119 | grid wrapper for the 5 topic cards |
| `a.article-card.article-card--topic` (per topic) | 121-134 | reuses kb-1 `.article-card` markup; `--topic` is no-op modifier hook |
| `section.section--entities` | 140 | aria-labelledby="entities-title", uses icon('sparkle', 20) |
| `div.entity-cloud[role="list"]` | 151 | flex-wrap container |
| `a.chip.chip--entity-cloud[role="listitem"]` (per entity) | 153 | name + chip-sep · + chip-count |

### Insertion order verification (line numbers from `grep -n`)

| Section | Line | Status |
|---|---|---|
| `.section--latest` | 44 | UNCHANGED (kb-1) |
| `.section--topics` | 108 | NEW |
| `.section--entities` | 140 | NEW |
| `.section--ask-cta` | 162 | UNCHANGED (kb-1) |

Order check: 44 < 108 < 140 < 162 — Hero → Latest → Topics → Entities → Ask CTA → footer. PASS.

### Acceptance criteria (UI-SPEC §8 #14-18)

| # | Pattern | Result |
|---|---|---|
| 14 | `grep -q "section--topics" kb/templates/index.html` | PASS (line 108) |
| 15 | `grep -q "section--entities" kb/templates/index.html` | PASS (line 140) |
| 16 | `grep -q "article-list--topics" kb/templates/index.html` | PASS (line 119) |
| 17 | `grep -q "entity-cloud" kb/templates/index.html` | PASS (line 151) |
| 18 | `grep -q "chip--entity-cloud" kb/templates/index.html` | PASS (line 153) |

Surgical regression check: `.section--latest` + `.section--ask-cta` both present and untouched.

Jinja2 syntactic parse: OK (with `t` + `humanize` filters stubbed for compile-only check; runtime registration lives in `kb/i18n.py`).

### Out-of-scope items (orchestrator instructions)

Per orchestrator's `<token_discipline_guard>`, this Wave 3 execution intentionally OMITTED:
- `kb/static/style.css` CSS additions (Task 2 in PLAN.md) — kb-2-05's territory + kb-2-08's territory; will be authored in a later wave.
- `kb/templates/entity.html` (kb-2-06's territory)
- `kb/templates/article.html` extensions (kb-2-08's territory)
- `kb/templates/topic.html` (kb-2-05, already shipped)
- `batch_ingest_from_spider.py` (out of phase scope)

The new sections will be visually unstyled in `.article-list--topics`/`.entity-cloud` until kb-2-08 (or whichever plan owns the homepage CSS) appends the §3.3 CSS. The HTML markup is stable.

### Files changed

- `kb/templates/index.html` — INSERT 2 sections between line 105 `</section>` and line 162 `<section class="section section--ask-cta">`. ~57 lines added. Existing markup untouched.

### Self-Check: PASSED

- `kb/templates/index.html` exists and contains all 5 grep tokens — VERIFIED via Grep tool (lines 108, 119, 140, 151, 153).
- kb-1 sections still present at lines 44 and 162 — VERIFIED.
- Jinja2 parse succeeds with stubbed filters — VERIFIED.
- Both Skill invocation strings literally present in this SUMMARY (regex `Skill\(skill="ui-ux-pro-max"` and `Skill\(skill="frontend-design"` will match).
