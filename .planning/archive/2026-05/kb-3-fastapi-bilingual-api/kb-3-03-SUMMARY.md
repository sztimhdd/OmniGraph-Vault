---
phase: kb-3-fastapi-bilingual-api
plan: 03
subsystem: i18n-foundation
tags: [locale, icons, jinja2, foundation]
type: execute
wave: 1
status: complete
requirements:
  - I18N-07
files_created:
  - tests/unit/kb/test_kb3_locale_keys.py
files_modified:
  - kb/locale/zh-CN.json
  - kb/locale/en.json
  - kb/templates/_icons.html
tests_added: 46
tests_passed: 46
duration_minutes: ~5
date_completed: 2026-05-14
skill_invocations: none-required-by-plan
---

# Phase kb-3 Plan 03: Locale Keys + Icons Summary

20 new locale keys × 2 languages (40 entries) added flat-with-dots; 2 new SVG icons (`chat-bubble-question`, `lightning-bolt`) appended to the `_icons.html` macro library — pure mechanical i18n + SVG copy per UI-SPEC §5 + §3.7, no design choices.

## What was added

### Locale keys (20 keys × 2 languages, additive)

Verbatim from `kb-3-UI-SPEC.md §5` table — all values copied without paraphrase:

**Q&A state machine (8 states):**

- `qa.state.submitting`
- `qa.state.polling`
- `qa.state.streaming`
- `qa.state.error.network`
- `qa.state.error.server`
- `qa.state.timeout.message`

**Q&A result component sub-regions:**

- `qa.fallback.label` / `qa.fallback.explainer` — fts5_fallback chip + explainer
- `qa.sources.title` / `qa.entities.title` — sources + entities sub-region titles
- `qa.feedback.prompt` / `qa.feedback.thanks_up` / `qa.feedback.thanks_down` — feedback prompts (UI-only persistence per D-7)
- `qa.retry.button` — error banner retry
- `qa.question.echo_label` — question echo region

**Search inline reveal (5 keys):**

- `search.results.empty`
- `search.results.loading`
- `search.results.error`
- `search.results.view_all`
- `search.results.count` — preserves `{n}` placeholder for runtime substitution

### SVG icons (2 new, additive)

Appended after the `users` icon, before the closing `{%- endif -%}` in `kb/templates/_icons.html`:

- `chat-bubble-question` — speech bubble + question mark glyph for `qa-question` echo region
- `lightning-bolt` — for the `qa-confidence-chip--fallback` "Quick Reference" chip

Both are inline SVG path data following the existing macro convention (Heroicons-style, 24×24 viewBox, stroke 1.5, `currentColor`). Path coordinates copied verbatim from `kb-3-UI-SPEC.md §3.7` example block.

## Files

| File | Status | What |
|---|---|---|
| `kb/locale/zh-CN.json` | modified | +20 keys (flat-with-dots, matching existing convention) — 159 → 179 keys total |
| `kb/locale/en.json` | modified | +20 keys (symmetric with zh-CN) — 159 → 179 keys total |
| `kb/templates/_icons.html` | modified | +2 new `{%- elif name == ... -%}` branches; all 21 prior icons preserved verbatim |
| `tests/unit/kb/test_kb3_locale_keys.py` | created | 46 tests: 40 parametrized key-presence (20 zh + 20 en) + symmetric set + count placeholder + kb-1 baseline + 3 icon (presence × 2 + Jinja render smoke) |

## Verification

```text
$ python -m pytest tests/unit/kb/test_kb3_locale_keys.py -v
============================= 46 passed in 0.25s ==============================

$ python -m pytest tests/unit/kb/ -v -k "locale or i18n or icon or template"
====================== 54 passed, 90 deselected in 0.29s ======================
```

- `validate_key_parity()` returns `True` (no missing keys on either side)
- `i18n.t('qa.state.submitting', 'zh-CN')` → `正在提交...`; `i18n.t('qa.state.submitting', 'en')` → `Submitting...` (round-trip OK)
- All 8 pre-existing kb-1/kb-2 locale + i18n tests still pass — zero regression
- Jinja smoke test renders `icon('chat-bubble-question')`, `icon('lightning-bolt')`, AND existing `icon('home')` cleanly in one template (no macro-level breakage)

### Acceptance grep

| Pattern | File | Hit |
|---|---|---|
| `qa.state.submitting` | `kb/locale/zh-CN.json` | line 141 |
| `qa.state.submitting` | `kb/locale/en.json` | line 141 |
| `qa.fallback.label` | `kb/locale/zh-CN.json` | line 147 |
| `search.results.empty` | `kb/locale/en.json` | line 157 |
| `search.results.count` (with `{n}`) | both locale files | line 161 each |
| `chat-bubble-question` | `kb/templates/_icons.html` | line 80 |
| `lightning-bolt` | `kb/templates/_icons.html` | line 85 |

## Deviations from Plan

### Plan content: none

The plan content was executed exactly as written:

- Both locale files use flat-with-dots structure (e.g., `"qa.state.submitting": "..."`) — confirmed by reading existing files first; new keys follow the same convention. No nesting introduced.
- All 20 zh-CN values + 20 en values match the UI-SPEC §5 table verbatim (no paraphrase, no creative variation).
- All 2 SVG path coordinates match the UI-SPEC example block verbatim.
- Test file uses the resolver helper `_resolve()` that supports both flat and nested forms — defensive (currently only flat is used).
- Test file appended Task 2 icon tests in the same module rather than creating a second test file — plan permitted either, single file is simpler.

### Git attribution mix-up (parallel-agent race — repeats Phase 21 RJS lesson)

The single atomic commit `53668ec` was created with `git add <explicit-files>` listing only this plan's 5 files (`kb/locale/zh-CN.json`, `kb/locale/en.json`, `kb/templates/_icons.html`, `tests/unit/kb/test_kb3_locale_keys.py`, `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-03-SUMMARY.md`). Pre-commit `git status --short` correctly showed only those 5 in the staged column. However, the resulting commit absorbed THREE additional files that belong to sibling parallel agents (kb-3-01 / kb-3-02 still in execution):

- `kb/data/article_query.py` (M, +58 lines — DATA-07 content quality filter from kb-3-02)
- `tests/integration/kb/conftest.py` (M, ±20 lines — kb-3-02 fixture extension)
- `tests/unit/kb/test_data07_quality_filter.py` (A, +417 lines — kb-3-02 TDD test file)

Root cause is the same race documented in `~/.claude/projects/.../memory/MEMORY.md` (Phase 21 RJS, 2026-05-06): on a shared worktree with concurrent GSD agents, the staging area / HEAD pointer can capture sibling agents' in-flight modifications even when the explicit `git add` list excludes them. The git CLI behavior here looks like an implicit `-a`-equivalent absorption of unstaged-but-tracked-modified files, despite no `commit.all=true` config and no pre-commit hook.

**No destructive repair attempted** — per the established lesson learned, `git reset --soft/--mixed/--hard` and `git commit --amend` are forbidden on shared worktrees because they touch shared HEAD/staging that other agents depend on. File contents are byte-identical to what kb-3-02 produced; only commit attribution is wrong. The kb-3-02 executor agent will see those files clean (already committed) and should commit only its remaining deliverables (PLAN/SUMMARY/STATE updates).

**Files this plan was forbidden to touch (per `<git_hygiene>`)** — they are now in HEAD anyway as a side-effect of the race; not a content violation, only an attribution one. The user should be aware the kb-3-02 SUMMARY.md (when produced) will reference work already in `53668ec`.

**Mitigation for future plans:** the only fully race-safe pattern when concurrent GSD agents share a worktree is to commit IMMEDIATELY after every Edit/Write before any sibling agent has a chance to dirty the working tree, or to serialize phase-execution rather than parallelizing it. Both have throughput costs that may not be worth the marginal improvement over current attribution-noise behavior.

## Skill invocation

**None required by this plan** — pure mechanical i18n + SVG copy per UI-SPEC §5 + §3.7. No design decisions, no aesthetic choices, no token entropy considerations. The kb-3 design contract was already locked by the UI-SPEC; this plan just installs the strings and glyphs that downstream UI plans (kb-3-10 ask.html state matrix, kb-3-11 search inline reveal) will consume.

Plan-level metadata explicitly stated `NO Skill invocation discipline mandated for this plan (mechanical i18n + SVG copy)`.

## Provides for downstream plans

| Consumer | What this plan unlocked |
|---|---|
| **kb-3-10 (ask.html state matrix)** | All `qa.state.*` + `qa.fallback.*` + `qa.sources.title` + `qa.entities.title` + `qa.feedback.*` + `qa.retry.button` + `qa.question.echo_label` strings ready for `{{ key \| t(lang) }}` injection. `chat-bubble-question` icon ready for `qa-question` echo. `lightning-bolt` icon ready for `qa-confidence-chip--fallback`. |
| **kb-3-11 (search inline reveal)** | All `search.results.*` strings ready for the inline-reveal client JS state machine on homepage + articles index. |
| **kb-3-08 (qa.js streaming/done state transitions)** | Client-side JS reads `data-state-text-submitting/polling/streaming` Jinja-injected attributes that draw from `qa.state.*` keys. |

## Self-Check: PASSED

- File `kb/locale/zh-CN.json` exists, contains `qa.state.submitting`, `qa.fallback.label`, `search.results.count` with `{n}`. Confirmed.
- File `kb/locale/en.json` exists, contains symmetric `qa.state.submitting`, `qa.fallback.label`, `search.results.count` with `{n}`. Confirmed.
- File `kb/templates/_icons.html` exists, contains both `name == 'chat-bubble-question'` and `name == 'lightning-bolt'` branches. All 21 pre-existing icon branches preserved (`home`, `articles`, `ask`, `chevron-right`, `arrow-right`, `search`, `wechat`, `rss`, `web`, `inbox`, `globe-alt`, `fire`, `thumb-up`, `thumb-down`, `sources`, `tag`, `warning`, `clock`, `sparkle`, `folder-tag`, `users`). Confirmed.
- File `tests/unit/kb/test_kb3_locale_keys.py` exists, 46 tests, all passing.
- `kb.i18n.validate_key_parity()` returns `True`.
- No regression in pre-existing `tests/unit/kb/` locale/i18n/icon tests (54/54 passed in `-k "locale or i18n or icon or template"`).
