# Phase kb-1: SSG Export + i18n Foundation — Context

**Gathered:** 2026-05-12
**Status:** Ready for planning
**Source:** PRD Express Path equivalent — synthesized from `PROJECT-KB-v2.md` + `REQUIREMENTS-KB-v2.md` + `ROADMAP-KB-v2.md` + `kb/docs/01..09` (no `/gsd:discuss-phase` round-trip; design fully locked at milestone level).

---

<domain>
## Phase Boundary

**What this phase delivers:** Bilingual SSG output renders from a clean `kol_scan.db`-plus-filesystem data layer. By the end of this phase, running `python kb/export_knowledge_base.py` produces a complete static HTML tree under `kb/output/` covering homepage / article list / per-article detail / Q&A entry pages — every page bilingual-switchable, every article detail page tagged with its own content language, every image URL rewritten, every web-courtesy meta tag in place.

**What is explicitly NOT in this phase:**

- ❌ FastAPI / HTTP API / `/api/*` endpoints — all in **kb-3**
- ❌ FTS5 search (虚表 build, `articles_fts` virtual table) — in **kb-3**
- ❌ Q&A `/synthesize` endpoint, language directive injection — in **kb-3** (I18N-07 lives in kb-3, not here)
- ❌ Caddy / systemd / cron / install.sh / smoke verification — all in **kb-4**
- ❌ Entity pages / topic Pillar pages / canonical_map UI — out of scope this milestone (deferred to v2.1)
- ❌ Content auto-translation — out of scope (v2.2 candidate)

**What this phase consumes (read-only inputs):**

- SQLite `kol_scan.db` — read paths & schema; **DATA-01** adds nullable `lang` column (schema-extending non-breaking per C3)
- `~/.hermes/omonigraph-vault/images/{hash}/final_content.md` + `metadata.json` — D-14 fallback chain
- `kb/docs/03-ARCHITECTURE.md` § Page layouts / Design tokens — UI source-of-truth
- vitaclaw-site reused brand assets (logo `VitaClaw-Logo-v0.png`, `favicon.svg`, dark palette)

</domain>

<decisions>
## Implementation Decisions

### Architecture

- **Stack:** Python 3.11+ / Jinja2 (no Astro / Next.js / SPA framework) — D-08 locked
- **Output target:** `kb/output/` directory (Caddy directly serves; no Python runtime at request time for SSG pages)
- **Idempotent rebuild:** re-running `export_knowledge_base.py` produces byte-identical output for unchanged inputs (EXPORT-01)
- **Read-only data access:** export code MUST NOT write to SQLite or to `~/.hermes/omonigraph-vault/images/` — those are owned by the OmniGraph ingest pipeline (EXPORT-02)
- **Phase numbering:** `kb-N-*` prefix (parallel-track), KB-2 explicitly skipped — directories under `.planning/phases/kb-1-*` / `kb-3-*` / `kb-4-*`

### Bilingual switching strategy (UI chrome)

- **Single HTML file per page contains BOTH languages' chrome strings inline.** No `/en/` URL prefix, no separate `index.en.html` files.
- Strings carry a `data-lang="zh"` / `data-lang="en"` attribute; CSS hides the inactive language; small JS bootstrap (`kb/static/lang.js`, ~30 LOC) reads `kb_lang` cookie or `?lang=` query, sets `<html lang>` accordingly.
- **Why this over two-file approach:** simpler SSG output (one render pass per page), no URL canonical issues, easier to maintain ~50 strings × 2 langs in one place. Cost is ~5-10% larger HTML — acceptable given page sizes <100KB.
- **Default lang detection:** JS reads `navigator.language` + `navigator.languages`, picks `en` if any starts with `en`, else `zh-CN`. Default falls back to `zh-CN`. (I18N-01)
- **`?lang=zh` / `?lang=en` query param** sets cookie, persists 1 year, max-age 31536000, SameSite=Lax. Cookie name: `kb_lang`. (I18N-02)

### Content language vs UI language (two axes)

- **Content language** (per-article, fixed): determined by `articles.lang` / `rss_articles.lang` column (populated by DATA-02 detection script). Sets `<html lang>` on article detail pages (I18N-05) + drives the badge (I18N-06).
- **UI chrome language** (per-user, switchable): determined by cookie / query / Accept-Language. Independent of content language. Switching UI chrome does NOT change `<html lang>` on detail pages.
- These two axes are intentionally different — a Chinese-UI user can read an English article (UI chrome shows in 中文, article body shows in English with badge "English").
- Article LIST pages: `<html lang>` matches UI chrome (the list itself is chrome content).

### Lang detection algorithm (DATA-02)

- **Threshold:** Chinese char ratio > 30% → `zh-CN`, else `en`
- **Char counter:** CJK Unified Ideographs range — `'一' <= c <= '鿿'` (covers 99% of Chinese articles in this corpus). Alternative `unicodedata.east_asian_width` rejected — needs unicodedata import + slower.
- **Input source:** `body` column for both `articles` and `rss_articles`. Title alone insufficient (RSS feeds often have English titles for Chinese-body articles or vice versa).
- **Output:** Update `lang` column in-place; print stdout `{zh-CN: N, en: M, unknown: K}` coverage report.
- **Idempotent:** `WHERE lang IS NULL` filter — re-running only updates new rows.
- **Edge case:** `LENGTH(body) < 200` rows → `lang = 'unknown'` (insufficient sample).

### content_hash URL resolution (DATA-06)

3-branch decision tree implemented as single function `resolve_url_hash(article_record) -> str`:

```python
def resolve_url_hash(rec) -> str:
    if rec.source == "wechat":
        if rec.content_hash:        # KOL with content_hash (rare, 0.6%)
            return rec.content_hash  # already 10 chars
        return md5(rec.body.encode()).hexdigest()[:10]  # runtime fallback
    elif rec.source == "rss":
        return rec.content_hash[:10]  # truncate full md5 to 10 chars
    raise ValueError(f"unknown source: {rec.source}")
```

**No DB writes** — purely runtime computation (K-2 locked).

**Stability concern:** if `articles.body` mutates after ingest, the runtime md5 changes → URL drift. Mitigation: `kb/output/_url_index.json` records `(article_id, hash)` mapping; on conflict (existing article_id with different new hash) → log WARN + keep old hash. Implementation detail — not in REQ but in plan.

### Article body source resolution (D-14, EXPORT-04)

Single function `get_article_body(article_hash, article_id) -> tuple[str, str]`:

```python
IMAGES_DIR = config.KB_IMAGES_DIR  # ~/.hermes/omonigraph-vault/images/

def get_article_body(article_hash, article_id):
    for fname in ("final_content.enriched.md", "final_content.md"):
        p = IMAGES_DIR / article_hash / fname
        if p.exists():
            md = p.read_text(encoding="utf-8")
            md = re.sub(r'http://localhost:8765/', '/static/img/', md)
            return md, "vision_enriched"
    body = db.execute("SELECT body FROM articles WHERE id=?", [article_id]).fetchone()
    if not body or not body[0]:
        body = db.execute("SELECT body FROM rss_articles WHERE id=?", [article_id]).fetchone()
    return (body[0] if body else ""), "raw_markdown"
```

Returns `(body_md, source_kind)` where `source_kind ∈ {"vision_enriched", "raw_markdown"}`. UI uses `source_kind` to show indicator if needed.

### Markdown rendering

- **Library:** `markdown` (PyPI) — pin `markdown>=3.5` per PROJECT-KB-v2.md tech stack
- **Extensions:** `fenced_code` + `codehilite` (Pygments) + `tables` + `toc` + `nl2br`
- **Pygments theme:** **Monokai** (matches dark theme); style def rendered into `kb/static/style.css` at build time via `pygments.formatters.HtmlFormatter(style='monokai').get_style_defs('.codehilite')`

### i18n filter implementation (I18N-03)

- **Custom Jinja2 filter `t(key, lang='zh-CN')`** — NOT Babel, NOT gettext, NOT `flask-babel`
- Loads `kb/locale/zh-CN.json` + `kb/locale/en.json` at module import; flat dict with dot-notation keys
- Templates use `{{ t('nav.home') }}` (defaults to current chrome lang via Jinja2 context); for explicit lang use `{{ t('nav.home', 'en') }}`
- **Both languages emitted in HTML output** — `<span data-lang="zh">{{ t('nav.home', 'zh') }}</span><span data-lang="en">{{ t('nav.home', 'en') }}</span>`. JS toggles visibility.
- **Missing key behavior:** return `key` literal + log WARN (so missing translations are visible in UI for fast debugging)

### i18n string namespace

- Dot-notation: `nav.home` / `nav.articles` / `nav.ask` / `article.read_more` / `article.source_label` / `footer.copyright` / `lang.switch_to_en` / `lang.switch_to_zh` / etc.
- ~50 keys total (estimate)
- Both `zh-CN.json` and `en.json` MUST have identical key sets (build-time check)

### Page set (EXPORT-03)

- `kb/output/index.html` — homepage with latest articles (limit 20 by `update_time DESC`) + Q&A entry CTA + brand intro
- `kb/output/articles/index.html` — article list with filter UI (source / lang via JS-side filtering of pre-rendered cards, NO server filtering at SSG time — that's kb-3 API job)
- `kb/output/articles/{hash}.html` — per-article detail, ~290+ files expected (after DATA-02 detect populates lang on all qualifying rows)
- `kb/output/ask/index.html` — Q&A entry placeholder (form posts to `/api/synthesize` later, kb-3 wires)
- `kb/output/sitemap.xml` — all article URLs + 3 index pages
- `kb/output/robots.txt` — `User-agent: *`, `Sitemap: /sitemap.xml`
- `kb/output/static/style.css` — single CSS file, Pygments style + design tokens + responsive layout
- `kb/output/static/lang.js` — ~30 LOC JS bootstrap

### Web courtesy meta tags (UI-05, UI-06)

Every page emits in `<head>`:

```html
<meta property="og:title" content="...">
<meta property="og:description" content="...">
<meta property="og:image" content="...">
<meta property="og:type" content="website|article">
<meta property="og:locale" content="zh_CN|en_US">  <!-- matches <html lang> -->
```

Article detail pages additionally emit:

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "...",
  "datePublished": "...",
  "inLanguage": "zh-CN|en",  // matches content language
  "author": {"@type": "Organization", "name": "VitaClaw"},
  "image": "..."
}
</script>
```

**Stated explicitly: this is web courtesy baseline, NOT SEO push.** No 百度推送 API, no keyword stuffing, no `<priority>` in sitemap.

### Design tokens (UI-01, UI-02)

Single `kb/static/style.css` defines CSS variables:

```css
:root {
  --bg: #0f172a;
  --bg-card: #1e293b;
  --text: #f0f4f8;
  --text-secondary: #94a3b8;
  --accent: #3b82f6;
  --accent-green: #22d3a0;
  --border: rgba(255, 255, 255, 0.1);
  --font-sans: 'Inter', 'Noto Sans SC', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
}
```

**No external font loading on first paint** — relies on system Inter / Noto Sans SC fallback chain. Web fonts can be added in v2.1 if needed.

### Responsive breakpoints (UI-03)

- Mobile: 320-767px (single column, hamburger nav)
- Tablet: 768-1023px (two columns where useful)
- Desktop: 1024px+ (sidebar layouts on detail pages)
- Use CSS `@media (min-width: ...)` mobile-first
- No horizontal scroll on any breakpoint

### Brand asset strategy (UI-04)

- Reuse vitaclaw-site assets — copy `VitaClaw-Logo-v0.png` to `kb/static/` and `favicon.svg` to `kb/static/` at build time (or symlink if same-host)
- No new design files in this milestone
- Brand name: "企小勤" main, "VitaClaw" English aux per kb/docs/09 V-3 decision

### Configuration (CONFIG-01)

`kb/config.py` reads env with defaults:

| Env var | Default | Purpose |
|---|---|---|
| `KB_DB_PATH` | `~/.hermes/data/kol_scan.db` | SQLite path |
| `KB_IMAGES_DIR` | `~/.hermes/omonigraph-vault/images` | filesystem images base |
| `KB_OUTPUT_DIR` | `kb/output` | SSG target |
| `KB_PORT` | `8766` | (for kb-3, not used in kb-1 but exported) |
| `KB_DEFAULT_LANG` | `zh-CN` | fallback when no Accept-Language match |
| `KB_SYNTHESIZE_TIMEOUT` | `60` | (for kb-3, exported here) |

**No path hardcoded outside `kb/config.py`.** Verification: `grep -rE "/.hermes|kol_scan.db" kb/ --include='*.py' --exclude=config.py` should return only the config.py defaults.

### Module / file layout

```
kb/
├── __init__.py
├── config.py                  # CONFIG-01 — env-driven paths/ports
├── data/
│   ├── __init__.py
│   ├── article_query.py       # DATA-04, DATA-05, DATA-06
│   └── lang_detect.py         # DATA-02 (helper, also used by detect script)
├── scripts/
│   ├── migrate_lang_column.py # DATA-01
│   └── detect_article_lang.py # DATA-02, DATA-03
├── locale/
│   ├── zh-CN.json
│   └── en.json
├── templates/                  # Jinja2
│   ├── base.html
│   ├── index.html
│   ├── article.html
│   ├── articles_index.html
│   └── ask.html
├── static/
│   ├── style.css
│   ├── lang.js
│   ├── VitaClaw-Logo-v0.png   # copied from vitaclaw-site
│   └── favicon.svg            # copied from vitaclaw-site
├── output/                     # SSG build output (gitignored)
│   └── ...
└── export_knowledge_base.py   # EXPORT-01..06 — single CLI entry
```

### Claude's Discretion (not specified by REQs)

These are implementation decisions the planner / executor can make freely as long as they don't conflict with above:

- **Article ordering on homepage / list:** `update_time DESC` then `id DESC` for ties — already implied by DATA-04 sort order
- **Article card layout in list:** flexible — title + 1-line snippet + lang badge + source + date is the minimum
- **JS bundling / minification:** none for v2.0 (~30 LOC, not worth it); v2.1 can add esbuild
- **CSS preprocessor:** none — vanilla CSS with custom properties is sufficient
- **Image lazy loading:** `loading="lazy"` attribute on `<img>` tags is free, do it
- **Build CLI args:** at least `--output-dir`, `--db-path` to override config; `--limit N` for dev mode partial builds
- **Print logging vs structured logging:** print is fine; export script is a one-shot CLI

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone-level scope (read all)

- `.planning/PROJECT-KB-v2.md` — milestone scope, locked architectural choices, smoke tests, contracts C1-C4, file pattern (parallel-track suffix), out-of-scope list
- `.planning/REQUIREMENTS-KB-v2.md` — 50 REQs across 9 categories, future v2.1+ candidates, traceability table
- `.planning/ROADMAP-KB-v2.md` — kb-1 / kb-3 / kb-4 phase decomposition, 27 REQs mapped to kb-1, success criteria, T-shirt sizes, cross-phase touches table

### Original design docs (vitaclaw-side authored, then OmniGraph-internalized)

- `kb/docs/01-PRD.md` — original PRD; **§4 SEO 章节作废** (project goal pivot — see PROJECT-KB-v2.md "Goal"); §3 architecture and §5 UX still authoritative; SEO-* / PAGE-* / LINK-* REQs in §8 superseded by REQUIREMENTS-KB-v2.md
- `kb/docs/02-DECISIONS.md` — D-01 ~ D-20, all locked; phase planner does NOT re-discuss
- `kb/docs/03-ARCHITECTURE.md` — page layouts, data flow diagrams, design tokens, breadcrumb / sidebar / CTA structure; **primary reference for UI implementation**
- `kb/docs/04-KB1-EXPORT-SSG.md` — original execution sketch; superseded by ROADMAP-KB-v2.md kb-1 section but useful for cross-reference
- `kb/docs/09-AGENT-QA-HANDBOOK.md` — vitaclaw decision回执 (V-1..V-6, K-1..K-5, R-1..R-5)

### Code references (for read_first when planning concrete tasks)

- `config.py` — main project config; pattern to mirror in `kb/config.py` (env-driven with defaults)
- `kg_synthesize.py` — contract C1 holder (NOT touched in kb-1, but in kb-3); referenced for understanding the system
- `omnigraph_search/query.py` — contract C2 holder
- `lib/llm_complete.py` — contract C2's downstream; provides `get_llm_func()` abstraction (kb-1 doesn't touch, kb-3 does)
- `image_pipeline.py` § `save_markdown_with_images()` — `final_content.md` write semantics (path/format kb-1 reads from)
- `enrichment/rss_schema.py` § `_ensure_rss_columns` — pattern for idempotent SQLite migrations (DATA-01 should mirror this `PRAGMA table_info` pre-check style)

### vitaclaw-site brand assets (to copy at build time)

- (location TBD — vitaclaw-site is a sibling repo; copy or symlink at install/build time):
  - `VitaClaw-Logo-v0.png` → `kb/static/VitaClaw-Logo-v0.png`
  - `favicon.svg` → `kb/static/favicon.svg`
- Brand color tokens already documented in `kb/docs/03-ARCHITECTURE.md`

</canonical_refs>

<specifics>
## Specific Ideas

### REQ → file mapping (planner reference)

| REQ | Primary file(s) | Tests/verification |
|---|---|---|
| I18N-01 | `kb/static/lang.js` | manual: open page in browser with `Accept-Language: en` → UI shows English |
| I18N-02 | `kb/static/lang.js` | manual: `?lang=en` then reload, cookie persists |
| I18N-03 | `kb/locale/*.json` + Jinja2 filter | `kb/templates/base.html` uses `{{ t('nav.home') }}` |
| I18N-04 | (kb-1 SSG side) `kb/templates/articles_index.html` JS filter; (kb-3) `/api/articles?lang=` | manual: filter shows English-only / Chinese-only |
| I18N-05 | `kb/templates/article.html` | grep `<html lang="{{ article.lang }}">` |
| I18N-06 | `kb/templates/article.html` | grep visible `<span class="lang-badge">{{ article.lang_label }}</span>` |
| I18N-08 | `kb/templates/base.html` nav | `class="lang-toggle"` element present |
| DATA-01 | `kb/scripts/migrate_lang_column.py` | run twice → second is no-op; `PRAGMA table_info(articles)` shows `lang TEXT` |
| DATA-02 | `kb/data/lang_detect.py` + `kb/scripts/detect_article_lang.py` | run on dev DB → coverage report shows zh-CN / en counts |
| DATA-03 | `kb/scripts/detect_article_lang.py` `WHERE lang IS NULL` clause | re-run after first run → 0 updates |
| DATA-04 | `kb/data/article_query.py::list_articles` | unit test: filters work, sort is `update_time DESC` |
| DATA-05 | `kb/data/article_query.py::get_article_by_hash` | unit test: KOL hash + RSS hash + missing hash 都 ok |
| DATA-06 | `kb/data/article_query.py::resolve_url_hash` | unit test: 3 branches each pass |
| EXPORT-01 | `kb/export_knowledge_base.py` | run twice → second produces byte-identical output (sha256 check) |
| EXPORT-02 | code review: grep `INSERT\|UPDATE\|DELETE\|.write\|os.remove` in `kb/export*.py` → 0 hits against DB/images |
| EXPORT-03 | `kb/export_knowledge_base.py` | `ls kb/output/articles/*.html | wc -l` ≥ 290 (or whatever local DB count is) |
| EXPORT-04 | `kb/export_knowledge_base.py::get_article_body` | manual: detail page renders with code highlighting |
| EXPORT-05 | regex rewrite in `get_article_body` | grep `localhost:8765` in any `kb/output/articles/*.html` → 0 hits |
| EXPORT-06 | `kb/export_knowledge_base.py` final step | `kb/output/sitemap.xml` exists, valid XML, lists all articles + index |
| UI-01 | `kb/static/style.css` | grep `--bg: #0f172a` |
| UI-02 | `kb/static/style.css` | grep `font-family.*Inter.*Noto Sans SC` |
| UI-03 | manual viewport test | mobile / tablet / desktop no horizontal scroll |
| UI-04 | `kb/static/VitaClaw-Logo-v0.png` + `kb/static/favicon.svg` | files exist post-build |
| UI-05 | `kb/templates/base.html` `<head>` block | grep `og:title\|og:description\|og:image\|og:type\|og:locale` |
| UI-06 | `kb/templates/article.html` | grep `application/ld+json` + `inLanguage` |
| UI-07 | `kb/templates/article.html` | grep `breadcrumb` + i18n labels |
| CONFIG-01 | `kb/config.py` | unit test: env override works for all 6 keys; defaults match docs |

### Estimated LOC budget per file (rough)

```
kb/config.py                       ~50 LOC
kb/data/article_query.py          ~150 LOC (3 functions, dataclass, query SQL)
kb/data/lang_detect.py             ~30 LOC (single function)
kb/scripts/migrate_lang_column.py  ~50 LOC
kb/scripts/detect_article_lang.py  ~80 LOC
kb/locale/zh-CN.json               ~50 string keys (data, not LOC)
kb/locale/en.json                  ~50 string keys
kb/templates/base.html            ~150 LOC (Jinja2 + chrome HTML)
kb/templates/index.html            ~80 LOC
kb/templates/article.html         ~120 LOC
kb/templates/articles_index.html  ~100 LOC (filter JS inline)
kb/templates/ask.html              ~50 LOC (placeholder)
kb/static/style.css               ~400 LOC (tokens + responsive + Pygments)
kb/static/lang.js                  ~30 LOC
kb/export_knowledge_base.py       ~250 LOC (main entry, all rendering)
─────────────────────────────────────────
Total (rough)                    ~1500-1800 LOC
```

### Output verification at end of phase

`kb/output/` after a clean export should contain:

```
kb/output/
├── index.html
├── robots.txt
├── sitemap.xml
├── _url_index.json          # internal: hash → article_id mapping (gitignored)
├── articles/
│   ├── index.html
│   ├── {hash1}.html
│   ├── {hash2}.html
│   └── ... (~290 files)
├── ask/
│   └── index.html
└── static/
    ├── style.css
    ├── lang.js
    ├── VitaClaw-Logo-v0.png
    └── favicon.svg
```

`python -m http.server 8080 --directory kb/output/` should let user browse the full site for visual verification before kb-3 lands HTTP backend.

</specifics>

<deferred>
## Deferred Ideas

These are mentioned in REQ-related context but **delivered in later phases** — kb-1 should NOT include their implementation.

| Item | Where delivered | Why mentioned here |
|---|---|---|
| `/api/articles?lang=` query API | kb-3 (API-02) | I18N-04 spans both phases — kb-1 does the SSG-side filter UI (JS-only); kb-3 adds server-side filter |
| `/api/article/{hash}` endpoint | kb-3 (API-03) | DATA-04 / DATA-05 / DATA-06 functions are first-delivered here, kb-3 imports them |
| FTS5 trigram virtual table | kb-3 (SEARCH-01) | not needed for SSG; kb-3 builds index for HTTP search |
| `/api/synthesize` Q&A endpoint | kb-3 (API-06, QA-01..05) | I18N-07 lives there |
| FastAPI `/static/img` mount | kb-3 (API-08) | kb-1 only emits markdown with `/static/img/` path; the mount itself is HTTP-time |
| systemd / Caddy / cron | kb-4 | no deploy in kb-1 |
| Smoke verification | kb-4 (DEPLOY-04) | kb-1 unit/integration tests only; full smoke at kb-4 |
| KB-2 entity / topic Pillar pages | v2.1 milestone | explicitly out of scope this milestone |

</deferred>

---

*Phase: kb-1-ssg-export-i18n-foundation*
*Context gathered: 2026-05-12 via PRD Express Path equivalent (synthesized from existing artifacts; no /gsd:discuss-phase round-trip)*
