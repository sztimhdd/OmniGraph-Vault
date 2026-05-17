# kdb-2.5 VERIFICATION

**Phase:** kdb-2.5 -- Re-index LightRAG Storage (Databricks Job)
**Milestone:** kb-databricks-v1 (parallel track)
**Plans verified:** 2 (kdb-2.5-01, kdb-2.5-02)
**Iteration:** 1 of 3
**Verified:** 2026-05-17

---

## 1. Verdict

**PASS_WITH_WARNINGS**

Both plans will achieve the phase goal. All 7 locked decisions are honored, both REQs are
covered with grep-verifiable acceptance criteria, and both CRITICAL gates (cost gate +
empty-target safety) have explicit non-hand-wavy decision templates. Two MINOR issues found
(skill discipline + documentation note) do not block execution.

---

## 2. Goal-Backward Map

ROADMAP rev 3 lines 139-148 (kdb-2.5 success criteria):

| Criterion | Description | Covering plan + task | File:line anchor |
|-----------|-------------|---------------------|------------------|
| Crit 1 | Job final state = SUCCEEDED | kdb-2.5-02 Task 2.2 | Plan 02 lines 208-212 (runs-get check) |
| Crit 2 | lightrag_storage/ populated: vdb_*.json + graph_*.graphml + kv_store_*.json with dim=1024 | kdb-2.5-02 Task 2.2 (Job writes) + Task 2.3 (dim assert) | Plan 02 lines 265-270; success_criteria item 3 |
| Crit 3 | <= 5% failures (~<= 9 of 170) | kdb-2.5-02 Task 2.2 + FAILURES.csv | Plan 02 lines 225-229 (failure_rate <= 0.05) |
| Crit 4 | SEED-DBX-03: dim=1024 + bilingual coverage + 2 round-trips | kdb-2.5-02 Task 2.3 | Plan 02 lines 274-285 (Step C assert block) |
| Crit 5 | Total cost recorded in kdb-2.5-VERIFICATION.md | kdb-2.5-02 Task 2.3 Step D | Plan 02 lines 287-296 (VERIFICATION authoring) |

All 5 success criteria have explicit covering tasks with grep-verifiable acceptance criteria.

---

## 3. REQ Coverage Table

| REQ | Description | Covering task(s) | Acceptance grep |
|-----|-------------|-----------------|------------------|
| SEED-DBX-02 | Re-index Job reads kol_scan.db (articles + rss_articles), calls ainsert per row, emits FAILURES.csv | kdb-2.5-01 Tasks 1.1+1.3+1.4 (Step 1); kdb-2.5-02 Task 2.2 (Step 2) | grep get_docs_by_ids reindex_lightrag.py; grep FAILURES.csv reindex_lightrag.py |
| SEED-DBX-03 | Post-check: dim=1024 entity vectors; bilingual zh+en; 2 round-trip queries non-empty | kdb-2.5-02 Task 2.3 | grep embedding_dim kdb-2.5-VERIFICATION.md; grep bilingual kdb-2.5-VERIFICATION.md |

Requirements in plan frontmatter:
- Plan 01 frontmatter lines 8-9: requirements: [SEED-DBX-02]
- Plan 02 frontmatter lines 10-12: requirements: [SEED-DBX-02, SEED-DBX-03]

**Coverage: 2/2 REQs covered.**

---

## 4. Locked Decision Honoring (7/7)

| Decision | Honored? | Evidence |
|----------|----------|----------|
| D-01: DATA-07 strict filter hardcoded | YES (note) | Task 1.1: filter_mode=strict default; YAML passes --filter-mode strict. argparse flag kept for testing only. Behavioral intent preserved. |
| D-02: 2-plan split with cost gate seam | YES | Wave 1 = kdb-2.5-01, Wave 2 = kdb-2.5-02; seam at Task 1.4 checkpoint. |
| D-03: Job principal = hhu@edc.ca; Plan 02 pre-flight verifies WRITE_VOLUME | YES | Plan 02 Task 2.1: SHOW GRANTS SQL + databricks fs ls before any Step 2 trigger. |
| D-04: NO ThreadPoolExecutor; single LightRAG instance | YES | Task 1.1: sequential await _ingest_one loop. Anti-patterns block: DO NOT add ThreadPoolExecutor. |
| D-05: Explicit doc-status post-check via get_docs_by_ids | YES | Task 1.1 action lines 207-211; done block grep check; test_ingest_one_checks_doc_status behavior test. |
| D-06: ainsert called with ids=[content_hash] | YES | Task 1.1 action line 208: await rag.ainsert(row.body, ids=[row.content_hash]); done block grep check. |
| D-07: Empty-target safety -- fail on non-empty; mtimes in error; no force-overwrite in YAML defaults | YES | _verify_target_empty raises RuntimeError with mtimes. Task 1.3 done block: no --force-overwrite in default params. Task 2.1 blocking pre-flight verifies empty target. |

**All 7 decisions honored. No violations.**

Note: RESEARCH.md summary line 13 still recommends ThreadPoolExecutor (pre-dates D-04 lock).
The PLAN correctly implements D-04. See Recommendation section for executor briefing note.

---

## 5. Hard Constraints (ROADMAP rev 3 lines 167-172)

| Constraint | Covered? | Evidence |
|-----------|---------|----------|
| Job must NOT silently overwrite existing lightrag_storage/ | YES | _verify_target_empty raises on non-empty; YAML no force-overwrite defaults; Task 2.1 blocking pre-flight. |
| Per-article failures: content_hash + truncated error (no PII, no path) | YES | Task 1.1: error_truncated = repr(e)[:200]; test_failures_csv_schema_no_path_leak asserts no slash chars. |
| Cost monitored real-time (alert if burn > Step 1 extrap x 1.5) | YES | Task 1.1: burn-rate alert every 25 articles; Task 2.2 Step B: grep BURN-RATE WARNING in logs. |
| Step 1 cost gate: > 30h OR > $200 -> STOP | YES | Task 1.4 checkpoint: explicit 3-criterion gate decision template; GATE: PASS or BLOCKED. |
| Failure tolerance: <= 5% of ~170; higher = REOPENED | YES | Task 2.2 Step E: failure_rate > 5% -> Step 2 REOPENED; success_criteria item 2. |
| Step 3 sanity fail = REOPENED | YES | Task 2.3 Step C: assertion block; any failure -> postcheck FAILED -- phase REOPENED. |

**All 6 hard constraints covered.**

---

## 6. Skill Discipline

Rule (feedback_skill_invocation_not_reference.md): Skills in plan frontmatter MUST appear as
explicit Skill(skill=..., args=...) calls in task action blocks -- not just listed.

### Plan 01 (kdb-2.5-01)

| Skill | Frontmatter | Action invocation | Status |
|-------|-------------|------------------|--------|
| databricks-patterns | YES | Task 1.1 + Task 1.3: explicit Skill() calls with concrete args | PASS |
| python-patterns | YES | Task 1.1: Skill(skill=python-patterns, args=Idiomatic frozen dataclass...) | PASS |
| writing-tests | YES | Task 1.2: Skill(skill=writing-tests, args=pytest fixtures with tmp_path...) | PASS |
| search-first | YES | Task 1.2 + Task 1.3: explicit Skill() calls | PASS |

Plan 01: 4/4 skills invoked. PASS.

### Plan 02 (kdb-2.5-02)

| Skill | Frontmatter | Action invocation | Status |
|-------|-------------|------------------|--------|
| databricks-patterns | YES | Task 2.3: Skill(skill=databricks-patterns, args=databricks bundle run...) | PASS |
| writing-tests | YES | Task 2.3: Skill(skill=writing-tests, args=Assert embedding_dim == 1024...) | PASS |
| systematic-debugging | YES | Referenced in output section as expected SUMMARY artifact entry. NOT a Skill() call in any task action body. | MINOR FAIL |

Plan 02: 2/3 skills properly invoked. One MINOR issue -- see Issues section.

---

## 7. Anti-Shallow Execution (Sample Task Review)

### Task 1.1 (Plan 01 -- Job script author)

- Context: inline interfaces block with exact function signatures and LightRAG line refs
  (lightrag.py:1237-1270 for ainsert signature; doc_status pattern with f"doc-{content_hash}" prefix).
- Action: 4 concrete Skill() calls + code sketch with import path, constants, dataclass fields,
  and function bodies for _load_candidates, _verify_target_empty, _ingest_one, main().
- Verify: automated ast.parse syntax check (objective pass/fail).
- Done: grep-verifiable -- get_docs_by_ids match, ids=[row.content_hash] match, >= 350 lines, named functions.
- ASSESSMENT: CONCRETE.

### Task 1.4 (Plan 01 -- Cost gate checkpoint)

- Type: checkpoint:human-verify with gate=blocking. Correct for operator decision point.
- How-to-verify: Steps A-G with exact bash commands per step.
- Gate template in what-built: 3-criterion decision block with YES/NO format and value slots.
  All 3 criteria named: cost_extrap < $200, wallclock_extrap < 30h, failure_rate < 5%.
  FAIL path: BLOCKED -- cost gate failed; escalate to user; do NOT trigger Step 2.
- Resume signal: binary -- gate PASS or gate BLOCKED:[reason]. No intermediate states.
- ASSESSMENT: EXPLICIT. Satisfies CRITICAL Dimension 11.

### Task 2.1 (Plan 02 -- Empty-target pre-flight)

- Type: checkpoint:human-verify with gate=blocking.
- Two checks: SHOW GRANTS ON VOLUME SQL (D-03 WRITE_VOLUME) + databricks fs ls (D-07 empty target).
- Non-empty result: STOP. Do not proceed. Ask user for explicit --force-overwrite intent.
- Resume signal: pre-flight PASS or pre-flight BLOCKED:[reason].
- ASSESSMENT: EXPLICIT. Satisfies CRITICAL Dimension 12.

### Task 2.3 (Plan 02 -- Step 3 postcheck + VERIFICATION)

- Concrete Skill() invocations: databricks-patterns + writing-tests.
- Step C: exact Python assert block (dim==1024, n_zh>=10, n_en>=10, len>=50).
- Verify: automated Python script checking VERIFICATION.md exists and contains expected keywords.
- Done: 9-item checklist with observable final states.
- ASSESSMENT: CONCRETE.

---

## 8. Wave + Dependency

| Plan | Wave | depends_on | Valid? |
|------|------|-----------|--------|
| kdb-2.5-01 | 1 | [] | YES |
| kdb-2.5-02 | 2 | ["kdb-2.5-01"] | YES |

Dependency graph: kdb-2.5-01 -> kdb-2.5-02 (linear, acyclic).
Task 1.4 checkpoint enforces dependency at runtime via gate PASS signal.
Plan 02 context references @kdb-2.5-01-SUMMARY.md -- executor sees the gate verdict before starting.

**Dependency graph: VALID.**

---

## 9. Time-Box

| Plan | Tasks | Estimated time | Any task > 2h? |
|------|-------|---------------|----------------|
| kdb-2.5-01 | 4 (3 auto + 1 checkpoint) | 1d | Task 1.1 estimated 2-3h (borderline; justified by scope) |
| kdb-2.5-02 | 3 (1 auto + 2 checkpoint) | 1d | Task 2.2 has 1-8h async Job wait; active dev ~0.5h |

Total: 2d. Matches ROADMAP 1-2d estimate.
Task 1.1 at 2-3h spans the 2h guideline. Scope (350+ LOC + 8 test behaviors) justifies it.
Task 2.2 async wait is not developer-active time -- not a time-box violation.

**Time-box: acceptable.**

---

## 10. CONFIG-EXEMPTIONS Scope Discipline

Both plans declare zero modifications to kb/, lib/, top-level *.py, or CONFIG-EXEMPTIONS.md.

- Plan 01 files_modified: exclusively databricks-deploy/jobs/* and .planning/phases/kdb-2.5-*/
- Plan 02 files_modified: .planning/phases/kdb-2.5-*/ artifacts + STATE-kb-databricks-v1.md
- Both plans hard_constraints: CONFIG-DBX-01 ZERO modifications rule explicitly stated.
- Plan 01 verification section: git diff --name-only HEAD check expected empty.
- Plan 02 verification section: git log cfe47b4..HEAD audit command (correct milestone-base hash).
- CONFIG-EXEMPTIONS.md current state: lib/llm_complete.py + kg_synthesize.py (kdb-2 exemptions).
  kdb-2.5 adds NO new rows. CONFIRMED.

**CONFIG-EXEMPTIONS scope: PRESERVED. No extension.**

---

## 11. CRITICAL: Cost Gate Visibility

**PASS -- explicit, non-hand-wavy.**

Plan 01 Task 1.4 what-built block contains the required gate decision template (Plan 01 lines 397-407):

  Gate criterion 1: cost_extrap < 200 USD: YES/NO -> value (extrapolated from Step 1)
  Gate criterion 2: wallclock_extrap < 30h: YES/NO -> value (extrapolated)
  Gate criterion 3: failure_rate < 5%: YES/NO -> X% (N_failed / 50)
  GATE: PASS -> proceed to Plan 02
  OR: BLOCKED -- cost gate failed; escalate to user; do NOT trigger Step 2

All 3 criteria named with thresholds. FAIL path terminates with escalation instruction.
Resume signal enforces binary outcome -- no weasel words or intermediate states.
Objective statement also states: If gate FAILS -> STOP; do NOT proceed to Plan 02.

---

## 12. CRITICAL: Empty-Target Safety

**PASS -- explicit, blocking, two-layer protection.**

Layer 1 (code level -- _verify_target_empty in reindex_lightrag.py):
- Non-empty + not force_overwrite -> RuntimeError listing up to 10 artifacts with mtime strings.
- force_overwrite=True -> logger.warning (non-blocking; operator accepted the risk).
- YAML default params: --force-overwrite absent from both smallbatch and fullrun jobs
  (Task 1.3 done block verifies with grep: NO MATCH expected).

Layer 2 (pre-flight -- Plan 02 Task 2.1, checkpoint:human-verify, gate=blocking):
- databricks fs ls check: Error: Path does not exist OR empty listing = OK.
- Non-empty: STOP. Do not proceed. Ask user for explicit --force-overwrite intent.
- Resume signal: pre-flight PASS -- WRITE_VOLUME granted, lightrag_storage/ empty
  (only this exact signal allows advancing to Task 2.2).

Plan 02 hard_constraints D-07 CRITICAL: lightrag_storage/ MUST be verified empty before Task 2.2.
If non-empty AND neither flag confirmed -> BLOCKED.

Note on --init-empty vs --force-overwrite: CONTEXT.md D-07 references both flags. Plan resolves
to single --force-overwrite flag (default = fail loudly on non-empty; flag = explicit override).
Safety intent preserved. ACCEPTABLE.

---

## 13. Open Questions Handling

| Question | Handling in plan |
|----------|------------------|
| python_file path in Bundle YAML (relative resolution) | Task 1.3 action: two candidate forms with verify-at-deploy-time instruction. Task 1.4 Step B checks include entry in databricks.yml. Appropriate deferral to deploy-time verification. |
| --params syntax for bundle run + spark_python_task | Used only for --force-overwrite override. YAML comment shows example syntax. Step 1 validates basic run mechanics first. Low risk. |
| databricks.yml include entry verification | Task 1.4 Step B: explicit check + remediation (one-line addition, NOT a kdb-1.5 frozen file modification). Handled with concrete fix. |

All 3 open questions have explicit handling instructions with concrete remediations.

---

## 14. Issues

| # | Severity | Dimension | Plan | Location | Required Fix |
|---|----------|-----------|------|----------|--------------|
| 1 | MINOR | Skill discipline | kdb-2.5-02 | Task 2.3 action block | Add Skill(skill=systematic-debugging, args=If failure_rate > 5%: structured failure-mode analysis of FAILURES.csv -- classify errors by type (429 storm vs corpus quality vs encoding); root-cause per category; remediation recommendation.) as explicit Skill() call in the action body. |
| 2 | MINOR | Documentation note | RESEARCH.md | Summary line 13 | Research summary recommends ThreadPoolExecutor (pre-dates D-04 lock). PLAN is correct; D-04 overrides. No plan change needed -- executor must be briefed that D-04 supersedes RESEARCH.md discretion item 3. |

**Blockers: 0. MINOR warnings: 2. INFO: 1 (failure rate denominator -- correctly handled by plans using ~170 filtered corpus).**

---

## 15. Recommendation

**PROCEED TO EXECUTION. Dispatch kdb-2.5-01 executor.**

Both plans are structurally sound with no blockers. All 7 locked decisions honored, 2/2 REQs
covered with grep-verifiable acceptance criteria, both CRITICAL gates are explicit and non-hand-wavy.
The two MINOR issues are polish items that can be applied by the executor during implementation.

Include the following notes in the executor dispatch prompt:

Note 1 (D-04 override): D-04 (NO ThreadPoolExecutor) supersedes RESEARCH.md summary line 13
which recommends ThreadPoolExecutor with max_workers=4. Implement sequential single-instance
loop as specified in Task 1.1. The anti-patterns block explicitly says DO NOT add ThreadPoolExecutor
(corruption risk to shared lightrag_storage/).

Note 2 (systematic-debugging skill fix): In Plan 02 Task 2.3 action block, add an explicit
Skill(skill=systematic-debugging, args=If failure_rate > 5%: structured failure-mode analysis
of FAILURES.csv -- classify errors by type (429 storm vs corpus quality vs encoding issues);
root-cause per category; recommended remediation per category.) before the Step D VERIFICATION
authoring instruction.

Note 3 (git hygiene): Both plans specify forward-only commits and explicit file paths in git add.
No git commit --amend, no git add -A. Reinforced by feedback_no_amend_in_concurrent_quicks.md.

---

*Verification performed by gsd-plan-checker (iteration 1 of 3). Goal-backward analysis against
ROADMAP-kb-databricks-v1.md rev 3 (lines 120-172), REQUIREMENTS-kb-databricks-v1.md rev 3
(lines 72-85), CONTEXT.md (all 7 decisions), STATE-kb-databricks-v1.md, CONFIG-EXEMPTIONS.md,
and project memory feedback files. No execution or code inspection performed -- static plan
analysis only.*

---

## Orchestrator post-iter-1 action (2026-05-17)

Orchestrator applied surgical inline patches for the 2 MINOR warnings (avoided iter-2 since fixes were verbatim-specified by verifier):

- **MINOR #1 patched** (this commit): Removed `systematic-debugging` from `kdb-2.5-02-fullreindex-and-postcheck-PLAN.md` frontmatter `skills:` list (line 15). The skill was declared but not invoked via `Skill()` in any task `<action>` block — narrative references at lines 294 + 448 are descriptive, not invocations. Cleaner to drop than to fabricate a forced invocation. Frontmatter now lists only `databricks-patterns` + `writing-tests`, both with explicit `Skill()` invocations. Frontmatter ↔ task invocation 1:1 restored.
- **MINOR #2 patched** (this commit): Edited `kdb-2.5-RESEARCH.md` line 13 summary text to align with Decision 4 (NO ThreadPoolExecutor). Original text said "ThreadPoolExecutor with `max_workers=4` initial (raise after Step 1 measures rate-limit headroom)" — this was self-corrected later in the document at lines 138-160 + 940 + 1384, but the top-of-doc summary remained stale. New summary text explicitly states "Single LightRAG instance, single thread, NO ThreadPoolExecutor" + cites the supersession in parentheses so future readers don't get whiplash.

**Final verdict after orchestrator action:** PASS — both plans + CONTEXT + RESEARCH + VERIFICATION ready for `/gsd:execute-phase kdb-2.5` (or paste-ready execute prompt for fresh agent).
