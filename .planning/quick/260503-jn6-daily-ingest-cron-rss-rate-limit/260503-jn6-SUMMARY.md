---
phase: quick-260503-jn6
plan: 01
subsystem: daily-ingest-cron-rss-rate-limit
tags: [phase-5, cron, rate-limit, rss, orchestrate-daily, hotfix]
requires:
  - enrichment/rss_ingest.py --max-articles flag (already existed pre-plan)
  - batch_ingest_from_spider.py --max-articles CLI argument (already defined)
  - scripts/register_phase5_cron.sh from Plan 05-06 Task 6.1
provides:
  - orchestrate_daily.py accepts --step / --max-kol / --max-rss
  - ingest_from_db honors max_articles as a total-cap on --from-db path
  - daily-ingest cron body = orchestrate_daily --step 7 --max-kol 20 --max-rss 20
  - replace_job helper in register script (update-or-add semantics)
affects:
  - daily-ingest cron @ 09:00 (fires orchestrate_daily step 7 now, not raw batch_ingest)
tech-stack:
  added: []
  patterns:
    - "update-or-add bash pattern: replace_job tries remove/delete/rm in cascade"
    - "--step N flag via numeric prefix parsing (int(name.split('_')[0]))"
key-files:
  created: []
  modified:
    - enrichment/orchestrate_daily.py
    - batch_ingest_from_spider.py
    - scripts/register_phase5_cron.sh
    - tests/unit/test_orchestrate_daily.py
decisions:
  - JN6-01 --step implemented by numeric-prefix comparison on the step name tuple — no new data structure
  - JN6-02 cap point chosen at TOP of loop; uses existing `processed` counter so no new state variable introduced
  - JN6-03 replace_job tries hermes cron remove/delete/rm in cascade; fails quietly if none match — operator fallback documented
metrics:
  duration: "~6m (348s)"
  tasks: 3
  files: 4
  commits: 3
  completed: "2026-05-03"
---

# Phase quick-260503-jn6: daily-ingest cron RSS + rate limit Summary

**One-liner:** Daily-ingest cron now fires `orchestrate_daily --step 7` with per-branch `--max-kol 20 --max-rss 20` rate caps — closes the RSS gap (RSS was never ingested by any cron) and makes each 09:00 fire rate-limited so the Day-1 backlog (249 KOL + 479 RSS) consumes in controlled chunks.

---

## What Changed (per-file diff summary, ignore-CR-at-eol semantic lines)

| File | Lines | Role |
|---|---|---|
| `enrichment/orchestrate_daily.py` | +50 / -3 | `run()` gains `step` / `max_kol` / `max_rss` kwargs; `step_7_ingest_all` appends `--max-articles N` to each branch's cmd iff non-None; `main()` argparse wires three new CLI flags; module docstring updated |
| `batch_ingest_from_spider.py` | +17 / -1 | `ingest_from_db` accepts `max_articles: int \| None = None`; cap check at top of for-loop breaks after N successful rows (skips don't count); `main()` threads `args.max_articles` through; `--max-articles` help text updated for dual-mode behaviour |
| `scripts/register_phase5_cron.sh` | +36 / -4 | New `replace_job` helper (update-or-add); `daily-ingest` entry switched from `add_job` → `replace_job` with new body `run enrichment/orchestrate_daily.py --step 7 --max-kol 20 --max-rss 20`; header comment updated; other 5 jobs untouched |
| `tests/unit/test_orchestrate_daily.py` | +59 / -0 | 3 new tests (`test_step_flag_runs_only_that_step`, `test_max_kol_appended_to_kol_cmd`, `test_max_rss_appended_to_rss_cmd`); mock-only via `patch.object(od, "_run")`, no real HTTP |

**Total:** 4 files, 162 insertions / 8 deletions (semantic, `--ignore-cr-at-eol`).

Note on raw diff stat for `batch_ingest_from_spider.py`: `git show --stat` reports `59 insertions / 43 deletions` because git's diff algorithm sees per-line CR/LF ending drift when the Edit tool rewrites surrounding lines. The `--ignore-cr-at-eol` and `--ignore-all-space` diffs both confirm the real semantic diff is **17 insertions / 1 deletion** — exactly the 4 prescribed edits (signature addition, docstring, cap-check block, call-site + help-text). No adjacent code was semantically modified.

---

## Commits (origin/main, pushed in one push d9d1da3..665e55f)

| # | SHA | Message |
|---|---|---|
| 1 | `233ae61` | `feat(orchestrate): --step + --max-kol + --max-rss flags` |
| 2 | `a158019` | `feat(batch_ingest): --max-articles cap on --from-db path` |
| 3 | `665e55f` | `feat(cron): daily-ingest → orchestrate_daily --step 7 with rate limits` |

Push: `git push origin main` → `d9d1da3..665e55f  main -> main`

---

## Test Evidence

```
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\huxxha\Desktop\OmniGraph-Vault
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, mock-3.15.1, typeguard-4.5.1
collected 12 items

tests/unit/test_orchestrate_daily.py::test_nine_step_functions_defined PASSED           [  8%]
tests/unit/test_orchestrate_daily.py::test_success_path_traverses_all_9_steps PASSED    [ 16%]
tests/unit/test_orchestrate_daily.py::test_non_critical_failure_continues PASSED        [ 25%]
tests/unit/test_orchestrate_daily.py::test_critical_failure_triggers_alert_and_halts PASSED [ 33%]
tests/unit/test_orchestrate_daily.py::test_dry_run_prints_without_subprocess PASSED     [ 41%]
tests/unit/test_orchestrate_daily.py::test_skip_scan_skips_three_steps PASSED           [ 50%]
tests/unit/test_orchestrate_daily.py::test_step_8_failure_triggers_telegram_in_step_9 PASSED [ 58%]
tests/unit/test_orchestrate_daily.py::test_step_6_sql_does_not_touch_rss_tables PASSED  [ 66%]
tests/unit/test_orchestrate_daily.py::test_step_6_uses_bridge_not_direct_skill PASSED   [ 75%]
tests/unit/test_orchestrate_daily.py::test_step_flag_runs_only_that_step PASSED         [ 83%]
tests/unit/test_orchestrate_daily.py::test_max_kol_appended_to_kol_cmd PASSED           [ 91%]
tests/unit/test_orchestrate_daily.py::test_max_rss_appended_to_rss_cmd PASSED           [100%]

============================== 12 passed in 0.37s ==============================
```

**Count delta:** 9 → 12 (+3 new, 0 regressions, 0 real HTTP calls).

**CLI smoke test — `orchestrate_daily --step 7 --max-kol 5 --max-rss 5 --dry-run`:**

```
INFO SKIP 1_fetch_rss (--step 7)
INFO SKIP 2_classify_rss (--step 7)
INFO SKIP 3_health_check (--step 7)
INFO SKIP 4_scan_kol (--step 7)
INFO SKIP 5_classify_kol (--step 7)
INFO SKIP 6_enrich_deep (--step 7)
INFO DRY RUN: venv\bin\python batch_ingest_from_spider.py --from-db --topic-filter openclaw,hermes,agent,harness --min-depth 2 --max-articles 5
INFO DRY RUN: venv\bin\python enrichment/rss_ingest.py --max-articles 5
INFO 7_ingest_all: success=True critical=False
INFO SKIP 8_generate_digest (--step 7)
INFO SKIP 9_deliver (--step 7)
INFO done: {'failures': 0, 'results': {'7_ingest_all': True}}
```

Both DRY RUN lines include `--max-articles 5`; steps 1-6 and 8-9 are SKIPPED.

**Shell syntax:** `bash -n scripts/register_phase5_cron.sh` → exit 0.

---

## Operator Checklist (Hermes-side — run AFTER Day-1 digest lands 2026-05-04 09:30 ADT)

Run this on the production Hermes WSL2 PC. Remote runtime paths per CLAUDE.md: code at `~/OmniGraph-Vault`, runtime at `~/.hermes/omonigraph-vault/`, env at `~/.hermes/.env`.

### Step 1 — ssh to Hermes + pull the 3 new commits

```bash
ssh <hermes>
cd ~/OmniGraph-Vault
git pull --ff-only
# Expect: Updating d9d1da3..665e55f, Fast-forward
source venv/bin/activate
```

Optional sanity check that the 3 expected commits landed:

```bash
git log --oneline -4
# Expect top-3:
#   665e55f feat(cron): daily-ingest → orchestrate_daily --step 7 with rate limits
#   a158019 feat(batch_ingest): --max-articles cap on --from-db path
#   233ae61 feat(orchestrate): --step + --max-kol + --max-rss flags
```

### Step 2 — Remove the old daily-ingest cron body

**If `hermes cron` has a working `remove` / `delete` / `rm` subcommand,** Step 3 (`replace_job`) will auto-detect it — no manual work required. Skip ahead to Step 3.

**If the automatic cascade silently fails** (script prints `(remove failed; see SUMMARY for manual steps)`), use the manual path below. First, discover the correct subcommand name:

```bash
hermes cron --help
hermes cron list | grep daily-ingest
```

Then remove by matching subcommand name. Any of these, whichever works:

```bash
hermes cron remove --name daily-ingest
# or:
hermes cron delete --name daily-ingest
# or:
hermes cron rm --name daily-ingest
# or (positional form):
hermes cron remove daily-ingest
```

**Fallback — if no CLI remove works (cron registry edits require manual crontab):**

```bash
crontab -e
# Find the line containing "daily-ingest" with body referencing batch_ingest_from_spider.py
# Delete that single line, save, exit.
# Verify removal:
hermes cron list | grep daily-ingest   # should return empty
```

### Step 3 — Re-run register_phase5_cron.sh to add the new body

```bash
bash scripts/register_phase5_cron.sh
```

**Expected output:**

```
SKIP rss-fetch (already registered)
SKIP rss-classify (already registered)
SKIP daily-classify-kol (already registered)
SKIP daily-enrich (already registered)
REPLACE daily-ingest — removing existing then re-adding
SKIP daily-digest (already registered)
=== hermes cron list ===
<6 jobs listed>
```

If Step 2's automatic cascade worked, you'll see 5 SKIP + 1 REPLACE. If the cascade failed but you manually removed per Step 2 fallback, you'll see 5 SKIP + 1 `ADD daily-ingest @ 0 9 * * *` (because the snapshot's `$EXISTING` no longer contains the name). Both outcomes are success.

### Step 4 — Verify the new body is in place

```bash
hermes cron list | grep daily-ingest
# Expect exactly one line containing:
#   orchestrate_daily.py --step 7 --max-kol 20 --max-rss 20
```

### Step 5 — Manual dry-run smoke test (optional, on Hermes)

```bash
venv/bin/python enrichment/orchestrate_daily.py --step 7 --max-kol 5 --max-rss 5 --dry-run
# Expect:
#   6x SKIP lines for steps 1-6
#   1x DRY RUN venv/bin/python batch_ingest_from_spider.py --from-db ... --max-articles 5
#   1x DRY RUN venv/bin/python enrichment/rss_ingest.py --max-articles 5
#   2x SKIP lines for steps 8-9
#   done: {'failures': 0, 'results': {'7_ingest_all': True}}
```

Tomorrow at 09:00 the cron fires with the real caps `--max-kol 20 --max-rss 20`; watch the 09:30 digest for ingestion counts.

---

## Stop/Ping Conditions Triggered

None. All 3 tasks executed cleanly with no Rule 4 (architectural) escalations and no unexpected structures.

Minor considerations that did **not** trigger a ping (surfaced here for transparency per CLAUDE.md "Think Before Coding"):

1. **`batch_ingest_from_spider.py --max-articles` default=50 now applies to `--from-db`.** Plan explicitly prescribed threading `args.max_articles` through (not a conditional). Pre-plan, ad-hoc `--from-db` invocations without `--max-articles` would run unbounded; post-plan they cap at 50. This is a **behavior change for manual-backlog runs**, but it's a safety improvement (prevents another 249-article blow-past) and is exactly what the plan asked for. New cron always passes `--max-kol 20` → `--max-articles 20`, overriding default. Documented here for the operator.
2. **`batch_ingest_from_spider.py` raw diff shows 59/-43.** This is CR/LF eol drift from the Edit tool, not adjacent code modification. `--ignore-cr-at-eol --shortstat` shows the true semantic diff is **17/-1**, matching the 4 prescribed edits exactly. No `git diff --check` semantic regression; no lint regressions; tests green.

---

## Non-negotiables Preserved

- [x] **Other 5 crons untouched** — `rss-fetch`, `rss-classify`, `daily-classify-kol`, `daily-enrich`, `daily-digest` still use `add_job` (idempotent SKIP on re-run). Verified via `grep -n '^add_job "' scripts/register_phase5_cron.sh` — 5 matches.
- [x] **orchestrate_daily.py other 8 steps unchanged** — only `step_7_ingest_all` signature and body touched; `step_1..6` and `step_8..9` are byte-identical to HEAD before this plan. `run()` adds kwargs but routes them only to step_7 (all other steps called with the same `(dry_run)` arg as before). Verified via `test_success_path_traverses_all_9_steps`, `test_non_critical_failure_continues`, `test_critical_failure_triggers_alert_and_halts`, `test_dry_run_prints_without_subprocess`, `test_skip_scan_skips_three_steps`, `test_step_8_failure_triggers_telegram_in_step_9`, `test_step_6_sql_does_not_touch_rss_tables`, `test_step_6_uses_bridge_not_direct_skill` — 8/8 green.
- [x] **D-07 REVISED + D-19 preserved** — `step_6_enrich_deep` unchanged (KOL-only SQL, forward-only `date(a.fetched_at) = date('now','localtime')`); verified by the pre-existing `test_step_6_sql_does_not_touch_rss_tables` + `test_step_6_uses_bridge_not_direct_skill` passing.
- [x] **LLM routing unchanged** — no touches to `lib/*`, `enrichment/rss_ingest.py`, `enrichment/rss_fetch.py`, `enrichment/rss_classify.py`, `batch_classify_kol.py`, `enrichment/daily_digest.py`. DeepSeek stays for classify/translate; Gemini for Vision + embedding only.
- [x] **All tests mock-only** — the 3 new tests all use `patch.object(od, "_run")` or `patch("enrichment.orchestrate_daily.sqlite3")`; no `requests.post`, no subprocess exec, no real HTTP. Verified against the Cisco Umbrella proxy constraint.

---

## Self-Check: PASSED

- `.planning/quick/260503-jn6-daily-ingest-cron-rss-rate-limit/260503-jn6-SUMMARY.md` — will exist after this Write completes
- commit `233ae61` — found in `git log --oneline`: `233ae61 feat(orchestrate): --step + --max-kol + --max-rss flags`
- commit `a158019` — found in `git log --oneline`: `a158019 feat(batch_ingest): --max-articles cap on --from-db path`
- commit `665e55f` — found in `git log --oneline`: `665e55f feat(cron): daily-ingest → orchestrate_daily --step 7 with rate limits`
- remote `origin/main` — pushed at `d9d1da3..665e55f`
- `enrichment/orchestrate_daily.py` — modified (signature check: `run(dry_run, skip_scan, step=None, max_kol=None, max_rss=None)` confirmed in source)
- `batch_ingest_from_spider.py` — modified (signature check: `ingest_from_db(..., max_articles: int | None = None)` confirmed via `python -c "import inspect; import batch_ingest_from_spider as m; print(inspect.signature(m.ingest_from_db))"`)
- `scripts/register_phase5_cron.sh` — modified (`replace_job` defined, `daily-ingest` body = `orchestrate_daily.py --step 7 --max-kol 20 --max-rss 20` confirmed)
- `tests/unit/test_orchestrate_daily.py` — modified (12/12 tests pass; 3 new tests present)

All claims verified against disk + git log.
