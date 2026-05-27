# T4 — lib/scraper.py Deep Review (read-only post-release hygiene)

**Generated:** 2026-05-11 ADT
**File:** `lib/scraper.py` — 418 LOC, last touch `a3a98d3` (260511-rsr UA fallback for non-WeChat URLs)
**Audit budget:** 2-3 h target — completed under budget (single-pass read-only).
**Auditor scope:** read-only / no business code edits / no Hermes SSH / no pytest.
**Cross-reference T3 review:** `.planning/quick/260511-d7m-t3-batch-ingest-from-spider-py-deep-revi/260511-d7m-REVIEW.md` (`8832e95`).
**Note:** No prior T2 review (`ingest_wechat.py` deep audit) exists — confirmed by Glob for `*t2*` and `*ingest-wechat*` finding only the 260510-rl2 F-4 trivial-cleanup quick. §3 cascade extraction is therefore grounded directly on `ingest_wechat.py` source, not on prior peer-review.

---

## TL;DR

| Severity | Count | Notes |
|----------|-------|-------|
| HIGH | **0** | No release blocker. Cascade divergence (CLAUDE.md 2026-05-08 #1 — the F-1 hypothesis) is **already fixed** by commit `fab60e0` and `a3a98d3`. Both files cascade UA-first today. |
| MEDIUM | **2** | M-1 SCRAPE_CASCADE single-bad-token poisons whole list (cron op-risk); M-2 generic-cascade Layer-3 (CDP/MCP) intentionally skipped — Phase 20 deferred work surfaces as silent `summary_only=True` for non-WeChat URLs that fail trafilatura + 429-fallback. |
| LOW | **3** | L-1 mixed exception-swallow style + duplicate fallback-warning bodies in `_resolve_cascade_order`; L-2 `requests.get` 15-second timeout is a hard ceiling against slow remotes (no env override); L-3 lazy `import ingest_wechat` inside `_scrape_wechat` body (line 278) — small late-import locality cost on every WeChat call. |

**F-1 unlock verdict: `not-needed`** — the original cascade divergence (CLAUDE.md 2026-05-08 #1) was resolved by quick `260508-ev2` (`fab60e0`, the only commit in the `lib/scraper.py` history that ever changed the cascade default). Both files independently order UA-first today. Detailed §3 evidence + commit SHA confirms this. **Recommendation:** backlog F-1 (no T5 needed). The two MEDIUM findings are independent of F-1 and minor — they belong in a future small "scraper hygiene" quick, not blocked on release.

**Estimated cleanup:** **0.5-1.5 h across 1 quick** (one tiny patch fixing M-1 + L-1 in lockstep — both in `_resolve_cascade_order`). M-2 is a Phase-20 deferral, not a quick — it's a roadmap item.

**Release verdict (informational, scope is post-release hygiene):** **CLEAR** ✅ — no HIGH; both MEDIUMs are operability/ergonomics, not correctness; production cron path (UA → Apify → CDP → MCP) is intact and healthy.

---

## 1. File sectional map

10 named symbols / 418 LOC. ⚠ marks **god functions** (>100 LOC); no such functions exist — all symbols are <80 LOC, well-decomposed.

| Lines | LOC | Symbol | Purpose |
|------:|----:|--------|---------|
| 1-15 | 15 | module docstring | Public-API contract: `ScrapeResult`, `scrape_url`. |
| 27-32 | 6 | `_MIN_CONTENT_LENGTH` | SCR-04 floor (200 chars; lowered 500→200 in 260511-b4k for short-form RSS). |
| 34-51 | 18 | `_LOGIN_WALL_PATTERNS` | 16 patterns (English + Chinese) for SCR-04 login-wall detection. |
| 55 | 1 | `_BACKOFF_SCHEDULE_S` | (30s, 60s, 120s) — SCR-05 retry schedule. |
| 56-60 | 5 | `_DEFAULT_UA` | Chrome-120 desktop UA string. |
| 65-77 | 13 | `ScrapeResult` (frozen dataclass) | Public output shape: `markdown`, `images`, `metadata`, `method`, `summary_only`, `content_html`. |
| 82-101 | 20 | `_route` | URL → cascade identifier (`wechat` / `arxiv_abs` / `arxiv_pdf` / `generic`); `site_hint='wechat'` overrides host. |
| 106-117 | 12 | `_passes_quality_gate` | SCR-04 length + login-wall check. |
| 122-156 | 35 | `_fetch_with_backoff_on_429` | SCR-05 GET with 30/60/120s backoff on 429. Non-429 4xx/5xx → returns None immediately. |
| 161-207 | 47 | `_extract_with_fallbacks` | Quick 260511-b4k Layer-2 chain: trafilatura precision → recall → html2text. |
| 215-220 | 6 | `_CASCADE_TOKEN_MAP` | env-token → ingest_wechat function-name mapping. |
| 227-232 | 6 | `_DEFAULT_CASCADE_ORDER` | UA → Apify → CDP → MCP (post-`fab60e0` UA-first). |
| 235-263 | 29 | `_resolve_cascade_order` | Reads `SCRAPE_CASCADE`, parses comma list, falls back to default on invalid. |
| 266-332 | 67 | `_scrape_wechat` | Iterates resolved cascade order, invokes layer fn from `ingest_wechat`, short-circuits on first non-None. SCR-06 dual-key consumer (markdown vs content_html). |
| 337-397 | 61 | `_scrape_generic` | 4-layer cascade for non-WeChat URLs (Layer 1 trafilatura.fetch_url, Layer 2 requests+extract chain, Layer 3 SKIPPED, Layer 4 summary_only fallback). |
| 402-418 | 17 | `scrape_url` (public API) | Routes URL → cascade. Never raises — returns `summary_only=True` on full-cascade exhaustion. |

**Module health signal:** every symbol ≤ ~70 LOC, every public name documented, no god-functions, no backward-compat shims. The file is the smallest "lib core" in the repo and it shows.

---

## 2. CLAUDE.md "Lessons Learned" cross-reference

| Lesson (CLAUDE.md L-#) | Status | Evidence | Notes |
|------------------------|--------|----------|-------|
| **2026-05-08 #1** — `lib/scraper._scrape_wechat()` cascade was Apify→CDP→MCP→UA, `ingest_wechat.py` was UA→Apify→MCP→CDP — divergence wasted 600s/article in 2026-05-08 09:00 ADT cron. (CLAUDE.md:514) | **fixed** | `lib/scraper.py:227-232` `_DEFAULT_CASCADE_ORDER = ('scrape_wechat_ua','scrape_wechat_apify','scrape_wechat_cdp','scrape_wechat_mcp')`. `ingest_wechat.py:1050,1054,1070,1073` order: UA(1050) → Apify(1054) → CDP(1070) / MCP(1073, mutually-exclusive on `_is_mcp_endpoint(CDP_URL)`). Both are UA-first. Commit `fab60e0 feat(scraper): F1b cascade reorder ua-first + SCRAPE_CASCADE env var override` is the only ever-commit that changed this default in lib/scraper.py. | F-1 hypothesis verified resolved. See §3. |
| **2026-05-05 #1** — half-fix pattern: scraper Apify markdown-key fix `ecaa2df` but consumer `batch_ingest_from_spider.py:948` was inconsistent → silent reject of 121 articles. (T3 §2 row "fixed") | **fixed** | `lib/scraper.py:295-312` reads BOTH `result.get("content_html")` AND `result.get("markdown")`. Producer (`_scrape_wechat`) emits both via `ScrapeResult.markdown` + `ScrapeResult.content_html`. Consumer at `batch_ingest_from_spider.py:1042-1053` reads BOTH (`scraped.content_html`, `scraped.markdown`). Producer↔consumer contract is symmetrical. | Verified end-to-end. |
| **2026-05-05 #4** — operational angle of #1: Apify success but consumer reject = paid-for waste. | **fixed (no recurrence)** | Three-way grep across `batch_ingest_from_spider.py` (lines 1042/1050/1053/1882) + tests (`test_scrape_on_demand_apify_markdown.py:31,44,53,60,67,75-79,88-91`) shows every `scraped.markdown` reader also handles `scraped.content_html` symmetrically. No site reads only one of the two. | Symmetric handling in 100% of consumers grepped. |
| **2026-05-05 #5** — body must persist atomically at scrape moment, before downstream gate. | **applicable / not violated** | `lib/scraper.py:330-332` final-cascade fallback returns `ScrapeResult(markdown="", method="none", summary_only=True, content_html=None)`. Scraper itself is stateless — it does not write `articles.body`. The atomic-persist responsibility lives in `batch_ingest_from_spider.py:_persist_scraped_body` (T3 §2 row "fixed"). Scraper's contract is to return either `summary_only=True` (no body) OR a real `ScrapeResult` with a populated body — there is no "scrape succeeded but body empty" silent path because line 301 (`if not content_html and not scraped_markdown: continue`) explicitly cascades on empty results. | No silent-empty-success risk in scraper. |
| **2026-05-08 ev2** — APIFY_TOKEN_BACKUP rotation + SCRAPE_CASCADE env override deployment. (CLAUDE.md:514) | **fixed (deployed)** | F1a: `ingest_wechat.py` (`87b052c`) — `_apify_call` helper + dual-token rotation (test `tests/unit/test_apify_rotation.py` 3 cases). F1b: `lib/scraper.py:215-263` SCRAPE_CASCADE env var (test `tests/unit/test_scrape_cascade_order.py` 5 cases). No half-finished migration debris in the audit window. No legacy env names referenced. **Half-finished migration audit complete: clean.** | All four F1a/F1b/F2 fixes still present. |

**No regressions** found in any of the 5 anchor lessons against current `lib/scraper.py`.

---

## 3. Cascade divergence (STAR ANGLE — A2 / F-1 unlock test)

### Cascade order in `lib/scraper.py` (today)

`lib/scraper.py:227-232` (constant):
```python
_DEFAULT_CASCADE_ORDER: tuple[str, ...] = (
    "scrape_wechat_ua",
    "scrape_wechat_apify",
    "scrape_wechat_cdp",
    "scrape_wechat_mcp",
)
```

`_scrape_wechat()` at `lib/scraper.py:266-332` iterates this tuple via `_resolve_cascade_order()` (lines 235-263) and calls each layer fn from `ingest_wechat` module via `getattr`. First non-None result short-circuits.

**Effective order: UA → Apify → CDP → MCP.**

### Cascade order in `ingest_wechat.py` (today)

`ingest_wechat.py:1048-1073` (top-level orchestrator inside `ingest_article`):
```
1049:        # 1. UA spoofing (primary — fast, free, reliable)
1050:        article_data = await scrape_wechat_ua(url)
1051:
1052:        if not article_data:
1053:            # 2. Apify (backup)
1054:            article_data = await scrape_wechat_apify(url)
...
1066:        # Cascade order ua → apify → cdp/mcp (cdp branch listed first; mcp via _is_mcp_endpoint check)
1067:        if not article_data:
1068:            if not _is_mcp_endpoint(CDP_URL):
1069:                print("UA & Apify failed. Falling back to local CDP...")
1070:                article_data = await scrape_wechat_cdp(url)
1071:            else:
1072:                print("UA & Apify failed. Falling back to remote Playwright MCP...")
1073:                article_data = await scrape_wechat_mcp(url)
```

**Effective order: UA → Apify → (CDP or MCP, env-mutually-exclusive).**

### Side-by-side comparison

| Position | `lib/scraper.py` | `ingest_wechat.py` (CLI direct) |
|---------:|------------------|---------------------------------|
| 1st | UA | UA |
| 2nd | Apify | Apify |
| 3rd | CDP | CDP _or_ MCP (decided by `_is_mcp_endpoint(CDP_URL)`) |
| 4th | MCP | (n/a — already exhausted) |

### Divergence still present? **No.** ✅

**Root-cause evidence (decisive):**
- Commit `fab60e0` (`Fri May 8 11:21:07 2026 -0300`) — `feat(scraper): F1b cascade reorder ua-first + SCRAPE_CASCADE env var override`. From `git show --stat fab60e0`:
  - `lib/scraper.py: new _resolve_cascade_order() ... Default tuple changed from apify,cdp,mcp,ua to ua,apify,cdp,mcp.`
  - `ingest_wechat.py:982-989: cosmetic if/else inversion in direct cascade — CDP-local branch now appears first textually (semantics unchanged: still mutually exclusive on _is_mcp_endpoint(CDP_URL)).`
- This is the only commit in `git log -- lib/scraper.py` history that ever changed the cascade default (verified by `git log --oneline -- lib/scraper.py` returning 6 entries, with `fab60e0` being the lone reorder).
- The current `ingest_wechat.py:1048-1073` cascade matches the post-`fab60e0` shape.

**Source-of-truth recommendation:** `lib/scraper.py` is authoritative for batch ingest (`batch_ingest_from_spider.py:1039,1880` both call `from lib.scraper import scrape_url`). `ingest_wechat.py:1050-1073` is the direct CLI dispatcher (only invoked when running `python ingest_wechat.py <url>` directly). **Both are UA-first today; the divergence is closed.** No source-of-truth split is required because both expressions encode identical UA → Apify → CDP/MCP semantics — they are duplicated by intent (CLI vs library), not by drift.

**Subtle remaining duplication (LOW, not a finding):** the cascade order is hard-coded twice — once as a tuple constant in `lib/scraper.py:227`, once as imperative if/else in `ingest_wechat.py:1048-1073`. If the user ever changes one without the other, the 2026-05-08 lesson recurs. **Mitigation:** the CLAUDE.md "Lessons Learned" entry already captures the grep pattern (`grep -rn "scrape_wechat_apify\|scrape_wechat_cdp\|scrape_wechat_mcp\|scrape_wechat_ua" lib/ *.py`) as a pre-edit check. This is documented institutional memory; no code-level fix needed (consolidating into a single shared list would couple the CLI dispatcher to lib/, an inversion the F-2 rubric forbids — see T3 M-3).

---

## 4. Findings by severity

### HIGH (release blocker / bound to break)

**No findings.** No silent-fail-labeled-success, no producer↔consumer mismatch, no swallowed exception that hides correctness errors, no async task escape. Cascade divergence is closed. Apify dual-token rotation is wired (`tests/unit/test_apify_rotation.py:18-69`, 3 cases all PASS by inspection — primary success, primary→backup fallthrough, both raise). Production cron path verified intact.

### MEDIUM (real but not urgent)

#### M-1 — `SCRAPE_CASCADE` single-bad-token poisons the entire list (silent operability hazard)

**Evidence:** `lib/scraper.py:246-256`:
```python
tokens = [t.strip().lower() for t in raw.split(",") if t.strip()]
resolved: list[str] = []
for tok in tokens:
    fn_name = _CASCADE_TOKEN_MAP.get(tok)
    if fn_name is None:
        logger.warning(
            "scraper: invalid SCRAPE_CASCADE=%r — falling back to default",
            raw,
        )
        return _DEFAULT_CASCADE_ORDER
    resolved.append(fn_name)
```

**Behavior:** if an operator sets `SCRAPE_CASCADE=ua,apify,foo` (one typo) the entire cascade silently reverts to the default `ua,apify,cdp,mcp` — losing the explicit "Apify-only-but-no-CDP" intent. The warning fires, but in a daemon (`tmux` cron path) nobody reads logs except in postmortem.

**Why MEDIUM:** the fix `cron_daily_ingest.sh` shipped in `260508-ev2` parses an explicit cron line for SCRAPE_CASCADE — a typo in that file silently blesses paid Apify calls plus expensive 600s CDP/MCP timeouts (the very failure mode `260508-ev2` was designed to prevent). The lesson 2026-05-08 #1 ("UA-only is the safe default") is silently subverted by a one-character typo.

**Why not HIGH:** test `test_env_invalid_falls_back` (`tests/unit/test_scrape_cascade_order.py:84-100`) explicitly asserts the warning fires + default applies. Default is UA-first (safe). So the worst-case behavior is "operator wanted X, got safe-default Y, found out only via stderr". Not a correctness failure — an ergonomic one.

**Why not LOW:** the impact is on cron op-cost and the lesson the ev2 quick was specifically intended to enforce. M-grade because it can quietly waste 600s of cron budget on a typo.

**Suggested fix (post-release hygiene):**
- Drop unknown tokens silently with a warning, but continue with the parsed-prefix subset (i.e. `ua,apify,foo` → `(ua, apify)`, not full default).
- OR: raise a `ValueError` at module import-time when SCRAPE_CASCADE is set and contains an unknown token, to fail fast at cron startup rather than silently mid-run.
- Either path is ~5 LOC + 1 test. Quick type: `tighten-env-parser`. Risk: very low.

**Maps to:** new finding (not on prior backlog).

---

#### M-2 — Generic-cascade Layer-3 (CDP/MCP) is intentionally skipped — non-WeChat scrape cascade is shallow

**Evidence:** `lib/scraper.py:387-388`:
```python
# Layer 3: SKIPPED in Phase 19 per D-RSS-SCRAPER-SCOPE Option A scope
# Generic CDP/MCP is deferred to Phase 20.
```

`_scrape_generic` at lines 337-397 has only Layer 1 (trafilatura.fetch_url + extract) + Layer 2 (`_fetch_with_backoff_on_429` + extraction-fallback chain) before falling through to `summary_only=True`. There is no headless-browser fallback for non-WeChat URLs that 429-block trafilatura's static fetch.

**Impact today (informational):** RSS articles whose host blocks unauthenticated GETs (Cloudflare-protected blogs, login-walled SaaS docs, JS-rendered SPAs without `<noscript>`) silently land at `summary_only=True`. Per `_persist_scraped_body` (T3 §2 row "fixed"), `summary_only=True` results are not persisted into `articles.body` — the article stays `body=NULL` and is re-tried on the next ingest tick (T3 lesson "DB candidate SELECT does not exclude `status='skipped'` rows" applies). On chronic-fail hosts, this becomes an infinite scrape loop with no remediation path until Phase 20 ships.

**Why MEDIUM, not HIGH:** the `_persist_scraped_body` path correctly drops `summary_only=True` rather than persisting empty bodies (see `batch_ingest_from_spider.py:1882`: `if scraped and not scraped.summary_only`). No silent corruption — just chronic capacity waste. The 260511-rsr quick (`a3a98d3`) recently fixed a tighter related bug (auto-router was routing 45 RSS URLs to the WeChat path); generic-cascade Layer-3 deferral is the broader follow-up.

**Why not LOW:** the RSS pipeline is a v3.5 deliverable that's actively scaling — every Phase-20 deferral compounds the chronic-retry cost. As soon as RSS reaches a few thousand candidates/day, the cron-budget cost of repeated Layer-1/Layer-2 dead-end retries becomes user-visible.

**Suggested fix:** Phase 20 (or its successor quick) should add a Layer 3 generic-CDP/MCP path mirroring `_scrape_wechat`'s cascade pattern. Estimated effort: ~50 LOC delta + Playwright-CDP plumbing (already present in `ingest_wechat.scrape_wechat_cdp`) + test mocks. **Not a quick — a roadmap item.** Tracked in CLAUDE.md and `lib/scraper.py:387` already.

**Maps to:** **F-deferred** — Phase 20 generic-CDP/MCP. Already on roadmap (line 387 inline marker).

---

### LOW (nice-to-have)

#### L-1 — Mixed exception-swallow style + duplicate fallback warning bodies in `_resolve_cascade_order`

**Evidence:** `lib/scraper.py:251-262`:
- Two identical `logger.warning(...) ; return _DEFAULT_CASCADE_ORDER` blocks (lines 251-255 and 258-262), one for unknown-token, one for empty-resolved.
- The second block (`if not resolved`) is dead code if the parsing happens via the for-loop above — `resolved` is non-empty unless `tokens` was empty after the `if t.strip()` filter, which means input was something like `,,,` or `   ,  ` — already handled by line 244 (`raw.strip() == ""`)? **Actually no:** `"  ,  "` would reach line 246, get filtered to `[]` by `if t.strip()`, then bypass the for-loop, reach line 257, fire the warning. So the path IS reachable.

**Why LOW:** the duplicate warning bodies could be factored. The `if not resolved` path is reachable (rare degenerate input) but the user log will say "invalid SCRAPE_CASCADE=' , '" which is informative enough.

**Why not MEDIUM:** purely cosmetic — both branches behave identically and correctly.

**Suggested fix:** factor the `logger.warning(...) ; return _DEFAULT_CASCADE_ORDER` into a single helper or a `try/except`-style sentinel. Either-way, drop into the same quick as M-1 (~3 LOC delta).

#### L-2 — `requests.get` 15-second timeout is hard-coded (no env override)

**Evidence:** `lib/scraper.py:141`:
```python
lambda: requests.get(url, headers=headers, timeout=15),
```

Compare with `ingest_wechat.py` which has 5+ different timeouts across CDP (30000ms), MCP (30s sync, 4500ms inside Playwright), Apify (300s `wait_for`), UA (15s) — all different, none consolidated. SCR-05's 15s is reasonable for free-tier scraping but a slow target with network jitter (e.g. simonwillison.net under high load) could blow it on every retry across the 30/60/120s backoff schedule, wasting 4× attempts × 15s = 60s before falling through.

**Why LOW:** 15s is a sane default; the SCR-05 backoff is 429-specific (rate-limit retry, not slow-server retry), so a slow remote that returns 200 in 16s would fail with `RequestException` — not 429 — and `_fetch_with_backoff_on_429` correctly returns None on `RequestException` (line 143-145, no retry). Cascade falls through to the `_extract_with_fallbacks` path which won't be reached if `html2 is None`. So the failure mode is "slow remote → cascade exhausts → summary_only=True". Acceptable.

**Why not MEDIUM:** no operator has reported a slow-remote failure. Phase 19 picked 15s deliberately. Not a backlog blocker.

**Suggested fix (defer):** if Phase 20 generic-CDP/MCP lands (M-2), add a `OMNIGRAPH_SCRAPE_HTTP_TIMEOUT_SEC` env var to override the 15s default for known-slow remotes (e.g. `arxiv.org` under load). Not urgent.

#### L-3 — `_scrape_wechat` does `import ingest_wechat` inside its body (line 278)

**Evidence:** `lib/scraper.py:278`:
```python
async def _scrape_wechat(url: str) -> ScrapeResult:
    ...
    import ingest_wechat
    cascade_order = _resolve_cascade_order()
    ...
```

**Why LOW:** lazy import is here to avoid the circular dependency at module-load time (`ingest_wechat` imports from `config`, `lib.checkpoint`, `lib.vision_cascade` — initializing it eagerly at `lib/scraper.py` import time would be expensive and pull in LightRAG init). The pattern is intentional. But it IS an "app→lib→app inversion" symptom (T3 M-3 / CC-1) — `lib/scraper.py` reaches sideways into `ingest_wechat.py` (a top-level driver, not a lib module).

**Why not MEDIUM:** T3 M-3 already covers the F-2 lib→app inversion class of finding; this is the same hypothesis instance, listed once for completeness in this audit. It is a **deliberate design accommodation** (the four `scrape_wechat_*` helpers live in `ingest_wechat.py` because they share a giant top-of-module set of selectors / cookies / Playwright-CDP setup, which would be even more painful to factor out as `lib/`-level helpers). Refactor cost is high; current cost is one lazy import.

**Suggested fix (defer / batch):** if a future scraper-hygiene wave decides to relocate `scrape_wechat_*` into `lib/scraper_wechat.py` (genuine lib placement), the lazy import here becomes unnecessary. Not a quick. ~2 h refactor + integration-test verify.

**Maps to:** T3 M-3 (lib→app `config` import inversion); same class. T3 found 4 lib files importing root `config`; this audit confirms `lib/scraper.py` is a 5th instance (it imports `ingest_wechat` lazily, which is functionally equivalent — `ingest_wechat` is a root-level pipeline driver, not a lib module).

---

## 5. Cross-cutting issues

### CC-1 — Same lib→app reach-around as T3 M-3 (5th instance)

T3 audited four `lib/*.py` files importing root-level `config.py` (`from config import BASE_DIR`, `from config import load_env`). This audit adds a 5th lib-side reach-around: `lib/scraper.py:278` lazy-imports the **whole** `ingest_wechat` module (a root-level pipeline driver, not even a config module). Listed once in T3 M-3 for resolution; this is the same finding.

**Single-quick consolidation:** if `Q-CONFIG` (T3 §7) lands, it should also consider whether `scrape_wechat_*` helpers should relocate from `ingest_wechat.py` to `lib/scraper_wechat.py` to close the 5th instance. Estimated additional effort: ~2 h (vs. the 0.5-1 h for T3's 4-import-flatten).

### CC-2 — None other found in scope

No other cross-cutting issues. `lib/scraper.py`'s only other imports (lines 16-23) are 100% stdlib (`asyncio`, `logging`, `os`, `dataclasses`, `typing`, `urllib.parse`). No `from config import ...`, no `from <project root> import ...`. The `import requests` (line 130), `import trafilatura` (lines 168, 345), `import html2text` (line 169) are all third-party libraries — appropriate for a `lib/` module.

---

## 6. Async + error-handling observations (A5+A6)

### A5 — Error-handling silent-fail audit (5 try/except sites in 418 LOC)

| Site | Pattern | Verdict |
|------|---------|---------|
| `:138-145` (`_fetch_with_backoff_on_429`) | `try: requests.get; except RequestException: log + return None` | **Correct.** Returns None lets caller cascade to next layer. No swallow-and-claim-success. |
| `:198-201` (`_extract_with_fallbacks` html2text) | `try: html2text(html); except Exception: log + treat as ""` (`# noqa: BLE001`) | **Correct.** Last-resort extractor explicitly documented as "swallow + record"; caller (Layer 2 fallback chain) just sees an empty md and falls through to Layer 4 summary_only. No silent-success. |
| `:285-292` (`_scrape_wechat` per-layer) | `try: result = await fn(url); except Exception: log + continue` (`# noqa: BLE001`) | **Correct.** Cascading on any layer error is intentional — preserves the "first non-None wins" semantics even if a layer raises (e.g. Apify rate-limit exception, MCP session-drop). The log message includes layer name + exception text. |
| Line 301 `if not content_html and not scraped_markdown: continue` | empty-result cascade gate | **Correct.** Critical defense: a scrape layer that returns `{"title": "x"}` but no body is treated as a miss, NOT as a success. This is the "scrape succeeded but body empty" defensive path that CLAUDE.md 2026-05-05 #5 lesson warned about. ✅ |
| `:330-332` (final fallback) | `return ScrapeResult(markdown="", method="none", summary_only=True, content_html=None)` | **Correct.** Caller (`batch_ingest_from_spider.py:1882`) gates on `not scraped.summary_only` before persisting. Empty body never persists. |

**Conclusion A5:** **no silent-fail-labeled-ok patterns.** The cascade fail-path is clean: every layer error → next layer. Every empty result → next layer. Final exhaustion → `summary_only=True` flag for caller to drop. **Apify dual-token rotation specifically:** the rotation logic lives in `ingest_wechat.py:_apify_call` + `scrape_wechat_apify`, NOT in `lib/scraper.py` (verified by reading `ingest_wechat.py:671-708` — the wrapper handles primary→backup fallthrough and re-raises the LAST exception per `tests/unit/test_apify_rotation.py:53-69`). `lib/scraper.py:285-292` catches any raised Apify exception (including the dual-token "both fail" case) and cascades to CDP — exactly the contract expected post-`87b052c`.

### A6 — Async engineering audit

| Pattern | Sites | Verdict |
|---------|-------|---------|
| `async def` | 4 functions (`:122, :266, :337, :402`) | All awaited at call site. |
| `asyncio.create_task` | **0 hits** | No background task spawning at this layer (correct — vision-task spawning lives in `ingest_wechat.ingest_article`, already audited 260509-p1n). No risk of orphaned task escape. |
| `asyncio.gather` | 0 hits | No fan-out. |
| `asyncio.wait_for` | 0 hits | No internal timeout — relies on layer-fn (Apify, CDP, MCP, UA) to enforce its own timeout. |
| `asyncio.sleep` | 1 site (`:137`) | SCR-05 backoff. Awaited correctly. |
| `asyncio.get_event_loop().run_in_executor` | 2 sites (`:139, :348`) | Wraps blocking `requests.get` and `trafilatura.fetch_url`. Both awaited correctly. |
| `nest_asyncio` | 0 hits | Not needed — pure coroutine path. |
| `await` | 8 sites | All inside coroutine bodies; no orphaned awaitables. |

**Timeout map (A6 sub-angle):**
- Layer 1 generic (`trafilatura.fetch_url`): no explicit timeout — trafilatura's internal default applies (~20s).
- Layer 2 generic (`requests.get`): hard-coded 15s (`:141`). See L-2.
- Layer 1 wechat → delegated to `ingest_wechat`: per-layer-fn timeouts: UA 15s (`ingest_wechat.py:554`), Apify 300s `wait_for` (`:655`), MCP 30s sync + 4500ms in-page (`:734, :769`), CDP 30000ms connect (`:850`).
- Cascade-level: NO `asyncio.wait_for` wrapping the layer call at `lib/scraper.py:286` — relies entirely on each layer-fn's internal timeout. **This is fine** because each layer-fn has its own timeout AND `_scrape_wechat` cascades on any exception (line 287). But if a layer-fn ever drops its internal timeout (regression), the whole batch budget could be consumed.

**Inconsistent timeouts:** UA (15s), Apify (300s), MCP (30s+4.5s), CDP (30s). 20× variance is real. **Not a finding** because each layer's timeout is calibrated to its expected latency. Mentioned for completeness — same observation as T3 §5 (vision worker 60s vs LLM 600-1800s, 30× variance).

**No task-escape risks.** No fire-and-forget. Vision drain (audited 260509-p1n) is in `ingest_wechat`, not here.

---

## 7. Test coverage (A7)

### Test files referencing `lib/scraper.py` symbols

7 test files / **931 LOC of test code** for 418 LOC of source. **2.23× test-to-source ratio** — very high (compare T3's batch_ingest at ~2.94×).

| Test file | LOC | Test cases | Targets |
|-----------|----:|----------:|---------|
| `tests/unit/test_scraper.py` | 263 | 7 (1 frozen-shape + 1 route + 1 quality-gate + 1 backoff + 3 generic-cascade) | `ScrapeResult`, `_route`, `_passes_quality_gate`, `_fetch_with_backoff_on_429`, `_scrape_generic` Layer-1/2/4 |
| `tests/unit/test_scraper_ua_img_merge.py` | 192 | 4 | `_scrape_wechat` SCR-06-followup img_urls merge |
| `tests/unit/test_scrape_cascade_order.py` | 126 | 5 | `_scrape_wechat` cascade order + `SCRAPE_CASCADE` env |
| `tests/unit/test_apify_rotation.py` | 69 | 3 | `ingest_wechat.scrape_wechat_apify` dual-token rotation |
| `tests/unit/test_apify_run_input.py` | 134 | 1 | `ingest_wechat._apify_call` max_items=1 kwarg |
| `tests/unit/test_scrape_on_demand_apify_markdown.py` | 118 | (count not extracted — dead-prod per T3 M-1) | `_classify_full_body` + ScrapeResult markdown handling |
| (subset of `test_dual_source_dispatch.py:110, test_persist_body_pre_classify.py:43, test_batch_ingest_hash.py:19`) | (cross-file) | (n/a) | `ScrapeResult` import / persistence integration |

### Coverage map per audit angle

**A2 (cascade order):** `tests/unit/test_scrape_cascade_order.py:48-125` — 5 cases. Default order, ua-only env, ua+apify env, invalid env fallback+warning, first-success short-circuit. **Cascade order tested at the contract level.** Confirmed.

**A3 (producer↔consumer dual-key):** `tests/unit/test_scraper_ua_img_merge.py:64-192` — 4 cases. Asserts `result.images` equals UA `img_urls` + `process_content` images. Plus `test_scraper.py:20-30` (`ScrapeResult` field set + frozen). The dual-key (markdown/content_html) symmetry is exercised at the consumer level by `test_scrape_on_demand_apify_markdown.py:31-91` — 5 explicit `should_reject = not scraped or (not scraped.content_html and not scraped.markdown)` checks.

**A5 (error-handling):** `tests/unit/test_scraper.py:67-105` — backoff schedule verified (3 cases: 429×3 then 200, persistent 429 returns None, non-429 returns None immediately with no sleep). `test_apify_rotation.py:53-69` — both-tokens-raise re-raises LAST exception. **Solid.**

**A6 (async):** the cascade-order test (5 cases) implicitly verifies async invocation. No dedicated test for `asyncio.wait_for` timeout (none present in scraper). No dedicated test for "layer fn raises → cascade continues" — but T3 M-1 dead-code test `test_scrape_first_classify.py` (now T3 M-1 cleanup target) exercises it indirectly. **Gap (LOW): no direct test for `_scrape_wechat:285-292` Exception-cascade behavior.** Adding one is ~10 LOC.

**A7 sub-angles per task brief:**

- **Cascade order test (mocks all four providers, fails first, asserts second is called):** YES — `test_scrape_cascade_order.py:104-125` (`test_first_success_short_circuits`, `test_default_order_ua_apify_cdp_mcp`).
- **Dual-token rotation:** YES — `test_apify_rotation.py` 69 LOC, 3 cases. **Comprehensive.**
- **`_passes_quality_gate` (SCR-04):** YES — `test_scraper.py:46-61`, 5 assertions (None, empty, 199-char, 200-char + clean, login-wall-en, login-wall-cn, pattern count).

### Gaps (LOW)

1. **No test for "layer fn raises Exception → cascade continues to next":** `_scrape_wechat:287` swallows any layer error; the dual-token rotation test exercises the inside-`scrape_wechat_apify` Exception path, but no test asserts that `_scrape_wechat` itself catches an unhandled Exception from a layer fn. Adding one (e.g., mock `scrape_wechat_apify` to raise → assert cascade reaches `cdp`) is ~15 LOC. **Low priority — the swallow-pattern is documented + the test for cascade-order short-circuit covers the success-case symmetry.**
2. **No test for `_resolve_cascade_order` mid-list bad token (M-1 surface):** `test_env_invalid_falls_back` covers the `SCRAPE_CASCADE=invalid` (single bad token) case — but not `SCRAPE_CASCADE=ua,apify,foo` (one bad mixed with two good). The current behavior (revert to default) is undocumented in tests. If M-1 fix changes behavior to "drop bad, keep good prefix", a new test is needed. ~10 LOC.
3. **No test for Layer-3 SKIPPED in generic cascade:** `_scrape_generic` has 3 tests (`test_cascade_layer_order`, `test_scrape_generic_layer2_recall_wins_when_precision_short`, `test_scrape_generic_layer2_html2text_wins_when_both_trafilatura_short`). None explicitly assert the absence of a CDP/MCP layer-3 fallback. Acceptable today (Phase-20 deferred) but if M-2 ships a Layer-3, the assertion needs to flip.

**Conclusion A7:** test coverage is **strong** — every public symbol has a dedicated test, plus integration-style fixtures for the consumer contract. Three small gaps documented above; total ~35 LOC delta to close all three.

---

## 8. Recommended fix-quick sequence

| # | Quick | Effort | Depends on | Notes |
|---|-------|-------:|------------|-------|
| 1 | **Q-SCRAPER-HYG** — Combine M-1 (SCRAPE_CASCADE bad-token poison) + L-1 (duplicate warning bodies). Drop unknown tokens with a warning, keep parsed-prefix subset; factor warning-body. Add 1 test for mid-list bad token. | 0.5-1 h | none | ~10 LOC source delta + ~10 LOC test delta. Risk: very low (env-parser-tightening only). |
| 2 | **F-deferred (M-2)** — Phase 20 generic-cascade Layer 3 (CDP/MCP for non-WeChat URLs). | (roadmap, not quick) | Phase 20 | ~50 LOC + Playwright wiring + flagged tests. Wait until RSS pipeline scales beyond Layer-1/2 capacity. |
| 3 | (optional, deferred) — Relocate `scrape_wechat_*` helpers from `ingest_wechat.py` to `lib/scraper_wechat.py` to close the L-3 / CC-1 lazy-import inversion. Batch with T3 Q-CONFIG. | 2 h | Q-CONFIG (T3 M-3) | ~50 LOC move + integration test rerun. Cosmetic — defer. |

**Total post-release hygiene cleanup directly attributable to this audit: 0.5-1 h** (Q-SCRAPER-HYG only).

### Dependency graph

```
Q-SCRAPER-HYG (M-1 + L-1)   — release-independent, parallel with T3 backlog
    │
    └── (no dependencies)

F-deferred (M-2)            — Phase 20 roadmap, not a quick

(optional)                  — depends on T3 Q-CONFIG (M-3 lib→app flatten)
```

### Relationship to F-1 (cascade divergence) / F-2 (lib↔app inversion)

- **F-1 (cascade divergence):** **resolved**, see §3. Backlog.
- **F-2 (lib↔app inversion):** **partial / same as T3 M-3 + CC-1.** This audit confirms `lib/scraper.py:278` lazy `import ingest_wechat` is a 5th instance of the same class. T3's Q-CONFIG quick should consolidate, OR this can be deferred to a dedicated `lib/scraper_wechat.py` relocation.

---

## 9. Module verdict

### Pollution score: **LOW**

Reasoning:
- **418 LOC, 10 named symbols, all <80 LOC** — by absolute size and shape, this is the cleanest core lib module in the repo. No god-functions, no dead branches, no migration debris (zero TODO/FIXME/XXX/HACK/DEPRECATED markers).
- **Only "Phase X" markers** are 4 instances of `Phase 19` (current) and `Phase 20` (deferred Layer-3) — both still applicable, both load-bearing context.
- **Zero correctness HIGHs.** Cascade divergence (CLAUDE.md 2026-05-08 #1, the F-1 hypothesis) is **closed**. Producer↔consumer dual-key contract is **symmetrical** at every consumer site grepped. No silent-empty-success path (line 301 explicit cascade-on-empty). No async task escape. No SQL.
- **Test coverage is strong:** 7 test files / 931 LOC / 2.23× test-to-source ratio. Every public symbol has dedicated tests; cascade order, env override, dual-token rotation, quality gate, 429 backoff all individually verified.
- **All previously-audited 260508-ev2 fixes verified intact:** F1a Apify dual-token (`87b052c`, `tests/unit/test_apify_rotation.py` 3 cases), F1b SCRAPE_CASCADE env override + UA-first default (`fab60e0`, `tests/unit/test_scrape_cascade_order.py` 5 cases). No regression.

### F-1 unlock verdict: **`not-needed`** ✅

**One-line justification:** Cascade divergence (the original F-1 hypothesis from CLAUDE.md 2026-05-08 #1) was already resolved by quick `260508-ev2` commit `fab60e0` — both `lib/scraper.py:227-232` and `ingest_wechat.py:1048-1073` independently order UA → Apify → CDP/MCP today, and decision rule HIGH=0 + MEDIUM≤3 + (independently-resolved) puts F-1 firmly in the `not-needed` cell of the verdict matrix.

### Release readiness: **CLEAR** ✅

- HIGH = 0 (decision threshold: HIGH = 0 + MEDIUM ≤ 3 → release directly)
- MEDIUM = 2 (M-1 SCRAPE_CASCADE bad-token poison — operability; M-2 Phase-20 Layer-3 deferred — roadmap)
- LOW = 3 (L-1 cosmetic dup warning; L-2 hard-coded 15s timeout; L-3 lazy-import lib→app inversion already covered by T3 M-3)

### Recommendation: **ship release now; backlog Q-SCRAPER-HYG**

- F-1: **do NOT spawn T5.** Backlog the divergence-grep CLAUDE.md institutional-memory entry for future-edit hygiene. The actual divergence is closed.
- M-1 + L-1: backlog as Q-SCRAPER-HYG (~0.5-1 h post-release).
- M-2: roadmap (Phase 20 — wait until RSS capacity demands it).
- L-2 + L-3: defer indefinitely; revisit on next intentional scraper-hygiene wave or Phase 20 ship.

---

## 10. Open questions for user

1. **Confirm M-1 fix preference: drop-bad-token-and-continue, OR fail-fast?**
   - Option A (drop-and-continue): `SCRAPE_CASCADE=ua,apify,foo` becomes `(ua, apify)` with a warning. Most permissive. Aligns with operator intent ("I wanted UA+Apify, with one typo").
   - Option B (fail-fast at module import): raise ValueError if any token is unknown. Most strict. Aligns with CLAUDE.md "Lessons Learned" 2026-05-08 #1 spirit (any cascade-order ambiguity should be loud).
   - Auditor preference: **Option B** — fail-fast at startup rather than silently mid-run, because the cron path doesn't read warnings. But Option A is also defensible. Defer to user.

2. **M-2 (Phase-20 Layer-3) scheduling:** is the RSS pipeline currently at capacity such that Phase-20 generic-CDP/MCP is releasable into the next planning window, or is the trafilatura+429-backoff cascade still good enough? Per CLAUDE.md L:514, the immediate concern was WeChat — non-WeChat RSS has fewer hard-blocked hosts so may not be urgent. Recommend a quick "RSS Layer-1+Layer-2 success-rate" measurement against the last 7 days of `articles.body IS NULL` rows before scheduling Phase 20.

3. **L-3 / CC-1 (relocate `scrape_wechat_*` to `lib/scraper_wechat.py`):** willing to accept the ~2h refactor cost to close the F-2 inversion class once and for all, or batch with the next T3 Q-CONFIG quick? Auditor recommendation: **batch** — separately, both refactors are too small; together the lib-flatten wave is one coherent ~2-3h quick.

4. **Cascade order encoded in two places** (`lib/scraper.py:227` constant + `ingest_wechat.py:1048-1073` imperative): the institutional-memory grep pattern (CLAUDE.md L:514 last sentence) is the current safety net. Acceptable, or consolidate? Auditor recommendation: **acceptable** — consolidating would force `ingest_wechat` to depend on `lib/scraper`, an inversion the F-2 rubric forbids. Keep duplication + grep discipline.

---

**End of REVIEW.md.** Auditor: read-only / no business code modified / no Hermes SSH / no pytest invocation. All findings cite raw evidence (file:line / commit SHA). Evidence density: 30+ distinct file:line citations + 4 commit SHAs (`fab60e0`, `87b052c`, `a3a98d3`, `ecaa2df`). Total wall time: ~2 h.
