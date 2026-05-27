---
phase: 19-generic-scraper-schema-kol-hotfix
verified: 2026-05-03T23:55:00Z
status: human_needed
score: 10/10 automated must-haves verified; 4 pending-operator items require Hermes SSH
re_verification: null
human_verification:
  - test: "Live KOL 1-article non-dry-run on Hermes returns method:apify or method:cdp (NOT pure method:ua)"
    expected: "Scrape log shows method:apify or method:cdp or method:mcp for first 3 cron articles"
    why_human: "Live Apify + CDP paths unreachable from dev box (Cisco Umbrella); only Hermes network + credentials can exercise this. Success Criterion 2."
  - test: "SELECT body, depth, topics, classify_rationale, body_scraped_at FROM rss_articles LIMIT 1 against live ~/.hermes/omonigraph-vault DB on Hermes"
    expected: "Query executes without error; columns present"
    why_human: "Live kol_scan.db only exists on Hermes; SCH-01 idempotent ALTER only runs when init_rss_schema is invoked on that DB. Success Criterion 3."
  - test: "python scripts/checkpoint_status.py on Hermes shows only 16-char directory names"
    expected: "No 10-char MD5 dirs remaining after checkpoint_reset.py --all --confirm"
    why_human: "Legacy MD5-10 checkpoint dirs only exist on Hermes runtime volume. Success Criterion 4 operator half."
  - test: "Hermes post-pull DEPLOY.md steps 1-5 execute cleanly"
    expected: "git pull ff-only; pip install OK; trafilatura imports 2.x; pytest green; dry-run exits 0"
    why_human: "Plan 19-03 Task 3.3 is autonomous:false — operator must SSH per memory/hermes_ssh.md and run 19-DEPLOY.md verbatim; YOLO executor cannot SSH."
---

# Phase 19: Generic Scraper + Schema + KOL Hotfix — Verification Report

**Phase Goal (from ROADMAP.md):** A single reusable scraper module (`lib/scraper.py`) exists with 4-layer cascade and serves both KOL and RSS arms; the Day-1 KOL regression bug at `batch_ingest_from_spider.py:940` is closed; `rss_articles` schema has the 5 new columns needed by Wave 2; checkpoint hash is unified to SHA-256.

**Verified:** 2026-05-03T23:55:00Z
**Status:** `human_needed` — all automated code-gate checks GREEN; 4 live-environment items pending operator Hermes SSH per 19-DEPLOY.md
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `from lib.scraper import scrape_url, ScrapeResult` imports cleanly | ✓ VERIFIED | Python import smoke test exits 0; `scrape_url` is a coroutine function (inspect.iscoroutinefunction=True) |
| 2 | `ScrapeResult` has the 6 expected fields in order | ✓ VERIFIED | `dataclasses.fields(ScrapeResult)` returns `['markdown', 'images', 'metadata', 'method', 'summary_only', 'content_html']` |
| 3 | `ScrapeResult` is frozen (mutation raises FrozenInstanceError) | ✓ VERIFIED | Runtime smoke: `r.markdown = 'y'` raises `FrozenInstanceError` |
| 4 | `_route()` dispatches wechat/arxiv_abs/arxiv_pdf/generic per urllib.parse | ✓ VERIFIED | `test_route_dispatch` GREEN; covers 4 URL classes + `site_hint='wechat'` override on medium.com host |
| 5 | `_passes_quality_gate()` uses 500-char minimum + 16 login-wall phrases (case-insensitive) | ✓ VERIFIED | `len(_LOGIN_WALL_PATTERNS) == 16`; `test_quality_gate` asserts None/<500/english/chinese/clean cases |
| 6 | `_fetch_with_backoff_on_429()` uses (30.0, 60.0, 120.0) with 3 retries then cascades | ✓ VERIFIED | `_BACKOFF_SCHEDULE_S == (30.0, 60.0, 120.0)` verified at runtime; `test_backoff_429` GREEN for 429×3→200, 429×4→None, 500→None-no-sleep |
| 7 | `batch_ingest_from_spider.py:940` calls `scrape_url(url, site_hint="wechat")` | ✓ VERIFIED | grep hit at line 944 `scraped = await scrape_url(url, site_hint="wechat")`; `scrape_wechat_ua(url)` returns 0 hits in file |
| 8 | `batch_ingest_from_spider.py:275` uses `get_article_hash(url)` (SHA-256[:16]), not MD5[:10] | ✓ VERIFIED | grep hit at line 275 `article_hash = get_article_hash(url)`; `hashlib.md5(url.encode()).hexdigest()[:10]` returns 0 hits |
| 9 | `_ensure_rss_columns` is idempotent (second call is no-op; 5 columns added) | ✓ VERIFIED | `test_ensure_columns_idempotent` GREEN; uses PRAGMA table_info pre-check in `enrichment/rss_schema.py:82` |
| 10 | All 8 phase-19 pytest tests exit 0 | ✓ VERIFIED | `venv/Scripts/python -m pytest tests/unit/test_scraper.py tests/unit/test_batch_ingest_hash.py tests/unit/test_rss_schema_migration.py -q` → `8 passed, 9 warnings in 9.22s` |

**Score:** 10/10 automated truths verified.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `lib/scraper.py` | Exists; exports scrape_url + ScrapeResult; 4-layer cascade; 16-phrase login-wall gate; 30/60/120s backoff | ✓ VERIFIED | 286 LOC; frozen dataclass; `_route`, `_passes_quality_gate`, `_fetch_with_backoff_on_429`, `_scrape_wechat`, `_scrape_generic`, `scrape_url` all present |
| `batch_ingest_from_spider.py:275` | `article_hash = get_article_hash(url)` | ✓ VERIFIED | Line 275 grep match; old MD5 line gone (0 hits) |
| `batch_ingest_from_spider.py:940` | `scrape_url(url, site_hint="wechat")` + `scraped.content_html` | ✓ VERIFIED | Lines 942-950: late import `from lib.scraper import scrape_url`, awaited with site_hint, attribute access `scraped.content_html` (2 hits) |
| `enrichment/rss_schema.py` | `_ensure_rss_columns` idempotent; 5 nullable cols | ✓ VERIFIED | Lines 59-88: `_PHASE19_RSS_ARTICLES_ADDITIONS` tuple of 5 cols, PRAGMA-based idempotent ALTER; wired into `init_rss_schema` at line 103 |
| `requirements.txt` | `trafilatura>=2.0.0,<3.0` + `lxml>=4.9,<6` | ✓ VERIFIED | Lines 27-28; `venv/Scripts/python -c "import trafilatura; print(trafilatura.__version__)"` → `2.0.0` |
| `tests/unit/test_scraper.py` | 5 GREEN tests (SCR-01..05) | ✓ VERIFIED | 5 test functions, 0 pytest.fail stubs; all pass |
| `tests/unit/test_batch_ingest_hash.py` | 2 GREEN tests (SCR-06 + SCH-02) | ✓ VERIFIED | 2 test functions, 0 pytest.fail stubs; both pass |
| `tests/unit/test_rss_schema_migration.py` | 1 GREEN test (SCH-01) | ✓ VERIFIED | 1 test function, 0 pytest.fail stubs; passes |
| `19-DEPLOY.md` | Hermes operator runbook with checkpoint_reset + method:apify/cdp/mcp/ua callouts | ✓ VERIFIED | 98 lines; `checkpoint_reset.py --all --confirm` appears 3× (≥2 required); 6-step operator flow + 8-item checklist |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `tests/unit/test_scraper.py` | `lib.scraper` | `from lib.scraper import` | ✓ WIRED | Imports `ScrapeResult, _BACKOFF_SCHEDULE_S, _LOGIN_WALL_PATTERNS, _fetch_with_backoff_on_429, _passes_quality_gate, _route, _scrape_generic, scrape_url` |
| `lib/scraper.py _scrape_wechat` | `ingest_wechat.scrape_wechat_apify/_cdp/_mcp/_ua` | `getattr(ingest_wechat, fn_name)` for all 4 layers | ✓ WIRED | Line 166: `import ingest_wechat`; line 168-169: 4 layer names iterated; line 186: `ingest_wechat.process_content(content_html)` preserves markdown derivation |
| `lib/scraper.py _scrape_generic` | `trafilatura.fetch_url + trafilatura.extract` | layer 1 trafilatura path | ✓ WIRED | Line 217: `import trafilatura`; line 221: `trafilatura.fetch_url(url)`; line 224: `trafilatura.extract(html, ...)` |
| `lib/scraper.py _scrape_generic` | `_fetch_with_backoff_on_429` | layer 2 requests+trafilatura with 429 retry | ✓ WIRED | Line 239: `html2 = await _fetch_with_backoff_on_429(url)`; then `trafilatura.extract(html2, ...)` at line 241 |
| `batch_ingest_from_spider.py:940` | `lib.scraper.scrape_url` | `scrape_url(url, site_hint="wechat")` | ✓ WIRED | Line 942 late import; line 944 awaited call with the correct kwarg |
| `batch_ingest_from_spider.py:275` | `lib.checkpoint.get_article_hash` | module-level import at line 63 | ✓ WIRED | Line 63 `from lib.checkpoint import get_article_hash, has_stage`; line 275 usage |
| `enrichment/rss_schema.py::init_rss_schema` | `_ensure_rss_columns` | called after _DDL loop | ✓ WIRED | Line 103: `_ensure_rss_columns(conn)` at tail of `init_rss_schema` |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| 8 Phase-19 pytest tests pass | `DEEPSEEK_API_KEY=dummy venv/Scripts/python -m pytest tests/unit/test_scraper.py tests/unit/test_batch_ingest_hash.py tests/unit/test_rss_schema_migration.py -q` | `8 passed, 9 warnings in 9.22s` | ✓ PASS |
| Public scraper API imports | `venv/Scripts/python -c "from lib.scraper import scrape_url, ScrapeResult"` | exit 0 | ✓ PASS |
| `scrape_url` is a coroutine function | `inspect.iscoroutinefunction(scrape_url)` | True | ✓ PASS |
| `ScrapeResult` is frozen | `r.markdown = 'y'` on an instance | `FrozenInstanceError` raised | ✓ PASS |
| Login-wall patterns count | `len(_LOGIN_WALL_PATTERNS)` | `16` | ✓ PASS |
| Backoff schedule | `_BACKOFF_SCHEDULE_S` | `(30.0, 60.0, 120.0)` | ✓ PASS |
| `trafilatura 2.x` installed | `python -c "import trafilatura; print(trafilatura.__version__)"` | `2.0.0` | ✓ PASS |
| Live KOL article returns method:apify/cdp/mcp | `python batch_ingest_from_spider.py --from-db --topic-filter AI --min-depth 2 --max-articles 1` on Hermes | *Not testable from dev box* | ? SKIP (human) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| SCR-01 | 19-01-PLAN | `lib/scraper.py` public API `scrape_url(url, site_hint) -> ScrapeResult` dataclass with 6 fields | ✓ SATISFIED | `test_import_and_dataclass_shape` GREEN; runtime smoke confirms 6 fields |
| SCR-02 | 19-01-PLAN | 4-layer cascade (trafilatura → requests+trafilatura → CDP/MCP deferred → RSS summary fallback) | ✓ SATISFIED | `test_cascade_layer_order` GREEN with tight layer-1 + layer-2 call-count assertions |
| SCR-03 | 19-01-PLAN | URL router via `urllib.parse.urlparse` (no tldextract) | ✓ SATISFIED | `test_route_dispatch` GREEN; covers wechat/arxiv_abs/arxiv_pdf/generic + site_hint override |
| SCR-04 | 19-01-PLAN | Content-quality gate `len >= 500` + login-wall keywords | ✓ SATISFIED | `test_quality_gate` GREEN with 16 patterns; English + Chinese coverage |
| SCR-05 | 19-01-PLAN | HTTP 429 exponential backoff 30s/60s/120s | ✓ SATISFIED | `test_backoff_429` GREEN; verified schedule tuple |
| SCR-06 | 19-02-PLAN | `batch_ingest_from_spider.py:940` UA-only replaced by `scrape_url(url, site_hint="wechat")` | ✓ SATISFIED (code) / ? NEEDS HUMAN (live) | `test_classify_full_body_uses_scraper` GREEN; live verification requires Hermes cron log |
| SCR-07 | 19-00-PLAN | `trafilatura>=2.0.0,<3.0` + `lxml>=4.9,<6` pinned | ✓ SATISFIED | requirements.txt lines 27-28; `import trafilatura, lxml.etree` both succeed |
| SCH-01 | 19-02-PLAN | `rss_articles` ALTER adds 5 nullable columns | ✓ SATISFIED (code) / ? NEEDS HUMAN (live DB) | `test_ensure_columns_idempotent` GREEN; live run against `data/kol_scan.db` pending operator |
| SCH-02 | 19-02-PLAN | Hash unified to SHA-256[:16] at line 275 | ✓ SATISFIED (code) / ? NEEDS HUMAN (live) | `test_hash_is_sha256_16` GREEN; legacy checkpoint dir cleanup pending operator |

**Orphaned requirements:** none — all 9 phase-19 REQ IDs are declared across plans 19-00 through 19-02.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `lib/scraper.py` | 255 | Comment "Layer 3: SKIPPED in Phase 19 per D-RSS-SCRAPER-SCOPE Option A" | ℹ️ Info | Documented deferral to Phase 20 — intentional scope boundary, not a bug. D-RSS-SCRAPER-SCOPE Option A explicitly excludes generic CDP/MCP from Phase 19. |
| `batch_ingest_from_spider.py` | 942 | Late import `from lib.scraper import scrape_url` inside `if not body:` | ℹ️ Info | Matches existing pattern of late `import ingest_wechat` in same block. Prevents LightRAG eager init for classifier-only callers. Plan-specified. |

**No blockers found.** The skipped Layer 3 is scope-bound (per ROADMAP D-RSS-SCRAPER-SCOPE Option A); the late imports are plan-specified to avoid module-load cost.

### Human Verification Required

Four pending-operator items. Plan 19-03 Task 3.3 is explicitly `autonomous: false`; the YOLO executor cannot SSH to Hermes. All require the operator to follow `.planning/phases/19-generic-scraper-schema-kol-hotfix/19-DEPLOY.md` steps 1-5 verbatim.

#### 1. Hermes post-pull deploy steps 1-5

**Test:** SSH to Hermes per `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_ssh.md`; run 19-DEPLOY.md steps 1-5 (pull / venv activate / pip install / checkpoint_reset / pytest / dry-run).
**Expected:** All steps exit 0; `python -c "import trafilatura; print(trafilatura.__version__)"` prints 2.x; pytest shows ≈ 464 passed / ≤ 13 pre-existing failed; dry-run `batch_ingest_from_spider.py --from-db --topic-filter Agent --min-depth 2 --max-articles 1 --dry-run` exits 0.
**Why human:** Hermes SSH is operator-only; dev box cannot reach.

#### 2. Live KOL article method verification

**Test:** After deploy steps complete, either run a real 1-article ingest (`--max-articles 1` without `--dry-run`) or wait for 2026-05-04 06:00 ADT cron and inspect scrape log.
**Expected:** First 3 articles log `method: apify` or `method: cdp` or `method: mcp` (not pure `method: ua`). Confirms SCR-06 hotfix landed on the live pipeline.
**Why human:** Apify + CDP paths require Apify credentials and local browser on Hermes; both unreachable from dev box.

#### 3. Live rss_articles schema spot-check

**Test:** On Hermes, `sqlite3 ~/.hermes/omonigraph-vault/data/kol_scan.db "SELECT body, depth, topics, classify_rationale, body_scraped_at FROM rss_articles LIMIT 1"` (requires `init_rss_schema` to have been invoked, e.g., by triggering a fresh RSS fetch after pull).
**Expected:** Query executes without error; 5 new columns present. Confirms SCH-01 idempotent ALTER reached the live DB.
**Why human:** Live kol_scan.db only exists on Hermes runtime volume; in-memory test GREEN but live DB upgrade is operator side.

#### 4. Checkpoint dir length sanity check

**Test:** After `python scripts/checkpoint_reset.py --all --confirm`, run `ls ~/.hermes/omonigraph-vault/checkpoints/ | awk '{print length($0)}' | sort -u`.
**Expected:** Output is either empty or contains only `16`. No `10`-char MD5 dirs remaining.
**Why human:** Legacy MD5-10 directories are on Hermes runtime volume only; dev box has no equivalent state.

### Success Criteria (ROADMAP.md Phase 19)

| # | Success Criterion | Status | Evidence |
|---|---|---|---|
| 1 | `from lib.scraper import scrape_url, ScrapeResult` imports cleanly; `scrape_url("https://example.com", site_hint="generic")` returns ScrapeResult with non-empty markdown for any reachable public URL | ✓ VERIFIED (import) / ? NEEDS HUMAN (live fetch) | Import smoke test passes; live HTTPS to example.com blocked by Cisco Umbrella on dev box (plan mock-only) |
| 2 | KOL article ingest returns `method: apify` or `method: cdp` (not `method: ua`) — confirms line-940 hotfix | ? NEEDS HUMAN | Code path verified (`test_classify_full_body_uses_scraper` GREEN); live cron log on Hermes required |
| 3 | `SELECT body, depth, topics, classify_rationale, body_scraped_at FROM rss_articles LIMIT 1` runs on live `data/kol_scan.db` | ? NEEDS HUMAN | Code path verified (`test_ensure_columns_idempotent` GREEN); live DB upgrade on Hermes required |
| 4 | `python scripts/checkpoint_status.py` shows only 16-char dir names | ? NEEDS HUMAN | `get_article_hash(url)` returns SHA-256[:16] verified; legacy dir cleanup is operator step |
| 5 | HTTP 429 triggers exponential backoff 30/60/120s in logs; login-wall keyword triggers cascade without hanging | ✓ VERIFIED | `test_backoff_429` GREEN verifies schedule; `test_quality_gate` GREEN verifies 16-phrase gate |

### Gaps Summary

**No code gaps found.** All 10 automated must-haves verified against the actual codebase:

- `lib/scraper.py` exists with the 286 LOC cascade module exactly matching plan specifications
- `batch_ingest_from_spider.py` line 275 (hash) and line 940 (scrape_url) both land correctly
- `enrichment/rss_schema.py` has `_ensure_rss_columns` wired into `init_rss_schema`
- `requirements.txt` pins trafilatura + lxml per SCR-07
- All 8 pytest tests pass in 9.22s (re-verified during this audit)
- 16-phrase login-wall list present; backoff schedule is `(30.0, 60.0, 120.0)` exact
- `ScrapeResult` is frozen (runtime-verified); 6 fields match spec

**Pending-operator items are scope-bound by Plan 19-03 frontmatter (`autonomous: false`).** Phase 19 code is shippable as-is per Plan 19-03 Task 3.4's stance ("code gate passed, field gate pending"). The four human-verification items are the live-environment half of Success Criteria 2, 3, 4 and DEPLOY.md step sequence — they do NOT represent code defects but operational confirmations only the operator can run.

---

*Verified: 2026-05-03T23:55:00Z*
*Verifier: Claude (gsd-verifier, Opus 4.7)*
