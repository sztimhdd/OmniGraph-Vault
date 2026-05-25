---
plan_id: aim-5-3
phase: aim-5
wave: 2
depends_on:
  - aim-5-6
requirements_addressed:
  - STAB-03
files_modified:
  - .planning/phases/aim-5-stability-watch/aim-5-3-EVIDENCE.md
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-1.log
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-2.log
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-3.log
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-4.log
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-5.log
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-6.log
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-7.log
  - .planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md
autonomous: true
t_shirt: S
---

# aim-5-3 — STAB-03 Hermes daily-pull + Databricks git-pull watch + aim-4-4 TODO closure

## Goal

Daily read-only watch of the **two SYNC-03 consumers**:
1. Hermes `omnigraph-daily-pull.service` systemd timer (fires 02:00 ADT
   = 05:00 UTC after aim-4-3 cutover) — verified via journal grep for
   `sync OK on attempt N` + 48h marker file age check
2. Databricks-side `git pull` consumer — verified via day-7 spot-check
   `cd <databricks-repo>; git log -1 kb/wiki/` showing commit timestamp
   ≥ aim-4 deploy

This plan **also closes the 4-item TODO checklist deferred from
aim-4-4-EVIDENCE PARTIAL** (per `.planning/STATE-Aliyun-Ingest-Migration-v1.md:143`
+ `aim-5-CONTEXT.md` FINDING 8). aim-4-4 was the natural checkpoint plan
because it shipped the SYNC-03 verification + Aliyun manual wiki commit
runbooks; aim-5-3 closes its open items.

REQ STAB-03 verbatim
(`.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` line 82):

> **STAB-03**: Daily sync (SYNC-02 cron on Hermes + Databricks
> `git pull`) succeeds 7 consecutive days with **zero** failures (no
> 3-retry-exhausted events, no 48h marker triggers from SYNC-04). §7
> SC #8. Failure-day count tolerance is 0 — a single failed day
> restarts the 7-day window.

Per FINDING 7, STAB-03 has TWO daily checks (Hermes journal probe +
marker-file probe) and ONE day-7 check (Databricks git log). Failure-
day tolerance is 0 across both consumers.

Per FINDING 9, all probes are read-only — labeled `[agent-runnable]`.
The agent SSHes Hermes (port 49221, user sztimhdd) via memory pointer
`hermes_ssh.md`. Databricks day-7 spot-check may require operator-side
intervention (Databricks workspace SSH path is non-standard); plan
emits an `[agent-runnable]` attempt first, falls back to operator
prompt only if direct access fails.

## Acceptance criteria

1. For each day N in 1..7, a daily probe runs against Hermes and
   captures stdout into `aim-5-EVIDENCE/daily-checks-day-N.log`,
   prepended with `=== STAB-03 day N ===`.
2. Per-day Hermes probe captures:
   - `journalctl -u omnigraph-daily-pull.service --since "24 hours ago"`
     output, grepped for `sync OK|sync attempt|ERROR|Failed`
   - Marker file age check: `ls -la /tmp/aliyun-sync-failed-* 2>/dev/null`
   - Timer next-fire status: `systemctl list-timers omnigraph-daily-pull.timer --no-pager`
3. Per-day pass criterion (must hold every day):
   - At least one `sync OK on attempt N` line in last 24h journal
   - No `aliyun-sync-failed-*` marker file aged > 48h
   - Timer is `enabled` + `active`
4. Day-7 Databricks `git log -1 kb/wiki/` probe runs ONCE on day 7
   (after first natural Hermes timer fire + at least one Aliyun manual
   wiki commit have occurred — preconditions per
   `docs/runbooks/aim-4-databricks-sync03-verify.md`):
   - timestamp ≥ aim-4 deploy timestamp (= aim-4-3 commit `b522f64` @
     `2026-05-24 21:15:28 -0300`, per `aim-4-4-EVIDENCE.md` lines 13-19)
   - commit hash captured into evidence
5. **Failure-day tolerance: 0** (per FINDING 1). ANY single failed day
   on Hermes journal probe OR a marker-file > 48h triggers RESTART of
   the 7-day window.
6. **aim-4-4 TODO carry-over closure** (4 items, verbatim from
   `aim-4-4-EVIDENCE.md` lines 53-65 — per FINDING 8):

   - [ ] Path A deploy key actually generated on Aliyun + registered
         read-write on the GitHub repo. Deferred — first wiki commit
         will trigger this setup if Path A is the chosen route.
   - [ ] Path B patch round-trip exercised end-to-end. Deferred — only
         relevant if Path A is blocked by GitHub admin or corp network.
   - [ ] First real wiki commit verified at the Databricks consumer via
         `git log -1 kb/wiki/`. Deferred — depends on
         LLM-Wiki-Integration-P2 (or operator) producing the first wiki
         content commit.
   - [ ] aim-5 STAB checkpoint will close all 4 items above (collect
         Databricks `git log -1 kb/wiki/` stdout, Aliyun wiki commit
         hash, PASS verdict, append forward-only to this evidence file).

   At day-7, this plan appends a **forward-only correction block** to
   `.planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md` recording:
   the Databricks `git log -1 kb/wiki/` stdout, the Aliyun wiki commit
   hash that produced it, the per-item closure status (closed / still
   open with reason), and a final PASS / PARTIAL verdict.
7. `aim-5-3-EVIDENCE.md` exists at day-7 with:
   - 7 daily Hermes verdicts (sync OK present? marker age?)
   - Day-7 Databricks `git log -1 kb/wiki/` stdout + verdict
   - aim-4-4 TODO 4-item closure status (4/4 / 3/4 / 2/4 / 1/4 / 0/4)
   - Aggregate STAB-03 verdict: PASS / RESTART
8. Forward-only commits per CLAUDE.md 2026-05-15 #1 + memory
   `feedback_no_amend_in_concurrent_quicks.md`. Day-7 commit MAY
   include both `aim-5-3-EVIDENCE.md` AND the appended correction block
   in `aim-4-4-EVIDENCE.md` in a single commit.

## Tasks

### Task 1 — Daily Hermes probe (run once per day, day 1..7) `[agent-runnable]`

**`<read_first>`**
- `aim-5-CONTEXT.md` lines 316-331 (STAB-03 daily probe pattern)
- `aim-5-CONTEXT.md` FINDING 2 (Hermes WSL2 TZ = America/Halifax)
- `aim-5-CONTEXT.md` FINDING 7 (two consumers, two checks)
- Memory `hermes_ssh.md` (Hermes port 49221, user sztimhdd)
- `docs/runbooks/aim-4-databricks-sync03-verify.md` (preconditions for
  day-7 Databricks probe)

**`<acceptance_criteria>`**
- Daily log file `aim-5-EVIDENCE/daily-checks-day-N.log` contains a
  `=== STAB-03 day N ===` section with: journal grep result, marker
  file ls output, timer list output, per-day verdict.

**`<action>`**

Run via the Bash tool — one invocation per day (day 1..7):

```bash
DAY=N   # 1..7
LOG=.planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-${DAY}.log
mkdir -p "$(dirname "$LOG")"

{
  echo "=== STAB-03 day $DAY ==="
  ssh -p 49221 sztimhdd@ohca.ddns.net '
    date -u; date
    echo "--- last 24h omnigraph-daily-pull journal ---"
    journalctl -u omnigraph-daily-pull.service --since "24 hours ago" --no-pager | \
      grep -E "sync OK|sync attempt|ERROR|Failed" || echo "(empty)"
    echo "--- marker file age ---"
    ls -la /tmp/aliyun-sync-failed-* 2>/dev/null | head -5 || echo "(no marker — good)"
    echo "--- timer next fire ---"
    systemctl list-timers omnigraph-daily-pull.timer --no-pager
  '
} >> "$LOG" 2>&1

# Per-day verdict (executor manually inspects log):
# PASS conditions ALL must hold:
# 1. At least one "sync OK on attempt N" line in 24h journal
# 2. No marker files OR marker file aged < 48h
# 3. Timer status shows "active" + "enabled"
```

**Marker-age computation (manual):**

```bash
# If marker exists, compute age
MARKER=$(ssh -p 49221 sztimhdd@ohca.ddns.net 'ls /tmp/aliyun-sync-failed-* 2>/dev/null | head -1')
if [ -n "$MARKER" ]; then
  MARKER_AGE_HOURS=$(ssh -p 49221 sztimhdd@ohca.ddns.net "echo \$(( (\$(date +%s) - \$(stat -c %Y $MARKER)) / 3600 ))")
  echo "marker_age_hours=$MARKER_AGE_HOURS"
  # FAIL if > 48
fi
```

### Task 2 — Day-7 Databricks `git log -1 kb/wiki/` probe `[agent-runnable preferred, operator-fallback]`

**`<read_first>`**
- `docs/runbooks/aim-4-databricks-sync03-verify.md` (full verification
  procedure, preconditions, fail diagnosis)
- `aim-4-4-EVIDENCE.md` lines 13-19 (aim-4 deploy timestamp =
  `b522f64` @ `2026-05-24 21:15:28 -0300`)
- `aim-5-CONTEXT.md` FINDING 7 (Databricks SSH path non-standard;
  may require operator)

**`<acceptance_criteria>`**
- One of the following is captured in `aim-5-EVIDENCE/daily-checks-day-7.log`
  under `=== STAB-03 day 7 Databricks probe ===`:
  - **Direct probe success:** stdout from `git log -1 kb/wiki/
    --format='%H %ai %s'` on the Databricks Repos checkout, with
    timestamp ≥ aim-4 deploy timestamp
  - **Operator-fallback:** explicit operator prompt emitted +
    operator's reply pasted into log; same fields captured
- Probe verdict line: `STAB-03 day 7 Databricks: PASS / FAIL` recorded.

**`<action>`**

First, attempt agent-runnable direct probe (per CLAUDE.md "Databricks
Apps logs WebSocket" memory area + memory
`databricks_llm_api_local_invocation.md` — Databricks workspace API
auth available via `WorkspaceClient(profile="dev", auth_type="pat")`):

```bash
LOG=.planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-7.log

{
  echo "=== STAB-03 day 7 Databricks probe ==="
  date -u; date
  # Path 1: if Databricks Repos checkout is accessible via Databricks SDK file API
  # (databricks workspace export-dir) — this can pull the .git metadata for git log inspection.
  # Reference: CLAUDE.md "Databricks SSG lang flip" — workspace path is
  # /Workspace/Users/hhu@edc.ca/<project> on adb-2717931942638877.
  databricks workspace list /Workspace/Users/hhu@edc.ca/ --profile dev 2>&1 | grep OmniGraph || \
    echo "(no OmniGraph repo at expected workspace path)"

  # Path 2: if a databricks Job runs `git log -1 kb/wiki/` on the workspace clone,
  # invoke it via `databricks bundle run`. Defer to operator if no such job exists.
} >> "$LOG" 2>&1
```

If direct probe is not feasible (Databricks Repos `git log` is not
exposed via the SDK + no pre-existing job), emit an operator prompt
to the user:

```text
[OPERATOR PROMPT — aim-5-3 day-7 Databricks probe]

Please run on the Databricks Repos checkout of OmniGraph-Vault
(workspace path: /Workspace/Users/hhu@edc.ca/<project-folder>):

  cd <databricks-repo>
  git pull
  git log -1 kb/wiki/ --format='%H %ai %s'

Paste stdout back. Acceptance: timestamp ≥ 2026-05-24 21:15:28 -0300
(aim-4 deploy = commit b522f64 on `main`).

If timestamp < aim-4 deploy:
  - Confirm Aliyun manual wiki commit ran post-aim-4 deploy (per
    `docs/runbooks/aim-4-aliyun-wiki-commit.md`)
  - Confirm Hermes `omnigraph-daily-pull.timer` natural fire happened
    (verify aim-5-3 daily Hermes probes ≥ 1 PASS day)
```

Append the operator's reply to the log under the same `=== STAB-03 day 7
Databricks probe ===` header.

### Task 3 — aim-4-4 TODO carry-over closure (forward-only append) `[agent-runnable]`

**`<read_first>`**
- `.planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md` (full file —
  identify the "Deferred operator action" section + 4-item TODO
  checklist at lines 38-65)
- Memory `feedback_git_add_explicit_in_parallel_quicks.md` (forward-
  only correction discipline)
- Memory `feedback_no_amend_in_concurrent_quicks.md`

**`<acceptance_criteria>`**
- A new section `## aim-5-3 closure (appended <ts>)` is appended to
  `.planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md` (forward-
  only — do NOT edit prior content; only append at EOF).
- The appended section contains:
  - Per-item closure status for all 4 TODO items (`[x]` closed with
    evidence, `[ ]` still open with reason)
  - Aliyun wiki commit hash that triggered the Databricks pull (if any)
  - Databricks `git log -1 kb/wiki/` stdout (from Task 2)
  - Final aim-4-4 PASS / PARTIAL verdict
- aim-4-4 status field is updated by the appended block from PARTIAL
  to PASS (if all 4 items closed) or remains PARTIAL with carry-over
  to next milestone if any item is still open.

**`<action>`**

Use the `Edit` tool to append a closure section to
`.planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md`. Skeleton:

```markdown
## aim-5-3 closure (appended <YYYY-MM-DD HH:MM ADT>)

**Source:** aim-5-3 plan (Wave 3 day-7 Databricks probe + carry-over
closure). This is a forward-only append; the original "PARTIAL" record
above stays intact for traceability.

### TODO item closures

- [x]/[ ] **Item 1 (Path A deploy key on Aliyun)**: <closed: evidence
       hash / open: reason>
- [x]/[ ] **Item 2 (Path B patch round-trip)**: <closed: evidence /
       open: not exercised because Path A succeeded / open: blocked
       by reason>
- [x]/[ ] **Item 3 (Databricks `git log -1 kb/wiki/` first wiki commit
       verified)**: <closed: stdout below / open: reason>
- [x]/[ ] **Item 4 (aim-5 STAB checkpoint closure)**: <closed: this
       block is the closure / open: incomplete>

### Aliyun wiki commit hash

<commit hash> @ <ISO timestamp> — produced by manual run of
`docs/runbooks/aim-4-aliyun-wiki-commit.md` on Aliyun

### Databricks `git log -1 kb/wiki/` stdout

```
<commit hash> <ISO timestamp> <subject>
```

(Captured via aim-5-3 Task 2 — direct probe / operator prompt.)

### Verdict

**aim-4-4 status:** PASS (all 4 TODO items closed) / PARTIAL (X/4 closed,
remaining items carry to <next milestone>)

### References

- aim-5-3-EVIDENCE.md (parent closure)
- `docs/runbooks/aim-4-databricks-sync03-verify.md`
```

### Task 4 — Day-7 verdict + aim-5-3-EVIDENCE.md `[agent-runnable]`

**`<read_first>`**
- 7 daily logs (STAB-03 sections)
- `aim-5-CONTEXT.md` FINDING 1 (tolerance 0)

**`<acceptance_criteria>`**
- `aim-5-3-EVIDENCE.md` exists with:
  - 7 daily Hermes verdicts table
  - Day-7 Databricks probe stdout + verdict
  - aim-4-4 TODO 4-item closure score (X/4)
  - Aggregate STAB-03 verdict: PASS / RESTART
- Single forward-only commit on `main` containing:
  - `aim-5-3-EVIDENCE.md`
  - `aim-4-4-EVIDENCE.md` (with appended closure section)
  - Any uncommitted daily logs
- Conventional commit message: `docs(aim-5): STAB-03 7-day verdict + aim-4-4 TODO closure (aim-5-3)`.
- `git status` clean post-commit.

**`<action>`**

Author `aim-5-3-EVIDENCE.md`:

```markdown
# aim-5-3 — STAB-03 7-day Hermes daily-pull + Databricks git-pull evidence

**Timestamp:** <day-7 ts>
**Plan:** aim-5-3
**REQs:** STAB-03 + closes aim-4-4 TODO carry-over (4 items)
**Status:** PASS / RESTART

## Per-day Hermes verdicts

| Day | Date (ADT) | sync OK present? | marker file age (h) | timer status | verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | <ts> | ✅/❌ | <h or n/a> | active | PASS/FAIL |
| 2 | <ts> | ... | ... | ... | ... |
| 3 | <ts> | ... | ... | ... | ... |
| 4 | <ts> | ... | ... | ... | ... |
| 5 | <ts> | ... | ... | ... | ... |
| 6 | <ts> | ... | ... | ... | ... |
| 7 | <ts> | ... | ... | ... | ... |

## Day-7 Databricks probe

Direct probe attempted: <yes/no, with method>
Operator prompt fallback used: <yes/no>

`git log -1 kb/wiki/` stdout:
```
<hash> <ISO timestamp> <subject>
```

aim-4 deploy timestamp reference: `b522f64` @ `2026-05-24 21:15:28 -0300`

Verdict: PASS (≥) / FAIL (<)

## aim-4-4 TODO carry-over closure

| Item | Status | Evidence |
| --- | --- | --- |
| 1 — Path A deploy key on Aliyun | closed/open | <evidence or reason> |
| 2 — Path B patch round-trip | closed/open | ... |
| 3 — First wiki commit verified at Databricks | closed/open | ... |
| 4 — aim-5 STAB checkpoint closure | closed | this file + appended block in aim-4-4-EVIDENCE.md |

Closure score: X/4

## Aggregate verdict

**STAB-03:** PASS / RESTART (failure-day tolerance 0; both consumers must pass)

## References

- REQUIREMENTS STAB-03 (line 82)
- aim-5 CONTEXT FINDING 1 + FINDING 7 + FINDING 8
- `docs/runbooks/aim-4-databricks-sync03-verify.md`
- `aim-4-4-EVIDENCE.md` (appended closure block)
```

Commit:

```bash
git add .planning/phases/aim-5-stability-watch/aim-5-3-EVIDENCE.md \
        .planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md \
        .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-*.log
git status   # confirm only intended files staged
git commit -m "docs(aim-5): STAB-03 7-day verdict + aim-4-4 TODO closure (aim-5-3)"
git log -1 --name-only
```

## Risk and mitigation

| Risk | Mitigation |
| ---- | ---------- |
| Hermes WSL2 host TZ = America/Halifax (NOT UTC) → `journalctl --since "24 hours ago"` window straddles midnight UTC ambiguously | Per FINDING 2: every probe runs `date -u; date` side-by-side; cross-check timestamps at day-7 if any sync-OK line lands near midnight UTC |
| Databricks workspace SSH/access path not yet exercised by aim-N → day-7 probe falls back to operator | Plan emits operator prompt as fallback per FINDING 7; record the path used (direct vs. fallback) in EVIDENCE.md |
| Aliyun manual wiki commit cadence has not produced a fresh commit during aim-5 window → Databricks `git log -1 kb/wiki/` shows pre-aim-4 timestamp | This is the documented Q4c trade-off; aim-5-3 records the gap, classifies it as `aim-4-4 TODO item 3 still OPEN`, and PARTIAL closure is acceptable. Operator owns wiki cadence per Q4c. |
| 48h marker file logic from SYNC-04 ambiguous — what if marker exists but is from before aim-5 day-0? | Pre-aim-5-day-0 markers are out-of-scope; aim-5-3 only counts markers created during the 7-day window. Document the cutoff timestamp in EVIDENCE.md. |
| Failure on day N triggers RESTART → 6 days of work effectively forfeited | This is by design (REQ tolerance 0); document failure root cause; new 7-day window starts the day the fix lands |
| Forward-only append accidentally edits prior content of aim-4-4-EVIDENCE.md | Use `Edit` tool with explicit append-only behavior; verify `git diff aim-4-4-EVIDENCE.md` shows only added lines (no deletions) before commit |

## Evidence

- 7 per-day logs in `aim-5-EVIDENCE/daily-checks-day-N.log` (STAB-03
  sections)
- `aim-5-3-EVIDENCE.md` with 7-day Hermes table + Databricks day-7
  probe + aim-4-4 TODO 4-item closure score + aggregate verdict
- Forward-only append in `.planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md`
  recording closure
- Single forward-only commit hash on `main` containing all 3 of the above
