---
phase: kb-1-ssg-export-i18n-foundation
plan: "09"
subsystem: kb
tags: [kb-v2, ssg, export, jinja2, markdown, pygments, sitemap, idempotency, EXPORT-01..06]

# Dependency graph
requires:
  - phase: kb-1-01
    provides: "kb.config — KB_DB_PATH / KB_IMAGES_DIR / KB_OUTPUT_DIR"
  - phase: kb-1-03
    provides: "kb.i18n — register_jinja2_filter + validate_key_parity"
  - phase: kb-1-04
    provides: "kb/static/style.css + lang.js"
  - phase: kb-1-04b
    provides: "kb/static/favicon.svg + VitaClaw-Logo-v0.png placeholder"
  - phase: kb-1-06
    provides: "kb.data.article_query — ArticleRecord + 4 read-only query functions"
  - phase: kb-1-07
    provides: "base/index/articles_index/ask templates"
  - phase: kb-1-08
    provides: "article.html detail template"
provides:
  - "kb/export_knowledge_base.py — single CLI entry point for SSG build"
  - "kb/output/ tree (gitignored): index.html + articles/{hash}.html ×N + ask/index.html + sitemap.xml + robots.txt + _url_index.json + static/"
affects:
  - "Phase kb-1 capstone — wires every prior Wave 1-4 deliverable"
  - "kb-3 (FastAPI) reuses kb.data.article_query.list_articles + get_article_body, no overlap"
  - "kb-4 deploy: Caddy serves kb/output/ directly, no Python runtime at request time for SSG pages"

# Tech tracking
tech-stack:
  added:
    - "jinja2>=3.1 (templating)"
    - "markdown>=3.5 (markdown -> HTML)"
    - "pygments>=2.17 (codehilite syntax highlighting)"
    - "fastapi>=0.110 + uvicorn[standard]>=0.27 + python-multipart>=0.0.6 (kb-3 deps, pinned now for unified install order)"
  patterns:
    - "Atomic writes via .tmp + Path.replace (idempotency-safe)"
    - "Deterministic sitemap lastmod from article update_time (NEVER datetime.now)"
    - "json.dumps(sort_keys=True, ensure_ascii=False) for _url_index.json byte stability"
    - "Markdown re-instantiated per article (avoids codehilite state leak; cleanest per-call form)"
    - "sys.path defensive guard at module top — replaces kb/ with project root when run as script, so stdlib `locale` resolves correctly while `from kb import` still works"

key-files:
  created:
    - "kb/export_knowledge_base.py (360 lines)"
    - "tests/integration/kb/__init__.py"
    - "tests/integration/kb/test_export.py (244 lines, 6 tests)"
    - "requirements-kb.txt (13 lines, 6 deps)"
  modified: []

key-decisions:
  - "DB path override is env-only (KB_DB_PATH=/path), NOT a CLI flag — config.KB_DB_PATH is bound at module import before argparse runs, so a flag would be a no-op (REVISION 1 / Issue #3)"
  - "Sitemap <lastmod> derived from max(article.update_time[:10]) for index URLs and per-article update_time for detail URLs; deterministic _LASTMOD_FALLBACK='1970-01-01' for missing data — never datetime.now() (REVISION 1 / Issue #1)"
  - "og:description falls back to article title when stripped body <20 chars — covers image-only / very-short articles (REVISION 1 / Issue #6)"
  - "sys.path defensive guard at module top is required because kb/locale subpackage shadows stdlib `locale` when script is invoked as `python kb/export_knowledge_base.py` (kb/ is prepended to sys.path → argparse → gettext → locale.normalize fails). Fix: replace sys.path[0] with project root when it equals kb/."

requirements-completed: [EXPORT-01, EXPORT-02, EXPORT-03, EXPORT-04, EXPORT-05, EXPORT-06, I18N-04, UI-04]

# Metrics
duration: "~7 minutes"
completed: "2026-05-13"
tasks-completed: 3
tests-added: 6
tests-passing: 71
files-created: 4
files-modified: 0
loc-prod: 360
loc-tests: 244
commits: 3
---

# Phase kb-1 Plan 09: SSG Export Driver Summary

Single CLI entry point `python kb/export_knowledge_base.py` that wires every prior Wave 1-4 deliverable into a complete static-site build. Reads SQLite + filesystem, renders 4 Jinja2 templates with i18n, generates sitemap.xml + robots.txt + _url_index.json, copies static assets — all output byte-deterministic across runs.

## Objective Recap

The capstone plan for phase kb-1. Without it, every prior plan's artifacts are orphaned (kb.config, kb.i18n, kb.data.article_query, the 4 templates, kb/static/ all sit unused). This plan ships the spine: a 360-line CLI module + 6 integration tests proving the full pipeline works.

## What Shipped

**`kb/export_knowledge_base.py` (360 lines)** — single CLI entry point with the flow:

```
parse_args -> validate_key_parity (i18n parity check)
           -> build Jinja2 env + register kb.i18n filter
           -> list_articles(limit=10000) (read-only DB)
           -> for each article: render_article_detail (markdown -> HTML, atomic write)
           -> render_index_pages (home / articles list / ask)
           -> render_sitemap (deterministic lastmod from article data)
           -> render_robots
           -> write_url_index (collision detection + sorted JSON)
           -> copy_static_assets (kb/static/ -> kb/output/static/)
```

CLI flags: `--output-dir PATH`, `--limit N`. NO `--db-path` flag — DB path overridden via `KB_DB_PATH` env var only (config.KB_DB_PATH is bound at module import, so a flag would be silently ignored — Issue #3 fix preserves honesty).

**`tests/integration/kb/test_export.py` (244 lines, 6 tests)** — pytest integration suite:

| # | Test | Proves |
| --- | --- | --- |
| 1 | `test_export_produces_expected_output_tree` | EXPORT-03: index + articles/{hash} + ask + sitemap + robots + _url_index + static |
| 2 | `test_export_is_read_only_db` | EXPORT-02: source DB md5 byte-identical pre/post |
| 3 | `test_export_rewrites_localhost_image_url` | EXPORT-05: `localhost:8765` -> `/static/img/` in detail HTML; `localhost:8765` ABSENT |
| 4 | `test_export_idempotent_recursive_sha256` | EXPORT-01: recursive sha256 across ALL files identical between two runs (catches sitemap/robots/_url_index drift; defends against datetime.now leaks) |
| 5 | `test_detail_html_has_mandatory_i18n_ui_elements` | I18N-05/06 + UI-05/06/07: `<html lang>`, `class="lang-badge"`, `class="breadcrumb"`, `application/ld+json`, `og:type="article"` all present |
| 6 | `test_og_description_fallback_to_title_for_short_body` | REVISION 1 / Issue #6: short-body article's og:description equals article title (fallback path) |

**`requirements-kb.txt` (13 lines, 6 deps)** — isolated KB-v2 milestone deps:

```
# kb-1 (SSG)
jinja2>=3.1
markdown>=3.5
pygments>=2.17

# kb-3 (FastAPI) — pinned now for unified install order
fastapi>=0.110
uvicorn[standard]>=0.27
python-multipart>=0.0.6
```

Root `requirements.txt` UNCHANGED — verified via `git diff --name-only requirements.txt` (empty).

## Tests

**71/71 tests passing** in `tests/{unit,integration}/kb/`:

- 65 prior unit tests (config + lang_detect + migrate_lang + i18n + detect_article_lang + article_query + 04+04b+05) — all pass, no regressions
- 6 new integration tests for the export driver — all pass

```
$ pytest tests/unit/kb/ tests/integration/kb/ -v
============================= 71 passed in 1.14s ==============================
```

## Verification Evidence

### EXPORT-01 idempotency

Recursive sha256 across all output files (Test 4) — same DB content -> byte-identical output:

```python
files1 = sorted(p.relative_to(out1) for p in out1.rglob("*") if p.is_file())
files2 = sorted(p.relative_to(out2) for p in out2.rglob("*") if p.is_file())
assert files1 == files2  # same file set
for rel in files1:
    assert _sha256_file(out1 / rel) == _sha256_file(out2 / rel)  # byte-identical
```

Test 4 PASSED. Also grep-proof:

```
$ grep -E "datetime\.now|datetime\.utcnow|time\.time\(" kb/export_knowledge_base.py
68:# NEVER use datetime.now() anywhere in this module ...   (comment only)
206:    REVISION 1 / Issue #1: NEVER use datetime.now() ... (docstring only)
224:    NEVER from datetime.now()...                        (docstring only)
```

Zero actual calls to wall-clock time functions — all 3 hits are comments / docstrings warning future contributors.

### EXPORT-02 read-only

Test 2: md5(fixture_db) PRE export == md5(fixture_db) POST export. PASSED.

Also grep-proof (zero hits each):

```
$ grep -E "(INSERT INTO|UPDATE.*SET|DELETE FROM)" kb/export_knowledge_base.py  # 0 hits
$ grep -E "\.unlink\(|rmtree" kb/export_knowledge_base.py                       # 0 hits
```

### EXPORT-03

Test 1 verifies presence of `index.html` + `articles/index.html` + `articles/{hash}.html ×3` + `ask/index.html` + `sitemap.xml` + `robots.txt` + `_url_index.json` + `static/style.css` + `static/lang.js`. PASSED.

### EXPORT-04

Markdown -> HTML pipeline uses `markdown.markdown(body, extensions=['fenced_code', 'codehilite', 'tables', 'toc', 'nl2br'])`. Verified by grep:

```
$ grep -E "MD_EXTENSIONS|codehilite" kb/export_knowledge_base.py
55:MD_EXTENSIONS = ["fenced_code", "codehilite", "tables", "toc", "nl2br"]
... (4 more hits in docstrings + the convert call)
```

### EXPORT-05

Test 3: fixture article body contains `http://localhost:8765/abc/img.png`; rendered detail HTML contains `/static/img/abc/img.png` AND does NOT contain `localhost:8765`. PASSED.

### EXPORT-06

Test 1 verifies `sitemap.xml` starts with `<?xml version="1.0"` and contains exactly 6 `<url>` blocks (3 index + 3 article). `robots.txt` contains `User-agent: *` and `Sitemap: /sitemap.xml`. PASSED.

### I18N-04 + UI-04

I18N-04 (SSG-side): `articles_index.html` template renders ALL articles into pre-existing cards; client-side JS handles filter — driver itself just renders the full set. PASSED via Test 1 (3 detail files exist; index renders all).

UI-04: `copy_static_assets` copies `kb/static/*` -> `kb/output/static/*`; Test 1 asserts `style.css` + `lang.js` present in output. PASSED.

### CLI honesty (REVISION 1 / Issue #3)

```
$ python kb/export_knowledge_base.py --help
usage: export_knowledge_base.py [-h] [--output-dir OUTPUT_DIR] [--limit LIMIT]

KB-v2 SSG export. Override DB path with env: KB_DB_PATH=/path python
kb/export_knowledge_base.py
...
options:
  -h, --help
  --output-dir OUTPUT_DIR
  --limit LIMIT
```

NO `--db-path` flag in usage line. Description string explicitly directs users to `KB_DB_PATH` env var.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] `kb/locale` subpackage shadows stdlib `locale` when script is invoked as `python kb/export_knowledge_base.py`**

- **Found during:** Task 2 verify (smoke run of `--help`)
- **Issue:** Python prepends the script's directory (`kb/`) to `sys.path[0]` when invoked as a script. The `kb/locale/` subpackage (a package created in kb-1-03 to hold locale JSON files) then shadows Python's stdlib `locale` module. argparse internally calls `gettext.gettext(...)` which calls `locale.normalize(...)`, triggering `AttributeError: module 'locale' has no attribute 'normalize'`. Reproducible by running `python kb/export_knowledge_base.py --help` from project root with stock CPython 3.13.
- **Fix:** Defensive 11-line guard at module top — when `sys.path[0]` resolves to `kb/`, replace it with the project root. This way (a) stdlib `locale` resolves correctly, (b) `from kb import config` still works (project root is on path), and (c) the guard is a no-op when invoked via `python -m kb.export_knowledge_base` (sys.path[0] is then '' or project root, never kb/).
- **Why this is the right call:** Surgical Changes principle — alternative fixes (rename kb/locale, install entry-point script) would either break kb-1-03's locale module path or require a setup.py/pyproject.toml change adding new install-mode scope. The defensive sys.path guard is 11 lines and documented inline with full rationale. Both invocation forms now work.
- **Files modified:** `kb/export_knowledge_base.py` (added _THIS_DIR/_PROJECT_ROOT block + `# noqa: E402` on subsequent imports per PEP 8 late-import rule)
- **Commit:** `2f389f8` (Task 2 — fix included in initial commit)

### Note on TDD telescoping for Task 3

Plan marked Task 3 as `tdd="true"` (RED -> GREEN -> REFACTOR). In practice, since Task 2 shipped the impl directly, the RED phase telescoped — the test file as written exercises the already-shipped impl and validates GREEN on first run (6/6 pass). Net result: same coverage as classic TDD; a single `test(...)` commit instead of separate test+feat commits. Documented here for traceability.

## Phase kb-1 Goal-Backward Verification

Per CONTEXT.md "Output verification at end of phase" — every Phase kb-1 ROADMAP "Phase kb-1 Success Criteria" item now satisfied:

| # | Criterion | Status |
| --- | --- | --- |
| 1 | `kb.config` env-driven constants importable | ✅ kb-1-01 |
| 2 | `articles.lang` + `rss_articles.lang` columns exist (DATA-01/02) | ✅ kb-1-02 (migration script + idempotent re-runs) |
| 3 | i18n module + 45 chrome strings × 2 langs | ✅ kb-1-03 (key parity validated at build time) |
| 4 | static/style.css + lang.js + brand assets | ✅ kb-1-04 + kb-1-04b |
| 5 | one-shot lang detect script idempotent | ✅ kb-1-05 |
| 6 | article query layer (5 functions) read-only | ✅ kb-1-06 (24 unit tests) |
| 7 | 4 Jinja2 templates render with i18n | ✅ kb-1-07 + kb-1-08 |
| 8 | `python kb/export_knowledge_base.py` produces complete kb/output/ tree | ✅ kb-1-09 (this plan; 6 integration tests) |

**Phase kb-1 — COMPLETE.** Ready for kb-3 (FastAPI bilingual API + FTS5 search + /synthesize wrapper).

## Commits

| Commit | Type | Description |
| --- | --- | --- |
| `0a597f3` | chore | Add requirements-kb.txt for KB-v2 milestone deps |
| `2f389f8` | feat | Add SSG export driver wiring all kb-1 deliverables (Task 2 + sys.path defensive guard) |
| `1d6de5e` | test | Integration tests for SSG export driver — 6/6 passing |

## Acceptance Criteria — All Met

Task 1:
- [x] `requirements-kb.txt` exists with `jinja2>=3.1`, `markdown>=3.5`, `pygments>=2.17`
- [x] `pip install -r requirements-kb.txt` exits 0
- [x] `python -c "import jinja2, markdown, pygments; print('OK')"` outputs `OK`
- [x] Root `requirements.txt` UNCHANGED (`git diff --name-only requirements.txt` empty)

Task 2:
- [x] `kb/export_knowledge_base.py` exists, line count 360 (≥200)
- [x] Parses as valid Python (1564 AST nodes)
- [x] All required imports present (config + article_query + i18n + markdown + jinja2)
- [x] All required strings present (validate_key_parity / register_jinja2_filter / MD_EXTENSIONS / codehilite / _write_atomic / _LASTMOD_FALLBACK / _compute_index_lastmod)
- [x] Issue #1: zero `datetime.now`/`datetime.utcnow`/`time.time(` actual calls (3 hits in comments/docstrings only)
- [x] Issue #3: `--db-path` removed from argparse; `--help` does NOT mention it; description explicitly says `KB_DB_PATH=/path`
- [x] Issue #6: `_build_og` body contains `len(description) < 20` falling back to `article_dict["title"]`
- [x] Issue #8: `# TODO v2.1: env-overridable KB_HOME_LATEST_LIMIT` comment present
- [x] EXPORT-02: zero `INSERT INTO`/`UPDATE.*SET`/`DELETE FROM` strings
- [x] EXPORT-02: zero `.unlink(`/`rmtree` calls
- [x] CLI: `--help` exits 0; shows `--output-dir` + `--limit`; only those 2 flags

Task 3:
- [x] `pytest tests/integration/kb/test_export.py -v` exits 0 with 6 passing
- [x] File contains `pytest.mark.integration` marker
- [x] Test 2 explicitly asserts DB md5 unchanged (EXPORT-02 proof)
- [x] Test 3 explicitly greps `/static/img/` IN output AND `localhost:8765` NOT in output (EXPORT-05 proof)
- [x] Test 4 uses `Path.rglob("*")` + `hashlib.sha256` for ALL output files (EXPORT-01 proof covers sitemap/robots/_url_index)
- [x] Test 6 parses og:description for short-body article and asserts equals title
- [x] No `--db-path` arg appears in test invocations (Issue #3 surfaced in tests)

Plan-level success criteria:
- [x] All 8 EXPORT/I18N-04/UI-04 requirements satisfied
- [x] All 6 integration tests pass (and earlier 65 unit tests still passing) → 71/71
- [x] REVISION 1 hygiene: no `--db-path` CLI flag, no `datetime.now()` source-level calls, og:description never empty, KB_HOME_LATEST_LIMIT TODO documented

## Self-Check: PASSED

- File `kb/export_knowledge_base.py` exists: FOUND
- File `tests/integration/kb/__init__.py` exists: FOUND
- File `tests/integration/kb/test_export.py` exists: FOUND
- File `requirements-kb.txt` exists: FOUND
- Commit `0a597f3` (chore): FOUND
- Commit `2f389f8` (feat): FOUND
- Commit `1d6de5e` (test): FOUND
