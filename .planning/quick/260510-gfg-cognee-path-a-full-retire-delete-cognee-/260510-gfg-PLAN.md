---
phase: 260510-gfg-cognee-path-a
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  # ── Commit 1: production code retirement ──
  - cognee_wrapper.py                                      # DELETE (entire file)
  - cognee_batch_processor.py                              # DELETE (entire file)
  - init_cognee.py                                         # DELETE (entire file)
  - setup_cognee.py                                        # DELETE (entire file)
  - tests/integration/test_cognee_rotation.py              # DELETE (entire file)
  - tests/unit/test_cognee_remember_detaches.py            # DELETE (entire file)
  - tests/unit/test_cognee_vertex_model_name.py            # DELETE (entire file)
  - tests/unit/test_ingest_wechat_cognee_gate.py           # DELETE (entire file)
  - tests/verify_gate_a.py                                 # DELETE (entire file)
  - tests/verify_gate_b.py                                 # DELETE (entire file)
  - tests/verify_gate_c.py                                 # DELETE (entire file)
  - ingest_wechat.py                                       # EDIT — drop import + _cognee_inline_enabled() + gated block
  - query_lightrag.py                                      # EDIT — drop import + log_query_pattern() call
  - lib/api_keys.py                                        # EDIT — drop refresh_cognee() + cognee docstring refs
  - lib/__init__.py                                        # EDIT — drop refresh_cognee re-export from import + __all__
  - lib/checkpoint.py                                      # EDIT — rewrite 2 comment-only refs (no functional change)
  - lib/llm_deepseek.py                                    # EDIT — rewrite 1 comment-only ref (no functional change)
  - batch_ingest_github.py                                 # EDIT — drop cognee github URL from repo list
  - requirements.txt                                       # EDIT — drop `cognee` line
  - tests/integration/test_checkpoint_resume_e2e.py        # EDIT — strip cognee assertions/imports only
  - tests/unit/test_api_keys.py                            # EDIT — strip refresh_cognee tests only
  - tests/unit/test_checkpoint_ingest_integration.py       # EDIT — strip cognee assertions/imports only
  - tests/unit/test_kol_scan_db_path_override.py           # EDIT — strip cognee assertions/imports only
  - tests/unit/test_query_history.py                       # EDIT — strip cognee assertions/imports only
  - tests/unit/test_text_first_ingest.py                   # EDIT — strip cognee assertions/imports only
  # ── Commit 2: docs ──
  - CLAUDE.md                                              # EDIT — env var table + Architecture + Lessons + Common Commands + Tech Stack
  - Deploy.md                                              # EDIT — refresh_cognee mention
  - README.md                                              # EDIT — directory listing entries (L189 + L340)
  - .planning/REQUIREMENTS.md                              # EDIT — COG-01/02/03 → RETIRED + AGNT-MEM-01 placeholder
  - .planning/PROJECT-Agentic-RAG-v1.md                    # EDIT — Out-of-scope row
  # ── Commit 3: STATE ──
  - .planning/STATE.md                                     # EDIT — append quick 260510-gfg row to Quick Tasks Completed
autonomous: true
requirements:
  - COG-01    # transition Complete → RETIRED with retirement commit hash
  - COG-02    # transition Complete → RETIRED with retirement commit hash
  - COG-03    # transition Pending → RETIRED (was the gate-removal req; now subsumed by full retirement)

must_haves:
  truths:
    - "No production *.py file (excluding scripts/cognee_diag/ + tests/) imports `cognee` or `cognee_wrapper` after Commit 1"
    - "No production *.py file calls `cognee.remember()`, `cognee.search()`, `cognee.cognify()`, or `refresh_cognee()` after Commit 1"
    - "`python -c 'import ingest_wechat; import query_lightrag; import lib'` succeeds with `DEEPSEEK_API_KEY=dummy` (no ImportError, no AttributeError on cognee_wrapper)"
    - "Pytest baseline (excluding deleted cognee tests) is GREEN — count = pre-retire-baseline minus deleted-cognee-test-count"
    - "`scripts/local_e2e.sh` dry-run-equivalent (`kol --max-articles 1 --dry-run` or `wechat <fixture> --dry-run`) reaches first network/scrape attempt without raising ImportError on cognee"
    - "REQUIREMENTS.md COG-01/02/03 status changed to RETIRED with the Commit 1 SHA cited"
    - "PROJECT-Agentic-RAG-v1.md Out-of-scope row for Cognee updated to reflect 2026-05-10 retirement"
    - "STATE.md Quick Tasks Completed table contains the 260510-gfg row with all 3 commit SHAs"
  artifacts:
    - path: ".scratch/cognee-retire-pre-grep.log"
      provides: "Pre-state inventory (already produced upstream — locks the edit list)"
      contains: "==production *.py refs"
    - path: ".scratch/cognee-retire-post-grep.log"
      provides: "Post-Commit-1 grep proving zero production *.py functional refs remain"
      contains: "0 functional refs"
    - path: ".scratch/cognee-retire-import-smoke.log"
      provides: "Import smoke proving deleted-module references are all rewired"
      contains: "import smoke: all OK"
    - path: ".scratch/cognee-retire-pytest-pre.log"
      provides: "Pre-Commit-1 pytest baseline (with cognee tests still present)"
      contains: "passed"
    - path: ".scratch/cognee-retire-pytest-post.log"
      provides: "Post-Commit-1 pytest baseline (cognee tests deleted, expected count = pre minus deleted-test-count)"
      contains: "passed"
    - path: ".scratch/cognee-retire-dryrun.log"
      provides: "local_e2e.sh dry-run smoke proving the ingest path imports cleanly without cognee"
      contains: "EXIT=0"
  key_links:
    - from: "ingest_wechat.py"
      to: "cognee_wrapper (DELETED)"
      via: "previously `import cognee_wrapper` at L57; previously `cognee_wrapper.remember_article(...)` at L1221"
      pattern: "must NOT match `import cognee` or `cognee_wrapper\\.` after Commit 1"
    - from: "query_lightrag.py"
      to: "cognee_wrapper (DELETED)"
      via: "previously `import cognee_wrapper` at L2; previously `cognee_wrapper.log_query_pattern(...)` at L44"
      pattern: "must NOT match `import cognee` or `cognee_wrapper\\.` after Commit 1"
    - from: "lib/__init__.py"
      to: "lib.api_keys.refresh_cognee (DELETED)"
      via: "previously re-exported `refresh_cognee` at L27 + L50"
      pattern: "must NOT match `refresh_cognee` after Commit 1"
    - from: ".planning/REQUIREMENTS.md (Traceability table)"
      to: "Commit 1 SHA"
      via: "Status column transitions to RETIRED with SHA cited"
      pattern: "COG-0[123]\\s*\\|\\s*Phase 20\\s*\\|\\s*RETIRED"
---

<objective>
Retire Cognee from the OmniGraph-Vault repository as dead code. Path A per quick 260509-syd's INVESTIGATION.md (Discovery 4: inline writes are CURRENTLY DEAD WRITES, no readers). This is dead-code removal, not feature removal. Output is 3 atomic forward-only commits + .scratch evidence + REQUIREMENTS/PROJECT/STATE updates.

Purpose: Eliminate ~600 LOC + 1 unused dependency (`cognee` package), close COG-01/02/03 as RETIRED, and unblock the Agentic-RAG-v1 milestone (memory layer, if needed, will be designed inside ar-* phase, not bolted on via dead Cognee path).

Output:
- 3 atomic commits with bodies citing real .scratch/ log paths (anti-fabrication contract)
- `.scratch/cognee-retire-{pre-grep,post-grep,import-smoke,pytest-pre,pytest-post,dryrun}.log` evidence trail
- Production `*.py` files free of all functional Cognee refs (only kept: `scripts/cognee_diag/` audit-trail + `.planning/quick/260509-syd-*` investigation + planning-history references in committed `.planning/quick/260503-v9z-*` / `260504-lt2-*` PLANs/SUMMARYs which document past states and must not be edited)
- `requirements.txt` shrunk by 1 line (cognee package retired)
- REQUIREMENTS.md COG-01/02/03 status → RETIRED, AGNT-MEM-01 placeholder added
- PROJECT-Agentic-RAG-v1.md Out-of-scope Cognee row updated
- STATE.md Quick Tasks Completed table contains 260510-gfg row
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/PROJECT-Agentic-RAG-v1.md
@CLAUDE.md
@.planning/quick/260509-syd-cognee-root-cause-investigation-422-not-/INVESTIGATION.md
@.scratch/cognee-retire-pre-grep.log

<interfaces>
<!-- Pre-grep evidence is the contract. Executor MUST treat .scratch/cognee-retire-pre-grep.log -->
<!-- as the locked edit list. No discovery — every file edited / deleted is on that list. -->
<!-- Any file outside the list that the executor "feels" needs editing → STOP and report. -->

Edit list — DELETE entirely (11 files):
  cognee_wrapper.py
  cognee_batch_processor.py
  init_cognee.py
  setup_cognee.py
  tests/integration/test_cognee_rotation.py
  tests/unit/test_cognee_remember_detaches.py
  tests/unit/test_cognee_vertex_model_name.py
  tests/unit/test_ingest_wechat_cognee_gate.py
  tests/verify_gate_a.py
  tests/verify_gate_b.py
  tests/verify_gate_c.py

Edit list — TRIM cognee refs (8 production + 6 test files = 14 files):
  Production:
    ingest_wechat.py            (L57 import; L847-860 _cognee_inline_enabled() def; L1215-1228 gated inline call)
    query_lightrag.py           (L2 import; L44 log_query_pattern call — DELETE call entirely, query path doesn't need it)
    lib/api_keys.py             (L4-7 docstring; L92-94 docstring; L159-174 refresh_cognee() function)
    lib/__init__.py             (L27 refresh_cognee, in import list; L50 "refresh_cognee", in __all__)
    lib/checkpoint.py           (L7 + L84 — comment-only "cognee_batch_processor.py" mentions; rewrite to drop cognee or generic phrasing)
    lib/llm_deepseek.py         (L50 — comment "Mirrors cognee_wrapper.py's pattern"; rewrite to drop cognee mention)
    batch_ingest_github.py      (L41 — "https://github.com/topoteretes/cognee" entry in repo list; DELETE the line)
    requirements.txt            (L6 — `cognee` package; DELETE the line)
  Tests (mixed — strip cognee assertions/imports/test functions ONLY, keep the rest):
    tests/integration/test_checkpoint_resume_e2e.py
    tests/unit/test_api_keys.py
    tests/unit/test_checkpoint_ingest_integration.py
    tests/unit/test_kol_scan_db_path_override.py
    tests/unit/test_query_history.py
    tests/unit/test_text_first_ingest.py

Edit list — DOCS (Commit 2):
  CLAUDE.md            (lines per pre-grep: 61, 63, 83, 91, 94, 104, 107-108, 178, 186, 188, 196, 209, 211, 217, 240, 456, 644, 646, 654, 664, 712, 731, 733, 767, 781, 795, 797, 801-802, 811, 817, 829, 835, 850, 856, 863)
  Deploy.md            (L67 — `cognee_batch_processor.run_batch()` mention; rewrite as retired)
  README.md            (L189 + L340 — directory listing entries; remove)
  .planning/REQUIREMENTS.md   (lines 67-75 narrative + 130-132 traceability table; transition to RETIRED + add AGNT-MEM-01 placeholder)
  .planning/PROJECT-Agentic-RAG-v1.md  (L87 — Out-of-scope Cognee row; rewrite per scope_constraints)

Edit list — STATE (Commit 3):
  .planning/STATE.md   (Quick Tasks Completed table — append 260510-gfg row after 260509-s29 row at L276)

NEVER MODIFY:
  scripts/cognee_diag/* (audit trail of investigation 260509-syd)
  .planning/quick/260509-syd-*/* (investigation artifacts)
  .planning/quick/260503-v9z-*/* (history; mentions cognee in past-state context)
  .planning/quick/260504-lt2-*/* (history; cognee_batch_processor.py was a real file at the time)
  Any file under ~/.hermes/
  lib/article_filter.py (user-locked per scope)
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Commit 1 — production code retirement (DELETE 4 production scripts + 7 cognee-only tests; EDIT 8 production refs + 6 mixed tests + requirements.txt)</name>
  <files>
    cognee_wrapper.py, cognee_batch_processor.py, init_cognee.py, setup_cognee.py,
    tests/integration/test_cognee_rotation.py, tests/unit/test_cognee_remember_detaches.py,
    tests/unit/test_cognee_vertex_model_name.py, tests/unit/test_ingest_wechat_cognee_gate.py,
    tests/verify_gate_a.py, tests/verify_gate_b.py, tests/verify_gate_c.py,
    ingest_wechat.py, query_lightrag.py, lib/api_keys.py, lib/__init__.py,
    lib/checkpoint.py, lib/llm_deepseek.py, batch_ingest_github.py, requirements.txt,
    tests/integration/test_checkpoint_resume_e2e.py, tests/unit/test_api_keys.py,
    tests/unit/test_checkpoint_ingest_integration.py, tests/unit/test_kol_scan_db_path_override.py,
    tests/unit/test_query_history.py, tests/unit/test_text_first_ingest.py
  </files>
  <action>
    **Step 0 — capture pre-state pytest baseline FIRST** (do NOT skip; this is the anti-fabrication anchor):
    ```bash
    cd C:/Users/huxxha/Desktop/OmniGraph-Vault
    DEEPSEEK_API_KEY=dummy GEMINI_API_KEY=dummy .venv/Scripts/python -m pytest tests/ -q 2>&1 | tee .scratch/cognee-retire-pytest-pre.log
    ```
    Record the pre-retire pytest pass count from the last line (e.g. `45 passed`). This is the baseline for the post-retire delta check.

    **Step 1 — DELETE 11 entire files** (use `git rm`):
    ```bash
    git rm cognee_wrapper.py cognee_batch_processor.py init_cognee.py setup_cognee.py \
      tests/integration/test_cognee_rotation.py \
      tests/unit/test_cognee_remember_detaches.py \
      tests/unit/test_cognee_vertex_model_name.py \
      tests/unit/test_ingest_wechat_cognee_gate.py \
      tests/verify_gate_a.py tests/verify_gate_b.py tests/verify_gate_c.py
    ```

    **Step 2 — EDIT production refs** (per pre-grep line numbers; preserve surrounding code untouched per CLAUDE.md surgical principle):

    1. `ingest_wechat.py`:
       - L57: delete `import cognee_wrapper`
       - L847-860: delete the entire `_cognee_inline_enabled()` function definition + its docstring
       - L1215-1228: delete the entire gated block including the `if _cognee_inline_enabled():` line and its body (the `await cognee_wrapper.remember_article(...)` call). Replace with NOTHING — surrounding code path was already correct without it (Wave 0 of milestone removed Cognee from synthesis path; inline was a dead write per quick 260509-syd Discovery 4).

    2. `query_lightrag.py`:
       - L2: delete `import cognee_wrapper`
       - L44: delete the entire line `await cognee_wrapper.log_query_pattern(query_text, "hybrid", True)` (per scope_constraints: query path doesn't need it; this is dead-write removal). Preserve the `try:`/`except:` structure — if removing the line leaves an empty try block, also remove the try/except wrapper.

    3. `lib/api_keys.py`:
       - L4-7 docstring lines mentioning cognee — rewrite to drop cognee mention while preserving file-level docstring purpose
       - L92-94 docstring lines mentioning `refresh_cognee()` — drop those lines
       - L159-174: delete the entire `refresh_cognee()` function definition + its docstring + its try/except body

    4. `lib/__init__.py`:
       - L27: remove `refresh_cognee,` from the multi-line import statement (preserve the rest of the import)
       - L50: remove `"refresh_cognee",` from the `__all__` tuple/list

    5. `lib/checkpoint.py`:
       - L7: comment mentions `cognee_batch_processor.py` — rewrite to generic "atomic-write pattern" or drop the cognee reference
       - L84: comment mentions `cognee_batch_processor.py os.rename pattern` — rewrite to "atomic os.replace pattern" (no functional change)

    6. `lib/llm_deepseek.py`:
       - L50: comment `Mirrors cognee_wrapper.py's pattern` — rewrite to drop cognee mention while preserving the comment's intent (e.g., "Mirrors the same import-time env var capture pattern used elsewhere")

    7. `batch_ingest_github.py`:
       - L41: delete the line `"https://github.com/topoteretes/cognee",` from the URL list. Preserve trailing commas on adjacent entries (verify the list is still syntactically valid Python after the deletion).

    8. `requirements.txt`:
       - L6: delete the `cognee` line entirely

    **Step 3 — EDIT mixed test files** (strip cognee-only test functions, imports, and assertions; keep all non-cognee test logic):

    For each of the 6 mixed test files, do this in order:
    a. Open file. Grep for `cognee` (case-insensitive).
    b. For each match, classify:
       - Import line (`from cognee_wrapper import ...`, `import cognee`, `from lib import refresh_cognee` etc.) → DELETE
       - Test function whose primary purpose is exercising cognee (`def test_cognee_*`, `def test_refresh_cognee_*`) → DELETE entire function
       - Assertion or fixture mentioning cognee but inside a test that primarily covers something else → DELETE just the lines mentioning cognee, preserving the test's primary assertions
       - Module-level docstring or comment mentioning cognee → rewrite to drop the cognee reference
    c. After edit, re-grep for `cognee` in the file. Should return 0 lines (no residual references).

    Specific known cases (executor confirms via grep before editing):
    - `tests/unit/test_api_keys.py`: likely has `test_refresh_cognee_*` test functions — delete them; KEEP all other `test_*` functions (rotate_key etc.)
    - `tests/integration/test_checkpoint_resume_e2e.py`: likely imports `cognee_batch_processor` for atomic-write fixture — replace with direct `os.replace` calls or drop the cognee-batch-processor reference if the test now covers checkpoint atomic-writes via `lib/checkpoint.py` directly
    - `tests/unit/test_checkpoint_ingest_integration.py`: same pattern
    - `tests/unit/test_kol_scan_db_path_override.py`: per quick 260504-lt2-SUMMARY, has a `cognee_batch_processor.py:41 DB_PATH env override` test — DELETE that test function entirely (the file it tests is now deleted)
    - `tests/unit/test_query_history.py`: likely tests `cognee_wrapper.log_query_pattern` — DELETE those tests
    - `tests/unit/test_text_first_ingest.py`: likely has a cognee-gate fixture — strip the cognee-gate setup, preserve the text-first-ingest assertions

    If after editing a test file all test functions are gone, the file becomes empty (or has only imports). In that case, DELETE the file with `git rm` and add it to the deletion list in the commit body.

    **Step 4 — Validation gate (POST-grep)**:
    ```bash
    git ls-files '*.py' | grep -v '^scripts/cognee_diag/' | grep -v '^\\.planning/quick/260509-syd' | grep -v '^tests/' | xargs grep -l -i 'cognee\\|refresh_cognee' 2>&1 | tee .scratch/cognee-retire-post-grep.log
    ```
    EXPECT: empty result (0 production *.py files outside cognee_diag still reference cognee). If any file appears, STOP and re-trim it.

    Then re-grep with `grep -n` to surface comment-only refs:
    ```bash
    git ls-files '*.py' | grep -v '^scripts/cognee_diag/' | grep -v '^\\.planning/quick/260509-syd' | xargs grep -n -i 'cognee\\|refresh_cognee' 2>&1 | tee -a .scratch/cognee-retire-post-grep.log
    ```
    EXPECT: any remaining matches are inside `tests/` files that legitimately retain other purposes — count must be ≤ 0 functional refs (only comment/string-literal refs allowed if they're docstring history). If functional `import cognee` or `cognee.<method>(` calls survive, STOP.

    **Step 5 — Validation gate (import smoke)**:
    ```bash
    DEEPSEEK_API_KEY=dummy GEMINI_API_KEY=dummy .venv/Scripts/python -c "
    import ingest_wechat
    import query_lightrag
    import lib
    import lib.api_keys
    import lib.checkpoint
    import lib.llm_deepseek
    import batch_ingest_github
    print('import smoke: all OK')
    " 2>&1 | tee .scratch/cognee-retire-import-smoke.log
    ```
    EXPECT: `import smoke: all OK` on the last line. If any ImportError mentions cognee or `refresh_cognee`, STOP.

    **Step 6 — Validation gate (post-retire pytest)**:
    ```bash
    DEEPSEEK_API_KEY=dummy GEMINI_API_KEY=dummy .venv/Scripts/python -m pytest tests/ -q 2>&1 | tee .scratch/cognee-retire-pytest-post.log
    ```
    EXPECT: post-pass-count == pre-pass-count − (number of cognee-test functions deleted in Steps 1+3). The expected delta is documented in the commit body. NO unexpected failures (failures must trace 1:1 to cognee path or be pre-existing baseline fails per CLAUDE.md "260509-p1n" Lesson — list any pre-existing baseline fails by name in commit body).

    **Step 7 — Validation gate (local-e2e dry-run)**:
    ```bash
    bash scripts/local_e2e.sh kol --max-articles 1 --dry-run 2>&1 | tee .scratch/cognee-retire-dryrun.log
    echo "EXIT=$?" >> .scratch/cognee-retire-dryrun.log
    ```
    EXPECT: `EXIT=0` and no `ImportError`/`AttributeError`/`ModuleNotFoundError` mentioning cognee. The script may exit early due to corp-network blocks or schema drift (per CLAUDE.md "local harness is NOT a full e2e validator") — that is acceptable. The gate is purely "did the import phase complete cleanly without cognee".

    **Step 8 — Atomic forward-only commit** (NO stash, NO reset, NO rebase, NO amend, NO force-push per CLAUDE.md Lessons-Learned 2026-05-06 #5):
    ```bash
    git pull --ff-only origin main
    git add -A    # CAUTION: scope is locked by the edit list above; verify with `git status` first
    git status    # human/agent confirms ONLY the listed files appear; if anything else, RESET that path with `git checkout -- <path>` (NOT `git reset`)
    git commit -m "$(cat <<'EOF'
refactor(cognee-260510-gfg): retire cognee_wrapper + cognee_batch_processor + rewire callers

Path A (full retirement) per quick 260509-syd INVESTIGATION.md Discovery 4: inline
Cognee writes are CURRENTLY DEAD WRITES (no readers). Wave 0 of milestone
already removed Cognee from synthesis path (kg_synthesize.py:41-44); this commit
removes the dead writers + the wrapper module + the standalone batch processor.

Deleted (11 files):
- cognee_wrapper.py, cognee_batch_processor.py, init_cognee.py, setup_cognee.py
- tests/integration/test_cognee_rotation.py
- tests/unit/test_cognee_{remember_detaches,vertex_model_name}.py
- tests/unit/test_ingest_wechat_cognee_gate.py
- tests/verify_gate_{a,b,c}.py

Edited (production):
- ingest_wechat.py: drop import + _cognee_inline_enabled() + gated inline block
- query_lightrag.py: drop import + log_query_pattern() call (dead write)
- lib/api_keys.py: drop refresh_cognee() function + cognee docstring refs
- lib/__init__.py: drop refresh_cognee re-export from import + __all__
- lib/checkpoint.py, lib/llm_deepseek.py: rewrite comment-only cognee refs
- batch_ingest_github.py: drop topoteretes/cognee URL from repo list
- requirements.txt: drop cognee package

Edited (tests, cognee assertions/imports stripped only):
- tests/integration/test_checkpoint_resume_e2e.py
- tests/unit/test_{api_keys,checkpoint_ingest_integration,kol_scan_db_path_override,query_history,text_first_ingest}.py

Validation evidence:
- pre-grep: .scratch/cognee-retire-pre-grep.log (309 lines, locked the edit list)
- post-grep: .scratch/cognee-retire-post-grep.log (0 functional refs in production *.py)
- import smoke: .scratch/cognee-retire-import-smoke.log (import smoke: all OK)
- pytest pre/post: .scratch/cognee-retire-pytest-{pre,post}.log (delta == deleted cognee tests, no unexpected failures)
- local-e2e dry-run: .scratch/cognee-retire-dryrun.log (EXIT=0, no cognee ImportError)

Closes COG-01/02/03 as RETIRED. AGNT-MEM-01 placeholder added in REQUIREMENTS.md
in the docs commit; episodic memory layer (if needed) will be designed inside ar-*.

No SSH to Hermes. No ~/.hermes/ edits. No stash/reset/rebase/amend/force-push.
EOF
)"
    git rev-parse HEAD    # capture COMMIT-1-SHA for use in Commit 2 (REQUIREMENTS.md citations)
    ```

    Save COMMIT-1-SHA to a local variable for Commit 2.
  </action>
  <verify>
    <automated>
    DEEPSEEK_API_KEY=dummy GEMINI_API_KEY=dummy .venv/Scripts/python -c "import ingest_wechat; import query_lightrag; import lib; import lib.api_keys; print('OK')" \
    && grep -L 'cognee\|refresh_cognee' cognee_wrapper.py cognee_batch_processor.py 2>&1 | grep -q 'No such file' \
    && DEEPSEEK_API_KEY=dummy GEMINI_API_KEY=dummy .venv/Scripts/python -m pytest tests/ -q --no-header 2>&1 | tail -3
    </automated>
  </verify>
  <done>
    - 11 cognee-only files deleted via `git rm`
    - 14 files edited (8 production + 6 mixed-test + requirements.txt; checkpoint.py + llm_deepseek.py only had comment changes)
    - `.scratch/cognee-retire-{pre-grep,post-grep,import-smoke,pytest-pre,pytest-post,dryrun}.log` all populated
    - post-grep shows 0 functional `import cognee` / `cognee.<x>(` / `refresh_cognee` references in production *.py outside scripts/cognee_diag/
    - import smoke prints `import smoke: all OK`
    - post-pytest pass count == pre-pytest pass count − (deleted cognee test count); no unexpected failures
    - local-e2e dry-run EXIT=0 with no cognee-related ImportError
    - Commit 1 created on origin/main with body citing all 5 evidence log paths
    - COMMIT-1-SHA captured for Commit 2 REQUIREMENTS.md citations
  </done>
</task>

<task type="auto">
  <name>Task 2: Commit 2 — docs (CLAUDE.md, Deploy.md, README.md, REQUIREMENTS.md COG status, PROJECT-Agentic-RAG-v1.md Out-of-scope)</name>
  <files>
    CLAUDE.md, Deploy.md, README.md,
    .planning/REQUIREMENTS.md, .planning/PROJECT-Agentic-RAG-v1.md
  </files>
  <action>
    Use COMMIT-1-SHA captured at the end of Task 1.

    **Step 1 — CLAUDE.md edits** (per pre-grep line numbers — read each section first, do surgical edit per CLAUDE.md "Surgical Changes" principle):

    Lines to edit (from `.scratch/cognee-retire-pre-grep.log` lines 90-126):
    - L61: project summary "enriched with **Cognee** async memory" → drop "enriched with **Cognee** async memory" phrase, keep "ingests web content (...) into a **LightRAG** knowledge graph, then exposes that graph as agent skills"
    - L63: tech stack "LightRAG (KG engine), Cognee (memory layer)" → "LightRAG (KG engine)"
    - L83: `python -c "import cognee; print('Cognee OK')"` → DELETE this line
    - L91: comment `# Query with Cognee memory context` → rewrite to `# Query with optional memory context` or drop the line entirely (the synthesize command itself stays)
    - L94: comment `# Direct LightRAG query (no Cognee, for debugging)` → simplify to `# Direct LightRAG query (for debugging)`
    - L104: `python cognee_batch_processor.py` line + its surrounding comment → DELETE the line + comment
    - L107-108: `python tests/verify_gate_a.py # Cognee remember()` etc. → DELETE all 3 verify_gate_*.py lines
    - L178: "Entity canonicalization runs **async and decoupled** via `cognee_batch_processor.py`, which polls `entity_buffer/` and writes to `canonical_map.json` atomically" → rewrite as "Entity canonicalization is no longer performed; canonical_map.json is no longer maintained" OR delete the entire paragraph if it now stands alone
    - L186: query/synthesis flow line `cognee_wrapper.recall_previous_context() → past query memory` → DELETE this branch of the flow diagram
    - L188: `cognee_wrapper.remember_synthesis() → store for future recall` → DELETE this branch of the flow diagram
    - L196: "**Cognee** — wrapped by `cognee_wrapper.py` (provides `remember_synthesis()`, ...). Batch processing in `cognee_batch_processor.py`. Must be configured ..." → DELETE the entire **Cognee** integration paragraph
    - L209: env var table row `OMNIGRAPH_COGNEE_INLINE` → DELETE the entire row
    - L211: "Cognee-specific vars (`LLM_PROVIDER`, `EMBEDDING_PROVIDER`, etc.) are hardcoded in each script that uses Cognee." → DELETE the sentence
    - L217: "**Standalone Cognee rotation caveat (Hermes FLAG 1):** ..." paragraph → DELETE the entire paragraph
    - L240: "**Cognee is async** — never block the ingestion fast-path on any Cognee operation" bullet → DELETE the bullet
    - L456 (Lessons Learned): "Cognee batch operations silently drop entities ..." bullet → DELETE the bullet
    - L644: "Cognee requires Python 3.12 venv per wrapper" constraint → rewrite to drop cognee mention or DELETE the bullet
    - L646: "Stack: Python 3.11+, LightRAG, Cognee, Gemini 2.5 ..." → "Stack: Python 3.11+, LightRAG, Gemini 2.5 ..."
    - L654: "Python 3.12 - Virtual environment target (referenced in `cognee_wrapper.py`)" → DELETE this bullet
    - L664: "Cognee - Stateful memory layer for context tracking" bullet → DELETE the bullet
    - L712: "Module scripts: lowercase with underscores (`cognee_wrapper.py`, ...)" → drop `cognee_wrapper.py` from the example list
    - L731: "Local modules imported directly by name (`import cognee_wrapper`)." → rewrite example to use a non-cognee module (e.g., `import config` or `import lib.scraper`)
    - L733: "Return `None` on non-critical failures: `cognee_wrapper.py` functions" → rewrite or DELETE the bullet
    - L767: "Example from `cognee_wrapper.py` (lines 7-45) ..." → rewrite the example to reference a different module (e.g., `config.py`)
    - L781: "Decoupled memory layer (Cognee) for entity canonicalization and context recall" → DELETE the bullet
    - L795-797: Layer description for Cognee → DELETE the entire layer description block
    - L801-802: "Custom prompt engineering, response generation, Cognee integration" + "Depends on: LightRAG queries + Cognee context recall" → drop cognee mention
    - L811: "Cognee memory: Persistent in Cognee's internal DB ..." → DELETE the bullet
    - L817: "Examples: LightRAG, Cognee, n8n, Cursor" → "Examples: LightRAG, n8n, Cursor"
    - L829: "Invokes: Apify client, CDP browser, Gemini Vision for images, LightRAG insertion, Cognee entity buffering" → drop "Cognee entity buffering"
    - L835: "Triggers: ... (direct LightRAG query without Cognee)" → "Triggers: ... (direct LightRAG query for debugging)"
    - L850: "Cognee operations: Always wrapped in try/except, warnings logged, main flow unaffected (async + non-blocking)" bullet → DELETE
    - L856: "File-based for batch processor: `cognee_batch.log` ..." → DELETE the bullet
    - L863: "Cognee/LiteLLM: Credentials sourced from Gemini API key" → DELETE the bullet

    Note: Line numbers will shift as edits accumulate. Executor must re-locate each anchor by content (via grep) before each edit, not blindly trust the numeric anchor. The pre-grep log fixes the SET of anchors; their numeric positions drift with each delete.

    **Step 2 — Deploy.md edits**:
    - L67: `cognee_batch_processor.run_batch()` calls `refresh_cognee()` at every poll → REWRITE the entire bullet to indicate Cognee is retired (e.g., "Cognee was retired 2026-05-10 in commit ${COMMIT-1-SHA}; the rotation hand-off documented here is no longer applicable.") OR delete the bullet if it no longer makes sense in context

    **Step 3 — README.md edits**:
    - L189: `├── cognee_batch_processor.py # Batch entity canonicalization` directory listing entry → DELETE
    - L340: `├── cognee_batch_processor.py # 实体归一化批处理` Chinese directory listing entry → DELETE

    **Step 4 — REQUIREMENTS.md edits**:

    Narrative section (lines 67-75 area):
    - L67 heading "Cognee (COG) — Day-1 preview round 2 discovery (2026-05-03), revised post-74f7503" → APPEND ", retired 2026-05-10 (quick 260510-gfg, commit ${COMMIT-1-SHA})"
    - L69 paragraph → APPEND a final sentence: "**2026-05-10 retirement update (Path A, quick 260510-gfg):** quick 260509-syd's investigation confirmed inline Cognee writes are dead writes (no readers). All three COG-01/02/03 requirements are RETIRED via dead-code removal in commit ${COMMIT-1-SHA}; if an episodic-memory layer is needed for Agentic-RAG-v1, it will be designed inside the ar-* phase rather than via the retired Cognee path."
    - L71 (`COG-01 — LANDED via 74f7503...`): change `[x]` to leave checked, but APPEND `**RETIRED 2026-05-10 by ${COMMIT-1-SHA} (quick 260510-gfg, Path A) — cognee_wrapper.py deleted; rationale: dead writes, no readers per quick 260509-syd Discovery 4.**`
    - L73 (`COG-02 — Cognee run_in_background=True ...`): same pattern — append RETIRED note with SHA
    - L75 (`COG-03 — Retire OMNIGRAPH_COGNEE_INLINE env gate ...`): change `[ ]` to `[x]` and append `**RETIRED 2026-05-10 by ${COMMIT-1-SHA} (quick 260510-gfg, Path A) — entire OMNIGRAPH_COGNEE_INLINE gate AND inline call removed; CLAUDE.md env-vars table row removed in same retirement commit.**`

    Add new requirement immediately after the COG block (under a new sub-heading or as continuation):
    ```
    #### Agentic-RAG Memory Placeholder (AGNT-MEM)

    - [ ] **AGNT-MEM-01** — TBD: episodic memory layer for Agentic-RAG-v1, if needed. Design happens inside the ar-* phase, not as a bolted-on Cognee replacement. Cognee was retired 2026-05-10 (quick 260510-gfg) as dead code; this placeholder records that a future requirement may emerge if Agentic-RAG-v1 design surfaces a need for cross-session memory beyond LightRAG's existing graph state.
    ```

    Traceability table (lines 130-132):
    - L130 `| COG-01 | Phase 20 | Complete (landed 2026-05-03 via 74f7503) |` → change to `| COG-01 | Phase 20 | RETIRED 2026-05-10 (quick 260510-gfg, ${COMMIT-1-SHA}) |`
    - L131 `| COG-02 | Phase 20 | Complete |` → `| COG-02 | Phase 20 | RETIRED 2026-05-10 (quick 260510-gfg, ${COMMIT-1-SHA}) |`
    - L132 `| COG-03 | Phase 20 | Pending (depends on COG-01 + COG-02) |` → `| COG-03 | Phase 20 | RETIRED 2026-05-10 (quick 260510-gfg, ${COMMIT-1-SHA}) |`

    Append new row after CUT-* rows:
    ```
    | AGNT-MEM-01 | TBD (ar-*) | Pending (placeholder; design inside Agentic-RAG-v1 milestone) |
    ```

    **Step 5 — PROJECT-Agentic-RAG-v1.md edits**:
    - L87 (Out-of-scope table row): `| Cognee / query-history injection | Deferred until v3.4 Phase 20/21 + Cognee revival lands (Axis 7) |` → REWRITE to `| Cognee / query-history injection | Cognee retired 2026-05-10 (quick 260510-gfg, commit ${COMMIT-1-SHA}); memory layer if needed will be designed inside ar-* phase per AGNT-MEM-01 placeholder. |`

    **Step 6 — Atomic forward-only commit**:
    ```bash
    git pull --ff-only origin main
    git add CLAUDE.md Deploy.md README.md .planning/REQUIREMENTS.md .planning/PROJECT-Agentic-RAG-v1.md
    git status    # confirm ONLY these 5 files staged
    git commit -m "$(cat <<'EOF'
docs(cognee-260510-gfg): mark COG-01/02/03 RETIRED, update CLAUDE/REQ/AR-1

Updates project documentation to reflect Cognee Path A full retirement landed
in the prior commit. Three traceability transitions:

REQUIREMENTS.md:
- COG-01/02/03 → RETIRED with retirement-commit SHA cited
- AGNT-MEM-01 placeholder added (memory layer if needed = ar-* phase decision)

CLAUDE.md (35 line edits per pre-grep inventory):
- Project summary, tech stack, env-vars table, architecture sections,
  ingestion/query flow diagrams, Lessons Learned, conventions all freed of
  Cognee references
- OMNIGRAPH_COGNEE_INLINE env-var row deleted
- Cognee rotation caveat paragraph deleted
- Stack constraint "Python 3.12 venv per Cognee wrapper" deleted

Deploy.md: refresh_cognee() rotation hand-off marked retired
README.md: cognee_batch_processor.py directory listings removed (L189 + L340)
PROJECT-Agentic-RAG-v1.md: Out-of-scope Cognee row updated to reflect retirement

Companion to refactor commit (Cognee code retirement) on the same quick.
No source code in this commit; only planning + reference docs.
EOF
)"
    git rev-parse HEAD    # capture COMMIT-2-SHA
    ```
  </action>
  <verify>
    <automated>
    grep -c -i 'cognee\|refresh_cognee' CLAUDE.md Deploy.md README.md 2>&1 | tail -10 \
    && grep -E 'COG-0[123].*Phase 20.*RETIRED' .planning/REQUIREMENTS.md | wc -l \
    && grep -i 'AGNT-MEM-01' .planning/REQUIREMENTS.md | wc -l \
    && grep -i 'cognee retired 2026-05-10' .planning/PROJECT-Agentic-RAG-v1.md | wc -l
    </automated>
  </verify>
  <done>
    - CLAUDE.md cognee mentions stripped (only audit-trail/lessons references remain in past-tense if any; no current-state references)
    - Deploy.md L67 refresh_cognee mention rewritten as retired
    - README.md L189 + L340 cognee_batch_processor.py entries removed
    - REQUIREMENTS.md narrative + traceability table show COG-01/02/03 status RETIRED with COMMIT-1-SHA cited
    - REQUIREMENTS.md has AGNT-MEM-01 placeholder row
    - PROJECT-Agentic-RAG-v1.md Out-of-scope row reflects 2026-05-10 retirement with COMMIT-1-SHA
    - Commit 2 created on origin/main with body matching template
    - COMMIT-2-SHA captured for Commit 3 STATE.md row
  </done>
</task>

<task type="auto">
  <name>Task 3: Commit 3 — STATE backfill (append 260510-gfg row to Quick Tasks Completed)</name>
  <files>.planning/STATE.md</files>
  <action>
    Use COMMIT-1-SHA + COMMIT-2-SHA captured at the end of Tasks 1 and 2.

    **Step 1 — Locate the insertion point**:
    Run `grep -n '^| 260509-s29' .planning/STATE.md` to find the last quick row. Insert the new row immediately AFTER that row (preserving table column count and pipe alignment).

    **Step 2 — Append the row**:
    The row must follow the established 5-column format `| ID | Description | Date | Commit | Path |`. Use a single-line description (no embedded newlines — the table is markdown-pipe-rendered).

    Template:
    ```
    | 260510-gfg | Cognee Path A — full retirement (dead-code removal, not feature removal). Continuation of investigation quick 260509-syd Discovery 4 (inline Cognee writes are CURRENTLY DEAD WRITES, no readers; Wave 0 already removed Cognee from synthesis path). 11 files DELETED entirely (`cognee_wrapper.py` 191 LOC + `cognee_batch_processor.py` 250 LOC + `init_cognee.py` + `setup_cognee.py` + 7 cognee-only test files including `verify_gate_{a,b,c}.py`); 8 production files EDITED to drop cognee imports/calls (`ingest_wechat.py` L57+L847-860+L1215-1228 inline gate; `query_lightrag.py` L2+L44 dead log_query_pattern call; `lib/api_keys.py` L4-7+L92-94 docstring + L159-174 `refresh_cognee()` function; `lib/__init__.py` L27+L50 `refresh_cognee` re-export; `lib/checkpoint.py` L7+L84 + `lib/llm_deepseek.py` L50 comment-only refs; `batch_ingest_github.py` L41 cognee URL; `requirements.txt` L6 `cognee` package); 6 mixed test files trimmed of cognee assertions only (preserved non-cognee test logic). REQUIREMENTS.md COG-01/02/03 transitioned to RETIRED with retirement-commit SHA cited; AGNT-MEM-01 placeholder added (memory layer if needed = ar-* phase decision). PROJECT-Agentic-RAG-v1.md Out-of-scope Cognee row updated. CLAUDE.md 35-line edit pass purged Cognee from project summary, tech stack, env-vars table, architecture sections, flow diagrams, Lessons Learned, and conventions; `OMNIGRAPH_COGNEE_INLINE` env var retired; "Cognee rotation caveat (Hermes FLAG 1)" paragraph deleted. Validation: pre-grep `.scratch/cognee-retire-pre-grep.log` (309 lines, locked the edit list); post-grep `.scratch/cognee-retire-post-grep.log` (0 functional refs in production *.py outside `scripts/cognee_diag/`); import-smoke `.scratch/cognee-retire-import-smoke.log` (`import smoke: all OK`); pytest pre/post `.scratch/cognee-retire-pytest-{pre,post}.log` (post-pass-count == pre-pass-count − deleted-cognee-test-count, no unexpected failures); local-e2e dry-run `.scratch/cognee-retire-dryrun.log` (`EXIT=0`, no cognee `ImportError`). Three atomic forward-only commits; no stash/reset/rebase/amend/force-push. HARD scope honored: `scripts/cognee_diag/` audit trail untouched (260509-syd investigation evidence); `.planning/quick/260509-syd-*` untouched; `.planning/quick/260503-v9z-*` + `260504-lt2-*` history untouched (those past PLAN/SUMMARYs reference cognee in past-state context); `lib/article_filter.py` untouched (user-locked); LightRAG / LiteLLM / Vertex AI / DeepSeek paths untouched (retire is not a routing fix); `~/.hermes/` untouched (no SSH); cron untouched (operator gate). | 2026-05-10 | `${COMMIT-1-SHA}` (refactor), `${COMMIT-2-SHA}` (docs), `${COMMIT-3-SHA}` (STATE) | [260510-gfg-cognee-path-a-full-retire-delete-cognee-](./quick/260510-gfg-cognee-path-a-full-retire-delete-cognee-/) |
    ```

    Replace `${COMMIT-1-SHA}`, `${COMMIT-2-SHA}` with the actual short SHAs (7 chars) captured from Tasks 1 and 2. `${COMMIT-3-SHA}` is the SHA of THIS commit — handle by either:
    (a) commit first with placeholder `(STATE pending)`, capture SHA, amend... — NO, amend is forbidden per scope_constraints. Use option (b):
    (b) commit with `(STATE)` and no SHA in the third slot. After commit, run `git rev-parse --short HEAD` to capture for any external reference. Or simply leave the third slot as `(STATE)` text since the commit's own SHA is the row's commit reference and is implicit.

    Recommended approach: write the commit slot as `\`${COMMIT-1-SHA}\` (refactor), \`${COMMIT-2-SHA}\` (docs), STATE-row-self-referential` — no third SHA needed because the Commit 3 SHA == the SHA shown by `git log` for the commit that introduces this row. Mirror the existing convention in STATE.md: e.g., row 260509-s29 lists `a85a91a` (W1) + `42a1b79` (W2) + `e538b2d` (W3) — all three commits self-record without circular reference issues because the row is added in the W3 commit. For 260510-gfg, the same applies: list COMMIT-1 (refactor) + COMMIT-2 (docs); the third "STATE" commit is the one introducing the row, and conventionally the row text doesn't need to cite its own SHA. Adjust the template to:
    `| ... | 2026-05-10 | \`${COMMIT-1-SHA}\` (refactor), \`${COMMIT-2-SHA}\` (docs) | [path] |`

    **Step 3 — Atomic forward-only commit**:
    ```bash
    git pull --ff-only origin main
    git add .planning/STATE.md
    git status    # confirm ONLY .planning/STATE.md staged
    git diff --cached .planning/STATE.md | head -20    # spot-check the row format
    git commit -m "$(cat <<'EOF'
docs(quick-260510-gfg): add Cognee retirement to STATE.md Quick Tasks Completed

Backfills the Quick Tasks Completed table with the 260510-gfg row covering the
full Cognee Path A retirement: 11 files deleted + 14 files edited + 5 doc files
updated across two prior atomic commits (refactor + docs).

Companion to:
- refactor(cognee-260510-gfg) — code retirement
- docs(cognee-260510-gfg) — REQUIREMENTS/PROJECT/CLAUDE updates

Closes quick 260510-gfg.
EOF
)"
    ```
  </action>
  <verify>
    <automated>
    grep -E '^\| 260510-gfg' .planning/STATE.md | wc -l \
    && git log --oneline -3 | grep -c 'cognee-260510-gfg'
    </automated>
  </verify>
  <done>
    - .planning/STATE.md Quick Tasks Completed table has the 260510-gfg row immediately after the 260509-s29 row
    - Row format matches the established 5-column convention (ID | Description | Date | Commit | Path)
    - Description cell is a single line (no embedded newlines breaking pipe rendering)
    - Commit cell cites both COMMIT-1-SHA (refactor) and COMMIT-2-SHA (docs)
    - All 5 .scratch/ evidence log paths are referenced inside the description cell
    - Path cell links to the quick directory `.planning/quick/260510-gfg-cognee-path-a-full-retire-delete-cognee-/`
    - Commit 3 created on origin/main with body matching template
    - 3 commits total exist on origin/main with `cognee-260510-gfg` in subject lines
  </done>
</task>

</tasks>

<verification>
**End-of-quick verification (run after all 3 commits land)**:

1. **Three commits on origin/main**:
   ```bash
   git log --oneline -5 | grep 'cognee-260510-gfg' | wc -l    # MUST output 3
   ```

2. **Zero functional cognee refs in production *.py** (outside the audit trail):
   ```bash
   git ls-files '*.py' | grep -v '^scripts/cognee_diag/' | grep -v '^\\.planning/quick/260509-syd' | grep -v '^tests/' | xargs grep -l 'import cognee\\|cognee_wrapper\\|refresh_cognee\\|cognee\\.[a-z]' 2>/dev/null | wc -l    # MUST output 0
   ```

3. **No deleted-file references survive**:
   ```bash
   git ls-files | xargs grep -l 'cognee_wrapper\\|cognee_batch_processor\\|init_cognee\\.py\\|setup_cognee\\.py\\|verify_gate_[abc]' 2>/dev/null | grep -v '^\\.planning/quick/260' | grep -v '^scripts/cognee_diag/' | wc -l    # SHOULD be 0 or only docs in past-tense form (Lessons Learned, Deploy.md retirement note)
   ```

4. **Pytest baseline preserved (no regressions)**:
   ```bash
   DEEPSEEK_API_KEY=dummy GEMINI_API_KEY=dummy .venv/Scripts/python -m pytest tests/ -q --no-header 2>&1 | tail -3
   # Last line must say "X passed in Y.Ys" with X == pre-baseline minus deleted-cognee-tests, NO unexpected fails
   ```

5. **Import smoke clean**:
   ```bash
   DEEPSEEK_API_KEY=dummy GEMINI_API_KEY=dummy .venv/Scripts/python -c "import ingest_wechat, query_lightrag, lib, lib.api_keys, batch_ingest_github; print('OK')"
   # MUST output: OK
   ```

6. **REQUIREMENTS.md status transitions confirmed**:
   ```bash
   grep -E 'COG-0[123].*Phase 20.*RETIRED' .planning/REQUIREMENTS.md | wc -l    # MUST output 3
   grep -E 'AGNT-MEM-01.*Pending' .planning/REQUIREMENTS.md | wc -l    # MUST output 1
   ```

7. **STATE.md row present**:
   ```bash
   grep -c '^| 260510-gfg' .planning/STATE.md    # MUST output 1
   ```

8. **Anti-fabrication evidence trail intact**:
   ```bash
   ls -la .scratch/cognee-retire-{pre-grep,post-grep,import-smoke,pytest-pre,pytest-post,dryrun}.log
   # All 6 files MUST exist
   ```

9. **No SSH artifacts** (this is a local-only quick):
   ```bash
   git log --oneline -3 | grep -i 'hermes\\|ssh\\|deploy' | wc -l    # MUST output 0
   ```
</verification>

<success_criteria>
The quick is complete when ALL of the following hold:

- [ ] 3 atomic forward-only commits land on origin/main, each with `cognee-260510-gfg` in subject
- [ ] No `git stash`, `git reset`, `git rebase`, `git commit --amend`, or `git push --force` was used
- [ ] `git ls-files | xargs grep -l 'cognee_wrapper\|cognee_batch_processor\|init_cognee\|setup_cognee\|verify_gate_[abc]'` produces zero hits outside `scripts/cognee_diag/` and `.planning/quick/260*`
- [ ] `python -c "import ingest_wechat; import query_lightrag; import lib; import lib.api_keys; import batch_ingest_github"` succeeds with `DEEPSEEK_API_KEY=dummy GEMINI_API_KEY=dummy`
- [ ] Pytest pass count post-retire == pytest pass count pre-retire − (number of cognee-only test functions deleted), with NO unexpected failures (failures must trace either to deleted cognee code path or to pre-existing baseline fails listed by name)
- [ ] `.scratch/cognee-retire-{pre-grep,post-grep,import-smoke,pytest-pre,pytest-post,dryrun}.log` all 6 files exist and were referenced verbatim in the relevant commit body (anti-fabrication contract)
- [ ] REQUIREMENTS.md COG-01/02/03 status column is "RETIRED 2026-05-10 (quick 260510-gfg, ${SHA})" for all three rows
- [ ] REQUIREMENTS.md has new AGNT-MEM-01 placeholder row in traceability table
- [ ] PROJECT-Agentic-RAG-v1.md L87 Out-of-scope Cognee row reflects 2026-05-10 retirement with COMMIT-1-SHA
- [ ] CLAUDE.md `OMNIGRAPH_COGNEE_INLINE` env-vars row is gone; tech stack no longer mentions Cognee
- [ ] STATE.md Quick Tasks Completed table has the 260510-gfg row immediately after the 260509-s29 row, with single-line description, both commit SHAs cited, and links to evidence logs
- [ ] No SSH to Hermes performed; no edits to `~/.hermes/` files; no cron change
- [ ] `scripts/cognee_diag/`, `.planning/quick/260509-syd-*`, `lib/article_filter.py`, LightRAG/LiteLLM/Vertex AI/DeepSeek paths all untouched
</success_criteria>

<output>
After completion, the executor returns a SUMMARY block citing all 3 commit SHAs + all 6 .scratch evidence log paths. No SUMMARY.md file is written for quick tasks (per CLAUDE.md "Do NOT Write report/summary/findings/analysis .md files" rule). The quick is closed by the orchestrator after STATE.md row lands.
</output>
