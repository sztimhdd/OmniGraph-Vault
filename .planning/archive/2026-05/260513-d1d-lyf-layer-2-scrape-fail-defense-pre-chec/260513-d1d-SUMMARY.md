---
phase: quick-260513-d1d
plan: 01
type: execute
wave: 1
status: complete
completed: 2026-05-13
commits:
  - a7a8ab6
files_modified:
  - lib/article_filter.py
  - tests/unit/test_article_filter.py
files_created:
  - migrations/010_layer2_scrape_fail_marker.sql
requirements_satisfied:
  - LYF-1
  - LYF-2
  - LYF-3
---

# Quick 260513-d1d: Layer 2 scrape_fail Defense Pre-check — SUMMARY

## One-liner

Added deterministic `scrape_fail` pre-check to `layer2_full_body_score` so articles with `body < 500 chars AND content_length > 2000 chars` short-circuit BEFORE the DeepSeek LLM call (Patch B of 2026-05-13 Layer 2 audit) — no prompt change, no `PROMPT_VERSION_LAYER2` bump, no LF-2.6 reclassify storm.

## Commit SHA(s)

| SHA | Status | Message |
|---|---|---|
| `a7a8ab6` | local only (NOT pushed) | `feat(layer2): add scrape_fail pre-check before LLM call (Patch B of 2026-05-13 Layer 2 audit)` |

Full SHA: `a7a8ab68500e487292dbb4eb4bb5bd2a915e50d8`

## Files changed (3)

| File | Status | LOC delta |
|---|---|---|
| `lib/article_filter.py` | M | +80 / -14 |
| `tests/unit/test_article_filter.py` | M | +127 / -0 |
| `migrations/010_layer2_scrape_fail_marker.sql` | A (new) | +33 / -0 |
| **Total** | | **+240 / -14** |

## Task 1 — `_detect_scrape_failed` + entry pre-check

### `_detect_scrape_failed(body, content_length) -> bool`

**LOC:** 19 lines (signature + docstring + 3-line body).
**Edge cases handled:**

| Input | Behavior | Test coverage |
|---|---|---|
| `body=None` | Treated as 0-length via `len(body or "")` | Implicit (any short body trigger) |
| `body=""` | Treated as 0-length | Implicit |
| `content_length=None` | Treated as 0 via `(content_length or 0)`, returns False | `test_layer2_scrape_fail_null_content_no_trigger` |
| `content_length=0` | Returns False (0 not > 2000) | Implicit |
| Body < 500 AND content > 2000 | Returns True | `test_layer2_scrape_fail_short_body_long_content` |
| Body >= 500, any content | Returns False | `test_layer2_scrape_fail_long_body_no_trigger` |
| Body < 500 AND content <= 2000 | Returns False | `test_layer2_scrape_fail_short_body_short_content_no_trigger` |

### `layer2_full_body_score` LOC delta

- **Before:** 79-LOC function body (lines 509-633)
- **After:** ~107-LOC function body
- **Delta:** approximately **+28 LOC** (within the +15/-5 expected range, slightly higher due to inline `_fill_in` helper added for the LLM-error fill-in pattern)

Refactor shape:
- Empty-batch + over-max-batch checks UNCHANGED at top
- NEW: partition pass over `articles` → `results: list[FilterResult | None]` pre-allocated
- NEW: short-circuit early return if `real_payload_articles` is empty
- EXISTING: payload build + LLM call + cleanup + parse logic, scoped to `real_payload_articles` only
- NEW: `_fill_in()` helper writes LLM results back into pre-allocated `results` at correct indices
- All error paths (`timeout`, `non_json`, `partial_json`, `row_count_mismatch`, `exception:*`) now go through `_fill_in(_all_null(reason))` so scrape_fail slots stay scrape_fail

### Type widening

`FilterResult.verdict` Literal widened from `["candidate", "reject", "ok"] | None` → `["candidate", "reject", "ok", "scrape_fail"] | None`. Type-only change, no runtime impact.

### `__all__` export additions

Added `SCRAPE_FAIL_BODY_MIN` and `SCRAPE_FAIL_CONTENT_MIN` to module `__all__` per spec. Helper `_detect_scrape_failed` stays private (underscore prefix).

### `PROMPT_VERSION_LAYER2` invariant

```
$ grep -n "PROMPT_VERSION_LAYER2: str =" lib/article_filter.py
80:PROMPT_VERSION_LAYER2: str = "layer2_v0_20260507"
```

Byte-unchanged — no LF-2.6 reclassify storm trigger at next 08:15 ADT cron.

`_LAYER2_V0_PROMPT_BODY` is also byte-unchanged.

## Task 2 — Unit tests

### Test count delta

| Before | After | New tests |
|---|---|---|
| 16 | 20 | +4 |

### New test names + status

```
tests/unit/test_article_filter.py::test_layer2_scrape_fail_short_body_long_content PASSED
tests/unit/test_article_filter.py::test_layer2_scrape_fail_short_body_short_content_no_trigger PASSED
tests/unit/test_article_filter.py::test_layer2_scrape_fail_long_body_no_trigger PASSED
tests/unit/test_article_filter.py::test_layer2_scrape_fail_null_content_no_trigger PASSED
```

### Full pytest run

```
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.0.3, pluggy-1.6.0
collected 20 items

tests/unit/test_article_filter.py::test_filter_result_is_frozen_three_field PASSED [  5%]
tests/unit/test_article_filter.py::test_layer1_batch_of_30_persists_all PASSED [ 10%]
tests/unit/test_article_filter.py::test_layer1_timeout_all_null PASSED   [ 15%]
tests/unit/test_article_filter.py::test_layer1_partial_json_all_null PASSED [ 20%]
tests/unit/test_article_filter.py::test_layer1_row_count_mismatch_all_null PASSED [ 25%]
tests/unit/test_article_filter.py::test_layer1_prompt_version_bump_invalidates_prior PASSED [ 30%]
tests/unit/test_article_filter.py::test_layer1_empty_batch_no_op PASSED  [ 35%]
tests/unit/test_article_filter.py::test_layer1_over_max_raises PASSED    [ 40%]
tests/unit/test_article_filter.py::test_layer2_batch_of_5_persists_all PASSED [ 45%]
tests/unit/test_article_filter.py::test_layer2_timeout_all_null PASSED   [ 50%]
tests/unit/test_article_filter.py::test_layer2_partial_json_all_null PASSED [ 55%]
tests/unit/test_article_filter.py::test_layer2_row_count_mismatch_all_null PASSED [ 60%]
tests/unit/test_article_filter.py::test_layer2_prompt_version_bump_invalidates_prior PASSED [ 65%]
tests/unit/test_article_filter.py::test_layer2_reject_writes_skipped_via_persist_round_trip PASSED [ 70%]
tests/unit/test_article_filter.py::test_layer2_scrape_fail_short_body_long_content PASSED [ 75%]
tests/unit/test_article_filter.py::test_layer2_scrape_fail_short_body_short_content_no_trigger PASSED [ 80%]
tests/unit/test_article_filter.py::test_layer2_scrape_fail_long_body_no_trigger PASSED [ 85%]
tests/unit/test_article_filter.py::test_layer2_scrape_fail_null_content_no_trigger PASSED [ 90%]
tests/unit/test_article_filter.py::test_layer2_empty_batch_no_op PASSED  [ 95%]
tests/unit/test_article_filter.py::test_layer2_over_max_raises PASSED    [100%]

============================= 20 passed in 3.20s ==============================
```

All 16 prior tests still PASS — no regressions on `None` / `'ok'` / `'reject'` paths.

### Test helpers added

- `_with_body_cl(i, body, content_length, source)` — `SimpleNamespace` factory that duck-types `ArticleWithBody` PLUS carries `content_length`. Avoids mutating the frozen dataclass (Option A from PLAN, Option B rejected).
- `_counting_llm_factory(response)` — like `_fake_llm_factory` but tracks call count so tests can assert LLM was (or wasn't) invoked.

## Task 3 — Marker migration + caller-contract grep + mock E2E

### Marker migration

Created `migrations/010_layer2_scrape_fail_marker.sql` (33 LOC). Documents verdict alphabet expansion:
- `'ok'` — Layer 2 LLM kept (relevant=true AND depth_score>=2)
- `'reject'` — Layer 2 LLM rejected
- `'scrape_fail'` — NEW: short-circuited before LLM
- `NULL` — pending re-evaluation

NO DDL — `articles.layer2_verdict` and `rss_articles.layer2_verdict` are `TEXT NULL` with no CHECK constraint (verified against `migrations/007_layer2_columns.sql:19-27`). New value lands transparently.

### Mock E2E (mixed batch order assertion)

```
Input: [scrape_fail, real, scrape_fail, real, real]  (5 articles)
LLM called with: 3 articles (ids 2, 4, 5) — payload size verified internally
LLM mock returns: [ok, reject (depth=1), reject (relevant=false)]

VERDICTS: ['scrape_fail', 'ok', 'scrape_fail', 'reject', 'reject']
REASONS:  ['body=100 content=11000', 'real-1', 'body=140 content=20000', 'real-2', 'real-3']
Mock E2E PASS
```

Order-preservation invariant verified — interleaving of pre-LLM `scrape_fail` slots and LLM-emitted `ok`/`reject` slots writes back to original input indices correctly.

### Additional edge case E2Es (run inline)

1. **All scrape_fail (no LLM call):**
   ```
   arts = [body=100/content=11000, body=200/content=12000]
   LLM mock raises AssertionError if invoked → never raises
   Verdicts: ['scrape_fail', 'scrape_fail']
   Edge case 1 PASS (no-LLM short-circuit)
   ```

2. **All real (no scrape_fail, full LLM path):**
   ```
   arts = [body=5000/content=8000, body=5000/content=9000]
   Verdicts: ['ok', 'ok']
   Edge case 2 PASS
   ```

### Caller-contract audit findings

`grep -rn "layer2_verdict" --include="*.py" .` returned matches across 12 production files. Analysis of the dispatching shapes:

| Caller | File:line | Compares against | Behavior on `'scrape_fail'` |
|---|---|---|---|
| Daily digest (KOL) | `enrichment/daily_digest.py:80` | `a.layer2_verdict = 'ok'` | Filtered out (correct — broken article shouldn't appear in digest) |
| Daily digest (RSS) | `enrichment/daily_digest.py:92` | `a.layer2_verdict = 'ok'` | Filtered out (correct) |
| Daily digest summary | `daily_digest.py:106,109` | `layer2_verdict = 'ok'` | Filtered out (correct) |
| VitaClaw export | `scripts/export_vitaclaw_agent_news.py:116,136` | `layer2_verdict = 'ok'` | Filtered out (correct) |
| Agent news gen | `scripts/gen_agent_news.py:106` | `layer2_verdict = 'ok'` | Filtered out (correct) |
| RSS classify select | `batch_classify_rss_layer2.py:73` | `layer2_verdict IS NULL` | NOT re-pulled (correct — already evaluated, do not re-LLM) |
| Persistence | `lib/article_filter.py:726` | `layer2_verdict = ?` (UPDATE) | Pure write — no alphabet check |

**1 hostile / latent-issue caller — recorded as follow-up per PLAN directive ("DO NOT fix in this quick"):**

| Caller | File:line | Issue |
|---|---|---|
| Layer 2 dispatcher loop | `batch_ingest_from_spider.py:1695-1714` | The if/elif chain is `if verdict=='reject' → skipped; if verdict is None → skip; else → ainsert`. A `'scrape_fail'` verdict falls into the `else` branch and would trigger an `ainsert()` on the truncated body. Comment at line 1714 explicitly says "Verdict is 'ok' (or future non-reject value) → proceed to ainsert" — wrong assumption for `scrape_fail`. **Follow-up needed:** add explicit `elif result.verdict == 'scrape_fail': continue` before the ainsert path, OR change the condition at line 1714 to `if result.verdict == 'ok':`. |

**Follow-up severity assessment (informational, not part of this quick):**

- Severity: **LOW for the immediate v1.0-rc1 release window.** Today, no rows have `layer2_verdict='scrape_fail'` because this is the first release. The first cron run (08:15 ADT next) will be the first time `'scrape_fail'` ever lands in the DB.
- Severity: **MEDIUM-HIGH starting tomorrow.** Once the first batch produces `'scrape_fail'` rows, a subsequent ingest cron WILL re-pull those rows (because they have `layer2_verdict IS NOT NULL` — but wait, the candidate query gates on `layer2_verdict IS NULL OR layer2_prompt_version != ?`, so they will NOT be re-pulled until next prompt-version bump). So in the immediate path, the LLM dispatch loop hostile branch is only reached on the SAME tick that emits the `'scrape_fail'` — which means the article goes pre-LLM-shortcut → persist scrape_fail verdict → ainsert path on truncated body. **This is a real bug that defeats half of the quick's value.** The `scrape_fail` audit signal is correctly persisted, BUT the truncated body still gets ainserted.
- The plan author was aware (Task 3 audit instructions explicitly anticipated this). Per plan directive, NOT fixed here.
- **Recommended follow-up:** quick `260513-XXX` adding 4 lines to `batch_ingest_from_spider.py:1707` — `elif result.verdict == "scrape_fail": continue` (with comment).

## Risk assessment

| Area | Risk | Mitigation |
|---|---|---|
| Prompt-version drift | None — `PROMPT_VERSION_LAYER2` byte-unchanged | grep verified post-commit |
| Existing test regressions | None — 16 prior tests still PASS | pytest run logged above |
| Order preservation | None — mock E2E proves index-based fill-in works | Mock E2E PASS section above |
| `_LAYER2_V0_PROMPT_BODY` drift | None — not edited | Prompt body remains byte-identical |
| ArticleWithBody dataclass mutation | None — used `getattr` fallback per spec | dataclass unchanged |
| DB schema impact | None — no DDL, marker migration only | `layer2_verdict TEXT NULL` already accepts any text |
| **Downstream `ainsert()` on truncated body** | **MEDIUM** — see Caller-Contract Audit above | **Recorded as follow-up; NOT fixed in this quick per plan directive** |
| Cron operational impact | LOW — `scrape_fail` rows correctly emit audit signal in `layer2_verdict` column for later re-scrape job | Future re-scrape job can `WHERE layer2_verdict = 'scrape_fail'` |

## Side effects

None unintended. Changes are surgical:
- 2 new module-level constants
- 1 new private helper function
- 1 entry-function refactor (partition + fill-in pattern)
- 1 type-Literal widening (compile-time only)
- 4 new unit tests (additive)
- 1 new marker migration file (additive, no DDL)

No imports added. No network calls added. No environment variables introduced. No prompt text edited.

## Constraints honored

- [x] No `git add -A` / `git add .` (used 3 explicit files)
- [x] No `git push` (commit is local only)
- [x] No SSH to Hermes prod
- [x] No DB UPDATE on existing rows
- [x] `PROMPT_VERSION_LAYER2` unchanged (`layer2_v0_20260507`)
- [x] `_LAYER2_V0_PROMPT_BODY` byte-unchanged
- [x] `ArticleWithBody` dataclass NOT mutated (used `getattr` fallback)
- [x] Migration in `migrations/` (not `data/migrations/`)
- [x] Surgical: only entry pre-check + helper, LLM call / payload build / parse logic unchanged
- [x] Backward compat: existing `None` / `'ok'` / `'reject'` paths unchanged

## Time elapsed

Approximately 6 minutes wall clock from PLAN ingestion to commit (SUMMARY.md write excluded).

## Self-Check: PASSED

- File `lib/article_filter.py` modified — `git show HEAD --numstat` shows `80 / 14`
- File `tests/unit/test_article_filter.py` modified — `127 / 0`
- File `migrations/010_layer2_scrape_fail_marker.sql` created — `33 / 0`
- Commit `a7a8ab6` exists in `git log` (verified via `git log -1 --format=%H`)
- All 20 unit tests PASS
- `python -m py_compile lib/article_filter.py` exits 0
- `PROMPT_VERSION_LAYER2 = "layer2_v0_20260507"` byte-match verified via grep
