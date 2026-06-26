---
phase: quick-260626-jgp
plan: 01
subsystem: batch_scan_kol / systemd
tags: [kol-scan, staleness-partition, argparse, systemd, tdd]
dependency_graph:
  requires: []
  provides: [--max-accounts flag, staleness SELECT, 4-batch timers, retimed classify timer]
  affects: [batch_scan_kol.py, deploy/aliyun/systemd/]
tech_stack:
  added: []
  patterns: [behavior-anchor harness, version-safe SQLite ordering, systemd template units]
key_files:
  created:
    - tests/unit/test_scan_max_accounts.py
    - deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service
    - deploy/aliyun/systemd/omnigraph-kol-scan-batch@1.timer
    - deploy/aliyun/systemd/omnigraph-kol-scan-batch@2.timer
    - deploy/aliyun/systemd/omnigraph-kol-scan-batch@3.timer
    - deploy/aliyun/systemd/omnigraph-kol-scan-batch@4.timer
  modified:
    - batch_scan_kol.py
    - deploy/aliyun/systemd/omnigraph-kol-classify.timer
    - deploy/aliyun/systemd/omnigraph-kol-scan.timer
decisions:
  - "Version-safe staleness SQL: `(MAX(a.scanned_at) IS NULL) DESC` boolean ordering used instead of NULLS FIRST keyword; Aliyun SQLite version unknown"
  - "run() new param placed LAST after summary_json to preserve all existing keyword-arg call sites"
  - "Plan-checker advisory folded in: monkeypatch.setattr(batch_scan_kol.time, 'sleep', lambda *_a, **_k: None) added to tests (a) and (b) to avoid 5s per-account sleep accumulation"
metrics:
  duration_minutes: ~25
  tasks_completed: 2
  files_modified: 9
  completed_date: "2026-06-26"
---

# Quick 260626-jgp: KOL Scan 4-Batch Coverage Summary

KOL scan gains a `--max-accounts N` staleness-partition flag; 4 staggered systemd timers each call `--max-accounts 15` to guarantee 4×15=60 ≥ 58 accounts covered daily.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Add --max-accounts staleness path + tests (TDD) | 9887e87 | batch_scan_kol.py, tests/unit/test_scan_max_accounts.py |
| 2 | Author systemd repo unit copies | 9e70da2 | 5 new + 2 modified deploy/aliyun/systemd/ files |

## What Was Built

### Task 1: `--max-accounts` flag + staleness SELECT

`batch_scan_kol.py` `run()` gains a new last keyword param `max_accounts: int | None = None`.

- **Default path (`max_accounts is None`)**: byte-behavior-identical to before — `SELECT name, fakeid FROM accounts ORDER BY name` + unconditional `random.shuffle(rows)`. Zero truncation.
- **Staleness path (`max_accounts is not None`)**: version-safe LEFT JOIN + GROUP BY with `ORDER BY (MAX(a.scanned_at) IS NULL) DESC, MAX(a.scanned_at) ASC, acc.name ASC` — NULL-first (never-scanned), then oldest-scanned, then name tiebreak. No shuffle. Truncates to `rows[:max_accounts]`.
- `argparse`: `--max-accounts` type=int default=None, backward-compatible with all existing flags.

### Task 2: Systemd units

| File | Change |
|------|--------|
| `omnigraph-kol-scan-batch@.service` | NEW template: `--daily --max-accounts 15`, RuntimeMaxSec=1800, OnFailure alert chain |
| `omnigraph-kol-scan-batch@1.timer` | NEW: OnCalendar 01:30 UTC, Persistent=true, Unit=...@1.service, no Requires= |
| `omnigraph-kol-scan-batch@2.timer` | NEW: OnCalendar 05:30 UTC, Persistent=true, Unit=...@2.service, no Requires= |
| `omnigraph-kol-scan-batch@3.timer` | NEW: OnCalendar 11:00 UTC, Persistent=true, Unit=...@3.service, no Requires= |
| `omnigraph-kol-scan-batch@4.timer` | NEW: OnCalendar 15:30 UTC, Persistent=true, Unit=...@4.service, no Requires= |
| `omnigraph-kol-classify.timer` | MODIFIED: OnCalendar 11:15→16:00 UTC, Requires= line dropped from [Unit] |
| `omnigraph-kol-scan.timer` | MODIFIED: SUPERSEDED header comment prepended, body unchanged |

## Pytest Results

**Interpreter:** `/c/Users/huxxha/Desktop/OmniGraph-Vault/venv/Scripts/python.exe` (main repo venv — worktree has no venv; run via absolute path from main repo root)

**Command used:** `cd /c/Users/huxxha/Desktop/OmniGraph-Vault && python.exe -m pytest "<absolute-path-to-test-file>" -v`

**Result:** 4/4 PASSED

- `test_staleness_selection_null_first_then_oldest` PASSED
- `test_default_path_no_truncation` PASSED
- `test_argparse_max_accounts_int` PASSED
- `test_argparse_max_accounts_absent_is_none` PASSED

**Note on worktree / pytest path:** The git worktree at `agent-afa0d2516c133639b` is sparse — only changed files are present; `kol_config.py` (imported at module level by `batch_scan_kol.py`) lives only in the main repo. Running `pytest` from the worktree root with a relative path fails with `ModuleNotFoundError: No module named 'kol_config'`. The workaround is to run pytest from the main repo root (`cd /c/.../OmniGraph-Vault`) with the absolute path to the test file — this is the correct invocation and was what the plan's `venv/Scripts/python.exe -m pytest tests/unit/test_scan_max_accounts.py -v` intended (the plan assumes the worktree has a local venv or will be run from the right context).

## Deviations from Plan

### Plan-checker advisories folded in (both NON-BLOCKING)

**1. `time.sleep` patch in tests (a) and (b)**

The plan's `<plan_checker_advisories_to_honor>` block specified patching `time.sleep` to prevent 5s × N delays accumulating in the test suite. Applied `monkeypatch.setattr(batch_scan_kol.time, "sleep", lambda *_a, **_k: None)` in both `test_staleness_selection_null_first_then_oldest` and `test_default_path_no_truncation`. Suite runs in ~0.8s not ~30s.

**2. Resume-mode log imprecision (cosmetic only)**

As noted in the advisory: `total_accounts = len(rows)` on the staleness path reflects the truncated N (15), not the full account count. Left as-is per advisory — this is mutually-exclusive with batch cron usage (`--daily`, not `--resume`). No code added.

### No other deviations

All must_haves verified:
- Default path byte-behavior-identical: `SELECT name, fakeid FROM accounts ORDER BY name` + `random.shuffle(rows)` — confirmed by line 245+256 in batch_scan_kol.py and passing `test_default_path_no_truncation`
- Staleness SQL has no `NULLS FIRST` keyword (grep confirms)
- `shuffle` call is inside the `max_accounts is None` branch only (line 256)
- argparse backward-compatible (mutual-exclusion check, all existing flags unmodified)
- Template @.service: `--max-accounts 15`, `RuntimeMaxSec=1800`, `OnFailure=omnigraph-kol-scan-alert.service` all verified
- 4 batch timers: no `Requires=` in any (grep -L confirms all 4)
- classify.timer: retimed to 16:00 UTC, Requires= removed
- scan.timer: SUPERSEDED header prepended, file retained
- Scope: only the 9 named files modified (git diff HEAD~2..HEAD confirms)

## Commits

- `9887e87` feat(scan): add --max-accounts staleness-partition path to batch_scan_kol (260626-jgp)
- `9e70da2` chore(systemd): 4-batch KOL scan timers + retime classify 16:00 UTC (260626-jgp)

Both atomic, forward-only, explicit `git add <files>`, NOT pushed (orchestrator handles Aliyun rollout in Phase 2).

## Known Stubs

None. This plan has no UI components and no deferred data wiring.

## Self-Check

- [x] `batch_scan_kol.py` exists and modified
- [x] `tests/unit/test_scan_max_accounts.py` created (4 tests GREEN)
- [x] `deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service` created
- [x] `deploy/aliyun/systemd/omnigraph-kol-scan-batch@{1,2,3,4}.timer` created (4 files)
- [x] `deploy/aliyun/systemd/omnigraph-kol-classify.timer` modified (16:00, no Requires=)
- [x] `deploy/aliyun/systemd/omnigraph-kol-scan.timer` modified (SUPERSEDED header)
- [x] Commits 9887e87 and 9e70da2 verified in git log
