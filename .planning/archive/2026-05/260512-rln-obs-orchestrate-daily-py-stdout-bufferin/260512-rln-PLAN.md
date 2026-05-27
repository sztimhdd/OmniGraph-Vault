---
phase: quick-260512-rln
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - enrichment/orchestrate_daily.py
  - lib/lightrag_queue_probe.py
  - tests/unit/test_lightrag_queue_probe.py
autonomous: true
requirements:
  - OBS-RLN-01  # drop capture_output in orchestrate_daily._run so child stdout/stderr stream to tee
  - OBS-RLN-02  # add 1 logger.info in compute_dynamic_budget so gqu Pattern A burst is grep-able
  - OBS-RLN-03  # add 1 caplog test verifying the new logger.info fires

must_haves:
  truths:
    - "enrichment/orchestrate_daily.py:_run() no longer passes capture_output=True or text=True"
    - "enrichment/orchestrate_daily.py:_run() passes env={**os.environ, 'PYTHONUNBUFFERED': '1'} to subprocess.run"
    - "lib/lightrag_queue_probe.py:compute_dynamic_budget() emits exactly one logger.info containing 'gqu Pattern A' AND 'queue_depth' AND the effective budget"
    - "compute_dynamic_budget() return value is unchanged (same min/max math, just extracted into a local before logging)"
    - "tests/unit/test_lightrag_queue_probe.py has 1 new caplog-based test asserting the logger.info string"
    - "pytest tests/unit/test_lightrag_queue_probe.py -v reports 7 tests collected, all PASS (was 6)"
    - "python -m py_compile enrichment/orchestrate_daily.py lib/lightrag_queue_probe.py exits 0"
    - "no caller in enrichment/ or tests/ parses StepResult.detail string content (verified by grep)"
    - "single git commit stages exactly the 3 listed files (no -A, no sibling files)"
  artifacts:
    - path: "enrichment/orchestrate_daily.py"
      provides: "_run() with streamed child output + PYTHONUNBUFFERED=1"
      contains: "PYTHONUNBUFFERED"
    - path: "lib/lightrag_queue_probe.py"
      provides: "compute_dynamic_budget with gqu Pattern A logger.info"
      contains: "gqu Pattern A"
    - path: "tests/unit/test_lightrag_queue_probe.py"
      provides: "caplog-based test for the new logger.info"
      contains: "caplog"
  key_links:
    - from: "enrichment/orchestrate_daily.py:_run"
      to: "subprocess.run"
      via: "no capture_output, env injects PYTHONUNBUFFERED=1"
      pattern: "PYTHONUNBUFFERED"
    - from: "lib/lightrag_queue_probe.py:compute_dynamic_budget"
      to: "logger.info"
      via: "single new logger.info before return"
      pattern: "gqu Pattern A"
    - from: "tests/unit/test_lightrag_queue_probe.py"
      to: "lib.lightrag_queue_probe.compute_dynamic_budget"
      via: "pytest caplog fixture"
      pattern: "caplog"
---

<objective>
Land a small, surgical observability fix as one atomic quick commit:

1. Drop `capture_output=True` in `enrichment/orchestrate_daily.py:_run()` so child subprocess stdout/stderr streams directly to the parent terminal/tee. Hermes 2026-05-12 evening manual fire confirmed `capture_output=True` silently swallowed orchestrate sub-step logs.

2. Add ONE `logger.info` line at the end of `lib/lightrag_queue_probe.py:compute_dynamic_budget()` so tomorrow morning's 09:00 ADT cron makes gqu Pattern A burst activation directly grep-able (bcy quick 178dd6e shipped the budget logic but added zero log lines — current state is "infer via external sampling of kv_store_doc_status.json").

3. Add ONE pytest `caplog`-based test verifying the new logger.info string contains "gqu Pattern A" and "queue_depth".

Purpose: Make the next 09:00 ADT cron the validation site for gqu Pattern A by giving operators a grep target, and unblock orchestrate-daily debugging by letting child sub-step logs reach the operator's tee/terminal.

Output: 3 modified files, 1 atomic commit, 7/7 unit tests PASS, no push.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@enrichment/orchestrate_daily.py
@lib/lightrag_queue_probe.py
@tests/unit/test_lightrag_queue_probe.py

<interfaces>
<!-- Key call sites and contracts the executor needs. -->

From enrichment/orchestrate_daily.py (current target — lines 54-75):
```python
def _run(cmd: list[str], dry_run: bool, critical: bool = False) -> StepResult:
    logger.info("%sRUN: %s", "DRY " if dry_run else "", " ".join(cmd))
    if dry_run:
        return StepResult(True, f"dry: {' '.join(cmd)}")
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,    # ← DROP
            text=True,              # ← DROP
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
        if r.returncode != 0:
            return StepResult(
                False,
                f"exit={r.returncode} stderr={r.stderr[:500]}",   # ← simplify (no r.stderr without capture_output)
                critical=critical,
            )
        return StepResult(True, r.stdout[:500])                    # ← simplify (no r.stdout without capture_output)
    except subprocess.TimeoutExpired:
        return StepResult(False, "timeout", critical=critical)
    except Exception as ex:
        return StepResult(False, f"exception: {ex}", critical=critical)
```

`import os` IS already present at line 26. No new import needed.

`StepResult` is a dataclass at lines 46-51:
```python
@dataclass
class StepResult:
    success: bool
    summary: str
    critical: bool = False
    next_step: str | None = None
```

From lib/lightrag_queue_probe.py (current target — lines 46-72):
```python
def compute_dynamic_budget(
    doc_status: dict[str, Any] | None = None,
    *,
    base_budget_s: float = 300.0,
    per_doc_avg_s: float = 60.0,
    cap_s: float = 1800.0,
) -> float:
    """..."""
    if doc_status is None:
        queue_depth = read_queue_depth()
    else:
        queue_depth = sum(
            1
            for d in doc_status.values()
            if isinstance(d, dict) and d.get("status") == "processing"
        )
    candidate = max(base_budget_s, queue_depth * per_doc_avg_s)
    return float(min(candidate, cap_s))   # ← extract `effective` local + add logger.info before return
```

`logger = logging.getLogger(__name__)` is already at line 16. No new import.

From tests/unit/test_lightrag_queue_probe.py:
- 6 existing tests (lines 12-62)
- Uses `pytest.mark.unit` decorator
- Imports already present: `from lib.lightrag_queue_probe import compute_dynamic_budget, read_queue_depth`
- pytest `caplog` fixture is stdlib pytest — no new import.
</interfaces>

<out_of_scope>
The plan must NOT do any of these:
- Refactor _run() logic broadly (e.g. Popen + streaming, signal handling, partial-output capture)
- Touch any other step_* function in orchestrate_daily.py
- Change SUBPROCESS_TIMEOUT_SECONDS or add an env override for it
- Change read_queue_depth() in lightrag_queue_probe.py
- Add OMNIGRAPH_PER_DOC_AVG_S or any other env override to compute_dynamic_budget
- Add metrics / dashboard / observability scaffolding
- Modify ingest_wechat.py or any other caller of compute_dynamic_budget
- Push to remote, SSH to Hermes, or mutate any prod state
- Run `git add -A` or `git add .` — must use explicit file list (concurrent-quick staging-race protection per CLAUDE.md 2026-05-11 lesson)
- Amend, soft-reset, or otherwise rewrite any commit (parallel-GSD safety)
- Add a "metadata" or "next_step" field to StepResult
- Touch any other test file in tests/unit/
</out_of_scope>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Edit _run() + compute_dynamic_budget + add caplog test, single commit</name>
  <files>
    enrichment/orchestrate_daily.py,
    lib/lightrag_queue_probe.py,
    tests/unit/test_lightrag_queue_probe.py
  </files>

  <behavior>
    Test expectations to satisfy (one new caplog test added; six existing tests untouched):

    - **NEW test_compute_dynamic_budget_emits_pattern_a_log_line** (uses pytest `caplog` fixture):
        - Set `caplog.set_level(logging.INFO, logger="lib.lightrag_queue_probe")` (or just INFO globally — `caplog.at_level(logging.INFO)`).
        - Call `compute_dynamic_budget({"d0": {"status": "processing"}, "d1": {"status": "processing"}}, base_budget_s=300.0, per_doc_avg_s=60.0, cap_s=1800.0)`.
        - Assert return value is exactly `300.0` (queue_depth=2, 2*60=120, max(300,120)=300, min(300,1800)=300).
        - Assert `caplog.records` contains exactly one INFO record from logger `lib.lightrag_queue_probe`.
        - Assert that record's formatted message contains all of: `"gqu Pattern A"`, `"queue_depth=2"`, `"effective_budget_s=300"`.
    - All 6 existing tests still pass (do NOT modify them).

    Implementation expectations (post-edit, by file):

    - **enrichment/orchestrate_daily.py:_run()**: no `capture_output`, no `text` kwarg, env passed = `{**os.environ, "PYTHONUNBUFFERED": "1"}`, returncode!=0 returns `StepResult(False, f"exit={r.returncode}", critical=critical)`, returncode==0 returns `StepResult(True, "ok")`, dry-run path unchanged (`StepResult(True, f"dry: {' '.join(cmd)}")`), TimeoutExpired returns `StepResult(False, "timeout", critical=critical)` (unchanged), generic Exception returns `StepResult(False, f"exception: {ex}", critical=critical)` (unchanged), and a `# NOTE:` comment cites 2026-05-12 Hermes evening fire as the rationale.
    - **lib/lightrag_queue_probe.py:compute_dynamic_budget()**: `effective` local extracted, single `logger.info("gqu Pattern A: queue_depth=%d effective_budget_s=%.0f base=%.0f cap=%.0f", queue_depth, effective, base_budget_s, cap_s)` before `return effective`. Math result unchanged from prior `float(min(candidate, cap_s))`.
  </behavior>

  <action>
    Implement RED → GREEN in three file edits, then a single atomic commit.

    ### Step A — write the failing test first (RED)

    Edit `tests/unit/test_lightrag_queue_probe.py`. Append this new test at the end of the file (after the existing `test_fixture_busy_has_real_processing_docs`):

    ```python
    @pytest.mark.unit
    def test_compute_dynamic_budget_emits_pattern_a_log_line(caplog):
        """gqu Pattern A burst activation must be directly grep-able via 'gqu Pattern A' marker."""
        import logging as _logging
        caplog.set_level(_logging.INFO, logger="lib.lightrag_queue_probe")
        ds = {"d0": {"status": "processing"}, "d1": {"status": "processing"}}
        budget = compute_dynamic_budget(
            ds, base_budget_s=300.0, per_doc_avg_s=60.0, cap_s=1800.0
        )
        # Math sanity: queue_depth=2, 2*60=120, max(300,120)=300, min(300,1800)=300
        assert budget == 300.0
        # Exactly one INFO record from the probe module
        records = [r for r in caplog.records if r.name == "lib.lightrag_queue_probe"]
        assert len(records) == 1, f"expected 1 INFO record, got {len(records)}"
        msg = records[0].getMessage()
        assert "gqu Pattern A" in msg, f"missing marker: {msg!r}"
        assert "queue_depth=2" in msg, f"missing queue_depth: {msg!r}"
        assert "effective_budget_s=300" in msg, f"missing effective_budget_s: {msg!r}"
    ```

    Run `venv/Scripts/python -m pytest tests/unit/test_lightrag_queue_probe.py::test_compute_dynamic_budget_emits_pattern_a_log_line -v` and confirm it FAILS with an assertion error on the `len(records) == 1` line (because the logger.info doesn't exist yet). This is the RED gate.

    ### Step B — implement compute_dynamic_budget logger.info (GREEN for new test)

    Edit `lib/lightrag_queue_probe.py` lines 71-72. Current end of function:

    ```python
        candidate = max(base_budget_s, queue_depth * per_doc_avg_s)
        return float(min(candidate, cap_s))
    ```

    Replace with:

    ```python
        candidate = max(base_budget_s, queue_depth * per_doc_avg_s)
        effective = float(min(candidate, cap_s))
        logger.info(
            "gqu Pattern A: queue_depth=%d effective_budget_s=%.0f base=%.0f cap=%.0f",
            queue_depth, effective, base_budget_s, cap_s,
        )
        return effective
    ```

    Math is identical (just extracted into `effective` local). Per OBS-RLN-02: surgical, 1 line of new logging, no other logic change.

    Re-run the new test — it must now PASS. All 6 existing tests must still PASS (existing tests don't inspect logs, so adding logger.info won't break them).

    ### Step C — drop capture_output in orchestrate_daily._run() (OBS-RLN-01)

    Edit `enrichment/orchestrate_daily.py` lines 54-75. `import os` is already present at line 26 — confirm before editing; if missing, add it. Replace the entire `_run` function body with:

    ```python
    def _run(cmd: list[str], dry_run: bool, critical: bool = False) -> StepResult:
        logger.info("%sRUN: %s", "DRY " if dry_run else "", " ".join(cmd))
        if dry_run:
            return StepResult(True, f"dry: {' '.join(cmd)}")
        try:
            # NOTE: do NOT capture_output — let child stdout/stderr stream directly
            # to the parent (terminal / tee). 2026-05-12 Hermes evening manual fire
            # confirmed capture_output=True silently swallowed orchestrate sub-step
            # logs. PYTHONUNBUFFERED=1 forces Python child line-flush so tee sees
            # progress in real time.
            r = subprocess.run(
                cmd,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            if r.returncode != 0:
                return StepResult(False, f"exit={r.returncode}", critical=critical)
            return StepResult(True, "ok")
        except subprocess.TimeoutExpired:
            return StepResult(False, "timeout", critical=critical)
        except Exception as ex:
            return StepResult(False, f"exception: {ex}", critical=critical)
        ```

    Caller-impact note: `StepResult.detail` (well, `.summary`) field for the success path goes from "first 500 chars stdout" to literal "ok"; failure path goes from "exit=N stderr=..." to literal "exit=N". Step B grep below verifies no caller parses `.summary` content.

    ### Step D — verification gate sweep

    Run, in order:

    1. `venv/Scripts/python -m py_compile enrichment/orchestrate_daily.py lib/lightrag_queue_probe.py` — must exit 0 (syntax sane).
    2. `venv/Scripts/python -m pytest tests/unit/test_lightrag_queue_probe.py -v` — must report `7 passed` (6 existing + 1 new).
    3. PowerShell: `Select-String -Path "enrichment\*.py","tests\**\*.py" -Pattern "\.summary\b|StepResult\("` — confirm visually that no caller does string parsing on `.summary` content (e.g. `.summary.startswith(...)`, `.summary.split(...)`, `re.match(.., r.summary)`). The orchestrator only logs `r.summary[:200]` for human display, and step_9 reads `step_8_result.summary[:300]` to embed in a Telegram alert — both display-only, no parsing. Document this in the SUMMARY.
    4. Manual eyeball: `_run([str(PYTHON), "echo", "hi"], dry_run=True)` would still return `StepResult(True, "dry: venv/bin/python echo hi")` — back-compat preserved.

    ### Step E — single atomic commit (per CLAUDE.md 2026-05-11 lmc/lmx lesson: explicit file list, never -A)

    ```bash
    git add enrichment/orchestrate_daily.py lib/lightrag_queue_probe.py tests/unit/test_lightrag_queue_probe.py
    git status   # confirm exactly 3 files staged, no siblings
    git commit -m "$(cat <<'EOF'
    chore(observability): drop capture_output in orchestrate _run + log Pattern A budget activation

    Two surgical observability fixes merged into one quick:

    1. enrichment/orchestrate_daily.py:_run() — drop capture_output=True/text=True
       and inject PYTHONUNBUFFERED=1 into the child env. Hermes 2026-05-12 evening
       manual orchestrate fire confirmed capture_output=True silently swallowed
       sub-step logs from tee. StepResult.summary content now "ok" / "exit=N"
       (no caller parses it — display-only via logger.info "%s ... summary=%s").

    2. lib/lightrag_queue_probe.py:compute_dynamic_budget — add 1 logger.info
       so gqu Pattern A activation is grep-able. bcy quick 178dd6e shipped the
       Pattern A budget math but added zero log lines, leaving operators to
       infer activation via external kv_store_doc_status.json sampling.

    3. tests/unit/test_lightrag_queue_probe.py — 1 new caplog test verifying
       the new logger.info string. 6 existing tests untouched. 7/7 PASS.

    Validation site: next 09:00 ADT daily-ingest cron. Operators can now
    grep 'gqu Pattern A' in the cron log to confirm queue-depth-aware budget
    is activating, and orchestrate sub-steps will stream their stdout to tee
    in real time.

    No push — commit stays local until user decides push timing.
    EOF
    )"
    ```

    Confirm the commit landed with `git log --oneline -1` and `git show --stat HEAD`. Do NOT push.
  </action>

  <verify>
    <automated>venv/Scripts/python -m py_compile enrichment/orchestrate_daily.py lib/lightrag_queue_probe.py &amp;&amp; venv/Scripts/python -m pytest tests/unit/test_lightrag_queue_probe.py -v</automated>
  </verify>

  <done>
    - `python -m py_compile enrichment/orchestrate_daily.py lib/lightrag_queue_probe.py` exits 0.
    - `pytest tests/unit/test_lightrag_queue_probe.py -v` reports `7 passed`.
    - `git log -1 --name-only` shows exactly the 3 listed files.
    - Grep sweep for `.summary` parsing in `enrichment/` + `tests/` returns only display-only sites (logger.info, alert message embedding) — no `.summary.split`, `.summary.startswith`, or regex parsing.
    - No `git push` executed; no SSH to Hermes; no prod mutation.
  </done>
</task>

</tasks>

<verification>
End-to-end gates that must hold after Task 1 lands:

1. **Compile gate**: `venv/Scripts/python -m py_compile enrichment/orchestrate_daily.py lib/lightrag_queue_probe.py` exits 0.
2. **Test gate**: `venv/Scripts/python -m pytest tests/unit/test_lightrag_queue_probe.py -v` reports `7 passed` (6 existing untouched + 1 new caplog test).
3. **Caller-contract gate**: PowerShell `Select-String -Path "enrichment\*.py","tests\**\*.py" -Pattern "\.summary\b"` — visual confirmation that all `.summary` references are display-only (logger.info or Telegram message embedding) — no string parsing of summary content.
4. **Back-compat gate**: dry-run path of `_run()` still returns `StepResult(True, f"dry: {' '.join(cmd)}")`. Manually inspect by reading the post-edit `_run` body.
5. **Stage hygiene gate**: `git log -1 --name-only` shows exactly the 3 listed files, no siblings. `git status` shows clean working tree post-commit.
6. **No-push gate**: `git status` confirms branch is ahead of origin by 1 commit (or whatever the user's pre-quick offset was + 1). NO `git push` was run. NO SSH to Hermes was run.
</verification>

<success_criteria>
- 3 files modified: `enrichment/orchestrate_daily.py`, `lib/lightrag_queue_probe.py`, `tests/unit/test_lightrag_queue_probe.py`.
- 1 atomic git commit with message header `chore(observability): drop capture_output in orchestrate _run + log Pattern A budget activation`.
- Test count went 6 → 7, all PASS.
- Compile gate passes for both edited Python modules.
- No caller of `StepResult.summary` does string parsing (verified by grep).
- No push, no SSH, no prod mutation.
- Out-of-scope items (Popen refactor, SUBPROCESS_TIMEOUT_SECONDS change, read_queue_depth touch, ingest_wechat.py edits, env overrides, dashboard scaffolding, `git add -A`, amend, soft-reset) all NOT done.
</success_criteria>

<output>
After completion, create `.planning/quick/260512-rln-obs-orchestrate-daily-py-stdout-bufferin/260512-rln-SUMMARY.md` with:
- Commit SHA + `git show --stat HEAD` output
- Pre/post test count (6 → 7) and pytest output snippet
- Confirmation that the grep sweep found no `.summary` string-parsing callers (with the actual grep output)
- Explicit "no push, no SSH, no prod mutation" line
- Explicit "next validation site: 09:00 ADT daily-ingest cron — operator should grep 'gqu Pattern A' in cron log"
</output>
