---
phase: kb-3-fastapi-bilingual-api
plan: 02
subsystem: data
tags: [python, sqlite, tdd, data-quality-filter, read-only-queries, DATA-07]
type: execute
wave: 1
requirements:
  - DATA-07
status: complete
completed: 2026-05-14
duration_minutes: ~50
---

# kb-3-02 — DATA-07 Content-Quality Filter Summary

DATA-07 content-quality filter applied to 6 list-style query functions in
`kb/data/article_query.py`. Direct hash access (`get_article_by_hash`)
preserved as carve-out per kb-3-CONTENT-QUALITY-DECISIONS.md.

## Skill Invocations (mandatory per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1)

Skill(skill="python-patterns", args="Idiomatic module-level env var read pattern: `QUALITY_FILTER_ENABLED = os.environ.get('KB_CONTENT_QUALITY_FILTER', 'on').lower() != 'off'` evaluated once at import time. Schema-guard helper `_verify_quality_columns(conn)` using PRAGMA table_info() — fail loud with RuntimeError listing exact missing columns + the env override hint. Schema guard called lazily on first list-query invocation per process (cache `_SCHEMA_VERIFIED` dict keyed on id(conn)) so test fixtures can pre-set conn before guard runs. No imports beyond stdlib (os, sqlite3). PEP 8 + type hints throughout (dict[int, bool], etc.).")

Skill(skill="writing-tests", args="TDD tests for env override (case-insensitive 'off' bypass + 'on' default) + schema guard (missing column raises RuntimeError naming the column; healthy fixture passes) + fixture extension (positive verdict rows + ≥2 negative rows per source covering body=NULL/'', layer1=reject, layer2=reject) + filter applied to 6 list-style functions + carve-out preserved on get_article_by_hash + env-off bypasses guard + read-only SQL spy. Testing Trophy: integration-flavored unit tests against real fixture_db SQLite — no mocks. monkeypatch.setattr on the module-level QUALITY_FILTER_ENABLED constant instead of importlib.reload to avoid invalidating EntityCount/TopicSummary class identity across test files. SpyConn proxy captures every SQL string for read-only assertion (allows PRAGMA alongside SELECT/WITH).")

Both Skills loaded from `~/.claude/skills/python-patterns/SKILL.md` and
`~/.claude/skills/writing-tests/SKILL.md` BEFORE writing any code.
Guidance applied:
- python-patterns: PEP 8 type hints, explicit module-level env constant, EAFP avoided for schema drift (programmer error, not exception flow), `dict[int, bool]` Python 3.9+ built-in generic, no try/except for guard misses.
- writing-tests: integration-first against real SQLite, behavior-focused (assert on returned `ArticleRecord` lists, not SQL string structure), happy + error paths covered, sqlite3 in-memory connection allowed under "test DB" exception.

## What changed

### `kb/data/article_query.py` (+79 / -0)

| Addition | Purpose |
|---|---|
| `QUALITY_FILTER_ENABLED = os.environ.get(...).lower() != 'off'` | Module-level kill switch read at import |
| `_SCHEMA_VERIFIED: dict[int, bool]` | Per-conn-id cache; schema guard runs once per conn |
| `_verify_quality_columns(conn)` | PRAGMA table_info-based schema drift detection — fails loud with column names + bypass hint |
| `_DATA07_KOL_FRAGMENT` / `_DATA07_RSS_FRAGMENT` / `_DATA07_BARE` | SQL fragment constants for aliased (`a.`/`r.`) and unaliased SELECTs |
| Filter applied in `list_articles` | KOL + RSS legs both gated by `_DATA07_BARE`; WHERE/AND inserted correctly relative to optional `lang =` clause |
| Filter applied in `topic_articles_query` | Append `_DATA07_KOL_FRAGMENT` / `_DATA07_RSS_FRAGMENT` after existing cohort gate |
| Filter applied in `entity_articles_query` | Same pattern; threshold gate runs first (unchanged) |
| Filter applied in `cooccurring_entities_in_topic` | f-string interpolation of fragment constants into both legs of CTE |
| Filter applied in `related_entities_for_article` | Early-return `[]` if source article fails `_DATA07_BARE` EXISTS check |
| Filter applied in `related_topics_for_article` | Same early-return pattern |
| Carve-out comment in `get_article_by_hash` | Explicit non-filter rationale for direct URL access stability |

### `tests/integration/kb/conftest.py` (+20 / -2)

Added 4 negative-case rows to fixture (additive — kb-2 baseline tests
unaffected because negatives don't touch any classifications/entities used
by existing assertions):
- KOL id=99: body='', layer1='reject' — fails 2/3 conditions
- KOL id=98: body present, layer1='candidate', layer2='reject' — fails 1/3
- RSS id=97: body=NULL, layer1='candidate', layer2='ok' — fails body condition
- RSS id=96: body present, layer1='reject', layer2=NULL — fails layer1 condition

### `tests/unit/kb/test_article_query.py` (+25 / -8)

kb-1 fixture extended with `layer1_verdict TEXT` + `layer2_verdict TEXT`
columns on both `articles` + `rss_articles`; all rows tagged
`candidate` + `ok` so kb-1 tests pass through DATA-07 filter unchanged.

Read-only spy assertion relaxed to allow `PRAGMA` (schema guard is
read-only metadata access).

### `tests/unit/kb/test_kb2_queries.py` (+12 / -8)

Read-only assertions in `test_topic_articles_read_only` and
`test_kb2_queries_read_only` allow `PRAGMA` alongside SELECT/WITH.

### `tests/unit/kb/test_data07_quality_filter.py` (NEW, 417 lines)

17 tests covering all behaviors:

| # | Behavior |
|---|---|
| 1-3 | Env override: unset → True; `off` → False; `OFF`/`Off`/`oFf` → False (case-insensitive); other values stay True |
| 4 | Schema guard raises `RuntimeError` with column name when `articles` missing `layer1_verdict` |
| 5 | Schema guard passes silently on healthy fixture |
| 6 | Fixture has ≥3 positive verdict rows per source |
| 7 | Fixture has ≥2 negative verdict rows per source |
| 8 | `list_articles` excludes 4 negative rows; positive rows pass |
| 9 | `topic_articles_query` excludes layer2='reject' even when classified |
| 10 | `entity_articles_query` excludes layer2='reject' even when entity-mentioned |
| 11 | `cooccurring_entities_in_topic` cohort excludes negatives → entity only on negative rows doesn't surface |
| 12 | `related_entities_for_article` on negative source → [] |
| 13 | `related_topics_for_article` on negative source → [] |
| 14 | Carve-out: `get_article_by_hash` STILL returns negative-case row by hash |
| 15 | Env-off → `list_articles` returns ALL rows including negatives |
| 16 | Env-off bypasses schema guard (works on pre-DATA-07 schema) |
| 17 | Read-only spy across all 6 filtered functions: only SELECT/WITH/PRAGMA |

## Test results

- **DATA-07 tests:** 17/17 pass
- **kb-1 baseline (`test_article_query.py`):** 26/26 pass
- **kb-2 baseline (`test_kb2_queries.py`):** 19/19 pass
- **All kb unit tests:** 145/145 pass
- **All kb integration tests:** 64/64 pass (no regression on existing kb-1 export, kb-2 export pipelines)
- **Total kb tests:** 225/225 pass

## Acceptance criteria (from PLAN)

| Criterion | Status |
|---|---|
| `grep -E "layer1_verdict = 'candidate'" kb/data/article_query.py` returns ≥6 | 9 occurrences (across 3 fragment constants + 6 inlined cohort gates) |
| `grep "DATA-07 carve-out" kb/data/article_query.py` finds carve-out comment | 1 occurrence in `get_article_by_hash` docstring |
| `def get_article_by_hash` body has zero `_DATA07` references | Verified via Python regex extraction — body has NO `_DATA07`, NO `QUALITY_FILTER_ENABLED` |
| `pytest tests/unit/kb/test_data07_quality_filter.py` passes ≥17 tests | 17/17 pass |
| kb-2 regression: `test_kb2_queries.py` passes | 19/19 pass |
| kb-1 regression: `test_article_query.py` passes | 26/26 pass |
| No INSERT/UPDATE/DELETE in `kb/data/article_query.py` | grep returns 0 |
| Module imports clean: `python -c "from kb.data.article_query import list_articles, QUALITY_FILTER_ENABLED"` | Verified — exits 0 |
| `KB_CONTENT_QUALITY_FILTER` mentioned ≥2x in test file | 5 occurrences |
| `PRAGMA table_info` present | 2 occurrences (one for `articles`, one for `rss_articles`) |

## Cross-phase impact

| Phase / Surface | Inherits filter? |
|---|---|
| kb-1 SSG `kb/output/articles/index.html` | YES — next SSG re-export will reflect filter |
| kb-1 SSG `kb/output/index.html` Latest cards | YES |
| kb-1 SSG `kb/output/articles/{hash}.html` detail pages | NO (already-rendered files persist; future re-runs may skip filtered articles but existing files remain accessible) |
| kb-2 topic page article lists | YES |
| kb-2 entity page article lists | YES |
| kb-2 homepage Browse-by-Topic / Featured Entities counts | YES |
| kb-2 article detail related-entities + related-topics | YES (LINK-01 / LINK-02 — early-return [] for filtered-out source) |
| kb-3 `GET /api/articles` (when implemented) | YES (delegates to `list_articles`) |
| kb-3 `GET /api/article/{hash}` (when implemented) | NO (delegates to `get_article_by_hash` — carve-out preserved) |
| kb-3 `GET /api/search` (when implemented) | DECISION: apply filter by default, `KB_SEARCH_BYPASS_QUALITY=on` env override per DECISIONS doc |

## Deviations from PLAN

### Auto-fixed during execution

**1. [Rule 3 — Blocking issue] kb-1 baseline test fixture missing layer1/layer2 columns**

- **Found during:** Task 2, after applying schema guard
- **Issue:** `tests/unit/kb/test_article_query.py::fixture_conn` and `fixture_conn_prod_shape` both create their own in-memory schemas without `layer1_verdict` / `layer2_verdict` columns. Once Task 2 wired the schema guard into `list_articles`, every kb-1 test using those fixtures raised `RuntimeError: DATA-07 schema guard: table 'articles' missing columns ['layer1_verdict', 'layer2_verdict']`.
- **Fix:** Added the 2 columns to both kb-1 fixtures + tagged every existing row `layer1='candidate'` + `layer2='ok'`. Additive — no semantic change to kb-1 tests since they don't assert on verdict columns.
- **Files modified:** `tests/unit/kb/test_article_query.py` (the kb-1 test fixture file)

**2. [Rule 3 — Blocking issue] Read-only assertions broke when schema guard issued PRAGMA**

- **Found during:** Task 2, kb-1 + kb-2 read-only spy tests failed
- **Issue:** kb-1's `test_queries_are_read_only_no_mutation_sql` and kb-2's `test_topic_articles_read_only` + `test_kb2_queries_read_only` asserted `first_word == "SELECT"` (or SELECT/WITH). DATA-07 schema guard issues `PRAGMA table_info(...)`, which fails the assertion.
- **Fix:** Allowed `PRAGMA` alongside SELECT/WITH in the spy assertion. PRAGMA is read-only metadata access, not a mutation.
- **Files modified:** `tests/unit/kb/test_article_query.py`, `tests/unit/kb/test_kb2_queries.py`

**3. [Rule 1 — Bug] Module reload caused class-identity pollution across test files**

- **Found during:** Task 2 test verification, when running data07 + kb-2 tests together
- **Issue:** Plan's `<action>` block specified `importlib.reload(kb.data.article_query)` for env-override tests. After reload, `EntityCount` and `TopicSummary` are NEW class objects; kb-2 test file's `from kb.data.article_query import EntityCount` binding is stale. Subsequent kb-2 tests' `isinstance(r, EntityCount)` assertions failed because returned instances were of the NEW class.
- **Fix:** Replaced `importlib.reload` with `monkeypatch.setattr(article_query, "QUALITY_FILTER_ENABLED", True/False)` for all Task 2 tests. Kept import-time semantics tested via a helper function `_eval_quality_filter_env(env_value)` that reproduces the import-time expression without reloading.
- **Files modified:** `tests/unit/kb/test_data07_quality_filter.py`

These three are all classic Rule 1-3 fixes — caused directly by my changes
(schema guard added, filter applied, env-test reload pattern from plan).
None affect the design contract; all are surgical, reversible, well-documented.

### Workflow note: parallel-agent commit attribution

Task 1 work (env constant + schema guard + fragment constants + fixture
extension + 7 unit tests) was absorbed into the parallel `kb-3-03` agent's
commit (`53668ec feat(kb-3-03): add 20 locale keys + 2 SVG icons for kb-3
i18n foundation`) due to shared staging area on this worktree —
**the same scenario captured in 2026-05-11 lessons learned (lmc/lmx)**.
File contents are byte-identical to the spec; attribution is wrong.
Task 2 work (this commit `b307db8`) explicitly used `git add <files>` only
and was not affected.

## Self-Check: PASSED

- [x] kb/data/article_query.py exists with DATA-07 filter wired into 6 functions
- [x] tests/unit/kb/test_data07_quality_filter.py exists, 17 tests pass
- [x] tests/integration/kb/conftest.py extended with 4 negative rows
- [x] Commit b307db8 in `git log` (verified: `git log --oneline -3` shows it)
- [x] Skill invocation literals present in this SUMMARY (regex-matchable)
- [x] kb-1 + kb-2 baselines hold: 225/225 kb tests pass

## Files / Commits

- **Commit:** `b307db8` — feat(kb-3-02): apply DATA-07 content-quality filter to 6 list queries
- **Files modified:**
  - C:\Users\huxxha\Desktop\OmniGraph-Vault\kb\data\article_query.py (+79 lines)
  - C:\Users\huxxha\Desktop\OmniGraph-Vault\tests\integration\kb\conftest.py (+18 lines, via Task 1 absorbed in `53668ec`)
  - C:\Users\huxxha\Desktop\OmniGraph-Vault\tests\unit\kb\test_article_query.py (+25 / -8)
  - C:\Users\huxxha\Desktop\OmniGraph-Vault\tests\unit\kb\test_data07_quality_filter.py (NEW, 417 lines)
  - C:\Users\huxxha\Desktop\OmniGraph-Vault\tests\unit\kb\test_kb2_queries.py (+12 / -8)
