---
phase: 05-pipeline-automation
plan: 04
subsystem: orchestrate-daily
tags: [wave2, orchestrate, state-machine, d-07-revised, d-19, telegram]
status: complete
created: 2026-05-03
completed: 2026-05-03
---

# Plan 05-04 SUMMARY — orchestrate_daily.py (9-step state machine)

**Status:** Complete (local; dry-run smoke deferred to Hermes)
**Wave:** 2
**Depends on:** 05-02, 05-03, 05-03b (all Wave 1 plans closed)

## 1. What shipped

| Task | Artifact | Status |
|------|----------|--------|
| 4.1  | `enrichment/orchestrate_daily.py` (308 lines; 9 step functions) | — |
| 4.1  | `tests/unit/test_orchestrate_daily.py` (9 tests) | 9/9 pass |

## 2. 9-step traversal & criticality classification

| # | Step | Invokes | Critical? | Rationale |
|---|------|---------|-----------|-----------|
| 1 | `fetch_rss`         | `enrichment/rss_fetch.py`             | No  | One feed 404 should not halt the pipeline; `rss_fetch.py` already has per-feed fault tolerance |
| 2 | `classify_rss`      | `enrichment/rss_classify.py`           | No  | DeepSeek transient error → retry tomorrow |
| 3 | `health_check`      | *delegated to 07:55 cron e7afccd9931b* | No  | Unconditional pass-through — never run from orchestrator |
| 4 | `scan_kol`          | `batch_scan_kol.py --daily`            | **Yes** | Without fresh scans, nothing downstream has input |
| 5 | `classify_kol`      | loop: `batch_classify_kol.py --topic X --min-depth 2` × 5 topics | No  | Per-topic fail → `any_failure=True`; pipeline still proceeds |
| 6 | `enrich_deep`       | `run_enrich_for_id.py --source kol --article-id N` per today's KOL row at depth>=2 | No  | Per-article loop; D-07 REVISED + D-19 scoped (forward-only, KOL-only) |
| 7 | `ingest_all`        | `batch_ingest_from_spider.py --from-db --topic-filter <keywords>` + `enrichment/rss_ingest.py` | No  | Aggregate summary; one branch failure doesn't mask the other |
| 8 | `generate_digest`   | `enrichment/daily_digest.py`           | No  | Empty-state is valid per design (see 05-05 Claude's Discretion §4) |
| 9 | `deliver`           | (no-op on happy path; `_telegram_alert` if step_8 failed) | No  | `daily_digest.py` handles its own Telegram send |

## 3. D-07 REVISED + D-19 compliance

**Step 6 SQL** (hardcoded; RSS tables never queried):

```sql
SELECT DISTINCT a.id FROM articles a
JOIN classifications c ON c.article_id = a.id
WHERE c.depth_score >= 2 AND COALESCE(a.enriched, 0) < 2
  AND date(a.fetched_at) = date('now','localtime')
```

- `articles` + `classifications` only — `rss_articles` / `rss_classifications`
  are NOT referenced (Test 8 asserts this by capturing all SQL issued in
  step_6 and checking substrings).
- `date(fetched_at) = date('now','localtime')` — forward-only guard per D-19.
- Per-article bridge call: `run_enrich_for_id.py --source kol
  --article-id <N>` (Test 9 asserts `--source kol` present,
  `--source rss` absent, `hermes` absent from every invocation).

**Forbidden literal scan:**

| Pattern | Count | Expected |
|---------|-------|----------|
| `--source rss` | 0 | 0 |
| `rss_classifications` | 0 | 0 |
| `hermes.*skill.*run.*enrich_article.*--article-id` | 0 | 0 |

## 4. Telegram alert wiring (D-18 + BLOCKER 5)

Two trigger paths (both use the shared `_telegram_alert()`):

1. **Critical step failure** (currently only step_4 has `critical=True`):
   orchestrator writes `CRITICAL: step 4_scan_kol failed: <summary>` and
   halts traversal. step_5..9 NOT called. Verified by Test 4.
2. **Digest (step_8) failure** (BLOCKER 5 from plan): step_9 receives
   step_8's result; if failed, fires alert with `Phase 5 digest failed:
   <step_8 summary>`. Verified by Test 7.

Message envelope: `[OmniGraph orchestrate_daily] <message>` prefix. On
missing `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` env vars, logs a
`CRITICAL (no Telegram creds): ...` line instead of crashing.

## 5. Step 5 classify_kol loop — contract observation

`batch_classify_kol.py --topic` is a **single-value required** argparse
parameter (verified 2026-05-03 @ `9062b45`). The orchestrator loops over
`DEFAULT_TOPICS = ("Agent", "LLM", "RAG", "NLP", "CV")` — one subprocess
per topic — rather than passing a CSV or multi-flag. Plan 05-04
interfaces text suggested `--topic <all>` which does not match the
actual CLI; the loop shape is the production contract (matches Wave 0
catch-up pattern). Also: `--days-back` is NOT present on
`batch_classify_kol.py`; dropped from the step_5 cmd.

## 6. Unit test summary

| # | Test | Verifies |
|---|------|----------|
| 1 | `test_nine_step_functions_defined` | all 9 `step_N_*` functions exist |
| 2 | `test_success_path_traverses_all_9_steps` | happy path records all 9 step keys |
| 3 | `test_non_critical_failure_continues` | rss_fetch failure does not halt traversal |
| 4 | `test_critical_failure_triggers_alert_and_halts` | scan_kol failure halts; step_5..9 NOT called; alert fires once |
| 5 | `test_dry_run_prints_without_subprocess` | `--dry-run` → `subprocess.run` call_count == 0 |
| 6 | `test_skip_scan_skips_three_steps` | `--skip-scan` removes steps 3, 4, 5; 6 others still run |
| 7 | `test_step_8_failure_triggers_telegram_in_step_9` | BLOCKER 5 — digest failure → exactly one "digest failed" alert |
| 8 | `test_step_6_sql_does_not_touch_rss_tables` | D-19 compliance — SQL captures prove no `rss_articles`/`rss_classifications` touched |
| 9 | `test_step_6_uses_bridge_not_direct_skill` | Every step_6 subprocess invokes `run_enrich_for_id.py --source kol`; no `hermes` CLI, no `--source rss` |

## 7. Known caveats

- **Subprocess timeout 3600s**: defence-in-depth ceiling. Real batch
  budget comes from `OMNIGRAPH_BATCH_TIMEOUT_SEC` (v3.2 Phase 17
  default 28800s) inside `batch_ingest_from_spider.py`. Orchestrator
  does NOT pass its own timeout to that subprocess beyond the 3600s
  defence bound, so a batch longer than 3600s will have the wrapper
  subprocess killed while the underlying Python may have work
  in-flight. If operational data shows this is a problem, raise the
  orchestrator-level timeout; budget layering stays at
  `lib/batch_timeout.py`.
- **No `lib.checkpoint` / `lib.vision_cascade` / `lib.batch_timeout`
  imports**: intentional per 05-CONTEXT infra_composition "Scope
  guardrail". Orchestrator is pure subprocess glue to preserve the D-16
  "Hermes drives" substitutability (cron prompts can replace the
  Python orchestrator at any time).
- **step_3 is a pass-through**: health-check runs from the existing
  07:55 cron `e7afccd9931b`. When `orchestrate_daily.py` is run
  manually outside cron context, health-check is NOT executed — this is
  by design; run `hermes cronjob run e7afccd9931b` separately if a
  manual ad-hoc health-check is needed.

## 8. Hermes-side verification (operator to run)

```bash
cd ~/OmniGraph-Vault && git pull --ff-only
venv/bin/python -m pytest tests/unit/test_orchestrate_daily.py -v   # expect 9/9

# Dry-run smokes
venv/bin/python enrichment/orchestrate_daily.py --dry-run --skip-scan
venv/bin/python enrichment/orchestrate_daily.py --dry-run
# Both should exit 0 and print 6-9 planned commands without invoking any.
```

## 9. Commits

1. (pending) — `feat(05-04): orchestrate_daily.py 9-step state machine + 9 unit tests`

## 10. Hand-off

Plan 05-04 complete. Plan 05-05 (`enrichment/daily_digest.py`) unblocked —
state machine's step_8 has a target. Plan 05-06 cron registration follows
05-05.
