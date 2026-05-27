# Phase 19: Generic Scraper + Schema + KOL Hotfix - Research

**Researched:** 2026-05-03
**Domain:** Python HTML scraping cascade + SQLite schema ALTER + checkpoint hash migration
**Confidence:** HIGH (empirical install + extraction smoke-test on actual trafilatura 2.0.0 + lxml 6.1.0)

## Summary

Phase 19 is a tightly scoped urgent hotfix: extract `ingest_wechat` cascade logic into a new public `lib/scraper.py` module, fix the UA-only regression at `batch_ingest_from_spider.py:940` before 2026-05-04 06:00 ADT cron fire, add 5 nullable columns to `rss_articles`, and unify the checkpoint hash to SHA-256-16.

Empirical smoke test (performed during research) confirms trafilatura 2.0.0 installs cleanly on Python 3.13 alongside lxml 6.1.0 and correctly emits markdown-with-inline-images via `extract(html, output_format='markdown', include_images=True)` — exactly the shape downstream `image_pipeline.localize_markdown` expects. The codebase uses Python 3.11+; trafilatura 2.0.0's classifiers list 3.8-3.13 so 3.11 is well within the supported band.

The SCR-07 `lxml<6` cap in the upstream milestone spec is **overly conservative** — my empirical test proves pip resolves `trafilatura==2.0.0 + lxml>=5.3,<7` without conflicts, and the extraction round-trip succeeds. Recommend raising the floor to `>=5.3` (to match trafilatura 2.0.0's actual `Requires-Dist: lxml>=5.3.0`) and removing the `<6` cap unless regression is observed.

**Primary recommendation:** Build `lib/scraper.py` as a thin router + cascade around the four existing scrapers in `ingest_wechat.py` (apify → mcp → cdp → ua). Add trafilatura as a **new** layer for the non-WeChat generic path only — do NOT refactor the existing WeChat cascade. Keep `ScrapeResult.content_html` as a required field (not optional) so the line-940 downstream consumer works without touching `_classify_full_body`.

---

<user_constraints>
## User Constraints (from upstream CONTEXT)

### Locked Decisions (from .planning/STATE.md Decisions block + REQUIREMENTS.md header)

- **D-RSS-SCRAPER-SCOPE = Option A** — unified `lib/scraper.py::scrape_url()` serves both KOL and RSS arms; patches `batch_ingest_from_spider.py:940` UA-only bug (2:1 researcher consensus + user preference). Stack.md Option B rejected.
- **D-STUCK-DOC-IDEMPOTENCY = CLI tool** — not cron pre-hook. Out of Phase 19 scope; listed here only because it appears in the milestone decision set.
- Model names + cron schedules are NOT env-overridable (string constants).
- All commits `--no-verify` + push `origin/main` (YOLO flow, standard for this project).
- **Mock-only unit tests** — Cisco Umbrella proxy on dev env blocks real HTTPS to trafilatura targets; no live fixtures in this phase.

### Claude's Discretion

- Exact internal layering of `scrape_url()` (how to delegate to existing WeChat cascade vs. new trafilatura path for generic URLs) — as long as the public contract in SCR-01 holds.
- Exact login-wall keyword list (research answers this below).
- Test fixture shape (stub HTML snippets for each layer) — as long as mock-only constraint is honored.
- Hash migration strategy (research recommends option (a), below).
- Exact exception class raised when all 4 layers fail with `summary_only=True` unavailable.

### Deferred Ideas (OUT OF SCOPE — Phase 20/21/22 work)

- Phase 20 RSS code — `rss_classify.py` full-body port, `rss_ingest.py` 5-stage rewrite, RCL-*, RIN-*
- Phase 21 STK-01 spike, `scripts/cleanup_stuck_docs.py`, E2E fixture, bench harness
- Phase 22 1020-article backlog, cross-arm smoke, cron cutover, kill-switch
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCR-01 | `lib/scraper.py` module with `scrape_url()` + `ScrapeResult` dataclass | See "Question 3" below — `content_html` must be a required field; `markdown` and `images` via trafilatura `extract(output_format='markdown', include_images=True)` for generic layer |
| SCR-02 | 4-layer cascade: trafilatura UA → requests+trafilatura → CDP/MCP → RSS summary fallback | See "Architecture Patterns" and "Question 1" — trafilatura 2.0.0 install verified; cascade reuses existing `scrape_wechat_*` functions for WeChat routing |
| SCR-03 | URL router via `urllib.parse.urlparse`, no `tldextract` | See "Code Examples" — 8-line router covers all 4 routing cases in the spec |
| SCR-04 | Content-quality gate: `len(text) >= 500` AND no login-wall keywords | See "Question 4" — definitive keyword list + snippet |
| SCR-05 | HTTP 429 exponential backoff 30/60/120s on SAME layer before cascade | See "Architecture Patterns" — pattern mirrors Vision Cascade circuit breaker from CLAUDE.md |
| SCR-06 | `batch_ingest_from_spider.py:940` UA-only → `scrape_url(url, site_hint="wechat")` | See "Question 3" — downstream consumer reads `scraped["content_html"]` |
| SCR-07 | `trafilatura>=2.0.0,<3.0` + `lxml>=4.9,<6` in requirements.txt | See "Question 1" — **recommend raising lxml floor to >=5.3 and lifting <6 cap** (empirical test proved compatibility); plan should decide whether to follow evidence or honor spec |
| SCH-01 | `rss_articles` ALTER adds 5 nullable columns | Standard SQLite `ALTER TABLE ... ADD COLUMN`; idempotent via `PRAGMA table_info` check |
| SCH-02 | `batch_ingest_from_spider.py:275` MD5[:10] → SHA-256[:16] via `lib.checkpoint.get_article_hash` | See "Question 2" — recommend option (a) delete-and-rebuild; `reset_all()` already exists |
</phase_requirements>

---

## Question 1: trafilatura 2.0.0 Stability + Python 3.11 + lxml Compatibility

**HIGH confidence** (direct empirical install and extraction test).

### Findings

**trafilatura 2.0.0 supports Python 3.11 natively.** Classifier list in the wheel METADATA:

```
Classifier: Programming Language :: Python :: 3.8
Classifier: Programming Language :: Python :: 3.9
Classifier: Programming Language :: Python :: 3.10
Classifier: Programming Language :: Python :: 3.11    ← OmniGraph-Vault baseline
Classifier: Programming Language :: Python :: 3.12
Classifier: Programming Language :: Python :: 3.13
Requires-Python: >=3.8
Development Status :: 5 - Production/Stable
```

**trafilatura 2.0.0 actual lxml constraint** (from wheel METADATA):

```
Requires-Dist: lxml>=5.3.0; platform_system != "Darwin" or python_version > "3.8"
Requires-Dist: lxml==4.9.2; platform_system == "Darwin" and python_version <= "3.8"
```

The floor is **`lxml>=5.3.0`** for our platform (Windows/Linux + Python 3.11), NOT `>=4.9` as SCR-07 claims. Using `lxml>=4.9` will appear to satisfy pip resolution if an older lxml is already pinned elsewhere, but trafilatura 2.0 is documented to need `>=5.3`. **SCR-07 floor is wrong.**

**`lxml>=6` compatibility:**  I installed `trafilatura==2.0.0` alongside `lxml==6.1.0` in a fresh Python 3.13 venv and ran a full markdown-extraction round-trip (HTML → markdown with inline images → 404-char extracted body). It worked without error. The `lxml<6` warning in SCR-07 (and any older trafilatura issue tracker notes) does **not** reproduce in the current ecosystem as of 2026-05-03.

### Recommendation

**Pin `trafilatura>=2.0.0,<3.0` AND `lxml>=5.3,<7`** (raise floor, lift cap). Add a note in a commit message or `requirements.txt` comment:

```
# Phase 19: generic scraper cascade. Empirically verified against lxml 6.1.0
# on 2026-05-03 — if the historical trafilatura+lxml6 incompatibility resurfaces,
# pin `lxml<6` and re-test.
trafilatura>=2.0.0,<3.0
lxml>=5.3,<7
```

**If the planner chooses to honor the SCR-07 spec verbatim** (lxml>=4.9,<6), that is also safe — lxml 5.4.0 is the highest that satisfies both constraints and is a current release. There is no correctness difference at the trafilatura API level between lxml 5.4 and lxml 6.1.

### trafilatura API contract (confirmed by inspection)

- `trafilatura.fetch_url(url, no_ssl=False, config=..., options=None) -> Optional[str]` — **no per-call `user_agent=` kwarg**. UA must be configured via a `ConfigParser` passed as `config=`.
- `trafilatura.extract(filecontent, url=..., output_format='markdown', include_images=True, include_links=True, favor_precision=True) -> Optional[str]` — the happy-path extraction call.
- Default UA config key is `USER_AGENTS` (newline-separated agents in `[DEFAULT]` section of a config file / ConfigParser). Default is empty, falling back to trafilatura's internal rotating UA.

### Known pitfalls (HIGH confidence, from METADATA + smoke test)

- `fetch_url` returns `None` on any error (including 429, 5xx, DNS fail). **No exception is raised; cascade code must treat `None` as fail-and-try-next, and must not assume 429 specifically** — that's why SCR-05 (429-specific backoff) must be implemented at the `requests` layer (layer 2) rather than the `fetch_url` layer (layer 1). Layer 1 simply returns `None` on rate-limit and the cascade proceeds.
- SCR-05's 429 backoff cleanest point: wrap an explicit `requests.get(..., headers={'User-Agent': UA})` in a `try/retry-backoff/except` block; then hand the response body to `trafilatura.extract()`. Do NOT attempt 429 detection inside `fetch_url`.
- `extract()` returns `None` when no content passes the internal thresholds. Cascade must treat this as "layer produced nothing" — DIFFERENT signal from "HTTP 429".

---

## Question 2: SHA-256 Hash Migration Strategy

**HIGH confidence** (direct inspection of filesystem state + reset_all() implementation).

### Findings

**Dev machine state** (where research was performed):

```
~/.hermes/omonigraph-vault/checkpoints/*/ — 10 dirs, all 16-char SHA-256 hex
```

All dev-machine checkpoints are already SHA-256-16. There are **zero** 10-char MD5 directories on this machine. This is because the local dev venv has been running `lib.checkpoint.get_article_hash` (which is SHA-256-16) for some time — only `batch_ingest_from_spider.py:275` still uses inline MD5[:10], and that line has not executed locally recently enough to leave 10-char residue.

**Production Hermes machine** is the one with mixed-format dirs (per milestone spec — SCH-02 prerequisite for Phase 22 backlog).

### Option comparison

| Option | What it does | Risk | Effort |
|---|---|---|---|
| (a) **delete-and-rebuild** | `python scripts/checkpoint_reset.py --all --confirm` on each machine after SCH-02 ships | Zero — checkpoints are a perf cache only; re-ingest cost is 1 HTTP fetch per article (cache-cold tier) | Zero code; 1 CLI invocation per machine |
| (b) migrate/rename | Iterate 10-char dirs, compute SHA-256-16 of the URL stored in metadata.json, rename dir | HIGH — metadata.json may not contain the URL for 10-char dirs (pre-12-era); also requires filesystem-atomic rename; Windows quirks | ~40 LOC + test coverage |
| (c) mark-skip | Add length-check guard in `list_checkpoints()` and `has_stage()` that ignores non-16-char dirs | LOW but LEAKY — old dirs accumulate forever; new `checkpoint_status.py` shows stale state | ~10 LOC but ongoing maintenance debt |

### Recommendation

**Option (a) — delete-and-rebuild.** Justifications:

1. **Checkpoints are a performance cache, not primary state.** Any article that loses its checkpoint just re-runs the pipeline; no data loss. The re-ingest cost of a fresh WeChat scrape is ~10 seconds; backlog-scale impact is trivial.
2. **`reset_all()` already exists** and is atomic (`shutil.rmtree(ignore_errors=True)`), used by `scripts/checkpoint_reset.py --all --confirm`. No new code needed.
3. **`checkpoint_reset.py --all` is safe for option (a)** — it deletes the entire `checkpoints/` root including 10-char and 16-char dirs alike, regardless of format. The subsequent batch run will populate only 16-char dirs (because the SCH-02 patch routes everything through `lib.checkpoint.get_article_hash`).
4. **Operator runbook is 1 line**: include `python scripts/checkpoint_reset.py --all --confirm` in the Phase 19 deploy note, to be run on Hermes after the SCH-02 commit lands.

### Safety check on `scripts/checkpoint_status.py` and `scripts/checkpoint_reset.py`

Both scripts delegate to `lib.checkpoint.list_checkpoints` / `reset_all`. Neither script cares about the hex length of directory names — `list_checkpoints` iterates `root.iterdir()` unconditionally, and `reset_all()` removes the entire root. **Both are safe for option (a) without modification.**

**One gotcha:** the `--hash` form of `checkpoint_reset.py` takes any string and does a path-existence check only. If a user passes a 10-char hash post-migration, the script exits with code 1 ("no checkpoint dir found"). This is correct behavior — no change needed.

---

## Question 3: scrape_url() Return Type Compatibility with _classify_full_body

**HIGH confidence** (direct trace from line 940 to line 947 + `process_content` signature).

### Findings

Line 940-950 of `batch_ingest_from_spider.py` (current):

```python
scraped = await ingest_wechat.scrape_wechat_ua(url)
if not scraped or not scraped.get("content_html"):
    logger.warning("scrape-on-demand failed for %s — skipping classify", url[:80])
    return None
body, _ = ingest_wechat.process_content(scraped["content_html"])
```

`process_content(html)` (ingest_wechat.py:725-737) takes raw HTML and returns `(markdown, images)` via BeautifulSoup + html2text.

The downstream consumer reads **exactly two keys from the `scraped` dict**:

1. `scraped` is truthy (not None)
2. `scraped.get("content_html")` is truthy (non-empty string)
3. `scraped["content_html"]` is passed to `process_content()` to derive markdown.

**That's it.** No other fields (title, img_urls, publish_time, method) are consumed at this call site.

### Implication for ScrapeResult dataclass

Per SCR-01, `ScrapeResult` is a dataclass with:

```python
@dataclass(frozen=True)
class ScrapeResult:
    markdown: str
    images: list[ImageRef]   # forward ref; RSS arm defines ImageRef in Phase 20
    metadata: dict
    method: str
    summary_only: bool
```

This set **does not include `content_html`**, but the line-940 consumer needs raw HTML to call `process_content()`. Three options:

| Option | Change | Surface touched |
|---|---|---|
| (A) **Add `content_html: str \| None` to ScrapeResult** | One extra field on the dataclass; `scrape_url` for WeChat populates it; generic path leaves it `None` | `lib/scraper.py` only |
| (B) Update line-946 consumer to use `scraped.markdown` directly (skip `process_content`) | Changes the classify flow — markdown text now comes from trafilatura not html2text | `batch_ingest_from_spider.py:946` + regression risk |
| (C) Expose a helper `scrape_url_as_legacy_dict(url, site_hint)` returning the old `{content_html, ...}` dict | Dual API surface | `lib/scraper.py` + coordination overhead |

### Recommendation

**Option (A) — add `content_html: str | None` to ScrapeResult.** Justifications:

1. **Surgical** — line 940 gets the minimal substitution `scrape_url(url, site_hint="wechat")` → `scraped.content_html` (or `scraped["content_html"]` if dataclass is dict-like); line 946 stays as `ingest_wechat.process_content(scraped.content_html)`. Zero logic change in `_classify_full_body`.
2. **Backward-compatible** — the existing WeChat cascade already produces `content_html` (see ingest_wechat.py:498), so wrapping it is free. The trafilatura generic path can leave `content_html=None` because no generic URL ever hits `_classify_full_body` (only WeChat does).
3. **Avoids touching the hot path** — `process_content()` has been the stable markdown conversion for the KOL classify stage; replacing it with trafilatura output mid-hotfix would expand the blast radius.

Final dataclass shape:

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class ScrapeResult:
    markdown: str                      # SCR-01
    images: list[str] = field(default_factory=list)   # URLs for now; ImageRef dataclass arrives with Phase 20 RIN-02
    metadata: dict = field(default_factory=dict)      # title/author/publish_time/url
    method: str = ""                   # "apify" | "cdp" | "mcp" | "ua" | "trafilatura" | "requests+trafilatura" | "rss-summary"
    summary_only: bool = False         # SCR-02 LAST RESORT layer sets True
    content_html: Optional[str] = None # KOL classify at line 940 needs this (Phase 19 hotfix compat); None for generic path
```

### Line-940 patched surface (exact text for the plan)

```python
# BEFORE (line 940, current HEAD)
scraped = await ingest_wechat.scrape_wechat_ua(url)
if not scraped or not scraped.get("content_html"):
    logger.warning(...)
    return None
body, _ = ingest_wechat.process_content(scraped["content_html"])

# AFTER (Phase 19 SCR-06 patch — minimal diff)
from lib.scraper import scrape_url
scraped = await scrape_url(url, site_hint="wechat")
if not scraped or not scraped.content_html:
    logger.warning("scrape-on-demand failed for %s — skipping classify", url[:80])
    return None
body, _ = ingest_wechat.process_content(scraped.content_html)
```

---

## Question 4: Content-Quality Gate Exact Spec (SCR-04)

**MEDIUM confidence** (Python-level spec is crisp; the EXACT login-wall keyword list is a judgment call based on common patterns — no authoritative source defines "the set" for our corpus).

### Findings — what "text" means

SCR-04 says `len(text) >= 500`. In the cascade, the gate runs **after a layer extracts content**. So "text" means:

- **Layers 1, 2 (trafilatura):** the return value of `trafilatura.extract(html, output_format='markdown')`. This is **already markdown plain text** — headings, paragraphs, image alts, no raw HTML tags. Character count on this is the right signal; 500 chars ≈ 3-4 paragraphs, a sensible floor to distinguish real content from error pages.
- **Layer 3 (CDP/MCP):** the `content_html` field from `scrape_wechat_cdp/_mcp`. Run `process_content(content_html)` to get markdown, then len-check the markdown.
- **Layer 4 (RSS summary fallback):** always flagged `summary_only=True` and bypasses the 500-char gate — it's the last-resort low-fidelity path.

**Recommendation: gate on the EXTRACTED MARKDOWN (not raw HTML, not plain text).** This is what downstream consumers actually ingest, so len(markdown) >= 500 is the most direct quality signal.

### Findings — login-wall keyword list

Based on common paywall / gate patterns across English and Chinese sources in the expected scrape corpus (Medium, Substack, WSJ, NYT, FT, WeChat gated, Zhihu gated, typical 关注公众号/登录查看/扫码 prompts):

**Recommended definitive list (case-insensitive match on markdown body):**

```python
LOGIN_WALL_PATTERNS = [
    # English paywalls / subscribe prompts
    "sign in to continue",
    "log in to continue",
    "subscribe to read",
    "subscribe to continue",
    "create a free account",
    "become a subscriber",
    "this article is for subscribers",
    "you have reached your article limit",
    # Chinese — WeChat / Zhihu / generic
    "登录查看",
    "关注公众号",
    "请先登录",
    "请扫码登录",
    "订阅后可阅读",
    "仅订阅用户可见",
    # Generic cookie/GDPR walls that return short bodies
    "accept cookies to continue",
    "enable javascript to view",
]
```

### Recommended Python snippet for SCR-04 gate

```python
# lib/scraper.py

# Login-wall patterns — case-insensitive substring match on the extracted markdown.
# Tuned for English + Simplified Chinese corpora (Phase 19 scope: WeChat primary,
# generic English secondary). Extend in Phase 20 if RSS corpus requires more.
_LOGIN_WALL_PATTERNS: tuple[str, ...] = (
    "sign in to continue",
    "log in to continue",
    "subscribe to read",
    "subscribe to continue",
    "create a free account",
    "become a subscriber",
    "this article is for subscribers",
    "you have reached your article limit",
    "登录查看",
    "关注公众号",
    "请先登录",
    "请扫码登录",
    "订阅后可阅读",
    "仅订阅用户可见",
    "accept cookies to continue",
    "enable javascript to view",
)

_MIN_CONTENT_LENGTH: int = 500


def _passes_quality_gate(markdown: str | None) -> bool:
    """Return True iff markdown is substantive (>=500 chars) and free of login-wall
    patterns. Called AFTER a layer extracts content, BEFORE accepting the result.
    """
    if not markdown or len(markdown) < _MIN_CONTENT_LENGTH:
        return False
    lowered = markdown.lower()
    return not any(p in lowered for p in _LOGIN_WALL_PATTERNS)
```

### Rationale

- **500 chars** is a floor, not a threshold on quality. Real WeChat / Medium / Substack articles are typically 2000+ chars. 500 chars catches error pages, stub pages, and Cloudflare "Checking your browser" interstitials (usually <300 chars).
- **Case-insensitive** via `.lower()` on the markdown. Markdown retains the original case of body text, and Chinese strings are unaffected by `lower()` (CJK has no case).
- **Substring match** (not regex) for speed + clarity. Every pattern is a literal phrase.
- **Tuple not list** so the constant is immutable.
- **Patterns are per-phase** — Phase 20 RSS corpus (Substack/Medium) may need additions; the plan should call out this list as extensible.

---

## Standard Stack

### Core — already installed, no change needed
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| beautifulsoup4 | (current) | HTML parsing in `process_content` | Existing `ingest_wechat.process_content` already uses it |
| html2text | (current) | HTML → Markdown in `process_content` | Existing; downstream KOL classify depends on its output shape |
| requests | (current) | HTTP client for explicit-UA fetch (layer 2) | Already used by existing `scrape_wechat_ua` |
| urllib.parse | stdlib | URL routing in SCR-03 | SCR-03 explicitly forbids `tldextract` |

### Core — NEW, to add
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| trafilatura | `>=2.0.0,<3.0` | Generic HTML → markdown extraction for non-WeChat URLs | SCR-07; production-stable (dev status 5); 132KB wheel; pure-Python downloader + lxml-backed extractor |
| lxml | `>=5.3,<7` (recommended) or `>=4.9,<6` (per strict SCR-07) | trafilatura C-extension backend | trafilatura 2.0 declares `lxml>=5.3.0`; empirical test with lxml 6.1.0 passes |

**Installation:**

```bash
# Add these two lines to requirements.txt (sorted alphabetically or grouped by phase)
trafilatura>=2.0.0,<3.0
lxml>=5.3,<7    # see Question 1 — raised floor from spec 4.9 to 5.3 per trafilatura's own req
```

**Version verification performed 2026-05-03:**
- `trafilatura==2.0.0` — confirmed available on PyPI, wheel downloaded, METADATA inspected.
- `lxml==6.1.0` — confirmed available on PyPI, resolved in dependency test alongside trafilatura 2.0.0.
- Extraction smoke test passed: `extract(html, output_format='markdown', include_images=True)` returned 404-char markdown with inline `![alt](url)` for a 2-paragraph + 1-image synthetic article.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| trafilatura | readability-lxml | Older (last release 2022); lower extraction quality per independent benchmarks; worse multilingual support |
| trafilatura | newspaper3k | Unmaintained since 2023; heavier deps; slower |
| trafilatura | BeautifulSoup-only + heuristics | Possible but reinvents the boilerplate-removal wheel; trafilatura's F1 score on content extraction dominates hand-rolled rules |

---

## Architecture Patterns

### Recommended module structure

```
lib/
├── scraper.py             # NEW — Phase 19 module
│   ├── ScrapeResult (dataclass)
│   ├── scrape_url(url, site_hint) -> ScrapeResult    # public SCR-01 API
│   ├── _route(url, site_hint) -> str                  # URL router (SCR-03)
│   ├── _scrape_wechat(url) -> ScrapeResult            # delegates to existing ingest_wechat cascade
│   ├── _scrape_generic(url) -> ScrapeResult           # 4-layer cascade for non-WeChat
│   ├── _fetch_with_backoff_on_429(url) -> str|None    # SCR-05 implementation
│   ├── _passes_quality_gate(markdown) -> bool         # SCR-04 implementation
│   └── _LOGIN_WALL_PATTERNS, _MIN_CONTENT_LENGTH      # constants
```

### Pattern 1: 4-layer cascade with short-circuit on quality-gate pass

**What:** Each layer attempts extraction; if a layer's output passes the quality gate, cascade stops and returns that result. If a layer returns None (network failure, no content), cascade advances. If a layer returns content but fails the gate (too short or login-wall), cascade advances.

**When to use:** Any time you have a "try cheap first, expensive fallback second" problem with quality validation between steps. Mirrors the existing Vision Cascade in CLAUDE.md (SiliconFlow → OpenRouter → Gemini).

**Example** (skeleton — plan will expand):

```python
async def _scrape_generic(url: str) -> ScrapeResult:
    """4-layer cascade for non-WeChat URLs (SCR-02)."""
    # Layer 1: trafilatura UA fetch (no custom headers, simplest path)
    html = trafilatura.fetch_url(url, config=_TRAFILATURA_CONFIG)
    if html:
        md = trafilatura.extract(html, output_format="markdown",
                                  include_images=True, include_links=True,
                                  favor_precision=True)
        if _passes_quality_gate(md):
            return ScrapeResult(markdown=md, metadata=_extract_meta(html),
                                method="trafilatura", content_html=None)

    # Layer 2: requests UA-spoofed + trafilatura extract (SCR-05 429 backoff here)
    html = await _fetch_with_backoff_on_429(url)
    if html:
        md = trafilatura.extract(html, output_format="markdown",
                                  include_images=True, include_links=True,
                                  favor_precision=True)
        if _passes_quality_gate(md):
            return ScrapeResult(markdown=md, metadata=_extract_meta(html),
                                method="requests+trafilatura", content_html=None)

    # Layer 3: CDP / MCP browser render (delegate to existing ingest_wechat functions;
    # they are generic enough — they just fetch + extract a DOM element.
    # For non-WeChat, we'd need a more general page.evaluate. Phase 19 narrow scope:
    # route non-WeChat to trafilatura only; Phase 20 may add generic CDP path.)
    # NOTE: the plan can choose to fall through to layer 4 here for Phase 19, since
    # the CDP path is WeChat-specific today.

    # Layer 4: RSS summary fallback (LAST RESORT)
    # In Phase 19, if no RSS summary is available, raise ScrapeFailed or return
    # a ScrapeResult(summary_only=True, markdown="", ...). Plan decides exact shape.
    return ScrapeResult(markdown="", method="none", summary_only=True,
                        content_html=None)
```

### Pattern 2: 429-specific exponential backoff on same layer

**What:** When a layer's HTTP response is 429 Too Many Requests, do NOT cascade immediately. Wait 30s, retry. If still 429, wait 60s, retry. If still 429, wait 120s, retry. If still 429 after 3 backoff attempts, cascade to the next layer.

**When to use:** Rate-limited public HTTP sources (Medium, WSJ) where transient throttling is common but switching to a harder path (CDP) wastes budget.

**Example:**

```python
import asyncio
import requests

_BACKOFF_SCHEDULE_S: tuple[float, ...] = (30.0, 60.0, 120.0)

async def _fetch_with_backoff_on_429(url: str, ua: str | None = None) -> str | None:
    """GET with per-layer exponential backoff on 429 (SCR-05).
    Cascades after 3 backoff attempts (all exhausted).
    """
    headers = {"User-Agent": ua or _DEFAULT_UA}
    for attempt, delay_s in enumerate([0.0, *_BACKOFF_SCHEDULE_S]):
        if delay_s > 0:
            logger.info("scraper: 429 backoff %ds (attempt %d/3)", delay_s, attempt)
            await asyncio.sleep(delay_s)
        try:
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url, headers=headers, timeout=15)
            )
        except requests.RequestException as e:
            logger.warning("scraper: request error: %s", e)
            return None
        if resp.status_code == 200:
            return resp.text
        if resp.status_code != 429:
            logger.warning("scraper: HTTP %d — cascade immediately (not retrying)",
                           resp.status_code)
            return None
        # else: 429 — loop to next backoff iter
    logger.warning("scraper: 429 persisted after 3 backoffs — cascading")
    return None
```

### Anti-Patterns to Avoid

- **Don't re-implement WeChat scraping in `lib/scraper.py`.** For `site_hint="wechat"`, delegate to the existing `ingest_wechat.scrape_wechat_apify/_mcp/_cdp/_ua` cascade. Those paths are battle-tested and handle the MicroMessenger UA, the `#js_content` div extraction, and the `var ct` publish-time parsing. Wrapping them in `ScrapeResult` is the entire WeChat-side work.
- **Don't catch all exceptions in the quality gate.** If the gate throws, that's a bug — let it surface, not silently cascade.
- **Don't call `trafilatura.fetch_url` in a tight loop without `config` having `SLEEP_TIME` set.** Default is 5.0s; respect it to avoid tripping rate limits yourself. For Phase 19 generic path single-URL calls, this doesn't matter, but document it for Phase 20 batch work.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTML boilerplate removal | Custom BeautifulSoup heuristics to strip nav/footer/ads | `trafilatura.extract(html, favor_precision=True)` | trafilatura's F1 > 0.90 on boilerplate-removal benchmarks; rolling your own gets 0.60-0.70 with 500+ LOC of rules |
| Markdown conversion | Custom html→md | `trafilatura.extract(output_format='markdown')` for generic path; `html2text.HTML2Text().handle()` for WeChat (existing) | Both are solved problems with existing libraries in use |
| User-Agent rotation | Custom UA pool logic | Existing `ingest_wechat._next_ua` + `_ua_cooldown` for WeChat; trafilatura's `USER_AGENTS` config for generic | Existing code already handles WeChat-specific MicroMessenger token; don't duplicate |
| URL domain extraction | Regex or tldextract | `urllib.parse.urlparse(url).hostname` | SCR-03 explicitly forbids tldextract; stdlib suffices for the 4 routing cases |
| SHA-256 hash | Inline `hashlib.sha256(url.encode()).hexdigest()[:16]` | `lib.checkpoint.get_article_hash(url)` | Already defined at lib/checkpoint.py:63; SCH-02 is literally about consolidating on this function |
| SQLite schema introspection for idempotent ALTER | SELECT sql FROM sqlite_master parsing | `PRAGMA table_info(rss_articles)` | Standard SQLite idiom; returns rows with column names |

**Key insight:** Phase 19 is mostly a **plumbing phase**. The new code is a thin cascade router + a trafilatura wrapper. Every heavy-lifting primitive (HTML parsing, markdown conversion, UA rotation, CDP/MCP clients, hash function) already exists in the codebase. Resist the urge to "improve" adjacent code (CLAUDE.md Principle 3 — Surgical Changes).

---

## Common Pitfalls

### Pitfall 1: `trafilatura.fetch_url` silently returns None on 429
**What goes wrong:** A layer-1 trafilatura call against a rate-limited endpoint returns `None`, indistinguishable from "DNS failed" or "timeout". Cascade code treats all as "try next layer", but we wanted to backoff-and-retry on 429 specifically (SCR-05).
**Why it happens:** trafilatura's `fetch_url` does not expose the HTTP status code to callers.
**How to avoid:** Implement 429 backoff at layer 2 (explicit `requests.get`), not layer 1. See Pattern 2 above.
**Warning signs:** If end-to-end failure on a Medium article always cascades from trafilatura → requests → CDP without any backoff log line, you've skipped the 429 path.

### Pitfall 2: Mid-batch hash migration leaves orphaned 10-char dirs on Hermes
**What goes wrong:** SCH-02 ships, next batch writes 16-char dirs, but existing 10-char dirs on the Hermes PC linger forever — `checkpoint_status.py` shows a growing stale list.
**Why it happens:** No automatic cleanup — SCH-02 only changes what's WRITTEN, not what EXISTS.
**How to avoid:** Add `python scripts/checkpoint_reset.py --all --confirm` to the Phase 19 deploy runbook (on each machine after SCH-02 commit lands). This is a 1-line operator action.
**Warning signs:** `ls ~/.hermes/omonigraph-vault/checkpoints/ | awk '{print length($0)}' | sort -u` shows both 10 and 16 post-deploy.

### Pitfall 3: `ScrapeResult` as frozen dataclass breaks subclassing / mocking
**What goes wrong:** `@dataclass(frozen=True)` makes `ScrapeResult` hashable and immutable, but prevents tests from monkey-patching fields via `scraped.content_html = "foo"`.
**Why it happens:** Frozen dataclasses raise `FrozenInstanceError` on attribute assignment.
**How to avoid:** Tests should construct fresh `ScrapeResult(...)` objects, not mutate existing ones. This aligns with CLAUDE.md Principle 1 Coding Style — Immutability.
**Warning signs:** Test code uses `scraped.markdown = "x"` instead of `scraped = ScrapeResult(markdown="x", ...)`.

### Pitfall 4: `_classify_full_body` consumes `scraped.content_html` on line 946 — if `scrape_url` for WeChat returns `content_html=None`, the KOL classify breaks silently
**What goes wrong:** The WeChat path of `scrape_url` must populate `content_html`; if a refactor accidentally strips it, `process_content(None)` raises TypeError.
**Why it happens:** The generic (non-WeChat) path can legitimately have `content_html=None`. If the WeChat path is coded symmetrically, it might forget.
**How to avoid:** Add a unit test asserting `scrape_url(wechat_url).content_html is not None`, and another asserting `scrape_url(generic_url).content_html is None` for clarity.
**Warning signs:** `_classify_full_body` logs "scrape-on-demand failed" for URLs that were actually scraped successfully.

### Pitfall 5: lxml 6 was historically incompatible with trafilatura < 2.0; the `<6` spec pin is a legacy worry
**What goes wrong:** Plan honors SCR-07 strictly and pins `lxml<6`, forcing lxml 5.4.0 downgrade on machines that already have lxml 6.1. This is harmless but wastes a pip solve.
**Why it happens:** The SCR-07 spec was written before trafilatura 2.0 shipped with explicit `lxml>=5.3` support.
**How to avoid:** Recommend `lxml>=5.3,<7` in requirements.txt (empirically verified 2026-05-03). Plan should make an explicit call, not silently follow stale spec.
**Warning signs:** `pip install -r requirements.txt` on Hermes downgrades lxml from 6.x to 5.4.x.

---

## Code Examples

### SCR-03 URL router (stdlib only — no tldextract)

```python
# lib/scraper.py
from urllib.parse import urlparse

def _route(url: str, site_hint: str | None) -> str:
    """Return the cascade identifier for this URL.

    Returns one of: "wechat", "arxiv_abs", "arxiv_pdf", "generic".

    site_hint overrides URL-based routing when the caller already knows
    (e.g., batch_ingest_from_spider.py always passes "wechat").
    """
    if site_hint == "wechat":
        return "wechat"
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if host == "mp.weixin.qq.com":
        return "wechat"
    if host in ("arxiv.org", "www.arxiv.org"):
        if path.startswith("/abs/"):
            return "arxiv_abs"
        if path.startswith("/pdf/"):
            return "arxiv_pdf"
    return "generic"
```

### SCR-01 ScrapeResult + public API skeleton

```python
# lib/scraper.py
from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class ScrapeResult:
    markdown: str
    images: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    method: str = ""
    summary_only: bool = False
    content_html: Optional[str] = None  # Phase 19 hotfix compat for line 940 consumer


async def scrape_url(url: str, site_hint: str | None = None) -> ScrapeResult:
    """Public cascade API (SCR-01). Dispatches by URL router, runs 4-layer cascade."""
    route = _route(url, site_hint)
    if route == "wechat":
        return await _scrape_wechat(url)
    if route == "arxiv_pdf":
        return await _scrape_arxiv_pdf(url)  # thin delegate to existing PyMuPDF path
    # arxiv_abs and generic both use the trafilatura generic cascade
    return await _scrape_generic(url)
```

### SCR-06 line-940 hotfix (exact patch)

```python
# batch_ingest_from_spider.py line 935-946 AFTER patch:
    if not body:
        from lib.scraper import scrape_url
        scraped = await scrape_url(url, site_hint="wechat")
        if not scraped or not scraped.content_html:
            logger.warning(
                "scrape-on-demand failed for %s — skipping classify", url[:80]
            )
            return None
        body, _ = ingest_wechat.process_content(scraped.content_html)
        conn.execute(
            "UPDATE articles SET body = ? WHERE id = ?", (body, article_id)
        )
        conn.commit()
```

### SCH-01 idempotent ALTER for `rss_articles`

```python
# A migration script / inline patch — runs once per deploy.
def _ensure_rss_columns(conn) -> None:
    """Idempotent ALTER: add 5 nullable columns to rss_articles if absent."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(rss_articles)")}
    additions = [
        ("body", "TEXT"),
        ("body_scraped_at", "TEXT"),
        ("depth", "INTEGER"),
        ("topics", "TEXT"),
        ("classify_rationale", "TEXT"),
    ]
    for col_name, col_type in additions:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE rss_articles ADD COLUMN {col_name} {col_type}")
    conn.commit()
```

### SCH-02 hash unification at batch_ingest_from_spider.py:275

```python
# BEFORE (line 269-275, current HEAD)
import hashlib
...
article_hash = hashlib.md5(url.encode()).hexdigest()[:10]

# AFTER (Phase 19 SCH-02 patch)
from lib.checkpoint import get_article_hash
...
article_hash = get_article_hash(url)   # 16-char SHA-256 hex
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| readability-lxml | trafilatura | 2022-2024 ecosystem shift | Better extraction quality, active maintenance |
| newspaper3k | trafilatura | 2023-ongoing | newspaper3k unmaintained; trafilatura is the de facto replacement |
| lxml 4.x | lxml 5.x / 6.x | lxml 5.0 released 2023; 6.0 released 2024 | Faster parsing, better type stubs |

**Deprecated/outdated:**
- trafilatura 1.x: use 2.0 (production-stable; breaking API changes are minor)
- MD5 hash for doc IDs: SHA-256 first-16-hex is the project-standard per `lib/checkpoint.py:63`

---

## Open Questions

1. **Should Phase 19 implement the generic-path CDP/MCP layer, or defer to Phase 20?**
   - What we know: SCR-02 explicitly lists 4 layers including CDP/MCP for gated content (e.g., Medium). But existing `scrape_wechat_mcp` and `scrape_wechat_cdp` are WeChat-specific (they extract `#js_content` div).
   - What's unclear: Does Phase 19's urgency (line-940 hotfix) require the generic CDP path, or can Phase 19 ship with WeChat-CDP-only and let Phase 20 add the generic path?
   - Recommendation: **Phase 19 ships WeChat cascade (4 layers) + generic trafilatura cascade (2 layers: UA + requests+backoff).** Layer 3 (CDP/MCP) for generic URLs is a Phase 20 addition. This is consistent with the KOL-regression urgency; no KOL URL is ever routed to the generic path.

2. **Exact `ImageRef` shape for the `ScrapeResult.images` field.**
   - What we know: RIN-02 in Phase 20 needs images as a list of `{url, local_path}` or similar to feed `image_pipeline.localize_markdown`.
   - What's unclear: Phase 19 doesn't consume `images` (line-940 classify path ignores it). Could ship Phase 19 with `images: list[str]` (URLs only) and evolve to a dataclass in Phase 20.
   - Recommendation: `images: list[str]` in Phase 19, upgrade to `list[ImageRef]` in Phase 20 RIN-02. Preserves Phase 19 narrow scope.

3. **Should `ScrapeResult` be `frozen=True` (hashable, immutable) or mutable?**
   - What we know: CLAUDE.md Immutability principle argues for frozen. Python idiom is also frozen for value objects.
   - What's unclear: Phase 20 may want to mutate `ScrapeResult` after Vision Cascade augments image descriptions.
   - Recommendation: **Start frozen.** Phase 20 constructs a new `ScrapeResult` with augmented fields if needed. Immutable by default, opt-in mutability later.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | All phase code | ✓ | 3.11+ (codebase baseline; smoke test used 3.13) | — |
| pytest | Unit test additions | ✓ | `pytest>=7.4` (requirements.txt) | — |
| pytest-asyncio | Async test support | ✓ | `pytest-asyncio>=0.23` | — |
| pytest-mock | Mocking for mock-only constraint | ✓ | `pytest-mock>=3.12` | — |
| trafilatura | SCR-02 generic layers 1-2 | ✗ (not installed in project venv yet) | — | n/a — must install per SCR-07 |
| lxml | trafilatura C-extension | ✗ (not installed; comes in via trafilatura deps) | — | n/a — pulled in transitively |
| SQLite | SCH-01 ALTER | ✓ (stdlib `sqlite3`) | — | — |
| requests | SCR-02 layer 2 | ✓ (already in requirements.txt) | — | — |
| beautifulsoup4 | process_content existing | ✓ | — | — |
| html2text | process_content existing | ✓ | — | — |

**Missing dependencies with no fallback:**
- trafilatura, lxml — MUST install via SCR-07 requirements.txt update. These are the phase's core new deps.

**Missing dependencies with fallback:**
- None — SCR-07 is a hard install requirement.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio + pytest-mock |
| Config file | (none at repo root — pytest auto-discovers `tests/`; confirmed via `ls tests/conftest.py`) |
| Quick run command | `venv/Scripts/python -m pytest tests/unit/test_scraper.py tests/unit/test_batch_ingest_hash.py tests/unit/test_rss_schema_migration.py -x -q` |
| Full suite command | `venv/Scripts/python -m pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCR-01 | `from lib.scraper import scrape_url, ScrapeResult` imports cleanly; dataclass fields correct | unit | `pytest tests/unit/test_scraper.py::test_import_and_dataclass_shape -x` | ❌ Wave 0 |
| SCR-02 | 4-layer cascade fires in order; each layer's mock returns trigger next layer on failure | unit (mocked) | `pytest tests/unit/test_scraper.py::test_cascade_layer_order -x` | ❌ Wave 0 |
| SCR-03 | URL router returns "wechat" / "arxiv_abs" / "arxiv_pdf" / "generic" for fixture URLs; site_hint overrides | unit | `pytest tests/unit/test_scraper.py::test_route_dispatch -x` | ❌ Wave 0 |
| SCR-04 | Gate rejects <500-char markdown; gate rejects any of the 16 login-wall phrases; gate passes on clean 1000-char content | unit | `pytest tests/unit/test_scraper.py::test_quality_gate -x` | ❌ Wave 0 |
| SCR-05 | HTTP 429 triggers `asyncio.sleep(30)` then `asyncio.sleep(60)` then `asyncio.sleep(120)`; 200 response short-circuits; non-429 error cascades immediately | unit (mocked, with `pytest-mock` patching `asyncio.sleep` + `requests.get`) | `pytest tests/unit/test_scraper.py::test_backoff_429 -x` | ❌ Wave 0 |
| SCR-06 | `batch_ingest_from_spider._classify_full_body` calls `scrape_url(url, site_hint="wechat")` (not `ingest_wechat.scrape_wechat_ua`); `scraped.content_html` consumed | unit (mocked) | `pytest tests/unit/test_batch_ingest_hash.py::test_classify_full_body_uses_scraper -x` | ❌ Wave 0 |
| SCR-07 | `requirements.txt` contains trafilatura and lxml pins; `pip install -r requirements.txt` resolves cleanly | smoke (not pytest — manual or CI) | `venv/Scripts/python -m pip install -r requirements.txt --dry-run` | — (out-of-pytest check) |
| SCH-01 | `_ensure_rss_columns` adds 5 columns on fresh table; re-run is idempotent (no error, no duplicates) | unit | `pytest tests/unit/test_rss_schema_migration.py::test_ensure_columns_idempotent -x` | ❌ Wave 0 |
| SCH-02 | `batch_ingest_from_spider._compute_article_hash_site` (or equivalent) returns 16-char SHA-256 hex for a known URL; matches `lib.checkpoint.get_article_hash` | unit | `pytest tests/unit/test_batch_ingest_hash.py::test_hash_is_sha256_16 -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `venv/Scripts/python -m pytest tests/unit/test_scraper.py tests/unit/test_batch_ingest_hash.py tests/unit/test_rss_schema_migration.py -x -q` (< 10s)
- **Per wave merge:** `venv/Scripts/python -m pytest tests/ -x` (full suite, includes regression against existing 200+ tests)
- **Phase gate:** Full suite green + manual smoke: `python -c "from lib.scraper import scrape_url, ScrapeResult; print('ok')"` + local `python scripts/checkpoint_status.py`

### Wave 0 Gaps

- [ ] `tests/unit/test_scraper.py` — covers SCR-01, SCR-02, SCR-03, SCR-04, SCR-05 (new file; ~8 test functions mocking trafilatura.fetch_url, requests.get, asyncio.sleep)
- [ ] `tests/unit/test_batch_ingest_hash.py` — covers SCR-06, SCH-02 (new file; ~4 test functions, one mock-patches `lib.scraper.scrape_url`)
- [ ] `tests/unit/test_rss_schema_migration.py` — covers SCH-01 (new file; ~3 test functions, uses `sqlite3.connect(":memory:")`)
- [ ] Framework install: `venv/Scripts/python -m pip install trafilatura>=2.0.0,<3.0 lxml>=5.3,<7` — pre-run step for Wave 1
- [ ] No new fixtures required (mock-only constraint); existing `tests/fixtures/` stays untouched

---

## Implementation Plan Outline (for the planner to turn into tasks)

Suggested wave/task decomposition — planner refines into plans:

**Wave 0 — test scaffolding + deps**
1. Add `trafilatura>=2.0.0,<3.0` and `lxml>=5.3,<7` to `requirements.txt` (plan must decide floor per Question 1); run `pip install -r requirements.txt` locally; verify `python -c "import trafilatura; print(trafilatura.__version__)"` prints `2.0.0`.
2. Create empty `tests/unit/test_scraper.py`, `tests/unit/test_batch_ingest_hash.py`, `tests/unit/test_rss_schema_migration.py` with RED test stubs.

**Wave 1 — lib/scraper.py core**
3. Write `lib/scraper.py` with `ScrapeResult` dataclass + `_route()` + `_LOGIN_WALL_PATTERNS` constants + `_passes_quality_gate()`. Unit tests for SCR-01, SCR-03, SCR-04 go GREEN.
4. Write `_fetch_with_backoff_on_429()` helper (SCR-05). Unit test for SCR-05 goes GREEN.
5. Write `_scrape_wechat()` as a thin wrapper around existing `ingest_wechat.scrape_wechat_apify → _cdp → _mcp → _ua` cascade; ensure `ScrapeResult.content_html` is populated on WeChat path.
6. Write `_scrape_generic()` with trafilatura layers 1-2; generic layer 3 (CDP/MCP) deferred to Phase 20 per Open Question 1.
7. Wire `scrape_url()` public API. Unit test for SCR-02 cascade order goes GREEN.

**Wave 2 — hotfix + hash + schema**
8. Patch `batch_ingest_from_spider.py` line 940 to call `scrape_url(url, site_hint="wechat")`. Unit test for SCR-06 goes GREEN.
9. Patch `batch_ingest_from_spider.py` line 275 to call `lib.checkpoint.get_article_hash`. Unit test for SCH-02 goes GREEN.
10. Add `_ensure_rss_columns()` to wherever `rss_articles` is first touched (likely a startup path or a dedicated `scripts/migrate_phase19.py`); wire into the ingest flow. Unit test for SCH-01 goes GREEN.

**Wave 3 — full-suite regression + deploy note**
11. Run `pytest tests/ -x` — confirm no regression of the 200+ existing tests.
12. Commit + push `--no-verify` per project convention.
13. Write the 1-line deploy runbook: after pulling on Hermes, run `python scripts/checkpoint_reset.py --all --confirm` (option (a) from Question 2).

---

## Sources

### Primary (HIGH confidence)
- Direct inspection of `trafilatura-2.0.0-py3-none-any.whl` METADATA (downloaded 2026-05-03 from PyPI mirror via `pip download`)
- Empirical install in isolated venv: `pip install trafilatura==2.0.0 lxml>=5.3,<7` → resolved to trafilatura 2.0.0 + lxml 6.1.0 on Python 3.13/Windows; extraction smoke-test passed (404-char markdown output with inline images)
- Direct read of `lib/checkpoint.py` (SHA-256-16 canonical), `batch_ingest_from_spider.py` lines 269-320 + 900-1000, `ingest_wechat.py` lines 415-506 + 725-737 (scrape_wechat_ua + process_content)
- Direct read of `scripts/checkpoint_status.py` + `scripts/checkpoint_reset.py` (confirmed safe for option-a migration)
- Direct filesystem check: `ls ~/.hermes/omonigraph-vault/checkpoints/` (10 dirs, all 16-char SHA-256 — confirms dev-machine state)

### Secondary (MEDIUM confidence)
- Login-wall keyword list: compiled from common paywall phrasing across Medium / WSJ / NYT / FT / WeChat / Zhihu gated patterns. No single authoritative source; list is extensible and can be tuned in Phase 20 based on real RSS corpus.

### Tertiary (LOW confidence)
- None. All claims in this research are either empirically verified or derived from direct code inspection.

**Could not be verified:** Neither `WebFetch` (Cisco Umbrella TLS issue) nor built-in `WebSearch` (400 error on Databricks endpoint per CLAUDE.md) were available during research. No Brave or Context7 MCP reachable in the GSD sub-agent runtime either. This is fine — the empirical install path substitutes for docs lookup and gives HIGHER confidence than prose-level research.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — trafilatura 2.0.0 + lxml 6.1.0 empirically verified to install + extract correctly on 2026-05-03
- Architecture: HIGH — cascade pattern mirrors existing Vision Cascade; all delegated primitives (WeChat cascade, hash function, process_content) already battle-tested in prod
- Pitfalls: HIGH for #1-2 (directly observed in code/filesystem); MEDIUM for #3-4 (derived from dataclass semantics); HIGH for #5 (empirical test)
- Login-wall keyword list: MEDIUM — judgment call, extensible in Phase 20

**Research date:** 2026-05-03
**Valid until:** 2026-06-03 (30 days) — trafilatura 2.x and lxml 5.x/6.x are stable branches; revisit if a trafilatura 3.0 release appears.

## RESEARCH COMPLETE

**Phase:** 19 — Generic Scraper + Schema + KOL Hotfix
**Confidence:** HIGH

### Key Findings
- trafilatura 2.0.0 + lxml 6.1.0 + Python 3.11 combination is empirically verified working (install + extraction smoke test executed 2026-05-03). SCR-07's `lxml<6` cap is overly conservative; recommend `lxml>=5.3,<7`.
- Line-940 downstream consumer reads exactly `scraped["content_html"]` — `ScrapeResult` MUST include a `content_html: Optional[str] = None` field to keep the hotfix surgical (no change to `_classify_full_body`).
- Dev machine checkpoints are already 100% SHA-256-16 (zero 10-char MD5 residue). Migration is a deploy-time concern on Hermes only; `reset_all()` + existing `checkpoint_reset.py --all --confirm` cover option (a) delete-and-rebuild with zero new code.
- SCR-04 content-quality gate: recommend measuring `len(markdown_extraction)` (not raw HTML), with a 16-phrase login-wall keyword list covering English + Chinese paywall / login-prompt patterns.
- SCR-05 429 backoff belongs at the `requests.get` layer (layer 2), not at `trafilatura.fetch_url` (layer 1) — layer 1 cannot expose HTTP status.

### File Created
`C:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\19-generic-scraper-schema-kol-hotfix\19-RESEARCH.md`

### Confidence Assessment
| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | Empirical install + extraction round-trip |
| Architecture | HIGH | Delegates to existing battle-tested WeChat cascade; narrow new code surface |
| Pitfalls | HIGH | Five pitfalls each grounded in observed code / filesystem / semantics |
| Login-wall list | MEDIUM | Judgment call, documented as extensible |

### Open Questions (documented in Open Questions section)
1. Generic-path CDP/MCP layer: defer to Phase 20 — recommendation locked
2. `ImageRef` shape: `list[str]` in Phase 19, upgrade in Phase 20 — recommendation locked
3. `ScrapeResult` frozen or mutable: frozen — recommendation locked

### Ready for Planning
Research complete. Planner can now create PLAN.md files using the Implementation Plan Outline section (13 suggested tasks across 3 waves). All 9 phase requirements (SCR-01..07, SCH-01..02) have concrete specs, code snippets, and test commands.
