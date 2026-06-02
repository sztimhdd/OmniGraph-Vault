---
phase: quick-260517-lok
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - kg_synthesize.py
  - tests/unit/test_lightrag_embedding_timeout.py
autonomous: false
requirements:
  - LOK-01  # Pass `default_embedding_timeout` kwarg to LightRAG() in kg_synthesize.py:106
  - LOK-02  # Honor `LIGHTRAG_EMBEDDING_TIMEOUT` env var override (default 90)
  - LOK-03  # Defensive int() parse — non-numeric env value falls back to 90
  - LOK-04  # Unit-test coverage asserting kwarg propagation (mock LightRAG; no network)
  - LOK-05  # Aliyun retest evidence — journal must show "Func: 90s, Worker: 180s, Health Check: 195s"
  - LOK-06  # Aliyun retest evidence — POST /api/synthesize qa + long_form returns non-empty markdown

must_haves:
  truths:
    - "Aliyun journal logs `Embedding func: 8 new workers initialized (Timeouts: Func: 90s, Worker: 180s, Health Check: 195s)` on systemd restart"
    - "POST /api/synthesize {mode:qa, question:'Hermes Agent 是什么'} returns non-empty markdown with error=None"
    - "POST /api/synthesize {mode:long_form, question:'对比 LangChain 和 LangGraph 各自的设计哲学'} returns markdown_len > 2000 and sources >= 1"
    - "LIGHTRAG_EMBEDDING_TIMEOUT env var (e.g. 120) overrides the default at startup without code change"
    - "Full kb test suite remains 489/489 PASS"
  artifacts:
    - path: "kg_synthesize.py"
      provides: "LightRAG() init with default_embedding_timeout kwarg sourced from env (default 90)"
      contains: "default_embedding_timeout=int(os.environ.get(\"LIGHTRAG_EMBEDDING_TIMEOUT\", \"90\"))"
    - path: "tests/unit/test_lightrag_embedding_timeout.py"
      provides: "Unit tests asserting kwarg propagation (default + env override + invalid env fallback + regression guard for other kwargs)"
      min_lines: 60
  key_links:
    - from: "kg_synthesize.py:106"
      to: "lightrag.lightrag.LightRAG.__init__"
      via: "default_embedding_timeout kwarg"
      pattern: "default_embedding_timeout=int\\(os\\.environ\\.get\\("
    - from: "tests/unit/test_lightrag_embedding_timeout.py"
      to: "kg_synthesize.synthesize_response"
      via: "monkeypatch swap of LightRAG class to capture kwargs"
      pattern: "monkeypatch\\.setattr.*kg_synthesize.*LightRAG"
---

<objective>
Fix the cross-border embedding worker timeout that is blocking Aliyun KB
synthesize on real long-form articles. P1 deployment blocker — currently every
hybrid query falls into the silent-degrade path (worker timeout fires →
embeddings = None → vdb retrieval skipped → empty markdown).

Surgical change: pass `default_embedding_timeout=int(os.environ.get("LIGHTRAG_EMBEDDING_TIMEOUT", "90"))`
as a kwarg to the `LightRAG(...)` constructor in `kg_synthesize.py:106`. Per
RESEARCH.md, LightRAG 1.4.15 derives Worker = Func × 2 and Health = Func × 2 + 15
internally, so this single kwarg yields the target Func 90 / Worker 180 / Health 195.

Purpose: unblock P1 Aliyun deploy. The 60s Worker default was sized for
same-region embedding; cross-border Aliyun→GCP-Singapore via WireGuard
takes 15-25s per Vertex call, and one hybrid query batches 3 sequential
calls → 45-75s easily exceeds 60s.

Output:

  - 1 modified file: kg_synthesize.py (single-line constructor edit)
  - 1 new test file: tests/unit/test_lightrag_embedding_timeout.py (3-4 cases)
  - 1 SUMMARY.md citing local pytest evidence + Aliyun retest evidence
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/quick/260517-lok-lightrag-embedding-worker-timeout-kg/260517-lok-RESEARCH.md
@kg_synthesize.py
@tests/unit/test_lightrag_timeout.py
@requirements.txt

<interfaces>
<!-- Key signatures the executor needs. Extracted from current code + RESEARCH.md verified source. -->
<!-- Use these directly — no codebase exploration required. -->

From kg_synthesize.py:106 (current — to be modified):

```python
async def synthesize_response(query_text: str, mode: str = "hybrid"):
    rag = LightRAG(working_dir=RAG_WORKING_DIR, llm_model_func=get_llm_func(), embedding_func=embedding_func)
```

From kg_synthesize.py:106 (target shape after edit):

```python
async def synthesize_response(query_text: str, mode: str = "hybrid"):
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=get_llm_func(),
        embedding_func=embedding_func,
        # Cross-border Aliyun→GCP-Singapore embedding via WireGuard takes
        # 15-25s per Vertex call. Hybrid query batches 3 sequential calls
        # (query/ll/hl). 90s Func → 180s Worker (LightRAG auto-derives
        # Worker = Func * 2 in utils.py:680-685) accommodates 3 × 25s + jitter.
        # Default 30/60/75 was sized for same-region; too tight cross-border.
        default_embedding_timeout=int(os.environ.get("LIGHTRAG_EMBEDDING_TIMEOUT", "90")),
    )
```

From venv/Lib/site-packages/lightrag/lightrag.py:393-395 (verified in RESEARCH.md):

```python
default_embedding_timeout: int = field(
    default=int(os.getenv("EMBEDDING_TIMEOUT", DEFAULT_EMBEDDING_TIMEOUT))
)
```

LightRAG accepts `default_embedding_timeout` as a dataclass field; passing it
as a kwarg overrides the env-default lookup.

From venv/Lib/site-packages/lightrag/utils.py:680-689 (verified in RESEARCH.md):

```python
if llm_timeout is not None:
    if max_execution_timeout is None:
        max_execution_timeout = llm_timeout * 2          # Worker
    if max_task_duration is None:
        max_task_duration = llm_timeout * 2 + 15         # Health Check
```

Confirms 90 → 180 Worker / 195 Health.

From tests/unit/test_lightrag_timeout.py (existing pattern for LLM-side timeout test):

- Uses `monkeypatch.setenv` + `importlib.reload(lr)` to re-evaluate dataclass field default.
- Useful as a reference, but for THIS task we want a different angle: assert the
  kwarg propagates from `kg_synthesize` to `LightRAG()` (not that env-var-only
  reload works, which is already covered by test_lightrag_timeout.py for the LLM side).
</interfaces>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add unit tests for default_embedding_timeout kwarg propagation (RED)</name>
  <files>tests/unit/test_lightrag_embedding_timeout.py</files>
  <behavior>
    Test 1 — `test_default_embedding_timeout_passed_to_lightrag`:
      - `monkeypatch.delenv("LIGHTRAG_EMBEDDING_TIMEOUT", raising=False)`
      - Stub LightRAG class with __init__ that captures kwargs into a list
      - `monkeypatch.setattr("kg_synthesize.LightRAG", StubLightRAG)`
      - Run `asyncio.run(kg_synthesize.synthesize_response("dummy"))` (will likely fail at later steps; that's fine — we only inspect captured init kwargs BEFORE failure, OR raise early from the stub's aquery)
      - Better: stub LightRAG with `initialize_storages` (no-op coroutine) AND `aquery` (returns "stubbed") so synthesize_response returns cleanly
      - Assert captured["default_embedding_timeout"] == 90
      - Assert captured["working_dir"], captured["llm_model_func"], captured["embedding_func"] all present (regression guard)

    Test 2 — `test_lightrag_embedding_timeout_env_override`:
      - `monkeypatch.setenv("LIGHTRAG_EMBEDDING_TIMEOUT", "120")`
      - Same stub-and-call pattern
      - Assert captured["default_embedding_timeout"] == 120

    Test 3 — `test_lightrag_embedding_timeout_invalid_env_falls_back_to_default`:
      - `monkeypatch.setenv("LIGHTRAG_EMBEDDING_TIMEOUT", "abc")`
      - Same stub-and-call pattern
      - Should NOT raise (defensive parsing); assert captured["default_embedding_timeout"] == 90
      - DECISION: implementation picks `int(os.environ.get(..., "90"))` which WILL raise ValueError on "abc". Therefore Test 3 documents the desired defensive behavior. Implementation in Task 2 may either (a) wrap the int() in try/except returning 90, or (b) use a small helper function. Test 3 must match Task 2's choice. RECOMMENDED: try/except, since it's 3 lines and avoids new helper. If author chooses (b), update test accordingly.

    Test 4 (regression guard) — `test_lightrag_other_kwargs_unchanged`:
      - Same stub-and-call pattern, env unset
      - Assert captured["working_dir"] == RAG_WORKING_DIR (or the imported config value)
      - Assert callable(captured["llm_model_func"])
      - Assert captured["embedding_func"] is the imported `embedding_func` symbol
      - Confirms the new kwarg did not displace existing kwargs

    Pattern reference: tests/unit/test_lightrag_timeout.py (LLM-side equivalent, already in tree). Imports: `import asyncio`, `import pytest`, `import kg_synthesize`. NO real LightRAG import. NO network. Stub the canonical-map sqlite path by also monkeypatching `kg_synthesize.DB_PATH` to a non-existent Path so the canonical-map block short-circuits cleanly.
  </behavior>
  <action>
    Create `tests/unit/test_lightrag_embedding_timeout.py` with the 4 test cases described in &lt;behavior&gt; above. RED step: tests will fail because kg_synthesize.py:106 currently does NOT pass `default_embedding_timeout`.

    Use this exact stub class shape to keep tests fast and side-effect-free:
    ```python
    class _StubRAG:
        def __init__(self, **kwargs):
            captured.update(kwargs)
        async def initialize_storages(self):
            return None
        async def aquery(self, prompt, param=None):
            return "stubbed"
    ```
    Use `monkeypatch.setattr("kg_synthesize.LightRAG", _StubRAG)` and a fresh `captured = {}` dict per test. Also `monkeypatch.setattr("kg_synthesize.DB_PATH", Path("/nonexistent-path-for-test"))` to skip the sqlite canonical-map load. `monkeypatch.setattr("kg_synthesize.CANONICAL_MAP_FILE", Path("/nonexistent-path-for-test"))` likewise. Drop `LIGHTRAG_EMBEDDING_TIMEOUT` in the autouse fixture for clean state per test.

    Run `python -m pytest tests/unit/test_lightrag_embedding_timeout.py -v` — expect failure (kwarg not yet passed). Document this RED state in the task verification.

    Test file MUST follow PEP 8, use type hints on helper functions, use `from __future__ import annotations` per repo convention (see test_lightrag_timeout.py).
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/test_lightrag_embedding_timeout.py -v</automated>
    Expected at end of Task 1: 4 tests collected, all 4 FAIL with assertion-style errors confirming the kwarg is not yet passed (this is the RED state). After Task 2, same command should report all 4 PASS.
  </verify>
  <done>
    File `tests/unit/test_lightrag_embedding_timeout.py` exists with 3-4 tests. Initial pytest run shows tests collected and failing for the expected reason ("default_embedding_timeout not in captured kwargs" or KeyError) — confirming RED.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Pass default_embedding_timeout kwarg in kg_synthesize.py:106 (GREEN)</name>
  <files>kg_synthesize.py</files>
  <behavior>
    After this edit:
      - `LightRAG()` is called with `default_embedding_timeout=90` when `LIGHTRAG_EMBEDDING_TIMEOUT` env var is unset
      - `LightRAG()` is called with `default_embedding_timeout=120` when `LIGHTRAG_EMBEDDING_TIMEOUT=120` is set
      - Non-numeric env value (e.g. "abc") falls back to 90 (defensive parse via try/except, NOT raise)
      - Existing kwargs (`working_dir`, `llm_model_func`, `embedding_func`) remain unchanged
      - All 4 unit tests from Task 1 turn GREEN
      - Existing kb suite remains 489/489 PASS (no regression)
  </behavior>
  <action>
    Edit ONLY `kg_synthesize.py` line 106. Replace the single-line LightRAG() call with a multi-line form that adds the `default_embedding_timeout` kwarg. Use the EXACT shape from the RESEARCH.md recommended diff (also in &lt;interfaces&gt; above). Include the inline comment explaining the cross-border rationale (3-4 lines max).

    Defensive int parsing — do NOT inline `int(os.environ.get(..., "90"))` because that raises ValueError on "abc" (Test 3 RED). Instead, factor a tiny inline helper or use try/except. RECOMMENDED implementation (matches Task 1 Test 3):

    ```python
    def _embedding_timeout_default() -> int:
        """Return embedding timeout (env override or 90s default).

        Cross-border Aliyun→GCP-Singapore embedding via WireGuard takes
        15-25s per Vertex call; LightRAG hybrid query batches 3 sequential
        calls. 90s Func → 180s Worker (utils.py:680-685 derives Worker = Func * 2)
        accommodates 3 × 25s + jitter. Default 30/60/75 (LightRAG built-in)
        was sized for same-region deploys and is too tight cross-border.
        """
        raw = os.environ.get("LIGHTRAG_EMBEDDING_TIMEOUT", "90")
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 90
    ```
    Place this helper at module level near `_archive_filename` (top-level helpers section). Then update `synthesize_response` line 106 to:
    ```python
    async def synthesize_response(query_text: str, mode: str = "hybrid"):
        rag = LightRAG(
            working_dir=RAG_WORKING_DIR,
            llm_model_func=get_llm_func(),
            embedding_func=embedding_func,
            default_embedding_timeout=_embedding_timeout_default(),
        )
    ```

    Per CLAUDE.md HIGHEST PRIORITY PRINCIPLE 3 (Surgical Changes):
      - Touch ONLY this constructor call + the new helper function definition
      - Do NOT touch IMAGE_URL_DIRECTIVE, query history, canonical map, or any other code in this file
      - Do NOT reformat any existing line
      - Do NOT add unrelated imports (`os` is already imported at line 1)

    Run the unit test suite from Task 1 — all 4 must turn GREEN.
    Run the full kb test suite — must remain 489/489.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/test_lightrag_embedding_timeout.py -v &amp;&amp; venv/Scripts/python.exe -m pytest kb/tests/ -q</automated>
    Expected: tests/unit/test_lightrag_embedding_timeout.py — 4 PASS. kb/tests/ — 489 PASS (no regression). Also: import smoke `venv/Scripts/python.exe -c "import kg_synthesize; print(kg_synthesize._embedding_timeout_default())"` should print `90`.
  </verify>
  <done>
    All 4 new tests PASS. Full kb suite still 489/489. `kg_synthesize.py` diff is exactly 1 helper function added + 1 constructor call expanded from 1 line to 5 lines (plus inline kwarg). No other lines modified. `git diff kg_synthesize.py` shows ONLY these changes.
  </done>
</task>

<task type="checkpoint:human-action" gate="blocking">
  <name>Task 3: Aliyun retest (operator-side, post-merge)</name>
  <what-built>
    `kg_synthesize.py` now passes `default_embedding_timeout=90` (env-overridable
    via `LIGHTRAG_EMBEDDING_TIMEOUT`) to LightRAG. Local unit tests confirm
    kwarg propagation. Full kb suite green.

    Local environment cannot validate end-to-end (no GCP credentials locally;
    cross-border path only exists on Aliyun ECS). Therefore operator must
    perform Aliyun retest to confirm runtime behavior matches design.
  </what-built>
  <how-to-verify>
    Operator (user, via Aliyun SSH alias `aliyun-vitaclaw` per memory
    `aliyun_vitaclaw_ssh.md`) executes the following sequence after Task 2 is
    committed and pushed locally:

    1. **SCP file to prod** (GitHub HTTPS unreachable from Aliyun per memory):
       ```bash
       scp kg_synthesize.py aliyun-vitaclaw:/root/OmniGraph-Vault/kg_synthesize.py
       ```

    2. **Restart kb-api service**:
       ```bash
       ssh aliyun-vitaclaw "systemctl restart kb-api.service"
       ```

    3. **Verify journal startup signature** — must show the new timeout values:
       ```bash
       ssh aliyun-vitaclaw "journalctl -u kb-api.service -n 50 --no-pager | grep -i 'embedding func.*workers initialized'"
       ```
       Expected line:
       `INFO: Embedding func: 8 new workers initialized (Timeouts: Func: 90s, Worker: 180s, Health Check: 195s)`

       If the line shows `Func: 30s, Worker: 60s, Health Check: 75s` — the kwarg
       did NOT take effect. STOP, investigate (likely SCP path wrong or service
       didn't actually restart). Do NOT proceed to step 4.

    4. **Smoke test qa mode** — short factual question:
       ```bash
       ssh aliyun-vitaclaw "curl -s -X POST http://127.0.0.1:8000/api/synthesize \
         -H 'Content-Type: application/json' \
         -d '{\"mode\":\"qa\",\"question\":\"Hermes Agent 是什么\"}' | python3 -m json.tool"
       ```
       Expected: JSON response with `error: null` and `markdown` field containing
       non-empty real KB content (NOT empty string, NOT "no information available").

    5. **Smoke test long_form mode** — longer multi-source question:
       ```bash
       ssh aliyun-vitaclaw "curl -s -X POST http://127.0.0.1:8000/api/synthesize \
         -H 'Content-Type: application/json' \
         -d '{\"mode\":\"long_form\",\"question\":\"对比 LangChain 和 LangGraph 各自的设计哲学\"}' | python3 -m json.tool"
       ```
       Expected: `error: null`, `markdown_len > 2000`, `sources` array contains
       at least 1 entry (assuming KG holds LangChain/LangGraph articles).

    6. **Capture journal during smoke** — confirm NO worker timeout warnings fire:
       ```bash
       ssh aliyun-vitaclaw "journalctl -u kb-api.service --since '2 minutes ago' --no-pager | grep -i 'worker timeout' || echo 'NO WORKER TIMEOUT — clean'"
       ```
       Expected: `NO WORKER TIMEOUT — clean`. If any `Worker timeout for task` lines
       fire, the 180s Worker budget is still being exceeded → real cross-border
       latency exceeds design expectation; STOP and document as a network-layer
       bottleneck (do NOT bump higher in this phase).

    Paste journal grep + curl JSON outputs into a comment for the executor to
    cite in SUMMARY.md.
  </how-to-verify>
  <resume-signal>
    Operator types one of:
      - "approved" + pastes journal startup line + qa response snippet + long_form response snippet → executor writes SUMMARY.md citing operator's evidence
      - "worker timeout still firing — abort" + pastes the timeout log line → executor writes SUMMARY.md documenting the network-layer bottleneck and rolls back kg_synthesize.py if user requests
      - "kwarg did not take effect" + pastes the journal line showing 30/60/75 still → executor investigates SCP path, file permissions, systemd reload state
  </resume-signal>
  <done>
    Operator confirms journal shows `Func: 90s, Worker: 180s, Health Check: 195s`
    AND both `/api/synthesize` smoke tests return non-empty markdown with
    error=null. Evidence pasted by operator and cited verbatim in SUMMARY.md.
  </done>
</task>

</tasks>

<verification>
**Local verification (executor):**
1. New test file exists at `tests/unit/test_lightrag_embedding_timeout.py` with 3-4 cases
2. `pytest tests/unit/test_lightrag_embedding_timeout.py -v` — all PASS post-Task-2
3. `pytest kb/tests/ -q` — 489/489 PASS (no regression)
4. `git diff kg_synthesize.py` shows ONLY: (a) one new helper function `_embedding_timeout_default()`, (b) one constructor call expanded with `default_embedding_timeout=_embedding_timeout_default()` kwarg
5. `grep -c "default_embedding_timeout" kg_synthesize.py` returns 1 (only one call site)
6. `python -c "import kg_synthesize; print(kg_synthesize._embedding_timeout_default())"` prints `90`
7. With env: `LIGHTRAG_EMBEDDING_TIMEOUT=120 python -c "import kg_synthesize; print(kg_synthesize._embedding_timeout_default())"` prints `120`
8. With invalid env: `LIGHTRAG_EMBEDDING_TIMEOUT=abc python -c "import kg_synthesize; print(kg_synthesize._embedding_timeout_default())"` prints `90`

**Aliyun verification (operator, Task 3):**

- Journal `Embedding func: 8 new workers initialized (Timeouts: Func: 90s, Worker: 180s, Health Check: 195s)`
- POST /api/synthesize qa returns non-empty markdown
- POST /api/synthesize long_form returns markdown_len > 2000 with sources
- No `Worker timeout for task` warnings during smoke

**SUMMARY.md must cite:**

- Local pytest output (4/4 new + 489/489 existing)
- Aliyun journal startup line (verbatim)
- Aliyun curl JSON snippets (qa + long_form)
- The fact that LightRAG is unmodified (no vendor patch, no monkey-patch — matches `feedback_lightrag_is_core_asset_no_bypass.md`)
</verification>

<success_criteria>

- [ ] `tests/unit/test_lightrag_embedding_timeout.py` exists with 3-4 unit tests asserting kwarg propagation, env override, and defensive int parse
- [ ] All 4 new tests PASS
- [ ] `kb/tests/` suite remains 489/489 PASS
- [ ] `kg_synthesize.py` diff: exactly 1 new helper function + 1 constructor call expanded; no other files touched in this layer
- [ ] No vendor `venv/Lib/site-packages/lightrag/` files modified
- [ ] No `kb/services/synthesize.py`, `lib/lightrag_embedding.py`, `kb/api_routers/`, `kb/templates/`, `kb/static/` files modified
- [ ] No new dependency added to `requirements.txt`
- [ ] Aliyun journal verifies new timeouts (Func: 90 / Worker: 180 / Health: 195) on systemd restart
- [ ] Aliyun POST /api/synthesize returns non-empty markdown for both qa and long_form smoke questions
- [ ] No `Worker timeout for task` warnings during Aliyun smoke
- [ ] SUMMARY.md cites all of the above with verbatim evidence (no fabricated stats — see memory `feedback_no_literal_secrets_in_prompts.md` adjacency: ALL claims must reference real log/test output)
</success_criteria>

<output>
After completion, create `.planning/quick/260517-lok-lightrag-embedding-worker-timeout-kg/260517-lok-SUMMARY.md` containing:
  - Local pytest evidence (commands run, exit codes, key output lines)
  - Aliyun journal evidence (verbatim startup line + verbatim curl JSON for qa + long_form)
  - Diff stat for `kg_synthesize.py` (lines added/removed; expect ~12 added / 1 removed)
  - Confirmation that no LightRAG vendor code was modified
  - Note on `LIGHTRAG_EMBEDDING_TIMEOUT` env var as the operational tuning knob (no redeploy required to bump)
  - Forward note: if Aliyun smoke shows clean 90/180/195 behavior for ≥3 days under real query load, this quick is sealed; if Worker timeout fires on real traffic at 180s, queue v1.0.y candidate to bump default to 120s OR (better) parallelize Vertex calls inside `lib/lightrag_embedding.py:207` per RESEARCH.md Q5
</output>
