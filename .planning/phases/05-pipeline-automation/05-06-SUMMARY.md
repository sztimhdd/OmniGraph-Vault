---
phase: 05-pipeline-automation
plan: 06
subsystem: cron-deploy-and-observation
tags: [wave2, cron, hermes, d-16, observation-pending]
status: partial
created: 2026-05-03
task_6_1_completed: 2026-05-03
task_6_2_status: pending (3-day observation window; user-driven)
task_6_3_status: pending (after Task 6.2 user verdict)
---

# Plan 05-06 SUMMARY — Cron deploy + observation (Task 6.1 only)

**Status:** Task 6.1 complete; Tasks 6.2 + 6.3 blocked on 3-day
observation window (user-driven checkpoint).

**Wave:** 2 (partial close)
**Depends on:** 05-04, 05-05

## 1. Task 6.1 — What shipped

| Artifact | Status |
|----------|--------|
| `scripts/register_phase5_cron.sh` (85 lines, executable) | — |

Idempotent shell script. Snapshot of existing `hermes cronjob list`
taken once at startup; `add_job` helper skips names already present
with `SKIP <name>` message. Per D-16 "Hermes drives", each cron job
is registered with a natural-language prompt, not a hardcoded Python
subprocess invocation.

## 2. The 6 cron jobs registered

| # | Name | Schedule (local) | Prompt |
|---|------|------------------|--------|
| 1 | `rss-fetch`           | `0 6 * * *`  | `run enrichment/rss_fetch.py` |
| 2 | `rss-classify`        | `0 7 * * *`  | `run enrichment/rss_classify.py` |
| 3 | `daily-classify-kol`  | `15 8 * * *` | `run batch_classify_kol.py --topic Agent --topic LLM --topic RAG --topic NLP --topic CV --min-depth 2 --days-back 1` |
| 4 | `daily-enrich`        | `30 8 * * *` | `run the enrich_article skill for all KOL articles (WeChat source only; RSS excluded per D-07 REVISED 2026-05-02 + D-19) with depth_score >= 2 fetched today` |
| 5 | `daily-ingest`        | `0 9 * * *`  | `run batch_ingest_from_spider.py --from-db --topic-filter openclaw,hermes,agent,harness --min-depth 2` |
| 6 | `daily-digest`        | `30 9 * * *` | `run enrichment/daily_digest.py` |

**Not touched** (preserved from earlier phases):
- `health-check` @ 07:55 (id `e7afccd9931b`)
- `scan-kol` @ 08:00 (id `df7dc3fa0390`)

Total after registration: **8** cron jobs (6 new + 2 existing).

## 3. D-07 REVISED + D-19 compliance in cron wording

Job #4 (`daily-enrich`) prompt is load-bearing. The Hermes skill
resolver uses the wording to decide which DB table to enumerate:

> "run the enrich_article skill for all KOL articles **(WeChat source only; RSS excluded per D-07 REVISED 2026-05-02 + D-19)** with depth_score >= 2 **fetched today**"

Two gates encoded in natural language:
- "KOL articles (WeChat source only; RSS excluded …)" — D-07 REVISED
  enforced at prompt level, mirroring `run_enrich_for_id.py --source kol`
  and `orchestrate_daily.step_6_enrich_deep`'s SQL scope.
- "fetched today" — D-19 forward-only guard.

Alternate wording that would break D-07 REVISED (must NEVER land):
- "all articles with depth_score >= 2" (would include RSS)
- "all KOL articles …" without "(WeChat source only)" qualifier (risks
  the resolver aliasing rss_articles under "KOL")
- Omitting "fetched today" (would backfill historical KOL rows per D-19
  prohibition)

## 4. Job #5 `daily-ingest` composition note (from infra_composition §4)

Optional pre-check `print(check_balance())` via
`lib/siliconflow_balance.py` is **not** wired into the cron prompt.
Cascade circuit breaker in `lib/vision_cascade.py` handles provider
failover automatically; adding a balance pre-check to the prompt
complicates the natural-language contract without material benefit.
Operator can monitor SiliconFlow balance separately per
`docs/OPERATOR_RUNBOOK.md`.

## 5. Job #6 `daily-digest` H-11 note

Plan body had a deprecated `--deliver telegram` flag; removed. Current
`daily_digest.py` delivers via Telegram unconditionally unless
`--dry-run` is set. Per-05-05 design: missing Telegram creds →
`rc=1` + archive still written; cron sees `rc=1` and can emit its own
alert.

## 6. Model identifier (H-12)

Script defaults to `--model deepseek-v4-flash`. Per PRD §3.4 wording.
If the remote rejects the identifier (H-12 fallback), operator can
override at runtime:

```bash
MODEL=gemini-2.5-flash bash scripts/register_phase5_cron.sh
```

The script prints `hermes cronjob list` at the end so the operator
can confirm the model used.

## 7. Task 6.1 verification (to run on Hermes)

```bash
cd ~/OmniGraph-Vault && git pull --ff-only
bash scripts/register_phase5_cron.sh

# Expect 6 "ADD <name> @ ..." lines on first run
# Expect 6 "SKIP <name> (already registered)" lines on second run (idempotency)

hermes cronjob list | grep -cE '\b(rss-fetch|rss-classify|daily-classify-kol|daily-enrich|daily-ingest|daily-digest)\b'
# Expect: 6

hermes cronjob list | grep -cE '\b(health-check|scan-kol)\b'
# Expect: 2 (preserved)
```

## 8. Task 6.2 — 3-day observation window (pending, user-driven)

**Autonomous execution stops here.** Task 6.2 is a blocking
`checkpoint:human-verify`: the user watches for 3 consecutive daily
digests (cron goes live the day after registration — first digest at
09:30 local).

Signal options when observation completes:
- `approved` — all 3 daily digests delivered, no cron failures.
- `approved-with-notes: <details>` — digests delivered with caveats.
- `rejected: <reason>` — pipeline broke; needs debug.

## 9. Task 6.3 — STATE + ROADMAP + VALIDATION finalization (pending)

Runs AFTER Task 6.2 user signal:
- `.planning/STATE.md` `## Current Position` → Phase 5 closed.
- `.planning/STATE.md` insert `## Phase 5 Exit State` block after
  `## Phase 4 Exit State`.
- `.planning/ROADMAP.md` move Phase 5 entry from `## Next` → `## Done`.
- `.planning/phases/05-pipeline-automation/05-VALIDATION.md`
  frontmatter flip: `status: draft → final`, `wave_0_complete: true`,
  `nyquist_compliant: true`.

Not executed in this autonomous run.

## 10. Commits

1. (pending) — `feat(05-06): register_phase5_cron.sh + Task 6.1 SUMMARY`

## 11. Hand-off

Task 6.1 complete. Operator runs `bash scripts/register_phase5_cron.sh`
on Hermes; cron goes live tomorrow at 06:00 local (RSS fetch); first
digest lands 09:30 local. Resume with observation signal after 3 days.
