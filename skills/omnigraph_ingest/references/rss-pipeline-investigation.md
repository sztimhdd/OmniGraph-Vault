# RSS Pipeline Investigation (2026-05-10)

## Problem

0 RSS articles ever reached `ingestions.status='ok'`. 1569/1649 (95%) rejected at Layer 1, 45 stuck in scrape retry loop, 4 passed Layer 2 but ainsert failed.

## Root Cause: Multi-Layer Filtering, Not Single Bug

### Layer 1: 95% rejection (by design)
RSS feeds contain broad tech content. Layer 1 prompt is tuned for AI-agent engineering — correctly rejects compiler optimization, politics, SQLAlchemy tutorials, chip microarchitecture, etc. Top reject reasons:
- 编译器优化话题 (18)
- 无关主题 (17)  
- 政治评论 (7)
- SQLAlchemy数据库教程 (7)
- 芯片微架构 (6)

### Scrape: 45 URLs stuck (generic scraper not invoked)
45 articles pass Layer 1 but never get a body. These are from high-quality feeds:
simonwillison.net (8), seangoedecke.com (9), antirez.com (11), lucumr.pocoo.org (6),
geoffreylitt.com (4), etc.

**Scraper Coverage Matrix (2026-05-10): 45/45 URLs 100% scrapable with simple `requests.get` + UA header.** All return 200 with meaningful content (< 1.5s, avg ~30KB). Not blocked, not paywalled, no JS required. The problem is the scraper auto-router never invokes the generic HTTP path for these URLs.

**Fixed by b4k** (commit a3a98d3): `lib/scraper.py` UA fallback + `_extract_with_fallbacks` with `favor_recall=True`.

### Ainsert: 4 passed everything, failed at finish
4 articles from martinalderson.com (3) + michael.stapelberg.ch (1) reached Layer 2='ok' but ainsert failed. Small dev blogs with content format unsuitable for LightRAG chunking.

**Fixed by uai** (commit a66622c): source-aware dispatch with `MIN_INGEST_BODY_LEN=500` and RSS `rss_` doc_id prefix.

## Pipeline Flow (post-fix)

```
RSS feed → rss_fetch → rss_articles table
  → Layer 1 (prompt filter, source-aware → rss_articles.layer1_verdict)
  → candidates: _needs_scrape checks body length
  → b4k scraper: UA fallback → trafilatura extraction
  → persist body to rss_articles.body
  → Layer 2 (full-body score, source-aware → rss_articles.layer2_verdict)
  → ainsert (uai: source-aware dispatch, rss_ doc_id prefix, MIN_INGEST_BODY_LEN gate)
  → ingestions (source='rss')
```

## Key Code Locations

- `batch_ingest_from_spider.py:929-933` — `_needs_scrape` source-aware RSS threshold
- `batch_ingest_from_spider.py:937` — `_BODY_TABLE_FOR` maps "rss" → "rss_articles"
- `lib/article_filter.py:639-683` — `persist_layer2_verdicts` source-aware dispatch
- `lib/scraper.py:161-191` — `_extract_with_fallbacks` with `favor_recall`
- `ingest_wechat.py:62` — `MIN_INGEST_BODY_LEN = 500`
- `ingest_wechat.py:922` — `async def ingest_article(url, *, source: str = "wechat", ...)`

## Ingestions Table

RSS rows use `source='rss'` and reference `article_id` from `rss_articles` table.
WeChat rows use `source='wechat'` and reference `article_id` from `articles` table.
Both coexist in the same `ingestions` table via the UNIQUE(article_id, source) constraint.
