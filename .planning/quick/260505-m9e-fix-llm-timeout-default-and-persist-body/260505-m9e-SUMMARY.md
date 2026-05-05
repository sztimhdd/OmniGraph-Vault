---
phase: quick-260505-m9e
plan: 01
type: execute
wave: 1
status: complete
completed: "2026-05-05T16:55:00Z"
duration_min: ~30
requirements:
  - LLMT-01
  - BODY-01
commits:
  - 54baa64  # fix(timeout): bump OMNIGRAPH_LLM_TIMEOUT_SEC default 600 -> 1800
  - 239f4a0  # fix(body): persist scraped body before classify (eliminates SCR-06-class data loss)
files_modified:
  - lib/vertex_gemini_complete.py
  - batch_ingest_from_spider.py
  - tests/unit/test_vertex_gemini_complete.py
files_created:
  - tests/unit/test_persist_body_pre_classify.py
tests_added: 4
deviations: 1  # spec said 900 -> 1800; actual was 600 -> 1800 (planner-flagged, executor honored)
---

# Phase quick-260505-m9e: Fix LLM Timeout Default + Persist Body Pre-Classify Summary

Two atomic blocking-bug fixes from the local 5-article cold-graph pilot (260504-x9l) and Day-1 cron postmortem: bump Vertex Gemini LLM default timeout 600 → 1800s (eliminates 60-image-article 100% timeout); atomically persist scraped body to `articles.body` BEFORE classify (eliminates SCR-06-class data loss when downstream stages fail).

## Commits

| # | Hash | Subject |
|---|------|---------|
| 1 | `54baa64` | `fix(timeout): bump OMNIGRAPH_LLM_TIMEOUT_SEC default 600 -> 1800` |
| 2 | `239f4a0` | `fix(body): persist scraped body before classify (eliminates SCR-06-class data loss)` |

## Tests Added (4 total, all green)

| # | File | Test | Result |
|---|------|------|--------|
| 1 | `tests/unit/test_vertex_gemini_complete.py` | `test_default_timeout_is_1800` | PASS |
| 2 | `tests/unit/test_persist_body_pre_classify.py` | `test_persist_body_when_null` | PASS |
| 3 | `tests/unit/test_persist_body_pre_classify.py` | `test_persist_body_skips_existing_long_body` | PASS |
| 4 | `tests/unit/test_persist_body_pre_classify.py` | `test_persist_body_swallows_db_exception` | PASS |

**Verification command:** `pytest tests/unit/test_vertex_gemini_complete.py tests/unit/test_persist_body_pre_classify.py -q` → `14 passed in 3.79s` (11 in vertex file: 10 prior + 1 new; 3 in body file: all new).

## Spec Discrepancy (planner-flagged, executor honored)

- **Task spec said:** "default 900 → 1800"
- **Actual prior value found:** `_DEFAULT_TIMEOUT_SEC = 600` at `lib/vertex_gemini_complete.py:62`
- **Module docstring also said:** "default: 600, integer seconds" (line 37) — consistent with the actual code, NOT the task spec.
- **Resolution:** Implemented 600 → 1800 (intent unambiguous: bump to 1800 to fix 60-image timeouts). Discrepancy noted in commit 1's body. Module docstring updated to match new default.

## Implementation Details

### Task 1 — LLMT-01

- `lib/vertex_gemini_complete.py:37` — module docstring "default: 600" → "default: 1800"
- `lib/vertex_gemini_complete.py:62` — `_DEFAULT_TIMEOUT_SEC = 600` → `_DEFAULT_TIMEOUT_SEC = 1800`
- `tests/unit/test_vertex_gemini_complete.py` — added `test_default_timeout_is_1800` immediately after `test_timeout_propagation` (same fixture pattern: `_set_vertex_env` + `monkeypatch.delenv("OMNIGRAPH_LLM_TIMEOUT_SEC")` + `_install_client_mock`)
- Env override (`OMNIGRAPH_LLM_TIMEOUT_SEC=42` → 42*1000 ms) verified unchanged via existing `test_timeout_propagation`

### Task 2 — BODY-01

- `batch_ingest_from_spider.py` — new module-level `_persist_scraped_body(conn, article_id, scrape) -> str | None` helper added immediately above `_classify_full_body` (~line 907). SQL guard: `UPDATE articles SET body = ? WHERE id = ? AND (body IS NULL OR length(body) < 500)`. Body source rule: `markdown.strip() or content_html.strip()`. Empty body → no-op; DB exception → swallowed with WARNING log.
- `batch_ingest_from_spider.py` — main loop wired immediately inside the `if not dry_run and api_key:` block, BEFORE the existing `_classify_full_body` call. Lazy import `from lib.scraper import scrape_url`. Skips when `body` already populated (the existing `body` variable from the SQL SELECT 80 lines up).
- `_classify_full_body`'s internal scrape-on-demand path (lines 938-957) **left intact** as defensive fallback (Surgical Changes principle).
- `tests/unit/test_persist_body_pre_classify.py` — new file with 3 mock-only tests using sqlite3 in-memory + hand-rolled `lib.scraper.ScrapeResult` instances. Autouse `DEEPSEEK_API_KEY=dummy` fixture mirrors `test_scrape_first_classify.py` style.

## Hard Constraints — All Honored

| Constraint | Status |
|------------|--------|
| `lib/lightrag_embedding.py` untouched | OK |
| `lib/scraper.py` untouched | OK |
| LightRAG config (e833206) untouched | OK |
| `LLM_TIMEOUT` setdefaults across `batch_ingest_from_spider.py`, `ingest_wechat.py`, `run_uat_ingest.py`, `scripts/bench_ingest_fixture.py`, `scripts/probe_e2e_v3_2.py` — still `"600"` | OK |
| `_classify_full_body` internal scrape-on-demand path (lines 938-957) — UNCHANGED | OK |
| Graded probe code (lines 1410-1426) — UNCHANGED | OK |
| Async-drain hang code (D-10.09) — UNTOUCHED | OK |
| Mock-only tests, no real LLM/Apify/LightRAG calls | OK |

## Deviations from Plan

**1. [Rule N/A — Spec Discrepancy] Bumped default from 600 → 1800 (not 900 → 1800 as task spec claimed)**

- **Found during:** Planning phase (planner read the file before writing the plan)
- **Issue:** Task spec referenced "default 900 → 1800" but `lib/vertex_gemini_complete.py:62` actually had `_DEFAULT_TIMEOUT_SEC = 600`. Module docstring (line 37) consistent with the code at "default: 600".
- **Resolution:** Bumped 600 → 1800 (intent unambiguous: fix 60-image-article timeouts). Discrepancy flagged in plan + commit body for reviewer transparency.
- **Files modified:** `lib/vertex_gemini_complete.py` (lines 37, 62)
- **Commit:** `54baa64`

No other deviations from the plan. No deferred items, no auto-fixes (Rules 1-3) triggered.

## Pre-existing Test Suite Hang (out of scope, documented)

`pytest tests/unit/` (full suite) hangs at `tests/unit/test_scrape_first_classify.py::test_scrape_on_demand_when_body_empty` after 5 passes + 2 unrelated failures (FF). **Verified pre-existing on baseline (commit `54baa64` reverted) — NOT caused by these changes.** The hanging test patches `ingest_wechat.scrape_wechat_ua`, but the production code path in `_classify_full_body` (line 945) imports `lib.scraper.scrape_url` instead — the mock target is no longer covering the actual call site. This is a pre-existing test-stability issue from Phase 19 SCR-06 hotfix and is **out of scope per CLAUDE.md "scope boundary" rule**. Did not attempt to fix; not introduced by this quick task.

Per the plan's verification target (`pytest tests/unit/test_persist_body_pre_classify.py -x -q`), the new tests are 100% green:
- `tests/unit/test_persist_body_pre_classify.py`: **3/3 PASS**
- `tests/unit/test_vertex_gemini_complete.py`: **11/11 PASS** (10 prior + 1 new)
- Combined: **14/14 PASS in 3.79s**

## Wall-clock

~30 minutes total Claude execution time (well under the 60-90 min target, well within the 2h hard cap).

## Self-Check: PASSED

- Files modified exist:
  - `lib/vertex_gemini_complete.py`: FOUND
  - `batch_ingest_from_spider.py`: FOUND
  - `tests/unit/test_vertex_gemini_complete.py`: FOUND
  - `tests/unit/test_persist_body_pre_classify.py`: FOUND
- Commits exist:
  - `54baa64`: FOUND (`fix(timeout): bump OMNIGRAPH_LLM_TIMEOUT_SEC default 600 -> 1800`)
  - `239f4a0`: FOUND (`fix(body): persist scraped body before classify (eliminates SCR-06-class data loss)`)
- New helper `_persist_scraped_body` defined at module level: VERIFIED
- New test `test_default_timeout_is_1800` defined: VERIFIED
- Three new body-persist tests defined: VERIFIED
- Test verification: 14/14 PASS via `pytest tests/unit/test_vertex_gemini_complete.py tests/unit/test_persist_body_pre_classify.py -q`
