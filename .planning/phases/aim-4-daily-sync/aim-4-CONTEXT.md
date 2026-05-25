# Phase aim-4: Daily sync Aliyun → Hermes + Databricks — Context

**Gathered:** 2026-05-24
**Status:** Ready for planning
**Source:** ROADMAP-Aliyun-Ingest-Migration-v1.md §"Phase aim-4" (lines 148-170) +
REQUIREMENTS-Aliyun-Ingest-Migration-v1.md SYNC-01..04 + STATE-Aliyun-Ingest-Migration-v1.md
+ aliyun_vitaclaw_ssh.md memory + hermes_ssh.md memory

---

<domain>
## Phase Boundary

Install consumer-side daily pulls **from** Aliyun (authoritative producer) **to** Hermes
and Databricks. End-state: Aliyun is unaware of downstream consumers (pull mode);
Hermes net cron count is 11 → 1 (one new daily-pull job replacing the 11 ingest jobs
retired at aim-3); Databricks pulls wiki + DB via existing `git pull` workflow.

**In scope:**
- `scripts/sync-from-aliyun.sh` — rsync-over-SSH puller (runs on Hermes)
- Hermes `omnigraph-daily-pull.{service,timer}` — systemd timer @ 02:00 ADT
- Retry policy: ≤ 3 retries, exp backoff 60s / 300s / 1800s, journald log, 48h marker file
- Databricks `git pull` verification (no new code — existing workflow)

**Not in scope:**
- Wiki write-back automation from Aliyun (Q4c — manual `git commit` from Aliyun is acceptable
  during aim-4..aim-5; auto-hook deferred to LLM-Wiki-Integration-P2 milestone)
- Incremental / `--partial` rsync optimization (deferred to `Aliyun-Sync-v2` derivative milestone, PROJECT §8)
- 7-day stability observation (aim-5 owns)
- Databricks pulling `images/` or `lightrag_storage/` — Databricks consumes wiki + DB only

</domain>

<decisions>
## Critical Findings

### FINDING 1 — Sync direction = pull, runs on Hermes (NOT push from Aliyun)

Per ROADMAP §aim-4 goal: "Aliyun is unaware of downstream consumers (pull mode)". The
script `scripts/sync-from-aliyun.sh` is committed to the repo but its **execution
host is Hermes** (and conceptually re-usable on any consumer). Aliyun runs no sync
service. Hermes initiates the SSH connection outbound to Aliyun.

### FINDING 2 — SSH from Hermes → Aliyun requires a prereq key install

User's corp dev box has SSH alias `aliyun-vitaclaw` (key `~/.ssh/aliyun_orchestrator_ed25519`,
host 101.133.154.49 port 22, user root). Hermes (`ohca.ddns.net:49221`, user `sztimhdd`)
does **NOT** have this key installed today. SYNC-01's script depends on Hermes being
able to `ssh root@101.133.154.49` non-interactively. Planner must include either:
(a) an SSH-key bootstrap step (generate Hermes-side ed25519, install pubkey on
Aliyun authorized_keys) as a prereq plan, OR (b) document the prereq as a one-time
operator step recorded in the deploy runbook before the systemd timer can fire.

Recommended: option (a) as its own plan — without it SYNC-01 will silently fail
on first cron fire.

### FINDING 3 — systemd unit on Hermes, NOT Hermes-agent-cron and NOT crontab

SYNC-04 requires `journalctl -u omnigraph-daily-pull.service` evidence. That requires
a systemd unit, not a crontab line and not a Hermes-agent-cron entry. Hermes runs
WSL2 Linux (per hermes_ssh.md) which has systemd available. Pattern matches aim-3
(Aliyun systemd units) — same `[Unit]/[Service]/[Timer]` template, different host.

The "Hermes net cron count: 11 → 1" wording in SYNC-02 counts the new systemd timer
as the "1 cron". The 11 retired at aim-3 were Hermes-agent-cron jobs (jobs.json
registry, NOT crontab). Mixing categories is intentional — both are scheduled jobs
the operator manages on Hermes.

### FINDING 4 — Schedule: 02:00 ADT = 05:00 UTC

OnCalendar value: `*-*-* 05:00:00`. ADT = UTC-3. Choice rationale (per ROADMAP note):
Aliyun evening-ingest fires at 21:00 ADT (00:00 UTC); 5h budget covers ingest
finishing + buffer. Pulling at 02:00 ADT captures the freshest snapshot.

### FINDING 5 — Sync targets (rsync source paths on Aliyun)

Per SYNC-01:
1. `articles JSON` — Aliyun source: TBD (verify which dir; likely `/root/OmniGraph-Vault/articles/`
   or `/root/.hermes/omonigraph-vault/articles/`). **Planner must SSH-probe Aliyun**
   to find the canonical articles JSON location at planning time.
2. `data/kol_scan.db` — Aliyun source: `/root/OmniGraph-Vault/data/kol_scan.db`
   (820 articles + 1728 RSS, ~32 MB; per aliyun_vitaclaw_ssh.md FINDING table)
3. `images/` — Aliyun source: `/root/.hermes/omonigraph-vault/images/`
4. `kb/wiki/` — Aliyun source: `/root/OmniGraph-Vault/kb/wiki/` (in-repo, manual
   commit per Q4c)

Targets on Hermes:
- All four → `~/.hermes/omonigraph-vault/` (typo is canonical) overwriting Hermes's
  retired storage with Aliyun's snapshot

`kb/wiki/` is in-repo on both ends — it travels via repo `git pull` for the
**Databricks consumer** (SYNC-03), but for **Hermes** the SYNC-01 rsync handles it
to keep the runtime data dir consistent. Both consumers see the same wiki state
within ≤24h after Aliyun's manual commit.

### FINDING 6 — Idempotency + exit code semantics

SYNC-01 success criterion: "re-running on the same day produces identical local
state. Exit code 0 on success, non-zero on any rsync failure."

Idempotency comes free from rsync (delta sync). The script's own exit handling
must:
- Aggregate exit codes across all 4 rsync invocations
- Exit 0 only if all 4 succeeded
- Exit non-zero (e.g., the last failed rsync's exit code) on any failure

### FINDING 7 — Retry + marker logic lives IN the shell script (NOT in systemd)

Systemd has `Restart=on-failure` + `RestartSec=...` but does NOT support exp backoff
60/300/1800s natively (would need 3 separate Restart-spec stanzas with conditional
logic — fragile). Cleaner: implement the 3-retry loop inside `sync-from-aliyun.sh`.

Pseudo:
```bash
delays=(60 300 1800)
for attempt in 0 1 2; do
  do_rsync_all && exit 0
  log "rsync attempt $((attempt+1)) failed; sleeping ${delays[$attempt]}s"
  sleep "${delays[$attempt]}"
done
do_rsync_all && exit 0
# All 4 attempts failed
date_str=$(date +%Y-%m-%d)
touch "/tmp/aliyun-sync-failed-${date_str}"
echo "ERROR: aliyun sync exhausted 3 retries on ${date_str}" >&2
exit 1
```

The systemd unit captures stderr via journald automatically (per aim-3 template:
`StandardError=journal`). No extra wiring needed.

### FINDING 8 — Databricks SYNC-03 = verification only, no install

Databricks already runs `git pull` on its existing repo checkout (per ROADMAP note).
No new code or cron required on Databricks. The plan is a post-deploy verification:
24h after first SYNC-02 fire, run `git log -1 kb/wiki/` on Databricks and confirm
the latest commit timestamp ≥ aim-4 deploy. This is operator-side / run once /
verification only, not a recurring job.

If Aliyun's manual `git commit` lag is > 24h, SYNC-03 verification slips to that
window. This is the documented Q4c trade-off.

### FINDING 9 — Hermes-side venv / Python dependency = NONE for the script

`sync-from-aliyun.sh` is pure bash + rsync + ssh. No Python, no venv. This is
intentional: the consumer does NOT depend on Aliyun's `venv-aim1/` or any Hermes
Python state. Failure modes are limited to network / SSH / rsync exit codes —
clean separation from ingest pipeline complexity.

### FINDING 10 — Alert criterion = marker file age, not retry count

SYNC-04 §6 Risk row 8 alert criterion: marker file `/tmp/aliyun-sync-failed-<date>`
older than 48h (i.e., 2 consecutive sync failures) = operator action required. No
automated escalation beyond "marker exists + ERROR in journald". Planner does NOT
need to wire pagerduty / email / webhook — stops at marker + journald.

For aim-5 STAB-03 to pass (7 consecutive zero-fail days), the marker file must
not appear for 7 consecutive days. The marker file should be cleaned up on a
successful next-day sync (`rm -f /tmp/aliyun-sync-failed-*` at the top of the
script if all rsyncs succeed) — otherwise stale markers from a transient failure
2 weeks ago would falsely trip aim-5 monitoring.

</decisions>

<canonical_refs>
## Canonical References

### Planning artifacts (read first)
- `.planning/ROADMAP-Aliyun-Ingest-Migration-v1.md` (lines 148-170) — Phase aim-4 goal + 4 SYNC REQs success criteria
- `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` (line 71-74) — SYNC-01..04 verbatim
- `.planning/STATE-Aliyun-Ingest-Migration-v1.md` (line 41, 76, 90, 122-126) — milestone state, Decision 5
- `.planning/PROJECT-Aliyun-Ingest-Migration-v1.md` Q4c, §8 — Wiki write-back deferral, Aliyun-Sync-v2 derivative
- `.planning/phases/aim-3-cutover/aim-3-CONTEXT.md` — systemd unit template (reuse for aim-4-2 Hermes timer)

### Memory pointers (do NOT cite verbatim — verify before asserting)
- `aliyun_vitaclaw_ssh.md` — Aliyun host 101.133.154.49 port 22, root, key on dev box
- `hermes_ssh.md` — Hermes ohca.ddns.net port 49221 user sztimhdd, WSL2 Linux,
  runtime dir `~/.hermes/omonigraph-vault/` (typo canonical)

### Reference patterns
- `scripts/cron_daily_ingest.sh` — Hermes-side cron wrapper (do NOT copy structure;
  aim-4 uses systemd directly without tmux)
- `aim-3-CONTEXT.md` §"systemd Unit Template" — copy template, change ExecStart and OnCalendar

</canonical_refs>

<specifics>
## Specific Implementation Notes

### sync-from-aliyun.sh skeleton (planner expand)

```bash
#!/usr/bin/env bash
# scripts/sync-from-aliyun.sh
# Pull articles JSON / kol_scan.db / images/ / kb/wiki/ from Aliyun → Hermes
# Idempotent. Exits 0 on success, non-zero on any rsync failure after 3 retries.

set -u
ALIYUN_SSH_HOST="root@101.133.154.49"
ALIYUN_SSH_KEY="${HOME}/.ssh/hermes_to_aliyun_ed25519"  # planner: confirm path
HERMES_DATA_DIR="${HOME}/.hermes/omonigraph-vault"

# Sync targets: SRC (Aliyun) → DST (Hermes)
declare -A TARGETS=(
  ["/root/OmniGraph-Vault/articles/"]="${HERMES_DATA_DIR}/articles/"
  ["/root/OmniGraph-Vault/data/kol_scan.db"]="${HERMES_DATA_DIR}/kol_scan.db"
  ["/root/.hermes/omonigraph-vault/images/"]="${HERMES_DATA_DIR}/images/"
  ["/root/OmniGraph-Vault/kb/wiki/"]="${HERMES_DATA_DIR}/kb/wiki/"
)

do_one_rsync() {
  local src="$1" dst="$2"
  rsync -az --delete \
    -e "ssh -i ${ALIYUN_SSH_KEY} -o StrictHostKeyChecking=accept-new -o BatchMode=yes" \
    "${ALIYUN_SSH_HOST}:${src}" "${dst}"
}

do_rsync_all() {
  local rc=0
  for src in "${!TARGETS[@]}"; do
    do_one_rsync "${src}" "${TARGETS[$src]}" || rc=$?
  done
  return $rc
}

main() {
  local delays=(60 300 1800)
  for attempt in 0 1 2; do
    if do_rsync_all; then
      rm -f /tmp/aliyun-sync-failed-*
      echo "sync ok (attempt $((attempt+1)))"
      exit 0
    fi
    echo "sync attempt $((attempt+1)) failed; sleeping ${delays[$attempt]}s" >&2
    sleep "${delays[$attempt]}"
  done

  if do_rsync_all; then
    rm -f /tmp/aliyun-sync-failed-*
    echo "sync ok (attempt 4 — final)"
    exit 0
  fi

  local date_str=$(date +%Y-%m-%d)
  touch "/tmp/aliyun-sync-failed-${date_str}"
  echo "ERROR: aliyun sync exhausted 3 retries on ${date_str}" >&2
  exit 1
}

main "$@"
```

### Hermes systemd units

`/etc/systemd/system/omnigraph-daily-pull.service`:
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

`/etc/systemd/system/omnigraph-daily-pull.timer`:
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

(Note: ADT 02:00 = UTC 05:00. `Persistent=true` re-fires if Hermes was offline at fire time.)

### Hermes → Aliyun SSH key bootstrap (prereq plan)

```bash
# On Hermes (sztimhdd):
ssh-keygen -t ed25519 -f ~/.ssh/hermes_to_aliyun_ed25519 -N ""
cat ~/.ssh/hermes_to_aliyun_ed25519.pub
# → operator copies pubkey

# On Aliyun (root) via existing dev-box SSH:
ssh aliyun-vitaclaw 'echo "<pubkey>" >> /root/.ssh/authorized_keys'

# Validate from Hermes:
ssh -i ~/.ssh/hermes_to_aliyun_ed25519 root@101.133.154.49 'hostname'
# Expected: <aliyun hostname>
```

### Databricks SYNC-03 verification command

```bash
# 24h after first SYNC-02 fire, run on Databricks consumer:
cd <databricks-repo-checkout>
git pull
git log -1 kb/wiki/ --format='%H %ai %s'
# Acceptance: timestamp ≥ aim-4 deploy timestamp
```

### Aliyun manual wiki commit guide (Q4c during aim-4..5)

Document for operator:
```bash
ssh aliyun-vitaclaw '
  cd /root/OmniGraph-Vault
  git status kb/wiki/
  git add kb/wiki/
  git commit -m "wiki: daily increment $(date +%Y-%m-%d)"
  git push origin main
'
```

This is operator-driven during aim-4..5; auto-hook is LLM-Wiki-Integration-P2 scope.

### Acceptance probe checklist (planner bake into each plan's `<acceptance_criteria>`)

- SYNC-01: `bash scripts/sync-from-aliyun.sh && echo $?` → 0; re-run → 0; idempotent
- SYNC-02: `systemctl list-timers omnigraph-daily-pull.timer` shows `*-*-* 05:00:00 UTC` next fire
- SYNC-02: After first natural fire, `journalctl -u omnigraph-daily-pull.service --since "24h ago"` shows
  `sync ok (attempt 1)` log line
- SYNC-03: `cd <databricks-repo>; git log -1 kb/wiki/` timestamp ≥ aim-4 deploy
- SYNC-04: Simulate failure (ssh to bad host) → 3 retries logged → marker file created → exit 1

</specifics>

<deferred>
## Deferred (out of aim-4 scope)

- **Wiki write-back automation** (Q4c → LLM-Wiki-Integration-P2 milestone with deploy key)
- **Incremental rsync** (`--partial`, parallel workers, selective sync) → `Aliyun-Sync-v2` derivative (PROJECT §8)
- **Automated escalation beyond marker + journald** (pagerduty / email / webhook) — operator-driven only
- **Aliyun → Databricks direct push** (Databricks pulls via existing `git pull`; no direct Aliyun → DBX channel needed)
- **Hermes → Aliyun reverse sync** (Aliyun is sole producer; Hermes-side edits are deprecated post aim-3)

</deferred>

<plan_skeleton_hint>
## Suggested Plan Decomposition (planner is free to adjust)

Suggested 4 plans, all Wave-1 dependencies forming a chain:

1. **aim-4-1** — Hermes → Aliyun SSH key bootstrap (prereq for SYNC-01)
   - Generate ed25519 key on Hermes, install pubkey on Aliyun, validate non-interactive ssh
   - Files: none in repo (operator step), but documented in `.planning/phases/aim-4-daily-sync/aim-4-1-SSH-bootstrap.md`
   - REQs: prereq (none directly, but blocks SYNC-01)

2. **aim-4-2** — `scripts/sync-from-aliyun.sh` (SYNC-01 + SYNC-04 retry/marker logic)
   - Author script per skeleton above; commit to repo
   - Acceptance: dry-run on Hermes returns 0; simulated failure triggers marker
   - REQs: SYNC-01, SYNC-04

3. **aim-4-3** — Hermes systemd unit install (SYNC-02 + SYNC-04 journald)
   - `omnigraph-daily-pull.{service,timer}` on Hermes
   - Schedule UTC 05:00 (= 02:00 ADT)
   - Acceptance: `systemctl list-timers` shows next fire, `journalctl -u` empty pre-first-fire
   - REQs: SYNC-02, SYNC-04 (journald wiring)

4. **aim-4-4** — Databricks SYNC-03 verification + Aliyun manual wiki commit guide
   - Documentation-only plan: verification command + wiki commit guide
   - Acceptance: verification run 24h after first SYNC-02 fire, evidence captured in `aim-4-EVIDENCE/`
   - REQs: SYNC-03

Wave structure:
- Wave 1: aim-4-1 (SSH key bootstrap) — no deps
- Wave 2: aim-4-2 (script) — depends on aim-4-1
- Wave 3: aim-4-3 (systemd unit) — depends on aim-4-2 (script must exist before unit installed)
- Wave 4 (post-deploy): aim-4-4 (Databricks verify) — depends on aim-4-3 first natural fire

Planner is free to merge aim-4-1 into aim-4-2 if SSH bootstrap is reframed as a runbook step.

</plan_skeleton_hint>
