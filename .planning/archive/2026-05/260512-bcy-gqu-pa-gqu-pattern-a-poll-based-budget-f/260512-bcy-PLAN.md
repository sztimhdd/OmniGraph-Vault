---
phase: quick-260512-bcy
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - lib/lightrag_queue_probe.py
  - tests/unit/test_lightrag_queue_probe.py
  - tests/fixtures/lightrag_doc_status/sample_busy.json
  - tests/fixtures/lightrag_doc_status/sample_idle.json
  - ingest_wechat.py
  - .scratch/gqu-pa-spec.md
autonomous: true
requirements:
  - GQU-PA-01  # Replace fixed h09 budget with poll-based dynamic budget
  - GQU-PA-02  # New module lib/lightrag_queue_probe.py with read_queue_depth + compute_dynamic_budget
  - GQU-PA-03  # Unit tests cover empty / busy / capped / file-missing / corrupt-JSON
  - GQU-PA-04  # Hermes untouched (no push, no SSH writes); fixtures pulled read-only via hermes-remote-check
must_haves:
  truths:
    - "Calling compute_dynamic_budget on an empty queue returns base_budget_s"
    - "Calling compute_dynamic_budget on a 100-doc processing queue returns 1800 (cap)"
    - "Calling compute_dynamic_budget when kv_store_doc_status.json is missing or corrupt returns base_budget_s (no exception)"
    - "ingest_wechat._verify_doc_processed_or_raise consults compute_dynamic_budget at start of run; effective_max_retries scales with live queue depth"
    - "Existing Option B (error_msg guard) and Option A (stable-state re-poll) inside _verify_doc_processed_or_raise are unchanged byte-for-byte"
    - "pytest tests/unit/test_lightrag_queue_probe.py passes 5/5"
  artifacts:
    - path: "lib/lightrag_queue_probe.py"
      provides: "read_queue_depth() + compute_dynamic_budget() helpers"
      exports: ["read_queue_depth", "compute_dynamic_budget"]
      min_lines: 30
    - path: "tests/unit/test_lightrag_queue_probe.py"
      provides: "5 unit tests for the probe module"
      contains: "compute_dynamic_budget"
    - path: "tests/fixtures/lightrag_doc_status/sample_busy.json"
      provides: "Real Hermes prod queue snapshot (multi-doc, processing state)"
    - path: "tests/fixtures/lightrag_doc_status/sample_idle.json"
      provides: "Real Hermes prod queue snapshot (idle / mostly-processed state)"
    - path: ".scratch/gqu-pa-spec.md"
      provides: "Design spec — algorithm, edge cases, signature"
  key_links:
    - from: "ingest_wechat.py:_verify_doc_processed_or_raise"
      to: "lib.lightrag_queue_probe.compute_dynamic_budget"
      via: "module-level import + call before retry loop"
      pattern: "from lib.lightrag_queue_probe import compute_dynamic_budget"
    - from: "lib/lightrag_queue_probe.py:read_queue_depth"
      to: "$OMNIGRAPH_BASE_DIR/lightrag_storage/kv_store_doc_status.json"
      via: "Path-derived file read"
      pattern: "kv_store_doc_status.json"
---

<objective>
Replace the fixed retry budget in `ingest_wechat._verify_doc_processed_or_raise`
(currently 30 × 2s = 60s default; production override 150 × 2s = 300s) with a
**poll-based dynamic budget** that consults the live LightRAG queue depth from
`kv_store_doc_status.json`. Goal: when N=40 batch dispatch floods the queue and
LightRAG processes serially (30-60s/doc), h09 should wait long enough for the
doc to actually finish — not raise prematurely and wrongly mark
`status='failed'` while LightRAG is still chewing through the queue.

This quick is local-only: design + module + unit tests + surgical wire-up in
`ingest_wechat.py`. **No Hermes deploy. No push. User decides ship time.**

Purpose: Fix the LightRAG queue race that 8adbfd0 (status flip dual guard) and
91b19d5 (DeepSeek client timeout) did NOT address. Those guarded *what happens
once we observe a status*; this quick fixes *how long we are willing to wait
before declaring the doc lost*.

Output: New module `lib/lightrag_queue_probe.py`, 5 unit tests, ~10-15 LOC
delta in `ingest_wechat.py`, design spec at `.scratch/gqu-pa-spec.md`, two real
Hermes-pulled fixtures.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@ingest_wechat.py
@lib/__init__.py
@.claude/skills/hermes-remote-check/SKILL.md

# Background — h09 history (read-only, for orientation; do NOT modify)

The h09 retry helper has shipped through three quicks already:
- 260510-h09  — initial 3 × 2s budget (clearly too small, raised constantly)
- 260510-h09b — bumped to 30 × 2s default + env override (current production: 150 × 2s = 300s)
- 260511-lmc  — added Option C dual guard (error_msg check + stable re-poll) for TOCTOU race

Pattern A (this quick) is the **fourth** iteration: the budget is no longer fixed.
It is computed at function entry from live queue depth. Existing dual guard
(Option B + Option A) is preserved untouched.

# Critical existing code (do not change)

`ingest_wechat.py:53-127` is the `_verify_doc_processed_or_raise` function.
Lines 76-83: function signature with `max_retries` and `backoff_s` defaults
sourced from `PROCESSED_VERIFY_MAX_RETRIES` / `PROCESSED_VERIFY_BACKOFF_S`
module constants (lines 55-56).
Lines 114-188: retry loop body — **DO NOT TOUCH** the body. Only change the
loop's range bound (`max_retries` value passed in / computed at top of function).

The 2026-05-11 quick-260511-lmc Option C dual guard lives at lines 136-176.
**These lines must not change byte-for-byte.**

# Hermes fixture pull — agent runs SSH itself

Use the `hermes-remote-check` skill (`.claude/skills/hermes-remote-check/SKILL.md`)
to read `~/.hermes/omonigraph-vault/lightrag_storage/kv_store_doc_status.json`
from Hermes. SSH connection details live in memory file `hermes_ssh.md` (loaded
automatically per-session). **The agent runs the SSH command itself via the
Bash tool — DO NOT ask the user to paste anything.**

The skill's "Connection" section gives the canonical SSH flag set:
`ssh -p <PORT> -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new <USER>@<HOST> '<remote command>'`.

Approach for the pull:
1. Read `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_ssh.md` to get host/port/user.
2. Run `ssh ... 'cat ~/.hermes/omonigraph-vault/lightrag_storage/kv_store_doc_status.json'` and capture stdout.
3. Save to `tests/fixtures/lightrag_doc_status/sample_busy.json` (the snapshot **as it is** — should have at least one `processing` doc; if not busy at pull time, retry during a known-busy window, or fall back to grabbing whatever the snapshot is and call it `sample_idle.json`).
4. For the second fixture, take a second pull at a different time, or trim the busy snapshot down to all-processed entries to construct `sample_idle.json` deterministically. **Document in the commit message which fixture was scp'd as-is and which was derived.**

If the SSH read returns nothing (file not present), STOP and surface the issue —
LightRAG is supposed to maintain this file; absence implies a deeper problem
out of scope for this quick.

# kv_store_doc_status.json schema (per-quirk row in hermes-remote-check skill)

Statuses are **lowercase**: `processing`, `pending`, `processed`, `failed`.
Schema is roughly: `{ <doc_id>: { "status": "...", "error_msg": "..." | null, ... } }`.
The probe only needs the count of entries with `status == "processing"`.

# Python rules

Per `~/.claude/rules/python/coding-style.md`: PEP 8, type annotations on all
function signatures. The new module is small enough that black/ruff aren't
strictly required, but match existing project style (4-space indent, docstrings,
`from __future__ import annotations` is fine but optional).

# Staging-race protection

CLAUDE.md Lessons 2026-05-06 #5: NEVER `git add -A` on this repo while parallel
quicks may be running. Always: `git add <explicit-files-list>` then commit.
The explicit files for this quick are listed in `files_modified` frontmatter above.

# .gitignore for `.scratch/`

`.scratch/` is git-ignored (see project root `.gitignore`). The spec doc at
`.scratch/gqu-pa-spec.md` will NOT be committed — that's intentional (design
artifacts live in `.scratch/`, code/tests live in tracked paths). The plan body
+ commit message body are sufficient for review traceability.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Pull Hermes fixtures + write design spec + create probe module + unit tests</name>
  <files>
    tests/fixtures/lightrag_doc_status/sample_busy.json,
    tests/fixtures/lightrag_doc_status/sample_idle.json,
    .scratch/gqu-pa-spec.md,
    lib/lightrag_queue_probe.py,
    tests/unit/test_lightrag_queue_probe.py
  </files>
  <action>
    **Step 1.1 — Pull two real fixtures from Hermes prod (via hermes-remote-check skill).**

    Read `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_ssh.md`
    to get HOST/PORT/USER. Run the agent's own Bash tool — the user pastes nothing.

    Pull command (run via Bash tool yourself):

    ```bash
    ssh -p <PORT> -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new <USER>@<HOST> \
      'cat ~/.hermes/omonigraph-vault/lightrag_storage/kv_store_doc_status.json' \
      > tests/fixtures/lightrag_doc_status/sample_busy.json
    ```

    Then create `sample_idle.json` either by a second SSH pull at a different
    time OR by deriving from `sample_busy.json` (filter all entries to status
    in {`processed`}, drop any `processing`/`pending`/`failed` rows, write
    back as a valid JSON dict). Document which path you took in the commit
    body.

    **Validation gate**: open `sample_busy.json` and confirm
    `sum(1 for v in obj.values() if v.get("status") == "processing")` is
    ≥1 (the whole point of this fixture is to exercise the busy path).
    If it's 0, pull again or wait for a busy window. Do NOT fabricate data.

    Record the observed `queue_depth` in the design spec (Step 1.2 below).

    **Step 1.2 — Write design spec at `.scratch/gqu-pa-spec.md`.**

    Required sections:
    - Problem statement (1 paragraph): N=40 dispatch flood + serial LightRAG
      processing → h09 raises prematurely → wrong `status='failed'`.
    - Function signatures:
      ```python
      def read_queue_depth(path: Path | None = None) -> int: ...
      def compute_dynamic_budget(
          doc_status: dict[str, dict] | None = None,
          base_budget_s: float = 300.0,
          per_doc_avg_s: float = 60.0,
          cap_s: float = 1800.0,
      ) -> float: ...
      ```
    - Algorithm (verbatim):
      ```
      queue_depth = sum(1 for d in doc_status.values() if d.get("status") == "processing")
      candidate = max(base_budget_s, queue_depth * per_doc_avg_s)
      return min(candidate, cap_s)
      ```
    - Edge cases:
      * `doc_status is None` → caller didn't pass; module-level
        `read_queue_depth()` returned a degenerate empty dict → budget = base_budget_s
      * file missing / IOError → `read_queue_depth` returns `0`; caller
        passes `{}` → budget = base_budget_s
      * JSON corrupt (json.JSONDecodeError) → same: `0` from
        `read_queue_depth`, budget = base_budget_s
      * Non-dict entry values → skip with `if not isinstance(d, dict): continue`
    - Default values (locked, NOT env-overridable in v1):
      * per_doc_avg_s = 60.0 (LightRAG observed 30-60s/doc serial)
      * cap_s = 1800.0 (30 min)
      * base_budget_s defaults to 300.0 in the function signature, but
        the caller in `ingest_wechat.py` will pass
        `PROCESSED_VERIFY_MAX_RETRIES * PROCESSED_VERIFY_BACKOFF_S` so
        the existing env vars `OMNIGRAPH_PROCESSED_RETRY` /
        `OMNIGRAPH_PROCESSED_BACKOFF` continue to govern the floor.
    - Observed fixture values: from Step 1.1, write the actual queue_depth
      seen in `sample_busy.json`. (This validates the race understanding.)
    - Out of scope (call out so reviewer doesn't ask):
      * No new env vars (per_doc_avg_s hardcoded; future quick can add
        `OMNIGRAPH_PER_DOC_AVG_S`)
      * No metrics/logging (defer)
      * No N=40 batch reproduction (impossible locally)

    **Step 1.3 — Create `lib/lightrag_queue_probe.py`.**

    Skeleton (~40 LOC):

    ```python
    """LightRAG queue-depth probe for h09 dynamic budget (gqu Pattern A).

    See `.scratch/gqu-pa-spec.md` for design. Defends against the 2026-05-11/12
    LightRAG queue race where N=40 batch dispatch floods the queue but
    LightRAG processes serially, causing the fixed h09 budget to exhaust
    before the doc actually reaches PROCESSED.
    """
    from __future__ import annotations

    import json
    import logging
    import os
    from pathlib import Path
    from typing import Any

    logger = logging.getLogger(__name__)

    _DEFAULT_BASE_DIR = Path("~/.hermes/omonigraph-vault").expanduser()


    def _doc_status_path() -> Path:
        base = os.environ.get("OMNIGRAPH_BASE_DIR") or str(_DEFAULT_BASE_DIR)
        return Path(base).expanduser() / "lightrag_storage" / "kv_store_doc_status.json"


    def read_queue_depth(path: Path | None = None) -> int:
        """Return count of docs with status=='processing'. Returns 0 on any failure."""
        target = path if path is not None else _doc_status_path()
        try:
            with open(target, "r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
        except FileNotFoundError:
            return 0
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("read_queue_depth: failed to parse %s: %s", target, exc)
            return 0
        if not isinstance(data, dict):
            return 0
        depth = 0
        for entry in data.values():
            if isinstance(entry, dict) and entry.get("status") == "processing":
                depth += 1
        return depth


    def compute_dynamic_budget(
        doc_status: dict[str, Any] | None = None,
        *,
        base_budget_s: float = 300.0,
        per_doc_avg_s: float = 60.0,
        cap_s: float = 1800.0,
    ) -> float:
        """Compute a queue-aware h09 retry budget in seconds.

        budget = min(cap_s, max(base_budget_s, queue_depth * per_doc_avg_s))

        - doc_status: pre-loaded dict (used by tests for fixture injection); if
          None, the module reads kv_store_doc_status.json itself and computes
          queue_depth from it.
        - On any read/parse failure, queue_depth defaults to 0 and the result
          is base_budget_s (graceful degrade).
        """
        if doc_status is None:
            queue_depth = read_queue_depth()
        else:
            queue_depth = sum(
                1
                for d in doc_status.values()
                if isinstance(d, dict) and d.get("status") == "processing"
            )
        candidate = max(base_budget_s, queue_depth * per_doc_avg_s)
        return float(min(candidate, cap_s))
    ```

    **Step 1.4 — Create `tests/unit/test_lightrag_queue_probe.py` with at least 5 cases.**

    ```python
    """Unit tests for lib.lightrag_queue_probe (gqu Pattern A)."""
    from __future__ import annotations

    import json
    from pathlib import Path

    import pytest

    from lib.lightrag_queue_probe import compute_dynamic_budget, read_queue_depth


    @pytest.mark.unit
    def test_empty_queue_returns_base_budget():
        budget = compute_dynamic_budget({}, base_budget_s=300.0)
        assert budget == 300.0


    @pytest.mark.unit
    def test_busy_queue_scales_linearly():
        # 10 processing docs × 60s/doc = 600s; floor of 300s does NOT override
        ds = {f"d{i}": {"status": "processing"} for i in range(10)}
        budget = compute_dynamic_budget(ds, base_budget_s=300.0, per_doc_avg_s=60.0)
        assert budget == 600.0


    @pytest.mark.unit
    def test_huge_queue_hits_cap():
        # 100 × 60 = 6000 > cap=1800
        ds = {f"d{i}": {"status": "processing"} for i in range(100)}
        budget = compute_dynamic_budget(ds, base_budget_s=300.0, per_doc_avg_s=60.0, cap_s=1800.0)
        assert budget == 1800.0


    @pytest.mark.unit
    def test_file_missing_returns_zero(tmp_path: Path):
        # Point read_queue_depth at a non-existent file
        target = tmp_path / "nonexistent.json"
        assert read_queue_depth(target) == 0


    @pytest.mark.unit
    def test_corrupt_json_returns_zero(tmp_path: Path):
        target = tmp_path / "bad.json"
        target.write_text("{not valid json", encoding="utf-8")
        assert read_queue_depth(target) == 0


    @pytest.mark.unit
    def test_fixture_busy_has_real_processing_docs():
        """Validates the prod-pulled busy fixture actually exercises the busy path."""
        fix = Path(__file__).parent.parent / "fixtures" / "lightrag_doc_status" / "sample_busy.json"
        if not fix.exists():
            pytest.skip("sample_busy.json fixture not present")
        with open(fix, "r", encoding="utf-8") as f:
            data = json.load(f)
        depth = sum(1 for v in data.values() if isinstance(v, dict) and v.get("status") == "processing")
        # Allow 0 only if pull happened during a quiet window — but warn loudly
        if depth == 0:
            pytest.skip("sample_busy.json was pulled during a quiet window — re-pull recommended")
        # Sanity: budget must be > base_budget_s when fixture has real busy state
        budget = compute_dynamic_budget(data, base_budget_s=300.0)
        assert budget >= 300.0
    ```

    Ignore status_val types (Enum vs dict) — kv_store_doc_status.json on disk
    is plain JSON dicts; the Enum form only appears in-memory inside LightRAG.

    **Step 1.5 — Run tests locally.**

    ```bash
    .venv/Scripts/python -m pytest tests/unit/test_lightrag_queue_probe.py -v
    ```

    All 5 named tests must PASS. The 6th (fixture realism) PASSes if a busy
    fixture was successfully pulled, otherwise SKIPs cleanly — that's
    acceptable.
  </action>
  <verify>
    <automated>.venv/Scripts/python -m pytest tests/unit/test_lightrag_queue_probe.py -v</automated>
  </verify>
  <done>
    - tests/fixtures/lightrag_doc_status/sample_busy.json exists, valid JSON, observed queue_depth recorded in spec
    - tests/fixtures/lightrag_doc_status/sample_idle.json exists, valid JSON
    - .scratch/gqu-pa-spec.md exists with all required sections + observed fixture queue_depth
    - lib/lightrag_queue_probe.py exists, ~30-50 LOC, exports read_queue_depth + compute_dynamic_budget with PEP 8 type annotations
    - tests/unit/test_lightrag_queue_probe.py exists, 5+ tests, all PASS (the 6th may SKIP if busy pull was quiet)
    - `python -c "from lib.lightrag_queue_probe import compute_dynamic_budget; print(compute_dynamic_budget({}))"` runs cleanly and prints `300.0`
  </done>
</task>

<task type="auto">
  <name>Task 2: Wire dynamic budget into ingest_wechat._verify_doc_processed_or_raise + commit</name>
  <files>
    ingest_wechat.py
  </files>
  <action>
    Surgical modification to `ingest_wechat.py:76-188` ONLY. Lines 1-75 untouched.
    Lines 130-188 (the retry-loop body) untouched byte-for-byte.

    **Step 2.1 — Add module-level import.**

    Find the top of `ingest_wechat.py` (around lines 13-25, the existing imports
    block). Add ONE line:

    ```python
    from lib.lightrag_queue_probe import compute_dynamic_budget
    ```

    Place it next to other `from lib...` imports if any exist, otherwise after
    the stdlib imports.

    **Step 2.2 — Replace the retry-budget computation at function entry.**

    Current code (lines 111-114, do NOT modify lines 76-110 except as noted):

    ```python
        last_status_val: str | None = None
        last_exc: Exception | None = None

        for attempt in range(max_retries):
    ```

    Change to:

    ```python
        last_status_val: str | None = None
        last_exc: Exception | None = None

        # gqu Pattern A: dynamic budget — read live LightRAG queue depth and
        # extend the retry envelope when many docs are queued for serial
        # processing. Existing OMNIGRAPH_PROCESSED_RETRY/BACKOFF env vars set
        # the floor (base_budget_s); per_doc_avg_s and cap_s are constants
        # for v1 (see lib/lightrag_queue_probe.py).
        base_budget_s = max_retries * backoff_s
        effective_budget_s = compute_dynamic_budget(base_budget_s=base_budget_s)
        effective_max_retries = max(max_retries, int(effective_budget_s / backoff_s))

        for attempt in range(effective_max_retries):
    ```

    **DO NOT touch ANYTHING ELSE in lines 130-188.** All references to
    `max_retries` inside the loop body should remain as-is — the only behavioral
    change is the loop's outer `range()`. The `RuntimeError` message at the end
    should also remain referencing `max_retries` (it's the floor; the error
    message accurately tells the operator the configured floor and the dynamic
    extension is implicit).

    Optionally: extend the RuntimeError message (line 181-188) to include
    `effective_max_retries` for debuggability:

    ```python
        raise RuntimeError(
            f"post-ainsert PROCESSED verification failed for doc_id={doc_id} "
            f"after {effective_max_retries} retries (configured floor "
            f"{max_retries}, backoff {backoff_s}s, dynamic budget "
            f"{effective_budget_s:.0f}s). Last status={last_status_val!r}, "
            f"last_exc={last_exc.__class__.__name__ if last_exc else None}. "
            f"Checked both error_msg guard (Option B) and stable-state re-poll (Option A). "
            f"The article will be marked 'failed' in ingestions and retried by next cron."
        )
    ```

    This is the ONLY allowed text change inside lines 130-188 — the message
    string. The control flow stays identical.

    **Step 2.3 — Smoke import test.**

    ```bash
    .venv/Scripts/python -c "import ingest_wechat; print('import OK')"
    ```

    Must print `import OK` and exit 0. (DEEPSEEK_API_KEY=dummy may be required
    per the Phase 5 cross-coupling note in lib/__init__.py docstring — if the
    env is unset, set it to `dummy` for this smoke step.)

    **Step 2.4 — Re-run the unit tests to confirm no regression.**

    ```bash
    .venv/Scripts/python -m pytest tests/unit/test_lightrag_queue_probe.py -v
    ```

    Expected: same 5 PASS + 1 fixture-realism PASS-or-SKIP.

    **Step 2.5 — Count LOC delta in ingest_wechat.py.**

    ```bash
    git diff --stat ingest_wechat.py
    ```

    Must be ≤ 15 lines changed (per task constraint). The error-message
    optional extension is the only multi-line change; if it's too long, drop
    it and keep just the budget computation (target: <10 lines).

    **Step 2.6 — Stage explicit files + commit.**

    Per CLAUDE.md Lessons 2026-05-06 #5: NEVER `git add -A`. Use explicit
    paths only. The `.scratch/gqu-pa-spec.md` path is `.gitignore`d — do
    not stage it.

    ```bash
    git add lib/lightrag_queue_probe.py \
            tests/unit/test_lightrag_queue_probe.py \
            tests/fixtures/lightrag_doc_status/sample_busy.json \
            tests/fixtures/lightrag_doc_status/sample_idle.json \
            ingest_wechat.py
    git status -sb   # confirm only the 5 above are staged + nothing else
    git commit -m "$(cat <<'EOF'
feat(h09): gqu Pattern A — poll-based dynamic budget for LightRAG queue race

Replaces fixed h09 retry budget (300s prod) with a live-queue-aware budget.
read_queue_depth() reads kv_store_doc_status.json; compute_dynamic_budget()
returns max(base_budget_s, queue_depth * 60s) capped at 1800s.

Defends against the N=40 batch-dispatch flood: LightRAG processes chunks
serially (30-60s/doc); queue piles up; previous fixed budget exhausted before
doc actually reached PROCESSED, wrongly raising and marking status='failed'
while LightRAG was still mid-extraction.

Preserves Option B (error_msg guard) + Option A (stable-state re-poll) from
quick 260511-lmc unchanged byte-for-byte. Only loop range() bound is dynamic.

Files:
- lib/lightrag_queue_probe.py (NEW)
- tests/unit/test_lightrag_queue_probe.py (NEW, 6 tests, 5 named + 1 fixture-realism)
- tests/fixtures/lightrag_doc_status/sample_busy.json (NEW, scp'd from Hermes prod)
- tests/fixtures/lightrag_doc_status/sample_idle.json (NEW, derived/pulled)
- ingest_wechat.py (~10 LOC delta — import + budget calc + range() bound)

Local-only commit; user decides Hermes ship time. No env-var changes; existing
OMNIGRAPH_PROCESSED_RETRY/BACKOFF still set the floor.
EOF
)"
    ```

    Confirm commit landed:

    ```bash
    git log --oneline -1
    ```

    DO NOT push. DO NOT touch ~/.hermes/.env. DO NOT SSH-write anything to Hermes.
  </action>
  <verify>
    <automated>.venv/Scripts/python -m pytest tests/unit/test_lightrag_queue_probe.py -v && .venv/Scripts/python -c "from lib.lightrag_queue_probe import compute_dynamic_budget; print('import OK', compute_dynamic_budget({}))"</automated>
  </verify>
  <done>
    - ingest_wechat.py modified: import added + budget calc inserted + range() bound replaced + (optional) error message extended
    - LOC delta ≤ 15 lines per `git diff --stat ingest_wechat.py`
    - Lines 130-180 (retry loop body, Option B + Option A guards) byte-for-byte unchanged except possibly the RuntimeError message string
    - `python -c "import ingest_wechat; print('OK')"` runs cleanly (DEEPSEEK_API_KEY=dummy if needed)
    - All 5 unit tests still PASS after wire-up
    - Single commit landed locally with the canonical message above
    - `git status -sb` shows clean tree (no leftover unstaged changes outside `.scratch/` which is gitignored)
    - NO push performed; NO Hermes mutations of any kind
  </done>
</task>

</tasks>

<verification>
**Final report (executor's summary MUST include):**

1. **Production h09 fixed-budget actual value confirmed?**
   - Read `~/.hermes/.env` on Hermes (read-only via hermes-remote-check skill) for `OMNIGRAPH_PROCESSED_RETRY` and `OMNIGRAPH_PROCESSED_BACKOFF` — confirm they are set (likely `150` and `2.0` per task brief, giving 300s).
   - If env vars unset on Hermes, the production budget is the code default
     `30 × 2.0 = 60s` — flag this divergence in the report.

2. **Fixture queue_depth observed value** (validates the race understanding):
   - Quote the actual count from `sample_busy.json`. If the count is 0 or ≤2,
     note in the report that the fixture is "weakly busy" and may not exercise
     the linear-scale path well, but the synthetic test cases in
     `test_lightrag_queue_probe.py` cover that.

3. **Unit tests result**: 5/5 named PASS + fixture-realism PASS-or-SKIP.

4. **ingest_wechat.py LOC delta**: report `git diff --stat ingest_wechat.py`
   exact count.

5. **Prepared (un-pushed) commit SHA**: report `git log --oneline -1`.

6. **Follow-up suggestions** (operator decides separately):
   - When to ship to Hermes (recommend: after a 24h window where no h09
     premature-raise has been observed locally, or after a paired
     `OMNIGRAPH_PROCESSED_RETRY` floor reduction since the dynamic budget now
     handles the burst case).
   - Future env override `OMNIGRAPH_PER_DOC_AVG_S` for tuning per_doc_avg_s
     (defer; v1 hardcodes 60.0).
   - Metric instrumentation: emit `effective_budget_s` and `queue_depth` to
     the existing logger at function entry — easy follow-up quick.
   - Consider adding `kv_store_doc_status.json` schema check (e.g., if file
     hasn't been written in >10 min, that's its own anomaly worth surfacing).
</verification>

<success_criteria>
- pytest tests/unit/test_lightrag_queue_probe.py -v: 5/5 named tests PASS
- `python -c "from lib.lightrag_queue_probe import compute_dynamic_budget; ..."`: imports cleanly
- `python -c "import ingest_wechat"` (with DEEPSEEK_API_KEY=dummy): imports cleanly
- ingest_wechat.py git diff: ≤ 15 lines changed
- Lines 130-176 of ingest_wechat.py (Option B + Option A dual guard): byte-for-byte unchanged (verify with `git diff -U0 ingest_wechat.py | grep -E "^[-+]"` — should show ONLY the budget-calc additions and the (optional) RuntimeError message string change)
- Single local commit landed with conventional message; no push
- Hermes ~/.hermes/.env untouched; no SSH writes performed
- `git status -sb` clean except `.scratch/gqu-pa-spec.md` (gitignored)
- Two real Hermes-pulled fixtures present at `tests/fixtures/lightrag_doc_status/`
</success_criteria>

<output>
After completion, write summary to:
`.planning/quick/260512-bcy-gqu-pa-gqu-pattern-a-poll-based-budget-f/260512-bcy-SUMMARY.md`

Summary should cover the 6 final-report items in the `<verification>` section
above plus a 1-paragraph "what changed" overview.
</output>
