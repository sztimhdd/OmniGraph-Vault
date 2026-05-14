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
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
        results: list[ArticleRecord] = []
        if source != "rss":
            sql = "SELECT id, title, url, body, content_hash, lang, update_time FROM articles"
            params: list = []
            if lang is not None:
                sql += " WHERE lang = ?"
                params.append(lang)
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


def get_article_body(rec: ArticleRecord) -> tuple[str, BodySource]:
    """D-14 fallback chain for article body markdown.

    Resolution order:
        1. {KB_IMAGES_DIR}/{hash}/final_content.enriched.md  -> 'vision_enriched'
        2. {KB_IMAGES_DIR}/{hash}/final_content.md            -> 'vision_enriched'
        3. rec.body (from DB row)                              -> 'raw_markdown'

    Applies EXPORT-05 rewrite at read time:
        'http://localhost:8765/' -> '/static/img/'

    Returns:
        (body_markdown, body_source) tuple.
    """
    url_hash = resolve_url_hash(rec)
    images_dir = Path(config.KB_IMAGES_DIR)
    for fname in ("final_content.enriched.md", "final_content.md"):
        p = images_dir / url_hash / fname
        if p.exists():
            md = p.read_text(encoding="utf-8")
            md = _IMAGE_SERVER_REWRITE.sub("/static/img/", md)
            return md, "vision_enriched"
    body = rec.body or ""
    body = _IMAGE_SERVER_REWRITE.sub("/static/img/", body)
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
    """TOPIC-02 cohort filter.

    Returns ArticleRecords UNION-ed across `articles` + `rss_articles` where:
        classifications.depth_score >= depth_min
        AND (a.layer1_verdict = 'candidate' OR a.layer2_verdict = 'ok')
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
        # KOL articles
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

    If COUNT(DISTINCT (article_id, source)) for entity_name < min_freq, returns
    [] — entity below threshold, do not surface a list page.
    Otherwise UNIONs `articles` + `rss_articles` whose id appears in
    `extracted_entities` for this name. Sorted by update_time DESC.
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
