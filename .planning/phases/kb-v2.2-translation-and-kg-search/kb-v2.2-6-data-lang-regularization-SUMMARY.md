---
phase: kb-v2.2-6-data-lang-regularization
status: complete
shipped: 2026-05-18
loc_added_modified: ~30 LOC (helper + 3 call-site updates) + ~180 LOC tests
---

# Phase kb-v2.2-6 — SSG Export data-lang Regularization (F6)

## Goal

Eliminate legacy short-code `data-lang="zh"` on article cards in the SSG
output. Canonicalize all article-level lang attrs to `zh-CN` so the JS
filter `[data-lang='zh-CN']` no longer silently misses Chinese cards
tagged with the legacy short code.

## Background

Per kb-v2.2 INPUT.md Wave 1 hygiene scope: prod `/articles/index.html`
emitted mixed values:

| data-lang value | count (prod) | source |
|---|---|---|
| `"zh"`          | 760 | legacy DB rows with `articles.lang = 'zh'` |
| `"zh-CN"`       | 288 | DB rows with `articles.lang = 'zh-CN'` |
| `"en"`          | 864 | English articles |

The JS filter at `articles_index.html:154` uses
`c.getAttribute('data-lang') === current.lang` where `current.lang` is the
canonical long form `'zh-CN'`. This silently dropped the 760 `zh`-tagged
cards from the 中文 filter view.

## Root cause

`kb/export_knowledge_base.py::_record_to_dict` passed `rec.lang` through
to the template dict verbatim:

```python
"lang": rec.lang or "unknown",
```

`rec.lang` came directly from `articles.lang` / `rss_articles.lang`
columns. Prod has both `'zh'` (legacy ingest output) and `'zh-CN'`
(canonical). No normalization layer existed.

## Fix

Added pure helper `_canonical_lang()` at the data-layer-to-template
boundary in `kb/export_knowledge_base.py`:

```python
def _canonical_lang(lang: str | None) -> str:
    if lang is None or lang == "":
        return "unknown"
    if lang == "zh":
        return "zh-CN"
    return lang
```

Mapping:

- `'zh'` → `'zh-CN'` (legacy short → canonical)
- `'zh-CN'` → `'zh-CN'` (idempotent)
- `'en'` → `'en'`
- `'unknown'` → `'unknown'`
- `None` / `''` → `'unknown'`
- other (e.g. `'ja-JP'`, `'fr'`) → pass through (defensive: don't silently
  rewrite future codes)

Applied at 3 SSG emission sites:

1. `_record_to_dict` line 240 — article-card data dict (the main fix)
2. Article-detail page `ctx["lang"]` line 340 — page-level html lang attr
3. URL-index sidecar `lang` field line 351 — internal hash index

NOT a multi-form aliasing scheme; SSG output is always single canonical
long form `zh-CN`. API request schema (`Literal['zh','en']`) is unaffected
— that layer never passes through this helper.

## Tests

`tests/integration/kb/test_ssg_export_data_lang.py` — 8 cases, all PASS:

### Unit tests (6 cases — pure helper)

- `test_canonical_lang_maps_legacy_zh_to_canonical_zh_cn`
- `test_canonical_lang_idempotent_on_zh_cn`
- `test_canonical_lang_passes_through_en`
- `test_canonical_lang_none_or_empty_returns_unknown`
- `test_canonical_lang_unknown_passes_through`
- `test_canonical_lang_passes_through_unrecognized_codes` (defensive)

### Integration tests (2 cases — full SSG render with synthetic fixture)

- `test_ssg_export_normalizes_legacy_zh_to_zh_cn_in_articles_index` —
  builds a fixture DB with 1 legacy `zh` + 1 canonical `zh-CN` + 1 `en`
  article; runs `python -m kb.export_knowledge_base` as subprocess;
  asserts both Chinese cards render with `data-lang="zh-CN"` and zero
  with `data-lang="zh"`
- `test_ssg_export_emits_no_legacy_zh_data_lang_on_article_cards` —
  acceptance test: regex-extracts every `<a class="article-card" ... data-lang>`
  + `<span class="lang-badge" ... data-lang>` from SSG output and asserts
  none equal `"zh"`

These tests are the actual acceptance gate; browser UAT was skipped
because local DB has no legacy `zh` rows to demonstrate the fix visually
(local DB query: `articles.lang` is uniform `zh-CN`). Synthetic-fixture
integration test exercises the same code path with the failure-case data
that exists in prod. The full SSG output verification (subprocess run +
post-render DOM assertions) is more rigorous than a browser screenshot
would have been.

## Verification

- `pytest tests/integration/kb/test_ssg_export_data_lang.py -v`: **8/8 PASS** in 2.39s
- Full pytest: **1284 passed, 0 failed**, 5 skipped, 13 xfailed, 9 warnings (no regression vs F5 baseline of 1276)
- Local re-export (`KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe kb/export_knowledge_base.py`): completes successfully; data-lang counts in output unchanged because local DB has no legacy `zh` values (only `zh-CN`/`en`/`unknown`) — the fix is a no-op on local data, which is the correct idempotent behavior

## Skill discipline

`Skill(skill="python-patterns")` — pure-function helper with explicit
mapping table, type-annotated, idempotent on canonical input, defensive
pass-through on unrecognized codes (no silent rewriting of future
language codes).

## Files changed

| File | Change |
|---|---|
| `kb/export_knowledge_base.py` | +29 LOC: `_canonical_lang()` helper + 3 call-site updates (lines 240/340/351) |
| `tests/integration/kb/test_ssg_export_data_lang.py` | +180 LOC NEW: 6 unit + 2 integration |

Total: ~210 LOC (29 prod + 180 test).

## Anti-patterns honored

- ❌ NOT touched API request schema (`Literal['zh','en']`) — backward compat preserved
- ❌ NOT changed DB `articles.lang` column — already documented as canonical zh-CN target; SSG-side normalization is the right place for legacy-data hygiene
- ❌ NOT introduced multi-form aliasing — single canonical form `zh-CN` only
- ❌ NOT changed UI bilingual chrome (`data-lang="zh"` / `data-lang="en"` short codes used by CSS visibility selectors `html[lang="zh-CN"] [data-lang="zh"]`) — that's a separate concern (binary visibility toggle, not article-level lang)
- ❌ NO `git add -A`, `--amend`, `--reset --hard`, `--rebase -i`, `push --force`
- ❌ NO scope creep — discovered local DB has no zh rows but did NOT investigate `lang_detect.py` (would-be scope expansion)

## Concurrent agent safety

Per `feedback_git_add_explicit_in_parallel_quicks.md` strengthened pattern
(post-2026-05-18 update), this commit uses atomic `git add → commit → push`
chain in a single Bash invocation. Post-commit `git show --stat HEAD` audit
verifies attribution.

## Next

kb-v2.2 Wave 1 complete (F5 + F6 + F9; F12 is Wave 1 P0 prereq, plan
already exists, awaits execute). Wave 2 phases (F1' bidirectional
translation, F8' KG search default, FU-1 citation+image) blocked on F12
completion.
