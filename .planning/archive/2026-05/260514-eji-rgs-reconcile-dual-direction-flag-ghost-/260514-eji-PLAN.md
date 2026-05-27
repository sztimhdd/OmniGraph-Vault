---
phase: 260514-eji
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/reconcile_ingestions.py
  - tests/unit/test_reconcile_rss.py
autonomous: true
requirements:
  - RGS-01  # reverse scan (failed-in-DB but processed-in-kv_store) → ghost++ + JSON line + exit 1
  - RGS-02  # backward-compat output (old "X mystery" substring still parses)
  - RGS-03  # ghost JSON line has discriminator "kind": "ghost"
  - RGS-04  # exit 1 when ghost > 0 OR mystery > 0
must_haves:
  truths:
    - "When status='failed' row's doc_id IS present in kv_store with status='processed' → ghost is detected and counted"
    - "When status='failed' row's doc_id is NOT in kv_store (or status != processed) → not counted (real failure, expected, ignored)"
    - "Old parsers grepping 'X mystery' substring continue to extract correctly from new output"
    - "Ghost JSON lines carry kind=\"ghost\" discriminator; mystery JSON lines stay unchanged (no kind field)"
    - "Exit code = 1 when ghost > 0 OR mystery > 0; exit code = 0 only when both = 0"
    - "All 22 existing tests still PASS unchanged after the refactor"
  artifacts:
    - path: "scripts/reconcile_ingestions.py"
      provides: "Dual-direction reconcile (forward ok→processed, reverse failed→processed=ghost)"
      contains: "_query_failed_rows"
    - path: "tests/unit/test_reconcile_rss.py"
      provides: "4 new ghost-detection tests + preserved 14 existing tests"
      contains: "test_ghost_success_failed_in_db_processed_in_kv"
  key_links:
    - from: "scripts/reconcile_ingestions.py:main"
      to: "_query_failed_rows + _load_doc_status"
      via: "reverse scan loop emitting ghost JSON lines with kind discriminator"
      pattern: "ghost_count.*kind.*ghost"
    - from: "tests/unit/test_reconcile_rss.py"
      to: "scripts.reconcile_ingestions.main"
      via: "subprocess-style invocation with --db-path + --storage-dir + --date flags"
      pattern: "reconcile_main|main\\("
---

<objective>
Extend `scripts/reconcile_ingestions.py` to detect "ghost success" race condition: rows in `ingestions` marked `status='failed'` whose corresponding `doc_id` IS present in `kv_store_doc_status.json` with `status='processed'` (LightRAG completed independently after the h09 retry budget gave up).

Purpose: Surface silent ghosts so the candidate-pool re-pick (which would burn paid Vision API budget) becomes visible in cron logs. Exit 1 → cron alert.

Output:
- `scripts/reconcile_ingestions.py` with a NEW `_query_failed_rows` function + reverse-scan loop in `main()` + extended summary line + extended exit code semantics.
- `tests/unit/test_reconcile_rss.py` with 4 new test cases (total 18, plus 8 in `test_reconcile_ingestions.py` = 26).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@scripts/reconcile_ingestions.py
@tests/unit/test_reconcile_rss.py
@tests/unit/test_reconcile_ingestions.py

<interfaces>
<!-- Existing helpers in scripts/reconcile_ingestions.py — reuse, do NOT reimplement -->

```python
def _compute_doc_id(url: str, source: str = "wechat") -> str
    # Returns f"{prefix}_{md5(url)[:10]}", prefix in {"wechat", "rss"}
    # Verified against prod kv_store on 2026-05-12 — DO NOT alter formula

def _load_doc_status(storage_dir: Path) -> dict[str, dict[str, Any]]
    # Loads kv_store_doc_status.json; returns {} if missing
    # Map shape: {doc_id: {"status": "processed"|"processing"|"failed"|...}}

def _query_ok_rows(db_path: Path, date_start: date, date_end: date) -> list[dict[str, Any]]
    # Existing forward-scan SQL: WHERE i.status='ok' + LEFT JOIN articles + rss_articles
    # Returns rows with keys: id, article_id, url, source, ingested_at
```

Existing mystery JSON line shape (DO NOT touch — backward compat for downstream parsers):
```json
{"art_id": int, "url": str, "doc_id": str, "actual_status": str, "ingested_at": str}
```

Existing summary line (DO NOT touch left side, only append after `|`):
```
2026-05-14: 1 ok rows / 1 matched / 0 mystery (wechat: 0, rss: 0)
```
</interfaces>

<test_fixture_helpers>
<!-- Existing helpers in tests/unit/test_reconcile_rss.py — reuse for new tests -->

```python
@pytest.fixture
def tmp_db() -> Path:           # pre-creates articles, rss_articles, ingestions tables
@pytest.fixture
def tmp_storage(tmp_path) -> Path:  # empty storage dir

def _add_article(db, art_id, url) -> None        # WeChat
def _add_rss_article(db, art_id, url) -> None    # RSS
def _add_ingestion(db, art_id, source, status, date_str="2026-05-12") -> None
def _set_doc_status(storage_dir, doc_id, status) -> None
```

The fixture's `ingestions.status` column is plain TEXT (no CHECK constraint) → `status='failed'` accepts cleanly.
</test_fixture_helpers>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add reverse-scan ghost detection + 4 new tests + verify all 26 pass</name>
  <files>scripts/reconcile_ingestions.py, tests/unit/test_reconcile_rss.py</files>
  <behavior>
    NEW behaviors (must be expressed as 4 new pytest cases first):

    - test_ghost_success_failed_in_db_processed_in_kv:
        GIVEN ingestions row {art_id=166, source='wechat', status='failed', url=U}
              AND kv_store has doc_id `wechat_{md5(U)[:10]}` → status='processed'
        WHEN  main() runs for 2026-05-14
        THEN  stdout contains "1 ghost (wechat: 1, rss: 0)"
        AND   stdout contains a JSON line with `"kind": "ghost"` AND `"art_id": 166` AND `"doc_id"` matching
        AND   exit code == 1

    - test_ghost_zero_normal_failed_no_match:
        GIVEN ingestions row status='failed' AND kv_store empty (doc_id missing)
        WHEN  main() runs
        THEN  stdout contains "0 ghost (wechat: 0, rss: 0)"
        AND   no ghost JSON line emitted
        AND   exit code == 0  (no mystery, no ghost)

    - test_ghost_mixed_with_mystery:
        GIVEN 1 ok-row whose doc_id is missing in kv_store (=> mystery)
              AND 1 failed-row whose doc_id IS processed in kv_store (=> ghost)
        WHEN  main() runs
        THEN  stdout contains "1 mystery" AND "1 ghost"
        AND   exactly 2 JSON lines: one WITHOUT kind field (mystery, backward-compat), one WITH `"kind": "ghost"`
        AND   exit code == 1

    - test_ghost_backward_compat_output_format:
        GIVEN any healthy day (1 ok row matched, no failed rows)
        WHEN  main() runs
        THEN  stdout contains the verbatim substring "1 ok rows / 1 matched / 0 mystery (wechat: 0, rss: 0)"
              (proves old grep parsers still extract; ghost section appended after `|`)
        AND   stdout ALSO contains "| 0 ghost (wechat: 0, rss: 0)" (proves new section present)

    All 22 existing tests (14 in test_reconcile_rss.py + 8 in test_reconcile_ingestions.py = 22 baseline → 18 + 8 = 26 after adding 4; counts via `pytest --collect-only`) must continue to PASS.
  </behavior>
  <action>
    ## Step 1 — RED: write the 4 new tests in tests/unit/test_reconcile_rss.py

    Append at the end of the file (after `test_reconcile_backward_compat`). Reuse existing `tmp_db`, `tmp_storage`, `_add_article`, `_add_rss_article`, `_add_ingestion`, `_set_doc_status`, `_compute_doc_id`. No new fixtures needed.

    For the mixed test, the mystery JSON line shape is the EXISTING shape (no `kind` field) — assertion uses `"kind" not in mystery_line and mystery_line["actual_status"] == "missing"`. The ghost line shape is the NEW shape with `"kind": "ghost"`.

    For ghost JSON line, assert keys: `kind == "ghost"`, `ingestion_id`, `art_id`, `source`, `doc_id`, `ingested_at` (per spec).

    Run pytest — expect 4 RED. Confirm failure messages reference missing "ghost" substring or exit code mismatch (NOT import errors).

    ## Step 2 — GREEN: extend scripts/reconcile_ingestions.py

    Surgical changes only. DO NOT touch existing forward-scan logic, JSON line shape, or `_compute_doc_id` / `_load_doc_status`.

    ### 2a. Add new SQL helper after `_query_ok_rows` (~ line 83)

    ```python
    def _query_failed_rows(
        db_path: Path, date_start: date, date_end: date
    ) -> list[dict[str, Any]]:
        """Reverse-scan companion to _query_ok_rows.

        Returns ingestions rows with status='failed' (h09 retry budget exhausted)
        for the date window, with URL recovered via the same LEFT JOIN pattern.
        Used to detect ghost successes (DB=failed but kv_store=processed).
        """
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT i.id AS id, i.article_id AS article_id, "
                "       COALESCE(a.url, r.url) AS url, i.source AS source, "
                "       i.ingested_at AS ingested_at "
                "FROM ingestions i "
                "LEFT JOIN articles a ON a.id = i.article_id AND i.source = 'wechat' "
                "LEFT JOIN rss_articles r ON r.id = i.article_id AND i.source = 'rss' "
                "WHERE i.status='failed' "
                "AND date(i.ingested_at) BETWEEN date(?) AND date(?) "
                "ORDER BY i.ingested_at",
                (date_start.isoformat(), date_end.isoformat()),
            )
            return [dict(r) for r in cur.fetchall()]
    ```

    Identical shape to `_query_ok_rows` except `WHERE i.status='failed'`. Pure copy + one-token change — DRY violation here is intentional (clarity > dedup for two-call sites).

    ### 2b. Extend main() — add reverse-scan loop AFTER the existing forward-scan loop, BEFORE the summary line

    Insert this block after the existing `for row in rows:` loop ends (around line 161, after the closing of the JSON dump for mystery) and BEFORE the `date_range = ...` computation:

    ```python
        # Reverse scan — ghost successes (DB=failed but kv_store=processed).
        # Independent SQL + accounting; does NOT touch mystery counters.
        failed_rows = _query_failed_rows(db_path, start_date, end_date)
        ghost_count = 0
        ghost_count_wechat = 0
        ghost_count_rss = 0
        for row in failed_rows:
            doc_id = _compute_doc_id(row["url"], row["source"]) if row["url"] else None
            if doc_id is None:
                continue
            entry = status_map.get(doc_id)
            actual = entry.get("status") if isinstance(entry, dict) else None
            if not (isinstance(actual, str) and actual.lower() == "processed"):
                continue  # real fail (expected); skip without counting
            ghost_count += 1
            if row["source"] == "rss":
                ghost_count_rss += 1
            else:
                ghost_count_wechat += 1
            sys.stdout.write(
                json.dumps(
                    {
                        "kind": "ghost",
                        "ingestion_id": row["id"],
                        "art_id": row["article_id"],
                        "source": row["source"],
                        "doc_id": doc_id,
                        "ingested_at": row["ingested_at"],
                    }
                )
                + "\n"
            )
    ```

    Notes:
    - URL-NULL guard (`if row["url"]`) handles the rare case where an `ingestions.article_id` orphans (no matching articles/rss_articles row). Forward-scan does not have this guard either, but ghost path runs against arbitrary historical failed rows where orphans are more plausible. Skip silently.
    - The ghost JSON line is a SEPARATE write call from the mystery line; their formats differ (mystery has no `kind`, ghost does). Backward compat preserved.

    ### 2c. Extend summary line — append `| N ghost (wechat: X, rss: Y)` always

    Replace the existing `sys.stdout.write(f"{date_range}: ...\n")` with:

    ```python
        sys.stdout.write(
            f"{date_range}: {ok_count} ok rows / "
            f"{processed_count} matched / {mystery_count} mystery "
            f"(wechat: {mystery_count_wechat}, rss: {mystery_count_rss}) "
            f"| {ghost_count} ghost "
            f"(wechat: {ghost_count_wechat}, rss: {ghost_count_rss})\n"
        )
    ```

    The space before `|` ensures the old substring `"0 mystery (wechat: 0, rss: 0)"` stays an intact substring of the new line. Old grep `"X mystery"` extractors are unaffected.

    ### 2d. Update exit code

    Replace `return 1 if mystery_count > 0 else 0` with:

    ```python
        return 1 if (mystery_count > 0 or ghost_count > 0) else 0
    ```

    ### 2e. Update module docstring

    Append one paragraph after the existing "Quick 260512-rrx" line:

    ```
    Quick 260514-eji: dual-direction reverse scan (status='failed' but
    kv_store=processed → ghost). Surfaces h09 race condition (DB lost,
    LightRAG completed asynchronously). Exit 1 on ghost > 0 alongside
    existing mystery > 0 alert.
    ```

    Update the Exit codes block:
    ```
    Exit codes:
        0 — zero mystery AND zero ghost (silent healthy day)
        1 — mystery > 0 OR ghost > 0 (cron logs surface details as JSON lines)
    ```

    ## Step 3 — Verify GREEN

    Run `pytest tests/unit/test_reconcile_rss.py tests/unit/test_reconcile_ingestions.py -v`. Expect 26 PASS, 0 FAIL.

    Note: `(wechat: 0, rss: 0)` appears twice in the extended summary line — once for mystery, once for ghost. Substring assertions in existing tests remain valid (substring match is non-exclusive); do NOT mistakenly try to "fix" passing tests that match this pattern.

    If any of the existing 22 break, the most likely cause is the summary-line format change. The old test `test_reconcile_backward_compat` asserts substring `"1 ok rows / 1 matched / 0 mystery"` — that substring IS preserved (left of the `|`). The other tests assert substrings like `"0 mystery"`, `"1 mystery"`, `"wechat: 0, rss: 0"` — all still present.

    If a test fails, fix the script (do NOT change the test). Loop until 26/26.

    ## Step 4 — py_compile sanity check

    `python -m py_compile scripts/reconcile_ingestions.py` → exit 0.

    ## Step 5 — git commit (explicit files, NEVER -A)

    ```bash
    git add scripts/reconcile_ingestions.py tests/unit/test_reconcile_rss.py
    git commit -m "$(cat <<'EOF'
    feat(reconcile): scope extend to ghost successes (status=failed but kv_store=processed)

    2026-05-14 09:22 ADT first ghost observed: id=166 retried 150 times in
    h09, marked status='failed' in DB, but LightRAG async pipeline
    completed 9 minutes later → kv_store status='processed'. Without
    dual-direction reconcile, these are silent gaps that cause the
    candidate-pool query to re-pick the article and burn paid Vision
    API budget on next cron.

    Hermes scan: 1 ghost / 188 LightRAG-processed rows = 0.5% historical
    rate, no accumulation. RETRY=300 (600s budget) deployed; expected to
    drop further. This change adds surfacing for ongoing observation.

    Changes:
    - Add _query_failed_rows() — reverse SQL companion to _query_ok_rows
    - main() reverse-scan loop emits JSON line with kind="ghost" discriminator
    - Summary line appends "| N ghost (wechat: X, rss: Y)" after old format
      (old grep "X mystery" parsers still extract correctly)
    - Exit code: 1 when ghost > 0 OR mystery > 0 (was: mystery > 0 only)
    - 4 new pytest cases in test_reconcile_rss.py; all 22 existing pass

    Memory: ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/project_ghost_success_observed_260514.md

    Out of scope (deferred):
    - Auto-repair (UPDATE ingestions SET status='ok' WHERE ...)
    - --ghost-as-warn flag (defer to v1.x if alert spam)
    - Cleanup 4 historical real RSS failures (separate v1.0.y task)
    EOF
    )"
    ```
  </action>
  <verify>
    <automated>python -m py_compile scripts/reconcile_ingestions.py &amp;&amp; pytest tests/unit/test_reconcile_rss.py tests/unit/test_reconcile_ingestions.py -v 2>&amp;1 | tail -40</automated>
  </verify>
  <done>
    - `python -m py_compile scripts/reconcile_ingestions.py` exits 0
    - `pytest tests/unit/test_reconcile_rss.py tests/unit/test_reconcile_ingestions.py -v` reports 26 passed, 0 failed
    - Summary line in mock fixture run contains substring `"1 ok rows / 1 matched / 0 mystery"` (left side preserved)
    - Summary line in mock fixture run contains substring `"| 0 ghost"` (right side new)
    - Mixed-scenario test asserts exactly 2 JSON lines: 1 mystery (no `kind` key) + 1 ghost (with `"kind": "ghost"`)
    - Exit code = 1 when ghost > 0 even if mystery = 0
    - One commit on `main` with files `scripts/reconcile_ingestions.py` and `tests/unit/test_reconcile_rss.py` only (verified by `git show --stat HEAD`)
  </done>
</task>

</tasks>

<verification>
1. Sanity compile:
   ```
   python -m py_compile scripts/reconcile_ingestions.py
   ```
2. Full unit run (26 = 18 in test_reconcile_rss.py + 8 in test_reconcile_ingestions.py):
   ```
   pytest tests/unit/test_reconcile_rss.py tests/unit/test_reconcile_ingestions.py -v
   ```
   Expect: `26 passed`.

3. Manual mock end-to-end (already covered by `test_ghost_mixed_with_mystery`):
   - Fixture: 2 ok-rows matched + 1 mystery (ok-row, doc missing) + 1 ghost (failed-row, doc processed)
   - Assert: stdout contains `"2 ok / 2 matched / 1 mystery"` AND `"1 ghost"` (NOTE: old test substring `"1 ok rows / 1 matched / 0 mystery"` is NOT this scenario; the spec's "2 ok / 2 matched / 1 mystery / 1 ghost" example is loose phrasing — the actual output line is `2 ok rows / 2 matched / 1 mystery (wechat: ..., rss: ...) | 1 ghost (...)`)
   - Assert: 2 JSON lines (mystery without `kind`, ghost with `kind`)
   - Assert: exit code = 1

4. Backward compat regression (covered by existing `test_reconcile_backward_compat` + new `test_ghost_backward_compat_output_format`):
   - Old `grep "X mystery"` substring extractor still matches.
</verification>

<success_criteria>
- [ ] All 26 unit tests PASS (22 existing + 4 new)
- [ ] `_query_failed_rows` helper exists in `scripts/reconcile_ingestions.py`
- [ ] Summary line appends `| N ghost (wechat: X, rss: Y)` (always present, even when ghost = 0)
- [ ] Old summary substring `"X ok rows / Y matched / Z mystery (wechat: ..., rss: ...)"` preserved verbatim left of `|`
- [ ] Ghost JSON lines carry `"kind": "ghost"` discriminator field
- [ ] Mystery JSON lines unchanged (no `kind` field — backward compat)
- [ ] Exit code = 1 when ghost > 0 OR mystery > 0; exit code = 0 only when both = 0
- [ ] One commit on `main`, message starts with `feat(reconcile): scope extend to ghost successes`, body cites 2026-05-14 observation + memory file path
- [ ] LOC delta in `scripts/reconcile_ingestions.py` roughly +50/-5 (per spec); LOC in test file +60-80
- [ ] No edits outside the two listed files
</success_criteria>

<output>
After completion, the orchestrator will collect:
- Commit SHA
- pytest summary (`26 passed`)
- Final summary line printed by a sample run
</output>
