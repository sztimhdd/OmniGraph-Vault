# ir-4 W2 — `_needs_scrape` helper + `_persist_scraped_body` source dispatch (LF-4.4 dispatch)

**Commit:** `df495c8`
**Files:** 3 changed, +436 / -19

## Goal

Replace W1's KOL-only scrape gate with proper dual-source dispatch:
- KOL: scrape only when body missing (legacy semantic preserved).
- RSS: scrape when body missing OR shorter than `RSS_SCRAPE_THRESHOLD` (100
  chars) — RSS feed `<description>` excerpts are typically 50-80 chars,
  too short for Layer 2 / ainsert.
- `_persist_scraped_body` writes to the correct source-table.
- `scrape_url` auto-routes by URL (no hardcoded site_hint).

## Deliverables

### `_needs_scrape(source, body)` module-level helper

`batch_ingest_from_spider.py` — pure-Python decision function:

```python
RSS_SCRAPE_THRESHOLD = 100

def _needs_scrape(source: str, body: str | None) -> bool:
    if not body:
        return True
    if source == "rss" and len(body) <= RSS_SCRAPE_THRESHOLD:
        return True
    return False
```

KOL: any non-empty body skips scrape (pre-ir-4 semantic preserved).
RSS: short bodies (≤100 chars) trigger scrape via the generic cascade.

### `_persist_scraped_body` source dispatch

Signature change: `(conn, article_id, scrape) → (conn, article_id, source, scrape)`.

Source-table dispatch via `_BODY_TABLE_FOR = {"wechat": "articles", "rss": "rss_articles"}`.

Unknown source → soft-skip with WARNING log (refused write rather than
defaulting to `articles` and silently corrupting a KOL row when source was
mis-set).

500-char idempotency guard preserved on both tables (`UPDATE {table} SET
body = ? WHERE id = ? AND (body IS NULL OR length(body) < 500)`).

Exception swallow preserved (DB lock / schema mismatch logs WARNING, never
raises into main loop).

### ingest_from_db scrape call cleanup

Removed W1's `if not body and source == "wechat":` gate; replaced with
`if _needs_scrape(source, body):`.

Removed `site_hint='wechat'` from the `scrape_url(url)` call. ir-4
dual-source needs URL-based auto-route via `_route(url)` inside
`scrape_url`: WeChat URLs (mp.weixin.qq.com) hit `_scrape_wechat`;
non-WeChat URLs hit `_scrape_generic`.

Updated `_persist_scraped_body(conn, art_id, source, scraped)` to pass
source through.

### Tests

- `tests/unit/test_dual_source_dispatch.py` (new): 16 tests covering:
    - `_needs_scrape` (KOL no-body / KOL any-body / RSS no-body / RSS
      short-body / RSS long-body / threshold-value pin)
    - `_persist_scraped_body` dispatch (KOL writes articles only, RSS
      writes rss_articles only, id collision isolation, unknown source
      soft-skip with WARNING, RSS 500-char guard, RSS exception swallow)
    - Structural: scrape_url call has no site_hint, ingest_from_db uses
      `_needs_scrape` helper, `_BODY_TABLE_FOR` complete, signature pin
- `tests/unit/test_persist_body_pre_classify.py`: 3 existing call sites
  updated from `(conn, 1, scrape)` → `(conn, 1, "wechat", scrape)`.

## Local validation gate — all PASS

| Gate | Result | Evidence |
|---|---|---|
| G1 W2+W1 pytest | 71/72 → 72/72 PASS after fixing the over-eager site_hint regex (was matching the W2 explanatory comment that mentions the W1 hardcoded value) | `.scratch/ir-4-w2-pytest.log` |
| G2 harness regression | EXIT=0, total inputs=1749 (matches W1 G2 count) | `.scratch/ir-4-w2-kol-dryrun.log` |

## Out-of-scope deferred

`batch_ingest_from_spider.py:1048` — `_classify_full_body` also calls
`scrape_url(url, site_hint='wechat')` but that path is the legacy KOL
graded-classify (used only by `OMNIGRAPH_GRADED_CLASSIFY=1`, default OFF)
and writes only to `articles.body`. ir-4 scope is the `--from-db` path;
legacy graded-classify keeps its pre-ir-4 KOL-only behavior.
