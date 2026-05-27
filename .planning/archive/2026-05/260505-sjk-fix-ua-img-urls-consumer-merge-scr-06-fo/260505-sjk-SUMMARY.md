---
quick_id: 260505-sjk
type: quick
phase: quick
plan: 260505-sjk
subsystem: scraper-consumer
tags: [scr-06-followup, ua, image-fidelity, surgical-fix]
wave: 1
depends_on: []
requirements: [SCR-06-followup]
status: complete
commit: af01315
commit_message: "fix(scr-06-followup): merge UA img_urls with content_html images (silent loss fix per audit ece03ae)"
duration_min: ~25
completed: 2026-05-05
---

# Quick 260505-sjk: SCR-06-followup — UA `img_urls` consumer merge fix

## One-liner

Closes 🔴 silent data loss in `lib/scraper.py:_scrape_wechat` consumer — UA-fallback articles now retain pre-HTML `img_urls` (images outside `#js_content`) by mirroring `ingest_article:978` plain-concat merge.

## Audit cross-reference

- **Audit:** `ece03ae` (`docs/research/scraper_layer_shape_audit_2026_05_05.md`)
- **Fix closes:** Mismatch #1 🔴 (UA `img_urls` silently dropped by new consumer)
- **NOT in scope:** Mismatch #2 🟡 (Apify markdown image regex absent in new consumer) — DEFERRED per audit recommendation
- **NOT in scope:** Mismatch #3 (CDP `body` fallback noise) — DEFERRED, observability only per audit recommendation

## Diff

| File | Lines added | Lines removed | Notes |
| ---- | ----------- | ------------- | ----- |
| `lib/scraper.py` | 6 | 1 | Patch in `_scrape_wechat` `else:` branch (~line 195) |
| `tests/unit/test_scraper_ua_img_merge.py` | 192 | 0 | New file, 4 mock-only tests |

`git diff HEAD~1 -- ingest_wechat.py` → 0 lines (no layer-function diff, consumer-side only).

## Patch (lib/scraper.py:195-200)

```python
if scraped_markdown and not content_html:
    markdown = scraped_markdown
    imgs = result.get("images") or []
else:
    markdown, _process_imgs = ingest_wechat.process_content(content_html)
    # Mirror ingest_article:978 — merge UA's full-page data-src img_urls
    # (images outside #js_content) with process_content output (images
    # inside content_html). Plain concat, no dedup, preserves order.
    # Audit ece03ae Mismatch #1 — fixes silent data loss for UA fallback.
    imgs = list(result.get("img_urls") or []) + _process_imgs
```

Three structural points (mirrors `ingest_article.py:978` exactly):
- Order: `img_urls` FIRST, then `_process_imgs` — exact mirror of legacy
- Plain `+` concat — no dedup, no set semantics
- Defensive read: `list(result.get("img_urls") or [])` handles `None` AND avoids mutating caller's list

## Test result

| Test | Pre-fix | Post-fix |
| ---- | ------- | -------- |
| `test_ua_merges_img_urls_with_content_html_images` | FAIL (`["c"]` ≠ `["a","b","c"]`) | PASS |
| `test_ua_empty_img_urls_yields_only_process_content_images` | PASS (invariant) | PASS |
| `test_ua_img_urls_only_no_html_imgs` | FAIL (`[]` ≠ `["x"]`) | PASS |
| `test_apify_short_circuit_unchanged_no_img_urls_key` | PASS (regression sanity) | PASS |

**4/4 GREEN** post-fix. The "PASS pre-fix" on test #2 is mathematically invariant — `[] + ["x","y"] == ["x","y"]` regardless of bug — but the assertion is still useful as a guard against future regressions that would invert the merge order.

## Regression gate

```
pytest tests/unit/test_scraper_ua_img_merge.py tests/unit/test_scraper.py -v
9 passed, 9 warnings in 7.96s
```

5 pre-existing `test_scraper.py` tests (SCR-01..05 + cascade order) all GREEN. No new regressions.

## Commit

- **Hash:** `af01315`
- **Message:** `fix(scr-06-followup): merge UA img_urls with content_html images (silent loss fix per audit ece03ae)`
- **Pushed:** `origin/main` (`e925237..af01315`)

## Audit Mismatch status

| # | Layer | Severity | Status |
| - | ----- | -------- | ------ |
| 1 | UA `img_urls` vs consumer `images` | 🔴 | **CLOSED** (this commit) |
| 2 | Apify markdown image regex absent in new consumer | 🟡 | UNCHANGED — DEFER per audit |
| 3 | CDP `body` fallback noise (observability) | 🟡 | UNCHANGED — DEFER per audit |

## Deviations from plan

None. Plan executed exactly as written; one minor observation:

- Plan Task 1 "done" criterion expected 3 RED tests + 1 PASS. Actual RED state was 2 RED + 2 PASS, because `test_ua_empty_img_urls_yields_only_process_content_images` is mathematically invariant under the bug (empty list `+` X equals X regardless of merge order). The post-fix GREEN gate (4/4) is still the correct success criterion — kept the test as a future-regression guard against accidental order swap.

## Self-Check: PASSED

- `lib/scraper.py:195-200` contains `result.get("img_urls"` ✓
- `tests/unit/test_scraper_ua_img_merge.py` exists with 4 test functions ✓
- `git log af01315 --pretty=%s` matches exact required string ✓
- `git push origin main` succeeded (`e925237..af01315`) ✓
- 4/4 new tests GREEN, 5/5 pre-existing scraper tests GREEN ✓
