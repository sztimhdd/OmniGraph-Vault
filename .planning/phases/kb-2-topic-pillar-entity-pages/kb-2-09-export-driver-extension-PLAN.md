---
phase: kb-2-topic-pillar-entity-pages
plan: 09
subsystem: ssg-driver
tags: [python, jinja2, ssg, export-driver]
type: execute
wave: 4
depends_on: ["kb-2-04-query-functions", "kb-2-05-topic-template", "kb-2-06-entity-template", "kb-2-07-homepage-extension", "kb-2-08-article-aside"]
files_modified:
  - kb/export_knowledge_base.py
autonomous: true
requirements:
  - TOPIC-01
  - TOPIC-03
  - ENTITY-01
  - ENTITY-03
  - LINK-01
  - LINK-02
  - LINK-03

must_haves:
  truths:
    - "kb/export_knowledge_base.py extends kb-1 driver to render kb/output/topics/{slug}.html × 5 + kb/output/entities/{slug}.html × N (≥50 on Hermes prod)"
    - "Driver discovers topics from classifications.topic DISTINCT (5 expected: Agent, CV, LLM, NLP, RAG)"
    - "Driver discovers qualifying entities by COUNT(DISTINCT article_id) >= KB_ENTITY_MIN_FREQ (default 5, env-overridable)"
    - "Homepage render context gains `topics` (5 sorted by article_count DESC) + `featured_entities` (top 12 sorted by article_count DESC, alpha tiebreak)"
    - "Article render context gains `related_entities` + `related_topics` per LINK-01 + LINK-02"
    - "sitemap.xml auto-extends via existing Path.rglob (kb-1 EXPORT-06) — verify topics/ + entities/ URLs appear"
    - "Idempotency preserved (EXPORT-01) — re-running on unchanged DB produces byte-identical output"
    - "Read-only preserved (EXPORT-02) — driver imports only the 5 kb-1 + 5 kb-2 read-only query functions, no DB writes"
  artifacts:
    - path: "kb/export_knowledge_base.py"
      provides: "EXTENDED with topic loop + entity loop + homepage context + article context"
      contains: "topic_articles_query, entity_articles_query, related_entities_for_article, related_topics_for_article, cooccurring_entities_in_topic, slugify_entity_name"
  key_links:
    - from: "kb/export_knowledge_base.py topic loop"
      to: "kb/templates/topic.html (plan 05)"
      via: "env.get_template('topic.html').render(context)"
      pattern: "topic\\.html"
    - from: "kb/export_knowledge_base.py entity loop"
      to: "kb/templates/entity.html (plan 06)"
      via: "env.get_template('entity.html').render(context)"
      pattern: "entity\\.html"
    - from: "kb/export_knowledge_base.py article render"
      to: "kb/templates/article.html (plan 08 extended) related-link context"
      via: "context['related_entities'] + context['related_topics']"
      pattern: "related_entities|related_topics"
---

<objective>
Extend `kb/export_knowledge_base.py` (kb-1's SSG driver) to render the kb-2 page set: 5 topic pillar pages, ~91 entity pages on Hermes prod, homepage with topics + featured_entities sections, article detail with related-entities + related-topics aside. Preserve EXPORT-01 idempotency + EXPORT-02 read-only.

Purpose: Without this driver extension, the templates from plans 05-08 + the query functions from plan 04 are orphaned — nothing calls them. This is the integrating glue.

Output: 1 file extended; new render loops + new context fields.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-04-SUMMARY.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-05-SUMMARY.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-06-SUMMARY.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-07-SUMMARY.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-08-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-09-export-driver-PLAN.md
@kb/export_knowledge_base.py
@kb/data/article_query.py
@kb/i18n.py
@kb/config.py
@CLAUDE.md

<interfaces>
kb-1 driver baseline (already implemented in `kb/export_knowledge_base.py`):
- `_render_index(env, articles, output_dir, lang)` — homepage
- `_render_articles_index(env, articles, output_dir, lang)` — list page
- `_render_article_detail(env, rec, output_dir, lang)` — per-article
- `_render_ask(env, output_dir, lang)` — Q&A entry
- `_write_sitemap(output_dir)` — uses Path.rglob → auto-extends to topics/ + entities/
- `_write_robots(output_dir)` — static
- Driver entry point: `def main()` with KB_DB_PATH env override

kb-2 NEW imports needed:

```python
from kb.data.article_query import (
    # kb-1 (already imported):
    ArticleRecord, list_articles, get_article_by_hash, resolve_url_hash, get_article_body,
    # kb-2 NEW (this plan):
    topic_articles_query, entity_articles_query,
    related_entities_for_article, related_topics_for_article,
    cooccurring_entities_in_topic, slugify_entity_name,
    EntityCount, TopicSummary,
)
```

Topic enumeration (5 fixed, derived from classifications.topic DISTINCT):

```python
KB2_TOPICS = ["Agent", "CV", "LLM", "NLP", "RAG"]   # raw DB values, ordered alpha
TOPIC_SLUG_MAP = {"Agent": "agent", "CV": "cv", "LLM": "llm", "NLP": "nlp", "RAG": "rag"}
```

Entity enumeration query (TOPIC of plan 09 task 2):

```sql
SELECT name, COUNT(DISTINCT article_id || '-' || source) AS freq
FROM extracted_entities
GROUP BY name
HAVING freq >= ?       -- KB_ENTITY_MIN_FREQ env, default 5
ORDER BY freq DESC, name ASC
```

KB_ENTITY_MIN_FREQ env override:
```python
KB_ENTITY_MIN_FREQ = int(os.environ.get("KB_ENTITY_MIN_FREQ", "5"))
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Invoke python-patterns Skill + extend driver with topic loop + entity loop + entity-counts helper</name>
  <read_first>
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-09-export-driver-PLAN.md (driver structure pattern)
    - kb/export_knowledge_base.py (existing kb-1 driver — APPEND new render functions, EXTEND main loop)
    - kb/data/article_query.py (kb-2 functions defined plan 04)
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §3.1 + §3.2 (render context expectations)
    - .planning/REQUIREMENTS-KB-v2.md TOPIC-01 + ENTITY-01 (slug + threshold rules)
  </read_first>
  <files>kb/export_knowledge_base.py</files>
  <action>
    Skill(skill="python-patterns", args="Extend kb/export_knowledge_base.py with two new render loops (topic loop × 5 + entity loop × N where N is dynamic per KB_ENTITY_MIN_FREQ env). Mirror existing kb-1 patterns: per-language render (zh-CN + en), Path.write_text with atomic-ish behavior, env-driven KB_OUTPUT_DIR. New helper `_discover_qualifying_entities(conn, min_freq)` returns list of (name, slug, count, lang_zh, lang_en, lang_unknown) tuples — one SQL aggregation query, no Python-side bucketing. New helper `_localize_topic(slug, lang, t_filter)` returns localized name + desc by composing existing Jinja2 t() filter on `topic.{slug}.name` and `topic.{slug}.desc`. Idempotency: render outputs deterministic — sort entity loop by name ASC for stable file order. Read-only: NO INSERT/UPDATE/DELETE in driver — only SELECT through query functions.")

    **Locate and EXTEND `kb/export_knowledge_base.py`:**

    1. **Add imports at module top** (extend existing import block):

       ```python
       from kb.data.article_query import (
           ArticleRecord, list_articles, get_article_by_hash,
           resolve_url_hash, get_article_body,
           # kb-2 additions:
           topic_articles_query, entity_articles_query,
           related_entities_for_article, related_topics_for_article,
           cooccurring_entities_in_topic, slugify_entity_name,
           EntityCount, TopicSummary,
       )
       ```

    2. **Add module constants** (top of file):

       ```python
       KB2_TOPICS = ["Agent", "CV", "LLM", "NLP", "RAG"]
       TOPIC_SLUG_MAP = {"Agent": "agent", "CV": "cv", "LLM": "llm", "NLP": "nlp", "RAG": "rag"}
       KB_ENTITY_MIN_FREQ = int(os.environ.get("KB_ENTITY_MIN_FREQ", "5"))
       ```

    3. **Add `_discover_qualifying_entities` helper** (after kb-1 helpers):

       ```python
       def _discover_qualifying_entities(
           conn: sqlite3.Connection, min_freq: int
       ) -> list[dict]:
           """Return list of {name, slug, article_count, lang_zh, lang_en, lang_unknown}
           for entities crossing the freq threshold. Sorted by name ASC for idempotency.
           """
           sql = """
               SELECT
                 e.name,
                 COUNT(DISTINCT e.article_id || '-' || e.source) AS total_count,
                 SUM(CASE WHEN COALESCE(a.lang, r.lang) = 'zh-CN' THEN 1 ELSE 0 END) AS lang_zh,
                 SUM(CASE WHEN COALESCE(a.lang, r.lang) = 'en'    THEN 1 ELSE 0 END) AS lang_en,
                 SUM(CASE WHEN COALESCE(a.lang, r.lang) NOT IN ('zh-CN','en')
                              OR COALESCE(a.lang, r.lang) IS NULL THEN 1 ELSE 0 END) AS lang_unknown
               FROM extracted_entities e
               LEFT JOIN articles      a ON e.source = 'wechat' AND a.id = e.article_id
               LEFT JOIN rss_articles  r ON e.source = 'rss'    AND r.id = e.article_id
               GROUP BY e.name
               HAVING total_count >= ?
               ORDER BY e.name ASC
           """
           return [
               {
                   "name": row["name"],
                   "slug": slugify_entity_name(row["name"]),
                   "article_count": row["total_count"],
                   "lang_zh": row["lang_zh"] or 0,
                   "lang_en": row["lang_en"] or 0,
                   "lang_unknown": row["lang_unknown"] or 0,
               }
               for row in conn.execute(sql, (min_freq,))
           ]
       ```

    4. **Add `_render_topic_pages` function:**

       ```python
       def _render_topic_pages(
           env, output_dir: Path, conn: sqlite3.Connection, lang: str, origin: str
       ) -> int:
           """Render kb/output/topics/{slug}.html × 5. Returns count rendered."""
           tpl = env.get_template("topic.html")
           topics_dir = output_dir / "topics"
           topics_dir.mkdir(parents=True, exist_ok=True)
           count = 0
           for raw_topic in KB2_TOPICS:
               slug = TOPIC_SLUG_MAP[raw_topic]
               articles = topic_articles_query(raw_topic, depth_min=2, conn=conn)
               cooccurring = cooccurring_entities_in_topic(
                   raw_topic, limit=5, min_global_freq=KB_ENTITY_MIN_FREQ, conn=conn
               )
               # Localized name/desc — looked up via i18n on filter at template render time
               # via {{ ('topic.' ~ slug ~ '.name') | t(lang) }} pattern. Pass slug, raw_topic.
               topic_ctx = {
                   "slug": slug,
                   "raw_topic": raw_topic,
                   "localized_name": _t(env, f"topic.{slug}.name", lang),
                   "localized_desc": _t(env, f"topic.{slug}.desc", lang),
               }
               page_url = f"{origin}/topics/{slug}.html"
               # Pre-process articles: add url_hash, snippet, update_time_human
               prepared_articles = [_prepare_article_for_card(a) for a in articles]
               html = tpl.render(
                   lang=lang, topic=topic_ctx, articles=prepared_articles,
                   cooccurring_entities=cooccurring,
                   page_url=page_url, origin=origin,
               )
               (topics_dir / f"{slug}.html").write_text(html, encoding="utf-8")
               count += 1
           return count
       ```

    5. **Add `_render_entity_pages` function:**

       ```python
       def _render_entity_pages(
           env, output_dir: Path, conn: sqlite3.Connection, lang: str, origin: str,
           qualifying: list[dict],
       ) -> int:
           """Render kb/output/entities/{slug}.html × N. Returns count rendered.

           qualifying: pre-computed by _discover_qualifying_entities (avoids re-scanning).
           """
           tpl = env.get_template("entity.html")
           entities_dir = output_dir / "entities"
           entities_dir.mkdir(parents=True, exist_ok=True)
           count = 0
           for ent in qualifying:
               articles = entity_articles_query(
                   ent["name"], min_freq=KB_ENTITY_MIN_FREQ, conn=conn
               )
               prepared_articles = [_prepare_article_for_card(a) for a in articles]
               page_url = f"{origin}/entities/{ent['slug']}.html"
               html = tpl.render(
                   lang=lang, entity=ent, articles=prepared_articles,
                   page_url=page_url, origin=origin,
               )
               (entities_dir / f"{ent['slug']}.html").write_text(html, encoding="utf-8")
               count += 1
           return count
       ```

       (`_prepare_article_for_card` is a kb-1 helper — if it doesn't exist by that name, mirror the kb-1 pattern that adds `url_hash`, `snippet`, `update_time_human` keys to the dict-shape used by `.article-card` markup. The exact name should match what `_render_index`/`_render_articles_index` already use.)

    6. **Add `_t(env, key, lang)` helper if not already present** — wraps the kb-1 i18n filter so Python code can also resolve keys (for `topic.{slug}.name` lookups before render). If kb-1 already exposes this, reuse it.

    Surgical changes: do NOT modify any kb-1 render function or the existing main() loop in this task. Only ADD new functions + imports + constants.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "import ast; tree = ast.parse(open('kb/export_knowledge_base.py', encoding='utf-8').read()); fnames = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}; required = {'_discover_qualifying_entities', '_render_topic_pages', '_render_entity_pages'}; assert required.issubset(fnames), f'Missing: {required - fnames}'; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "_render_topic_pages" kb/export_knowledge_base.py`
    - `grep -q "_render_entity_pages" kb/export_knowledge_base.py`
    - `grep -q "_discover_qualifying_entities" kb/export_knowledge_base.py`
    - `grep -q "KB2_TOPICS" kb/export_knowledge_base.py`
    - `grep -q "KB_ENTITY_MIN_FREQ" kb/export_knowledge_base.py`
    - `grep -q "from kb.data.article_query import" kb/export_knowledge_base.py` (extended import already exists)
    - `grep -q "topic_articles_query" kb/export_knowledge_base.py`
    - `grep -q "cooccurring_entities_in_topic" kb/export_knowledge_base.py`
    - `grep -q "Skill(skill=\"python-patterns\"" .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-09-export-driver-extension-PLAN.md`
    - Module imports without error (verify command above passes)
    - Read-only preserved: `grep -E "execute\\(.*(INSERT|UPDATE|DELETE) " kb/export_knowledge_base.py` returns 0
  </acceptance_criteria>
  <done>3 new functions + module constants + extended imports added; kb-1 render functions untouched.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Wire new render loops into main() + extend homepage + article render contexts (LINK-01..03)</name>
  <read_first>
    - kb/export_knowledge_base.py (Task 1 output — extends main() loop)
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §3.3 (homepage context: topics + featured_entities)
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §3.4 (article context: related_entities + related_topics)
  </read_first>
  <files>kb/export_knowledge_base.py</files>
  <action>
    Skill(skill="python-patterns", args="Wire the new functions from Task 1 into main(). Extend `_render_index` (kb-1) to add `topics` (5 fixed by KB2_TOPICS, ordered by article_count DESC at runtime) + `featured_entities` (top 12 from qualifying-entities list). Extend `_render_article_detail` (kb-1) render context with `related_entities` (3-5 from related_entities_for_article) + `related_topics` (1-3 from related_topics_for_article — also localize via _t). Add the two new render-loop calls into main() AFTER existing kb-1 renders, BEFORE _write_sitemap. Sitemap auto-extends — kb-1's Path.rglob picks up topics/ + entities/ on its own.")

    **Edit `main()`** in `kb/export_knowledge_base.py`. Find the existing kb-1 sequence (typically: open conn → list_articles → render index/articles_index/articles/ask/sitemap/robots → copy static). Insert AFTER article-detail loop, BEFORE _write_sitemap:

    ```python
    # kb-2: discover qualifying entities ONCE (used by both _render_entity_pages
    # and _render_index for featured_entities context)
    qualifying_entities = _discover_qualifying_entities(conn, KB_ENTITY_MIN_FREQ)

    # kb-2 page renders (per UI lang × topic/entity loops)
    for lang in ("zh-CN", "en"):
        topic_count = _render_topic_pages(env, output_dir / lang, conn, lang, origin)
        entity_count = _render_entity_pages(
            env, output_dir / lang, conn, lang, origin, qualifying_entities
        )
        print(f"[kb-2] lang={lang}: topics={topic_count} entities={entity_count}")
    ```

    **(Adjust `output_dir / lang` per the kb-1 driver's actual lang-output convention — if kb-1 puts lang prefix elsewhere, mirror it. The point is: per-lang output of topic + entity pages.)**

    **Extend `_render_index` context** to include `topics` + `featured_entities`. Find the existing context dict and add:

    ```python
    # Topic discovery — 5 fixed, ordered by article_count DESC, alpha tiebreak
    topic_summary = []
    for raw_topic in KB2_TOPICS:
        slug = TOPIC_SLUG_MAP[raw_topic]
        articles = topic_articles_query(raw_topic, depth_min=2, conn=conn)
        topic_summary.append({
            "slug": slug,
            "raw_topic": raw_topic,
            "localized_name": _t(env, f"topic.{slug}.name", lang),
            "localized_desc": _t(env, f"topic.{slug}.desc", lang),
            "article_count": len(articles),
        })
    topic_summary.sort(key=lambda t: (-t["article_count"], t["slug"]))

    # Featured entities — top 12 by article_count DESC, alpha tiebreak
    featured_entities = sorted(
        qualifying_entities,
        key=lambda e: (-e["article_count"], e["name"]),
    )[:12]

    context = {
        # ... existing kb-1 context ...
        "topics": topic_summary,
        "featured_entities": featured_entities,
    }
    ```

    **(`_render_index` will now receive `qualifying_entities` as a new param — pass it from main(). Same for `conn` if not already passed.)**

    **Extend `_render_article_detail` context** with related-link injection. Find the existing context dict and add:

    ```python
    # kb-2 LINK-01 + LINK-02: related entities + topics
    related_entity_objs = related_entities_for_article(
        rec.id, rec.source, limit=5, min_global_freq=KB_ENTITY_MIN_FREQ, conn=conn
    )
    related_topic_objs = related_topics_for_article(
        rec.id, rec.source, depth_min=2, limit=3, conn=conn
    )
    related_entities = [{"name": e.name, "slug": e.slug} for e in related_entity_objs]
    related_topics = [
        {"slug": t.slug, "localized_name": _t(env, f"topic.{t.slug}.name", lang)}
        for t in related_topic_objs
    ]

    context = {
        # ... existing kb-1 context ...
        "related_entities": related_entities,
        "related_topics": related_topics,
    }
    ```

    **Surgical changes:** do NOT modify the existing kb-1 render template calls, JSON-LD generation, or markdown→HTML pipeline. Only ADD context fields + ADD topic + entity loop calls.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "src = open('kb/export_knowledge_base.py', encoding='utf-8').read(); assert 'qualifying_entities' in src; assert '_render_topic_pages' in src; assert '_render_entity_pages' in src; assert 'related_entities' in src; assert 'related_topics' in src; assert 'featured_entities' in src; assert '\"topics\"' in src or 'topics=' in src or '\\'topics\\'' in src; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "qualifying_entities = _discover_qualifying_entities" kb/export_knowledge_base.py`
    - `grep -q "_render_topic_pages" kb/export_knowledge_base.py` (called in main, not just defined)
    - `grep -q "_render_entity_pages" kb/export_knowledge_base.py`
    - `grep -q "featured_entities" kb/export_knowledge_base.py`
    - `grep -q "related_entities" kb/export_knowledge_base.py`
    - `grep -q "related_topics" kb/export_knowledge_base.py`
    - Driver still runs: `KB_DB_PATH=tests/integration/kb/<temp> python kb/export_knowledge_base.py` (smoke — full integration in plan 10)
    - kb-1 regression: existing kb-1 integration tests still pass: `pytest tests/integration/kb/test_export.py -v` exits 0 (assertions may need updating in plan 10)
    - Read-only preserved: `grep -E "execute\\(.*(INSERT|UPDATE|DELETE) " kb/export_knowledge_base.py` returns 0
  </acceptance_criteria>
  <done>main() extended with topic + entity loops; homepage + article render contexts gain LINK-03 + LINK-01/02 fields; kb-1 untouched.</done>
</task>

</tasks>

<verification>
- 3 new helper functions added (_discover_qualifying_entities, _render_topic_pages, _render_entity_pages)
- main() wires them in correct order (after kb-1 article render, before _write_sitemap)
- Homepage context has topics + featured_entities
- Article context has related_entities + related_topics
- Read-only enforced (grep regression)
- Skill(skill="python-patterns") literal in PLAN.md
</verification>

<success_criteria>
- TOPIC-01 enabled: 5 topic HTMLs generated to kb/output/topics/{slug}.html
- TOPIC-03 enabled: each topic page receives localized name + desc + article count + cooccurring_entities context
- ENTITY-01 enabled: ~91 entity HTMLs generated (Hermes prod) at KB_ENTITY_MIN_FREQ=5 default
- ENTITY-03 enabled: entity render context has lang_zh + lang_en + lang_unknown for chip row
- LINK-01 enabled: each article detail context has related_entities (3-5)
- LINK-02 enabled: each article detail context has related_topics (1-3)
- LINK-03 enabled: homepage context has topics (5) + featured_entities (12)
</success_criteria>

<output>
After completion, create `.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-09-SUMMARY.md` documenting:
- 3 new helper functions
- main() wiring (loop order)
- Homepage + article context extensions
- Literal Skill(skill="python-patterns") string
- Foundation for plan 10 (integration test full pipeline)
</output>
