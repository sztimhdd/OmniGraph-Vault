---
phase: kb-1-ssg-export-i18n-foundation
plan: 04
subsystem: ui
tags: [css, javascript, i18n, pygments, monokai, design-tokens, responsive, ssg]

# Dependency graph
requires: []
provides:
  - kb/static/style.css — global design tokens, responsive layout, Pygments Monokai inline
  - kb/static/lang.js — IIFE Accept-Language detection + cookie persistence + ?lang= switch
  - CSS [data-lang] visibility selectors paired with lang.js for inline-bilingual chrome
  - .lang-toggle hook (reads/writes data-current attr; cycles on click)
affects:
  - kb-1-07 (base.html template — links style.css + lang.js, uses .nav/.lang-toggle/.article-card classes)
  - kb-1-08 (article detail template — uses .article-body, .breadcrumb, .lang-badge, sets html data-fixed-lang)
  - kb-1-04b (brand assets — drops VitaClaw-Logo-v0.png + favicon.svg into kb/static/ which the nav already styles)

# Tech tracking
tech-stack:
  added:
    - "Pygments Monokai (offline-generated CSS, embedded — no second render-time stylesheet)"
  patterns:
    - "Inline bilingual via [data-lang] CSS selectors (single SSG render, JS toggles visibility)"
    - "ES5-compatible vanilla JS for older WeChat in-app browser support (no arrow functions, no let/const)"
    - "Mobile-first responsive with 768px (tablet) and 1024px (desktop) breakpoints"
    - "data-fixed-lang='true' opt-out so server-set <html lang> on article detail pages is preserved"

key-files:
  created:
    - kb/static/style.css
    - kb/static/lang.js
  modified: []

key-decisions:
  - "Pygments Monokai style def baked into kb/static/style.css (not a separate render-time CSS file) per plan; reduces template complexity, single source of truth"
  - "ES5 IIFE for lang.js — no arrow functions, no let/const, no ES6 modules — supports older WeChat in-app browser per task acceptance criteria"
  - "Inline-bilingual via [data-lang] CSS visibility (NOT separate /en/ URLs); JS toggles visibility on cookie/query/Accept-Language detection"

patterns-established:
  - "Single CSS file with sectioned design tokens + reset + primitives + components + responsive + Pygments — all in style.css (~587 LOC)"
  - "Lang resolution priority: ?lang= query > kb_lang cookie > navigator.languages > zh-CN fallback (locked in resolveLang())"
  - "Cookie format: kb_lang=zh-CN|en, max-age=31536000 (1 year), path=/, SameSite=Lax"

requirements-completed: [UI-01, UI-02, UI-03, I18N-01, I18N-02, I18N-08]

# Metrics
duration: 3min
completed: 2026-05-12
---

# Phase kb-1 Plan 04: Static CSS + JS Summary

**Bilingual UI chrome layer: 587-line dark-theme CSS with embedded Pygments Monokai + 104-line ES5 lang.js IIFE implementing 4-tier resolution (query > cookie > navigator > fallback)**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-05-12T23:43:19Z
- **Completed:** 2026-05-12T23:45:56Z
- **Tasks:** 2
- **Files modified:** 2 (created)

## Accomplishments
- Single `kb/static/style.css` (587 lines) with all 8 design-token CSS variables, mobile-first responsive at 768/1024px breakpoints, [data-lang] visibility selectors, and Pygments Monokai inline — no external font loads, no Tailwind, no preprocessor
- `kb/static/lang.js` (104 lines) ES5-compatible IIFE implementing the 4-tier language resolution: `?lang=` query → `kb_lang` cookie → `navigator.languages` → `zh-CN` default; cookie persisted 1 year with SameSite=Lax
- `.lang-toggle` click handler cycles zh ↔ en, writes cookie, reloads via `?lang=`
- `data-fixed-lang="true"` opt-out so future article detail pages can keep server-set `<html lang>` matching content language (UI-04b / I18N-05 alignment)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write kb/static/style.css** — `f300bac` (feat)
2. **Task 2: Write kb/static/lang.js** — `db8d02a` (feat)

## Files Created/Modified
- `kb/static/style.css` — Global design tokens (`--bg`, `--bg-card`, `--text`, `--accent`, `--accent-green`, etc.), reset, layout primitives, top-nav, i18n span toggling via `[data-lang]`, article list cards, article detail body styles (`.article-body`, `.breadcrumb`, `.lang-badge`), mobile-first responsive at 768/1024px, Pygments Monokai under `.codehilite` — 587 lines, 0 external font/CDN imports
- `kb/static/lang.js` — IIFE, `'use strict'`, ES5 (var + function() only), implements `readCookie`/`writeCookie`/`readQueryLang`/`detectFromBrowser`/`resolveLang`/`applyLang`/`bindToggle`, supports both `loading` and post-load DOMContentLoaded paths — 104 lines

## Acceptance Criteria Verification

### Task 1 (style.css)
- Line count 587 ≥ 300 — PASS
- 5 design-token CSS variables (`--bg: #0f172a`, `--bg-card: #1e293b`, `--text: #f0f4f8`, `--accent: #3b82f6`, `--accent-green: #22d3a0`) all present — PASS (5 grep hits)
- Font stack literal `'Inter', 'Noto Sans SC', system-ui, sans-serif` present — PASS
- 2 `@media (min-width:` queries (768px, 1024px) — PASS
- `[data-lang]`, `html[lang="en"]`, `.codehilite`, `.lang-badge` selectors — PASS (85 combined hits)
- `grep -E "@import.*://|googleapis|cdn\."` returns 0 — PASS

### Task 2 (lang.js)
- Line count 104 (range 60–110) — PASS
- All required strings (`kb_lang`, `COOKIE_MAX_AGE = 31536000`, `SameSite=Lax`, `data-fixed-lang`, `navigator.languages`, `URLSearchParams`) — PASS (9 grep hits)
- IIFE: starts with `(function ()` and ends with `})();` — PASS
- Both `addEventListener('DOMContentLoaded'` and `document.readyState` check — PASS
- No `import`, no `=>`, no `let`/`const` outside comments — PASS

## Decisions Made
- None — followed plan as specified. CSS structure (9 sections in order) and lang.js code body were both written verbatim per plan spec.

## Deviations from Plan

None — plan executed exactly as written. All acceptance criteria pass on first run.

## Issues Encountered

**Cross-agent staging contention (parallel execution side-effect):** When Task 1's `git add kb/static/style.css && git commit` ran, the staging area already contained `kb/locale/en.json` and `kb/locale/zh-CN.json` from a sibling parallel agent (kb-1-03). Per the documented `feedback_git_add_explicit_in_parallel_quicks.md` lesson, I used explicit `git add <file>` (not `-A`) — but the `git commit` step still captured everything in staging. Result: Task 1's commit `f300bac` carries 2 unrelated locale files alongside style.css. The locale file content is correct (kb-1-03's intended deliverable), so no rework needed; kb-1-03 will discover its files already committed when it runs. Documented here for traceability. Task 2's commit `db8d02a` is clean (only `kb/static/lang.js`).

## User Setup Required

None — no external service configuration required.

## Note on UI-04 (brand assets)

Per the plan's REVISION 1 (2026-05-12, Issue #4), brand-asset sourcing (UI-04: VitaClaw-Logo-v0.png + favicon.svg) was extracted into a dedicated `kb-1-04b-brand-assets-checkpoint-PLAN.md`. UI-04 is **not** delivered by this plan. The CSS in this plan defines `.nav-brand img { height: 32px; width: auto; }` so the logo will render correctly once kb-1-04b drops it into `kb/static/`.

## Next Phase Readiness

- `kb/static/style.css` and `kb/static/lang.js` are ready for the base template (kb-1-07) and article detail template (kb-1-08) to link via `<link rel="stylesheet" href="/static/style.css">` and `<script src="/static/lang.js"></script>`
- Class hooks already in place: `.nav`, `.nav-brand`, `.nav-links`, `.lang-toggle`, `.container`, `.btn`, `.btn-secondary`, `.article-card`, `.article-card-title`, `.article-card-meta`, `.lang-badge`, `.source-badge`, `.breadcrumb`, `.article-body`, `.article-detail-layout`
- Lang attribute hook: `<html data-fixed-lang="true" lang="...">` on article detail pages will be preserved by lang.js (Wave 1 unblocks template work)

## Self-Check: PASSED

- `kb/static/style.css` exists — FOUND (587 lines)
- `kb/static/lang.js` exists — FOUND (104 lines)
- Commit `f300bac` (Task 1) — FOUND in git log
- Commit `db8d02a` (Task 2) — FOUND in git log

---
*Phase: kb-1-ssg-export-i18n-foundation*
*Plan: 04*
*Completed: 2026-05-12*
