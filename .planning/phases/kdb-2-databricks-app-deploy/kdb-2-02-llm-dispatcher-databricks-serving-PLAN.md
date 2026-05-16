---
phase: kdb-2
plan_id: kdb-2-02
slug: llm-dispatcher-databricks-serving
wave: 1
depends_on: []
estimated_time: 0.5d
requirements:
  - LLM-DBX-01
  - LLM-DBX-04
skills:
  - python-patterns
  - writing-tests
---

# Plan kdb-2-02 — `lib/llm_complete.py` `databricks_serving` Branch + Decision-1 Exception Translation + 4 Unit Tests

## Objective

Add the `databricks_serving` provider branch to `lib/llm_complete.py` so callers setting `OMNIGRAPH_LLM_PROVIDER=databricks_serving` route LLM calls through the kdb-1.5 factory `databricks-deploy/lightrag_databricks_provider.make_llm_func()` against MosaicAI Model Serving (`databricks-claude-sonnet-4-6`).

**Decision-1 implementation lives here:** the new branch wraps `make_llm_func()`'s returned callable in an exception-translation layer that re-raises Databricks SDK 503/429/timeout/connection failures as generic exception types matching the existing `kg_unavailable` reason-code path in `kb/services/synthesize.py`. This means LLM-DBX-04 (Model Serving error → graceful degrade) is satisfied entirely inside `lib/llm_complete.py` without modifying `kb/services/synthesize.py` and without extending CONFIG-EXEMPTIONS.

Maps to: LLM-DBX-01 (full); LLM-DBX-04 (implementation — verification in kdb-2-03).

CONFIG-EXEMPTIONS row flip for `lib/llm_complete.py` happens in this plan (status `NOT YET MODIFIED` → `MODIFIED — see commit <hash>`).

## Read-first

- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-RESEARCH.md` Q2 (lines 188-282) — full file shape + add-branch sketch + 4 unit-test patterns
- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-RESEARCH.md` Q4 (lines 405-548) — error classifier shape; **Decision 1 OVERRIDES Q4 default-recommendation** — translation lives in `lib/llm_complete.py` not `kb/services/synthesize.py`
- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-CONTEXT.md` § "Decision 1" — explicit override
- `lib/llm_complete.py` (full file, 48 lines) — current 2-branch shape
- `databricks-deploy/lightrag_databricks_provider.py` (full file, 148 lines) — `make_llm_func()` factory, **read-only**
- `tests/unit/test_llm_complete.py` (full file, 60 lines, 5 tests) — pattern to extend
- `databricks-deploy/CONFIG-EXEMPTIONS.md` (29 lines) — current ledger (`lib/llm_complete.py` row at line 11 is `NOT YET MODIFIED`)
- `.planning/REQUIREMENTS-kb-databricks-v1.md` line 38 — LLM-DBX-01 full text
- `.planning/REQUIREMENTS-kb-databricks-v1.md` line 45 — LLM-DBX-04 full text (Decision 1 satisfies via translation, not new reason code)

## Scope

### In scope

- Add `"databricks_serving"` to `_VALID` tuple at `lib/llm_complete.py:27`
- Insert new `databricks_serving` branch in `get_llm_func()` between the `vertex_gemini` branch and the `raise ValueError(...)` (RESEARCH.md Q2 lines 217-253)
- Branch lazy-imports the kdb-1.5 factory + wraps the returned async callable in an exception-translation shim that maps Databricks SDK error patterns (RuntimeError with HTTP 503/429/504/timeout text, `socket.timeout`, `ConnectionError`, etc.) — preserves the kg_unavailable bucket per Decision 1
- The branch ALSO `sys.path.insert(0, "<repo>/databricks-deploy")` if needed so `from lightrag_databricks_provider import make_llm_func` works (because `databricks-deploy/` has a hyphen and isn't a legal package name) — RESEARCH.md Q2 lines 237-253
- Extend `tests/unit/test_llm_complete.py` with **4 new unit tests** per RESEARCH.md Q2 lines 256-281:
  1. `test_databricks_serving_returns_factory_callable` — happy path with mocked factory
  2. `test_unknown_provider_lists_databricks_in_error` — `_VALID` extension surfaced in error message
  3. `test_databricks_branch_is_lazy_import` — `import lib.llm_complete` does NOT pull `databricks_sdk` or `lightrag_databricks_provider` into `sys.modules`
  4. `test_databricks_provider_error_path_surfaces` — mocked factory raises 503 → translation shim re-raises with the same exception type so `kb/services/synthesize.py` `except Exception` path catches it and routes to existing `kg_unavailable` fallback (Decision 1 contract)
- Flip `databricks-deploy/CONFIG-EXEMPTIONS.md` row for `lib/llm_complete.py` from `NOT YET MODIFIED` → `MODIFIED (kdb-2-02 — commit <hash>; databricks_serving provider branch + LLM-DBX-04 translation)`

### Out of scope

- `kg_synthesize.py` modifications — Decision 3: ZERO new lines; CONFIG-EXEMPTIONS row flip + integration test for that file are kdb-2-03 territory
- `kb/services/synthesize.py` modifications — Decision 1: NOT extended; CONFIG-EXEMPTIONS NOT extended
- New `lib/embedding_complete.py` file — Decision 2: embedding work DEFERRED
- `app.yaml`, `Makefile`, deploy work — kdb-2-04 territory
- AUTH grants — kdb-2-01 territory
- `databricks-deploy/lightrag_databricks_provider.py` modifications — kdb-1.5 territory; READ-ONLY here

### CONFIG-EXEMPTIONS impact

This plan flips ONE row in `databricks-deploy/CONFIG-EXEMPTIONS.md`:

| Before | After |
|--------|-------|
| `\| `lib/llm_complete.py` \| LLM-DBX-01 \| kdb-2 \| NOT YET MODIFIED \|` | `\| `lib/llm_complete.py` \| LLM-DBX-01 + LLM-DBX-04 (translation) \| kdb-2 \| MODIFIED (kdb-2-02 — see commit <hash>) \|` |

**No new exemption rows added.** The row flip records the historical exemption already approved in CONFIG-EXEMPTIONS rev-1.

## Tasks

### Task 2.1 — Write 4 RED unit tests for `databricks_serving` branch

**Read-first:**
- `tests/unit/test_llm_complete.py` (full 60 lines) — pattern: monkeypatch env, lazy-import contract, ValueError match
- `kdb-2-RESEARCH.md` Q2 lines 256-281 — concrete test sketches for all 4
- `databricks-deploy/lightrag_databricks_provider.py:48-98` — `make_llm_func()` shape (so the test mock returns a compatible async callable)
- `~/.claude/skills/writing-tests/SKILL.md` — Testing Trophy: these are unit tests (mocked, no I/O); pattern for monkeypatch + sys.modules

**Action:**

1. Invoke `Skill(skill="writing-tests")` with args `"Scaffold 4 new unit tests for tests/unit/test_llm_complete.py covering OMNIGRAPH_LLM_PROVIDER=databricks_serving: (1) happy path with mocked make_llm_func returning a sentinel async callable; (2) unknown provider error message lists 'databricks_serving'; (3) lazy-import contract — importing lib.llm_complete does NOT pull databricks-sdk or lightrag_databricks_provider into sys.modules; (4) error-path translation — when factory's returned callable raises RuntimeError('HTTP 503'), the dispatcher branch re-raises so kb/services/synthesize.py's existing 'except Exception' handler catches it and routes to kg_unavailable bucket. Pattern: monkeypatch.setenv, sys.modules manipulation for lazy-import test, _purge_modules helper at top of file."` — record output substring in SUMMARY.md
2. Write the 4 tests as new functions appended to `tests/unit/test_llm_complete.py` (do NOT modify the existing 5 tests — surgical addition only). Add `import asyncio` at the top if not already present (existing file uses `import sys`, `import pytest`).
3. The 4 test bodies (concrete shape from RESEARCH.md Q2):

   ```python
   def test_databricks_serving_returns_factory_callable(monkeypatch: pytest.MonkeyPatch) -> None:
       """OMNIGRAPH_LLM_PROVIDER=databricks_serving routes to the kdb-1.5 factory.

       Mocks lightrag_databricks_provider.make_llm_func to return a sentinel async
       callable; asserts get_llm_func() returns that sentinel (post-translation-wrap).
       """
       import os
       repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
       sys.path.insert(0, os.path.join(repo_root, "databricks-deploy"))
       _purge_modules(["lib.llm_complete", "lightrag_databricks_provider"])
       monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "databricks_serving")

       async def sentinel_llm(prompt, **kwargs):
           return f"sentinel:{prompt}"

       # Inject a fake module that exposes make_llm_func returning sentinel
       import types
       fake_mod = types.ModuleType("lightrag_databricks_provider")
       fake_mod.make_llm_func = lambda: sentinel_llm  # type: ignore[attr-defined]
       monkeypatch.setitem(sys.modules, "lightrag_databricks_provider", fake_mod)

       from lib.llm_complete import get_llm_func
       fn = get_llm_func()
       # The translation wrapper preserves the underlying callable's invocation
       # contract; calling it should return the sentinel result OR (if wrapped)
       # be invokable via asyncio.run.
       result = asyncio.run(fn("hi"))
       assert result == "sentinel:hi"


   def test_unknown_provider_lists_databricks_in_error(monkeypatch: pytest.MonkeyPatch) -> None:
       """ValueError message lists 'databricks_serving' as a valid choice.

       Pins the _VALID extension; defends against accidental tuple revert.
       """
       monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "nope-not-real")
       _purge_modules(["lib.llm_complete"])
       from lib.llm_complete import get_llm_func
       with pytest.raises(ValueError, match="databricks_serving"):
           get_llm_func()


   def test_databricks_branch_is_lazy_import(monkeypatch: pytest.MonkeyPatch) -> None:
       """Importing lib.llm_complete must NOT pull lightrag_databricks_provider or databricks-sdk.

       Pins the lazy-import contract — DeepSeek-only callers should not pay
       databricks-sdk or kdb-1.5 factory import cost.
       """
       _purge_modules([
           "lib.llm_complete",
           "lightrag_databricks_provider",
           "databricks.sdk",
       ])
       import lib.llm_complete  # noqa: F401
       assert "lightrag_databricks_provider" not in sys.modules
       assert "databricks.sdk" not in sys.modules


   def test_databricks_provider_error_path_surfaces(monkeypatch: pytest.MonkeyPatch) -> None:
       """When factory's callable raises 503/429/timeout, dispatcher branch re-raises.

       LLM-DBX-04 contract via Decision 1 (translation in dispatcher): the wrapped
       callable surfaces an exception that kb/services/synthesize.py's existing
       'except Exception as e' handler catches and routes to kg_unavailable
       fallback. Test asserts the exception bubbles up; downstream-classification
       behavior is verified in kdb-2-03 integration test.
       """
       import os, types
       repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
       sys.path.insert(0, os.path.join(repo_root, "databricks-deploy"))
       _purge_modules(["lib.llm_complete", "lightrag_databricks_provider"])
       monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "databricks_serving")

       async def boom(prompt, **kwargs):
           raise RuntimeError("HTTP 503 Service Unavailable: model_overloaded")

       fake_mod = types.ModuleType("lightrag_databricks_provider")
       fake_mod.make_llm_func = lambda: boom  # type: ignore[attr-defined]
       monkeypatch.setitem(sys.modules, "lightrag_databricks_provider", fake_mod)

       from lib.llm_complete import get_llm_func
       fn = get_llm_func()
       with pytest.raises(RuntimeError, match="503"):
           asyncio.run(fn("trigger 503"))
   ```

4. Run `pytest tests/unit/test_llm_complete.py -v` and confirm: 5 existing tests PASS, 4 new tests FAIL with import or logic errors (RED phase). Capture stderr/stdout to `.scratch/kdb-2-02-red.log`.

**Acceptance** (grep-verifiable):
- `grep -c "^def test_" tests/unit/test_llm_complete.py` returns `9` (5 existing + 4 new)
- `grep -c "test_databricks_serving_returns_factory_callable\|test_unknown_provider_lists_databricks_in_error\|test_databricks_branch_is_lazy_import\|test_databricks_provider_error_path_surfaces" tests/unit/test_llm_complete.py` returns `4`
- `pytest tests/unit/test_llm_complete.py -v` exit code is non-zero (RED — 4 failures expected); 5 existing tests still PASS
- Test file imports `asyncio` (`grep -c "^import asyncio" tests/unit/test_llm_complete.py` ≥ 1)
- SUMMARY.md will contain literal `Skill(skill="writing-tests"` (≥1 occurrence)

**Done:** 4 RED tests committed; existing 5 still green; LLM-DBX-01 acceptance test scaffolding ready for GREEN.

**Time estimate:** 1.0h (most of which is concrete test body authorship + RED verification).

### Task 2.2 — GREEN: implement `databricks_serving` branch + Decision-1 translation

**Read-first:**
- `lib/llm_complete.py` (full 48 lines) — exact insertion point
- `kdb-2-RESEARCH.md` Q2 lines 217-253 — concrete branch sketch
- `kdb-2-RESEARCH.md` Q4 lines 476-503 — error-classifier patterns (used here as the translation reference, not as a new helper in `kb/services/synthesize.py`)
- `databricks-deploy/lightrag_databricks_provider.py:48-98` — `make_llm_func()` returns an async callable matching LightRAG `llm_model_func` signature
- `~/.claude/skills/python-patterns/SKILL.md` — Callable type hints, lazy imports, sys.path manipulation idioms

**Action:**

1. Invoke `Skill(skill="python-patterns")` with args `"Confirm idiomatic Python pattern for: (a) lazy module import inside a function body to avoid module-import-time cost; (b) sys.path.insert(0, ...) used to resolve a hyphenated directory name (databricks-deploy) since hyphens aren't legal Python package identifiers; (c) Callable[..., Coroutine] type hint for an async wrapper that re-raises specific exception types unchanged; (d) keeping _VALID tuple ordering stable when extending."` — record output in SUMMARY.md
2. Edit `lib/llm_complete.py`:
   - **Line 27** — change `_VALID = ("deepseek", "vertex_gemini")` to `_VALID = ("deepseek", "vertex_gemini", "databricks_serving")`
   - **Insert new branch** between line 41 (end of vertex_gemini branch) and line 42 (start of `raise ValueError(...)`):
     ```python
         if provider == "databricks_serving":
             # kdb-2 LLM-DBX-01 + LLM-DBX-04 (Decision 1 — translation in dispatcher).
             # Wraps the kdb-1.5 factory at databricks-deploy/lightrag_databricks_provider.py.
             # The factory returns an async callable matching LightRAG's llm_model_func
             # contract. We add a thin exception-translation wrapper so Databricks SDK
             # 503/429/timeout/connection errors surface as standard exceptions that
             # kb/services/synthesize.py's existing 'except Exception as e' branch
             # catches and routes to its kg_unavailable fallback (kb-v2.1-1 KG MODE
             # HARDENING contract preserved — no new reason code, no kb/services
             # modification, no CONFIG-EXEMPTIONS extension).
             #
             # databricks-deploy/ has a hyphen and isn't a legal Python package name —
             # we add it to sys.path so the bare-module import works. Apps runtime
             # adds the directory to PYTHONPATH via app.yaml command: (kdb-2-04);
             # locally and in tests, callers prepend it explicitly.
             import os as _os
             import sys as _sys
             _here = _os.path.dirname(_os.path.abspath(__file__))
             _repo_root = _os.path.abspath(_os.path.join(_here, _os.pardir))
             _ddpath = _os.path.join(_repo_root, "databricks-deploy")
             if _ddpath not in _sys.path:
                 _sys.path.insert(0, _ddpath)
             from lightrag_databricks_provider import make_llm_func  # type: ignore[import-not-found]
             _underlying = make_llm_func()
             async def _databricks_serving_llm(
                 prompt,
                 system_prompt=None,
                 history_messages=None,
                 **kwargs,
             ):
                 # Translation shim: pass-through happy path; on Databricks SDK
                 # exception or 503/429/timeout/connection-error pattern, re-raise
                 # unchanged so the existing 'except Exception' bucket in
                 # kb/services/synthesize.py routes to kg_unavailable. We do NOT
                 # swallow exceptions or remap to a new reason code (Decision 1).
                 return await _underlying(
                     prompt,
                     system_prompt=system_prompt,
                     history_messages=history_messages,
                     **kwargs,
                 )
             return _databricks_serving_llm
     ```
   - **Update module docstring** lines 1-19 — extend the provider list to mention `databricks_serving` and reference kdb-2 LLM-DBX-01 + LLM-DBX-04 with one sentence each. Surgical addition only — no rewrite of unrelated content.
3. Run `pytest tests/unit/test_llm_complete.py -v` — expect ALL 9 tests to PASS (GREEN). Capture stdout to `.scratch/kdb-2-02-green.log`.
4. Spot-check the lazy-import contract via `python -c "import lib.llm_complete; import sys; assert 'lightrag_databricks_provider' not in sys.modules; assert 'databricks.sdk' not in sys.modules; print('OK')"` → expect `OK`.

**Acceptance** (grep-verifiable):
- `grep -c '"databricks_serving"' lib/llm_complete.py` returns ≥3 (in `_VALID`, in the branch `if provider ==`, and in docstring)
- `grep -c "from lightrag_databricks_provider import make_llm_func" lib/llm_complete.py` returns 1
- `pytest tests/unit/test_llm_complete.py -v` exit code 0; output contains `9 passed`
- `python -c "import lib.llm_complete; import sys; assert 'lightrag_databricks_provider' not in sys.modules; assert 'databricks.sdk' not in sys.modules; print('OK')"` returns `OK`
- SUMMARY.md will contain literal `Skill(skill="python-patterns"` (≥1 occurrence)
- File length: `wc -l lib/llm_complete.py` returns approximately 75-95 (was 48; added ~30-40 lines for branch + docstring update + comments)

**Done:** 9/9 unit tests PASS. `databricks_serving` provider branch live. LLM-DBX-01 implementation complete. LLM-DBX-04 translation in place (verification in kdb-2-03 integration test).

**Time estimate:** 1.5h (Edit + verify + skill invoke + spot-checks).

### Task 2.3 — Flip CONFIG-EXEMPTIONS row + commit forward-only

**Read-first:**
- `databricks-deploy/CONFIG-EXEMPTIONS.md` (full 29 lines) — current ledger
- `feedback_no_amend_in_concurrent_quicks.md` — forward-only commit rule
- `feedback_git_add_explicit_in_parallel_quicks.md` — explicit file paths in `git add`

**Action:**

1. Edit `databricks-deploy/CONFIG-EXEMPTIONS.md`:
   - Change line 11 row from:
     ```
     | `lib/llm_complete.py` | LLM-DBX-01 | kdb-2 | NOT YET MODIFIED |
     ```
     to (placeholder commit hash filled in step 4):
     ```
     | `lib/llm_complete.py` | LLM-DBX-01 + LLM-DBX-04 (translation per Decision 1) | kdb-2 | MODIFIED (kdb-2-02 — see commit <FILL_AT_COMMIT>) |
     ```
   - Add a paragraph under "Phase kdb-1.5 contribution" titled "Phase kdb-2-02 contribution":
     ```
     ## Phase kdb-2-02 contribution

     Plan kdb-2-02 modifies `lib/llm_complete.py` (allowed per CONFIG-EXEMPTIONS rev 1)
     to add the `databricks_serving` provider branch (LLM-DBX-01) plus an exception-
     translation shim that satisfies LLM-DBX-04 entirely inside the dispatcher per
     phase Decision 1 — `kb/services/synthesize.py` is NOT modified, CONFIG-EXEMPTIONS
     is NOT extended. Translation re-raises Databricks SDK 503/429/timeout/connection
     errors unchanged so the existing `except Exception as e` handler in
     `kb/services/synthesize.py:448` routes to the `kg_unavailable` reason-code
     bucket (kb-v2.1-1 KG MODE HARDENING contract).
     ```
2. Stage explicitly: `git add lib/llm_complete.py tests/unit/test_llm_complete.py databricks-deploy/CONFIG-EXEMPTIONS.md`
3. Commit forward-only with message:
   ```
   feat(kdb-2-02): add databricks_serving provider branch + LLM-DBX-04 translation

   - lib/llm_complete.py: extend _VALID to include "databricks_serving";
     new branch lazy-imports make_llm_func from databricks-deploy/ and wraps
     the returned async callable in an exception-translation shim that
     re-raises Databricks SDK errors unchanged so kb/services/synthesize.py's
     existing kg_unavailable bucket handles them (Decision 1 — no kb/ edit,
     no CONFIG-EXEMPTIONS extension).
   - tests/unit/test_llm_complete.py: add 4 new tests covering happy path,
     _VALID error message, lazy-import contract, and 503-translation surface.
   - databricks-deploy/CONFIG-EXEMPTIONS.md: flip lib/llm_complete.py row
     from NOT YET MODIFIED to MODIFIED + add kdb-2-02 contribution paragraph.

   REQs: LLM-DBX-01 (full); LLM-DBX-04 (implementation; verification in kdb-2-03)
   ```
4. After commit, capture commit hash via `git log -1 --format=%H`. Edit `databricks-deploy/CONFIG-EXEMPTIONS.md` to replace `<FILL_AT_COMMIT>` with the actual hash. Stage + commit forward-only as a second commit:
   ```
   docs(kdb-2-02): backfill commit hash into CONFIG-EXEMPTIONS row
   ```
   (This is the 2-forward-commit pattern from STATE-kb-databricks-v1.md — never `git commit --amend`, ever, on shared main checkout.)

**Acceptance** (grep-verifiable):
- `grep -E "lib/llm_complete\.py.*MODIFIED \(kdb-2-02" databricks-deploy/CONFIG-EXEMPTIONS.md` returns ≥1 row
- `grep -c "Phase kdb-2-02 contribution" databricks-deploy/CONFIG-EXEMPTIONS.md` returns 1
- `git log --oneline | head -3` shows BOTH the feat commit AND the docs backfill commit (forward-only — no `--amend`)
- `git log -1 --name-only` for the feat commit shows exactly: `lib/llm_complete.py`, `tests/unit/test_llm_complete.py`, `databricks-deploy/CONFIG-EXEMPTIONS.md`
- No `--amend`, no `git reset`, no `git add -A` in the working session (audit via `history | grep -E "amend|reset|add -A"` empty for this plan window)

**Done:** Two clean forward-only commits land plan kdb-2-02 deliverables; CONFIG-EXEMPTIONS row carries the actual commit hash for audit.

**Time estimate:** 30 min (edit + 2 commits + grep verification).

## Verification (what `kdb-2-02-SUMMARY.md` MUST cite)

1. `pytest tests/unit/test_llm_complete.py -v` output verbatim showing `9 passed`
2. The 4 new test names exactly: `test_databricks_serving_returns_factory_callable`, `test_unknown_provider_lists_databricks_in_error`, `test_databricks_branch_is_lazy_import`, `test_databricks_provider_error_path_surfaces`
3. Lazy-import spot-check: `python -c "import lib.llm_complete; import sys; assert 'lightrag_databricks_provider' not in sys.modules; assert 'databricks.sdk' not in sys.modules; print('OK')"` → `OK`
4. `grep -c '"databricks_serving"' lib/llm_complete.py` ≥ 3
5. `grep -E "lib/llm_complete\.py.*MODIFIED \(kdb-2-02" databricks-deploy/CONFIG-EXEMPTIONS.md` returns ≥1 row with actual commit hash
6. The 2 commit hashes (feat + docs backfill) for forward-only audit
7. Verbatim insertion-point line numbers in `lib/llm_complete.py` (where the new branch was added)
8. Skill invocation evidence — literal `Skill(skill="python-patterns"` AND `Skill(skill="writing-tests"` substrings (each ≥1 in SUMMARY.md per `feedback_skill_invocation_not_reference.md`)

## Hard constraints honored

- **(scope — Decision 3)** ZERO modifications to `kg_synthesize.py` (verified by `git diff <commit-feat> -- kg_synthesize.py` returning empty)
- **(scope — Decision 1)** ZERO modifications to `kb/services/synthesize.py`; CONFIG-EXEMPTIONS NOT extended (verified by `git diff <commit-feat> -- kb/services/synthesize.py` returning empty AND CONFIG-EXEMPTIONS still has only the original 2 rows)
- **(scope — Decision 2)** No `lib/embedding_complete.py` file created (verified by `ls lib/embedding_complete.py` returning "No such file")
- **(scope — kdb-1.5 territory)** ZERO modifications to `databricks-deploy/startup_adapter.py` or `databricks-deploy/lightrag_databricks_provider.py` (verified by `git diff <commit-feat> -- databricks-deploy/startup_adapter.py databricks-deploy/lightrag_databricks_provider.py` returning empty)
- **(safety)** Forward-only commits — `git add <explicit-files>` only; no `git add -A`; no `git commit --amend` (audited per Task 2.3 acceptance)
- **(LLM-DBX-01 contract)** Lazy-import contract preserved — `import lib.llm_complete` does NOT pull `lightrag_databricks_provider` or `databricks.sdk` into `sys.modules`
- **(skills)** `Skill(skill="writing-tests")` invoked in Task 2.1; `Skill(skill="python-patterns")` invoked in Task 2.2 — frontmatter ↔ task invocation 1:1

## Anti-patterns (block list)

This plan MUST NOT:
- Modify `kg_synthesize.py` (Decision 3 — kdb-2-03 territory + zero net change anyway)
- Modify `kb/services/synthesize.py` (Decision 1 — translation lives in dispatcher)
- Add `kb/services/synthesize.py` to CONFIG-EXEMPTIONS (Decision 1)
- Create `lib/embedding_complete.py` (Decision 2 — embedding work deferred)
- Modify `databricks-deploy/startup_adapter.py` or `databricks-deploy/lightrag_databricks_provider.py` (kdb-1.5 frozen)
- Hardcode any literal Foundation Model API token / secret in `lib/llm_complete.py` (Apps SP injection covers auth)
- Use `git commit --amend` to backfill the commit hash (Task 2.3 step 4 uses a separate forward commit)
- Use `git add -A` or `git add .`
- Add a `kg_serving_unavailable` literal anywhere in the codebase (Decision 1 — no new reason code; existing `kg_unavailable` is reused via translation)
- Modify the existing 5 unit tests in `tests/unit/test_llm_complete.py` (surgical addition only)

## Estimated time total

0.5d (Task 2.1: 1.0h + Task 2.2: 1.5h + Task 2.3: 0.5h + buffer ≈ 3.0-4.0h ≈ 0.4-0.5d)
