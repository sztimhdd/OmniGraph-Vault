---
phase: 06-graphify-addon-code-graph
plan: 03b
type: execute
wave: 4
depends_on:
  - "06-03"
  - "06-02"
files_modified:
  - skills/omnigraph_query/SKILL.md
autonomous: true
requirements:
  - REQ-03
  - REQ-04

must_haves:
  truths:
    - "`venv/Scripts/python skill_runner.py skills/omnigraph_search --validate` exits 0 (REQ-03 green)"
    - "`venv/Scripts/python skill_runner.py skills/omnigraph_search --test-file tests/skills/test_omnigraph_search.json` exits 0 and all 8 test cases print PASS (REQ-04 routing green)"
    - "Live LightRAG smoke: either local `python -m omnigraph_search.query` returns non-empty output (if local storage populated), or remote SSH smoke returns non-empty output (06-02 guarantees remote graph exists)"
    - "omnigraph_query and omnigraph_search disambiguate bidirectionally — `skills/omnigraph_query/SKILL.md` now references `omnigraph_search` in at least the frontmatter, body 'When NOT to Use', and 'Related Skills' sections"
  artifacts:
    - path: "skills/omnigraph_query/SKILL.md"
      provides: "Updated with cross-reference to omnigraph_search in description frontmatter, 'When NOT to Use' bullet, and 'Related Skills'"
      contains: "omnigraph_search"
  key_links:
    - from: "skills/omnigraph_query/SKILL.md"
      to: "skills/omnigraph_search/SKILL.md"
      via: "description + body mentions of omnigraph_search for disambiguation"
      pattern: "omnigraph_search"
    - from: "tests/skills/test_omnigraph_search.json"
      to: "skill_runner.py"
      via: "Gemini-backed routing test against SKILL.md body"
      pattern: "skill_runner\\.py.*omnigraph_search"
---

<objective>
Complete the `omnigraph_search` skill rollout by: (a) adding the back-reference/disambiguation edit to `skills/omnigraph_query/SKILL.md` so Hermes routes both directions correctly, and (b) running the three-tier validation (skill_runner --validate, skill_runner --test-file, live LightRAG smoke). This plan depends on both 06-03 (the skill files themselves) and 06-02 (the seeded remote code graph — which also implies the remote domain graph has already been exercised in prior phases, so the remote live smoke path is reliable).

Purpose: REQ-03 green (skill validates) + REQ-04 green (live LightRAG call returns data). This is the final gate before Phase 6 demo runs (Plan 05).

Output: Surgical edit to `skills/omnigraph_query/SKILL.md` (additions only) + captured validation + smoke-test output for the SUMMARY.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/06-graphify-addon-code-graph/06-RESEARCH.md
@.planning/phases/06-graphify-addon-code-graph/06-VALIDATION.md
@.planning/phases/06-graphify-addon-code-graph/06-03-SUMMARY.md
@.planning/phases/06-graphify-addon-code-graph/06-02-SUMMARY.md
@skills/omnigraph_query/SKILL.md
@skills/omnigraph_search/SKILL.md
@tests/skills/test_omnigraph_search.json
@skill_runner.py

<interfaces>
<!-- skill_runner.py CLI flags (from the existing tool in repo root) -->
<!-- Always run with the venv python on Windows: venv/Scripts/python -->

skill_runner.py <skill_dir> --validate
  → exits 0 if SKILL.md frontmatter well-formed; else prints validation errors and exits 1

skill_runner.py <skill_dir> --test-file <json_path>
  → runs each test case; prints PASS/FAIL per case; exits 0 only if ALL pass

python -m omnigraph_search.query "<question>"
  → live LightRAG hybrid-mode call; requires GEMINI_API_KEY + populated lightrag_storage
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 3.5: Add cross-reference to omnigraph_query SKILL.md (disambiguation both directions)</name>
  <files>skills/omnigraph_query/SKILL.md</files>
  <read_first>
    - skills/omnigraph_query/SKILL.md (current "Do NOT use when" section — we add ONE clause; do NOT rewrite the file)
    - .planning/phases/06-graphify-addon-code-graph/06-RESEARCH.md §Pitfall 7 (both skills must cross-reference; current omnigraph_query SKILL.md does not mention omnigraph_search)
  </read_first>
  <action>
    In `skills/omnigraph_query/SKILL.md`, add ONE line to the "Do NOT use this skill when:" paragraph in the `description:` frontmatter block, and ONE bullet to the "## When NOT to Use" body section. Touch nothing else. This is a surgical edit per the HIGHEST PRIORITY PRINCIPLES.

    **Frontmatter description edit:** Locate the existing line starting with "Do NOT use this skill when:" (around line 16 of current file). After the existing clause ending "use `omnigraph_manage`." add:

    ```
      Do NOT use when the user wants raw entity-attributed retrieval without synthesis —
      use `omnigraph_search` instead (same backend, simpler output, no synthesis).
    ```

    **Body edit:** In the "## When NOT to Use" section, add this bullet immediately after the existing "User wants to delete entities or manage the graph → use `omnigraph_manage` instead" bullet:

    ```
    - User wants raw entity-attributed retrieval without long-form synthesis → use `omnigraph_search` instead
    ```

    In the "## Related Skills" section, add:

    ```
    - For raw entity-attributed retrieval without synthesis: `omnigraph_search`
    ```

    Do NOT change any other content, formatting, capitalization, or whitespace in the file.
  </action>
  <verify>
    <automated>grep -q "omnigraph_search" skills/omnigraph_query/SKILL.md && grep -c "omnigraph_search" skills/omnigraph_query/SKILL.md | awk '{exit !($1 >= 3)}'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "omnigraph_search" skills/omnigraph_query/SKILL.md` exits 0
    - `grep -c "omnigraph_search" skills/omnigraph_query/SKILL.md` returns >= 3 (frontmatter + body + related skills)
    - `git diff skills/omnigraph_query/SKILL.md` shows ONLY additions — no deletions of existing content (check via `git diff --stat skills/omnigraph_query/SKILL.md` — deletions count should be 0 except possibly the lines right above where inserts happen if they were modified in-place)
    - `grep -c "omnigraph_ingest" skills/omnigraph_query/SKILL.md` — MUST remain unchanged relative to pre-edit (surgical check: existing cross-refs to other skills should not be touched)
  </acceptance_criteria>
  <done>omnigraph_query SKILL.md now cross-references omnigraph_search; surgical edit verified.</done>
</task>

<task type="auto">
  <name>Task 3.6: Run skill_runner validate + test-file + live smoke test (local + remote)</name>
  <files>(none — this task runs tests and captures output; no code edits)</files>
  <read_first>
    - skill_runner.py (to understand CLI flags — at least `--validate` and `--test-file`)
    - tests/skills/test_omnigraph_search.json (from Plan 06-03 Task 3.1)
    - .planning/phases/06-graphify-addon-code-graph/06-02-SUMMARY.md (confirms remote graph.json seeded)
    - ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_ssh.md (SSH details for remote smoke test — do NOT commit)
  </read_first>
  <action>
    Run the three-step verification against the now-populated skill. Step 1 + Step 2 are blocking local validation. Step 3 has both a local-only path and a remote-only path and records the status of each.

    **Step 1 — Structural validation (local, blocking):**
    ```
    venv/Scripts/python skill_runner.py skills/omnigraph_search --validate
    ```
    Must exit 0. This confirms SKILL.md frontmatter is well-formed.

    **Step 2 — Routing tests (local, Gemini-backed, blocking):**
    ```
    venv/Scripts/python skill_runner.py skills/omnigraph_search --test-file tests/skills/test_omnigraph_search.json
    ```
    Must exit 0. All 8 test cases must print PASS. If any fail, diagnose whether (a) the SKILL.md body needs clearer routing text, (b) the test case is too ambiguous, or (c) Gemini quota was the issue (retry). Do NOT weaken the tests to make them pass — fix the SKILL.md body.

    **Step 3a — Local live smoke (conditional, cross-platform — no `/tmp/` redirects):**
    Use a Git-Bash-compatible pipeline (works on Windows and Linux without temp files):
    ```
    if [ -d "$HOME/.hermes/omonigraph-vault/lightrag_storage" ] && [ -n "$(ls -A "$HOME/.hermes/omonigraph-vault/lightrag_storage" 2>/dev/null)" ]; then
      venv/Scripts/python -m omnigraph_search.query "what is LightRAG?" 2>&1 | head -1 | grep -v '^$'
      LOCAL_SMOKE_EXIT=$?
      echo "LOCAL_SMOKE_EXIT=$LOCAL_SMOKE_EXIT"
    else
      echo "LOCAL_SMOKE_EXIT=SKIPPED (lightrag_storage empty or missing)"
    fi
    ```
    Pass condition: either `LOCAL_SMOKE_EXIT=0` (first stdout line is non-empty) OR `LOCAL_SMOKE_EXIT=SKIPPED` (with reason recorded in SUMMARY).

    **Step 3b — Remote live smoke (required — 06-02 seeded the graph):**
    ```
    ssh <remote> "cd ~/OmniGraph-Vault && venv/bin/python -m omnigraph_search.query 'what is LightRAG?' 2>&1 | head -1 | grep -v '^$'"
    REMOTE_SMOKE_EXIT=$?
    ```
    Pass condition: `REMOTE_SMOKE_EXIT=0` AND the captured first line is non-empty.

    Note: the remote repo must have the 06-03 changes pulled first. If the remote is behind, orchestrator does `ssh <remote> "cd ~/OmniGraph-Vault && git pull --ff-only"` before running the smoke test. Do not echo any SSH credential into committed logs — capture only the query output.

    Capture all four command outputs for the SUMMARY. Sanitize: remove hostname/port/username before committing.
  </action>
  <verify>
    <automated>venv/Scripts/python skill_runner.py skills/omnigraph_search --validate && venv/Scripts/python skill_runner.py skills/omnigraph_search --test-file tests/skills/test_omnigraph_search.json</automated>
  </verify>
  <acceptance_criteria>
    - `venv/Scripts/python skill_runner.py skills/omnigraph_search --validate` exits 0
    - `venv/Scripts/python skill_runner.py skills/omnigraph_search --test-file tests/skills/test_omnigraph_search.json` exits 0 and prints "PASS" for all 8 test cases (check: `skill_runner.py ... 2>&1 | grep -c PASS` returns >= 8)
    - Local live smoke: if `~/.hermes/omonigraph-vault/lightrag_storage/` exists AND is non-empty (has files), then `venv/Scripts/python -m omnigraph_search.query "what is LightRAG?"` exits 0 AND produces non-empty stdout (first line non-empty). If local storage is empty, mark local smoke SKIPPED with reason in SUMMARY.
    - Remote live smoke (06-02 completed so remote graph exists): `ssh remote "cd ~/OmniGraph-Vault && venv/bin/python -m omnigraph_search.query 'what is LightRAG?'"` exits 0 AND produces non-empty stdout.
    - No `/tmp/` temp-file redirects are used (pipeline-only pattern works on Windows Git Bash + Linux)
    - SUMMARY records the first 200 chars of both local (or SKIPPED reason) and remote smoke outputs, sanitized
  </acceptance_criteria>
  <done>REQ-03 + REQ-04 green: skill_runner validate + test-file pass; at least the remote live smoke returns a non-empty response.</done>
</task>

</tasks>

<verification>
- REQ-03: `skill_runner.py --validate` exits 0
- REQ-04: `skill_runner.py --test-file ...` all 8 cases PASS AND remote live smoke returns non-empty output (plus local if storage populated)
- Disambiguation: both omnigraph_search and omnigraph_query SKILL.md files now cross-reference each other
- No collateral damage: `kg_synthesize.py`, `query_lightrag.py`, `config.py` not modified
</verification>

<success_criteria>
- skill_runner validate + tests all green
- Remote live smoke returns a non-empty response (local smoke is PASS or SKIPPED with reason)
- omnigraph_query.SKILL.md edit is surgical (git diff shows only additions)
</success_criteria>

<output>
After completion, create `.planning/phases/06-graphify-addon-code-graph/06-03b-SUMMARY.md` with:
- skill_runner --validate output (pass/fail)
- skill_runner --test-file output summary (per-case PASS/FAIL + any failure diagnosis)
- Local smoke result: PASS (first 200 chars of stdout) OR SKIPPED (reason)
- Remote smoke result: PASS (first 200 chars of stdout) AND confirmation that remote repo was pulled to include 06-03 changes before the smoke
- Git diff stat for `skills/omnigraph_query/SKILL.md` (additions-only confirmation)
</output>
</content>
</invoke>