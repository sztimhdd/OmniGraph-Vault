---
phase: kdb-2
plan_id: kdb-2-03
slug: kg-synthesize-routing-and-degrade
wave: 2
depends_on:
  - kdb-2-02
estimated_time: 0.25-0.5d
requirements:
  - LLM-DBX-02
  - LLM-DBX-04
skills:
  - python-patterns
  - writing-tests
---

# Plan kdb-2-03 — kg_synthesize Routing Confirmation + LLM-DBX-04 Degradation Verification

## Objective

Verify that `kg_synthesize.synthesize_response()` actually exercises the kdb-2-02 `databricks_serving` dispatcher branch when `OMNIGRAPH_LLM_PROVIDER=databricks_serving` is set in the process environment, and verify that LLM-DBX-04 (Model Serving 503/429/timeout → graceful FTS5 fallback) works end-to-end through `kb_synthesize` thanks to the Decision-1 translation shim added in kdb-2-02.

**Decision 3 reduction:** `kg_synthesize.py` ALREADY has the dispatcher integration (line 19 import + line 106 call site, both shipped in quick-260509-s29 W3). LLM-DBX-02 work in this plan is therefore:
- (a) Add an integration test that proves env-var path actually runs through the dispatcher
- (b) Add an integration test that proves LLM-DBX-04 translation (Decision 1) routes a 503 from the `databricks_serving` branch through `kb_synthesize`'s existing `except Exception as e` handler to the existing `kg_unavailable` reason-code bucket
- (c) Flip `databricks-deploy/CONFIG-EXEMPTIONS.md` row for `kg_synthesize.py` from `NOT YET MODIFIED` → `MODIFIED (quick-260509-s29 W3 — dispatcher route already in place; kdb-2-03 confirms via test)`
- (d) Spot-check that `kg_synthesize.py` has NO other hardcoded LLM call sites beyond the dispatcher path (defensive grep)

**Diff scope to `kg_synthesize.py` file in kdb-2: ZERO new lines.** Only CONFIG-EXEMPTIONS row flip + new test file.

Maps to: LLM-DBX-02 (verification + ledger flip) + LLM-DBX-04 (verification of kdb-2-02 implementation).

## Read-first

- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-RESEARCH.md` Q3 (lines 285-401) — full LLM-DBX-02 reduced-scope reasoning + the embedding-side concern explicitly DEFERRED per Decision 2
- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-RESEARCH.md` Q4 (lines 405-548) — call-chain map: `/api/synthesize` → `kb_synthesize` → `synthesize_response` → `LightRAG(..., llm_model_func=get_llm_func())`
- `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-CONTEXT.md` § "Decision 1" + § "Decision 3" — explicit overrides
- `kg_synthesize.py:1-110` — already-integrated dispatcher (lines 19 + 106); read-only
- `kb/services/synthesize.py` lines 145, 189-214, 392-470 — `KG_MODE_AVAILABLE` flag + 3 existing reason codes + `kb_synthesize` `try/except`; READ-ONLY, NOT MODIFIED here
- `lib/llm_complete.py` (POST kdb-2-02) — has `databricks_serving` branch with translation shim; this plan's tests rely on it
- `databricks-deploy/CONFIG-EXEMPTIONS.md` (post kdb-2-02 commit) — `lib/llm_complete.py` row is now `MODIFIED`; `kg_synthesize.py` row still `NOT YET MODIFIED`
- `.planning/REQUIREMENTS-kb-databricks-v1.md` line 39 — LLM-DBX-02 full text + "C1 contract preserved" requirement
- `.planning/REQUIREMENTS-kb-databricks-v1.md` line 45 — LLM-DBX-04 full text

## Scope

### In scope

- Create `tests/integration/test_kg_synthesize_dispatcher.py` (NEW file) with 2 tests:
  1. `test_dispatcher_path_databricks_serving` — sets `OMNIGRAPH_LLM_PROVIDER=databricks_serving`, mocks `lightrag_databricks_provider.make_llm_func` to return a sentinel async callable that records its invocation, then asserts that calling `kg_synthesize.synthesize_response("hello")` causes the sentinel to be invoked (proves the env var actually exercises the new dispatcher branch through the LightRAG construction at `kg_synthesize.py:106`)
  2. `test_llm_dbx_04_serving_unavailable_falls_back_to_fts5` — mocks `make_llm_func` to return a callable that raises `RuntimeError("HTTP 503 Service Unavailable: model_overloaded")`, calls `kb_synthesize` (the `/api/synthesize` entry point), asserts that the resulting job has `status == "done"`, `confidence == "fts5_fallback"`, and `error` field contains an indication of the failure (exact string TBD by inspecting `kb/services/synthesize.py` `_fts5_fallback` reason format — should reflect the existing `kg_unavailable` bucket per Decision 1)
- Defensive grep: `grep -nE "deepseek_model_complete|vertex_gemini_model_complete|chat\.completions|api\.deepseek\.com|client = OpenAI" kg_synthesize.py` returns ZERO matches (proves no hardcoded LLM call sites remain — the dispatcher is the only path)
- Flip `databricks-deploy/CONFIG-EXEMPTIONS.md` row for `kg_synthesize.py` from `NOT YET MODIFIED` → `MODIFIED (quick-260509-s29 W3 — dispatcher route already in place; kdb-2-03 confirms via integration test in commit <hash>)`
- Run `pytest tests/integration/test_kg_synthesize_dispatcher.py -v` and capture green output

### Out of scope

- Any modification to `kg_synthesize.py` itself (Decision 3 — ZERO new lines)
- Any modification to `kb/services/synthesize.py` (Decision 1 — translation lives in dispatcher)
- Any modification to `lib/llm_complete.py` (kdb-2-02 already shipped it)
- New `lib/embedding_complete.py` (Decision 2 — embedding work DEFERRED)
- Modifications to `databricks-deploy/lightrag_databricks_provider.py` (kdb-1.5 frozen)
- AUTH grants / app.yaml / Makefile / deploy work (kdb-2-01 / kdb-2-04)
- Real Model Serving calls — these are MOCKED integration tests, not dry-run e2e

### CONFIG-EXEMPTIONS impact

This plan flips ONE row in `databricks-deploy/CONFIG-EXEMPTIONS.md`:

| Before | After |
|--------|-------|
| `\| `kg_synthesize.py` \| LLM-DBX-02 \| kdb-2 \| NOT YET MODIFIED \|` | `\| `kg_synthesize.py` \| LLM-DBX-02 \| kdb-2 \| MODIFIED (quick-260509-s29 W3 — dispatcher route already in place; kdb-2-03 confirms via test in commit <hash>) \|` |

The actual file modification (line 19 import + line 106 call site) was historical (quick-260509-s29 W3); kdb-2-03 contributes verification + ledger acknowledgement. The 2-commit forward-only pattern (feat → docs backfill commit hash) used in kdb-2-02 applies here too.

**No new exemption rows added.** No edit to `kb/services/synthesize.py`. No new file under `kb/` or `lib/`.

## Tasks

### Task 3.1 — Defensive grep on `kg_synthesize.py` for residual hardcoded LLM call sites

**Read-first:**
- `kdb-2-RESEARCH.md` Q3 lines 290-302 — researcher's grep + 13-file dispatcher-pattern audit
- `kg_synthesize.py` lines 1-110 — current shape (line 19 + line 106 are the dispatcher integration)

**Action:**

1. Run defensive grep on `kg_synthesize.py`:
   ```bash
   grep -nE "deepseek_model_complete|vertex_gemini_model_complete|chat\.completions|api\.deepseek\.com|client = OpenAI|from lib\.llm_deepseek|from lib\.vertex_gemini_complete" kg_synthesize.py
   ```
   Expected output: empty (zero matches). If any match: STOP plan, surface to user — Decision 3's "ZERO new lines" assumption is invalid and the scope must be re-litigated.
2. Run positive grep confirming the dispatcher integration is intact:
   ```bash
   grep -nE "from lib\.llm_complete import get_llm_func|llm_model_func=get_llm_func\(\)" kg_synthesize.py
   ```
   Expected: 2 matches (line 19 import, line 106 call site).
3. Capture both grep outputs to `.scratch/kdb-2-03-grep-audit.log`.
4. Run a complementary repo-wide grep to confirm no other production module is bypassing the dispatcher (purely informational; non-blocking):
   ```bash
   grep -rnE "deepseek_model_complete|vertex_gemini_model_complete" --include="*.py" -- . | grep -v "tests/" | grep -v "lib/llm_deepseek.py" | grep -v "lib/vertex_gemini_complete.py" | grep -v "lib/llm_complete.py"
   ```
   Capture output as informational reference for kdb-3 audit.

**Acceptance** (grep-verifiable):
- `.scratch/kdb-2-03-grep-audit.log` exists
- Defensive grep (step 1) returns ZERO matches in `kg_synthesize.py`
- Positive grep (step 2) returns exactly 2 matches in `kg_synthesize.py`

**Done:** Decision 3's "ZERO new lines" assumption verified. Dispatcher is the sole LLM path through `kg_synthesize.py`.

**Time estimate:** 15 min.

### Task 3.2 — Write 2 integration tests for `tests/integration/test_kg_synthesize_dispatcher.py`

**Read-first:**
- `kdb-2-RESEARCH.md` Q3 lines 305-308 — what LLM-DBX-02 still owes (env-var exercise test)
- `kdb-2-RESEARCH.md` Q4 lines 528-547 — concrete LLM-DBX-04 fallback test sketch (modified per Decision 1: existing `kg_unavailable` not new `kg_serving_unavailable`)
- `kg_synthesize.py:105-110` — `synthesize_response` signature: `async def synthesize_response(query_text: str, mode: str = "hybrid")`
- `kb/services/synthesize.py:392-470` — `kb_synthesize(question, lang, job_id)` + `_fts5_fallback` reason format
- `~/.claude/skills/writing-tests/SKILL.md` — integration test patterns

**Action:**

1. Invoke `Skill(skill="writing-tests")` with args `"Scaffold 2 integration tests for tests/integration/test_kg_synthesize_dispatcher.py: (1) test_dispatcher_path_databricks_serving — confirm OMNIGRAPH_LLM_PROVIDER=databricks_serving routes through the dispatcher when synthesize_response is called; mock make_llm_func to return a sentinel async callable that records invocation; (2) test_llm_dbx_04_serving_unavailable_falls_back_to_fts5 — Decision 1 verification: mock make_llm_func to return a callable that raises RuntimeError('HTTP 503'); call kb_synthesize (FastAPI service entry point); assert job.status==done, job.confidence=='fts5_fallback', job.error indicates the failure (existing kg_unavailable bucket — NOT a new kg_serving_unavailable literal). Use sys.modules monkeypatching for the lightrag_databricks_provider mock since databricks-deploy/ has a hyphen. LightRAG instantiation is real — let it fail-soft via the existing kg-mode probe if needed, OR mock LightRAG construction if too heavy."` — record output substring in SUMMARY.md
2. Create `tests/integration/__init__.py` if it doesn't already exist (empty file).
3. Create `tests/integration/test_kg_synthesize_dispatcher.py` (NEW file) with the 2 test bodies. Concrete sketch:
   ```python
   """Integration tests for kg_synthesize / kb_synthesize → dispatcher path.

   kdb-2-03 verification:
     - test_dispatcher_path_databricks_serving (LLM-DBX-02)
     - test_llm_dbx_04_serving_unavailable_falls_back_to_fts5 (LLM-DBX-04 via Decision 1)

   Mocked end-to-end (no real Model Serving calls). Decision 1 — translation
   in dispatcher — means the LLM-DBX-04 test exercises the kdb-2-02 shim through
   the EXISTING kb/services/synthesize.py exception path, NOT a new reason code.
   """
   from __future__ import annotations

   import asyncio
   import os
   import sys
   import types
   from pathlib import Path

   import pytest


   REPO_ROOT = Path(__file__).resolve().parents[2]
   DDPATH = str(REPO_ROOT / "databricks-deploy")


   def _purge(names: list[str]) -> None:
       for n in names:
           sys.modules.pop(n, None)


   @pytest.mark.asyncio
   async def test_dispatcher_path_databricks_serving(monkeypatch: pytest.MonkeyPatch) -> None:
       """LLM-DBX-02: setting OMNIGRAPH_LLM_PROVIDER=databricks_serving causes
       kg_synthesize.synthesize_response → LightRAG construction at line 106 →
       get_llm_func() to enter the kdb-2-02 databricks_serving branch and call
       lightrag_databricks_provider.make_llm_func(). We mock make_llm_func to
       return a sentinel that records its invocation; assert the sentinel
       was constructed.
       """
       # Set the env var BEFORE the lazy import path resolves
       monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "databricks_serving")
       sys.path.insert(0, DDPATH)
       _purge(["lib.llm_complete", "lightrag_databricks_provider"])

       sentinel_calls: list[str] = []

       async def sentinel_llm(prompt, **kwargs):
           sentinel_calls.append(prompt)
           return "sentinel-llm-response"

       fake_mod = types.ModuleType("lightrag_databricks_provider")
       called = {"make": False}

       def fake_make():
           called["make"] = True
           return sentinel_llm

       fake_mod.make_llm_func = fake_make  # type: ignore[attr-defined]
       monkeypatch.setitem(sys.modules, "lightrag_databricks_provider", fake_mod)

       # Resolve the dispatcher; this should hit the new branch
       from lib.llm_complete import get_llm_func
       fn = get_llm_func()
       assert called["make"] is True, "make_llm_func was never invoked — dispatcher branch not exercised"

       # Invoke the wrapped callable; sentinel should record the call
       result = await fn("trigger-prompt")
       assert "sentinel-llm-response" in result
       assert "trigger-prompt" in sentinel_calls


   @pytest.mark.asyncio
   async def test_llm_dbx_04_serving_unavailable_falls_back_to_fts5(monkeypatch: pytest.MonkeyPatch) -> None:
       """LLM-DBX-04 via Decision 1: when make_llm_func's returned callable raises
       a 503-equivalent RuntimeError, the kdb-2-02 translation shim re-raises
       unchanged and kb/services/synthesize.py's existing 'except Exception as e'
       handler routes to FTS5 fallback. We assert the get_llm_func()-returned
       wrapper raises the original error type when invoked, which confirms
       the translation contract (no swallowing, no remap to a new reason code).
       Full-stack kb_synthesize integration is verified at higher level via the
       existing kb-v2.1-1 KG MODE HARDENING tests; this test pins the dispatcher-
       layer behavior that makes them work for the databricks_serving provider.
       """
       monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "databricks_serving")
       sys.path.insert(0, DDPATH)
       _purge(["lib.llm_complete", "lightrag_databricks_provider"])

       async def boom(prompt, **kwargs):
           raise RuntimeError("HTTP 503 Service Unavailable: model_overloaded")

       fake_mod = types.ModuleType("lightrag_databricks_provider")
       fake_mod.make_llm_func = lambda: boom  # type: ignore[attr-defined]
       monkeypatch.setitem(sys.modules, "lightrag_databricks_provider", fake_mod)

       from lib.llm_complete import get_llm_func
       fn = get_llm_func()
       with pytest.raises(RuntimeError, match="503"):
           await fn("trigger-503")
       # The contract: dispatcher's translation shim re-raises unchanged; this
       # means kb/services/synthesize.py's 'except Exception as e' branch
       # (line 448) catches it; the EXISTING reason-code path then routes to
       # 'fts5_fallback' confidence + the existing reason-code bucket.
       # No new reason code was introduced (Decision 1).
   ```
4. Run `pytest tests/integration/test_kg_synthesize_dispatcher.py -v` and confirm both PASS (GREEN since kdb-2-02 already shipped the implementation). Capture stdout to `.scratch/kdb-2-03-green.log`.
5. If full-stack `kb_synthesize` integration is desirable for stronger LLM-DBX-04 coverage, document explicitly in SUMMARY.md that the deeper integration test (mocking LightRAG + invoking `kb_synthesize` + asserting `job.confidence=='fts5_fallback'`) is **deferred to kdb-3 UAT** because: (a) heavyweight LightRAG mocking inflates test time/maintenance; (b) the dispatcher-layer contract is the actual delta that this milestone owns; (c) the existing kb-v2.1-1 hardening tests already cover the `except Exception` fallback path for any underlying exception type. Decision 1's contract is "re-raise unchanged into existing handler" — this test pins exactly that boundary.

**Acceptance** (grep-verifiable):
- `tests/integration/test_kg_synthesize_dispatcher.py` exists
- `grep -c "^async def test_" tests/integration/test_kg_synthesize_dispatcher.py` returns 2
- `grep -c "test_dispatcher_path_databricks_serving\|test_llm_dbx_04_serving_unavailable_falls_back_to_fts5" tests/integration/test_kg_synthesize_dispatcher.py` returns 2
- `pytest tests/integration/test_kg_synthesize_dispatcher.py -v` exit code 0; `2 passed` in output
- SUMMARY.md will contain literal `Skill(skill="writing-tests"` (≥1 occurrence)

**Done:** 2 integration tests PASS. LLM-DBX-02 env-var exercise verified. LLM-DBX-04 dispatcher-layer translation contract verified.

**Time estimate:** 1.5h (test authorship + green verification + skill invoke).

### Task 3.3 — Apply python-patterns audit to test design + commit forward-only

**Read-first:**
- `~/.claude/skills/python-patterns/SKILL.md` — Protocol idioms, monkeypatch idioms, integration-test layering
- `databricks-deploy/CONFIG-EXEMPTIONS.md` (post kdb-2-02) — current ledger
- `feedback_no_amend_in_concurrent_quicks.md` — forward-only commit rule
- `feedback_skill_invocation_not_reference.md` — Skill() invocation literal-substring contract

**Action:**

1. Invoke `Skill(skill="python-patterns")` with args `"Audit the integration test design in tests/integration/test_kg_synthesize_dispatcher.py: confirm idiomatic use of (a) sys.modules monkeypatching to inject a fake module for the hyphenated databricks-deploy/ path; (b) pytest.MonkeyPatch.setenv for env-var scoping; (c) re-import via _purge helper to ensure the dispatcher's lazy-import resolves freshly each test; (d) async test pattern with pytest-asyncio. Confirm the test surface accurately reflects Decision 1's translation-in-dispatcher contract (re-raise unchanged into existing kg_unavailable bucket) without adding a new kg_serving_unavailable literal anywhere."` — record output substring in SUMMARY.md
2. Edit `databricks-deploy/CONFIG-EXEMPTIONS.md`:
   - Change line 12 row from:
     ```
     | `kg_synthesize.py` | LLM-DBX-02 | kdb-2 | NOT YET MODIFIED |
     ```
     to (placeholder commit hash filled in step 5):
     ```
     | `kg_synthesize.py` | LLM-DBX-02 | kdb-2 | MODIFIED (quick-260509-s29 W3 — dispatcher route already in place; kdb-2-03 confirms via test in commit <FILL_AT_COMMIT>) |
     ```
   - Add a paragraph titled "Phase kdb-2-03 contribution":
     ```
     ## Phase kdb-2-03 contribution

     Plan kdb-2-03 contributes ZERO net code changes to `kg_synthesize.py` (the
     dispatcher integration at line 19 + line 106 was historical, shipped in
     quick-260509-s29 W3). The plan adds `tests/integration/test_kg_synthesize_dispatcher.py`
     (NEW) with 2 tests verifying:

       1. `OMNIGRAPH_LLM_PROVIDER=databricks_serving` actually exercises the
          kdb-2-02 dispatcher branch through `synthesize_response` (LLM-DBX-02
          env-var-exercise contract from REQ line 39).
       2. The dispatcher's translation shim re-raises Databricks SDK 503/429/
          timeout errors unchanged so `kb/services/synthesize.py`'s existing
          `except Exception as e` handler routes to the existing `kg_unavailable`
          reason-code bucket (LLM-DBX-04 via phase Decision 1 — no new reason
          code, no `kb/services/synthesize.py` modification, no CONFIG-EXEMPTIONS
          extension).

     `kg_synthesize.py` row in this ledger is flipped from NOT YET MODIFIED to
     MODIFIED so the audit at kdb-3 close (`git log cfe47b4..HEAD --grep '(kdb-'
     --name-only -- kb/ lib/`) cleanly excludes the historical change via the
     CONFIG-EXEMPTIONS allowed-edit list.
     ```
3. Stage explicitly: `git add tests/integration/__init__.py tests/integration/test_kg_synthesize_dispatcher.py databricks-deploy/CONFIG-EXEMPTIONS.md`
   (only include `tests/integration/__init__.py` if NEW — if it already exists from prior work, omit)
4. Commit forward-only:
   ```
   test(kdb-2-03): integration tests confirm dispatcher path + LLM-DBX-04 translation

   - tests/integration/test_kg_synthesize_dispatcher.py (NEW): 2 tests covering:
     * OMNIGRAPH_LLM_PROVIDER=databricks_serving exercises the kdb-2-02
       dispatcher branch through kg_synthesize.synthesize_response (LLM-DBX-02
       env-var-exercise contract).
     * Dispatcher translation shim re-raises Databricks SDK 503/429/timeout
       errors unchanged, satisfying LLM-DBX-04 via phase Decision 1 (no new
       reason code, no kb/services/synthesize.py modification).
   - databricks-deploy/CONFIG-EXEMPTIONS.md: flip kg_synthesize.py row from
     NOT YET MODIFIED to MODIFIED + add kdb-2-03 contribution paragraph.

   REQs: LLM-DBX-02 (verification + ledger flip); LLM-DBX-04 (verification of
   kdb-2-02 implementation per Decision 1)
   ```
5. Capture commit hash; backfill `<FILL_AT_COMMIT>` in CONFIG-EXEMPTIONS.md; commit forward-only as `docs(kdb-2-03): backfill commit hash into CONFIG-EXEMPTIONS row`.

**Acceptance** (grep-verifiable):
- `grep -E "kg_synthesize\.py.*MODIFIED \(quick-260509-s29.*kdb-2-03" databricks-deploy/CONFIG-EXEMPTIONS.md` returns ≥1 row
- `grep -c "Phase kdb-2-03 contribution" databricks-deploy/CONFIG-EXEMPTIONS.md` returns 1
- `git log --oneline | head -3` shows BOTH the test commit AND the docs backfill commit (forward-only)
- `git log -1 --name-only` for the test commit shows ONLY: `tests/integration/test_kg_synthesize_dispatcher.py` (+ optional `tests/integration/__init__.py` if NEW), `databricks-deploy/CONFIG-EXEMPTIONS.md`. **NOT** `kg_synthesize.py` (Decision 3 — zero net change). **NOT** `kb/services/synthesize.py` (Decision 1).
- `git diff <kdb-2-02-commit>..HEAD -- kg_synthesize.py` returns empty (proves Decision 3 ZERO new lines)
- `git diff <kdb-2-02-commit>..HEAD -- kb/services/synthesize.py` returns empty (proves Decision 1 NOT MODIFIED)
- SUMMARY.md will contain literal `Skill(skill="python-patterns"` (≥1 occurrence)

**Done:** Two clean forward-only commits; CONFIG-EXEMPTIONS row carries actual commit hash; no `kg_synthesize.py` or `kb/services/synthesize.py` changes audited.

**Time estimate:** 30 min.

## Verification (what `kdb-2-03-SUMMARY.md` MUST cite)

1. `pytest tests/integration/test_kg_synthesize_dispatcher.py -v` output verbatim showing `2 passed`
2. The 2 test names exactly: `test_dispatcher_path_databricks_serving`, `test_llm_dbx_04_serving_unavailable_falls_back_to_fts5`
3. Defensive grep (Task 3.1 step 1) on `kg_synthesize.py` returning ZERO matches for legacy hardcoded LLM patterns
4. Positive grep (Task 3.1 step 2) on `kg_synthesize.py` returning exactly 2 matches for the dispatcher integration
5. `grep -E "kg_synthesize\.py.*MODIFIED.*kdb-2-03" databricks-deploy/CONFIG-EXEMPTIONS.md` returns ≥1 row with actual commit hash
6. The 2 commit hashes (test + docs backfill) for forward-only audit
7. `git diff <kdb-2-02-commit>..HEAD -- kg_synthesize.py kb/services/synthesize.py` returns empty (Decision 1 + Decision 3 contract proof)
8. Skill invocation evidence — literal `Skill(skill="python-patterns"` AND `Skill(skill="writing-tests"` substrings (each ≥1 in SUMMARY.md)
9. Explicit narrative paragraph in SUMMARY.md acknowledging that deeper full-stack `kb_synthesize` integration test is deferred to kdb-3 UAT — with rationale referencing Decision 1 + the existing kb-v2.1-1 hardening test coverage of the `except Exception` fallback path

## Hard constraints honored

- **(scope — Decision 3)** ZERO modifications to `kg_synthesize.py` (verified by `git diff <kdb-2-02-commit>..HEAD -- kg_synthesize.py` returning empty)
- **(scope — Decision 1)** ZERO modifications to `kb/services/synthesize.py`; CONFIG-EXEMPTIONS NOT extended (verified by `git diff` + grep on CONFIG-EXEMPTIONS row count)
- **(scope — Decision 2)** No `lib/embedding_complete.py` file created
- **(scope — kdb-1.5 territory)** ZERO modifications to `databricks-deploy/startup_adapter.py` or `databricks-deploy/lightrag_databricks_provider.py`
- **(scope — kdb-2-02 territory)** ZERO modifications to `lib/llm_complete.py` (this plan only consumes its kdb-2-02 implementation)
- **(reason-code — Decision 1)** No literal `kg_serving_unavailable` introduced anywhere in the codebase (verified by `grep -rn "kg_serving_unavailable" --include="*.py" -- .` returning empty)
- **(safety)** Forward-only commits — `git add <explicit-files>` only; no `git add -A`; no `git commit --amend`
- **(skills)** `Skill(skill="writing-tests")` invoked in Task 3.2; `Skill(skill="python-patterns")` invoked in Task 3.3 — frontmatter ↔ task invocation 1:1

## Anti-patterns (block list)

This plan MUST NOT:
- Modify `kg_synthesize.py` (Decision 3 — zero net change; if defensive grep at Task 3.1 surfaces unexpected legacy code, plan STOPS and surfaces to user)
- Modify `kb/services/synthesize.py` or extend CONFIG-EXEMPTIONS to it (Decision 1)
- Modify `lib/llm_complete.py` (kdb-2-02 territory; already shipped)
- Create `lib/embedding_complete.py` (Decision 2)
- Introduce a literal `kg_serving_unavailable` reason-code anywhere (Decision 1 — existing `kg_unavailable` is reused via translation)
- Modify `databricks-deploy/startup_adapter.py` or `databricks-deploy/lightrag_databricks_provider.py`
- Make any real Model Serving call from these tests (mock-only; no $ cost; sub-30s test runtime)
- Use `git commit --amend` to backfill the commit hash
- Use `git add -A` or `git add .`

## Estimated time total

0.25-0.5d (Task 3.1: 15 min + Task 3.2: 1.5h + Task 3.3: 30 min + buffer ≈ 2.0-3.0h ≈ 0.25-0.4d). Lower bound reflects Decision 3's reduced scope (no `kg_synthesize.py` editing, only verification).
