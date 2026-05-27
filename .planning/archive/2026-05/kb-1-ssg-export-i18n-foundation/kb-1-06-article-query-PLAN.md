---
phase: kb-1-ssg-export-i18n-foundation
plan: 06
type: execute
wave: 2
depends_on: ["kb-1-01-config-skeleton", "kb-1-02-migration-lang-detect"]
files_modified:
  - kb/data/article_query.py
  - tests/unit/kb/test_article_query.py
autonomous: true
requirements:
  - DATA-04
  - DATA-05
  - DATA-06

must_haves:
  truths:
    - "list_articles(lang, source, limit, offset) returns paginated ArticleRecord list sorted by update_time DESC"
    - "get_article_by_hash(hash) resolves md5[:10] across BOTH articles + rss_articles tables, returns ArticleRecord or None"
    - "resolve_url_hash(rec) implements 3-branch tree: KOL+content_hash→use it; KOL+NULL→md5(body)[:10]; RSS→content_hash[:10]"
    - "ALL queries are read-only (NEVER write to SQLite — EXPORT-02 enforced)"
    - "ArticleRecord is a frozen dataclass with documented fields"
  artifacts:
    - path: "kb/data/article_query.py"
      provides: "ArticleRecord + list_articles + get_article_by_hash + resolve_url_hash + get_article_body"
      exports: ["ArticleRecord", "list_articles", "get_article_by_hash", "resolve_url_hash", "get_article_body"]
  key_links:
    - from: "kb/data/article_query.py"
      to: "kb.config.KB_DB_PATH + KB_IMAGES_DIR"
      via: "from kb import config"
      pattern: "config\\.KB_DB_PATH|config\\.KB_IMAGES_DIR"
    - from: "kb/data/article_query.py::get_article_body"
      to: "filesystem images/{hash}/final_content[.enriched].md OR articles.body fallback"
      via: "D-14 fallback chain"
      pattern: "final_content\\.enriched\\.md|final_content\\.md"
---

<objective>
Build the read-only data layer that powers the SSG export. Five public functions on a single module: `ArticleRecord` dataclass, `list_articles()`, `get_article_by_hash()`, `resolve_url_hash()`, `get_article_body()`. Plan kb-1-09 (export driver) imports all five.

Purpose: This is the core of the kb-1 data plane. The export script needs to enumerate articles for list pages, resolve a hash → record for detail pages, compute the URL hash for href construction, and read the body markdown (with D-14 file-first fallback chain + EXPORT-05 image URL rewrite).

Output: Single Python module + comprehensive unit tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-01-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-02-SUMMARY.md
@kb/config.py
@kb/docs/03-ARCHITECTURE.md
@CLAUDE.md

<interfaces>
Locked function signatures (from CONTEXT.md "content_hash URL resolution (DATA-06)" and "Article body source resolution (D-14, EXPORT-04)"):

```python
from dataclasses import dataclass
from typing import Literal, Optional

@dataclass(frozen=True)
class ArticleRecord:
    id: int                          # SQLite PRIMARY KEY
    source: Literal["wechat", "rss"] # which table this row came from
    title: str
    url: str                         # original article URL
    body: str                        # raw body text (may be empty for unscoped rows)
    content_hash: Optional[str]      # may be NULL for KOL articles
    lang: Optional[str]              # 'zh-CN' | 'en' | 'unknown' | None
    update_time: str                 # ISO-8601-ish or whatever DB stores
    publish_time: Optional[str]      # for RSS articles


def list_articles(
    lang: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[ArticleRecord]: ...


def get_article_by_hash(hash: str) -> Optional[ArticleRecord]: ...


def resolve_url_hash(rec: ArticleRecord) -> str: ...
# Returns 10-char md5 prefix. Algorithm:
#   if rec.source == "wechat":
#       if rec.content_hash: return rec.content_hash  (already 10 chars)
#       return md5(rec.body.encode("utf-8")).hexdigest()[:10]  (runtime fallback)
#   elif rec.source == "rss":
#       return rec.content_hash[:10]  (truncate full md5 to 10)
#   else: raise ValueError


def get_article_body(rec: ArticleRecord) -> tuple[str, Literal["vision_enriched", "raw_markdown"]]:
    # D-14 fallback chain:
    #   1. {KB_IMAGES_DIR}/{hash}/final_content.enriched.md  -> ('vision_enriched')
    #   2. {KB_IMAGES_DIR}/{hash}/final_content.md            -> ('vision_enriched')
    #   3. rec.body (from DB)                                 -> ('raw_markdown')
    # Plus EXPORT-05: rewrite 'http://localhost:8765/' -> '/static/img/'
```

Schema (verified live):

```sql
CREATE TABLE articles (
  id INTEGER PRIMARY KEY,
  ...
  title TEXT,
  url TEXT,
  body TEXT,
  content_hash TEXT,    -- 10-char md5 prefix or NULL
  update_time TEXT,
  lang TEXT             -- added by kb-1-02 migration
);

CREATE TABLE rss_articles (
  id INTEGER PRIMARY KEY,
  ...
  title TEXT,
  url TEXT,
  body TEXT,
  content_hash TEXT,    -- 32-char full md5
  published_at TEXT,
  fetched_at TEXT,
  lang TEXT             -- added by kb-1-02 migration
);
```

Note: `articles` table has `update_time` column; `rss_articles` table uses `fetched_at` (or `published_at`). The query layer must NORMALIZE these into the dataclass's single `update_time` field. For `rss_articles`, prefer `published_at` if non-NULL else `fetched_at`.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Define ArticleRecord dataclass + resolve_url_hash + tests</name>
  <read_first>
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md "content_hash URL resolution (DATA-06)"
    - .planning/REQUIREMENTS-KB-v2.md DATA-06 (exact REQ wording)
    - .claude/rules/python/coding-style.md (frozen dataclass for immutability)
  </read_first>
  <files>kb/data/article_query.py, tests/unit/kb/test_article_query.py</files>
  <behavior>
    - Test 1: ArticleRecord is `@dataclass(frozen=True)` — attempting `rec.title = "x"` raises FrozenInstanceError
    - Test 2: `resolve_url_hash(ArticleRecord(source="wechat", content_hash="abcdef0123", body="..."))` returns `"abcdef0123"` (KOL with content_hash uses it directly)
    - Test 3: `resolve_url_hash(ArticleRecord(source="wechat", content_hash=None, body="hello world"))` returns `md5(b"hello world").hexdigest()[:10]` exactly (runtime fallback)
    - Test 4: `resolve_url_hash(ArticleRecord(source="rss", content_hash="e2a95c834a47f0f64c8e5826b5c3b9ab", body="..."))` returns `"e2a95c834a"` (truncate full md5 to 10 chars)
    - Test 5: `resolve_url_hash(ArticleRecord(source="unknown", ...))` raises ValueError
    - Test 6: `resolve_url_hash` is a pure function — does NOT touch DB, does NOT touch filesystem (verify by importing without env vars set)
  </behavior>
  <action>
    Create the start of `kb/data/article_query.py` with the ArticleRecord dataclass + resolve_url_hash function:

    ```python
    """DATA-04 + DATA-05 + DATA-06: Read-only article query layer.

    Five public functions consumed by kb/export_knowledge_base.py + (kb-3) kb/api.py:
    - ArticleRecord: dataclass row representation
    - list_articles(): paginated list query with optional filters
    - get_article_by_hash(): resolve md5[:10] -> ArticleRecord (both tables)
    - resolve_url_hash(): pure function computing the URL hash per source rules
    - get_article_body(): D-14 fallback chain for body content with EXPORT-05 image rewrite

    EXPORT-02 contract: NEVER writes to SQLite or to the images/ filesystem.
    All functions are read-only.
    """
    from __future__ import annotations

    import hashlib
    import re
    import sqlite3
    from dataclasses import dataclass
    from pathlib import Path
    from typing import Literal, Optional

    from kb import config

    Source = Literal["wechat", "rss"]
    BodySource = Literal["vision_enriched", "raw_markdown"]


    @dataclass(frozen=True)
    class ArticleRecord:
        """Immutable article row representation.

        Attributes:
            id: SQLite primary key (within its source table)
            source: 'wechat' (KOL articles table) or 'rss' (rss_articles table)
            title: article title
            url: original source URL
            body: raw body markdown (may be empty if not yet scraped)
            content_hash: KOL md5[:10] OR RSS full md5; may be None for KOL rows
            lang: 'zh-CN' | 'en' | 'unknown' | None (None until DATA-02 detect runs)
            update_time: ISO-8601-ish timestamp; for rss this is published_at or fetched_at
            publish_time: optional original publish time (RSS only typically)
        """
        id: int
        source: Source
        title: str
        url: str
        body: str
        content_hash: Optional[str]
        lang: Optional[str]
        update_time: str
        publish_time: Optional[str] = None


    def resolve_url_hash(rec: ArticleRecord) -> str:
        """Return the 10-char URL hash per source rules (DATA-06).

        Pure function: NO DB, NO filesystem.

        - source='wechat' + content_hash present -> use it directly (already 10 chars)
        - source='wechat' + content_hash is None -> md5(body)[:10] runtime fallback
        - source='rss' + content_hash present -> truncate full md5 to 10 chars
        - source='rss' + content_hash is None -> ValueError (RSS rows always have hash)
        - other source -> ValueError
        """
        if rec.source == "wechat":
            if rec.content_hash:
                return rec.content_hash
            return hashlib.md5(rec.body.encode("utf-8")).hexdigest()[:10]
        if rec.source == "rss":
            if rec.content_hash:
                return rec.content_hash[:10]
            raise ValueError(f"RSS row id={rec.id} has NULL content_hash (unexpected)")
        raise ValueError(f"unknown source: {rec.source}")
    ```

    Then write tests for the 6 behaviors at `tests/unit/kb/test_article_query.py` (this file will get more tests added in Task 2 + 3).
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; pytest tests/unit/kb/test_article_query.py -v -k "resolve_url_hash or ArticleRecord or frozen"</automated>
  </verify>
  <acceptance_criteria>
    - `kb/data/article_query.py` exists with `@dataclass(frozen=True)` decorator
    - File contains string `class ArticleRecord:`
    - File contains string `def resolve_url_hash`
    - `pytest -k "resolve_url_hash or ArticleRecord or frozen"` exits 0 with ≥ 6 tests passing
    - `python -c "from kb.data.article_query import ArticleRecord, resolve_url_hash; r=ArticleRecord(id=1, source='wechat', title='t', url='u', body='hello', content_hash=None, lang=None, update_time='2026-01-01'); print(resolve_url_hash(r))"` outputs a 10-char hex string
  </acceptance_criteria>
  <done>ArticleRecord + resolve_url_hash complete, 6 tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add list_articles + get_article_by_hash with SQL queries + tests</name>
  <read_first>
    - kb/data/article_query.py (Task 1 output — extends this file)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md "Module / file layout" + REQ → file mapping table
    - .planning/REQUIREMENTS-KB-v2.md DATA-04 + DATA-05 (exact wordings)
  </read_first>
  <files>kb/data/article_query.py, tests/unit/kb/test_article_query.py</files>
  <behavior>
    - Test 1: `list_articles()` with no filters on a fixture DB returns ALL passable rows from BOTH `articles` AND `rss_articles`, sorted by update_time DESC.
    - Test 2: `list_articles(lang='en')` filters BOTH tables to lang='en' rows only.
    - Test 3: `list_articles(source='wechat')` returns ONLY rows from articles table; `list_articles(source='rss')` returns ONLY rss_articles rows.
    - Test 4: `list_articles(limit=5, offset=10)` returns the 11th-15th rows by update_time DESC (pagination).
    - Test 5: `list_articles(lang='zh-CN', source='wechat')` filters to articles WHERE lang='zh-CN' (combined filter).
    - Test 6: `get_article_by_hash('abcd012345')` finds a KOL row whose content_hash matches → returns ArticleRecord with source='wechat'.
    - Test 7: `get_article_by_hash('e2a95c834a')` finds an RSS row whose content_hash STARTS WITH 'e2a95c834a' (10-char truncation match) → returns ArticleRecord with source='rss'.
    - Test 8: `get_article_by_hash('nonexistent')` returns None.
    - Test 9: For a KOL row with content_hash=NULL, `get_article_by_hash` falls back to computing md5(body)[:10] of each NULL-hash row and matching against the input hash. (This is the slow path — only invoked if direct content_hash match misses.)
    - Test 10: All queries are READ-ONLY — verified by spying that `conn.execute` only sees SELECT statements (no INSERT/UPDATE/DELETE).
  </behavior>
  <action>
    APPEND to `kb/data/article_query.py` (do not rewrite Task 1 content):

    ```python
    # ---- Query helpers ----

    def _connect() -> sqlite3.Connection:
        """Open read-only connection to KB_DB_PATH."""
        # SQLite URI mode allows mode=ro for true read-only enforcement
        uri = f"file:{config.KB_DB_PATH}?mode=ro"
        return sqlite3.connect(uri, uri=True)


    def _row_to_record_kol(row: sqlite3.Row) -> ArticleRecord:
        return ArticleRecord(
            id=row["id"],
            source="wechat",
            title=row["title"] or "",
            url=row["url"] or "",
            body=row["body"] or "",
            content_hash=row["content_hash"],
            lang=row["lang"],
            update_time=row["update_time"] or "",
            publish_time=None,
        )


    def _row_to_record_rss(row: sqlite3.Row) -> ArticleRecord:
        # RSS update_time normalization: prefer published_at, else fetched_at
        update_time = row["published_at"] or row["fetched_at"] or ""
        return ArticleRecord(
            id=row["id"],
            source="rss",
            title=row["title"] or "",
            url=row["url"] or "",
            body=row["body"] or "",
            content_hash=row["content_hash"],
            lang=row["lang"],
            update_time=update_time,
            publish_time=row["published_at"],
        )


    def list_articles(
        lang: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        conn: Optional[sqlite3.Connection] = None,
    ) -> list[ArticleRecord]:
        """DATA-04: Return paginated ArticleRecord list, sorted by update_time DESC.

        Args:
            lang: filter by content language ('zh-CN' | 'en' | 'unknown' | None)
            source: 'wechat' | 'rss' | None for both
            limit: page size (default 20)
            offset: skip this many rows
            conn: optional injected connection (for tests); else opens read-only

        Returns:
            list of ArticleRecord, sorted by normalized update_time DESC.
            Empty list on no matches.
        """
        own_conn = conn is None
        if own_conn:
            conn = _connect()
        conn.row_factory = sqlite3.Row
        try:
            results: list[ArticleRecord] = []
            if source != "rss":
                # KOL articles table
                sql = "SELECT id, title, url, body, content_hash, lang, update_time FROM articles"
                params: list = []
                clauses: list[str] = []
                if lang is not None:
                    clauses.append("lang = ?")
                    params.append(lang)
                if clauses:
                    sql += " WHERE " + " AND ".join(clauses)
                sql += " ORDER BY update_time DESC, id DESC"
                results.extend(_row_to_record_kol(r) for r in conn.execute(sql, params))
            if source != "wechat":
                # RSS articles table
                sql = (
                    "SELECT id, title, url, body, content_hash, lang, "
                    "published_at, fetched_at FROM rss_articles"
                )
                params = []
                clauses = []
                if lang is not None:
                    clauses.append("lang = ?")
                    params.append(lang)
                if clauses:
                    sql += " WHERE " + " AND ".join(clauses)
                sql += " ORDER BY COALESCE(published_at, fetched_at) DESC, id DESC"
                results.extend(_row_to_record_rss(r) for r in conn.execute(sql, params))
            # Re-sort merged across both tables by update_time DESC
            results.sort(key=lambda r: r.update_time, reverse=True)
            # Apply pagination after merge sort
            return results[offset:offset + limit]
        finally:
            if own_conn:
                conn.close()


    def get_article_by_hash(
        hash: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[ArticleRecord]:
        """DATA-05: Resolve md5[:10] -> ArticleRecord. Searches both tables.

        Resolution order:
        1. Direct match: articles.content_hash = ? (KOL with hash set, ~0.6%)
        2. Direct match (truncated): substr(rss_articles.content_hash, 1, 10) = ?
        3. Fallback: walk articles WHERE content_hash IS NULL, compute md5(body)[:10]
        """
        own_conn = conn is None
        if own_conn:
            conn = _connect()
        conn.row_factory = sqlite3.Row
        try:
            # Direct KOL match
            row = conn.execute(
                "SELECT id, title, url, body, content_hash, lang, update_time "
                "FROM articles WHERE content_hash = ?",
                (hash,),
            ).fetchone()
            if row:
                return _row_to_record_kol(row)
            # Direct RSS match (truncate full md5 to 10 in SQL)
            row = conn.execute(
                "SELECT id, title, url, body, content_hash, lang, "
                "published_at, fetched_at FROM rss_articles "
                "WHERE substr(content_hash, 1, 10) = ?",
                (hash,),
            ).fetchone()
            if row:
                return _row_to_record_rss(row)
            # Fallback: KOL rows with NULL content_hash (slow path)
            for row in conn.execute(
                "SELECT id, title, url, body, content_hash, lang, update_time "
                "FROM articles WHERE content_hash IS NULL"
            ):
                rec = _row_to_record_kol(row)
                if resolve_url_hash(rec) == hash:
                    return rec
            return None
        finally:
            if own_conn:
                conn.close()
    ```

    Then APPEND tests for the 10 behaviors above. Tests must use `conn=...` injection (in-memory SQLite fixture) so they don't depend on the production DB. Each test sets up `articles` and `rss_articles` tables with sample rows, passes that conn to the function, asserts results.

    For test 10, use `unittest.mock.patch.object` on `conn.execute` to capture all SQL strings, then assert all start with `SELECT` (case-insensitive).
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; pytest tests/unit/kb/test_article_query.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `pytest tests/unit/kb/test_article_query.py -v` exits 0 with ≥ 16 tests passing (Task 1 + Task 2 = 6 + 10)
    - File contains string `def list_articles`
    - File contains string `def get_article_by_hash`
    - File contains string `mode=ro` (read-only SQLite URI)
    - File does NOT contain any `INSERT`, `UPDATE`, or `DELETE` SQL keyword (in code body — comments OK; verify via `grep -E "execute\(.*(INSERT|UPDATE|DELETE)" kb/data/article_query.py` returns 0)
    - `python -c "from kb.data.article_query import list_articles, get_article_by_hash; print('OK')"` exits 0
  </acceptance_criteria>
  <done>list_articles + get_article_by_hash with full filter + pagination + resolution coverage; 16 tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Add get_article_body with D-14 fallback chain + EXPORT-05 image rewrite + tests</name>
  <read_first>
    - kb/data/article_query.py (Task 2 output — extends this file)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md "Article body source resolution (D-14, EXPORT-04)"
    - .planning/REQUIREMENTS-KB-v2.md EXPORT-04 (D-14 fallback) + EXPORT-05 (localhost:8765 -> /static/img rewrite)
  </read_first>
  <files>kb/data/article_query.py, tests/unit/kb/test_article_query.py</files>
  <behavior>
    - Test 1: When `{KB_IMAGES_DIR}/{hash}/final_content.enriched.md` exists, get_article_body reads it AND returns body_source='vision_enriched'.
    - Test 2: When `final_content.enriched.md` is absent BUT `final_content.md` exists, reads the latter AND returns 'vision_enriched'.
    - Test 3: When neither file exists, falls back to rec.body AND returns 'raw_markdown'.
    - Test 4: When all 3 sources are missing/empty, returns ('', 'raw_markdown') — no exception.
    - Test 5: Body containing `http://localhost:8765/path/img.png` is rewritten to `/static/img/path/img.png` AT READ TIME (EXPORT-05).
    - Test 6: Body containing `localhost:8765` without `http://` prefix is NOT rewritten (must be exact pattern `http://localhost:8765/`).
    - Test 7: Body containing multiple `http://localhost:8765/` strings — all are rewritten.
  </behavior>
  <action>
    APPEND to `kb/data/article_query.py`:

    ```python
    # ---- Body resolution (D-14) ----

    _IMAGE_SERVER_REWRITE = re.compile(r"http://localhost:8765/")


    def get_article_body(
        rec: ArticleRecord,
    ) -> tuple[str, BodySource]:
        """D-14 fallback chain for article body markdown.

        Resolution order:
        1. {KB_IMAGES_DIR}/{hash}/final_content.enriched.md  -> 'vision_enriched'
        2. {KB_IMAGES_DIR}/{hash}/final_content.md            -> 'vision_enriched'
        3. rec.body (from DB row)                              -> 'raw_markdown'

        Applies EXPORT-05 rewrite: 'http://localhost:8765/' -> '/static/img/'.

        Returns:
            (body_markdown, body_source) tuple.
        """
        url_hash = resolve_url_hash(rec)
        for fname in ("final_content.enriched.md", "final_content.md"):
            p = config.KB_IMAGES_DIR / url_hash / fname
            if p.exists():
                md = p.read_text(encoding="utf-8")
                md = _IMAGE_SERVER_REWRITE.sub("/static/img/", md)
                return md, "vision_enriched"
        # Fallback to DB body (already has whatever inline images were saved at scrape time)
        body = rec.body or ""
        body = _IMAGE_SERVER_REWRITE.sub("/static/img/", body)
        return body, "raw_markdown"
    ```

    Then APPEND tests for the 7 behaviors using `tmp_path` fixture for the IMAGES_DIR mock + `monkeypatch.setattr(config, 'KB_IMAGES_DIR', tmp_path)`.

    For test 5, write a fixture with body content `"# Title\\n\\n![](http://localhost:8765/abc/img.png)\\n\\nText"` and assert the returned body contains `"/static/img/abc/img.png"` and does NOT contain `"localhost:8765"`.

    For test 7, write body with 3 image refs all using `http://localhost:8765/` and assert all 3 are rewritten.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; pytest tests/unit/kb/test_article_query.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `pytest tests/unit/kb/test_article_query.py -v` exits 0 with ≥ 23 tests passing (Tasks 1+2+3 = 6 + 10 + 7)
    - File contains string `def get_article_body`
    - File contains string `final_content.enriched.md`
    - File contains string `_IMAGE_SERVER_REWRITE`
    - File contains string `/static/img/` (the rewrite target)
    - `python -c "from kb.data.article_query import get_article_body; print('OK')"` exits 0
    - Negative check: `grep "INSERT INTO\\|UPDATE\\|DELETE FROM" kb/data/article_query.py` returns 0 hits (read-only enforced for entire file)
  </acceptance_criteria>
  <done>Five-function module complete, 23 tests pass, all read-only, D-14 + EXPORT-05 implemented.</done>
</task>

</tasks>

<verification>
- `pytest tests/unit/kb/test_article_query.py -v` exits 0 with 23 tests passing
- `kb/data/article_query.py` has 5 public exports: ArticleRecord, list_articles, get_article_by_hash, resolve_url_hash, get_article_body
- Module is read-only (no INSERT/UPDATE/DELETE SQL anywhere)
</verification>

<success_criteria>
- DATA-04 satisfied: list_articles paginated + filtered + sorted
- DATA-05 satisfied: get_article_by_hash resolves both tables including NULL-hash KOL fallback
- DATA-06 satisfied: resolve_url_hash 3-branch tree complete
- D-14 + EXPORT-04 satisfied: get_article_body fallback chain + Pygments-ready content
- EXPORT-05 satisfied: localhost:8765 -> /static/img regex rewrite at body read time
- All 23 unit tests pass
</success_criteria>

<output>
After completion, create `.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-06-SUMMARY.md` documenting:
- Test pass count (target: 23)
- Read-only proof (grep enforcement)
- All 5 public exports listed
</output>
