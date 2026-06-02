---
phase: quick-260527-swt
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/integration/kb/test_async_safety.py
  - .scratch/v1.1-yolo-p5verify-<ts>.log
autonomous: true
requirements:
  - P5-SC3   # P5-stub Success Criteria #3 — async-safety verified under N=4 concurrent /api/synthesize
gap_closure: false

must_haves:
  truths:
    - "N=4 asyncio.gather()-fired POST /api/synthesize requests reach status=done OR a race/deadlock/corruption is observed and reported"
    - "If 4 jobs complete: 4 markdown bodies are mutually distinct (no shared-state corruption)"
    - "Each markdown body contains the marker phrase from its own question (no crosstalk)"
    - "Acceptance branch (A=race observed / B=clean / C=can't run) is explicitly recorded in the executor's final report"
  artifacts:
    - path: "tests/integration/kb/test_async_safety.py"
      provides: "Pytest async-safety regression gate (N=4 concurrent /api/synthesize)"
      max_lines: 30
    - path: ".scratch/v1.1-yolo-p5verify-<ts>.log"
      provides: "Final report with environment used + N=4 result + acceptance branch"
  key_links:
    - from: "tests/integration/kb/test_async_safety.py"
      to: "running kb-api singleton (local localhost:8766 OR Databricks app URL)"
      via: "httpx.AsyncClient + asyncio.gather"
      pattern: "asyncio\\.gather.*post.*synthesize"
---

<objective>
Verify P5-stub Success Criteria #3 — that the LightRAG singleton (currently
`kg_synthesize._get_or_init_rag()` module-global cache; commit 67dfe5b) is
async-safe under N=4 concurrent `/api/synthesize` requests.

This is a TEST-ONLY phase. We are NOT modifying the singleton implementation.
Three acceptance branches:

- **(A)** Race / deadlock / state corruption observed → HALT + escalate to
  `/gsd:plan-phase v1.1.P5`. This may be the root cause of bug 2c
  (job 564f270d59e6 polling reports done@T=59s while backend logs c1_after_aquery
  at T=92s).
- **(B)** Test GREEN, no race → P5 SC#3 satisfied; commit + push the test as
  a permanent regression gate.
- **(C)** Test cannot be authored within hard constraints (≤30 LoC, no
  singleton edits) OR neither local nor remote env is reachable → HALT +
  escalate.

Purpose: empirical verification of an unverified async-safety claim. If we
find the race here, we save P5 plan-phase from rebuilding it later.

Output:

- `tests/integration/kb/test_async_safety.py` (≤30 LoC, single async test)
- `.scratch/v1.1-yolo-p5verify-<UTC-iso>.log` (final report)
- On branch (B): atomic forward-only commit on `main`, pushed to origin
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md
@.planning/phases/v1.1-roadmap/P5-stub.md
@kb/api.py
@kg_synthesize.py
@.scratch/local_serve.py

<interfaces>
<!-- Singleton + endpoint contracts the test consumes. Do NOT modify either. -->

Module-global singleton in `kg_synthesize.py:82`:

```python
async def _get_or_init_rag() -> LightRAG: ...   # cached after first call
```

Called by `synthesize_response()` at line 186 (`rag = await _get_or_init_rag()`).

Endpoint contract from `kb/api_routers/synthesize.py` (per P5-stub line 64-67):

```
POST /api/synthesize     → 202 Accepted, body: {"job_id": "<uuid>"}
GET  /api/synthesize/{job_id} → {"status": "queued"|"running"|"done"|"failed",
                                  "markdown": str|None,
                                  "confidence": float|None}
```

Local launcher (preferred env per orchestrator brief):
`venv/Scripts/python.exe .scratch/local_serve.py` → http://localhost:8766
(Storage at `.dev-runtime/databricks-app-local/` per local-dev runbook;
 must be hydrated before invocation.)
</interfaces>

<halt_rules>
<!-- Halt-on-detection — these stop the executor immediately, no auto-fix. -->

1. Test file > 30 LoC → HALT + branch (C).
2. Implementation requires editing `kb/api.py` or `kg_synthesize.py` or
   `kb/services/synthesize.py` → HALT + branch (C).
3. Any git op returns non-zero → HALT.
4. Singleton race / deadlock / state corruption observed during test
   execution → HALT + branch (A). DO NOT FIX. DO NOT add asyncio.Lock.
   Report only.
5. Both local launcher (`localhost:8766`) and Databricks app URL unreachable
   → HALT + branch (C).
6. Pre-commit / commit hook fails → HALT (DO NOT --amend, DO NOT --no-verify).
7. Push to origin/main rejected → HALT (DO NOT force-push).
</halt_rules>

<discipline>
- NO `git add -A` — explicit paths only (test file + report log).
- NO `git commit --amend` (per `feedback_no_amend_in_concurrent_quicks.md`).
- NO `git reset --hard` / `git push --force` (per CLAUDE.md highest-priority rules).
- NO literal secrets in test file or report (per `feedback_no_literal_secrets_in_prompts.md`).
- "omonigraph-vault" misspelling is canonical — DO NOT correct.
- Run `scripts/local_e2e.sh` IF a smoke is needed (per `feedback_use_local_e2e_sh.md`);
  raw `python` invocations bypass corp-network env handling.
</discipline>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write the N=4 async-safety test (≤30 LoC)</name>
  <files>tests/integration/kb/test_async_safety.py</files>
  <action>
    Create a single pytest module with one async test. Implements P5-SC3.
    HARD CEILING: total file ≤ 30 LoC (excluding the module docstring; if
    the implementation cannot fit, HALT per halt-rule #1 — do NOT split).

    Test design (matches orchestrator brief verbatim):

    1. Resolve target base URL from env var `KB_BASE_URL`
       (default `http://localhost:8766`). One env var, no auth headers
       (test only runs against unauthenticated local OR an SP-token-already-
       configured Databricks app surfaced by the operator out-of-band — the
       test never inlines a token).
    2. Define 4 marker-bearing questions, e.g.:
         `"AAAA-MARKER-1: What is OmniGraph-Vault?"`
         `"BBBB-MARKER-2: What is LightRAG?"`
         `"CCCC-MARKER-3: What is FastAPI?"`
         `"DDDD-MARKER-4: What is asyncio?"`
       Markers must be distinct, non-overlapping, and unlikely to appear
       organically in any KG-generated answer.
    3. Use `httpx.AsyncClient(timeout=httpx.Timeout(180.0))` once for all
       requests (httpx is already a project dep — see existing
       `tests/integration/kb/` modules).
    4. `asyncio.gather(*[submit(q) for q in questions])` where `submit`
       POSTs `/api/synthesize` and returns the `job_id`. Assert 4 distinct
       job_ids (`len(set(ids)) == 4`).
    5. Poll each job_id via `GET /api/synthesize/{job_id}` with a single
       async-poll helper (1s sleep, max 180s). Run the 4 polls under
       `asyncio.gather` so they wait concurrently — this is the actual race
       window.
    6. Assertions (each on a separate line for readable failures):
       - All 4 final statuses == `"done"` (no deadlock; no failed). If any
         is `"failed"` → branch (A).
       - 4 markdown bodies pairwise distinct: `len({r["markdown"] for r in results}) == 4`.
       - For each (question, result) pair: the question's marker phrase
         appears in `result["markdown"]` (no crosstalk; this is the KEY
         corruption assertion).
       - `confidence` field present and finite (`isinstance(c, (int, float))`)
         on all 4 — guards against shared-state nulling.
    7. Mark with `@pytest.mark.integration` and `@pytest.mark.asyncio`.

    Style:
    - Type hints on the test function (`-> None`).
    - One module docstring (1-3 lines) explaining P5-SC3 + branch logic.
    - NO new fixtures, NO conftest edits. NO retry/backoff helpers beyond the
      single 1-sec poll loop. NO env mutation. NO mocking the singleton.

    NEVER edit `kb/api.py`, `kg_synthesize.py`, `kb/services/synthesize.py`,
    or any router file. If a structural shortcoming forces an edit, HALT.

    LoC budget reminder: 30 lines is tight but sufficient — use list
    comprehensions and `asyncio.gather` to compress the poll fan-out.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -c "import pathlib; lines=[l for l in pathlib.Path('tests/integration/kb/test_async_safety.py').read_text(encoding='utf-8').splitlines() if l.strip() and not l.lstrip().startswith('#') and not (l.strip().startswith('\"\"\"') or l.strip().endswith('\"\"\"') or l.strip().startswith(\"'''\"))]; assert len(lines) <= 30, f'LoC ceiling exceeded: {len(lines)} > 30'; print(f'LoC = {len(lines)} (≤30 OK)')"</automated>
  </verify>
  <done>
    File `tests/integration/kb/test_async_safety.py` exists, parses as a
    Python module, contains exactly one `async def test_*` function, and
    its non-blank / non-comment / non-docstring LoC ≤ 30. NO files outside
    this single test path were modified.
  </done>
</task>

<task type="auto">
  <name>Task 2: Run the test against a live singleton + decide branch (A/B/C)</name>
  <files>.scratch/v1.1-yolo-p5verify-&lt;UTC-iso&gt;.log</files>
  <action>
    Two-channel attempt to land the test against a real singleton instance.
    DO NOT mock. DO NOT TestClient — TestClient creates a fresh app per test
    and bypasses the lifespan-scoped singleton question entirely.

    **Channel 1 — local one-port deploy (preferred per orchestrator brief):**

    1. Verify storage hydration: `Test-Path .dev-runtime/databricks-app-local/lightrag_storage/graph_chunk_entity_relation.graphml`. If missing → check `docs/LOCAL_DEV_SETUP.md` Step 3 (Hermes hydrate); if not feasible right now, fall through to Channel 2.
    2. Apply env from `databricks-deploy/.env.local` (preferred) OR set the
       minimum env per `CLAUDE.md` "Local dev env vars" section:
       `OMNIGRAPH_BASE_DIR=...absolute path to .dev-runtime/databricks-app-local`,
       `OMNIGRAPH_LLM_PROVIDER=deepseek` (parity), `DATABRICKS_CONFIG_PROFILE=dev`.
       Do NOT inline secrets. Do NOT log secrets.
    3. Run the smoke from `CLAUDE.md` "Step 4 — smoke before launch":
       `venv/Scripts/python.exe scripts/smoke_databricks_serving_local.py`
       (only if vertex_gemini provider chosen; skip for deepseek). Expect three `ok` lines.
    4. Launch local server in the background:
       `venv/Scripts/python.exe .scratch/local_serve.py` (binds 8766).
       Tail until `Application startup complete` + LightRAG hydrate log
       (`Loaded graph from ... with N nodes, M edges`). Confirms the
       singleton boots BEFORE any traffic.
    5. Smoke `/health` via curl: `curl -s http://localhost:8766/health` →
       `{"status":"ok",...}`. If 5xx → branch (C); record full curl output
       in the log and HALT.
    6. Run the test:
       `venv/Scripts/python.exe -m pytest tests/integration/kb/test_async_safety.py -v --tb=short -p no:cacheprovider`
       (NO `-W error`, NO `--strict-markers` if those break asyncio markers).
    7. Capture full pytest output. Tee to log file.
    8. Stop the local server cleanly (Ctrl+C / TerminateProcess).

    **Channel 2 — Databricks app (fallback if Channel 1 storage missing):**

    Only attempt if Channel 1 explicitly cannot be hydrated. Set
    `KB_BASE_URL=&lt;app URL&gt;` env var; run pytest as in step 6 above. The
    Databricks app must already be deployed + healthy — DO NOT redeploy in
    this quick (deploy is out of scope per orchestrator brief).

    If neither Channel 1 nor Channel 2 reachable → branch (C), HALT.

    **Branch decision (write to log file, ALL fields required):**

    Use timestamp `$(Get-Date -Format "yyyyMMddTHHmmssZ")` as `<ts>`
    (UTC). Path: `.scratch/v1.1-yolo-p5verify-&lt;ts&gt;.log`.

    Required log fields:
    - `# Test environment used:` channel-1-local | channel-2-databricks
    - `# Storage state:` (graphml path + node/edge count if hydrated)
    - `# Pytest exit code:` 0 | non-zero
    - `# N=4 result summary:` per-job (job_id, final_status, marker_match
      bool, markdown_len). Truncate markdown bodies to first 200 chars
      each — never paste full bodies (might leak KG content).
    - `# Acceptance branch:` A | B | C
    - `# If branch A:` race/deadlock/corruption description suitable for
      bug 2c diagnosis (which assertion failed; observed vs expected;
      hypothesis on which singleton state mutated). Include backend log
      excerpt (last 50 lines of `.uvicorn.log` or equivalent) showing
      timing if a deadlock-style hang.
    - `# If branch B:` (filled in Task 3 after commit lands)
    - `# If branch C:` blocking-point details (what couldn't be authored /
      reached / verified) and concrete next step to recommend in the
      `/gsd:plan-phase v1.1.P5` escalation prompt.

    HALT rules in this task:
    - Pytest exit non-zero AND failure is in the marker-crosstalk /
      pairwise-distinct / status=done assertions → branch (A) — do not
      retry, do not "fix" the test. The test caught what it was designed
      to catch. Report and exit.
    - Pytest exit non-zero from infrastructure flake (httpx connect refused
      / 502 / 503): retry ONCE; on second failure → branch (C).
    - Server crash mid-test → branch (A) (deadlock-class symptom).
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -c "import pathlib, glob; logs = sorted(glob.glob('.scratch/v1.1-yolo-p5verify-*.log')); assert logs, 'no report log written'; body = pathlib.Path(logs[-1]).read_text(encoding='utf-8'); assert '# Acceptance branch:' in body, 'log missing branch field'; assert any(b in body for b in ('# Acceptance branch: A','# Acceptance branch: B','# Acceptance branch: C')), 'branch field must be A/B/C'; print(f'report ok: {logs[-1]}')"</automated>
  </verify>
  <done>
    A `.scratch/v1.1-yolo-p5verify-&lt;ts&gt;.log` exists with the seven
    required fields populated. Acceptance branch is one of A/B/C. The test
    has been run against a real running singleton (NOT TestClient, NOT
    mocked) — confirmed by either a `localhost:8766` `/health` excerpt
    (Channel 1) or a `KB_BASE_URL` value pointing at the Databricks app
    (Channel 2). On branch A the log contains a race/deadlock/corruption
    description detailed enough to feed `/gsd:plan-phase v1.1.P5`.
  </done>
</task>

<task type="auto">
  <name>Task 3: Commit + push (branch B only) OR exit cleanly (branch A/C)</name>
  <files>tests/integration/kb/test_async_safety.py, .scratch/v1.1-yolo-p5verify-&lt;ts&gt;.log</files>
  <action>
    Branch dispatch — read the log written in Task 2.

    **Branch B (test GREEN, P5-SC3 satisfied):**

    1. Confirm `git status` shows ONLY two paths dirty:
       `tests/integration/kb/test_async_safety.py` (new file) and
       `.scratch/v1.1-yolo-p5verify-*.log` (new file). If anything else is
       dirty → HALT (out-of-scope changes; surgical principle violated).
    2. Stage explicitly (NEVER `-A`):
       `git add tests/integration/kb/test_async_safety.py .scratch/v1.1-yolo-p5verify-&lt;ts&gt;.log`
    3. Commit with conventional-commits format. ONE atomic commit, NO
       `--amend`, NO co-author trailer (CLAUDE.md global setting disables
       attribution):
       ```
       test(v1.1.P5-verify): pin singleton async-safety regression gate

       N=4 concurrent /api/synthesize against module-global LightRAG
       singleton (kg_synthesize._get_or_init_rag, commit 67dfe5b);
       4 distinct markers, no crosstalk, no deadlock observed locally.
       Closes P5-stub Success Criteria #3.

       Verification: tests/integration/kb/test_async_safety.py PASS;
       full report in .scratch/v1.1-yolo-p5verify-&lt;ts&gt;.log.
       ```
    4. Push: `git push origin main`. If rejected → HALT (do NOT
       force-push; surface the rejection in the log).
    5. Append the commit hash + push range to the log under
       `# If branch B:` header.

    **Branch A (race / deadlock / corruption observed):**

    1. STOP. Do NOT commit the test (it failed; we do not commit failing
       tests on `main`).
    2. Do NOT modify singleton code in this quick (per HARD CONSTRAINT
       #2 + halt-rule #4).
    3. Print the escalation prompt to stdout for the operator to feed to
       `/gsd:plan-phase v1.1.P5`:
       ```
       /gsd:plan-phase v1.1.P5 --reason async-safety-race-detected \
         --evidence .scratch/v1.1-yolo-p5verify-&lt;ts&gt;.log \
         --bug-link 564f270d59e6
       ```
    4. Leave both files on-disk (uncommitted) for the next session to
       inspect. They are gitignored under `.scratch/` already (verify);
       the test file lives under `tests/` and is NOT gitignored, so leave
       it in working tree only — operator decides whether to keep on
       branch or discard.

    **Branch C (could not author or run):**

    1. STOP. Do NOT commit anything.
    2. Print the escalation prompt to stdout:
       ```
       /gsd:plan-phase v1.1.P5 --reason verify-quick-blocked \
         --evidence .scratch/v1.1-yolo-p5verify-&lt;ts&gt;.log \
         --blocking-point "&lt;C-field summary from log&gt;"
       ```
    3. Leave artifacts in working tree, uncommitted.

    NEVER on any branch:
    - `git commit --amend`
    - `git reset --hard`
    - `git push --force` / `git push --force-with-lease`
    - `git add -A`
    - Modify `kb/api.py`, `kg_synthesize.py`, `kb/services/synthesize.py`,
      or any router file
    - Inline secrets / tokens / SSH details in any committed artifact
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -c "import pathlib, glob, subprocess; log=sorted(glob.glob('.scratch/v1.1-yolo-p5verify-*.log'))[-1]; body=pathlib.Path(log).read_text(encoding='utf-8'); branch='A' if '# Acceptance branch: A' in body else ('B' if '# Acceptance branch: B' in body else 'C'); r=subprocess.run(['git','log','-1','--pretty=%s'],capture_output=True,text=True); subj=r.stdout.strip(); ok=(branch=='B' and 'P5-verify' in subj) or (branch in ('A','C') and 'P5-verify' not in subj); assert ok, f'branch={branch} but commit subject={subj!r}'; print(f'branch={branch}, commit-subject={subj!r}, OK')"</automated>
  </verify>
  <done>
    On branch B: `git log -1 --pretty=%s` shows the `test(v1.1.P5-verify):
    ...` subject and `git status` is clean against `origin/main`.
    On branch A or C: no new commit landed; both artifact files
    (test + log) are present in working tree; the escalation prompt is
    printed; the operator has been given the exact next-step command.
    In all three cases the singleton implementation files are unchanged
    (verifiable by `git diff HEAD~1 -- kb/api.py kg_synthesize.py kb/services/synthesize.py`
    showing zero diff).
  </done>
</task>

</tasks>

<verification>
Phase-level checks (in order):

1. `tests/integration/kb/test_async_safety.py` exists and ≤30 LoC.
2. `.scratch/v1.1-yolo-p5verify-<ts>.log` exists with branch field A/B/C.
3. Singleton implementation untouched: `git diff origin/main..HEAD --name-only`
   produces ZERO matches against `kb/api.py`, `kg_synthesize.py`,
   `kb/services/synthesize.py`, `kb/api_routers/synthesize.py`.
4. On branch B only: working tree clean against `origin/main`; the new
   commit pushed; commit subject starts with `test(v1.1.P5-verify):`.
5. No `git add -A`, no `--amend`, no force-push detected (reflog clean).
</verification>

<success_criteria>

- Test file `tests/integration/kb/test_async_safety.py` lands at ≤30 LoC,
  exercises N=4 concurrent `/api/synthesize`, asserts marker-bearing
  pairwise-distinct markdowns, runs against a real singleton (local or
  Databricks — never TestClient, never mock).
- `.scratch/v1.1-yolo-p5verify-<ts>.log` records the environment,
  per-job results, and an explicit acceptance branch (A | B | C).
- Branch (B) → atomic forward-only commit on `main`, pushed; closes
  P5-stub Success Criteria #3.
- Branch (A) → operator handed a concrete `/gsd:plan-phase v1.1.P5`
  escalation with the bug 2c diagnosis evidence path; NO singleton edits
  shipped.
- Branch (C) → operator handed a concrete `/gsd:plan-phase v1.1.P5`
  escalation with the blocking-point summary; NO commits shipped.
</success_criteria>

<output>
After completion, the executor returns:

- The acceptance branch (A | B | C)
- Path to the report log (`.scratch/v1.1-yolo-p5verify-<ts>.log`)
- On branch B: the commit hash + push range
- On branch A or C: the escalation prompt to forward to
  `/gsd:plan-phase v1.1.P5`
</output>
