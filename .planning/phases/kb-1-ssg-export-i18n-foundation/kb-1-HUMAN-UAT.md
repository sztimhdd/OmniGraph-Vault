---
status: partial
phase: kb-1-ssg-export-i18n-foundation
source: [kb-1-VERIFICATION.md]
started: 2026-05-13T13:30:00Z
updated: 2026-05-13T13:30:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Browser visual rendering of generated article HTML

expected: Per ROADMAP Success Criterion #3 — open one of `.scratch/kb-1-10-final-output-20260513-092347/articles/*.html` (5 files) in a browser. Verify visible `中文` / `English` lang badge, correct breadcrumb labels (Home > Articles > Title), JSON-LD article schema in `<head>`, og:* meta in `<head>`, code highlighting via Pygments inline CSS, no broken images (logo placeholder degrades gracefully via onerror).
result: [pending]
why_human: Visual rendering is only verifiable by opening generated HTML in a real browser.

### 2. Browser i18n language switch + cookie persistence

expected: Per ROADMAP Success Criterion #4 — load any generated page with `?lang=en`, verify all UI chrome strings (nav, footer, page titles, etc.) toggle to English. Reload without the query param. Verify English persists via `kb_lang` cookie (1-year SameSite=Lax per kb-1-04 spec).
result: [pending]
why_human: Browser-side JavaScript behavior + cookie persistence — not verifiable from CLI alone.

### 3. Viewport responsive testing across breakpoints

expected: Per ROADMAP Success Criterion #6 (UI-03 responsive) — open homepage / articles list / article detail / Q&A entry pages on mobile (320–767px), tablet (768–1023px), desktop (1024px+) viewports. No horizontal scroll on any breakpoint.
result: [pending]
why_human: Visual viewport testing requires a real browser at multiple viewport sizes.

### 4. Source real `VitaClaw-Logo-v0.png` before kb-4 public deploy

expected: Per kb-1-04b SUMMARY "User Setup Required" — replace `kb/static/VitaClaw-Logo-v0.png.MISSING.txt` with a real PNG copied from the vitaclaw-site sibling repo. UI-04 is considered satisfied for kb-1 milestone scope per `approved-placeholder` resume signal; this is a carry-forward gate to kb-4.
result: [pending]
why_human: Operator action — sourcing a binary asset from a sibling repo not present on this Windows dev box. Currently graceful-degraded via base.html `onerror="this.style.display='none'"`.

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
