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
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Literal, Optional

from kb import config

Source = Literal["wechat", "rss"]
BodySource = Literal["vision_enriched", "raw_markdown"]


# ---- DATA-07 content-quality filter ----
# Per .planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md
# Excludes rows where: body IS NULL/empty OR layer1_verdict != 'candidate'
# OR layer2_verdict = 'reject'.
#
# Skill(skill="python-patterns", args="Idiomatic module-level env var read pattern: QUALITY_FILTER_ENABLED evaluated once at import. Schema-guard helper using PRAGMA table_info() — fail loud with RuntimeError listing exact missing columns + the env override hint. Schema guard called lazily on first list-query invocation per process (cache via _SCHEMA_VERIFIED dict keyed on id(conn)). No imports beyond stdlib (os, sqlite3).")
# Skill(skill="writing-tests", args="TDD tests for env override (3 cases: unset/off/OFF) + schema guard (2 cases: missing column raises, healthy passes) + fixture extension (positive verdicts + ≥2 negative rows per source). monkeypatch.setenv + importlib.reload for env tests. sqlite3.connect(':memory:') stripped-down articles table for missing-column test.")
QUALITY_FILTER_ENABLED = os.environ.get("KB_CONTENT_QUALITY_FILTER", "on").lower() != "off"

# Schema verification cache — runs once per connection on first list-query call.
# Keyed on id(conn) so test fixtures can pre-build a stripped-down conn and
# re-verify a fresh fixture conn in the same process.
_SCHEMA_VERIFIED: dict[int, bool] = {}


def _verify_quality_columns(conn: sqlite3.Connection) -> None:
    """Fail loud if articles or rss_articles is missing any of (body,
    layer1_verdict, layer2_verdict). Catches schema drift early — without
    this, a missing column would silently produce zero results when filter
    is on.
    """
    key = id(conn)
    if _SCHEMA_VERIFIED.get(key):
        return
    required = {"body", "layer1_verdict", "layer2_verdict"}
    for table in ("articles", "rss_articles"):
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        missing = required - cols
        if missing:
            raise RuntimeError(
                f"DATA-07 schema guard: table {table!r} missing columns "
                f"{sorted(missing)}. Either run migration to add them, or set "
                f"KB_CONTENT_QUALITY_FILTER=off to bypass."
            )
    _SCHEMA_VERIFIED[key] = True


# SQL fragment shared across DATA-07-aware queries.
# Aliased forms for JOIN paths (kb-2 queries use `a.` for KOL, `r.` for RSS).
# Bare form for unaliased paths (kb-1 list_articles).
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
_DATA07_BARE = (
    "body IS NOT NULL AND body != '' "
    "AND layer1_verdict = 'candidate' "
    "AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')"
)


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


# ---- Query helpers ----


def _connect() -> sqlite3.Connection:
    """Open a read-only connection to KB_DB_PATH using SQLite URI mode."""
    uri = f"file:{config.KB_DB_PATH}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _normalize_update_time(raw) -> str:
    """Normalize the raw articles.update_time column to a sortable ISO-8601 string.

    Production: articles.update_time is INTEGER (Unix epoch seconds, e.g. 1777249680).
    Legacy/test: may be TEXT ISO-8601. Both must produce ISO-8601 string output so
    list_articles can sort uniformly across articles + rss_articles (rss has TEXT
    published_at/fetched_at, mixing them with raw INT epochs raised TypeError at
    the merge sort — see kb-1-VERIFICATION.md gap 1).

    Returns '' on None / empty / zero (preserves prior empty-string contract).
    """
    if raw is None or raw == "" or raw == 0:
        return ""
    if isinstance(raw, int):
        return datetime.fromtimestamp(raw, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S+00:00"
        )
    return str(raw)  # TEXT path: pass through unchanged


def _normalize_rss_update_time(
    published_at: Optional[str], fetched_at: Optional[str]
) -> str:
    """Normalize RSS published_at to ISO-8601 for cross-table merge sort with KOL articles.

    rss_articles.published_at is heterogeneous in production: some rows are ISO-8601
    ('2026-05-02T17:26:40+00:00'), others are RFC 822 ('Wed, 02 May 2026 17:26:40 +0000').
    Lexicographic DESC sort against KOL ISO-8601 puts all RFC 822 rows ahead of ISO rows
    ('W' > '2' in ASCII) — KOL articles get pushed past list_articles() limit.

    Strategy:
        - 'YYYY-' prefix (4 digits + dash) → ISO-8601, pass through
        - Otherwise → parse as RFC 822 (with or without weekday prefix; RFC 822 day-of-week
          is optional, so '02 May 2026 17:26:40 +0000' is also valid)
        - Parse failure or empty published_at → fall back to fetched_at

    fetched_at is space-separated ISO from ingest cron ('2026-05-03 00:11:59'); its
    lex-prefix matches ISO-8601 at the date level so the merge sort stays correct.

    Returns '' when both inputs are empty / unparseable.
    """
    if published_at:
        # ISO-8601 discriminator: 'YYYY-' prefix. Stricter than first-char-digit because
        # RFC 822 day-of-week is optional and digit-leading strings like '7 Aug 2017'
        # are valid RFC 822 that would slip through a looser check.
        if (
            len(published_at) >= 5
            and published_at[0:4].isdigit()
            and published_at[4] == "-"
        ):
            return published_at
        try:
            dt = parsedate_to_datetime(published_at)
        except (TypeError, ValueError):
            dt = None
        if dt is not None:
            return dt.isoformat()
    return fetched_at or ""


def _row_to_record_kol(row) -> ArticleRecord:
    return ArticleRecord(
        id=row["id"],
        source="wechat",
        title=row["title"] or "",
        url=row["url"] or "",
        body=row["body"] or "",
        content_hash=row["content_hash"],
        lang=row["lang"],
        update_time=_normalize_update_time(row["update_time"]),
        publish_time=None,
    )


def _row_to_record_rss(row) -> ArticleRecord:
    # Normalize RSS update_time: ISO-8601 pass-through OR RFC 822 → ISO; fallback fetched_at.
    # Cross-source merge-sort fix (260514-av8 quick task) — see _normalize_rss_update_time.
    update_time = _normalize_rss_update_time(row["published_at"], row["fetched_at"])
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

    Reads from BOTH `articles` and `rss_articles` tables (unless `source`
    selects one), merges results, sorts by normalized update_time DESC,
    then applies offset/limit pagination.

    Args:
        lang: filter by content language ('zh-CN' | 'en' | 'unknown' | None)
        source: 'wechat' | 'rss' | None for both
        limit: page size (default 20)
        offset: skip this many rows from the merged list
        conn: optional injected connection (for tests); else opens read-only

    Returns:
        list of ArticleRecord, sorted by update_time DESC. Empty if no matches.
    """
    own_conn = conn is None
    if own_conn:
        conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        # DATA-07 schema guard runs lazily on first list-query call per conn.
        # Skipped when filter disabled — operators can use env override on
        # pre-DATA-07 schemas without first migrating columns.
        if QUALITY_FILTER_ENABLED:
            _verify_quality_columns(conn)
        results: list[ArticleRecord] = []
        if source != "rss":
            sql = "SELECT id, title, url, body, content_hash, lang, update_time FROM articles"
            params: list = []
            if lang is not None:
                sql += " WHERE lang = ?"
                params.append(lang)
            if QUALITY_FILTER_ENABLED:
                sql += " AND " if " WHERE " in sql else " WHERE "
                sql += _DATA07_BARE
            sql += " ORDER BY update_time DESC, id DESC"
            results.extend(_row_to_record_kol(r) for r in conn.execute(sql, params))
        if source != "wechat":
            sql = (
                "SELECT id, title, url, body, content_hash, lang, "
                "published_at, fetched_at FROM rss_articles"
            )
            params = []
            if lang is not None:
                sql += " WHERE lang = ?"
                params.append(lang)
            if QUALITY_FILTER_ENABLED:
                sql += " AND " if " WHERE " in sql else " WHERE "
                sql += _DATA07_BARE
            sql += " ORDER BY COALESCE(published_at, fetched_at) DESC, id DESC"
            results.extend(_row_to_record_rss(r) for r in conn.execute(sql, params))
        # Merge sort across both tables.
        results.sort(key=lambda r: r.update_time, reverse=True)
        return results[offset : offset + limit]
    finally:
        if own_conn:
            conn.close()


def get_article_by_hash(
    hash: str,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[ArticleRecord]:
    """DATA-05: Resolve md5[:10] -> ArticleRecord by searching both tables.

    Resolution order:
        1. articles.content_hash = ? (KOL with hash set, ~0.6% of corpus)
        2. substr(rss_articles.content_hash, 1, 10) = ? (truncated full md5)
        3. Fallback: walk articles WHERE content_hash IS NULL, compute
           md5(body)[:10] and compare. (Slow path — only when 1+2 miss.)

    Returns ArticleRecord or None.

    DATA-07 carve-out: this function is INTENTIONALLY UNFILTERED.
    Direct hash access (search hits, KG sources, bookmarks) must resolve
    regardless of quality verdicts. See
    .planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md
    "NOT affected (carve-out)".
    """
    own_conn = conn is None
    if own_conn:
        conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        # 1. Direct KOL match
        row = conn.execute(
            "SELECT id, title, url, body, content_hash, lang, update_time "
            "FROM articles WHERE content_hash = ?",
            (hash,),
        ).fetchone()
        if row:
            return _row_to_record_kol(row)
        # 2. Direct RSS match (truncate full md5 to 10 in SQL)
        row = conn.execute(
            "SELECT id, title, url, body, content_hash, lang, "
            "published_at, fetched_at FROM rss_articles "
            "WHERE substr(content_hash, 1, 10) = ?",
            (hash,),
        ).fetchone()
        if row:
            return _row_to_record_rss(row)
        # 3. Fallback: KOL rows with NULL content_hash (slow path)
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


# ---- Body resolution (D-14) ----

# EXPORT-05: rewrite the local image-server URL prefix to the static mount path.
_IMAGE_SERVER_REWRITE = re.compile(r"http://localhost:8765/")


# kb-v2.1-6: Phase 5-00 retrieval-binding plain-text image refs
# (ingest_wechat.py:1303 — DO NOT MODIFY ingestion; this is the export-side bridge).
# Format emitted by ingestion: "Image {N} from article '{title}': {local_url}"
# After _rewrite_image_paths runs, {local_url} has been rewritten to the deploy
# URL (e.g. "/static/img/abc/0.jpg" or "/kb/static/img/abc/0.jpg"); this regex
# converts the plain-text line into a real <img> tag for browser rendering.
#
# Title with a single apostrophe is a known limitation: [^']* stops at the
# first ' so the regex would not match such a line — input passes through
# unchanged (graceful degradation). Test 5 covers this.
_IMG_TEXT_REF_PATTERN = re.compile(
    r"Image (\d+) from article '([^']*)': (\S+)"
)


def _rewrite_image_text_refs_to_html(body: str) -> str:
    """Convert Phase 5-00 retrieval-binding plain-text image refs into ``<img>`` tags.

    Phase 5-00 (Hermes 2f576b1, ``ingest_wechat.py:1303``) emits each downloaded
    image as a plain-text line in the article body so LightRAG ``aquery`` can
    correlate the parent doc with the sub-doc image descriptions during
    ``kg_synthesize``. SSG export and ``/api/article/{hash}`` need ``<img>``
    tags for browser rendering. This function is the export-side bridge.

    Idempotent: ``<img>`` output does not contain the literal
    "Image N from article" so the regex won't re-match.

    Caller order: invoke AFTER ``_rewrite_image_paths()`` so the URL prefix
    (``KB_BASE_PATH``) is already correct for the deployment target.

    Pure function — no I/O, no global mutation. Safe to call from anywhere
    that has body markdown post-``_rewrite_image_paths``.

    Args:
        body: markdown body. Empty string and ``None``-ish values pass
            through unchanged.

    Returns:
        Body with plain-text image refs replaced by ``<img>`` tags.
        Markdown image syntax (``![alt](url)``) is left untouched — only
        the Phase 5-00 plain-text format is rewritten.
    """
    if not body:
        return body
    return _IMG_TEXT_REF_PATTERN.sub(
        lambda m: f'<img src="{m.group(3)}" alt="image {m.group(1)}" loading="lazy">',
        body,
    )


def _rewrite_image_paths(body_md: str, base_path: str = "") -> str:
    """Rewrite image URLs in ``body_md`` so they resolve under the configured
    deploy root.

    Two passes:
        1. ``http://localhost:8765/X`` → ``{base_path}/static/img/X``
           (EXPORT-05 contract — ``final_content.md`` hardcodes the legacy
           image-server URL; rewrite at read time.)
        2. (Only when ``base_path`` is non-empty.) Bare ``/static/img/`` that
           is NOT already preceded by ``base_path`` gets the prefix.
           Implemented with a negative lookbehind so already-prefixed paths
           pass through unchanged — function is idempotent.

    Pure function (no I/O, no global mutation) — safe to call from anywhere
    that has body markdown and the desired base_path. Reused by
    ``get_article_body`` here and by ``kb.export_knowledge_base`` so SSG and
    API responses agree on the rewrite contract.

    Args:
        body_md: markdown body. Empty string and ``None``-ish values pass
            through unchanged.
        base_path: deploy root prefix without trailing slash, e.g. ``""`` for
            root deploy or ``"/kb"`` for subdir-mounted deploy. Mirrors
            ``kb.config.KB_BASE_PATH``.

    Returns:
        Rewritten markdown. Identical input produces identical output on
        repeat calls (idempotency).
    """
    if not body_md:
        return body_md
    rewritten = _IMAGE_SERVER_REWRITE.sub(f"{base_path}/static/img/", body_md)
    if base_path:
        rewritten = re.sub(
            rf"(?<!{re.escape(base_path)})/static/img/",
            f"{base_path}/static/img/",
            rewritten,
        )
    return rewritten


def get_article_body(rec: ArticleRecord) -> tuple[str, BodySource]:
    """D-14 fallback chain for article body markdown.

    Resolution order:
        1. {KB_IMAGES_DIR}/{hash}/final_content.enriched.md  -> 'vision_enriched'
        2. {KB_IMAGES_DIR}/{hash}/final_content.md            -> 'vision_enriched'
        3. rec.body (from DB row)                              -> 'raw_markdown'

    Applies EXPORT-05 + kb-v2.1-2 image-path rewrite at read time:
        'http://localhost:8765/' -> '{KB_BASE_PATH}/static/img/'
        bare '/static/img/'      -> '{KB_BASE_PATH}/static/img/' (when set)

    Returns:
        (body_markdown, body_source) tuple.
    """
    base_path = config.KB_BASE_PATH
    url_hash = resolve_url_hash(rec)
    images_dir = Path(config.KB_IMAGES_DIR)
    for fname in ("final_content.enriched.md", "final_content.md"):
        p = images_dir / url_hash / fname
        if p.exists():
            md = p.read_text(encoding="utf-8")
            md = _rewrite_image_paths(md, base_path)
            md = _rewrite_image_text_refs_to_html(md)  # kb-v2.1-6
            return md, "vision_enriched"
    body = rec.body or ""
    body = _rewrite_image_paths(body, base_path)
    body = _rewrite_image_text_refs_to_html(body)  # kb-v2.1-6
    return body, "raw_markdown"


# ---- kb-2 query functions (TOPIC + ENTITY + LINK) ----


@dataclass(frozen=True)
class EntityCount:
    """Entity name + URL slug + article count (used by entity cloud + sidebar)."""

    name: str
    slug: str  # lowercase + URL-safe (per ENTITY-02)
    article_count: int


@dataclass(frozen=True)
class TopicSummary:
    """Topic slug + raw DB value (used by related-topics chip + topic loops)."""

    slug: str  # 'agent' | 'cv' | 'llm' | 'nlp' | 'rag'
    raw_topic: str  # 'Agent' | 'CV' | 'LLM' | 'NLP' | 'RAG' (db value)


_SLUG_DROP_CHARS = re.compile(r"[/\\&\"'<>?#%]+")
_SLUG_WS = re.compile(r"\s+")

# Stable mapping for the 5 known topics — avoids fragile `.lower()` per emission.
_SLUG_TOPIC_MAP = {"Agent": "agent", "CV": "cv", "LLM": "llm", "NLP": "nlp", "RAG": "rag"}


def slugify_entity_name(name: str) -> str:
    """ENTITY-02: lowercase + URL-safe slug, Unicode preserved.

    Rules:
        - lowercase
        - strip leading/trailing whitespace
        - drop URL-unsafe ASCII chars (slash, backslash, ampersand, quote, lt/gt, ?, #, %)
        - collapse internal whitespace to single '-'
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
    """TOPIC-02 cohort filter — KOL via classifications, RSS via rss_articles.topics.

    Returns ArticleRecords UNION-ed across `articles` + `rss_articles` where:
      KOL: classifications.topic = ? AND classifications.depth_score >= ?
           AND (a.layer1_verdict = 'candidate' OR a.layer2_verdict = 'ok')
      RSS: rss_articles.topics LIKE '%<topic>%' AND rss_articles.depth >= ?
           AND (r.layer1_verdict = 'candidate' OR r.layer2_verdict = 'ok')

    Schema reality (Hermes prod 2026-05-14): `classifications` is KOL-only
    (no `source` column). RSS topic membership is stored on
    `rss_articles.topics` (JSON-encoded list) and `rss_articles.depth`.

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
        if QUALITY_FILTER_ENABLED:
            _verify_quality_columns(conn)
        results: list[ArticleRecord] = []
        # KOL articles — JOIN classifications without source predicate
        # (classifications is KOL-only per prod schema).
        sql_kol = (
            "SELECT a.id, a.title, a.url, a.body, a.content_hash, a.lang, a.update_time "
            "FROM articles a "
            "JOIN classifications c ON c.article_id = a.id "
            "WHERE c.topic = ? AND c.depth_score >= ? "
            "AND (a.layer1_verdict = 'candidate' OR a.layer2_verdict = 'ok')"
        )
        if QUALITY_FILTER_ENABLED:
            sql_kol += " AND " + _DATA07_KOL_FRAGMENT
        for row in conn.execute(sql_kol, (topic, depth_min)):
            results.append(_row_to_record_kol(row))
        # RSS articles — match topic via rss_articles.topics LIKE pattern.
        # rss_articles.topics is a JSON-stringified list (e.g. '["Agent","NLP"]')
        # so a LIKE '%<topic>%' check matches when the topic name appears
        # anywhere in the JSON. Substring false-positives are minimal — topic
        # values are domain-disjoint short strings (Agent / CV / LLM / NLP / RAG)
        # that won't collide with body URLs because `topics` is a structured
        # column populated only by the classify cron.
        sql_rss = (
            "SELECT r.id, r.title, r.url, r.body, r.content_hash, r.lang, "
            "r.published_at, r.fetched_at "
            "FROM rss_articles r "
            "WHERE r.topics LIKE '%' || ? || '%' AND r.depth >= ? "
            "AND (r.layer1_verdict = 'candidate' OR r.layer2_verdict = 'ok')"
        )
        if QUALITY_FILTER_ENABLED:
            sql_rss += " AND " + _DATA07_RSS_FRAGMENT
        for row in conn.execute(sql_rss, (topic, depth_min)):
            results.append(_row_to_record_rss(row))
        # Merge sort by update_time DESC (lexicographic — kb-1-10 normalizes
        # epoch INTs to ISO-8601 strings via _normalize_update_time, so KOL +
        # RSS rows compare correctly).
        results.sort(key=lambda r: r.update_time, reverse=True)
        return results
    finally:
        if own_conn:
            conn.close()


def entity_articles_query(
    entity_name: str,
    min_freq: int = 5,
    conn: Optional[sqlite3.Connection] = None,
) -> list[ArticleRecord]:
    """ENTITY-01 + ENTITY-03: list articles mentioning entity_name.

    If COUNT(DISTINCT article_id) for entity_name < min_freq, returns []
    — entity below threshold, do not surface a list page.
    Otherwise returns matching `articles` rows. Sorted by update_time DESC.

    Schema reality (Hermes prod 2026-05-14): `extracted_entities` is KOL-only
    (no `source` column, `entity_name` column not `name`).
    `rss_extracted_entities` does not exist — RSS articles have no entity
    extraction in v1.0. The RSS branch is therefore dropped from this query.
    """
    own_conn = conn is None
    if own_conn:
        conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        if QUALITY_FILTER_ENABLED:
            _verify_quality_columns(conn)
        (freq,) = conn.execute(
            "SELECT COUNT(DISTINCT article_id) "
            "FROM extracted_entities WHERE entity_name = ?",
            (entity_name,),
        ).fetchone()
        if freq < min_freq:
            return []
        results: list[ArticleRecord] = []
        # KOL articles only — extracted_entities is KOL-only per prod schema.
        sql_kol = (
            "SELECT a.id, a.title, a.url, a.body, a.content_hash, a.lang, a.update_time "
            "FROM articles a JOIN extracted_entities e "
            "ON e.article_id = a.id "
            "WHERE e.entity_name = ?"
        )
        if QUALITY_FILTER_ENABLED:
            sql_kol += " AND " + _DATA07_KOL_FRAGMENT
        for row in conn.execute(sql_kol, (entity_name,)):
            results.append(_row_to_record_kol(row))
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

    Schema reality (Hermes prod 2026-05-14): `extracted_entities` is KOL-only
    (no `source` column, `entity_name` column not `name`).
    `rss_extracted_entities` does not exist — RSS articles have no entity
    extraction. RSS callers short-circuit at function entry (return []) so
    KOL/RSS id-range overlap (KOL ids 1-973 vs RSS ids 1-14209) cannot leak
    KOL entities onto an RSS detail page.
    """
    # RSS short-circuit — RSS articles have no entity extraction in v1.0.
    # Done BEFORE acquiring conn / running schema guard so the path is cheap.
    if source == "rss":
        return []
    own_conn = conn is None
    if own_conn:
        conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        if QUALITY_FILTER_ENABLED:
            _verify_quality_columns(conn)
            # DATA-07: source article must itself satisfy the filter; if it
            # doesn't, the article wouldn't appear on a list page anyway —
            # related-link rows on its detail page should be empty.
            row = conn.execute(
                f"SELECT 1 FROM articles WHERE id = ? AND {_DATA07_BARE} LIMIT 1",
                (article_id,),
            ).fetchone()
            if row is None:
                return []
        sql = (
            "SELECT e.entity_name, "
            "(SELECT COUNT(DISTINCT article_id) "
            " FROM extracted_entities WHERE entity_name = e.entity_name) AS global_freq "
            "FROM extracted_entities e "
            "WHERE e.article_id = ? "
            "GROUP BY e.entity_name "
            "HAVING global_freq >= ? "
            "ORDER BY global_freq DESC, e.entity_name ASC "
            "LIMIT ?"
        )
        return [
            EntityCount(
                name=row["entity_name"],
                slug=slugify_entity_name(row["entity_name"]),
                article_count=row["global_freq"],
            )
            for row in conn.execute(sql, (article_id, min_global_freq, limit))
        ]
    finally:
        if own_conn:
            conn.close()


def related_topics_for_article(
    article_id: int,
    source: str,
    depth_min: int = 2,
    limit: int = 3,
    conn: Optional[sqlite3.Connection] = None,
) -> list[TopicSummary]:
    """LINK-02: 1-3 topics for this article — KOL via classifications, RSS via rss_articles.topics.

    Sorted by depth_score DESC then topic alpha. Returns TopicSummary with the
    slug already lowercased (matching kb/output/topics/{slug}.html convention).

    Schema reality (Hermes prod 2026-05-14): `classifications` is KOL-only.
    RSS topic membership is on rss_articles.topics (JSON-encoded list) and
    rss_articles.depth.
    """
    own_conn = conn is None
    if own_conn:
        conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        if QUALITY_FILTER_ENABLED:
            _verify_quality_columns(conn)
            # DATA-07: source article must itself satisfy the filter or we
            # return [] — same rationale as related_entities_for_article.
            table = "articles" if source == "wechat" else "rss_articles"
            row = conn.execute(
                f"SELECT 1 FROM {table} WHERE id = ? AND {_DATA07_BARE} LIMIT 1",
                (article_id,),
            ).fetchone()
            if row is None:
                return []
        if source == "rss":
            # RSS path: parse rss_articles.topics JSON list (alpha-sorted by
            # convention) + rss_articles.depth. Match the depth gate at the
            # row level (rss_articles.depth applies to all topics on the row;
            # there's no per-topic depth on RSS).
            row = conn.execute(
                "SELECT topics, depth FROM rss_articles WHERE id = ? "
                "AND topics IS NOT NULL AND topics != '' AND topics != '[]' "
                "AND depth >= ?",
                (article_id, depth_min),
            ).fetchone()
            if row is None:
                return []
            # Parse JSON list (or LIKE-extract for malformed). Topics are
            # always one of the 5 fixed values; tolerate ordering / extra spaces.
            import json as _json
            try:
                topics_list = _json.loads(row["topics"])
                if not isinstance(topics_list, list):
                    topics_list = []
            except (ValueError, TypeError):
                topics_list = []
            # Filter to known topics only (defensive — prod data quality varies).
            valid_topics = [t for t in topics_list if t in _SLUG_TOPIC_MAP]
            valid_topics.sort()  # alpha-sort matches LIMIT semantics on KOL path
            return [
                TopicSummary(slug=_SLUG_TOPIC_MAP[t], raw_topic=t)
                for t in valid_topics[:limit]
            ]
        # KOL path: classifications JOIN without source predicate
        # (classifications is KOL-only per prod schema).
        return [
            TopicSummary(
                slug=_SLUG_TOPIC_MAP.get(row["topic"], row["topic"].lower()),
                raw_topic=row["topic"],
            )
            for row in conn.execute(
                "SELECT topic, depth_score FROM classifications "
                "WHERE article_id = ? AND depth_score >= ? "
                "ORDER BY depth_score DESC, topic ASC LIMIT ?",
                (article_id, depth_min, limit),
            )
        ]
    finally:
        if own_conn:
            conn.close()


def articles_by_hashes(
    hashes: list[str],
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict]:
    """kb-v2.1-4: Resolve a batch of url-hashes (md5[:10]) to ``[{hash, title, lang}]``.

    Filters through DATA-07 (same contract as list_articles): rows that fail
    the quality filter are silently dropped. Order of return matches input
    order; missing hashes are skipped.

    KOL: matches against ``articles.content_hash`` directly (10-char already).
    RSS: matches against ``substr(rss_articles.content_hash, 1, 10)``
    (full md5 truncated, mirrors get_article_by_hash semantics).
    """
    if not hashes:
        return []
    own_conn = conn is None
    if own_conn:
        conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        if QUALITY_FILTER_ENABLED:
            _verify_quality_columns(conn)
        placeholders = ",".join("?" for _ in hashes)
        kol_filter = (
            (" AND " + _DATA07_KOL_FRAGMENT) if QUALITY_FILTER_ENABLED else ""
        )
        rss_filter = (
            (" AND " + _DATA07_RSS_FRAGMENT) if QUALITY_FILTER_ENABLED else ""
        )
        kol_sql = (
            f"SELECT a.content_hash AS hash, a.title, a.lang "
            f"FROM articles a "
            f"WHERE a.content_hash IN ({placeholders})"
            f"{kol_filter}"
        )
        rss_sql = (
            f"SELECT substr(r.content_hash, 1, 10) AS hash, r.title, r.lang "
            f"FROM rss_articles r "
            f"WHERE substr(r.content_hash, 1, 10) IN ({placeholders})"
            f"{rss_filter}"
        )
        found: dict[str, dict] = {}
        for row in conn.execute(kol_sql, hashes):
            found[row["hash"]] = {
                "hash": row["hash"],
                "title": row["title"] or "",
                "lang": row["lang"],
            }
        for row in conn.execute(rss_sql, hashes):
            # KOL takes precedence on accidental collision (vanishingly unlikely).
            found.setdefault(row["hash"], {
                "hash": row["hash"],
                "title": row["title"] or "",
                "lang": row["lang"],
            })
        # Preserve input order, skip misses.
        return [found[h] for h in hashes if h in found]
    finally:
        if own_conn:
            conn.close()


def entities_for_articles(
    article_hashes: list[str],
    limit: int = 8,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict]:
    """kb-v2.1-4: Top-N entities mentioned across the given KOL article hashes.

    Returns ``[{name, article_count}]`` sorted by article_count DESC then
    entity_name ASC. RSS hashes are silently ignored (extracted_entities is
    KOL-only per Hermes prod schema; see related_entities_for_article docs).

    DATA-07 filter applies to the source articles via _DATA07_KOL_FRAGMENT.
    """
    if not article_hashes:
        return []
    own_conn = conn is None
    if own_conn:
        conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        if QUALITY_FILTER_ENABLED:
            _verify_quality_columns(conn)
        placeholders = ",".join("?" for _ in article_hashes)
        kol_filter = (
            (" AND " + _DATA07_KOL_FRAGMENT) if QUALITY_FILTER_ENABLED else ""
        )
        sql = f"""
            SELECT e.entity_name AS name,
                   COUNT(DISTINCT e.article_id) AS article_count
            FROM extracted_entities e
            JOIN articles a ON a.id = e.article_id
            WHERE a.content_hash IN ({placeholders}){kol_filter}
            GROUP BY e.entity_name
            ORDER BY article_count DESC, e.entity_name ASC
            LIMIT ?
        """
        return [
            {"name": row["name"], "article_count": row["article_count"]}
            for row in conn.execute(sql, [*article_hashes, limit])
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
    """TOPIC-05: top entities by article-frequency within the KOL topic cohort.

    Cohort gate: classifications.depth_score >= depth_min AND
    (layer1_verdict = 'candidate' OR layer2_verdict = 'ok').
    Filters out entities whose GLOBAL frequency < min_global_freq.

    Schema reality (Hermes prod 2026-05-14): `classifications` and
    `extracted_entities` are both KOL-only (no `source` column;
    rss_extracted_entities does not exist). The cohort is therefore
    fundamentally KOL-only — the RSS branch is dropped.
    """
    own_conn = conn is None
    if own_conn:
        conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        if QUALITY_FILTER_ENABLED:
            _verify_quality_columns(conn)
        # DATA-07 cohort gate: append _DATA07_KOL_FRAGMENT to the topic-articles
        # CTE. Built inline as f-string interp of constants (no user input — safe).
        kol_data07 = (" AND " + _DATA07_KOL_FRAGMENT) if QUALITY_FILTER_ENABLED else ""
        sql = f"""
            WITH topic_articles AS (
                SELECT a.id AS article_id
                FROM articles a
                JOIN classifications c ON c.article_id = a.id
                WHERE c.topic = ? AND c.depth_score >= ?
                  AND (a.layer1_verdict = 'candidate' OR a.layer2_verdict = 'ok')
                  {kol_data07}
            )
            SELECT e.entity_name,
                   COUNT(DISTINCT e.article_id) AS topic_freq,
                   (SELECT COUNT(DISTINCT article_id)
                      FROM extracted_entities WHERE entity_name = e.entity_name) AS global_freq
            FROM extracted_entities e
            JOIN topic_articles t
              ON t.article_id = e.article_id
            GROUP BY e.entity_name
            HAVING global_freq >= ?
            ORDER BY topic_freq DESC, e.entity_name ASC
            LIMIT ?
        """
        return [
            EntityCount(
                name=row["entity_name"],
                slug=slugify_entity_name(row["entity_name"]),
                article_count=row["topic_freq"],
            )
            for row in conn.execute(
                sql, (topic, depth_min, min_global_freq, limit)
            )
        ]
    finally:
        if own_conn:
            conn.close()
