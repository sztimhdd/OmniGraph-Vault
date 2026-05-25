---
plan_id: aim-4-2
phase: aim-4
wave: 2
depends_on:
  - aim-4-1
requirements_addressed:
  - SYNC-01
  - SYNC-04
files_modified:
  - scripts/sync-from-aliyun.sh
  - .planning/phases/aim-4-daily-sync/aim-4-2-EVIDENCE.md
autonomous: true
t_shirt: S
---

# aim-4-2 — Author scripts/sync-from-aliyun.sh (SYNC-01 + SYNC-04)

## Goal

Write `scripts/sync-from-aliyun.sh` — the consumer-side rsync-over-SSH
puller that runs on Hermes (and is conceptually re-usable on any
consumer). Idempotent, exits 0 on success, non-zero on any failure
after 3 retries with exponential backoff (60s / 300s / 1800s).
Aggregates 4 rsync invocations (articles SSG output / kol_scan.db /
images / kb/wiki). Implements the marker-file protocol for SYNC-04
(`/tmp/aliyun-sync-failed-<date>` on exhausted retries; cleanup of stale
markers on next successful sync).

This plan covers SYNC-01 (the script itself, idempotency, exit code
semantics) and SYNC-04 (retry/backoff/marker logic — implemented IN the
shell script, NOT in systemd, per FINDING 7). aim-4-3 will install the
systemd unit that calls this script and routes its journald output.

This plan is autonomous (agent-only). No SSH to Aliyun or Hermes during
authoring; only repo-local file write + commit. Smoke validation
(running the script on Hermes against Aliyun) happens at end of plan.

## Acceptance criteria

1. `scripts/sync-from-aliyun.sh` exists in repo at top of `scripts/`.
2. File mode is 0755 (executable for owner / group / world). Confirmed
   via `git ls-files --stage scripts/sync-from-aliyun.sh` showing
   `100755`.
3. Script header includes shebang `#!/usr/bin/env bash` and `set -u`
   (`set -e` is INTENTIONALLY OMITTED — we want to capture rsync exit
   codes inside the retry loop without exiting on first failure).
4. The 4 sync targets are defined exactly:
   - `/root/OmniGraph-Vault/kb/output/articles/` →
     `${HERMES_DATA_DIR}/articles/`
   - `/root/OmniGraph-Vault/data/kol_scan.db` →
     `${HERMES_DATA_DIR}/kol_scan.db`
   - `/root/.hermes/omonigraph-vault/images/` →
     `${HERMES_DATA_DIR}/images/`
   - `/root/OmniGraph-Vault/kb/wiki/` →
     `${HERMES_DATA_DIR}/kb/wiki/`
5. `HERMES_DATA_DIR` defaults to `${HOME}/.hermes/omonigraph-vault`
   (canonical typo preserved per CLAUDE.md Lessons Learned).
6. `ALIYUN_SSH_KEY` defaults to
   `${HOME}/.ssh/hermes_to_aliyun_ed25519` (matches aim-4-1).
7. Each rsync invocation uses flags: `-az --delete -e "ssh -i
   ${ALIYUN_SSH_KEY} -o StrictHostKeyChecking=accept-new -o
   BatchMode=yes"`.
8. Retry loop: exactly 3 retries via delays array `(60 300 1800)` then
   one final attempt — total 4 rsync-all attempts maximum (matches
   "≤ 3 retries" SYNC-04 wording).
9. On all-success: `rm -f /tmp/aliyun-sync-failed-*` runs BEFORE exit
   0 (cleans up stale markers; addresses FINDING 10 to prevent aim-5
   STAB-03 false-trip).
10. On all-fail: `touch /tmp/aliyun-sync-failed-$(date +%Y-%m-%d)` runs
    AND an `ERROR:` line is emitted to stderr; script exits non-zero
    (1 specifically).
11. `BatchMode=yes` is set so any password prompt → immediate non-zero
    exit (no hang).
12. Script is shellcheck-clean: `shellcheck scripts/sync-from-aliyun.sh`
    returns 0 issues (or only documented stylistic warnings — not
    errors). If shellcheck unavailable in environment, skip and
    document.
13. Smoke validation on Hermes against Aliyun: `bash
    scripts/sync-from-aliyun.sh && echo $?` returns 0 within ≤ 30 min
    on first run (cold cache 872MB images + 32MB DB + 32MB articles +
    256K wiki = ~937 MB transfer). Re-run within 5 min returns 0 with
    near-zero transfer (idempotency proof).
14. Smoke evidence captured in
    `.planning/phases/aim-4-daily-sync/aim-4-2-EVIDENCE.md`.
15. Single forward-only commit containing `scripts/sync-from-aliyun.sh`
    + evidence file. Conventional commit message:
    `feat(aim-4): scripts/sync-from-aliyun.sh — Aliyun→Hermes daily pull (SYNC-01,SYNC-04)`.

## Task list

### Task 1 — Author scripts/sync-from-aliyun.sh

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-4-daily-sync\aim-4-CONTEXT.md`
  lines 192-251 (script skeleton + retry loop + marker cleanup)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-4-daily-sync\aim-4-CONTEXT.md`
  lines 75-94 (FINDING 5 sync targets — verified 2026-05-24 via SSH
  probe: articles JSON dir is `/root/OmniGraph-Vault/kb/output/articles/`
  containing 1944 SSG-rendered HTML files / 32 MB)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-4-daily-sync\aim-4-CONTEXT.md`
  lines 152-161 (FINDING 10 stale-marker cleanup requirement)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\REQUIREMENTS-Aliyun-Ingest-Migration-v1.md`
  lines 71, 74 (SYNC-01 and SYNC-04 verbatim)

**`<acceptance_criteria>`**
- `scripts/sync-from-aliyun.sh` exists with content matching the
  template in `<action>` (sections may be adjusted for clarity but the
  4 targets, retry timings 60/300/1800, and marker logic are bit-exact).
- `chmod +x scripts/sync-from-aliyun.sh` applied (mode 0755 / 100755
  in git index).
- `bash -n scripts/sync-from-aliyun.sh` (syntax check) exits 0.
- `grep -c '^do_one_rsync\|^do_rsync_all\|^main' scripts/sync-from-aliyun.sh`
  returns 3 (one definition each, plus `main "$@"` invocation at
  bottom).
- `grep -E '/root/OmniGraph-Vault/kb/output/articles/|/root/OmniGraph-Vault/data/kol_scan.db|/root/\.hermes/omonigraph-vault/images/|/root/OmniGraph-Vault/kb/wiki/' scripts/sync-from-aliyun.sh`
  returns exactly 4 lines.
- `grep -E 'delays=\(60 300 1800\)' scripts/sync-from-aliyun.sh`
  returns 1 line.
- `grep -E 'rm -f /tmp/aliyun-sync-failed-\*' scripts/sync-from-aliyun.sh`
  returns at least 1 line.
- `grep -E 'BatchMode=yes' scripts/sync-from-aliyun.sh` returns ≥ 1 line.

**`<action>`**

Use the Write tool to create `scripts/sync-from-aliyun.sh` with this
exact content:

```bash
#!/usr/bin/env bash
# scripts/sync-from-aliyun.sh
#
# Pull articles SSG output / kol_scan.db / images / kb/wiki from
# Aliyun (101.133.154.49, root) → Hermes ${HERMES_DATA_DIR}.
# Runs as oneshot on Hermes (systemd timer). Pure bash + rsync + ssh.
#
# Idempotent (re-run on same day = no-op transfer). Exit 0 on full
# success across all 4 targets; non-zero on any rsync failure after 3
# retries with exponential backoff (60s / 300s / 1800s).
#
# Retry exhaustion writes /tmp/aliyun-sync-failed-<date> marker per
# SYNC-04. Stale markers (any failed-<date>) are cleaned up on next
# success per FINDING 10 (prevents aim-5 STAB-03 false-trip).
#
# REQs: SYNC-01 (script + idempotency + exit semantics)
#       SYNC-04 (retry/backoff/marker logic)
#
# Aliyun side prep: aim-4-1 installed Hermes pubkey on
# /root/.ssh/authorized_keys.

set -u

# --- Config (overridable via env) -------------------------------------
ALIYUN_SSH_HOST="${ALIYUN_SSH_HOST:-root@101.133.154.49}"
ALIYUN_SSH_KEY="${ALIYUN_SSH_KEY:-${HOME}/.ssh/hermes_to_aliyun_ed25519}"
HERMES_DATA_DIR="${HERMES_DATA_DIR:-${HOME}/.hermes/omonigraph-vault}"

SSH_OPTS="-i ${ALIYUN_SSH_KEY} -o StrictHostKeyChecking=accept-new -o BatchMode=yes"
RSYNC_OPTS="-az --delete"

# --- Sync targets: SRC (Aliyun) → DST (Hermes) ------------------------
# Order: cheapest first so a fail-fast on later targets still gets
# small early targets to disk. Verified 2026-05-24 via SSH probe.
SYNC_PAIRS=(
  "/root/OmniGraph-Vault/data/kol_scan.db|${HERMES_DATA_DIR}/kol_scan.db"
  "/root/OmniGraph-Vault/kb/wiki/|${HERMES_DATA_DIR}/kb/wiki/"
  "/root/OmniGraph-Vault/kb/output/articles/|${HERMES_DATA_DIR}/articles/"
  "/root/.hermes/omonigraph-vault/images/|${HERMES_DATA_DIR}/images/"
)

# --- Helpers ----------------------------------------------------------
log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

ensure_parent_dirs() {
  mkdir -p \
    "${HERMES_DATA_DIR}/kb/wiki" \
    "${HERMES_DATA_DIR}/articles" \
    "${HERMES_DATA_DIR}/images"
}

do_one_rsync() {
  local src="$1" dst="$2"
  rsync ${RSYNC_OPTS} \
    -e "ssh ${SSH_OPTS}" \
    "${ALIYUN_SSH_HOST}:${src}" \
    "${dst}"
}

do_rsync_all() {
  local rc=0
  for pair in "${SYNC_PAIRS[@]}"; do
    local src="${pair%%|*}"
    local dst="${pair##*|}"
    log "rsync ${src} → ${dst}"
    if ! do_one_rsync "${src}" "${dst}"; then
      local code=$?
      log "  → rsync FAILED (exit ${code}) for ${src}"
      rc=${code}
    fi
  done
  return ${rc}
}

clean_stale_markers() {
  # FINDING 10: clear all markers on success so a transient old
  # failure does not falsely trip aim-5 STAB-03.
  rm -f /tmp/aliyun-sync-failed-* 2>/dev/null || true
}

write_failure_marker() {
  local date_str
  date_str="$(date +%Y-%m-%d)"
  touch "/tmp/aliyun-sync-failed-${date_str}"
  log "MARKER /tmp/aliyun-sync-failed-${date_str} written"
}

# --- Main retry loop --------------------------------------------------
main() {
  ensure_parent_dirs

  local delays=(60 300 1800)
  local attempt

  for attempt in 0 1 2; do
    if do_rsync_all; then
      clean_stale_markers
      log "sync OK on attempt $((attempt + 1))"
      exit 0
    fi
    local d="${delays[${attempt}]}"
    log "attempt $((attempt + 1)) failed; sleeping ${d}s before retry"
    sleep "${d}"
  done

  # 4th and final attempt
  if do_rsync_all; then
    clean_stale_markers
    log "sync OK on final attempt (4)"
    exit 0
  fi

  write_failure_marker
  echo "ERROR: aliyun sync exhausted 3 retries on $(date +%Y-%m-%d)" >&2
  exit 1
}

main "$@"
```

After writing, run `chmod +x scripts/sync-from-aliyun.sh` and verify
with `bash -n scripts/sync-from-aliyun.sh`.

### Task 2 — Smoke validation on Hermes

**`<read_first>`**
- aim-4-1-EVIDENCE.md (must show validation 1 + 2 PASS — bootstrap
  prereq for this smoke to succeed)
- Memory `hermes_ssh.md` (Hermes user `sztimhdd`, port 49221)

**`<acceptance_criteria>`**
- The script committed in Task 1 is copied to Hermes (via `scp` or
  `rsync` from Hermes pulling repo `git` — not yet possible since
  commit hasn't happened. Plan: stage the file via temporary scp from
  local repo to Hermes, run smoke, then commit. Order matters: Task 1
  authors locally → Task 2 stages on Hermes via scp + runs → Task 3
  records evidence + commits both.)
- First-run smoke `bash ~/scripts/sync-from-aliyun.sh` on Hermes exits 0.
- Re-run smoke (within ≤5 min of first) exits 0 with rsync transfer
  size near zero (idempotency proof — `du -sh` of `images/` should be
  unchanged byte-for-byte).
- After successful smoke,
  `~/.hermes/omonigraph-vault/articles/` contains ≥ 1900 HTML files.
- After successful smoke,
  `~/.hermes/omonigraph-vault/kol_scan.db` exists with size ≥ 30 MB.
- After successful smoke, `~/.hermes/omonigraph-vault/kb/wiki/`
  exists with at least the dirs `concepts/`, `comparisons/`.
- `/tmp/aliyun-sync-failed-*` does NOT exist after success.

**`<action>`**

```bash
# Stage the script onto Hermes from corp dev box (scp from local repo).
# (Hermes can't `git pull` the latest commit because aim-4-2 hasn't
# committed yet — by design, smoke-before-commit.)
scp -P 49221 scripts/sync-from-aliyun.sh \
  sztimhdd@ohca.ddns.net:/tmp/sync-from-aliyun.sh.aim-4-2-smoke

ssh -p 49221 sztimhdd@ohca.ddns.net 'set -e; \
  chmod +x /tmp/sync-from-aliyun.sh.aim-4-2-smoke; \
  echo "=== FIRST RUN ==="; \
  time bash /tmp/sync-from-aliyun.sh.aim-4-2-smoke 2>&1 | tail -50; \
  echo "RC=$?"; \
  echo "=== SECOND RUN (idempotency) ==="; \
  time bash /tmp/sync-from-aliyun.sh.aim-4-2-smoke 2>&1 | tail -20; \
  echo "RC=$?"; \
  echo "=== POST-SYNC INVENTORY ==="; \
  ls ~/.hermes/omonigraph-vault/articles/ | wc -l; \
  du -sh ~/.hermes/omonigraph-vault/articles/; \
  ls -la ~/.hermes/omonigraph-vault/kol_scan.db; \
  ls -la ~/.hermes/omonigraph-vault/kb/wiki/; \
  du -sh ~/.hermes/omonigraph-vault/images/; \
  echo "=== MARKER CHECK ==="; \
  ls /tmp/aliyun-sync-failed-* 2>/dev/null && echo MARKER_PRESENT_BAD || echo NO_MARKER_OK; \
  rm -f /tmp/sync-from-aliyun.sh.aim-4-2-smoke'
```

Capture all stdout for the evidence file. If first-run RC != 0, do
NOT proceed to commit. Diagnose: typical failures are (a) pubkey not
deployed (re-run aim-4-1 validation), (b) Aliyun source path wrong
(SSH-probe to confirm), (c) Hermes disk full (`df -h ~`).

Acceptable first-run wallclock: up to 30 min for cold-cache ~937 MB
transfer over corp WAN. If > 30 min hard ceiling, examine if rsync is
hung vs. progressing (check Aliyun `iftop` or Hermes `ifstat`).

### Task 3 — Author evidence markdown + commit

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\CLAUDE.md` Lessons Learned
  2026-05-06 #5 + 2026-05-15 #1 (forward-only, explicit `git add`)
- Memory `feedback_git_add_explicit_in_parallel_quicks.md`

**`<acceptance_criteria>`**
- `.planning/phases/aim-4-daily-sync/aim-4-2-EVIDENCE.md` exists.
- File contains: timestamp; first-run wallclock + RC=0; second-run RC=0
  + transfer size near 0; post-sync inventory (article count, DB size,
  wiki dirs, images du); marker check stdout `NO_MARKER_OK`.
- `git ls-files --stage scripts/sync-from-aliyun.sh` shows `100755`.
- Single forward-only commit on `main` containing both
  `scripts/sync-from-aliyun.sh` and the evidence file.
- Commit message:
  `feat(aim-4): scripts/sync-from-aliyun.sh — Aliyun→Hermes daily pull (SYNC-01,SYNC-04)`.
- `git status` clean post-commit.

**`<action>`**

Use the Write tool to author evidence skeleton:

```markdown
# aim-4-2 — sync-from-aliyun.sh authoring + smoke evidence

**Timestamp:** <ts>
**Plan:** aim-4-2
**REQs:** SYNC-01, SYNC-04
**Status:** PASS

## Script

- Path: `scripts/sync-from-aliyun.sh`
- Mode: 0755 (per `git ls-files --stage`)
- `bash -n` syntax check: exit 0
- 4 sync targets verified in source via grep

## First-run smoke on Hermes

- Wallclock: <X> min
- RC: 0
- Bytes transferred (rsync stats line): <Y> MB

## Re-run smoke (idempotency)

- Wallclock: <Z> seconds
- RC: 0
- Bytes transferred: ~0 (cache hit)

## Post-sync inventory on Hermes

- `~/.hermes/omonigraph-vault/articles/` file count: <N> (≥1900 expected)
- `~/.hermes/omonigraph-vault/articles/` size: <S>
- `~/.hermes/omonigraph-vault/kol_scan.db` size: <S> (≥30 MB expected)
- `~/.hermes/omonigraph-vault/kb/wiki/` dirs: comparisons/, concepts/, ...
- `~/.hermes/omonigraph-vault/images/` size: <S>

## Marker check

- `/tmp/aliyun-sync-failed-*`: NO_MARKER_OK

## References

- aim-4 CONTEXT.md §"sync-from-aliyun.sh skeleton"
- REQUIREMENTS SYNC-01, SYNC-04
```

Then commit:

```bash
git add scripts/sync-from-aliyun.sh \
        .planning/phases/aim-4-daily-sync/aim-4-2-EVIDENCE.md
git status   # confirm only the 2 files staged
git commit -m "feat(aim-4): scripts/sync-from-aliyun.sh — Aliyun→Hermes daily pull (SYNC-01,SYNC-04)"
git log -1 --name-only
```

## Abort/rollback protocol

| Condition | Action |
| --- | --- |
| `bash -n` syntax check fails | Fix syntax in `scripts/sync-from-aliyun.sh`. Do NOT commit broken script. |
| First-run smoke RC != 0 with "Permission denied (publickey)" | aim-4-1 bootstrap incomplete — return to aim-4-1 Task 3 validation. Do NOT commit until smoke PASS. |
| First-run smoke RC != 0 with "No such file or directory" on a sync target | SSH-probe Aliyun: `ssh aliyun-vitaclaw 'ls -d <src>'`. If path actually different, update `SYNC_PAIRS` in script and re-smoke. |
| First-run smoke RC != 0 with rsync exit 12 (premature EOF) | Network flake. Re-run smoke. If recurrent, investigate `iftop` on Aliyun side. |
| Marker file `/tmp/aliyun-sync-failed-*` present after smoke | Bug in script's `clean_stale_markers` — script entered failure path but RC=0 path printed "OK". Inspect log; do not commit. |
| Forward-only correction needed post-commit | New commit `fix(aim-4): ...`. Do NOT amend. |

## Evidence to capture

- `scripts/sync-from-aliyun.sh` (in repo)
- aim-4-2-EVIDENCE.md (in repo)
- One forward-only commit hash on `main` with both files
- Smoke stdout captured into evidence file
