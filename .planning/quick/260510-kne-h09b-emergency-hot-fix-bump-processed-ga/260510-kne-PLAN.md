---
quick_id: 260510-kne
commit_slug: 260510-h09b
type: quick
wave: 1
depends_on: []
files_modified:
  - ingest_wechat.py
  - CLAUDE.md
  - .planning/STATE.md
autonomous: true
requirements: [H09B-01]
must_haves:
  truths:
    - "Default PROCESSED-gate retry budget is 60s (30 retries × 2.0s) instead of 6s (3 × 2.0s)"
    - "Both retry count and backoff are env-overridable via OMNIGRAPH_PROCESSED_RETRY and OMNIGRAPH_PROCESSED_BACKOFF"
    - "All 6 existing unit tests in tests/unit/test_ingest_article_processed_gate.py still pass without modification"
    - "CLAUDE.md local-dev env-var table documents the two new variables"
    - "Local HEAD is rebased on origin/main and pushed cleanly (no rtr conflict)"
  artifacts:
    - path: "ingest_wechat.py"
      provides: "Module-level constants PROCESSED_VERIFY_MAX_RETRIES + PROCESSED_VERIFY_BACKOFF_S sourced from env with defaults 30 / 2.0"
      contains: 'os.getenv("OMNIGRAPH_PROCESSED_RETRY"'
    - path: "CLAUDE.md"
      provides: "Two new rows in the 'Local dev env vars (quick task 260504-g7a)' table documenting OMNIGRAPH_PROCESSED_RETRY + OMNIGRAPH_PROCESSED_BACKOFF"
      contains: "OMNIGRAPH_PROCESSED_RETRY"
    - path: ".planning/STATE.md"
      provides: "Quick Tasks Completed row keyed 260510-kne"
      contains: "260510-kne"
    - path: ".scratch/h09b-pytest-260510-kne.log"
      provides: "Captured pytest output proving 6 GREEN"
    - path: ".scratch/h09b-default-260510-kne.log"
      provides: "Captured default-value output (30 2.0)"
    - path: ".scratch/h09b-env-260510-kne.log"
      provides: "Captured env-override output (5 0.5)"
  key_links:
    - from: "ingest_wechat.py:52-53 module-level constants"
      to: "ingest_wechat._verify_doc_processed_or_raise default kwargs"
      via: "kwarg defaults max_retries=PROCESSED_VERIFY_MAX_RETRIES, backoff_s=PROCESSED_VERIFY_BACKOFF_S"
      pattern: 'max_retries: int = PROCESSED_VERIFY_MAX_RETRIES'
---

<objective>
Emergency hot-fix bumping the post-ainsert PROCESSED-gate retry budget shipped in quick 260510-h09 (commit 949e3f4) from 6s (3 × 2.0s) to 60s (30 × 2.0s), with env-var override hooks.

Purpose: h09 shipped a budget too short for heavy WeChat articles whose Phase 2 entity-merging routinely takes 30-180s. gqu Mock Scenario 4 + Hermes 2026-05-10 ~13:50 ADT live observation confirm the 6s default forces loud-failure on every heavy article and breaks daily throughput.

Output: 2-line constant change (now env-overridable) + 2 new CLAUDE.md doc rows + STATE.md row + atomic forward-only commit + clean push to origin/main.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@ingest_wechat.py
@tests/unit/test_ingest_article_processed_gate.py

<interfaces>
<!-- Existing module-level state in ingest_wechat.py:1-66 -->
<!-- Executor uses these directly — no further codebase exploration needed. -->

From ingest_wechat.py:1 (already present):
```python
import os
```

From ingest_wechat.py:47-53 (TARGET — current state to be replaced):
```python
# 2026-05-10 hot-fix (quick 260510-h09): retry budget for the post-ainsert
# PROCESSED verification helper. Three attempts × 2s backoff covers the
# 2026-05-09/10 ainsert async-pipeline race where LightRAG's internal
# enqueue had not yet promoted the doc to status='PROCESSED' by the time
# the caller checked.
PROCESSED_VERIFY_MAX_RETRIES = 3
PROCESSED_VERIFY_BACKOFF_S = 2.0
```

From ingest_wechat.py:60-66 (downstream consumer — unchanged):
```python
async def _verify_doc_processed_or_raise(
    rag,
    doc_id: str,
    *,
    max_retries: int = PROCESSED_VERIFY_MAX_RETRIES,
    backoff_s: float = PROCESSED_VERIFY_BACKOFF_S,
) -> None:
```
The helper reads constants as kwarg defaults at function-definition time. Bumping the constants flows through to all callers that omit the kwargs. Existing 6 unit tests pass kwargs explicitly (`max_retries=3, backoff_s=0.0`) so they are insulated from the default change and MUST still pass byte-for-byte.

From CLAUDE.md:213-217 (TARGET — table to extend):
```markdown
| Var | Required | Default | Purpose |
|-----|----------|---------|---------|
| `OMNIGRAPH_LLM_PROVIDER` | No | `deepseek` | ... |
| `OMNIGRAPH_LLM_MODEL` | No | `gemini-3.1-flash-lite-preview` | ... |
| `OMNIGRAPH_VISION_SKIP_PROVIDERS` | No | _(empty)_ | ... |
| `OMNIGRAPH_BASE_DIR` | Yes for local dev | `~/.hermes/omonigraph-vault` | Absolute path to runtime data root. Empty string treated as unset. |
| `OMNIGRAPH_LLM_TIMEOUT_SEC` | No | `600` | Int seconds; applies to Vertex Gemini LLM calls only. DeepSeek path unaffected. |
```
Append two new rows AFTER `OMNIGRAPH_LLM_TIMEOUT_SEC` — same column ordering (Var | Required | Default | Purpose).
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Bump PROCESSED-gate budget to env-overridable defaults (30 × 2.0s = 60s); update CLAUDE.md doc rows + STATE.md; verify 3 gates; rebase + atomic commit + push</name>
  <files>ingest_wechat.py, CLAUDE.md, .planning/STATE.md</files>
  <action>
    Implements requirement H09B-01 (emergency hot-fix raising h09 PROCESSED-gate budget envelope from 6s → 60s with env override).

    **Step 1 — Source-code change at ingest_wechat.py:52-53.** Replace the two literal-int constants with env-sourced reads. `import os` is already present at line 1 — do NOT add a new import.

    BEFORE (current contents of lines 52-53):
    ```python
    PROCESSED_VERIFY_MAX_RETRIES = 3
    PROCESSED_VERIFY_BACKOFF_S = 2.0
    ```

    AFTER:
    ```python
    PROCESSED_VERIFY_MAX_RETRIES = int(os.getenv("OMNIGRAPH_PROCESSED_RETRY", "30"))
    PROCESSED_VERIFY_BACKOFF_S = float(os.getenv("OMNIGRAPH_PROCESSED_BACKOFF", "2.0"))
    ```

    Comment block at lines 47-51 referencing quick 260510-h09 STAYS (do not delete). Optionally append ONE short line acknowledging 260510-h09b raised the envelope, e.g.:
    ```
    # 2026-05-10 quick 260510-h09b: budget envelope bumped 6s → 60s default
    # (30 × 2.0s) with OMNIGRAPH_PROCESSED_RETRY / OMNIGRAPH_PROCESSED_BACKOFF
    # env override; covers Phase 2 entity-merging on heavy WeChat articles.
    ```
    Keep total comment delta under 5 lines. Do NOT touch any other line in `ingest_wechat.py`.

    **Hard out-of-scope (do NOT do):**
    - Do NOT refactor `_verify_doc_processed_or_raise` (lines 60-onwards). Its kwarg signature is unchanged; only the module-level defaults move.
    - Do NOT modify `tests/unit/test_ingest_article_processed_gate.py`. Existing 6 tests pass `max_retries`/`backoff_s` kwargs explicitly and MUST still pass byte-for-byte.
    - Do NOT touch `batch_ingest_from_spider.py` (Quick A scope, after rtr).
    - Do NOT touch any Vision sub-doc helper (Quick C scope).
    - Do NOT add a poll API or smart backoff (Pattern A — separate quick).
    - Do NOT add new tests — bump is config-level, not behavioral.

    **Step 2 — CLAUDE.md doc-row append.** Locate the table under section header "### Local dev env vars (quick task 260504-g7a)" (grep `OMNIGRAPH_BASE_DIR` confirms line 216-217 region). After the existing `OMNIGRAPH_LLM_TIMEOUT_SEC` row at line 217, INSERT these two rows BEFORE the blank line that follows the table:

    ```markdown
    | `OMNIGRAPH_PROCESSED_RETRY` | No | `30` | Int. h09 PROCESSED-gate max retries; combined with `OMNIGRAPH_PROCESSED_BACKOFF` controls the post-ainsert verification budget (default 30 × 2.0s = 60s, was 3 × 2.0s = 6s before quick 260510-h09b). |
    | `OMNIGRAPH_PROCESSED_BACKOFF` | No | `2.0` | Float seconds. h09 PROCESSED-gate retry backoff. See `OMNIGRAPH_PROCESSED_RETRY`. |
    ```

    Match the existing column ordering (Var | Required | Default | Purpose) and existing markdown conventions (backticks around var names, backticks around defaults, sentence-style purpose). Do NOT re-flow other rows.

    **Step 3 — Run verification gates and capture to .scratch/.** Create `.scratch/` dir if missing. Run all three gates from project root with `.venv/Scripts/` Python:

    Gate 1 — pytest (must show 6 passed, 0 failed):
    ```bash
    .venv/Scripts/python -m pytest tests/unit/test_ingest_article_processed_gate.py -v 2>&1 | tee .scratch/h09b-pytest-260510-kne.log
    ```

    Gate 2 — default values (expected output: `30 2.0`):
    ```bash
    DEEPSEEK_API_KEY=dummy .venv/Scripts/python -c "import ingest_wechat as i; print(i.PROCESSED_VERIFY_MAX_RETRIES, i.PROCESSED_VERIFY_BACKOFF_S)" 2>&1 | tee .scratch/h09b-default-260510-kne.log
    ```

    Gate 3 — env override (expected output: `5 0.5`):
    ```bash
    DEEPSEEK_API_KEY=dummy OMNIGRAPH_PROCESSED_RETRY=5 OMNIGRAPH_PROCESSED_BACKOFF=0.5 .venv/Scripts/python -c "import ingest_wechat as i; print(i.PROCESSED_VERIFY_MAX_RETRIES, i.PROCESSED_VERIFY_BACKOFF_S)" 2>&1 | tee .scratch/h09b-env-260510-kne.log
    ```

    Note: `DEEPSEEK_API_KEY=dummy` satisfies the eager Phase 5 import at `lib/__init__.py` (FLAG 2 documented in CLAUDE.md).

    All three logs MUST be captured to disk — SUMMARY.md will cite their paths verbatim. If any gate fails (pytest red, default not `30 2.0`, env-override not `5 0.5`), STOP and surface — do NOT proceed to commit.

    **Step 4 — STATE.md update.** Open `.planning/STATE.md`, locate the Quick Tasks Completed table (search for `## Quick Tasks Completed` heading; if multiple Quick Tasks rows exist, append in chronological order — typically below the most recent `260510-*` row). Append a row keyed `260510-kne` with the user's commit-message-derived Description column:

    | 260510-kne | 2026-05-10 | fix(ingest-260510-h09b): bump PROCESSED gate budget 6s → 60s with env override |

    Match the exact column format already in use (read 1-2 existing rows first to confirm column count + delimiter style). Do NOT modify the front-matter `last_activity` / `last_updated` / `progress.*` fields beyond what is required to record this quick — keep changes surgical to the Quick Tasks block.

    **Step 5 — rtr-conflict guard + atomic commit + push.** Pre-flight already confirmed local HEAD == origin/main == a40edc8 (no active rtr in flight). Still:

    ```bash
    git fetch origin
    git rebase origin/main
    ```

    If rebase reports a conflict (especially in `ingest_wechat.py` top-of-file imports/constants region), STOP IMMEDIATELY and surface to user. Do NOT auto-resolve. The user explicitly warned about this.

    If rebase is clean, stage and commit atomically:
    ```bash
    git add ingest_wechat.py CLAUDE.md .planning/STATE.md
    git commit -m "fix(ingest-260510-h09b): bump PROCESSED gate budget 6s → 60s with env override"
    git push origin main
    ```

    Commit message is verbatim per user instruction — do NOT add Co-Authored-By trailer (project has attribution disabled globally per `~/.claude/settings.json`). Do NOT amend the prior 949e3f4 commit (forward-only — new commit).

    Note: `.scratch/` is gitignored; the three log files are NOT staged. Their paths still get cited in SUMMARY.md as evidence.
  </action>
  <verify>
    <automated>
      .venv/Scripts/python -m pytest tests/unit/test_ingest_article_processed_gate.py -v
    </automated>
    Plus manual gate inspection:
    - `cat .scratch/h09b-pytest-260510-kne.log | tail -20` shows `6 passed`
    - `cat .scratch/h09b-default-260510-kne.log` shows exactly `30 2.0`
    - `cat .scratch/h09b-env-260510-kne.log` shows exactly `5 0.5`
    - `git log -1 --format='%H %s'` shows the new commit with message `fix(ingest-260510-h09b): bump PROCESSED gate budget 6s → 60s with env override`
    - `git status` shows clean working tree
    - `git rev-parse HEAD` == `git rev-parse origin/main` (push succeeded)
  </verify>
  <done>
    - `ingest_wechat.py:52-53` reads constants from `OMNIGRAPH_PROCESSED_RETRY` / `OMNIGRAPH_PROCESSED_BACKOFF` with defaults `30` / `2.0`
    - `tests/unit/test_ingest_article_processed_gate.py` reports 6/6 GREEN with no test-file modifications
    - `python -c "import ingest_wechat as i; print(i.PROCESSED_VERIFY_MAX_RETRIES, i.PROCESSED_VERIFY_BACKOFF_S)"` prints `30 2.0` by default and `5 0.5` under env override
    - `CLAUDE.md` table under "Local dev env vars (quick task 260504-g7a)" has two new rows for `OMNIGRAPH_PROCESSED_RETRY` and `OMNIGRAPH_PROCESSED_BACKOFF` matching existing row format
    - `.planning/STATE.md` Quick Tasks Completed table has new row `260510-kne` with commit-message description
    - Three `.scratch/h09b-*-260510-kne.log` files exist with captured raw command output
    - Single atomic commit with message `fix(ingest-260510-h09b): bump PROCESSED gate budget 6s → 60s with env override` is pushed to origin/main; no force-push, no amend, no rebase conflict
  </done>
</task>

</tasks>

<verification>
Overall quick-task acceptance (one-shot, no checker phase):
1. The three `.scratch/h09b-*-260510-kne.log` files exist and contain raw command output. SUMMARY.md cites these file paths verbatim — no "should pass" / "expected to" hedging.
2. `git log --oneline -3` shows the new commit immediately after `a40edc8` with the exact verbatim message.
3. `git rev-parse HEAD` == `git rev-parse origin/main` (push landed).
4. Existing 6 PROCESSED-gate unit tests are GREEN unchanged.
5. Default constants under no-env shell yield `30 2.0`; under `OMNIGRAPH_PROCESSED_RETRY=5 OMNIGRAPH_PROCESSED_BACKOFF=0.5` they yield `5 0.5`.
</verification>

<success_criteria>
- 6/6 GREEN on `tests/unit/test_ingest_article_processed_gate.py` (no test modifications)
- Default budget moved from 6s (3 × 2.0s) → 60s (30 × 2.0s)
- Env override `OMNIGRAPH_PROCESSED_RETRY` + `OMNIGRAPH_PROCESSED_BACKOFF` both functional
- CLAUDE.md table has 2 new rows in correct column-order
- STATE.md Quick Tasks Completed table has 260510-kne row
- Atomic forward-only commit `fix(ingest-260510-h09b): bump PROCESSED gate budget 6s → 60s with env override` pushed to origin/main
- No conflict surfaced from `git rebase origin/main` (or if conflict surfaced, user was alerted and execution halted)
- All three verification gate logs captured under `.scratch/`
</success_criteria>

<output>
After completion, create `.planning/quick/260510-kne-h09b-emergency-hot-fix-bump-processed-ga/260510-kne-SUMMARY.md` with:
- Files changed (3): paths + 1-line diff summary each
- Verification evidence: explicit cite of `.scratch/h09b-pytest-260510-kne.log`, `.scratch/h09b-default-260510-kne.log`, `.scratch/h09b-env-260510-kne.log` with key lines quoted (e.g. "6 passed in N.NNs", "30 2.0", "5 0.5")
- Commit SHA + verbatim message
- Push confirmation (`git rev-parse HEAD == origin/main`)
- Anti-fabrication: no "should pass" / "expected to" / "I believe" — every claim cites a real artifact
</output>
