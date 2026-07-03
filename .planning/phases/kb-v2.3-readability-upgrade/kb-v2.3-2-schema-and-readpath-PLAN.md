---
phase: kb-v2.3-readability-upgrade
plan: 2
type: execute
wave: 2
depends_on: [kb-v2.3-1]
files_modified:
  - kb/data/migrations/009_add_body_rewritten_columns.sql
  - kb/data/article_query.py
  - tests/integration/kb/conftest.py
  - tests/unit/kb/test_article_query_body_rewritten.py
autonomous: true
requirements: [SCHEMA-009, READ-PATH-D14]
must_haves:
  truths:
    - "Migration 009 adds body_rewritten + rewritten_at to BOTH articles and rss_articles; running it is idempotent and non-breaking"
    - "get_article_body() returns body_rewritten when non-NULL, ABOVE filesystem final_content.md sources"
    - "All 8 SELECT sites in article_query.py (list x2 + get_by_hash x3 + topic x2 + entity x1) fetch body_rewritten so the API/SSG/topic/entity routes never silently return None"
    - "conftest.py fixtures include body_rewritten so tests exercise the real column, not _row_get None-fallback"
  artifacts:
    - path: "kb/data/migrations/009_add_body_rewritten_columns.sql"
      provides: "Additive ALTER TABLE for body_rewritten TEXT + rewritten_at DATETIME on both tables"
      contains: "ALTER TABLE articles ADD COLUMN body_rewritten TEXT"
    - path: "kb/data/article_query.py"
      provides: "body_rewritten field on ArticleRecord, D-14 prepend, 8 SELECT sites updated, both row converters updated"
      contains: "rec.body_rewritten"
    - path: "tests/integration/kb/conftest.py"
      provides: "body_rewritten + rewritten_at in both CREATE TABLE fixtures"
      contains: "body_rewritten TEXT"
    - path: "tests/unit/kb/test_article_query_body_rewritten.py"
      provides: "Test asserting body_rewritten wins over a seeded final_content.md"
  key_links:
    - from: "kb/data/article_query.py:get_article_body"
      to: "ArticleRecord.body_rewritten"
      via: "if rec.body_rewritten: return that BEFORE the final_content.md filesystem loop"
      pattern: "if rec\\.body_rewritten"
    - from: "kb/data/article_query.py:list_articles + get_article_by_hash SELECTs"
      to: "body_rewritten column"
      via: "append 'body_rewritten' (alias-qualified in topic/entity SELECTs) to all 8 SELECT column lists + _row_get in both converters"
      pattern: "body_rewritten"
---

<objective>
Add the display-only storage slot and wire the read path so a populated body_rewritten always wins. This is the schema + read-path atomic unit — migration 009, the D-14 precedence prepend, all 8 SELECT sites, both row converters, the ArticleRecord field, and the conftest fixtures — all in one plan because they are a single contract change (missing any one silently degrades to None).

Purpose: Without this, plan 03's cron would write body_rewritten but the API/SSG would never read it (get_article_by_hash has 3 SELECTs; missing any returns None — Pitfall 5), OR the filesystem final_content.md would shadow it for 70% of articles (the fatal flaw the storage-slot decision caught).

Output: A schema that both tables share, a read chain where body_rewritten is checked FIRST, and tests proving body_rewritten beats a seeded final_content.md.

**⚠️ CORRECTION NOTE (2026-07-03):** The storage-slot + read-path design in this plan is UNAFFECTED by the input-source correction. `body_rewritten` is still an additive TEXT NULL column checked FIRST in the D-14 chain. The ONLY correction that touches this plan is WORDING: `body_rewritten` is populated from the CLEANED D-14 DISPLAY content (what get_article_body returns pre-image-rewrite: final_content.enriched.md -> final_content.md -> body_cleaned -> body), NOT from raw DB `body`. This plan does not produce body_rewritten (plan 03 does) — it only stores + reads it — so the change here is limited to a clarifying comment/docstring so no downstream reader mistakenly assumes body_rewritten is a body-derivative. The D-14 read-path test (body_rewritten wins above final_content.md) is exactly right and unchanged.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-CONTEXT.md
@.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-RESEARCH.md
@kb/data/migrations/008_add_body_cleaned_columns.sql

<interfaces>
<!-- Exact code to modify. Line numbers verified against live code 2026-07-02. -->

kb/data/article_query.py ArticleRecord dataclass (frozen), current last two fields at lines 130-131:
```python
    body_cleaned: Optional[str] = None
    body_repositioned: Optional[str] = None
```

kb/data/article_query.py get_article_body() current chain (lines 602-619):
```python
    base_path = config.KB_BASE_PATH
    url_hash = resolve_url_hash(rec)
    images_dir = Path(config.KB_IMAGES_DIR)
    for fname in ("final_content.enriched.md", "final_content.md"):   # line 605
        p = images_dir / url_hash / fname
        if p.exists():
            md = p.read_text(encoding="utf-8")
            md = _strip_hermes_metadata_prefix(md)
            md = _strip_external_wechat_images(md)
            md = _rewrite_image_paths(md, base_path)
            md = _rewrite_image_text_refs_to_html(md)
            return md, "vision_enriched"
    body = rec.body_cleaned or rec.body or ""                          # line 615
    body = _strip_external_wechat_images(body)
    body = _rewrite_image_paths(body, base_path)
    body = _rewrite_image_text_refs_to_html(body)
    return body, "raw_markdown"                                        # line 619
```

kb/data/article_query.py — the 8 SELECT sites (verified line numbers 2026-07-02; CORRECTED from 5 per plan-checker Blocker 1):
- list_articles KOL (313-316): `... body_cleaned, body_repositioned FROM articles`
- list_articles RSS (328-333): `... body_cleaned FROM rss_articles`
- get_article_by_hash KOL direct (379-382): `... body_cleaned, body_repositioned FROM articles WHERE content_hash = ?`
- get_article_by_hash RSS direct (388-394): `... body_cleaned FROM rss_articles WHERE substr(content_hash,1,10)=?`
- get_article_by_hash KOL NULL-hash fallback (400-404): `... body_cleaned, body_repositioned FROM articles WHERE content_hash IS NULL`
- topic_articles_query KOL (841-844): `SELECT a.id, ... a.body_cleaned, a.body_repositioned FROM articles a JOIN classifications c ...` — uses `a.` alias
- topic_articles_query RSS (861-865): `SELECT r.id, ... r.body_cleaned FROM rss_articles r WHERE r.topics LIKE ...` — uses `r.` alias
- entity_articles_query KOL (916-919): `SELECT a.id, ... a.body_cleaned, a.body_repositioned FROM articles a JOIN extracted_entities e ...` — uses `a.` alias; NO RSS branch (extracted_entities KOL-only)

kb/data/article_query.py row converters (append after the existing last field):
- _row_to_record_kol (252): `body_repositioned=_row_get(row, "body_repositioned"),`
- _row_to_record_rss (273): `body_cleaned=_row_get(row, "body_cleaned"),`  (RSS has NO body_repositioned — keep asymmetry)

Migration 008 pattern (kb/data/migrations/008_add_body_cleaned_columns.sql):
```sql
ALTER TABLE articles ADD COLUMN body_cleaned TEXT;
ALTER TABLE articles ADD COLUMN body_repositioned TEXT;
ALTER TABLE rss_articles ADD COLUMN body_cleaned TEXT;
```

conftest.py CREATE TABLE last columns (lines 94-95 articles, 114 rss):
```sql
-- articles:  ... body_cleaned TEXT, body_repositioned TEXT
-- rss_articles: ... body_cleaned TEXT
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write migration 009 + update conftest.py fixtures (SAME commit — fixture parity)</name>
  <files>kb/data/migrations/009_add_body_rewritten_columns.sql, tests/integration/kb/conftest.py</files>
  <read_first>
    - kb/data/migrations/008_add_body_cleaned_columns.sql (the exact additive pattern to mirror)
    - kb/data/migrations/run_migrations.py (confirm PRAGMA table_info idempotency guard so re-run is safe)
    - tests/integration/kb/conftest.py (lines 78-115 — both CREATE TABLE blocks to update)
    - .planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-RESEARCH.md (Finding 4 migration shape, Finding 5 conftest columns, Pitfall 3 fixture drift)
    - CLAUDE.md (Behavior-Anchor section — "test fixture CREATE TABLE not synced with migration silently masks the downstream bug")
  </read_first>
  <action>
Create `kb/data/migrations/009_add_body_rewritten_columns.sql` with EXACTLY these four ALTER statements (additive, non-breaking, run_migrations.py guards via PRAGMA table_info):
```sql
-- 009: Add body_rewritten column for kb-v2.3 display-only LLM rewrite.
-- Additive, non-breaking, idempotent (run_migrations.py guards via PRAGMA table_info).
-- rewrite_body_cron.py writes clean bodies here. INPUT to the rewrite is the D-14-resolved
-- DISPLAY content (final_content.enriched.md -> final_content.md -> body_cleaned -> body),
-- NOT raw DB body (DB body has WeChat CDN URLs, not the localhost:8765 URLs the display carries).
-- get_article_body() D-14 chain checks body_rewritten FIRST, above filesystem final_content.md sources.
-- KG (LightRAG) ALWAYS uses original body; body_rewritten is display-only.
-- body_cleaned NOT reused (0-populated; shadowed by final_content.md for 70% of corpus).
-- See decision_rewrite_display_only_kg_uses_original.md (incl. "CRITICAL CORRECTION" section).
-- No backfill required (NULL is correct until plan-03 cron runs).
-- Rollback: ALTER TABLE <t> DROP COLUMN body_rewritten (SQLite >= 3.35).
ALTER TABLE articles ADD COLUMN body_rewritten TEXT;
ALTER TABLE articles ADD COLUMN rewritten_at DATETIME;
ALTER TABLE rss_articles ADD COLUMN body_rewritten TEXT;
ALTER TABLE rss_articles ADD COLUMN rewritten_at DATETIME;
```
Do NOT add body_repositioned to rss_articles (stays KOL-only — RESEARCH Finding 4 note).

In `tests/integration/kb/conftest.py`, add to the `articles` CREATE TABLE (after `body_repositioned TEXT` at line 95):
```sql
                body_rewritten TEXT,
                rewritten_at DATETIME
```
And to the `rss_articles` CREATE TABLE (after `body_cleaned TEXT` at line 114):
```sql
                body_rewritten TEXT,
                rewritten_at DATETIME
```
(Watch trailing commas — the previous last column needs a comma added when it becomes non-last.) Do NOT add body_repositioned to rss_articles fixture.

Both files MUST land in the SAME commit (Pitfall 3 fixture-drift discipline). Use `git add kb/data/migrations/009_add_body_rewritten_columns.sql tests/integration/kb/conftest.py` (explicit paths, never -A).
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/integration/kb/ -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "ADD COLUMN body_rewritten TEXT" kb/data/migrations/009_add_body_rewritten_columns.sql` == 2 (articles + rss_articles).
    - `grep -c "ADD COLUMN rewritten_at DATETIME" kb/data/migrations/009_add_body_rewritten_columns.sql` == 2.
    - `grep -c "body_repositioned" kb/data/migrations/009_add_body_rewritten_columns.sql` == 0 (not added to rss).
    - The migration comment states the rewrite INPUT is the D-14 display content, NOT raw body: `grep -iE "D-14|display content|localhost:8765|NOT raw" kb/data/migrations/009_add_body_rewritten_columns.sql` matches.
    - `grep -c "body_rewritten TEXT" tests/integration/kb/conftest.py` == 2 (both CREATE TABLE blocks).
    - Running migration 009 twice against a temp DB is idempotent (no error on second run — verify via run_migrations.py PRAGMA guard, or a quick script that applies twice).
    - `venv/Scripts/python.exe -m pytest tests/integration/kb/ -v` green (fixtures parse with new columns).
  </acceptance_criteria>
  <done>Migration 009 exists with 4 additive ALTERs (2 tables × body_rewritten+rewritten_at, no body_repositioned on rss) and a comment noting the input is D-14 display content (not raw body); conftest fixtures include body_rewritten+rewritten_at in both tables; integration suite green; both files in one commit.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add body_rewritten to ArticleRecord + all 8 SELECT sites + both row converters + D-14 prepend</name>
  <files>kb/data/article_query.py, tests/unit/kb/test_article_query_body_rewritten.py</files>
  <read_first>
    - kb/data/article_query.py (lines 97-131 dataclass, 237-274 converters, 305-343 list_articles SELECTs, 352-412 get_article_by_hash 3 SELECTs, 831-878 topic_articles_query 2 SELECTs, 900-929 entity_articles_query 1 KOL SELECT, 587-619 get_article_body D-14 chain)
    - .planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-RESEARCH.md (Finding 2 exact D-14 edit, Finding 3 dataclass+SELECTs, Finding 9 full SELECT audit table, Pitfall 1 & 5)
    - tests/unit/kb/ (existing test layout — where test_article_query_body_rewritten.py goes; confirm dir exists or create it)
  </read_first>
  <behavior>
    - Test 1 (D14-REWRITTEN-WINS): seed an ArticleRecord with body_rewritten set AND write a final_content.md on disk for its hash; get_article_body() returns the body_rewritten content (image-rewritten), NOT the file content.
    - Test 2 (D14-NULL-FALLTHROUGH): body_rewritten=None + final_content.md on disk -> returns the file content ("vision_enriched") — unchanged legacy behavior.
    - Test 3 (D14-NULL-NO-FILE): body_rewritten=None + no file -> returns rec.body_cleaned or rec.body ("raw_markdown") — unchanged legacy behavior.
    - Test 4 (SELECT-ROUNDTRIP): insert a row with body_rewritten via list_articles/get_article_by_hash against the conftest fixture DB -> the returned ArticleRecord.body_rewritten is populated (proves the SELECT + converter carry the column).
    - Test 5 (IMAGE-REWRITE-APPLIED): the body_rewritten path still applies _rewrite_image_paths (localhost:8765 -> KB_BASE_PATH/static/img) so images render. NOTE this is the READ path applying the rewrite AT DISPLAY TIME — the STORED body_rewritten keeps raw localhost:8765 URLs (that is what plan-03's cron writes, mirroring how final_content.md stores raw localhost URLs).
    - Test 6 (TOPIC-ENTITY-ROUNDTRIP): seed a KOL row with body_rewritten + a classifications row + an extracted_entities row (freq >= min_freq) in the fixture DB; topic_articles_query() AND entity_articles_query() each return an ArticleRecord whose body_rewritten is populated (proves the 3 topic/entity SELECTs + alias-qualified column carry it). If the fixture lacks classifications/extracted_entities tables, extend the conftest fixture minimally to seed them (guard against fixture drift — CLAUDE.md behavior-anchor lesson).
  </behavior>
  <action>
In `kb/data/article_query.py`:

1. Dataclass (after line 131 `body_repositioned: Optional[str] = None`):
   ```python
   body_rewritten: Optional[str] = None    # kb-v2.3 display-only LLM rewrite of the D-14 display content (wins over filesystem)
   ```
   Also add the field to the docstring Attributes list, noting it is derived from the cleaned D-14 DISPLAY content (final_content.md etc.), NOT from raw body.

2. get_article_body() — insert BEFORE the filesystem loop (before line 605). Concrete edit:
   ```python
   base_path = config.KB_BASE_PATH
   url_hash = resolve_url_hash(rec)
   images_dir = Path(config.KB_IMAGES_DIR)
   # kb-v2.3: body_rewritten (display-only LLM rewrite of the D-14 display content) wins
   # over ALL filesystem sources. It stores raw localhost:8765 URLs (like final_content.md),
   # so the same image-path rewrite applies here at read time.
   if rec.body_rewritten:
       body = rec.body_rewritten
       body = _strip_external_wechat_images(body)   # kb-v2.2-9
       body = _rewrite_image_paths(body, base_path)
       body = _rewrite_image_text_refs_to_html(body)  # kb-v2.1-6
       return body, "raw_markdown"
   for fname in ("final_content.enriched.md", "final_content.md"):
       ...  # unchanged
   ```
   Use the `"raw_markdown"` BodySource tag (zero new type — RESEARCH Finding 2 recommendation). Also update the get_article_body docstring resolution-order list to show body_rewritten as step 0/1 and note it is the cleaned display content.

3. Append `body_rewritten` to ALL 8 SELECT column lists (RESEARCH Finding 9 CORRECTED table — the topic/entity SELECTs use `a.`/`r.` table aliases, so the added column MUST be alias-qualified there):
   - list_articles KOL (line ~315): `"body_cleaned, body_repositioned, body_rewritten "`
   - list_articles RSS (line ~332): `"body_cleaned, body_rewritten "`
   - get_article_by_hash KOL direct (line ~381): `"body_cleaned, body_repositioned, body_rewritten "`
   - get_article_by_hash RSS direct (line ~392): `"body_cleaned, body_rewritten "`
   - get_article_by_hash KOL NULL-hash fallback (line ~403): `"body_cleaned, body_repositioned, body_rewritten "`
   - topic_articles_query KOL sql_kol (line ~844): change `"a.body_cleaned, a.body_repositioned "` to `"a.body_cleaned, a.body_repositioned, a.body_rewritten "`
   - topic_articles_query RSS sql_rss (line ~865): change `"r.body_cleaned "` to `"r.body_cleaned, r.body_rewritten "`
   - entity_articles_query KOL sql_kol (line ~919): change `"a.body_cleaned, a.body_repositioned "` to `"a.body_cleaned, a.body_repositioned, a.body_rewritten "`
   NOTE: entity_articles_query has NO RSS branch (extracted_entities is KOL-only) — do NOT add one. These 3 sites feed the topic-browse (/topic/{slug}) and entity-search (/entity/{slug}) routes; missing any leaves those routes silently returning body_rewritten=None (Pitfall 5).

4. Both row converters:
   - `_row_to_record_kol` (after line 252): `body_rewritten=_row_get(row, "body_rewritten"),`
   - `_row_to_record_rss` (after line 273): `body_rewritten=_row_get(row, "body_rewritten"),`

Create `tests/unit/kb/test_article_query_body_rewritten.py` implementing behavior tests 1-5 (+ Test 6). Use tmp_path for the seeded final_content.md and monkeypatch config.KB_IMAGES_DIR; use the conftest in-memory fixture DB for the SELECT-roundtrip test. Use `git add kb/data/article_query.py tests/unit/kb/test_article_query_body_rewritten.py` (explicit paths, never -A).
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/kb/test_article_query_body_rewritten.py tests/integration/kb/ -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "body_rewritten" kb/data/article_query.py` >= 12 (1 dataclass field + 8 SELECTs + 2 converters + 1 D-14 prepend + docstring mentions; a raw count is a WEAK check — the per-site enumeration below is authoritative).
    - `grep -c "if rec.body_rewritten" kb/data/article_query.py` == 1 (the D-14 prepend).
    - The `if rec.body_rewritten:` block appears BEFORE the `for fname in ("final_content.enriched.md", "final_content.md"):` loop (verify by line order — grep -n and confirm the if-line number < the for-line number).
    - ALL 8 SELECT sites carry body_rewritten (per-site enumeration — the raw count above passes silently even when the 3 topic/entity sites are missing, so verify EACH explicitly via `grep -n`):
      1. list_articles KOL SELECT (~313-316) contains `body_rewritten`.
      2. list_articles RSS SELECT (~328-333) contains `body_rewritten`.
      3. get_article_by_hash KOL direct (~379-382) contains `body_rewritten`.
      4. get_article_by_hash RSS direct (~388-394) contains `body_rewritten`.
      5. get_article_by_hash KOL NULL-hash fallback (~400-404) contains `body_rewritten`.
      6. topic_articles_query KOL sql_kol (~841-844) contains `a.body_rewritten`.
      7. topic_articles_query RSS sql_rss (~861-865) contains `r.body_rewritten`.
      8. entity_articles_query KOL sql_kol (~916-919) contains `a.body_rewritten`.
      Automated aggregate check: `grep -cE "(a\.body_rewritten|r\.body_rewritten|body_rewritten )" kb/data/article_query.py` >= 8 SELECT occurrences (excluding the dataclass field / converters / D-14 lines) — cross-check against the 8-item list above via `grep -n`.
    - The Test 6 (TOPIC-ENTITY-ROUNDTRIP) behavior test passes, proving the topic-browse + entity-search routes carry body_rewritten (not just list/hash).
    - `venv/Scripts/python.exe -m pytest tests/unit/kb/test_article_query_body_rewritten.py -v` — all behavior tests pass, including D14-REWRITTEN-WINS (body_rewritten beats a seeded final_content.md).
    - Full integration suite still green: `venv/Scripts/python.exe -m pytest tests/integration/kb/ -v`.
  </acceptance_criteria>
  <done>ArticleRecord has body_rewritten (documented as cleaned D-14 display content); get_article_body checks it FIRST above filesystem; all 8 SELECTs (list x2 + hash x3 + topic x2 + entity x1) + both converters carry it; the D14-REWRITTEN-WINS + TOPIC-ENTITY-ROUNDTRIP tests prove precedence and topic/entity-route coverage; unit + integration suites green.</done>
</task>

</tasks>

<verification>
- Migration 009 additive + idempotent; conftest fixtures parity; integration suite green.
- get_article_body returns body_rewritten (image-rewritten at read time) above filesystem when non-NULL — proven by D14-REWRITTEN-WINS test.
- All 8 SELECT sites + both row converters + dataclass carry body_rewritten (no silent None).
- `venv/Scripts/python.exe -m pytest tests/unit/kb/ tests/integration/kb/ -v` green.
</verification>

<success_criteria>
CONTEXT.md Stage 1 gates satisfied:
- "Schema: migration 009 adds body_rewritten TEXT to articles AND rss_articles; conftest fixtures updated; pytest tests/integration/kb/ green."
- "Read path: get_article_body() returns body_rewritten when non-NULL, ABOVE filesystem sources — provable by a test that seeds body_rewritten + a final_content.md and asserts body_rewritten wins."
- body_rewritten is documented (dataclass docstring + migration comment) as the cleaned D-14 DISPLAY content, not a raw-body derivative.
</success_criteria>

<output>
After completion, create `.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-2-schema-and-readpath-SUMMARY.md`.
</output>
