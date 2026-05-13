---
phase: kb-1-ssg-export-i18n-foundation
verified: 2026-05-13T13:00:00Z
status: gaps_found
score: 6/8 must-haves verified

# REQ IDs that are now satisfied with codebase evidence
# (orchestrator should manually edit REQUIREMENTS-KB-v2.md traceability table for these)
requirements_satisfied:
  - I18N-01      # kb/static/lang.js Accept-Language detect + zh-CN fallback (kb-1-04)
  - I18N-02      # ?lang= query + kb_lang cookie 1y SameSite=Lax (kb-1-04)
  - I18N-03      # kb.i18n.t() Jinja2 filter + 45-key locale parity (kb-1-03)
  - I18N-05      # article.html sets <html lang> from article.lang (kb-1-08)
  - I18N-06      # article.html lang badge zh/en single-emit (kb-1-08)
  - I18N-08      # base.html .lang-toggle nav element (kb-1-04 + kb-1-07)
  - DATA-01      # kb/scripts/migrate_lang_column.py idempotent ALTER (kb-1-02)
  - DATA-02      # kb/data/lang_detect.py pure-fn CJK ratio detector (kb-1-02)
  - DATA-03      # detect_article_lang.py WHERE lang IS NULL idempotent (kb-1-05)
  - DATA-04      # article_query.list_articles signature matches spec (kb-1-06) — runtime broken; see gap 1
  - DATA-05      # article_query.get_article_by_hash 3-tier resolution (kb-1-06)
  - DATA-06      # article_query.resolve_url_hash 3-branch pure (kb-1-06)
  - EXPORT-02    # grep-clean: zero INSERT/UPDATE/DELETE/unlink/rmtree in export_knowledge_base.py
  - EXPORT-04    # markdown lib + codehilite extensions wired in MD_EXTENSIONS (kb-1-09)
  - EXPORT-05    # localhost:8765 -> /static/img/ regex rewrite in get_article_body (kb-1-06) + integration test 3 PASS
  - EXPORT-06    # render_sitemap + render_robots in export driver; verified by integration test 1
  - UI-01        # kb/static/style.css design tokens --bg #0f172a etc. (kb-1-04)
  - UI-02        # font-family Inter + Noto Sans SC chain (kb-1-04)
  - UI-03        # mobile-first @media (min-width: 768px / 1024px) (kb-1-04)
  - UI-04        # PARTIAL — favicon.svg placeholder + Logo .MISSING.txt stub; user accepted via approved-placeholder (kb-1-04b). Real PNG is kb-4 prerequisite.
  - UI-05        # base.html og:* meta in <head> (kb-1-07)
  - UI-06        # article.html <script type="application/ld+json"> with inLanguage (kb-1-08)
  - UI-07        # article.html breadcrumb with i18n-localized labels (kb-1-08)
  - CONFIG-01    # kb/config.py 6 env-driven constants; CONFIG-01 grep clean (kb-1-01)

# REQ IDs explicitly NOT yet satisfied at codebase level (blocked by gaps below)
requirements_blocked:
  - EXPORT-01    # Idempotency tested with TEXT-only update_time fixture; cannot run against production DB due to data-shape bug
  - EXPORT-03    # index/articles/{hash}/ask page generation cannot complete on production DB until update_time mixed-type bug fixed
  - I18N-04      # SSG-side filter UI exists in articles_index.html, but full rendered list cannot be generated against production DB

gaps:
  - truth: "Running `python kb/export_knowledge_base.py` against the real `kol_scan.db` produces a complete `kb/output/` tree (ROADMAP Success Criterion #2)"
    status: failed
    reason: "Data-shape bug: production `articles.update_time` is INTEGER (Unix epoch); `rss_articles.published_at`/`fetched_at` are TEXT ISO strings. `_row_to_record_kol` and `_row_to_record_rss` assign raw values into `ArticleRecord.update_time` (typed as `str` but not enforced at runtime). `list_articles` line 165 sorts the merged list by `update_time`, raising `TypeError: '<' not supported between instances of 'int' and 'str'`. The export driver cannot run end-to-end against the actual production schema. Reproduced 2026-05-13 against `.dev-runtime/data/kol_scan.db` (KOL update_time samples: 1777249680, 1776990480, ...; RSS published_at samples: '2026-05-02T17:26:40+00:00', ...). The bug was masked because the integration test fixture at `tests/integration/kb/test_export.py:73` declares `update_time TEXT` (uniform string type) — which does not match production schema."
    artifacts:
      - path: "kb/data/article_query.py"
        issue: "_row_to_record_kol line 95 passes raw `row['update_time']` (INTEGER from production schema) into ArticleRecord.update_time without normalizing to ISO string. _row_to_record_rss line 102 passes TEXT. list_articles line 165 then sorts mixed types -> TypeError."
      - path: "tests/integration/kb/test_export.py"
        issue: "Fixture schema at line 73 declares `update_time TEXT` instead of mirroring the actual production `articles.update_time INTEGER`. Test passed because fixture types were uniform; production types are not."
    missing:
      - "Normalize KOL `update_time` from Unix epoch (int) to ISO-8601 date string (text) at the row-mapper boundary (`_row_to_record_kol`). Suggested form: `datetime.fromtimestamp(row['update_time'], tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')` if non-None, else empty string."
      - "Update integration test fixture to declare `articles.update_time INTEGER` (matching production schema), insert epoch ints, and assert the rendered detail HTML / sitemap lastmod use the formatted date (catches future regressions of the same shape)."
      - "Re-run `python kb/export_knowledge_base.py --limit 5` against `.dev-runtime/data/kol_scan.db` after the fix and capture the produced `kb/output/articles/*.html` count + `sitemap.xml` <lastmod> values."

  - truth: "ROADMAP Success Criterion #1: `kb/scripts/detect_article_lang.py` runs on the live `kol_scan.db` and reports `articles.lang` + `rss_articles.lang` 100% non-NULL afterward; re-running is a no-op (idempotent) (DATA-01..03)"
    status: partial
    reason: "Code is correct (idempotent migration + idempotent WHERE lang IS NULL + 7/7 unit tests pass), but neither migration nor detect was actually run against the dev/production DB at phase-completion time. Verified during this verification run: at start, `articles.lang` 100% NULL (653 rows) and `rss_articles.lang` 100% NULL (1600 rows). After running `KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe -m kb.scripts.migrate_lang_column` then `... -m kb.scripts.detect_article_lang`, columns are 100% non-NULL: KOL {unknown: 457, en: 121, zh-CN: 75}; RSS {unknown: 1203, en: 397}. Note: high `unknown` count is expected per DATA-02 spec (rows with body length < 200 chars). The Success Criterion #1 outcome is reachable; the operational step was never performed."
    artifacts:
      - path: "kb/scripts/migrate_lang_column.py"
        issue: "Code correct, but never executed against the dev/production DB before this verification."
      - path: "kb/scripts/detect_article_lang.py"
        issue: "Code correct, but never executed against the dev/production DB before this verification."
    missing:
      - "Operational: document in kb-4 daily_rebuild.sh (or a kb-1 follow-up note) that DB-state preconditions for kb-1 success criterion #1 are met by running migrate_lang_column + detect_article_lang once at deploy time / once at first cron run. (Idempotency means re-runs are safe.)"
      - "Optional: add a startup self-check in `kb/export_knowledge_base.py` that runs `_ensure_lang_column` (mirror of detect_article_lang's pre-flight) and exits with a clear error message if the columns are absent — defensive, since the export driver hard-depends on `articles.lang`."

human_verification:
  - test: "Open a generated article detail HTML in a browser; verify <html lang>, lang badge, breadcrumb, og:* meta, JSON-LD all render correctly"
    expected: "Per ROADMAP Success Criterion #3 — visible '中文' / 'English' badge, correct breadcrumb labels, code highlighting, no broken images"
    why_human: "Visual rendering — only verifiable by opening generated HTML in a real browser. BLOCKED until gap 1 (update_time mixed type) is fixed and a real export run produces output."
  - test: "Load any generated page with `?lang=en`, verify all UI chrome strings switch to English; reload without param, verify English persists via `kb_lang` cookie"
    expected: "Per ROADMAP Success Criterion #4 — all chrome strings (nav, footer, page titles, etc.) toggle correctly; cookie persists 1 year per kb-1-04 spec"
    why_human: "Browser-side JavaScript behavior + cookie persistence — not verifiable from the CLI alone. BLOCKED until gap 1 is fixed."
  - test: "Open generated index/articles list/article detail/Q&A pages on mobile (320-767px), tablet (768-1023px), desktop (1024px+) viewports; verify no horizontal scroll"
    expected: "Per ROADMAP Success Criterion #6 — UI-03 responsive across breakpoints"
    why_human: "Visual viewport testing requires a real browser at multiple viewport sizes."
  - test: "Verify `kb/output/static/VitaClaw-Logo-v0.png` is present (replace .MISSING.txt stub) before kb-4 public deploy"
    expected: "Per kb-1-04b SUMMARY 'User Setup Required' — real PNG copied from vitaclaw-site sibling repo"
    why_human: "Operator action — sourcing the asset from a sibling repo not present on this Windows dev box. Currently flagged graceful-degraded via base.html `onerror=\"this.style.display='none'\"`. UI-04 considered satisfied for kb-1 milestone scope per `approved-placeholder` resume signal; carry-forward gate to kb-4."
---

# Phase kb-1: SSG Export + i18n Foundation Verification Report

**Phase Goal:** Build SSG export driver + bilingual i18n foundation that produces a complete static HTML site from `kol_scan.db`.

**Verified:** 2026-05-13T13:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| #   | Truth                                                                                                                                                                                                                                                                            | Status     | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `kb/scripts/detect_article_lang.py` runs on the live `kol_scan.db`; `articles.lang` + `rss_articles.lang` 100% non-NULL after; re-runs idempotent (DATA-01..03)                                                                                                                  | ⚠️ PARTIAL | Code correct + 7/7 unit tests pass + driver is auto-migrating. NOT actually run against dev DB at phase-completion time — verified during this verification run that pre-state was 100% NULL (2253 rows). After running, KOL {unknown: 457, en: 121, zh-CN: 75}; RSS {unknown: 1203, en: 397}. Operational step missing.                                                                                                                                                                |
| 2   | `python kb/export_knowledge_base.py` produces `kb/output/index.html`, `kb/output/articles/{hash}.html` for every passable KOL + RSS row, and `kb/output/ask/index.html` (EXPORT-01..03)                                                                                          | ✗ FAILED   | `--help` succeeds. 6/6 integration tests pass against TEXT-only test fixture. **Real-DB run FAILS**: `KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe kb/export_knowledge_base.py --limit 3` raises `TypeError: '<' not supported between instances of 'int' and 'str'` at `kb/data/article_query.py:165` because `articles.update_time` is INTEGER and `rss_articles.published_at` is TEXT.                                                                          |
| 3   | Article detail HTML shows correct `<html lang>`, content-language badge, rendered markdown body with codehilite, `localhost:8765/` rewritten to `/static/img/`, breadcrumb with localized labels (I18N-05/06, EXPORT-04/05, UI-07)                                               | ? UNCERTAIN | Templates verified at code level (`kb/templates/article.html` — 105 lines with all required elements per integration test 5). Cannot confirm in-browser without a successful real-DB export. Integration test 3 confirmed `localhost:8765 → /static/img/` rewrite at fixture-data level.                                                                                                                                                                                              |
| 4   | `?lang=en` switches UI chrome to English; `kb_lang` cookie persists; `Accept-Language` detection produces zh-CN fallback; article list `?lang=en` filters to English articles (I18N-01/02/04/08)                                                                                | ? UNCERTAIN | `kb/static/lang.js` (104 LOC ES5 IIFE) implements 4-tier resolution per kb-1-04 SUMMARY. Cannot confirm browser behavior without successful real-DB export. Code-level grep confirms `?lang=` parsing + `kb_lang` cookie set/read.                                                                                                                                                                                                                                                     |
| 5   | `kb/output/sitemap.xml` lists every article URL + homepage with `<lastmod>`; `robots.txt` allows all + `Sitemap:`; article detail pages carry `og:title/description/image/type/locale` + JSON-LD `Article` with `inLanguage` (EXPORT-06, UI-05/06)                              | ? UNCERTAIN | `render_sitemap` + `render_robots` in export driver use deterministic input-derived `<lastmod>`. Integration test 1 confirms 6 `<url>` blocks (3 index + 3 article fixtures), `User-agent: *`, `Sitemap: /sitemap.xml`. og + JSON-LD verified by integration test 5. Cannot confirm against real DB until gap 1 is fixed.                                                                                                                                                              |
| 6   | Mobile/desktop viewports render without horizontal scroll; design tokens + font stack load from single `kb/static/style.css`; logo + favicon present (UI-01/02/03/04)                                                                                                            | ? UNCERTAIN | `kb/static/style.css` (587 lines) verified to contain `--bg: #0f172a` design token + `font-family: 'Inter', 'Noto Sans SC', system-ui` + `@media (min-width: 768px/1024px)` mobile-first responsive. UI-04 placeholder accepted via `approved-placeholder` resume signal. Browser visual confirmation deferred to human verification.                                                                                                                                                  |
| 7   | `kb/data/article_query.list_articles(lang, source, limit, offset)` returns paginated `ArticleRecord` lists sorted by `update_time DESC` (DATA-04); `get_article_by_hash` resolves md5[:10] across both KOL and RSS (DATA-05); content_hash 3-branch resolution (DATA-06)         | ⚠️ PARTIAL | All 5 public exports importable: `from kb.data.article_query import ArticleRecord, list_articles, get_article_by_hash, resolve_url_hash, get_article_body` succeeds. 24/24 unit tests pass. **Runtime gap**: `list_articles` against production DB raises TypeError due to update_time mixed-type bug (gap 1).                                                                                                                                                                       |
| 8   | `kb/config.py` reads `KB_DB_PATH`, `KB_IMAGES_DIR`, `KB_OUTPUT_DIR`, `KB_PORT`, `KB_DEFAULT_LANG`, `KB_SYNTHESIZE_TIMEOUT` from env with documented defaults; no path hardcoded outside config.py (CONFIG-01)                                                                    | ✓ VERIFIED | `kb/config.py` ships 6 env-driven constants; 8/8 unit tests pass; CONFIG-01 enforcement grep `grep -rE "/.hermes\|kol_scan\.db" kb/ --include='*.py' --exclude=config.py` returns 0 hits per kb-1-01 SUMMARY.                                                                                                                                                                                                                                                                          |

**Score:** 1/8 truths fully VERIFIED, 2/8 PARTIAL, 4/8 UNCERTAIN (blocked by gap 1), 1/8 FAILED.

If gap 1 is fixed and the export run succeeds, truths 3-6 become VERIFIED automatically and truths 2 + 7 also flip to VERIFIED. Net post-fix score: 7/8 truths VERIFIED + 1/8 PARTIAL (truth 1 — operational step still owed).

### Required Artifacts

| Artifact                                       | Expected                                                          | Status     | Details                                                                       |
| ---------------------------------------------- | ----------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------- |
| `kb/__init__.py`                               | namespace package                                                 | ✓ VERIFIED | exists                                                                        |
| `kb/config.py`                                 | env-driven constants                                              | ✓ VERIFIED | 6 constants + 8 unit tests pass                                               |
| `kb/data/__init__.py`                          | data subpackage                                                   | ✓ VERIFIED | exists                                                                        |
| `kb/data/article_query.py`                     | 5 public exports + ArticleRecord                                  | ⚠️ PARTIAL | 252 LOC, 5 exports importable, 24 unit tests pass; runtime broken on real DB  |
| `kb/data/lang_detect.py`                       | pure-fn CJK ratio detector                                        | ✓ VERIFIED | 47 LOC, 12 unit tests pass                                                    |
| `kb/scripts/migrate_lang_column.py`            | idempotent ALTER for both tables                                  | ✓ VERIFIED | 60 LOC, 6 unit tests pass + idempotent re-run verified during verification    |
| `kb/scripts/detect_article_lang.py`            | CLI driver `WHERE lang IS NULL`                                   | ✓ VERIFIED | 97 LOC, 7 unit tests pass + real-DB run verified during verification          |
| `kb/i18n.py`                                   | `t()` filter + key parity validator                               | ✓ VERIFIED | 95 LOC, 8 unit tests pass                                                     |
| `kb/locale/zh-CN.json`                         | 45 chrome string keys                                             | ✓ VERIFIED | 55 lines (45 keys, identical key set to en.json)                              |
| `kb/locale/en.json`                            | 45 chrome string keys                                             | ✓ VERIFIED | 55 lines, parity with zh-CN.json                                              |
| `kb/templates/base.html`                       | Jinja2 chrome layout                                              | ✓ VERIFIED | 53 LOC, 5 named blocks                                                        |
| `kb/templates/index.html`                      | homepage                                                          | ✓ VERIFIED | 47 LOC                                                                        |
| `kb/templates/articles_index.html`             | article list                                                      | ✓ VERIFIED | 76 LOC                                                                        |
| `kb/templates/article.html`                    | article detail with content-lang axis                             | ✓ VERIFIED | 105 LOC                                                                       |
| `kb/templates/ask.html`                        | Q&A entry placeholder                                             | ✓ VERIFIED | 39 LOC                                                                        |
| `kb/static/style.css`                          | design tokens + responsive + Pygments inline                      | ✓ VERIFIED | 587 LOC                                                                       |
| `kb/static/lang.js`                            | ES5 IIFE 4-tier resolution                                        | ✓ VERIFIED | 104 LOC                                                                       |
| `kb/static/favicon.svg`                        | favicon                                                           | ✓ VERIFIED | 305 B placeholder per kb-1-04b user-approved resume signal                    |
| `kb/static/VitaClaw-Logo-v0.png`               | logo PNG                                                          | ⚠️ PLACEHOLDER | `.MISSING.txt` stub (vitaclaw-site sibling repo absent locally); `<img onerror>` graceful-degrade per kb-1-04b. Hard kb-4 prerequisite. |
| `kb/export_knowledge_base.py`                  | single CLI entry point                                            | ⚠️ PARTIAL | 360 LOC, all expected wiring (config + i18n + article_query + markdown + Jinja2). `--help` succeeds. End-to-end run against real DB FAILS at gap 1 (update_time mixed type). |

### Key Link Verification

| From                          | To                              | Via                                                                                  | Status     | Details                                                                  |
| ----------------------------- | ------------------------------- | ------------------------------------------------------------------------------------ | ---------- | ------------------------------------------------------------------------ |
| export_knowledge_base.py      | kb.data.article_query           | `from kb.data.article_query import ArticleRecord, get_article_body, list_articles, resolve_url_hash` | ✓ WIRED    | grep line 50, 5 exports imported                                          |
| export_knowledge_base.py      | kb.i18n                         | `from kb.i18n import register_jinja2_filter, validate_key_parity`                    | ✓ WIRED    | grep line 56, register called at `_build_env`                             |
| export_knowledge_base.py      | markdown library + Pygments     | `markdown.Markdown(extensions=['fenced_code', 'codehilite', 'tables', 'toc', 'nl2br'])` | ✓ WIRED    | grep line 65, 85; codehilite enables Pygments                            |
| export_knowledge_base.py      | Jinja2                          | `from jinja2 import Environment, FileSystemLoader, select_autoescape`                 | ✓ WIRED    | grep line 47                                                             |
| export_knowledge_base.py      | kb.config                       | `from kb import config`                                                              | ✓ WIRED    | grep line 49, used for `KB_DB_PATH`, `KB_OUTPUT_DIR`                      |
| article.html template         | kb.i18n filter                  | `{{ key | t('zh-CN') }}` Jinja2 filter                                               | ✓ WIRED    | grep article.html for `\| t(`                                             |
| base.html template            | static assets                   | `<link rel="stylesheet" href="/static/style.css">` + `<script src="/static/lang.js">` | ✓ WIRED    | per kb-1-07 SUMMARY                                                       |

### Data-Flow Trace (Level 4)

| Artifact                            | Data Variable           | Source                                              | Produces Real Data | Status            |
| ----------------------------------- | ----------------------- | --------------------------------------------------- | ------------------ | ----------------- |
| kb/export_knowledge_base.py          | `articles`              | `list_articles(limit=10000, offset=0)` (real DB)    | NO                 | ✗ DISCONNECTED — TypeError on production schema; works only on uniform-TEXT test fixture |
| kb/data/article_query.py             | `update_time` (KOL)     | `articles.update_time` column (INTEGER in prod)     | YES (epoch int)    | ⚠️ STATIC type mismatch — int leaks past row mapper |
| kb/data/article_query.py             | `update_time` (RSS)     | `rss_articles.published_at` or `fetched_at` (TEXT)  | YES (ISO string)   | ✓ FLOWING                                          |
| kb/scripts/detect_article_lang.py    | `articles.lang` writes  | `UPDATE articles SET lang = ? WHERE id = ?`         | YES                | ✓ FLOWING (verified during verification: 653 rows newly written) |

### Behavioral Spot-Checks

| Behavior                                                                  | Command                                                                                                | Result                                          | Status                  |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ----------------------------------------------- | ----------------------- |
| `kb/export_knowledge_base.py` parses + presents CLI                       | `venv/Scripts/python.exe kb/export_knowledge_base.py --help`                                           | usage line shown; `--output-dir` + `--limit` only; no `--db-path` (per Issue #3 fix) | ✓ PASS                  |
| Module-level imports succeed                                              | `venv/Scripts/python.exe -c "from kb.data.article_query import ArticleRecord, list_articles, ..."`     | `5 exports OK`                                   | ✓ PASS                  |
| Test suite (unit + integration)                                            | `venv/Scripts/python.exe -m pytest tests/unit/kb/ tests/integration/kb/ -q`                              | `71 passed in 1.12s`                             | ✓ PASS                  |
| Migration script runs idempotently                                        | `KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe -m kb.scripts.migrate_lang_column`  | first run: `articles: added`, `rss_articles: added`; (re-run during integration tests proven idempotent) | ✓ PASS                  |
| Lang detect populates production DB                                       | `KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe -m kb.scripts.detect_article_lang`   | `articles: updated={'unknown': 457, 'en': 121, 'zh-CN': 75}`; `rss_articles: updated={'unknown': 1203, 'en': 397}` | ✓ PASS                  |
| End-to-end real-DB export                                                 | `KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe kb/export_knowledge_base.py --limit 3` | `TypeError: '<' not supported between instances of 'int' and 'str'` at article_query.py:165 | ✗ FAIL                  |
| EXPORT-02 invariant: zero DB mutation patterns in export driver           | `grep -E "INSERT INTO\|UPDATE.*SET\|DELETE FROM\|\.unlink\(\|rmtree" kb/export_knowledge_base.py`     | no matches                                       | ✓ PASS                  |
| EXPORT-01 invariant: zero wall-clock calls in export driver               | `grep -nE "datetime\.now\|datetime\.utcnow\|time\.time\(" kb/export_knowledge_base.py`                  | 3 matches at lines 68, 206, 224 — all comments/docstrings warning future contributors; zero actual calls | ✓ PASS                  |

### Requirements Coverage

| Requirement | Source Plan      | Description                                                        | Status     | Evidence                                                                                                       |
| ----------- | ---------------- | ------------------------------------------------------------------ | ---------- | -------------------------------------------------------------------------------------------------------------- |
| I18N-01     | kb-1-04          | Accept-Language detect + zh-CN fallback                            | ✓ SATISFIED | `kb/static/lang.js` 4-tier resolution; needs human browser verify                                              |
| I18N-02     | kb-1-04          | `?lang=` + `kb_lang` cookie 1y                                     | ✓ SATISFIED | `kb/static/lang.js`; needs human browser verify                                                                |
| I18N-03     | kb-1-03          | locale JSON + Jinja2 filter                                        | ✓ SATISFIED | 8/8 unit tests; 45 keys identical parity                                                                       |
| I18N-04     | kb-1-07          | `?lang=` filter on article list (SSG-side JS)                      | ⚠️ BLOCKED  | Filter UI exists in articles_index.html, but rendered list cannot be generated against real DB until gap 1 fixed |
| I18N-05     | kb-1-08          | `<html lang>` from article.lang                                    | ✓ SATISFIED | article.html line 1; integration test 5 PASS                                                                   |
| I18N-06     | kb-1-08          | content-lang badge                                                  | ✓ SATISFIED | article.html lang-badge single-emit; integration test 5 PASS                                                   |
| I18N-08     | kb-1-04 + kb-1-07 | nav `.lang-toggle`                                                  | ✓ SATISFIED | base.html nav element; needs human browser verify                                                              |
| DATA-01     | kb-1-02          | nullable `lang TEXT` migration idempotent                           | ✓ SATISFIED | 6 unit tests pass + verified 2-run idempotent against dev DB during verification                                |
| DATA-02     | kb-1-02 + kb-1-05 | CJK ratio detector + driver                                         | ✓ SATISFIED | 12 + 7 unit tests pass; verified populates real DB during verification                                          |
| DATA-03     | kb-1-05          | incremental `WHERE lang IS NULL`                                    | ✓ SATISFIED | 7/7 unit tests; idempotent re-run pattern proven via spy                                                       |
| DATA-04     | kb-1-06          | `list_articles` paginated sort                                      | ⚠️ BLOCKED  | Code-level correct (24 unit tests pass); runtime FAILS on real DB due to gap 1                                  |
| DATA-05     | kb-1-06          | `get_article_by_hash` resolves md5[:10] across both tables         | ✓ SATISFIED | 24/24 unit tests including 3-tier resolution                                                                   |
| DATA-06     | kb-1-06          | content_hash 3-branch resolution                                    | ✓ SATISFIED | `resolve_url_hash` pure function, 6 unit tests cover 3 branches + ValueError                                    |
| EXPORT-01   | kb-1-09          | Idempotent rebuild byte-identical                                   | ⚠️ BLOCKED  | Test 4 (recursive sha256) PASS on TEXT-only fixture; cannot verify against real DB until gap 1 fixed              |
| EXPORT-02   | kb-1-09          | Read-only consumption                                               | ✓ SATISFIED | grep clean (zero INSERT/UPDATE/DELETE/unlink/rmtree) + integration test 2 (md5 unchanged pre/post)              |
| EXPORT-03   | kb-1-09          | minimum page set generated                                          | ⚠️ BLOCKED  | Integration test 1 PASS on TEXT-only fixture; cannot verify against real DB until gap 1 fixed                  |
| EXPORT-04   | kb-1-09          | markdown + codehilite                                               | ✓ SATISFIED | `MD_EXTENSIONS = [..., 'codehilite']` line 65; integration test 1 confirms styling pipeline                    |
| EXPORT-05   | kb-1-06 + kb-1-09 | `localhost:8765/` -> `/static/img/` rewrite                         | ✓ SATISFIED | regex in `get_article_body`; integration test 3 explicit grep negative                                          |
| EXPORT-06   | kb-1-09          | sitemap.xml + robots.txt                                            | ✓ SATISFIED | render_sitemap + render_robots; integration test 1 PASS (6 url blocks; User-agent: * + Sitemap: /sitemap.xml) |
| UI-01       | kb-1-04          | design tokens                                                       | ✓ SATISFIED | `kb/static/style.css` line 1+ has `--bg: #0f172a` etc.                                                          |
| UI-02       | kb-1-04          | font stack                                                          | ✓ SATISFIED | grep `font-family.*Inter.*Noto Sans SC` matches                                                                |
| UI-03       | kb-1-04          | responsive 320/768/1024px                                            | ✓ SATISFIED | grep `@media (min-width: 768px/1024px)` matches; needs human viewport verify                                   |
| UI-04       | kb-1-04b         | brand assets reused from vitaclaw-site                               | ⚠️ PARTIAL  | favicon.svg placeholder (305 B "VC" mark on dark theme); Logo `.MISSING.txt` stub. User accepted via `approved-placeholder` resume signal. Hard kb-4 prerequisite. |
| UI-05       | kb-1-07          | og:* meta tags every page                                            | ✓ SATISFIED | base.html `<head>` block; integration test 5 PASS                                                              |
| UI-06       | kb-1-08          | JSON-LD Article schema with inLanguage                               | ✓ SATISFIED | article.html `<script type="application/ld+json">`; integration test 5 PASS                                    |
| UI-07       | kb-1-08          | breadcrumb localized                                                  | ✓ SATISFIED | article.html `class="breadcrumb"` + `\| t()` filter; integration test 5 PASS                                  |
| CONFIG-01   | kb-1-01          | env-driven config 6 keys                                              | ✓ SATISFIED | 8/8 unit tests pass; CONFIG-01 grep enforcement clean                                                          |

**Status totals:** 22 SATISFIED · 1 PARTIAL (UI-04) · 4 BLOCKED (I18N-04, DATA-04, EXPORT-01, EXPORT-03) by gap 1 — all become SATISFIED once gap 1 is fixed and a real-DB export run is captured.

### Anti-Patterns Found

| File                                  | Line(s)         | Pattern                                                                                                          | Severity   | Impact                                                                                                            |
| ------------------------------------- | --------------- | ---------------------------------------------------------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------- |
| `kb/data/article_query.py`            | 86-97, 100-113   | `_row_to_record_kol` and `_row_to_record_rss` accept raw column values into a dataclass field annotated `update_time: str` without type-normalizing — dataclass annotations are not runtime-enforced in Python | 🛑 Blocker  | TypeError on `list_articles` sort against production schema (gap 1). Same shape bug pattern as 2026-05-06 lesson "tests pin to independently-verifiable values, not mirror impl." |
| `tests/integration/kb/test_export.py`  | 73              | Fixture schema declares `update_time TEXT` instead of mirroring production `articles.update_time INTEGER` — fixture diverges from production schema | 🛑 Blocker  | Masked gap 1 — all 6 integration tests pass against the wrong-shape fixture. Direct precedent: 2026-05-07 CV-mass-classify postmortem "any schema/SQL改动必须在 production-shape 数据上跑过完整使用场景". |
| `kb/export_knowledge_base.py`          | 68, 206, 224    | 3 hits for `datetime.now` — false positive (all are comments/docstrings warning future contributors)             | ℹ️ Info    | Not a bug; documented intentional pattern.                                                                       |
| `kb/static/VitaClaw-Logo-v0.png.MISSING.txt` | 1-30            | Placeholder logo stub instead of real PNG                                                                         | ⚠️ Warning | Documented + user-approved (`approved-placeholder` resume signal). Hard kb-4 deploy prerequisite.                |

### Test Suite Verification

```
$ venv/Scripts/python.exe -m pytest tests/unit/kb/ tests/integration/kb/ -q
.......................................................................  [100%]
71 passed in 1.12s
```

- 65 unit tests across `kb-1-01` through `kb-1-08` — all pass
- 6 integration tests for `kb-1-09` export driver — all pass against TEXT-only fixture

### Outstanding Items

**Code-level gaps (blocking):**

1. `update_time` type mismatch in `kb/data/article_query.py` row mappers — production `articles.update_time` is INTEGER (Unix epoch) but `_row_to_record_kol` passes the int through. `list_articles` then mixes int + str → `TypeError`. **Blocks ROADMAP Success Criterion #2 entirely.** Fix scope: ~5 LOC in row mapper to normalize epoch -> ISO string + 1 fixture schema fix in integration test to mirror production schema (`update_time INTEGER`).

**Operational gaps (non-blocking, but listed for kb-4 / first-deploy):**

2. Migration + lang_detect were not run against `.dev-runtime/data/kol_scan.db` at phase-completion time. Status restored during this verification (KOL: 75 zh-CN + 121 en + 457 unknown / 653 total; RSS: 397 en + 1203 unknown / 1600 total; the `unknown` rows have body length < 200 chars per DATA-02 spec).

**Human verification (deferred):**

3. Visual rendering, browser-side i18n switching, viewport responsive testing, real PNG asset (kb-4 prerequisite) — all blocked behind gap 1 fix + a real-DB export run.

## Decision

**Status: gaps_found** — 1 blocking gap (gap 1: `update_time` mixed-type bug) prevents ROADMAP Success Criterion #2 from being achievable against production data. The fix is small (~5 LOC + 1 fixture) but real. 22/27 phase REQs are codebase-satisfied; 4 are blocked behind gap 1; 1 (UI-04) is partial-by-user-approval.

**Recommended next step:** `/gsd:plan-phase --gaps` to scaffold a focused plan that:
1. Normalizes `_row_to_record_kol` `update_time` from epoch int -> ISO string at the row-mapper boundary
2. Fixes integration fixture schema to mirror production (`articles.update_time INTEGER`)
3. Adds a new test asserting epoch->ISO normalization works against an INTEGER fixture
4. Runs a real-DB smoke (`KB_DB_PATH=.dev-runtime/data/kol_scan.db ... --limit 5`) and captures evidence

Once that plan ships, re-verify and the phase status flips to `human_needed` (the 4 truths currently UNCERTAIN can then be human-verified in a real browser against a real export).

**Note on REQUIREMENTS-KB-v2.md update:** The `requirements_satisfied` list in this verification's frontmatter enumerates the 24 REQs that have full codebase evidence today. The orchestrator should manually edit the REQUIREMENTS-KB-v2.md traceability table for these IDs (Status column from `Not started` → `Complete (kb-1-XX)`). The 4 BLOCKED REQs (I18N-04, DATA-04, EXPORT-01, EXPORT-03) should remain at their current status until gap 1 closes.

---

_Verified: 2026-05-13T13:00:00Z_
_Verifier: Claude (gsd-verifier)_
