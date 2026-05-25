---
plan_id: aim-5-1
phase: aim-5
wave: 2
depends_on:
  - aim-5-6
requirements_addressed:
  - STAB-01
files_modified:
  - .planning/phases/aim-5-stability-watch/aim-5-1-EVIDENCE.md
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-1.log
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-2.log
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-3.log
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-4.log
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-5.log
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-6.log
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-7.log
autonomous: true
t_shirt: S
---

# aim-5-1 — STAB-01 daily systemd ingest timer watch (3 timers × 7 days)

## Goal

Daily read-only watch of the **3 Aliyun systemd ingest timers** that
replaced the 11 retired Hermes crons (per CUTOVER-01 from aim-3):
`omnigraph-daily-ingest.timer` (09:00 ADT), `omnigraph-afternoon-ingest.timer`
(14:00 ADT), `omnigraph-evening-ingest.timer` (21:00 ADT). Pass criterion
is **7 consecutive days with zero unit-level failures**, verified per
REQ STAB-01.

REQ STAB-01 verbatim
(`.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` line 80):

> **STAB-01**: Aliyun systemd ingest timers (the 3 ingest-loop
> equivalents from CUTOVER-01: daily-ingest 09:00 / afternoon-ingest
> 14:00 / evening-ingest 21:00 ADT) fire 7 consecutive days with
> **zero** unit-level failures. Verified via `systemctl status
> omnigraph-*.timer` showing `Last triggered` advancing daily AND
> `journalctl -u omnigraph-*.service --since "7 days ago" | grep -E
> "Failed|exit-code"` returning empty. §7 SC #1.

Per `aim-5-CONTEXT.md` FINDING 6, this filter is **specifically the
3 ingest-loop services**, NOT the `omnigraph-*.service` wildcard. The
other 8 supporting jobs (kol_scan health, rss-fetch, daily-digest,
vertex-probe-monthly, etc.) are tracked under CUTOVER-04 journald
sampling, not STAB-01 zero-fail discipline.

Per FINDING 9 + memory `feedback_aim1_agent_is_operator.md`, ALL probes
are read-only diagnostics — labeled `[agent-runnable]`. The agent
SSHes Aliyun via the `aliyun-vitaclaw` alias and writes outputs into
`aim-5-EVIDENCE/daily-checks-day-N.log` files (one per day).

## Acceptance criteria

1. For each day N in 1..7, a daily probe runs against Aliyun and
   captures stdout into
   `.planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-N.log`
   (STAB-01 section, prepended with `=== STAB-01 day N ===`).
2. Per-day pass criterion (must hold every day):
   - For each of the 3 timers, `systemctl status <unit>.timer`
     `Last triggered` value advances vs. yesterday (i.e., is within
     the last 24h, not stale).
   - `journalctl -u <unit>.service --since "24 hours ago"` shows the
     unit started + exited 0 (look for `Started <unit>.service` and
     no `Failed` / `exit-code` substrings).
3. 7-day rollup pass criterion (verdict):
   - `journalctl -u "omnigraph-(daily|afternoon|evening)-ingest.service"
     --since "7 days ago" | grep -E "Failed|exit-code" | wc -l`
     returns `0` (verbatim per REQ wording, narrowed to the 3 services).
4. **Failure-day tolerance: 0** (per `aim-5-CONTEXT.md` FINDING 1).
   ANY single failed timer fire on ANY of the 3 timers on ANY day
   restarts the 7-day window. Honestly log the failure in the day's
   log file + OBSERVATION.md Day N entry; operator decides RESTART
   timing.
5. `aim-5-1-EVIDENCE.md` exists at day-7 with:
   - 7 daily verdicts (Day 1..7 PASS / FAIL)
   - 7-day rollup grep result + count
   - Aggregate STAB-01 verdict: PASS / RESTART
   - Pointer to per-day logs in `aim-5-EVIDENCE/`
6. Each day's log includes `date -u; date` outputs side-by-side (per
   FINDING 2 — TZ disambiguation between Aliyun host TZ and UTC).
7. Forward-only commits per CLAUDE.md 2026-05-15 #1 lesson + memory
   `feedback_git_add_explicit_in_parallel_quicks.md`. Each daily
   probe MAY commit individually; aim-5-1-EVIDENCE.md is committed
   at day-7.
8. The 7-day rollup grep filter narrows to exactly the 3 unit names —
   it does NOT use the `omnigraph-*.service` wildcard (per FINDING 6).

## Tasks

### Task 1 — Daily probe (run once per day, day 1..7) `[agent-runnable]`

**`<read_first>`**
- `aim-5-CONTEXT.md` lines 268-283 (STAB-01 daily probe pattern)
- `aim-5-CONTEXT.md` FINDING 6 (3-timer narrow, NOT wildcard)
- `aim-5-CONTEXT.md` FINDING 9 (read-only / agent-runnable boundary)
- Memory `aliyun_vitaclaw_ssh.md` (Aliyun SSH alias)

**`<acceptance_criteria>`**
- Daily log file
  `aim-5-EVIDENCE/daily-checks-day-N.log` exists and contains:
  - `date -u` and `date` outputs (UTC + Aliyun host TZ)
  - For each of the 3 timers: `systemctl status` head + 24h journal
    grep for Failed/exit-code/Started/Stopped
  - The 7-day rollup grep run on day 7 only (or daily — running daily
    is acceptable for redundant defense, just cite explicitly)
- Per-day verdict line `STAB-01 day N: PASS / FAIL` recorded.

**`<action>`**

Run via the Bash tool — one invocation per day (day 1..7):

```bash
DAY=N   # 1..7
LOG=.planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-${DAY}.log
mkdir -p "$(dirname "$LOG")"

{
  echo "=== STAB-01 day $DAY ==="
  ssh aliyun-vitaclaw '
    date -u; date
    for unit in omnigraph-daily-ingest omnigraph-afternoon-ingest omnigraph-evening-ingest; do
      echo "--- $unit ---"
      systemctl status ${unit}.timer --no-pager | head -10
      echo "--- 24h journal for ${unit}.service ---"
      journalctl -u ${unit}.service --since "24 hours ago" --no-pager | \
        grep -E "Failed|exit-code|Started|Stopped" || echo "(empty)"
    done
    echo "--- 7d failure grep across the 3 ingest-loop services ---"
    journalctl -u omnigraph-daily-ingest.service \
               -u omnigraph-afternoon-ingest.service \
               -u omnigraph-evening-ingest.service \
               --since "7 days ago" --no-pager | \
      grep -cE "Failed|exit-code" || echo 0
  '
} >> "$LOG" 2>&1

# Compute per-day verdict — manually inspect log for "Failed" / "exit-code"
# substrings AND confirm "Last triggered" advances for each of the 3 timers.
```

**Per-day acceptance probe (executor checks log content):**

```bash
# Pass conditions ALL must hold:
# 1. Each timer's "Last triggered" line shows a timestamp within the last 24h
# 2. No "Failed" or "exit-code" substring in the 24h journal for any unit
# 3. "(empty)" or only "Started" / "Stopped" lines appear in journal sections
grep -E "Failed|exit-code" "$LOG" | grep -v "grep -E" | grep -v "^---" || echo "PASS day $DAY"
```

If any line containing `Failed` / `exit-code` appears (other than the
literal grep command echoed back): mark Day N FAIL and surface to
OBSERVATION.md.

### Task 2 — Day-7 rollup verdict + aim-5-1-EVIDENCE.md `[agent-runnable]`

**`<read_first>`**
- All 7 daily logs in `aim-5-EVIDENCE/daily-checks-day-N.log`
- `aim-5-CONTEXT.md` FINDING 1 (failure-day tolerance = 0)

**`<acceptance_criteria>`**
- `aim-5-1-EVIDENCE.md` exists with:
  - 7 daily verdicts table (Day N | timestamp | result)
  - 7-day rollup grep count line (`= 0` for PASS)
  - Aggregate STAB-01 verdict (PASS / RESTART)
- Single forward-only commit on `main` containing the evidence file +
  any uncommitted daily logs.
- Conventional commit message: `docs(aim-5): STAB-01 7-day verdict (aim-5-1)`.
- `git status` clean post-commit.

**`<action>`**

Author `aim-5-1-EVIDENCE.md`:

```markdown
# aim-5-1 — STAB-01 7-day systemd ingest timer watch evidence

**Timestamp:** <day-7 ts>
**Plan:** aim-5-1
**REQs:** STAB-01
**Status:** PASS / RESTART

## Per-day verdicts

| Day | Date (ADT) | daily-ingest 09:00 | afternoon-ingest 14:00 | evening-ingest 21:00 | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1   | <ts> | ✅ | ✅ | ✅ | PASS |
| 2   | <ts> | ✅ | ✅ | ✅ | PASS |
| 3   | <ts> | ✅ | ✅ | ✅ | PASS |
| 4   | <ts> | ✅ | ✅ | ✅ | PASS |
| 5   | <ts> | ✅ | ✅ | ✅ | PASS |
| 6   | <ts> | ✅ | ✅ | ✅ | PASS |
| 7   | <ts> | ✅ | ✅ | ✅ | PASS |

## 7-day rollup

```
journalctl -u omnigraph-daily-ingest.service \
           -u omnigraph-afternoon-ingest.service \
           -u omnigraph-evening-ingest.service \
           --since "7 days ago" | grep -cE "Failed|exit-code"
→ 0
```

## Aggregate verdict

**STAB-01:** PASS (failure-day tolerance 0 honored across 7 days × 3 timers = 21 fires)

## Per-day log files

- `.planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-1.log`
- ... through day-7

## References

- REQUIREMENTS STAB-01 (line 80)
- aim-5 CONTEXT FINDING 1 (tolerance) + FINDING 6 (3-timer scope)
```

Commit:

```bash
git add .planning/phases/aim-5-stability-watch/aim-5-1-EVIDENCE.md \
        .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-*.log
git status   # confirm only intended files staged
git commit -m "docs(aim-5): STAB-01 7-day verdict (aim-5-1)"
git log -1 --name-only
```

## Risk and mitigation

| Risk | Mitigation |
| ---- | ---------- |
| TZ ambiguity in journal grep window — `--since "24 hours ago"` runs in Aliyun host TZ, not UTC | Each daily probe records `date -u; date` side-by-side; cross-check at day-7 if `Last triggered` straddles midnight UTC |
| `omnigraph-*.service` wildcard would over-grep (catches kol_scan, rss-fetch, etc.) → false-positive failure | Filter is narrowed to the 3 ingest-loop unit names only (per FINDING 6) |
| Single daily probe fails to SSH Aliyun (transient network) → log incomplete | Re-run probe later same day; cite original failure timestamp in log; per-day verdict requires all 3 timers reported |
| Operator skips a day → 6 valid days + 1 missing day = ambiguous | Honest log "(probe missed; resync next day)"; aim-5-6 day-7 verdict treats missing day as INDETERMINATE; aim-5 close gate may RESTART or extend window per operator |
| Failure on day N triggers RESTART → 6 days of work effectively forfeited | This is by design (REQ tolerance 0). Document the failure root cause to ensure aim-N regression doesn't repeat; the new 7-day window starts the day the fix lands. |
| Forward-only commit discipline broken | Per CLAUDE.md 2026-05-15 #1: NEVER `git commit --amend`; use forward-only correction commits |

## Evidence

- 7 per-day logs in `aim-5-EVIDENCE/daily-checks-day-N.log` (STAB-01
  section)
- `aim-5-1-EVIDENCE.md` with 7-day rollup verdict + aggregate PASS/RESTART
- Single forward-only commit hash on `main` with the evidence file +
  daily logs
