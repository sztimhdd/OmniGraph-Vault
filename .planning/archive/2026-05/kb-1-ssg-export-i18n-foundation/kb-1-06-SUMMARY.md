---
phase: kb-1-ssg-export-i18n-foundation
plan: "06"
subsystem: kb
tags: [kb-v2, data-layer, article-query, sqlite, dataclass, read-only, EXPORT-04, EXPORT-05]
dependency-graph:
  requires:
    - kb-1-01 (kb.config — KB_DB_PATH + KB_IMAGES_DIR)
    - kb-1-02 (articles.lang + rss_articles.lang columns)
  provides:
    - "kb.data.article_query.ArticleRecord — frozen dataclass row representation"
    - "kb.data.article_query.list_articles — paginated/filtered list across both tables"
    - "kb.data.article_query.get_article_by_hash — resolve md5[:10] -> record (slow-path NULL fallback)"
    - "kb.data.article_query.resolve_url_hash — pure 3-branch DATA-06 hash resolver"
    - "kb.data.article_query.get_article_body — D-14 fallback chain + EXPORT-05 image rewrite"
  affects:
    - "kb-1-09 (export driver) imports all 5 public functions"
    - "kb-3 API (kb/api.py) reuses the same functions for /api/articles + /api/article/{hash}"
tech-stack:
  added: []
  patterns:
    - "@dataclass(frozen=True) for immutable record types (per common/coding-style.md)"
    - "Optional conn= kwarg for test injection — avoids touching production DB during unit tests"
    - "Read-only SQLite URI ('file:...?mode=ro') for production connections"
    - "SpyConn proxy class for SELECT-only enforcement (avoids attribute-write restriction on sqlite3.Connection in CPython 3.13 — same idiom as kb-1-02 test_migrate_lang_column.py)"
key-files:
  created:
    - "kb/data/article_query.py"
    - "tests/unit/kb/test_article_query.py"
  modified: []
decisions:
  - "RSS update_time normalization: prefer published_at, else fetched_at (production schema has both columns; published_at is the user-meaningful timestamp)"
  - "list_articles uses merge-sort across the two table queries instead of UNION ALL — simpler SQL, cheaper to reason about, and avoids needing to fabricate matching column lists across schemas with different time-column names"
  - "Optional conn= kwarg for test injection: when omitted, _connect() opens a read-only SQLite URI; in tests an in-memory connection is passed directly. Pattern matches kb-1-02's SpyConn approach"
  - "Test count is 24 (plan target was 23): test 3 in plan ('source filter') was split into 3a (wechat-only) + 3b (rss-only) for cleaner asserts. Same coverage; one additional test name."
metrics:
  duration: "~15 minutes"
  tasks-completed: 3
  tests-added: 24
  tests-passing: 24
  commits: 6
  loc-prod: 252
  loc-tests: 421
  completed: "2026-05-12"
requirements: [DATA-04, DATA-05, DATA-06]
---

# Phase kb-1 Plan 06: Article Query Data Layer Summary

Read-only `kb/data/article_query.py` module providing the five public functions the SSG export driver (kb-1-09) and the kb-3 FastAPI handlers will both consume — `ArticleRecord` (frozen dataclass), `list_articles`, `get_article_by_hash`, `resolve_url_hash`, `get_article_body`.

## What Was Built

### `kb/data/article_query.py` (252 LOC)

Five public exports plus two private row-mapper helpers (`_row_to_record_kol`, `_row_to_record_rss`) and a private `_connect()` that opens a read-only SQLite URI (`file:{KB_DB_PATH}?mode=ro`).

| Function | REQ | Behavior |
|---|---|---|
| `ArticleRecord` | DATA-04/05/06 | `@dataclass(frozen=True)` with 9 fields including normalized `update_time` and optional `publish_time` |
| `resolve_url_hash(rec)` | DATA-06 | Pure 3-branch tree: KOL+hash→use it, KOL+NULL→md5(body)[:10], RSS→content_hash[:10]; raises ValueError on unknown source. **No DB, no filesystem.** |
| `list_articles(lang, source, limit, offset, conn=None)` | DATA-04 | Queries `articles` + `rss_articles`, merge-sorts by `update_time` DESC, applies offset/limit. Honors lang+source filters; RSS path coalesces `published_at` → `fetched_at`. |
| `get_article_by_hash(hash, conn=None)` | DATA-05 | 3-tier resolution: direct KOL match → `substr(rss.content_hash,1,10)` → walk NULL-hash KOL rows computing `md5(body)[:10]`. Returns `None` on miss. |
| `get_article_body(rec)` | EXPORT-04 + EXPORT-05 | D-14 fallback chain: `final_content.enriched.md` → `final_content.md` → `rec.body`; applies `http://localhost:8765/` → `/static/img/` regex rewrite at read time; returns `(body, body_source)` tuple where `body_source ∈ {'vision_enriched','raw_markdown'}`. |

## Tests

**24 tests, 24 passing** (`tests/unit/kb/test_article_query.py`):

| Section | Count | Coverage |
|---|---|---|
| Task 1: ArticleRecord + resolve_url_hash | 6 | frozen-dataclass enforcement; 3 source/hash branches; ValueError on unknown source; pure-function check (works with broken config paths) |
| Task 2: list_articles + get_article_by_hash | 11 | both tables merged sort; lang filter; source=wechat-only; source=rss-only; pagination; combined filters; KOL direct hash; RSS truncate-substr match; missing returns None; KOL NULL-hash fallback; SpyConn read-only enforcement |
| Task 3: get_article_body | 7 | enriched preferred; final_content.md fallback; DB body fallback; empty-everywhere returns ('', 'raw_markdown'); image rewrite single; no-rewrite-without-prefix; rewrite-all-occurrences |
| **Total** | **24** | All pass; runtime 0.18s |

```
tests/unit/kb/test_article_query.py ........................        [100%]
============================= 24 passed in 0.18s ==============================
```

Full kb suite (config + lang_detect + migrate + i18n + article_query): **65/65 pass**.

## Read-Only Proof (EXPORT-02)

**Negative grep on the production module:**

```bash
grep -E "INSERT INTO|UPDATE |DELETE FROM" kb/data/article_query.py
# (no matches)
```

**Positive proof — SpyConn test enforcement** (`test_queries_are_read_only_no_mutation_sql`): wraps the test connection with a proxy that captures every SQL string passed to `.execute()`, then asserts every captured statement starts with `SELECT`. Run during pytest covers both `list_articles` (with various filters) and `get_article_by_hash` (3 hash inputs covering all three resolution tiers).

## Verification Evidence

```
$ venv/Scripts/python -c "from kb.data.article_query import ArticleRecord, list_articles, get_article_by_hash, resolve_url_hash, get_article_body; print('5 exports OK')"
5 exports OK

$ venv/Scripts/python -c "from kb.data.article_query import ArticleRecord, resolve_url_hash; r=ArticleRecord(id=1, source='wechat', title='t', url='u', body='hello', content_hash=None, lang=None, update_time='2026-01-01'); print(resolve_url_hash(r))"
5d41402abc

$ grep -n "mode=ro" kb/data/article_query.py
82:    uri = f"file:{config.KB_DB_PATH}?mode=ro"

$ grep -n "_IMAGE_SERVER_REWRITE\|/static/img/\|final_content\.enriched\.md" kb/data/article_query.py
225:_IMAGE_SERVER_REWRITE = re.compile(r"http://localhost:8765/")
232:        1. {KB_IMAGES_DIR}/{hash}/final_content.enriched.md  -> 'vision_enriched'
237:        'http://localhost:8765/' -> '/static/img/'
244:    for fname in ("final_content.enriched.md", "final_content.md"):
248:            md = _IMAGE_SERVER_REWRITE.sub("/static/img/", md)
251:    body = _IMAGE_SERVER_REWRITE.sub("/static/img/", body)
```

## All Five Public Exports

```python
from kb.data.article_query import (
    ArticleRecord,        # frozen dataclass
    list_articles,        # DATA-04
    get_article_by_hash,  # DATA-05
    resolve_url_hash,     # DATA-06 (pure)
    get_article_body,     # EXPORT-04 + EXPORT-05
)
```

## Commits

| # | Hash | Type | Description |
|---|------|------|-------------|
| 1 | `0dbb670` | test | add failing tests for ArticleRecord + resolve_url_hash (TDD RED) |
| 2 | `0b0eb16` | feat | implement ArticleRecord dataclass + resolve_url_hash (TDD GREEN) |
| 3 | `735cf5f` | test | add failing tests for list_articles + get_article_by_hash (TDD RED) |
| 4 | `b591c83` | feat | implement list_articles + get_article_by_hash (TDD GREEN) |
| 5 | `b41ee95` | test | add failing tests for get_article_body D-14 + EXPORT-05 (TDD RED) |
| 6 | `ccbc608` | feat | implement get_article_body D-14 fallback + EXPORT-05 rewrite (TDD GREEN) |

Six commits, three TDD cycles (RED → GREEN per task), no REFACTOR commits needed.

## Deviations from Plan

### Auto-fixed Issues

None — plan ran cleanly. No Rule-1/2/3 fixes were needed.

### Minor Plan Adaptations (no functional change)

**1. Test count: 24 vs plan target 23.** The plan listed Test 3 as a single test ("`source='wechat'` returns only KOL; `source='rss'` returns only rss_articles"). I split it into two named tests (`test_list_articles_filter_by_source_wechat_only` and `test_list_articles_filter_by_source_rss_only`) for cleaner failure messages — each asserts a single source. Same coverage, one extra test name. Plan acceptance criterion was "≥ 16 tests pass" / "≥ 23 tests pass" — both exceeded.

**2. SpyConn pattern mirrors kb-1-02.** The plan suggested using `unittest.mock.patch.object` on `conn.execute`. CPython 3.13 makes `sqlite3.Connection.execute` read-only (same constraint kb-1-02 hit per its lesson 2). I used the SpyConn proxy idiom kb-1-02 already established — owns its own `execute()`, delegates to `_real.execute()` via `__getattr__`. This is consistent with the existing project pattern and not a deviation in spirit.

**3. RSS update_time test data uses 32-char hashes.** The plan's `test_get_article_by_hash_rss_truncated_match` uses `e2a95c834a47f0f64c8e5826b5c3b9ab` (the exact full md5 from the plan), and confirms `get_article_by_hash("e2a95c834a", ...)` matches via `substr(content_hash, 1, 10)`. To make `test_list_articles_filter_by_lang_en` work cleanly I padded one fixture hash to exactly 32 chars (`"abcdef0000111122223333444455556666"[:32]`). Doesn't affect any assertion.

### Authentication Gates

None encountered — module is pure unit-test scope, no external API calls.

## Acceptance Criteria — All Met

### Task 1
- [x] `kb/data/article_query.py` exists with `@dataclass(frozen=True)` decorator (line 28)
- [x] File contains string `class ArticleRecord:` (line 29)
- [x] File contains string `def resolve_url_hash` (line 55)
- [x] `pytest -k "resolve_url_hash or ArticleRecord or frozen"` exits 0 with 6 tests passing
- [x] Smoke `python -c "...resolve_url_hash..."` outputs 10-char hex string `5d41402abc`

### Task 2
- [x] `pytest tests/unit/kb/test_article_query.py -v` exits 0 (17 tests at end of Task 2; final 24 at end of Task 3)
- [x] File contains string `def list_articles` (line 116)
- [x] File contains string `def get_article_by_hash` (line 172)
- [x] File contains string `mode=ro` (line 82)
- [x] No `INSERT|UPDATE|DELETE` SQL keyword (`grep -E "execute\(.*(INSERT|UPDATE|DELETE)"` returns 0)
- [x] Smoke import `python -c "from kb.data.article_query import list_articles, get_article_by_hash; print('OK')"` exits 0

### Task 3
- [x] `pytest tests/unit/kb/test_article_query.py -v` exits 0 with 24 tests passing (≥ 23)
- [x] File contains string `def get_article_body` (line 228)
- [x] File contains string `final_content.enriched.md` (lines 232, 244)
- [x] File contains string `_IMAGE_SERVER_REWRITE` (lines 225, 248, 251)
- [x] File contains string `/static/img/` (lines 237, 248, 251)
- [x] Smoke import `python -c "from kb.data.article_query import get_article_body; print('OK')"` exits 0
- [x] Negative grep `grep "INSERT INTO\|UPDATE\|DELETE FROM" kb/data/article_query.py` returns 0 hits — entire file read-only

## Requirements Satisfied

- **DATA-04**: `list_articles(lang=None, source=None, limit=20, offset=0)` with paginated `ArticleRecord` list sorted by `update_time DESC` — both tables merged ✓
- **DATA-05**: `get_article_by_hash(hash)` resolving `md5[:10]` across `articles` + `rss_articles`, including NULL-hash KOL fallback ✓
- **DATA-06**: `resolve_url_hash(rec)` 3-branch decision tree (KOL+hash, KOL+NULL md5(body)[:10], RSS truncate to 10) — pure function, no DB writes ✓

Plan also delivered EXPORT-04 (D-14 fallback chain) and EXPORT-05 (image URL rewrite at read time) infrastructure inside `get_article_body` — those REQs remain "Not started" in the traceability table because export_knowledge_base.py (kb-1-09) is the one that wires them into HTML output. This module provides the function the export driver will call.

## Self-Check: PASSED

- File `kb/data/article_query.py` exists: FOUND
- File `tests/unit/kb/test_article_query.py` exists: FOUND
- Commit `0dbb670` (Task 1 RED): FOUND
- Commit `0b0eb16` (Task 1 GREEN): FOUND
- Commit `735cf5f` (Task 2 RED): FOUND
- Commit `b591c83` (Task 2 GREEN): FOUND
- Commit `b41ee95` (Task 3 RED): FOUND
- Commit `ccbc608` (Task 3 GREEN): FOUND
- All 24 unit tests pass: VERIFIED
- All 65 kb-suite tests pass (no regressions): VERIFIED
