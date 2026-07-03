---
plan: kb-v2.3-2-schema-and-readpath
status: complete
completed: 2026-07-03
commits:
  - 6290393  # migration 009 + conftest parity
  - 9f2d8b7  # article_query D-14 prepend + 8 SELECTs + converters + tests
---

# kb-v2.3-2 Schema + Read Path — SUMMARY

## What was built

**Migration 009** (`kb/data/migrations/009_add_body_rewritten_columns.sql`): 4 additive
ALTERs — `body_rewritten TEXT` + `rewritten_at DATETIME` on BOTH `articles` and
`rss_articles`. Idempotent via `run_migrations._apply_sql` PRAGMA guard (verified by
apply-twice: RUN1 all OK, RUN2 all SKIP). No `body_repositioned` added to rss (KOL-only,
preserved asymmetry). Comment documents the rewrite INPUT is D-14 display content, NOT raw body.

**Read path** (`kb/data/article_query.py`):
- `ArticleRecord.body_rewritten` field added (documented as clean D-14 display content, not raw-body derived).
- `get_article_body()` D-14 prepend: `if rec.body_rewritten:` returns it (with read-time
  `_strip_external_wechat_images` + `_rewrite_image_paths` + `_rewrite_image_text_refs_to_html`)
  BEFORE the `final_content.enriched.md`/`final_content.md` filesystem loop. Verified: if-line 615 < for-line 623.
- All **8 SELECT sites** carry `body_rewritten` (list KOL+RSS, get_article_by_hash KOL-direct
  + RSS-direct + KOL-null-fallback, topic KOL `a.` + RSS `r.`, entity KOL `a.`).
- Both row converters (`_row_to_record_kol`, `_row_to_record_rss`) fetch it via `_row_get`.

**Tests** (`tests/unit/kb/test_article_query_body_rewritten.py`, 9 tests): D14-REWRITTEN-WINS
(body_rewritten beats a seeded final_content.md), NULL-fallthrough, NULL-no-file,
image-rewrite-at-read-time, + SELECT-roundtrip across list / hash-KOL / hash-RSS / topic
(KOL+RSS) / entity routes.

## Verification evidence

- `venv/Scripts/python.exe -m pytest tests/unit/kb/ -q` → **327 passed**.
- Migration idempotency: real `_apply_sql` apply-twice → RUN2 all `SKIP (already exists)`, both tables have both columns.
- D-14 precedence proven by D14-REWRITTEN-WINS test (body_rewritten wins over on-disk final_content.md).
- All 8 SELECT sites confirmed via `grep -n body_rewritten kb/data/article_query.py` (16 total occurrences).

## Deviations / issues surfaced

1. **Fixture-drift sweep required beyond the plan.** The plan named only
   `tests/integration/kb/conftest.py`. Running the suite exposed inline CREATE TABLE fixtures
   in THREE more files (`test_article_query.py`, `test_data07_quality_filter.py`,
   `test_translation_fields_surfaced.py`) that also needed `body_rewritten`+`rewritten_at`,
   plus 4 positional `INSERT ... VALUES` that needed 2 trailing NULLs. This is exactly the
   CLAUDE.md behavior-anchor fixture-drift lesson — fixed all, 327/327 green.
2. **Migration comment SQL-splitter bug (caught + fixed pre-commit).** The first draft's comment
   prose contained inline `;` and `()`, which `run_migrations._apply_sql`'s naive `sql.split(";")`
   split mid-comment → `sqlite3.OperationalError: syntax error`. Would have crashed the migration
   on Aliyun. Rewrote comment prose to avoid `;`/`()` (matches migration 008's discipline).
3. **3 pre-existing integration failures** (`test_ssg_export_data_lang` x2, `test_export`
   og_description_fallback) confirmed failing IDENTICALLY on a clean `git stash` tree — NOT
   introduced by this plan. Filed for ISSUES.md.
