---
phase: 12-checkpoint-resume
plan: 03
status: complete
completed: 2026-05-01
key-files:
  created:
    - tests/integration/test_checkpoint_resume_e2e.py
  modified:
    - batch_ingest_from_spider.py
---

## What was built

**batch_ingest_from_spider.py** — two checkpoint-skip guards, one per ingestion loop:
1. KOL spider loop (line ~656): skip article when `has_stage(ckpt_hash, "text_ingest")` is True; append `"status": "skipped_ingested"` to summary + log `checkpoint-skip: already-ingested`.
2. DB-driven loop (line ~886): same guard + SQLite `ingestions` table status = `'skipped_ingested'`.

**tests/integration/test_checkpoint_resume_e2e.py** — 7 failure-injection + invariant tests:
- `test_gate1_fail_at_image_download_then_resume` — Gate-1 acceptance scenario (fail at stage 3, resume at stage 4, scrape/classify NOT re-run)
- `test_fail_at_scrape_leaves_no_stage_checkpoints` — full scrape cascade failure produces zero stage markers
- `test_fail_at_text_ingest_preserves_stages_1_to_3` — rag.ainsert raises, scrape/classify/image_download persist, second run writes text_ingest marker
- `test_batch_skip_guard_predicate` — unit-level guard predicate
- `test_batch_ingest_from_spider_contains_skip_guard` — static grep on batch spider for skip-guard wiring
- `test_metadata_updated_at_advances` — metadata.json `updated_at` is monotonic after a run
- `test_no_tmp_files_after_success` — atomic-write invariant (no leftover `.tmp` under checkpoints/)

## Acceptance criteria

All plan grep/exit-code checks pass:
- `from lib.checkpoint import` + `has_stage(ckpt_hash, "text_ingest")` + `checkpoint-skip: already-ingested` all grep-present in batch_ingest_from_spider.py
- 7 test functions (>=6 required); includes the Gate-1 test
- `pytest tests/integration/test_checkpoint_resume_e2e.py` → 7/7 green

Full Phase 12 matrix:
- test_checkpoint.py (32) + test_checkpoint_cli.py (8) + test_checkpoint_ingest_integration.py (11) + test_checkpoint_resume_e2e.py (7) = **58/58 green**

Plus no regression in Phase 10:
- test_text_first_ingest.py + test_vision_worker.py + test_scrape_first_classify.py = untouched, still green per 12-02 subagent report.

## Deviations

`FilterStats` dataclass has 5 required fields (`input`, `kept`, `filtered_too_small`, `size_read_failed`, `timings_ms`) — the plan's mock fixture assumed a 3-field form with try/except TypeError fallback. Explicit construction with all 5 fields added. Same deviation applies to Plan 12-02's mock fixture (still works there because the subagent caught it too).

## Gate-1 Acceptance

The v3.2 Phase 12 Gate-1 scenario ("Single article with injected failure at stage 3 (image-download) resumes correctly at stage 4 (text-ingest)") is PROVEN by `test_gate1_fail_at_image_download_then_resume` — asserts:
1. After injected RuntimeError in `download_images`, checkpoints for `scrape`/`classify` exist; `image_download`/`text_ingest` absent.
2. After removing the injection and re-running, `scrape_wechat_ua` NOT called (scrape skipped), `rag.ainsert` called (text ingest runs), all 4 primary stage markers present.

## Follow-ups for Phase 13

- Vision Cascade (Phase 13) will replace the current `"provider": "cascade"` placeholder in `05_vision/*.json` with real per-image provider names (siliconflow / openrouter / gemini) + latency_ms.
- Phase 13-02 image_pipeline integration will consume `lib.checkpoint.list_vision_markers()` to aggregate provider usage for `batch_validation_report.json`.
