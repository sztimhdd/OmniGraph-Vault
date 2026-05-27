---
phase: 19-generic-scraper-schema-kol-hotfix
plan: 01
subsystem: scraper
tags: [scraper, cascade, trafilatura, lxml, dataclass, tdd, wave-1, generic, wechat-delegate, 429-backoff]

# Dependency graph
requires:
  - phase: 19-00
    provides: 5 RED test stubs in tests/unit/test_scraper.py + trafilatura 2.0.0 + lxml 5.4.0 pinned
  - module: ingest_wechat
    provides: scrape_wechat_apify/_cdp/_mcp/_ua cascade + process_content(html) — reused verbatim, not re-implemented
provides:
  - "lib/scraper.py public API: scrape_url(url, site_hint=None) -> ScrapeResult"
  - "ScrapeResult frozen dataclass (6 fields) available for KOL (Phase 19-02) and RSS (Phase 20) consumers"
  - "SCR-01..05 locked GREEN (SCR-02 cascade, SCR-03 router, SCR-04 quality gate, SCR-05 429 backoff)"
affects: [phase-19-02, phase-20, phase-21]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Frozen dataclass as immutable value object (ScrapeResult) — prevents accidental mutation during cascade"
    - "URL-based dispatch via _route(url, site_hint) — single source of truth for cascade branching"
    - "Per-layer exponential backoff on HTTP 429 (30/60/120s) before cascading to next layer"
    - "Quality gate before accepting layer output — 500-char minimum + 16 login-wall phrases (8 English + 8 Chinese)"
    - "WeChat delegation via getattr on ingest_wechat module — zero reimplementation of the 4-layer WeChat cascade"
    - "Tightened test assertions on cascade call counts — a regression that skips layer 1 entirely would fail the test"

key-files:
  created:
    - lib/scraper.py
  modified:
    - tests/unit/test_scraper.py

key-decisions:
  - "Layer 3 (generic CDP/MCP) intentionally deferred to Phase 20 per D-RSS-SCRAPER-SCOPE Option A — falls through to layer 4 summary_only fallback instead of raising NotImplementedError"
  - "content_html field preserved on WeChat ScrapeResult so batch_ingest_from_spider.py:940 consumer can call ingest_wechat.process_content downstream (no API break for the existing consumer)"
  - "scrape_url never raises on scrape failure — returns summary_only=True result so callers decide whether to skip (graceful cascade semantics)"
  - "site_hint='wechat' short-circuits URL parsing (KOL always passes this hint) — future-proofs against non-mp.weixin.qq.com WeChat mirror hosts"

patterns-established:
  - "Thin delegation wrapper pattern: new lib/scraper.py module delegates to existing ingest_wechat.scrape_wechat_* functions via getattr — no duplication, preserves Phase 2-8 WeChat-specific fixes"
  - "Tightened cascade ordering tests: assert call_count on each layer's mock proves the cascade actually fired through each layer, not just the final fallback"

requirements-completed: [SCR-01, SCR-02, SCR-03, SCR-04, SCR-05]

# Metrics
duration: 6min
completed: 2026-05-04
---

# Phase 19 Plan 01: Wave 1 Generic Scraper Core Summary

**lib/scraper.py created (286 LOC) with ScrapeResult frozen dataclass, 4-layer cascade, URL router, 500-char + 16-phrase quality gate, and 30/60/120s 429 backoff — all 5 RED stubs in tests/unit/test_scraper.py driven GREEN**

## Performance

- **Duration:** ~6 min (402s)
- **Started:** 2026-05-04T02:01:49Z
- **Completed:** 2026-05-04T02:08:31Z
- **Tasks:** 3/3 completed
- **Files created:** 1 (`lib/scraper.py`)
- **Files modified:** 1 (`tests/unit/test_scraper.py` — 5 stubs replaced with real assertions)

## Accomplishments

- Created `lib/scraper.py` (286 LOC, slightly above the 150-200 estimate due to explicit inline docstrings per SCR-01..05 and the full 16-phrase verbatim login-wall list).
- `ScrapeResult` frozen dataclass with exactly 6 fields: `markdown, images, metadata, method, summary_only, content_html`.
- `_route(url, site_hint)` dispatches mp.weixin.qq.com → `wechat`, arxiv.org/abs/ → `arxiv_abs`, arxiv.org/pdf/ → `arxiv_pdf`, anything else → `generic`. `site_hint='wechat'` forces wechat regardless of host.
- `_passes_quality_gate(markdown)` rejects None/empty/<500-char markdown and content containing any of the 16 login-wall phrases (8 English + 8 Chinese), case-insensitive.
- `_fetch_with_backoff_on_429(url, ua)` retries HTTP 429 on the `(30.0, 60.0, 120.0)` schedule; cascades to `None` after 3 attempts. HTTP 4xx/5xx (non-429) returns `None` immediately without sleeping.
- `_scrape_wechat(url)` delegates to `ingest_wechat.scrape_wechat_apify → _cdp → _mcp → _ua` (first non-None wins) via `getattr`; preserves `content_html` on the returned `ScrapeResult` so the downstream `batch_ingest_from_spider.py:940` consumer can call `ingest_wechat.process_content(content_html)` as before.
- `_scrape_generic(url)` 4-layer cascade: (1) `trafilatura.fetch_url` + `trafilatura.extract` → quality gate; (2) `_fetch_with_backoff_on_429` + `trafilatura.extract` → quality gate; (3) **intentionally skipped** per D-RSS-SCRAPER-SCOPE Option A (deferred to Phase 20); (4) summary_only fallback.
- `scrape_url(url, site_hint=None)` public API — never raises, always returns a `ScrapeResult`.
- All 5 RED stubs in `tests/unit/test_scraper.py` driven GREEN with mock-only assertions (no live HTTPS — Cisco Umbrella proxy compliance).
- Tightened `test_cascade_layer_order` with explicit `call_count` and `await_count` assertions that prove layer 1 AND layer 2 actually fired before the summary fallback — a regression that skipped layer 1 entirely would have passed the old test.

## Task Commits

Each task committed atomically with `--no-verify` and pushed to `origin/main`:

1. **Task 1.1: lib/scraper.py core (ScrapeResult + _route + _passes_quality_gate + _fetch_with_backoff_on_429)** — `1a70adc` (feat)
2. **Task 1.2: append _scrape_wechat + _scrape_generic + scrape_url** — `597b5c9` (feat)
3. **Task 1.3: replace 5 RED stubs in tests/unit/test_scraper.py with GREEN tests** — `523990e` (test)

## Test Output (5 tests GREEN)

```
$ DEEPSEEK_API_KEY=dummy venv/Scripts/python -m pytest tests/unit/test_scraper.py -v
tests/unit/test_scraper.py::test_import_and_dataclass_shape PASSED       [ 20%]
tests/unit/test_scraper.py::test_route_dispatch                PASSED    [ 40%]
tests/unit/test_scraper.py::test_quality_gate                  PASSED    [ 60%]
tests/unit/test_scraper.py::test_backoff_429                   PASSED    [ 80%]
tests/unit/test_scraper.py::test_cascade_layer_order           PASSED    [100%]

============================== 5 passed in 2.93s ==============================
```

### Test → Requirement Mapping

| Test | Requirement | Task-ID | Asserts |
|------|-------------|---------|---------|
| `test_import_and_dataclass_shape` | SCR-01 | 19-01-01 | ScrapeResult has 6 fields {markdown, images, metadata, method, summary_only, content_html}; frozen=True raises FrozenInstanceError; content_html defaults to None |
| `test_route_dispatch` | SCR-03 | 19-01-02 | _route returns wechat/arxiv_abs/arxiv_pdf/generic for 4 URL classes; site_hint='wechat' overrides medium.com host |
| `test_quality_gate` | SCR-04 | 19-01-03 | _passes_quality_gate rejects None/empty/<500/English login-wall/Chinese login-wall; accepts 500+clean; 16 patterns defined |
| `test_backoff_429` | SCR-05 | 19-01-04 | (429×3→200): returns "body" with sleep(30,60,120); (429×4): None + 3 sleeps; 500: None + 0 sleeps |
| `test_cascade_layer_order` | SCR-02 | 19-01-05 | _scrape_generic calls layer 1 exactly once, layer 2 exactly once, then falls through to summary_only=True fallback |

## Full Suite Regression (no new breakage)

```
$ DEEPSEEK_API_KEY=dummy venv/Scripts/python -m pytest tests/ -q --ignore=tests/unit/test_scraper_live.py
14 failed, 463 passed, 1 skipped, 11 warnings in 82.91s
```

**Pass delta:** 458 (post-Wave-0 baseline) → 463 = exactly +5 GREEN from Wave 1. No existing GREEN test regressed.

**Failure attribution (all known):**
- **3 Wave 2 RED stubs (expected, will go GREEN in plan 19-02):**
  - `test_batch_ingest_hash.py::test_classify_full_body_uses_scraper`
  - `test_batch_ingest_hash.py::test_hash_is_sha256_16`
  - `test_rss_schema_migration.py::test_ensure_columns_idempotent`
- **11 pre-existing out-of-scope failures (documented in `deferred-items.md` — phases 5/10/11/13):**
  - `test_bench_integration.py::test_text_ingest_over_threshold_fails_gate`
  - `test_lightrag_embedding.py::test_embedding_func_reads_current_key`
  - `test_lightrag_embedding_rotation.py::*` (6 tests)
  - `test_siliconflow_balance.py::*` (2 tests)
  - `test_text_first_ingest.py::test_parent_ainsert_content_has_references_not_descriptions`

(The 12th pre-existing failure from Wave 0, `test_bench_integration.py::test_live_gate_run`, was skipped in this run — it is a live-gate integration test and is environment-conditional.)

## Files Created/Modified

- `lib/scraper.py` (new, 286 LOC) — ScrapeResult dataclass + _route + _passes_quality_gate + _fetch_with_backoff_on_429 + _scrape_wechat (delegation) + _scrape_generic (4-layer cascade) + scrape_url public API.
- `tests/unit/test_scraper.py` (modified) — 5 `pytest.fail(...)` RED stubs replaced with real mock-only assertions covering SCR-01..05.

## Decisions Made

- **Layer 3 deferred, not raised:** `_scrape_generic` layer 3 (CDP/MCP for gated sites) is intentionally skipped — the code simply falls through to layer 4 summary_only fallback with no `NotImplementedError`. Per `D-RSS-SCRAPER-SCOPE` Option A scope, generic CDP/MCP is Phase 20's concern. This keeps Phase 19 minimal and non-breaking.
- **content_html preservation:** The WeChat path populates `ScrapeResult.content_html` from the underlying `scrape_wechat_*` result's `content_html`. The generic path leaves it `None`. This matches the existing consumer contract at `batch_ingest_from_spider.py:940` exactly.
- **Delegation via `getattr` not direct import of all four functions:** `_scrape_wechat` iterates over `("scrape_wechat_apify", "scrape_wechat_cdp", "scrape_wechat_mcp", "scrape_wechat_ua")` and calls each via `getattr(ingest_wechat, fn_name, None)`. This keeps the delegation loop compact and resilient if ingest_wechat temporarily loses one of the four layers.
- **Test mock strategy:** `test_cascade_layer_order` uses `mocker.patch.dict("sys.modules", {"trafilatura": fake_trafilatura})` + a custom `run_in_executor` replacement that synchronously evaluates its lambda argument. This ensures `fake_trafilatura.fetch_url` is actually called and call-counts are meaningful.

## Deviations from Plan

None — plan executed exactly as written. All three task actions ran verbatim. No auto-fixes needed. The `DEEPSEEK_API_KEY=dummy` environment variable was used per the documented CLAUDE.md Phase 5 cross-coupling workaround when running verification commands (not a code change, just an environment preconfig for the dev box — production deployments have the real key set).

## Issues Encountered

### DEEPSEEK_API_KEY import-time requirement (documented pre-existing quirk)

Every `lib/*` import triggers `lib/__init__.py` which eagerly imports `lib.llm_deepseek.deepseek_model_complete`, which raises `RuntimeError` at import time if `DEEPSEEK_API_KEY` is unset. This is the Phase 5 FLAG 2 cross-coupling documented in CLAUDE.md; the documented workaround (`DEEPSEEK_API_KEY=dummy`) was used for all verification commands in this plan. No scraper code was affected — `lib/scraper.py` does not import or use any DeepSeek functionality. Production deployments already have `DEEPSEEK_API_KEY` set in `~/.hermes/.env`, so nothing changes there.

## User Setup Required

None — no external service configuration required. `trafilatura` + `lxml` were pinned + installed in Wave 0.

## Next Phase Readiness

- **Plan 19-02 (Wave 2) ready:** patches `batch_ingest_from_spider.py:940` (SCR-06) to consume `lib.scraper.scrape_url` instead of the in-line WeChat code, unifies article hashing to `lib.checkpoint.get_article_hash` (SCH-02), and adds `_ensure_rss_columns` to `enrichment/rss_schema.py` (SCH-01). This will drive the remaining 3 Wave 2 RED stubs to GREEN.
- **Execute gate reminder:** v3.4 production execution still blocked until Day-1/2/3 KOL cron baseline completes (~2026-05-06 ADT). Wave 1 is planning-layer + test-layer only; no production code path is touched until Wave 2 migrates the consumer.

## Pitfall 5 Note (per plan § Output)

`lxml<6` pin honored per REQUIREMENTS.md SCR-07 authoritative spec (researcher recommended `<7`, but REQUIREMENTS.md governed the hotfix). Already committed in Wave 0 (`requirements.txt` line 28). Retention noted here for v3.5 relaxation traceability.

## Self-Check: PASSED

Files exist:
- `lib/scraper.py` — FOUND (286 LOC)
- `tests/unit/test_scraper.py` — FOUND (modified, 5 GREEN tests, 0 pytest.fail stubs)

Commits exist on `main`:
- `1a70adc` — FOUND (feat: lib/scraper.py core)
- `597b5c9` — FOUND (feat: _scrape_wechat + _scrape_generic + scrape_url)
- `523990e` — FOUND (test: 5 RED → 5 GREEN)

Acceptance checks:
- `grep -c "^@dataclass(frozen=True)" lib/scraper.py` → 1 — PASS
- `grep -c "class ScrapeResult:" lib/scraper.py` → 1 — PASS
- `grep -c "^def _route" lib/scraper.py` → 1 — PASS
- `grep -c "^def _passes_quality_gate" lib/scraper.py` → 1 — PASS
- `grep -c "^async def _fetch_with_backoff_on_429" lib/scraper.py` → 1 — PASS
- `grep -c "^async def _scrape_wechat" lib/scraper.py` → 1 — PASS
- `grep -c "^async def _scrape_generic" lib/scraper.py` → 1 — PASS
- `grep -c "^async def scrape_url" lib/scraper.py` → 1 — PASS
- `grep "content_html: Optional" lib/scraper.py` → match — PASS
- `grep -E '"(Sign in|登录查看|请先登录|付费内容)"' lib/scraper.py | wc -l` → 4 — PASS (≥4)
- `grep "_BACKOFF_SCHEDULE_S: tuple\[float, ...\] = (30.0, 60.0, 120.0)" lib/scraper.py` → match — PASS (value `(30.0, 60.0, 120.0)` verbatim)
- `grep -c "pytest.fail" tests/unit/test_scraper.py` → 0 — PASS (all RED stubs replaced)
- `grep -c "^def test_\|^async def test_" tests/unit/test_scraper.py` → 5 — PASS
- Frozen enforcement: `ScrapeResult(markdown='x').markdown='y'` raises `FrozenInstanceError` — PASS
- `pytest tests/unit/test_scraper.py` → 5 passed — PASS
- Full regression: 463 passed (458 baseline + 5 new GREEN), 14 failed (3 Wave 2 RED stubs + 11 pre-existing) — PASS (zero new regressions)

---
*Phase: 19-generic-scraper-schema-kol-hotfix*
*Plan: 01*
*Completed: 2026-05-04*
