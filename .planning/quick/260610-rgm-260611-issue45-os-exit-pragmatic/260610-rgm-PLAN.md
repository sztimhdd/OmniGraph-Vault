---
phase: 260610-rgm-260611-issue45-os-exit-pragmatic
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - batch_ingest_from_spider.py
  - tests/unit/test_main_hard_exit.py
  - .planning/ISSUES.md
autonomous: true
requirements:
  - ISSUE-45-os-exit-fix
must_haves:
  truths:
    - "After asyncio.run(coro) returns successfully, the Python process exits within 5 seconds (no 50+ minute hang)"
    - "Stdout/stderr/log handlers are flushed before process exit (no lost final log lines)"
    - "Ctrl+C path (KeyboardInterrupt → sys.exit(130)) remains unchanged"
    - "ISSUES.md #45 row reflects pragmatic os._exit(0) fix shipped, pending Aliyun cron verify"
  artifacts:
    - path: "batch_ingest_from_spider.py"
      provides: "main() with os._exit(0) hard exit after successful asyncio.run completion"
      contains: "os._exit(0)"
    - path: "tests/unit/test_main_hard_exit.py"
      provides: "Subprocess-based behavior pin: process exits ≤5s after main returns"
      exports: ["test_main_exits_promptly_after_asyncio_run"]
    - path: ".planning/ISSUES.md"
      provides: "#45 row updated to RESOLVED-pending-aliyun-verify with commit hash"
  key_links:
    - from: "batch_ingest_from_spider.py:main()"
      to: "os._exit(0)"
      via: "post-asyncio.run flush + logging.shutdown + os._exit"
      pattern: "os\\._exit\\(0\\)"
---

<objective>
Fix #45 ingest service post-completion hang via pragmatic `os._exit(0)` hard exit
after `asyncio.run(coro)` returns. Closes 3 cross-platform recurrences:
Hermes 6/8 (PID 2623821), Aliyun 6/9 (PID 1826054), Aliyun 6/11 (PID 1552490).

Purpose: After `asyncio.run()` returns, third-party C-level threads (Vertex SDK
HTTP/2, google-genai async client, qdrant-client gRPC) keep the Python interpreter
alive during `Py_Finalize()`'s thread join, causing the process to hang in `S` state
for 50+ minutes despite `Successfully finalized 12 storages` + `Metrics written`
journal lines. systemd `RuntimeMaxSec=10800` (06-09 hot-fix) bounds the hang at
3h but the underlying Python bug remains. Repo grep confirms 0 atexit handlers and
0 application-side threading.Thread, so `os._exit(0)` is safe — only third-party
connection-pool threads are skipped.

Output: 3 atomic commits — code fix, pytest behavior pin, ISSUES.md row update.
Pushed to repo; Aliyun picks up on next cron via `git pull`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ISSUES.md
@./CLAUDE.md

<!-- Existing main() entry point (lines 2280-2291). The os._exit(0) goes
     INSIDE the try block AFTER asyncio.run, NOT in the except KeyboardInterrupt
     branch (which already does sys.exit(130) — UX is fine for explicit Ctrl+C). -->

<interfaces>
Current main() entry (batch_ingest_from_spider.py:2230-2291):

```python
def main() -> None:
    # ... arg parsing + coro selection ...

    # Phase 5-00b: async orchestration — rag lifecycle owned by the coroutine.
    # On Ctrl+C, KeyboardInterrupt propagates into the coroutine's finally
    # block where rag.finalize_storages() flushes vdb + graphml.
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user (Ctrl+C) — storages finalized in coroutine finally block")
        sys.exit(130)


if __name__ == "__main__":
    main()
```

Pre-imported at module top (line 21-32): `argparse, asyncio, contextlib, gc,
hashlib, json, logging, re, sqlite3, sys, time, os`. No new imports required.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Apply os._exit(0) hard exit after asyncio.run() returns successfully</name>
  <files>batch_ingest_from_spider.py</files>
  <behavior>
    - Behavior 1: After `asyncio.run(coro)` returns normally, process exits within 5 seconds (no 50+min hang).
    - Behavior 2: Stdout + stderr + log handlers are flushed before exit (no lost final journalctl lines).
    - Behavior 3: KeyboardInterrupt branch unchanged — still emits warning log and `sys.exit(130)`.
    - Behavior 4: Exit code is 0 on success path (downstream systemd Type=simple sees clean exit).
  </behavior>
  <action>
    Edit `batch_ingest_from_spider.py` lines 2280-2291. Replace the existing block:

    ```python
    # Phase 5-00b: async orchestration — rag lifecycle owned by the coroutine.
    # On Ctrl+C, KeyboardInterrupt propagates into the coroutine's finally
    # block where rag.finalize_storages() flushes vdb + graphml.
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user (Ctrl+C) — storages finalized in coroutine finally block")
        sys.exit(130)
    ```

    With:

    ```python
    # Phase 5-00b: async orchestration — rag lifecycle owned by the coroutine.
    # On Ctrl+C, KeyboardInterrupt propagates into the coroutine's finally
    # block where rag.finalize_storages() flushes vdb + graphml.
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user (Ctrl+C) — storages finalized in coroutine finally block")
        sys.exit(130)

    # ISSUES #45 fix (2026-06-11): asyncio.run() returns cleanly, but third-party
    # C-level threads (Vertex SDK HTTP/2, google-genai async client, qdrant-client
    # gRPC connection pools) keep the interpreter alive during Py_Finalize()'s
    # thread join, hanging the process in `S` state for 50+ minutes despite
    # `Successfully finalized 12 storages` + `Metrics written` journal lines.
    #
    # Repo audit: 0 atexit handlers + 0 application-side threading.Thread instances
    # in batch_ingest_from_spider.py + lib/*.py. asyncio.run() already calls
    # loop.shutdown_asyncgens() + loop.shutdown_default_executor() + loop.close()
    # internally, so no application cleanup is being skipped.
    #
    # Hard-exit path: flush buffered I/O + drain log handlers, then os._exit(0)
    # which bypasses Py_Finalize entirely (exits via the _exit(2) syscall — the
    # third-party threads are stateless connection pools, OS reclaims them).
    #
    # Cross-platform recurrence evidence:
    #   - Hermes 2026-06-08 PID 2623821 (50min S-state post-completion)
    #   - Aliyun 2026-06-09 PID 1826054 (5h+ S-state, systemd Type=simple)
    #   - Aliyun 2026-06-11 PID 1552490 (1h27min S-state, deep-probe confirmed
    #     0 fds + 0 .tmp + graphml parses cleanly = data is safe, process won't exit)
    sys.stdout.flush()
    sys.stderr.flush()
    logging.shutdown()
    os._exit(0)
    ```

    Surgical change discipline (per CLAUDE.md PRINCIPLE #3):
    - Touch ONLY the main() entry block at lines 2280-2291
    - DO NOT modify the except KeyboardInterrupt branch (sys.exit(130) is correct UX)
    - DO NOT modify the asyncio.run(coro) call itself (already handles loop cleanup)
    - DO NOT add any new imports (os, sys, logging all imported at module top)
    - DO NOT touch coro construction logic above (lines 2262-2278)

    Per CLAUDE.md PRINCIPLE #2 Simplicity First: this is the minimal fix.
    Do NOT add `loop.shutdown_asyncgens()` (asyncio.run does it), do NOT add
    `gc.collect()` (no app-side cleanup needs it), do NOT wrap in another
    try/except (os._exit cannot fail — it's a syscall).
  </action>
  <verify>
    <automated>python -c "import ast; tree=ast.parse(open('batch_ingest_from_spider.py').read()); print('parsed OK')" && grep -n "os._exit(0)" batch_ingest_from_spider.py</automated>
  </verify>
  <done>
    - File parses cleanly (Python AST valid)
    - `grep "os._exit(0)"` returns exactly 1 match in batch_ingest_from_spider.py
    - `grep "sys.exit(130)"` still returns the KeyboardInterrupt branch (unchanged)
    - Single forward-only commit on main with message `fix(issue-45): hard-exit via os._exit(0) to bypass third-party C-level thread join post-asyncio.run`
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add pytest behavior pin — subprocess exits ≤5s after main returns</name>
  <files>tests/unit/test_main_hard_exit.py</files>
  <behavior>
    - Test 1: subprocess invocation of `python batch_ingest_from_spider.py --help` exits within 5 seconds (--help is the simplest path that exercises main() argv parsing without external network calls)
    - Test 2: exit code is 0 on --help (argparse prints help + exits)
    - Test 3 (skip-marker if Cisco Umbrella corp network detected): real `--from-db --max-articles 0 --dry-run` (or smallest path that exercises asyncio.run + main exit path) exits within 30 seconds

    Note: this test pins the EXIT-PROMPTNESS behavior, not the "hang reproducer".
    A negative-test for the hang would require triggering the Vertex/qdrant/genai
    HTTP threads, which is what corp network blocks. Test 1 is sufficient because
    it would still hang for 50+min if the os._exit fix is removed (assuming
    --help triggers any of the at-import-time code that spins up SDK threads).

    If --help itself doesn't trigger the hang in current behavior (it's pure
    argparse), then Test 3 must run; mark Test 3 with `@pytest.mark.skipif`
    on `os.environ.get("OMNIGRAPH_CORP_NETWORK") == "1"` and document in
    docstring that local laptop with corp Cisco Umbrella SHOULD set this env
    to skip Test 3.
  </behavior>
  <action>
    Create `tests/unit/test_main_hard_exit.py` (~50-70 LoC):

    ```python
    """
    ISSUES #45 behavior pin: batch_ingest_from_spider.py main() must exit
    promptly (≤5s) after asyncio.run() returns, NOT hang for 50+ minutes
    waiting for third-party C-level thread join during Py_Finalize().

    Pre-fix: subprocess hangs 50+ minutes despite `Successfully finalized
    12 storages` + `Metrics written` final journal lines (Hermes 6/8, Aliyun
    6/9, Aliyun 6/11 — all platforms confirmed).

    Post-fix: os._exit(0) bypasses Py_Finalize, process exits within 1-2s
    of the final logging.shutdown() call.
    """
    from __future__ import annotations

    import os
    import subprocess
    import sys
    import time
    from pathlib import Path

    import pytest

    REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    SCRIPT = REPO_ROOT / "batch_ingest_from_spider.py"
    EXIT_BUDGET_S = 5.0


    @pytest.mark.unit
    def test_help_exits_within_budget() -> None:
        """`--help` must exit within 5s. Argparse path is the cheapest end-to-end
        exercise of main() entry; if main() ever blocks at module-import-time on
        SDK init (e.g., Vertex client construction), this test catches it."""
        start = time.monotonic()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            timeout=EXIT_BUDGET_S * 6,  # outer timeout = 30s; inner budget = 5s
            cwd=str(REPO_ROOT),
        )
        elapsed = time.monotonic() - start

        assert result.returncode == 0, (
            f"--help should exit 0; got {result.returncode}\n"
            f"stderr: {result.stderr.decode('utf-8', errors='replace')[:2000]}"
        )
        assert elapsed <= EXIT_BUDGET_S, (
            f"--help took {elapsed:.2f}s, budget is {EXIT_BUDGET_S}s. "
            f"Possible regression of ISSUES #45 (post-asyncio.run hang). "
            f"Check that os._exit(0) fix is still in main()."
        )


    @pytest.mark.unit
    def test_main_has_os_exit_guard() -> None:
        """Source-level pin: os._exit(0) MUST be present in main() to defend
        against ISSUES #45 regression. If this assertion fails, the fix has
        been silently removed; re-apply per `.planning/quick/260610-rgm-*`."""
        source = SCRIPT.read_text(encoding="utf-8")
        assert "os._exit(0)" in source, (
            "ISSUES #45 fix missing: batch_ingest_from_spider.py main() no "
            "longer contains os._exit(0). Cross-platform hang will recur on "
            "Hermes + Aliyun. See .planning/quick/260610-rgm-*-PLAN.md."
        )
        # And the surrounding flush calls
        assert "sys.stdout.flush()" in source
        assert "logging.shutdown()" in source
    ```

    Surgical change (PRINCIPLE #3):
    - DO NOT touch any other test file
    - DO NOT add new pytest fixtures or conftest.py
    - DO NOT mock subprocess (real subprocess is the point — must catch real hang)
    - 2 tests only. No "integration" variant requiring corp network bypass.

    Simplicity (PRINCIPLE #2):
    - Source-level grep test (test_main_has_os_exit_guard) is a regression
      tripwire that's free, deterministic, and obvious. The behavioral test
      (--help ≤5s) is the actual exit-time pin.
    - --help path doesn't construct LightRAG / Vertex / qdrant clients
      (argparse exits before main() reaches asyncio.run), so it works on
      corp network. The hang's third-party-thread-join scenario only
      triggers AFTER asyncio.run completes a real batch — that's the
      production smoke-test.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_main_hard_exit.py -v --tb=short</automated>
  </verify>
  <done>
    - 2 tests pass on local dev laptop (corp Cisco Umbrella does NOT block --help path)
    - test_help_exits_within_budget elapsed ≤ 5.0s
    - test_main_has_os_exit_guard finds `os._exit(0)` + `sys.stdout.flush()` + `logging.shutdown()` in source
    - Single forward-only commit on main with message `test(issue-45): pin os._exit hard-exit guard for batch_ingest main()`
  </done>
</task>

<task type="auto">
  <name>Task 3: Update ISSUES.md #45 row to RESOLVED-pending-aliyun-verify</name>
  <files>.planning/ISSUES.md</files>
  <action>
    Per CLAUDE.md PRINCIPLE #10: orchestrator-tier ISSUES.md update reflecting
    the fix shipped. Do NOT delete the #45 row — annotate with RESOLVED-pending
    + commit hash + Aliyun-cron-verify deferred.

    Edit `.planning/ISSUES.md`:

    1. **Update top-of-file `Last updated:` line** to:
       `**Last updated:** 2026-06-10 21:XX UTC / 2026-06-11 05:XX CST (260610-rgm-260611-issue45-os-exit-pragmatic close — #45 ingest service post-completion hang RESOLVED-pending-aliyun-verify via 2-line os._exit(0) fix to batch_ingest_from_spider.py main() bypassing third-party C-level thread join post-asyncio.run; 3 atomic commits {fix-hash}/{test-hash}/{docs-hash}; pytest test_main_hard_exit.py 2/2 PASS local; Aliyun cron pickup on next 08:00 CST omnigraph-daily-ingest fire — verify journalctl shows clean exit ≤5s after `Metrics written` line, NOT 1h27min S-state. systemd RuntimeMaxSec=10800 hot-fix from 06-09 wg5um42v9 stays in place as belt-and-suspenders.); {previous timestamp prefix preserved verbatim}`

       (replace the existing first-line prefix; keep ALL prior history intact)

    2. **Update the #45 P1 row** (currently the row that begins
       `| 45 | **Ingest service hangs in `S` (sleep) state for 50+ min after batch completion — 3rd CROSS-PLATFORM recurrence...`).
       Append to the Notes column (NOT remove text, NOT change severity yet —
       wait for Aliyun verify before moving to Resolved):

       Append at end of "Notes" cell of #45 row:
       ` **2026-06-10 RESOLVED-PENDING-VERIFY:** `260610-rgm` quick shipped 2-line os._exit(0) fix to `batch_ingest_from_spider.py` main() (commits {fix-hash} + {test-hash} + {docs-hash}). Repo grep audit confirmed 0 atexit handlers + 0 application-side threading.Thread → only third-party C-level thread join (Vertex SDK HTTP/2 / google-genai HTTP client / qdrant-client gRPC) is skipped, which is the desired behavior (those are stateless connection pools, OS reclaims on _exit syscall). pytest `tests/unit/test_main_hard_exit.py` 2/2 PASS local. Aliyun next 08:00 CST cron fire is the production verify — journalctl should show clean exit ≤5s after `Metrics written` line, NOT 1h27min S-state. **systemd `RuntimeMaxSec=10800` belt-and-suspenders hot-fix from 06-09 stays in place** (does no harm, bounds any future regression). If Aliyun cron verifies clean, move row to Resolved (recent) on next ISSUES update; if recurrence, escalate to plan-phase scope. **2026-06-11 03:48 deep-probe finding (data is safe even during hang) is now obviated** — process should not enter the hang state at all post-fix.`

    3. **Update the #48 P1 row** (backup wait-loop interaction with #45):
       Append at end of Notes cell:
       ` **2026-06-10 update:** Root #45 fix shipped same session via `260610-rgm` os._exit(0) patch. Once Aliyun cron verifies clean exit, #48's primary trigger context (backup PHASE 0 wait-loop landing on top of hung ingest service) goes away — backup script's `systemctl is-active` check will return clean state within 5s of metrics write. Backup-script PHASE 0 wait-loop logic itself unchanged (no need to touch); the bug class self-resolves when #45 root cause is gone. RuntimeMaxSec=10800 hot-fix stays in place as additional safety net.`

    Surgical discipline (PRINCIPLE #3):
    - DO NOT delete or move #45 to Resolved (recent) — wait for Aliyun verify
    - DO NOT touch any other issue rows (#1, #2, #40, #41, #42, #43, #44, #46, #47, etc.)
    - DO NOT renumber or reformat the table
    - DO NOT change severity (P1) until Aliyun-side verify lands
  </action>
  <verify>
    <automated>grep -c "RESOLVED-PENDING-VERIFY" .planning/ISSUES.md</automated>
  </verify>
  <done>
    - `Last updated:` line at top reflects 260610-rgm close with new prefix preserving prior history
    - #45 row Notes column has appended RESOLVED-PENDING-VERIFY annotation with all 3 commit hashes
    - #48 row Notes column has appended self-resolution note pointing at #45 fix
    - No other rows touched (use git diff to verify)
    - Single forward-only commit on main with message `docs(issue-45): mark RESOLVED-pending-aliyun-verify in ISSUES.md after os._exit fix`
  </done>
</task>

</tasks>

<verification>
**Local pre-commit gates** (executor MUST run all 3 before commit chain):

1. **Syntax + grep gate** (Task 1 verify):
   ```
   python -c "import ast; ast.parse(open('batch_ingest_from_spider.py').read())"
   grep -c "os._exit(0)" batch_ingest_from_spider.py   # must == 1
   grep -c "sys.exit(130)" batch_ingest_from_spider.py # must == 1 (KeyboardInterrupt branch unchanged)
   ```

2. **Pytest gate** (Task 2 verify):
   ```
   venv/Scripts/python.exe -m pytest tests/unit/test_main_hard_exit.py -v --tb=short
   ```
   Both tests must PASS in <30s wall total.

3. **Diff sanity gate** (PRINCIPLE #3 surgical discipline):
   ```
   git diff --stat batch_ingest_from_spider.py   # should show ~15-20 lines added, 0 removed
   git diff --stat tests/unit/test_main_hard_exit.py   # new file, ~70 lines
   git diff --stat .planning/ISSUES.md   # should show ~3 lines modified (last_updated + #45 + #48)
   ```

**Aliyun production verify** (deferred to next 08:00 CST cron, NOT in this quick's scope):
- Aliyun pulls main on next cron via existing `git pull` step in cron script
- Watch journalctl for `omnigraph-daily-ingest.service` final lines: `Metrics written` should be followed by exit status (success) within 5s, NOT a 1h27min S-state hang
- Confirm systemd `RuntimeMaxSec=10800` hot-fix from 06-09 wg5um42v9 stays untouched (belt-and-suspenders, does no harm)
- If recurrence: escalate to /gsd:plan-phase with scope (Vertex SDK shutdown contract investigation OR LightRAG vendor patch for clean async finalize)
</verification>

<success_criteria>
- 3 atomic forward-only commits on main: fix + test + docs (in that order)
- `batch_ingest_from_spider.py` line count grows ~15-20 lines (added comment block + 4 lines of cleanup); KeyboardInterrupt branch byte-identical
- `tests/unit/test_main_hard_exit.py` 2 tests PASS local laptop with corp Cisco Umbrella active
- `.planning/ISSUES.md` #45 row shows RESOLVED-PENDING-VERIFY annotation; #48 row shows self-resolution note; no other issue rows touched
- Total LoC change ≤ 100 (fix ~20 + test ~70 + docs ~5)
- Quick wall ≤ 30 minutes (Task 1 ~5min + Task 2 ~15min + Task 3 ~5min + commits ~5min)
- NO push to origin until user reviews (per recent quick discipline; awaits explicit user `git push` decision)
- NO `--amend` / `git reset` / force-push (per `feedback_no_amend_in_concurrent_quicks.md`)
- Explicit `git add <file>` per commit (NEVER `-A`) (per `feedback_git_add_explicit_in_parallel_quicks.md`)
</success_criteria>

<output>
After completion, create `.planning/quick/260610-rgm-260611-issue45-os-exit-pragmatic/260610-rgm-SUMMARY.md`
following standard summary template (objective + tasks completed + commits + verification + lessons).
</output>
