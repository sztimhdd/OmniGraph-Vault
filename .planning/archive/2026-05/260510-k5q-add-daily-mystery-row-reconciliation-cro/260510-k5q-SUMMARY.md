---
phase: quick-260510-k5q
plan: 01
type: execute
status: complete
date_completed: 2026-05-10
commits:
  - 920a4d8b0938a07fd05301822a62d73746d625cd
  - 2f1f1067e300b8c9cb81613d8417305415422f80
files_created:
  - scripts/reconcile_ingestions.py
  - tests/unit/test_reconcile_ingestions.py
files_modified:
  - scripts/register_phase5_cron.sh
  - .planning/STATE.md
requirements_satisfied:
  - RCN-01
  - RCN-02
  - RCN-03
  - RCN-04
  - RCN-05
---

# Quick 260510-k5q — Daily Reconcile-Ingestions Canary

## TL;DR

Built the operational canary for commit `949e3f4` (h09 PROCESSED-gate hot-fix):
a daily 09:30 ADT cron `reconcile-ingestions` that scans `ingestions=ok` rows
and exits 1 if any wechat row's LightRAG `doc_status` is missing or
`!= 'processed'`. Without this canary, the gating fix is invisible in
production. RSS reconciliation deferred to ar-1.

Two atomic forward-only commits:

| # | SHA (short) | SHA (full) | Message |
|---|-------------|------------|---------|
| 1 | `920a4d8` | `920a4d8b0938a07fd05301822a62d73746d625cd` | `feat(ingest-260510-rcn): daily reconcile-ingestions cron — detect mystery rows where ingestions=ok lacks LightRAG status=processed` |
| 2 | `2f1f106` | `2f1f1067e300b8c9cb81613d8417305415422f80` | `docs(state): record 260510-k5q commit SHA in STATE.md` |

Slug `260510-rcn` per user instruction (mental shorthand); GSD ID `260510-k5q`
remains for STATE row + planning dir.

## 1. Commit SHAs

- Feature: `920a4d8b0938a07fd05301822a62d73746d625cd` (short `920a4d8`)
- SHA backfill: `2f1f1067e300b8c9cb81613d8417305415422f80` (short `2f1f106`)
- Verified via `git log --oneline -3` — both land on `main`.

## 2. Pytest Evidence (Task 1 — TDD)

**Phase 1 RED:** 8 ERRORS (`ModuleNotFoundError: No module named 'reconcile_ingestions'`)
captured at `.scratch/test-reconcile-260510-k5q-RED.log` — confirms tests written
before script (TDD discipline).

**Phase 2 GREEN:** `.scratch/test-reconcile-260510-k5q.log` final line:

```
============================== 8 passed in 0.95s ==============================
```

8 collected items = 6 logical test functions (Test 4 parametrized into 3 cases
per plan's `(0,0), (1,1), (5,1)` matrix). Test list:

| # | Function | Outcome |
|---|----------|---------|
| 1 | `test_zero_mystery_returns_exit_zero` | PASSED |
| 2 | `test_doc_status_missing_is_mystery` | PASSED |
| 3 | `test_doc_status_processing_is_mystery` | PASSED |
| 4a-c | `test_exit_codes_parametrized[{0-0,1-1,5-1}]` | PASSED (3) |
| 5 | `test_date_flag_filters_to_arbitrary_historical_date` | PASSED |
| 6 | `test_lookback_days_extends_window` | PASSED |

Mock-only — no live LightRAG, no live network. Each test uses `tmp_path` for
both the sqlite DB and the `kv_store_doc_status.json`. RSS-skip behavior
verified inline as part of Test 1 (the second seeded row has `source='rss'`
and is silently skipped — no JSON line, exit still 0).

## 3. Cron Idempotency Evidence (Task 2 — STEP 1, 3)

**Before** (`.scratch/before-grep-260510-k5q.txt`):

```
NOT FOUND (expected)
```

Zero pre-existing matches.

**After** (`.scratch/after-grep-260510-k5q.txt`, 2 lines):

```
117:add_job "reconcile-ingestions" \
119:  "cd ~/OmniGraph-Vault && source venv/bin/activate && python scripts/reconcile_ingestions.py 2>&1 | tee /tmp/reconcile-\$(date +%Y%m%d).log"
```

**Idempotency proof** (`.scratch/grep-count-260510-k5q.txt`):

Command: `grep -c '^add_job "reconcile-ingestions"' scripts/register_phase5_cron.sh`
Output: `1`

Re-running `bash scripts/register_phase5_cron.sh` after this change will print
`SKIP reconcile-ingestions (already registered)` — verified by inspecting the
existing `EXISTING="$(hermes cron list ...)"` snapshot logic at lines 25-43.

The `\$(date ...)` escape defers expansion to cron-fire time on Hermes (so
`/tmp/reconcile-YYYYMMDD.log` is per-day, not per-register).

## 4. Smoke Evidence (Task 2 — STEP 4)

`.scratch/smoke-reconcile-260510-k5q.log` (68 lines) contains TWO smoke runs:

**Run A** — empty-window healthy day (`--date 2026-05-10` against
`.dev-runtime/data/kol_scan.db`):

```
2026-05-10: 0 ok rows / 0 matched / 0 mystery
EXIT=0
```

**Run B** — broader window with real mystery rows
(`--date 2026-05-06 --lookback-days 5`):

```
{"art_id": 348, "url": "...", "doc_id": "wechat_b5b1febc8b", "actual_status": "missing", "ingested_at": "2026-05-02 02:35:10"}
... [62 more JSON lines, one per mystery row] ...
2026-05-02..2026-05-06: 66 ok rows / 2 matched / 64 mystery
EXIT=1
```

Both EXIT codes (0 and 1) exercised against real local data.
Zero stack traces, zero argparse errors. JSON-line shape matches plan spec
exactly: `{"art_id", "url", "doc_id", "actual_status", "ingested_at"}`.

## 5. Idempotency Proof Citation

```
$ grep -c '^add_job "reconcile-ingestions"' scripts/register_phase5_cron.sh
1
```

Output captured at `.scratch/grep-count-260510-k5q.txt` line 1. Cited verbatim.

## 6. Operator Follow-up Note

On Hermes, after the next pull:

```bash
ssh <hermes> "cd ~/OmniGraph-Vault && git pull --ff-only && bash scripts/register_phase5_cron.sh"
```

First run prints `ADD reconcile-ingestions @ 30 9 * * *`. Subsequent runs print
`SKIP reconcile-ingestions (already registered)` — driven by the existing
`hermes cron list` snapshot guard at `register_phase5_cron.sh:25-43`.

The cron prompt is a single line natural-language string per the
`add_job` convention; Hermes resolves the literal `python scripts/...` shell
command at fire time.

## 7. Known-Canary-Behavior Note

Tomorrow's 2026-05-11 09:30 ADT cron will fire for the first time. If it
exits 1 with one or more JSON mystery lines, **that is the canary FIRING**
(working as designed) — NOT a bug in the canary itself.

The next response in that case is to:

1. Read `/tmp/reconcile-YYYYMMDD.log` on Hermes (the cron's tee target)
2. Investigate why the h09 PROCESSED-gate hot-fix (`949e3f4`) did not gate
   the offending rows — i.e. why `ingest_article` returned without raising
   despite `kv_store_doc_status` lacking `status='processed'`
3. **Do NOT "fix" the canary** by lowering its exit code or relaxing its
   gate. The canary is the operational ground truth of whether the
   PROCESSED-gate is holding.

Possible root causes if canary fires:

- `_verify_doc_processed_or_raise` retry budget exceeded under real Vertex
  pipeline (see contract test at `tests/unit/test_ainsert_persistence_contract.py`)
- Cancelled vision-worker sub-doc race (parallel quick `260510-gqu`
  investigation: PENDING/PROCESSING never reach FAILED at
  `lightrag.py:2053-2074`)
- Outer `INSERT OR REPLACE INTO ingestions(... status='ok')` clobbering an
  inner `status='failed'` (would re-open the original h09 hole)

## Deviations from Plan

### Rule 1 (Bug fix during execution): production schema vs plan `<interfaces>`

**Found during:** Task 2 STEP 4 (smoke run).

The plan's `<interfaces>` block specified `ingestions.url` as a column on the
`ingestions` table:

```sql
SELECT id, article_id, url, source, ingested_at FROM ingestions WHERE ...
```

**Actual production schema** (mig 008, verified via
`.dev-runtime/data/kol_scan.db` `sqlite_master` SELECT):

```sql
CREATE TABLE "ingestions" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'wechat' CHECK (source IN ('wechat', 'rss')),
    status TEXT NOT NULL CHECK (status IN (...)),
    ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
    enrichment_id TEXT, skip_reason_version INTEGER NOT NULL DEFAULT 0,
    UNIQUE (article_id, source)
)
```

There is **no `url` column** on `ingestions`. URL lives on `articles.url`.
Pattern verified in `run_uat_ingest.py:65`:

```python
SELECT url FROM articles WHERE id IN (SELECT article_id FROM ingestions WHERE status='ok')
```

**Fix:** changed `_query_ok_rows` SQL to `LEFT JOIN articles ON a.id = i.article_id`
and updated the test helper `_seed_ingestions_db` to seed both `articles` and
`ingestions` tables. Tests still GREEN (8 passed) post-fix; smoke against real
`.dev-runtime` DB exercises the JOIN path correctly (see Run B above —
URLs are real WeChat URLs read from `articles.url`).

This is a Rule 1 (auto-fix bug) deviation — without the JOIN the script
would `OperationalError: no such column: url` on every cron fire, defeating
the entire canary purpose.

### No other deviations

- HARD scope honored: ZERO touches to `ingest_wechat.py`,
  `batch_ingest_from_spider.py`, `cron_daily_ingest.sh`, RSS scripts.
- Cron entry escape `\$(date ...)` matches plan spec verbatim — no other
  prompt strings in `register_phase5_cron.sh` use shell substitution, so no
  pre-existing convention to mirror; chose plan-spec form.
- No SSH to Hermes; no `git push` (operator runs that manually).

## Anti-Fabrication Checklist

- [x] No "should work" / "expected to" / "approximately" / "looks like"
      language anywhere in this SUMMARY.
- [x] Test count = exact `8 passed` from
      `.scratch/test-reconcile-260510-k5q.log` final line.
- [x] Cron entry count claim cites `grep -c` output `1` from
      `.scratch/grep-count-260510-k5q.txt`.
- [x] Smoke result claim cites EXIT lines from
      `.scratch/smoke-reconcile-260510-k5q.log` (EXIT=0 + EXIT=1, both
      exercised).
- [x] Commit slug in commit message is `260510-rcn` (user-dictated),
      verified via `git log --oneline -3 | grep "feat(ingest-260510-rcn)"`.
- [x] Every factual numeric claim cites a real `.scratch/` file path.

## Self-Check: PASSED

- `scripts/reconcile_ingestions.py` — 162 LOC, exists and importable
- `tests/unit/test_reconcile_ingestions.py` — 392 LOC, 8 passed (6 functions)
- `scripts/register_phase5_cron.sh` — line 117 `add_job "reconcile-ingestions"`
  (exactly 1 occurrence per `grep -c`)
- `.planning/STATE.md` — 260510-k5q row at end of "Quick Tasks Completed" with
  commit SHA `920a4d8`
- All 5 evidence files present in `.scratch/` (gitignored, never committed)
- Both commits land on `main`: `920a4d8` (feature) → `2f1f106` (SHA backfill)
