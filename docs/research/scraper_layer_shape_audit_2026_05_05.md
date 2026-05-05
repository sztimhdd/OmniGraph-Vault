# Scraper Layer Return-Shape Audit (2026-05-05)

## TL;DR

- **3 mismatches found across UA + Apify layers** — 1 🔴 silent data loss (UA images dropped in lib/scraper.py consumer), 2 🟡 incorrect-fallback (Apify images never extracted; UA + Apify metadata under-populated downstream).
- Worst severity 🔴: `scrape_wechat_ua` returns `img_urls`, but `lib/scraper.py:_scrape_wechat` reads `images`. Every UA-fallback article loses its pre-HTML image list.
- **Primary recommendation:** when Apify and CDP both fail today's 06:00 ADT cron, the UA fallback will silently strip images — patch the key name in a follow-up `/gsd:quick`, do NOT change layer return shapes.

## Audit Scope

- **Audited (read-only):** `lib/scraper.py` lines 60-213 (ScrapeResult + `_scrape_wechat` consumer); `ingest_wechat.py` lines 426-734 (the 4 layer functions).
- **Cross-referenced:** `ingest_wechat.ingest_article` lines 938-955 (the legacy in-process consumer — the original "correct" contract; useful as a control).
- **Method:** trace each layer's `return {...}` literals, normalize key names + value types, compare against the consumer's `result.get(...)` reads.
- **Out of scope:**
  - Apify deep dive — already fixed via SCR-06 hotfix on 2026-05-04. Apify section in this report exists for reference / cross-comparison only.
  - Generic (trafilatura) cascade in `_scrape_generic` — different consumer, not in scope.
  - Any code change. Any runtime call. Any Hermes SSH or `git pull`/`git fetch`. Audit is purely against current local working tree.

## Consumer Expectations — `lib/scraper.py:_scrape_wechat`

Source: `lib/scraper.py` lines 157-213. The consumer iterates the 4 layers, and on the first non-None result reads the keys below.

| Key            | Type        | Required?                           | Used for                                                | Source line  |
| -------------- | ----------- | ----------------------------------- | ------------------------------------------------------- | ------------ |
| `content_html` | `str`       | One-of (`content_html` ∨ `markdown`) | Fed to `ingest_wechat.process_content()` to get markdown + images | 183          |
| `markdown`     | `str`       | One-of (`content_html` ∨ `markdown`) | SCR-06 short-circuit branch — returned as `ScrapeResult.markdown` directly | 188          |
| `images`       | `list[str]` | Optional (only on `markdown` branch) | Returned as `ScrapeResult.images` when SCR-06 short-circuit fires | 193          |
| `method`       | `str`       | Optional (defaulted)                 | `ScrapeResult.method`. Falls back to `fn_name.replace("scrape_wechat_", "")` | 196          |
| `title`        | `str`       | Optional (defaulted to `""`)         | `ScrapeResult.metadata["title"]`                        | 201          |
| `publish_time` | `str`       | Optional (defaulted to `""`)         | `ScrapeResult.metadata["publish_time"]`                 | 202          |

**Branching logic (the SCR-06 short-circuit):**

```text
if content_html:                              → use process_content(content_html) → (markdown, images)
elif markdown and not content_html:           → use markdown directly + result.get("images") or []   ← SCR-06
elif neither:                                 → continue cascade
```

**Notes on the consumer:**
- `images` is read ONLY in the SCR-06 short-circuit branch (line 193). On the `content_html` branch (line 195), images are derived purely from `process_content()` parsing the HTML — any pre-extracted image URL list on the result dict is silently discarded.
- `result.get("images") or []` returns `[]` for missing key OR empty-list OR None. There is no warning logged when this drops data.
- The four iterated function names are hard-coded. If any layer is missing or returns `None`, the consumer cascades silently.

## Per-Layer Return Shapes

### Apify — `scrape_wechat_apify` (reference only — fixed via SCR-06)

- **Location:** `ingest_wechat.py:520-556`.
- **Return paths:**

| Path | Trigger | Returns | Notes |
|------|---------|---------|-------|
| 1 | `APIFY_TOKEN` unset (line 522) | `None` | Print "Apify Token not found" |
| 2 | `client.actor(...).call(...)` succeeds + non-empty results (lines 540-553) | `dict` (see schema below) | Happy path |
| 3 | Apify call raises (line 554-555) | `None` | Print "Apify scraping failed: {e}" |
| 4 | Empty `results` list | falls through, returns `None` (line 556) | Silent — no specific log |

- **Happy-path dict (line 547-553):**

  ```python
  {
    "title":        item.get("title", ""),                   # str
    "markdown":     item.get("markdown", item.get("data", "")),  # str   ← key name driving SCR-06
    "publish_time": item.get("publish_time", ""),            # str
    "url":          url,                                      # str
    "method":       "apify",                                  # str
  }
  ```

- **Notable absences:** no `content_html`, no `images`, no `img_urls`. Apify already gives markdown — the legacy `ingest_article` consumer (line 945) extracts images from the markdown body via `re.findall(r'!\[.*?\]\((.*?)\)', markdown)`.

### CDP — `scrape_wechat_cdp`

- **Location:** `ingest_wechat.py:692-734`.
- **Return paths:**

| Path | Trigger | Returns | Notes |
|------|---------|---------|-------|
| 1 | CDP connect fails (line 698-700) | `None` | Logs "Failed to connect to CDP" |
| 2 | Connect + navigate succeed (lines 702-733) | `dict` (see schema below) | Happy path |
| 3 | `#js_content` selector missing (line 715-717) | Same dict, but `content_html = inner_html("body")` | Falls back to `<body>` — likely tens of kB of UI chrome, may flunk login-wall heuristics elsewhere |
| 4 | Any unhandled exception | propagates to caller | Caller's `try/except Exception` in `_scrape_wechat:175` cascades |

- **Happy-path dict (line 728-733):**

  ```python
  {
    "title":        title,         # str — from page.title()
    "content_html": content_html,  # str — inner_html("#js_content") OR inner_html("body")
    "publish_time": publish_time,  # str — inner_text("#publish_time") OR ""
    "url":          url,           # str
    "method":       "cdp",         # str
  }
  ```

- **No images key.** Consumer's `process_content(content_html)` will re-parse images from inside content_html — fine for CDP because CDP captures the rendered DOM (lazy-loaded `data-src` images get materialized after `wait_until="networkidle"` and the explicit scroll-to-bottom on line 709-710).
- **Quirk:** when CDP falls back to `inner_html("body")` (line 717), the resulting "content_html" is the entire page body. The consumer has no way to know this happened — and `process_content` will attempt to extract images from the whole page (header logos, footer ads, etc.).

### MCP — `scrape_wechat_mcp`

- **Location:** `ingest_wechat.py:558-689`.
- **Return paths:**

| Path | Trigger | Returns | Notes |
|------|---------|---------|-------|
| 1 | `_post("initialize")` HTTP error / non-200 (line 581-585) | flows to caller, eventually `None` | Returns `None` from `_post`, then layer's outer try fires `Exception` retry |
| 2 | MCP returns non-parseable result on attempt 2/2 (line 656-664) | `None` | Logged "MCP returned unparseable result" |
| 3 | `content_html` < 100 chars on attempt 2/2 (line 667-671) | `None` | Logged "MCP returned too little content" |
| 4 | Both attempts raise (line 684-688) | `None` | Logged with attempt # |
| 5 | Happy path (line 677-683) | `dict` (see below) | First successful atomic run |

- **Happy-path dict (line 677-683):**

  ```python
  {
    "title":        title,         # str — from data.get("title", "Untitled")
    "content_html": content_html,  # str — innerHTML of #js_content
    "publish_time": publish_time,  # str — from data.get("pubTime", "")
    "url":          url,           # str
    "method":       "mcp",         # str
  }
  ```

- **No images key.** Like CDP, consumer falls through to `process_content(content_html)`. **But unlike CDP**, MCP's JS extracts only `#js_content` innerHTML (line 622-625) — the surrounding `<head>` / `og:image` references are not carried.
- **Quirk:** the MCP path's JS also computes `imgCount` (line 626-628) from the DOM, but that count is not returned in the result dict. The data is computed and discarded — not a bug for the new consumer (which doesn't expect it), but a missed observability signal.
- **Relevant pre-existing finding:** `tools/call` invokes `browser_run_code_unsafe` (line 649). Per memory `cdp_mcp_dual_mode.md`, this is the correct name for Playwright MCP 1.60+. Not a return-shape issue.

### UA — `scrape_wechat_ua`

- **Location:** `ingest_wechat.py:426-517`.
- **Return paths:**

| Path | Trigger | Returns | Notes |
|------|---------|---------|-------|
| 1 | HTTP non-200 (line 447-449) | `None` | Logged `UA scrape: HTTP {code}` |
| 2 | `js_content`/`img-content` div not found in raw HTML (line 497-499) | `None` | Logged "article body not found in HTML" |
| 3 | Any exception (line 515-517) | `None` | Logged `UA scrape failed: {e}` |
| 4 | Happy path (line 507-514) | `dict` (see below) | UA spoof + manual div extraction |

- **Happy-path dict (line 507-514):**

  ```python
  {
    "title":        title,          # str — from og:title or <title>
    "content_html": content_html,   # str — bracket-matched div extraction (NOT a real HTML parser)
    "img_urls":     img_urls,       # list[str]   ← KEY-NAME MISMATCH vs consumer's "images"
    "url":          url,            # str
    "publish_time": publish_time,   # str — formatted from `var ct=...` UNIX ts OR #publish_time text
    "method":       "ua",           # str
  }
  ```

- **Critical quirk — image extraction strategy:** UA scans the *full* HTML for `data-src="(https?://mmbiz...)"` (line 503-504), NOT only `content_html`. So `img_urls` may include images that are referenced outside the `js_content` div (lazy-loaded via JS, or moved into modal galleries). Conversely, `process_content(content_html)` only extracts images present *inside* the bracket-matched div. The two lists are **non-overlapping in the general case** — `ingest_article` line 951 explicitly merges both: `img_urls = article_data.get("img_urls", []) + _img_urls`. The new `lib/scraper.py` consumer does neither (see Mismatch #1 below).

## Mismatch Findings

Sorted by severity descending. Severity scale:
- 🔴 silent data loss — runs to completion, downstream artifact incorrect
- 🟡 incorrect / underpopulated fallback — may impair quality, may cascade unexpectedly, needs runtime verification
- ⚪ harmless quirk — extra/unused field; no behavior change

| # | Layer | Consumer expects (`lib/scraper.py:_scrape_wechat`) | Layer returns (`ingest_wechat.py`) | Severity | Notes |
|---|-------|----------------------------------------------------|------------------------------------|---------|-------|
| 1 | **UA** | When SCR-06 short-circuit fires: `images` key (line 193) | `img_urls` key (line 510) | 🔴 | Silent data loss. **However:** SCR-06 short-circuit only fires when `markdown` is set AND `content_html` is empty (line 191). UA returns BOTH `content_html` non-empty AND no `markdown`. So UA actually takes the `process_content(content_html)` branch (line 195), and the `img_urls` from the full HTML are dropped on the floor regardless of key name. **Realized impact:** every UA-fallback article loses the images that exist outside the `#js_content` div. Compared to legacy `ingest_article` line 951, this is a measurable regression. |
| 2 | **Apify** | When SCR-06 short-circuit fires: `images` key (line 193) | Apify dict has no `images` AND no `img_urls` — only `markdown` containing `![...](url)` syntax | 🟡 | The legacy `ingest_article` consumer (line 945) handles this with `re.findall(r'!\[.*?\]\((.*?)\)', markdown)`. The new consumer just defaults to `[]`. Result: Apify articles routed via `lib/scraper.py:_scrape_wechat` get `ScrapeResult.images=[]`, even when the markdown body contains image references. Whether this is "data loss" depends on whether the downstream caller (e.g., `batch_ingest_from_spider.py:940`) re-parses images from `ScrapeResult.markdown` itself. Needs runtime verification. |
| 3 | **All four layers** | `metadata = {"title": ..., "publish_time": ..., "url": ...}` only (line 200-204) | All layers also return `url` (already covered) but extra fields like `img_urls` (UA) or even `imgCount` (computed-then-discarded, MCP) are simply dropped | ⚪ | Harmless on the consumer side — these keys aren't expected. Mentioning for completeness. |

**No CDP- or MCP-specific 🔴/🟡 mismatches found.** Both layers return `content_html` which the consumer correctly feeds to `process_content()`. The only CDP-specific concern (the `#js_content` → `body` fallback at line 717) is a content-quality concern, not a return-shape mismatch.

## Recommendations

Numbered, ranked by severity. **None of these should be implemented in this audit task** — they are queue-for-future-phase items per the audit-only constraint.

1. **DEFER — UA `images` vs `img_urls` mismatch (🔴).** Smallest possible fix is a one-line key normalization in either:
   - `ingest_wechat.scrape_wechat_ua` (rename returned key from `img_urls` → `images`), or
   - `lib/scraper.py:_scrape_wechat` (read `result.get("images") or result.get("img_urls") or []` AND apply on BOTH branches, not just the SCR-06 branch — i.e. merge with `process_content` output the way `ingest_article` line 951 already does for UA).

   The legacy `ingest_article` already proves the merge-both-lists semantic is correct. Recommend mirroring it in the consumer rather than touching the layer (preserves backward-compat for the legacy in-process caller). **Capture in next `/gsd:quick`, NOT this audit.**

2. **DEFER — Apify markdown image extraction missing in new consumer (🟡).** When `_scrape_wechat` takes the SCR-06 short-circuit, it returns `images=[]` for Apify. Mirror the regex `re.findall(r'!\[.*?\]\((.*?)\)', scraped_markdown)` from `ingest_article` line 945 inside the SCR-06 short-circuit branch. Smallest possible fix is one line. **Verify first** that downstream callers don't already re-parse `ScrapeResult.markdown` for images — if they do, this is moot.

3. **VERIFY at runtime — CDP body-fallback noise (🟡 → ⚪ if confirmed).** `inner_html("body")` (line 717) returns the entire page body when `#js_content` is absent. Add a structured log + count when this branch fires in production; if non-zero, investigate whether the resulting `ScrapeResult.markdown` is passing the SCR-04 quality gate when it shouldn't (i.e. login-wall pages slipping through). No code change yet — add observability and rerun.

4. **OBSERVABILITY ONLY — Surface `imgCount` from MCP path.** `scrape_wechat_mcp` JS (line 626-628) computes `imgCount` and discards it. Including it in the returned dict (e.g. `"imgCount": img_count`) at zero cost would let operators sanity-check MCP scraping fidelity against CDP. Cosmetic improvement; not a bug.

5. **NO ACTION — Extra debug keys.** `url` on every layer's return dict is harmless (consumer ignores it; metadata builds its own from the `url` parameter). `data` fallback in Apify (line 549, `item.get("markdown", item.get("data", ""))`) is a defensive shim — leave alone.

## Limitations

- **MCP layer protocol depth:** `_post` / `_text` / `_parse_run_code_json` helpers (lines 572-613) wrap an MCP-over-SSE protocol with session-id heartbeats. The full session lifecycle (initialize → notifications/initialized → tools/call → result) was traced shallowly; deeper edge cases (e.g. MCP server returns `result` without a `content` array, or `content` contains non-text entries first) might surface additional return-shape variance. **Marked INCONCLUSIVE for failure-mode return shapes; happy-path shape verified.** Within 30-min budget per layer per the plan.
- **No runtime probes performed.** All findings are static-source analysis. Severity 🟡 entries explicitly flagged as "needs runtime verification".
- **Apify deep dive intentionally skipped per scope.** Reference table only; no failure-path tracing beyond the four high-level branches.
- **Generic (`_scrape_generic`) cascade audit deferred** — different consumer (`ScrapeResult` directly, no `result.get()` indirection), out of scope.
