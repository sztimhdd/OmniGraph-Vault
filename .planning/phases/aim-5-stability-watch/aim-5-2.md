---
plan_id: aim-5-2
phase: aim-5
wave: 2
depends_on:
  - aim-5-6
requirements_addressed:
  - STAB-02
files_modified:
  - .planning/phases/aim-5-stability-watch/aim-5-2-EVIDENCE.md
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

# aim-5-2 — STAB-02 daily reconcile ghost_success rate watch (7 days)

## Goal

Daily read-only watch of the **bidirectional reconcile job** (scope
extended in v1.0.y closure commit `587fa85`, per
`feedback_contract_shape_change_full_audit.md` lineage). Compute the
24h ghost_success rate (`ghost_count / total_ingestions`) on Aliyun for
7 consecutive days. Pass criterion is rolling 7-day rate **< 1%**, with
asymmetric handling: any single day ≥ 1% AND root cause is migration-
related → RESTART; any single day ≥ 1% but classified as v1.0.x noise
floor → log + continue.

REQ STAB-02 verbatim
(`.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` line 81):

> **STAB-02**: Reconcile job (the bidirectional ghost-success scope
> from `feedback_contract_shape_change_full_audit.md` lineage) runs
> daily for the same 7-day window. ghost_success rate
> (`ghost / total ingestions`) < 1% across the 7-day rolling window.
> §7 SC #4. Failure case: any single day with ghost_success ≥ 1%
> triggers operator review; if root cause is migration-related (vs.
> pre-existing v1.0.x noise floor), aim-5 restarts.

Per `aim-5-CONTEXT.md` FINDING 3 (migration-related vs. v1.0.x noise
floor distinction): historical v1.0 production day-1 noise floor was
1/188 = 0.5%. Decision rule for any ghost observation:

- if `migration_related` → RESTART
- else (classify as v1.0.x noise floor) → log + continue

Per FINDING 9, all probes are read-only diagnostics — labeled
`[agent-runnable]`. The agent SSHes Aliyun via `aliyun-vitaclaw` alias.

## Acceptance criteria

1. For each day N in 1..7, a daily probe runs against Aliyun and
   captures stdout into the same `daily-checks-day-N.log` file used by
   sibling plans (aim-5-1/3/5), prepended with `=== STAB-02 day N ===`.
2. Per-day probe captures:
   - `total_ingestions_24h` (count of `ingestions` rows with
     `ingested_at >= datetime("now", "-24 hours")` AND
     `status IN ("ok", "failed")`)
   - `ghost_success_count_24h` (the bidirectional reconcile output —
     count of rows where DB status disagrees with LightRAG kv_store
     state, in either direction per v1.0.y closure scope)
   - `rate = ghost / total`
   - If any ghost present: a brief root-cause hypothesis +
     classification (`migration_related` Y/N)
3. Per-day pass criterion: `rate < 0.01` (1%).
4. Threshold-bust handling (per FINDING 1 + FINDING 3):
   - rate ≥ 1% AND classified `migration_related=Y` → RESTART aim-5
   - rate ≥ 1% AND classified `migration_related=N` (v1.0.x noise
     floor) → OPERATOR-REVIEW (log + continue, do not auto-RESTART)
   - rate < 1% → PASS
5. 7-day rollup verdict (in `aim-5-2-EVIDENCE.md`):
   - 7-day total ghost / 7-day total ingestions = rolling rate
   - Aggregate STAB-02 verdict: PASS / OPERATOR-REVIEW / RESTART
6. **Reconcile script discovery**: per CONTEXT lines 290-309, the
   exact reconcile script path is "planner: confirm". Probe step 1
   greps `scripts/` for `reconcile|ghost`; if no script exists,
   probe falls back to inline SQL count from `kol_scan.db` ingestions
   table + a manual cross-check against LightRAG kv_store.
7. Each day's log includes `date -u; date` outputs (FINDING 2 — TZ
   disambiguation).
8. Forward-only commits per CLAUDE.md 2026-05-15 #1 + memory
   `feedback_git_add_explicit_in_parallel_quicks.md`. Daily probe
   commits MAY batch with sibling plans (same log file). EVIDENCE
   committed at day-7.

## Tasks

### Task 1 — Daily probe (run once per day, day 1..7) `[agent-runnable]`

**`<read_first>`**

- `aim-5-CONTEXT.md` lines 288-309 (STAB-02 daily probe pattern)
- `aim-5-CONTEXT.md` FINDING 3 (migration-related vs. v1.0.x noise
  floor classification rules)
- Memory `feedback_contract_shape_change_full_audit.md` (bidirectional
  reconcile scope lineage; v1.0.y commit `587fa85`)
- Memory `aliyun_vitaclaw_ssh.md`

**`<acceptance_criteria>`**

- Daily log file
  `aim-5-EVIDENCE/daily-checks-day-N.log` contains a `=== STAB-02 day N ===`
  section with: `total_24h`, `ghost_24h`, `rate`, classification (if
  any ghost), per-day verdict.

**`<action>`**

Run via the Bash tool — one invocation per day (day 1..7):

```bash
DAY=N   # 1..7
LOG=.planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-${DAY}.log
mkdir -p "$(dirname "$LOG")"

{
  echo "=== STAB-02 day $DAY ==="
  ssh aliyun-vitaclaw '
    date -u; date
    cd /root/OmniGraph-Vault
    source venv-aim1/bin/activate 2>/dev/null || source venv/bin/activate

    # Step 1: 24h ingestions count (eligible for ghost classification)
    python -c "
import sqlite3
conn = sqlite3.connect(\"data/kol_scan.db\")
c = conn.cursor()
c.execute(\"\"\"
  SELECT COUNT(*) FROM ingestions
  WHERE status IN (\"ok\", \"failed\")
    AND ingested_at >= datetime(\"now\", \"-24 hours\")
\"\"\")
print(f\"total_24h={c.fetchone()[0]}\")
"

    # Step 2: locate reconcile script (planner-deferred discovery)
    echo "--- reconcile script discovery ---"
    ls scripts/ | grep -E "reconcile|ghost" || echo "(no reconcile script — fallback to SQL inline)"

    # Step 3: if reconcile script exists, run it; else inline SQL
    if ls scripts/ | grep -qE "reconcile|ghost"; then
      RECONCILE_SCRIPT=$(ls scripts/ | grep -E "reconcile|ghost" | head -1)
      echo "--- running scripts/$RECONCILE_SCRIPT --24h ---"
      python scripts/$RECONCILE_SCRIPT --24h 2>&1 || echo "(reconcile error — capture for triage)"
    else
      echo "--- inline ghost-detection SQL fallback ---"
      python -c "
import sqlite3
import json
conn = sqlite3.connect(\"data/kol_scan.db\")
c = conn.cursor()
# status=ok ingestions in last 24h — sample for ghost cross-check
c.execute(\"\"\"
  SELECT article_id, ingested_at FROM ingestions
  WHERE status = \"ok\" AND ingested_at >= datetime(\"now\", \"-24 hours\")
\"\"\")
ok_rows = c.fetchall()
print(f\"status_ok_24h={len(ok_rows)}\")
# status=failed ingestions in last 24h — sample for reverse-ghost cross-check
c.execute(\"\"\"
  SELECT article_id, ingested_at FROM ingestions
  WHERE status = \"failed\" AND ingested_at >= datetime(\"now\", \"-24 hours\")
\"\"\")
failed_rows = c.fetchall()
print(f\"status_failed_24h={len(failed_rows)}\")
print(\"NOTE: bidirectional ghost detection requires LightRAG kv_store cross-check —\")
print(\"      run reconcile script when available; manual sample below.\")
# Sample article_id list for operator manual cross-check
print(\"sample_ok_article_ids=\", [r[0] for r in ok_rows[:5]])
print(\"sample_failed_article_ids=\", [r[0] for r in failed_rows[:5]])
"
    fi
  '
} >> "$LOG" 2>&1

# Compute per-day verdict — extract total_24h + ghost count from log,
# compute rate, classify if any ghost.
```

**Per-day acceptance probe (executor extracts from log):**

```bash
TOTAL=$(grep -oE "total_24h=[0-9]+" "$LOG" | tail -1 | cut -d= -f2)
# Ghost count: from reconcile script output if available, else manual.
# If reconcile script returned "ghost_count=N", parse it; else count via
# operator cross-check against LightRAG kv_store and append to log.

# Pass: ghost_count / total_24h < 0.01
# Threshold bust: classify migration-related Y/N before deciding RESTART vs. continue
```

If any ghost is observed, append a classification block to the log:

```text
=== STAB-02 day N ghost classification ===
ghost_article_id: <id>
hypothesis: "<short>"
migration_related: Y/N
reasoning: "<one-paragraph why Y or why N — e.g., 'matches 2026-05-14 ghost class
            from project_v1_0_y_closure_260517.md, OMNIGRAPH_PROCESSED_RETRY=300
            budget exhausted but LightRAG completed 9min later — NOT migration-
            related, classify as v1.0.x noise floor'>"
verdict: RESTART (if Y) / OPERATOR-REVIEW (if N + ≥1%) / PASS (if <1%)
```

### Task 2 — Day-7 rollup verdict + aim-5-2-EVIDENCE.md `[agent-runnable]`

**`<read_first>`**

- All 7 daily logs (STAB-02 sections)
- `aim-5-CONTEXT.md` FINDING 1 (threshold-based handling) + FINDING 3
  (classification rules)
- Memory `project_ghost_success_observed_260514.md` (v1.0.x noise floor
  baseline reference)

**`<acceptance_criteria>`**

- `aim-5-2-EVIDENCE.md` exists with:
  - 7 daily rates table (Day | total | ghost | rate | classification | verdict)
  - 7-day rolling rate computation
  - Aggregate STAB-02 verdict: PASS / OPERATOR-REVIEW / RESTART
- Single forward-only commit on `main`.
- Conventional commit message: `docs(aim-5): STAB-02 7-day verdict (aim-5-2)`.
- `git status` clean post-commit.

**`<action>`**

Author `aim-5-2-EVIDENCE.md`:

```markdown
# aim-5-2 — STAB-02 7-day reconcile ghost_success rate evidence

**Timestamp:** <day-7 ts>
**Plan:** aim-5-2
**REQs:** STAB-02
**Status:** PASS / OPERATOR-REVIEW / RESTART

## Per-day rates

| Day | Date (ADT) | total_24h | ghost_24h | rate | classification | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | <ts> | N | n | n/N | (none / migration / v1.0.x) | PASS/REVIEW/RESTART |
| 2 | <ts> | ... | ... | ... | ... | ... |
| 3 | <ts> | ... | ... | ... | ... | ... |
| 4 | <ts> | ... | ... | ... | ... | ... |
| 5 | <ts> | ... | ... | ... | ... | ... |
| 6 | <ts> | ... | ... | ... | ... | ... |
| 7 | <ts> | ... | ... | ... | ... | ... |

## 7-day rolling rate

`Σ ghost_24h / Σ total_24h = X / Y = Z.Z%`

## Aggregate verdict

**STAB-02:** PASS / OPERATOR-REVIEW / RESTART

(Decision per FINDING 3: any day ≥ 1% migration-related → RESTART;
≥ 1% classified as v1.0.x noise → OPERATOR-REVIEW; all days < 1% → PASS.)

## Reconcile scope reference

Bidirectional scope from v1.0.y closure (commit `587fa85`); historical
noise floor 1/188 = 0.5% per `project_ghost_success_observed_260514.md`.

## References

- REQUIREMENTS STAB-02 (line 81)
- aim-5 CONTEXT FINDING 1 + FINDING 3
- Memory `feedback_contract_shape_change_full_audit.md`
```

Commit:

```bash
git add .planning/phases/aim-5-stability-watch/aim-5-2-EVIDENCE.md \
        .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/daily-checks-day-*.log
git status
git commit -m "docs(aim-5): STAB-02 7-day verdict (aim-5-2)"
git log -1 --name-only
```

## Risk and mitigation

| Risk | Mitigation |
| ---- | ---------- |
| No reconcile script in repo `scripts/` — bidirectional scope only exists conceptually post-v1.0.y | Probe falls back to inline SQL count + emits operator-side cross-check note. If no reconcile script ships during aim-5, the inline SQL captures `total_24h` deterministically; ghost count requires manual cross-check against LightRAG kv_store. Document the gap in EVIDENCE.md. |
| Migration-related vs. v1.0.x noise floor classification is ambiguous | Default to OPERATOR-REVIEW (NOT auto-RESTART) per FINDING 3. Decision is operator's; agent records the classification + reasoning, does not auto-restart. |
| Ghost rate spikes mid-window from a single bad article (e.g., 1 ghost / 5 ingestions on a slow day = 20%) | The threshold rule is per-day rate, not per-article count. Rate spike with low total → classify as v1.0.x noise floor (small denominator), unless the specific ghost is migration-related. |
| Daily probe SSH fails | Re-run later same day; cite original failure timestamp; per-day verdict requires successful probe. |
| Reconcile script paths drift between aim-N phases (renamed / moved) | Probe greps `scripts/` for `reconcile\|ghost` substring — survives renames as long as substring matches. |
| Forward-only commit discipline broken | Per CLAUDE.md 2026-05-15 #1: NEVER amend; forward-only correction commits |

## Evidence

- 7 per-day logs in `aim-5-EVIDENCE/daily-checks-day-N.log` (STAB-02
  sections with total / ghost / rate / classification)
- `aim-5-2-EVIDENCE.md` with per-day table + 7-day rolling rate +
  aggregate verdict
- Single forward-only commit hash on `main`
