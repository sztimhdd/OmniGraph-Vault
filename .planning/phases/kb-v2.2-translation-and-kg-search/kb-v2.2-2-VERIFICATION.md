# kb-v2.2-2 Verification: Bidirectional Article Translation (F1')

**Phase:** kb-v2.2-2  
**Feature:** Bidirectional Article Translation  
**Verified:** 2026-05-18  
**Status:** ✅ COMPLETE

---

## Acceptance Criteria

| REQ | Criterion | Status |
|-----|-----------|--------|
| F1'-1 | Translation columns added to `articles` table via idempotent migration | ✅ |
| F1'-2 | `translate_article()` enforces DATA-07: only `layer1_verdict='candidate'` eligible | ✅ |
| F1'-3 | Same-language guard: returns `same_lang` error, no LLM call | ✅ |
| F1'-4 | Idempotency: already-translated article returns ok without re-calling LLM | ✅ |
| F1'-5 | NULL `content_hash` fallback: match via runtime `md5(body)[:10]` | ✅ |
| F1'-6 | `POST /api/translate/{hash}?target_lang=` → 202 + job_id | ✅ |
| F1'-7 | `GET /api/translate/{hash}` → `{status, translated_lang}` (not_translated / done) | ✅ |
| F1'-8 | `GET /api/article/{hash}?lang=en` → translated fields when translation exists | ✅ |
| F1'-9 | Article template shows "Read in English" / "阅读中文" toggle (wechat source only) | ✅ |
| F1'-10 | JS toggle: POST translate → poll until done → swap title + body in-place | ✅ |
| F1'-11 | Toggle back: reverts to original content without re-fetching | ✅ |
| F1'-12 | 422 on `POST /api/translate/{hash}` without `?target_lang=` | ✅ |

---

## Test Results

### Unit Tests — `tests/unit/kb/test_translation_service.py`

All 11 tests pass:

| Test | Result |
|------|--------|
| `test_translate_result_ok_fields` | ✅ |
| `test_translate_result_error_fields` | ✅ |
| `test_translate_article_not_found` | ✅ |
| `test_translate_article_not_eligible` | ✅ |
| `test_translate_article_same_lang` | ✅ |
| `test_translate_article_idempotent_no_llm_call` | ✅ |
| `test_translate_article_success_stores_to_db` | ✅ |
| `test_translate_article_null_hash_fallback` | ✅ |
| `test_strip_llm_wrapper_removes_translation_prefix` | ✅ |
| `test_strip_llm_wrapper_removes_surrounding_quotes` | ✅ |
| `test_strip_llm_wrapper_passthrough` | ✅ |

### Integration Tests — `tests/integration/kb/test_translation_endpoint.py`

All 8 tests pass:

| Test | Result |
|------|--------|
| `test_translate_missing_target_lang_returns_422` | ✅ |
| `test_translate_post_returns_202_and_job_id` | ✅ |
| `test_translate_background_task_stores_translation` | ✅ |
| `test_get_translate_status_before_translation` | ✅ |
| `test_get_translate_status_after_translation` | ✅ |
| `test_article_endpoint_returns_translated_fields_when_lang_matches` | ✅ |
| `test_article_endpoint_no_translation_fields_without_lang` | ✅ |
| `test_data07_rejected_article_translation_not_stored` | ✅ |

**Total new tests: 19 (11 unit + 8 integration)**  
**Total suite: 532 tests passing**

---

## Files Delivered

| File | Type | Description |
|------|------|-------------|
| `kb/data/migrations/006_add_translation_columns.sql` | New | Adds 4 columns to `articles` table |
| `kb/data/migrations/run_migrations.py` | Modified | Added `_strip_sql_comments()` bug fix |
| `kb/services/translation.py` | New | `TranslateResult` dataclass + `translate_article()` service |
| `kb/api_routers/articles.py` | Modified | `?lang=` on GET article; POST/GET `/api/translate/{hash}` |
| `kb/templates/article.html` | Modified | Toggle button + JS polling/swap logic |
| `tests/unit/kb/test_translation_service.py` | New | 11 unit tests |
| `tests/integration/kb/test_translation_endpoint.py` | New | 8 integration tests |
| `tests/integration/kb/conftest.py` | Modified | Added 4 translation columns to fixture schema |

---

## Local UAT

**Launcher:** `venv/Scripts/python.exe .scratch/local_serve.py` (port 8766)  
**DB:** `.dev-runtime/data/kol_scan.db` with UAT translation row pre-seeded for article `5a362bf61e`

### Migration Smoke

```
Applying 006_add_translation_columns.sql ...
  OK: ALTER TABLE articles ADD COLUMN body_translated TEXT
  SKIP (already exists): articles.title_translated
  SKIP (already exists): articles.translated_lang
  SKIP (already exists): articles.translated_at
```

Idempotency confirmed (2nd run all SKIP).

### API Smoke

```
GET /health → 200 {"status":"ok"}
GET /api/article/5a362bf61e → 200 (original fields, translated_lang=null)
GET /api/article/5a362bf61e?lang=en → 200 {translated_lang:"en", translated_title:"AI Technology Progress — UAT Translation", translated_body_html:"<h2>..."}
POST /api/translate/5a362bf61e?target_lang=en → 202 {job_id:..., target_lang:"en"}
GET /api/translate/5a362bf61e → 200 {status:"done", translated_lang:"en"}
POST /api/translate/abc1234 → 422 (missing target_lang)
```

### Browser UAT Screenshots

- **Before toggle:** `.playwright-mcp/f1-prime-uat-01.png`
  - Shows original zh-CN title with "Read in English" button
- **After toggle:** `.playwright-mcp/f1-prime-uat-02.png`
  - Title: "AI Technology Progress — UAT Translation"
  - Button: "阅读中文" (correctly flipped to back-label)
  - Body: English translated content rendered in article body
  - Related entities sidebar intact (Anthropic, LLM, OpenAI, Claude Code, MCP)

---

## Bug Fixed During Implementation

**`run_migrations.py` SQL comment stripping:** The original code used `stmt.startswith("--")` after `stmt.strip()` to skip empty/comment statements. When SQL files begin with block comments before the first DDL statement, the entire first statement (including the real DDL) was skipped. Fixed by adding `_strip_sql_comments()` which strips `--` lines from each statement fragment before checking if it's empty. This allowed all 4 `ALTER TABLE ADD COLUMN` statements to execute correctly.
