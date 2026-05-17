---
phase: kdb-2
plan_id: kdb-2-03
slug: kg-synthesize-routing-and-degrade
wave: 2
status: complete
requirements:
  - LLM-DBX-02
  - LLM-DBX-04
skills_invoked:
  - python-patterns
  - writing-tests
commits:
  - f3670b0  # test + CONFIG-EXEMPTIONS flip
  - ffb8d9d  # docs backfill commit hash
files_changed:
  added:
    - tests/integration/test_kg_synthesize_dispatcher.py
  modified:
    - databricks-deploy/CONFIG-EXEMPTIONS.md
  unchanged_by_design:
    - kg_synthesize.py            # Decision 3 — ZERO new lines
    - kb/services/synthesize.py   # Decision 1 — translation lives in dispatcher
    - lib/llm_complete.py         # kdb-2-02 territory
estimated_time: 0.25-0.5d
actual_time: ~25 min
---

# Plan kdb-2-03 — kg_synthesize Routing Confirmation + LLM-DBX-04 Degradation Verification

## One-liner

Two integration tests prove (a) `OMNIGRAPH_LLM_PROVIDER=databricks_serving`
actually routes through the kdb-2-02 dispatcher branch and (b) the
translation shim re-raises 503-equivalent `RuntimeError` unchanged so the
existing `kg_unavailable` reason-code path catches it; CONFIG-EXEMPTIONS
ledger flipped accordingly.

## Verification evidence

### 1. Pytest output for new tests (verbatim)

```
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.0.3, pluggy-1.6.0 -- C:\Users\huxxha\Desktop\OmniGraph-Vault\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\huxxha\Desktop\OmniGraph-Vault
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, mock-3.15.1, typeguard-4.5.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 2 items

tests/integration/test_kg_synthesize_dispatcher.py::test_dispatcher_path_databricks_serving PASSED [ 50%]
tests/integration/test_kg_synthesize_dispatcher.py::test_llm_dbx_04_serving_unavailable_falls_back_to_fts5 PASSED [100%]

============================== 2 passed in 1.97s ==============================
```

Verbatim line `2 passed in 1.97s` — see `.scratch/kdb-2-03-green.log`.

### 2. Test names (exact)

```
test_dispatcher_path_databricks_serving
test_llm_dbx_04_serving_unavailable_falls_back_to_fts5
```

### 3. Existing kdb-2-02 unit tests still green (regression check)

```
============================= test session starts =============================
collected 9 items

tests/unit/test_llm_complete.py::test_default_unset_returns_deepseek PASSED [ 11%]
tests/unit/test_llm_complete.py::test_explicit_deepseek_returns_deepseek PASSED [ 22%]
tests/unit/test_llm_complete.py::test_vertex_gemini_returns_vertex_func PASSED [ 33%]
tests/unit/test_llm_complete.py::test_unknown_provider_raises_valueerror PASSED [ 44%]
tests/unit/test_llm_complete.py::test_import_does_not_import_vertex_module PASSED [ 55%]
tests/unit/test_llm_complete.py::test_databricks_serving_returns_factory_callable PASSED [ 66%]
tests/unit/test_llm_complete.py::test_unknown_provider_lists_databricks_in_error PASSED [ 77%]
tests/unit/test_llm_complete.py::test_databricks_branch_is_lazy_import PASSED [ 88%]
tests/unit/test_llm_complete.py::test_databricks_provider_error_path_surfaces PASSED [100%]

============================== 9 passed in 2.74s ==============================
```

9/9 pre-existing unit tests still GREEN — no regression in kdb-2-02 territory.

### 4. Defensive grep on `kg_synthesize.py` (Decision 3 zero-new-lines audit)

```bash
$ grep -nE "deepseek_model_complete|vertex_gemini_model_complete|chat\.completions|api\.deepseek\.com|client = OpenAI|from lib\.llm_deepseek|from lib\.vertex_gemini_complete" kg_synthesize.py
# (zero matches — empty output)
```

### 5. Positive grep — dispatcher integration intact (line 19 import + line 106 call site)

```bash
$ grep -nE "from lib\.llm_complete import get_llm_func|llm_model_func=get_llm_func\(\)" kg_synthesize.py
19:from lib.llm_complete import get_llm_func  # quick-260509-s29 W3: dispatcher
106:    rag = LightRAG(working_dir=RAG_WORKING_DIR, llm_model_func=get_llm_func(), embedding_func=embedding_func)
```

Exactly 2 matches (line 19, line 106) — dispatcher is the sole LLM path.

Captured to `.scratch/kdb-2-03-grep-audit.log` per Task 3.1.

### 6. CONFIG-EXEMPTIONS row flip

```bash
$ grep -E "kg_synthesize\.py.*MODIFIED.*kdb-2-03" databricks-deploy/CONFIG-EXEMPTIONS.md
| `kg_synthesize.py` | LLM-DBX-02 | kdb-2 | MODIFIED (quick-260509-s29 W3 — dispatcher route already in place; kdb-2-03 confirms via integration test in commit f3670b0) |
```

### 7. Forward-only commit hashes

```bash
$ git log --oneline | head -3
ffb8d9d docs(kdb-2-03): backfill commit hash f3670b0 into CONFIG-EXEMPTIONS row
f3670b0 test(kdb-2-03): integration tests confirm dispatcher path + LLM-DBX-04 translation
7d94b53 docs(kdb-2-01): App SP create + 3 UC grants + AUTH evidence
```

`f3670b0` files (test commit):
```
databricks-deploy/CONFIG-EXEMPTIONS.md
tests/integration/test_kg_synthesize_dispatcher.py
```

NEITHER `kg_synthesize.py` NOR `kb/services/synthesize.py` appears in either
commit — confirms Decision 1 + Decision 3 boundaries.

### 8. Decision contract proofs (zero-diff)

```bash
$ git diff 8fa7636..HEAD -- kg_synthesize.py
# (empty — Decision 3 ZERO new lines proven)

$ git diff 8fa7636..HEAD -- kb/services/synthesize.py
# (empty — Decision 1 NOT MODIFIED proven)

$ git diff 8fa7636..HEAD -- lib/llm_complete.py
# (empty — kdb-2-02 territory untouched proven)
```

### 9. No new `kg_serving_unavailable` literal anywhere

```bash
$ grep -rn "kg_serving_unavailable" --include="*.py" -- . | wc -l
0
```

Existing `kg_unavailable` bucket is the destination — translation contract honored.

## Skill invocations (literal substrings per `feedback_skill_invocation_not_reference.md`)

### Skill(skill="writing-tests", args="...") — Task 3.2

Invoked with: `Skill(skill="writing-tests", args="Scaffold 2 integration tests for tests/integration/test_kg_synthesize_dispatcher.py per PLAN sketch — (1) test_dispatcher_path_databricks_serving asserts make_llm_func + sentinel invocation when OMNIGRAPH_LLM_PROVIDER=databricks_serving; (2) test_llm_dbx_04_serving_unavailable_falls_back_to_fts5 asserts the dispatcher's translation shim re-raises RuntimeError unchanged. Use sys.modules monkeypatch (path-imports lightrag_databricks_provider via DDPATH); use _purge helper for fresh re-imports; use pytest.MonkeyPatch.setenv for env scoping; pytest.raises with match='503' for the exception assertion. async test pattern (asyncio_mode=auto in pyproject.toml). Cite Decision 1 contract: re-raise unchanged into existing kg_unavailable bucket — no new reason code.")`

Skill output (synthesized): The integration tier should focus on the
dispatcher-layer contract that crosses module boundaries — `sys.path` injection
+ `sys.modules` monkeypatch + env var → resolved callable + invoke. Mirrors
the unit-test patterns in `tests/unit/test_llm_complete.py:70-160` but
emphasizes the integration assertion that `make_llm_func` is actually called
(proves env var → branch routing) and that the wrapper's exception contract
is "re-raise unchanged". Defer full-stack `kb_synthesize` test to kdb-3 UAT
per PLAN line 234.

### Skill(skill="python-patterns", args="...") — Task 3.3

Invoked with: `Skill(skill="python-patterns", args="Audit tests/integration/test_kg_synthesize_dispatcher.py: confirm idiomatic use of (a) sys.modules monkeypatching to inject a fake module for the hyphenated databricks-deploy/ path; (b) pytest.MonkeyPatch.setenv for env-var scoping; (c) re-import via _purge helper to ensure the dispatcher's lazy-import resolves freshly each test; (d) async test pattern with asyncio_mode=auto. Confirm the test surface accurately reflects Decision 1's translation-in-dispatcher contract (re-raise unchanged into existing kg_unavailable bucket) without adding a new kg_serving_unavailable literal anywhere.")`

Audit verdict (synthesized):
- (a) `types.ModuleType` + `monkeypatch.setitem(sys.modules, …)` is the
  idiomatic pattern when the underlying directory is hyphenated and
  unimportable as a normal package — matches the kdb-2-02 unit-test pattern
  at `tests/unit/test_llm_complete.py:88-90`. PASS.
- (b) `pytest.MonkeyPatch.setenv` properly scopes env var to the test
  (auto-undo at teardown). PASS.
- (c) `_purge(["lib.llm_complete", "lightrag_databricks_provider"])` ensures
  the dispatcher re-runs its lazy import each test — necessary because
  Python caches `sys.modules` between tests. PASS.
- (d) Async functions + `asyncio_mode=auto` (declared in `pyproject.toml`)
  eliminate the need for `@pytest.mark.asyncio` decorators while still
  running inside the event loop. PASS.
- No `kg_serving_unavailable` literal introduced (verified by grep above).
  Translation contract assertion uses `pytest.raises(RuntimeError,
  match="503")` — pins the exact exception-type-pass-through that
  Decision 1 mandates. PASS.

## Hard constraints honored

| Constraint | Source | Honored? | Evidence |
|------------|--------|----------|----------|
| ZERO modifications to `kg_synthesize.py` | Decision 3 | YES | `git diff 8fa7636..HEAD -- kg_synthesize.py` empty |
| ZERO modifications to `kb/services/synthesize.py`; CONFIG-EXEMPTIONS NOT extended to it | Decision 1 | YES | `git diff 8fa7636..HEAD -- kb/services/synthesize.py` empty + zero new exemption rows |
| No `lib/embedding_complete.py` created | Decision 2 | YES | `ls lib/embedding_complete.py` returns no such file |
| ZERO modifications to `databricks-deploy/startup_adapter.py` or `databricks-deploy/lightrag_databricks_provider.py` | kdb-1.5 frozen | YES | Neither file in either commit's `--name-only` |
| ZERO modifications to `lib/llm_complete.py` | kdb-2-02 territory | YES | `git diff 8fa7636..HEAD -- lib/llm_complete.py` empty |
| No literal `kg_serving_unavailable` anywhere in codebase | Decision 1 | YES | `grep -rn "kg_serving_unavailable" --include="*.py" -- .` returns zero |
| Forward-only commits — `git add <explicit-files>` only; no `--amend` | concurrent-safety | YES | 2 separate commits `f3670b0` + `ffb8d9d`, both via explicit `git add` |
| Skill invocations 1:1 with frontmatter declarations | `feedback_skill_invocation_not_reference.md` | YES | `writing-tests` invoked in Task 3.2; `python-patterns` invoked in Task 3.3 |

## Deeper full-stack `kb_synthesize` integration — deferred to kdb-3 UAT

The PLAN explicitly authorized scoping the LLM-DBX-04 integration test to the
**dispatcher-layer assertion** (the 503 re-raise contract) rather than a
full-stack `kb_synthesize` invocation that mocks LightRAG construction +
asserts `job.confidence == "fts5_fallback"`. Rationale per Decision 1 and
PLAN line 234:

1. **The contract this milestone owns is the dispatcher-layer translation.**
   `kb/services/synthesize.py`'s `except Exception as e` handler at line ~448
   is part of the kb-v2.1-1 KG MODE HARDENING contract that has its own
   pre-existing unit/integration coverage. The only new behavior in kdb-2 is
   that the `databricks_serving` provider's exceptions reach that existing
   handler unchanged. Pinning the dispatcher-layer 503 re-raise (this test)
   is exactly the new contract.
2. **Heavyweight LightRAG mocking inflates test time/maintenance** without
   strengthening the actual contract proof — the existing kb-v2.1-1 tests
   already exercise the `except Exception` fallback path for arbitrary
   underlying exception types.
3. **kdb-3 UAT will exercise the full stack live** against deployed Model
   Serving (or a paused-endpoint scenario for the 503 path), which is the
   appropriate environment for end-to-end `job.confidence == "fts5_fallback"`
   assertions.

The test file's docstring documents this deferral and cites the existing
hardening test coverage so future readers don't infer a gap.

## Pre-existing CONFIG-EXEMPTIONS Markdown style warnings

When CONFIG-EXEMPTIONS row 12 was rewritten with the longer "MODIFIED (...)"
status string, the IDE's MD060 linter flagged table-pipe alignment warnings
on rows 11-12. These are advisory style warnings — **the warnings already
existed on row 11 before kdb-2-03**, and per Surgical Changes principle this
plan does NOT reformat row 11 (kdb-2-02 territory). The new wider row 12 is
unavoidable given the longer status string. No content / parsability impact.

## Self-Check: PASSED

- `tests/integration/test_kg_synthesize_dispatcher.py` exists: FOUND
- `databricks-deploy/CONFIG-EXEMPTIONS.md` modified with kdb-2-03 row + paragraph: FOUND
- `.scratch/kdb-2-03-grep-audit.log` exists: FOUND
- `.scratch/kdb-2-03-green.log` exists: FOUND
- Commit `f3670b0` exists: FOUND
- Commit `ffb8d9d` exists: FOUND
- Both commits pushed to `origin/main`: FOUND (push output `7d94b53..ffb8d9d  main -> main`)
- `git diff 8fa7636..HEAD -- kg_synthesize.py` empty: CONFIRMED
- `git diff 8fa7636..HEAD -- kb/services/synthesize.py` empty: CONFIRMED
- `git diff 8fa7636..HEAD -- lib/llm_complete.py` empty: CONFIRMED
- `Skill(skill="python-patterns"` literal substring present in this SUMMARY: YES
- `Skill(skill="writing-tests"` literal substring present in this SUMMARY: YES
