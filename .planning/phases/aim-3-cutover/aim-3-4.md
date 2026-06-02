---
plan_id: aim-3-4
phase: aim-3
wave: 4
depends_on:
  - aim-3-3
requirements_addressed:
  - CUTOVER-04
  - CUTOVER-02
files_modified:
  - .planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-04-journald-evidence.md
autonomous: true
t_shirt: M
---

# aim-3-4 — Journald verification + 24h DB-write verification (CUTOVER-04 + CUTOVER-02 part 2)

## Goal

After Aliyun's systemd timers have had ≥ 1 natural fire each (per their UTC OnCalendar schedules from aim-3-2), sample 3 of 13 units and prove their journald log is non-empty. Also verify CUTOVER-02's 24h-window invariant: Aliyun-side `data/kol_scan.db`'s `MAX(layer2_at)` (or equivalent latest-write column) advances past the cutover-window-start timestamp recorded in aim-3-3.

This plan's wallclock window is naturally ≥ 24h after aim-3-3 closes (you must wait for ≥ 1 fire of each sampled timer + at least one full daily cycle to confirm DB writes). The agent does NOT keep an SSH session open for 24h — this plan is structured as: define what to capture → ask user to come back when the wallclock window passes → run the captures.

This plan closes the aim-3 phase. After aim-3-4 verdict PASS, the milestone advances to aim-4 (daily sync setup).

**Pre-condition:** aim-3-3 EVIDENCE shows verdict PASS (kol_scan.db synced, Hermes disabled, missed-window recorded). aim-3-2 EVIDENCE shows all 13 timers enabled+active.

## Acceptance criteria

1. ≥ 24h wallclock has elapsed since `cutover_window_start` (recorded in aim-3-3 CUTOVER-EVIDENCE.md). Verification: agent confirms timestamp before running captures.
2. For 3 sampled units (`omnigraph-daily-ingest.service`, `omnigraph-rss-fetch.service`, `omnigraph-reconcile.service`):
   - `journalctl -u <unit> --since "1 hour ago"` OR `--since "1 day ago"` returns non-empty stdout for the relevant lookback window.
   - At least one entry shows the unit invoked and ran to completion (`Started ... .service` + `Deactivated successfully` OR `Main process exited`).
3. For all 13 timers: `systemctl list-timers --all omnigraph-*` shows `LAST` column populated with a wallclock ≥ `cutover_window_start` (proves at least one natural fire happened post-cutover).
4. Aliyun-side `sqlite3 data/kol_scan.db "SELECT MAX(layer2_at) FROM articles"` returns a value > the Hermes-side `MAX(layer2_at)` recorded at aim-3-3 Task 1 (proves Aliyun has written new rows since cutover — CUTOVER-02 24h verify).
5. EVIDENCE file `.planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-04-journald-evidence.md` exists, committed locally, contains: 3 sampled `journalctl` outputs, the `list-timers --all` LAST column, the post-cutover MAX(layer2_at) comparison, the kol-enrich stub journald check (should show `/bin/true` exit 0 entries — confirming the stub still fires its timer cleanly), final aim-3 PASS/FAIL verdict.
6. (Optional but recommended) Aim-3 closure note appended to `.planning/STATE-Aliyun-Ingest-Migration-v1.md` advancing milestone state from "aim-3 in flight" to "aim-3 DONE; next aim-4". Forward-only edit (no rewrite).

## Task list

### Task 1 — Confirm wallclock window has passed

**`<read_first>`**

- `.planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-EVIDENCE.md` (aim-3-3 output) — section "Cutover window + missed-window estimate" — `cutover_window_start` ISO

**`<acceptance_criteria>`**

- Current UTC wallclock ≥ `cutover_window_start` + 24h.
- For each of the 3 sampled timers, ≥ 1 OnCalendar fire has occurred since `cutover_window_start`. Compute by hand from the UTC schedule:
  - `omnigraph-rss-fetch.timer` fires daily at `09:00 UTC` — at least 1 fire ≥ 24h after start
  - `omnigraph-daily-ingest.timer` fires daily at `12:00 UTC` — at least 1 fire ≥ 24h after start
  - `omnigraph-reconcile.timer` fires daily at `12:30 UTC` — at least 1 fire ≥ 24h after start

**`<action>`**

```bash
# Read cutover_window_start from the aim-3-3 evidence file
grep "cutover_window_start" .planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-EVIDENCE.md

# Compute current UTC and verify 24h+ has elapsed
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

If less than 24h has elapsed, STOP this plan. Tell the user the wallclock target ISO at which to resume. Do NOT run Task 2 prematurely — partial fires would produce inconsistent evidence.

If ≥ 24h has elapsed, proceed to Task 2.

### Task 2 — Capture journald for 3 sampled units

**`<read_first>`**

- aim-3-2 evidence file `EVIDENCE/CUTOVER-01-deploy-evidence.md` (the unit names + UTC schedules)
- Memory `aliyun_vitaclaw_ssh.md` (SSH alias)

**`<acceptance_criteria>`**

- 3 journalctl outputs captured (daily-ingest, rss-fetch, reconcile).
- Each output non-empty.
- Each output contains a `Started ... .service` entry AND a completion entry (either `Deactivated successfully` for `Type=simple` or `Main process exited`).

**`<action>`**

```bash
ssh aliyun-vitaclaw bash -c "'
set -e

echo \"=== current Aliyun UTC ===\"
date -u +\"%Y-%m-%dT%H:%M:%SZ\"
timedatectl | grep -E \"Time zone|Local time|Universal time\"

echo \"\"
echo \"=== systemctl list-timers --all omnigraph-* ===\"
systemctl list-timers --all \"omnigraph-*\"

echo \"\"
echo \"=== journalctl -u omnigraph-daily-ingest.service --since \\\"24 hours ago\\\" ===\"
journalctl -u omnigraph-daily-ingest.service --since \"24 hours ago\" --no-pager | head -100

echo \"\"
echo \"=== journalctl -u omnigraph-rss-fetch.service --since \\\"24 hours ago\\\" ===\"
journalctl -u omnigraph-rss-fetch.service --since \"24 hours ago\" --no-pager | head -100

echo \"\"
echo \"=== journalctl -u omnigraph-reconcile.service --since \\\"24 hours ago\\\" ===\"
journalctl -u omnigraph-reconcile.service --since \"24 hours ago\" --no-pager | head -100

echo \"\"
echo \"=== journalctl -u omnigraph-kol-enrich.service --since \\\"24 hours ago\\\" (STUB confirmation) ===\"
journalctl -u omnigraph-kol-enrich.service --since \"24 hours ago\" --no-pager | head -50
'"
```

Capture full output to `.scratch/aim-3-4-journald-<TS>.log`.

If any of the 3 sampled units returns an empty journalctl, do NOT abort yet — investigate first:

- Check `systemctl status omnigraph-<unit>.timer` — is the timer still active?
- Check `systemctl list-timers omnigraph-<unit>.timer` — is `LAST` column populated?
- If `LAST` is empty, the timer never fired (could be a clock issue OR the unit was disabled by something).
- If `LAST` is populated but journalctl is empty, the service may have failed silently — check `journalctl -u <unit>.service --no-pager` without time filter.

Document any anomaly in the evidence file.

### Task 3 — Capture Aliyun DB write progression (CUTOVER-02 24h verify)

**`<read_first>`**

- aim-3-3 evidence file `EVIDENCE/CUTOVER-EVIDENCE.md` — section 1 — Hermes-side `MAX(layer2_at)` value at cutover
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` line 62 (CUTOVER-02 verify wording: "24h after cutover, Aliyun-side DB has new rows ... advances past the cutover timestamp")

**`<acceptance_criteria>`**

- Aliyun `MAX(layer2_at)` > Hermes-side baseline `MAX(layer2_at)` from aim-3-3 Task 1.
- Aliyun row counts (articles, rss_articles) ≥ Hermes-side baseline + at least 1 (proves Aliyun wrote at least one new row in the 24h window — the threshold is intentionally weak: even 1 row advance is sufficient because that proves write authority transferred).
- Optional richer signal: per-day row count for the 24h window post-cutover ≥ 1.

**`<action>`**

```bash
ssh aliyun-vitaclaw bash -c "'
set -e
cd /root/OmniGraph-Vault

echo \"=== Aliyun row counts post-cutover ===\"
sqlite3 data/kol_scan.db \"SELECT COUNT(*) AS articles FROM articles;\"
sqlite3 data/kol_scan.db \"SELECT MAX(layer2_at) AS max_layer2_at FROM articles;\"
sqlite3 data/kol_scan.db \"SELECT MAX(scanned_at) AS max_scanned_at FROM articles;\"
sqlite3 data/kol_scan.db \"SELECT COUNT(*) AS rss_articles FROM rss_articles;\"

echo \"\"
echo \"=== rows added in past 24h (Aliyun cutover signal) ===\"
sqlite3 data/kol_scan.db \"
  SELECT COUNT(*) AS articles_24h
  FROM articles
  WHERE scanned_at >= datetime(\\\"now\\\", \\\"-24 hours\\\");
\"
sqlite3 data/kol_scan.db \"
  SELECT COUNT(*) AS layer2_24h
  FROM articles
  WHERE layer2_at >= datetime(\\\"now\\\", \\\"-24 hours\\\");
\"
'"
```

Capture output to `.scratch/aim-3-4-db-verify-<TS>.log`.

Compare to aim-3-3 Task 1 output verbatim. The Aliyun `MAX(layer2_at)` MUST be > Hermes-side baseline. If not, EITHER no Aliyun timer fired (Task 2 will have shown this) OR the timers fired but the script failed every time (Task 2 journalctl will show the failures).

### Task 4 — Write CUTOVER-04-journald-evidence.md and aim-3 closure

**`<read_first>`**

- All `.scratch/aim-3-4-*.log` outputs
- aim-3-3 evidence (for cutover_window_start cross-reference)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\STATE-Aliyun-Ingest-Migration-v1.md` (for the closure-note append)

**`<acceptance_criteria>`**

- File `.planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-04-journald-evidence.md` exists.
- Sections: "Wallclock window check", "list-timers LAST column" (all 13 rows), "Sampled journalctl outputs" (3 units verbatim + kol-enrich stub), "Aliyun DB write progression" (Hermes baseline vs. Aliyun current), "CUTOVER-04 verdict" (PASS / PARTIAL / FAIL), "aim-3 phase verdict" (PASS / FAIL aggregating CUTOVER-01..05).
- (Optional) STATE-Aliyun-Ingest-Migration-v1.md has a forward-only appended line under "Pending Todos" or "Phase plan" reflecting aim-3 closure.
- Single forward-only commit on `main`.

**`<action>`**

Use the Write tool to create `EVIDENCE/CUTOVER-04-journald-evidence.md`. Skeleton:

```markdown
# CUTOVER-04 — Journald + 24h DB-write evidence

Phase: aim-3 (cutover)
REQs covered: CUTOVER-04 (journald per-unit) + CUTOVER-02 part 2 (24h DB write verify)

---

## 1. Wallclock window check

- aim-3-3 `cutover_window_start`: [paste from CUTOVER-EVIDENCE.md]
- Current UTC at this verification: [paste]
- Elapsed: [N.N hours] (required ≥ 24h)
- [PASS / FAIL]

## 2. systemctl list-timers --all omnigraph-* (LAST column populated check)

```

[paste full table from Task 2]

```

13-row LAST column summary: [N of 13 timers have LAST > cutover_window_start]
- (Required: 13 of 13. The kol-enrich stub MUST also show a LAST entry — its `/bin/true` exits 0 immediately, so the timer fires and journald records the entry.)

## 3. Sampled journalctl outputs

### omnigraph-daily-ingest.service (24h lookback)

```

[paste verbatim Task 2 output for daily-ingest]

```

Entries observed:
- Number of `Started omnigraph-daily-ingest.service` lines: [N]
- Number of completion lines (`Deactivated successfully` or equivalent): [N]
- Any failure lines (`exit-code` / `Failed`): [paste any, or "none"]

### omnigraph-rss-fetch.service (24h lookback)

```

[paste verbatim]

```

Entries observed:
- Number of started/completed pairs: [N]
- Any failures: [paste / none]

### omnigraph-reconcile.service (24h lookback)

```

[paste verbatim]

```

Entries observed:
- Number of started/completed pairs: [N]
- Any failures: [paste / none]

### omnigraph-kol-enrich.service (24h lookback — STUB confirmation)

```

[paste verbatim]

```

Stub confirmation:
- Started/completed pairs: [N — should be 1 per UTC 11:30 fire]
- Each completion should be near-instant (`/bin/true` exits 0) — duration entry: [paste]

## 4. Aliyun DB write progression (CUTOVER-02 24h verify)

- Hermes-side baseline `MAX(layer2_at)` (from aim-3-3 Task 1): [paste]
- Aliyun-side `MAX(layer2_at)` now: [paste]
- Strictly greater: [PASS / FAIL]

- Aliyun-side rows added in past 24h: `articles` = [N], `layer2_24h` = [N]
- (Required: ≥ 1 row written by Aliyun in the post-cutover window)

## 5. Verdicts

### CUTOVER-04 (per-unit journald)

- 3 sampled units have non-empty journalctl with started+completed entries: [PASS / FAIL]
- All 13 timers have LAST > cutover_window_start: [PASS / FAIL]
- kol-enrich stub fires cleanly (exit 0 from /bin/true): [PASS / FAIL]

### CUTOVER-02 part 2 (24h DB write)

- Aliyun MAX(layer2_at) > Hermes baseline MAX(layer2_at): [PASS / FAIL]
- ≥ 1 article written by Aliyun post-cutover: [PASS / FAIL]

### aim-3 phase aggregate verdict

| REQ | Evidence file | Verdict |
| --- | --- | --- |
| CUTOVER-01 | aim-3-2 EVIDENCE/CUTOVER-01-deploy-evidence.md | [paste] |
| CUTOVER-02 | aim-3-3 CUTOVER-EVIDENCE.md (part 1) + this file (part 2) | [paste] |
| CUTOVER-03 | aim-3-3 CUTOVER-EVIDENCE.md (Hermes jobs.json + crontab) | [paste] |
| CUTOVER-04 | this file | [paste] |
| CUTOVER-05 | aim-3-3 CUTOVER-EVIDENCE.md (cutover window + missed-window) | recorded |

aim-3 phase: [PASS / FAIL]

If PASS, milestone advances: aim-3 DONE → aim-4 next (daily sync Aliyun → Hermes + Databricks).

## 6. Anomalies (if any)

[paste anything unexpected — e.g., a unit that timed out, a journalctl entry showing an unexpected error, a partial DB write that suggests cron resumed somewhere]

If anomalies present, decide per-anomaly: forward-fix in a quick OR document as v1 follow-up for aim-5 stability watch.
```

Then commit:

```bash
git add .planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-04-journald-evidence.md
git status   # confirm only this file staged
git commit -m "docs(aim-3): record CUTOVER-04 journald + 24h DB-write verification (aim-3 closure)"
git log -1 --name-only
```

### Task 5 (optional) — Append aim-3 closure note to STATE-Aliyun-Ingest-Migration-v1.md

**`<read_first>`**

- Current `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\STATE-Aliyun-Ingest-Migration-v1.md` (top-of-file YAML + "Phase plan" table + "Pending Todos" if exists)

**`<acceptance_criteria>`**

- Forward-only edit: ONE line added (or one row's "Status" column updated from "blocked by aim-2" → "✅ DONE — commit [HASH] / [DATE]"). No other lines touched.
- Commit: separate from the evidence-file commit above (forward-only, single-purpose commits per `feedback_git_add_explicit_in_parallel_quicks.md`).

**`<action>`**

Use the Edit tool with surgical replacement. Target lines (per current STATE.md inspection — lines may shift; locate the row by content): the row in the "Phase plan" table reading `| aim-3 | Cutover ... | M | blocked by aim-2 |` → replace with `| aim-3 | Cutover ... | M | ✅ DONE — commit [aim-3-4 hash] / [today-iso-date] |`.

Then commit:

```bash
git add .planning/STATE-Aliyun-Ingest-Migration-v1.md
git status   # confirm only this file staged
git commit -m "docs(aim-3): mark phase aim-3 DONE in STATE (cutover complete)"
```

This task is OPTIONAL — agent runs it only if aim-3 phase verdict at Task 4 = PASS. If any verdict component is FAIL, skip Task 5 and let the user decide on rollback / forward-fix.

## Abort/rollback protocol

| Condition | Action |
| --- | --- |
| Less than 24h has elapsed since cutover_window_start | STOP. Tell user the resume-ISO. Do NOT run Task 2 prematurely. |
| Any 1 of 3 sampled timers has empty journalctl AND empty `LAST` column | The timer never fired. Investigate via `systemctl status omnigraph-<unit>.timer` and `systemctl status omnigraph-<unit>.service`. Likely causes: clock not UTC (run `timedatectl` to verify), unit disabled by something, dependency failure. Forward-fix via quick; do NOT skip evidence. |
| `LAST` column populated but journalctl shows only failures | The service is running but every run errors. Capture stderr in evidence; investigate via separate quick (likely a missing dependency or env var). Per CUTOVER-04 wording, "non-empty stdout" is satisfied even by failure entries — but verdict should be FAIL because the unit is broken. |
| Aliyun MAX(layer2_at) ≤ Hermes baseline | Aliyun has not written any new layer2 rows in 24h. EITHER no kol-classify ran successfully (check Task 2 journalctl for that unit) OR all classify runs returned 0 candidates. Investigate before concluding FAIL — the candidate pool may genuinely be empty for one day. |
| Anomaly that needs immediate rollback | Operator-side: re-enable the matching Hermes job in jobs.json (CUTOVER-03 abort path). Aliyun-side: `systemctl disable --now omnigraph-<unit>.timer`. Forward-only commit recording the rollback. Do NOT amend any prior aim-3 commit. |

## Evidence to capture

- `EVIDENCE/CUTOVER-04-journald-evidence.md` — committed locally
- (Optional) STATE-Aliyun-Ingest-Migration-v1.md forward-only update — committed separately
- `.scratch/aim-3-4-*.log` — uncommitted, agent-side reference

That closes the aim-3 phase. Next milestone gate: aim-4 (daily sync setup).
