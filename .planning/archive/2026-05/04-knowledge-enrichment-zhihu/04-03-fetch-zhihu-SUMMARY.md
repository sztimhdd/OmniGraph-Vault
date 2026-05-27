---
phase: 04-knowledge-enrichment-zhihu
plan: "03"
subsystem: enrichment
tags: [zhihu, fetch, image-pipeline, cdp, tdd]
dependency_graph:
  requires: [04-00, 04-01]
  provides: [enrichment.fetch_zhihu, D-03-contract]
  affects: [04-04-merge-and-ingest, 04-06-enrich-article-top-skill]
tech_stack:
  added: []
  patterns: [tdd, dependency-injection, image-pipeline-reuse, cdp-triple-path]
key_files:
  created:
    - enrichment/__init__.py
    - enrichment/fetch_zhihu.py
    - tests/unit/test_fetch_zhihu.py
  modified: []
decisions:
  - html_fetcher DI seam allows unit tests to bypass CDP entirely (zero network calls in tests)
  - image namespacing uses <hash>/zhihu_<q_idx>/ prefix to avoid collision with WeChat images
  - MCP path mirrors ingest_wechat.py _MCPClient pattern, auto-detected by /mcp suffix in CDP_URL
  - exactly 100px images are KEPT (filter is strict < 100, not <=)
metrics:
  duration: ~25m
  completed: 2026-04-27
  tasks_completed: 1
  files_created: 3
requirements: [D-03, D-15]
---

# Phase 04 Plan 03: fetch-zhihu Summary

**One-liner:** Zhihu answer fetcher with CDP/MCP dual-path, PRD §6.2 image filter, and image namespacing via shared image_pipeline.

## Objective

Build `enrichment/fetch_zhihu.py` — the per-question Python helper the Hermes `enrich_article` skill shells to. Given a Zhihu URL, fetches the page via CDP (or MCP), extracts the main answer body as markdown, downloads and describes images, and writes everything to `$ENRICHMENT_DIR/<hash>/<q_idx>/`.

## Tasks Completed

### Task 3.1 — enrichment/fetch_zhihu.py + unit tests (TDD)

**TDD RED commit:** `1fd4d31` — 9 failing tests written first  
**TDD GREEN commit:** `f7cd106` — implementation; all 9 tests pass

**Files created:**
- `enrichment/__init__.py` — empty package marker (parallel-safe: 04-02 also creates this; trivially merged)
- `enrichment/fetch_zhihu.py` — 333 lines, full implementation
- `tests/unit/test_fetch_zhihu.py` — 221 lines, 9 unit tests

## Implementation Details

### fetch_zhihu.py

Public API:
- `fetch_zhihu(url, wechat_hash, q_idx, base_dir, html_fetcher=None) -> dict` — async orchestrator
- `html_to_markdown(raw_html) -> tuple[str, list[str]]` — extract + filter + convert
- `_filter_small_images(html, min_width=100) -> tuple[str, list[str]]` — PRD §6.2 filter
- `main(argv=None) -> int` — argparse CLI entry point

### CDP triple-path

Auto-detects by `CDP_URL` suffix:
1. `http://localhost:9223` — `playwright.connect_over_cdp()` (local Edge)
2. `http://host:port/mcp` — `_mcp_fetch()` using MCP-over-SSE with `initialize` + `browser_navigate` + `browser_evaluate` (remote Playwright MCP server)

Both paths implement the same contract: accept `url`, return raw HTML string.

### Image pipeline reuse

All image work is delegated to `image_pipeline.py` (D-15):
- `download_images(image_urls, images_dir)` — downloads to `<out_dir>/images/`
- `describe_images(paths)` — batch Gemini Vision describe with 4s inter-image sleep
- `localize_markdown(md, url_to_path, article_hash=ns_hash)` — rewrites URLs
- `save_markdown_with_images(md, out_dir, metadata)` — atomic write (tmp → rename)

No image-download or Gemini-Vision logic duplicated in fetch_zhihu.py.

### Image namespacing

Zhihu images are namespaced as `<hash>/zhihu_<q_idx>/` to prevent collision:
- WeChat images: `http://localhost:8765/abc123/0.jpg`
- Zhihu images: `http://localhost:8765/abc123/zhihu_0/0.jpg`

### D-03 stdout contract

Success: `{"hash": ..., "q_idx": ..., "status": "ok", "md_path": "...", "image_count": N}`  
Error: `{"hash": ..., "q_idx": ..., "status": "error", "error": "..."}`  
Single-line JSON, <50KB, non-zero exit on error.

## Test Coverage

9 unit tests — all pass, zero network I/O:

| Test | What it verifies |
|------|-----------------|
| `test_small_image_filter_drops_sub_100px` | 50px dropped, 400px kept, unknown-width kept |
| `test_small_image_filter_respects_data_width` | `data-width=32` filtered |
| `test_small_image_filter_boundary_exactly_100px_is_kept` | exactly 100px NOT filtered (`< 100` rule) |
| `test_html_to_markdown_extracts_rich_content` | RichContent-inner extracted, footer dropped |
| `test_html_to_markdown_returns_image_urls` | image URLs returned from HTML |
| `test_fetch_zhihu_writes_expected_artifacts` | final_content.md + metadata.json written with correct fields |
| `test_fetch_zhihu_image_namespacing` | image URLs use `<hash>/zhihu_<q_idx>/` prefix |
| `test_cli_error_path_returns_1` | exit code 1 + error JSON on CDP failure |
| `test_cli_stdout_under_50kb` | single-line, < 50KB (D-03 cap) |

## Verification

```
pytest tests/unit/test_fetch_zhihu.py -v    # 9 passed
python -m enrichment.fetch_zhihu --help     # argparse usage printed
grep "from image_pipeline import" enrichment/fetch_zhihu.py  # reuse confirmed
grep "MIN_IMAGE_WIDTH_PX = 100" enrichment/fetch_zhihu.py    # PRD §6.2 constant
```

## Deviations from Plan

### Auto-fixed: duplicate boundary test removed

**Found during:** TDD GREEN  
**Issue:** Initial test file had two conflicting tests for the 100px boundary — one with a wrong assertion (`not in kept`). pytest caught it as a failure.  
**Fix:** Removed the wrong test, kept only `test_small_image_filter_boundary_exactly_100px_is_kept` with the correct `in kept` assertion.  
**Files modified:** `tests/unit/test_fetch_zhihu.py`

### Test count expanded: 9 tests instead of 6

The plan sketch showed 6 tests. I added 3 additional edge-case tests: `data-width` attribute support, boundary exactly-100px rule, and `html_to_markdown_returns_image_urls`. All tests are fast and mocked.

### Pre-existing issue: test_migrations.py fails on import

`tests/unit/test_migrations.py` fails to collect due to `ModuleNotFoundError: No module named 'kol_config'`. This is a pre-existing issue unrelated to this plan — the `kol_config` module is missing from the repo. It was already broken before this plan began. Not fixed (out of scope per Rule 3 — not caused by our changes).

## Known Stubs

None — all data flows are wired:
- HTML fetcher DI seam is intentional, not a stub (CDP is the real default)
- Image descriptions use real Gemini Vision in production (mocked in tests only)

## Self-Check

- [x] `enrichment/fetch_zhihu.py` exists at expected path
- [x] `enrichment/__init__.py` exists at expected path  
- [x] `tests/unit/test_fetch_zhihu.py` exists at expected path
- [x] commit `1fd4d31` exists (RED)
- [x] commit `f7cd106` exists (GREEN)
- [x] 9 unit tests pass
- [x] CLI `--help` works
- [x] `image_pipeline` imported, not duplicated
- [x] `MIN_IMAGE_WIDTH_PX = 100` defined
- [x] image namespacing present
- [x] `html_fetcher` DI seam present
- [x] Did NOT modify STATE.md or ROADMAP.md

## Self-Check: PASSED
