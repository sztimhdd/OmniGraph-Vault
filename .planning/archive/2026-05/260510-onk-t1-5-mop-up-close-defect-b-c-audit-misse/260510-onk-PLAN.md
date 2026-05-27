---
phase: quick-260510-onk
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - ingest_github.py
  - omnigraph_search/query.py
  - scripts/wave0c_smoke.py
  - batch_classify_kol.py
  - batch_scan_kol.py
autonomous: true
requirements:
  - DEFECT-B-IN-SCOPE  # Hardcoded llm_model_name="deepseek-v4-flash" closure outside T2/T3
  - DEFECT-C-IN-SCOPE  # Duplicate _load_hermes_env() closure outside T3

must_haves:
  truths:
    - "ingest_github.py:58 hardcoded `llm_model_name=\"deepseek-v4-flash\"` kwarg is removed"
    - "omnigraph_search/query.py:57 hardcoded `llm_model_name=\"deepseek-v4-flash\"` kwarg is removed"
    - "scripts/wave0c_smoke.py:71 hardcoded `llm_model_name=\"deepseek-v4-flash\"` kwarg is removed (verified-NON-orphan: 2 production-file refs + commit on 2026-05-09)"
    - "batch_classify_kol.py:52 _load_hermes_env() body replaced with `from config import load_env; load_env()`"
    - "batch_scan_kol.py:47 _load_hermes_env() body replaced with `from config import load_env; load_env()`"
    - "Final grep — Defect B closure outside T2/T3: only `ingest_wechat.py:318` (T2-excluded) remains"
    - "Final grep — Defect C closure outside T3: only `batch_ingest_from_spider.py:358` (T3-excluded) remains"
    - "Pytest pass rate matches T1 baseline (626 passed, 16 pre-existing failures, 5 skipped)"
  artifacts:
    - path: "ingest_github.py"
      provides: "Defect B fix (line 58 area)"
      contains_not: "llm_model_name=\"deepseek-v4-flash\""
    - path: "omnigraph_search/query.py"
      provides: "Defect B fix (line 57 area)"
      contains_not: "llm_model_name=\"deepseek-v4-flash\""
    - path: "scripts/wave0c_smoke.py"
      provides: "Defect B fix (line 71 area)"
      contains_not: "llm_model_name=\"deepseek-v4-flash\""
    - path: "batch_classify_kol.py"
      provides: "Defect C fix; _load_hermes_env body replaced with config.load_env"
      contains: "from config import load_env"
    - path: "batch_scan_kol.py"
      provides: "Defect C fix; _load_hermes_env body replaced with config.load_env"
      contains: "from config import load_env"
    - path: ".scratch/quick-260510-onk-final-grep-b.log"
      provides: "Final-grep evidence — Defect B closure"
    - path: ".scratch/quick-260510-onk-final-grep-c.log"
      provides: "Final-grep evidence — Defect C closure"
    - path: ".scratch/quick-260510-onk-pytest.log"
      provides: "Pytest evidence; modified-files targeted suites + relevant baseline checks"
  key_links:
    - from: "ingest_github.py"
      to: "lib/llm_complete.get_llm_func"
      via: "LightRAG ctor without hardcoded llm_model_name"
      pattern: "llm_model_func=get_llm_func\\(\\)"
    - from: "batch_classify_kol.py"
      to: "config.load_env"
      via: "import + call replaces _load_hermes_env body"
      pattern: "from config import load_env"
    - from: "batch_scan_kol.py"
      to: "config.load_env"
      via: "import + call replaces _load_hermes_env body"
      pattern: "from config import load_env"
---

<objective>
Mechanical mop-up — close 5 audit-missed sites surfaced during T1 (Quick 260510-l14, just shipped). After T1.5, both Defect B (hardcoded `llm_model_name="deepseek-v4-flash"`) and Defect C (duplicate `_load_hermes_env()`) are CLOSED outside T2 (`ingest_wechat.py`) and T3 (`batch_ingest_from_spider.py`) territory.

Purpose: T1 SUMMARY explicitly carved 5 sites out of scope ("OUT OF SCOPE for T2" section). T1.5 closes them now while T1 patterns are fresh; this prevents drift between T1 fixes and remaining mop-up.

Output: 1 atomic commit (5 files modified, 0 deleted), final-grep evidence + pytest log in `.scratch/`, SUMMARY.md.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/audit/POLLUTION-AUDIT.md
@.planning/quick/260510-l14-t1-cross-cutting-boot-time-module-init-p/260510-l14-SUMMARY.md
@./CLAUDE.md

@config.py
@lib/cli_bootstrap.py
@lib/llm_deepseek.py
@lib/llm_complete.py
@query_lightrag.py

<interfaces>
<!-- Canonical fix patterns the executor will apply. Both come from T1 commits. -->
<!-- Executor should mirror these — no codebase exploration needed. -->

From `query_lightrag.py:18-24` (T1 W2 commit `03eee42`) — Defect B canonical fix:
```python
async def query_and_synthesize(query_text: str):
    """Initializes LightRAG and performs a query to synthesize a markdown response."""
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=get_llm_func(),
        embedding_func=embedding_func,
    )
    # NOTE: No `llm_model_name="deepseek-v4-flash"` kwarg.
    # LightRAG defaults the model name; get_llm_func() picks the actual provider.
```

From `lib/llm_deepseek.py:43-49` (T1 W3 commit `14f1136`) — Defect C canonical fix:
```python
# Defect C (quick 260510-l14): use the canonical loader from config.py
# instead of duplicating the .env parser. lib.llm_deepseek may import before
# CLI scripts call bootstrap_cli(), so we still need to populate the env at
# module top — but config.load_env() is now the single source of truth.
from config import load_env

load_env()
```
For T1.5 batch scripts: replace the entire `def _load_hermes_env(): ...` body + the call site (`_load_hermes_env()` line 394 in batch_classify_kol.py / line 258 in batch_scan_kol.py) with the canonical 2-line form. Concretely: delete the function definition, change the call site `_load_hermes_env()` to `load_env()`, add `from config import load_env` to the imports.

Pre-verification grep evidence (already collected):
- `batch_classify_kol.py:52` defines `_load_hermes_env`, `batch_classify_kol.py:394` calls it.
- `batch_scan_kol.py:47` defines `_load_hermes_env`, `batch_scan_kol.py:258` calls it.
- `scripts/wave0c_smoke.py` is verified NON-orphan: referenced as comment in `lib/lightrag_embedding.py:47` + `tests/unit/test_ainsert_persistence_contract.py:147`; last commit `e538b2d` on 2026-05-09 (within 30 days). Apply Option a (fix), do NOT delete.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Close Defect B (3 sites) — remove hardcoded llm_model_name</name>
  <files>ingest_github.py, omnigraph_search/query.py, scripts/wave0c_smoke.py</files>
  <action>
For each of the 3 target lines, apply T1 W2's canonical fix pattern (commit `03eee42`):

  1. **`ingest_github.py:58`** — Read 5 lines of context (lines 54-62). Confirm pattern: inside `LightRAG(...)` ctor, kwargs include `llm_model_func=get_llm_func()` (line 56) AND `llm_model_name="deepseek-v4-flash"` (line 58). Delete line 58 entirely (the hardcoded kwarg + trailing comma cleanup if needed). Result: `LightRAG(working_dir=..., llm_model_func=get_llm_func(), embedding_func=embedding_func,)` — no `llm_model_name` kwarg.

  2. **`omnigraph_search/query.py:57`** — Read 5 lines of context (lines 53-61). Same shape: line 55 has `llm_model_func=get_llm_func()`, line 57 has `llm_model_name="deepseek-v4-flash"`. Delete line 57.

  3. **`scripts/wave0c_smoke.py:71`** — Read 5 lines of context (lines 67-75). Same shape inside `LightRAG(...)` ctor: line 69 has `llm_model_func=get_llm_func()`, line 71 has `llm_model_name="deepseek-v4-flash"`. Delete line 71. Note: line 72-74 contain `embedding_func_max_async`, `embedding_batch_num`, `llm_model_max_async` kwargs — preserve those (they tune smoke perf and are unrelated to Defect B).

Verify-then-act protocol per site:
- Read 5-line context first
- Confirm pattern matches (ctor uses `get_llm_func()` AND has hardcoded `deepseek-v4-flash`)
- If pattern matches: apply the fix
- If pattern does NOT match (line shifted, file refactored, kwarg structure differs): STOP that site, document deviation, continue with others

Surgical-changes discipline (CLAUDE.md Principle 3):
- Touch ONLY the line containing the `llm_model_name` kwarg + adjacent comma if syntactically required
- Do NOT reformat the rest of the ctor call
- Do NOT add explanatory comments inline (the rationale belongs in commit message + SUMMARY)
- Do NOT touch unrelated lines / imports / docstrings

Line-ending preservation (T1 Risk event #2): `ingest_github.py`, `omnigraph_search/query.py`, `scripts/wave0c_smoke.py` are all LF (verified by T1 normalization helper). Edit tool's default LF should be safe; if `git diff --stat` shows whole-file churn after the edit, re-normalize per T1 Deviation 2 pattern.

DO NOT bundle "while we're here" tweaks. No comment cleanup, no formatter pass, no model-name updates elsewhere.

References: T1 W2 commit `03eee42`, T1 SUMMARY "OUT OF SCOPE for T2" section, query_lightrag.py:18-24 (canonical fix exemplar).
  </action>
  <verify>
    <automated>cd "C:/Users/huxxha/Desktop/OmniGraph-Vault" &amp;&amp; grep -n 'llm_model_name="deepseek-v4-flash"' ingest_github.py omnigraph_search/query.py scripts/wave0c_smoke.py 2>&amp;1 | tee .scratch/quick-260510-onk-defect-b-grep.log; echo "---"; grep -rn 'llm_model_name="deepseek-v4-flash"' --include="*.py" . | tee -a .scratch/quick-260510-onk-defect-b-grep.log</automated>
  </verify>
  <done>
    - `ingest_github.py:58`, `omnigraph_search/query.py:57`, `scripts/wave0c_smoke.py:71` no longer contain `llm_model_name="deepseek-v4-flash"` kwarg
    - Final repo-wide grep `llm_model_name="deepseek-v4-flash"` shows ONLY `ingest_wechat.py:318` (T2-excluded) — 1 line total
    - All 3 files still parse (Python syntax intact); imports unchanged
  </done>
</task>

<task type="auto">
  <name>Task 2: Close Defect C (2 sites) — replace _load_hermes_env with config.load_env</name>
  <files>batch_classify_kol.py, batch_scan_kol.py</files>
  <action>
For each of the 2 target files, apply T1 W3's canonical fix pattern (commit `14f1136`):

  1. **`batch_classify_kol.py`** — Read full context around lines 50-75 (definition) and lines 390-400 (call site).
     - Confirm pattern: `def _load_hermes_env() -> None:` at line 52, body lines 53-74, call `_load_hermes_env()` at line 394.
     - Action:
       a. Add `from config import load_env` to the imports section (top of file). Place it adjacent to existing relative-style imports (e.g., near `from lib import INGESTION_LLM, generate_sync` at line 45). Use surgical placement — do NOT reorganize the import block.
       b. Delete the entire `def _load_hermes_env() -> None: ... ` function (lines 52-74 inclusive). 23 LOC removed.
       c. Update call site at (formerly) line 394: replace `_load_hermes_env()` with `load_env()`. Single token change on one line.

  2. **`batch_scan_kol.py`** — Same pattern:
     - Confirm: `def _load_hermes_env() -> None:` at line 47, body lines 48-70, call `_load_hermes_env()` at line 258.
     - Action:
       a. Add `from config import load_env` to imports (surgical placement near other top-level imports).
       b. Delete the entire `def _load_hermes_env() -> None: ...` function (lines 47-70 inclusive). 24 LOC removed.
       c. Update call site at (formerly) line 258: replace `_load_hermes_env()` with `load_env()`.

Verify-then-act protocol per site:
- Read function definition + call site BEFORE editing
- Confirm pattern matches (same 24-LOC body shape; reads from `Path.home() / ".hermes" / ".env"` AND `Path("//wsl.localhost/...")` fallback; populates `os.environ` only when key absent)
- If pattern matches: apply the fix
- If pattern does NOT match (function refactored, additional callers, signature changed): STOP that site, document deviation

Behavioral note: `config.load_env()` reads only `Path.home() / ".hermes" / ".env"` (no WSL fallback). The WSL fallback in the duplicate `_load_hermes_env` was Hermes-specific dev-time scaffolding. T1 W3 already accepted this same trade-off when retiring `lib/llm_deepseek._load_hermes_env`. Per T1 SUMMARY closure check (cross-cutting issue 3, "PARTIAL → CLOSED"), the canonical loader IS `config.load_env`; T1.5 just extends the same retirement to the 2 batch scripts.

Surgical-changes discipline:
- Touch ONLY the function definition (delete) + the call site (1-token replace) + 1 import line (add)
- Do NOT touch other functions, docstrings, logging setup
- Do NOT remove unrelated unused imports created by the deletion (Python's GC handles dead imports; `Path` may still be used elsewhere — verify via grep before removing any imports)

Line-ending preservation: both `batch_classify_kol.py` and `batch_scan_kol.py` should already be LF (Linux-deployment-targeted). Verify with `file -bi` if uncertain. If Edit produces CRLF/LF churn, re-normalize per T1 Deviation 2.

References: T1 W3 commit `14f1136` (`lib/llm_deepseek.py:37-55` canonical), T1 SUMMARY closure check ("issue 3 — PARTIAL"), `config.py:42-53` canonical `load_env` definition.
  </action>
  <verify>
    <automated>cd "C:/Users/huxxha/Desktop/OmniGraph-Vault" &amp;&amp; grep -rn 'def _load_hermes_env\|def load_hermes_env' --include="*.py" . | tee .scratch/quick-260510-onk-defect-c-grep.log; echo "---"; python -c "import ast; ast.parse(open('batch_classify_kol.py').read()); print('batch_classify_kol.py parses OK')"; python -c "import ast; ast.parse(open('batch_scan_kol.py').read()); print('batch_scan_kol.py parses OK')"</automated>
  </verify>
  <done>
    - `batch_classify_kol.py` no longer defines `_load_hermes_env`; calls `load_env()` (imported from `config`) instead
    - `batch_scan_kol.py` no longer defines `_load_hermes_env`; calls `load_env()` (imported from `config`) instead
    - Final repo-wide grep `def _load_hermes_env|def load_hermes_env` shows ONLY `batch_ingest_from_spider.py:358` (T3-excluded) — 1 line total
    - Both files parse via `ast.parse` (Python syntax intact)
  </done>
</task>

<task type="auto">
  <name>Task 3: Pytest verification + atomic commit + SUMMARY</name>
  <files>.scratch/quick-260510-onk-pytest.log, .scratch/quick-260510-onk-final-grep-b.log, .scratch/quick-260510-onk-final-grep-c.log, .planning/quick/260510-onk-t1-5-mop-up-close-defect-b-c-audit-misse/260510-onk-SUMMARY.md</files>
  <action>
Step 3.1 — Final grep evidence (cite in SUMMARY):

```bash
cd "C:/Users/huxxha/Desktop/OmniGraph-Vault"

# Defect B final grep
grep -rn 'llm_model_name="deepseek-v4-flash"' --include="*.py" . > .scratch/quick-260510-onk-final-grep-b.log 2>&1
# Expect: ONLY ingest_wechat.py:318 (T2-excluded). 0 hits at any other line.

# Defect C final grep
grep -rn 'def _load_hermes_env\|def load_hermes_env' --include="*.py" . > .scratch/quick-260510-onk-final-grep-c.log 2>&1
# Expect: ONLY batch_ingest_from_spider.py:358 (T3-excluded). 0 hits in batch_classify_kol.py or batch_scan_kol.py.
```

If either final grep shows MORE than the expected single excluded site, STOP — a fix did not land and Task 1 or 2 must be re-checked.

Step 3.2 — Targeted pytest on modified files' suites + baseline check:

```bash
cd "C:/Users/huxxha/Desktop/OmniGraph-Vault"

# T1 baseline reference: 626 passed, 16 pre-existing failures, 5 skipped, 9 warnings.
# Run full suite to verify no T1.5-induced regressions.
.venv/Scripts/python -m pytest tests/ -q 2>&1 | tee .scratch/quick-260510-onk-pytest.log

# Acceptance: pass count ≥ 626 AND failure count ≤ 16 (same set; spot-check failures
# match the T1 SUMMARY "16 pre-existing" list at line 167-181 of T1 SUMMARY).
# If new failures appear, isolate them — they MUST be either:
#   (a) pre-existing test-pollution variants not in T1's 16 list (verify via `git stash`
#       baseline run on HEAD), OR
#   (b) actual T1.5 regressions (rare given mechanical scope; STOP if found).
```

Note: the 5 modified files do NOT have exact-match unit-test files. Targeted suite means the full pytest run, since import-related changes can affect any consumer. `.venv/Scripts/python` is the canonical Windows venv interpreter per CLAUDE.md.

Step 3.3 — Atomic commit (forward-only, no rebase/amend):

Choose 1-commit OR 2-commit form per planner discretion (5 trivial mechanical fixes — single commit is acceptable).

Recommended 1-commit form:
```bash
git add ingest_github.py omnigraph_search/query.py scripts/wave0c_smoke.py \
        batch_classify_kol.py batch_scan_kol.py
git commit -m "fix(t1.5-260510-onk): close defect B + C audit-missed sites" \
           -m "Defect B (3 sites): remove hardcoded llm_model_name=\"deepseek-v4-flash\"" \
           -m "  - ingest_github.py:58, omnigraph_search/query.py:57, scripts/wave0c_smoke.py:71" \
           -m "Defect C (2 sites): replace _load_hermes_env() with config.load_env()" \
           -m "  - batch_classify_kol.py:52, batch_scan_kol.py:47" \
           -m "Patterns: T1 W2 commit 03eee42 (B), T1 W3 commit 14f1136 (C)" \
           -m "Verified-NON-orphan: scripts/wave0c_smoke.py — last commit e538b2d 2026-05-09 + 2 production-file refs"
```

DO NOT use `--amend`, `git reset --soft`, `git rebase` (per CLAUDE.md "Lessons Learned 2026-05-06 #5" — concurrent GSD agent staging-race risk).

Step 3.4 — Write SUMMARY.md mirroring T1 shape (`260510-l14-SUMMARY.md`).

Required sections:
1. Frontmatter — `phase`, `plan`, `type`, `status: complete`, `completed: 2026-05-10`, `commits: [<sha>]`, `loc_delta: <signed>`, `defects_closed: [POLLUTION-B-IN-SCOPE, POLLUTION-C-IN-SCOPE]`
2. Per-site outcome table: site (file:line) | defect | action | line-range diff cite | result (PASS / DEVIATION)
3. Final-grep evidence with `.scratch/quick-260510-onk-final-grep-{b,c}.log` cites + line counts
4. Pytest result vs T1 baseline (cite `.scratch/quick-260510-onk-pytest.log`)
5. Closure check vs POLLUTION-AUDIT.md cross-cutting issues #2 (B) and #3 (C) — should mark both **CLOSED outside T2/T3 territory** (residual: ingest_wechat.py for #2, batch_ingest_from_spider.py for #3)
6. Risk events / deviations (any site where `verify-then-act` produced STOP)
7. No-fabrication compliance — every claim cites `.scratch/` log path or git SHA

Anti-fabrication discipline (CLAUDE.md Lesson 2026-05-08 #2):
- Every "X verified" assertion MUST cite a `.scratch/` raw log file with line range OR a git SHA
- DO NOT claim test pass/fail counts without referencing the pytest log
- DO NOT claim grep ceiling without referencing the final-grep log
  </action>
  <verify>
    <automated>cd "C:/Users/huxxha/Desktop/OmniGraph-Vault" &amp;&amp; git log --oneline HEAD~1..HEAD &amp;&amp; ls -la .scratch/quick-260510-onk-*.log &amp;&amp; ls -la .planning/quick/260510-onk-t1-5-mop-up-close-defect-b-c-audit-misse/260510-onk-SUMMARY.md &amp;&amp; tail -5 .scratch/quick-260510-onk-final-grep-b.log &amp;&amp; tail -5 .scratch/quick-260510-onk-final-grep-c.log</automated>
  </verify>
  <done>
    - 1 atomic commit on main (forward-only, no rebase/amend) with all 5 modified files
    - `.scratch/quick-260510-onk-final-grep-b.log` shows ONLY `ingest_wechat.py:318` for Defect B
    - `.scratch/quick-260510-onk-final-grep-c.log` shows ONLY `batch_ingest_from_spider.py:358` for Defect C
    - `.scratch/quick-260510-onk-pytest.log` shows pass count ≥ 626; failures = same 16 pre-existing set as T1 baseline
    - `.planning/quick/260510-onk-t1-5-mop-up-close-defect-b-c-audit-misse/260510-onk-SUMMARY.md` exists with all 7 required sections + commit SHA cited in frontmatter
  </done>
</task>

</tasks>

<verification>
Cross-task acceptance gates (ALL must hold):

1. **Final grep — Defect B closure outside T2/T3** (`.scratch/quick-260510-onk-final-grep-b.log`):
   `grep -rn 'llm_model_name="deepseek-v4-flash"' --include="*.py" .`
   shows ONLY `ingest_wechat.py:318` (T2-excluded). **0 hits at any other line.**

2. **Final grep — Defect C closure outside T3** (`.scratch/quick-260510-onk-final-grep-c.log`):
   `grep -rn 'def _load_hermes_env\|def load_hermes_env' --include="*.py" .`
   shows ONLY `batch_ingest_from_spider.py:358` (T3-excluded). **0 hits in batch_classify_kol.py or batch_scan_kol.py.**

3. **Pytest pass count ≥ 626; failure set = T1's 16 pre-existing** (`.scratch/quick-260510-onk-pytest.log`):
   No new failures. Same pre-existing-vs-new separation as T1 SUMMARY Risk events (lines 167-181).

4. **Single atomic commit** (forward-only): `git log --oneline HEAD~1..HEAD` shows 1 SHA touching exactly the 5 target files.

5. **SUMMARY.md** exists with all 7 sections; every claim cites `.scratch/` log line range OR git SHA.

If ANY gate fails: STOP, document in SUMMARY's "Risk events" section, do NOT mass-edit to "fix" the gate.
</verification>

<success_criteria>
- All 5 sites mechanically fixed per T1 canonical patterns (commit `03eee42` for B, commit `14f1136` for C)
- Defect B + C CLOSED outside T2/T3 territory (residual: 1 ingest_wechat.py line + 1 batch_ingest_from_spider.py line, both expected & documented)
- Pytest baseline preserved (626 pass / 16 pre-existing fail / 5 skip)
- 1 atomic commit on main, forward-only
- SUMMARY.md follows T1 shape, anti-fabrication compliance asserted
- Net LOC delta: roughly -50 (3 lines deleted for Defect B + ~47 lines deleted for Defect C duplicate function bodies)
- Zero modifications to T1 territory (lib/cli_bootstrap.py, lib/llm_deepseek.py, lib/__init__.py, config.py, lib/llm_complete.py)
- Zero modifications to T2 territory (ingest_wechat.py)
- Zero modifications to T3 territory (batch_ingest_from_spider.py)
- `scripts/wave0c_smoke.py` is **kept and fixed** (NOT deleted) — verified-NON-orphan evidence: 2 production-file references + commit `e538b2d` on 2026-05-09 (within 30-day window)
</success_criteria>

<output>
After completion, create `.planning/quick/260510-onk-t1-5-mop-up-close-defect-b-c-audit-misse/260510-onk-SUMMARY.md` with:
- Frontmatter (phase, plan, type, status, completed, commits, loc_delta, defects_closed)
- Per-site outcome table (5 rows: 3 Defect B + 2 Defect C)
- Final-grep evidence cites
- Pytest result vs T1 baseline
- Closure check vs POLLUTION-AUDIT.md issues #2 + #3
- Risk events / deviations (if any)
- No-fabrication compliance assertion
</output>
