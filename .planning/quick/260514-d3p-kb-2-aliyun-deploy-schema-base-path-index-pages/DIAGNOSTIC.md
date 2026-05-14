# 2026-05-14 Aliyun ECS Deploy Diagnostic — kb-2 Production Defects

**Source:** Aliyun ECS deploy at `http://101.133.154.49/kb/`
**Reported by:** OmniGraph operator (Hai Hu) 2026-05-14
**Verified against:** Hermes prod via SSH 2026-05-14 + `.dev-runtime/data/kol_scan.db` SCP'd from Hermes

---

## Issue 1 — Schema mismatch (CRITICAL)

Every kb-2 query SQL-errors against the real production schema.

### What's wrong

`kb/data/article_query.py` and `kb/export_knowledge_base.py` reference columns that **do not exist** in production:

- `extracted_entities.name` → actual column is `entity_name`
- `extracted_entities.source` → column does not exist (RSS has no entity extraction)
- `classifications.source` → column does not exist (classifications is KOL-only)

### Why it wasn't caught locally

The kb-2 test fixture at `tests/integration/kb/conftest.py:84-99` defined an **imagined schema** with these columns:

```sql
CREATE TABLE classifications (..., source TEXT NOT NULL CHECK(source IN ('wechat','rss')), ...);
CREATE TABLE extracted_entities (..., source TEXT NOT NULL ..., name TEXT NOT NULL, ...);
```

Because the fixture and the SQL were written from the same false mental model, all 19 kb-2 unit tests + 8 integration tests passed locally. When kb-2 hit production schema, every SQL statement raised `OperationalError: no such column: name` / `no such column: source`.

### Production schema reality (verified Hermes SSH 2026-05-14)

```
extracted_entities:
  id INTEGER PK, article_id INTEGER NOT NULL → articles(id),
  entity_name TEXT NOT NULL, entity_type TEXT, extracted_at TEXT
  -- NO `source` column, NO `name` column

classifications:
  id INTEGER PK, article_id INTEGER NOT NULL → articles(id),
  topic TEXT, depth_score INTEGER, relevant INTEGER, excluded INTEGER,
  reason TEXT, classified_at TEXT, depth INTEGER, topics TEXT, rationale TEXT
  -- NO `source` column

rss_articles.topics + rss_articles.depth → RSS classifications stored row-side
rss_classifications: TABLE EXISTS but empty (0 rows on Hermes prod)
rss_extracted_entities: DOES NOT EXIST — RSS has no entity extraction in v1.0
```

### Root cause

kb-2 implementation never validated against production schema. The fixture was written to match the kb-2 SQL (not vice versa), so the test loop self-confirmed the broken design.

---

## Issue 2 — `classifications` table empty on Aliyun (operator-side, NOT code)

### What's wrong

Aliyun ECS does not have a populated `classifications` table for the deployed `kol_scan.db`. Topic pillar pages render as empty-state.

### Why it's not in code scope

This is a data-population issue, not a code defect. The fix is one of:

- (A) `scp` Hermes `data/kol_scan.db` (which has 3945 KOL classifications + 5285 extracted entities) onto Aliyun, or
- (B) Run `python batch_classify_kol.py` on Aliyun to repopulate classifications from the LLM cron.

Option A is fastest and includes the entire pre-classified corpus. Option B requires DEEPSEEK_API_KEY (or vertex_gemini provider) on Aliyun.

Documented in `RUNBOOK.md` for the operator. **No code changes for Issue 2.**

---

## Issue 3 — Hardcoded absolute paths break subdirectory deploy

### What's wrong

`kb/templates/*.html` use `/static/...`, `/articles/...`, `/ask/...`, `/entities/...`, `/topics/...` literal absolute paths. Aliyun deploys the KB under the `/kb/` subdirectory prefix:

```
Caddy reverse-proxy:    http://101.133.154.49/kb/  →  /var/www/kb/
```

Caddy strips the `/kb/` prefix when proxying. The exported templates emit absolute paths like `/static/style.css`. Browser requests this absolute URL. Caddy catch-all serves the SPA `index.html` (text/html) instead of CSS. Page styling is lost; nav links jump back to the parent vitaclaw-site SPA.

### Fix

Add `KB_BASE_PATH` env var to `kb/config.py`. Inject as Jinja2 `env.globals['base_path']`. Replace all hardcoded `/...` paths with `{{ base_path }}/...` in 7 templates. Inject `<script>window.KB_BASE_PATH = "{{ base_path }}";</script>` in `base.html` `<head>` for JS path construction. Update `kb/static/qa.js` + `kb/static/search.js` to use `window.KB_BASE_PATH` for fetch URLs and emitted hrefs.

`KB_BASE_PATH=/kb python kb/export_knowledge_base.py` then emits `/kb/static/...`, `/kb/articles/...` etc. Default (`KB_BASE_PATH` unset = empty string) preserves bare `/static/`, `/articles/` paths for root-deploy compatibility.

---

## Issue 4 — Missing index pages for `/topics/` and `/entities/`

### What's wrong

`kb/output/topics/index.html` and `kb/output/entities/index.html` are NOT generated. Homepage's "查看全部 →" links to `/topics/` and `/entities/` get HTTP 404 on Aliyun. Caddy `try_files` fallback then returns the root `index.html`, so users navigate in circles when clicking the homepage's directory-browse links.

### Fix

Add 2 new templates: `kb/templates/topics_index.html` (5-card grid reusing `.article-card--topic`) and `kb/templates/entities_index.html` (chip cloud reusing `.chip--entity-cloud`). Both reuse kb-1 + kb-2 patterns verbatim — zero new CSS classes, zero new `:root` vars. Add 9 locale keys (parity zh-CN.json + en.json). Wire into `kb/export_knowledge_base.py` via `_render_topics_index_page` + `_render_entities_index_page`.

---

## Issue 5 — kb-3 deferred test isolation (importlib.reload class identity drift)

### What's wrong

`tests/integration/kb/test_export.py:56` uses `importlib.reload(kb.data.article_query)` to flip module-level constants in test setup. The reload creates **new** class objects for `EntityCount` and `TopicSummary`. But `tests/unit/kb/test_kb2_queries.py` imports those classes at module load (before the reload), so its `isinstance()` checks against post-reload return values fail with class-identity drift.

Symptom: `test_related_entities_for_article` and `test_cooccurring_entities_in_topic` PASS in isolation; FAIL when the integration suite + unit suite run together.

Documented in `.planning/phases/kb-3-fastapi-bilingual-api/deferred-items.md` as kb-3-02 deferred work.

### Fix

Replace `importlib.reload(kb.data.article_query)` with `monkeypatch.setattr(kb.data.article_query, "QUALITY_FILTER_ENABLED", <value>)`. The `setattr` patches only the env-derived module-level constant without rebinding class objects, preserving class identity across the combined run.

Folded into this quick task because (a) the conftest fixture is being rewritten anyway for Issue 1, (b) test_export.py touches the same domain, and (c) it saves a separate quick task for what is effectively a one-line pattern fix.
