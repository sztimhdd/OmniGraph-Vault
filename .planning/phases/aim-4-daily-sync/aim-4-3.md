---
plan_id: aim-4-3
phase: aim-4
wave: 3
depends_on:
  - aim-4-2
requirements_addressed:
  - SYNC-02
  - SYNC-04
files_modified:
  - deploy/hermes/systemd/omnigraph-daily-pull.service
  - deploy/hermes/systemd/omnigraph-daily-pull.timer
  - deploy/hermes/systemd/README.md
  - .planning/phases/aim-4-daily-sync/aim-4-3-EVIDENCE.md
autonomous: true
t_shirt: S
---

# aim-4-3 — Hermes systemd timer install (SYNC-02 + SYNC-04 journald)

## Goal

Author canonical, version-controlled systemd unit files for the
Hermes-side daily pull from Aliyun, then deploy them to Hermes
(`/etc/systemd/system/`), enable + start the timer, and verify
`systemctl list-timers` shows the next 02:00 ADT (05:00 UTC) fire.

This plan covers SYNC-02 (Hermes-side daily-pull cron installed,
schedule 02:00 ADT, output lands at `~/.hermes/omonigraph-vault/`,
Hermes net cron count: 11 → 1) and the journald-wiring portion of
SYNC-04 (`StandardOutput=journal` + `StandardError=journal` so
`journalctl -u omnigraph-daily-pull.service` captures retry attempts +
ERROR lines from `scripts/sync-from-aliyun.sh`).

The schedule choice 02:00 ADT = 05:00 UTC defends against Aliyun's
21:00 ADT evening-ingest finishing (5h budget). Per CONTEXT.md
FINDING 3, this is a systemd timer (Hermes WSL2 has systemd), NOT a
crontab line and NOT a Hermes-agent-cron registry entry.

This plan is autonomous (agent-only). Hermes user `sztimhdd` does NOT
have passwordless sudo by default; the systemd unit deployment uses
`sudo` (which may require Hermes account password to be cached, OR may
require user-side authorization). The plan documents both paths in the
abort/rollback section.

## Acceptance criteria

1. Repo files committed:
   - `deploy/hermes/systemd/omnigraph-daily-pull.service`
   - `deploy/hermes/systemd/omnigraph-daily-pull.timer`
   - `deploy/hermes/systemd/README.md`
2. `.service` file content matches the template in `<action>` exactly:
   - `Type=oneshot`
   - `User=sztimhdd`
   - `WorkingDirectory=/home/sztimhdd/OmniGraph-Vault`
   - `ExecStart=/home/sztimhdd/OmniGraph-Vault/scripts/sync-from-aliyun.sh`
   - `StandardOutput=journal`
   - `StandardError=journal`
   - `After=network-online.target`
   - `Wants=network-online.target`
3. `.timer` file content:
   - `OnCalendar=*-*-* 05:00:00` (UTC = 02:00 ADT)
   - `Persistent=true` (re-fire if Hermes was offline at fire time)
   - `Requires=omnigraph-daily-pull.service`
   - `WantedBy=timers.target`
4. README.md describes deploy / enable / verify commands and the
   ADT→UTC schedule conversion.
5. On Hermes:
   - `/etc/systemd/system/omnigraph-daily-pull.service` exists with
     identical content to repo file.
   - `/etc/systemd/system/omnigraph-daily-pull.timer` exists with
     identical content.
   - `systemctl is-enabled omnigraph-daily-pull.timer` returns
     `enabled`.
   - `systemctl is-active omnigraph-daily-pull.timer` returns `active`.
   - `systemctl list-timers omnigraph-daily-pull.timer --no-pager`
     shows next fire at next `*-*-* 05:00:00 UTC`.
   - `journalctl -u omnigraph-daily-pull.service --since "5 minutes ago" --no-pager`
     is empty (timer hasn't fired yet — not a regression).
6. Hermes net cron count check (SYNC-02 wording "11 → 1"):
   - On Hermes: `crontab -l 2>/dev/null | grep -E "ingest|kol_scan|rss" | wc -l`
     returns 0 (per aim-3 cutover).
   - On Hermes: count of OmniGraph-related Hermes-agent-cron entries
     in `~/.hermes/cron/jobs.json` related to ingest = 0 (verified via
     aim-3 evidence).
   - On Hermes: `systemctl list-timers omnigraph-* --no-pager` shows
     exactly 1 timer (`omnigraph-daily-pull.timer`).
   - Net Hermes-side scheduled OmniGraph job count = 1 (per SYNC-02
     "11 → 1"). Documented in evidence.
7. Manual fire test (optional but recommended for SYNC-04 journald
   wiring proof):
   - On Hermes: `sudo systemctl start omnigraph-daily-pull.service`
     triggers a real run.
   - `journalctl -u omnigraph-daily-pull.service -f --no-pager` shows
     log lines from `scripts/sync-from-aliyun.sh` (e.g., "rsync ...",
     "sync OK on attempt 1").
   - Service exits 0 (`systemctl status` shows `Result: success`).
8. Evidence markdown
   `.planning/phases/aim-4-daily-sync/aim-4-3-EVIDENCE.md` records all
   verification outputs.
9. Single forward-only commit on `main` containing the 3 repo files +
   evidence file. Conventional commit message:
   `feat(aim-4): Hermes omnigraph-daily-pull systemd timer (SYNC-02,SYNC-04)`.

## Task list

### Task 1 — Author 2 systemd unit files + README in repo

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-4-daily-sync\aim-4-CONTEXT.md`
  lines 252-288 (Hermes systemd unit templates with verbatim ini content)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-3-cutover\aim-3-1.md`
  lines 102-160 (Aliyun systemd unit pattern — for parallelism in style)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\REQUIREMENTS-Aliyun-Ingest-Migration-v1.md`
  lines 72, 74 (SYNC-02 + SYNC-04 verbatim)

**`<acceptance_criteria>`**
- `deploy/hermes/systemd/` directory exists in repo.
- The 3 files (`omnigraph-daily-pull.service`,
  `omnigraph-daily-pull.timer`, `README.md`) exist with content
  matching templates below.
- `grep -c 'OnCalendar=\*-\*-\* 05:00:00' deploy/hermes/systemd/omnigraph-daily-pull.timer`
  returns 1.
- `grep -c 'ExecStart=/home/sztimhdd/OmniGraph-Vault/scripts/sync-from-aliyun.sh' deploy/hermes/systemd/omnigraph-daily-pull.service`
  returns 1.
- `grep -c 'StandardError=journal' deploy/hermes/systemd/omnigraph-daily-pull.service`
  returns 1.

**`<action>`**

Write the 3 files via the Write tool.

**`deploy/hermes/systemd/omnigraph-daily-pull.service`:**

```ini
[Unit]
Description=OmniGraph daily pull from Aliyun
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=sztimhdd
WorkingDirectory=/home/sztimhdd/OmniGraph-Vault
ExecStart=/home/sztimhdd/OmniGraph-Vault/scripts/sync-from-aliyun.sh
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**`deploy/hermes/systemd/omnigraph-daily-pull.timer`:**

```ini
[Unit]
Description=OmniGraph daily pull from Aliyun timer
Requires=omnigraph-daily-pull.service

[Timer]
OnCalendar=*-*-* 05:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

**`deploy/hermes/systemd/README.md`:**

```markdown
# Hermes systemd unit — daily pull from Aliyun

These two files (`omnigraph-daily-pull.service` and
`omnigraph-daily-pull.timer`) replace the 11 ingest-related Hermes-agent-cron
entries that aim-3 cutover retired (CUTOVER-03). They install the single
new daily-pull job (SYNC-02 "11 → 1" net cron count).

## Schedule

| Local | UTC OnCalendar |
| --- | --- |
| 02:00 ADT | `*-*-* 05:00:00` |

ADT (Atlantic Daylight Time) = UTC-3. Hermes WSL2 uses UTC system clock;
the OnCalendar value is in UTC. Choice rationale: Aliyun evening-ingest
fires at 21:00 ADT (00:00 UTC); 5h budget covers ingest finishing +
buffer. Pulling at 02:00 ADT captures the freshest snapshot.

## Deployment

```bash
# Copy to /etc/systemd/system/
sudo cp deploy/hermes/systemd/omnigraph-daily-pull.service /etc/systemd/system/
sudo cp deploy/hermes/systemd/omnigraph-daily-pull.timer /etc/systemd/system/

# Reload + enable + start
sudo systemctl daemon-reload
sudo systemctl enable --now omnigraph-daily-pull.timer

# Verify
systemctl list-timers omnigraph-daily-pull.timer --no-pager
systemctl is-enabled omnigraph-daily-pull.timer
systemctl is-active omnigraph-daily-pull.timer
```

## Verification post-deploy

```bash
# Manual fire (skip waiting for next 02:00 ADT)
sudo systemctl start omnigraph-daily-pull.service

# Watch journald output (Ctrl+C to stop)
journalctl -u omnigraph-daily-pull.service -f --no-pager

# Confirm exit success
systemctl status omnigraph-daily-pull.service --no-pager
```

## SYNC-04 retry / marker observability

The retry loop and marker-file logic live IN
`scripts/sync-from-aliyun.sh` (per FINDING 7). The systemd unit captures
all stdout / stderr via `StandardOutput=journal` /
`StandardError=journal`. To inspect:

```bash
# Last 24h of pull logs
journalctl -u omnigraph-daily-pull.service --since "24 hours ago" --no-pager

# Stale failure marker (>48h = §6 Risk row 8 alert)
ls -la /tmp/aliyun-sync-failed-*
```

## References

- `.planning/phases/aim-4-daily-sync/aim-4-CONTEXT.md`
- `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` SYNC-02 + SYNC-04
- `scripts/sync-from-aliyun.sh` (the script this unit calls)
```

### Task 2 — Deploy units to Hermes + enable timer

**`<read_first>`**
- `deploy/hermes/systemd/README.md` (just authored — for deploy command pattern)
- Memory `hermes_ssh.md` (Hermes connection details)
- aim-4-2-EVIDENCE.md (proves `scripts/sync-from-aliyun.sh` exists on
  Hermes — confirm via `ssh ... 'ls -la ~/OmniGraph-Vault/scripts/sync-from-aliyun.sh'`
  before enabling timer; otherwise the timer would fire and fail.)

**`<acceptance_criteria>`**
- `scripts/sync-from-aliyun.sh` exists at
  `/home/sztimhdd/OmniGraph-Vault/scripts/sync-from-aliyun.sh` on Hermes.
  (NOTE: aim-4-2 only smoke-tested via /tmp staging; this plan must
  ensure Hermes pulls the committed version via `git pull`. If Hermes
  `git pull` is blocked by HTTPS-PAT issue per
  `aliyun_vitaclaw_ssh.md` git auth caveat, fall back to
  `scp` from corp dev box.)
- Both unit files exist at `/etc/systemd/system/omnigraph-daily-pull.{service,timer}`
  on Hermes with identical content to the repo files.
- `systemctl daemon-reload` succeeded.
- `systemctl enable --now omnigraph-daily-pull.timer` succeeded.
- `systemctl is-enabled omnigraph-daily-pull.timer` returns `enabled`.
- `systemctl is-active omnigraph-daily-pull.timer` returns `active`.
- `systemctl list-timers omnigraph-daily-pull.timer --no-pager` shows
  next fire at the next `*-*-* 05:00:00 UTC` after current time.

**`<action>`**

```bash
# Step 1: Ensure Hermes has the latest scripts/sync-from-aliyun.sh
# committed in aim-4-2. Try git pull first; fall back to scp on auth fail.

ssh -p 49221 sztimhdd@ohca.ddns.net 'set -e; \
  cd ~/OmniGraph-Vault; \
  git fetch origin 2>&1 | head -5; \
  git status -sb; \
  ls -la scripts/sync-from-aliyun.sh 2>/dev/null || echo SCRIPT_MISSING'

# If `git pull` hangs (per aliyun_vitaclaw_ssh.md HTTPS-PAT caveat),
# scp the script directly from corp dev box:
# scp -P 49221 scripts/sync-from-aliyun.sh \
#   sztimhdd@ohca.ddns.net:~/OmniGraph-Vault/scripts/sync-from-aliyun.sh

ssh -p 49221 sztimhdd@ohca.ddns.net 'set -e; \
  cd ~/OmniGraph-Vault; \
  git pull --ff-only 2>&1 | head -10 || echo PULL_FAILED_FALLBACK_SCP_NEEDED'

# If pull failed: from local Bash session
# scp -P 49221 scripts/sync-from-aliyun.sh \
#   sztimhdd@ohca.ddns.net:/home/sztimhdd/OmniGraph-Vault/scripts/sync-from-aliyun.sh

# Step 2: Stage unit files via scp from corp dev box (avoids needing
# Hermes to git-pull the deploy/hermes/systemd/ tree if pull is broken)

scp -P 49221 deploy/hermes/systemd/omnigraph-daily-pull.service \
  sztimhdd@ohca.ddns.net:/tmp/omnigraph-daily-pull.service
scp -P 49221 deploy/hermes/systemd/omnigraph-daily-pull.timer \
  sztimhdd@ohca.ddns.net:/tmp/omnigraph-daily-pull.timer

# Step 3: Move into place + enable + start (via sudo on Hermes)
ssh -p 49221 sztimhdd@ohca.ddns.net 'set -e; \
  sudo cp /tmp/omnigraph-daily-pull.service /etc/systemd/system/; \
  sudo cp /tmp/omnigraph-daily-pull.timer /etc/systemd/system/; \
  sudo systemctl daemon-reload; \
  sudo systemctl enable --now omnigraph-daily-pull.timer; \
  echo "=== is-enabled ==="; \
  sudo systemctl is-enabled omnigraph-daily-pull.timer; \
  echo "=== is-active ==="; \
  sudo systemctl is-active omnigraph-daily-pull.timer; \
  echo "=== list-timers ==="; \
  sudo systemctl list-timers omnigraph-daily-pull.timer --no-pager; \
  rm -f /tmp/omnigraph-daily-pull.service /tmp/omnigraph-daily-pull.timer'
```

If `sudo` requires interactive password and BatchMode-style ssh fails:
the user must authorize via the connected terminal. Treat this as
expected. Document the gating in evidence.

### Task 3 — Net cron count audit + manual fire smoke

**`<read_first>`**
- aim-3 SUMMARY (CUTOVER-03 evidence — Hermes ingest crontab cleared)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\STATE-Aliyun-Ingest-Migration-v1.md`
  lines 78-90 (Hermes operational state pre/post cutover)

**`<acceptance_criteria>`**
- On Hermes: `crontab -l 2>/dev/null | grep -E "ingest|kol_scan|rss" | wc -l` returns 0.
- On Hermes: `systemctl list-timers omnigraph-* --no-pager` shows
  exactly 1 timer (`omnigraph-daily-pull.timer`). If aim-3 erroneously
  installed Aliyun systemd units on Hermes (it should NOT have — aim-3
  units live on Aliyun), this count would be > 1; investigate and
  document.
- Manual fire `sudo systemctl start omnigraph-daily-pull.service` →
  service runs to completion → `systemctl status` shows
  `Active: inactive (dead)` with `Result: success`.
- `journalctl -u omnigraph-daily-pull.service --since "10 minutes ago" --no-pager`
  shows `scripts/sync-from-aliyun.sh` log lines (the `[ts] rsync ...`
  patterns from the script).

**`<action>`**

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net 'set -e; \
  echo "=== Crontab ingest line count ==="; \
  crontab -l 2>/dev/null | grep -cE "ingest|kol_scan|rss" || echo 0; \
  echo "=== systemctl list-timers omnigraph-* ==="; \
  sudo systemctl list-timers --no-pager 2>&1 | grep omnigraph || echo NONE; \
  echo "=== Manual fire smoke ==="; \
  sudo systemctl start omnigraph-daily-pull.service; \
  sleep 5; \
  echo "=== status ==="; \
  sudo systemctl status omnigraph-daily-pull.service --no-pager 2>&1 | head -20; \
  echo "=== journalctl tail ==="; \
  sudo journalctl -u omnigraph-daily-pull.service --since "10 minutes ago" --no-pager | tail -30'
```

If the manual fire is in-progress (rsync still running), wait via
`while sudo systemctl is-active omnigraph-daily-pull.service >/dev/null;
do sleep 30; done` (max 30 min — the smoke in aim-4-2 already proved
~30 min cold-cache; this is warm-cache so should be < 5 min).

Capture all stdout for evidence.

### Task 4 — Author evidence + commit

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\CLAUDE.md` Lessons Learned 2026-05-06 #5 + 2026-05-15 #1
- Memory `feedback_git_add_explicit_in_parallel_quicks.md`

**`<acceptance_criteria>`**
- `.planning/phases/aim-4-daily-sync/aim-4-3-EVIDENCE.md` exists with
  all stdout from Task 2 + Task 3.
- Single forward-only commit on `main` with the 3 unit/README files +
  evidence file (4 paths total).
- Commit message:
  `feat(aim-4): Hermes omnigraph-daily-pull systemd timer (SYNC-02,SYNC-04)`.
- `git status` clean post-commit.

**`<action>`**

Write the evidence file:

```markdown
# aim-4-3 — Hermes systemd timer install evidence

**Timestamp:** <ts>
**Plan:** aim-4-3
**REQs:** SYNC-02, SYNC-04 (journald)
**Status:** PASS

## Repo files committed

- `deploy/hermes/systemd/omnigraph-daily-pull.service`
- `deploy/hermes/systemd/omnigraph-daily-pull.timer`
- `deploy/hermes/systemd/README.md`

## Hermes deployment

- `/etc/systemd/system/omnigraph-daily-pull.service`: installed
- `/etc/systemd/system/omnigraph-daily-pull.timer`: installed
- `daemon-reload`: succeeded
- `systemctl is-enabled omnigraph-daily-pull.timer`: enabled
- `systemctl is-active omnigraph-daily-pull.timer`: active
- `systemctl list-timers omnigraph-daily-pull.timer`: <stdout>

## Net cron count

- `crontab -l | grep -cE "ingest|kol_scan|rss"`: 0
- `systemctl list-timers omnigraph-* --no-pager`: 1 entry (`omnigraph-daily-pull.timer`)
- Net Hermes-side OmniGraph scheduled jobs: 1 (per SYNC-02 "11 → 1")

## Manual fire smoke

- `sudo systemctl start omnigraph-daily-pull.service`: triggered
- `systemctl status` Result: success
- `journalctl -u omnigraph-daily-pull.service` tail: <stdout showing rsync log lines>
- Exit code (via `systemctl show`): 0

## References

- aim-4 CONTEXT.md §"Hermes systemd units"
- REQUIREMENTS SYNC-02, SYNC-04
```

Commit:

```bash
git add deploy/hermes/systemd/omnigraph-daily-pull.service \
        deploy/hermes/systemd/omnigraph-daily-pull.timer \
        deploy/hermes/systemd/README.md \
        .planning/phases/aim-4-daily-sync/aim-4-3-EVIDENCE.md
git status   # confirm only the 4 files staged
git commit -m "feat(aim-4): Hermes omnigraph-daily-pull systemd timer (SYNC-02,SYNC-04)"
git log -1 --name-only
```

## Abort/rollback protocol

| Condition | Action |
| --- | --- |
| `scripts/sync-from-aliyun.sh` not on Hermes | aim-4-2 didn't reach Hermes via `git pull`. Fallback: `scp` from corp dev box, then re-validate. |
| `git pull` on Hermes hangs (HTTPS-PAT prompt) | Skip `git pull`; scp the deploy/hermes/systemd/ files directly. Document fallback in evidence. |
| `sudo systemctl daemon-reload` fails with "Failed to load unit file" | Inspect `/etc/systemd/system/omnigraph-daily-pull.service` for syntax errors. Common: tab vs space, missing `=`. Compare bit-by-bit to repo file. |
| `systemctl enable` fails with "Refusing to operate on linked unit file" | Unit file was symlinked instead of copied — `sudo rm /etc/systemd/system/omnigraph-daily-pull.{service,timer}` then re-cp. |
| Manual fire smoke service exits non-zero | Likely sync-from-aliyun.sh issue; `journalctl -u omnigraph-daily-pull.service` shows error. Diagnose per aim-4-2 abort table. Do NOT commit until smoke PASS. |
| `systemctl list-timers omnigraph-*` shows additional timers (stale aim-3 units left on Hermes) | aim-3 units belong on Aliyun, NOT Hermes. If found on Hermes, disable + remove: `sudo systemctl disable --now <unit>; sudo rm /etc/systemd/system/<unit>; sudo systemctl daemon-reload`. Document the cleanup in evidence (this is a regression on aim-3 process; surface to orchestrator). |
| Forward-only correction needed post-commit | New commit `fix(aim-4): ...`. Do NOT amend. |

## Evidence to capture

- 3 repo files (.service / .timer / README.md)
- aim-4-3-EVIDENCE.md with full deploy + smoke + audit stdout
- Single forward-only commit hash
- `journalctl` tail showing real rsync log lines from manual fire
