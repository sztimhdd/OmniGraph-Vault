---
quick_id: 260505-sjk
type: quick
wave: 1
depends_on: []
files_modified:
  - lib/scraper.py
  - tests/unit/test_scraper_ua_img_merge.py
autonomous: true
requirements:
  - SCR-06-followup
must_haves:
  truths:
    - "UA-fallback articles retain pre-HTML img_urls (data-src outside #js_content) instead of silently dropping them"
    - "Apify SCR-06 short-circuit branch behavior is unchanged (no images key, no img_urls key — still falls back to result.get('images') or [])"
    - "process_content branch (UA / CDP / MCP / resumed) merges result.get('img_urls', []) with the list returned by process_content, in that order, mirroring ingest_article:978"
    - "All 4 mock-only tests pass; full pytest regression on tests/unit/test_scraper*.py is green"
  artifacts:
    - path: "lib/scraper.py"
      provides: "Patched _scrape_wechat() consumer that mirrors ingest_article:978 merge semantic"
      contains: "result.get(\"img_urls\""
    - path: "tests/unit/test_scraper_ua_img_merge.py"
      provides: "4 mock-only test cases covering UA merge + Apify short-circuit sanity"
      contains: "test_ua_merges_img_urls_with_content_html_images"
  key_links:
    - from: "lib/scraper.py:_scrape_wechat (process_content branch, ~line 195)"
      to: "ingest_wechat.process_content output + result['img_urls']"
      via: "list concat: result.get('img_urls', []) + process_content_imgs"
      pattern: "result\\.get\\(\"img_urls\""
---

<objective>
Fix the 🔴 silent data-loss bug found in audit `ece03ae` (`docs/research/scraper_layer_shape_audit_2026_05_05.md` Mismatch #1).

`scrape_wechat_ua` at `ingest_wechat.py:507-514` returns key `img_urls` (images extracted from the FULL HTML via `data-src="..."` regex — including images outside the `#js_content` div). The new consumer at `lib/scraper.py:_scrape_wechat` reads key `images` ONLY on the SCR-06 short-circuit branch. UA always takes the `process_content(content_html)` branch (line 195), so its `img_urls` are silently discarded. The legacy in-process consumer at `ingest_wechat.py:978` correctly merges both lists:

    img_urls = article_data.get("img_urls", []) + _img_urls

Goal: Mirror that merge semantic in `_scrape_wechat`'s `process_content` branch so UA-fallback articles retain their pre-HTML image URLs.

Purpose: Restores image-fidelity parity between the new `lib/scraper.py` consumer and the legacy `ingest_article` consumer for UA-fallback articles. Day-1/2/3 KOL cron observations have shown UA is firing as a real fallback — every UA-fallback article today is losing its outside-`#js_content` images.

Output: 1 surgical patch in `lib/scraper.py` + 1 new mock-only test file at `tests/unit/test_scraper_ua_img_merge.py` + 1 atomic commit.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/STATE.md
@./CLAUDE.md
@docs/research/scraper_layer_shape_audit_2026_05_05.md
@lib/scraper.py
@ingest_wechat.py

<interfaces>
<!-- Key types and contracts the executor needs. Extracted from current source. -->
<!-- DO NOT change any of these — only the marked section in lib/scraper.py is in scope. -->

From lib/scraper.py:60-73 — the dataclass (DO NOT TOUCH):
```python
@dataclass(frozen=True)
class ScrapeResult:
    markdown: str
    images: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    method: str = ""
    summary_only: bool = False
    content_html: Optional[str] = None
```

From lib/scraper.py:157-213 — current `_scrape_wechat` consumer (THE PATCH SITE).
The `process_content` branch is line 195 inside the `else:` of the SCR-06 if/elif:

```python
if scraped_markdown and not content_html:
    markdown = scraped_markdown
    imgs = result.get("images") or []          # SCR-06 short-circuit (Apify) — UNCHANGED
else:
    markdown, imgs = ingest_wechat.process_content(content_html)
    # ← FIX GOES HERE: merge result.get("img_urls", []) with imgs
```

From ingest_wechat.py:507-514 — UA layer return shape (DO NOT TOUCH):
```python
return {
    "title": title,
    "content_html": content_html,
    "img_urls": img_urls,           # ← key name stays as-is
    "url": url,
    "publish_time": publish_time,
    "method": "ua",
}
```

From ingest_wechat.py:976-978 — LEGACY merge semantic (the contract to mirror):
```python
markdown, _img_urls = process_content(article_data["content_html"])
# Merge UA-extracted data-src images with process_content images
img_urls = article_data.get("img_urls", []) + _img_urls
```

Notes on the legacy line — read carefully:
- It is **plain concat with `+`** — NOT dedup, NOT set semantics. Order is preserved: `img_urls` first, `process_content` images second.
- Duplicates ARE possible if the same `data-src` URL appears both inside `#js_content` (caught by `process_content`) and elsewhere in the page (caught by the UA `data-src` regex).
- The legacy code path proves this is the production-correct contract today (legacy callers have not reported duplication issues — downstream image_pipeline likely de-dupes by hash).

From ingest_wechat.py:763-775 — `process_content` (DO NOT TOUCH; mock target in tests):
```python
def process_content(html):
    soup = BeautifulSoup(html, 'html.parser')
    images = []
    for img in soup.find_all('img'):
        src = img.get('data-src') or img.get('src')
        if src and src.startswith('http'):
            images.append(src)
    h = html2text.HTML2Text()
    h.ignore_links = False
    markdown = h.handle(html)
    return markdown, images
```
</interfaces>

**Hard scope guards (HARD NO list — re-read before writing any code):**
- Do NOT change `scrape_wechat_ua` (key naming stays `img_urls`)
- Do NOT touch Apify / CDP / MCP layer functions
- Do NOT touch any production env vars
- Do NOT redo or extend the audit
- Do NOT fix 🟡 / ⚪ / INCONCLUSIVE items from the audit (Apify markdown image regex, CDP body fallback, MCP imgCount surfacing — all out of scope)
- Do NOT invent a new merge strategy (no dedup, no set, no order swap) — mirror line 978 exactly

**Pre-flight assumption to surface (per "Think Before Coding"):**
The task brief says "deduped, preserving order" for test case 1, but legacy `ingest_article:978` does plain `+` concat with NO dedup. Test 1 inputs (`img_urls=["a","b"]` + html with `<img src="c">`) are non-overlapping, so plain concat produces `["a","b","c"]` naturally — no dedup behavior is exercised by these inputs. The fix mirrors the legacy concat exactly. If the user wants dedup later, that is a separate decision (would diverge from `ingest_article:978`). This plan does NOT add dedup.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add 4 mock-only RED tests for UA img_urls merge in lib/scraper._scrape_wechat</name>
  <files>tests/unit/test_scraper_ua_img_merge.py</files>
  <behavior>
    Mock-only tests — no real HTTP, no real Apify/CDP/MCP/UA calls, no LightRAG. Patch `ingest_wechat.scrape_wechat_apify`, `ingest_wechat.scrape_wechat_cdp`, `ingest_wechat.scrape_wechat_mcp`, `ingest_wechat.scrape_wechat_ua`, and `ingest_wechat.process_content` via monkeypatch / unittest.mock so the cascade is fully controlled.

    All tests are async and call `lib.scraper._scrape_wechat(url)` directly (not the public `scrape_url` — keeps the unit narrow and avoids the router).

    Test cases:

    - **test_ua_merges_img_urls_with_content_html_images** (the bug under fix)
      - apify/cdp/mcp mocked to return `None`
      - ua mocked to return `{"title":"t", "content_html":"<div><img src='c'></div>", "img_urls":["a","b"], "url":url, "publish_time":"", "method":"ua"}`
      - process_content mocked to return `("md-body", ["c"])`
      - assert: result.images == ["a","b","c"]
      - assert: result.method == "ua"
      - assert: result.markdown == "md-body"
      - assert: result.metadata["title"] == "t"

    - **test_ua_empty_img_urls_yields_only_process_content_images**
      - apify/cdp/mcp mocked to return `None`
      - ua mocked to return same shape but `"img_urls": []` and content_html with one `<img>`
      - process_content mocked to return `("md", ["x", "y"])`
      - assert: result.images == ["x", "y"]
      - assert: result.method == "ua"

    - **test_ua_img_urls_only_no_html_imgs**
      - apify/cdp/mcp mocked to return `None`
      - ua mocked to return `"img_urls": ["x"]` and content_html present (e.g., "<div>plain text</div>")
      - process_content mocked to return `("md", [])`
      - assert: result.images == ["x"]
      - assert: result.method == "ua"

    - **test_apify_short_circuit_unchanged_no_img_urls_key**
      - apify mocked to return `{"title":"t", "markdown":"# h\n![alt](url1)", "publish_time":"", "url":url, "method":"apify"}` (NO content_html, NO img_urls, NO images key)
      - cdp/mcp/ua should never be invoked (cascade short-circuits on first non-None)
      - process_content should NOT be called
      - assert: result.markdown == "# h\n![alt](url1)"
      - assert: result.images == []   # SCR-06 path — no images key, defaults to []
      - assert: result.method == "apify"
      - This is the regression sanity guard: confirms the fix did not change SCR-06 short-circuit semantics.

    Implementation hints:
    - Use `pytest.mark.asyncio` (already used in other test files in tests/unit/) — confirm by quick grep before writing.
    - Async mocks: define `async def fake_apify(url): return None` (or whatever return value), then `monkeypatch.setattr(ingest_wechat, "scrape_wechat_apify", fake_apify)`. process_content is sync — plain `monkeypatch.setattr(ingest_wechat, "process_content", lambda html: ("md", ["c"]))`.
    - All tests must be in a single file `tests/unit/test_scraper_ua_img_merge.py`.

    These tests must FAIL (RED) before the patch in Task 2.
  </behavior>
  <action>
    1. Create `tests/unit/test_scraper_ua_img_merge.py`.
    2. Top of file: standard pytest + asyncio imports + import `lib.scraper` and `ingest_wechat`.
    3. Use `monkeypatch` fixture to patch the 4 layer functions (apify/cdp/mcp/ua) and `process_content` per test.
    4. Each test: `result = await lib.scraper._scrape_wechat("https://mp.weixin.qq.com/s/test")` then assert on `result.images`, `result.markdown`, `result.method`.
    5. Run `python -m pytest tests/unit/test_scraper_ua_img_merge.py -v` — expect 3 FAIL (the 3 UA tests; the apify short-circuit one will already pass on current code) → that is the correct RED state for the bug under fix.
    6. Do NOT modify `lib/scraper.py` in this task. Do NOT add dedup logic.
    7. Pre-check before writing: quick grep for `pytest.mark.asyncio` in existing tests/unit/test_scraper*.py to confirm the project's async-test idiom; mirror it.
  </action>
  <verify>
    <automated>python -m pytest tests/unit/test_scraper_ua_img_merge.py -v 2>&amp;1 | grep -E "(PASSED|FAILED|ERROR)"</automated>
  </verify>
  <done>
    Test file exists at `tests/unit/test_scraper_ua_img_merge.py` with exactly 4 test functions named per the behavior spec. The 3 UA tests FAIL with assertion mismatches on `result.images` (expect "a","b","c" or "x"; actual ["c"] or []). The apify short-circuit test PASSES (regression guard confirms current behavior is preserved). No real network calls. No real LightRAG init.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Patch lib/scraper._scrape_wechat process_content branch to merge img_urls (mirrors ingest_article:978)</name>
  <files>lib/scraper.py</files>
  <behavior>
    Smallest possible diff in `lib/scraper.py:_scrape_wechat`. Only the `else:` branch of the SCR-06 if/elif (currently line 194-195) changes.

    Before:
    ```python
    if scraped_markdown and not content_html:
        markdown = scraped_markdown
        imgs = result.get("images") or []
    else:
        markdown, imgs = ingest_wechat.process_content(content_html)
    ```

    After:
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

    Three structural points:
    - Use `list(result.get("img_urls") or [])` (not bare `result.get("img_urls", [])`) so that `None` falls through to `[]` AND the resulting object is a fresh list (defensive — avoids mutating the dict's underlying list if caller later iterates).
    - Order: `img_urls` FIRST, then `_process_imgs` — exact mirror of `ingest_article.py:978`.
    - Comment cites `ingest_article:978` AND audit commit `ece03ae` so future readers can trace the contract.

    No other lines in `lib/scraper.py` change. The SCR-06 short-circuit branch is untouched. The dataclass is untouched. The router is untouched. The generic cascade is untouched.
  </behavior>
  <action>
    1. Read `lib/scraper.py` lines 180-210 to confirm the patch site is exactly as described above.
    2. Apply the smallest possible diff using the `Edit` tool (NOT Write — preserves the rest of the file).
    3. Re-run the test file from Task 1: `python -m pytest tests/unit/test_scraper_ua_img_merge.py -v`. Expect all 4 tests to PASS.
    4. Run a wider regression: `python -m pytest tests/unit/test_scraper*.py -v` — expect no NEW failures (pre-existing failures, if any, are out of scope per audit-only-style hard scope).
    5. NO refactoring of adjacent code (per Surgical Changes). NO comment cleanup elsewhere. NO type annotation additions.
    6. NO change to `scrape_wechat_ua` in `ingest_wechat.py`. NO change to any other layer function.

    HARD NO list (re-confirm before commit):
    - Do not add dedup. Plain `+` concat per legacy.
    - Do not change argument order in the concat.
    - Do not touch the SCR-06 short-circuit branch (Apify path — that's audit Mismatch #2, out of scope).
    - Do not touch `_scrape_generic`, `_route`, `_passes_quality_gate`, `_fetch_with_backoff_on_429`, `scrape_url`.
  </action>
  <verify>
    <automated>python -m pytest tests/unit/test_scraper_ua_img_merge.py tests/unit/test_scraper*.py -v 2>&amp;1 | tail -20</automated>
  </verify>
  <done>
    All 4 tests in `tests/unit/test_scraper_ua_img_merge.py` PASS. No new regressions in other `tests/unit/test_scraper*.py` files. Diff in `lib/scraper.py` is contained to the `else:` branch around line 194-195 (~3-5 lines added including the 3-line comment). `git diff lib/scraper.py` shows ONLY that block changed. Then run a single atomic commit:

    `git add lib/scraper.py tests/unit/test_scraper_ua_img_merge.py`
    `git commit -m "fix(scr-06-followup): merge UA img_urls with content_html images (silent loss fix per audit ece03ae)"`

    Commit message must be EXACTLY that string per task brief — no Co-Authored-By footer, no attribution (per `~/.claude/settings.json` global setting). Verify with `git log -1 --pretty=%s` matches.
  </done>
</task>

</tasks>

<verification>
After Task 2 commits:

1. **Test gate:** `python -m pytest tests/unit/test_scraper_ua_img_merge.py -v` → 4/4 PASSED.
2. **Regression gate:** `python -m pytest tests/unit/test_scraper*.py -v` → no new failures (pre-existing failures, if any, must be unchanged from pre-patch baseline).
3. **Diff size gate:** `git diff HEAD~1 -- lib/scraper.py | wc -l` → expect roughly 5-12 lines (3-5 production code + comment + diff context). If >20 lines, the patch is over-scoped — revisit.
4. **Commit message exactness:** `git log -1 --pretty=%s` → must match exactly `fix(scr-06-followup): merge UA img_urls with content_html images (silent loss fix per audit ece03ae)`.
5. **No layer-function diff:** `git diff HEAD~1 -- ingest_wechat.py` → must be empty. The fix is consumer-side ONLY.
</verification>

<success_criteria>
1. `lib/scraper.py:_scrape_wechat` `process_content` branch merges `result.get("img_urls", [])` with `process_content` output, in that order, via plain list concat (mirrors `ingest_article:978` exactly).
2. UA-fallback articles now have `ScrapeResult.images` containing both data-src URLs from outside `#js_content` AND images parsed from inside `content_html`. Audit `ece03ae` Mismatch #1 closed.
3. SCR-06 short-circuit branch (Apify path) behavior is byte-identical to before — proven by `test_apify_short_circuit_unchanged_no_img_urls_key`.
4. No changes to any layer function (`scrape_wechat_ua` / `_apify` / `_cdp` / `_mcp`).
5. Single atomic commit with exact message string from task brief.
6. Time budget: ≤45 min total. Hard stop at 60 min — if blocked at that point, revert WIP and surface the blocker rather than landing a half-fix.
</success_criteria>

<output>
After completion, create `.planning/quick/260505-sjk-fix-ua-img-urls-consumer-merge-scr-06-fo/260505-sjk-SUMMARY.md` summarizing:
- Diff size (lines added/removed in lib/scraper.py)
- Test result (4/4 GREEN)
- Regression result (full pytest tests/unit/test_scraper*.py pass count vs baseline)
- Commit hash and exact message
- Audit Mismatch #1 status: CLOSED
- Audit Mismatch #2 (Apify markdown image regex) and #3 (CDP body fallback): UNCHANGED — still DEFER per audit recommendation; out of scope for this quick task
</output>
