# Stack Research

**Domain:** v3.4 RSS-KOL Alignment — full-body article extraction for non-WeChat sources
**Researched:** 2026-05-03
**Confidence:** HIGH for extractor choice and version; MEDIUM for anti-bot coverage claims (site policies change)

---

## Context: What Stays (Do Not Re-Research)

The existing OmniGraph-Vault stack is validated and unchanged:

| Component | Library | Status |
|-----------|---------|--------|
| HTTP fetch (WeChat) | `requests` + UA rotation in `ingest_wechat.py` | Stays |
| HTML→Markdown | `html2text` | Stays for WeChat path |
| Vision cascade | `image_pipeline.py` (SiliconFlow → OpenRouter → Gemini) | Reused as-is |
| LightRAG ingest | `lightrag-hku`, kuzu backend | Unchanged |
| Checkpoint system | `lib/checkpoint.py` | Reused unchanged |
| Entity buffer | `ENTITY_BUFFER_DIR` + SQLite dual-write | Unchanged |
| Classification prompt | `_build_fullbody_prompt` in `batch_classify_kol.py` | Ported to RSS |

The additions below target only the **new cascade scraper abstraction** (Wave 1) and RSS-adapted content extraction.

---

## New Libraries Required

### Core Addition: trafilatura

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `trafilatura` | **2.0.0** (released 2024-12-03) | Full-body extraction from non-WeChat HTML | Highest recall + precision on open-web article URLs; RAG-aware topics in its own tag set; actively used by HuggingFace, IBM, Microsoft Research; 5.8k GitHub stars; Markdown output native since v1.9 |

**Why trafilatura beats alternatives for OmniGraph's site mix:**

- **vs. newspaper4k 0.9.5:** newspaper4k (released 2026-02-28) is the active fork of newspaper3k, but it has known issues with Medium's `<section>` structure (open issues: "Medium.com & `<section>` problems", "Silent failing on medium article"). newspaper4k also requires NLP downloads for keyword extraction — unused weight. trafilatura handles the same sites with zero config.
- **vs. goose3 3.1.21 (released 2025-11-30):** goose3 extracts main text and candidate image only. No Markdown output, no code block preservation, no table support. Designed for news article text, not tech blog content with code. Poor fit for Arxiv HTML pages.
- **vs. readability-lxml 0.8.1 (last release 2020-07-04):** Essentially unmaintained. Mozilla Readability.js has moved on; the Python port is frozen at 2020. trafilatura actually includes a maintained readability_lxml module as an internal fallback component.

**trafilatura code block support (verified in source, commit post-2025-02-07):**

`htmlprocessing.py` contains `_is_code_block()` which detects code-containing `<pre>` elements via `CODE_INDICATORS = ["{", '("', "('", "\n    "]` and `hljs` class detection. PR #776 (merged 2025-02-07) fixed fenced code block formatting. This is available in v2.0.0.

**trafilatura Markdown output:**

```python
from trafilatura import extract

text = extract(
    html,
    output_format="markdown",
    include_formatting=True,
    include_tables=True,
    include_images=True,      # preserves <img alt="..."> as markdown image refs
    include_links=True,
    favor_recall=True,        # for tech blogs: fewer false negatives
    url=source_url,           # enables absolute link conversion
)
```

**Known limitation — math/figure elements stripped by default:**

`MANUALLY_CLEANED` in `trafilatura/settings.py` explicitly includes `"figure"`, `"math"`, `"svg"`, `"picture"`. This means:
- Inline LaTeX in Arxiv HTML (`<math>` tags) will be dropped
- Figures without alt text lose their caption

**Mitigation:** For `arxiv.org/abs/*` URLs, skip trafilatura and use the existing PyMuPDF path on the PDF (`arxiv.org/pdf/*`). PyMuPDF preserves the full paper text. This is the correct routing strategy (see URL Routing section below).

### Supporting Addition: tldextract (optional)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `tldextract` | **5.3.1** (released 2025-12-29) | Accurate subdomain/domain/suffix splitting for URL routing | Only if using pattern matching on `*.substack.com`, `*.medium.com` etc. |

**However:** `urllib.parse.urlparse` is sufficient for the v3.4 routing table because all target domains are either exact matches (`arxiv.org`, `huggingface.co`, `github.blog`) or simple suffix matches (`mp.weixin.qq.com`, `*.substack.com`). tldextract adds a PSL dependency for a problem solvable with a 20-line routing dict. **Defer tldextract unless the routing table grows beyond 15 entries.**

Simple routing with stdlib:

```python
from urllib.parse import urlparse

def _site_type(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "mp.weixin.qq.com" in host:
        return "wechat"
    if host.endswith(".substack.com") or "substack.com" in host:
        return "substack"
    if "medium.com" in host:
        return "medium"
    if "arxiv.org" in host:
        return "arxiv"
    if "huggingface.co" in host:
        return "huggingface"
    if "github.blog" in host or ("github.com" in host and "/blog" in urlparse(url).path):
        return "github_blog"
    return "generic"
```

---

## Site Coverage Analysis

### What Works With UA-Only HTTP (no JS rendering needed)

| Site | Anti-Bot | trafilatura UA fetch | Notes |
|------|----------|---------------------|-------|
| `huggingface.co/blog/*` | None (SSR Hugo static) | YES — clean HTML, works out of the box | No session, no JS required |
| `arxiv.org/abs/*` | None | YES — but prefer PDF path for formulas | HTML abstract only; full paper needs PDF |
| `github.blog/*` | None (static) | YES | Clean blog HTML |
| `*.substack.com/*` (free newsletter) | Light (Cloudflare but no captcha for free posts) | YES for public posts | Paid posts need login — out of scope for RSS |
| WordPress blogs (`/wp-json/...` or standard HTML) | Varies | YES via trafilatura UA | Some use Cloudflare |
| Ghost blogs (free tier) | None | YES | Members-only posts gated — skip |

### What Requires CDP/MCP Fallback

| Site | Anti-Bot | Reason | Cascade Layer |
|------|----------|--------|---------------|
| `medium.com/*` | Cloudflare + JS paywall | UA fetch returns login wall for non-members; even free articles have JS-rendered content behind a soft paywall after ~3 reads | CDP/MCP layer 3 |
| `mp.weixin.qq.com/*` | WeChat token check | Already handled by existing UA rotation with MicroMessenger UA | Layer 1 (existing) |

**Medium reality check (2025-2026):** Medium serves article HTML to bots but injects a paywall overlay via JS. The raw HTML contains the article text in the DOM for many articles (metered paywall). trafilatura on the raw HTML of a free Medium article often succeeds. The CDP fallback is only needed for paywalled content — which OmniGraph should exclude via depth_score gate anyway.

**Practical rule:** RSS feeds from Medium/Substack only surface URLs the author chose to make public. Paywalled articles won't appear in free RSS feeds. So UA+trafilatura is sufficient for RSS-sourced Medium/Substack URLs.

### Arxiv Routing Strategy

```
arxiv.org/abs/XXXX.XXXXX  →  trafilatura on abstract HTML (title, abstract, metadata)
arxiv.org/pdf/XXXX.XXXXX  →  PyMuPDF path (already in stack via multimodal_ingest.py)
arxiv.org/html/XXXX.XXXXX →  trafilatura with favor_recall=True (newer papers 2024+)
```

For arxiv.org/html/* pages (the new HTML rendering of full papers), trafilatura works but will lose `<math>` elements. Acceptable — the abstract + metadata is what matters for LightRAG; the full paper math is not queryable meaningfully.

---

## Cascade Architecture

### Layer Order and Trigger Conditions

The new generic scraper implements a 4-layer cascade. Each layer has explicit trigger conditions — not just "try and see":

```
Layer 1: trafilatura UA fetch (PRIMARY)
    Trigger: All non-WeChat URLs
    Success signal: extracted text length >= 500 chars AND not a login/error page
    Fail signal: text < 500 chars OR contains login-wall keywords
        OR HTTP status in {401, 403, 429, 503}
    Implementation: trafilatura.fetch_url(url) + trafilatura.extract(html, ...)

Layer 2: requests UA-spoofed fetch + trafilatura extract (SECONDARY)
    Trigger: Layer 1 returns None OR text < 500 chars
    Why separate: trafilatura.fetch_url() uses its own UA "trafilatura/2.0.0 (+...)"
        which some sites block; Layer 2 uses a browser-like UA
    Success signal: same as Layer 1
    Implementation: requests.get(url, headers={"User-Agent": BROWSER_UA}, timeout=15)
        then trafilatura.extract(html, ...)

Layer 3: CDP / MCP browser render (TERTIARY)
    Trigger: Layer 2 fails OR site_type == "medium" (skip layers 1-2, start here)
    Success signal: content_html length >= 200 chars after JS renders
    Implementation: existing scrape_wechat_cdp / scrape_wechat_mcp with
        site-specific selector (not just #js_content — parameterize selector)
    Note: For generic sites use document.body.innerHTML as selector fallback

Layer 4: RSS summary fallback (LAST RESORT)
    Trigger: All layers failed
    Action: Use existing rss_articles.summary as body; flag as "summary_only"
        in checkpoint metadata; do NOT set enriched=2 (retry next batch)
    Success signal: summary length >= 200 chars
```

### Concrete Trigger Conditions (code-ready)

```python
# Layer 1/2 content quality gate
MIN_CONTENT_LENGTH = 500  # chars after extraction
LOGIN_WALL_KEYWORDS = [
    "sign in", "log in", "subscribe to continue",
    "create a free account", "members only",
    "please verify", "login required",
    "完成验证", "请登录",  # WeChat Chinese equivalents already in existing code
]

def _is_scrape_success(text: str | None) -> bool:
    if not text or len(text) < MIN_CONTENT_LENGTH:
        return False
    text_lower = text.lower()
    return not any(kw in text_lower for kw in LOGIN_WALL_KEYWORDS)

# HTTP status gate (before extraction)
RETRY_STATUS_CODES = {429, 503, 502, 504}  # transient → retry with backoff
FAIL_STATUS_CODES = {401, 403, 404, 410}   # permanent → cascade immediately
```

### Integration With Existing ingest_wechat.py

The generic scraper abstraction slots in as a new module `enrichment/scraper.py` (or `lib/scraper.py`) that:

1. Imports trafilatura (new dependency)
2. Returns the same dict shape as `scrape_wechat_ua`: `{"title", "markdown", "img_urls", "url", "method"}`
3. Does NOT touch `ingest_wechat.py` directly — WeChat path stays unchanged

**D-RSS-SCRAPER-SCOPE Decision (from PROJECT.md):**

Option A (both KOL + RSS use the generic scraper) is preferred but carries **one regression risk**: `batch_ingest_from_spider.py:940` calls `scrape_wechat_ua` directly in `_classify_full_body`. If the generic scraper replaces this, the UA-rotation timing (`_ua_cooldown`) must be preserved. The safe approach:

- **Wave 1:** Implement generic scraper as a NEW function (`scrape_generic_url`) parallel to the existing `scrape_wechat_ua`. No changes to WeChat path.
- **Wave 3 regression:** After RSS E2E passes, upgrade `_classify_full_body` to call `scrape_generic_url` for non-WeChat KOL articles (there should be very few — KOL sources are WeChat-only by definition). This keeps regression scope minimal.

**Integration point for Wave 1:**

- New file: `enrichment/scraper.py` (or `lib/scraper.py`)
- `rss_ingest.py` imports from it: `from enrichment.scraper import scrape_generic_url`
- `image_pipeline.py` reused unchanged — the generic scraper returns `img_urls` which feeds the existing `download_images()` + `describe_images()` cascade

---

## Recommended Stack: What to Add

```bash
# New addition (single package)
pip install trafilatura==2.0.0

# trafilatura v2.0 dependencies (auto-installed):
# - lxml (already in stack via beautifulsoup4[lxml])
# - courlan (URL utilities)
# - certifi, urllib3 (already in stack via requests)
# NO NEW HEAVY DEPENDENCIES
```

**requirements.txt delta:**

```
trafilatura>=2.0.0,<3.0
```

That is the only new package. tldextract is explicitly deferred. No new browser automation libraries needed (existing Playwright CDP/MCP handles Layer 3).

---

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| `trafilatura 2.0` | `newspaper4k 0.9.5` | Known Medium `<section>` bugs; NLP download required for keyword extraction (unused); fewer fidelity controls for code/table content |
| `trafilatura 2.0` | `goose3 3.1.21` | No Markdown output; no code block support; designed for news text not tech blogs |
| `trafilatura 2.0` | `readability-lxml 0.8.1` | Last release 2020; unmaintained; trafilatura uses readability as internal fallback already |
| `urllib.parse` routing | `tldextract 5.3.1` | Stdlib sufficient for 6-site routing table; tldextract adds PSL download cost for zero benefit at current scale |
| Existing `requests` | `httpx 0.28.1` | httpx async is not needed — trafilatura and the UA layer are already in asyncio.to_thread; adding httpx is scope creep |

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `selenium` / headless Chrome (separate from existing Playwright) | Duplicate browser automation; existing Playwright CDP/MCP is Layer 3 | Existing `scrape_wechat_cdp` / `scrape_wechat_mcp` |
| `scrapy` framework | Full framework overhead for single-URL extraction; conflicts with existing asyncio | `trafilatura.fetch_url` + `requests` |
| `playwright-stealth` | Unnecessary for open-web RSS sources; adds maintenance burden; existing MicroMessenger UA rotation already handles WeChat | Standard browser UA in Layer 2 |
| `tldextract` (now) | PSL download; stdlib handles the routing table | `urllib.parse.urlparse()` |
| Any JS parser (e.g., `pyduktape`, `js2py`) | RSS sources that are fully JS-rendered at all layers are not worth ingesting; they won't have quality content detectable via RSS anyway | Skip / flag as unscrapable |

---

## Version Compatibility Notes

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `trafilatura>=2.0.0` | `lxml>=5.0` | trafilatura 2.0 requires lxml ≥ 5; incompatibility with `lxml 6` is an open issue (#open bug as of 2026-05-03) — pin `lxml>=4.9,<6` in requirements if lxml 6 is not already pinned |
| `trafilatura>=2.0.0` | `beautifulsoup4` any | trafilatura uses lxml directly, not bs4; no conflict |
| `trafilatura>=2.0.0` | `html2text` any | Different extraction path — trafilatura for open-web URLs, html2text for WeChat HTML already parsed by bs4; coexist without conflict |
| `trafilatura 2.0` | Python 3.11+ | Drops 3.6/3.7 (breaking change in 2.0); 3.11 is fine |

**lxml version check:**

```bash
python -c "import lxml; print(lxml.__version__)"
```

If lxml >= 6 is installed, add `lxml>=4.9,<6` to requirements.txt until the trafilatura issue is resolved.

---

## Stack Patterns by Variant

**If URL is WeChat (`mp.weixin.qq.com`):**
- Use existing `ingest_wechat.py` path unchanged (UA rotation → Apify → CDP/MCP)
- Do NOT route through trafilatura
- Rationale: WeChat MicroMessenger UA spoofing is a bespoke solution that trafilatura's generic UA cannot replicate

**If URL is Arxiv (`arxiv.org/abs/*`):**
- Fetch HTML via trafilatura Layer 1 for abstract/metadata
- If full paper needed: rewrite URL to `arxiv.org/pdf/XXXX.pdf` and use PyMuPDF path
- Rationale: trafilatura drops `<math>` elements; PyMuPDF preserves equation text

**If URL is Arxiv HTML (`arxiv.org/html/*`):**
- Use trafilatura with `favor_recall=True`; accept math loss
- Rationale: newer papers (2024+) have HTML versions; math loss is acceptable for LightRAG entity extraction

**If URL is Medium (`medium.com/*`) from RSS:**
- Attempt Layer 1 (trafilatura UA) — many free articles succeed
- On failure, fall back to Layer 3 (CDP/MCP) without Layer 2 retry
- Rationale: Medium's Cloudflare is triggered by repeated bot-like requests; skip Layer 2 on first failure

**If URL is Substack (free newsletter):**
- Layer 1 (trafilatura UA) succeeds reliably for public posts
- No CDP needed
- Paid posts do not appear in free RSS feeds

**If URL returns HTTP 429:**
- Do NOT cascade immediately — 429 is transient
- Apply exponential backoff (30s, 60s, 120s) then retry Layer 1
- If 429 persists after 3 retries, cascade to Layer 3
- Rationale: cascading on first 429 burns CDP session quota unnecessarily

---

## Sources

- trafilatura GitHub releases API — v2.0.0 confirmed 2024-12-03 (HIGH confidence)
- trafilatura source: `htmlprocessing.py` `_is_code_block()` function, `settings.py` `MANUALLY_CLEANED` — direct code inspection (HIGH confidence)
- trafilatura PR #776 merged 2025-02-07 — code block fix confirmed (HIGH confidence)
- newspaper4k GitHub releases API — v0.9.5 confirmed 2026-02-28 (HIGH confidence)
- newspaper4k issues: "Medium.com & `<section>` problems", "Silent failing on medium article" — open issues confirmed (HIGH confidence)
- goose3 GitHub releases API — v3.1.21 confirmed 2025-11-30 (HIGH confidence)
- readability-lxml GitHub releases API — v0.8.1 last release 2020-07-04 (HIGH confidence)
- tldextract GitHub releases API — v5.3.1 confirmed 2025-12-29 (HIGH confidence)
- trafilatura open issue: "Incompatibility with `lxml` 6" — confirmed open 2026-05-03 (HIGH confidence)
- `ingest_wechat.py` source read — cascade order, return dict shape, UA rotation confirmed (HIGH confidence)
- `batch_ingest_from_spider.py:940` — `_classify_full_body` UA-only path confirmed (HIGH confidence)
- Medium/Substack anti-bot assessment: MEDIUM confidence — site policies change; verified against known scraping community knowledge as of 2025

---

*Stack research for: v3.4 RSS-KOL Alignment — generic scraper abstraction (Wave 1)*
*Researched: 2026-05-03*
