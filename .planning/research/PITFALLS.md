# Domain Pitfalls: Hermes Skill Packaging for a Python KB Pipeline

**Project:** OmniGraph-Vault — Phase 2 (Skill Packaging + Gate 6/7)
**Domain:** Hermes Agent skill packaging over a multi-script Python knowledge-base pipeline
**Researched:** 2026-04-21
**Confidence:** HIGH for in-repo evidence (codebase analysis, CONCERNS.md, existing SKILL.md files);
MEDIUM for Hermes-specific runtime conventions (inferred from CLAUDE.md, which was synthesized from
official skill writing guides by the project author — treat as authoritative proxy)

---

## Critical Pitfalls

Mistakes that cause rewrites, hard-to-debug failures, or silent wrong behaviour.

---

### Pitfall 1: Hardcoded Developer Paths Survive Into Skill Scripts

**What goes wrong:** Python scripts called by the skill contain `/home/sztimhdd/` absolute paths.
When Hermes executes the skill on a different machine (or even a different user account on the
same Windows machine via WSL vs native path), every path-dependent call silently fails or crashes
with `FileNotFoundError`. The agent receives an error exit, but the error message is useless
because it names a path that doesn't exist on the running system.

**Why it happens:** Phase 1 development on a single machine never required portability. Paths were
hardcoded as a shortcut. Now that skill scripts invoke those same Python files, the assumption
propagates through the execution chain.

**Files already known to be affected (from CONCERNS.md):**
- `ingest_wechat.py` lines 279, 280, 368 — entity buffer path
- `kg_synthesize.py` line 50 — canonical map path
- `cognee_batch_processor.py` lines 9, 30, 35, 36
- `cognee_wrapper.py` line 8
- `init_cognee.py` lines 5, 23
- `list_entities.py` line 5
- `query_lightrag.py` line 12
- All `tests/verify_gate_*.py` files

**Consequences:**
- Skill passes `skill_runner.py --validate` (structure check) but fails silently at runtime
- Gate 7 passes locally on the original machine but breaks on any other machine
- `skill_runner.py` LLM tests pass (they only test the LLM response, not script execution)

**Prevention:**
1. Before writing any skill scripts, fix ALL hardcoded paths to use `config.py` constants.
   Add `ENTITY_BUFFER_DIR` and `CANONICAL_MAP_FILE` to `config.py`. Import from there everywhere.
2. Skill wrapper scripts must set `PROJECT_ROOT` from their own location:
   ```bash
   PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
   cd "$PROJECT_ROOT"
   python ingest_wechat.py "$@"
   ```
3. Test the skill by moving the working directory before running — paths that break on `cd` reveal
   every hardcoded assumption.

**Detection:** Run `grep -r '/home/' skills/ scripts/` and `grep -r '/home/' *.py`. Any hit is a
blocker before publishing.

---

### Pitfall 2: Trigger Phrase Collisions Between Skills

**What goes wrong:** Hermes matches user intent to a skill using both the frontmatter `triggers`
list and the Level-0 `description`. When two skills have semantically overlapping triggers, the
agent fires the wrong one. The user says "summarize what I know about X" and gets `omnigraph_ingest`
instead of `omnigraph_query` or `omnigraph_synthesize`. No error is surfaced — the wrong skill runs
and produces a confusing response.

**Why it happens:** Trigger phrases are written independently per skill. Overlap creeps in because
natural language phrasing is ambiguous. The current `omnigraph_ingest` triggers include
`"save this article"`. The current `omnigraph_query` triggers include `"search my knowledge base"`.
But `"search"` can also feel like retrieval-then-summarise, which is closer to `omnigraph_synthesize`.

**Specific collision risks in the current trigger set:**

| Phrase | Intended Skill | Collision Risk |
|--------|---------------|----------------|
| `"what do I know about"` | `omnigraph_query` | Also sounds like `omnigraph_synthesize` |
| `"search my kb"` | `omnigraph_query` | "search" in Chinese-context can mean "find and report" |
| `"ingest"` | `omnigraph_ingest` | Bare word, could fire on "ingest this report" meaning read-it |
| `"save this article"` | `omnigraph_ingest` | "save" could mean save the output of a query |
| `"find in graph"` | `omnigraph_query` | Matches accidentally if user says "find and delete from graph" |

**Future collision risk:** Once `omnigraph_synthesize` and `omnigraph_status` are added, the phrase
`"summarize what I know"` will compete between `omnigraph_query` and `omnigraph_synthesize` depending
on how their triggers and descriptions are written.

**Consequences:**
- Wrong skill fires, user gets an unexpected prompt or action
- Destructive skills (`omnigraph_manage`) firing when user intended a query — the most dangerous case
- Gate 7 trigger-phrase tests can pass locally on `skill_runner.py` (which loads one skill at a time)
  but fail on real Hermes (which resolves across the full catalog)

**Prevention:**
1. Write the `description` field for Level-0 matching with the precision of a mutex. It is the
   primary disambiguation signal. Bad: `"Query the knowledge graph"`. Good: `"Retrieve and answer
   a question from ingested articles — does NOT ingest new content"`.
2. Enumerate "when NOT to trigger" cases in SKILL.md explicitly for every overlapping phrase. The
   existing skills do this correctly (they already list redirects). Maintain this discipline for all
   future skills.
3. Before adding any new trigger phrase, check whether it appears verbatim or semantically in any
   other skill's triggers list or description.
4. Gate 7 test cases must include cross-skill routing tests: send a phrase that is ambiguous between
   two skills and assert only one skill name appears in the response. The existing test suites already
   do this for ingest vs query — extend this pattern to all skill pairs.

**Detection:** Review all `triggers` lists side-by-side. Run `skill_runner.py` with a phrase that
sits on the boundary between two skills and check which skill name the LLM proposes.

---

### Pitfall 3: Environment Variable Pre-flight Failures Are Opaque from the Hermes Side

**What goes wrong:** The skill runs, the Python script is invoked, but `GEMINI_API_KEY` is not in
the shell environment that Hermes uses to exec the skill. The script dies with a Python traceback.
Hermes receives stderr output and displays it as a generic error. The user sees a wall of Python
traceback instead of `"⚠️ Configuration error: GEMINI_API_KEY is not set. Please add it to
~/.hermes/.env and restart."` as specified in the skill decision tree.

**Why it happens:** The skill decision trees check for missing env vars and specify clean error
messages. But those checks are in the SKILL.md instructions to the LLM — not in the shell scripts
that actually invoke Python. The Python scripts fail before the LLM can intercept. The LLM only
sees what the agent surfaces back to it, and a raw traceback from a subprocess does not match
the `expect_contains: ["GEMINI_API_KEY", ".env"]` pattern the tests verify.

**Three distinct failure modes:**

1. **Missing key entirely**: `~/.hermes/.env` not present or key not in it. Python crashes with
   `KeyError` or `AssertionError` depending on where validation happens.
2. **Key present in `.env` but not exported to subprocess env**: The wrapper script sources `.env`
   but uses `source` syntax that doesn't propagate to child processes, or uses `export` on the
   wrong variable name.
3. **Cognee-specific vars not set**: `LLM_PROVIDER`, `LLM_MODEL`, `EMBEDDING_PROVIDER` are
   hardcoded in each script that uses Cognee, but `config.py` doesn't validate them. Cognee silently
   misconfigures, then fails with a cryptic API error much later in execution.

**Consequences:**
- `skill_runner.py` test cases for "config error" pass (the LLM correctly describes what to do in
  response to the hypothetical scenario) but the actual skill wrapper doesn't perform the pre-flight
  check before invoking Python.
- The user sees a traceback. The agent tries to interpret it. The interpretation is usually wrong.

**Prevention:**
1. Perform env pre-flight in the shell wrapper script, before invoking Python:
   ```bash
   if [ -z "$GEMINI_API_KEY" ]; then
     echo "⚠️ Configuration error: GEMINI_API_KEY is not set. Add it to ~/.hermes/.env and restart."
     exit 1
   fi
   ```
   This is the only reliable way to guarantee the clean error format the SKILL.md specifies.
2. Add `assert os.environ.get("GEMINI_API_KEY"), "GEMINI_API_KEY must be set"` at the top of
   `config.py` — not in individual scripts.
3. The `metadata.openclaw.requires.config: ["GEMINI_API_KEY"]` frontmatter field signals to
   OpenClaw/Hermes to check this before loading the skill — verify whether Hermes actually enforces
   this pre-check or only surfaces it to the agent as advisory text.

**Detection:** Remove `GEMINI_API_KEY` from the environment, run the skill wrapper script directly
from a plain shell (not from within `skill_runner.py`), observe what the agent receives.

---

### Pitfall 4: `skill_runner.py` LLM Tests Give False Passes for Script Execution Issues

**What goes wrong:** `skill_runner.py` tests whether the LLM correctly follows the SKILL.md
decision tree. It does not execute the Python scripts. A test case that says "ingest this URL" and
`expect_contains: ["ingest_wechat.py"]` passes as long as the LLM outputs the text `ingest_wechat.py`
in its response. It does not verify that `ingest_wechat.py` actually ran, succeeded, or produced
correct output.

**Why it matters:** This creates a gap class of failures that `skill_runner.py` will never catch:
- Hardcoded paths that break on the current machine
- Missing `import json` in `kg_synthesize.py` (the known bug from CONCERNS.md line 55)
- `ingest_pdf()` undefined variable crashes (CONCERNS.md lines 89-99)
- Subprocess timeout or hang with no output
- `canonical_map.json` absent on first run causing a crash in `kg_synthesize.py`

**Consequences:**
- Gate 7 says "PASS" on all `skill_runner.py` tests. Developer ships the skill. First real use on
  Hermes fails silently because the Python script crashes before producing output.
- The `missing json import` bug in `kg_synthesize.py` only manifests after the first article has
  been ingested (when `canonical_map.json` gets created). Gate 6 single-article ingestion doesn't
  trigger it. Cross-article Gate 6 query will trigger it. So Gate 7 can pass while Gate 6 is still
  broken.

**Prevention:**
1. Gate 7 must include a live execution test, not just an LLM response test. The test flow:
   a. Run the skill wrapper script directly from shell against a real (or mock) URL
   b. Assert exit code 0
   c. Assert output contains expected confirmation text
   d. Assert LightRAG storage was actually written to
2. Fix the known `import json` bug in `kg_synthesize.py` before Gate 6 cross-article synthesis.
3. Fix `ingest_pdf()` undefined variable scope bugs before any PDF skill is declared working.
4. Keep `skill_runner.py` tests for what they are good at: LLM routing correctness and output
   format. Do not conflate "LLM routing test passed" with "skill works end-to-end."

**Detection:** After `skill_runner.py` passes all tests, run `python kg_synthesize.py "test query"
hybrid` from a shell with `canonical_map.json` present. If it crashes, the skill is not ready.

---

### Pitfall 5: Subprocess CWD Mismatch Breaks Relative Script Calls

**What goes wrong:** The SKILL.md decision tree shows `python ingest_wechat.py "<URL>"` as the
command to run. This assumes `cwd` is the project root. When Hermes executes a skill, its working
directory may be the skill directory, the Hermes data directory, or the OS home directory —
not the project root. `python ingest_wechat.py` then fails with `ModuleNotFoundError` or
`FileNotFoundError` because `config.py` (imported at the top of `ingest_wechat.py`) cannot be found
relative to that cwd.

**Why it happens:** During local testing, the developer runs `python ingest_wechat.py` from the
project root. `skill_runner.py` also runs from the project root. Neither surface the cwd problem.
Real Hermes execution is the first context where cwd is something unexpected.

**Consequences:**
- Every Python invocation in every skill wrapper silently fails on first deploy to real Hermes.
- Error message is `ModuleNotFoundError: No module named 'config'` or similar — not useful.

**Prevention:**
1. Shell wrapper scripts must `cd` to an absolute project root before invoking Python:
   ```bash
   SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
   PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
   cd "$PROJECT_ROOT"
   python ingest_wechat.py "$@"
   ```
2. Consider making all Python scripts importable from any cwd by using `sys.path` manipulation
   in `config.py`, but the shell-wrapper `cd` is simpler and more reliable.
3. Verify by running `skill wrapper script` from `/tmp` before declaring Gate 7 complete.

---

### Pitfall 6: Missing `import json` Causes Silent Post-Ingestion Failure in kg_synthesize.py

**What goes wrong:** `kg_synthesize.py` calls `json.load(f)` at line 54 to read `canonical_map.json`,
but `import json` is not present in the file (confirmed in CONCERNS.md line 55). On the first run
after ingestion, `canonical_map.json` is created. The next call to `kg_synthesize.py` crashes with
`NameError: name 'json' is not defined`. This is silent from the Hermes side — the agent receives
a non-zero exit code and a Python traceback.

**Why it matters for Gate 6 specifically:** Gate 6 requires ingesting 3 articles then running a
cross-article synthesis query. The cross-article query is the first call to `kg_synthesize.py` after
`canonical_map.json` has been written. Gate 6 will fail at this exact step unless the bug is fixed
first.

**Prevention:** Add `import json` to `kg_synthesize.py` before running Gate 6. This is a one-line
fix but a Gate 6 blocker.

**Detection:** `python -c "import py_compile; py_compile.compile('kg_synthesize.py')"` will pass
(syntax is valid). The bug only manifests at runtime when the conditional branch at line 54 is
reached. Verify with: `python kg_synthesize.py "test" hybrid` after creating a minimal
`canonical_map.json` with `{}`.

---

## Moderate Pitfalls

Mistakes that degrade functionality without causing a complete failure.

---

### Pitfall 7: SKILL.md Bloat Degrades Agent Decision Quality

**What goes wrong:** As SKILL.md grows (more cases added, more error scenarios documented, mode
tables expanded), the agent's ability to follow the decision tree degrades. At Level 1 loading,
the full SKILL.md body is in context. Long skills push out earlier decision branches from the
effective attention window. The agent correctly recalls the last few cases but "forgets" earlier
ones, most often the "when NOT to trigger" redirects.

**Why it happens:** Progressive feature additions each feel small. Each error case, each query mode
explanation, each output format rule is individually justified. The cumulative effect is a 3-5KB
skill body that is longer than the attention bandwidth of the LLM for precise instruction-following.

**Current state:** Both `omnigraph_ingest/SKILL.md` (92 lines) and `omnigraph_query/SKILL.md`
(102 lines) are at the acceptable boundary. The query skill's "Query modes explained" table is the
most at-risk section — it is informational but not decision-critical, and adds ~15 lines that
compete with the routing logic for attention.

**Prevention:**
1. SKILL.md hard ceiling: 80 lines of body (after frontmatter). Above that, move content to
   `references/`.
2. Move the "Query modes explained" table to `references/query-modes.md`. Reference it explicitly
   in the skill body: "See references/query-modes.md for when to use each mode."
3. Decision tree branches (when to trigger / when not to trigger / error handling) must always
   appear before informational content. Agents read top-down and stop when they have enough
   information to act.
4. Write one test case specifically for recall of an early "when NOT to trigger" branch after
   reading a long input that exercises many sections of the skill.

**Detection:** Send a test input that triggers an early "when NOT to trigger" redirect after also
matching a later section's pattern. If the agent routes correctly, attention is sufficient.

---

### Pitfall 8: Gate 6 Cross-Article Tests Produce False Passes

**What goes wrong:** Gate 6 tests cross-article synthesis by ingesting 3 articles and querying for
a topic that spans them. The test "passes" if the synthesis output contains any content. But the
output could be:
- A response that draws only from the most recently ingested article (LightRAG recency bias)
- A Gemini-hallucinated answer that is confident but not grounded in the graph
- A correct answer that uses only local-mode retrieval even when hybrid was specified

**Why it happens:** `kg_synthesize.py` defaults to `"naive"` mode (CONCERNS.md line 222) unless
the caller explicitly passes `"hybrid"`. The skill always passes `"hybrid"`, but if a developer
runs the gate test directly (`python kg_synthesize.py "test" `), it silently uses naive mode and
appears to work.

**Specific Gate 6 risks:**
- All 3 articles must be about topics that can be cross-linked. If 2 of 3 are unrelated, a
  superficially coherent response may not actually require cross-document retrieval.
- `canonical_map.json` may not exist yet (blocking the json load), or may be empty (no
  canonicalization has run), making the cross-article entity linking invisible in the response.
- The image server (port 8765) must be running for report image URLs to resolve. If it is not,
  the synthesis output is technically correct but the rendered report is broken.

**Prevention:**
1. Choose 3 Gate 6 articles that share specific named entities (e.g., all 3 mention "LightRAG"
   or a specific concept). The cross-article query must ask about that entity explicitly.
2. The expected output must contain a specific string that can only come from cross-document
   retrieval — not something Gemini could hallucinate from the query text alone.
3. Run `cognee_batch_processor.py` after ingesting all 3 articles and before running the synthesis
   query. Verify `canonical_map.json` is non-empty. Only then run the cross-article query.
4. Verify the default mode is `"hybrid"` in `kg_synthesize.py` before Gate 6. Fix the default
   from `"naive"` (current) to `"hybrid"`.

---

### Pitfall 9: Bare `except` Clauses Hide Skill Execution Failures

**What goes wrong:** `cognee_wrapper.py` (line 94) and `ingest_wechat.py` (line 158) have bare
`except: pass` clauses (confirmed in CONCERNS.md lines 67-83). When these are hit during skill
execution, the script continues, exits with code 0, and the skill reports success. The agent tells
the user ingestion is complete. But Cognee silently dropped the entity buffer, and the knowledge
graph is partially populated.

**Why it matters for skills specifically:** Skills interpret exit code 0 as success. A script that
silently swallowed a `cognee.remember()` error looks identical to a script that succeeded. The
user's next query finds no Cognee memory context and gets a degraded synthesis. No error, no
indication of why.

**Prevention:**
1. Replace `except: pass` with `except Exception as e: logger.warning("cognee.remember failed: %s", e)`.
   The script can still continue (Cognee is non-blocking by design), but the failure is logged.
2. Skill output should include a line like `[Cognee memory: OK]` or `[Cognee memory: degraded — check logs]`
   so the agent can surface it to the user.
3. Before Gate 7, run the skill against a scenario where Cognee is unreachable. Confirm the
   skill reports degraded (not success) and exits with a non-zero code if the primary operation
   (LightRAG insert) also failed.

---

### Pitfall 10: Windows-Specific Path Separators in Skill Wrapper Scripts

**What goes wrong:** The project is Windows-primary (see PROJECT.md: "Platform: Windows-primary").
Shell wrapper scripts written with Unix path assumptions (`/` separators, `~` expansion, `source`)
fail when Hermes execs them on Windows via Git Bash, PowerShell, or cmd.exe depending on the shell
Hermes uses internally.

**Specific risks:**
- `source ~/.hermes/.env` expands `~` correctly in Bash but not in PowerShell/cmd
- `export VAR=value` is Bash syntax; PowerShell uses `$env:VAR = "value"`
- `cd ~/.hermes/omonigraph-vault` fails if Hermes uses a Windows-native shell
- `python` resolves to system Python, not the venv Python, unless the venv is explicitly activated

**Why it happens:** `skill_runner.py` is run from Git Bash and works fine. The actual Hermes
exec environment is never tested separately.

**Prevention:**
1. Test all shell wrapper scripts explicitly from both Git Bash and PowerShell before Gate 7.
2. Use Python scripts as wrappers instead of shell scripts when portability is required:
   ```python
   # scripts/run-ingest.py
   import subprocess, sys, os
   from pathlib import Path
   project_root = Path(__file__).parent.parent.parent
   env = os.environ.copy()
   subprocess.run([sys.executable, str(project_root / "ingest_wechat.py"), sys.argv[1]], env=env, check=True)
   ```
3. The venv Python path differs on Windows (`.venv/Scripts/python.exe`) vs Linux/macOS
   (`.venv/bin/python`). Do not hardcode the venv path; use `sys.executable` if already inside
   the venv, or detect the platform.

---

### Pitfall 11: Cognee Batch Processor Not Running Before Cross-Article Query

**What goes wrong:** `canonical_map.json` is written by `cognee_batch_processor.py`, which runs
separately and asynchronously. If Gate 6 ingests 3 articles and immediately queries without waiting
for the batch processor to complete, `canonical_map.json` either does not exist or contains entities
from only the most recently processed batch. Cross-article entity linking via canonical names fails
silently — the query runs against non-canonical entity names and produces poorer results.

**Prevention:**
1. The skill decision tree for `omnigraph_ingest` should note: "Entity canonicalization runs via
   `cognee_batch_processor.py` which must be run separately. For best cross-article query results,
   run the batch processor before querying."
2. Gate 6 procedure must explicitly include: run batch processor, wait for completion, verify
   `canonical_map.json` is updated, then run synthesis query.
3. Consider adding a `--wait-for-batch` flag to `kg_synthesize.py` that polls for pending
   entity_buffer files before querying.

---

## Minor Pitfalls

Nuisances that slow development but do not cause data loss or wrong answers.

---

### Pitfall 12: `skill_runner.py --validate` Does Not Check Frontmatter Consistency

**What goes wrong:** `validate_skill()` in `skill_runner.py` checks for `name` and `description`
presence and validates that referenced files exist. It does not check that `triggers` phrases
in frontmatter are not duplicated across skills, and does not validate that `requires.config`
names match the actual env var names used in the SKILL.md body.

**Example:** A trigger phrase added to `omnigraph_synthesize` that duplicates one in `omnigraph_query`
will pass validation. The collision only manifests on real Hermes.

**Prevention:** Add a cross-skill validation mode: `python skill_runner.py skills/ --validate --test-all`
should also check for trigger phrase overlap across all loaded skills.

---

### Pitfall 13: `test_omnigraph_query.json` "Empty Result" Test Has a False Pass Condition

**What goes wrong:** The test case `"what do I know about quantum computing chip fabrication methods?"`
has `expect_contains: ["omnigraph_ingest"]`. It passes as long as the LLM mentions `omnigraph_ingest`
somewhere in its response. But it does not verify that `kg_synthesize.py` was NOT called, or that
the response format is correct (no hallucinated content about quantum computing). The LLM could
run the query AND mention `omnigraph_ingest` as a follow-up suggestion, which would pass the test
but represent the wrong behaviour.

**Prevention:** Add `expect_not_contains: ["kg_synthesize.py"]` to this test case. The correct
behaviour is to NOT run the query, just redirect to ingest.

---

### Pitfall 14: `synthesis_output.md` Path in SKILL.md Is Inconsistent With `omonigraph-vault` Typo

**What goes wrong:** `omnigraph_query/SKILL.md` line 94 states:
`"The synthesized report is also saved to ~/.hermes/omonigraph-vault/synthesis_output.md."`
This path uses the correct `omonigraph-vault` spelling (with the typo preserved, as per convention).
If a future developer "fixes" the typo in `config.py` without also updating the SKILL.md body,
the SKILL.md will reference the wrong path. Users following the path manually will not find
the file.

**Prevention:** Keep a single source of truth: the path in SKILL.md should reference the
env var `OMNIGRAPH_DATA_DIR` rather than a hardcoded path, for the same reason the Python scripts
should use `config.py` constants. Alternatively, add a comment in `config.py` next to the typo
constant saying "also referenced in skills/omnigraph_query/SKILL.md — update together."

---

## Phase-Specific Warnings

| Phase / Gate | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Gate 6: 3-article ingest | Missing `import json` crashes kg_synthesize.py | Fix before Gate 6 runs |
| Gate 6: cross-article synthesis | Batch processor not run; canonical_map.json empty | Gate procedure must include batch processor step |
| Gate 6: default mode is "naive" | Synthesis uses wrong retrieval mode | Change default to "hybrid" in kg_synthesize.py |
| Gate 7: skill_runner.py pass | False confidence; scripts not executed | Add shell-level execution tests |
| Gate 7: real Hermes deploy | CWD mismatch breaks every Python call | Test scripts from /tmp before deploying |
| Gate 7: real Hermes deploy | GEMINI_API_KEY not in Hermes shell env | Pre-flight check in wrapper, not just in SKILL.md instructions |
| Gate 7: Windows shell | Path separators, venv activation | Test wrappers from PowerShell AND Git Bash |
| omnigraph_synthesize (future) | Trigger collision with omnigraph_query | Write description as explicit mutex from the start |
| omnigraph_manage (future) | Guard clause bypassed by ambiguous phrasing | Every destructive action needs exact-match confirmation phrase |

---

## Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Hardcoded paths pitfall | HIGH | Directly confirmed in CONCERNS.md with specific file/line evidence |
| Missing `import json` | HIGH | Directly confirmed in CONCERNS.md line 55 |
| Trigger collision analysis | MEDIUM | Based on SKILL.md analysis + Hermes matching model behavior (inferred) |
| Env var pre-flight failure modes | MEDIUM | Inferred from codebase structure; exact Hermes exec environment not verified |
| skill_runner false pass analysis | HIGH | Verified by reading skill_runner.py source — it tests LLM output, not script execution |
| Windows path pitfalls | MEDIUM | PROJECT.md confirms Windows-primary; exact Hermes shell not verified |
| Gate 6 false pass conditions | HIGH | Based on CONCERNS.md default mode bug + batch processor timing evidence |
| SKILL.md bloat attention degradation | LOW | General LLM behavior; not Hermes-specific evidence available |

---

## Sources

- `c:/Users/huxxha/Desktop/OmniGraph-Vault/.planning/codebase/CONCERNS.md` — primary evidence for
  bugs, hardcoded paths, bare except clauses, missing imports (HIGH confidence, direct codebase analysis)
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/skills/omnigraph_ingest/SKILL.md` — trigger phrase analysis
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/skills/omnigraph_query/SKILL.md` — trigger phrase analysis, synthesis_output.md path
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/skill_runner.py` — test architecture analysis (false pass risk)
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/tests/skills/test_omnigraph_ingest.json` — existing test coverage gaps
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/tests/skills/test_omnigraph_query.json` — false pass risk in empty-result test
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/.planning/PROJECT.md` — platform constraint (Windows-primary)
- `c:/Users/huxxha/Desktop/OmniGraph-Vault/CLAUDE.md` — Hermes skill writing standards (synthesized from official docs by project author)
