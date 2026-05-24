---
phase: aim-3
plan: aim-3-1
subsystem: deploy/aliyun/systemd
tags: [systemd, aliyun, cutover, ingest, cron-migration]
dependency_graph:
  requires: [aim-2]
  provides: [deploy/aliyun/systemd/*.service, deploy/aliyun/systemd/*.timer]
  affects: [aim-3-2]
tech_stack:
  added: [systemd unit files]
  patterns: [systemd service+timer pairs, ExecStartPre for pre-flight cleanup, EnvironmentFile injection]
key_files:
  created:
    - deploy/aliyun/systemd/omnigraph-kol-zombie-cleanup.service
    - deploy/aliyun/systemd/omnigraph-kol-zombie-cleanup.timer
    - deploy/aliyun/systemd/omnigraph-kol-scan.service
    - deploy/aliyun/systemd/omnigraph-kol-scan.timer
    - deploy/aliyun/systemd/omnigraph-kol-classify.service
    - deploy/aliyun/systemd/omnigraph-kol-classify.timer
    - deploy/aliyun/systemd/omnigraph-kol-enrich.service
    - deploy/aliyun/systemd/omnigraph-kol-enrich.timer
    - deploy/aliyun/systemd/omnigraph-rss-fetch.service
    - deploy/aliyun/systemd/omnigraph-rss-fetch.timer
    - deploy/aliyun/systemd/omnigraph-rss-rescrape.service
    - deploy/aliyun/systemd/omnigraph-rss-rescrape.timer
    - deploy/aliyun/systemd/omnigraph-rss-layer2-classify.service
    - deploy/aliyun/systemd/omnigraph-rss-layer2-classify.timer
    - deploy/aliyun/systemd/omnigraph-daily-ingest.service
    - deploy/aliyun/systemd/omnigraph-daily-ingest.timer
    - deploy/aliyun/systemd/omnigraph-daily-digest.service
    - deploy/aliyun/systemd/omnigraph-daily-digest.timer
    - deploy/aliyun/systemd/omnigraph-reconcile.service
    - deploy/aliyun/systemd/omnigraph-reconcile.timer
    - deploy/aliyun/systemd/omnigraph-afternoon-ingest.service
    - deploy/aliyun/systemd/omnigraph-afternoon-ingest.timer
    - deploy/aliyun/systemd/omnigraph-evening-ingest.service
    - deploy/aliyun/systemd/omnigraph-evening-ingest.timer
    - deploy/aliyun/systemd/omnigraph-vertex-probe.service
    - deploy/aliyun/systemd/omnigraph-vertex-probe.timer
    - deploy/aliyun/systemd/README.md
  modified: []
decisions:
  - venv-aim1 (not venv) for all Python ExecStart lines
  - No tmux in any unit file — systemd is the process manager, no inactivity ceiling
  - omnigraph-kol-enrich.service is a stub (/bin/true) per FINDING 6
  - ExecStartPre cleanup_stuck_docs on the 3 ingest units only
  - Persistent=true on all timers for missed-fire recovery
metrics:
  duration: ~15min
  completed: 2026-05-24
  tasks: 4
  files: 27
---

# Phase aim-3 Plan aim-3-1: Author 26 systemd unit files (CUTOVER-01 part 1) Summary

## One-liner

26 systemd unit files (13 .service + 13 .timer) authoring all Aliyun ingest cron replacements with venv-aim1 Python, UTC schedules, ExecStartPre cleanup, and kol-enrich stub.

## What Was Built

Created `deploy/aliyun/systemd/` with 26 unit files and a README.md (27 files total) representing the complete systemd replacement for the 13 enabled Hermes agent-cron ingest jobs.

### Service file characteristics (all 13)

- `[Unit]` block: `After=network-online.target`, `Wants=network-online.target`
- `[Service]` block: `Type=simple`, `User=root`, `WorkingDirectory=/root/OmniGraph-Vault`, `EnvironmentFile=/root/.hermes/.env`, `StandardOutput=journal`, `StandardError=journal`
- `[Install]` block: `WantedBy=multi-user.target`
- All Python ExecStart lines use `/root/OmniGraph-Vault/venv-aim1/bin/python` (Python 3.11 ingest venv, NOT kb-api venv)

### Timer file characteristics (all 13)

- `OnCalendar=` in UTC (ADT+3h conversion applied to all Hermes ADT schedules)
- `Persistent=true` on all timers (missed-fire recovery on reboot/maintenance)
- `Requires=<matching-service>.service`
- `WantedBy=timers.target`

### Ingest units (3 of 13) — ExecStartPre

`omnigraph-daily-ingest`, `omnigraph-afternoon-ingest`, `omnigraph-evening-ingest` each include:

```ini
ExecStartPre=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/scripts/cleanup_stuck_docs.py --all-failed
```

This resets stuck articles before each ingest batch, mirroring the pre-existing behavior in `scripts/cron_daily_ingest.sh`.

### kol-enrich stub

`omnigraph-kol-enrich.service` uses `ExecStart=/bin/true` (FINDING 6: no standalone batch enrich script exists in the repo). The comment block in the file explains the gap. The timer fires on schedule, proving the slot; activating real enrich logic is a one-line edit.

## Sanity Greps (all passed)

| Check | Expected | Result |
|---|---|---|
| Total file count | 27 | 27 |
| `.service` file count | 13 | 13 |
| `.timer` file count | 13 | 13 |
| `grep -l "venv/bin/python" *.service` (kb-api venv leak) | 0 | 0 |
| `grep -l "venv-aim1/bin/python" *.service` | 12 | 12 |
| `grep -r "tmux" *.service *.timer` | 0 | 0 |
| `grep -l "EnvironmentFile=/root/.hermes/.env" *.service` | 13 | 13 |
| `grep -l "ExecStartPre" *.service` | 3 | 3 |
| `grep -l "OnCalendar=" *.timer` | 13 | 13 |

## Deviations from Plan

None — plan executed exactly as written.

The "tmux" grep on `deploy/aliyun/systemd/` returned matches in `README.md` prose (the section titled "No tmux" explaining why tmux is not used). The plan's intent was no tmux in unit files; unit files themselves are clean. Sanity check was verified with `grep -r "tmux" *.service *.timer` returning 0 matches.

## Commit

- `5b5a313`: `feat(aim-3): author 26 systemd unit files for Aliyun cutover (CUTOVER-01 part 1)`

## Self-Check

All 27 files verified to exist at `deploy/aliyun/systemd/`. Commit `5b5a313` verified in `git log`. Working tree clean post-commit.

## Self-Check: PASSED
