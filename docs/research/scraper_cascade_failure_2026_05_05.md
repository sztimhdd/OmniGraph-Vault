# Scraper Cascade Failure Investigation — 2026-05-05

## TL;DR

- 121 failures are NOT "4-layer scraper all None" — **Apify succeeded on every single one**
- Root cause: SCR-06 hotfix surfaces Apify's `markdown` key correctly in `_scrape_wechat()`, but `content_html` stays empty. Consumer in `batch_ingest_from_spider.py` rejects empty `content_html`.
- **This is an SCR-06 completeness bug** — the cascade function was fixed, its consumer wasn't.
- The 5 user-tested URLs (art_ids 695, 507, 600, 664, 412) are not in the overnight-graded log — they never entered the batch.

## Evidence

### Log statistics (overnight-graded-20260505-0057.log)

| Metric | Count |
|--------|-------|
| Total articles in batch | 226 |
| Apify SUCCEEDED | ~121 (exact match to failures) |
| "all 4 wechat layers returned None" | **0** |
| checkpoint-skip (already ingested) | 3 |
| graded-skip (topic doesn't match) | 98 |
| classify failed (D-10.04) | **121** |

### Failure pattern (every one of the 121)

```
1. [apify] FETCH → SCRAPE → COMPLETE → Status: True  (11-16s)
2. [apify] Status: SUCCEEDED
3. "scrape-on-demand failed for <URL> -- skipping classify"
4. "classify failed — skipping ingest (D-10.04 no fail-open)"
```

Apify actor completes successfully with `exit_code: 0`. The content was fetched and scraped. But the downstream code rejects it.

### Code-path analysis

**lib/scraper.py lines 183-208** — the SCR-06 hotfix:

```python
content_html = result.get("content_html") or ""       # line 183 → "" for Apify
scraped_markdown = result.get("markdown") or ""       # line 188 → actual content
if scraped_markdown and not content_html:              # line 191 → True
    markdown = scraped_markdown                         # ✅ markdown set correctly
    imgs = result.get("images") or []
return ScrapeResult(
    markdown=markdown,                                  # ✅ has content
    content_html=content_html,                          # ❌ "" (empty!)
)
```

The markdown is correctly populated, but `content_html` remains empty string because Apify returns `{"markdown": "..."}` — no `content_html` key.

**batch_ingest_from_spider.py line 948** — the consumer:

```python
scraped = await scrape_url(url, site_hint="wechat")
if not scraped or not scraped.content_html:           # ← "" is falsy → True → FAIL
    logger.warning("scrape-on-demand failed for %s -- skipping classify", url[:80])
    return None
```

`scraped.content_html` is `""` (falsy). The check fails despite `scraped.markdown` containing valid content.

## Root cause: SCR-06 partial fix

The SCR-06 hotfix (2026-05-04) correctly identified that Apify returns a `markdown` key instead of `content_html`. It added `markdown` extraction in the cascade function. But the `content_html` field of `ScrapeResult` stays empty, and the consumer at `batch_ingest_from_spider.py:948` only checks `content_html`.

**Impact:** 121/226 articles rejected (53.5%). All Apify responses discarded.

## Per-URL probe results

Not performed—the 5 user-tested URLs don't appear in the overnight-graded log. They were either pre-filtered by the grader or belong to a different batch run.

| art_id | KOL | In overnight log? |
|--------|-----|-------------------|
| 695 | 苍何 | ❌ Not found |
| 507 | 字节笔记本 | ❌ Not found |
| 600 | 阿里通义实验室 | ❌ Not found |
| 664 | 孟健AI编程 | ❌ Not found |
| 412 | CVer | ❌ Not found |

## Hypothesis ranking

| H | Description | Evidence | Verdict |
|---|-------------|----------|---------|
| SCR-06 consumer gap | Apify `markdown` extracted but `content_html=""` kills consumer | 121 Apify SUCCEEDED → 121 classify failed. Code at scraper.py:207 returns empty content_html. Consumer at batch_ingest:948 rejects empty. | **CONFIRMED** |
| Apify token expired | Apify runs would fail with auth error | All 121 Apify runs show SUCCEEDED, exit_code 0 | **REFUTED** |
| CDP/MCP unreachable | CDP layer would show connection errors | CDP/MCP never reached—cascade short-circuits at Apify (SCR-06: "no need to cascade to CDP/MCP/UA") | **REFUTED** |
| WeChat rate-limit | Would show fetch errors or HTTP 429 | Apify FETCH → Status: True for all 121 | **REFUTED** |
| URL chksm/sn parameters break parsing | Would affect specific URLs, not 121 uniformly | Pattern is uniform across all 121 | **REFUTED** |

## Additional observations

### The "all 4 layers None" message never fired

The log has 0 occurrences of `"scraper: all 4 wechat layers returned None"`. The user's characterization was based on a misinterpretation: the `scrape-on-demand failed` message looks similar but is the consumer-side rejection, not the cascade-side exhaustion.

### graded-skip reasons are working correctly

98 articles were correctly classified as off-topic. Examples:
- `art_id=392: 'Article about video generation, not openclaw/hermes/agent/harness'`
- `art_id=408: 'Article about DeepSeek multimodal tech, not related to specified terms'`

### checkpoint-skip is working correctly

3 articles skipped because they were already ingested in prior runs.

## Recommendation

**One-line fix** — at `lib/scraper.py` line 207, when Apify markdown path is taken, propagate the markdown to `content_html`:

```python
# Line 191-193, add:
if scraped_markdown and not content_html:
    markdown = scraped_markdown
    imgs = result.get("images") or []
    content_html = f"<html><body>{scraped_markdown}</body></html>"  # ← ADD THIS
```

Or alternatively, fix the consumer at `batch_ingest_from_spider.py` line 948 to also check `scraped.markdown`:

```python
if not scraped or (not scraped.content_html and not scraped.markdown):
```

**Recommendation: leaf fix at consumer** (batch_ingest_from_spider.py:948) — less invasive, doesn't change ScrapeResult semantics, and the markdown is already what `process_content` would produce from HTML anyway.

## Files affected (if fix applied)

- `batch_ingest_from_spider.py` line 948: add `scraped.markdown` fallback check
- `lib/scraper.py`: no change needed (markdown already correctly populated)

## Verification

After fix: re-run the 121 failed articles. Expected: Apify content used, classify proceeds normally on the markdown body.
