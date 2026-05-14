"""API-02 + API-03: GET /api/articles + GET /api/article/{hash}.

Thin FastAPI router — all DB logic lives in `kb.data.article_query`, which
already applies the DATA-07 content-quality filter (per kb-3-02). This
router parses query params, calls the data layer, formats the response,
and handles 404 / 422.

See `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md` (kb-3-01)
for the response shape contract.

DATA-07 cross-phase impact (per kb-3-CONTENT-QUALITY-DECISIONS.md):
    - GET /api/articles    : DATA-07 APPLIED (default on; via list_articles)
    - GET /api/article/{h} : DATA-07 CARVE-OUT (always unfiltered; direct
                              hash access by bookmark/citation must resolve
                              regardless of layer1/layer2 verdict)

Skill discipline (kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):

    Skill(skill="python-patterns", args="Idiomatic FastAPI APIRouter pattern: kb/api_routers/__init__.py is empty package marker; kb/api_routers/articles.py defines `router = APIRouter(prefix='/api', tags=['articles'])` then registers @router.get handlers. Use Annotated[type, Query(...)] for declarative param validation (ge/le/min_length/max_length). The endpoint handler is THIN: parses params -> calls list_articles(...) -> maps ArticleRecord -> dict via list comprehension -> returns. NO direct SQL in router; NO try/except for DB errors (let FastAPI's default 500 handler take over for DB-down case — synthesize is the only never-500 path per QA-05). NO new env vars (CONFIG-02 transitive). PEP 8 + type hints throughout.")

    Skill(skill="writing-tests", args="TestClient integration tests for /api/articles + /api/article/{hash}. Tests cover: list shape, pagination math, source/lang/q filters, 422 validation, DATA-07 inheritance (negative fixture rows absent from list), hash field correctness, p50 latency; detail full shape, 404 miss, body_html rendered, body_source enum, DATA-07 carve-out (negative rows still addressable by hash), images list, latency. Real SQLite via fixture_db — NO mocks for the DB layer.")
"""
from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Optional

import markdown as md_lib
from fastapi import APIRouter, HTTPException, Query

from kb.data import article_query

router = APIRouter(prefix="/api", tags=["articles"])


# ---- Helpers ----------------------------------------------------------------


def _record_to_list_item(rec: article_query.ArticleRecord) -> dict[str, Any]:
    """Map ArticleRecord -> /api/articles list item shape (kb-3-API-CONTRACT §3.3)."""
    return {
        "hash": article_query.resolve_url_hash(rec),
        "title": rec.title,
        "url": rec.url,
        "lang": rec.lang,
        "source": rec.source,
        "update_time": rec.update_time,
        # `snippet` populated by /api/search; null on the plain list per contract §3.3.
        "snippet": None,
    }


# Image-extraction regex — match both markdown `![](url)` and html `<img src="url">`.
_MD_IMG_PATTERN = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_HTML_IMG_PATTERN = re.compile(r'<img[^>]*src="([^"]+)"', re.IGNORECASE)


def _extract_image_urls(body_md: str) -> list[str]:
    """Extract image URLs from markdown body (md and html img syntax, deduped)."""
    urls: list[str] = []
    urls.extend(_MD_IMG_PATTERN.findall(body_md))
    urls.extend(_HTML_IMG_PATTERN.findall(body_md))
    seen: set[str] = set()
    result: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


# ---- Endpoints --------------------------------------------------------------


@router.get("/articles")
async def list_articles_endpoint(
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    source: Annotated[Optional[Literal["wechat", "rss"]], Query()] = None,
    lang: Annotated[Optional[Literal["zh-CN", "en", "unknown"]], Query()] = None,
    q: Annotated[Optional[str], Query(min_length=1, max_length=200)] = None,
) -> dict[str, Any]:
    """API-02: paginated article list. DATA-07 filter applied via list_articles().

    Query params:
        page: 1-indexed page (ge=1)
        limit: page size (1..100)
        source: 'wechat' | 'rss' | omitted (both)
        lang: 'zh-CN' | 'en' | 'unknown' | omitted (all)
        q: case-insensitive LIKE substring on title (1..200 chars)

    Returns: ``{items, page, limit, total, has_more}`` per kb-3-API-CONTRACT §3.3.

    DATA-07 inheritance: this endpoint surfaces only rows that pass the
    quality filter (default on; ``KB_CONTENT_QUALITY_FILTER=off`` to bypass).
    See kb-3-CONTENT-QUALITY-DECISIONS.md.
    """
    offset = (page - 1) * limit
    # Cheapest correct path on a ~160-row v2.0 corpus: ask data layer for the
    # full filtered set, apply optional q-filter in Python, then paginate.
    # If the corpus grows past ~10K rows, push q-filter into list_articles
    # via SQL LIKE.
    all_records = article_query.list_articles(
        lang=lang, source=source, limit=10000, offset=0
    )
    if q:
        ql = q.lower()
        all_records = [r for r in all_records if ql in (r.title or "").lower()]
    total = len(all_records)
    page_records = all_records[offset : offset + limit]
    items = [_record_to_list_item(r) for r in page_records]
    return {
        "items": items,
        "page": page,
        "limit": limit,
        "total": total,
        "has_more": (offset + len(page_records)) < total,
    }


@router.get("/article/{hash}")
async def get_article_endpoint(hash: str) -> dict[str, Any]:
    """API-03: single article by md5[:10] hash.

    DATA-07 carve-out: this endpoint does NOT apply the content-quality filter.
    Direct URL access (search hits, KG citations, bookmarks) must resolve to
    the rendered article regardless of layer1/layer2 verdict — see
    kb-3-CONTENT-QUALITY-DECISIONS.md "NOT affected (intentional carve-out)".

    Returns the canonical detail-page payload + D-14 body-source flag per
    kb-3-API-CONTRACT §4.3:
        ``{hash, title, body_md, body_html, lang, source, images, metadata, body_source}``
    """
    rec = article_query.get_article_by_hash(hash)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"article {hash!r} not found")
    body_md, body_source = article_query.get_article_body(rec)
    body_html = md_lib.markdown(body_md, extensions=["fenced_code", "tables"])
    return {
        "hash": article_query.resolve_url_hash(rec),
        "title": rec.title,
        "body_md": body_md,
        "body_html": body_html,
        "lang": rec.lang,
        "source": rec.source,
        "images": _extract_image_urls(body_md),
        "metadata": {
            "url": rec.url,
            "publish_time": rec.publish_time,
            "update_time": rec.update_time,
        },
        "body_source": body_source,
    }
