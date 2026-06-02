---
plan_id: aim-3-2
phase: aim-3
wave: 2
depends_on:
  - aim-3-1
requirements_addressed:
  - CUTOVER-01
files_modified:
  - .planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-01-deploy-evidence.md
autonomous: true
t_shirt: M
---

# aim-3-2 — Deploy + enable 13 systemd units on Aliyun (CUTOVER-01 part 2/2)

## Goal

SCP the 26 unit files (13 `.service` + 13 `.timer`) authored at aim-3-1 from the local repo to Aliyun ECS at `/etc/systemd/system/`, run `systemctl daemon-reload`, then `systemctl enable --now omnigraph-*.timer` to register all 13 timers, and capture proof in `CUTOVER-01-deploy-evidence.md`.

This plan is agent-autonomous: per memory `feedback_aim1_agent_is_operator.md`, the agent IS the operator on Aliyun side and runs SSH directly via Bash. No Hermes operator prompt in this plan — Hermes is not touched until aim-3-3.

The timers fire at their scheduled UTC times after enable. We do NOT manually `systemctl start` any service — natural fire is what aim-3-4 verifies in journald.

**Pre-condition:** aim-2 cutover complete (Aliyun has authoritative LightRAG storage, kb-api functional). aim-3-1 commit landed locally (unit files exist on disk in this checkout).

## Acceptance criteria

1. SSH `ls /etc/systemd/system/omnigraph-*.service | wc -l` returns `13`.
2. SSH `ls /etc/systemd/system/omnigraph-*.timer | wc -l` returns `13`.
3. SSH `systemctl daemon-reload` exits 0.
4. SSH `systemctl list-timers omnigraph-* --all` shows all 13 timers, with future `NEXT` wallclock times that match the UTC OnCalendar schedule (e.g., `omnigraph-rss-fetch.timer` next fire at the next 09:00:00 UTC).
5. SSH `systemctl is-enabled omnigraph-*.timer | sort -u` returns `enabled` (and only `enabled`) — proves all 13 are enabled.
6. SSH `systemctl is-active omnigraph-*.timer | sort -u` returns `active` (and only `active`) — proves all 13 are running (timer running, not service running).
7. SSH for each of the 13 services: `systemctl cat omnigraph-<name>.service | grep -E "ExecStart=|EnvironmentFile=|WorkingDirectory="` shows the canonical lines verbatim. (Sample 3 representative ones — daily-ingest, kol-scan, vertex-probe — for evidence file.)
8. `EVIDENCE/CUTOVER-01-deploy-evidence.md` exists, committed locally, contains the verbatim outputs of (1)-(7).

## Task list

### Task 1 — SCP unit files to Aliyun /etc/systemd/system/

**`<read_first>`**

- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-3-cutover\aim-3-1.md` (confirm aim-3-1 acceptance criteria all met — 26 unit files + README in `deploy/aliyun/systemd/`)
- Memory `aliyun_vitaclaw_ssh.md` (SSH alias + connection details)
- Memory `feedback_aim1_agent_is_operator.md` (agent IS operator on Aliyun; SSH directly)

**`<acceptance_criteria>`**

- All 26 unit files copied to Aliyun `/etc/systemd/system/`. README.md is NOT copied (it's repo-side documentation only).
- File permissions: `0644` (default for `cp` of plain files; systemd does not require executable bit).
- Owner: `root:root` (already, since SSH is as root).

**`<action>`**

```bash
# From local repo root. Capture timestamps for evidence.
date -u +"%Y-%m-%dT%H:%M:%SZ" | tee .scratch/aim-3-2-deploy-start.iso

# Confirm local aim-3-1 artifacts exist
ls deploy/aliyun/systemd/*.service | wc -l   # expect 13
ls deploy/aliyun/systemd/*.timer | wc -l     # expect 13

# Copy via scp. Iterate one-by-one OR tarball — tarball is fewer SSH connections.
tar -czf /tmp/aim-3-2-units.tar.gz -C deploy/aliyun/systemd \
  $(ls deploy/aliyun/systemd | grep -E '\.(service|timer)$')
ls -la /tmp/aim-3-2-units.tar.gz

# Push to Aliyun /tmp, extract into /etc/systemd/system
scp /tmp/aim-3-2-units.tar.gz aliyun-vitaclaw:/tmp/aim-3-2-units.tar.gz

ssh aliyun-vitaclaw bash -c "'
set -e
cd /etc/systemd/system/
echo \"=== BEFORE: existing omnigraph-* units ===\"
ls -la /etc/systemd/system/omnigraph-* 2>&1 || echo \"(none — first install)\"

tar -xzf /tmp/aim-3-2-units.tar.gz -C /etc/systemd/system/
ls -la /etc/systemd/system/omnigraph-*.service | wc -l
ls -la /etc/systemd/system/omnigraph-*.timer | wc -l

echo \"=== file ownership + mode ===\"
ls -la /etc/systemd/system/omnigraph-daily-ingest.service
ls -la /etc/systemd/system/omnigraph-daily-ingest.timer
'"
```

If pre-existing `/etc/systemd/system/omnigraph-*` units are found (e.g., from a prior aim-3 attempt), STOP. Do NOT overwrite blindly. Capture their content first via `cat`, then decide whether to replace (this run is the source of truth) or abort and investigate.

Capture all SSH output to `.scratch/aim-3-2-scp-<TS>.log`.

### Task 2 — daemon-reload and enable --now all 13 timers

**`<read_first>`**

- systemd.unit(5) man page on `enable --now` semantics: enables the unit (creates symlink in `multi-user.target.wants/` or `timers.target.wants/`) AND starts it. For timers, this means the timer becomes active immediately and waits for its next OnCalendar fire.

**`<acceptance_criteria>`**

- `systemctl daemon-reload` exits 0.
- `systemctl enable --now omnigraph-*.timer` exits 0 for all 13 (or use a bash loop and capture per-unit exit codes).
- After enable, `systemctl is-enabled` returns `enabled` for all 13 timers.
- After enable, `systemctl is-active` returns `active` for all 13 timers (timer is active = it's waiting to fire; the service is NOT yet running).
- `systemctl list-timers --all omnigraph-*` shows 13 rows, each with a future NEXT wallclock matching the UTC schedule.

**`<action>`**

```bash
ssh aliyun-vitaclaw bash -c "'
set -e

echo \"=== daemon-reload ===\"
systemctl daemon-reload
echo \"daemon_reload_exit=\$?\"

echo \"=== enable --now all 13 timers ===\"
for t in /etc/systemd/system/omnigraph-*.timer; do
  name=\$(basename \"\$t\")
  echo \"--- \$name ---\"
  systemctl enable --now \"\$name\"
  echo \"exit=\$?\"
done

echo \"=== is-enabled ===\"
for t in /etc/systemd/system/omnigraph-*.timer; do
  name=\$(basename \"\$t\")
  printf \"%-50s %s\\n\" \"\$name\" \"\$(systemctl is-enabled \$name)\"
done

echo \"=== is-active ===\"
for t in /etc/systemd/system/omnigraph-*.timer; do
  name=\$(basename \"\$t\")
  printf \"%-50s %s\\n\" \"\$name\" \"\$(systemctl is-active \$name)\"
done

echo \"=== list-timers ===\"
systemctl list-timers --all \"omnigraph-*\"
'"
```

Capture all output to `.scratch/aim-3-2-enable-<TS>.log`.

If any single timer fails to enable (`exit != 0`), do NOT abort the loop — let all 13 attempt. Then in evidence note which failed and why. The most likely failure is a typo in the unit file (e.g., `Requires=` pointing at a non-existent service) which manifests as a daemon-reload error or enable error.

### Task 3 — Verify ExecStart / EnvironmentFile / WorkingDirectory of representative units

**`<read_first>`**

- aim-3-1 plan ExecStart matrix (sanity check the deployed values match the authored values byte-for-byte)

**`<acceptance_criteria>`**

- For each of `omnigraph-daily-ingest.service`, `omnigraph-kol-scan.service`, `omnigraph-vertex-probe.service`:
  - `systemctl cat <name>` shows `ExecStart=` matching the matrix in aim-3-1 exactly.
  - `EnvironmentFile=/root/.hermes/.env` is present.
  - `WorkingDirectory=/root/OmniGraph-Vault` is present.
- For `omnigraph-daily-ingest.service`: `ExecStartPre=...cleanup_stuck_docs.py --all-failed` is present.
- For `omnigraph-kol-enrich.service`: `ExecStart=/bin/true` is present (stub confirmed deployed).

**`<action>`**

```bash
ssh aliyun-vitaclaw bash -c "'
set -e
for u in omnigraph-daily-ingest.service \
         omnigraph-kol-scan.service \
         omnigraph-vertex-probe.service \
         omnigraph-kol-enrich.service; do
  echo \"=== systemctl cat \$u ===\"
  systemctl cat \"\$u\"
  echo
done
'"
```

Capture output to `.scratch/aim-3-2-verify-<TS>.log`.

### Task 4 — Write CUTOVER-01-deploy-evidence.md and commit

**`<read_first>`**

- All `.scratch/aim-3-2-*.log` outputs from Tasks 1-3
- Memory `feedback_git_add_explicit_in_parallel_quicks.md` (explicit add, no `-A`)

**`<acceptance_criteria>`**

- File `.planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-01-deploy-evidence.md` exists.
- File contains: deploy-start ISO timestamp, file count check (13 .service + 13 .timer), full `systemctl list-timers` table, full `is-enabled` and `is-active` listings, the 4 `systemctl cat` outputs from Task 3, any per-timer enable failures (or "all 13 enabled successfully").
- Committed locally to `main` via explicit `git add`, single commit.

**`<action>`**

```bash
mkdir -p .planning/phases/aim-3-cutover/EVIDENCE
```

Use the Write tool to author `CUTOVER-01-deploy-evidence.md`. Skeleton:

```markdown
# CUTOVER-01 — Aliyun systemd deploy + enable evidence

Phase: aim-3 (cutover)
REQ: CUTOVER-01

## Deploy-start ISO (UTC)

[paste from /scratch start iso]

## File counts on Aliyun

- `/etc/systemd/system/omnigraph-*.service`: [N] (required: 13)
- `/etc/systemd/system/omnigraph-*.timer`: [N] (required: 13)

## daemon-reload

`systemctl daemon-reload` exit code: [0]

## enable --now results (per unit)

[paste verbatim Task 2 enable loop output — all 13 lines]

## is-enabled

[paste verbatim is-enabled loop output — all 13 should say "enabled"]

## is-active

[paste verbatim is-active loop output — all 13 should say "active"]

## list-timers (next-fire schedule confirmation)

```

[paste verbatim systemctl list-timers --all omnigraph-* output]

```

## Sample unit verification (3 services + kol-enrich stub)

### omnigraph-daily-ingest.service

```

[paste verbatim systemctl cat output]

```

### omnigraph-kol-scan.service

```

[paste systemctl cat output]

```

### omnigraph-vertex-probe.service

```

[paste systemctl cat output]

```

### omnigraph-kol-enrich.service (STUB — FINDING 6)

```

[paste systemctl cat output — confirms ExecStart=/bin/true]

```

## Verdict

- [PASS / FAIL] All 13 units deployed, daemon-reload OK, all enabled+active.
- [PASS / FAIL] All 13 timers have a future NEXT fire matching their UTC OnCalendar.
- [PASS / FAIL] Sample ExecStart / EnvironmentFile / WorkingDirectory match aim-3-1 authored values.

## Next gate

aim-3-3 — kol_scan.db pre-cutover sync + Hermes jobs disable + CUTOVER-EVIDENCE.md.
DO NOT proceed if any of the three verdict lines above is FAIL — investigate via separate quick first.
```

Then commit:

```bash
git add .planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-01-deploy-evidence.md
git status   # confirm only this file staged
git commit -m "docs(aim-3): record CUTOVER-01 systemd deploy + enable evidence"
```

## Abort/rollback protocol

| Condition | Action |
| --- | --- |
| `daemon-reload` fails | Stop. The most likely cause is a malformed unit file. SSH-side `systemctl status omnigraph-*` will name the bad unit. Do NOT proceed to enable. Roll back: forward-fix the unit file in aim-3-1 → new commit → re-run aim-3-2 from Task 1. |
| Some but not all 13 timers fail to `enable --now` | Capture failures in evidence file. Decide per-unit: forward-fix the unit OR mark it as a CUTOVER-01 gap (like kol-enrich stub) and proceed. Hard rule: ≥ 12 of 13 timers must be active for aim-3-3 to be safe (the missing one delays at most one ingest path). If < 12 active, abort. |
| Existing `/etc/systemd/system/omnigraph-*` units found before deploy | STOP. Do NOT overwrite blindly. Capture content via `cat`. Decide: replace (treat them as stale from earlier attempt) OR abort to investigate. |
| `list-timers` shows a NEXT wallclock that does not match the OnCalendar schedule | Likely a timezone mistake on Aliyun (system clock not UTC). SSH `timedatectl` to confirm `Time zone: UTC` or `Etc/UTC`. If not UTC, `timedatectl set-timezone UTC` then re-run from Task 2. Re-running enable on already-enabled units is idempotent. |

## Evidence to capture

- `EVIDENCE/CUTOVER-01-deploy-evidence.md` — committed locally
- `.scratch/aim-3-2-*.log` — uncommitted, agent-side reference (in case evidence file needs to be regenerated)

That is the only committed artifact of this plan. aim-3-3 produces CUTOVER-EVIDENCE.md.
