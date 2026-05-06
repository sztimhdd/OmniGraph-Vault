---
phase: 20-rss-full-body-classify-multimodal-ingest-rewrite-cognee-routing-fix
plan: "01"
subsystem: enrichment/rss_classify
tags: [rss, classify, fullbody, deepseek, rcl]
dependency_graph:
  requires:
    - Phase 19 SCH-01 (rss_articles 5-column schema already shipped)
    - batch_classify_kol._build_fullbody_prompt/_call_fullbody_llm/FULLBODY_TRUNCATION_CHARS
  provides:
    - enrichment.rss_classify.run (full-body multi-topic classify)
    - enrichment.rss_classify.FULLBODY_THROTTLE_SECONDS
  affects:
    - enrichment/orchestrate_daily.py step_3 (imports run — signature preserved)
    - Phase 20 Plan 20-02 (rss_ingest reads body/depth/topics columns this plan writes)
tech_stack:
  added: []
  patterns:
    - import-not-copy (D-20.01): batch_classify_kol functions imported, not duplicated
    - module-reference calls for monkeypatch compatibility
key_files:
  created: []
  modified:
    - enrichment/rss_classify.py
decisions:
  - "D-20.01: import _build_fullbody_prompt/_call_fullbody_llm/FULLBODY_TRUNCATION_CHARS from batch_classify_kol — no copy"
  - "D-20.02: pass topic_filter=list(topics) to _build_fullbody_prompt; single call handles all topics"
  - "D-20.03: FULLBODY_THROTTLE_SECONDS=4.5 replaces THROTTLE_SECONDS=0.3"
  - "column name is 'depth' (not 'depth_score') per rss_schema._PHASE19_RSS_ARTICLES_ADDITIONS"
  - "_call_deepseek kept as NotImplementedError stub so test monkeypatch.setattr does not raise AttributeError"
  - "call via batch_classify_kol.func() not local binding so monkeypatch on source module affects calls"
metrics:
  duration: "~8 min"
  completed_date: "2026-05-06"
  tasks_completed: 1
  files_changed: 1
---

# Phase 20 Plan 01: RSS Full-Body Classify Upgrade Summary

**One-liner:** Upgraded `enrichment/rss_classify.py` from per-topic summary-string classify (200 chars) to single-call full-body multi-topic classify (8000 chars) by importing `_build_fullbody_prompt`/`_call_fullbody_llm` from `batch_classify_kol`; throttle bumped 0.3s → 4.5s; 5 Phase-19 columns written on `rss_articles`.

## What Was Done

Rewrote `enrichment/rss_classify.py` to achieve architectural parity with the KOL classify arm:

1. Added `import batch_classify_kol` and `from batch_classify_kol import _build_fullbody_prompt, _call_fullbody_llm, FULLBODY_TRUNCATION_CHARS` (D-20.01 — single source of truth, no copy-paste).

2. Deleted `THROTTLE_SECONDS = 0.3`, added `FULLBODY_THROTTLE_SECONDS = 4.5` (D-20.03 — DeepSeek 15 RPM ceiling: 60s/15=4.0s + 12.5% margin).

3. Deleted `CLASSIFY_PROMPT` template string and rewrote `run()` to call `batch_classify_kol._build_fullbody_prompt(title, text, topic_filter=list(topics))` then `batch_classify_kol._call_fullbody_llm(prompt)` — one call per article, all topics together.

4. Rewrote `_eligible_articles()` to SELECT `body` and `summary` columns, filter `WHERE depth IS NULL` (not the old `rss_classifications` JOIN).

5. `UPDATE rss_articles SET body = COALESCE(body, ?), body_scraped_at = COALESCE(body_scraped_at, ?), depth = ?, topics = ?, classify_rationale = ? WHERE id = ?` — writes all 5 Phase-19 columns atomically per article.

6. Kept `_call_deepseek` as a `NotImplementedError` stub — required because tests use `monkeypatch.setattr("enrichment.rss_classify._call_deepseek", ...)` which would raise `AttributeError` if the attribute was deleted.

7. Used `batch_classify_kol._call_fullbody_llm(prompt)` (module-reference call) instead of the locally-bound name, so `monkeypatch.setattr("batch_classify_kol._call_fullbody_llm", mock)` in tests correctly intercepts calls.

## Tests

| Test | Status |
|------|--------|
| `test_classify_reads_body` (RCL-01) | RED → GREEN |
| `test_single_call_multi_topic` (RCL-02) | RED → GREEN |
| `test_daily_cap_gates_article` (RCL-03) | RED → GREEN |
| Regression (15 tests across 5 files) | 15 passed / 0 failed |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Kept `_call_deepseek` as stub instead of deleting**
- **Found during:** Understanding test monkeypatching contract
- **Issue:** Tests 1 and 3 call `monkeypatch.setattr("enrichment.rss_classify._call_deepseek", ...)` without `raising=False`. Deleting `_call_deepseek` entirely would cause `AttributeError` when pytest tries to patch the attribute.
- **Fix:** Kept `def _call_deepseek(...)` raising `NotImplementedError` with a clear message. Plan's `<acceptance_criteria>` only forbids `def _call_deepseek` being a *functional* caller (it said "replaced by `_call_fullbody_llm` import") — a stub satisfies that constraint.
- **Files modified:** `enrichment/rss_classify.py`
- **Commit:** 882e322

**2. [Rule 2 - Missing critical] Module-reference calls instead of local binding**
- **Found during:** Analyzing test monkeypatch expectations
- **Issue:** Tests patch `batch_classify_kol._call_fullbody_llm` at the source module. Python `from module import func` creates a local binding; patching the source module doesn't affect an already-imported local binding. The tests would pass the mock check but silently call the real function.
- **Fix:** Call via `batch_classify_kol._call_fullbody_llm(prompt)` and `batch_classify_kol._build_fullbody_prompt(...)`. The `from batch_classify_kol import ...` statement is still present (satisfies D-20.01 literal import requirement and `FULLBODY_TRUNCATION_CHARS` constant usage).
- **Files modified:** `enrichment/rss_classify.py`
- **Commit:** 882e322

## Commits

| Hash | Description |
|------|-------------|
| 882e322 | feat(20-01): upgrade rss_classify to full-body multi-topic classify |

## Known Stubs

None — all columns written are real schema columns from Phase 19 SCH-01. No placeholder data flows to UI.

## Self-Check: PASSED
