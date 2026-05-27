---
phase: quick-260511-lmx
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - batch_ingest_from_spider.py
  - tests/unit/test_max_articles_hard_cap.py
autonomous: true
requirements:
  - QUICK-260511-LMX-01  # strict hard cap on ok+failed; skipped excluded
  - QUICK-260511-LMX-02  # exit cleanly when cap reached; log line emitted
  - QUICK-260511-LMX-03  # 4 mock pytest cases pinning new contract

must_haves:
  truths:
    - "When --max-articles N is passed, ok+failed ingestions never exceed N (strict hard cap)."
    - "Skipped statuses (skipped, skipped_ingested, skipped_graded) DO NOT consume cap budget."
    - "When the cap is reached the loop breaks cleanly with one log line containing 'max-articles cap reached'."
    - "When candidate pool exhausts before cap (e.g. all rejected), loop ends naturally without error."
    - "Existing scan-mode (run() at L689) is untouched; only --from-db ingest_from_db() (L1443) changes."
    - "Pre-fix smoke (instrumented stderr line per loop iteration) shows --max-articles 2 produces > 2 ingest rows; post-fix shows exactly 2 (or fewer if pool exhausted)."
  artifacts:
    - path: "batch_ingest_from_spider.py"
      provides: "Strict hard-cap enforcement at enqueue boundary in ingest_from_db loop"
      contains: "max_articles is not None and (processed + len(layer2_queue))"
    - path: "tests/unit/test_max_articles_hard_cap.py"
      provides: "4 pytest cases pinning the strict hard-cap contract"
      contains: "test_cap_excludes_skipped_layer1_rejects, test_cap_break_on_third_ok, test_cap_with_mid_loop_failure_counts, test_cap_pool_exhausted_before_reached"
  key_links:
    - from: "batch_ingest_from_spider.py:1911 (layer2_queue.append)"
      to: "max_articles cap"
      via: "pre-enqueue gate using (processed + len(layer2_queue)) budget"
      pattern: "processed \\+ len\\(layer2_queue\\) >= max_articles"
    - from: "tests/unit/test_max_articles_hard_cap.py"
      to: "ingest_from_db loop counter contract"
      via: "mock-only mocker.patch on layer2_full_body_score + ingest_article + scrape_url"
      pattern: "mocker.patch.*ingest_article|mocker.patch.*layer2_full_body_score"
---

<objective>
Fix the `--max-articles N` cap leak in `batch_ingest_from_spider.py:ingest_from_db()`. Currently the cap is checked AFTER the layer2 batch drain, so up to LAYER2_BATCH_SIZE-1 (=4) extra articles can leak past the cap (observed: spec=5 → actual 7, 14, 7 across three smoke runs). Tighten to a strict per-article hard cap on `ok+failed` rows only (skipped statuses excluded), with clean exit-and-log when reached.

Purpose: Make `--max-articles` predictable so smoke runs and bounded reliability tests have deterministic wall-clock budgets. Eliminates the surprise "I asked for 5, got 14" failure mode that destroyed 2026-05-10 smoke timing.

Output: ~10-20 LOC change in `batch_ingest_from_spider.py` + new mock-only pytest file `tests/unit/test_max_articles_hard_cap.py` with 4 cases pinning the contract.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
</context>

<investigation_findings>

**Grepped 2026-05-11 by planner. Line numbers verified against current HEAD.**

### Where `--max-articles` lives

| Location | Line | Role |
|---|---|---|
| CLI arg parser | `batch_ingest_from_spider.py:1978` | `--max-articles` (default=50) |
| Dispatch (scan mode) | `batch_ingest_from_spider.py:723` | passes to `run()` |
| Dispatch (from-db) | `batch_ingest_from_spider.py:2009/2014` | passes to `ingest_from_db()` |
| `run()` signature | `batch_ingest_from_spider.py:689` | scan mode (NOT in scope) |
| `ingest_from_db()` signature | `batch_ingest_from_spider.py:1448` | --from-db mode (IN SCOPE) |

### `ingest_from_db()` loop structure (the buggy path)

```
L1625: processed = 0
L1632: layer2_queue: list[...] = []
L1635-L1750+: async def _drain_layer2_queue()
                — for each ok/failed/dry_run row drained: processed += 1
                — for layer2 reject rows: writes 'skipped' ingestion, NO processed++
L1772: for i, (...) in enumerate(candidate_rows, 1):
L1776:    if max_articles is not None and processed >= max_articles:    # CAP CHECK 1 (per-iter)
              break
L1788:    if dry_run: continue
L1795:    if not url: ...skip continue (no enqueue, no processed++)
L1807:    if has_stage(.., "text_ingest"): ...skipped_ingested continue
L1823:    if has_stage(.., "scrape") and not body: ...skipped continue
L1840:    if GRADED_ENABLED ...skipped_graded continue
L1878:    if _needs_scrape: scrape_url; persist body
L1898:    if not body: continue (no enqueue)
L1911:    layer2_queue.append((row, body))                              # ENQUEUE
L1916:    if len(layer2_queue) >= LAYER2_BATCH_SIZE (=5):
L1917:        await _drain_layer2_queue()                               # DRAIN
L1930:    if max_articles is not None and processed >= max_articles:    # CAP CHECK 2 (post-drain)
L1935:        await _drain_layer2_queue()
              break
L1939: await _drain_layer2_queue()  # FINAL DRAIN (always runs)
```

### Root cause

CAP CHECK 1 fires at the start of each iteration based on `processed`. But `processed` increments only **inside** `_drain_layer2_queue()`, which runs only when the queue hits `LAYER2_BATCH_SIZE=5` (or at end of loop). So between drains, `processed` is stale.

Walk-through with `--max-articles=2` and 6 layer2-OK candidates:
- Iter 1: processed=0, 0<2 ✓ pass cap check, enqueue (queue=1).
- Iter 2: processed=0, enqueue (queue=2).
- Iter 3: processed=0, enqueue (queue=3).
- Iter 4: processed=0, enqueue (queue=4).
- Iter 5: processed=0, enqueue (queue=5). Queue hits 5 → drain → processed=5. CAP CHECK 2: 5>=2 → break. **5 rows ingested when 2 was requested.**

If pool has < 5 layer2-OK candidates, the final drain at L1939 still processes whatever's queued — same leak shape, smaller magnitude.

### Skipped statuses (do NOT count toward cap, per spec — already correct in current code)

| Skip path | Line | Counter behavior |
|---|---|---|
| no URL → 'skipped' | L1795-1803 | continue, no enqueue, no processed++ ✓ |
| checkpoint text_ingest → 'skipped_ingested' | L1807-1815 | continue, no processed++ ✓ |
| anomalous scrape ckpt + body=NULL → 'skipped' | L1823-1833 | continue, no processed++ ✓ |
| graded probe unrelated → 'skipped_graded' | L1840-1856 | continue, no processed++ ✓ |
| body=NULL after scrape → no ingestion row | L1898-1906 | continue, no enqueue, no processed++ ✓ |
| layer1 reject (drained at chunk boundary L1735+) | persists 'skipped' | NOT counted ✓ |
| layer2 reject (inside drain) | L1695-1706 | persists 'skipped', NO processed++ ✓ |
| layer2 None (mixed-batch failure) | L1708-1712 | NO ingestion row, NO processed++ ✓ |

So the bug is **purely in cap-check timing**, not in counter semantics.

### Fix shape (~10 LOC)

Change CAP CHECK 1 (L1776) from `processed >= max_articles` to `processed + len(layer2_queue) >= max_articles`. The pending queue is committed work that WILL produce ok+failed rows on the next drain, so it must be charged against the cap budget at enqueue time, not at drain time.

```python
# L1776 BEFORE:
if max_articles is not None and processed >= max_articles:

# L1776 AFTER:
# Strict hard cap: in-flight queued rows count toward the cap because they
# WILL produce ok+failed ingestions on the next drain. Pre-fix this check
# was post-drain only, so up to LAYER2_BATCH_SIZE-1 rows could leak past
# the cap. See quick 260511-lmx investigation_findings.
if max_articles is not None and (processed + len(layer2_queue)) >= max_articles:
    logger.info(
        "max-articles cap reached (processed=%d + queued=%d >= %d); stopping --from-db loop.",
        processed, len(layer2_queue), max_articles,
    )
    break
```

CAP CHECK 2 (L1930) becomes redundant for the leak case but is harmless as a defensive belt-and-suspenders post-drain confirmation. **Leave it as-is** (surgical change rule — don't refactor what's working).

The final drain at L1939 still runs to flush the partial queue — that is correct behavior and not part of the leak (those rows were committed past the per-iter check).

### Why "processed" is the right counter (not a new "ok_failed_count")

Inside `_drain_layer2_queue()` the increment at L1758 (and the symmetric path inside the drain function near L1745-1755) only fires for layer2 verdict='ok' (or future non-reject). Layer2 'reject' rows write a 'skipped' ingestion at L1700-1706 with NO processed++. Layer2 'None' rows write NO ingestion row at L1712 with NO processed++. So `processed` is already "rows that committed an ok/failed/dry_run ingestions row" — exactly the spec definition. No new counter needed.

(`dry_run` ingestion status counts as processed today. Spec says cap is "ok+failed only". Dry-run is bypassed at L1788-1793 with a `continue` BEFORE enqueue, so it never reaches the queue — no impact on the fix. Keep dry-run semantics untouched per scope.)

### What this fix does NOT do (out of scope, do not touch)

- Does NOT change the candidate SQL (ir-4 scope).
- Does NOT change skip-status semantics (skipped paths continue to skip cap counting).
- Does NOT touch `tests/unit/test_ainsert_persistence_contract.py` (different concern).
- Does NOT touch `dry_run` behavior beyond confirming it stays bypassed before enqueue.
- Does NOT touch scan-mode `run()` at L689 (different code path; user reports were all `--from-db`).

</investigation_findings>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Reproduce bug, fix cap, write 4 mock-only tests, verify GREEN</name>
  <files>batch_ingest_from_spider.py, tests/unit/test_max_articles_hard_cap.py</files>

  <behavior>
    Pinning the post-fix contract — these 4 tests MUST be the function names in `tests/unit/test_max_articles_hard_cap.py`:

    1. `test_cap_excludes_skipped_layer1_rejects`
       - max_articles=3, 5 candidates: 2 layer1=reject + 3 layer2=ok.
       - Expected: 2 'skipped' ingestions (layer1) + 3 'ok' ingestions; processed counter = 3; loop exits naturally.
       - Asserts: cap-reached log line appears EXACTLY ONCE (or zero times if pool exhausts first); ok+failed count == 3.

    2. `test_cap_break_on_third_ok`
       - max_articles=3, 6 candidates ALL layer2=ok.
       - Expected: exactly 3 'ok' ingestions; rows 4-6 untouched; cap-reached log line appears.
       - Asserts: ingestions table has exactly 3 ok rows; 0 failed; 0 skipped; log captures "max-articles cap reached".

    3. `test_cap_with_mid_loop_failure_counts`
       - max_articles=3, 5 candidates layer2=ok; ingest_article side_effect: row1→ok, row2→failed (success=False), row3→ok, rows 4-5 not reached.
       - Expected: ok+failed = 3 (1+2); cap reached after row3.
       - Asserts: status counts {ok: 2, failed: 1}; cap-reached log present.

    4. `test_cap_pool_exhausted_before_reached`
       - max_articles=3, 2 candidates BOTH layer1=reject.
       - Expected: 2 'skipped' ingestions; loop exits via natural pool-exhaustion (no cap-reached log).
       - Asserts: ingestions table has 2 skipped; 0 ok+failed; cap-reached log NOT present.

    All 4 tests use `mocker.patch` on:
      - `lib.scraper.scrape_url` → returns ScrapeResult with body
      - `batch_ingest_from_spider.layer2_full_body_score` → returns predetermined verdicts
      - `batch_ingest_from_spider.layer1_classify_batch` (or whatever the chunk-boundary call is — grep before writing) → returns predetermined verdicts
      - `batch_ingest_from_spider.ingest_article` → AsyncMock with deterministic (success, wall, doc_confirmed) tuple
      - `batch_ingest_from_spider._load_hermes_env` → no-op
      - `batch_ingest_from_spider.get_deepseek_api_key` → "dummy"
      - LightRAG factory → mock returning AsyncMock with `finalize_storages` AsyncMock
    Use `:memory:` SQLite with the schema from `ingest_from_db` (CREATE TABLE ingestions … and articles + rss_articles fixtures). Pre-seed candidate rows directly via INSERT.

    Pattern reference: `tests/unit/test_batch_ingest_hash.py:test_classify_full_body_uses_scraper` (mocker.patch + sqlite3.connect(":memory:") fixture). Pattern reference: `tests/unit/test_batch_ingest_topic_filter.py` (header docstring style + dual-source schema).
  </behavior>

  <action>
    Execute these steps in strict order. Cite log file paths in SUMMARY.md.

    **Step 1 — Reproduce the bug (anti-fabrication evidence required).**

    1a. Add ONE temporary stderr line at the top of the for-loop in `ingest_from_db` (around L1773, immediately after `for i, ...`):
        ```python
        sys.stderr.write(f"[lmx-debug] iter={i} processed={processed} queue_len={len(layer2_queue)} max={max_articles}\n")
        ```
    1b. Run a local mock smoke that exercises this code path with `max_articles=2` and ≥5 layer2-OK candidates. Pre-fix expected: `iter=5 processed=0 queue_len=5` then drain bumps processed to 5 — leak.
        - Channel: write a small repro script at `.scratch/lmx-repro.py` that calls `ingest_from_db` with mocked layer2 + ingest_article. OR run a unit test temporarily marked xfail. Either is acceptable; pick whichever is cheaper.
        - Output: `.scratch/maxcap-prefix-<ts>.log` showing the leak pattern (>2 ingest rows when cap=2).
    1c. Capture the .log file path. SUMMARY.md MUST cite it with line numbers.
    1d. Remove the temporary stderr line. Verify with `git diff batch_ingest_from_spider.py` that ONLY the cap-check line is changing (Step 2 below).

    **Step 2 — Apply fix.**

    Edit `batch_ingest_from_spider.py` L1776-1781 (the per-iteration cap check ONLY):

    BEFORE:
    ```python
    if max_articles is not None and processed >= max_articles:
        logger.info(
            "max-articles cap reached (%d); stopping --from-db loop.",
            max_articles,
        )
        break
    ```

    AFTER:
    ```python
    # quick-260511-mxc: strict hard cap. Pre-fix this check was processed-only,
    # so queued-but-not-yet-drained rows leaked past the cap (up to
    # LAYER2_BATCH_SIZE-1 = 4 extra). Charging the in-flight queue against
    # the budget at enqueue time makes --max-articles a true per-article
    # hard cap on ok+failed (skipped statuses are excluded by their `continue`
    # branches above). See quick 260511-lmx investigation_findings.
    if max_articles is not None and (processed + len(layer2_queue)) >= max_articles:
        logger.info(
            "max-articles cap reached (processed=%d + queued=%d >= %d); stopping --from-db loop.",
            processed, len(layer2_queue), max_articles,
        )
        break
    ```

    Leave CAP CHECK 2 at L1930-1936 untouched (defensive belt-and-suspenders, harmless).
    Leave final drain at L1939 untouched.
    Leave scan-mode `run()` at L689 untouched.
    Leave skip branches untouched.

    **Step 3 — Write 4 mock-only tests.**

    Create `tests/unit/test_max_articles_hard_cap.py`:
    - Module docstring matching the style of `test_batch_ingest_topic_filter.py` (history + contract).
    - 4 tests with the function names in `<behavior>`.
    - Use `mocker` fixture from `pytest-mock`, `sqlite3.connect(":memory:")`, `tmp_path` if needed for checkpoint dir.
    - Pre-seed `articles` + `rss_articles` rows so the `_build_topic_filter_query` SELECT returns the desired candidate set.
    - Pre-seed `layer1_verdict` columns so layer1 chunk-drain runs but produces predetermined verdicts (or mock the layer1 entry point).
    - Mock `lib.scraper.scrape_url` to return ScrapeResult with body for layer2-ok candidates.
    - Mock `batch_ingest_from_spider.layer2_full_body_score` to return predetermined `Layer2Result(verdict='ok', ...)`.
    - Mock `batch_ingest_from_spider.ingest_article` with `mocker.AsyncMock(side_effect=...)` for per-row outcomes (Test 3).
    - Run `await ingest_from_db(topic="ai", min_depth=2, dry_run=False, max_articles=N)` and assert ingestions table state via `SELECT status, COUNT(*) FROM ingestions GROUP BY status`.
    - Use `caplog.at_level(logging.INFO)` to assert "max-articles cap reached" log line appears (or doesn't, per Test 4).
    - DO NOT touch `tests/unit/test_ainsert_persistence_contract.py`.

    Helper note: if `ingest_from_db` is hard to mock end-to-end (calls many external init paths), prefer factoring the mocking via `mocker.patch.multiple(...)` listing all modules that touch DeepSeek / LightRAG / network. Do NOT modify the production code to make it more testable — surgical change rule.

    **Step 4 — Verify tests GREEN.**

    Run from repo root:
    ```bash
    .venv/Scripts/python -m pytest tests/unit/test_max_articles_hard_cap.py -v 2>&1 | tee .scratch/maxcap-pytest-<ts>.log
    ```
    Expect: 4 passed, 0 failed.

    **Step 5 — Local post-fix smoke (anti-fabrication evidence required).**

    5a. Re-run the same Step 1b repro script (without the temporary stderr line) against the FIXED code with `max_articles=2`.
    5b. Output: `.scratch/maxcap-postfix-<ts>.log` showing exactly 2 ok+failed ingest rows (or fewer if pool exhausted).
    5c. SUMMARY.md MUST cite both pre-fix and post-fix log paths with line numbers showing the diff in row counts.

    NOTE on `scripts/local_e2e.sh`: there is no mode that exercises only the `--from-db` cap path against mocked LLMs/scrape — adding one would expand scope. The Step 1/5 mock-only repro script in `.scratch/lmx-repro.py` is the right channel for this fix. Document the exact command in SUMMARY.md so it's reproducible.

    **Step 6 — Commit (single atomic).**

    ```bash
    git add batch_ingest_from_spider.py tests/unit/test_max_articles_hard_cap.py
    git commit -m "fix(ingest-260511-mxc): --max-articles hard cap — count ok+failed only, exit cleanly when reached, eliminates unpredictable batch wall-clock"
    ```

    NOTE: commit slug `260511-mxc` is user-provided (NOT the quick_id `260511-lmx`). Use it verbatim in the commit subject.

    **Step 7 — Pre-push rebase.**

    ```bash
    git fetch origin main
    git rebase origin/main
    git push
    ```

    If rebase conflicts in `batch_ingest_from_spider.py`, resolve preserving BOTH the cap-check fix AND any peer changes (Quick A h09 race / Quick B DeepSeek timeout shouldn't touch L1776 but verify). Do NOT force-push without re-reading the merged file.
  </action>

  <verify>
    <automated>.venv/Scripts/python -m pytest tests/unit/test_max_articles_hard_cap.py -v</automated>

    Manual confirmations (executor must record in SUMMARY.md):
    - Pre-fix log `.scratch/maxcap-prefix-<ts>.log` cited with line numbers showing `processed=0 queue_len=5` pattern (leak reproduced).
    - Post-fix log `.scratch/maxcap-postfix-<ts>.log` cited showing exactly N or fewer ingest rows for `max_articles=N`.
    - `git diff origin/main -- batch_ingest_from_spider.py` shows ONLY the cap-check line modified (no adjacent refactoring).
    - `git log --oneline origin/main..HEAD` shows exactly ONE commit with subject starting `fix(ingest-260511-mxc):`.
  </verify>

  <done>
    - 4 pytest cases GREEN: `test_cap_excludes_skipped_layer1_rejects`, `test_cap_break_on_third_ok`, `test_cap_with_mid_loop_failure_counts`, `test_cap_pool_exhausted_before_reached`.
    - `batch_ingest_from_spider.py:1776` cap check uses `(processed + len(layer2_queue)) >= max_articles`.
    - Pre-fix smoke log shows leak (>N rows for cap=N). Post-fix smoke log shows exactly N or fewer rows.
    - Single atomic commit `fix(ingest-260511-mxc): --max-articles hard cap — count ok+failed only, exit cleanly when reached, eliminates unpredictable batch wall-clock` pushed to origin/main.
    - SUMMARY.md cites both .scratch log file paths with line numbers (no fabricated stats).
  </done>
</task>

</tasks>

<verification>
- pytest GREEN on `tests/unit/test_max_articles_hard_cap.py` (4/4 pass).
- `git diff` shows ONLY the cap-check line in `batch_ingest_from_spider.py` changed — no adjacent refactoring (surgical change rule).
- Pre-fix vs post-fix smoke log diff demonstrates the bug was real and the fix works (anti-fabrication: real .scratch log paths cited, not invented stats).
- Commit pushed cleanly after `git fetch && git rebase origin/main` (no peer-quick collisions on L1776).
</verification>

<success_criteria>
- `--max-articles N` is a strict hard cap on `ok+failed` ingestions; never exceeded across any pool composition.
- Skipped statuses (skipped, skipped_ingested, skipped_graded) DO NOT consume cap budget — verified by Test 1 + Test 4.
- Cap-reached log line emitted exactly once when cap fires (`processed=X + queued=Y >= N`).
- Pool-exhaustion path exits cleanly with no cap-reached log when fewer than N candidates produce ok+failed.
- No regression to scan-mode `run()` at L689 (untouched).
- No regression to skip branches (untouched).
- No regression to `tests/unit/test_ainsert_persistence_contract.py` (untouched).
</success_criteria>

<output>
After completion, create `.planning/quick/260511-lmx-fix-max-articles-cap-leak-strict-hard-ca/260511-lmx-SUMMARY.md` containing:
- Investigation findings confirmed (line numbers match plan).
- Pre-fix and post-fix .scratch log file paths with line-number citations.
- pytest run output excerpt (4/4 GREEN).
- Commit SHA and `git log --oneline` line.
- STATE.md row blurb for orchestrator to append (1-line: "Completed quick 260511-lmx — `--max-articles` strict hard cap on ok+failed only; eliminates batch wall-clock leak (was 5→14, now 5→5)").
</output>
