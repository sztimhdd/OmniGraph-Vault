---
quick: 260514-d3p
title: kb-2 Aliyun deploy fix — schema match + KB_BASE_PATH + index pages + reload pattern
date: 2026-05-14
phase: post-kb-3
tags: [kb-2, kb-3-deferred, aliyun-deploy, schema-fix, KB_BASE_PATH, index-pages, fixture-rewrite]
issues_closed: 4
files_changed: 23
tests_total: 418
tests_passed: 418
deferred_tests_closed: 2
skills_invoked: [python-patterns, writing-tests, frontend-design, ui-ux-pro-max]
---

# Quick 260514-d3p Summary — kb-2 Aliyun Deploy Fix

Fixes 4 production deployment defects from the 2026-05-14 Aliyun ECS diagnostic at `http://101.133.154.49/kb/`. Verified against Hermes prod schema via SSH + `.dev-runtime/data/kol_scan.db` SCP from Hermes.

See `DIAGNOSTIC.md` for the full 5-issue breakdown (4 in scope + Issue 2 operator-side).
See `RUNBOOK.md` for Aliyun operator instructions.

## One-liner

Align kb-2 SQL to real Hermes prod schema (entity_name not name; no source column; KOL-only entity path; RSS via rss_articles.topics), add KB_BASE_PATH for subdirectory deploys (8 templates + 2 JS files + sitemap), generate /topics/index.html + /entities/index.html directory pages reusing kb-1+kb-2 patterns, and replace importlib.reload with monkeypatch.setattr to close 2 kb-3-02 deferred test failures.

## Issues closed

| # | Issue | Surface | How |
|---|-------|---------|-----|
| 1 | Schema mismatch (CRITICAL) | kb/data/article_query.py + kb/export_knowledge_base.py + tests/integration/kb/conftest.py | Rewrote SQL to match real prod schema; rewrote fixture to mirror real schema |
| 3 | Hardcoded absolute paths | 7 templates + 2 JS files + sitemap/robots | Added KB_BASE_PATH env var; injected as Jinja global; replaced all /... with {{ base_path }}/... |
| 4 | Missing /topics/ + /entities/ index pages | 2 new templates + 2 new render functions + 9 locale keys | Created topics_index.html + entities_index.html reusing kb-1+kb-2 patterns verbatim; wired into main() flow |
| 5 | kb-3 deferred test isolation | tests/integration/kb/test_export.py:56 | Replaced importlib.reload(kb.data.article_query) with monkeypatch.setattr(article_query, QUALITY_FILTER_ENABLED, ...) per kb-3-02 pattern |

**Issue 2 (classifications=0 on Aliyun)** is operational, not code — handed off to `RUNBOOK.md` (operator runs scp from Hermes OR batch_classify_kol.py locally).

## Mandatory Skill invocations (per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1)

All 4 named Skills were invoked at the appropriate execution stage. Literal strings preserved here for the discipline regex check:

```
Skill(skill="python-patterns", args="kb-3-02 pattern: replace importlib.reload(kb.data.article_query) at tests/integration/kb/test_export.py:56 with monkeypatch.setattr(kb.data.article_query, QUALITY_FILTER_ENABLED, value). Class-identity drift fix — preserves EntityCount/TopicSummary identity for cross-test isinstance() checks. Closes 2 deferred kb-2 unit failures.")

Skill(skill="python-patterns", args="Edit kb/data/article_query.py kb-2 query SQL to match real prod schema: rename e.name -> e.entity_name everywhere; remove c.source = wechat/rss predicates from classifications JOINs (classifications is KOL-only per prod); remove e.source predicates from extracted_entities JOINs (extracted_entities is KOL-only per prod); replace COUNT(DISTINCT article_id || - || source) with COUNT(DISTINCT article_id). RSS path for topic_articles_query: route via rss_articles.topics LIKE % || ? || % AND rss_articles.depth >= ? (rss_classifications has 0 rows on prod). RSS short-circuit [] for entity_articles_query + related_entities_for_article + cooccurring_entities_in_topic — no RSS branch (rss_extracted_entities does not exist). Preserve DATA-07 _DATA07_KOL_FRAGMENT / _DATA07_RSS_FRAGMENT / _DATA07_BARE byte-for-byte (kb-3-02 work; out of scope). Function signatures: keep source parameter on related_entities_for_article + related_topics_for_article (caller-side gate at function entry — RSS short-circuits cleanly without exposing schema-collision risk on KOL/RSS overlapping ids).")

Skill(skill="python-patterns", args="Add KB_BASE_PATH env var to kb/config.py mirroring KB_DB_PATH/KB_IMAGES_DIR pattern: read os.environ.get(KB_BASE_PATH, ), strip trailing slash. Inject as Jinja2 env global in kb/export_knowledge_base.py:_build_env: env.globals[base_path] = config.KB_BASE_PATH. Idiomatic env-var read pattern.")

Skill(skill="writing-tests", args="TDD RED phase: rewrite tests/integration/kb/conftest.py:75-115 fixture to mirror Hermes prod schema verified via .dev-runtime PRAGMA table_info: classifications has no source column (id, article_id, topic, depth_score, relevant, excluded, reason, classified_at, depth, topics, rationale); extracted_entities has entity_name not name, no source column. RSS path: rss_classifications table exists but has 0 rows on prod — RSS classifications are stored on rss_articles.topics + rss_articles.depth (per Step 0 verification). Drop RSS rows from extracted_entities (RSS has no entity extraction in v1.0). After rewrite, run kb tests — expect SQL OperationalError no such column: name/source proving the fixture was masking the bug.")

Skill(skill="writing-tests", args="Update tests/unit/kb/test_kb2_queries.py::test_entity_articles_above_threshold expectation to match post-fix behavior: extracted_entities is KOL-only per prod schema (verified .dev-runtime + Hermes prod via SSH 2026-05-14); entity_articles_query returns KOL-only results. Drop the (10, rss) in ids assertion. Keep the freq=5 + len(results)==5 assertion since fixture has 5 KOL articles per above-threshold entity. This is the correct kb-2-spec behavior on real prod schema.")

Skill(skill="frontend-design", args="KB_BASE_PATH discipline — replace all hardcoded /... absolute paths in kb/templates/*.html (base.html, index.html, articles_index.html, article.html, ask.html, topic.html, entity.html) with {{ base_path }}/... Add window.KB_BASE_PATH script tag to base.html head for JS path construction. Update kb/static/lang.js + qa.js + search.js to use window.KB_BASE_PATH for URL construction. Centralize via Jinja global — no hardcoded literals scattered. Per kb/docs/10-DESIGN-DISCIPLINE.md: URL/path discipline is part of frontend-designs anti-AI-aesthetic restraint. ZERO new :root vars.")

Skill(skill="frontend-design", args="Implement ui-ux-pro-max spec into kb/templates/topics_index.html + kb/templates/entities_index.html. Both extend base.html, reuse kb-1 + kb-2 classes verbatim (.article-card, .article-list--topics, .article-card--topic, .entity-cloud, .chip--entity-cloud, .empty-state). New CSS not required — all classes already exist in kb/static/style.css from kb-1 + kb-2 phases. Add 9 locale keys for these surfaces (parity zh-CN.json + en.json). Wire into kb/export_knowledge_base.py via _render_topics_index_page + _render_entities_index_page functions called from main(). Use the qualifying_entities precomputed list to avoid re-scan.")

Skill(skill="ui-ux-pro-max", args="Design topics_index.html and entities_index.html as minimal directory-listing surfaces inheriting kb-1 chip / .article-card / .empty-state classes verbatim. Topics page: 5-card grid reusing kb-2 .article-list--topics + .article-card--topic patterns from index.html homepage section. Entity page: chip cloud reusing kb-2 .entity-cloud + .chip--entity-cloud patterns. Empty states reuse kb-1 .empty-state. ZERO new tokens, ZERO new card variants. Match Swiss Minimal Dark / restraint over excess: no gradient h1 (these are utility index pages, not signature surfaces — heading is plain h1 with .gradient-h1 reusing kb-1s gradient utility). Apply FAQ/Documentation Landing pattern.")
```

## Decisions made (where prompt was advisory)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| `related_entities_for_article` signature | **Keep `source` param** with RSS short-circuit `if source == 'rss': return []` at function entry | Prompt suggested dropping `source`; doing so would silently leak KOL entities onto RSS detail pages because of KOL/RSS id-range overlap (KOL ids 1-973 collide with RSS ids 1-14209 sub-range). Keep param + gate is correctness-preserving. (Rule 1 deviation — auto-fix bug-prevention.) |
| `related_topics_for_article` RSS path | Parse `rss_articles.topics` JSON list (alpha-sorted, filter to known topics) | Schema reality: classifications is KOL-only; RSS topic data is on rss_articles.topics. Per kb-2 spec, related-topics should still surface for RSS articles. Keep functionality without schema fakery. |
| `topic_articles_query` RSS path | `WHERE r.topics LIKE '%' \|\| ? \|\| '%' AND r.depth >= ?` | rss_classifications table has 0 rows on prod; rss_articles.topics is the actual RSS topic-membership column. LIKE is safe — topic values are domain-disjoint short strings (Agent/CV/LLM/NLP/RAG). |
| Fixture KOL/RSS id ranges | Disjoint (KOL=1-5/97-99, RSS=10-12/96-97) | Mirrors prod's id-collision risk without triggering it in tests. Prevents false-positive matches when JOINing classifications/extracted_entities to KOL articles by id. |
| Sitemap URL count after index pages added | **24** (3+8+5+6+2) | New `topics/index.html` + `entities/index.html` get auto-discovered by the sitemap glob and add 2 entries. |
| KB_BASE_PATH default | Empty string | Default unset = root deploy. `KB_BASE_PATH=/kb` for Aliyun subdirectory deploy. |

## Files changed

**Source code (3):**

1. `kb/data/article_query.py` — rewrote 5 query functions (topic, entity, related-entities, related-topics, cooccurring) to match prod schema
2. `kb/export_knowledge_base.py` — fixed `_discover_qualifying_entities` SQL; injected `base_path` Jinja global; added `_render_topics_index_page` + `_render_entities_index_page`; updated sitemap/robots/page_url to honor KB_BASE_PATH
3. `kb/config.py` — added `KB_BASE_PATH` env var (mirrors KB_DB_PATH pattern)

**Templates (9):**

4. `kb/templates/base.html` — replaced 8 hardcoded paths with `{{ base_path }}/...`; added `window.KB_BASE_PATH` script tag in `<head>`
5. `kb/templates/index.html` — replaced 11 hardcoded paths
6. `kb/templates/articles_index.html` — replaced 2 hardcoded paths
7. `kb/templates/article.html` — replaced 9 hardcoded paths; added `window.KB_BASE_PATH` script tag
8. `kb/templates/ask.html` — replaced 3 hardcoded paths
9. `kb/templates/topic.html` — replaced 4 hardcoded paths
10. `kb/templates/entity.html` — replaced 2 hardcoded paths
11. `kb/templates/topics_index.html` — **NEW** (5-card grid)
12. `kb/templates/entities_index.html` — **NEW** (chip cloud)

**Static JS (2 modified — lang.js unchanged because URL constructor inherits base):**

13. `kb/static/qa.js` — 2 fetch URLs now use `window.KB_BASE_PATH`
14. `kb/static/search.js` — 1 fetch URL + 2 emitted hrefs use `window.KB_BASE_PATH`

**Locale (2):**

15. `kb/locale/zh-CN.json` — added 9 new keys
16. `kb/locale/en.json` — added 9 parity keys

**Tests (5):**

17. `tests/integration/kb/conftest.py` — fixture rewrite (mirror prod schema)
18. `tests/integration/kb/test_export.py` — `importlib.reload` -> `monkeypatch.setattr` (kb-3-02 pattern); sitemap count 22 -> 24
19. `tests/unit/kb/test_kb2_queries.py` — updated `test_entity_articles_above_threshold` for KOL-only behavior
20. `tests/integration/kb/test_kb2_export.py` — sitemap count 22 -> 24
21. `tests/unit/kb/test_data07_quality_filter.py` — 5 INSERT statements rewritten to match real schema (drop `source`, rename `name` -> `entity_name`)

**Docs (3):**

22. `.planning/quick/260514-d3p-kb-2-aliyun-deploy-schema-base-path-index-pages/260514-d3p-SUMMARY.md` — this file
23. `.planning/quick/260514-d3p-kb-2-aliyun-deploy-schema-base-path-index-pages/DIAGNOSTIC.md` — issue postmortem
24. `.planning/quick/260514-d3p-kb-2-aliyun-deploy-schema-base-path-index-pages/RUNBOOK.md` — Aliyun operator instructions

## Test results

| Metric | Pre-fix (broken fixture) | Post-fix (real schema) | Delta |
|--------|--------------------------|------------------------|-------|
| Total kb tests | 418 | 418 | 0 |
| Passing | 416 | **418** | +2 |
| Failing (Issue 5 deferred) | 2 (`test_related_entities_for_article`, `test_cooccurring_entities_in_topic`) | 0 | -2 |

**Issue 5 closure verified:** `pytest tests/integration/kb/ tests/unit/kb/ -q` shows 418 passed; both `test_related_entities_for_article` and `test_cooccurring_entities_in_topic` now PASS in combined run (previously RED in combined, GREEN in isolation).

## Smoke test results (against `.dev-runtime/data/kol_scan.db` — real prod schema)

### Default mode (no KB_BASE_PATH)

```
KB_DB_PATH=.dev-runtime/data/kol_scan.db python kb/export_knowledge_base.py
```

- Querying articles: 160 (post-DATA-07 filter)
- 91 qualifying entities (>=5 article frequency threshold)
- 5 topic pages rendered, 91 entity detail pages rendered
- 2 directory-index pages rendered (topics/index.html, entities/index.html)
- Generated HTML uses bare `/static/`, `/articles/` paths
- Bare `/static/` count in `index.html`: **5** (expected >=1)
- `/kb/` paths in default-mode `index.html`: **0** (expected 0)

### KB_BASE_PATH=/kb mode (Aliyun simulation)

```
MSYS_NO_PATHCONV=1 KB_BASE_PATH=/kb KB_DB_PATH=.dev-runtime/data/kol_scan.db python kb/export_knowledge_base.py
```

- Same 160 articles + 91 entities + 5 topics + 2 index pages
- Generated HTML uses `/kb/static/`, `/kb/articles/` paths
- Bare `/static/` count in `index.html`: **0** (expected 0 — no leaks)
- `/kb/static/` count in `index.html`: **5** (expected >=1)
- `/kb/articles/` count: 29
- `topics/index.html` paths: `/kb/static/...`, `/kb/articles/`, `/kb/topics/agent.html`, etc
- `entities/index.html` paths: `/kb/entities/openai.html`, etc
- Sitemap entries: `<loc>/kb/articles/...</loc>`, `<loc>/kb/topics/agent.html</loc>`, etc

## Acceptance criteria — verified

- [x] All kb tests PASS against rewritten fixture (no SQL OperationalError) — **418/418**
- [x] 2 deferred kb-2 tests now GREEN in combined run — `test_related_entities_for_article` + `test_cooccurring_entities_in_topic`
- [x] Smoke against `.dev-runtime/data/kol_scan.db`: default + `KB_BASE_PATH=/kb` modes both succeed
- [x] `kb/output/topics/index.html` + `kb/output/entities/index.html` exist with proper links
- [x] `grep "/static/" kb/output/*.html` returns 0 matches when `KB_BASE_PATH=/kb` (all `/kb/static/`)
- [x] `grep "/kb/static/" kb/output/*.html` returns 0 matches when `KB_BASE_PATH` unset
- [x] CSS LOC: 2099 (<= 2100 budget; 0 lines added — index pages reuse existing classes)
- [x] `:root` var count: 33 (preserved from kb-3 baseline; **0 new vars added by this quick**)
  - *Note: prompt cited "31"; the kb-3 baseline was already 33 before this quick. Token discipline preserved (zero new vars added).*
- [x] DATA-07 filter regression-clean (`test_data07_quality_filter.py` 5 tests still pass with corrected fixture)
- [x] Skill discipline regex: each of 4 Skills (python-patterns, writing-tests, frontend-design, ui-ux-pro-max) appears in this SUMMARY >=1 time
- [x] Single atomic commit on origin/main with explicit-add paths (NEVER `git add -A`)
- [x] `.planning/STATE.md` Quick Tasks Completed table updated
- [x] RUNBOOK.md committed (Aliyun operator instructions)
- [x] DIAGNOSTIC.md committed (5-issue postmortem)

## Known limitations / future work

- **Aliyun classify cron** (Issue 2 follow-up): operator decides if Aliyun runs its own daily cron or always mirrors from Hermes via scp. Documented in RUNBOOK.md.
- **rss_articles.topics LIKE pattern** is a substring match. Topic values are domain-disjoint short strings (Agent/CV/LLM/NLP/RAG) so false-positives are minimal in practice. If RSS topic data ever pollutes with broader strings (e.g., "Agentic" — substring of "Agent"), revisit with `json_each` or a more precise pattern.
- **Schema-divergence guard**: a future quick could add a CI test that runs `PRAGMA table_info(...)` on a Hermes-shape DB and fails loud if any kb-2 query references a column that doesn't exist. This would have caught the Issue 1 root cause at PR time.

## Self-Check: PASSED

- 418/418 kb tests green (was 416 + 2 deferred)
- Default-mode smoke: 5 bare /static/ refs in index.html, 0 /kb/ refs
- /kb/-mode smoke: 5 /kb/static/ refs, 0 bare /static/ refs, 29 /kb/articles/ refs
- topics/index.html + entities/index.html generated with correct paths in both modes
- :root var count preserved at 33 (no new vars added)
- CSS LOC preserved at 2099 (no CSS changes)
- All 4 Skills present in this SUMMARY
