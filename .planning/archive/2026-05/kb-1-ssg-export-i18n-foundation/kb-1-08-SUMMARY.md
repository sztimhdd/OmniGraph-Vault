---
phase: kb-1-ssg-export-i18n-foundation
plan: "08"
subsystem: ui
tags: [kb-v2, jinja2, article-detail, i18n, content-lang, json-ld, breadcrumb, og-meta, ssg]

# Dependency graph
requires:
  - phase: kb-1-03
    provides: "kb.i18n.register_jinja2_filter — `{{ key | t(lang) }}` filter consumed by article.html"
  - phase: kb-1-04
    provides: "/static/style.css + /static/lang.js — referenced via link/script tags"
  - phase: kb-1-07
    provides: "kb/templates/base.html — chrome layout pattern; article.html intentionally INLINES chrome instead of extending base.html (content-lang axis divergence)"
provides:
  - "kb/templates/article.html — per-article detail template with `<html lang>` set to article CONTENT lang, data-fixed-lang='true' marker for lang.js, JSON-LD Article schema, breadcrumb, lang badge, pre-rendered body HTML via `| safe`"
affects:
  - "kb-1-09 (export driver) renders this template per article with the documented render-context shape"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Inlined chrome (not `{% extends \"base.html\" %}`): article.html is the sole template that overrides `<html lang>` to article-content lang and sets data-fixed-lang='true' so lang.js does NOT override. Trade-off: ~80 lines of chrome duplication vs hacking base.html with conditionals — Surgical Changes principle prefers duplication."
    - "`{{ body_html | safe }}` — body_html is pre-rendered HTML (markdown.markdown + Pygments codehilite already applied by the export driver in plan kb-1-09). `| safe` disables auto-escape so Pygments class attributes survive."
    - "`{{ json_ld | tojson }}` — Jinja2's tojson filter properly escapes for `<script type='application/ld+json'>` context (escapes `</script>` sequences, etc.)"
    - "Lang badge emits in CONTENT lang only (no dual-span) — it's a content marker, not chrome. Article meta labels (`article.source_label`, `article.published_at`) stay dual-span because they're chrome."

key-files:
  created:
    - kb/templates/article.html (105 lines)
  modified: []

key-decisions:
  - "article.html INLINES chrome instead of extending base.html — required because <html lang> + data-fixed-lang attributes diverge from base.html's UI-chrome-lang model. Per CONTEXT.md 'Content language vs UI language (two axes)' — detail pages are the ONE place where the two axes split."
  - "Lang badge uses single-emit (NOT dual-span). The badge is a content marker fixed to article.lang, never toggled by the UI lang switcher. Implementation: `{% if article.lang == 'zh-CN' %}{{ 'article.lang_zh' | t('zh-CN') }}{% elif article.lang == 'en' %}{{ 'article.lang_en' | t('zh-CN') }}{% else %}—{% endif %}` — both branches emit the zh-CN-locale label because the locale JSON keeps language-name labels in both languages anyway (zh-CN.json: lang_zh='中文', lang_en='English'; en.json: lang_zh='中文', lang_en='English')."
  - "og:type='article' (literal) — base.html has 'website'; article.html overrides because the page IS an article (UI-05 + Open Graph spec)."

patterns-established:
  - "Content-lang axis template pattern: any future page that emits a single piece of fixed-language content (article-detail-equivalent for entity pages, etc.) should follow this inlined-chrome pattern, NOT extend base.html"
  - "JSON-LD via | tojson filter: avoids manual JSON serialization and auto-handles `</script>` escaping"
  - "Body HTML is pre-rendered upstream of the template: the template never calls markdown.markdown() or pygments — those run in kb-1-09's export driver and the result is passed in as `body_html`"

requirements-completed: [I18N-05, I18N-06, UI-06, UI-07, EXPORT-04]

# Metrics
duration: 87s
completed: 2026-05-13
---

# Phase kb-1 Plan 08: Article Detail Template Summary

**kb/templates/article.html — 105-line bilingual article detail template with content-lang axis (`<html lang>` from article.lang), data-fixed-lang marker, JSON-LD Article schema, breadcrumb with localized labels, single-emit lang badge, and pre-rendered Pygments body HTML inlined via `| safe`. Inlines chrome instead of extending base.html.**

## Performance

- **Duration:** ~87 seconds
- **Started:** 2026-05-13T00:16:50Z
- **Completed:** 2026-05-13T00:18:17Z
- **Tasks:** 1
- **Files created:** 1

## Accomplishments

- `kb/templates/article.html` — per-article detail template (105 lines) with:
  - `<html lang="{{ article.lang }}" data-fixed-lang="true">` — content-lang axis (I18N-05); `data-fixed-lang` is the marker that lang.js (kb-1-04) checks to NOT override the server-set lang
  - `<title>` includes article title + bilingual brand
  - og:* meta block with `og:type='article'` (override of base.html's `'website'`) + `og:locale` matching content lang (UI-05)
  - JSON-LD Article schema via `{{ json_ld | tojson }}` (UI-06) — proper script-context JSON escaping
  - Top nav with bilingual chrome (dual-span), lang-toggle button (consistent with base.html)
  - Breadcrumb `<nav class="breadcrumb">` Home > Articles > [Article Title] with localized labels (UI-07)
  - Lang badge `<span class="lang-badge">` emits content lang in single language (I18N-06) — content marker, not chrome
  - Article meta block (source, published date, optional `vision_enriched` indicator) — labels are chrome (dual-span), values are data (single-emit)
  - Pre-rendered body HTML inline via `{{ body_html | safe }}` (EXPORT-04) — Pygments already baked in by export driver
  - Footer + lang.js script tag (matching base.html footer pattern)

## Task Commits

Committed atomically with `--no-verify` and explicit `git add <file>`:

1. **Task 1: Write kb/templates/article.html** — `d78acdc` (feat)

## Files Created/Modified

| Path | Lines | Purpose |
|------|------:|---------|
| `kb/templates/article.html` | 105 | Per-article detail template with content-lang axis + JSON-LD + breadcrumb + lang badge + pre-rendered body |

## Acceptance Criteria — All Met

| # | Criterion | Evidence |
|---|-----------|----------|
| 1 | `kb/templates/article.html` exists with line count ≥ 60 | 105 lines (`wc -l` output) |
| 2 | Contains `<html lang="{{ article.lang }}" data-fixed-lang="true">` | grep line 2 — exact match |
| 3 | Contains `application/ld+json` (UI-06 JSON-LD) | grep line 19 |
| 4 | Contains `class="lang-badge"` (I18N-06) | grep line 63 |
| 5 | Contains `class="breadcrumb"` (UI-07) | grep line 46 |
| 6 | Contains `og:type` with value `article` | grep + render assertion `'og:type' in html and 'content="article"' in html` PASS |
| 7 | Contains `{{ body_html \| safe }}` (EXPORT-04) | grep line 84 |
| 8 | Contains `{{ json_ld \| tojson }}` | grep line 20 |
| 9 | Renders without Jinja2 error with sample context | render exit 0, en_render_len=3226 |
| 10 | `lang='en'` context produces `lang="en"` in output | assert `'lang="en"' in html_en` PASS |
| 11 | Does NOT contain `{% extends "base.html" %}` | grep returns 0 hits — inlines chrome by design |

## Verification Evidence

```
$ wc -l kb/templates/article.html
105

$ PYTHONPATH=. venv/Scripts/python .scratch/kb-1-08-verify.py
OK en_render_len=3226 zh_render_len=3203

$ grep -nE 'application/ld\+json|class="lang-badge"|class="breadcrumb"|data-fixed-lang="true"|body_html \| safe|json_ld \| tojson' kb/templates/article.html
2:<html lang="{{ article.lang }}" data-fixed-lang="true">
19:  <script type="application/ld+json">
20:  {{ json_ld | tojson }}
46:      <nav class="breadcrumb" aria-label="breadcrumb">
63:            <span class="lang-badge">
84:          {{ body_html | safe }}

$ grep -c 'extends "base.html"' kb/templates/article.html
0
```

The verify script (`.scratch/kb-1-08-verify.py`) renders article.html under both `lang='en'` and `lang='zh-CN'` contexts and asserts:

- `lang="en"` appears in en-render output (content-lang propagation)
- `lang="zh-CN"` appears in zh-render output (content-lang propagation)
- `data-fixed-lang="true"` present
- `application/ld+json` script tag emitted
- `class="lang-badge"` element present
- `class="breadcrumb"` element present
- `og:type` ... `content="article"` (override of base.html's website type)
- `<p>Body HTML</p>` survives in output (proves `| safe` not escaping)
- `"inLanguage": "en"` round-trips through `| tojson` filter

All 11 acceptance criteria PASS.

## Requirements Satisfied

- **I18N-05** (`<html lang>` matches content lang on detail pages): `<html lang="{{ article.lang }}" data-fixed-lang="true">` — server-set from article.lang at SSG render time; `data-fixed-lang='true'` is the lang.js opt-out marker (kb-1-04 lang.js logic).
- **I18N-06** (visible content lang badge near article title): `<span class="lang-badge">` inside article header `<div class="article-meta">`, single-emit (not dual-span) per content-marker design.
- **UI-06** (JSON-LD Article schema with inLanguage): `<script type="application/ld+json">{{ json_ld | tojson }}</script>` — render context provides the schema dict; `inLanguage` field carries content lang. Verified via render assert `"inLanguage": "en"` in en-render output.
- **UI-07** (breadcrumb with localized labels): `<nav class="breadcrumb">` with localized `breadcrumb.home` + `breadcrumb.articles` keys + raw article title (content, not chrome).
- **EXPORT-04** (article body emits as pre-rendered HTML): `{{ body_html | safe }}` — template does NOT call markdown.markdown() or pygments; the export driver in kb-1-09 will render markdown → HTML with Pygments codehilite extension and pass the resulting HTML string through as `body_html` in the render context.

## Decisions Made

- **Inline chrome instead of extending base.html.** The PLAN explicitly preferred this approach because `<html lang>` and `data-fixed-lang` attributes diverge from base.html's UI-chrome-lang model. Trade-off: ~80 lines of chrome duplication vs. hacking base.html with `data_fixed_lang` flag conditionals. The Surgical Changes principle prefers duplication over polluting base.html with article-detail-only conditionals. Future templates that need the same axis split (entity pages in v2.1, etc.) can follow this same pattern.
- **Lang badge is single-emit, NOT dual-span.** The badge marks the article's CONTENT language, which is fixed at SSG time. Toggling UI chrome via lang.js never toggles this. Both branches of the `{% if %}` emit the badge text in the zh-CN locale (`'article.lang_zh' | t('zh-CN')` → `'中文'`; `'article.lang_en' | t('zh-CN')` → `'English'`) — works fine because the locale JSONs intentionally cross-pollinate language names so the badge reads correctly regardless of UI chrome lang.

## Deviations from Plan

None — plan executed exactly as written. Article.html content matches the PLAN's exact-content block byte-for-byte. All acceptance criteria passed on first attempt; no Rule 1/2/3 auto-fixes triggered.

## Issues Encountered

**PYTHONPATH not set when running ad-hoc verify scripts.** The PLAN's verify command snippet is a `python -c` one-liner; running it as `python .scratch/kb-1-08-verify.py` from the repo root failed with `ModuleNotFoundError: No module named 'kb'` because pytest's conftest.py / rootdir mechanism wasn't adding cwd to sys.path. Worked around by prefixing `PYTHONPATH=.` to the python invocation. **No code change** — this is a verify-script invocation pattern, not a defect in article.html or kb/i18n.py. Other kb-1-* SUMMARYs that ran similar verify scripts via venv/Scripts/python presumably picked up sys.path from the venv site-packages or used `python -c '...'` inline (which inherits cwd from shell).

## Authentication Gates

None encountered — pure template work, no external API calls.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **kb-1-09 (export driver):** must build the render context for article.html with the documented shape:

  ```python
  context = {
      'lang': article.lang,                       # drives <html lang>
      'article': {                                # nested dict
          'title': str,
          'url_hash': str,
          'lang': str,                            # same as outer lang
          'url': str,
          'source': str,                          # 'wechat' | 'rss'
          'update_time': str,
          'body_source': str,                     # 'vision_enriched' | 'raw_markdown'
      },
      'body_html': str,                           # markdown.markdown + Pygments PRE-rendered
      'og': {
          'title': str, 'description': str, 'image': str,
          'type': 'article', 'locale': str,       # zh_CN or en_US
      },
      'page_url': str,                            # canonical /articles/{hash}.html
      'json_ld': dict,                            # full schema.org Article dict
  }
  ```

  The export driver is responsible for:
  1. Calling `kb.data.article_query.get_article_body(rec)` (kb-1-06) to get the raw markdown + body_source kind
  2. Running `markdown.markdown(body_md, extensions=['fenced_code', 'codehilite', 'tables', 'toc', 'nl2br'])` to produce body_html
  3. Resolving the article's content lang to 'zh-CN' / 'en' / 'unknown' via `articles.lang` / `rss_articles.lang` (DATA-02)
  4. Building the JSON-LD dict including `inLanguage` matching content lang
  5. Computing `og.image` — prefer `/static/img/{hash}/cover.png` if exists, else fallback to `/static/VitaClaw-Logo-v0.png`
  6. Computing `og.locale` — `zh_CN` for `lang='zh-CN'`, `en_US` for `lang='en'`
  7. Computing `page_url = '/articles/' + article.url_hash + '.html'`

- **CSS classes referenced by template (must exist in kb/static/style.css from kb-1-04):** `.nav-wrap`, `.container`, `.nav`, `.nav-brand`, `.nav-links`, `.lang-toggle`, `.breadcrumb`, `.article-body`, `.article-meta`, `.lang-badge`, `.badge-enriched`, `.article-content`, `.article-footer`, `.btn`, `.btn-secondary`, `.footer`. All standard chrome classes; `.lang-badge` and `.breadcrumb` were specifically called out in CONTEXT.md as classes plan kb-1-04 should provide.

- **Caveat for kb-1-09 lang.js interaction:** the `data-fixed-lang="true"` attribute on `<html>` is the contract with lang.js (kb-1-04). The lang.js bootstrap MUST check this attribute before flipping `<html lang>` based on cookie / `?lang=` query — if the attribute is `'true'`, the server-set content lang stays. Worth a render-time grep check in kb-1-09 smoke verification: `grep -l 'data-fixed-lang="true"' kb/output/articles/*.html | wc -l` should equal the article-detail file count.

## Self-Check: PASSED

- `kb/templates/article.html` — FOUND (105 lines)
- Commit `d78acdc` (Task 1) — FOUND in `git log`
- Render under `kb.i18n.t` filter for both `lang='en'` and `lang='zh-CN'` — VERIFIED (en_render_len=3226, zh_render_len=3203)
- All 11 acceptance criteria from PLAN met — VERIFIED via `.scratch/kb-1-08-verify.py`

---
*Phase: kb-1-ssg-export-i18n-foundation*
*Plan: 08*
*Completed: 2026-05-13*
