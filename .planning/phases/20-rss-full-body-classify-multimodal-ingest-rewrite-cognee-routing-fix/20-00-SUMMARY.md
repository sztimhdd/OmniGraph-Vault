---
phase: 20
plan: "00"
subsystem: tests
tags: [tdd, wave-0, rss-classify, rss-ingest, cognee, red-stubs]
dependency_graph:
  requires: []
  provides: [RCL-01, RCL-02, RCL-03, RIN-01, RIN-02, RIN-03, RIN-04, RIN-05, RIN-06, COG-02]
  affects: [tests/unit/test_rss_classify_fullbody.py, tests/unit/test_rss_ingest_5stage.py, tests/unit/test_cognee_remember_detaches.py]
tech_stack:
  added: []
  patterns: [pytest-asyncio, monkeypatch, AsyncMock, TDD-RED-stubs]
key_files:
  created:
    - tests/unit/test_rss_classify_fullbody.py
    - tests/unit/test_rss_ingest_5stage.py
    - tests/unit/test_cognee_remember_detaches.py
  modified: []
decisions:
  - "Used monkeypatch to block _call_deepseek (legacy path) to prevent network calls while keeping RED assertion for _call_fullbody_llm"
  - "test_image_url_pattern_match passes today — intentional contract lock, not a false positive"
  - "COG-02 test is RED at ~5011ms — confirms asyncio.wait_for(5.0) is the blocking culprit Plan 20-03 must fix"
metrics:
  duration: "~9 minutes (516 seconds)"
  completed_date: "2026-05-06"
  tasks_completed: 3
  files_created: 3
  files_modified: 0
requirements: [RCL-01, RCL-02, RCL-03, RIN-01, RIN-02, RIN-03, RIN-04, RIN-05, RIN-06, COG-02]
---

# Phase 20 Plan 00: Wave-0 RED Stubs Summary

3 test files created that pin the Phase 20 verification contract.
All 10 tests collect cleanly (0 collection errors) and fail for the correct RED reasons.

## What Was Built

Wave 0 TDD infrastructure for Phase 20 RSS full-body classify + multimodal ingest rewrite + Cognee routing fix. 3 test files, 10 tests total, all collecting cleanly via pytest.

## Test File Summary

### tests/unit/test_rss_classify_fullbody.py (3 tests — RCL-01/02/03)

All 3 RED. Reasons:
- `test_classify_reads_body` (RCL-01): `call_count == 0` — production `run()` routes to `_call_deepseek` (blocked with AssertionError), never calls `_call_fullbody_llm` mock
- `test_single_call_multi_topic` (RCL-02): same call_count failure + `FULLBODY_THROTTLE_SECONDS` attribute will fail with AttributeError once Plan 20-01 is partially done
- `test_daily_cap_gates_article` (RCL-03): `classified_count == 0` (not 3) because legacy path is blocked

### tests/unit/test_rss_ingest_5stage.py (6 tests — RIN-01..06)

5 RED, 1 PASS:
- `test_5_stage_checkpoints` (RIN-01): `ImportError: cannot import name '_ingest_one_article'`
- `test_download_images_referer_svg` (RIN-02): `TypeError: download_images() got an unexpected keyword argument 'referer'`
- `test_pending_doc_ids_isolated` (RIN-03): `ImportError: cannot import name '_pending_doc_ids'`
- `test_timeout_rollback` (RIN-04): `ImportError: cannot import name '_ingest_one_article'`
- `test_vision_subdoc_format` (RIN-05): `ImportError: cannot import name '_ingest_one_article'`
- `test_image_url_pattern_match` (RIN-06): **PASSES** — locks existing `_IMAGE_URL_PATTERN` + `localize_markdown` contract

### tests/unit/test_cognee_remember_detaches.py (1 test — COG-02)

RED at `elapsed_ms = 5011.4ms >= 100ms`. Confirms `asyncio.wait_for(..., timeout=5.0)` blocks for the full timeout before returning False. Plan 20-03 D-20.15 `asyncio.create_task` wrap will make it return in <100ms.

## Wave-0 Prerequisites Verified

```
from enrichment.rss_schema import _ensure_rss_columns  # callable ✓
# fresh :memory: SQLite with 5 Phase-19 columns post-call ✓
# columns: body, body_scraped_at, depth, topics, classify_rationale ✓

from lib.scraper import scrape_url, ScrapeResult  # imports cleanly ✓
```

## Deviations from Plan

None — plan executed exactly as written with one minor improvement:

**Improvement (Rule 2 - correctness): Blocked legacy `_call_deepseek` in RCL tests**

Rather than letting tests hit `api.deepseek.com` (7+ second network timeout per test), the legacy `_call_deepseek` was patched to either raise `AssertionError` (test_classify_reads_body) or return `None` (other two), making RED assertions fire in <4 seconds total instead of 20+ seconds. This is strictly better: faster, offline-safe, and the RED message is clearer.

## Known Stubs

None — this plan only creates test files. No production code stubs.

## Baseline Regression Check

Pre-existing failures before Plan 20-00: **15 failures** (2 more than the 13 documented in Phase 19 deferred-items.md). These 15 are unrelated to Phase 20 scope:
- `test_cognee_vertex_model_name` (1)
- `test_lightrag_embedding` + `test_lightrag_embedding_rotation` (6)
- `test_llm_client` (1)
- `test_scrape_first_classify` (2)
- `test_siliconflow_balance` (2)
- `test_text_first_ingest` (1)

The 2 extra failures beyond the documented 13 are pre-existing and out-of-scope for Phase 20. Deferred to post-Phase 22 audit.

New tests add: 9 RED + 1 PASS = 10 tests to the suite.

## Self-Check: PASSED
