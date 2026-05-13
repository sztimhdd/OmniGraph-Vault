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
from dataclasses import dataclass
from typing import Literal, Optional

from kb import config  # noqa: F401  (kept for downstream tasks; pure resolve_url_hash does NOT use it)

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
