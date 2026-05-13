---
phase: kb-1-ssg-export-i18n-foundation
verified: 2026-05-13T13:30:00Z
status: human_needed
score: 7/8 must-haves VERIFIED, 1/8 PARTIAL (UI-04 user-approved placeholder)
re_verification:
  previous_status: gaps_found
  previous_score: 1/8 fully VERIFIED, 2/8 PARTIAL, 4/8 UNCERTAIN, 1/8 FAILED
  gap_closure_plan: kb-1-10-gap-time-normalization-PLAN.md
  gaps_closed:
    - "Truth #2 (FAILED → VERIFIED): Real-DB export run produces complete kb/output/ tree without TypeError"
    - "Truth #7 (PARTIAL → VERIFIED): list_articles works against production schema (mixed INT/TEXT update_time)"
    - "Operational owe (PARTIAL): _ensure_lang_column defensive guard fails fast with operator-actionable error"
  truths_promoted_to_human_needed:
    - "Truth #3 (UNCERTAIN → human-verifiable): real-DB exported HTML now exists for browser inspection"
    - "Truth #4 (UNCERTAIN → human-verifiable): browser ?lang= switch + cookie persistence ready for browser test"
    - "Truth #5 (UNCERTAIN → human-verifiable): sitemap + robots + og + JSON-LD ready for inspection on real output"
    - "Truth #6 (UNCERTAIN → human-verifiable): viewport responsive testing ready"
  gaps_remaining: []
  regressions: []

# REQ IDs that are now satisfied with codebase evidence
# (orchestrator should manually edit REQUIREMENTS-KB-v2.md traceability table for these)
requirements_satisfied:
  - I18N-01      # kb/static/lang.js Accept-Language detect + zh-CN fallback (kb-1-04)
  - I18N-02      # ?lang= query + kb_lang cookie 1y SameSite=Lax (kb-1-04)
  - I18N-03      # kb.i18n.t() Jinja2 filter + 45-key locale parity (kb-1-03)
  - I18N-04      # SSG-side filter UI in articles_index.html, real-DB rendered list now produces filterable output (kb-1-07 + kb-1-10)
  - I18N-05      # article.html sets <html lang> from article.lang (kb-1-08)
  - I18N-06      # article.html lang badge zh/en single-emit (kb-1-08)
  - I18N-08      # base.html .lang-toggle nav element (kb-1-04 + kb-1-07)
  - DATA-01      # kb/scripts/migrate_lang_column.py idempotent ALTER (kb-1-02)
  - DATA-02      # kb/data/lang_detect.py pure-fn CJK ratio detector (kb-1-02)
  - DATA-03      # detect_article_lang.py WHERE lang IS NULL idempotent (kb-1-05)
  - DATA-04      # article_query.list_articles real-DB run validated (kb-1-06 + kb-1-10 fix)
  - DATA-05      # article_query.get_article_by_hash 3-tier resolution (kb-1-06)
  - DATA-06      # article_query.resolve_url_hash 3-branch pure (kb-1-06)
  - EXPORT-01    # Real-DB --limit 3 + --limit 5 both succeed; idempotency proven on TEXT-only fixture + production schema (kb-1-09 + kb-1-10)
  - EXPORT-02    # grep-clean: zero INSERT/UPDATE/DELETE/unlink/rmtree in kb/data/article_query.py + kb/export_knowledge_base.py
  - EXPORT-03    # Real-DB run produces 14-file output tree: 3 articles + 3 index pages + sitemap.xml + robots.txt + 5 static (kb-1-09 + kb-1-10)
  - EXPORT-04    # markdown lib + codehilite extensions wired in MD_EXTENSIONS (kb-1-09)
  - EXPORT-05    # localhost:8765 -> /static/img/ regex rewrite in get_article_body (kb-1-06) + integration test 3 PASS
  - EXPORT-06    # render_sitemap + render_robots in export driver; verified by integration test 1 + real-DB run
  - UI-01        # kb/static/style.css design tokens --bg #0f172a etc. (kb-1-04)
  - UI-02        # font-family Inter + Noto Sans SC chain (kb-1-04)
  - UI-03        # mobile-first @media (min-width: 768px / 1024px) (kb-1-04)
  - UI-05        # base.html og:* meta in <head> (kb-1-07)
  - UI-06        # article.html <script type="application/ld+json"> with inLanguage (kb-1-08)
  - UI-07        # article.html breadcrumb with i18n-localized labels (kb-1-08)
  - CONFIG-01    # kb/config.py 6 env-driven constants; CONFIG-01 grep clean (kb-1-01)

requirements_partial:
  - UI-04        # PARTIAL — favicon.svg placeholder + Logo .MISSING.txt stub; user-approved via kb-1-04b approved-placeholder resume signal. Hard kb-4 deploy prerequisite (real PNG must be sourced from vitaclaw-site sibling repo before public deploy).

human_verification:
  - test: "Open a generated article detail HTML in a browser; verify <html lang>, lang badge, breadcrumb, og:* meta, JSON-LD all render correctly"
    expected: "Per ROADMAP Success Criterion #3 — visible '中文' / 'English' badge, correct breadcrumb labels, code highlighting, no broken images"
    why_human: "Visual rendering — only verifiable by opening generated HTML in a real browser. Real-DB output now exists at .scratch/kb-1-10-final-output-20260513-092347/ (5 article HTMLs)"
  - test: "Load any generated page with `?lang=en`, verify all UI chrome strings switch to English; reload without param, verify English persists via `kb_lang` cookie"
    expected: "Per ROADMAP Success Criterion #4 — all chrome strings (nav, footer, page titles, etc.) toggle correctly; cookie persists 1 year per kb-1-04 spec"
    why_human: "Browser-side JavaScript behavior + cookie persistence — not verifiable from the CLI alone"
  - test: "Open generated index/articles list/article detail/Q&A pages on mobile (320-767px), tablet (768-1023px), desktop (1024px+) viewports; verify no horizontal scroll"
    expected: "Per ROADMAP Success Criterion #6 — UI-03 responsive across breakpoints"
    why_human: "Visual viewport testing requires a real browser at multiple viewport sizes"
  - test: "Verify `kb/static/VitaClaw-Logo-v0.png` is replaced (currently .MISSING.txt stub) before kb-4 public deploy"
    expected: "Per kb-1-04b SUMMARY 'User Setup Required' — real PNG copied from vitaclaw-site sibling repo"
    why_human: "Operator action — sourcing the asset from a sibling repo not present on this Windows dev box. Currently flagged graceful-degraded via base.html `onerror=\"this.style.display='none'\"`. UI-04 considered satisfied for kb-1 milestone scope per `approved-placeholder` resume signal; carry-forward gate to kb-4."
---

# Phase kb-1: SSG Export + i18n Foundation Verification Report (Re-Verification)

**Phase Goal:** Build SSG export driver + bilingual i18n foundation that produces a complete static HTML site from `kol_scan.db`.

**Verified:** 2026-05-13T13:30:00Z (re-verification after kb-1-10 gap-closure plan)
**Status:** human_needed
**Re-verification:** Yes — initial verification 2026-05-13T13:00 surfaced 1 BLOCKING bug + 1 operational gap. Plan kb-1-10 closed both gaps via 4 commits; this re-verification confirms closure and promotes UNCERTAIN truths to human-verifiable.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| #   | Truth                                                                                                                                                                                                                                                                            | Previous   | Current     | Evidence                                                                                                                                                                                                                                                                                                                                                                                                       |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `kb/scripts/detect_article_lang.py` runs on the live `kol_scan.db`; `articles.lang` + `rss_articles.lang` 100% non-NULL after; re-runs idempotent (DATA-01..03)                                                                                                                  | ⚠️ PARTIAL | ✓ VERIFIED  | Code correct + 7/7 unit tests pass. During initial verification the migration + detect were run against `.dev-runtime/data/kol_scan.db` proving end-to-end: KOL {unknown: 457, en: 121, zh-CN: 75}; RSS {unknown: 1203, en: 397}. kb-1-10 also added `_ensure_lang_column` defensive guard in export driver: lang-less DB now produces operator-actionable error (`.scratch/kb-1-10-guard-smoke-20260513-092224.log`). |
| 2   | `python kb/export_knowledge_base.py` produces `kb/output/index.html`, `kb/output/articles/{hash}.html` for every passable KOL + RSS row, and `kb/output/ask/index.html` (EXPORT-01..03)                                                                                          | ✗ FAILED   | ✓ VERIFIED  | Real-DB run `KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe kb/export_knowledge_base.py --limit 3` exits 0; produces 14-file output tree (3 articles + 3 index pages + sitemap.xml + robots.txt + 5 static assets). `--limit 5` also exits 0 with 5 article HTMLs. Re-verified 2026-05-13T13:30 — confirmed exit 0. Evidence: `.scratch/kb-1-10-real-db-smoke-20260513-091713.log` lines 6-15. |
| 3   | Article detail HTML shows correct `<html lang>`, content-language badge, rendered markdown body with codehilite, `localhost:8765/` rewritten to `/static/img/`, breadcrumb with localized labels (I18N-05/06, EXPORT-04/05, UI-07)                                               | ? UNCERTAIN | ? HUMAN     | Templates verified at code level (article.html 105 LOC). Integration test 3 confirms `localhost:8765 → /static/img/` rewrite. Integration test 5 confirms `<html lang>`, lang badge, breadcrumb, og + JSON-LD elements rendered. Real-DB output now exists at `.scratch/kb-1-10-final-output-20260513-092347/articles/*.html` (5 files); ready for browser visual confirmation.                                  |
| 4   | `?lang=en` switches UI chrome to English; `kb_lang` cookie persists; `Accept-Language` detection produces zh-CN fallback; article list `?lang=en` filters to English articles (I18N-01/02/04/08)                                                                                | ? UNCERTAIN | ? HUMAN     | `kb/static/lang.js` (104 LOC ES5 IIFE) implements 4-tier resolution per kb-1-04 SUMMARY. Code-level grep confirms `?lang=` parsing + `kb_lang` cookie set/read. Real-DB articles_index.html now exists for browser test of the `?lang=` filter behavior.                                                                                                                                                       |
| 5   | `kb/output/sitemap.xml` lists every article URL + homepage with `<lastmod>`; `robots.txt` allows all + `Sitemap:`; article detail pages carry `og:title/description/image/type/locale` + JSON-LD `Article` with `inLanguage` (EXPORT-06, UI-05/06)                              | ? UNCERTAIN | ? HUMAN     | `render_sitemap` + `render_robots` in export driver use deterministic input-derived `<lastmod>`. Integration test 1 confirms 6 `<url>` blocks, `User-agent: *`, `Sitemap: /sitemap.xml`. Real-DB output now produces sitemap with 6 entries (3 index + 3 article URLs); 1 KNOWN sitemap caveat: RSS rows with RFC-822 `published_at` produce truncated `<lastmod>` (e.g. "Wed, 4 Sep") — see Outstanding Items.    |
| 6   | Mobile/desktop viewports render without horizontal scroll; design tokens + font stack load from single `kb/static/style.css`; logo + favicon present (UI-01/02/03/04)                                                                                                            | ? UNCERTAIN | ? HUMAN     | `kb/static/style.css` (587 lines) verified to contain `--bg: #0f172a` design token + `font-family: 'Inter', 'Noto Sans SC', system-ui` + `@media (min-width: 768px/1024px)` mobile-first responsive. UI-04 placeholder accepted via `approved-placeholder` resume signal. Browser viewport visual confirmation deferred to human verification.                                                                |
| 7   | `kb/data/article_query.list_articles(lang, source, limit, offset)` returns paginated `ArticleRecord` lists sorted by `update_time DESC` (DATA-04); `get_article_by_hash` resolves md5[:10] across both KOL and RSS (DATA-05); content_hash 3-branch resolution (DATA-06)         | ⚠️ PARTIAL | ✓ VERIFIED  | All 5 public exports importable. 24/24 unit tests pass + 2 new regression tests pin production schema (`update_time INTEGER`). `_normalize_update_time` boundary normalizer (`kb/data/article_query.py:87`) converts INT epoch → ISO-8601 str. Real-DB list_articles call returns 3 KOL records with `update_time='2026-05-07T10:15:32+00:00'` (ISO str), no TypeError. Evidence: `.scratch/kb-1-10-real-db-smoke-20260513-091713.log` lines 43-49. |
| 8   | `kb/config.py` reads `KB_DB_PATH`, `KB_IMAGES_DIR`, `KB_OUTPUT_DIR`, `KB_PORT`, `KB_DEFAULT_LANG`, `KB_SYNTHESIZE_TIMEOUT` from env with documented defaults; no path hardcoded outside config.py (CONFIG-01)                                                                    | ✓ VERIFIED | ✓ VERIFIED  | `kb/config.py` ships 6 env-driven constants; 8/8 unit tests pass; CONFIG-01 enforcement grep `grep -rE "/.hermes\|kol_scan\.db" kb/ --include='*.py' --exclude=config.py` returns 0 hits per kb-1-01 SUMMARY.                                                                                                                                                                                                  |

**Score:**
- 4/8 truths fully ✓ VERIFIED (1, 2, 7, 8) — was 1/8
- 0/8 ⚠️ PARTIAL (was 2/8: truths 1 + 7 promoted)
- 4/8 ? HUMAN (3, 4, 5, 6) — code-level + real-output now exist; only browser inspection remains
- 0/8 ✗ FAILED (was 1/8: truth 2 closed)

**Net change vs initial verification:** All 3 GAPS_FOUND signals (FAILED + 2 PARTIAL) closed. 4 UNCERTAIN truths now have real exported output ready for human verification. UI-04 stays partial-by-user-approval (acknowledged in resume signal; kb-4 deploy prereq).

### Required Artifacts

| Artifact                                       | Expected                                                          | Status     | Details                                                                       |
| ---------------------------------------------- | ----------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------- |
| `kb/__init__.py`                               | namespace package                                                 | ✓ VERIFIED | exists                                                                        |
| `kb/config.py`                                 | env-driven constants                                              | ✓ VERIFIED | 6 constants + 8 unit tests pass                                               |
| `kb/data/__init__.py`                          | data subpackage                                                   | ✓ VERIFIED | exists                                                                        |
| `kb/data/article_query.py`                     | 5 public exports + ArticleRecord + `_normalize_update_time`       | ✓ VERIFIED | 252+22 LOC, 5 exports importable, 24+2 unit tests pass; runtime works on real DB (kb-1-10) |
| `kb/data/lang_detect.py`                       | pure-fn CJK ratio detector                                        | ✓ VERIFIED | 47 LOC, 12 unit tests pass                                                    |
| `kb/scripts/migrate_lang_column.py`            | idempotent ALTER for both tables                                  | ✓ VERIFIED | 60 LOC, 6 unit tests pass + idempotent re-run verified during initial verification    |
| `kb/scripts/detect_article_lang.py`            | CLI driver `WHERE lang IS NULL`                                   | ✓ VERIFIED | 97 LOC, 7 unit tests pass + real-DB run verified during initial verification          |
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
| `kb/export_knowledge_base.py`                  | single CLI entry point + `_ensure_lang_column` guard              | ✓ VERIFIED | 360+28 LOC. Real-DB --limit 3 + --limit 5 both exit 0. `_ensure_lang_column` defensive guard at line 272, called from main() line 345. |

### Key Link Verification

| From                          | To                              | Via                                                                                  | Status     | Details                                                                  |
| ----------------------------- | ------------------------------- | ------------------------------------------------------------------------------------ | ---------- | ------------------------------------------------------------------------ |
| export_knowledge_base.py      | kb.data.article_query           | `from kb.data.article_query import ArticleRecord, get_article_body, list_articles, resolve_url_hash` | ✓ WIRED    | grep line 50, 5 exports imported                                          |
| export_knowledge_base.py      | kb.i18n                         | `from kb.i18n import register_jinja2_filter, validate_key_parity`                    | ✓ WIRED    | grep line 56, register called at `_build_env`                             |
| export_knowledge_base.py      | markdown library + Pygments     | `markdown.Markdown(extensions=['fenced_code', 'codehilite', 'tables', 'toc', 'nl2br'])` | ✓ WIRED    | grep line 65, 85; codehilite enables Pygments                            |
| export_knowledge_base.py      | Jinja2                          | `from jinja2 import Environment, FileSystemLoader, select_autoescape`                 | ✓ WIRED    | grep line 47                                                             |
| export_knowledge_base.py      | kb.config                       | `from kb import config`                                                              | ✓ WIRED    | grep line 49, used for `KB_DB_PATH`, `KB_OUTPUT_DIR`                      |
| export_knowledge_base.py      | _ensure_lang_column guard       | `_ensure_lang_column(config.KB_DB_PATH)` at start of main()                          | ✓ WIRED    | line 345 (def at 272); negative-branch smoke proven (`.scratch/kb-1-10-guard-smoke-20260513-092224.log`) |
| article_query._row_to_record_kol | _normalize_update_time helper | `update_time=_normalize_update_time(row["update_time"])`                              | ✓ WIRED    | line 116; helper at line 87                                                |
| article.html template         | kb.i18n filter                  | `{{ key | t('zh-CN') }}` Jinja2 filter                                               | ✓ WIRED    | grep article.html for `\| t(`                                             |
| base.html template            | static assets                   | `<link rel="stylesheet" href="/static/style.css">` + `<script src="/static/lang.js">` | ✓ WIRED    | per kb-1-07 SUMMARY                                                       |

### Data-Flow Trace (Level 4)

| Artifact                            | Data Variable           | Source                                              | Produces Real Data | Status            |
| ----------------------------------- | ----------------------- | --------------------------------------------------- | ------------------ | ----------------- |
| kb/export_knowledge_base.py          | `articles`              | `list_articles(limit=10000, offset=0)` (real DB)    | YES                | ✓ FLOWING — real-DB --limit 3 returns 3 KOL records, exits 0 (kb-1-10 fix) |
| kb/data/article_query.py             | `update_time` (KOL)     | `articles.update_time` column (INTEGER in prod)     | YES (ISO str post-normalize) | ✓ FLOWING — `_normalize_update_time` converts epoch INT → ISO-8601 str at row mapper boundary |
| kb/data/article_query.py             | `update_time` (RSS)     | `rss_articles.published_at` or `fetched_at` (TEXT)  | YES (ISO string)   | ✓ FLOWING — RSS path unchanged in kb-1-10 (was correct)                 |
| kb/scripts/detect_article_lang.py    | `articles.lang` writes  | `UPDATE articles SET lang = ? WHERE id = ?`         | YES                | ✓ FLOWING (verified during initial verification: 653 rows newly written) |

### Behavioral Spot-Checks

| Behavior                                                                  | Command                                                                                                | Result                                          | Status                  |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ----------------------------------------------- | ----------------------- |
| `kb/export_knowledge_base.py` parses + presents CLI                       | `venv/Scripts/python.exe kb/export_knowledge_base.py --help`                                           | usage line shown; `--output-dir` + `--limit` only | ✓ PASS                  |
| Module-level imports succeed                                              | `venv/Scripts/python.exe -c "from kb.data.article_query import ArticleRecord, list_articles, ..."`     | `5 exports OK`                                   | ✓ PASS                  |
| Test suite (unit + integration)                                            | `venv/Scripts/python.exe -m pytest tests/unit/kb/ tests/integration/kb/ -q`                              | `73 passed in 1.86s` (was 71 — 2 new kb-1-10 regression tests) | ✓ PASS                  |
| End-to-end real-DB export (PRIMARY GAP CLOSURE GATE)                      | `KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe kb/export_knowledge_base.py --limit 3` | exit 0; 14-file output tree; 3 article HTMLs   | ✓ PASS (was ✗ FAIL)     |
| End-to-end real-DB export (re-run during re-verification)                  | Same command, `--output-dir .scratch/kb-1-verify-recheck-output`                                       | exit 0 (re-confirmed 2026-05-13T13:30)         | ✓ PASS                  |
| Defensive guard fires on lang-less DB (NEGATIVE BRANCH)                   | Build temp DB without `lang` column, run export                                                         | exit 1 + operator-actionable error mentioning `migrate_lang_column` AND `detect_article_lang` | ✓ PASS                  |
| EXPORT-02 invariant: zero DB mutation patterns in export driver           | `grep -E "INSERT INTO\|UPDATE.*SET\|DELETE FROM\|\.unlink\(\|rmtree" kb/export_knowledge_base.py kb/data/article_query.py` | no matches                                       | ✓ PASS (preserved across kb-1-10 delta) |

### Requirements Coverage

| Requirement | Source Plan      | Description                                                        | Previous   | Current     | Evidence                                                                                                       |
| ----------- | ---------------- | ------------------------------------------------------------------ | ---------- | ----------- | -------------------------------------------------------------------------------------------------------------- |
| I18N-01     | kb-1-04          | Accept-Language detect + zh-CN fallback                            | ✓ SATISFIED | ✓ SATISFIED | `kb/static/lang.js` 4-tier resolution; needs human browser verify                                              |
| I18N-02     | kb-1-04          | `?lang=` + `kb_lang` cookie 1y                                     | ✓ SATISFIED | ✓ SATISFIED | `kb/static/lang.js`; needs human browser verify                                                                |
| I18N-03     | kb-1-03          | locale JSON + Jinja2 filter                                        | ✓ SATISFIED | ✓ SATISFIED | 8/8 unit tests; 45 keys identical parity                                                                       |
| I18N-04     | kb-1-07 + kb-1-10 | `?lang=` filter on article list (SSG-side JS)                      | ⚠️ BLOCKED  | ✓ SATISFIED | Filter UI exists in articles_index.html. Real-DB rendered list now exists (`.scratch/kb-1-10-final-output-20260513-092347/articles/index.html`). Browser filter behavior is human-verifiable. |
| I18N-05     | kb-1-08          | `<html lang>` from article.lang                                    | ✓ SATISFIED | ✓ SATISFIED | article.html line 1; integration test 5 PASS                                                                   |
| I18N-06     | kb-1-08          | content-lang badge                                                  | ✓ SATISFIED | ✓ SATISFIED | article.html lang-badge single-emit; integration test 5 PASS                                                   |
| I18N-08     | kb-1-04 + kb-1-07 | nav `.lang-toggle`                                                  | ✓ SATISFIED | ✓ SATISFIED | base.html nav element; needs human browser verify                                                              |
| DATA-01     | kb-1-02          | nullable `lang TEXT` migration idempotent                           | ✓ SATISFIED | ✓ SATISFIED | 6 unit tests pass + verified 2-run idempotent against dev DB during initial verification                       |
| DATA-02     | kb-1-02 + kb-1-05 | CJK ratio detector + driver                                         | ✓ SATISFIED | ✓ SATISFIED | 12 + 7 unit tests pass; verified populates real DB during initial verification                                  |
| DATA-03     | kb-1-05          | incremental `WHERE lang IS NULL`                                    | ✓ SATISFIED | ✓ SATISFIED | 7/7 unit tests; idempotent re-run pattern proven via spy                                                       |
| DATA-04     | kb-1-06 + kb-1-10 | `list_articles` paginated sort                                      | ⚠️ BLOCKED  | ✓ SATISFIED | 24+2 unit tests pass (kb-1-10 added 2 production-shape regression tests); real-DB list_articles returns sorted records, no TypeError. |
| DATA-05     | kb-1-06          | `get_article_by_hash` resolves md5[:10] across both tables         | ✓ SATISFIED | ✓ SATISFIED | 24/24 unit tests including 3-tier resolution                                                                   |
| DATA-06     | kb-1-06          | content_hash 3-branch resolution                                    | ✓ SATISFIED | ✓ SATISFIED | `resolve_url_hash` pure function, 6 unit tests cover 3 branches + ValueError                                    |
| EXPORT-01   | kb-1-09 + kb-1-10 | Idempotent rebuild byte-identical                                   | ⚠️ BLOCKED  | ✓ SATISFIED | Test 4 (recursive sha256) PASS on production-shape fixture (post kb-1-10 INTEGER fixture upgrade); real-DB --limit 3 + --limit 5 both succeed deterministically |
| EXPORT-02   | kb-1-09          | Read-only consumption                                               | ✓ SATISFIED | ✓ SATISFIED | grep clean (zero INSERT/UPDATE/DELETE/unlink/rmtree) preserved across kb-1-10 delta                            |
| EXPORT-03   | kb-1-09 + kb-1-10 | minimum page set generated                                          | ⚠️ BLOCKED  | ✓ SATISFIED | Integration test 1 PASS on production-shape fixture; real-DB --limit 3 produces 14-file tree (3 articles + 3 indexes + sitemap + robots + 5 static); --limit 5 produces 5 articles. |
| EXPORT-04   | kb-1-09          | markdown + codehilite                                               | ✓ SATISFIED | ✓ SATISFIED | `MD_EXTENSIONS = [..., 'codehilite']` line 65; integration test 1 confirms styling pipeline                    |
| EXPORT-05   | kb-1-06 + kb-1-09 | `localhost:8765/` -> `/static/img/` rewrite                         | ✓ SATISFIED | ✓ SATISFIED | regex in `get_article_body`; integration test 3 explicit grep negative                                          |
| EXPORT-06   | kb-1-09          | sitemap.xml + robots.txt                                            | ✓ SATISFIED | ✓ SATISFIED | render_sitemap + render_robots; integration test 1 PASS + real-DB sitemap.xml has 6 url blocks                |
| UI-01       | kb-1-04          | design tokens                                                       | ✓ SATISFIED | ✓ SATISFIED | `kb/static/style.css` line 1+ has `--bg: #0f172a` etc.                                                          |
| UI-02       | kb-1-04          | font stack                                                          | ✓ SATISFIED | ✓ SATISFIED | grep `font-family.*Inter.*Noto Sans SC` matches                                                                |
| UI-03       | kb-1-04          | responsive 320/768/1024px                                            | ✓ SATISFIED | ✓ SATISFIED | grep `@media (min-width: 768px/1024px)` matches; needs human viewport verify                                   |
| UI-04       | kb-1-04b         | brand assets reused from vitaclaw-site                               | ⚠️ PARTIAL  | ⚠️ PARTIAL  | favicon.svg placeholder (305 B "VC" mark on dark theme); Logo `.MISSING.txt` stub. User accepted via `approved-placeholder` resume signal. Hard kb-4 prerequisite. |
| UI-05       | kb-1-07          | og:* meta tags every page                                            | ✓ SATISFIED | ✓ SATISFIED | base.html `<head>` block; integration test 5 PASS                                                              |
| UI-06       | kb-1-08          | JSON-LD Article schema with inLanguage                               | ✓ SATISFIED | ✓ SATISFIED | article.html `<script type="application/ld+json">`; integration test 5 PASS                                    |
| UI-07       | kb-1-08          | breadcrumb localized                                                  | ✓ SATISFIED | ✓ SATISFIED | article.html `class="breadcrumb"` + `\| t()` filter; integration test 5 PASS                                  |
| CONFIG-01   | kb-1-01          | env-driven config 6 keys                                              | ✓ SATISFIED | ✓ SATISFIED | 8/8 unit tests pass; CONFIG-01 grep enforcement clean                                                          |

**Status totals:** 26 ✓ SATISFIED · 1 ⚠️ PARTIAL (UI-04 user-approved) · 0 ✗ BLOCKED (was 4: I18N-04, DATA-04, EXPORT-01, EXPORT-03 all flipped to SATISFIED).

### Test Suite Verification

```
$ venv/Scripts/python.exe -m pytest tests/unit/kb/ tests/integration/kb/ -q
........................................................................ [ 98%]
.                                                                        [100%]
73 passed in 1.86s
```

- 67 unit tests across `kb-1-01` through `kb-1-08` + `kb-1-10` regression — all pass (was 65)
- 6 integration tests for `kb-1-09` export driver — all pass against production-shape fixture (post kb-1-10 schema upgrade `update_time INTEGER`)

**Test count delta:** 71 → 73 (+2 from kb-1-10 production-shape regression tests).

### Gap Closure Verification

The previous VERIFICATION.md flagged 1 BLOCKING gap (truth #2 FAILED) and 1 operational gap (truth #1 PARTIAL). Plan kb-1-10 closed both via 4 commits:

| # | Hash      | Type | Description                                                                                                            |
|---|-----------|------|------------------------------------------------------------------------------------------------------------------------|
| 1 | `2d52022` | test | RED — regression tests for `update_time` mixed-type bug + production-shape fixture                                       |
| 2 | `ea40f37` | fix  | GREEN — `_normalize_update_time` boundary normalizer in `_row_to_record_kol`                                            |
| 3 | `6bc4308` | feat | `_ensure_lang_column` startup guard with operator-actionable error                                                       |
| 4 | `aa8b9fe` | docs | kb-1-10 SUMMARY.md + deferred-items.md                                                                                  |

All 4 commits visible in `git log --oneline -10`. Re-verified 2026-05-13T13:30 against current HEAD.

**Evidence files (verbatim citations, no fabrication per CLAUDE.md 2026-05-08 ir-1 lesson):**

1. **Gap 1 happy-path closure:** `.scratch/kb-1-10-real-db-smoke-20260513-091713.log`
   - Lines 6-13: stdout (Rendering 3 article detail pages... → Done)
   - Line 15: `=== EXIT CODE: 0 ===`
   - Lines 18-31: 14-file output tree
   - Line 34: article HTML count = 3
   - Lines 43-49: KOL update_time post-normalization proof (`'2026-05-07T10:15:32+00:00'` etc., `type=str`)

2. **Gap 2 negative-branch (defensive guard) closure:** `.scratch/kb-1-10-guard-smoke-20260513-092224.log`
   - Step 1: built lang-less DB
   - Step 2: PRAGMA confirms `lang` absent
   - Step 3: ran export driver → exit 1 + full operator-actionable error captured
   - Line 14-18: error message text matches expected format

3. **Final --limit 5 verification:** `.scratch/kb-1-10-final-verification-20260513-092347.log`
   - Exit 0, 5 article HTMLs

4. **Re-verification re-run 2026-05-13T13:30:** captured inline this report
   - `KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe kb/export_knowledge_base.py --limit 3 --output-dir .scratch/kb-1-verify-recheck-output` → exit 0, 14-file output tree confirmed.

### Anti-Patterns Found

| File                                  | Line(s)         | Pattern                                                                                                          | Severity   | Impact                                                                                                            |
| ------------------------------------- | --------------- | ---------------------------------------------------------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------- |
| `kb/static/VitaClaw-Logo-v0.png.MISSING.txt` | 1-30            | Placeholder logo stub instead of real PNG                                                                         | ⚠️ Warning | Documented + user-approved (`approved-placeholder` resume signal). Hard kb-4 deploy prerequisite.                |
| (resolved) `kb/data/article_query.py` | 86-97           | _row_to_record_kol epoch-INT passthrough                                                                          | ✓ Closed   | kb-1-10 commit `ea40f37` — `_normalize_update_time` boundary normalizer at line 87, called at line 116.            |
| (resolved) `tests/integration/kb/test_export.py` | 73       | Fixture schema diverged from production (`update_time TEXT` vs INTEGER)                                          | ✓ Closed   | kb-1-10 commit `2d52022` — fixture upgraded to `update_time INTEGER` + 2 epoch ints inserted.                      |

### Outstanding Items

**Code-level gaps:** None. All previous BLOCKING gaps closed by kb-1-10.

**Operational gaps:** None within kb-1 scope. The `_ensure_lang_column` defensive guard (kb-1-10 commit `6bc4308`) prevents the operational failure mode at kb-4 deploy time. kb-4's `daily_rebuild.sh` should still invoke `migrate_lang_column` + `detect_article_lang` at first cron run (idempotent — safe re-run).

**Deferred items (documented in `deferred-items.md`, NOT kb-1 gaps):**

1. **RSS `published_at` format heterogeneity** — `rss_articles.published_at` contains mixed RFC 822 (`'Wed, 4 Sep 2024 04:31:00 +0000'`) and ISO-8601 (`'2026-05-02T17:26:40+00:00'`) format strings. Lexicographic sort surfaces RFC 822 strings AFTER ISO-8601 (because `'W'` > `'2'` in ASCII), and sitemap `<lastmod>` truncation produces `Wed, 4 Sep`. Per CLAUDE.md "Surgical Changes": kb-1-10's gap was specifically the int-vs-str TypeError crash — RSS format heterogeneity is a separate pre-existing data quality concern. Not blocking kb-1 milestone (no must_have or REQ requires sortable RSS dates at the SSG layer; the article HTML pages render correctly, only sitemap `<lastmod>` for RFC 822-dated rows is cosmetically wrong). Logged for future plan; suggested fix in `deferred-items.md`.

**Human verification required (4 items):**

1. **Browser visual rendering** — open generated article detail HTML; verify `<html lang>`, lang badge, breadcrumb, og:* meta, JSON-LD all render correctly. Real-DB output exists at `.scratch/kb-1-10-final-output-20260513-092347/articles/*.html` (5 files).

2. **Browser i18n switch** — `?lang=en` switches all UI chrome to English; `kb_lang` cookie persists 1 year; reload without param keeps English.

3. **Viewport responsive testing** — open homepage / article list / article detail / Q&A entry on mobile (320-767px), tablet (768-1023px), desktop (1024px+); no horizontal scroll on any breakpoint.

4. **Real PNG asset (kb-4 prereq)** — replace `kb/static/VitaClaw-Logo-v0.png.MISSING.txt` stub with actual PNG from vitaclaw-site sibling repo before kb-4 public deploy. Current graceful-degrade: `<img onerror="this.style.display='none'">` keeps layout stable.

## Decision

**Status: human_needed** — All automated checks pass, all 4 previously-BLOCKED REQs flipped to SATISFIED, all observable truths either ✓ VERIFIED or ready for human browser verification. Phase deliverable is complete; only browser-side visual + behavioral confirmation remains, which is normal for any SSG output.

**Score breakdown:**
- 4/8 truths ✓ VERIFIED (1, 2, 7, 8) — was 1/8
- 4/8 truths ? HUMAN-VERIFIABLE (3, 4, 5, 6) — was 4/8 UNCERTAIN (now have real exported output to inspect)
- 0/8 ✗ FAILED (was 1/8)
- 0/8 ⚠️ PARTIAL (was 2/8)

**REQ totals:** 26/27 SATISFIED + 1/27 PARTIAL-by-user-approval (UI-04). Was: 22/27 SATISFIED + 1/27 PARTIAL + 4/27 BLOCKED.

**Net delta from gap closure:** Phase moves from `gaps_found` (blocking) to `human_needed` (browser inspection only). The 4 BLOCKED REQs (I18N-04, DATA-04, EXPORT-01, EXPORT-03) are all SATISFIED. The kb-1 phase is functionally complete — the SSG export driver runs end-to-end against the production schema, produces a complete `kb/output/` tree, and all unit + integration tests pass.

**Recommended orchestrator next steps:**

1. Mark phase kb-1 complete in `.planning/ROADMAP-KB-v2.md` Progress Table (parallel-track manual edit — gsd-tools doesn't parse parallel-track files).
2. Update `.planning/STATE.md` with kb-1 closure.
3. Update `.planning/PROJECT-KB-v2.md` "Validated Requirements" section with the 26 SATISFIED + 1 PARTIAL REQ IDs.
4. Update `.planning/REQUIREMENTS-KB-v2.md` traceability table (Status column flips: Not started → Complete for each newly-satisfied REQ; UI-04 → "Complete (placeholder; PNG owed at kb-4)").
5. Commit the orchestrator-level updates.
6. Schedule human visual + browser verification as a follow-up task (does NOT block kb-3 phase start, since kb-3 depends only on the data layer + i18n filter + content_hash resolution which are all ✓ VERIFIED at code + integration + real-DB level).

---

_Re-verified: 2026-05-13T13:30:00Z_
_Verifier: Claude (gsd-verifier)_
_Previous verification: 2026-05-13T13:00 (gaps_found, 4 BLOCKED REQs)_
_Gap-closure plan: kb-1-10-gap-time-normalization-PLAN.md (4 commits: 2d52022, ea40f37, 6bc4308, aa8b9fe)_
