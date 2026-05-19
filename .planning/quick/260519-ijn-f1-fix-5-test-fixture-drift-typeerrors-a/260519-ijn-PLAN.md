---
quick_id: 260519-ijn
description: F1 — fix 5 test fixture drift TypeErrors after H4 removed min_depth kwarg
---

# Plan: F1 — drop stale `min_depth` kwarg from `ingest_from_db` test calls

## Context

H4 quick (260518-jpu) removed `min_depth` from the `ingest_from_db()`
signature, but two old tests still pass `min_depth=...` and trip
`TypeError: ingest_from_db() got an unexpected keyword argument 'min_depth'`
(see CLAUDE.md 2026-05-15 lesson #2: fixture drift = silent contract
failure). 5 failures total.

## Tasks

### Task 1 — strip `min_depth` from test_max_articles_hard_cap.py (4 sites)

**Files**: `tests/unit/test_max_articles_hard_cap.py`

**Action**:
- Replace all 4 occurrences of `topic="ai", min_depth=2, dry_run=False,`
  with `topic="ai", dry_run=False,`
- All 4 sites are identical literal `await bi.ingest_from_db(...)` calls
  at L311-L314, L349-L352, L400-L403, L446-L449

**Verify**: `pytest tests/unit/test_max_articles_hard_cap.py -v` → 4 passed

### Task 2 — strip `min_depth` from test_vision_worker.py (1 site)

**Files**: `tests/unit/test_vision_worker.py`

**Action**:
- Replace `topic=["AI agents"], min_depth=1, dry_run=False` (L544)
  with `topic=["AI agents"], dry_run=False`

**Verify**: `pytest tests/unit/test_vision_worker.py::test_ingest_from_db_drains_pending_vision_tasks -v` → passed

### Task 3 — full unit regression

**Action**: `pytest tests/unit/ -v`

**Done when**: all 5 F1-target tests green; pre-existing-pass tests
unaffected by the edit (no causal regression).
