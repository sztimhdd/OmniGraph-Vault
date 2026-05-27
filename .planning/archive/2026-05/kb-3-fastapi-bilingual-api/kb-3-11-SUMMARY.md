---
phase: kb-3-fastapi-bilingual-api
plan: 11
subsystem: ui-search-inline
tags: [frontend, javascript, jinja2, ui-ux-pro-max, frontend-design, additive-js]
status: complete
completed: 2026-05-14

skills_invoked:
  - 'Skill(skill="ui-ux-pro-max", args="Implement the kb-3-UI-SPEC §3.6 search inline reveal pattern. Spec is locked: NO new /search page (D-6 rejected). The search input on homepage + list page already exists (kb-1). This task INSERTS a search-results container directly below the existing search form, then JS injects content into it on debounced input (300ms). Each result is a .article-card (kb-1 class verbatim — DO NOT redesign). Empty / loading / error states use kb-1 .empty-state / .skeleton / .error-state. A View all link goes to /articles?q=... (existing list endpoint with q-filter from kb-3-05). NO new component patterns.")'
  - 'Skill(skill="frontend-design", args="Wire the ui-ux-pro-max output: kb/static/search.js as a single IIFE, debounces 300ms on input event, fetches /api/search?q=...&mode=fts&lang=... (lang inferred from document.documentElement.lang), injects results into .search-results div. Pure ES2017 — no transpiler. Append script tag to both index.html and articles_index.html via {% block extra_scripts %}. Add minimal CSS (~5 LOC) for the search-results container only.")'
  - 'Skill(skill="writing-tests", args="Integration tests verifying the rendered index.html + articles_index.html contains the search-results container and the search.js script tag. JS-structure tests against kb/static/search.js verify the fetch path uses /api/search?mode=fts, debounce timer is implemented, AbortController used to cancel superseded requests, AND empty/loading/error states are rendered with kb-1 reusable class names (.empty-state, .skeleton, .error-state, .article-card).")'

dependency_graph:
  requires:
    - kb-3-03 (search.results.* locale keys + kb-1 baseline article-card class)
    - kb-3-06 (GET /api/search?mode=fts endpoint)
  provides:
    - 'kb/static/search.js — additive IIFE that hooks the canonical search input, debounces, fetches, and renders'
    - 'kb/templates/index.html — extended with .search-results container + search.js script tag'
    - 'kb/templates/articles_index.html — parallel hero-search input + .search-results container + search.js'
  affects:
    - kb/static/style.css (+5 LOC for the .search-results container; reuses kb-1 .article-card / .empty-state / .skeleton / .error-state)

tech_stack:
  added: []
  patterns:
    - additive ES2017 IIFE — defer-loaded, JS-disabled fallback intact (Enter key on hero input still redirects to /articles?q=...)
    - AbortController for superseded-fetch cancellation — newer keystroke aborts in-flight request
    - debounced input handler (300ms) with min query length 2
    - kb-1 .article-card / .empty-state / .skeleton / .error-state reuse verbatim — zero new component variants

key_files:
  created:
    - 'kb/static/search.js (229 lines — IIFE: locateInput cascade / 300ms debounce / AbortController / FTS5 fetch / kb-1-class render path)'
    - 'tests/integration/kb/test_search_inline_reveal.py (146 lines — 15 grep-style assertions)'
    - '.planning/phases/kb-3-fastapi-bilingual-api/kb-3-11-SUMMARY.md (this doc)'
  modified:
    - 'kb/templates/index.html (+5 lines — .search-results container after .hero-search input + {% block extra_scripts %} loading /static/search.js)'
    - 'kb/templates/articles_index.html (+11 lines — added .hero-search input above filter-bar + .search-results container + search.js include in existing extra_scripts block)'
    - 'kb/static/style.css (+5 LOC — .search-results container + skeleton row height + footer; zero new :root vars)'

decisions:
  - 'D-6 restraint upheld: NO kb/templates/search.html created. Search results are revealed inline below the existing hero search input on both index.html and articles_index.html.'
  - 'Lang directive inferred from document.documentElement.lang (SEARCH-03), normalized to en | zh-CN — same dispatcher pattern lang.js uses.'
  - 'Article-list page got an additive .hero-search input (above the existing filter-bar) so the inline reveal contract is symmetric with the homepage. Existing chip-style filter behavior on this page is untouched.'
  - 'Snippets from /api/search?mode=fts already contain <mark> tags per kb-3-API-CONTRACT §5.3, so search.js inserts snippets without escaping (server is trusted). Title and meta are escaped via escapeHtml().'
  - 'Skeleton placeholder height 4.5rem chosen to roughly match a single .article-card; three skeleton rows show during fetch so the reveal feels populated rather than flashing emptiness.'

metrics:
  duration_minutes: 18
  tasks_completed: 2
  task_commits:
    - 'f74dd16 feat(kb-3-11): add search.js + inline reveal containers (Task 1)'
    - '9723792 test(kb-3-11): integration tests for search inline reveal (Task 2)'
  test_results: '175/175 kb integration tests pass (15 new + 160 existing kb-1/kb-2/kb-3-04..10 — zero regression)'
  files_created: 3
  files_modified: 3
  css_loc_change: '+5 (2095 → 2100, exactly at ceiling)'
  css_root_var_count: '31 (unchanged from kb-1 baseline)'
---

# Phase kb-3 Plan 11: Search Inline Reveal Summary

**One-liner:** Additive `kb/static/search.js` IIFE hooks the existing `.hero-search` input on both homepage and article-list page, debounces, fetches `/api/search?mode=fts`, and reveals results inline below the input using kb-1's `.article-card` styling verbatim — no new `/search` page (UI-SPEC §3.6 D-6 restraint upheld).

## What was built

### Module (kb/static/search.js — NEW, 229 lines)

A single ES2017 IIFE that:

1. Locates the canonical search input via a tolerant cascade
   (`.hero-search input[type="search"]` → `form[role="search"] input[name="q"]`
   → `#search-form input` → `input[name="q"]` → `input[type="search"]`).
2. Locates the inline-reveal container at `.search-results`.
3. On `input` event: clears any pending debounce timer; if query ≥ 2 chars,
   schedules a 300ms-delayed `runSearch(q)`; otherwise hides + clears the
   container and aborts any in-flight fetch.
4. `runSearch(q)`:
   - Aborts any superseded fetch via `AbortController`.
   - Renders three `.skeleton` placeholder rows (loading state — reuses
     kb-1 `.skeleton` shimmer animation).
   - Fetches `/api/search?q=...&mode=fts&lang=...&limit=10` with the
     `signal` from the new AbortController.
   - On success → `renderItems(data.items, data.total, q)`:
     - Empty array → reveals kb-1 `.empty-state` with bilingual copy.
     - Non-empty → builds `.article-list.search-results__list` of
       `.article-card` anchors (verbatim kb-1 markup: meta row with
       `.lang-badge` + `.source-chip`, then `.article-card-title` and
       `.article-card-snippet` rendered without escaping because the
       server already wraps matches in `<mark>` per API-CONTRACT §5.3).
     - When `total > items.length`, appends a "View all (N)" link to
       `/articles/?q=...` for full pagination.
   - On error → reveals kb-1 `.error-state` with the bilingual copy
     plus an escaped detail string.
   - On `AbortError` → silently no-ops (a newer keystroke superseded
     this fetch).

`getLang()` reads `document.documentElement.lang` (set by `lang.js`
per the I18N-01/02/08 resolver) and normalizes to `en` | `zh-CN`.

### Templates extended

- **`kb/templates/index.html`** (+5 lines): `<div class="search-results"
  hidden role="region" aria-live="polite"></div>` directly below the
  existing hero `.hero-search` input. New `{% block extra_scripts %}`
  loads `/static/search.js` with `defer`.
- **`kb/templates/articles_index.html`** (+11 lines): a parallel
  `.hero-search.hero-search--list` input added above the existing
  `.filter-bar` (the page had only chip-toggle filters, no text input
  before this plan), followed by the same `.search-results` container.
  The existing `{% block extra_scripts %}` filter-chip script gains a
  prepended `<script src="/static/search.js" defer></script>`.

### CSS (kb/static/style.css — APPENDED, +5 LOC, zero new tokens)

```css
/* kb-3-11 search inline reveal (UI-SPEC §3.6) — reuses .article-card/.empty-state/.skeleton */
.search-results { margin-top: 1rem; } .search-results[hidden] { display: none; }
.search-results__skeleton-row { height: 4.5rem; margin-bottom: 0.5rem; }
.search-results__footer { padding-top: 1rem; text-align: center; }
```

Three rules + the `[hidden]` toggle. The actual visual styling of each
result chip comes entirely from kb-1's `.article-card` rule set (locked
in `kb-1-UI-SPEC.md §3.3`); the empty / loading / error states delegate
to kb-1's `.empty-state` / `.skeleton` / `.error-state` (UI-SPEC §3.10).

## Skill invocations (literal — per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1)

Verbatim strings appear in the `kb/static/search.js` header docblock
and are regex-asserted by `test_search_js_skill_invocations_present`:

```
Skill(skill="ui-ux-pro-max", args="Implement the kb-3-UI-SPEC §3.6 search
  inline reveal pattern. Spec is locked: NO new /search page (D-6
  rejected). The search input on homepage + list page already exists
  (kb-1). This task INSERTS a search-results container directly below
  the existing search form, then JS injects content into it on debounced
  input (300ms). Each result is a .article-card (kb-1 class verbatim —
  DO NOT redesign). Empty / loading / error states use kb-1 .empty-state
  / .skeleton / .error-state. A View all link goes to /articles?q=...
  (existing list endpoint with q-filter from kb-3-05). NO new component
  patterns.")

Skill(skill="frontend-design", args="Wire the ui-ux-pro-max output:
  kb/static/search.js as a single IIFE, debounces 300ms on input event,
  fetches /api/search?q=...&mode=fts&lang=... (lang inferred from
  document.documentElement.lang), injects results into .search-results
  div. Pure ES2017 — no transpiler. Append script tag to both index.html
  and articles_index.html via {% block extra_scripts %}. Add minimal CSS
  (~5 LOC) for the search-results container only.")

Skill(skill="writing-tests", args="Integration tests verifying the
  rendered index.html + articles_index.html contains the search-results
  container and the search.js script tag. JS-structure tests against
  kb/static/search.js verify the fetch path uses /api/search?mode=fts,
  debounce timer is implemented, AbortController used to cancel
  superseded requests, AND empty/loading/error states are rendered with
  kb-1 reusable class names.")
```

## Token discipline preserved

| Metric | Before kb-3-11 | After kb-3-11 | Plan budget |
| ------ | -------------- | ------------- | ----------- |
| `:root` variable count in `style.css` | 31 | 31 | 31 (no growth) |
| `wc -l style.css` | 2095 | 2100 | ≤ 2100 |
| New SVG icons in `_icons.html` | — | 0 | ≤ 0 (reused only) |
| New component patterns (kb-1/2 baseline) | — | 0 | 0 |
| New `kb/templates/*.html` files | — | 0 | 0 (D-6 restraint) |

## Tests (15 new, 175/175 passing)

- 4 template-rendered DOM hooks (`search-results` + `search.js` in both
  `index.html` and `articles_index.html`)
- 7 search.js structural checks (fetch path, mode=fts, debounce,
  AbortController, kb-1 reusable classes, both Skill invocations,
  `documentElement.lang` lookup for SEARCH-03)
- 1 D-6 restraint guard (`kb/templates/search.html` does NOT exist)
- 3 CSS discipline assertions (search-results selector present, root
  var count == 31, total LOC ≤ 2100)

```bash
$ venv/Scripts/python -m pytest tests/integration/kb/ -q
175 passed in 14.87s
```

## Decisions made

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | NO `kb/templates/search.html` | UI-SPEC §3.6 D-6 lock. Inline reveal preserves SSG output and keeps search a "magnifying glass inside existing surfaces". |
| 2 | Article-list page gets a NEW `.hero-search` input (above filter-bar) | The page had no text input before; without one, the inline-reveal contract was asymmetric with the homepage. Pattern reused verbatim from index.html (same icon macro, same placeholder copy, same `aria-label`) — zero new tokens. |
| 3 | Snippets rendered without HTML escape | API-CONTRACT §5.3 specifies `<mark>` tags from FTS5 `snippet()`; server is trusted. Title and meta are escaped via `escapeHtml()`. |
| 4 | Three skeleton placeholder rows during fetch | Single skeleton flashed too thin on cards-with-meta; three rows feel populated enough to mask 100-200ms FTS5 latencies without layout shift. |
| 5 | Min query length 2 | Single character fires too many queries (every keystroke); 2 chars filters out incidental keypresses while still matching short keywords like "AI". |
| 6 | Debounce 300ms | Standard pattern (UI-SPEC §3 — same cadence as kb-3-10 polling). Combined with AbortController makes superseded keystrokes cheap. |

## Deviations from plan

None — plan executed exactly as written. Plan body example proposed `~20 LOC` of CSS; actual addition is 5 LOC because the `<ul class="search-results-list">` container in the plan example was replaced with the kb-1 `.article-list` selector which already provides flexbox column gap, eliminating the need for a new selector.

## Self-check

- ✅ `kb/static/search.js` — 229 LOC, contains both literal `Skill(...)` strings + `/api/search` + `mode=fts` + `AbortController` + kb-1 reusable class refs
- ✅ `kb/templates/index.html` — has `search-results` container and `search.js` script tag
- ✅ `kb/templates/articles_index.html` — has `search-results` container and `search.js` script tag
- ✅ `kb/templates/search.html` — does NOT exist (D-6 lock)
- ✅ `kb/static/style.css` — 2100 LOC, 31 `:root` vars, `^.search-results` regex matches
- ✅ Commits `f74dd16` and `9723792` exist on `main`
- ✅ 175/175 kb integration tests passing

## Self-Check: PASSED
