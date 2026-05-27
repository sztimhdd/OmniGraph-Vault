---
phase: quick-260503-lq7
plan: 01
subsystem: phase-5-pipeline-automation
tags:
  - rss-classify
  - orchestrate-daily
  - env-cap
  - sql-schema-fix
  - pre-production-bug
  - atomic-commit

dependency-graph:
  requires:
    - enrichment/rss_classify.py (pre-existing, Phase 5 Wave 1 deliverable)
    - enrichment/orchestrate_daily.py (pre-existing, Phase 5 Wave 2 deliverable)
    - tests/unit/test_rss_classify.py (6 existing tests)
    - tests/unit/test_orchestrate_daily.py (12 existing tests)
  provides:
    - OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP env var support (default 500) in _eligible_articles
    - step_6_enrich_deep SQL corrected to a.scanned_at (articles schema match)
  affects:
    - Day-2 cron fire at 2026-05-05 06:00 ADT — will no longer throw OperationalError on step_6
    - RSS classifier batch safety — explicit 500 cap instead of accidental 1000

tech-stack:
  added: []  # No new dependencies
  patterns:
    - CLI-overrides-env-overrides-default idiom (Python stdlib os.environ.get with try/except ValueError fallback)
    - Atomic per-task commits with --no-verify + push origin/main

key-files:
  created: []
  modified:
    - enrichment/rss_classify.py (env cap fallback inside _eligible_articles)
    - enrichment/orchestrate_daily.py (docstring + SQL WHERE clause: fetched_at → scanned_at)
    - tests/unit/test_rss_classify.py (4 new env-cap tests)
    - tests/unit/test_orchestrate_daily.py (assertion updated to scanned_at)
    - CLAUDE.md (env var table row for OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP)

decisions:
  - Env cap default 500 matches what cron operator expects (undersized safety net was 1000 by accident)
  - CLI --max-articles precedence preserved explicitly: CLI > env > default
  - Parse failures silent (ValueError → 500, never raises) — bad env value must not crash daily cron
  - Fold CLAUDE.md doc update into commit 1 (2 atomic commits total, cleaner than 3)
  - rss_classify.py line 137 a.fetched_at (rss_articles, legitimate schema) left untouched per plan scope

metrics:
  duration: ~15 min
  completed: 2026-05-03
  tasks: 2
  files_modified: 5
  tests_added: 4
  tests_green: 22/22 (10 rss_classify + 12 orchestrate_daily)
---

# Quick Task 260503-lq7: Wave 1 Post-E2E Hygiene — RSS Classify Env Cap + orchestrate_daily SQL Fix Summary

One-liner: Added `OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP` env var (default 500) to RSS classifier and fixed pre-production `a.fetched_at` → `a.scanned_at` SQL bug in `orchestrate_daily.step_6` before Day-2 cron fires 2026-05-05 06:00 ADT.

## Commits

| # | Hash | Subject |
|---|------|---------|
| 1 | `0fa9674` | fix(rss_classify): add OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP env cap (default 500) for pipeline safety |
| 2 | `07d2b11` | fix(orchestrate_daily): step_6 SQL uses a.scanned_at (articles schema), not a.fetched_at |

Both pushed to `origin/main`. `git log --oneline -4` confirms `07d2b11` is head.

## Task 1 — Fix 1 (LQ7-01): env cap in rss_classify._eligible_articles

### What shipped

`enrichment/rss_classify.py::_eligible_articles` now resolves `OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP` inside the function when `max_articles is None`. Idiom:

```python
if max_articles is None:
    try:
        max_articles = int(os.environ.get("OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP", "500"))
    except ValueError:
        max_articles = 500
```

Precedence: `--max-articles CLI` > env var > default 500. Parse failures silent.

The old `(*topics, len(topics), max_articles or 1000)` bind expression was replaced with `(*topics, len(topics), max_articles)` — after the fix `max_articles` is always a non-None int at bind time.

### Tests added (4)

- `test_env_cap_default_500_when_no_cli_flag` — `max_articles=None`, no env var, 3 seeded rows → all 3 classified (500 >> 3).
- `test_env_cap_override_applies` — env=2, 3 seeded rows → 2 classified. **This was the RED test that failed before the implementation change.**
- `test_env_cap_parse_failure_falls_back_to_500` — env='abc' must not raise; fallback 500 → all 3 classified.
- `test_cli_max_articles_wins_over_env` — CLI=1, env=2 → 1 classified (CLI precedence).

All 6 pre-existing rss_classify tests still green (unchanged behavior for the non-env-cap paths).

### CLAUDE.md doc row

Appended after `CDP_URL` row at line 156:

```
| `OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP` | No | RSS classifier daily-batch safety cap (default 500 articles). Applies only when `--max-articles` CLI flag is NOT passed; CLI value always wins. Non-int values silently fall back to 500. |
```

## Task 2 — Fix 2 (LQ7-02): orchestrate_daily step_6 SQL schema match

### What shipped

Two surgical edits in `enrichment/orchestrate_daily.py`:

- Line 133 (docstring): `date(fetched_at) = today` → `date(scanned_at) = today`
- Line 150 (SQL WHERE): `AND date(a.fetched_at) = date('now','localtime')` → `AND date(a.scanned_at) = date('now','localtime')`

### Why this was a pre-production bug

The `articles` table (WeChat KOL source) has a `scanned_at` column, not `fetched_at` (confirmed via `batch_scan_kol.py:89-96` schema). The original code would have thrown `OperationalError: no such column: a.fetched_at` on first real execution of the daily cron. No prior run had ever executed step_6 against a real DB — the bug was only caught because the unit test was asserting against the buggy SQL string literal. Day-2 cron fire 2026-05-05 06:00 ADT would have been the first real execution.

### Test assertion updated

`test_step_6_sql_does_not_touch_rss_tables` line 181 assertion flipped from `fetched_at` → `scanned_at`. This is not a regression — the test was encoding the buggy SQL; fixing production requires the test to encode the correct SQL.

All 12 orchestrate_daily tests green.

## Grep evidence

```text
$ grep -n fetched_at enrichment/orchestrate_daily.py
(zero matches — both line 133 docstring and line 150 SQL updated)

$ grep -n "a.scanned_at" enrichment/orchestrate_daily.py
150:                 AND date(a.scanned_at) = date('now','localtime')

$ grep -n "a.fetched_at" enrichment/rss_classify.py
137:        f"ORDER BY a.fetched_at DESC "
(1 match — legitimate rss_articles owner, untouched per plan scope)

$ grep -n OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP enrichment/rss_classify.py
127:            max_articles = int(os.environ.get("OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP", "500"))

$ grep -n OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP CLAUDE.md
156:| `OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP` | No | RSS classifier daily-batch safety cap (default 500 articles). Applies only when `--max-articles` CLI flag is NOT passed; CLI value always wins. Non-int values silently fall back to 500. |
```

## Test evidence

```text
$ venv/Scripts/python -m pytest tests/unit/test_rss_classify.py tests/unit/test_orchestrate_daily.py -v
...
============================= 22 passed in 2.97s ==============================
```

10 rss_classify (6 existing + 4 new) + 12 orchestrate_daily = 22 / 22 green.

## Deviations from Plan

None — plan executed exactly as written. The pre-scouted fact about the test assertion update at line 181 was honored (flipped `fetched_at` → `scanned_at` per plan's `<critical_pre_scouted_test_update>` block).

Markdown-lint warnings on CLAUDE.md (MD025, MD029, MD010, MD040) surfaced by PostToolUse hook were all pre-existing and unrelated to the single-row table insertion. Per Surgical Changes principle they were not touched.

## Impact — Day-2 cron safety

Before this plan, the Day-2 cron fire at 2026-05-05 06:00 ADT would have:

1. Hit step_6 with real DB — `OperationalError: no such column: a.fetched_at` — step fails
2. step_8 digest generation would have run on whatever step_7 produced (KOL+RSS ingest survived), but without step_6 enrichment the depth-2+ articles for today would have had no Zhihu context appended
3. Telegram alert from step_9 would have fired only if step_8 itself failed — step_6's failure is non-critical by design, so it'd have silently continued

With both fixes in, Day-2 cron fire is safe. The RSS classify env cap is also active: any quiet day still caps at 500 (the intended default) rather than falling back to the accidental 1000.

## Out-of-scope (explicitly NOT touched)

Per plan constraint — quick-task scope only:

- STATE.md Quick Tasks Completed row — orchestrator handles
- ROADMAP.md — out of scope for quick tasks
- VALIDATION.md phase-state — out of scope
- rss_classifications schema — unchanged
- Cron body / scripts/register_phase5_cron.sh — unchanged
- step_6 signature beyond the SQL field — unchanged
- rss_classify.py line 137 `a.fetched_at` on rss_articles — legitimate schema usage, untouched

## Self-Check: PASSED

**Files verified:**
- `enrichment/rss_classify.py` — FOUND (contains `OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP` at line 127; no `or 1000`)
- `enrichment/orchestrate_daily.py` — FOUND (zero `fetched_at`; `a.scanned_at` at line 150)
- `tests/unit/test_rss_classify.py` — FOUND (4 new env-cap tests at tail)
- `tests/unit/test_orchestrate_daily.py` — FOUND (line 181 asserts `scanned_at`)
- `CLAUDE.md` — FOUND (env var row at line 156)

**Commits verified:**
- `0fa9674` — FOUND on origin/main
- `07d2b11` — FOUND on origin/main (HEAD)

**Test gate:** 22/22 green (10 rss_classify + 12 orchestrate_daily).
