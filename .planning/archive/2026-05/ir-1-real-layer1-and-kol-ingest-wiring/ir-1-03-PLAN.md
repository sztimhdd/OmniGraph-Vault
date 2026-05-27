---
phase: ir-1-real-layer1-and-kol-ingest-wiring
plan: 03
type: execute
wave: 3
depends_on:
  - "ir-1-00"
  - "ir-1-01"
  - "ir-1-02"
files_modified:
  - .planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md
autonomous: false  # ends with a STOP gate — operator runs the actual Hermes deploy
requirements:
  - LF-4.1

must_haves:
  truths:
    - "HERMES-DEPLOY.md is a complete operator runbook: pre-flight, backup, migration 006, code pull, smoke 5 articles, verification, rollback"
    - "Local .dev-runtime smoke evidence is captured at .scratch/ir-1-local-smoke-<timestamp>.md and referenced in the Hermes runbook as the 'this exact build was sanity-checked locally on <date>' artifact"
    - "Runbook explicitly enumerates the post-charter backlog implication from ROADMAP § ir-1 Notes (first cron run will see N batches × 8s wall-clock instead of 2-3, plus larger Gemini Flash Lite quota draw on day 1)"
    - "Rollback path documented: revert commits + drop layer1_* columns via PRAGMA + table-rebuild OR (simpler) leave columns in place since they are NULL-defaulted and harmless. Both options listed; simpler one recommended"
    - "Plan ENDS at runbook authored + local smoke green. Per user direction (2026-05-07 session): STOP at deploy stage, do NOT SSH or run the actual Hermes deploy commands"
  artifacts:
    - path: ".planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md"
      provides: "Operator runbook for ir-1 Hermes deploy. Operator runs SSH-side; agent does not"
      min_lines: 120
      contains: "migration 006"
    - path: ".scratch/ir-1-local-smoke-<timestamp>.md"
      provides: "Local sanity-check evidence — output of `--max-articles 5 --dry-run` against .dev-runtime DB after ir-1-00..02 ship"
      min_lines: 30
      contains: "[layer1] batch"
  key_links:
    - from: ".planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md"
      to: "migrations/006_layer1_columns.py (ir-1-00 output) + lib/article_filter.py (ir-1-00) + batch_ingest_from_spider.py (ir-1-01)"
      via: "documented step-by-step shell commands"
      pattern: "python migrations/006_layer1_columns.py"
    - from: ".scratch/ir-1-local-smoke-<timestamp>.md"
      to: ".dev-runtime/data/kol_scan.db (mirror of production schema)"
      via: "OMNIGRAPH_BASE_DIR override + --dry-run smoke"
      pattern: "OMNIGRAPH_BASE_DIR=.dev-runtime"
---

<objective>
Wave 3: produce the operator-facing artifacts that close ir-1 locally so the user can decide when to run the actual Hermes deploy. Deliverables: (1) a self-contained HERMES-DEPLOY.md runbook, (2) a local `.dev-runtime` smoke output capturing the exact behavior the runbook expects on Hermes.

Per user direction this session, this plan EXPLICITLY stops at "runbook authored + local smoke green". The agent does NOT SSH to Hermes, does NOT run migration 006 against production, does NOT touch cron state. Hermes deploy is the operator's next turn.

Output: `.planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md` + `.scratch/ir-1-local-smoke-<ts>.md`.
</objective>

<execution_context>
@.planning/PROJECT-v3.5-Ingest-Refactor.md
@.planning/ROADMAP-v3.5-Ingest-Refactor.md
@.planning/STATE-v3.5-Ingest-Refactor.md
@.planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/HERMES-DEPLOY.md
</execution_context>

<context>
@CLAUDE.md
</context>

<interfaces>
<!-- The Foundation Quick HERMES-DEPLOY.md (260507-lai) is the structural model.
     ir-1's runbook follows the same shape:
       1. Pre-flight (hostname, branch, HEAD)
       2. Backup (DB + cron registry — Lessons 2026-05-06 #2)
       3. Pull main
       4. Apply migration (006)
       5. Verify schema
       6. Smoke 5 articles (dry-run, then 1 real)
       7. Resume cron / monitor
       8. Rollback path (commits revert + DB restore from backup) -->

<!-- Existing Hermes operational state to reflect in the runbook (per
     STATE-v3.5-Ingest-Refactor.md § Current Hermes Operational State):

  - daily-classify-kol / daily-enrich / rss-classify: REMOVED by Foundation Quick
  - daily-ingest: ACTIVE, runs 09:00 ADT, prompt = `run batch_ingest_from_spider.py --from-db`
  - 每日KOL扫描 / KOL扫描前健康检查 / rss-fetch / daily-digest / vertex-probe-monthly: untouched, active

  ir-1 deploy must:
   - Pause daily-ingest BEFORE migration 006 (avoid mid-batch column races)
   - Apply migration 006
   - Resume daily-ingest AFTER smoke verifies 5 articles work end-to-end
   - Day-1 backlog warning: cron resume will see post-charter (2026-05-07 ~14:33 ADT)
     accumulation; first run is 5-15 batches × 8s wall-clock + extra Gemini quota draw -->
</interfaces>

<tasks>

<task type="auto" tdd="false">
  <name>Task 4.1: Local .dev-runtime smoke — capture evidence</name>
  <read_first>
    - .dev-runtime/data/kol_scan.db (verify it exists; if not, defer to operator manual setup per docs/LOCAL_DEV_SETUP.md)
    - docs/LOCAL_DEV_SETUP.md (if .dev-runtime not present)
    - lib/article_filter.py post ir-1-00 (verify the verbatim prompt is in place)
  </read_first>
  <files>.scratch/ir-1-local-smoke-<timestamp>.md</files>
  <behavior>
    - Run a 5-article dry-run smoke against `.dev-runtime/data/kol_scan.db` to verify:
      1. Migration 006 applies cleanly to the local DB (`python migrations/006_layer1_columns.py .dev-runtime/data/kol_scan.db`)
      2. PRAGMA table_info confirms 4 layer1_* columns on `articles` and `rss_articles`
      3. `python batch_ingest_from_spider.py --from-db --max-articles 5 --dry-run` exits 0
      4. Log output contains `[layer1] batch` line(s)
      5. Post-run, query `SELECT id, layer1_verdict, layer1_prompt_version FROM articles WHERE layer1_at IS NOT NULL ORDER BY layer1_at DESC LIMIT 10` returns rows with verdict ∈ {candidate, reject} and prompt_version='layer1_v0_20260507'
    - Capture output to `.scratch/ir-1-local-smoke-<YYYY-MM-DD-HHMM>.md` with sections: Pre-flight / Migration 006 output / Smoke command + log / DB verification query results / Conclusion
    - **If `.dev-runtime/data/kol_scan.db` does not exist on the operator's machine**: the smoke MUST be DEFERRED. Write the runbook anyway in Task 4.2 but mark this task's evidence file as "Deferred — operator to set up .dev-runtime per docs/LOCAL_DEV_SETUP.md before re-running this smoke." This is acceptable per CLAUDE.md "if you can't test the UI, say so explicitly"
  </behavior>
  <action>
1. **Pre-flight check**:
```bash
ls .dev-runtime/data/kol_scan.db 2>&1
```

2. **If exists, run smoke**. Otherwise, jump to step 5.

3. Apply migration 006 to local DB:
```bash
python migrations/006_layer1_columns.py .dev-runtime/data/kol_scan.db | tee /tmp/ir-1-mig006.log
sqlite3 .dev-runtime/data/kol_scan.db "PRAGMA table_info(articles)" | grep layer1_
sqlite3 .dev-runtime/data/kol_scan.db "PRAGMA table_info(rss_articles)" | grep layer1_
```
Expect: 8 lines total (4 layer1_* columns × 2 tables).

4. Run dry-run smoke:
```bash
TS=$(date +%Y-%m-%d-%H%M)
OMNIGRAPH_BASE_DIR=$(pwd)/.dev-runtime \
  python batch_ingest_from_spider.py --from-db --max-articles 5 --dry-run \
  2>&1 | tee /tmp/ir-1-smoke-${TS}.log
```
Expect: at least one `[layer1] batch` line; exit code 0.

5. **Author** `.scratch/ir-1-local-smoke-${TS}.md` with this template:

```markdown
# ir-1 Local Smoke Evidence

**Date:** <YYYY-MM-DD HH:MM ADT>
**Branch / HEAD:** <git rev-parse --abbrev-ref HEAD> @ <git rev-parse --short HEAD>
**.dev-runtime status:** <present | DEFERRED — operator-setup needed>

## Migration 006

```
<paste output of `python migrations/006_layer1_columns.py .dev-runtime/data/kol_scan.db` here>
```

PRAGMA verification:

```
<paste sqlite3 PRAGMA table_info output for articles + rss_articles, layer1_* lines>
```

## Dry-run smoke

Command:

```
OMNIGRAPH_BASE_DIR=.dev-runtime \
  python batch_ingest_from_spider.py --from-db --max-articles 5 --dry-run
```

Output (last ~30 lines):

```
<paste tail of the smoke log, including [layer1] batch lines>
```

## Post-run DB verification

```sql
SELECT id, layer1_verdict, layer1_prompt_version, layer1_at
FROM articles
WHERE layer1_at IS NOT NULL
ORDER BY layer1_at DESC
LIMIT 10;
```

```
<paste query result>
```

## Conclusion

- [ ] Migration 006 applies idempotently
- [ ] Layer 1 batch call hits LLM endpoint via `OMNIGRAPH_LLM_PROVIDER` route
- [ ] Verdicts persist with `prompt_version=layer1_v0_20260507`
- [ ] Reject rows skip per-article body; candidate rows hit dry-run short-circuit
- [ ] Exit code 0; no exceptions in log

Sign-off (local sanity only — Hermes deploy gated by operator):

— <author>, <YYYY-MM-DD HH:MM ADT>
```

6. **If `.dev-runtime/data/kol_scan.db` did NOT exist** in step 2, populate the file with a "DEFERRED" section explaining what's missing and pointing operator at `docs/LOCAL_DEV_SETUP.md`. Do NOT block ir-1 close on operator setup; flag the gap clearly in the file and continue to Task 4.2.

**HARD CONSTRAINTS:**
- DO NOT run migration 006 against `data/kol_scan.db` (production-shape clone or actual prod) — only against `.dev-runtime/data/kol_scan.db` (local sandbox)
- DO NOT use real LLM credentials in a way that incurs cost beyond a single 5-article smoke. The smoke makes 1 Layer 1 batch call (~¥0.001) — acceptable
- DO NOT SSH to Hermes
  </action>
  <verify>
    <automated>ls .scratch/ir-1-local-smoke-*.md 2>&1 | head -1</automated>
  </verify>
  <acceptance_criteria>
    - File `.scratch/ir-1-local-smoke-<ts>.md` exists, ≥30 lines
    - File contains either: (a) full 6-section evidence with all 5 conclusion checkboxes ticked, OR (b) a clearly-marked DEFERRED section explaining what blocked local smoke (.dev-runtime missing) + pointer to docs/LOCAL_DEV_SETUP.md
    - File contains literal `[layer1] batch` (proves smoke executed) OR contains literal `DEFERRED` (proves we honored the env-gap acknowledgment)
  </acceptance_criteria>
  <done>Local smoke evidence captured (or deferred with explicit reason). ir-1 close is no longer blocked on local sanity check.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 4.2: Author HERMES-DEPLOY.md operator runbook</name>
  <read_first>
    - .planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/HERMES-DEPLOY.md (Foundation Quick runbook — structural model)
    - .planning/phases/19-generic-scraper-schema-kol-hotfix/19-DEPLOY.md (Phase 19 deploy runbook for prior-art reference)
    - migrations/006_layer1_columns.py (Task 1.3 output — runbook references this exact path)
    - .planning/STATE-v3.5-Ingest-Refactor.md § "Current Hermes Operational State" (current cron registry state)
  </read_first>
  <files>.planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md</files>
  <behavior>
    - Self-contained runbook: operator can execute without referring back to PROJECT/REQUIREMENTS
    - Step-by-step shell commands with verification gates after each step
    - Backup gates per CLAUDE.md Lesson 2026-05-06 #2
    - Pause/resume cron via Hermes CLI (operator-side; runbook documents the exact command shape)
    - Day-1 backlog warning surfaced prominently
    - Rollback section documents two paths: simple (leave NULL columns in place; revert commits only) + invasive (DROP COLUMN via SQLite table-rebuild)
  </behavior>
  <action>
**Create `.planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md`** with this content:

```markdown
# HERMES Deploy Runbook — Phase ir-1

**REQ:** LF-4.1
**Scope:** Apply migration 006 + ship ir-1-00..02 code to Hermes; verify
end-to-end Layer 1 path on a 5-article smoke; resume `daily-ingest` cron.
**Pre-condition:** Local sign-off on ir-1-00..02 (PLAN files in this directory),
local `.dev-runtime` smoke green per `.scratch/ir-1-local-smoke-<ts>.md`,
all commits pushed to `main`.
**Operator:** runs all steps SSH-side. Agent does not SSH.

---

## Step 0 — Pre-flight

```bash
# On local machine — confirm pushed state
git log --oneline -10
git status -sb     # expect clean
git rev-parse main # capture local HEAD; you'll match it on Hermes
```

Note local HEAD: `<paste short SHA here at deploy time>`.

## Step 1 — Connect to Hermes (operator)

```bash
# Use SSH details from ~/.claude/projects/c--*-OmniGraph-Vault/memory/hermes_ssh.md
ssh -p <port> <user>@<host>
```

On Hermes:

```bash
cd ~/OmniGraph-Vault
git fetch origin
git status -sb
hostname; pwd; git rev-parse --abbrev-ref HEAD
```

Expected: branch `main`, clean working tree.

## Step 2 — Backup (mandatory)

```bash
# DB backup — per CLAUDE.md Lessons 2026-05-06 #2
cp data/kol_scan.db data/kol_scan.db.backup-pre-ir1-mig006-$(date +%Y%m%d-%H%M%S)
ls -lh data/kol_scan.db.backup-pre-ir1-mig006-*

# Cron registry backup
cp ~/.hermes/cron/jobs.json ~/.hermes/cron/jobs.json.pre-ir1.$(date +%Y%m%d-%H%M%S)
```

## Step 3 — Pause `daily-ingest` cron

> Reason: avoid mid-run column-mismatch when migration 006 lands while a batch
> is in-flight. Migration is fast (<1s) but mid-batch races are not worth the
> risk.

Use the Hermes CLI command appropriate to your cron driver. The driver is
`hermes-cron` per `~/.hermes/cron/jobs.json` registry. Example shape (verify
exact command on the operator's machine):

```bash
hermes cron disable daily-ingest
hermes cron list | grep daily-ingest
# Expect: enabled=false
```

## Step 4 — Pull main + verify HEAD matches

```bash
git pull --ff-only origin main
git rev-parse HEAD
# Compare against local HEAD captured in Step 0 — must match.
```

If FAILS to fast-forward: stop. Investigate (Hermes ahead? Local not pushed?).
Per CLAUDE.md "Remote Hermes Deployment", reconcile before proceeding.

## Step 5 — Apply migration 006

```bash
python migrations/006_layer1_columns.py data/kol_scan.db
```

Expected output (excerpt):

```
ADD  articles.layer1_verdict
ADD  articles.layer1_reason
ADD  articles.layer1_at
ADD  articles.layer1_prompt_version
ADD  rss_articles.layer1_verdict
... (4 more)
migration 006: applied 8 column(s); skipped 0 (already present)
```

Verify schema:

```bash
sqlite3 data/kol_scan.db "PRAGMA table_info(articles)" | grep layer1_
sqlite3 data/kol_scan.db "PRAGMA table_info(rss_articles)" | grep layer1_
# Expect 4 lines per table = 8 lines total
```

Re-run migration once to confirm idempotency:

```bash
python migrations/006_layer1_columns.py data/kol_scan.db
# Expect: applied 0 column(s); skipped 8 (already present)
```

## Step 6 — Smoke 5 articles (dry-run)

```bash
source venv/bin/activate
python batch_ingest_from_spider.py --from-db --max-articles 5 --dry-run \
  2>&1 | tee /tmp/ir-1-smoke-dry-$(date +%Y-%m-%d-%H%M).log
```

Verify log:

```bash
grep '\[layer1\] batch' /tmp/ir-1-smoke-dry-*.log | head -3
# Expect at least 1 line shaped:
# [layer1] batch 0 n=5 candidate=N reject=M null=0 wall_ms=...
```

DB verification:

```bash
sqlite3 data/kol_scan.db "
  SELECT id, layer1_verdict, layer1_prompt_version
  FROM articles
  WHERE layer1_at IS NOT NULL
  ORDER BY layer1_at DESC
  LIMIT 10;
"
# Expect: 5 rows with verdict ∈ {candidate, reject} and prompt_version='layer1_v0_20260507'
```

## Step 7 — Smoke 1 article (real ingest, optional but recommended)

```bash
python batch_ingest_from_spider.py --from-db --max-articles 1 \
  2>&1 | tee /tmp/ir-1-smoke-real-$(date +%Y-%m-%d-%H%M).log
# Expect: layer1 verdict, then either skipped (reject) or scrape→layer2→ainsert success
```

If 1-article smoke fails: STOP. Investigate. Do NOT resume cron.

## Step 8 — Resume `daily-ingest` cron

```bash
hermes cron enable daily-ingest
hermes cron list | grep daily-ingest
# Expect: enabled=true
```

## Step 9 — First-cron-run watch

> ⚠ **Day-1 backlog warning** (per ROADMAP § ir-1 Notes): the first cron run
> after this deploy will see Layer-1-NULL on the entire post-charter accumulated
> backlog (since 2026-05-07 ~14:33 ADT). Expect 5–15 batches × ~8s wall-clock +
> extra Gemini Flash Lite quota draw on day 1. Subsequent runs settle to
> 2–3 batches/day in steady state.

Monitor first cron tick (typically next 09:00 ADT; check
`hermes cron list | grep daily-ingest` for the precise schedule):

```bash
tail -f ~/.hermes/cron/logs/daily-ingest.<latest>.log
# Watch for: [layer1] batch lines, candidate/reject counts, no exceptions
```

## Step 10 — Sign-off

After first cron run completes successfully:

1. Update `.planning/STATE-v3.5-Ingest-Refactor.md` — append a § "ir-1 deploy
   sync" entry with:
   - Deploy timestamp (UTC + ADT)
   - First-cron-run wall-clock + batch count
   - layer1 reject rate observed (sanity: should be 50–70% per spike)
   - Any anomalies
2. Commit STATE update on local + push.

---

## Rollback

### Path A — Simple (recommended)

ir-1 deploy is non-destructive: migration 006 only ADDs nullable columns; code
changes are commits that can be reverted.

```bash
# On Hermes
hermes cron disable daily-ingest

git log --oneline -5  # find the ir-1 commits
git revert <sha-of-ir-1-01>      # ingest loop wiring
git revert <sha-of-ir-1-00>      # lib/article_filter rewrite (CAREFUL: also reverts migration .py + .sql)
git push origin main             # if deploys via git pull-only

# layer1_* columns can stay in place — they are nullable, ignored by reverted code.
# Do NOT DROP columns unless you have a strong reason; SQLite DROP COLUMN
# requires table-rebuild, see Path B.

hermes cron enable daily-ingest
```

### Path B — Invasive (only if Path A insufficient)

DROP COLUMN in SQLite < 3.35 requires CREATE TABLE new + INSERT SELECT + DROP +
RENAME. SQLite 3.49.1 (Hermes confirmed at deploy time) supports
`ALTER TABLE ... DROP COLUMN`, but it is still slow on large tables.

```bash
# Restore from backup (atomic, fastest):
hermes cron disable daily-ingest
mv data/kol_scan.db data/kol_scan.db.bad-$(date +%Y%m%d-%H%M%S)
cp data/kol_scan.db.backup-pre-ir1-mig006-<TIMESTAMP> data/kol_scan.db
hermes cron enable daily-ingest
```

This loses any post-deploy ingestions (typically a small loss; backup is taken
moments before deploy). Acceptable rollback only in serious-regression scenarios.

---

## STOP gate (per session direction 2026-05-07)

This runbook is authored as part of ir-1-03-PLAN. Per user direction:
**agent does NOT execute this runbook**. Operator triggers the deploy at the
operator's chosen window (likely overlapping with `daily-ingest` 09:00 ADT
schedule; see Step 9 backlog warning).

After deploy completes, operator:
- Updates STATE-v3.5-Ingest-Refactor.md per Step 10 sign-off
- Decides whether to proceed to ir-2 (real Layer 2 + DeepSeek) or pause for
  observation. Per ROADMAP, ir-2 starts immediately if ir-1 deploy is clean
  (the 7-day observation window is ir-3, post-ir-2 deploy)

---

## References

- PROJECT-v3.5-Ingest-Refactor.md § "6 User-Locked D-Decisions" (D-LF-1..6)
- REQUIREMENTS-v3.5-Ingest-Refactor.md § LF-4.1 + LF-1.6
- ROADMAP-v3.5-Ingest-Refactor.md § Phase ir-1 Notes (Day-1 backlog warning)
- STATE-v3.5-Ingest-Refactor.md § "Current Hermes Operational State"
- ir-1-00-PLAN.md (migration 006 source)
- ir-1-01-PLAN.md (ingest loop wiring source)
- ir-1-02-PLAN.md (LF-1.9 unit tests)
- .scratch/ir-1-local-smoke-<ts>.md (local sanity evidence)
- Foundation Quick HERMES-DEPLOY.md: `.planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/HERMES-DEPLOY.md` (structural model)
```

**HARD CONSTRAINTS:**
- DO NOT include real Hermes hostnames, ports, or credentials. Reference the memory file `~/.claude/projects/c--*-OmniGraph-Vault/memory/hermes_ssh.md` for SSH details
- DO NOT run any of the runbook's shell commands during this plan's execute step. They are operator instructions
- DO NOT skip the Day-1 backlog warning — surface it prominently per ROADMAP § ir-1 Notes
- The runbook DOES NOT replace operator judgment. If the operator's environment differs (e.g. systemd timer instead of hermes-cron), they adapt the cron commands; the runbook's Step 3 + Step 8 + Step 9 commands are templates
  </action>
  <verify>
    <automated>test -f .planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md</automated>
    <automated>grep -q "migration 006" .planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md</automated>
    <automated>grep -q "Day-1 backlog warning" .planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md</automated>
    <automated>grep -q "Rollback" .planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md</automated>
  </verify>
  <acceptance_criteria>
    - File exists, ≥120 lines
    - Contains literal `migration 006` (referenced multiple times)
    - Contains literal `Day-1 backlog warning` AND `2026-05-07 ~14:33 ADT` (specific accumulation timestamp)
    - Contains both rollback paths (Path A simple + Path B invasive)
    - Contains explicit STOP gate section per user direction
    - Does NOT contain literal IP addresses, real port numbers, or real usernames
  </acceptance_criteria>
  <done>LF-4.1 delivered. Hermes deploy is now operator-ready behind an explicit STOP gate.</done>
</task>

</tasks>

<verification>
After Tasks 4.1 + 4.2 land:

```bash
# Runbook completeness
wc -l .planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md
grep -c "^## Step" .planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/HERMES-DEPLOY.md
# Expect ≥10 steps

# Local smoke evidence (success or deferred)
ls .scratch/ir-1-local-smoke-*.md | head -1
```

After this plan: ir-1 phase is **complete locally**. Hermes deploy is gated
behind explicit user trigger. ir-2 plan-phase does NOT start automatically
(per session direction "不要自动起 ir-2").
</verification>

<commit_message>
docs(ir-1): HERMES-DEPLOY runbook + local smoke evidence (LF-4.1)

Authored .planning/phases/ir-1-*/HERMES-DEPLOY.md as a self-contained
operator runbook covering: pre-flight, DB + cron-registry backup, pause
daily-ingest, pull main, apply migration 006, schema verification,
5-article dry-run + 1-article real smoke, cron resume, first-cron watch
with Day-1 backlog warning surfaced, STATE sign-off step, and two-path
rollback (revert + leave NULL columns; or restore-from-backup).

Local sanity captured at .scratch/ir-1-local-smoke-<ts>.md (or marked
DEFERRED if .dev-runtime is not set up on the operator's machine).

Per session direction (2026-05-07): agent stops at runbook authored +
local smoke green. Operator triggers actual Hermes deploy.

REQs: LF-4.1
Phase: v3.5-Ingest-Refactor / ir-1 / plan 03
Depends-on: ir-1-00 (migration + lib changes), ir-1-01 (ingest loop),
ir-1-02 (unit tests)
</commit_message>
