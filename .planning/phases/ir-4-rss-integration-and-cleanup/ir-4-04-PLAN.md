# ir-4 W4 — Retire `enrichment/rss_ingest.py` + step_7 unification (LF-5.1 effective)

**Commit:** `9ff330d`
**Files:** 7 changed, +104 / -944

## Goal

Delete the legacy RSS ingest pipeline (translate → ainsert) and collapse
step_7's two parallel sub-commands (KOL via batch_ingest_from_spider, RSS
via rss_ingest.py) into a single dual-source invocation. Drop the
`max_rss` parameter — the candidate pool is now unified.

## Deliverables

### Deletions

- `enrichment/rss_ingest.py` (-434 lines)
- `tests/unit/test_rss_ingest_5stage.py` (-452 lines)

### Edits

- `enrichment/orchestrate_daily.py`:
    - `step_7_ingest_all` signature: drop `max_rss` parameter.
    - Body: drop `rss_cmd` block + RSS `_run()` call. Combined-success
      collapses to `kol_r.success`. Summary string: `dual-source: <kol summary>`.
    - `run()` signature: drop `max_rss` parameter + drop from step_7
      dispatch.
    - `main()` argparse: drop `--max-rss` option. `--max-kol` help text
      clarifies it now caps the dual-source pool.
- `enrichment/run_enrich_for_id.py:86`: doc comment updated. Pre-ir-4
  pointed at "rss_ingest.py's direct translate → ainsert path"; now
  points at `batch_ingest_from_spider`'s `--from-db` dual-source pipeline.
- `scripts/local_e2e.sh`:
    - Top docstring `Modes:` section: `rss` mode marked DEPRECATED;
      `kol` mode docstring updated to reflect dual-source coverage.
    - `KOL_SCAN_DB_PATH` env doc: removed pre-ir-4 reference to
      rss_ingest reading the DB.
    - DeepSeek-blocked-by-corp caveat: `rss_ingest.py` removed (file gone).
    - `rss)` case body: replaced `python -m enrichment.rss_ingest` with a
      4-line migration hint (echo + `EXIT=0`). Tells operators to use
      `bash scripts/local_e2e.sh kol` for both sources.
    - Mode validation status table updated.

### Tests

- `tests/unit/test_orchestrate_daily.py`:
    - `test_step_flag_runs_only_that_step` `other` skipped tuple pruned
      to 7 active steps (drops `2_classify_rss` from W3).
    - `test_max_kol_appended_to_kol_cmd` → renamed
      `test_max_kol_appended_to_unified_cmd`. Asserts exactly ONE
      batch_ingest_from_spider invocation and ZERO rss_ingest.py
      invocations.
    - `test_max_rss_appended_to_rss_cmd` deleted (no more max_rss).
    - `test_step_7_does_not_invoke_legacy_rss_ingest` (new): regression
      guard.
    - `test_run_signature_drops_max_rss` (new): inspect.signature pin
      so a future revert that re-adds max_rss fails loudly.
- `tests/unit/test_kol_scan_db_path_override.py`: drop
  `("enrichment.rss_ingest", "DB")` parametrize entry.

## Local validation — PASS

- 105/105 PASS across all ir-4 testsuites
  (test_orchestrate_daily 14, test_kol_scan_db_path_override 19,
   test_dual_source_dispatch 16, test_persist_body_pre_classify 3,
   test_batch_ingest_topic_filter 24, test_migration_008_idempotent 13,
   test_article_filter 16). See `.scratch/ir-4-w4-pytest.log`.
- Grep verify: `grep -rn "rss_ingest|step_2_classify_rss"` across
  `*.{py,sh,json,yaml,yml}`: zero active code references remain. All
  hits are retirement comments / regression guards.
- Harness rss-mode hint: EXIT=0, prints migration hint pointing at kol
  mode. See `.scratch/ir-4-w4-rss-mode.log`.
- Harness kol mode regression: EXIT=0, total inputs=1749 unchanged.
