---
plan: aim-3-2
phase: aim-3
subsystem: aliyun-systemd
tags: [systemd, aliyun, deploy, cutover, timers]
dependency_graph:
  requires: [aim-3-1]
  provides: [CUTOVER-01]
  affects: [aim-3-3, aim-3-4]
tech_stack:
  added: []
  patterns: [systemd-timer-utc-oncalendar, scp-tarball-deploy]
key_files:
  created:
    - .planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-01-deploy-evidence.md
  modified:
    - deploy/aliyun/systemd/omnigraph-*.timer (all 13 — UTC suffix added to OnCalendar)
decisions:
  - "UTC suffix mandatory on OnCalendar when Aliyun runs Asia/Shanghai (CST = UTC+8)"
  - "Tarball SCP approach (single connection) preferred over 26 individual scp calls"
  - "Re-enable --now on already-enabled timers is idempotent — safe to re-run"
metrics:
  duration: ~30min
  completed: 2026-05-24
  tasks_completed: 4
  files_modified: 14
---

# Phase aim-3 Plan 2: Deploy + enable 13 systemd units on Aliyun (CUTOVER-01)

**One-liner:** 26 systemd unit files (13 .service + 13 .timer) SCPed to Aliyun
`/etc/systemd/system/`, all 13 timers enabled+active with correct UTC OnCalendar
schedules, CUTOVER-01 evidence captured.

## What Was Done

Executed all 4 tasks of aim-3-2:

1. **Task 1 — SCP**: Verified 13+13 local artifacts from aim-3-1. Checked Aliyun for
   pre-existing omnigraph-* units (none found — first install). Created tarball of 26
   unit files (no README.md), SCPed to Aliyun, extracted to `/etc/systemd/system/`,
   fixed root:root ownership.

2. **Task 2 — daemon-reload + enable**: `systemctl daemon-reload` exit=0. All 13 timers
   enabled --now (symlinks created in `timers.target.wants/`). All 13 is-enabled=`enabled`,
   all 13 is-active=`active`.

3. **Task 3 — unit verification**: Verified 4 representative service files via `systemctl cat`:
   - `daily-ingest.service`: ExecStartPre cleanup_stuck_docs.py + correct ExecStart/Env/WD — PASS
   - `kol-scan.service`: correct ExecStart/Env/WD — PASS
   - `vertex-probe.service`: correct ExecStart/Env/WD — PASS
   - `kol-enrich.service`: ExecStart=/bin/true stub confirmed — PASS

4. **Task 4 — evidence + commit**: Created EVIDENCE/CUTOVER-01-deploy-evidence.md with
   full verbatim outputs. Committed with explicit `git add` (no -A).

## Acceptance Criteria Status

| Criterion | Status |
|---|---|
| 13 .service files on Aliyun | PASS |
| 13 .timer files on Aliyun | PASS |
| daemon-reload exit=0 | PASS |
| All 13 timers enabled | PASS |
| All 13 timers active | PASS |
| NEXT fire times match UTC schedule | PASS |
| Sample unit ExecStart/Env/WD verified | PASS |
| EVIDENCE/CUTOVER-01-deploy-evidence.md committed | PASS |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added UTC suffix to all 13 OnCalendar lines**

- **Found during:** Task 1/2 (after first enable, list-timers showed CST times 8h off)
- **Issue:** Aliyun runs Asia/Shanghai (CST = UTC+8). `OnCalendar=*-*-* 09:00:00` without
  UTC suffix is interpreted as 09:00 CST = 01:00 UTC — 8 hours early vs intended 09:00 UTC.
- **Fix:** Added ` UTC` suffix to all 13 `OnCalendar=` lines in `deploy/aliyun/systemd/*.timer`.
  Re-deployed second tarball, daemon-reload, re-enabled (idempotent). Verified all 13 NEXT
  times now match UTC schedule.
- **Files modified:** All 13 `deploy/aliyun/systemd/omnigraph-*.timer`
- **Commit:** d2f8fd5

## Decisions Made

1. **UTC suffix is mandatory** — any deployment to a non-UTC host requires explicit `UTC`
   suffix on OnCalendar. The aim-3 CONTEXT.md noted "ADT → UTC conversion: apply +3h to all
   schedules" but did not mention Aliyun's local timezone. This lesson is recorded.

2. **Tarball SCP** — one SSH connection for 26 files vs 26 individual scp calls. No
   measurable overhead difference at this scale, but cleaner.

3. **Timer re-enable idempotent** — `systemctl enable --now` on an already-enabled timer
   is idempotent; systemd detects the symlink exists and skips creation without error.

## Next Steps

- **aim-3-3**: kol_scan.db pre-cutover sync verification + Hermes jobs disable via operator
  prompt + CUTOVER-EVIDENCE.md
- First natural timer fires expected: `omnigraph-evening-ingest.timer` at 00:00 UTC
  (08:00 CST 2026-05-25)
- aim-3-4 will collect journald evidence after first natural fires

## Self-Check

Files created/modified:

- `.planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-01-deploy-evidence.md` — created
- `deploy/aliyun/systemd/omnigraph-*.timer` (all 13) — modified (UTC suffix)
- Commit `d2f8fd5` — verified via `git log --oneline -3`

## Self-Check: PASSED
