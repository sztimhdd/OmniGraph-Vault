---
phase: quick-260511-lmx
plan: 01
subsystem: ingest
tags: [batch-ingest, max-articles, cap, surgical-fix, mock-only-tests]
dependency_graph:
  requires: []
  provides:
    - "Strict hard-cap enforcement on --max-articles in ingest_from_db()"
  affects:
    - "batch_ingest_from_spider.ingest_from_db (per-iter cap check)"
tech_stack:
  added: []
  patterns:
    - "Anti-fabrication: pre-fix + post-fix log evidence cited with line numbers"
    - "Mock-only pytest with sqlite3 :memory:-equivalent tmp file + downstream stack patches"
key_files:
  created:
    - tests/unit/test_max_articles_hard_cap.py
    - .scratch/lmx-repro.py
  modified:
    - batch_ingest_from_spider.py
decisions:
  - "Charge in-flight queue against cap budget at enqueue (processed + len(layer2_queue) >= max_articles) — keeps the existing 'processed' counter, no new state added"
  - "Leave CAP CHECK 2 (post-drain at L1930) untouched as defensive belt-and-suspenders — surgical change rule"
  - "Test uses tmp DB file + DB_PATH patch (ingest_from_db opens its own connection); not :memory: which would require a refactor"
metrics:
  duration_min: 65
  completed: 2026-05-11
commit: 7629071
---

# Quick 260511-lmx: --max-articles strict hard cap fix

## One-liner

`ingest_from_db` per-iter cap check now charges the in-flight Layer 2 queue against the budget at enqueue time, eliminating the up-to-LAYER2_BATCH_SIZE-1-row leak past `--max-articles N` (was 5→14 in worst overnight smoke, now 5→5 deterministic).

## Investigation findings confirmed

Plan-claimed line numbers verified against worktree HEAD (`7306385` pre-fix):

| Plan claim | Actual location | Verified |
|---|---|---|
| `for i, ... in enumerate(candidate_rows, 1)` at L1772 | L1772 | ✅ |
| CAP CHECK 1 (per-iter) at L1776 | L1776 | ✅ |
| `layer2_queue.append(...)` at L1911 | L1911 | ✅ |
| `if len(layer2_queue) >= LAYER2_BATCH_SIZE: drain` at L1916 | L1916 | ✅ |
| CAP CHECK 2 (post-drain) at L1930 | L1930 | ✅ (untouched) |
| `await _drain_layer2_queue()` final at L1939 | L1939 | ✅ (untouched) |
| `LAYER2_BATCH_SIZE = 5` | `lib/article_filter.py:95` | ✅ |
| `processed` increments only inside `_drain_layer2_queue()` | L1758 confirmed | ✅ |

## Pre-fix smoke (anti-fabrication evidence)

Repro script: `.scratch/lmx-repro.py` (gitignored).

Command:
```bash
.venv/Scripts/python .scratch/lmx-repro.py
```

with `REPRO_N_CANDIDATES=6` (default), `REPRO_MAX_ARTICLES=2` (default).

Run with the temporary stderr line `[lmx-debug] iter=N processed=X queue_len=Y max=2` inserted at L1773 to instrument iteration state.

**Pre-fix log file**: `.scratch/maxcap-prefix-20260511T185332Z.log` (29 lines)

Key evidence lines:
- L6:  `[lmx-debug] iter=1 processed=0 queue_len=0 max=2`
- L8:  `[lmx-debug] iter=2 processed=0 queue_len=1 max=2`
- L10: `[lmx-debug] iter=3 processed=0 queue_len=2 max=2`
- L12: `[lmx-debug] iter=4 processed=0 queue_len=3 max=2`
- L14: `[lmx-debug] iter=5 processed=0 queue_len=4 max=2`
- L16: `[layer2] batch 0 n=5 ok=5 reject=0 null=0 wall_ms=0` ← drain bumps processed 0→5
- L22: `max-articles cap reached (2) — draining final layer2 queue and stopping.` ← CAP CHECK 2 fires AFTER 5 already committed
- L27: `[repro] ingestions by status: [('ok', 5)]`
- L28: `[repro] cap=2 ok=5 failed=0 skipped=0 ok+failed=5`
- L29: `[repro] LEAK DETECTED: ok+failed exceeds cap by 3`

**Leak magnitude**: cap=2 → 5 ok rows (3-row leak, matching the plan's predicted "up to LAYER2_BATCH_SIZE-1=4 extra"). The leak shape matches the plan's walk-through exactly.

## Fix applied

`batch_ingest_from_spider.py:1772-1786` (single hunk, +9/-5 effective lines, comment is most of the gain):

```diff
-            # JN6-02: stop AFTER successfully-processed rows hit the cap.
-            # Skips (no URL, checkpoint, classify, depth) don't count, so the
-            # cap limits real ingest work — correct semantics for rate limiting.
-            if max_articles is not None and processed >= max_articles:
+            # quick-260511-mxc: strict hard cap. Pre-fix this check was
+            # processed-only, so queued-but-not-yet-drained rows leaked past
+            # the cap (up to LAYER2_BATCH_SIZE-1 = 4 extra). Charging the
+            # in-flight queue against the budget at enqueue time makes
+            # --max-articles a true per-article hard cap on ok+failed
+            # (skipped statuses are excluded by their `continue` branches
+            # below). See quick 260511-lmx investigation_findings.
+            if max_articles is not None and (processed + len(layer2_queue)) >= max_articles:
                 logger.info(
-                    "max-articles cap reached (%d); stopping --from-db loop.",
-                    max_articles,
+                    "max-articles cap reached (processed=%d + queued=%d >= %d); stopping --from-db loop.",
+                    processed, len(layer2_queue), max_articles,
                 )
                 break
```

Untouched (per surgical-change rule):
- CAP CHECK 2 at L1930 (now redundant for the leak case but harmless as belt-and-suspenders)
- Final drain at L1939 (correct: flushes the in-flight queue after `break`)
- Scan-mode `run()` at L689 (different code path; user reports were all `--from-db`)
- All skip branches (no-URL, checkpoint, scrape-anomaly, graded probe — they `continue` BEFORE enqueue, correctly bypassing the cap)

## Post-fix smoke (anti-fabrication evidence)

Same repro script, same args, with the temporary stderr line removed and the fix applied.

**Post-fix log file**: `.scratch/maxcap-postfix-20260511T185437Z.log` (18 lines)

Key evidence lines:
- L6:  `[1/6] [kol-account-A] KOL article 100`
- L7:  `[2/6] [kol-account-A] KOL article 101`
- L8:  `max-articles cap reached (processed=0 + queued=2 >= 2); stopping --from-db loop.` ← per-iter check fires when queued=2 >= cap=2 BEFORE iter=3 enqueue
- L9:  `[layer2] batch 0 n=2 ok=2 reject=0 null=0 wall_ms=0` ← final drain flushes the 2-row partial queue
- L12: `Done — 2 candidates processed (of 6 total inputs)`
- L16: `[repro] ingestions by status: [('ok', 2)]`
- L17: `[repro] cap=2 ok=2 failed=0 skipped=0 ok+failed=2`
- L18: `[repro] cap respected`

**Diff vs pre-fix**: ok+failed dropped from 5 → 2 (exactly cap=2, as required). `not_started_articles=4` in metrics confirms 4 candidate rows untouched (rows 3-6 never enqueued).

## Pytest run (4/4 GREEN)

Pytest log file: `.scratch/maxcap-pytest-20260511T185651Z.log`

```
tests/unit/test_max_articles_hard_cap.py::test_cap_excludes_skipped_layer1_rejects PASSED [ 25%]
tests/unit/test_max_articles_hard_cap.py::test_cap_break_on_third_ok PASSED [ 50%]
tests/unit/test_max_articles_hard_cap.py::test_cap_with_mid_loop_failure_counts PASSED [ 75%]
tests/unit/test_max_articles_hard_cap.py::test_cap_pool_exhausted_before_reached PASSED [100%]

============================== 4 passed in 2.29s ==============================
```

Regression sweep on adjacent test files (same `batch_ingest_from_spider` import surface): 30/30 passed combined (24 pre-existing in `test_batch_ingest_topic_filter.py` + 2 in `test_batch_ingest_hash.py` + 4 new).

### Test mocking strategy

The `_patch_downstream` helper applies these per-test mocks:

| Target | Mock | Why |
|---|---|---|
| `bi.DB_PATH` | tmp file | `ingest_from_db` opens its own connection; cannot pass conn directly |
| `bi._load_hermes_env` | no-op | offline; no `~/.hermes/.env` dependency |
| `bi.get_deepseek_api_key` | `"dummy"` | Phase 5 cross-coupling defence |
| `bi.layer1_pre_filter` | per-row verdict mapping | drives candidate vs reject test branches |
| `bi.layer2_full_body_score` | per-row verdict mapping | drives ok/reject/None layer 2 outcomes |
| `bi.ingest_article` | `(success, wall, doc_confirmed)` tuples | drives ok/failed status mid-loop |
| `bi._drain_pending_vision_tasks` | no-op AsyncMock | finalize stage is a no-op offline |
| `bi.SLEEP_BETWEEN_ARTICLES` | `0` | keeps tests sub-second |
| `sys.modules['ingest_wechat']` | MagicMock with fake `get_rag` | avoids LightRAG init |
| `logging.basicConfig` | no-op | production line ~1607 calls `basicConfig(force=True)` after LightRAG init, which removes pytest's caplog handler — patch keeps caplog intact for cap-reached log assertions |

The seeded DB schema is the production subset (articles + rss_articles + accounts + rss_feeds + classifications + ingestions), with `layer1_*` / `layer2_*` columns pre-created so `persist_layer*_verdicts()` can `UPDATE` them.

## Commit + push

Single atomic commit:

```
7629071 fix(ingest-260511-mxc): --max-articles hard cap — count ok+failed only, exit cleanly when reached, eliminates unpredictable batch wall-clock
```

`git fetch origin main && git rebase origin/main`: "up to date" (no peer-quick collisions on L1776 — Quick A `260511-lmc` h09 race scope is `ingest_wechat.py`, Quick B `260511-lmw` DeepSeek timeout scope is `lib/llm_*`).

`git push origin HEAD:main`: fast-forward `7306385..7629071`.

`git log --oneline origin/main..HEAD` (post-push): empty (commit landed on origin/main).

`git diff` (post-fix vs origin/main pre-fix): 1 hunk in `batch_ingest_from_spider.py`, 9 lines added / 5 lines removed (4 of the additions are the new comment block); 1 new file `tests/unit/test_max_articles_hard_cap.py` (~470 lines including module docstring and helpers). No other production files touched.

## STATE.md row blurb

```
Completed quick 260511-lmx — `--max-articles` strict hard cap on ok+failed only; eliminates batch wall-clock leak (was 5→14, now 5→5)
```

## Self-Check: PASSED

Created files exist:
- `tests/unit/test_max_articles_hard_cap.py` — present, committed in `7629071`
- `.planning/quick/260511-lmx-fix-max-articles-cap-leak-strict-hard-ca/260511-lmx-SUMMARY.md` — this file
- `.scratch/maxcap-prefix-20260511T185332Z.log` — present (29 lines)
- `.scratch/maxcap-postfix-20260511T185437Z.log` — present (18 lines)
- `.scratch/maxcap-pytest-20260511T185651Z.log` — present (15 lines)

Commit pushed to origin/main:
- `7629071` — confirmed via `git push origin HEAD:main` fast-forward `7306385..7629071`
