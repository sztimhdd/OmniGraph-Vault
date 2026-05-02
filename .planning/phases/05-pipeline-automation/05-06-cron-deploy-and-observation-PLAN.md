---
phase: 05-pipeline-automation
plan: 06
type: execute
wave: 3
depends_on: [05-05]
files_modified:
  - scripts/register_phase5_cron.sh
  - .planning/STATE.md
  - .planning/ROADMAP.md
autonomous: false
requirements: [D-15, D-16]
must_haves:
  truths:
    - "6 Hermes cron jobs are registered on the remote host per PRD section 3.4 schedule"
    - "Existing jobs `health-check` (07:55) and `scan-kol` (08:00) are NOT touched or duplicated"
    - "`hermes cronjob list` shows all 6 new jobs as enabled"
    - "3-day observation window produces daily digest evidence"
    - "STATE.md and ROADMAP.md are updated with Phase 5 exit state after 3 days"
  artifacts:
    - path: "scripts/register_phase5_cron.sh"
      provides: "Idempotent script that registers the 6 Phase 5 cron jobs"
      min_lines: 40
    - path: ".planning/STATE.md"
      provides: "Updated Current Position + Phase 5 Exit State block"
  key_links:
    - from: "scripts/register_phase5_cron.sh"
      to: "hermes cronjob add"
      via: "shell commands per PRD section 3.4"
      pattern: "hermes cronjob add"
    - from: "Phase 5 Exit State in STATE.md"
      to: "daily digest delivery evidence"
      via: "3-day observation summary"
      pattern: "Phase 5 Exit"
---

<objective>
Register the 6 Phase 5 Hermes cron jobs per PRD section 3.4, observe for 3 days, and update STATE.md + ROADMAP.md when observations confirm autonomous operation.

Purpose: Cron is the only way the pipeline runs unattended. Without registration, the pipeline exists but never fires. This plan is the "go live" step.

Output: 6 new cron jobs registered (health-check + scan-kol preserved from Phase 4 unchanged), 3-day observation window evidenced, STATE and ROADMAP updated.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/05-pipeline-automation/05-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-PRD.md
@.planning/phases/05-pipeline-automation/05-04-orchestrate-daily-PLAN.md
@.planning/phases/05-pipeline-automation/05-05-daily-digest-PLAN.md
@.planning/STATE.md
@.planning/ROADMAP.md
@docs/OPERATOR_RUNBOOK.md
@docs/Deploy.md
@CLAUDE.md

<infra_composition>
**v3.1/v3.2 infrastructure composition (added 2026-05-01):** This plan goes live AFTER v3.2's operator docs landed. Three integrations:

1. **`docs/OPERATOR_RUNBOOK.md` is the recovery reference** — the 3-day observation window (Task 6.2) reports anomalies against it. Any Telegram alert during observation → operator cross-references to OPERATOR_RUNBOOK.md's recovery section. Task 6.3 Phase 5 Exit State in STATE.md MUST link to OPERATOR_RUNBOOK.md.
2. **`docs/Deploy.md` owns env var documentation** — Phase 5-specific env vars (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, optional `OMNIGRAPH_BATCH_TIMEOUT_SEC` override, OPML cache path if any) MUST be appended to `docs/Deploy.md` § "Environment Variables" as part of Task 6.1. **Do NOT create a separate Phase 5 env doc.**
3. **Checkpoint/resume metrics in 3-day observation** — Task 6.2 reporting additions:
   - Per day, run `python scripts/checkpoint_status.py --since "$(date -d 'yesterday' -I)"` (from v3.2 Phase 12) to report: articles started, articles that resumed from a prior stage (vs fresh), articles stuck mid-pipeline (partial state not advanced in >24h).
   - Any "stuck" count >0 → flag in Task 6.2 resume-signal message; operator consults OPERATOR_RUNBOOK.md for how to flush or retry.
   - Zero stuck across 3 days → strong signal the pipeline is converging per design.
4. **`daily-ingest` cron pre-check (optional, non-fatal)**: The cron prompt for job #5 (`daily-ingest`) MAY include "print siliconflow balance before starting" via `python -c "from lib.siliconflow_balance import check_balance; print(check_balance())"`. If balance check fails or returns negative, cron emits warning but does NOT block ingest (cascade circuit breaker handles provider failure). Decision: optional enhancement in Task 6.1 `add_job` prompt — can skip if it complicates the prompt.

**Non-changes**: PRD §3.4 cron schedule (6 jobs) is unchanged. "Hermes drives" pattern (D-16) unchanged. `scripts/register_phase5_cron.sh` idempotency unchanged.
</infra_composition>

<interfaces>
PRD section 3.4 full cron list (6 NEW jobs; 2 existing preserved):

Existing (preserve, do NOT re-register):
- 07:55 health-check  (id: e7afccd9931b)
- 08:00 scan-kol      (id: df7dc3fa0390)

NEW — register these 6:
1. rss-fetch           0 6  * * *  run enrichment/rss_fetch.py
2. rss-classify        0 7  * * *  run enrichment/rss_classify.py
3. daily-classify-kol  15 8 * * *  run batch_classify_kol.py --topic Agent --topic LLM --topic RAG --topic NLP --topic CV --min-depth 2 --days-back 1
4. daily-enrich        30 8 * * *  run the enrich_article skill for all KOL and RSS articles with depth_score >= 2 fetched today
5. daily-ingest        0 9  * * *  run batch_ingest_from_spider.py --from-db --topic-filter openclaw,hermes,agent,harness --min-depth 2
6. daily-digest        30 9 * * *  run enrichment/daily_digest.py

All jobs use `--model deepseek-v4-flash` (H-12: verify this identifier is valid on the remote — see Task 6.1 read_first; if not valid, substitute a confirmed model).

NOTE on "Hermes drives" (D-16): cron prompts describe intent in natural language ("run X"); Hermes translates the prompt into a Python subprocess invocation via the skill system. The orchestrator `enrichment/orchestrate_daily.py` is retained as a manual-run debugging tool (`--dry-run --skip-scan`), NOT as a cron body.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 6.1: Create idempotent cron-registration script and run it on remote</name>
  <files>scripts/register_phase5_cron.sh</files>
  <read_first>
    - .planning/phases/05-pipeline-automation/05-PRD.md section 3.4 (exact job definitions)
    - .planning/phases/05-pipeline-automation/05-CONTEXT.md D-16 "Hermes drives" pattern
    - On remote: `hermes cronjob --help` (confirm flag names and shapes)
    - On remote: `hermes cronjob list` output (confirm existing health-check + scan-kol jobs are present and untouched)
    - On remote (H-12): verify `--model deepseek-v4-flash` is a valid identifier. Try `hermes model list` (or equivalent) to confirm. If deepseek-v4-flash is not available, substitute a confirmed Gemini identifier — project CLAUDE.md shows Gemini is the project default and `databricks-claude-sonnet-4-6` etc. are Databricks endpoints, not Hermes models. Document the confirmed model in the plan SUMMARY.
  </read_first>
  <action>
    Create `scripts/register_phase5_cron.sh`. Structure:

    - Bash shebang + `set -euo pipefail`.
    - Capture existing jobs: `EXISTING="$(hermes cronjob list 2>/dev/null || echo '')"`.
    - Define a helper `add_job` that takes `name`, `schedule`, `prompt`, optional `extra_flags`; skips if name already appears in `$EXISTING`; otherwise runs `hermes cronjob add --name "$name" --schedule "$schedule" --prompt "$prompt" --model deepseek-v4-flash $extra_flags`.
    - Call `add_job` exactly 6 times with the arguments below:
      1. `add_job "rss-fetch" "0 6 * * *" "run enrichment/rss_fetch.py"`
      2. `add_job "rss-classify" "0 7 * * *" "run enrichment/rss_classify.py"`
      3. `add_job "daily-classify-kol" "15 8 * * *" "run batch_classify_kol.py --topic Agent --topic LLM --topic RAG --topic NLP --topic CV --min-depth 2 --days-back 1"`
      4. `add_job "daily-enrich" "30 8 * * *" "run the enrich_article skill for all KOL and RSS articles with depth_score >= 2 fetched today"`
      5. `add_job "daily-ingest" "0 9 * * *" "run batch_ingest_from_spider.py --from-db --topic-filter openclaw,hermes,agent,harness --min-depth 2"`
      6. `add_job "daily-digest" "30 9 * * *" "run enrichment/daily_digest.py"`  # H-11 fix: removed `--deliver telegram` (daily_digest.py argparse does not accept it; delivery is unconditional without --dry-run)
    - After all `add_job` calls, print `=== hermes cronjob list ===` and then run `hermes cronjob list` to show the final state.

    Make it executable: `chmod +x scripts/register_phase5_cron.sh`.

    Execute on remote:
    ```
    ssh remote "cd ~/OmniGraph-Vault && git pull --ff-only && bash scripts/register_phase5_cron.sh"
    ```

    Decision note: PRD section 3.4 lists 6 independent jobs (not an orchestrator-wrapped one). We follow PRD; `enrichment/orchestrate_daily.py` remains a manual-run debugging convenience (`--dry-run --skip-scan`) and a future consolidation candidate, not a cron body. This divergence from the originally-ambiguous "7 jobs" count in the planning context is recorded in the Task 6.3 STATE.md update.
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; bash scripts/register_phase5_cron.sh &amp;&amp; hermes cronjob list | grep -cE '^(rss-fetch|rss-classify|daily-classify-kol|daily-enrich|daily-ingest|daily-digest)\\b'" | tail -1 | grep -q "^6$"</automated>
  </verify>
  <acceptance_criteria>
    - File `scripts/register_phase5_cron.sh` exists and is executable (`-x` bit).
    - File contains exactly 6 `add_job` calls.
    - File does NOT register `health-check` or `scan-kol` (grep -q returns 1 for those names).
    - After execution on remote, `hermes cronjob list` shows 6 new names plus the 2 preserved existing jobs (total at least 8 jobs).
    - Re-running the script is a no-op (prints "SKIP <name>" for each already-registered job).
    - H-12: `ssh remote "hermes cronjob list"` shows all 6 new jobs registered with the confirmed model identifier.
  </acceptance_criteria>
  <done>All 6 cron jobs registered; pipeline armed for autonomous operation.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 6.2: 3-day observation window — user confirms digest arrives</name>
  <what-built>
    6 Phase 5 cron jobs registered on the remote host. From Task 6.1 forward, the remote host should autonomously scan + classify + enrich + ingest + deliver digest every day at ~09:30 local time.
  </what-built>
  <how-to-verify>
    Wait 3 calendar days after Task 6.1 completes.

    Each day:
    1. Confirm Telegram received the daily digest (or check `~/.hermes/omonigraph-vault/digests/YYYY-MM-DD.md` for the archive on the remote).
    2. Note any anomalies: missing digest, malformed Markdown, Telegram rate limit, etc.
    3. On the remote, inspect `hermes cronjob list --verbose` (or equivalent) for per-job success/fail counts.

    After 3 days, record in the task resume signal one of the following:
    - `approved` — all 3 daily digests delivered, no cron failures, ready to close Phase 5.
    - `approved-with-notes: <details>` — pipeline worked but with caveats (e.g., one day had zero candidates → empty-state skip per design).
    - `rejected: <reason>` — pipeline broke (e.g., CDP unreachable 2 of 3 mornings); needs debug.

    If `rejected`, Task 6.3 STATE.md update is a partial one (record failure mode); follow-up debugging is out of this plan.
  </how-to-verify>
  <resume-signal>Type `approved`, `approved-with-notes: ...`, or `rejected: ...`</resume-signal>
</task>

<task type="auto">
  <name>Task 6.3: Update STATE.md and ROADMAP.md with Phase 5 Exit State</name>
  <files>.planning/STATE.md, .planning/ROADMAP.md</files>
  <read_first>
    - .planning/STATE.md (current content — look for `## Current Position`, `## Phase 4 Exit State` for format reference)
    - .planning/ROADMAP.md (current content — look for `## Done`, `## Current`, `## Next` sections)
    - The plan SUMMARY files for 05-00 through 05-05 (already committed in earlier waves)
    - The Task 6.2 resume-signal result (from the user)
  </read_first>
  <action>
    **1. In `.planning/STATE.md`:**

    Replace the `## Current Position` block so Phase 5 is the closed phase. Use the Phase 4 Exit State block as the format template. Include:
    - Phase 5 closed on date X (today).
    - All 6 plans (00, 00b, 01, 02, 03, 04, 05, 06) shipped.
    - Progress bar: 100%.
    - Last activity: Phase 5 merged + cron live + 3-day observation complete.

    Insert a new `## Phase 5 Exit State` block directly after the existing `## Phase 4 Exit State`. Content:
    - Cron jobs registered: list the 6 new job names with schedule.
    - Day-1, day-2, day-3 digest delivery results from Task 6.2.
    - KOL catch-up result from Plan 05-00b (filtered subset count, LightRAG entity delta).
    - Benchmark result from Plan 05-00 (Chinese top-5 overlap avg, cross-modal hit rate).
    - Any blockers / follow-ups to carry forward (e.g., "Batch API unavailable on free tier; fell back to sync with 60 RPM throttle").

    Update `## Accumulated Context > Decisions` with a Phase 5 summary line like:
    - `- Phase 5: 18 locked decisions (D-01..D-18) captured in 05-CONTEXT.md; migrated embeddings to gemini-embedding-2; RSS pipeline + daily digest live`.

    **2. In `.planning/ROADMAP.md`:**

    Move the Phase 5 entry from `## Next` into `## Done`. Format match the existing Phase 4 entry:
    - Title: `Phase 5: pipeline-automation (YYYY-MM-DD)`
    - One-paragraph summary: N plans shipped, embedding migration + RSS pipeline + daily digest; autonomous cron observed for 3 days; reference to 05-CONTEXT.md for decisions.

    Update the `## Current` block to reflect the new present state — likely shifts to monitoring the autonomous pipeline or moves on to Phase 6 / Phase 7 depending on user direction. If unsure, just note "Phase 5 in autonomous operation; next phase selection pending".

    **3. In `.planning/phases/05-pipeline-automation/05-VALIDATION.md`:** (M-18 fix)

    Update the frontmatter:
    - Change `nyquist_compliant: false` to `nyquist_compliant: true`.
    - Change `wave_0_complete: false` to `wave_0_complete: true`.
    - Change `status: draft` to `status: final`.

    These flip after Wave 0 + Wave 1 + Wave 2 all exit green (via the per-plan SUMMARYs) and 3-day observation confirms autonomous operation. VALIDATION.md's per-task status column may also be updated to ✅ green for rows whose tasks completed.
  </action>
  <verify>
    <automated>grep -q "Phase 5 Exit State" .planning/STATE.md &amp;&amp; grep -q "pipeline-automation" .planning/ROADMAP.md &amp;&amp; awk '/## Done/,/## Current/' .planning/ROADMAP.md | grep -q "Phase 5"</automated>
  </verify>
  <acceptance_criteria>
    - `.planning/STATE.md` contains the header `## Phase 5 Exit State`.
    - `.planning/STATE.md` `## Current Position` no longer lists Phase 4 as the current focus; Phase 5 is shown as closed OR a new current focus is stated.
    - `.planning/ROADMAP.md` `## Done` section contains a Phase 5 entry with dated completion.
    - `.planning/ROADMAP.md` `## Next` section no longer lists Phase 5 pipeline-automation as the next phase.
    - M-18: `grep -q "nyquist_compliant: true" .planning/phases/05-pipeline-automation/05-VALIDATION.md` returns 0.
    - M-18: `grep -q "wave_0_complete: true" .planning/phases/05-pipeline-automation/05-VALIDATION.md` returns 0.
  </acceptance_criteria>
  <done>Phase 5 officially closed; STATE.md + ROADMAP.md + VALIDATION.md reflect current project state.</done>
</task>

</tasks>

<verification>
- 6 new cron jobs visible via `hermes cronjob list` on remote (plus the 2 preserved existing jobs).
- User confirmed (Task 6.2 resume signal) 3 consecutive daily digests delivered.
- STATE.md updated with Phase 5 Exit State.
- ROADMAP.md moved Phase 5 from Next to Done.
</verification>

<success_criteria>
- D-15 satisfied: cron registration + observation all happened on remote.
- D-16 satisfied: each cron prompt follows "Hermes drives" pattern (natural-language prompt → Hermes subprocess → Python helper).
- 3-day observation window complete.
- STATE/ROADMAP reflect phase closure.
</success_criteria>

<output>
After completion, create `.planning/phases/05-pipeline-automation/05-06-SUMMARY.md` with: full `hermes cronjob list` output, 3-day observation log (dates + digest delivery results + any failures), link to the updated STATE.md and ROADMAP.md diffs.
</output>
