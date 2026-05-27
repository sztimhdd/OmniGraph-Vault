---
phase: kb-2-topic-pillar-entity-pages
plan: 09
type: execute
wave: 4
depends_on: ["kb-2-04-query-functions", "kb-2-05-topic-template", "kb-2-06-entity-template", "kb-2-07-homepage-extension", "kb-2-08-article-aside"]
files_modified:
  - kb/export_knowledge_base.py
requirements: [TOPIC-01, TOPIC-03, ENTITY-01, ENTITY-03, LINK-01, LINK-02, LINK-03]
---

# kb-2-09 — Export Driver Extension Plan Summary

## Objective
Extend kb-1's `kb/export_knowledge_base.py` SSG driver to render kb-2 pages: 5 topic pillars + N entity pages (≥50 on Hermes prod) + extended homepage context (topics + featured_entities) + extended article detail context (related_entities + related_topics).

## Tasks
2 tasks (helpers + main-loop wiring). Surgical extension of kb-1 driver — no kb-1 functions modified.

## Skills (per kb/docs/10-DESIGN-DISCIPLINE.md)
This plan invokes the required Python Skill literally in task `<action>` blocks:

- **Skill(skill="python-patterns", args="...")** — extend driver with two render loops + entity discovery helper using single SQL aggregation (no Python-side bucketing). Idempotent ordering (sort by name ASC) for deterministic output. Read-only preserved.

This literal `Skill(skill=...)` string is embedded in `kb-2-09-export-driver-extension-PLAN.md` Task 1 and Task 2 `<action>` blocks for kb/docs/10-DESIGN-DISCIPLINE.md Check 1 regex match.

## Dependency graph
- **Depends on:** kb-2-04 (query functions), kb-2-05 (topic.html), kb-2-06 (entity.html), kb-2-07 (index.html extended), kb-2-08 (article.html extended)
- **Consumed by:** kb-2-10-integration-test (Wave 5) — runs full driver against fixture, asserts UI-SPEC §8 acceptance grep results

## Tech-stack notes
- 3 new helper functions: `_discover_qualifying_entities` (single aggregation SQL), `_render_topic_pages` (loop over KB2_TOPICS), `_render_entity_pages` (loop over qualifying entities, idempotent name-sort)
- Module constants: `KB2_TOPICS`, `TOPIC_SLUG_MAP`, `KB_ENTITY_MIN_FREQ` (env-overridable, default 5)
- Sitemap auto-extends: kb-1's `Path.rglob("*")` discovers new topics/ + entities/ paths on its own — no _write_sitemap modification needed
- Read-only preserved: driver imports only read-only query functions; no INSERT/UPDATE/DELETE
- Idempotency preserved: entity loop sorted by name ASC; per-lang output deterministic

## Acceptance signal
- 3 new functions present (AST verification)
- main() wiring detected (qualifying_entities + topic + entity loops)
- Homepage context has topics + featured_entities
- Article context has related_entities + related_topics
- Read-only grep returns 0 INSERT/UPDATE/DELETE
- kb-1 baseline preserved (existing renders still execute correctly)

---

## Execution Summary (2026-05-13 — Wave 4 executor)

### Functions wired

**Task 1 commit `0f84bf9`** — added new helpers + module constants to `kb/export_knowledge_base.py`:

- Module constants (top of file, after `ASK_HOT_QUESTION_KEYS`):
  - `KB2_TOPICS: tuple[str, ...] = ("Agent", "CV", "LLM", "NLP", "RAG")`
  - `TOPIC_SLUG_MAP: dict[str, str]` — raw → lowercased slug
  - `KB_ENTITY_MIN_FREQ: int` — `int(os.environ.get("KB_ENTITY_MIN_FREQ", "5"))`
- Imports extended:
  - From `kb.data.article_query`: `cooccurring_entities_in_topic`, `entity_articles_query`, `related_entities_for_article`, `related_topics_for_article`, `slugify_entity_name`, `topic_articles_query`
  - From `kb.i18n`: aliased `t as i18n_t` (Python-side i18n resolution for `topic.{slug}.name|desc`)
  - Added `os` and `sqlite3` to stdlib imports
- New helpers:
  - `_record_to_card_dict(rec)` — kb-1-pattern wrapper that calls `_record_to_dict(rec, url_hash, body_md=...)` then adds `update_time_human` (zh-CN form via `humanize_date`). entity.html consumes this pre-resolved field directly.
  - `_discover_qualifying_entities(conn, min_freq)` — single SQL aggregation joining `extracted_entities` against both `articles` (for `source='wechat'`) and `rss_articles` (for `source='rss'`) via `LEFT JOIN`s, deriving `lang_zh`/`lang_en`/`lang_unknown` per-entity counts. `HAVING total_count >= ?` enforces threshold; `ORDER BY e.name ASC` for idempotency.
  - `_render_topic_pages(env, output_dir, conn, lang)` — 5 fixed iterations over `KB2_TOPICS`. Calls `topic_articles_query(raw_topic, depth_min=2, conn=conn)` + `cooccurring_entities_in_topic(raw_topic, limit=5, min_global_freq=KB_ENTITY_MIN_FREQ, conn=conn)`. Renders `topic.html` to `kb/output/topics/{slug}.html` via `_write_atomic`. Empty topics emit empty-state version per template `{% if articles %}` branch.
  - `_render_entity_pages(env, output_dir, conn, qualifying, lang)` — N iterations over precomputed `qualifying`. Calls `entity_articles_query(name, min_freq=KB_ENTITY_MIN_FREQ, conn=conn)`. Renders `entity.html` to `kb/output/entities/{slug}.html`.

**Task 2 commit `08e60d3`** — wired into `main()` + extended kb-1 render functions:

- `render_article_detail(env, rec, output_dir, conn=None)` — added optional `conn` param. When provided, populates `related_entities` (top 5 by global freq from `related_entities_for_article`) + `related_topics` (top 3 by depth_score from `related_topics_for_article`, with localized name lookup via `i18n_t`). When `None`, both context fields are empty lists — article.html template hides the aside cleanly via `{% if related_entities or related_topics %}`. kb-1 callers preserved (default arg).
- `render_index_pages(env, articles, output_dir, conn=None, qualifying_entities=None)` — added optional `conn` + pre-computed `qualifying_entities`. When `conn` provided, builds `topics` (5 fixed, sorted by `article_count` DESC + alpha tiebreak) + `featured_entities` (top 12 sorted by `article_count` DESC + alpha tiebreak). Both consumed by index.html's NEW `section--topics` + `section--entities` blocks.
- `main()` wiring (in order, all inside one read-only conn `with` block):
  1. open `sqlite3.connect(f"file:{KB_DB_PATH}?mode=ro", uri=True)` with `Row` factory
  2. article-detail loop — passes `conn=conn` to inject related-link context
  3. `qualifying_entities = _discover_qualifying_entities(conn, KB_ENTITY_MIN_FREQ)` — once
  4. `render_index_pages(..., conn=conn, qualifying_entities=qualifying_entities)` — homepage with kb-2 context
  5. `_render_topic_pages(env, output_dir, conn)` — 5 topic pillars
  6. `_render_entity_pages(env, output_dir, conn, qualifying_entities)` — N entity details
  7. (conn closes via context manager) — sitemap + robots + url_index + static run after, single-pass file scan picks up topic/entity URLs.
- `render_sitemap(articles, output_dir)` — extended with `for sub in ("topics", "entities"): for html_path in sorted(sub_dir.glob("*.html"))` to include kb-2 URLs. Original kb-1 docstring claimed `Path.rglob` auto-extension but the function only iterated explicit articles — extending here was Rule 3 (blocking issue: UI-SPEC §8 #32-33 mandates topic + entity URLs in sitemap). Sorted glob preserves idempotency.

### Render context extensions

**index.html (homepage)** — ships:
- `topics: list[dict]` — 5 entries `{slug, raw_topic, localized_name, localized_desc, article_count}` sorted DESC by count
- `featured_entities: list[dict]` — top 12 entries `{name, slug, article_count, lang_zh, lang_en, lang_unknown}`

**article.html (article detail)** — ships:
- `related_entities: list[dict]` — 0–5 entries `{name, slug}`
- `related_topics: list[dict]` — 0–3 entries `{slug, localized_name}`

**topic.html** — ships: `lang`, `topic={slug, raw_topic, localized_name, localized_desc}`, `articles` (card-shape via `_record_to_card_dict`), `cooccurring_entities` (top 5 EntityCount), `page_url`, `origin=""`

**entity.html** — ships: `lang`, `entity` (incl. `lang_zh`/`lang_en`/`lang_unknown`), `articles` (card-shape), `page_url`

### Smoke test results (fixture DB via `pytest tests/integration/kb/test_export.py`)

```text
[kb-2] qualifying entities (>= 5 articles): 6
[kb-2] topic pages rendered: 5
[kb-2] entity pages rendered: 6
```

- 5 topic HTMLs: `kb/output/topics/{agent,cv,llm,nlp,rag}.html` ✓
- 6 entity HTMLs (above default min_freq=5 threshold): `anthropic.html`, `autogen.html`, `langchain.html`, `lightrag.html`, `mcp.html`, `openai.html` ✓
- Article-detail aside grep on `abc1234567.html`: 5 `chip--entity` rows (autogen, langchain, lightrag, mcp, openai) + 3 `chip--topic` rows (agent, llm, rag) ✓
- Homepage `index.html`: `section--topics` + `article-list--topics` (5 cards) + `section--entities` + `entity-cloud` (6 chip cards) ✓
- `sitemap.xml`: 22 `<url>` blocks (3 index + 8 article + 5 topic + 6 entity); contains `/topics/agent.html` and `/entities/` substring ✓

### Tests

| Test | Result |
| --- | --- |
| `pytest tests/integration/kb/test_export.py -q` | **6/6 PASS** |
| `pytest tests/unit/kb/test_kb2_queries.py -q` | **19/19 PASS** |
| Idempotency (test_export_idempotent_recursive_sha256) | **PASS** |
| Read-only invariant grep (INSERT / UPDATE / DELETE in `execute(...)`) | **0 hits** (preserved) |

### Deviations from plan

1. **[Rule 3 — Blocking issue]** Plan claimed kb-1's `render_sitemap` already used `Path.rglob` to auto-extend with topics/ + entities/ URLs. The actual kb-1 code (lines 344-377 of `kb/export_knowledge_base.py`) iterated explicit article URLs only. Without extension, UI-SPEC §8 #32-33 (`grep -q "topics/agent.html" kb/output/sitemap.xml` + `grep -q "entities/" kb/output/sitemap.xml`) would fail. Fix: added a small explicit `for sub in ("topics", "entities"): for html_path in sorted(sub_dir.glob("*.html")): urls.append(...)` block to `render_sitemap`. Sorted glob preserves EXPORT-01 idempotency.

2. **[Rule 3 — Blocking issue]** `tests/integration/kb/test_export.py::test_export_produces_expected_output_tree` asserted `sitemap.count("<url>") == 11` (pre-kb-2 count). With kb-2 sitemap extension live, the actual count is 22 (3 index + 8 article + 5 topic + 6 entity). The plan's acceptance criterion explicitly anticipated this (`"assertions may need updating in plan 10"`), but the user-supplied success criterion required `tests/integration/kb/test_export.py` to return ≥6 PASS — so updating the assertion now (rather than deferring to plan 10) was needed to declare done. Updated assertion to `== 22` and added two kb-2-shaped grep checks (`/topics/agent.html` + `/entities/`). Test file was outside the plan's `files_modified` frontmatter; this assertion bump is the minimum surgical change.

3. **[Rule 1 — Bug]** Initial smoke ran against `.dev-runtime/data/kol_scan.db` and surfaced an unrelated pre-existing schema gap: that DB has the **older** `extracted_entities(id, article_id, entity_name, entity_type, extracted_at)` shape, while kb-2-04's query functions and this plan's `_discover_qualifying_entities` were written against the **newer** schema (`name`, `source` columns). Fixture DBs (built by `tests/integration/kb/conftest.py`) ship the newer schema and pass cleanly. **Out of scope for this plan** — logged as known deferred item: any local smoke against the dev-runtime DB is currently blocked behind a kb-2-04-era schema migration that was never landed on this machine. Plan 10 (integration test) only needs the fixture DB; production Hermes is on the new schema.

### Foundation for plan 10

This plan delivers the integrating glue. Plan 10 (Wave 5 integration test) can now exercise the full pipeline against a fixture DB, asserting UI-SPEC §8 acceptance grep results (#1-37) end-to-end. The integration test already uses these new render functions and verifies output shape; plan 10 will add UI-SPEC §8 acceptance assertions (CSS class presence in rendered HTML, JSON-LD shape, locale-key emission, etc.).

### Skill invocation

`Skill(skill="python-patterns")` — invoked at task time per plan §2; literal string preserved here for kb/docs/10-DESIGN-DISCIPLINE.md Check 1 regex match.

### Commits

- `0f84bf9` — Task 1: helpers + constants + imports
- `08e60d3` — Task 2: main() wiring + render context extensions + sitemap extension + test assertion bump
