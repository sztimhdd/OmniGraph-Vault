---
phase: quick-260510-oxq
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - ingest_wechat.py
  - batch_ingest_from_spider.py
  - tests/unit/test_ingest_article_processed_gate.py
autonomous: true
requirements:
  - SIW-01
  - SIW-02
  - SIW-03
must_haves:
  truths:
    - "Inner ingest_wechat.ingest_article no longer writes to the ingestions table"
    - "Outer batch_ingest_from_spider.ingest_article returns a 3-tuple (success, wall, doc_confirmed)"
    - "Both main-loop call sites in batch_ingest_from_spider.py status='ok' branch require BOTH success AND doc_confirmed"
    - "Existing pytest unit test for outer-catches-inner-RuntimeError contract still passes after the signature change"
    - "Inner's UPDATE articles SET content_hash and UPDATE articles SET enriched statements remain unchanged (only the INSERT INTO ingestions block is removed)"
  artifacts:
    - path: "ingest_wechat.py"
      provides: "Inner ingest pipeline with the INSERT OR IGNORE INTO ingestions block surgically removed (lines ~1314-1318)"
      contains: "doc_confirmed = True"
    - path: "batch_ingest_from_spider.py"
      provides: "Outer wrapper returning (success, wall, doc_confirmed); both main-loop call sites unpack 3 values and gate status='ok' on success AND doc_confirmed"
      contains: "tuple[bool, float, bool]"
    - path: "tests/unit/test_ingest_article_processed_gate.py"
      provides: "Updated test unpacking 3-tuple and asserting doc_confirmed is False on inner RuntimeError"
      contains: "success, wall, doc_confirmed"
  key_links:
    - from: "ingest_wechat.ingest_article (inner)"
      to: "batch_ingest_from_spider.ingest_article (outer)"
      via: "implicit return of None on happy path → outer interprets as doc_confirmed=True; RuntimeError → outer catches and returns doc_confirmed=False"
      pattern: "doc_confirmed"
    - from: "batch_ingest_from_spider.ingest_article (outer)"
      to: "main loop status assignment (call site #1 line 822, call site #2 line 1730)"
      via: "elif success and doc_confirmed: status = 'ok'"
      pattern: "success and doc_confirmed"
    - from: "main loop --from-db path"
      to: "ingestions table (sole writer)"
      via: "INSERT OR REPLACE at line 1745 unchanged; outer is now sole writer because inner's INSERT is gone"
      pattern: "INSERT OR REPLACE INTO ingestions"
---

<objective>
Eliminate the outer/inner double-INSERT design smell on the ingestions table.

Today both ingest_wechat.py (inner) and batch_ingest_from_spider.py (outer, --from-db path) write to the ingestions table. The inner writes status='ok' speculatively when doc_confirmed is True; the outer overwrites with INSERT OR REPLACE based on its own (success, wall) judgment. This split-brain produces:
  * Two writers racing on the same row
  * Inner can mark 'ok' even when the outer ultimately decides 'failed' due to TimeoutError vs the doc_confirmed timing window
  * Maintenance hazard — any future status logic change must be made in two places

Goal: outer becomes the SOLE writer for ingestions. Inner stops writing entirely. Outer learns whether the inner's PROCESSED gate passed by receiving an explicit doc_confirmed bool through the return tuple, then gates status='ok' on (success AND doc_confirmed).

Purpose: removes a load-bearing race condition between two writers and consolidates the "what counts as a successful ingest" decision into a single code site.

Output:
  * ingest_wechat.py: 5-line INSERT OR IGNORE block removed (lines ~1314-1318)
  * batch_ingest_from_spider.py: outer return signature widened to (bool, float, bool); both main-loop call sites unpack 3 values; status='ok' gated on success AND doc_confirmed
  * tests/unit/test_ingest_article_processed_gate.py: 3-tuple unpack + new assertion
  * Single atomic commit
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md

<interfaces>
<!-- Key contracts the executor needs. Extracted from codebase. -->
<!-- Do NOT explore the codebase for these — they are pinned here. -->

CURRENT outer signature (batch_ingest_from_spider.py:237-242):
```python
async def ingest_article(
    url: str,
    dry_run: bool,
    rag,
    effective_timeout: int | None = None,
) -> tuple[bool, float]:
```

NEW outer signature:
```python
async def ingest_article(
    url: str,
    dry_run: bool,
    rag,
    effective_timeout: int | None = None,
) -> tuple[bool, float, bool]:
```

CURRENT outer return points (4 total):
  Line 270: `return True, 0.0`                        # dry_run
  Line 289: `return True, time.time() - t_start`      # happy path
  Line 318: `return False, wall`                      # TimeoutError
  Line 323: `return False, wall`                      # generic Exception

NEW outer return points:
  Line 270: `return True, 0.0, False`                 # dry_run (informational; main loop dry_run branch fires first)
  Line 289: `return True, time.time() - t_start, True`  # happy path — inner returned cleanly = PROCESSED gate passed
  Line 318: `return False, wall, False`               # TimeoutError — inner never reached doc_confirmed=True
  Line 323: `return False, wall, False`               # generic Exception (catches inner's RuntimeError from h09 PROCESSED-raise)

Inner block to REMOVE (ingest_wechat.py:1314-1318) — exactly these 5 lines:
```python
            conn.execute(
                "INSERT OR IGNORE INTO ingestions(article_id, source, status) "
                "VALUES ((SELECT id FROM articles WHERE url = ?), 'wechat', 'ok')",
                (url,),
            )
```
KEEP everything else in the surrounding `if DB_PATH.exists() and doc_confirmed:` block — UPDATE articles SET content_hash, the enriched=-1 UPDATE, conn.commit(), conn.close(). The local var `doc_confirmed = True` at line 1298 also stays (still gates the UPDATE articles writes — desirable for retry pool semantics).

Main-loop call sites — TWO of them:
  Site #1 (line 822-824, legacy --from-spider path, NO ingestions INSERT):
    `success, wall = await ingest_article(url, dry_run, rag, effective_timeout=effective_timeout)`
    → unpack 3 values, change `elif success:` → `elif success and doc_confirmed:` at line 827

  Site #2 (line 1730-1732, --from-db path, HAS ingestions INSERT at 1745):
    `success, wall = await ingest_article(url_d, dry_run, rag, effective_timeout=effective_timeout)`
    → unpack 3 values, change `elif success:` → `elif success and doc_confirmed:` at line 1735
    → INSERT OR REPLACE at lines 1745-1749 stays unchanged (writes the now-correctly-gated `status` variable)

Test to update (tests/unit/test_ingest_article_processed_gate.py:195):
  Currently: `success, wall = await bif.ingest_article(...)`
  After:     `success, wall, doc_confirmed = await bif.ingest_article(...)`
  Add assertion: `assert doc_confirmed is False`  (inner raises RuntimeError → outer's generic Exception branch → returns doc_confirmed=False)

Tests NOT touched (HARD OUT-OF-SCOPE):
  * tests/unit/test_ainsert_persistence_contract.py (parallel quick 260510-gkw has WIP)
  * tests/unit/test_text_first_ingest.py (calls INNER ingest_wechat.ingest_article; inner signature unchanged — still returns vision_task)
  * tests/unit/test_checkpoint_ingest_integration.py (calls INNER; same reason)
</interfaces>

<hard_out_of_scope>
The following must NOT be touched in this quick:
- tests/unit/test_ainsert_persistence_contract.py (parallel quick has WIP)
- _verify_doc_processed_or_raise body (in ingest_wechat.py)
- Pattern A poll budget — do not introduce
- Vision sub-doc verification logic
- ingestions table schema or any migration
- Outer's try/except STRUCTURE (only return statements within them change — branch logic stays identical)
- _status_is_processed / aget_docs_by_ids calls
- Inner's UPDATE articles SET content_hash / SET enriched statements (only the INSERT INTO ingestions block is removed)
- doc_confirmed local variable at ingest_wechat.py:1298 (stays — still gates UPDATE articles writes)
</hard_out_of_scope>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Remove inner INSERT, widen outer signature, update both call sites</name>
  <files>ingest_wechat.py, batch_ingest_from_spider.py</files>
  <action>
    Surgical changes only. Match existing style. Do NOT reformat surrounding code.

    Step 1 — ingest_wechat.py: remove the inner INSERT OR IGNORE block.
      Delete EXACTLY these 5 lines at ingest_wechat.py:1314-1318:
        ```
                    conn.execute(
                        "INSERT OR IGNORE INTO ingestions(article_id, source, status) "
                        "VALUES ((SELECT id FROM articles WHERE url = ?), 'wechat', 'ok')",
                        (url,),
                    )
        ```
      Do NOT delete: the surrounding `if DB_PATH.exists() and doc_confirmed:` predicate, `conn = sqlite3.connect(...)`, the UPDATE articles SET content_hash statement, the `if len(full_content) < ENRICHMENT_MIN_LENGTH:` UPDATE articles SET enriched block, conn.commit(), conn.close(), or the try/except. Do NOT touch `doc_confirmed = True` at line 1298 — it still gates the UPDATE articles writes (desirable for retry-pool semantics: leaves content_hash NULL on unverified ingest so mig 009 retry pool re-queues).

    Step 2 — batch_ingest_from_spider.py: widen outer signature and 4 return points.
      (a) Line 242 — change return type annotation:
          `) -> tuple[bool, float]:` → `) -> tuple[bool, float, bool]:`
      (b) Line 270 — dry_run return:
          `return True, 0.0` → `return True, 0.0, False`
      (c) Line 289 — happy path return:
          `return True, time.time() - t_start` → `return True, time.time() - t_start, True`
      (d) Line 318 — TimeoutError return:
          `return False, wall` → `return False, wall, False`
      (e) Line 323 — generic Exception return:
          `return False, wall` → `return False, wall, False`

      Do NOT modify the try/except branch logic, the rollback block (adelete_by_doc_id), the checkpoint flush block, or any logging.

    Step 3 — batch_ingest_from_spider.py: update BOTH main-loop call sites.

      Call site #1 (legacy --from-spider path, around lines 822-836):
        (a) Line 822-824 — unpack 3 values:
            `success, wall = await ingest_article(...)` → `success, wall, doc_confirmed = await ingest_article(...)`
        (b) Line 827 — gate status='ok':
            `elif success:` → `elif success and doc_confirmed:`

      Call site #2 (--from-db path, around lines 1730-1750):
        (a) Line 1730-1732 — unpack 3 values:
            `success, wall = await ingest_article(...)` → `success, wall, doc_confirmed = await ingest_article(...)`
        (b) Line 1735 — gate status='ok':
            `elif success:` → `elif success and doc_confirmed:`
        (c) The INSERT OR REPLACE at lines 1745-1749 stays UNCHANGED — it writes the (now correctly gated) `status` variable.

    Style notes:
      - Match existing 4-space indent
      - PEP 8 compliant (no extra trailing whitespace, no reflow of unrelated lines)
      - No print() additions, no logging changes
  </action>
  <verify>
    <automated>
      cd "C:/Users/huxxha/Desktop/OmniGraph-Vault" && \
      mkdir -p .scratch && \
      TS=$(date +%Y%m%d-%H%M%S) && \
      grep -n "INSERT OR IGNORE INTO ingestions" ingest_wechat.py > .scratch/siw-grep-${TS}.log 2>&1; \
      EC=$?; \
      echo "exit_code=$EC (expected 1 = no matches)" >> .scratch/siw-grep-${TS}.log && \
      grep -n "tuple\[bool, float, bool\]" batch_ingest_from_spider.py >> .scratch/siw-grep-${TS}.log && \
      grep -n "success and doc_confirmed" batch_ingest_from_spider.py >> .scratch/siw-grep-${TS}.log && \
      grep -cn "success, wall, doc_confirmed = await ingest_article" batch_ingest_from_spider.py >> .scratch/siw-grep-${TS}.log && \
      echo "DONE — verify exit_code=1 (no INSERT) AND tuple[bool, float, bool] present AND 'success and doc_confirmed' appears 2x AND unpack pattern appears 2x"
    </automated>
  </verify>
  <done>
    - `grep -n "INSERT OR IGNORE INTO ingestions" ingest_wechat.py` returns exit code 1 (no matches)
    - `batch_ingest_from_spider.py` contains exactly one occurrence of `tuple[bool, float, bool]` (the return annotation)
    - `batch_ingest_from_spider.py` contains exactly two occurrences of `elif success and doc_confirmed:`
    - `batch_ingest_from_spider.py` contains exactly two occurrences of `success, wall, doc_confirmed = await ingest_article`
    - `batch_ingest_from_spider.py` contains exactly four `return ..., False` or `return ..., True` patterns within `ingest_article`
    - Inner's `UPDATE articles SET content_hash` and `UPDATE articles SET enriched` statements still present in ingest_wechat.py
    - .scratch/siw-grep-<ts>.log file exists with verification evidence
  </done>
</task>

<task type="auto">
  <name>Task 2: Update test for 3-tuple return signature and run pytest</name>
  <files>tests/unit/test_ingest_article_processed_gate.py</files>
  <action>
    Surgical change to ONE existing test only.

    At tests/unit/test_ingest_article_processed_gate.py:195, change:
      ```
          success, wall = await bif.ingest_article(
              url="https://example.com/test",
              dry_run=False,
              rag=rag,
              effective_timeout=60,
          )
      ```
    To:
      ```
          success, wall, doc_confirmed = await bif.ingest_article(
              url="https://example.com/test",
              dry_run=False,
              rag=rag,
              effective_timeout=60,
          )
      ```

    Then add ONE assertion immediately after the existing `assert wall >= 0.0` line (line 203):
      ```
          assert doc_confirmed is False  # Inner raised RuntimeError → outer's generic Exception branch → doc_confirmed=False
      ```

    Do NOT touch any other test in the file. Do NOT touch tests/unit/test_ainsert_persistence_contract.py (parallel quick has WIP). Do NOT touch tests/unit/test_text_first_ingest.py or tests/unit/test_checkpoint_ingest_integration.py — they call INNER ingest_wechat.ingest_article whose signature is unchanged.

    After the edit, run pytest on the affected test file plus the parallel test surface (excluding the WIP ainsert file) to prove no regression:

    ```
    cd "C:/Users/huxxha/Desktop/OmniGraph-Vault" && \
    mkdir -p .scratch && \
    TS=$(date +%Y%m%d-%H%M%S) && \
    .venv/Scripts/python -m pytest \
        tests/unit/test_ingest_article_processed_gate.py \
        tests/unit/test_text_first_ingest.py \
        tests/unit/test_checkpoint_ingest_integration.py \
        -v 2>&1 | tee .scratch/siw-pytest-${TS}.log
    ```

    Capture last 50 lines of the log into the SUMMARY.md verbatim (anti-fabrication).
  </action>
  <verify>
    <automated>
      cd "C:/Users/huxxha/Desktop/OmniGraph-Vault" && \
      .venv/Scripts/python -m pytest tests/unit/test_ingest_article_processed_gate.py -v -x 2>&1 | tail -20
    </automated>
  </verify>
  <done>
    - test_outer_catches_inner_runtime_error_returns_failed PASSES with the 3-tuple unpack and new doc_confirmed assertion
    - tests/unit/test_text_first_ingest.py and tests/unit/test_checkpoint_ingest_integration.py still PASS (sanity — they call inner whose signature is unchanged)
    - .scratch/siw-pytest-<ts>.log file exists with pytest output
    - No new test failures vs baseline
  </done>
</task>

<task type="auto">
  <name>Task 3: Atomic commit + STATE.md row + SUMMARY.md</name>
  <files>.planning/STATE.md, .planning/quick/260510-oxq-eliminate-outer-inner-double-insert-desi/SUMMARY.md</files>
  <action>
    Step 1 — write SUMMARY.md at .planning/quick/260510-oxq-eliminate-outer-inner-double-insert-desi/SUMMARY.md.

    Required SUMMARY sections (use plain markdown, no emojis):
      - Title: `# Quick 260510-siw — Eliminate outer/inner double-INSERT design smell`
      - `## Outcome` — 2-3 sentences: outer is now sole writer for ingestions; inner stopped writing; doc_confirmed bool propagates from inner to outer via 3-tuple return; both main-loop call sites gate status='ok' on (success AND doc_confirmed)
      - `## Files Changed` — bullet list with diff stat from `git diff --stat HEAD`
      - `## Verification — pytest` — paste verbatim the LAST 50 LINES of .scratch/siw-pytest-<ts>.log (anti-fabrication; cite the log file path on the line above the paste)
      - `## Verification — grep` — paste verbatim the contents of .scratch/siw-grep-<ts>.log (cite log file path)
      - `## Out-of-Scope (unchanged)` — list confirming: test_ainsert_persistence_contract.py untouched, _verify_doc_processed_or_raise body untouched, no Pattern A added, no schema changes, no Vision sub-doc verification changes
      - `## Diff Stat Sanity` — output of `git diff --stat HEAD` showing changes ONLY in: ingest_wechat.py, batch_ingest_from_spider.py, tests/unit/test_ingest_article_processed_gate.py, .planning/STATE.md, .planning/quick/260510-oxq-*/

    DO NOT make any unverifiable claims. Every "I ran X" statement MUST cite the .scratch log file that proves it.

    Step 2 — append a row to .planning/STATE.md under the "Recent Activity" or equivalent log section. Match the existing STATE.md row format (read STATE.md first to mimic style). One-line entry:
      `- 260510-siw: refactor — eliminate outer/inner double-INSERT, outer is sole writer for ingestions, gates status='ok' on (success AND doc_confirmed bool from inner). Touches: ingest_wechat.py, batch_ingest_from_spider.py, test_ingest_article_processed_gate.py.`

    Step 3 — single atomic commit. Use ONLY explicit file paths (NEVER `git add -A`). Use HEREDOC for commit message.

    ```
    cd "C:/Users/huxxha/Desktop/OmniGraph-Vault" && \
    git add \
        ingest_wechat.py \
        batch_ingest_from_spider.py \
        tests/unit/test_ingest_article_processed_gate.py \
        .planning/STATE.md \
        .planning/quick/260510-oxq-eliminate-outer-inner-double-insert-desi/ \
        && git commit -m "$(cat <<'EOF'
    refactor(ingest-260510-siw): eliminate outer/inner double-INSERT — outer is sole writer for ingestions, gates on doc_confirmed bool from inner

    - ingest_wechat.py: remove INSERT OR IGNORE INTO ingestions block (lines ~1314-1318); UPDATE articles SET content_hash and SET enriched still gated on doc_confirmed (retry-pool semantics preserved)
    - batch_ingest_from_spider.py: outer ingest_article now returns (success, wall, doc_confirmed); both main-loop call sites unpack 3-tuple and gate status='ok' on (success AND doc_confirmed); --from-db INSERT OR REPLACE at line 1745 unchanged (sole writer)
    - tests/unit/test_ingest_article_processed_gate.py: 3-tuple unpack + doc_confirmed=False assertion on inner-RuntimeError path

    Out of scope:
    - test_ainsert_persistence_contract.py (parallel quick 260510-gkw has WIP)
    - _verify_doc_processed_or_raise body, Pattern A poll budget, Vision sub-doc verification, ingestions schema, retry/migration logic
    EOF
    )"
    ```

    Verify the commit landed (`git log --oneline -1` and `git status`). The commit MUST contain only the listed paths — anything else means the staging was wrong; abort and re-stage.

    Step 4 — confirm commit hygiene by running `git diff --stat HEAD~1 HEAD` and pasting that exact output as the final line of SUMMARY.md's "Diff Stat Sanity" section (post-commit verification).
  </action>
  <verify>
    <automated>
      cd "C:/Users/huxxha/Desktop/OmniGraph-Vault" && \
      git log --oneline -1 | grep -q "260510-siw" && \
      git diff --stat HEAD~1 HEAD | tee /dev/stderr | grep -E "^\s*(ingest_wechat\.py|batch_ingest_from_spider\.py|tests/unit/test_ingest_article_processed_gate\.py|\.planning/)" | wc -l
    </automated>
  </verify>
  <done>
    - SUMMARY.md exists at .planning/quick/260510-oxq-eliminate-outer-inner-double-insert-desi/SUMMARY.md with all 6 required sections
    - SUMMARY.md cites both .scratch/siw-pytest-<ts>.log and .scratch/siw-grep-<ts>.log file paths and pastes their contents verbatim (anti-fabrication)
    - One row appended to .planning/STATE.md
    - Single commit at HEAD with subject `refactor(ingest-260510-siw): eliminate outer/inner double-INSERT — outer is sole writer for ingestions, gates on doc_confirmed bool from inner`
    - `git diff --stat HEAD~1 HEAD` shows files ONLY from: ingest_wechat.py, batch_ingest_from_spider.py, tests/unit/test_ingest_article_processed_gate.py, .planning/STATE.md, .planning/quick/260510-oxq-*/
    - `git status` shows clean working tree (no leftover staged or unstaged changes outside .scratch/)
  </done>
</task>

</tasks>

<verification>
End-to-end checks after all 3 tasks complete:

1. Inner has zero ingestions writes:
   `grep -c "INSERT.*INTO ingestions" ingest_wechat.py` → 0

2. Outer signature widened:
   `grep -c "tuple\[bool, float, bool\]" batch_ingest_from_spider.py` → 1

3. Both call sites gated:
   `grep -c "elif success and doc_confirmed:" batch_ingest_from_spider.py` → 2

4. Test passes:
   `.venv/Scripts/python -m pytest tests/unit/test_ingest_article_processed_gate.py -v` → all green

5. No tests untouched outside scope:
   `git diff --name-only HEAD~1 HEAD` → exactly 5 paths (ingest_wechat.py, batch_ingest_from_spider.py, tests/unit/test_ingest_article_processed_gate.py, .planning/STATE.md, .planning/quick/260510-oxq-*/SUMMARY.md, plus .planning/quick/260510-oxq-*/PLAN.md if pre-staged)

6. test_ainsert_persistence_contract.py NOT in the diff (must remain untouched per parallel-quick conflict avoidance):
   `git diff --name-only HEAD~1 HEAD | grep ainsert_persistence` → empty
</verification>

<success_criteria>
All five must-have truths in the frontmatter are observable in the working tree:

  1. `grep -c "INSERT OR IGNORE INTO ingestions" ingest_wechat.py` returns 0
  2. `grep -c "tuple\[bool, float, bool\]" batch_ingest_from_spider.py` returns 1
  3. `grep -c "elif success and doc_confirmed:" batch_ingest_from_spider.py` returns 2
  4. `.venv/Scripts/python -m pytest tests/unit/test_ingest_article_processed_gate.py` returns exit code 0 with the new doc_confirmed assertion exercised
  5. `grep -c "UPDATE articles SET content_hash" ingest_wechat.py` returns >=1 (inner UPDATE preserved)

Single atomic commit at HEAD with subject matching the SIW commit-message spec, touching only the 5 expected paths.

No deviation from <hard_out_of_scope> list.
</success_criteria>

<output>
After completion, the executor should already have created:
  - .planning/quick/260510-oxq-eliminate-outer-inner-double-insert-desi/SUMMARY.md (with verbatim log pastes)

No additional artifacts required. The single atomic commit closes the quick.
</output>
