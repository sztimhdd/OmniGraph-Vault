---
plan_id: aim-2-5
phase: aim-2
wave: 5
depends_on:
  - aim-2-4
requirements_addressed:
  - STORAGE-05
files_modified:
  - .planning/STATE-Aliyun-Ingest-Migration-v1.md
  - .planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-05-cutover-evidence.md
autonomous: false
t_shirt: M
---

# aim-2-5 — Cutover: holding-dir → Aliyun production path + Hermes read-only + resume (STORAGE-05)

## Goal

Promote the byte-verified holding-dir extracted at aim-2-3 (and proven byte-identical at aim-2-4) into the Aliyun production path `/root/.hermes/omonigraph-vault/lightrag_storage/` via `mv` (NOT `cp`), set the original Hermes-side storage to read-only via `chmod -R a-w` (30-day cold-backup window per Q2a constraint #3), record the 30-day retention deadline as a forward-only edit to `STATE-Aliyun-Ingest-Migration-v1.md`, and resume the 11 Hermes ingest crontab lines that were paused at aim-2-1.

After this plan, Aliyun has the authoritative LightRAG storage at the production path, Hermes still has the original copy as a read-only cold backup, and Hermes ingest crons are running again — but Hermes is no longer the migration's authoritative ingest node (aim-3 will retire Hermes ingest cron entirely; aim-5 verifies 7-day stability). Resume of Hermes cron at THIS plan is intentional even though aim-3 will stop it again — it gives a 24h+ window of dual-ingest where Hermes is "warm spare" while aim-3 prep happens.

The aim-2-3 holding-dir at `/tmp/aim2-extract/` is consumed by the `mv`; that path is empty after this plan (no separate cleanup task — `mv` removes the source).

## Acceptance criteria

1. `ssh aliyun-vitaclaw ls /root/.hermes/omonigraph-vault/lightrag_storage/graph_chunk_entity_relation.graphml` exits 0 (production path now populated).
2. `ssh aliyun-vitaclaw ls /tmp/aim2-extract/lightrag_storage/ 2>&1 | grep -c "No such file"` returns 1 (holding-dir consumed by `mv`).
3. `ssh aliyun-vitaclaw du -sh /root/.hermes/omonigraph-vault/lightrag_storage/` reports ≥ 1 GiB (matches aim-2-2 floor).
4. Hermes-side `~/.hermes/omonigraph-vault/lightrag_storage/` still exists, ALL files have mode `r--r--r--` (no `w` for any of user / group / other).
5. Hermes-side `find ~/.hermes/omonigraph-vault/lightrag_storage/ -perm -u+w` returns empty (no writable file remains).
6. Hermes-side `crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)" | wc -l` returns 11 (aim-2-1's paused 11 lines uncommented; matches the pre-pause baseline captured in STORAGE-01 evidence).
7. `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\STATE-Aliyun-Ingest-Migration-v1.md` contains a NEW line under "Pending Todos" of the form `- Hermes lightrag_storage cold-backup retention deadline: <YYYY-MM-DD> (set by aim-2-5; cleanup at aim-5 close or later)` where `<YYYY-MM-DD>` = aim-2-5 cutover date + 30 days. Edit is forward-only (line appended; existing lines untouched).
8. `EVIDENCE/STORAGE-05-cutover-evidence.md` exists, committed locally, contains: mv before/after `ls`, Hermes chmod before/after `ls -l`, retention deadline ISO date, Hermes resume crontab line count.

## Task list

### Task 1 — Agent promotes holding-dir to Aliyun production path via `mv`

**`<read_first>`**

- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-2-lightrag-storage-migration\EVIDENCE\STORAGE-04-count-evidence.md` (CRITICAL — verify Overall verdict = PASS before doing ANY mv. If FAIL, do NOT execute this task; abort per aim-2-4 abort/rollback.)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\STATE-Aliyun-Ingest-Migration-v1.md` line 133 (path correction — Aliyun production path is `/root/.hermes/omonigraph-vault/lightrag_storage/`, NOT `/opt/omnigraph-vault/`)
- Memory `aliyun_vitaclaw_ssh.md` (SSH alias).

**`<acceptance_criteria>`**

- aim-2-4 STORAGE-04 verdict = PASS confirmed by reading evidence file.
- `/root/.hermes/omonigraph-vault/` parent directory exists on Aliyun before mv (mkdir -p if missing).
- `/root/.hermes/omonigraph-vault/lightrag_storage/` does NOT pre-exist before mv (target must be empty / non-existent — guards against accidental overwrite of any pre-existing storage).
- After mv: production path contains `graph_chunk_entity_relation.graphml` + `kv_store_*.json`; holding-dir at `/tmp/aim2-extract/lightrag_storage/` is gone.
- `du -sh` on production path matches aim-2-2 storage floor (≥ 1 GiB).

**`<action>`**

```bash
# Pre-flight: re-confirm STORAGE-04 PASS by reading the evidence file
grep -E "Overall verdict.*PASS" .planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-04-count-evidence.md

# If the above grep prints nothing, ABORT — do not run any of the lines below.

ssh aliyun-vitaclaw bash -c "'
set -e

echo \"=== pre-flight: parent dir exists, target empty ===\"
mkdir -p /root/.hermes/omonigraph-vault/
ls -la /root/.hermes/omonigraph-vault/

if [ -d /root/.hermes/omonigraph-vault/lightrag_storage ]; then
  echo \"FATAL: production path already exists. Aborting cutover.\"
  echo \"Investigate: ls -la /root/.hermes/omonigraph-vault/lightrag_storage/\"
  exit 1
fi

echo \"=== pre-flight: holding-dir present and populated ===\"
ls -la /tmp/aim2-extract/lightrag_storage/ | head -10
du -sh /tmp/aim2-extract/lightrag_storage/

echo \"=== mv (atomic on same filesystem) ===\"
mv /tmp/aim2-extract/lightrag_storage /root/.hermes/omonigraph-vault/lightrag_storage

echo \"=== post-flight: production path populated ===\"
ls -la /root/.hermes/omonigraph-vault/lightrag_storage/ | head -10
du -sh /root/.hermes/omonigraph-vault/lightrag_storage/

echo \"=== post-flight: holding-dir consumed ===\"
ls /tmp/aim2-extract/ 2>&1 || echo \"(empty or absent — expected)\"

echo \"=== sentinel files present ===\"
ls /root/.hermes/omonigraph-vault/lightrag_storage/graph_chunk_entity_relation.graphml
ls /root/.hermes/omonigraph-vault/lightrag_storage/kv_store_text_chunks.json 2>/dev/null || echo \"(kv_store_text_chunks.json absent — note in evidence)\"
'"
```

If `/tmp/aim2-extract` and `/root/.hermes/omonigraph-vault/` are on different filesystems, `mv` will fall back to copy+unlink (slower but still atomic from the consumer's perspective — production path either fully materializes or doesn't exist). Verify with `df /tmp /root/.hermes` if mv takes > 60 seconds; both should report the same filesystem on a typical single-disk Aliyun ECS.

Capture all output to `.scratch/aim-2-5-cutover-mv-<TS>.log` for evidence Task 4.

### Task 2 — Operator sets Hermes-side storage read-only via `chmod -R a-w`

**`<read_first>`**

- The Aliyun production-path verification output from Task 1 (mv must have succeeded before the Hermes original is locked).
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-2-lightrag-storage-migration\EVIDENCE\STORAGE-01-pause-evidence.md` (re-confirm pause is still active — locking storage while Hermes ingest is somehow running could corrupt mid-write files even though the pause should hold).

**`<acceptance_criteria>`**

- Aliyun production path validated populated (Task 1 done) BEFORE Hermes chmod runs.
- All files under `~/.hermes/omonigraph-vault/lightrag_storage/` have mode `r--r--r--` after chmod.
- `find ~/.hermes/omonigraph-vault/lightrag_storage/ -perm -u+w` returns empty.
- Pause still verified active (`crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)" | wc -l == 0`) BEFORE chmod runs — ordering matters: pause active → chmod → resume cron in Task 3, NEVER chmod before pause check.
- Original storage is still readable (Hermes can serve as cold backup; not deleted, not unreadable, just read-only).

**`<action>`**

Agent writes the operator prompt:

```hermes-operator-prompt
The Aliyun cutover at aim-2-5 Task 1 succeeded — production path on Aliyun is now populated. Next step: set the Hermes-side LightRAG storage to read-only as a 30-day cold backup. Run on Hermes:

Step 1 — re-confirm pause still active (sanity):

```bash
echo "=== expected: 0 uncommented ingest lines ==="
crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)" | wc -l
```

If that returns anything other than 0, STOP and notify agent — pause was broken between aim-2-1 and now and the cold backup may not be a true pre-cutover snapshot.

Step 2 — capture before-state for evidence:

```bash
ls -la ~/.hermes/omonigraph-vault/lightrag_storage/ | head -5
du -sh ~/.hermes/omonigraph-vault/lightrag_storage/
```

Step 3 — set read-only recursively:

```bash
chmod -R a-w ~/.hermes/omonigraph-vault/lightrag_storage/
```

Step 4 — verify no writable file remains:

```bash
echo "=== expected: empty output ==="
find ~/.hermes/omonigraph-vault/lightrag_storage/ -perm -u+w

echo "=== sample mode check (expect r--r--r--) ==="
ls -la ~/.hermes/omonigraph-vault/lightrag_storage/ | head -5

echo "=== still readable (sanity) ==="
ls ~/.hermes/omonigraph-vault/lightrag_storage/graph_chunk_entity_relation.graphml
```

Step 5 — capture cutover timestamp for retention deadline calculation:

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ" | tee /tmp/aim2-cutover-ts.iso
```

Paste FULL output of all 5 steps. The timestamp from Step 5 + 30 days is the retention deadline that aim-2-5 Task 4 records into STATE-Aliyun-Ingest-Migration-v1.md.

```

### Task 3 — Operator resumes Hermes ingest crontab (uncomment 11 lines)

**`<read_first>`**
- The Hermes operator response from Task 2 (chmod must be done BEFORE resume — otherwise resumed cron may try to write to the storage during the brief window before chmod completes; technically the pause-then-chmod ordering protects this, but resume-after-chmod is the belt-and-suspenders path).
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-2-lightrag-storage-migration\EVIDENCE\STORAGE-01-pause-evidence.md` (matches the 11-line baseline that must be restored).

**`<acceptance_criteria>`**
- Hermes-side chmod (Task 2) verified complete BEFORE resume runs.
- All 11 commented `^#.*(ingest|kol_scan|rss)` lines have their leading `#` removed.
- `crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)" | wc -l` returns 11 (matches STORAGE-01 baseline).
- `crontab -l | grep -E "^#.*(ingest|kol_scan|rss)" | wc -l` returns 0 (no leftover commented ingest lines).
- Hermes ingest cron is back to authoritative ingest behavior — but note: aim-2 ends here; aim-3 will retire these 11 lines permanently. The resume here gives Hermes a warm-spare window during aim-3 prep.

**`<action>`**

Agent writes the operator prompt:

```hermes-operator-prompt
Step 1 — sanity check chmod complete (re-confirm Task 2 outcome):

```bash
echo "=== expected: empty output (no writable file) ==="
find ~/.hermes/omonigraph-vault/lightrag_storage/ -perm -u+w
```

If output is non-empty, STOP — Task 2 didn't complete cleanly.

Step 2 — capture before-state of crontab:

```bash
echo "=== current commented ingest lines (expect 11) ==="
crontab -l | grep -E "^#.*(ingest|kol_scan|rss)" | wc -l

echo "=== current uncommented ingest lines (expect 0 — pause active) ==="
crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)" | wc -l
```

Step 3 — uncomment all 11 ingest lines via `crontab -e`:

```bash
crontab -e
```

In the editor, for every line matching `^#.*(ingest|kol_scan|rss)` remove the leading `#` (and any single space directly after the `#` you may have added at aim-2-1 — restore the line to its pre-pause shape). Save and exit.

Step 4 — verify post-state:

```bash
echo "=== expected: 11 uncommented ingest lines (resumed) ==="
crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)" | wc -l

echo "=== expected: 0 commented ingest lines (none left over) ==="
crontab -l | grep -E "^#.*(ingest|kol_scan|rss)" | wc -l

echo "=== resume timestamp ==="
date -u +"%Y-%m-%dT%H:%M:%SZ" | tee /tmp/aim2-resume-ts.iso
```

Paste FULL output of all 4 steps. The resume timestamp from Step 4 closes the aim-2-1 → aim-2-5 pause window.

```

### Task 4 — Agent records 30-day retention deadline in STATE + writes STORAGE-05 evidence + commits

**`<read_first>`**
- All output from Tasks 1, 2, 3 (mv, chmod, resume).
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\STATE-Aliyun-Ingest-Migration-v1.md` lines 135-140 (`### Pending Todos` section — this is where the retention-deadline line will be appended; verify section header presence and current last line).

**`<acceptance_criteria>`**
- Retention deadline ISO date is computed as: cutover-timestamp from Task 2 Step 5 + 30 days, expressed as `YYYY-MM-DD` (date-only, not full ISO datetime).
- New line APPENDED under `### Pending Todos`; existing lines (lines 137-140) remain byte-identical (forward-only edit, no re-formatting, no removal).
- `EVIDENCE/STORAGE-05-cutover-evidence.md` exists and contains: mv before/after `ls`, Aliyun production-path `du -sh` post-mv, Hermes chmod before/after `ls -l` + `find -perm -u+w` outputs, retention deadline ISO date with calculation shown, Hermes crontab line counts before+after resume, full timeline summary (pause @ aim-2-1 TS / tar @ aim-2-2 TS / scp+extract @ aim-2-3 TS / count verify @ aim-2-4 TS / cutover @ aim-2-5 Task 2 TS / resume @ aim-2-5 Task 3 TS / total pause window minutes).
- Both files committed in TWO separate commits (forward-only; no `git add -A`):
  1. `git add .planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-05-cutover-evidence.md && git commit -m "docs(aim-2): record STORAGE-05 cutover evidence (5/5)"`
  2. `git add .planning/STATE-Aliyun-Ingest-Migration-v1.md && git commit -m "docs(aim-2): register 30-day Hermes cold-backup retention deadline (forward-only)"`
- No `git commit --amend` invoked. No previously-committed lines in STATE.md modified.

**`<action>`**

Step 1 — compute retention deadline. Use the cutover timestamp from Task 2 Step 5 (`/tmp/aim2-cutover-ts.iso`). For example, if cutover-ts is `2026-05-23T14:30:00Z`, deadline = `2026-06-22`.

```bash
# Agent computes locally; the cutover-ts comes from operator response of Task 2 Step 5
CUTOVER_TS="<paste cutover ISO from operator>"        # e.g. 2026-05-23T14:30:00Z
CUTOVER_DATE=$(echo "$CUTOVER_TS" | cut -dT -f1)      # e.g. 2026-05-23
DEADLINE=$(python -c "
from datetime import date, timedelta
d = date.fromisoformat('$CUTOVER_DATE')
print((d + timedelta(days=30)).isoformat())
")
echo "Cutover date: $CUTOVER_DATE"
echo "Retention deadline: $DEADLINE"
```

Step 2 — use Edit tool to append the retention line to `STATE-Aliyun-Ingest-Migration-v1.md`. Locate the last existing bullet under `### Pending Todos` (currently line 140: `- aim-1 execute ✅ DONE 2026-05-23 (commit 718c52d); UAT 7/7 PASS; aim-1-UAT.md; next: /gsd:plan-phase aim-2`). Insert AFTER it:

```text
- Hermes lightrag_storage cold-backup retention deadline: <DEADLINE> (set by aim-2-5; cleanup at aim-5 close or later)
```

Where `<DEADLINE>` is the ISO date computed in Step 1. Do NOT modify any other line. Do NOT remove the trailing aim-1 todo line. The Edit tool's `old_string` should be the full line 140 byte-for-byte; `new_string` should be that same line plus a `\n` plus the new retention-deadline bullet.

Step 3 — use Write tool to create `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-2-lightrag-storage-migration\EVIDENCE\STORAGE-05-cutover-evidence.md`:

```markdown
# STORAGE-05 — Cutover evidence

Phase: aim-2 (LightRAG storage full migration)
REQ: STORAGE-05

## Pre-cutover gate

- aim-2-4 STORAGE-04 verdict: **PASS** (per `EVIDENCE/STORAGE-04-count-evidence.md`)
- All four count fields (entities / relations / chunks / kv_keys) byte-identical between Hermes-source and Aliyun holding-dir.

## Aliyun mv (Task 1)

Source: `/tmp/aim2-extract/lightrag_storage/`
Target: `/root/.hermes/omonigraph-vault/lightrag_storage/`

### Pre-flight

```text
[paste pre-flight ls + du output from .scratch/aim-2-5-cutover-mv-<TS>.log]
```

### Post-flight

```text
[paste post-flight ls + du output]
```

### Holding-dir consumed

```text
[paste "ls /tmp/aim2-extract/" output — should show empty or "No such file"]
```

## Hermes chmod (Task 2)

### Before

```text
[paste output of "ls -la ~/.hermes/omonigraph-vault/lightrag_storage/ | head -5" + "du -sh ~/.hermes/omonigraph-vault/lightrag_storage/"]
```

### After

```text
[paste output of "find ~/.hermes/omonigraph-vault/lightrag_storage/ -perm -u+w" — must be EMPTY]
[paste output of "ls -la ~/.hermes/omonigraph-vault/lightrag_storage/ | head -5" — modes should be r--r--r--]
[paste output of "ls ~/.hermes/omonigraph-vault/lightrag_storage/graph_chunk_entity_relation.graphml" — confirms still readable]
```

### Cutover timestamp (UTC)

`<paste content of /tmp/aim2-cutover-ts.iso from Task 2 Step 5>`

## Hermes crontab resume (Task 3)

### Before resume

- Commented ingest lines (`^#.*(ingest|kol_scan|rss)`): **11**
- Uncommented ingest lines: **0**

### After resume

- Commented ingest lines: **0**
- Uncommented ingest lines: **11** (matches STORAGE-01 pre-pause baseline)

### Resume timestamp (UTC)

`<paste content of /tmp/aim2-resume-ts.iso from Task 3 Step 4>`

## 30-day retention deadline

| Field | Value |
|-------|-------|
| Cutover date (UTC, date-only) | `<CUTOVER_DATE>` |
| +30 days | `<DEADLINE>` |
| Recorded at | `STATE-Aliyun-Ingest-Migration-v1.md` § Pending Todos (forward-only append) |
| Cleanup window | Earliest = aim-5 close; latest = `<DEADLINE>` |

## Phase timeline summary

| Step | UTC timestamp | Source |
|------|---------------|--------|
| aim-2-1 pause | `<TS>` | `/tmp/aim2-pause-active.iso` |
| aim-2-2 tar.gz complete | `<TS>` | `EVIDENCE/STORAGE-02-tar-evidence.md` |
| aim-2-3 scp + extract complete | `<TS>` | `EVIDENCE/STORAGE-03-transfer-evidence.md` |
| aim-2-4 count verify PASS | `<TS>` | `EVIDENCE/STORAGE-04-count-evidence.md` |
| aim-2-5 mv complete | `<TS>` | this file (Task 1 log) |
| aim-2-5 Hermes chmod complete | `<TS>` | this file (cutover-ts) |
| aim-2-5 Hermes resume | `<TS>` | this file (resume-ts) |
| **Total Hermes pause window** | **<MINUTES>** | resume-ts − pause-ts (Q2a constraint #1: ≥30min OK) |

## Decision

Aim-2 phase **CLOSED — STORAGE-01..05 all PASS**. Aliyun has authoritative LightRAG storage at production path. Hermes has read-only cold backup with 30-day retention. 11-line Hermes ingest cron resumed (warm-spare window until aim-3 retires it).

Next: `/gsd:plan-phase aim-3` (cutover proper — systemd timer + kol_scan.db handoff + Hermes crontab clear).

```

Step 4 — commit (TWO separate commits, forward-only):

```bash
# Commit 1: evidence file
git add .planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-05-cutover-evidence.md
git commit -m "docs(aim-2): record STORAGE-05 cutover evidence (5/5)"

# Commit 2: STATE retention deadline (separate commit so the 30-day reminder is bisectable / revertable independently)
git add .planning/STATE-Aliyun-Ingest-Migration-v1.md
git commit -m "docs(aim-2): register 30-day Hermes cold-backup retention deadline (forward-only)"
```

## Abort/rollback protocol

| Condition | Action |
| --- | --- |
| STORAGE-04 verdict not PASS at start of Task 1 | **DO NOT execute Task 1.** Return to aim-2-4 abort/rollback. Hermes resume already happened there if needed. |
| Task 1: Aliyun production path pre-exists (mv guard fires) | STOP. Investigate via `ssh aliyun-vitaclaw ls -la /root/.hermes/omonigraph-vault/`. If pre-existing storage is from an earlier failed cutover attempt and is empty / partial → `rm -rf /root/.hermes/omonigraph-vault/lightrag_storage` and retry Task 1. If pre-existing storage is non-empty and unknown provenance → DO NOT delete. Notify user. Phase aborts; Hermes pause must end via aim-2-1 reverse before any further work. |
| Task 1: mv fails mid-stream (cross-filesystem copy interrupted, e.g. SIGKILL on long copy) | Aliyun may have partial files at production path. (a) `ssh aliyun-vitaclaw rm -rf /root/.hermes/omonigraph-vault/lightrag_storage`; (b) Holding-dir at `/tmp/aim2-extract/lightrag_storage/` may also be partially gone. If so, restart from aim-2-3 Task 3 (re-extract from tar.gz on Aliyun — tar.gz at `/root/aim2-incoming/` is unchanged); (c) Hermes pause still active, no Hermes action needed yet. |
| Task 2: pause check at Step 1 returns non-zero (uncommented ingest lines exist on Hermes) | The pause was broken between aim-2-1 and now. The "cold backup" we're about to lock would not be a true pre-cutover snapshot. STOP. The cutover already happened at Task 1 — Aliyun production-path storage is already byte-identical to the Hermes state captured at aim-2-3 / aim-2-4. Skip the chmod (Hermes storage stays writable; user may either: keep it as a writable backup, or run a NEW STORAGE-04-style verify to compare current Hermes vs Aliyun and resolve drift before chmod). Do not silently chmod a drifted snapshot. |
| Task 2: chmod fails (permission denied — should not happen for user-owned files but guard anyway) | Investigate file ownership: `ls -la ~/.hermes/omonigraph-vault/lightrag_storage/ | head -5`. If files are owned by a different user (sudo previous), use `sudo chmod -R a-w` instead. Document the deviation in evidence. |
| Task 3: post-resume uncommented count ≠ 11 | Some lines weren't uncommented OR extra lines got uncommented. Operator re-runs `crontab -e` to fix. If unrecoverable, capture full `crontab -l` output for evidence and surface to user — Aliyun side is fine, only Hermes cron baseline drifted. |
| Task 4: Edit tool fails to find the exact line 140 byte-match (STATE.md was modified between aim-2 plan-phase and aim-2-5 execute) | Re-read STATE.md current state, locate the actual last line of `### Pending Todos`, retarget the Edit. Do NOT use Write (would lose other forward-only edits). |
| Task 4: git commit hook fails | Investigate hook output. Both commits are independent — if commit 1 fails, fix and retry commit 1 alone before commit 2. Do NOT `git reset` to combine them; forward-only. |

## Resume Hermes operator prompt (for use ONLY on Task 1 / Task 2 abort BEFORE Hermes chmod has succeeded)

If Task 1 mv fails AND we want Hermes back online while we investigate, agent writes this prompt:

```hermes-operator-prompt
ABORT recovery from aim-2-5 mv failure (cutover did NOT complete; Aliyun production path is empty or partial; Hermes original storage is still writable). Resume Hermes ingest crontab. Run:

```bash
echo "=== current commented ingest lines ==="
crontab -l | grep -E "^#.*(ingest|kol_scan|rss)" | wc -l

# Edit crontab and remove the leading `#` from every commented ingest/kol_scan/rss line
crontab -e

echo "=== verify uncommented count == 11 ==="
crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)" | wc -l

echo "=== resume timestamp ==="
date -u +"%Y-%m-%dT%H:%M:%SZ" | tee /tmp/aim2-pause-resumed.iso
```

Paste output. Hermes is back to authoritative ingest. Do NOT run Task 2 chmod — Hermes storage stays writable until aim-2 retry from aim-2-1.

```

If Task 2 chmod has already succeeded but Task 3 resume fails, the chmod is fine to leave in place — Hermes storage is read-only (cold backup) but ingest cron is broken. Operator needs only to fix the cron resume; no chmod reverse needed.

## Evidence to capture

- `.scratch/aim-2-5-cutover-mv-<TS>.log` (agent-side mv stdout/stderr).
- Operator response to Task 2 Hermes prompt (chmod before/after + cutover-ts).
- Operator response to Task 3 Hermes prompt (resume crontab + resume-ts).
- `EVIDENCE/STORAGE-05-cutover-evidence.md` (synthesizes all of the above + retention-deadline computation + phase timeline).
- STATE-Aliyun-Ingest-Migration-v1.md `### Pending Todos` section gains 1 new line; previous lines unchanged.
