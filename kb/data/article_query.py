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
import sqlite3
from dataclasses import dataclass
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


def _row_to_record_kol(row) -> ArticleRecord:
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


def _row_to_record_rss(row) -> ArticleRecord:
    # Normalize RSS update_time: prefer published_at, else fetched_at.
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
