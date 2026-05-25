---
plan_id: aim-5-6
phase: aim-5
wave: 1
depends_on: []
requirements_addressed: []
files_modified:
  - .planning/phases/aim-5-stability-watch/OBSERVATION.md
  - .planning/phases/aim-5-stability-watch/aim-5-6-EVIDENCE.md
  - .planning/phases/aim-5-stability-watch/aim-5-VERIFICATION.md
autonomous: true
t_shirt: S
---

# aim-5-6 — OBSERVATION.md scaffold + day-7 close verdict (cross-cutting closure)

## Goal

Author the central `OBSERVATION.md` scaffold at aim-5 day-0 and execute
the day-7 close verdict procedure. This plan owns the *artifact* into
which aim-5-1..5 write their daily probe outputs; without 7 populated
daily entries + a final verdict, aim-5 does not close.

Per `aim-5-CONTEXT.md` FINDING 10, OBSERVATION.md is the central closure
artifact. Per ROADMAP §aim-5 Notes, "phase plan is a checklist + an
OBSERVATION.md scaffold that operator updates daily."

This plan also surfaces the **Hermes lightrag_storage cold-backup
retention deadline (2026-06-22)** (per
`.planning/STATE-Aliyun-Ingest-Migration-v1.md:144`) at day-7 close.
Cleanup is OUT of aim-5 scope; the surface is calendar-only.

REQ coverage: cross-cutting — closes aim-5 milestone gate. No individual
STAB-NN ID is owned here, but all five are aggregated into the day-7
verdict.

## Acceptance criteria

1. `.planning/phases/aim-5-stability-watch/OBSERVATION.md` exists at
   day-0 with the schema specified verbatim in `aim-5-CONTEXT.md`
   FINDING 10 (sections: Baseline, Day 1..7, Day-7 verdict).
2. Baseline section is populated at day-0 with:
   - Aliyun kb-api article count (sourced from aim-5-4 day-0 baseline)
   - Hermes pre-migration Vertex monthly spend (sourced from aim-5-5
     day-0 baseline)
   - 3 known kb-api article hashes for STAB-04 probe (from aim-5-4)
   - 1 known FTS query for STAB-04 probe (from aim-5-4)
   - aim-4-4-EVIDENCE 4-item TODO carry-over reproduced verbatim
     (per FINDING 8 — items quoted from
     `.planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md` lines 53-65)
3. Day 1..7 entries are appended daily by the operator/agent compiling
   outputs from aim-5-1, aim-5-2, aim-5-3, aim-5-5 daily logs. Schema
   per FINDING 10 is followed for every day (5 STAB sections per day).
4. Day-7 verdict section computes:
   - STAB-01: PASS / RESTART (aggregates aim-5-1 daily verdicts; any
     single failure-day → RESTART, tolerance 0)
   - STAB-02: PASS / OPERATOR-REVIEW (aggregates aim-5-2 daily ghost
     rates; any day ≥ 1% AND migration-related → RESTART; otherwise
     log + continue per FINDING 3)
   - STAB-03: PASS / RESTART (aggregates aim-5-3 daily verdicts;
     tolerance 0; AND day-7 Databricks `git log -1 kb/wiki/` ≥ aim-4
     deploy timestamp)
   - STAB-04: PASS / FAIL (one-shot from aim-5-4 day-7 verdict — all 3
     hash probes 200, FTS ≥ 1 hit, monotonic article count, AND
     `/api/synthesize` returns ≠ 200)
   - STAB-05: PASS / OPERATOR-REVIEW (one-shot from aim-5-5 day-7
     verdict — `7d_aliyun × 4.3 ≤ baseline_hermes_monthly`)
   - aim-4-4 TODO carry-over: 4/4 closed Y/N (sourced from aim-5-3)
   - Hermes lightrag_storage retention deadline (2026-06-22)
     surfaced to operator: Y (with one-line note per FINDING in
     `aim-5-CONTEXT.md` lines 396-402)
   - aim-5 milestone close: PASS / RESTART
5. `aim-5-VERIFICATION.md` is authored at day-7 with the 5 STAB
   verdicts + aim-4-4 TODO closure status + retention reminder + final
   PASS / RESTART verdict. This file is the milestone-close evidence
   per ROADMAP §aim-5.
6. `aim-5-6-EVIDENCE.md` records: day-0 scaffold creation timestamp +
   commit hash, day-7 close verdict timestamp + commit hash, link to
   OBSERVATION.md and aim-5-VERIFICATION.md.
7. Forward-only commits per CLAUDE.md Lesson 2026-05-15 #1 + memory
   `feedback_no_amend_in_concurrent_quicks.md`. Two natural commit
   boundaries: (a) day-0 scaffold + baseline, (b) day-7 verdict +
   VERIFICATION.md. Daily appends (day 1..6) MAY be committed
   individually or batched at operator's discretion.
8. Failure-day discipline: if any STAB REQ fails its tolerance rule
   mid-window, this plan does NOT prematurely close aim-5. Instead,
   the failure is logged in OBSERVATION.md and the operator decides
   whether to RESTART the 7-day window (per FINDING 1 asymmetry rules).

## Tasks

### Task 1 — Day-0 OBSERVATION.md scaffold instantiation `[agent-runnable]`

**`<read_first>`**
- `.planning/phases/aim-5-stability-watch/aim-5-CONTEXT.md` lines
  186-236 (FINDING 10 — OBSERVATION.md schema verbatim)
- `.planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md` lines 52-65
  (4-item TODO carry-over verbatim)
- `.planning/STATE-Aliyun-Ingest-Migration-v1.md` line 144
  (Hermes lightrag_storage retention deadline 2026-06-22)

**`<acceptance_criteria>`**
- `OBSERVATION.md` exists with all sections from FINDING 10 schema.
- Baseline section captures the 4-item TODO from aim-4-4-EVIDENCE
  verbatim.
- Day 1..7 sections are stubbed (empty placeholders) ready for daily
  appends.
- Hermes retention deadline note appears in the Day-7 verdict template.

**`<action>`**

Use the `Write` tool to author `OBSERVATION.md`:

```markdown
# Aliyun-Ingest-Migration-v1 / aim-5 / OBSERVATION

**Window start (day-0):** <YYYY-MM-DD ADT>
**Window end (day-7 verdict):** <YYYY-MM-DD ADT>
**Owner:** Aliyun-Ingest-Migration-v1 milestone close gate
**Reference:** `.planning/phases/aim-5-stability-watch/aim-5-CONTEXT.md`
FINDING 10 (schema source)

## Baseline (captured day-0)

- Aliyun kb-api article count: <N>          # from aim-5-4-EVIDENCE day-0 baseline
- Hermes pre-migration Vertex monthly spend: $<X>   # from aim-5-5-EVIDENCE day-0 baseline
- Known kb-api article hashes for STAB-04 probe: [<h1>, <h2>, <h3>]
- Known FTS query for STAB-04 probe: "<term>"

### aim-4-4-EVIDENCE TODO carry-over (4 items, verbatim)

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

## Day 1 (<YYYY-MM-DD ADT> / <YYYY-MM-DD UTC>)

### STAB-01 (systemd ingest timers)
- daily-ingest 09:00 ADT: ✅/❌ (Last triggered: ..., journal grep result: ...)
- afternoon-ingest 14:00 ADT: ✅/❌
- evening-ingest 21:00 ADT: ✅/❌

### STAB-02 (reconcile ghost_success)
- ghost_success_count: N
- total_ingestions: M
- rate: N/M = X.X%
- root-cause hypothesis (if any ghost): "..."
- migration-related? Y/N

### STAB-03 (Hermes daily-pull + Databricks git pull)
- Hermes journal: "sync OK on attempt N" present? ✅/❌
- Marker file age: <h
- Databricks git log probe (day-7 only): N/A on day 1

### STAB-04 (kb-api regression — day-7 only spot-check, day-0 baseline)
- N/A daily; record full results at day-0 baseline + day-7 verdict

### STAB-05 (Vertex quota)
- 1-day Aliyun spend: $<x>
- running 7-day total: $<X>
- screenshot: aim-5-EVIDENCE/vertex-quota-day-1.png

## Day 2..7

(same schema as Day 1 — repeat 6 times)

## Day-7 verdict

- STAB-01: PASS / RESTART (any single failure-day → RESTART)
- STAB-02: PASS / OPERATOR-REVIEW
- STAB-03: PASS / RESTART
- STAB-04: PASS / FAIL (curl probes match baseline + /api/synthesize → 404)
- STAB-05: PASS / OPERATOR-REVIEW (7d × 4.3 ≤ baseline check)
- aim-4-4 TODO carry-over: 4/4 closed? Y/N
- Hermes lightrag_storage retention reminder surfaced to operator
  (deadline 2026-06-22)? Y/N
- aim-5 milestone close: PASS / RESTART

### Hermes lightrag_storage retention reminder (calendar-only)

Per `.planning/STATE-Aliyun-Ingest-Migration-v1.md:144`, the Hermes-side
`~/.hermes/omonigraph-vault/lightrag_storage/` read-only retention
deadline is **2026-06-22** (~28 days post-aim-5 close). Operator to
schedule cleanup post-milestone. Cleanup is OUT of aim-5 scope.
```

After authoring, evidence-stage and commit:

```bash
git add .planning/phases/aim-5-stability-watch/OBSERVATION.md
git status   # confirm only OBSERVATION.md staged
git commit -m "docs(aim-5): OBSERVATION.md scaffold (aim-5-6 day-0)"
git log -1 --name-only
```

### Task 2 — Daily append discipline (day 1..6) `[agent-runnable]`

**`<read_first>`**
- `OBSERVATION.md` (the scaffold from Task 1)
- Daily logs from aim-5-1, aim-5-2, aim-5-3, aim-5-5 evidence files
  (`aim-5-EVIDENCE/daily-checks-day-N.log` per CONTEXT lines 380-384)

**`<acceptance_criteria>`**
- For each day N in 1..6, the operator/agent appends a Day N section
  to OBSERVATION.md compiled from aim-5-1/2/3/5 daily probe outputs.
- TZ disambiguation: each Day N header carries BOTH ADT and UTC
  timestamps (per FINDING 2: include `date -u; date` outputs from the
  daily probes).
- Optional commit boundary per day (`docs(aim-5): OBSERVATION day N
  entry`) OR batched at day-7 — operator's discretion.

**`<action>`**

This task runs daily across the 7-day window. Pseudo-loop (executor
runs once per day):

```bash
# 1. Pull stdout from sibling daily-check logs
cat .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-N.log

# 2. Edit OBSERVATION.md to fill in Day N section using sibling probe outputs.
#    Use the Edit tool to surgically replace the "## Day N" stub with the populated entry.

# 3. (Optional) Commit per-day:
git add .planning/phases/aim-5-stability-watch/OBSERVATION.md
git commit -m "docs(aim-5): OBSERVATION day-N entry"
```

If a day's probe shows STAB-01 / STAB-03 zero-tolerance failure, log it
honestly in OBSERVATION.md and STOP (do NOT skip the day or fudge the
data). Operator decides RESTART vs. continue per FINDING 1.

### Task 3 — Day-7 close verdict + aim-5-VERIFICATION.md `[agent-runnable]`

**`<read_first>`**
- All 7 daily entries in `OBSERVATION.md`
- `aim-5-1-EVIDENCE.md`, `aim-5-2-EVIDENCE.md`, `aim-5-3-EVIDENCE.md`,
  `aim-5-4-EVIDENCE.md`, `aim-5-5-EVIDENCE.md` (per-plan verdicts)
- FINDING 1 (failure-day tolerance asymmetry — apply to verdict
  computation)
- `.planning/STATE-Aliyun-Ingest-Migration-v1.md` line 144 (retention
  deadline reminder text)

**`<acceptance_criteria>`**
- OBSERVATION.md "Day-7 verdict" section is fully populated (no
  placeholders left).
- For each STAB-NN, the verdict is computed using the asymmetric
  tolerance rules from FINDING 1:

  | STAB | Tolerance | Day-7 input |
  | ---- | --------- | ----------- |
  | STAB-01 | 0 failure-days | aim-5-1 daily verdicts × 7 |
  | STAB-02 | < 1% rolling 7-day, migration-related → RESTART else continue | aim-5-2 daily ghost rates + classifications |
  | STAB-03 | 0 failure-days | aim-5-3 daily verdicts × 7 + day-7 Databricks `git log -1 kb/wiki/` |
  | STAB-04 | one regression = FAIL | aim-5-4 day-7 one-shot |
  | STAB-05 | `7d × 4.3 ≤ baseline`; > 20% over → operator review | aim-5-5 day-7 one-shot |

- aim-4-4 TODO carry-over: 4/4 box-state captured (sourced from
  aim-5-3-EVIDENCE day-7 closure)
- Hermes retention deadline reminder line included verbatim
- `aim-5-VERIFICATION.md` exists at
  `.planning/phases/aim-5-stability-watch/aim-5-VERIFICATION.md` with
  the same verdict + a one-line milestone-close PASS or RESTART
  recommendation.
- Single forward-only commit on `main` containing OBSERVATION.md
  (day-7 verdict appended) + aim-5-VERIFICATION.md + aim-5-6-EVIDENCE.md.
- Conventional commit message: `docs(aim-5): day-7 verdict + VERIFICATION (aim-5-6)`.
- `git status` clean post-commit.

**`<action>`**

Author `aim-5-VERIFICATION.md`:

```markdown
# aim-5 — VERIFICATION (milestone close gate)

**Timestamp:** <YYYY-MM-DD HH:MM ADT>
**Phase:** aim-5 (Aliyun-Ingest-Migration-v1 / 7-day stability watch)
**Window:** <day-0 YYYY-MM-DD> through <day-7 YYYY-MM-DD>

## Per-REQ verdict

- **STAB-01** (systemd ingest timers, 0 tolerance): PASS / RESTART
  - Source: `aim-5-1-EVIDENCE.md`
- **STAB-02** (reconcile ghost_success < 1%): PASS / OPERATOR-REVIEW
  - Source: `aim-5-2-EVIDENCE.md`
- **STAB-03** (Hermes daily-pull + Databricks git pull, 0 tolerance):
  PASS / RESTART
  - Source: `aim-5-3-EVIDENCE.md` (also closes aim-4-4 TODO carry-over)
- **STAB-04** (kb-api regression, continuous): PASS / FAIL
  - Source: `aim-5-4-EVIDENCE.md`
  - Decision 4 / Q5c probe: `/api/synthesize` returned <code> (expect ≠ 200)
- **STAB-05** (Vertex quota, threshold ±20%): PASS / OPERATOR-REVIEW
  - Source: `aim-5-5-EVIDENCE.md`

## aim-4-4 TODO carry-over

- [x]/[ ] Item 1 (deploy key on Aliyun)
- [x]/[ ] Item 2 (Path B patch round-trip)
- [x]/[ ] Item 3 (Databricks `git log -1 kb/wiki/` first wiki commit verified)
- [x]/[ ] Item 4 (aim-5 STAB checkpoint closure — this file)

## Hermes lightrag_storage cold-backup retention deadline reminder

Per `.planning/STATE-Aliyun-Ingest-Migration-v1.md:144`, deadline is
**2026-06-22**. Cleanup is OUT of aim-5 scope; this is a calendar-only
surface to operator. Operator to schedule cleanup post-milestone.

## aim-5 close verdict

**RESULT:** PASS / RESTART

(If RESTART: which REQ failed, what is the corrective action, when
does the new 7-day window start.)
```

Then author `aim-5-6-EVIDENCE.md`:

```markdown
# aim-5-6 — OBSERVATION + day-7 verdict evidence

**Timestamp:** <ts>
**Plan:** aim-5-6 (Wave 1 day-0 + Wave 3 day-7)
**Status:** PASS / PARTIAL (aim-5 close gate)

## Day-0 scaffold

- File: `.planning/phases/aim-5-stability-watch/OBSERVATION.md`
- Created: <ts>
- Commit: <hash>

## Daily appends (day 1..6)

- Day 1 commit: <hash> (or "batched at day-7")
- ...
- Day 6 commit: <hash>

## Day-7 verdict

- File: `.planning/phases/aim-5-stability-watch/aim-5-VERIFICATION.md`
- Created: <ts>
- Commit: <hash>
- aim-5 close verdict: PASS / RESTART

## References

- aim-5 CONTEXT FINDING 10 (OBSERVATION.md schema)
- ROADMAP §aim-5 (close gate definition)
- STATE:144 (retention deadline reminder)
```

Commit:

```bash
git add .planning/phases/aim-5-stability-watch/OBSERVATION.md \
        .planning/phases/aim-5-stability-watch/aim-5-VERIFICATION.md \
        .planning/phases/aim-5-stability-watch/aim-5-6-EVIDENCE.md
git status   # confirm only the 3 files staged
git commit -m "docs(aim-5): day-7 verdict + VERIFICATION (aim-5-6)"
git log -1 --name-only
```

## Risk and mitigation

| Risk | Mitigation |
| ---- | ---------- |
| Sibling plans (aim-5-1..5) ship daily logs in inconsistent shape, hard to compile into Day N entry | OBSERVATION.md schema is fixed (per FINDING 10); sibling plan acceptance criteria reference the same schema → compile errors surface daily, not at day-7 |
| TZ confusion between ADT and UTC entries | Each daily probe runs `date -u; date` (per FINDING 2); Day N header includes both clocks side-by-side; ambiguity surfaces at compile-time, not retrospectively |
| Operator forgets retention deadline reminder at day-7 | Reminder is hard-coded into OBSERVATION.md scaffold + aim-5-VERIFICATION.md template; cannot be omitted without active deletion |
| Failure mid-window (e.g., day-3 STAB-01 fails) → unclear whether to RESTART now or continue logging | Per FINDING 1 (asymmetric tolerance), continue logging through day-7; verdict computation defers RESTART decision to day-7 close. Honest logging > premature close. |
| Day-7 Databricks `git log -1 kb/wiki/` requires Databricks-side access — not always agent-runnable | aim-5-3 owns this probe; aim-5-6 only consumes its verdict. If aim-5-3 cannot reach Databricks, aim-5-3 emits operator-only prompt; aim-5-6 day-7 verdict carries forward whatever aim-5-3 produced. |
| Forward-only commit discipline broken by `git commit --amend` | Per memory `feedback_no_amend_in_concurrent_quicks.md` and CLAUDE.md 2026-05-15 #1 lesson: NEVER amend; use forward-only correction commits |

## Evidence

- `.planning/phases/aim-5-stability-watch/OBSERVATION.md` (canonical
  daily log + day-7 verdict)
- `.planning/phases/aim-5-stability-watch/aim-5-VERIFICATION.md`
  (milestone-close gate evidence)
- `.planning/phases/aim-5-stability-watch/aim-5-6-EVIDENCE.md`
  (per-plan trail of commits + timestamps)
