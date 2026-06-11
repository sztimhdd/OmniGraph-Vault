---
quick_id: 260519-ijn
description: F1 — fix 5 test fixture drift TypeErrors after H4 removed min_depth kwarg
status: complete
date: 2026-05-19
---

# Summary: F1 — fixture drift cleanup post-H4

## What changed

5 stale `min_depth=...` kwargs removed from `ingest_from_db()` test calls.
Production code untouched.

| File | Sites | Edit |
|------|-------|------|
| `tests/unit/test_max_articles_hard_cap.py` | 4 | `topic="ai", min_depth=2, dry_run=False,` → `topic="ai", dry_run=False,` |
| `tests/unit/test_vision_worker.py` | 1 | `topic=["AI agents"], min_depth=1, dry_run=False` → `topic=["AI agents"], dry_run=False` |

Closes the fixture-drift gap identified during quick-260519-hwr (R1) full
unit regression — sister failure to the 2026-05-15 lesson #2 pattern
("test fixture not synced with production signature change silently masks
contract failure").

## Verification

| Stage | Command | Result |
|-------|---------|--------|
| Pre-change baseline | `pytest tests/unit/test_max_articles_hard_cap.py tests/unit/test_vision_worker.py -v` | **5 failed**, 9 passed ([log](../../.scratch/quick-f1-pre.log)) |
| Post-change targeted | `pytest tests/unit/test_max_articles_hard_cap.py tests/unit/test_vision_worker.py -v` | **14 passed** in 10.34s ([log](../../.scratch/quick-f1-post.log)) |
| Full unit regression | `pytest tests/unit/ -v` | 973 passed, 1 unrelated subprocess-timeout flake ([log](../../.scratch/quick-f1-full.log)) |

### Net delta vs R1's full run

- R1 full: 969 passed, **5 failed** (the 5 F1 fixed: 4× `test_max_articles_hard_cap` + 1× `test_vision_worker`)
- F1 full: **973 passed** (969 + 5 fixed = 974 — actually 973 because of the 1 subprocess flake), 1 failed

### Unrelated failure documented

`test_kol_scan_db_path_override.py::test_env_override_routes_to_custom_path[batch_classify_kol]`
fails in the full suite with `subprocess.TimeoutExpired: Command [...] timed out after 120 seconds`.
The test spawns a Python subprocess that imports `batch_classify_kol`; cold-import exceeded
the 120s subprocess timeout under full-suite system load (full-suite wall-clock 1:33:39 = 5619s).

**Verified F1-causally-independent**: ran in isolation, **passed in 3.32s**. F1 only deleted
`min_depth=...` kwargs from 2 unrelated test files; no code path connects to the kol_scan_db_path
override resolution. Filing as out-of-scope environmental flake.

## Files touched

- `tests/unit/test_max_articles_hard_cap.py` (4 line-changes — kwarg deletion only)
- `tests/unit/test_vision_worker.py` (1 line-change — kwarg deletion only)

No production code, no fixture-helper, no schema, no doc changes.

## Discipline

- explicit `git add tests/unit/test_max_articles_hard_cap.py tests/unit/test_vision_worker.py`
  per `feedback_git_add_explicit_in_parallel_quicks.md` (NEVER `-A`)
- NO `--amend` / `git reset` / force-push per `feedback_no_amend_in_concurrent_quicks.md`
- STATE.md edit limited to own quick row + Last activity line
- Single atomic forward-only commit on main
