---
phase: kb-3-fastapi-bilingual-api
plan: 02
subsystem: data
tags: [python, sqlite, tdd, data-quality-filter, read-only-queries]
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/data/article_query.py
  - tests/unit/kb/test_data07_quality_filter.py
  - tests/integration/kb/conftest.py
autonomous: true
requirements:
  - DATA-07

must_haves:
  truths:
    - "list_articles() excludes rows failing 3-condition filter: body present AND layer1_verdict='candidate' AND (layer2_verdict IS NULL OR != 'reject')"
    - "topic_articles_query() applies same DATA-07 filter (extends kb-2 cohort gate)"
    - "entity_articles_query() applies DATA-07 filter"
    - "cooccurring_entities_in_topic() applies DATA-07 filter (cohort articles must satisfy)"
    - "related_entities_for_article() applies DATA-07 filter on the source article"
    - "related_topics_for_article() applies DATA-07 filter on the source article"
    - "get_article_by_hash() does NOT apply filter (carve-out for direct URL access — search hits, KG sources, bookmarks must resolve)"
    - "KB_CONTENT_QUALITY_FILTER=off env var disables filter at module import time (debug kill-switch)"
    - "Module-level PRAGMA table_info() guard fails loud if any of the 3 columns (body, layer1_verdict, layer2_verdict) missing on either table"
  artifacts:
    - path: "kb/data/article_query.py"
      provides: "DATA-07 filter applied to all 6 list-style query functions; get_article_by_hash carve-out preserved"
      contains: "layer1_verdict = 'candidate'"
    - path: "tests/unit/kb/test_data07_quality_filter.py"
      provides: "TDD coverage for filter on/off + carve-out + schema-guard"
      min_lines: 200
    - path: "tests/integration/kb/conftest.py"
      provides: "fixture extension: add layer1_verdict + layer2_verdict columns + 2+ negative-case rows per source"
  key_links:
    - from: "kb/data/article_query.py (6 query functions)"
      to: "WHERE layer1_verdict = 'candidate' AND (layer2_verdict IS NULL OR layer2_verdict != 'reject') AND body IS NOT NULL AND body != ''"
      via: "SQL clause appended to each list-style function"
      pattern: "layer1_verdict = 'candidate'"
    - from: "kb/data/article_query.py module init"
      to: "PRAGMA table_info()"
      via: "schema-guard at import time"
      pattern: "PRAGMA table_info"
---

<objective>
Implement DATA-07 content-quality filter as 3 SQL conditions appended to all 6 list-style query functions in `kb/data/article_query.py`. The filter excludes rows failing ANY of: body NULL/empty, layer1_verdict != 'candidate', layer2_verdict = 'reject'. Single-article-by-hash lookup is the only carve-out — direct URL access stays intact.

Purpose: Per `kb-3-CONTENT-QUALITY-DECISIONS.md`, the kb-1 SSG output currently shows zero KOL articles in homepage cards because `list_articles()` returns all 2501 scanned rows including stubs/rejects. This plan ships the data-layer filter so kb-1 list page + kb-2 topic/entity pages + kb-3 /api/articles automatically inherit the quality bar. Expected visibility on Hermes prod: ~6% of scanned rows (~160/2501).

Output: extended article_query.py with filter SQL on 6 functions + env override + schema guard + dedicated unit test file + fixture extension covering positive AND negative cases.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-06-article-query-PLAN.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-04-query-functions-PLAN.md
@kb/data/article_query.py
@tests/integration/kb/conftest.py
@kb/docs/10-DESIGN-DISCIPLINE.md
@CLAUDE.md

<interfaces>
Existing kb-1 + kb-2 article_query.py exports — DO NOT modify signatures, only append SQL clauses inside each function:

```python
# kb-1 (preserve carve-out — get_article_by_hash NOT filtered)
def list_articles(lang=None, source=None, limit=20, offset=0, conn=None) -> list[ArticleRecord]: ...
def get_article_by_hash(hash, conn=None) -> Optional[ArticleRecord]: ...   # ← NO filter (DATA-07 carve-out)

# kb-2 (filter applies to all 5)
def topic_articles_query(topic, depth_min=2, conn=None) -> list[ArticleRecord]: ...
def entity_articles_query(entity_name, min_freq=5, conn=None) -> list[ArticleRecord]: ...
def related_entities_for_article(article_id, source, limit=5, min_global_freq=5, conn=None) -> list[EntityCount]: ...
def related_topics_for_article(article_id, source, depth_min=2, limit=3, conn=None) -> list[TopicSummary]: ...
def cooccurring_entities_in_topic(topic, limit=5, min_global_freq=5, depth_min=2, conn=None) -> list[EntityCount]: ...
```

DATA-07 SQL clause (paste-ready, from CONTENT-QUALITY-DECISIONS.md):

```sql
WHERE body IS NOT NULL
  AND body != ''
  AND layer1_verdict = 'candidate'
  AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')
```

Symmetric for both `articles` (KOL) and `rss_articles` tables (both have all 3 columns since v3.5 ir-4).

Schema guard (paste-ready):

```python
def _verify_quality_columns(conn: sqlite3.Connection) -> None:
    """DATA-07: fail loud at first call if any of (body, layer1_verdict, layer2_verdict)
    is missing on either articles or rss_articles. Catches schema drift early."""
    required = {"body", "layer1_verdict", "layer2_verdict"}
    for table in ("articles", "rss_articles"):
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        missing = required - cols
        if missing:
            raise RuntimeError(
                f"DATA-07 schema guard: table {table!r} missing columns {sorted(missing)}. "
                f"Either run migration to add them, or set KB_CONTENT_QUALITY_FILTER=off to bypass."
            )
```

Env override (paste-ready):

```python
import os
QUALITY_FILTER_ENABLED = os.environ.get("KB_CONTENT_QUALITY_FILTER", "on").lower() != "off"
```

Reads at module import once — no per-call overhead.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Invoke python-patterns + writing-tests Skills + extend fixture + add schema guard + env override</name>
  <read_first>
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md (full doc — locked decision)
    - kb/data/article_query.py (existing kb-1 + kb-2 module — APPEND only, never modify existing function signatures)
    - tests/integration/kb/conftest.py (kb-2 fixture builder — extend with verdict columns + negative-case rows)
    - .planning/REQUIREMENTS-KB-v2.md DATA-07 (exact REQ wording)
  </read_first>
  <files>kb/data/article_query.py, tests/integration/kb/conftest.py, tests/unit/kb/test_data07_quality_filter.py</files>
  <behavior>
    - Test 1: Module import with `KB_CONTENT_QUALITY_FILTER` unset → `QUALITY_FILTER_ENABLED == True`.
    - Test 2: Module import with `KB_CONTENT_QUALITY_FILTER=off` → reload module → `QUALITY_FILTER_ENABLED == False`.
    - Test 3: Module import with `KB_CONTENT_QUALITY_FILTER=OFF` (uppercase) → `QUALITY_FILTER_ENABLED == False` (case-insensitive).
    - Test 4: `_verify_quality_columns(conn)` on a connection where `articles` table is missing `layer1_verdict` raises RuntimeError mentioning the missing column.
    - Test 5: `_verify_quality_columns(conn)` on a healthy fixture conn (all columns present) returns None (no raise).
    - Test 6: Fixture extension: every positive-case row has `layer1_verdict='candidate'` + `layer2_verdict IN ('ok', NULL)` + `body != ''`.
    - Test 7: Fixture extension: at least 2 negative-case rows per source (KOL + RSS) — combinations of `body=NULL`, `layer1_verdict='reject'`, `layer2_verdict='reject'`.
  </behavior>
  <action>
    Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1, this plan invokes named Skills as tool calls before writing code:

    Skill(skill="python-patterns", args="Idiomatic module-level env var read pattern: `QUALITY_FILTER_ENABLED = os.environ.get('KB_CONTENT_QUALITY_FILTER', 'on').lower() != 'off'` evaluated once at import time. Schema-guard helper `_verify_quality_columns(conn)` using PRAGMA table_info() — fail loud with RuntimeError listing exact missing columns + the env override hint. Schema guard called lazily on first list-query invocation per process (cache `_schema_verified: bool` module flag) so test fixtures can pre-set conn before guard runs. No imports beyond stdlib (os, sqlite3).")

    Skill(skill="writing-tests", args="TDD tests for env override (3 cases: unset/off/OFF) + schema guard (2 cases: missing column raises, healthy passes) + fixture extension (verify positive rows have verdicts + ≥2 negative rows per source). Use `monkeypatch.setenv` + `importlib.reload(kb.data.article_query)` for env tests. Use `sqlite3.connect(':memory:')` to build a stripped-down articles table for the missing-column test (so we can simulate a pre-DATA-07 schema). Tests live at tests/unit/kb/test_data07_quality_filter.py.")

    **Step 1 — Extend fixture builder in `tests/integration/kb/conftest.py`** (locate `build_kb2_fixture_db` and APPEND verdict-column population):

    Find the CREATE TABLE statements for `articles` and `rss_articles`. Add columns if missing:

    ```python
    # In build_kb2_fixture_db, after CREATE TABLE articles ... :
    cur.execute("ALTER TABLE articles ADD COLUMN layer1_verdict TEXT")
    cur.execute("ALTER TABLE articles ADD COLUMN layer2_verdict TEXT")
    cur.execute("ALTER TABLE rss_articles ADD COLUMN layer1_verdict TEXT")
    cur.execute("ALTER TABLE rss_articles ADD COLUMN layer2_verdict TEXT")
    ```

    Then in the existing INSERT statements for fixture rows, populate verdicts so existing kb-2 tests still pass:
    - All currently-inserted positive-case rows MUST get `layer1_verdict='candidate'` and `layer2_verdict='ok'` (or NULL — pick mix).
    - ADD ≥2 NEW negative-case rows per source (rows that DATA-07 must exclude):
      - KOL row: `(id=99, title='REJECTED', body='', layer1_verdict='reject', ...)` — body empty AND layer1 reject
      - KOL row: `(id=98, title='LAYER2 REJ', body='real body', layer1_verdict='candidate', layer2_verdict='reject', ...)` — only layer2 rejects
      - RSS row: `(id=97, title='NULL BODY', body=NULL, layer1_verdict='candidate', ...)` — body NULL
      - RSS row: `(id=96, title='LAYER1 REJ', body='real body', layer1_verdict='reject', ...)` — layer1 reject

    Existing kb-2 tests should still pass because the kb-2 fixture had no DATA-07 awareness — adding these rows is additive. Re-run `pytest tests/unit/kb/test_kb2_queries.py -v` after fixture extension to confirm kb-2 tests still pass (the kb-2 query functions themselves don't yet apply DATA-07 — they will after Task 2).

    **Step 2 — Add module-level env + schema guard + utility constant to `kb/data/article_query.py`** (APPEND near top, just below imports):

    ```python
    # ---- DATA-07 content-quality filter ----
    # Per .planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md
    # Excludes rows where: body IS NULL/empty OR layer1_verdict != 'candidate' OR layer2_verdict = 'reject'
    QUALITY_FILTER_ENABLED = os.environ.get("KB_CONTENT_QUALITY_FILTER", "on").lower() != "off"

    # Schema verification (lazy — runs once per connection on first list-query call)
    _SCHEMA_VERIFIED: dict[str, bool] = {}


    def _verify_quality_columns(conn: sqlite3.Connection) -> None:
        """Fail loud if articles or rss_articles is missing any of (body, layer1_verdict,
        layer2_verdict). Catches schema drift early — without this, a missing column
        would silently produce zero results when filter is on."""
        # Use a per-conn-id cache key (id() of conn object — process-local OK for tests)
        key = f"{id(conn)}"
        if _SCHEMA_VERIFIED.get(key):
            return
        required = {"body", "layer1_verdict", "layer2_verdict"}
        for table in ("articles", "rss_articles"):
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            missing = required - cols
            if missing:
                raise RuntimeError(
                    f"DATA-07 schema guard: table {table!r} missing columns {sorted(missing)}. "
                    f"Either run migration to add them, or set "
                    f"KB_CONTENT_QUALITY_FILTER=off to bypass."
                )
        _SCHEMA_VERIFIED[key] = True


    # SQL fragment shared across all DATA-07-aware queries.
    # IMPORTANT: caller alias must be 'a' for KOL or 'r' for RSS — both tables have
    # the 3 columns. Inject into the WHERE clause AFTER any cohort/lang clauses.
    _DATA07_KOL_FRAGMENT = (
        "a.body IS NOT NULL AND a.body != '' "
        "AND a.layer1_verdict = 'candidate' "
        "AND (a.layer2_verdict IS NULL OR a.layer2_verdict != 'reject')"
    )
    _DATA07_RSS_FRAGMENT = (
        "r.body IS NOT NULL AND r.body != '' "
        "AND r.layer1_verdict = 'candidate' "
        "AND (r.layer2_verdict IS NULL OR r.layer2_verdict != 'reject')"
    )
    # Unaliased forms (for queries without table alias — list_articles non-JOINed paths)
    _DATA07_BARE = (
        "body IS NOT NULL AND body != '' "
        "AND layer1_verdict = 'candidate' "
        "AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')"
    )
    ```

    Add `Skill(skill="python-patterns")` and `Skill(skill="writing-tests")` literal strings as Python comments preceding the new code block, e.g.:

    ```python
    # Skill(skill="python-patterns", args="...idiomatic env var pattern...")
    # Skill(skill="writing-tests", args="...TDD for filter on/off + schema guard...")
    ```

    **Step 3 — Create `tests/unit/kb/test_data07_quality_filter.py`** with the 7 behaviors from `<behavior>` block:

    ```python
    """DATA-07 content-quality filter tests.

    Verifies env override + schema guard + fixture extension before filter is applied
    to query functions in Task 2.
    """
    from __future__ import annotations

    import importlib
    import sqlite3
    from pathlib import Path

    import pytest

    pytest_plugins = ["tests.integration.kb.conftest"]


    def _reload_module():
        import kb.data.article_query
        return importlib.reload(kb.data.article_query)


    def test_quality_filter_enabled_default(monkeypatch):
        monkeypatch.delenv("KB_CONTENT_QUALITY_FILTER", raising=False)
        m = _reload_module()
        assert m.QUALITY_FILTER_ENABLED is True


    def test_quality_filter_disabled_via_off(monkeypatch):
        monkeypatch.setenv("KB_CONTENT_QUALITY_FILTER", "off")
        m = _reload_module()
        assert m.QUALITY_FILTER_ENABLED is False


    def test_quality_filter_disabled_case_insensitive(monkeypatch):
        monkeypatch.setenv("KB_CONTENT_QUALITY_FILTER", "OFF")
        m = _reload_module()
        assert m.QUALITY_FILTER_ENABLED is False


    def test_schema_guard_raises_on_missing_column():
        from kb.data.article_query import _verify_quality_columns
        # Build a stripped-down articles table missing layer1_verdict
        c = sqlite3.connect(":memory:")
        c.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, body TEXT, layer2_verdict TEXT)")
        c.execute("CREATE TABLE rss_articles (id INTEGER PRIMARY KEY, body TEXT, layer1_verdict TEXT, layer2_verdict TEXT)")
        with pytest.raises(RuntimeError, match=r"layer1_verdict"):
            _verify_quality_columns(c)


    def test_schema_guard_passes_on_healthy_fixture(fixture_db):
        from kb.data.article_query import _verify_quality_columns, _SCHEMA_VERIFIED
        _SCHEMA_VERIFIED.clear()
        c = sqlite3.connect(str(fixture_db))
        try:
            _verify_quality_columns(c)  # should not raise
        finally:
            c.close()


    def test_fixture_has_positive_verdict_rows(fixture_db):
        c = sqlite3.connect(str(fixture_db))
        try:
            row = c.execute(
                "SELECT COUNT(*) FROM articles WHERE layer1_verdict='candidate' AND body!=''"
            ).fetchone()
            assert row[0] >= 3  # at least 3 positive KOL rows
        finally:
            c.close()


    def test_fixture_has_negative_verdict_rows(fixture_db):
        c = sqlite3.connect(str(fixture_db))
        try:
            kol_neg = c.execute(
                "SELECT COUNT(*) FROM articles "
                "WHERE body IS NULL OR body='' OR layer1_verdict='reject' OR layer2_verdict='reject'"
            ).fetchone()[0]
            rss_neg = c.execute(
                "SELECT COUNT(*) FROM rss_articles "
                "WHERE body IS NULL OR body='' OR layer1_verdict='reject' OR layer2_verdict='reject'"
            ).fetchone()[0]
            assert kol_neg >= 2, f"need ≥2 negative KOL rows, got {kol_neg}"
            assert rss_neg >= 2, f"need ≥2 negative RSS rows, got {rss_neg}"
        finally:
            c.close()
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/unit/kb/test_data07_quality_filter.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "QUALITY_FILTER_ENABLED" kb/data/article_query.py`
    - `grep -q "KB_CONTENT_QUALITY_FILTER" kb/data/article_query.py`
    - `grep -q "_verify_quality_columns" kb/data/article_query.py`
    - `grep -q "PRAGMA table_info" kb/data/article_query.py`
    - `grep -q 'layer1_verdict = .candidate.' kb/data/article_query.py`
    - `grep -q 'Skill(skill=\"python-patterns\"' kb/data/article_query.py` OR in plan SUMMARY (any literal occurrence in either)
    - `grep -q 'Skill(skill=\"writing-tests\"' kb/data/article_query.py` OR in plan SUMMARY
    - File `tests/unit/kb/test_data07_quality_filter.py` exists with ≥7 tests
    - `pytest tests/unit/kb/test_data07_quality_filter.py -v` exits 0 with ≥7 tests passing
    - kb-2 regression check: `pytest tests/unit/kb/test_kb2_queries.py -v` still exits 0 (fixture extension is additive)
    - kb-1 regression check: `pytest tests/unit/kb/test_article_query.py -v` still exits 0
  </acceptance_criteria>
  <done>Schema guard + env override + fixture extension complete; 7 unit tests pass; kb-1 + kb-2 baselines preserved.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Apply DATA-07 SQL filter to all 6 list-style query functions; preserve get_article_by_hash carve-out</name>
  <read_first>
    - kb/data/article_query.py (Task 1 output — existing fragments _DATA07_KOL_FRAGMENT / _DATA07_RSS_FRAGMENT / _DATA07_BARE)
    - tests/unit/kb/test_data07_quality_filter.py (Task 1 — APPEND new tests)
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md "Affected query functions" + "NOT affected (carve-out)"
  </read_first>
  <files>kb/data/article_query.py, tests/unit/kb/test_data07_quality_filter.py</files>
  <behavior>
    - Test 1: `list_articles(conn=fixture_db_conn)` excludes the 4 negative-case rows added in Task 1; returns only positive rows.
    - Test 2: `list_articles()` with `KB_CONTENT_QUALITY_FILTER=off` (env reload) returns ALL rows including negatives.
    - Test 3: `topic_articles_query("Agent", conn=fixture_db_conn)` excludes negative rows from Agent topic results.
    - Test 4: `entity_articles_query("OpenAI", conn=fixture_db_conn)` excludes any negative row that mentions OpenAI.
    - Test 5: `cooccurring_entities_in_topic("Agent", conn=fixture_db_conn)` cohort excludes negative rows from co-occurrence calculation.
    - Test 6: `related_entities_for_article(article_id=99_negative_kol, source="wechat", conn=fixture_db_conn)` returns [] because the source article fails the filter.
    - Test 7: `related_topics_for_article(99_negative_kol, "wechat", conn=fixture_db_conn)` returns [].
    - Test 8: **Carve-out preserved** — `get_article_by_hash(hash_of_negative_kol_row, conn=fixture_db_conn)` STILL returns the ArticleRecord (filter NOT applied; direct URL access intact).
    - Test 9: With `KB_CONTENT_QUALITY_FILTER=off` env, `list_articles()` count == count without filter (env override works on list).
    - Test 10: Read-only enforcement: SQL spy across all 6 modified functions captures only SELECT/WITH statements.
  </behavior>
  <action>
    Skill(skill="python-patterns", args="Apply DATA-07 SQL fragment to existing 6 list-style query functions WITHOUT changing their function signatures or return types. The pattern is: inside each function, after building the base SQL, append `if QUALITY_FILTER_ENABLED: sql += ' AND ' + _DATA07_FRAGMENT` for the appropriate alias. For functions with no existing WHERE clause (e.g. base list_articles when lang is None), use a small helper that inserts WHERE/AND correctly. Call _verify_quality_columns(conn) once per function entry (it caches via _SCHEMA_VERIFIED dict). Do NOT touch get_article_by_hash — DATA-07 carve-out preserved.")

    Skill(skill="writing-tests", args="Continue TDD coverage. APPEND to tests/unit/kb/test_data07_quality_filter.py: 10 tests covering filter applied to each of 6 list-style functions + carve-out preserved on get_article_by_hash + env-off reverts to unfiltered + read-only SQL spy. All tests use the shared fixture_db (which has positive + negative rows from Task 1 fixture extension).")

    **Step 1 — Modify each of 6 list-style query functions in `kb/data/article_query.py`.** For each function, the change is identical in pattern:

    ```python
    # Before each conn.execute(sql, params) — call schema guard:
    _verify_quality_columns(conn)

    # In the SQL string assembly, append DATA-07 fragment when enabled.
    # For aliased queries (have JOIN with `a.` or `r.` aliases):
    if QUALITY_FILTER_ENABLED:
        sql += " AND " + _DATA07_KOL_FRAGMENT  # for KOL paths
        # OR
        sql += " AND " + _DATA07_RSS_FRAGMENT  # for RSS paths

    # For unaliased list_articles SELECT FROM articles:
    if QUALITY_FILTER_ENABLED:
        if " WHERE " in sql:
            sql += " AND " + _DATA07_BARE
        else:
            sql += " WHERE " + _DATA07_BARE
    ```

    Apply to each function:

    1. **`list_articles`** (kb-1) — KOL path uses `FROM articles` (no alias). Append unaliased `_DATA07_BARE`. RSS path uses `FROM rss_articles` (no alias). Same pattern.

    2. **`topic_articles_query`** (kb-2) — KOL path JOIN with alias `a`, RSS path JOIN with alias `r`. Append `_DATA07_KOL_FRAGMENT` and `_DATA07_RSS_FRAGMENT` respectively.

    3. **`entity_articles_query`** (kb-2) — same JOIN pattern with `a` / `r` aliases. Append accordingly.

    4. **`cooccurring_entities_in_topic`** (kb-2) — uses CTE `WITH topic_articles AS (... FROM articles a JOIN ... UNION ALL ... FROM rss_articles r JOIN ...)`. Append `_DATA07_KOL_FRAGMENT` to the KOL leg and `_DATA07_RSS_FRAGMENT` to the RSS leg of the CTE.

    5. **`related_entities_for_article`** (kb-2) — adds article-existence check via subquery. Wrap the existing query with an early-return: if not QUALITY_FILTER_ENABLED, run as before; if enabled, first verify the source article passes the filter (single SELECT EXISTS check — return [] if it fails), then run existing query unchanged.

    6. **`related_topics_for_article`** (kb-2) — same as #5: early-return [] if source article fails DATA-07 filter (single EXISTS check), else run existing query unchanged.

    **DO NOT modify `get_article_by_hash`** — it is the explicit carve-out. Add a comment at top of that function:

    ```python
    # DATA-07 carve-out: this function is INTENTIONALLY UNFILTERED.
    # Direct hash access (search hits, KG sources, bookmarks) must resolve regardless
    # of quality verdicts. See kb-3-CONTENT-QUALITY-DECISIONS.md "NOT affected (carve-out)".
    ```

    **Step 2 — APPEND tests to `tests/unit/kb/test_data07_quality_filter.py`** matching the 10 behaviors from `<behavior>` block. Use these helpers:

    ```python
    def _conn(fixture_db: Path) -> sqlite3.Connection:
        c = sqlite3.connect(str(fixture_db))
        c.row_factory = sqlite3.Row
        return c


    def _hash_for_negative_kol_row(fixture_db: Path) -> str:
        """Return the URL hash of one of the negative-case KOL rows added in fixture
        extension (e.g. id=98 with layer2_verdict='reject')."""
        from kb.data.article_query import resolve_url_hash, _row_to_record_kol
        c = _conn(fixture_db)
        try:
            row = c.execute(
                "SELECT id, title, url, body, content_hash, lang, update_time "
                "FROM articles WHERE layer2_verdict='reject' LIMIT 1"
            ).fetchone()
            assert row is not None, "fixture must have at least one layer2_verdict='reject' row"
            return resolve_url_hash(_row_to_record_kol(row))
        finally:
            c.close()
    ```

    Sample test:

    ```python
    def test_get_article_by_hash_carve_out_preserved(fixture_db):
        """DATA-07 carve-out: direct hash access still works on negative-case rows."""
        from kb.data.article_query import get_article_by_hash
        h = _hash_for_negative_kol_row(fixture_db)
        with _conn(fixture_db) as c:
            rec = get_article_by_hash(h, conn=c)
        assert rec is not None
        assert rec.source == "wechat"


    def test_list_articles_excludes_negative_rows(fixture_db, monkeypatch):
        monkeypatch.delenv("KB_CONTENT_QUALITY_FILTER", raising=False)
        from kb.data import article_query
        importlib.reload(article_query)
        with _conn(fixture_db) as c:
            results = article_query.list_articles(limit=1000, conn=c)
        # Negative-case rows must NOT appear
        ids = {(r.id, r.source) for r in results}
        assert (99, "wechat") not in ids  # body='', layer1='reject'
        assert (98, "wechat") not in ids  # layer2='reject'
        assert (97, "rss") not in ids     # body=NULL
        assert (96, "rss") not in ids     # layer1='reject'
    ```

    Continue with the remaining 8 tests covering each query function + env-off override.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/unit/kb/test_data07_quality_filter.py -v && pytest tests/unit/kb/test_kb2_queries.py -v && pytest tests/unit/kb/test_article_query.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -cE "layer1_verdict = 'candidate'" kb/data/article_query.py` returns ≥6 (one per affected function — counted via fragment usages OR direct SQL)
    - `grep -q "DATA-07 carve-out" kb/data/article_query.py` (carve-out comment in get_article_by_hash)
    - `grep -A 30 "def get_article_by_hash" kb/data/article_query.py | grep -c "_DATA07"` returns 0 (carve-out function has zero DATA-07 references in body)
    - `pytest tests/unit/kb/test_data07_quality_filter.py -v` exits 0 with ≥17 tests passing (7 from Task 1 + 10 from Task 2)
    - kb-2 regression: `pytest tests/unit/kb/test_kb2_queries.py -v` exits 0 (fixture changes are additive — kb-2 tests filter on positive rows only and were already kept narrow)
    - kb-1 regression: `pytest tests/unit/kb/test_article_query.py -v` exits 0
    - Read-only enforcement: `grep -E "execute\\(.*(INSERT|UPDATE|DELETE) " kb/data/article_query.py` returns 0
    - Module imports: `python -c "from kb.data.article_query import list_articles, QUALITY_FILTER_ENABLED; print(QUALITY_FILTER_ENABLED)"` exits 0 outputs True
  </acceptance_criteria>
  <done>DATA-07 filter live on all 6 list functions; carve-out preserved on get_article_by_hash; ≥17 dedicated tests pass; no regression in kb-1 or kb-2 baselines.</done>
</task>

</tasks>

<verification>
- DATA-07 SQL fragment present and applied to all 6 list-style functions
- get_article_by_hash carve-out preserved with explanatory comment
- Schema guard fails loud on missing columns
- Env override `KB_CONTENT_QUALITY_FILTER=off` reverts to unfiltered
- Fixture extended with positive AND negative rows on both KOL + RSS
- Skill invocations literal in PLAN action AND will appear in SUMMARY (regex-verifiable)
- All tests pass: data07 (≥17) + kb-2 (≥18) + kb-1 (≥23) baselines preserved
</verification>

<success_criteria>
- DATA-07 REQ closed: 6 affected list-style functions filter, get_article_by_hash carve-out intact
- kb-1 list page + kb-2 topic/entity pages + kb-3 /api/articles automatically inherit filter on next consumer
- Env override available for debugging
- Schema-drift caught early (RuntimeError on import-time guard fail)
</success_criteria>

<output>
Create `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-02-SUMMARY.md` documenting:
- 6 affected functions + 1 carve-out (get_article_by_hash)
- ≥17 DATA-07 tests passing
- Skill invocation strings `Skill(skill="python-patterns", ...)` AND `Skill(skill="writing-tests", ...)` literal in summary for discipline regex match
- Fixture extension: ≥2 negative rows per source
- Cross-phase impact: kb-1 + kb-2 list output now filtered on next SSG re-render (no template changes needed)
</output>
</content>
</invoke>