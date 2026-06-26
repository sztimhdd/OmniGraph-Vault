---
phase: quick-260626-jgp
verified: 2026-06-26T00:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Quick 260626-jgp: KOL Scan 4-Batch Coverage Verification Report

**Phase Goal:** Add backward-compatible `--max-accounts N` + version-safe staleness ordering to `batch_scan_kol.py`, plus author systemd repo unit copies (template @.service + 4 batch timers + retimed classify timer + superseded-header on old scan timer) under `deploy/aliyun/systemd/`. Enable 58/58 daily KOL account coverage via 4 staggered staleness-partitioned cron batches.

**Verified:** 2026-06-26
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Default path (max_accounts is None) byte-behavior-identical — SELECT ORDER BY name + unconditional random.shuffle preserved, no truncation | VERIFIED | `batch_scan_kol.py` lines 245–256: `if max_accounts is None:` branch contains `SELECT name, fakeid FROM accounts ORDER BY name` + `random.shuffle(rows)`. Shuffle is NOT present in else branch. `test_default_path_no_truncation` PASSED (all 6 seeded accounts scanned). |
| 2 | Staleness path selects staleest N NULL-first, no shuffle, truncates rows[:max_accounts] | VERIFIED | `batch_scan_kol.py` lines 257–272: else branch uses LEFT JOIN + GROUP BY with `ORDER BY (MAX(a.scanned_at) IS NULL) DESC, MAX(a.scanned_at) ASC, acc.name ASC`, then `rows = rows[:max_accounts]`. No shuffle in else branch. `test_staleness_selection_null_first_then_oldest` PASSED (Alpha, Beta, Charlie in exact staleness order). |
| 3 | Version-safe SQL — `(MAX(a.scanned_at) IS NULL) DESC` used; `NULLS FIRST` keyword absent from all SQL code | VERIFIED | `grep -n "NULLS FIRST" batch_scan_kol.py` returns ONLY lines 260–261 which are comments (`NOT the NULLS FIRST keyword`). The actual ORDER BY clause uses the boolean-cast pattern. |
| 4 | Backward-compatible argparse — `--max-accounts type=int default=None`, threaded to run() via keyword | VERIFIED | `batch_scan_kol.py` line 359: `parser.add_argument("--max-accounts", type=int, default=None, ...)`. Line 373: `max_accounts=args.max_accounts,` in run() call. `test_argparse_max_accounts_int` (gets 15) + `test_argparse_max_accounts_absent_is_none` (gets None) + `daily` kwarg also asserted: all PASSED. |
| 5 | Template @.service: ExecStart has `--max-accounts 15`, RuntimeMaxSec=1800, OnFailure=omnigraph-kol-scan-alert.service kept, correct boilerplate | VERIFIED | File `deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service` confirmed: ExecStart line includes `--daily --max-accounts 15`, RuntimeMaxSec=1800 on separate line, OnFailure=omnigraph-kol-scan-alert.service in [Unit], Type=simple/User=root/WorkingDirectory/EnvironmentFile/After+Wants network-online.target/venv-aim1 python path — all present. |
| 6 | Four lean batch timers @1..@4: no Requires=, correct OnCalendar UTC (01:30/05:30/11:00/15:30), Unit=omnigraph-kol-scan-batch@N.service, WantedBy=timers.target | VERIFIED | All 4 timer files read and confirmed. `grep -n "Requires=" @1..@4.timer` returned exit 1 (no matches). OnCalendar values: @1=01:30:00 UTC, @2=05:30:00 UTC, @3=11:00:00 UTC, @4=15:30:00 UTC. Unit= lines instance-correct in each. |
| 7 | omnigraph-kol-classify.timer retimed 16:00 UTC + Requires= dropped | VERIFIED | File confirms: `OnCalendar=*-*-* 16:00:00 UTC`, [Unit] section contains only Description (no Requires= line), Persistent=true kept. |
| 8 | omnigraph-kol-scan.timer has SUPERSEDED header, NOT deleted | VERIFIED | File first line: `# SUPERSEDED 2026-06-27 by omnigraph-kol-scan-batch@{1..4}.timer (4-batch staleness coverage). Disabled on Aliyun; definition retained for reference.` Body (Requires=omnigraph-kol-scan.service, OnCalendar 11:00 UTC) unchanged. |
| 9 | Scope: ONLY batch_scan_kol.py + test + 7 deploy/aliyun/systemd/ files changed from baseline | VERIFIED | `git diff 2435e2c..HEAD --name-only` returns exactly 9 files: `batch_scan_kol.py`, `tests/unit/test_scan_max_accounts.py`, `deploy/aliyun/systemd/omnigraph-kol-classify.timer`, `deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service`, `deploy/aliyun/systemd/omnigraph-kol-scan-batch@{1,2,3,4}.timer`, `deploy/aliyun/systemd/omnigraph-kol-scan.timer`. No spiders/, no ingest units, no classify .service, no -alert/-refresh/-tunnel edits. |

**Score:** 9/9 truths verified

---

## Pytest Results (Behavioral Spot-Check)

Command: `venv/Scripts/python.exe -m pytest tests/unit/test_scan_max_accounts.py -v`

| Test | Status |
|------|--------|
| `test_staleness_selection_null_first_then_oldest` | PASSED |
| `test_default_path_no_truncation` | PASSED |
| `test_argparse_max_accounts_int` | PASSED |
| `test_argparse_max_accounts_absent_is_none` | PASSED |

**Result: 4/4 PASSED in 0.74s**

---

## Required Artifacts

| Artifact | Status | Details |
|----------|--------|---------|
| `batch_scan_kol.py` | VERIFIED | run() has `max_accounts: int \| None = None` as last keyword param; staleness SELECT + truncation in else branch; shuffle in if-None branch only; argparse flag wired |
| `tests/unit/test_scan_max_accounts.py` | VERIFIED | 4 behavior-anchor tests; real SQLite seeding via `init_db`; no SQL string matching; `time.sleep` patched; all 4 GREEN |
| `deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service` | VERIFIED | Template unit with `--max-accounts 15`, RuntimeMaxSec=1800, OnFailure alert chain |
| `deploy/aliyun/systemd/omnigraph-kol-scan-batch@1.timer` | VERIFIED | 01:30 UTC, no Requires=, Unit=@1.service |
| `deploy/aliyun/systemd/omnigraph-kol-scan-batch@2.timer` | VERIFIED | 05:30 UTC, no Requires=, Unit=@2.service |
| `deploy/aliyun/systemd/omnigraph-kol-scan-batch@3.timer` | VERIFIED | 11:00 UTC, no Requires=, Unit=@3.service |
| `deploy/aliyun/systemd/omnigraph-kol-scan-batch@4.timer` | VERIFIED | 15:30 UTC, no Requires=, Unit=@4.service |
| `deploy/aliyun/systemd/omnigraph-kol-classify.timer` | VERIFIED | 16:00 UTC, Requires= dropped |
| `deploy/aliyun/systemd/omnigraph-kol-scan.timer` | VERIFIED | SUPERSEDED header prepended, body retained |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `batch_scan_kol.py:main()` | `batch_scan_kol.py:run()` | `max_accounts=args.max_accounts` kwarg at line 373 | WIRED | `test_argparse_max_accounts_int` confirms value 15 threads through; `test_argparse_max_accounts_absent_is_none` confirms None default threads through |
| `omnigraph-kol-scan-batch@N.timer` | `omnigraph-kol-scan-batch@.service` | `Unit=omnigraph-kol-scan-batch@N.service` in [Timer] | WIRED | All 4 timers have correctly-instanced Unit= lines |

---

## Anti-Patterns Found

None. No TODO/FIXME/placeholder comments in modified files. No empty implementations. No hardcoded stub returns. The staleness SQL is substantive (LEFT JOIN + GROUP BY + multi-key ORDER BY). All 4 timer files are lean by design (no Requires=, per the PLAN's memory guidance on `aliyun_drift_recovery_260528 v4`).

---

## Git Commits

| Commit | Message |
|--------|---------|
| `e2995d0` | feat(scan): add --max-accounts staleness-partition path to batch_scan_kol (260626-jgp) |
| `9928661` | chore(systemd): 4-batch KOL scan timers + retime classify 16:00 UTC (260626-jgp) |

Both atomic, forward-only, explicit `git add <files>`, NOT pushed. Orchestrator handles Aliyun rollout in Phase 2.

---

## Human Verification Required

None for Phase 1 (repo artifacts + local pytest only). Phase 2 Aliyun rollout (install units, daemon-reload, enable/disable, 58/58 DB bootstrap validation) is operator work outside this verification scope.

---

_Verified: 2026-06-26_
_Verifier: Claude (gsd-verifier)_
