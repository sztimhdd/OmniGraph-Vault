---
artifact: VERIFICATION
phase: kdb-2
iteration: 1
total_iterations: 3
verifier: gsd-plan-checker
date: 2026-05-16
verdict: PASS_WITH_WARNINGS
---

# Phase kdb-2 -- Plan-phase Verification Report (iter 1 of 3)

## Verdict

**PASS_WITH_WARNINGS** -- All 6 locked decisions honored, all 6 ROADMAP rev 3 hard constraints addressed, all 20 REQs mapped to tasks with grep-verifiable acceptance, dependency graph clean, time-box 1.5-2.25d within budget, no Wave 1 file overlap. **2 MAJOR + 3 MINOR warnings** documented below -- none are blockers; orchestrator may proceed to commit-phase plus an optional follow-up patch dispatch (single iteration) if it wants to harden the frontmatter on plan kdb-2-02 + the layout-discovery fallback narrative on plan kdb-2-04.

The plan-phase artifacts are unusually disciplined for a 4-plan phase: every task has Read-first / Action / Acceptance / Done; every Skill named in frontmatter has a literal `Skill(skill="...")` invocation in a task body (per `feedback_skill_invocation_not_reference.md`); every locked decision is re-stated in each plan Hard-constraints-honored / Anti-patterns sections; CONFIG-EXEMPTIONS scope is surgical (2 row flips, no new rows); concurrent-quick safety is explicitly cited (`feedback_no_amend_in_concurrent_quicks.md` + `feedback_git_add_explicit_in_parallel_quicks.md`).

## 1. Goal-backward map (ROADMAP success criterion -> task)

ROADMAP-kb-databricks-v1.md lines 90-96 enumerate 5 numbered success criteria. Each maps to a concrete task:

| # | ROADMAP success criterion | Plan : Task | Grep-verifiable acceptance |
|---|---------------------------|-------------|----------------------------|
| 1 | `databricks apps get omnigraph-kb` shows `state: RUNNING` + non-null URL | kdb-2-04 : Task 4.4 | `apps get ... jq -r .compute_status.state` returns `ACTIVE`/`RUNNING`; `.url` non-null (Task 4.4 acceptance lines 429-430) |
| 2 | `SHOW GRANTS` verifiable for catalog/schema/volume + `serving-endpoints get-permissions` | kdb-2-01 : Task 1.2 + Task 1.3 | Task 1.2 acceptance lines 121-124 (3 SHOW GRANTS positive checks + 1 defensive WRITE absence check); Task 1.3 acceptance lines 150-153 (Path A or Path B-deferred narrative) |
| 3 | `lib/llm_complete.py` databricks_serving unit-tested + integrated; `kg_synthesize.py` routes via dispatcher; CONFIG-EXEMPTIONS records both | kdb-2-02 : Tasks 2.1+2.2+2.3 -> kdb-2-03 : Tasks 3.1+3.2+3.3 | kdb-2-02 acceptance lines 252-258 (9 tests pass + grep databricks_serving >=3); kdb-2-03 acceptance lines 236-241 (2 integ tests pass + CONFIG-EXEMPTIONS row flipped) |
| 4 | Smoke 1 PASS -- App URL renders home page; zero ERROR cold start; OMNIGRAPH_BASE_DIR + 3 LLM literals visible | kdb-2-04 : Task 4.5 | Task 4.5 acceptance lines 466-470 (5 screenshot paths + zero-ERROR Logs panel + cross-reference to Task 4.4 cold-start log); Task 4.1 grep audit C3 = 3 LLM literals in app.yaml |
| 5 | Smoke 2 PASS -- bilingual `/api/search` (>=3 zh + >=3 en) + detail page renders w/ images via `/static/img/...` | kdb-2-04 : Task 4.6 | Task 4.6 acceptance lines 500-505 (5 screenshot paths + >=3-hits assertion zh + en + lang attr verification + image-via-/static/img check + Smoke 3 deferral note) |

5 / 5 ROADMAP success criteria have a covering task with grep-verifiable acceptance. Goal-backward coverage **PASS**.


## 2. REQ coverage table -- all 20 REQs

ROADMAP line 88 enumerates 20 REQs. Per-REQ task ID + acceptance grep:

| REQ | Plan : Task | Acceptance grep | Status |
|-----|-------------|-----------------|--------|
| AUTH-DBX-01 | kdb-2-01 : 1.2 | `SHOW GRANTS ON CATALOG mdlg_ai_shared` filtered to SP returns `USE_CATALOG` row (line 121) | OK |
| AUTH-DBX-02 | kdb-2-01 : 1.2 | `SHOW GRANTS ON SCHEMA mdlg_ai_shared.kb_v2` returns `USE_SCHEMA` row (line 122) | OK |
| AUTH-DBX-03 | kdb-2-01 : 1.2 | `SHOW GRANTS ON VOLUME ...` returns `READ_VOLUME` >=1 row AND `WRITE_VOLUME` 0 rows (lines 123-124, defensive check) | OK |
| AUTH-DBX-04 | kdb-2-01 : 1.3 | `.scratch/kdb-2-01-perms-{llm,embed}.json` exists; evidence MD section explicit Path A or Path B-deferred (lines 150-153) | OK (Path B fallback explicitly documented; OK per RESEARCH Q1c) |
| AUTH-DBX-05 | kdb-2-01 : 1.4 + kdb-2-04 : 4.5 | Documented as Apps default + cited in Smoke 1 browser session (kdb-2-01 line 175; kdb-2-04 Task 4.5 implicit via SSO browser flow) | OK |
| LLM-DBX-01 | kdb-2-02 : 2.1+2.2 | `pytest tests/unit/test_llm_complete.py -v` exit 0; `9 passed`; grep -c "databricks_serving" lib/llm_complete.py >=3 (lines 252-256) | OK |
| LLM-DBX-02 | kdb-2-03 : 3.1+3.2+3.3 | Defensive grep zero matches; positive grep 2 matches (line 19 + 106); 2 integ tests pass; CONFIG-EXEMPTIONS row flipped to MODIFIED w/ commit hash | OK |
| LLM-DBX-04 | kdb-2-02 : 2.2 (impl) + kdb-2-03 : 3.2 (verify) | kdb-2-02 dispatcher branch contains translation shim (lines 229-246 of plan); kdb-2-03 test_llm_dbx_04_serving_unavailable_falls_back_to_fts5 proves re-raise contract | OK (but see Warning M-1 -- frontmatter listing) |
| LLM-DBX-05 | kdb-2-04 : 4.1 | grep -cE "OMNIGRAPH_LLM_PROVIDER|KB_LLM_MODEL|KB_EMBEDDING_MODEL" databricks-deploy/app.yaml returns 3 (Task 4.1 acceptance C3, line 242) | OK |
| DEPLOY-DBX-01 | kdb-2-04 : 4.4 | `apps get omnigraph-kb` returns non-error JSON; state ACTIVE/RUNNING (line 429) | OK |
| DEPLOY-DBX-02 | kdb-2-04 : 4.1 | `find databricks-deploy -maxdepth 1 -name app.yaml` returns 1 (Task 4.1 audit C1, line 237) | OK |
| DEPLOY-DBX-03 | kdb-2-04 : 4.1 | grep -c DATABRICKS_APP_PORT app.yaml >=1; grep -c :8766 = 0 (audit C2) | OK |
| DEPLOY-DBX-04 | kdb-2-04 : 4.1+4.4 | C3 grep (3 literals) + cold-start log shows `startup_adapter:` line + env literals echoed (Task 4.4 line 433) | OK |
| DEPLOY-DBX-05 | kdb-2-04 : 4.4 | Total elapsed seconds < 1200 captured in evidence (line 435) | OK |
| DEPLOY-DBX-06 | kdb-2-04 : 4.5 | Browser-SSO UAT screenshot of home page rendered post-SSO | OK |
| DEPLOY-DBX-07 | kdb-2-04 : 4.3 | `grep -ci "deepseek" databricks-deploy/requirements.txt` returns 0 (Task 4.3 line 378) | OK |
| DEPLOY-DBX-08 | kdb-2-04 : 4.1 | Literal `OMNIGRAPH_LLM_PROVIDER=databricks_serving` in app.yaml; valueFrom: count = 0 (audit C4) | OK |
| DEPLOY-DBX-09 | kdb-2-04 : 4.1 | grep -cE "KB_KG_GCP_SA_KEY_PATH|GOOGLE_APPLICATION_CREDENTIALS" databricks-deploy/app.yaml = 0 (audit C6) | OK |
| OPS-DBX-01 | kdb-2-04 : 4.5 | 5 screenshot paths + zero-ERROR Logs assertion + bilingual UI toggle verification | OK |
| OPS-DBX-02 | kdb-2-04 : 4.6 | 5 screenshot paths + >=3 hits zh + >=3 hits en + detail-page lang attr + image rendering | OK |

**20 / 20 REQs covered.** Each has a task ID and grep-verifiable acceptance criterion (or in 1 case -- AUTH-DBX-04 -- an explicitly-documented Path B fallback). **PASS.**

PROJECT.md cross-check: per CONTEXT.md the relevant in-scope set is the 20 listed; STORAGE-DBX-01..05 + SEED-DBX-01..03 are kdb-1 / kdb-2.5 territory; CONFIG-DBX-01..02 + QA-DBX + OPS-DBX-03..05 are kdb-3 territory; SPIKE-DBX + PREFLIGHT-DBX are kdb-1 territory. **No PROJECT.md / REQUIREMENTS.md REQ relevant to kdb-2 is silently dropped.**

## 3. Locked decision honoring (6/6)

| # | Decision | Plans verified | Status |
|---|----------|----------------|--------|
| 1 | LLM-DBX-04 = translation in dispatcher (no kb/services edit, no CONFIG-EXEMPTIONS extension, no kg_serving_unavailable literal) | kdb-2-02 plan body lines 21-23 (translation shim); kdb-2-02 anti-patterns line 356; kdb-2-03 anti-patterns line 354 (No literal kg_serving_unavailable); CONTEXT.md lines 35-44 | OK |
| 2 | Embedding dim risk DEFERRED | kdb-2-02 anti-pattern line 357; kdb-2-03 anti-pattern line 354 (Create lib/embedding_complete.py forbidden); kdb-2-04 anti-pattern line 616; explicit cite in kdb-2-04 Task 4.7 self-check + Verification line 587 | OK |
| 3 | LLM-DBX-02 reduced (zero new lines in kg_synthesize.py) | kdb-2-03 plan body lines 23-29; Task 3.3 acceptance line 317 (`git diff ... kg_synthesize.py` returns empty); Hard constraints honored line 339 | OK |
| 4 | Browser-SSO interactive UAT (no curl + Bearer; no Playwright-from-local for Smoke) | kdb-2-04 Tasks 4.5 + 4.6 user-checklist structure; explicit anti-patterns lines 624-625 (block external Bearer-token curl + Playwright MCP from local Windows for Smoke 1+2) | OK |
| 5 | app.yaml command verbatim shape (single bash -c, $DATABRICKS_APP_PORT) | kdb-2-04 Task 4.1 lines 191-194 reproduce locked shape verbatim; Task 4.0 Wave-0 layout discovery is the documented MEDIUM-confidence guard | OK |
| 6 | Smoke 3 DEFERRED to kdb-3 | kdb-2-04 Out-of-scope line 104; Task 4.6 step 6 (line 497, expected behavior NOT a failure); Verification line 586; Anti-patterns line 612 | OK |

**6 / 6 locked decisions honored.** No re-litigation; each decision is restated in at least 2 places per plan (body + anti-pattern + acceptance grep).

## 4. Hard constraints (ROADMAP rev 3 lines 98-105) -- 6/6

| # | Constraint | Verifier | Status |
|---|------------|----------|--------|
| a | `app.yaml` at root of `--source-code-path` | kdb-2-04 Task 4.1 audit C1: find databricks-deploy -maxdepth 1 -name app.yaml | wc -l = 1 | OK |
| b | `command:` uses `$DATABRICKS_APP_PORT` substitution | Task 4.1 audit C2: grep -c DATABRICKS_APP_PORT app.yaml >=1; grep -c :8766 = 0 | OK |
| c | 3 LLM env literals present | Task 4.1 audit C3: grep -cE OMNIGRAPH_LLM_PROVIDER pipe KB_LLM_MODEL pipe KB_EMBEDDING_MODEL app.yaml = 3 | OK |
| d | Zero `valueFrom:` for any LLM env | Task 4.1 audit C4: grep -c valueFrom: app.yaml = 0 | OK |
| e | Zero DeepSeek references in databricks-deploy/, app.yaml, requirements.txt | Task 4.1 audit C5: grep -ci deepseek databricks-deploy/requirements.txt = 0; grep -ci deepseek app.yaml = 1 (the documented `DEEPSEEK_API_KEY=dummy` Phase-5 cross-coupling guard, with explicit narrative) | OK (with documented exception -- see Minor M-3) |
| f | LLM-DBX-02 diff scope = ZERO new lines in kg_synthesize.py | kdb-2-03 Task 3.3 acceptance line 317: git diff kdb-2-02-commit..HEAD -- kg_synthesize.py returns empty | OK |

**6 / 6 hard constraints addressed** with grep-verifiable command. Constraint (e) has a documented exception: the `DEEPSEEK_API_KEY=dummy` line in app.yaml is explicitly called out as a Phase-5 cross-coupling guard per CLAUDE.md, NOT a real DeepSeek dep. The plan's evidence narrative makes this distinction clear (Task 4.1 step 3, Task 4.7 commit message). See Minor M-3.


## 5. Skill discipline -- per `feedback_skill_invocation_not_reference.md`

For each plan, frontmatter `skills:` must be matched 1:1 by literal `Skill(skill="<name>", ...)` invocation in at least one task. Verified by direct read of each plan file:

### kdb-2-01 -- frontmatter declares `databricks-patterns`, `security-review`

| Skill | Invocation site | Substring present |
|-------|-----------------|-------------------|
| databricks-patterns | Task 1.1 step 4 (line 82) | OK -- Skill(skill="databricks-patterns") |
| security-review | Task 1.2 step 2 (line 109) | OK -- Skill(skill="security-review") |

Both flow through to SUMMARY.md per Verification line 191 (literal substring requirement).

### kdb-2-02 -- frontmatter declares `python-patterns`, `writing-tests`

| Skill | Invocation site | Substring present |
|-------|-----------------|-------------------|
| writing-tests | Task 2.1 step 1 (line 85) | OK -- Skill(skill="writing-tests") |
| python-patterns | Task 2.2 step 1 (line 200) | OK -- Skill(skill="python-patterns") |

### kdb-2-03 -- frontmatter declares `python-patterns`, `writing-tests`

| Skill | Invocation site | Substring present |
|-------|-----------------|-------------------|
| writing-tests | Task 3.2 step 1 (line 125) | OK -- Skill(skill="writing-tests") |
| python-patterns | Task 3.3 step 1 (line 257) | OK -- Skill(skill="python-patterns") |

### kdb-2-04 -- frontmatter declares `databricks-patterns`, `search-first`

| Skill | Invocation site | Substring present |
|-------|-----------------|-------------------|
| databricks-patterns | Task 4.0 step 1 (line 130) | OK -- Skill(skill="databricks-patterns") |
| search-first | Task 4.2 step 1 (line 277) | OK -- Skill(skill="search-first") |

**Skill discipline ALL 4 plans PASS -- 8/8 frontmatter-to-invocation pairs match.** Zero overclaim, zero underclaim.

## 6. Anti-shallow execution (sample 2-3 tasks per plan)

### kdb-2-01

- **Task 1.1** -- Read-first 2 cites; Action 5 numbered steps with concrete CLI/MCP calls + jq filter; Acceptance 4 grep-verifiable conditions (GUID regex, line count, jq output, literal substring); Done sentence; Time 20 min. PASS.
- **Task 1.2** -- Read-first 3 cites; Action 5 steps incl. defensive WRITE-absence check (security-review-level rigor); Acceptance 5 conditions inc. defensive grep; PASS.
- **Task 1.3** -- Read-first 2 cites; Action handles BOTH Path A success + Path A failure with explicit branch; Acceptance recognizes either-path narrative as PASS -- appropriate given RESEARCH Q1c TBD-grammar uncertainty. PASS.

### kdb-2-02

- **Task 2.1** -- Read-first 4 cites; Action lays out concrete 4 test bodies in plan (Python source, ~80 lines); Acceptance 5 grep-verifiable conditions (test count, name match, RED-phase exit code, asyncio import, Skill substring); Time 1.0h. PASS.
- **Task 2.2** -- Read-first 5 cites incl. line-numbered RESEARCH refs; Action lays out the exact insertion-point line numbers + the 30-line branch source verbatim; Acceptance 6 grep conditions inc. lazy-import spot check; PASS.
- **Task 2.3** -- Read-first 3 cites; Action specifies the exact CONFIG-EXEMPTIONS row before/after diff + the 2-commit forward-only pattern (placeholder -> backfill) per `feedback_no_amend_in_concurrent_quicks.md`; Acceptance includes the no-amend audit; PASS.

### kdb-2-03

- **Task 3.1** -- Defensive + positive grep with explicit STOP-and-surface branch if defensive grep fails (Decision 3 self-protection); Acceptance 3 conditions; Time 15 min -- appropriately small for an audit task. PASS.
- **Task 3.2** -- Read-first 5 cites; Action specifies the integration test source file verbatim (~90 lines Python with sys.modules monkeypatch + pytest-asyncio); explicit deferral to kdb-3 UAT for deeper full-stack mocking with 3-bullet rationale; PASS -- but see Minor M-4 (Objective text vs. test body mismatch).
- **Task 3.3** -- Same forward-only 2-commit pattern as kdb-2-02. Acceptance includes Decision-1 + Decision-3 contract proof via `git diff` returning empty for kg_synthesize.py + kb/services/synthesize.py. PASS.

### kdb-2-04

- **Task 4.0** (Wave-0 layout discovery) -- Concretely defines the minimal app.yaml probe shape, the workspace-import + apps deploy sequence, the log-inspection target strings (WAVE0-PROBE-START/END + sys.path), and the Decision branch for layout-mismatch. PASS -- but see Warning M-2 (escalation path on layout failure).
- **Task 4.1** -- Production app.yaml laid out verbatim (~60 lines YAML + comments); 6 hard-constraint grep audits with expected values; the `DEEPSEEK_API_KEY=dummy` Phase-5 guard explicitly documented in YAML comment. PASS.
- **Task 4.5/4.6** -- User-in-loop checklists with screenshot path discipline (`.playwright-mcp/kdb-2-smoke{1,2}-N-...png`); explicit Decision-4 cite (no curl + Bearer); explicit Decision-6 cite (Smoke 3 deferral); 10 screenshots total across the two smokes. PASS.

**Anti-shallow PASS.** Every sampled task has concrete files, concrete commands or YAML/Python source, grep-verifiable acceptance, and no investigate-X / research-Y / make-it-work placeholders.

## 7. Wave + dependency graph

| Plan | Wave | depends_on | Files modified | Conflict? |
|------|------|------------|----------------|-----------|
| kdb-2-01 | 1 | `[]` | None in source-tree (CLI/SQL only) + `.planning/.../kdb-2-01-AUTH-EVIDENCE.md` (NEW) + `.scratch/*` | No |
| kdb-2-02 | 1 | `[]` | `lib/llm_complete.py` + `tests/unit/test_llm_complete.py` + `databricks-deploy/CONFIG-EXEMPTIONS.md` | No |
| kdb-2-03 | 2 | `["kdb-2-02"]` | `tests/integration/test_kg_synthesize_dispatcher.py` (NEW) + `databricks-deploy/CONFIG-EXEMPTIONS.md` (different row from kdb-2-02) | No |
| kdb-2-04 | 3 | `["kdb-2-01","kdb-2-02","kdb-2-03"]` | `databricks-deploy/{app.yaml,Makefile}` (NEW) + `kdb-2-SMOKE-EVIDENCE.md` (NEW) + optional `requirements.txt` | No |

**Wave 1 file overlap analysis:** kdb-2-01 modifies zero source-tree files; kdb-2-02 modifies `lib/llm_complete.py` + tests + CONFIG-EXEMPTIONS. Disjoint sets -- **safe to parallel-execute**.

**Wave 2 dependency:** kdb-2-03's integration tests rely on the kdb-2-02 dispatcher branch implementation. Dependency correct.

**Wave 3 dependency:** kdb-2-04 deploy needs (a) AUTH grants from kdb-2-01 for the App SP to read UC + query Model Serving at runtime; (b) the dispatcher branch from kdb-2-02 baked into the deployed image; (c) the kdb-2-03 verification proving the dispatcher path works pre-deploy. Dependency correct.

**CONFIG-EXEMPTIONS.md edit ordering:** kdb-2-02 flips row 1 (`lib/llm_complete.py`) in Wave 1; kdb-2-03 flips row 2 (`kg_synthesize.py`) in Wave 2 -- sequential; no concurrent edit. PASS.

**Dependency graph PASS.** No cycles, no future references, wave numbers consistent with dependency depth.

## 8. Time-box

| Plan | Estimated | Tasks | Largest single task |
|------|-----------|-------|---------------------|
| kdb-2-01 | 0.25d (~95 min) | 4 | Task 1.2 = 30 min |
| kdb-2-02 | 0.5d (3-4h) | 3 | Task 2.2 = 1.5h |
| kdb-2-03 | 0.25-0.5d (2-3h) | 3 | Task 3.2 = 1.5h |
| kdb-2-04 | 0.5-1d (5.5-7h) | 8 (incl. Task 4.0) | Task 4.0 = 1.0h, Task 4.1 = 1.0h |

**Total:** 1.5-2.25d (within 1.75-2.25d budget per CONTEXT line 7). **Largest single task = 1.5h** (Tasks 2.2 + 3.2 -- both implementation+test work). **No task exceeds 2h.** PASS.


## 9. CONFIG-EXEMPTIONS scope discipline

Pre-kdb-2 ledger (current state of `databricks-deploy/CONFIG-EXEMPTIONS.md` lines 11-12):

- Row 1: `lib/llm_complete.py` -- LLM-DBX-01 -- kdb-2 -- NOT YET MODIFIED
- Row 2: `kg_synthesize.py` -- LLM-DBX-02 -- kdb-2 -- NOT YET MODIFIED

Post-kdb-2 expected ledger:

- Row 1: `lib/llm_complete.py` -- LLM-DBX-01 + LLM-DBX-04 (translation) -- kdb-2 -- MODIFIED (kdb-2-02 -- see commit hash)
- Row 2: `kg_synthesize.py` -- LLM-DBX-02 -- kdb-2 -- MODIFIED (quick-260509-s29 W3 -- dispatcher route already in place; kdb-2-03 confirms via test in commit hash)

**Plans flip exactly 2 rows. No third row added.** kdb-2-04 explicitly states "CONFIG-EXEMPTIONS impact: NONE" (line 117). Decision 1 honored -- `kb/services/synthesize.py` is NOT added to the ledger. PASS.

## 10. Open questions handling (4 planner-surfaced)

| # | Open question | Handling | Status |
|---|---------------|----------|--------|
| a | `kb/api/app.py` actual entry point name | kdb-2-04 Task 4.0 Wave-0 minimal-deploy validates layout (incl. uvicorn-reachability of `kb.api.app:app`); Task 4.3 enumerates `kb/api/` imports to verify dependency baseline | OK (verified before app.yaml locks) |
| b | `--source-code-path` layout (PYTHONPATH semantics) | kdb-2-04 Task 4.0 Wave-0 explicit minimal-deploy probe with pwd; ls -la /app/; sys.path capture | OK |
| c | `databricks apps stop` CLI existence | kdb-2-04 Task 4.2 step 1 invokes Skill(skill="search-first") AND step 2 runs hands-on `databricks apps stop --help` probe | OK |
| d | Reason-code-string assertion shape in integration test | kdb-2-03 Task 3.2 step 5 explicitly defers deeper full-stack assertion to kdb-3 UAT with 3-bullet rationale | OK (deferred with rationale) |

**4 / 4 open questions handled** -- none silently swept under rug.


## 11. Issues found

### MAJOR (M-1, M-2) -- should fix; orchestrator can proceed but flag for executor awareness

#### M-1 -- kdb-2-02 frontmatter `requirements:` field omits LLM-DBX-04

- **File:** `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-02-llm-dispatcher-databricks-serving-PLAN.md` lines 8-9
- **Current state:** frontmatter `requirements:` lists only `LLM-DBX-01` (single-line bullet).
- **Issue:** Plan body line 23 reads "Maps to: LLM-DBX-01 (full); LLM-DBX-04 (implementation -- verification in kdb-2-03)". CONTEXT.md line 95 reads "kdb-2-02 ... REQs: LLM-DBX-01 (1) + LLM-DBX-04 implementation". Both confirm LLM-DBX-04 IMPLEMENTATION lives in kdb-2-02 (Decision 1 -- translation in dispatcher). However, the YAML frontmatter declares only LLM-DBX-01. The CONFIG-EXEMPTIONS row this plan flips actually carries the literal text "LLM-DBX-01 + LLM-DBX-04 (translation)" (line 69) -- proving the plan owns LLM-DBX-04 implementation. Frontmatter under-claims what the plan delivers.
- **Why it matters:** Future automated REQ-to-plan grep will incorrectly report LLM-DBX-04 as having ZERO implementing plans (only kdb-2-03 lists it for verification). At kdb-3 close audit, an orchestrator searching `requirements: ...LLM-DBX-04...` across kdb-2 plans would find only kdb-2-03 -- and would mistakenly conclude kdb-2-03 owns the implementation, whereas kdb-2-03 is verification-only per Decision 1 + Decision 3.
- **Required fix:** add `- LLM-DBX-04` to kdb-2-02 frontmatter `requirements:` -- so the list reads `- LLM-DBX-01` then `- LLM-DBX-04`. Re-commit forward-only on the planner side.
- **Severity:** MAJOR (not BLOCKER) because plan body + CONFIG-EXEMPTIONS row text are internally consistent -- substantive work is correctly scoped; only metadata is out of sync.

#### M-2 -- kdb-2-04 Task 4.0 layout-failure escalation lacks concrete fallback plan; could surface as a hidden BLOCKER mid-execution

- **File:** `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-04-deploy-and-smoke-PLAN.md` lines 148-151
- **Current state:** Wave-0 layout-discovery step describes the success branch concretely but the failure branch reads only: "STOP. Surface to user. Two options for resolution: (a) restructure --source-code-path to point at repo root with app.yaml symlinked or relocated; (b) restructure command: to use SDK Workspace files API to fetch kb/ from workspace at runtime. Both options exceed kdb-2 plan scope and require user decision."
- **Issue:** Both fallback options would actually require modifying frozen kdb-1.5 deliverables (option a -- if symlinking forces a startup_adapter.py move) or adding new code under `databricks-deploy/` that wraps Workspace files API (option b -- non-trivial; would itself need a CONFIG-EXEMPTIONS audit). If layout discovery reveals option-(a)/(b) is needed, the executor will be blocked mid-phase with an under-specified branch -- and the discovery does not happen until Task 4.0 (i.e. Wave 3, after kdb-2-01..03 land).
- **Why it matters:** This is a known risk per RESEARCH.md Q7 MEDIUM-confidence flag. The plan acknowledges it but does NOT specify what evidence the executor needs to capture before "Surface to user" -- and does NOT pre-stage which decision-maker (orchestrator vs user) is the escalation target. Mid-execution escalations on Wave-3 plans are the highest-cost class of plan failure (kdb-2-01..03 work is committed; rolling back is wasteful; redoing app.yaml shape forces a full re-deploy cycle).
- **Required fix:** Strengthen Task 4.0 step 5 with: (i) what fields to capture in the escalation report (pwd, ls /app/, sys.path, the workspace import-dir manifest); (ii) a Plan-B sketch -- option (a) is the lower-risk default because it is purely a path argument change (`--source-code-path /Workspace/.../omnigraph-kb` instead of `/Workspace/.../omnigraph-kb/databricks-deploy`); the corresponding `app.yaml` `command:` shape variant should be pre-written; (iii) explicit cite that this fallback is the SAME diff scope (still only `app.yaml` + `Makefile` -- does NOT modify kdb-1.5 deliverables); (iv) the escalation target = orchestrator (re-spawn planner with layout-evidence as input) NOT user (the user already locked Decision 5 -- a layout deviation is a planner re-litigation, not a user decision).
- **Severity:** MAJOR (not BLOCKER) -- Wave-0 may pass first try, in which case this is moot; but if it fails, the plan as-written under-specifies recovery.


### MINOR (M-3, M-4, M-5) -- cosmetic / paranoid hardening; not load-bearing

#### M-3 -- DEEPSEEK_API_KEY=dummy in app.yaml triggers grep-audit C5 returning 1 instead of 0; narrative compensates but tooling-grep would flag

- **File:** `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-04-deploy-and-smoke-PLAN.md` lines 99 + 226-227
- **Issue:** ROADMAP rev 3 line 104 hard-constraint reads: "Zero DeepSeek references in databricks-deploy/, app.yaml, or requirements.txt". The plan app.yaml includes `DEEPSEEK_API_KEY=dummy` as a Phase-5 cross-coupling guard (CLAUDE.md `lib/__init__.py:35` documented behavior). Plan correctly states grep -ci deepseek databricks-deploy/app.yaml will return 1, with explicit narrative in evidence MD (line 256). However a strict naive auditor at kdb-3 close would surface this as a hard-constraint violation.
- **Fix:** None required for kdb-2 plan-checker (the narrative is sound); but suggest planner add a one-line note in `kdb-2-SMOKE-EVIDENCE.md` template referencing the CLAUDE.md "Phase 5 DeepSeek cross-coupling" section so the kdb-3 audit passes without re-research. Already partially in place (Task 4.7 commit message line 551 mentions "DEEPSEEK_API_KEY=dummy guard"); could be more prominent in the evidence MD itself.
- **Severity:** MINOR.

#### M-4 -- kdb-2-03 Task 3.2 integration test test_dispatcher_path_databricks_serving does not actually call synthesize_response despite Objective claiming it

- **File:** `.planning/phases/kdb-2-databricks-app-deploy/kdb-2-03-kg-synthesize-routing-and-degrade-PLAN.md` lines 50-51 + lines 159-198 (test body)
- **Issue:** Plan Objective lines 50-51 and Scope line 51 promise a test that calls kg_synthesize.synthesize_response("hello") to cause the sentinel to be invoked (proves the env var actually exercises the new dispatcher branch through the LightRAG construction at kg_synthesize.py:106). But the actual concrete test body in lines 159-198 stops at `from lib.llm_complete import get_llm_func; fn = get_llm_func(); ... await fn("trigger-prompt")` -- it does NOT import kg_synthesize or call synthesize_response. This means the test verifies the lib/llm_complete.py dispatcher branch (already covered by kdb-2-02 unit tests) but does NOT verify the bridge from kg_synthesize.synthesize_response THROUGH the dispatcher (the actual LLM-DBX-02 contract per REQUIREMENTS line 39: "new test confirms dispatcher path executes when OMNIGRAPH_LLM_PROVIDER=databricks_serving is set" via the synthesize_response call site).
- **Why MINOR not MAJOR:** The dispatcher itself is unit-tested; LightRAG instantiation is heavyweight to mock; and Task 3.2 step 5 (line 234) acknowledges that deeper full-stack kb_synthesize integration test is deferred to kdb-3 UAT with 3-bullet rationale. The planner reasoning is defensible -- the LLM-DBX-02 dispatcher-path-executes contract is satisfied at the dispatcher layer. But the integration test body and the Objective/Scope text do not match.
- **Fix:** Either (a) tighten the Objective + Scope text to say "exercises the dispatcher branch through the same env-var that kg_synthesize.synthesize_response consumes" (i.e. accept that the test is dispatcher-layer only, which is what is actually written), OR (b) add a 3-line `import kg_synthesize` + verify kg_synthesize.get_llm_func resolves to the wrapped sentinel (cheap; no LightRAG instantiation needed). Option (a) is the simplest disambiguation.
- **Severity:** MINOR (text-vs-code mismatch; dispatcher contract substantively verified).

#### M-5 -- Smoke 1 evidence acceptance line "Logs panel zero ERROR" lacks a concrete grep-able definition

- **File:** kdb-2-04 Task 4.5 acceptance line 468
- **Issue:** Acceptance says the section must explicitly state "Smoke 1 PASS -- bilingual UI toggle works; cookie persistence works; ?lang=zh hard-switch works; Apps Logs tab shows zero ERROR during cold start". This is a literal-substring assertion on the evidence MD claimed text -- but the underlying observation ("zero ERROR during cold start") is a screenshot-only artifact. There is no grep against the actual log content (because Apps logs are not CLI-accessible in v0.260 per Task 4.2). A tester could in principle paste the wrong sentence into the evidence MD and the acceptance grep would still PASS.
- **Why MINOR:** This is intrinsic to Decision-4 user-in-loop UAT -- the screenshot IS the evidence; the textual claim is a paraphrase. No automated tool can validate a screenshot content. The plan correctly captures the screenshot path as part of acceptance (line 467) -- auditors at kdb-3 close can hand-inspect. Acceptable for kdb-2.
- **Fix:** None required. Documenting for awareness.
- **Severity:** MINOR.

## 12. Recommendation

**PASS_WITH_WARNINGS -- orchestrator may proceed to commit.**

Recommended actions before commit:

1. **(Optional, MAJOR M-1)** Patch kdb-2-02 frontmatter to add `LLM-DBX-04` to `requirements:` -- this is a single-line YAML edit, can be done as a follow-up commit on the planner side or absorbed into the executor first kdb-2-02 commit if surgical-add-only stays clean. Recommend the planner does it; the executor already has enough to track. If the orchestrator dispatches this fix as a single-shot revision (iter 2), expect ~5 minutes of planner time.

2. **(Optional, MAJOR M-2)** Strengthen kdb-2-04 Task 4.0 step 5 with a concrete Plan-B `app.yaml` variant + escalation-target = orchestrator (not user). Single-paragraph addition. Same rationale: 5-10 minutes of planner time; meaningful insurance against a Wave-3 mid-execution stall.

3. **(Skip)** M-3, M-4, M-5 are cosmetic / paranoid hardening; not load-bearing for plan execution. Defer to kdb-3 polish.

If the orchestrator wants to dispatch a single iter-2 revision: include only M-1 + M-2 in the revision prompt. If the orchestrator wants to commit-as-is: that is defensible -- the substantive work is correctly scoped, all 6 locked decisions are honored, all 20 REQs covered, all 6 hard constraints addressed, dependency graph clean, time-box within budget.

**Verdict:** PASS_WITH_WARNINGS. Iteration 1 of 3 closed. Plans are execution-ready.

---

_Authored: 2026-05-16 by gsd-plan-checker (iter 1 of 3). Honors all 6 locked decisions, 11 hard constraints (CONTEXT.md), 4 anti-pattern blocks. Plan-checker discipline:_

- Did NOT re-litigate locked decisions
- Did NOT verify code/runtime behavior (subject matter is plans, not codebase)
- Did NOT skip dependency analysis
- Cited file:line for every claim
- Honored `feedback_skill_invocation_not_reference.md`, `feedback_parallel_track_gates_manual_run.md`, `feedback_no_amend_in_concurrent_quicks.md`, `feedback_contract_shape_change_full_audit.md` -- all four memory directives surface in the analysis above

---

## Orchestrator post-iter-1 action (2026-05-16)

Orchestrator applied surgical inline patches for the 2 MAJOR warnings (avoided dispatching iter-2 since fixes were verbatim-specified by verifier):

- **M-1 patched** (commit shipped with this plan-phase commit): kdb-2-02 frontmatter `requirements:` now includes `LLM-DBX-04` alongside `LLM-DBX-01`, reflecting Decision-1 dispatcher-translation implementation ownership
- **M-2 patched** (same commit): kdb-2-04 Task 4.0 step 5 escalation branch now includes (i) concrete evidence-capture fields (pwd, ls -la /app/, sys.path, workspace import-dir manifest), (ii) Plan-B sketch with verbatim alternate `app.yaml` `command:` shape (`cd /app && PYTHONPATH=/app:/app/databricks-deploy ... databricks_deploy.startup_adapter`), (iii) explicit cite that diff scope is identical to baseline (no kdb-1.5 file edit, no CONFIG-EXEMPTIONS extension), (iv) escalation target = orchestrator (not user; Decision 5 locked)
- **M-3, M-4, M-5 accepted as MINOR** per verifier recommendation — cosmetic / paranoid hardening; not load-bearing for plan execution

**Final verdict after orchestrator action:** PASS — all 4 plans + CONTEXT + RESEARCH ready for `/gsd:execute-phase kdb-2`.
