# ir-4 W3 — Retire `enrichment/rss_classify.py` (LF-5.2 effective)

**Commit:** `4cc3757`
**Files:** 8 changed, +45 / -796

## Goal

Delete the legacy DeepSeek-only RSS classifier and rewire upstream callers
to expect 8 active orchestrator steps (was 9). RSS classification now
happens inside Layer 1 of `batch_ingest_from_spider`'s `--from-db`
dual-source candidate SQL (W1).

## Deliverables

### Deletions

- `enrichment/rss_classify.py` (-229 lines)
- `tests/unit/test_rss_classify.py` (-257 lines)
- `tests/unit/test_rss_classify_fullbody.py` (-288 lines)

### Edits

- `enrichment/orchestrate_daily.py`:
    - Delete `step_2_classify_rss` function definition.
    - Drop `("2_classify_rss", step_2_classify_rss)` from steps list.
    - Numeric step IDs stay non-contiguous (1, 3, 4, ..., 9) so cron
      history that references "step 2" cannot accidentally re-route.
- `scripts/register_phase5_cron.sh`:
    - Delete the `add_job "rss-classify"` block.
    - Replaced with operator note: "existing Hermes deploys must run
      `hermes cron remove <rss-classify-id>` manually" (script is
      idempotent for adds, not removes).
- `scripts/local_e2e.sh`: docstring DeepSeek-blocked-by-corp note updated
  to drop the `rss_classify.py` reference (file gone).
- `tests/unit/test_orchestrate_daily.py`:
    - `test_nine_step_functions_defined` →
      `test_eight_active_step_functions_defined` (drops
      `step_2_classify_rss` from expected set).
    - `test_step_2_classify_rss_retired` (new): regression guard via
      `not hasattr(od, "step_2_classify_rss")`.
    - `test_success_path_traverses_all_9_steps` expected set updated to 8.
    - `test_dry_run_prints_without_subprocess` `len(out["results"]) == 8`.
    - `test_skip_scan_skips_three_steps` expected-ran tuple updated to 5
      active steps; added regression guard against `2_classify_rss`
      reappearing.
- `tests/unit/test_kol_scan_db_path_override.py`: drop
  `("enrichment.rss_classify", "DB")` parametrize entry.

## Local validation — PASS

- 106/106 PASS across W1+W2+W3 testsuites. See `.scratch/ir-4-w3-pytest.log`.
- Grep verify: `grep -rn "rss_classify|step_2_classify_rss"` across
  `*.{py,sh,json,yaml,yml}`: zero active code references. All hits are
  retirement comments / regression guards / commit messages.
- Harness regression smoke: EXIT=0, total inputs=1749 unchanged. See
  `.scratch/ir-4-w3-kol-dryrun.log`.

## Operator note

`enrichment/rss_ingest.py:225,229` still mention rss_classify in
comments. The whole file retires in W4 — leaving those comments alone
here avoids churn on a file scheduled for deletion.
