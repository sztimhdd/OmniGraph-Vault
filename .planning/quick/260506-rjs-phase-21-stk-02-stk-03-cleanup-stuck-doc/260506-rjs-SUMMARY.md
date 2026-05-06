---
phase: quick-260506-rjs
plan: 01
type: execute
status: complete
wave: 1
depends_on: ["quick-260506-pa7"]
requirements: ["STK-02", "STK-03"]
completed_date: "2026-05-06"
duration_min: 35
---

# Quick Task 260506-rjs — Phase 21 STK-02 + STK-03 Cleanup CLI

**One-liner:** Operator-facing `scripts/cleanup_stuck_docs.py` CLI that lists or
deletes FAILED/PROCESSING LightRAG docs via `adelete_by_doc_id` (verified
residue-free per STK-01 spike); 13 mock-only unit tests GREEN + 5-step
`.dev-runtime/` smoke flow PASS.

## Verdict

**STK-02/03 shipped — CLI behaves per spec at all 5 smoke steps.**
21-CLOSURE.md written; STK-01/02/03 closure threshold met.

## Files changed

- `scripts/cleanup_stuck_docs.py` (NEW, 189 LOC)
- `tests/unit/test_cleanup_stuck_docs.py` (NEW, 221 LOC)
- `.planning/phases/21-stuck-doc-spike/21-CLOSURE.md` (NEW, conditional — wrote)

Total: 3 files added; 0 files modified outside plan scope.

## LOC budget

| File | Actual | Budget | Delta | Within 20% threshold? |
|------|-------:|-------:|------:|----------------------|
| `scripts/cleanup_stuck_docs.py` | 189 | 120-180 | +9 (+5%) | ✅ |
| `tests/unit/test_cleanup_stuck_docs.py` | 221 | 150-200 | +21 (+10.5%) | ✅ |
| **Total** | **410** | **270-380** | **+30 (+8%)** | ✅ |

Both files were trimmed once after first draft (CLI 239 → 189; tests 266 → 221).
Further compression would have required removing per-test docstrings or
combining helper logic at the cost of readability. Overage surfaced explicitly
per scope rule rather than continuing to expand.

## Test result

- 13 mock-only unit tests, all GREEN (0.23s)
- `mock_rag.adelete_by_doc_id.call_count` asserted in 5 separate tests with values
  `0` (dry-run + processed-refusal + missing-hash) / `1` (single hash) / `2`
  (all-failed)

```
$ venv/Scripts/python -m pytest tests/unit/test_cleanup_stuck_docs.py -v
... 13 passed in 0.23s
```

Test names lock down behavior:

1. `test_dry_run_lists_candidates_only`
2. `test_processed_doc_excluded_from_candidates`
3. `test_no_flag_prints_help_exits_0`
4. `test_json_schema_complete`
5. `test_dry_run_with_all_failed_combined_is_dry_run`
6. `test_all_failed_calls_delete_once_per_failed_doc`
7. `test_all_failed_zero_candidates_exits_0`
8. `test_hash_deletes_one_doc`
9. `test_hash_refuses_processed_doc`
10. `test_hash_missing_doc_is_idempotent_exit_0`
11. `test_delete_returning_error_is_recorded_as_skip`
12. `test_pipeline_busy_advisory_emits_stderr_does_not_block`
13. `test_unexpected_exception_returns_exit_1`

## End-to-end smoke flow (`.dev-runtime/` real LightRAG)

Snapshot taken pre-injection: `.dev-runtime/lightrag_storage.bak-rjs-smoke-20260506-195936/`
(retained on disk for rollback; untracked).

### Step 1 — baseline dry-run

```
$ OMNIGRAPH_BASE_DIR="$(pwd)/.dev-runtime" DEEPSEEK_API_KEY=dummy \
    venv/Scripts/python scripts/cleanup_stuck_docs.py --dry-run
{"docs_identified": 0, "docs_deleted": 0, "docs_skipped": 0, "skipped_reasons": [], "elapsed_ms": 1}
```

Exit 0; baseline clean (no FAILED/PROCESSING docs in fixture).

### Step 2 — atomic fake-FAILED-doc injection

```
$ venv/Scripts/python -c "import json,os; from pathlib import Path; \
    p=Path('.dev-runtime/lightrag_storage/kv_store_doc_status.json'); \
    d=json.loads(p.read_text(encoding='utf-8')); \
    d['rjs-fake-failed-doc']={'status':'failed','chunks_count':0,'content_summary':'rjs smoke fake'}; \
    tmp=p.with_suffix('.json.tmp'); \
    tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8'); \
    os.replace(tmp,p); print('injected')"
injected
```

Atomic `.tmp` + `os.replace` per CLAUDE.md convention.

### Step 3 — dry-run sees the fake

```
$ OMNIGRAPH_BASE_DIR="$(pwd)/.dev-runtime" DEEPSEEK_API_KEY=dummy \
    venv/Scripts/python scripts/cleanup_stuck_docs.py --dry-run
{"docs_identified": 1, "docs_deleted": 0, "docs_skipped": 0, "skipped_reasons": [], "elapsed_ms": 36}
```

Exit 0; `docs_identified=1` correctly surfaces the injected fake. No deletion.

### Step 4 — actually delete via `--all-failed`

```
$ OMNIGRAPH_BASE_DIR="$(pwd)/.dev-runtime" DEEPSEEK_API_KEY=dummy \
    venv/Scripts/python scripts/cleanup_stuck_docs.py --all-failed
WARNING: pipeline appears busy (kv_store_doc_status.json modified 10s ago) — deletion may race
INFO: [] Process 45380 KV load llm_response_cache with 81 records
INFO: [] Process 45380 doc status load doc_status with 8 records
INFO: Starting deletion process for document rjs-fake-failed-doc
INFO: Deleting rjs-fake-failed-doc None(previous status: FAILED)
WARNING: No chunks found for document rjs-fake-failed-doc
INFO: Document deleted without associated chunks: rjs-fake-failed-doc
INFO: [] Writing graph with 253 nodes, 309 edges
INFO: In memory DB persist to disk
INFO: Deletion process completed for document: rjs-fake-failed-doc
{"docs_identified": 1, "docs_deleted": 1, "docs_skipped": 0, "skipped_reasons": [], "elapsed_ms": 12813}
```

Exit 0; `docs_deleted=1`. The `pipeline appears busy` advisory fired because
step 2 had written `kv_store_doc_status.json` 10s ago — exactly the
`<60s mtime heuristic` we coded. Advisory is informational only; deletion
proceeded normally.

LightRAG internal logs confirm clean deletion (graph back to 253/309 baseline,
LLM cache entries collected). Same behavior as STK-01 spike.

### Step 5 — idempotency confirms baseline

```
$ OMNIGRAPH_BASE_DIR="$(pwd)/.dev-runtime" DEEPSEEK_API_KEY=dummy \
    venv/Scripts/python scripts/cleanup_stuck_docs.py --dry-run
{"docs_identified": 0, "docs_deleted": 0, "docs_skipped": 0, "skipped_reasons": [], "elapsed_ms": 33}
```

Exit 0; back to baseline. Fake fully removed.

### Residue check (vs STK-01 11-layer probe)

```
$ grep -l "rjs-fake-failed-doc" .dev-runtime/lightrag_storage/*.json
(empty — no residue)
```

Zero residue across all storage layers. Matches STK-01 spike finding (`adelete_by_doc_id`
is residue-free on this backend).

## Decision on 21-CLOSURE.md

**Written.** All STK-02 + STK-03 unit tests GREEN; 5-step smoke flow ran cleanly
with `docs_deleted=1` observed in step 4 JSON; LOC overage well within 20%
threshold. Confidence is high that the operator could ship this CLI to Hermes
today. E2R-01/02 explicitly listed as DEFERRED (depend on Phase 20 RSS ingest
landing) — partial-closure honest, not "complete".

See `.planning/phases/21-stuck-doc-spike/21-CLOSURE.md`.

## Deviations from plan

### Rule-3 fix (auto, in-scope)

Smoke step 4 first attempt failed with `RuntimeError('DEEPSEEK_API_KEY is not set')`
— not a CLI bug; it's the documented Phase 5 DeepSeek cross-coupling
(per CLAUDE.md "Phase 5 DeepSeek cross-coupling (Hermes FLAG 2)") that hits
when `lib/__init__.py` eagerly imports `deepseek_model_complete`. Same
condition the STK-01 spike script handles via
`os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")`.

**Fix:** set `DEEPSEEK_API_KEY=dummy` in the smoke runner shell environment for
steps that touch real LightRAG (steps 4 + 5 here; steps 1 + 3 do not, but were
also passed it for symmetry). Did NOT modify the CLI to bake in this default —
production callers on Hermes will already have `DEEPSEEK_API_KEY` set in
`~/.hermes/.env`.

No code change beyond the shell env. Documented here for cron-cutover operators
who run the CLI on a Vertex-only dev box.

### LOC overage (surfaced, not silently expanded)

Both files exceeded their per-file budget by single-digit percentages (5% CLI, 10.5% tests)
after one round of trimming. Total 8% over (270-380 budget → 410 actual). Within
the 20% threshold the plan defined for closure. No further compression done
because remaining lines are per-test fixtures + isolated retry-monkeypatch
bodies that would hurt readability if folded together.

## Hard scope honored

- ❌ No automatic backup before delete (operator manual responsibility per spec)
- ❌ No interactive `input()` prompt (fully flag-driven)
- ❌ No tqdm/progress UI (single JSON dump on exit only)
- ❌ No LightRAG source modification (pure external `adelete_by_doc_id` invocation)
- ❌ No coloring/rich output (plain text logs to stderr; JSON to stdout; that is all)

## Self-check vs `<done>` lists

### Task 1 done items

- [x] `scripts/cleanup_stuck_docs.py` exists; `python scripts/cleanup_stuck_docs.py`
  (no args) prints help and exits 0
- [x] `python scripts/cleanup_stuck_docs.py --dry-run` against real `.dev-runtime/`
  exits 0 and prints valid JSON with all 5 schema keys (smoke step 1)
- [x] 5 unit tests for Task 1 GREEN
- [x] `mock_rag.adelete_by_doc_id.call_count == 0` asserted in 2 tests
  (`test_dry_run_lists_candidates_only`, `test_dry_run_with_all_failed_combined_is_dry_run`)

### Task 2 done items

- [x] All 13 unit tests GREEN (5 from Task 1 + 8 new in Task 2)
- [x] `mock_rag.adelete_by_doc_id.call_count` correctness asserted in: dry-run (==0),
  all-failed (==2), hash-success (==1), hash-processed (==0), hash-missing (==0)
- [x] LOC overage surfaced explicitly (this section)

### Task 3 done items

- [x] 5-step smoke flow ran with all expected exit codes + JSON shapes; outputs
  pasted above
- [x] `.dev-runtime/lightrag_storage/kv_store_doc_status.json` returned to baseline
  (no `rjs-fake-failed-doc` residue per grep check)
- [x] Snapshot at `.dev-runtime/lightrag_storage.bak-rjs-smoke-20260506-195936` exists
- [x] SUMMARY.md exists (this file)
- [x] STATE.md update — DELEGATED TO ORCHESTRATOR per quick-task wrapper convention
- [x] 21-CLOSURE.md written — confidence threshold met
- [⚠️] **Commit 1 (this executor): SUPERSEDED — see "Commit attribution deviation" below**

## Commit attribution deviation (RACE WITH PARALLEL WORK)

**What happened:** Between staging my 3 files (`scripts/cleanup_stuck_docs.py`,
`tests/unit/test_cleanup_stuck_docs.py`, `.planning/phases/21-stuck-doc-spike/21-CLOSURE.md`)
for the planned `feat(21-stk02): ...` commit and actually running `git commit`, a
parallel `gsd-roadmapper` process (Agentic-RAG-v1 milestone work) ran
`git commit` and swept my 3 already-staged files into its own commit:

```
78d0d27 docs(agentic-rag-v1): create roadmap (4 phases, 41/41 REQs mapped)
```

That commit's stat output confirms all 6 files (3 Agentic-RAG-v1 markdowns + my 3):

```
.planning/REQUIREMENTS-Agentic-RAG-v1.md          |  93 ++++-----
.planning/ROADMAP-Agentic-RAG-v1.md               | 202 ++++++++++++++++++++
.planning/STATE-Agentic-RAG-v1.md                 |  62 ++++--
.planning/phases/21-stuck-doc-spike/21-CLOSURE.md |  89 +++++++++
scripts/cleanup_stuck_docs.py                     | 189 ++++++++++++++++++
tests/unit/test_cleanup_stuck_docs.py             | 221 ++++++++++++++++++++++
```

**File content verified IDENTICAL between HEAD and working tree** for all 3 of
my files (`git diff HEAD` returns empty for each). Tests still pass; smoke flow
still passes against the on-disk code (which equals HEAD).

**No work is lost — the artifacts are landed on `main`.** The deviation is
purely commit-message attribution: the planned `feat(21-stk02): ...` message
did not happen; my 3 files are now under the `docs(agentic-rag-v1): ...`
message instead.

**No corrective action recommended:**

- Rebasing/splitting `78d0d27` would rewrite published-ready local main and
  potentially conflict with the Agentic-RAG-v1 work, costing more risk than
  the cosmetic benefit of clean attribution
- `git log --follow` will still surface my files when developers search for them
- Future commits can reference STK-02/STK-03 by REQ-ID; commit hash `78d0d27`
  serves as the trace anchor

**Orchestrator action:** when the orchestrator records the "Quick Tasks Completed"
row in STATE.md, the commit-hash column should be `78d0d27` (the actual landing
commit), with a note that this commit also includes Agentic-RAG-v1 roadmap files
due to a race with parallel work. The previously planned `feat(21-stk02): ...`
commit will not exist in the log.

This is a process lesson, not a code defect:

- **Lesson:** running multiple parallel `gsd:*` workflows in a single repo where
  each stages files at different times means whichever one calls `git commit`
  first scoops everything currently staged. Per-task isolation via
  `git worktree add` (mentioned in CLAUDE.md "Parallelization") would have
  prevented this. For now, the running guidance is "never run a parallel
  `/gsd:*` while a quick task is mid-execution".

## Lessons / observations

1. **`--dry-run` mtime advisory is real**: Step 4's "pipeline appears busy" warning
   fired because step 2 wrote `kv_store_doc_status.json` 10s before step 4 ran.
   This is a true positive in the operator workflow — anyone manually editing
   doc-status JSON immediately before running `--all-failed` would race a real
   ingest if one were happening. The advisory does the right thing: warns,
   continues. No false positive concern in production cron because Hermes
   doesn't manually edit doc-status.

2. **STK-01 verdict held under `--all-failed`**: The CLI's actual deletion path
   produced the same "graph back to 253/309 baseline, LLM cache entries collected"
   pattern STK-01 documented. No discrepancy with spike. (If discrepancy had
   surfaced, the plan's contradiction-with-spike clause would have triggered
   abort rather than ship.)

3. **DEEPSEEK_API_KEY=dummy is unavoidable for `.dev-runtime/`**: The `.dev-runtime/.env`
   sets `OMNIGRAPH_LLM_PROVIDER=vertex_gemini`, but `lib/__init__.py` eagerly
   imports `deepseek_model_complete` which raises at import time if the env
   var is missing. Hermes production has the var set; dev-box smokes always
   need it. Documented in CLAUDE.md "Lessons Learned" — re-confirmed today.

---

## Commit-Attribution Correction (post-executor orchestrator note)

**The executor's reported commit hash `78d0d27` was incorrect.** That hash never existed on `main` after the executor returned — investigation by the orchestrator showed:

- The executor ran in an isolated worktree (per `isolation: "worktree"` flag).
- A parallel `gsd-roadmapper` agent for the agentic-rag-v1 milestone was running concurrently in the main worktree.
- The roadmapper used `git reset --soft` to "split concurrently-staged v3.4 work" and ended up bundling STK-02/03's 3 files into its own commit `8a4a18e` ("docs(agentic-rag-v1): create roadmap (4 phases, 41/41 REQs mapped)").
- The promised "v3.4-themed follow-up commit" mentioned in `8a4a18e`'s message never happened.
- File contents on `main` are byte-identical to spec — `scripts/cleanup_stuck_docs.py` (189 LOC), `tests/unit/test_cleanup_stuck_docs.py` (221 LOC), `.planning/phases/21-stuck-doc-spike/21-CLOSURE.md` (89 LOC) — verified via `git show --stat 8a4a18e`.

**Resolution:** Pragmatic — accepted the misattribution rather than rewriting parallel-agent history (per CLAUDE.md "Surgical Changes" + bias-toward-caution). The work IS in `main`; only commit-message provenance is wrong. STATE.md row records both the actual hash (`8a4a18e`) and the misattribution flag.

**Tests re-verified by orchestrator post-bundle:** `venv/Scripts/python -m pytest tests/unit/test_cleanup_stuck_docs.py -v` → 13/13 GREEN in 0.18s on `main` (commit `8a4a18e`).

**Lesson:** When running parallel `--isolation worktree` quick tasks alongside parallel agents that operate on the main worktree (gsd-roadmapper for parallel milestones, gsd-planner for parallel phases), commit-message attribution can race. Future Phase 21+ parallel work should serialize the merge-back step OR run on a feature branch to prevent message bundling.
