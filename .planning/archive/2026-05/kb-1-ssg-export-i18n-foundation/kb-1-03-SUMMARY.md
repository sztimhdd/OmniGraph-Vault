---
phase: kb-1-ssg-export-i18n-foundation
plan: 03
subsystem: kb-v2
tags: [kb-v2, i18n, bilingual, jinja2, tdd]
one_liner: "Bilingual i18n foundation — 45-key locale JSONs (zh-CN + en) + kb.i18n module exposing t(key, lang) as a Jinja2 filter, 8/8 unit tests pass."
requirements:
  - I18N-03
dependency_graph:
  requires:
    - kb/config.py (KB_DEFAULT_LANG constant) — landed via kb-1-01 parallel
  provides:
    - kb.i18n.t — translation function
    - kb.i18n.register_jinja2_filter — Jinja2 env wiring
    - kb.i18n.validate_key_parity — build-time invariant check
    - kb.i18n.load_locales — lazy module-level cache
    - kb/locale/zh-CN.json + kb/locale/en.json (45 keys, identical key set)
  affects: []
tech-stack:
  added:
    - jinja2 (already a LightRAG indirect dep; pinned in PROJECT-KB-v2.md)
  patterns:
    - module-level lazy locale cache (treats locale JSON as ship-time static)
    - dot-notation key namespace (no nested dict)
    - missing-key returns literal + WARN log (visible-in-UI debugging)
    - both-langs-inline emit pattern documented in plan (used by later kb-1-07 templates)
key-files:
  created:
    - kb/locale/zh-CN.json (45 keys, Chinese chrome strings)
    - kb/locale/en.json (45 keys, English chrome strings)
    - kb/i18n.py (95 lines: t, load_locales, validate_key_parity, register_jinja2_filter)
    - tests/unit/kb/test_i18n.py (108 lines: 8 tests)
  modified: []
decisions:
  - "45 keys (not 50) — plan said ~50; the actual chrome string set spans 9 namespaces (site/nav/lang/home/articles/article/breadcrumb/ask/footer) at 45. In-band per plan (45-55 acceptance range)."
  - "Missing key returns key literal + logs WARN (NOT raises) — per CONTEXT.md, missing translations should be visible in rendered HTML for fast debugging."
  - "Module-level _LOCALES cache cleared between tests via autouse fixture so monkeypatched _LOCALE_DIR in mismatch test takes effect."
metrics:
  duration_minutes: 4
  tasks: 2
  files: 4
  tests: 8
  test_pass: 8
  test_fail: 0
  completed: "2026-05-12T23:47:27Z"
---

# Phase kb-1 Plan 03: i18n Locale Foundation Summary

## Objective Recap

Build the bilingual i18n foundation per I18N-03 — locale JSON dictionaries for ~50 chrome strings + Python helper exposing `t(key, lang)` as a Jinja2 filter. Templates in plans kb-1-06/07/08 will consume `{{ 'nav.home' | t(lang) }}` everywhere, so a key-parity check upfront prevents downstream template rot.

## What Shipped

### Locale JSONs (45 keys each, perfect parity)

`kb/locale/zh-CN.json` and `kb/locale/en.json` — identical key sets across 9 namespaces:

| Namespace | Keys | Purpose |
|-----------|------|---------|
| `site.*` | 4 | brand, brand_aux, tagline, title |
| `nav.*` | 4 | home, articles, ask, search_placeholder |
| `lang.*` | 5 | toggle_to_en, toggle_to_zh, current_zh, current_en, switcher_aria |
| `home.*` | 5 | hero_title, hero_subtitle, section_latest, section_ask_cta, section_ask_desc |
| `articles.*` | 10 | page_title, filter_lang, filter_source, filter_all, filter_lang_zh, filter_lang_en, filter_source_wechat, filter_source_rss, empty, read_more |
| `article.*` | 7 | lang_zh, lang_en, source_label, published_at, body_source_enriched, body_source_raw, cta_ask |
| `breadcrumb.*` | 2 | home, articles |
| `ask.*` | 5 | page_title, input_placeholder, submit, hot_questions, disclaimer |
| `footer.*` | 3 | copyright, about, contact |
| **Total** | **45** | |

Brand: `企小勤` (zh main) / `VitaClaw` (en main) per V-3 from `kb/docs/09-AGENT-QA-HANDBOOK.md`.

### kb/i18n.py (95 LOC, library-style — `logging` not `print`)

Public API:

| Symbol | Purpose |
|--------|---------|
| `t(key, lang=None) -> str` | Translate dot-notation key. Falls back to `KB_DEFAULT_LANG` for None/unsupported lang; returns key literal + WARN on missing. |
| `register_jinja2_filter(env)` | Wires `t` as `env.filters["t"]` for `{{ 'nav.home' \| t(lang) }}` template usage. |
| `validate_key_parity() -> bool` | Build-time invariant — raises `ValueError` listing the diff if locales asymmetric, returns `True` on parity. |
| `load_locales() -> dict` | Lazy module-level cache; loads both JSONs once. |

### tests/unit/kb/test_i18n.py (8 tests, all pass)

| # | Test | Behavior |
|---|------|----------|
| 1 | `test_t_zh_cn_returns_chinese_string` | `t('nav.home', 'zh-CN')` → `'首页'` |
| 2 | `test_t_en_returns_english_string` | `t('nav.home', 'en')` → `'Home'` |
| 3 | `test_t_missing_key_returns_key_literal_and_logs_warn` | `t('nonexistent.key', 'en')` → `'nonexistent.key'` + WARN log |
| 4 | `test_t_no_lang_defaults_to_kb_default_lang` | `t('nav.home')` → `'首页'` (KB_DEFAULT_LANG=zh-CN) |
| 5 | `test_t_unsupported_lang_falls_back_and_logs_warn` | `t('nav.home', 'fr')` → `'首页'` + WARN log |
| 6 | `test_validate_key_parity_true_on_match_and_raises_on_mismatch` | Real locales pass; injected mismatched dir raises `ValueError(parity)` |
| 7 | `test_register_jinja2_filter_renders_in_template` | `Environment` + filter renders `{{ 'nav.home' \| t('en') }}` → `'Home'` |
| 8 | `test_load_locales_returns_both_languages` | dict has `zh-CN` and `en` keys with expected values |

## Verification

| Acceptance criterion | Evidence |
|----------------------|----------|
| Both files exist + parse as valid JSON | `python -c "import json; json.load(open('kb/locale/zh-CN.json',encoding='utf-8'))"` exits 0 |
| Identical key set | `set(zh.keys()) == set(en.keys())` → True (verified in Task 1 verify command) |
| 45-55 keys total | 45 (in band) |
| `nav.home` zh = `首页`, en = `Home` | Verified via t() output |
| All required keys (`site.brand`, `nav.home`, `nav.articles`, `nav.ask`, `lang.toggle_to_en`, `lang.toggle_to_zh`, `footer.copyright`, `breadcrumb.home`, `breadcrumb.articles`, `articles.page_title`) | All present in both files |
| `grep -c "lang.current_zh" kb/locale/zh-CN.json` | 1 |
| `python -c "from kb.i18n import t; print(t('nav.home', 'zh-CN'))"` outputs `首页` | Verified |
| `python -c "from kb.i18n import t; print(t('nav.home', 'en'))"` outputs `Home` | Verified |
| `python -c "from kb.i18n import t; print(t('missing.key', 'en'))"` outputs `missing.key` | Verified |
| `python -c "from kb.i18n import validate_key_parity; print(validate_key_parity())"` outputs `True` | Verified |
| `pytest tests/unit/kb/test_i18n.py -v` exits 0 with 8 tests passing | 8/8 PASS in 0.14s |
| `kb/i18n.py` does NOT contain `print(` | `grep -c "print(" kb/i18n.py` → 0 |
| `kb/i18n.py` contains `_SUPPORTED_LANGS`, `register_jinja2_filter`, `validate_key_parity`, `env.filters["t"] = t` | All 4 present (8 grep hits, multiple references each) |

## Commits

| Stage | Commit | Files |
|-------|--------|-------|
| Task 1 (locale JSONs) | `f300bac` | kb/locale/zh-CN.json, kb/locale/en.json (bundled with kb-1-04 due to parallel-agent staging-area collision — see Deviations) |
| Task 2 RED (failing tests) | `b435ae8` | tests/unit/kb/test_i18n.py |
| Task 2 GREEN (impl) | `1bd67dd` | kb/i18n.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Concurrency] Locale JSONs absorbed into kb-1-04 sibling commit**

- **Found during:** Task 1 commit attempt
- **Issue:** While I had `kb/locale/*.json` staged but uncommitted, the parallel kb-1-04 executor agent ran a `git add` (likely `-A` or path-glob) that swept my staged files into its own commit (`f300bac feat(kb-1-04): add static style.css ...`). When I retried `git commit`, my changes were already committed under the kb-1-04 message; staging area was empty.
- **Root cause:** Documented hazard from `~/.claude/CLAUDE.md` Lessons Learned 2026-05-11 lmc/lmx — concurrent GSD agents share staging area; one agent's broad `git add` absorbs another's staged files.
- **Fix:** Verified file content survived intact (45 keys, correct values). No code changes needed. Recorded `f300bac` as the Task 1 commit hash for traceability even though the message attribution is wrong.
- **Files modified:** None (cleanup only — content was correct before the race)
- **Commit:** `f300bac` (cross-attributed; my contribution = 2 files / 110 lines)

### Test Count

- Plan said "8 tests"; my initial draft had 9 (split parity-True and parity-Raises into two tests). Refactored to 8 per plan exactly by combining into single test that exercises both paths sequentially. No behavior loss; only the count reduced from 9→8 to match the literal acceptance criterion.

## Self-Check: PASSED

- `kb/locale/zh-CN.json` — FOUND
- `kb/locale/en.json` — FOUND
- `kb/i18n.py` — FOUND
- `tests/unit/kb/test_i18n.py` — FOUND
- Commit `f300bac` — FOUND in `git log`
- Commit `b435ae8` — FOUND in `git log`
- Commit `1bd67dd` — FOUND in `git log`
- 8/8 unit tests PASS (pytest exit 0)
- `validate_key_parity()` → True
- All acceptance criteria from PLAN met

## Notes for Downstream Plans

- **kb-1-06 (article_query):** does NOT consume kb.i18n; that plan stays in the data layer.
- **kb-1-07 (base templates) + kb-1-08 (article detail):** WILL import `kb.i18n.register_jinja2_filter` in their template environment setup, then use `{{ 'nav.home' | t(lang) }}` syntax. The "both langs inline via `<span data-lang>...</span>`" emit pattern from CONTEXT.md is template-side responsibility, not i18n.py's.
- **kb-1-09 (export driver):** SHOULD call `validate_key_parity()` once at build start; on `ValueError`, abort the export with a clear "fix locale JSON parity first" error. Recommendation only — adding to that plan is out-of-scope here.
- **Brand strings (`site.brand`, `site.brand_aux`, `footer.copyright`) are intentionally cross-pollinated** — zh shows "© 2026 企小勤 VitaClaw", en shows "© 2026 VitaClaw 企小勤" — both languages always present per V-3 lock.
