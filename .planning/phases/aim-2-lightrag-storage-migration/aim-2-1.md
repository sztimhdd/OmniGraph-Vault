---
plan_id: aim-2-1
phase: aim-2
wave: 1
depends_on: []
requirements_addressed:
  - STORAGE-01
files_modified:
  - .planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-01-pause-evidence.md
autonomous: false
t_shirt: S
---

# aim-2-1 — Hermes ingest pause (STORAGE-01)

## Goal

Pause **all 11 Hermes ingest-related cron entries** for the entire aim-2 tar + scp + verify + cutover window (≥ 30 min). Pause is achieved by an operator-driven `crontab -e` edit on Hermes that comments out (NOT deletes) every ingest entry. The pause is verified to be effective via `pgrep -f batch_ingest_from_spider` returning empty (no in-flight workers). This plan delivers ONLY the pause and its evidence; STORAGE-02 (tar) is the next gate.

This is the gating wave for the entire phase: nothing in STORAGE-02..05 may execute until pause is verified, because the storage on disk MUST stop changing during the tar window or the byte-identical guarantee at STORAGE-04 cannot hold.

## Acceptance criteria

All four must be true before declaring this plan done:

1. Hermes `crontab -l` output shows every ingest-related entry **commented out** with a leading `#`. Sentinel command: `crontab -l | grep -E "^#.*(ingest|kol_scan|rss)"` returns ≥ 11 lines AND `crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)"` returns 0 lines.
2. Hermes `pgrep -f batch_ingest_from_spider` returns **empty** (exit code 1). If non-empty, abort plan and wait for in-flight workers; do NOT proceed to aim-2-2.
3. Pause-start ISO timestamp captured in `EVIDENCE/STORAGE-01-pause-evidence.md`.
4. The evidence file is committed locally (forward-only commit; `git add` explicit path; no `-A`).

## Task list

### Task 1 — Operator pauses Hermes crontab

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\STATE-Aliyun-Ingest-Migration-v1.md` lines 80-90 (Hermes Operational State; the 11 ingest cron entries)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` line 51 (STORAGE-01 wording — pause method, verify method, resume protocol)

**`<acceptance_criteria>`**
- Operator-side: `crontab -l | grep -E "^#.*(ingest|kol_scan|rss)" | wc -l` returns ≥ 11.
- Operator-side: `crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)" | wc -l` returns 0.
- Operator-side: `pgrep -f batch_ingest_from_spider` exit code = 1 (empty stdout).
- Operator-side: `pgrep -f batch_scan_kol` exit code = 1 (empty stdout).
- Operator-side: `pgrep -f rss_ingest` exit code = 1 (empty stdout).

**`<action>`**

Agent writes the following operator prompt and asks the user to forward it to Hermes verbatim. The user pastes the Hermes terminal output back; the agent records it in the evidence file in Task 2.

```hermes-operator-prompt
You are operating the Hermes production host (家用 PC, WSL2). Run these commands in a single SSH session and paste the FULL output back to the local Claude Code session.

This is the aim-2 LightRAG storage migration "pause Hermes" gate. After this gate, a tar.gz of ~/.hermes/omonigraph-vault/lightrag_storage/ will be created on Hermes and SCP'd to Aliyun. The pause MUST stay in effect until the local agent says "STORAGE-04 verify passed, you may resume." Do NOT resume on your own initiative.

Step 1 — capture pre-pause state (read-only):

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ" | tee /tmp/aim2-pause-start.iso
echo "=== crontab BEFORE pause ==="
crontab -l
echo "=== running ingest workers BEFORE pause ==="
pgrep -af batch_ingest_from_spider || echo "NONE"
pgrep -af batch_scan_kol || echo "NONE"
pgrep -af rss_ingest || echo "NONE"
```

Step 2 — pause crontab. Edit with `crontab -e` and PREFIX EVERY LINE that matches ingest/kol_scan/rss with a leading `#`. Do NOT delete lines (we restore by removing the `#`). The 11 lines you are commenting out match the ingest-loop crons (daily-ingest 09:00 / afternoon-ingest 14:00 / evening-ingest 21:00 ADT) plus 8 supporting jobs (每日KOL扫描, KOL扫描前健康检查, rss-fetch, daily-digest, vertex-probe-monthly, etc.).

After saving, verify:

```bash
echo "=== commented ingest lines (expect >= 11) ==="
crontab -l | grep -E "^#.*(ingest|kol_scan|rss)" | wc -l
echo "=== UNCOMMENTED ingest lines (expect 0) ==="
crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)" | wc -l
```

Step 3 — wait for in-flight workers to finish. If any of these have output, sleep 60 and re-run until all three are empty:

```bash
pgrep -af batch_ingest_from_spider || echo "NONE"
pgrep -af batch_scan_kol || echo "NONE"
pgrep -af rss_ingest || echo "NONE"
```

Step 4 — capture pause-confirmed state:

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ" | tee /tmp/aim2-pause-confirmed.iso
echo "=== crontab AFTER pause ==="
crontab -l
echo "=== running ingest workers AFTER pause (expect ALL empty) ==="
pgrep -af batch_ingest_from_spider; echo "exit=$?"
pgrep -af batch_scan_kol; echo "exit=$?"
pgrep -af rss_ingest; echo "exit=$?"
```

Paste the FULL output of all four steps back. Do NOT skip any step. Do NOT abbreviate "..." anything. The agent needs the full text to write the evidence file.
```

After receiving the operator output, the agent moves to Task 2.

### Task 2 — Agent writes STORAGE-01 evidence file and commits

**`<read_first>`**
- The full operator response from Task 1 (pasted in chat)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\CLAUDE.md` PRINCIPLE 5 (don't outsource SSH) — this plan honors it: Hermes mutating ops via operator prompt, NOT agent SSH.

**`<acceptance_criteria>`**
- File `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-2-lightrag-storage-migration\EVIDENCE\STORAGE-01-pause-evidence.md` exists.
- File contains literal pause-start ISO timestamp from `/tmp/aim2-pause-start.iso`.
- File contains literal commented-line count (≥ 11).
- File contains literal pgrep exit codes (= 1 for all three).
- `git log -1 --name-only EVIDENCE/STORAGE-01-pause-evidence.md` returns a commit on `main` authored by current user.
- `git status` reports clean working tree on the local repo (no `-A` collateral; only this evidence file committed).

**`<action>`**

```bash
# Run from the repo root (c:\Users\huxxha\Desktop\OmniGraph-Vault)
mkdir -p .planning/phases/aim-2-lightrag-storage-migration/EVIDENCE
```

Use the Write tool to create `.planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-01-pause-evidence.md` with body:

```markdown
# STORAGE-01 — Hermes ingest pause evidence

Phase: aim-2 (LightRAG storage full migration)
REQ: STORAGE-01

## Pause-start ISO (UTC)

[paste contents of /tmp/aim2-pause-start.iso from operator output]

## Pause-confirmed ISO (UTC)

[paste contents of /tmp/aim2-pause-confirmed.iso from operator output]

## Crontab BEFORE pause (verbatim)

```
[paste verbatim Step 1 `crontab -l` output]
```

## Crontab AFTER pause (verbatim — every ingest line MUST start with `#`)

```
[paste verbatim Step 4 `crontab -l` output]
```

## Sentinel checks

- Commented ingest lines count: [N] (required ≥ 11)
- Uncommented ingest lines count: [N] (required == 0)
- pgrep batch_ingest_from_spider exit code: [N] (required == 1)
- pgrep batch_scan_kol exit code: [N] (required == 1)
- pgrep rss_ingest exit code: [N] (required == 1)

## Resume protocol

Hermes resumes ONLY after:
- (a) STORAGE-04 verify passes AND aim-2-5 cutover completes; OR
- (b) Any of STORAGE-01..04 fails (per Abort/rollback below) — in this case Hermes resume happens BEFORE retrying the failed stage.

Resume command (uncomment the 11 lines):
```bash
crontab -e   # remove leading `#` from each ingest/kol_scan/rss line
crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)" | wc -l   # expect 11
```
```

Then commit:

```bash
# explicit add — NEVER `git add -A` / `git add .` per feedback_git_add_explicit_in_parallel_quicks.md
git add .planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-01-pause-evidence.md
git commit -m "docs(aim-2): record STORAGE-01 Hermes ingest pause evidence"
```

## Abort/rollback protocol

If any of these conditions hold, ABORT this plan:

| Condition | Action |
| --- | --- |
| Operator reports `pgrep -f batch_ingest_from_spider` non-empty after 10 min wait | DO NOT proceed to aim-2-2. Wait additional 10 min. If still non-empty after 30 min total, abort plan; investigate via separate quick. |
| Operator reports commented-ingest-line count < 11 | Re-run Step 2 with operator; some entries were missed. |
| Operator reports any error opening `crontab -e` | Abort plan; do not proceed. |
| Operator dropped session before Step 4 confirmation | Re-run entire prompt from Step 1; confirm pause is actually in effect. |

If pause ABORTS for any reason, Hermes resume is automatic: crontab `#` lines stay only as long as operator wants — the operator may `crontab -e` them back any time. No `chmod` or other action needed.

## Evidence to capture

- `EVIDENCE/STORAGE-01-pause-evidence.md` (this file) — committed locally to main.

That is the only artifact of this plan. STORAGE-02..05 produce additional EVIDENCE files.
