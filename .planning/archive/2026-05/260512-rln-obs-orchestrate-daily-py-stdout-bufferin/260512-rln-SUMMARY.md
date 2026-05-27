---
phase: quick-260512-rln
plan: 01
title: "drop capture_output in orchestrate _run + log Pattern A budget activation"
commit: fa5499b9ca40ae39679fbf8f75260ded6d313ae7
files_modified:
  - enrichment/orchestrate_daily.py
  - lib/lightrag_queue_probe.py
  - tests/unit/test_lightrag_queue_probe.py
requirements_completed:
  - OBS-RLN-01
  - OBS-RLN-02
  - OBS-RLN-03
test_count_pre: 6
test_count_post: 7
test_status: 7/7 PASS
---

# Quick 260512-rln — Summary

## One-liner

Drop `capture_output=True` in `orchestrate_daily._run()` so child sub-step logs stream to tee, and add 1 `logger.info` in `compute_dynamic_budget()` so gqu Pattern A activation is grep-able in tomorrow 09:00 ADT cron output.

## Commit

```
commit fa5499b9ca40ae39679fbf8f75260ded6d313ae7
Author: Hai Hu <huhai.orion@gmail.com>
Date:   Tue May 12 19:56:53 2026 -0300

    chore(observability): drop capture_output in orchestrate _run + log Pattern A budget activation

 enrichment/orchestrate_daily.py         | 16 ++++++++--------
 lib/lightrag_queue_probe.py             |  7 ++++++-
 tests/unit/test_lightrag_queue_probe.py | 20 ++++++++++++++++++++
 3 files changed, 34 insertions(+), 9 deletions(-)
```

## LOC delta per file

| File | Insertions | Deletions | Net |
| ---- | ---------- | --------- | --- |
| `enrichment/orchestrate_daily.py` | 8 | 8 | 0 (replaced `_run` body, added 5-line NOTE comment, simplified return strings) |
| `lib/lightrag_queue_probe.py` | 6 | 1 | +5 (extracted `effective` local + 1 multi-line `logger.info`) |
| `tests/unit/test_lightrag_queue_probe.py` | 20 | 0 | +20 (1 new caplog-based test) |
| **Total** | **34** | **9** | **+25** |

## Verification gates

### 1. Compile gate

```
$ venv/Scripts/python -m py_compile enrichment/orchestrate_daily.py lib/lightrag_queue_probe.py
PY_COMPILE_OK
```

Exit 0. Both modules syntactically sane post-edit.

### 2. Test gate (target: 7 PASS)

```
$ venv/Scripts/python -m pytest tests/unit/test_lightrag_queue_probe.py -v
============================= test session starts =============================
collected 7 items

tests/unit/test_lightrag_queue_probe.py::test_empty_queue_returns_base_budget PASSED [ 14%]
tests/unit/test_lightrag_queue_probe.py::test_busy_queue_scales_linearly PASSED [ 28%]
tests/unit/test_lightrag_queue_probe.py::test_huge_queue_hits_cap PASSED [ 42%]
tests/unit/test_lightrag_queue_probe.py::test_file_missing_returns_zero PASSED [ 57%]
tests/unit/test_lightrag_queue_probe.py::test_corrupt_json_returns_zero PASSED [ 71%]
tests/unit/test_lightrag_queue_probe.py::test_fixture_busy_has_real_processing_docs PASSED [ 85%]
tests/unit/test_lightrag_queue_probe.py::test_compute_dynamic_budget_emits_pattern_a_log_line PASSED [100%]

============================== 7 passed in 1.85s ==============================
```

Pre-quick: 6 tests. Post-quick: 7 tests. **6 -> 7, all PASS.**

RED→GREEN evidence: pre-implementation run of the new test alone failed at
`AssertionError: expected 1 INFO record, got 0` (logger.info did not exist
yet). Post-implementation run shows `7 passed in 1.85s`.

### 3. Caller-contract gate (no caller parses StepResult.summary)

`enrichment/` `.summary` references (only relevant matches; SQL `a.summary`
column hits in `daily_digest.py:84` are unrelated to the dataclass):

```
enrichment/orchestrate_daily.py:209:        f"dual-source: {kol_r.summary[:300]}",     # display embedding
enrichment/orchestrate_daily.py:232:        f"Phase 5 digest failed: {step_8_result.summary[:300]}"  # Telegram alert text
enrichment/orchestrate_daily.py:236:        f"digest failed; alert sent: {step_8_result.summary[:200]}",  # display
enrichment/orchestrate_daily.py:315:            r.summary[:200],                         # logger.info display
enrichment/orchestrate_daily.py:320:                _telegram_alert(f"CRITICAL: step {name} failed: {r.summary}")  # alert text
```

`tests/` `.summary` references:

- `tests/unit/test_orchestrate_daily.py` — uses `StepResult(True, "ok")` etc.
  in fakes/patches; never asserts on `_run`'s actual return string content.
  Already passes "ok" in fakes, which is the new success summary value.
- `tests/unit/test_batch_ingest_topic_filter.py` — references `r.summary`
  as a SQL column from `rss_articles` table; unrelated to the
  `StepResult.summary` dataclass field.

**Conclusion: no caller does string parsing on `StepResult.summary` content
(no `.split(...)`, `.startswith(...)`, regex match, etc.). All 5 reference
sites are display-only (slice + log/embed in alert message). The summary
content shift from "first 500 chars stdout" to literal `"ok"` (and from
"exit=N stderr=..." to literal `"exit=N"`) is back-compat-safe.**

### 4. Back-compat gate (dry-run path preserved)

Inspecting post-edit `_run` body confirms:

- Dry-run branch: `return StepResult(True, f"dry: {' '.join(cmd)}")` —
  unchanged.
- TimeoutExpired: `return StepResult(False, "timeout", critical=critical)`
  — unchanged.
- Generic Exception: `return StepResult(False, f"exception: {ex}",
  critical=critical)` — unchanged.

Only the success-path summary content (and failure-path summary's stderr
suffix) changed; per gate 3 above, no caller cares about that content
beyond display.

### 5. Sanity: `tests/unit/test_orchestrate_daily.py` still passes

```
$ venv/Scripts/python -m pytest tests/unit/test_orchestrate_daily.py -v
============================= 14 passed in 0.23s ==============================
```

All 14 orchestrate_daily tests still pass. They patch `_run` directly with
`patch.object(od, "_run", ...)`, so my body change is invisible to them.

### 6. Stage hygiene gate

```
$ git log -1 --name-only
commit fa5499b9ca40ae39679fbf8f75260ded6d313ae7
    chore(observability): drop capture_output in orchestrate _run + log Pattern A budget activation

enrichment/orchestrate_daily.py
lib/lightrag_queue_probe.py
tests/unit/test_lightrag_queue_probe.py
```

Exactly 3 files in the commit. Used explicit `git add <3 files>`, never
`git add -A` or `git add .` (per CLAUDE.md 2026-05-11 lmc/lmx
parallel-quick staging-race protection).

### 7. No-push / no-SSH / no-prod-mutation gate

- **No `git push` executed.** Commit `fa5499b` is local on `main`; user
  decides push timing.
- **No SSH to Hermes executed.** All work was local file edits +
  local pytest + local git.
- **No prod state mutated.** No DB write, no env file change, no cron
  manipulation, no Hermes deploy.

## Risk note — tomorrow 09:00 ADT cron output volume

Dropping `capture_output=True` means child sub-step stdout (e.g.
`batch_ingest_from_spider.py`'s per-article INFO logs, `rss_fetch.py`
batch summaries, `batch_classify_kol.py` per-topic loops, `daily_digest.py`
digest assembly) streams directly to the orchestrate process's stdout
instead of being collected into `r.stdout` and discarded after a 500-char
slice.

**Expected effect on tomorrow's 09:00 ADT cron log file size**: roughly
**tens of KB → several MB**, depending on candidate pool size and ingest
volume. This is the desired outcome — operators get full sub-step
visibility — and IO bandwidth is fine on the Hermes WSL2 host. No log
rotation policy changes are required at this scale.

If this proves too verbose in practice (e.g. cron log file rotation
strain, scrolling time in `tail -f`), the follow-up is a separate quick
that wraps each sub-step's command in `python -u | tee >(grep -E
'^[A-Z]+:')` style filtering — but only ship that if the volume actually
becomes a problem. Per CLAUDE.md "Simplicity First": don't pre-optimize.

## Validation site

**Next 09:00 ADT daily-ingest cron** is the live validation site for both
fixes:

1. **OBS-RLN-01 evidence**: cron log shows full sub-step stdout streamed
   in real time (orchestrate `RUN: ...` line followed immediately by the
   child's own log lines, not after a multi-minute pause).

2. **OBS-RLN-02 evidence**: cron log can be grep'd for the marker:

   ```bash
   grep "gqu Pattern A" ~/.hermes/cron-logs/daily-ingest-*.log
   ```

   Expected output: 1 line per article ingested, e.g.
   `gqu Pattern A: queue_depth=15 effective_budget_s=900 base=300 cap=1800`.

If both signals appear in tomorrow's cron log, the quick is operationally
validated. If neither appears (e.g. orchestrate didn't fire, or the
`compute_dynamic_budget` code path wasn't exercised), file a follow-up
quick to investigate — neither fix introduces a new failure mode, only
new visibility.

## Out-of-scope items confirmed NOT done

- No Popen / streaming refactor of `_run`.
- No change to `SUBPROCESS_TIMEOUT_SECONDS` or new env override.
- No touch of `read_queue_depth()`.
- No `OMNIGRAPH_PER_DOC_AVG_S` env override added.
- No metrics / dashboard scaffolding.
- No `ingest_wechat.py` edits.
- No `git push`, no SSH to Hermes, no prod mutation.
- No `git add -A`, no `git add .`, no amend, no soft-reset.
- No new field on `StepResult`.
- No other `tests/unit/*.py` file touched.

## Self-Check: PASSED

- `enrichment/orchestrate_daily.py` exists and `_run` body matches the
  new shape (no `capture_output`, no `text`, env injects
  `PYTHONUNBUFFERED=1`).
- `lib/lightrag_queue_probe.py` exists and `compute_dynamic_budget`
  emits the `gqu Pattern A` `logger.info` before return.
- `tests/unit/test_lightrag_queue_probe.py` exists with 7 test
  functions, all PASS.
- Commit `fa5499b9ca40ae39679fbf8f75260ded6d313ae7` exists in
  `git log` with exactly the 3 listed files.
