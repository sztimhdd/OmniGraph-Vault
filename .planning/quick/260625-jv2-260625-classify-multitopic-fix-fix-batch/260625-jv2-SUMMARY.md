---
phase: 260625-jv2
plan: 01
subsystem: batch_classify_kol
tags: [argparse, multi-topic, regression, cli, unit-test]
dependency_graph:
  requires: []
  provides: [repeatable --topic flag, per-topic run() loop, behavior-anchor test]
  affects: [batch_classify_kol.py, tests/unit/test_classify_multitopic_argparse.py]
tech_stack:
  added: []
  patterns: [action=append argparse, MagicMock DB_PATH patch, os.environ.setdefault import-coupling defuse]
key_files:
  modified:
    - batch_classify_kol.py
  created:
    - tests/unit/test_classify_multitopic_argparse.py
decisions:
  - Patch DB_PATH as MagicMock at module level rather than patching WindowsPath.exists instance
    (CPython read-only slot; monkeypatch.setattr on instance raises AttributeError on Windows)
metrics:
  duration: ~8 min
  completed: 2026-06-25
  tasks_completed: 2
  files_changed: 2
---

# Phase 260625-jv2 Plan 01: Classify Multi-topic Fix Summary

**One-liner:** Restored repeatable `--topic` argparse flag (`action="append"`) plus per-topic `run()` loop in `batch_classify_kol.py` — re-regression fix for the last-wins collapse that left Agent/LLM/RAG/NLP frozen at 1013 rows while CV reached 2069.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Make --topic repeatable + loop run() per topic | 70ac77c | batch_classify_kol.py |
| 2 | Behavior-anchor test pinning argparse->run contract | 9ae68c3 | tests/unit/test_classify_multitopic_argparse.py |

## What Was Done

**Task 1 (batch_classify_kol.py — ~8 LoC change):**
- `--topic` argument changed from `type=str, required=True` (single-value, last-wins) to `type=str, action="append", required=True` (collects each flag into a list).
- `main()` now loops: `for topic in args.topic: run(topic, args.min_depth, args.classifier, args.dry_run)`.
- Added multi-topic usage example to module docstring.
- `run()` function body at line 369 is byte-unchanged; the fix is entirely in `main()`.

**Task 2 (tests/unit/test_classify_multitopic_argparse.py — 78 LoC):**
Three behavior-anchor tests pinning observable post-conditions (run call-count + call-arg order), not implementation shape:
- `test_multi_topic_runs_once_per_topic_in_order`: 5x `--topic` flags → 5 `run()` calls in CLI order.
- `test_single_topic_backward_compatible`: single `--topic Agent` → 1 call (backward-compat).
- `test_non_topic_args_forwarded_to_run`: `--min-depth 3 --classifier gemini --dry-run` forwarded intact to every `run()` call.

## Pytest Results

```
7 passed in 1.65s
  tests/unit/test_classify_multitopic_argparse.py::test_multi_topic_runs_once_per_topic_in_order PASSED
  tests/unit/test_classify_multitopic_argparse.py::test_single_topic_backward_compatible PASSED
  tests/unit/test_classify_multitopic_argparse.py::test_non_topic_args_forwarded_to_run PASSED
  tests/unit/test_classifications_multitopic.py::test_multi_topic_loop_creates_one_row_per_topic PASSED
  tests/unit/test_classifications_multitopic.py::test_rerun_loop_is_idempotent_upsert PASSED
  tests/unit/test_classifications_multitopic.py::test_multi_article_multi_topic_isolation PASSED
  tests/unit/test_classifications_multitopic.py::test_migration_005_idempotent PASSED
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] WindowsPath.exists is a read-only CPython slot**
- **Found during:** Task 2 — first pytest run (3 failed with `AttributeError: 'WindowsPath' object attribute 'exists' is read-only`)
- **Issue:** The plan's suggested `monkeypatch.setattr(batch_classify_kol.DB_PATH, "exists", lambda: True)` calls monkeypatch on a `WindowsPath` instance. On CPython, `Path.exists` is implemented as a C slot and cannot be overridden on an instance via `setattr`.
- **Fix:** Replace `DB_PATH` at the module level with a `unittest.mock.MagicMock()` whose `exists.return_value = True`. This sidesteps the slot restriction entirely and is semantically equivalent (the guard `if not DB_PATH.exists()` evaluates False, so no `sys.exit`).
- **Files modified:** `tests/unit/test_classify_multitopic_argparse.py`
- **Commit:** 9ae68c3 (folded into Task 2 commit — no separate commit needed for this 3-line fix)

## Post-execution Gates (orchestrator scope, NOT done here)

The following are prod-deploy steps for the orchestrator AFTER this quick closes:
1. Git push worktree branch / merge to main.
2. Aliyun `git pull` (with env sourced for real DEEPSEEK_API_KEY).
3. Backfill run: `python batch_classify_kol.py --topic Agent --topic LLM --topic RAG --topic NLP --topic CV` on Aliyun.
4. Prod DB verification: `SELECT topic, COUNT(*) FROM classifications GROUP BY topic;` — Agent/LLM/RAG/NLP should climb from 1013 toward 2069 (CV parity).

## Post-execution Gates — DONE (orchestrator, 2026-06-25/26)

Executor ran in an isolated worktree (branched from 996c993, 3 behind main). Its 2 commits were **cherry-picked** onto main rather than merged (a full merge would have reverted the intervening arx-4 work):

| Worktree hash | main hash | Commit |
| --- | --- | --- |
| 70ac77c | **b4d2450** | fix(classify): --topic repeatable (action=append) |
| 9ae68c3 | **6e252dc** | test(classify): pin argparse->run multi-topic call contract |

**Deploy:**
1. `git push origin main` → `996c993..6e252dc` pushed.
2. Aliyun `git pull` blocked by pre-existing uncommitted local mods to `synthesizer.py` + `qdrant_to_nanovdb.py` (in-flight prod hot-patches, NOT this quick's concern). Used surgical `git checkout origin/main -- batch_classify_kol.py` instead — brings only the fixed file, leaves the other modified files + HEAD untouched for separate reconciliation. Verified `action="append"` + `for topic in args.topic` landed (lines 470, 486).

**Backfill (Aliyun kol_scan.db, CST timestamps):**

| Topic | Before | After | Backlog before → after |
| --- | --- | --- | --- |
| Agent | 1013 | **2069** | 1056 → 0 ✅ |
| CV | 2069 | 2069 | 0 → 0 (already done) |
| LLM | 1013 | **2069** | 1056 → 0 ✅ |
| RAG | 1013 | **2069** | 1056 → 0 ✅ |
| NLP | 1013 | **2069** | 1056 → 0 ✅ (via #70 workaround) |

**Fix validated end-to-end:** all 5 topics now at full parity (2069 each, backlog→0). Agent/LLM/RAG climbed 1013 → 2069 on the normal 200-row path, proving the multi-topic loop now iterates every topic. Before the fix, a 5×`--topic` invocation only ever classified CV.

**Candidate-pool unlock:** ~3400 distinct `relevant=1` articles flagged across the 4 previously-starved topics (Agent=1625, LLM=1879, RAG=1473, NLP=1491 relevant). These are ingest candidates; `articles.layer2_verdict='ok'` (was 473) grows as the every-2h ingest cron processes the newly-unlocked pool.

**NLP — root cause pinned (#70), then resolved.** NLP failed `_call_deepseek` 11× across ~30 min on the 200-row path while Agent/LLM/RAG/CV succeeded. Initially looked like a transient empty-body flake, but a decisive A/B (same process/prompt/URL/model/key) showed a raw `requests.post` → HTTP 200 len=31898 while `b._call_deepseek` → FAIL. Dissection: NLP's 200-row batch-1 response hits DeepSeek `finish_reason=length` (token-truncated, ~28000 chars, JSON array cut mid-stream with no closing ```fence); the fence-strip at `batch_classify_kol.py:185-189` then leaves the raw `` ```json `` prefix and `json.loads` throws `Expecting value: line 1 column 1`. Batch-size sweep confirmed: **200→FAIL (finish=length), 100→OK, 50→OK**. Only NLP tripped it because its 200 title+digest set is the densest — the response just clears the token ceiling; the other topics stayed under. The script aborts the *whole topic* on any single batch failure (no retry, no partial-commit) → deterministic starvation, NOT a transient. **Resolved this session** via an ad-hoc 100-row-batch loop (idempotent UPSERT into the real `classifications` table): 11 batches, 1056/1056 written, NLP 1013→2069. Filed as **ISSUES #70 (P1)** with the pinned root cause; real code fix (lower batch_size / split-on-`finish_reason=length`) deferred — the systemd cron still uses batch_size=200 and will re-fail dense topics until that lands.

**systemd service — no change needed:** `omnigraph-kol-classify.service` ExecStart already passes `--topic Agent --topic LLM --topic RAG --topic NLP --topic CV --min-depth 2` (the exact line that previously collapsed to CV-only). With `action="append"` deployed, the next timer fire parses all 5 correctly — confirmed by inspection.

## Self-Check: PASSED

- `batch_classify_kol.py` — `action="append"` and `for topic in args.topic` present, file parses: OK
- `tests/unit/test_classify_multitopic_argparse.py` — exists, 78 lines, 3 tests: OK
- Fix commit `b4d2450` (was 70ac77c in worktree) — present in `git log --oneline main`: OK
- Test commit `6e252dc` (was 9ae68c3 in worktree) — present in `git log --oneline main`: OK
- Pytest result: 7/7 passed, 0 failed: OK
- Aliyun deploy + backfill: 4/5 topics at parity, NLP deferred to next timer fire: OK
