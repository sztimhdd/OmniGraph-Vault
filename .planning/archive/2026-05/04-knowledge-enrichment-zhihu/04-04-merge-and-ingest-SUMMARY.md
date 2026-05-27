---
phase: 04-knowledge-enrichment-zhihu
plan: "04"
subsystem: enrichment
tags: [lightrag, sqlite, merge, d-07, d-08, d-09, d-11, tdd]
dependency_graph:
  requires: [04-02, 04-03]
  provides: [enrichment.merge_md, enrichment.merge_and_ingest]
  affects: [04-06-enrich-article-top-skill, 04-07-ingest-wechat-integration]
tech_stack:
  added: []
  patterns: [tdd-red-green, pure-function-separation, failure-tolerant-sqlite, d-03-stdout-contract]
key_files:
  created:
    - enrichment/merge_md.py
    - enrichment/merge_and_ingest.py
    - tests/unit/test_merge_md.py
    - tests/unit/test_merge_and_ingest.py
  modified: []
decisions:
  - "D-09: 好问 summaries appended inline under ## 知识增厚 with 1-based question numbering preserving gaps"
  - "D-08: Zhihu docs use ids=[f'zhihu_{hash}_{q_idx}'] and file_paths=[f'enriches:{hash}'] for LightRAG backlink"
  - "D-07/D-11: enriched_state = 2 if success_count >= 1 else -2; enrichment_id = f'enrich_{hash}'"
  - "_ingest_to_lightrag late-imports ingest_wechat.get_rag to allow monkeypatching in tests without importing lightrag"
  - "merge_and_ingest tests use _mock_rag fixture that patches _ingest_to_lightrag entirely for D-07/D-11 tests; D-08 test patches ingest_wechat.get_rag directly to inspect ainsert call args"
metrics:
  duration: "~5 minutes"
  completed: "2026-04-27T17:21:29Z"
  tasks: 2
  files: 4
---

# Phase 04 Plan 04: merge-and-ingest Summary

**One-liner:** Pure WeChat+好问 merger (merge_md) + runner (merge_and_ingest) that seals enrichment artifacts into LightRAG with D-08 IDs and updates SQLite D-07/D-11 state machine.

## What Was Built

### `enrichment/merge_md.py` — Pure merger function (44 lines)

`merge_wechat_with_haowen(wechat_md, haowen)` appends a `## 知识增厚` section to the WeChat MD tail:
- Each successful question gets a `### 问题 N: <question>` subsection with summary + `来源:` URL
- Question numbering uses the original list position (1-based), so None gaps are visible
- All-fail (empty list or all-None): appends `(未找到相关的知乎问答)` footer
- Zero I/O, no side effects — pure function (D-09)

### `enrichment/merge_and_ingest.py` — Runner (226 lines)

Async orchestrator that reads disk artifacts, merges, ingests, and updates SQLite:
- `_load_haowen_list`: reads `haowen.json` per q_idx, returns `None` for missing/unreadable
- `_load_zhihu_mds`: reads `final_content.md` per q_idx
- `_ingest_to_lightrag`: calls `rag.ainsert(enriched_wechat_md)` + per-Zhihu-doc `rag.ainsert(md, ids=[f"zhihu_{hash}_{q_idx}"], file_paths=[f"enriches:{hash}"])` (D-08)
- `_update_sqlite_status`: failure-tolerant `UPDATE articles SET enriched` + `UPDATE ingestions SET enrichment_id` (D-07/D-11)
- `merge_and_ingest`: `enriched_state = 2 if success_count >= 1 else -2`
- `main`: argparse CLI, single-line JSON stdout (D-03), non-zero exit on error

## Tasks

### Task 4.1 — enrichment/merge_md.py + test_merge_md.py (TDD)

**RED commit:** `95e8cb8` — 5 failing tests (module not yet created)
**GREEN commit:** `c75f23a` — implementation passes all 5 tests

Files created:
- `enrichment/merge_md.py` — 44 lines, pure function
- `tests/unit/test_merge_md.py` — 5 unit tests

### Task 4.2 — enrichment/merge_and_ingest.py + test_merge_and_ingest.py (TDD)

**RED commit:** `95e8cb8` (bundled with Task 4.1 RED — both test files committed together)
**GREEN commit:** `f64e407` — implementation passes all 4 tests

Files created:
- `enrichment/merge_and_ingest.py` — 226 lines, runner with full side effects
- `tests/unit/test_merge_and_ingest.py` — 4 unit tests

## Acceptance Criteria Verification

| Check | Result |
|---|---|
| `enrichment/merge_md.py` exists, importable | PASS |
| `grep "def merge_wechat_with_haowen"` | PASS |
| `grep "知识增厚"` | PASS |
| `pytest tests/unit/test_merge_md.py -x -v` → 5 passed | PASS |
| `enrichment/merge_and_ingest.py` exists | PASS |
| `grep 'ids=\[f"zhihu_'` (D-08 synthetic ID) | PASS |
| `grep 'file_paths=\[f"enriches:'` (D-08 backlink) | PASS |
| `grep "UPDATE articles SET enriched"` | PASS |
| `grep "UPDATE ingestions SET enrichment_id"` | PASS |
| `grep "enriched_state = 2 if success_count >= 1 else -2"` (D-11) | PASS |
| `pytest tests/unit/test_merge_and_ingest.py -x -v` → 4 passed | PASS |
| `python -m enrichment.merge_and_ingest --help` exits 0 | PASS |
| Combined: 9/9 tests pass | PASS |

## Deviations from Plan

None — plan executed exactly as written.

The plan's action blocks provided the complete implementation code. I verified each acceptance grep, confirmed all 9 tests pass, and confirmed the CLI responds to `--help`.

Pre-existing warnings from Cognee/Pydantic libraries appear on the `test_zhihu_docs_use_deterministic_ids_and_enriches_backlink` test (which imports `ingest_wechat` transitively loading cognee_wrapper). These are third-party deprecation warnings unrelated to this plan and were present before this work.

## Known Stubs

None — all data flows are wired:
- `_ingest_to_lightrag` calls `ingest_wechat.get_rag()` (real in production, monkeypatched in D-08 test)
- `_update_sqlite_status` writes to real SQLite (skips gracefully if DB missing)
- `merge_wechat_with_haowen` is fully implemented with no placeholders

## Self-Check: PASSED

- `enrichment/merge_md.py` — FOUND
- `enrichment/merge_and_ingest.py` — FOUND
- `tests/unit/test_merge_md.py` — FOUND
- `tests/unit/test_merge_and_ingest.py` — FOUND
- Commit `95e8cb8` (RED) — FOUND
- Commit `c75f23a` (merge_md GREEN) — FOUND
- Commit `f64e407` (merge_and_ingest GREEN) — FOUND
- All 9 tests pass: CONFIRMED
