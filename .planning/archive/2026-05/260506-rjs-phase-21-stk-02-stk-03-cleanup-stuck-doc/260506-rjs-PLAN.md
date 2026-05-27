---
phase: quick-260506-rjs
plan: 01
type: execute
wave: 1
depends_on: ["quick-260506-pa7"]
files_modified:
  - scripts/cleanup_stuck_docs.py
  - tests/unit/test_cleanup_stuck_docs.py
autonomous: true
requirements: ["STK-02", "STK-03"]

must_haves:
  truths:
    - "Operator can list FAILED/PROCESSING doc IDs without modifying anything (--dry-run)"
    - "Operator can delete one specific doc by hash (--hash <doc_id>)"
    - "Operator can delete all FAILED docs in one shot (--all-failed)"
    - "Every successful run prints a JSON report with 5 schema keys to stdout"
    - "Exit 0 on 'nothing to clean', 'all cleaned', and on --dry-run; non-0 only on unexpected exception"
    - "PROCESSED docs are never in the candidate list"
    - "Active-pipeline-lock detection emits stderr advisory but never hard-fails"
    - "Real .dev-runtime/ smoke flow (dry-run → inject fake → dry-run → all-failed → dry-run) returns to baseline"
  artifacts:
    - path: scripts/cleanup_stuck_docs.py
      provides: "argparse CLI; lists/deletes FAILED|PROCESSING docs via adelete_by_doc_id; JSON report"
      min_lines: 120
      max_lines: 180
    - path: tests/unit/test_cleanup_stuck_docs.py
      provides: "mock-only unit tests; LightRAG and adelete_by_doc_id mocked; no real .dev-runtime mutation"
      min_lines: 150
      max_lines: 200
  key_links:
    - from: scripts/cleanup_stuck_docs.py
      to: lightrag.LightRAG.adelete_by_doc_id
      via: "await rag.adelete_by_doc_id(doc_id)"
      pattern: "adelete_by_doc_id"
    - from: scripts/cleanup_stuck_docs.py
      to: config.RAG_WORKING_DIR
      via: "from config import RAG_WORKING_DIR; reads kv_store_doc_status.json"
      pattern: "kv_store_doc_status.json"
    - from: tests/unit/test_cleanup_stuck_docs.py
      to: scripts/cleanup_stuck_docs.py
      via: "imports + AsyncMock(LightRAG) + monkeypatch RAG_WORKING_DIR"
      pattern: "AsyncMock|monkeypatch"
---

<objective>
Implement Phase 21 STK-02 + STK-03: a thin-wrapper CLI at `scripts/cleanup_stuck_docs.py` that finds FAILED / PROCESSING docs in `kv_store_doc_status.json` and deletes them via `LightRAG.adelete_by_doc_id` (verified clean per STK-01 spike findings). The CLI emits a structured 5-key JSON report on stdout and uses exit codes that are friendly to cron / shell pipelines.

Purpose: Operators need a one-shot tool to recover from stuck-doc situations without touching internal LightRAG storage layers. STK-01 already proved `adelete_by_doc_id` is residue-free on the production storage backend — this plan is the operator-facing CLI on top of that finding. Stuck-doc cleanup is a Phase 21 success-criterion gate for Phase 22 backlog re-ingest (BKF-02 delete-before-reinsert pattern depends on the same primitive, but is out of scope here).

Output:
- `scripts/cleanup_stuck_docs.py` (CLI; ~120-180 LOC; --dry-run / --all-failed / --hash flags)
- `tests/unit/test_cleanup_stuck_docs.py` (mock-only; ~150-200 LOC; 8+ assertions covering schema + exit codes + flag isolation)
- Local smoke evidence (5-step manual run on `.dev-runtime/`) recorded in commit message / SUMMARY.md
- Optional: `.planning/phases/21-stuck-doc-spike/21-CLOSURE.md` if executor confirms STK-01/02/03 all green AND explicitly defers E2R-01/02 to post-Phase-20 (judgment call deferred to executor — see decision gate in Task 3 below)
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/ROADMAP.md
@.planning/phases/21-stuck-doc-spike/21-00-SPIKE-FINDINGS.md
@.planning/quick/260506-pa7-phase-21-stk-01-nanovectordb-cleanup-spi/spike_cleanup_probe.py
@.planning/quick/260506-pa7-phase-21-stk-01-nanovectordb-cleanup-spi/260506-pa7-SUMMARY.md
@scripts/checkpoint_reset.py
@scripts/checkpoint_status.py
@config.py

<interfaces>
<!-- Key contracts the executor must hold to. Do NOT re-explore the codebase. -->

# CLI signature (argparse)
- `--dry-run` (flag) — list candidates only, no mutation; exit 0
- `--all-failed` (flag) — delete every doc with status=='failed'; exit 0 even if 0 found
- `--hash <doc_id>` (string) — delete exactly one doc by id; exit 0 if it was deleted
                                 OR was already absent (idempotent); exit 1 if doc exists
                                 but is in 'processed' status (refuse to delete healthy data)
- No flag → `parser.print_help(); return 0`
- `--all-failed` and `--hash` and `--dry-run` are mutually exclusive (argparse group). `--dry-run` may be combined with `--all-failed` to preview a planned delete (treat `--dry-run --all-failed` as `--dry-run` and exit 0).

# JSON report schema (single source of truth — define once, use in both impl + tests)
```python
from typing import TypedDict, Literal

SkipReason = Literal["pipeline_busy", "not_failed_status", "doc_not_found", "delete_returned_error"]

class SkipEntry(TypedDict):
    doc_id: str
    status: str         # actual status read from kv_store_doc_status.json (or "missing")
    reason: SkipReason

class CleanupReport(TypedDict):
    docs_identified: int            # count of FAILED/PROCESSING candidates seen
    docs_deleted: int               # count where adelete_by_doc_id returned status='success'
    docs_skipped: int               # len(skipped_reasons)
    skipped_reasons: list[SkipEntry]
    elapsed_ms: int                 # time.perf_counter_ns() based, integer ms
```
Output: `print(json.dumps(report, ensure_ascii=False))` exactly once on stdout.

# Eligible status values for cleanup (from kv_store_doc_status.json)
- `failed` → deletable
- `processing` → deletable (operator chose to clean — possible orphan from killed run)
- `processed` → NEVER deletable; if --hash targets a processed doc, refuse (exit 1, JSON.skipped_reasons[0].reason='not_failed_status')
- anything else → skip with reason='not_failed_status'

# Active-pipeline-lock detection (advisory; NEVER hard-fail)
Best-effort check before deletion. Try in this order, stop at first that succeeds:
  (a) `from lightrag.kg.shared_storage import get_pipeline_status_lock` — if importable, attempt non-blocking acquire / release pattern (see lightrag.kg.shared_storage source). If acquire fails or namespace says "busy", emit stderr warning.
  (b) Else: stat `RAG_WORKING_DIR / "pipeline_status.json"` if it exists; warn if mtime < 60s (best-effort heuristic).
  (c) Else: silent — no advisory, no warning. Spec says "advisory-level" so absence of signal is acceptable.
On any signal of pipeline busy: write to stderr `WARNING: pipeline appears busy — deletion may race with active ingest`. Continue execution. NEVER block.

# adelete_by_doc_id contract (per STK-01 findings)
- Returns `DeletionResult(status: str, doc_id: str, message: str, status_code: int, ...)` where status_code 200 + status=='success' means clean.
- May return non-success on its own (e.g., doc_id not found) — caller must check status, not assume exception.
- Async: must be awaited inside `asyncio.run(main_async())`.

# Imports the CLI must use (DO NOT diverge)
```python
import argparse, asyncio, json, logging, os, sys, time
from pathlib import Path
from typing import TypedDict, Literal, Any  # already shown above

# config + LightRAG (mirror spike_cleanup_probe.py:151)
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from config import RAG_WORKING_DIR
# Late import inside main_async() so .env is loaded:
#   from ingest_wechat import get_rag
```

# Test fixture pattern (mock-only — DO NOT touch .dev-runtime/)
```python
@pytest.fixture
def fake_doc_status(tmp_path, monkeypatch):
    """Build an isolated kv_store_doc_status.json with known FAILED/PROCESSING/PROCESSED entries."""
    storage = tmp_path / "lightrag_storage"
    storage.mkdir()
    status = {
        "doc_a_failed":     {"status": "failed",     "chunks_count": 1},
        "doc_b_processing": {"status": "processing", "chunks_count": 0},
        "doc_c_processed":  {"status": "processed",  "chunks_count": 3},
    }
    (storage / "kv_store_doc_status.json").write_text(json.dumps(status), encoding="utf-8")
    monkeypatch.setattr("scripts.cleanup_stuck_docs.RAG_WORKING_DIR", storage)
    return storage

@pytest.fixture
def mock_rag(monkeypatch):
    """AsyncMock LightRAG.adelete_by_doc_id; returns success-shaped object."""
    rag = MagicMock()
    rag.adelete_by_doc_id = AsyncMock(return_value=SimpleNamespace(
        status="success", doc_id="x", message="ok", status_code=200
    ))
    async def fake_get_rag(flush=False):
        return rag
    monkeypatch.setattr("scripts.cleanup_stuck_docs._build_rag", fake_get_rag)
    return rag
```
The CLI must expose a `_build_rag()` async helper (single-line wrapper around `from ingest_wechat import get_rag`) so tests can monkeypatch a single seam. Do NOT monkeypatch `ingest_wechat.get_rag` directly — too brittle.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Build CLI scaffold + JSON report schema + dry-run path</name>
  <files>scripts/cleanup_stuck_docs.py, tests/unit/test_cleanup_stuck_docs.py</files>
  <behavior>
    Mock-only tests, written first. Each test names the behavior it locks down:

    - `test_dry_run_lists_candidates_only`: with `fake_doc_status` containing 1 FAILED + 1 PROCESSING + 1 PROCESSED, `--dry-run` exits 0, prints JSON with `docs_identified=2, docs_deleted=0`, and `mock_rag.adelete_by_doc_id` is NEVER called (assert `.call_count == 0`).
    - `test_processed_doc_excluded_from_candidates`: same fixture, assert `'doc_c_processed'` does not appear in any output (stdout JSON or stderr).
    - `test_no_flag_prints_help_exits_0`: invoking with `argv=[]` (no flags) prints help to stdout, exit code 0, NO JSON dump (i.e. caller can detect "help mode" by absence of valid JSON parse — test asserts `argparse.print_help` was called or stdout starts with "usage:").
    - `test_json_schema_complete`: parse stdout from `--dry-run`, assert all 5 schema keys present (`docs_identified`, `docs_deleted`, `docs_skipped`, `skipped_reasons`, `elapsed_ms`), assert types match TypedDict (ints + list).
    - `test_dry_run_with_all_failed_combined_is_dry_run`: `--dry-run --all-failed` together → still no deletion calls, exit 0.
  </behavior>
  <action>
    Write `scripts/cleanup_stuck_docs.py` skeleton:

    1. Module docstring (≤8 lines): purpose, exit codes, refer to STK-01 findings doc.
    2. Imports: argparse, asyncio, json, logging, os, sys, time, pathlib.Path, typing (TypedDict, Literal, Any), types.SimpleNamespace.
    3. REPO_ROOT bootstrap exactly as in `scripts/checkpoint_reset.py:17-19`. Then `from config import RAG_WORKING_DIR`.
    4. Define `SkipReason`, `SkipEntry`, `CleanupReport` TypedDicts at module top — single source of truth, imported in tests.
    5. Pure helper `_load_doc_status(storage_dir: Path) -> dict[str, dict]`: reads `kv_store_doc_status.json`; returns `{}` if absent. No side effects.
    6. Pure helper `_filter_candidates(status_map: dict) -> list[tuple[str, str]]`: returns `[(doc_id, status), ...]` for entries where status in `("failed", "processing")`.
    7. Pure helper `_emit_pipeline_busy_warning(storage_dir: Path) -> None`: best-effort detection per `<interfaces>` block; writes to stderr only; never raises. Tries `lightrag.kg.shared_storage` first, falls back to silent.
    8. Async helper `_build_rag()`: single-line wrapper `from ingest_wechat import get_rag; return await get_rag(flush=False)`. The seam tests monkeypatch.
    9. `async def main_async(args: argparse.Namespace) -> int`: orchestrator. Dispatches to one of three branches (dry_run / all_failed / hash) and prints exactly one JSON line on stdout.
    10. Dry-run branch only this task: builds report with `docs_identified = len(candidates)`, `docs_deleted = 0`, `docs_skipped = 0`, `skipped_reasons = []`, `elapsed_ms = int(round((time.perf_counter() - t0) * 1000))`. Print JSON. Return 0.
    11. `def main(argv: list[str] | None = None) -> int`: argparse setup with mutually exclusive group `(--dry-run, --all-failed, --hash)` BUT allow `--dry-run --all-failed` together by using `add_mutually_exclusive_group(required=False)` only for `--all-failed` vs `--hash`, then add `--dry-run` separately. Validate combinations explicitly (exit 2 + parser error if `--hash X --all-failed`). No flag → `parser.print_help(); return 0`. Wrap `asyncio.run(main_async(args))` with try/except: any unexpected exception → log to stderr, print partial JSON if possible, return 1.

    Test file structure:
    - `pytest.ini`-compatible: top-of-file `import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))` so `scripts.cleanup_stuck_docs` importable.
    - Use `subprocess.run` is NOT allowed — these are unit tests. Call `cleanup_stuck_docs.main(argv=[...])` directly and capture stdout via `capsys`.
    - Use `monkeypatch.setattr` for both `RAG_WORKING_DIR` (per-test fake storage) and `_build_rag` (returns mock).
    - DO NOT use `unittest.mock.patch` decorators — prefer `monkeypatch` for pytest idiom.

    LOC budget for THIS task: CLI ≈70 LOC (skeleton + helpers + dry-run only); tests ≈80 LOC (5 tests + 2 fixtures).
  </action>
  <verify>
    <automated>venv/Scripts/python -m pytest tests/unit/test_cleanup_stuck_docs.py -v -k "dry_run or processed_doc or no_flag or json_schema or combined" 2>&amp;1 | tail -30</automated>
  </verify>
  <done>
    - `scripts/cleanup_stuck_docs.py` exists; `python scripts/cleanup_stuck_docs.py` (no args) prints help and exits 0
    - `python scripts/cleanup_stuck_docs.py --dry-run` against real `.dev-runtime/` exits 0 and prints valid JSON with all 5 schema keys (likely shows 0 candidates since fixture is currently clean)
    - 5 unit tests in `tests/unit/test_cleanup_stuck_docs.py` GREEN
    - `mock_rag.adelete_by_doc_id.call_count == 0` asserted in 2 tests
    - LOC count check: CLI between 60-100 lines; tests between 70-110 lines (pre-Task-2 expansion)
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add --all-failed and --hash deletion paths + skipped_reasons + advisory</name>
  <files>scripts/cleanup_stuck_docs.py, tests/unit/test_cleanup_stuck_docs.py</files>
  <behavior>
    Tests written first, then implementation. Each test's name = behavior locked:

    - `test_all_failed_calls_delete_once_per_failed_doc`: 1 FAILED + 1 PROCESSING + 1 PROCESSED in fixture; `--all-failed` invokes `mock_rag.adelete_by_doc_id` exactly twice (FAILED + PROCESSING — both eligible), with the right doc_ids; exit 0; JSON `docs_deleted == 2`.
    - `test_all_failed_zero_candidates_exits_0`: empty fixture; exit 0; JSON `docs_identified=0, docs_deleted=0, skipped_reasons=[]`.
    - `test_hash_deletes_one_doc`: fixture has FAILED `doc_a_failed`; `--hash doc_a_failed` invokes delete exactly once; JSON `docs_deleted=1, docs_identified=1`; exit 0.
    - `test_hash_refuses_processed_doc`: fixture has `doc_c_processed`; `--hash doc_c_processed` returns exit 1; `mock_rag.adelete_by_doc_id` NEVER called; JSON has `skipped_reasons[0].reason == "not_failed_status"`.
    - `test_hash_missing_doc_is_idempotent_exit_0`: `--hash totally_unknown_doc` → exit 0 (idempotent); JSON `docs_identified=0, docs_deleted=0, skipped_reasons` contains entry with reason `"doc_not_found"`. Rationale: re-running the same `--hash X` command after a successful delete must not error.
    - `test_delete_returning_error_is_recorded_as_skip`: monkeypatch `mock_rag.adelete_by_doc_id` to return `SimpleNamespace(status='error', status_code=500, message='kuzu lock', doc_id='doc_a_failed')`; assert exit 0 (per spec — only unexpected EXCEPTION returns non-0; documented error returns are skips); JSON `skipped_reasons[0].reason == "delete_returned_error"`, `docs_deleted == 0`.
    - `test_pipeline_busy_advisory_emits_stderr_does_not_block`: monkeypatch `_emit_pipeline_busy_warning` to write a known string to stderr; assert string appears in `capsys.readouterr().err`; exit code unaffected (still 0); deletion still ran.
    - `test_unexpected_exception_returns_exit_1`: monkeypatch `mock_rag.adelete_by_doc_id` to raise `RuntimeError("boom")`; exit 1; some JSON or error message goes to stderr/stdout; test does not depend on partial-JSON shape (just asserts exit 1).
  </behavior>
  <action>
    Extend `scripts/cleanup_stuck_docs.py`:

    1. Implement `--all-failed` branch in `main_async`:
       - Build candidates via `_filter_candidates`.
       - Call `_emit_pipeline_busy_warning(RAG_WORKING_DIR)` once before loop.
       - For each `(doc_id, status)` in candidates: `await rag.adelete_by_doc_id(doc_id)`, inspect return. If `result.status == 'success'`: increment deleted. Else: append SkipEntry with reason='delete_returned_error'.
       - Print JSON, return 0.
    2. Implement `--hash <doc_id>` branch:
       - Read doc_status. If doc_id not in map: report SkipEntry with reason='doc_not_found' and status='missing', return 0 (idempotent).
       - Else if status not in `('failed', 'processing')`: SkipEntry with reason='not_failed_status', status=actual status, return 1 (refuse to delete healthy data).
       - Else: build candidates list of length 1, run advisory, call delete, build report, return 0.
    3. `_emit_pipeline_busy_warning`: implement best-effort try-chain per <interfaces>. Key constraint: this function MUST NEVER RAISE. Wrap each branch in try/except OSError, ImportError, AttributeError. Logger to stderr only.
    4. Top-level main(): wrap `asyncio.run(main_async(args))` in try/except `Exception`. Log to stderr `f"unexpected error: {exc}"`. Return 1. Do NOT swallow KeyboardInterrupt.
    5. SkipEntry construction: helper `_skip(doc_id, status, reason) -> SkipEntry` returning the dict (single source of construction; tests assert via dict equality).

    LOC budget for cumulative file: CLI ≈120-180 (target 150); tests ≈150-200 (target 180). If projected over budget, STOP and surface in commit message + summary; do not silently expand. The plan's hard scope explicitly forbids over-budget creep.

    Hard scope reminders (DO NOT do these):
    - No automatic backup before delete (operator manual responsibility per spec)
    - No interactive prompt (`input()`) — fully flag-driven CLI
    - No tqdm / progress bar — single JSON dump on exit only
    - No modification of LightRAG source — pure external `adelete_by_doc_id` invocation
    - No coloring/rich output — plain text logs to stderr, JSON to stdout, that is all
  </action>
  <verify>
    <automated>venv/Scripts/python -m pytest tests/unit/test_cleanup_stuck_docs.py -v 2>&amp;1 | tail -40</automated>
  </verify>
  <done>
    - All 13 unit tests GREEN (5 from Task 1 + 8 new in Task 2)
    - `mock_rag.adelete_by_doc_id.call_count` correctness asserted in: dry-run (==0), all-failed (==2), hash-success (==1), hash-processed (==0), hash-missing (==0)
    - `wc -l scripts/cleanup_stuck_docs.py` reports 120-180 lines (per LOC budget)
    - `wc -l tests/unit/test_cleanup_stuck_docs.py` reports 150-200 lines
    - LOC over-budget surfaced explicitly if it occurs (do not silently expand scope)
  </done>
</task>

<task type="auto">
  <name>Task 3: Local end-to-end smoke + commit + close-out (no test code, just operational verification)</name>
  <files>scripts/cleanup_stuck_docs.py (no edits — verification only), .dev-runtime/lightrag_storage/kv_store_doc_status.json (manual fake-doc inject + cleanup), .planning/quick/260506-rjs-phase-21-stk-02-stk-03-cleanup-stuck-doc/260506-rjs-SUMMARY.md (NEW), .planning/STATE.md (single line update), .planning/phases/21-stuck-doc-spike/21-CLOSURE.md (NEW — CONDITIONAL; see decision gate below)</files>
  <action>
    Step 1 — Local smoke flow on `.dev-runtime/` (executor MUST run this; unit tests alone are not sufficient):

    Environment same as STK-01 (no override needed; `.dev-runtime/.env` already configures Vertex Gemini). Use `venv\Scripts\python` on Windows. Do NOT reset `.dev-runtime/lightrag_storage/`.

    1. **Smoke step 1 — baseline dry-run**:
       ```
       venv\Scripts\python scripts\cleanup_stuck_docs.py --dry-run
       ```
       Expected: exit 0, JSON shows `docs_identified=0` (clean fixture).

    2. **Smoke step 2 — atomically inject fake FAILED doc** into `.dev-runtime/lightrag_storage/kv_store_doc_status.json`:
       Use a one-line Python helper inline (NOT a new committed script):
       ```
       venv\Scripts\python -c "import json,os; from pathlib import Path; p=Path('.dev-runtime/lightrag_storage/kv_store_doc_status.json'); d=json.loads(p.read_text(encoding='utf-8')); d['rjs-fake-failed-doc']={'status':'failed','chunks_count':0,'content_summary':'rjs smoke fake'}; tmp=p.with_suffix('.json.tmp'); tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8'); os.replace(tmp,p); print('injected')"
       ```
       Atomic `.tmp` + `os.replace` per CLAUDE.md convention.

    3. **Smoke step 3 — dry-run sees the fake**:
       ```
       venv\Scripts\python scripts\cleanup_stuck_docs.py --dry-run
       ```
       Expected: exit 0, JSON `docs_identified=1`, `docs_deleted=0`. CRITICAL: the CLI MUST run real `adelete_by_doc_id` against real `.dev-runtime` LightRAG state in step 4 — do NOT mock here.

    4. **Smoke step 4 — actually delete**:
       ```
       venv\Scripts\python scripts\cleanup_stuck_docs.py --all-failed
       ```
       Expected: exit 0, JSON `docs_identified=1, docs_deleted=1, docs_skipped=0`. Note: this runs real LightRAG with real Vertex Gemini config (LLM cache may be touched but no real LLM call needed for delete-only path — adelete_by_doc_id does not extract entities).

    5. **Smoke step 5 — idempotency check**:
       ```
       venv\Scripts\python scripts\cleanup_stuck_docs.py --dry-run
       ```
       Expected: exit 0, JSON `docs_identified=0` (back to baseline; fake fully removed).

    Capture all 5 JSON outputs verbatim to paste into the SUMMARY.md.

    Pre-condition: snapshot `.dev-runtime/lightrag_storage/` to a sibling `.bak-rjs-smoke-{ts}` dir BEFORE step 2, identical to STK-01 spike Step 0. If anything goes sideways, restore is `Remove-Item -Recurse + Rename-Item`. (Snapshot is untracked, can delete after smoke passes.)

    Step 2 — Write `260506-rjs-SUMMARY.md` at the quick task directory. Use the standard summary template; include:
    - Smoke flow JSON outputs (5 steps)
    - LOC actuals vs budget
    - Test count + pass result
    - Decision on 21-CLOSURE.md (see Step 4 below)
    - Any deviations / lessons (if none, say so)

    Step 3 — Update `.planning/STATE.md` `last_activity:` line to:
    ```
    2026-05-06 — Completed quick task 260506-rjs: Phase 21 STK-02 + STK-03 cleanup_stuck_docs.py CLI shipped. <N> mock-only unit tests GREEN; 5-step .dev-runtime smoke pass (inject FAILED → delete → verify clean); LOC <X>/<Y> within budget. STK-01/02/03 ops line CLOSED.
    ```
    Surgical 1-line edit only — do NOT touch other state fields.

    Step 4 — DECISION GATE for `21-CLOSURE.md` (executor judgment per planner instruction):

    Phase 21 has 5 requirements: STK-01, STK-02, STK-03, E2R-01, E2R-02. STK-01/02/03 are the ops-tooling line and become DONE after Task 1+2+3 of this plan. E2R-01 (RSS sample fixture) and E2R-02 (bench harness) hard-depend on Phase 20 RSS ingest being functional.

    **Write `21-CLOSURE.md` ONLY IF**:
    - All STK-02 + STK-03 unit tests are GREEN
    - 5-step smoke flow ran cleanly (`docs_deleted=1` observed in step 4 JSON)
    - You are confident the operator could ship this CLI to Hermes today

    **Content if writing CLOSURE.md** (frontmatter + ~30 lines):
    ```yaml
    ---
    phase: 21-stuck-doc-spike
    status: partial-closure
    closed_segments: ["STK-01", "STK-02", "STK-03"]
    deferred_segments: ["E2R-01", "E2R-02"]
    deferred_reason: "Hard-depend on Phase 20 RSS ingest functional baseline; not blocked by anything in Phase 21 scope"
    closed_date: "2026-05-06"
    ---
    ```
    Body: list closed REQs with their commits + smoke evidence; list deferred REQs with explicit "depends on Phase 20 plan landing" call-out. Do NOT mark phase status `complete` — partial-closure is honest.

    **Skip writing CLOSURE.md** if any of: any test failed, smoke step had unexpected JSON, LOC exceeded budget by >20%, executor has remaining doubt about the CLI. In that case note in SUMMARY.md "21-CLOSURE.md deferred — STK-02/03 confidence not yet at closure threshold; <reason>".

    Step 5 — Commit structure (executor commits 1; orchestrator follows with 2 — but this task documents both):

    Commit 1 (this executor):
    ```
    git add scripts/cleanup_stuck_docs.py tests/unit/test_cleanup_stuck_docs.py
    git commit -m "feat(21-stk02): scripts/cleanup_stuck_docs.py CLI + JSON report"
    ```
    Commit 2 (orchestrator after this task — handled by /gsd:quick wrapper):
    ```
    git add .planning/quick/260506-rjs-phase-21-stk-02-stk-03-cleanup-stuck-doc/260506-rjs-PLAN.md \
            .planning/quick/260506-rjs-phase-21-stk-02-stk-03-cleanup-stuck-doc/260506-rjs-SUMMARY.md \
            .planning/STATE.md
    # If 21-CLOSURE.md was written, also include:
    git add .planning/phases/21-stuck-doc-spike/21-CLOSURE.md
    git commit -m "docs(quick-260506-rjs): plan + state update for STK-02/03"
    ```
    Then `git push origin main`.

    DO NOT use `git add .` or `git add -A` — explicit file paths only per global rules.
  </action>
  <verify>
    <automated>venv/Scripts/python scripts/cleanup_stuck_docs.py --dry-run</automated>
  </verify>
  <done>
    - 5-step smoke flow ran with all expected exit codes + JSON shapes; outputs pasted in SUMMARY.md
    - `.dev-runtime/lightrag_storage/kv_store_doc_status.json` returned to baseline (no `rjs-fake-failed-doc` residue)
    - Snapshot at `.dev-runtime/lightrag_storage.bak-rjs-smoke-*` exists for rollback
    - `.planning/quick/260506-rjs-.../260506-rjs-SUMMARY.md` exists with smoke JSON outputs + LOC actuals + closure decision
    - `.planning/STATE.md` last_activity line updated (single line)
    - `.planning/phases/21-stuck-doc-spike/21-CLOSURE.md` exists IF AND ONLY IF executor judged STK-02/03 confidence at closure threshold; SUMMARY.md explicitly states the decision either way
    - Commit 1 lands on local main with message `feat(21-stk02): ...`
    - Plan + summary + STATE commit 2 follows
    - Push to origin/main succeeded; verdict reported back to user
  </done>
</task>

</tasks>

<verification>
Manual smoke (Task 3 step 1-5) is the primary E2E verification — unit tests pass on mocks but only the smoke flow against `.dev-runtime/` exercises the real `adelete_by_doc_id` integration that STK-01 verified. Both must be green for completion.

Cross-task assertions:
- `mock_rag.adelete_by_doc_id.call_count` is asserted in at least 5 separate tests with specific values (0, 1, 2). This locks down the most subtle behavior of the CLI.
- LOC budget: CLI 120-180 + tests 150-200 = 270-380 LOC total. If actual exceeds 380 LOC, executor must STOP and surface the overage in SUMMARY.md before committing.
- JSON schema fidelity: tests call `json.loads(captured_stdout)` then check all 5 keys exist + types match. Schema definition is the single source in the CLI module — tests import it.
</verification>

<success_criteria>
1. `scripts/cleanup_stuck_docs.py` exists with --dry-run / --all-failed / --hash flags; no-flag → help + exit 0
2. JSON report on stdout has exactly 5 schema keys (`docs_identified`, `docs_deleted`, `docs_skipped`, `skipped_reasons`, `elapsed_ms`) on every successful invocation
3. PROCESSED docs are NEVER passed to `adelete_by_doc_id` (asserted in tests; verifiable by reading `_filter_candidates` source)
4. Active-pipeline-lock detection emits stderr advisory only; never hard-fails (asserted in `test_pipeline_busy_advisory_emits_stderr_does_not_block`)
5. Exit codes: 0 on dry-run / nothing-to-clean / all-cleaned / idempotent-missing-hash; 1 on attempt-to-delete-processed-doc and on unexpected exception
6. 13+ mock-only unit tests in `tests/unit/test_cleanup_stuck_docs.py` GREEN
7. 5-step `.dev-runtime/` smoke flow ran with `docs_deleted=1` observed in step 4 JSON; baseline restored in step 5
8. LOC budget honored (CLI 120-180, tests 150-200) — overage surfaced explicitly if it occurs
9. SUMMARY.md exists with smoke JSON outputs + LOC actuals + closure decision
10. STATE.md last_activity line updated; commit 1 + commit 2 + push to origin/main complete
</success_criteria>

<output>
After completion, create `.planning/quick/260506-rjs-phase-21-stk-02-stk-03-cleanup-stuck-doc/260506-rjs-SUMMARY.md` with:
- Smoke flow JSON outputs (5 steps verbatim)
- LOC actuals (`wc -l` on both files)
- Test count + pass/fail result
- Decision on 21-CLOSURE.md (write or defer + reason)
- Deviations / lessons (if any)
- Self-check section confirming all `<done>` items in each task

If `21-CLOSURE.md` written, also confirm STK-01/02/03 closed in REQUIREMENTS.md note (no edits needed there — closure is a doc-only artifact).
</output>
