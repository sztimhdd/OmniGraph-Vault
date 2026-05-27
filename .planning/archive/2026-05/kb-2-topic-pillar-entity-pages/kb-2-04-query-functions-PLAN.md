---
phase: kb-2-topic-pillar-entity-pages
plan: 04
subsystem: data
tags: [python, sqlite, tdd, read-only-queries]
type: execute
wave: 2
depends_on: ["kb-2-01-fixture-extension"]
files_modified:
  - kb/data/article_query.py
  - tests/unit/kb/test_kb2_queries.py
autonomous: true
requirements:
  - TOPIC-02
  - TOPIC-03
  - TOPIC-05
  - ENTITY-02
  - LINK-01
  - LINK-02

must_haves:
  truths:
    - "topic_articles_query(topic, depth_min=2) returns articles UNION-ed across KOL+RSS where classifications.depth_score >= depth_min AND (layer1_verdict='candidate' OR layer2_verdict='ok'), sorted by update_time DESC"
    - "entity_articles_query(entity_name, min_freq=5) returns articles where entity appears AND total entity frequency >= min_freq; if frequency < min_freq returns []"
    - "related_entities_for_article(article_id, source) returns 3-5 top entities for that article ranked by global frequency DESC"
    - "related_topics_for_article(article_id, source) returns 1-3 topics where depth_score >= 2 for that article"
    - "cooccurring_entities_in_topic(topic, limit=5) returns top entities by article frequency within topic article-set"
    - "ALL queries are read-only (NEVER write to SQLite — EXPORT-02 enforced)"
    - "All 5 functions have type hints, docstrings, parameterized SQL (no string concat)"
  artifacts:
    - path: "kb/data/article_query.py"
      provides: "+5 new query functions appended; existing 5 kb-1 functions preserved"
      exports: ["topic_articles_query", "entity_articles_query", "related_entities_for_article", "related_topics_for_article", "cooccurring_entities_in_topic"]
    - path: "tests/unit/kb/test_kb2_queries.py"
      provides: "TDD tests for all 5 new query functions against shared fixture_db"
      min_lines: 200
  key_links:
    - from: "kb/data/article_query.py (5 new functions)"
      to: "tests/integration/kb/conftest.py::build_kb2_fixture_db (plan 01)"
      via: "shared SQLite fixture with classifications + extracted_entities + layer verdicts"
      pattern: "build_kb2_fixture_db|fixture_db"
    - from: "kb/data/article_query.py (5 new functions)"
      to: "kb/export_knowledge_base.py (plan 09 driver loop)"
      via: "import & call pattern; driver iterates topics/entities and renders templates"
      pattern: "topic_articles_query|entity_articles_query|related_entities_for_article|related_topics_for_article|cooccurring_entities_in_topic"
---

<objective>
Add 5 read-only query functions to `kb/data/article_query.py` for TOPIC + ENTITY + LINK requirements. Each function follows the kb-1 pattern (frozen dataclass return, SQLite parameterization, optional `conn=` injection for tests). TDD-driven against shared `fixture_db` from plan 01.

Purpose: Without these functions, plans 05/06/07/08/09 cannot render any kb-2 page — the templates need topic-article lists, entity-article lists, related-entity / related-topic lists, and topic co-occurring entity lists. This plan is the data spine of kb-2.

Output: 1 file extended with 5 new functions + 1 test file with TDD coverage.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-01-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-06-article-query-PLAN.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-06-SUMMARY.md
@kb/data/article_query.py
@tests/integration/kb/conftest.py
@kb/docs/10-DESIGN-DISCIPLINE.md
@CLAUDE.md

<interfaces>
Existing kb-1 article_query.py exports (DO NOT modify these — append new functions only):

```python
@dataclass(frozen=True)
class ArticleRecord:  # already defined kb-1
    id: int
    source: Literal["wechat", "rss"]
    title: str
    url: str
    body: str
    content_hash: Optional[str]
    lang: Optional[str]
    update_time: str
    publish_time: Optional[str] = None

def list_articles(lang=None, source=None, limit=20, offset=0, conn=None) -> list[ArticleRecord]: ...
def get_article_by_hash(hash, conn=None) -> Optional[ArticleRecord]: ...
def resolve_url_hash(rec) -> str: ...
def get_article_body(rec) -> tuple[str, BodySource]: ...
```

Locked function signatures for kb-2 (per UI-SPEC §3 + §6 + REQUIREMENTS TOPIC-* / ENTITY-* / LINK-*):

```python
@dataclass(frozen=True)
class EntityCount:
    name: str
    slug: str            # lowercased + URL-safe (per ENTITY-02)
    article_count: int   # COUNT(DISTINCT (article_id, source))

@dataclass(frozen=True)
class TopicSummary:
    slug: str            # 'agent' | 'cv' | 'llm' | 'nlp' | 'rag'
    raw_topic: str       # 'Agent' | 'CV' | 'LLM' | 'NLP' | 'RAG' (db value)


def topic_articles_query(
    topic: str,
    depth_min: int = 2,
    conn: Optional[sqlite3.Connection] = None,
) -> list[ArticleRecord]:
    """TOPIC-02 cohort filter: classifications.depth_score >= depth_min
    AND (articles.layer1_verdict = 'candidate' OR articles.layer2_verdict = 'ok').
    UNION-ed across KOL articles + rss_articles. Sorted by update_time DESC.

    `topic` is the raw DB value: 'Agent' | 'CV' | 'LLM' | 'NLP' | 'RAG'."""


def entity_articles_query(
    entity_name: str,
    min_freq: int = 5,
    conn: Optional[sqlite3.Connection] = None,
) -> list[ArticleRecord]:
    """ENTITY-01 + ENTITY-03: list articles mentioning entity_name.
    If COUNT(DISTINCT article_id) < min_freq, returns [] (entity below threshold).
    Sorted by update_time DESC. UNION across KOL + RSS."""


def related_entities_for_article(
    article_id: int,
    source: Literal["wechat", "rss"],
    limit: int = 5,
    min_global_freq: int = 5,
    conn: Optional[sqlite3.Connection] = None,
) -> list[EntityCount]:
    """LINK-01: 3-5 entities for this article ordered by GLOBAL article frequency DESC.
    Filters to entities whose corpus-wide frequency >= min_global_freq (so we don't
    link to entity pages that don't exist). Returns [] if article has no qualifying
    entities."""


def related_topics_for_article(
    article_id: int,
    source: Literal["wechat", "rss"],
    depth_min: int = 2,
    limit: int = 3,
    conn: Optional[sqlite3.Connection] = None,
) -> list[TopicSummary]:
    """LINK-02: 1-3 topics where classifications.depth_score >= depth_min for
    this article. Sorted by depth_score DESC then topic alpha."""


def cooccurring_entities_in_topic(
    topic: str,
    limit: int = 5,
    min_global_freq: int = 5,
    depth_min: int = 2,
    conn: Optional[sqlite3.Connection] = None,
) -> list[EntityCount]:
    """TOPIC-05: top entities by article-frequency within the topic article cohort
    (same cohort gate as topic_articles_query). Returns up to `limit` entities ranked
    by COUNT(DISTINCT article_id) DESC within the topic. Filters out entities whose
    GLOBAL frequency < min_global_freq."""


def slugify_entity_name(name: str) -> str:
    """ENTITY-02: lowercase + spaces->'-' + drop unsafe chars. Preserves Unicode
    (Chinese names URL-encode at template emission time, not here)."""
```

Hermes prod schema (verified 2026-05-13 — same as plan 01 fixture):

```sql
CREATE TABLE classifications (
  id INTEGER PRIMARY KEY,
  article_id INTEGER NOT NULL,
  source TEXT NOT NULL CHECK(source IN ('wechat','rss')),
  topic TEXT NOT NULL CHECK(topic IN ('Agent','CV','LLM','NLP','RAG')),
  depth_score INTEGER,
  classified_at TEXT,
  UNIQUE(article_id, source, topic)
);

CREATE TABLE extracted_entities (
  id INTEGER PRIMARY KEY,
  article_id INTEGER NOT NULL,
  source TEXT NOT NULL CHECK(source IN ('wechat','rss')),
  name TEXT NOT NULL,
  extracted_at TEXT
);

-- articles + rss_articles already have layer1_verdict + layer2_verdict (added by kb-2 fixture).
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Invoke python-patterns + writing-tests Skills + add slugify_entity_name + topic_articles_query (TDD)</name>
  <read_first>
    - kb/data/article_query.py (existing kb-1 module — APPEND only, never modify existing functions)
    - tests/integration/kb/conftest.py (plan 01 — `build_kb2_fixture_db` + `fixture_db` fixture)
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §3.1 (topic page consumer of topic_articles_query)
    - .planning/REQUIREMENTS-KB-v2.md TOPIC-02 (cohort filter exact wording) + ENTITY-02 (slug rules)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-06-article-query-PLAN.md (mirror this pattern: dataclass + parameterized SQL + optional conn injection + sqlite3.Row factory + read-only)
  </read_first>
  <files>kb/data/article_query.py, tests/unit/kb/test_kb2_queries.py</files>
  <behavior>
    - Test 1: `slugify_entity_name("OpenAI")` returns `"openai"`.
    - Test 2: `slugify_entity_name("Lang Chain")` returns `"lang-chain"`.
    - Test 3: `slugify_entity_name("foo/bar")` returns `"foobar"` (slash dropped, not replaced — keeps single slug).
    - Test 4: `slugify_entity_name("叶小钗")` returns `"叶小钗"` (Unicode preserved).
    - Test 5: `slugify_entity_name("  hi  ")` returns `"hi"` (strip + collapse spaces).
    - Test 6: `topic_articles_query("Agent", conn=fixture_conn)` returns ≥3 ArticleRecords (per fixture: Agent has 5 classifications all depth>=2 + every fixture article has layer verdicts → 5 articles).
    - Test 7: `topic_articles_query("CV", conn=fixture_conn)` returns 2 ArticleRecords sorted by update_time DESC (article 12 RSS published 2026-05-08 should come before article 2 KOL with epoch 1778180400=2026-05-04 — verify the merge sort is correct given mixed timestamp formats).
    - Test 8: `topic_articles_query("LLM", depth_min=3, conn=fixture_conn)` returns only article 5 (its LLM classification has depth=3 in fixture; article 1 LLM=2 and article 10 LLM=2 are filtered out).
    - Test 9: `topic_articles_query("Agent", conn=fixture_conn)` returns articles UNION-ed from BOTH `articles` (KOL) and `rss_articles` (per fixture: article 1,3,5 KOL + 10,11 RSS = 5 total).
    - Test 10: SQL inspection — capture all `conn.execute` calls in the function; assert all start with `SELECT` (read-only enforced).
  </behavior>
  <action>
    Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1, this plan invokes named Skills as tool calls before writing code:

    Skill(skill="python-patterns", args="Idiomatic read-only sqlite3 query function with optional conn injection for tests, frozen dataclass return type, parameterized SQL (no string concat), type hints throughout. Mirror the existing kb/data/article_query.py kb-1 pattern: `_connect()` helper for ro URI, `sqlite3.Row` factory, `own_conn = conn is None` close-finally pattern. Module-level frozen dataclasses for return types. Also produce a `slugify_entity_name(name)` pure function: lowercase, strip+collapse whitespace to '-', drop ASCII unsafe chars (slash, ampersand, quote, etc.) but preserve Unicode (CJK). No imports beyond stdlib (sqlite3, re, dataclasses, typing).")

    Skill(skill="writing-tests", args="TDD tests for `slugify_entity_name` (5 cases: ASCII normal, ASCII with space, ASCII with slash, Unicode CJK, whitespace) and `topic_articles_query` (5 cases: returns ≥3 for Agent, sorted DESC for CV, depth=3 filter, UNION KOL+RSS, SQL is SELECT-only). Tests live at tests/unit/kb/test_kb2_queries.py and consume the shared `fixture_db` from tests/integration/kb/conftest.py via pytest dependency injection (use `from tests.integration.kb.conftest import build_kb2_fixture_db, fixture_db`). Use `sqlite3.connect(fixture_db)` to get a connection, pass `conn=` to the query function — DO NOT use mocks. Testing Trophy says integration > E2E > unit; these are integration-flavored unit tests against real SQLite.")

    **Step 1 — Append to `kb/data/article_query.py` (preserve all existing kb-1 code; add to bottom of file):**

    ```python
    # ---- kb-2 query functions (TOPIC + ENTITY + LINK) ----

    @dataclass(frozen=True)
    class EntityCount:
        """Entity name + URL slug + article count (used by entity cloud + sidebar)."""
        name: str
        slug: str            # lowercase + URL-safe (per ENTITY-02)
        article_count: int


    @dataclass(frozen=True)
    class TopicSummary:
        """Topic slug + raw DB value (used by related-topics chip + topic loops)."""
        slug: str            # 'agent' | 'cv' | 'llm' | 'nlp' | 'rag'
        raw_topic: str       # 'Agent' | 'CV' | 'LLM' | 'NLP' | 'RAG' (db value)


    _SLUG_DROP_CHARS = re.compile(r"[/\\&\"'<>?#%]+")
    _SLUG_WS = re.compile(r"\s+")


    def slugify_entity_name(name: str) -> str:
        """ENTITY-02: lowercase + URL-safe slug, Unicode preserved.

        Rules:
        - lowercase
        - strip leading/trailing whitespace
        - collapse internal whitespace to single '-'
        - drop URL-unsafe ASCII chars (slash, ampersand, quote, lt/gt, ?, #, %)
        - preserve Unicode (CJK names like 叶小钗 stay as-is; URL-encoding happens
          at template emission time)
        """
        s = (name or "").strip().lower()
        s = _SLUG_DROP_CHARS.sub("", s)
        s = _SLUG_WS.sub("-", s)
        return s


    def topic_articles_query(
        topic: str,
        depth_min: int = 2,
        conn: Optional[sqlite3.Connection] = None,
    ) -> list[ArticleRecord]:
        """TOPIC-02 cohort filter (per D-04 of plan kb-2-04 — addresses LF cohort gate).

        Returns ArticleRecords UNION-ed across articles + rss_articles where:
            classifications.depth_score >= depth_min
            AND (articles.layer1_verdict = 'candidate' OR articles.layer2_verdict = 'ok')
        Sorted by update_time DESC.

        Args:
            topic: raw DB value — one of 'Agent', 'CV', 'LLM', 'NLP', 'RAG'
            depth_min: minimum depth_score (default 2 per UI-SPEC TOPIC-02)
            conn: optional injected connection for tests
        """
        own_conn = conn is None
        if own_conn:
            conn = _connect()
        conn.row_factory = sqlite3.Row
        try:
            results: list[ArticleRecord] = []
            # KOL articles via classifications JOIN
            sql_kol = (
                "SELECT a.id, a.title, a.url, a.body, a.content_hash, a.lang, a.update_time "
                "FROM articles a "
                "JOIN classifications c ON c.article_id = a.id AND c.source = 'wechat' "
                "WHERE c.topic = ? AND c.depth_score >= ? "
                "AND (a.layer1_verdict = 'candidate' OR a.layer2_verdict = 'ok')"
            )
            for row in conn.execute(sql_kol, (topic, depth_min)):
                results.append(_row_to_record_kol(row))
            # RSS articles
            sql_rss = (
                "SELECT r.id, r.title, r.url, r.body, r.content_hash, r.lang, "
                "r.published_at, r.fetched_at "
                "FROM rss_articles r "
                "JOIN classifications c ON c.article_id = r.id AND c.source = 'rss' "
                "WHERE c.topic = ? AND c.depth_score >= ? "
                "AND (r.layer1_verdict = 'candidate' OR r.layer2_verdict = 'ok')"
            )
            for row in conn.execute(sql_rss, (topic, depth_min)):
                results.append(_row_to_record_rss(row))
            # Merge sort by update_time DESC (lexicographic — fixture uses ISO + epoch
            # mixed; for prod data both are ISO-comparable per kb-1-10 normalization)
            results.sort(key=lambda r: r.update_time, reverse=True)
            return results
        finally:
            if own_conn:
                conn.close()
    ```

    **Step 2 — Create `tests/unit/kb/test_kb2_queries.py`** (TDD-style — write tests, run, confirm RED before adding subsequent functions):

    ```python
    """TDD tests for kb-2 article_query.py extensions (plans 04 spec).

    Consumes the shared fixture_db from tests/integration/kb/conftest.py.
    Tests use direct sqlite3.connect(fixture_path) + conn= injection — no mocks.
    """
    from __future__ import annotations

    import sqlite3
    from pathlib import Path

    import pytest

    from kb.data.article_query import (
        slugify_entity_name,
        topic_articles_query,
        EntityCount,
        TopicSummary,
    )

    # Reuse the shared fixture (pytest auto-discovers conftest.py up the tree)
    pytest_plugins = ["tests.integration.kb.conftest"]


    # ---- slugify_entity_name ----

    def test_slugify_ascii_normal():
        assert slugify_entity_name("OpenAI") == "openai"

    def test_slugify_ascii_with_space():
        assert slugify_entity_name("Lang Chain") == "lang-chain"

    def test_slugify_ascii_with_slash():
        assert slugify_entity_name("foo/bar") == "foobar"

    def test_slugify_unicode_cjk():
        assert slugify_entity_name("叶小钗") == "叶小钗"

    def test_slugify_collapses_whitespace():
        assert slugify_entity_name("  hi  ") == "hi"


    # ---- topic_articles_query ----

    def _conn(fixture_db: Path) -> sqlite3.Connection:
        return sqlite3.connect(str(fixture_db))


    def test_topic_articles_agent_returns_union(fixture_db):
        with _conn(fixture_db) as c:
            results = topic_articles_query("Agent", conn=c)
        assert len(results) == 5  # 3 KOL (1,3,5) + 2 RSS (10,11) per fixture
        sources = {r.source for r in results}
        assert sources == {"wechat", "rss"}  # UNION proven

    def test_topic_articles_cv_sorted_desc(fixture_db):
        with _conn(fixture_db) as c:
            results = topic_articles_query("CV", conn=c)
        # CV: article 2 (KOL, update_time epoch 1778180400 = "1778180400") +
        #     article 12 (RSS, published_at "2026-05-08 08:00:00")
        # Lexicographic DESC: "2026-..." > "1778..." → RSS article 12 first
        assert len(results) == 2
        assert results[0].source == "rss" and results[0].id == 12

    def test_topic_articles_depth_3_filter(fixture_db):
        with _conn(fixture_db) as c:
            results = topic_articles_query("LLM", depth_min=3, conn=c)
        # Only article 5 has LLM depth=3 in fixture
        assert len(results) == 1
        assert results[0].id == 5

    def test_topic_articles_read_only(fixture_db, monkeypatch):
        captured: list[str] = []
        with _conn(fixture_db) as c:
            orig_execute = c.execute
            def spy(sql, *a, **k):
                captured.append(sql)
                return orig_execute(sql, *a, **k)
            monkeypatch.setattr(c, "execute", spy)
            topic_articles_query("Agent", conn=c)
        assert all(s.lstrip().upper().startswith("SELECT") for s in captured)
    ```

    Run: `pytest tests/unit/kb/test_kb2_queries.py -v` — RED expected on any function not yet implemented; GREEN after this task implements `slugify_entity_name` + `topic_articles_query`.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; pytest tests/unit/kb/test_kb2_queries.py -v -k "slugify or topic_articles"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "def slugify_entity_name" kb/data/article_query.py`
    - `grep -q "def topic_articles_query" kb/data/article_query.py`
    - `grep -q "class EntityCount" kb/data/article_query.py`
    - `grep -q "class TopicSummary" kb/data/article_query.py`
    - `grep -q "Skill(skill=\"python-patterns\"" .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-04-query-functions-PLAN.md`
    - `grep -q "Skill(skill=\"writing-tests\"" .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-04-query-functions-PLAN.md`
    - `pytest tests/unit/kb/test_kb2_queries.py -v -k "slugify or topic_articles"` exits 0 with ≥9 tests passing (5 slugify + 4 topic)
    - kb-1 regression check: `pytest tests/unit/kb/test_article_query.py -v` exits 0 with ≥23 tests passing (additive only)
    - Read-only enforced: `grep -E "execute\\(.*(INSERT|UPDATE|DELETE) " kb/data/article_query.py` returns 0
  </acceptance_criteria>
  <done>slugify_entity_name + topic_articles_query implemented with 9+ TDD tests passing; kb-1 baseline preserved.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add entity_articles_query + related_entities_for_article + related_topics_for_article + cooccurring_entities_in_topic (TDD)</name>
  <read_first>
    - kb/data/article_query.py (Task 1 output — APPEND only)
    - tests/unit/kb/test_kb2_queries.py (Task 1 output — APPEND only)
    - tests/integration/kb/conftest.py (fixture entities: 6 above-threshold + 2 below)
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §3.2 (entity page) + §3.4 (article aside)
    - .planning/REQUIREMENTS-KB-v2.md ENTITY-01..04 + LINK-01 + LINK-02
  </read_first>
  <files>kb/data/article_query.py, tests/unit/kb/test_kb2_queries.py</files>
  <behavior>
    - Test 1: `entity_articles_query("OpenAI", min_freq=5, conn=fixture)` returns 5 ArticleRecords (per fixture: OpenAI in articles 1,3,5 KOL + 10,11 RSS).
    - Test 2: `entity_articles_query("ObscureLib", min_freq=5, conn=fixture)` returns [] (ObscureLib has freq=2, below threshold).
    - Test 3: `entity_articles_query("ObscureLib", min_freq=2, conn=fixture)` returns 2 ArticleRecords (lowering threshold reveals it).
    - Test 4: `related_entities_for_article(article_id=1, source="wechat", conn=fixture)` returns ≤5 EntityCounts; each entity's `article_count` = its corpus-wide count; sorted DESC; below-threshold entities filtered out.
    - Test 5: `related_entities_for_article(1, "wechat", limit=3, conn=fixture)` returns exactly 3 EntityCounts.
    - Test 6: `related_topics_for_article(1, "wechat", conn=fixture)` returns 3 TopicSummary (Agent depth=3, LLM depth=2, RAG depth=2 per fixture); sorted by depth DESC.
    - Test 7: `related_topics_for_article(1, "wechat", depth_min=3, conn=fixture)` returns 1 TopicSummary (only Agent depth=3).
    - Test 8: `cooccurring_entities_in_topic("Agent", limit=5, conn=fixture)` returns ≤5 EntityCounts ranked by article frequency within Agent cohort; entities below global threshold excluded.
    - Test 9: All 4 functions are read-only (SQL spy passes).
  </behavior>
  <action>
    Skill(skill="python-patterns", args="Continue the same idiomatic pattern: parameterized SQL with `?` placeholders, frozen dataclass returns, optional conn injection. For ranking queries (related_entities_for_article, cooccurring_entities_in_topic) use SQL aggregation with GROUP BY + HAVING + ORDER BY COUNT DESC LIMIT — no Python-side bucket counting. For the JOIN between extracted_entities and the cohort gate, use a subquery / CTE that filters articles to the cohort first, then JOINs to entities.")

    Skill(skill="writing-tests", args="Continue TDD against fixture_db. Add 9 tests covering entity_articles_query (3 cases: above threshold returns N, below returns empty, lowered threshold reveals), related_entities_for_article (2 cases: returns sorted EntityCount with global counts, limit honored), related_topics_for_article (2 cases: returns 3 sorted by depth, depth_min filter narrows), cooccurring_entities_in_topic (1 case: ranks within Agent cohort), and 1 SQL-spy read-only test covering all 4 functions.")

    **APPEND to `kb/data/article_query.py`:**

    ```python
    def entity_articles_query(
        entity_name: str,
        min_freq: int = 5,
        conn: Optional[sqlite3.Connection] = None,
    ) -> list[ArticleRecord]:
        """ENTITY-01 + ENTITY-03: list articles mentioning entity_name.

        If COUNT(DISTINCT (article_id, source)) for entity_name < min_freq, returns
        [] — entity below threshold, do not surface a list page.
        Otherwise UNIONs articles + rss_articles whose id appears in
        extracted_entities for this name. Sorted by update_time DESC.
        """
        own_conn = conn is None
        if own_conn:
            conn = _connect()
        conn.row_factory = sqlite3.Row
        try:
            (freq,) = conn.execute(
                "SELECT COUNT(DISTINCT article_id || '-' || source) "
                "FROM extracted_entities WHERE name = ?",
                (entity_name,),
            ).fetchone()
            if freq < min_freq:
                return []
            results: list[ArticleRecord] = []
            for row in conn.execute(
                "SELECT a.id, a.title, a.url, a.body, a.content_hash, a.lang, a.update_time "
                "FROM articles a JOIN extracted_entities e "
                "ON e.article_id = a.id AND e.source = 'wechat' "
                "WHERE e.name = ?",
                (entity_name,),
            ):
                results.append(_row_to_record_kol(row))
            for row in conn.execute(
                "SELECT r.id, r.title, r.url, r.body, r.content_hash, r.lang, "
                "r.published_at, r.fetched_at "
                "FROM rss_articles r JOIN extracted_entities e "
                "ON e.article_id = r.id AND e.source = 'rss' "
                "WHERE e.name = ?",
                (entity_name,),
            ):
                results.append(_row_to_record_rss(row))
            results.sort(key=lambda r: r.update_time, reverse=True)
            return results
        finally:
            if own_conn:
                conn.close()


    def related_entities_for_article(
        article_id: int,
        source: str,
        limit: int = 5,
        min_global_freq: int = 5,
        conn: Optional[sqlite3.Connection] = None,
    ) -> list[EntityCount]:
        """LINK-01: 3-5 entities for this article ordered by GLOBAL article frequency DESC.

        Excludes entities whose corpus-wide DISTINCT-article frequency < min_global_freq
        (so we don't link to a /entities/{slug}.html page that won't exist).
        """
        own_conn = conn is None
        if own_conn:
            conn = _connect()
        conn.row_factory = sqlite3.Row
        try:
            sql = (
                "SELECT e.name, "
                "(SELECT COUNT(DISTINCT article_id || '-' || source) "
                " FROM extracted_entities WHERE name = e.name) AS global_freq "
                "FROM extracted_entities e "
                "WHERE e.article_id = ? AND e.source = ? "
                "GROUP BY e.name "
                "HAVING global_freq >= ? "
                "ORDER BY global_freq DESC, e.name ASC "
                "LIMIT ?"
            )
            return [
                EntityCount(
                    name=row["name"],
                    slug=slugify_entity_name(row["name"]),
                    article_count=row["global_freq"],
                )
                for row in conn.execute(sql, (article_id, source, min_global_freq, limit))
            ]
        finally:
            if own_conn:
                conn.close()


    _SLUG_TOPIC_MAP = {"Agent": "agent", "CV": "cv", "LLM": "llm", "NLP": "nlp", "RAG": "rag"}


    def related_topics_for_article(
        article_id: int,
        source: str,
        depth_min: int = 2,
        limit: int = 3,
        conn: Optional[sqlite3.Connection] = None,
    ) -> list[TopicSummary]:
        """LINK-02: 1-3 topics where classifications.depth_score >= depth_min for this article.

        Sorted by depth_score DESC then topic alpha. Returns TopicSummary with the
        slug already lowercased (matching kb/output/topics/{slug}.html convention).
        """
        own_conn = conn is None
        if own_conn:
            conn = _connect()
        conn.row_factory = sqlite3.Row
        try:
            return [
                TopicSummary(
                    slug=_SLUG_TOPIC_MAP.get(row["topic"], row["topic"].lower()),
                    raw_topic=row["topic"],
                )
                for row in conn.execute(
                    "SELECT topic, depth_score FROM classifications "
                    "WHERE article_id = ? AND source = ? AND depth_score >= ? "
                    "ORDER BY depth_score DESC, topic ASC LIMIT ?",
                    (article_id, source, depth_min, limit),
                )
            ]
        finally:
            if own_conn:
                conn.close()


    def cooccurring_entities_in_topic(
        topic: str,
        limit: int = 5,
        min_global_freq: int = 5,
        depth_min: int = 2,
        conn: Optional[sqlite3.Connection] = None,
    ) -> list[EntityCount]:
        """TOPIC-05: top entities by article-frequency within the topic article cohort.

        Cohort gate identical to topic_articles_query: classifications.depth_score >= depth_min
        AND (layer1_verdict = 'candidate' OR layer2_verdict = 'ok').
        Filters out entities whose GLOBAL frequency < min_global_freq.
        """
        own_conn = conn is None
        if own_conn:
            conn = _connect()
        conn.row_factory = sqlite3.Row
        try:
            sql = """
                WITH topic_articles AS (
                    SELECT a.id AS article_id, 'wechat' AS source
                    FROM articles a
                    JOIN classifications c ON c.article_id = a.id AND c.source = 'wechat'
                    WHERE c.topic = ? AND c.depth_score >= ?
                      AND (a.layer1_verdict = 'candidate' OR a.layer2_verdict = 'ok')
                    UNION ALL
                    SELECT r.id AS article_id, 'rss' AS source
                    FROM rss_articles r
                    JOIN classifications c ON c.article_id = r.id AND c.source = 'rss'
                    WHERE c.topic = ? AND c.depth_score >= ?
                      AND (r.layer1_verdict = 'candidate' OR r.layer2_verdict = 'ok')
                )
                SELECT e.name,
                       COUNT(DISTINCT e.article_id || '-' || e.source) AS topic_freq,
                       (SELECT COUNT(DISTINCT article_id || '-' || source)
                          FROM extracted_entities WHERE name = e.name) AS global_freq
                FROM extracted_entities e
                JOIN topic_articles t
                  ON t.article_id = e.article_id AND t.source = e.source
                GROUP BY e.name
                HAVING global_freq >= ?
                ORDER BY topic_freq DESC, e.name ASC
                LIMIT ?
            """
            return [
                EntityCount(
                    name=row["name"],
                    slug=slugify_entity_name(row["name"]),
                    article_count=row["topic_freq"],
                )
                for row in conn.execute(
                    sql, (topic, depth_min, topic, depth_min, min_global_freq, limit)
                )
            ]
        finally:
            if own_conn:
                conn.close()
    ```

    **APPEND to `tests/unit/kb/test_kb2_queries.py`** (after Task 1 tests):

    ```python
    from kb.data.article_query import (
        entity_articles_query,
        related_entities_for_article,
        related_topics_for_article,
        cooccurring_entities_in_topic,
    )


    def test_entity_articles_above_threshold(fixture_db):
        with _conn(fixture_db) as c:
            results = entity_articles_query("OpenAI", min_freq=5, conn=c)
        assert len(results) == 5  # OpenAI in 1,3,5 KOL + 10,11 RSS
        ids = {(r.id, r.source) for r in results}
        assert (1, "wechat") in ids and (10, "rss") in ids


    def test_entity_articles_below_threshold_empty(fixture_db):
        with _conn(fixture_db) as c:
            results = entity_articles_query("ObscureLib", min_freq=5, conn=c)
        assert results == []


    def test_entity_articles_lowered_threshold_returns_all(fixture_db):
        with _conn(fixture_db) as c:
            results = entity_articles_query("ObscureLib", min_freq=2, conn=c)
        assert len(results) == 2


    def test_related_entities_for_article(fixture_db):
        with _conn(fixture_db) as c:
            results = related_entities_for_article(1, "wechat", conn=c)
        assert all(isinstance(r, EntityCount) for r in results)
        assert len(results) <= 5
        # Each entity's article_count is its global frequency
        for r in results:
            assert r.article_count >= 5
        # Slugified
        names_to_slugs = {r.name: r.slug for r in results}
        if "OpenAI" in names_to_slugs:
            assert names_to_slugs["OpenAI"] == "openai"


    def test_related_entities_limit_honored(fixture_db):
        with _conn(fixture_db) as c:
            results = related_entities_for_article(1, "wechat", limit=3, conn=c)
        assert len(results) <= 3


    def test_related_topics_for_article(fixture_db):
        with _conn(fixture_db) as c:
            results = related_topics_for_article(1, "wechat", conn=c)
        # Article 1 has Agent (depth=3), LLM (depth=2), RAG (depth=2) per fixture
        assert len(results) == 3
        slugs = [t.slug for t in results]
        assert slugs[0] == "agent"  # depth=3 first


    def test_related_topics_depth_filter(fixture_db):
        with _conn(fixture_db) as c:
            results = related_topics_for_article(1, "wechat", depth_min=3, conn=c)
        assert len(results) == 1
        assert results[0].slug == "agent"


    def test_cooccurring_entities_in_topic(fixture_db):
        with _conn(fixture_db) as c:
            results = cooccurring_entities_in_topic("Agent", limit=5, conn=c)
        assert all(isinstance(r, EntityCount) for r in results)
        assert len(results) <= 5
        # All returned entities are above global threshold
        # Sorted by topic frequency DESC
        if len(results) >= 2:
            assert results[0].article_count >= results[1].article_count


    def test_kb2_queries_read_only(fixture_db, monkeypatch):
        captured: list[str] = []
        with _conn(fixture_db) as c:
            orig_execute = c.execute
            def spy(sql, *a, **k):
                captured.append(sql)
                return orig_execute(sql, *a, **k)
            monkeypatch.setattr(c, "execute", spy)
            entity_articles_query("OpenAI", conn=c)
            related_entities_for_article(1, "wechat", conn=c)
            related_topics_for_article(1, "wechat", conn=c)
            cooccurring_entities_in_topic("Agent", conn=c)
        # All SQL must be SELECT or WITH ... SELECT (CTE)
        for s in captured:
            head = s.lstrip().upper()
            assert head.startswith("SELECT") or head.startswith("WITH"), f"non-read SQL: {s[:80]}"
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; pytest tests/unit/kb/test_kb2_queries.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "def entity_articles_query" kb/data/article_query.py`
    - `grep -q "def related_entities_for_article" kb/data/article_query.py`
    - `grep -q "def related_topics_for_article" kb/data/article_query.py`
    - `grep -q "def cooccurring_entities_in_topic" kb/data/article_query.py`
    - `grep -q "WITH topic_articles AS" kb/data/article_query.py` (CTE pattern for cohort gate)
    - `pytest tests/unit/kb/test_kb2_queries.py -v` exits 0 with ≥18 tests passing (9 from Task 1 + 9 from Task 2)
    - kb-1 regression preserved: `pytest tests/unit/kb/test_article_query.py -v` exits 0
    - Read-only enforced: `grep -E "execute\\(.*(INSERT|UPDATE|DELETE) " kb/data/article_query.py` returns 0
    - Module imports without error: `python -c "from kb.data.article_query import topic_articles_query, entity_articles_query, related_entities_for_article, related_topics_for_article, cooccurring_entities_in_topic, slugify_entity_name; print('OK')"` exits 0
  </acceptance_criteria>
  <done>All 5 kb-2 query functions + slugify helper implemented; ≥18 TDD tests pass; module remains read-only.</done>
</task>

</tasks>

<verification>
- All 5 new query functions exist + are read-only
- 18+ TDD tests pass against shared fixture_db
- kb-1 baseline unchanged
- python-patterns + writing-tests Skill invocations literal in PLAN action AND SUMMARY (regex-verifiable)
</verification>

<success_criteria>
- TOPIC-02 enabled: topic_articles_query implements the cohort filter exactly per REQ wording
- TOPIC-03 enabled: TopicSummary + slug derivation supports localized name + desc lookup
- TOPIC-05 enabled: cooccurring_entities_in_topic returns top-5 entity ranking
- ENTITY-02 enabled: slugify_entity_name handles ASCII + Unicode safely
- LINK-01 enabled: related_entities_for_article returns 3-5 entities ranked by global frequency
- LINK-02 enabled: related_topics_for_article returns 1-3 topics ranked by depth
</success_criteria>

<output>
After completion, create `.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-04-SUMMARY.md` documenting:
- 5 new query functions + 2 dataclasses + 1 slugify helper
- ≥18 TDD tests passing (9 + 9)
- Skill invocation strings present (Skill(skill="python-patterns") + Skill(skill="writing-tests"))
- Read-only enforcement
- Foundation for plans 05/06/07/08/09 (templates + driver call these functions)
</output>
