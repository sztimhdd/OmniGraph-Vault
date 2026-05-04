# Phase 19 — Deferred Items

Pre-existing test failures observed during the Plan 19-00 regression gate. None of these were introduced by Wave 0 (requirements.txt append + 3 new RED stub files). All live in test files last touched by phases 5, 11, and 13. Logged here for future triage; not Phase 19's responsibility.

Regression command (run 2026-05-04 after Plan 19-00):

```
venv/Scripts/python -m pytest tests/ \
  --ignore=tests/unit/test_scraper.py \
  --ignore=tests/unit/test_batch_ingest_hash.py \
  --ignore=tests/unit/test_rss_schema_migration.py
```

Result: **12 failed, 458 passed** (~87s)

## Failing Tests (pre-existing, out of Phase 19 scope)

| File | Test | Last touched by |
|------|------|-----------------|
| `tests/integration/test_bench_integration.py` | `test_text_ingest_over_threshold_fails_gate` | Phase 11 (e7975b9) |
| `tests/integration/test_bench_integration.py` | `test_live_gate_run` | Phase 11 (e7975b9) |
| `tests/unit/test_lightrag_embedding.py` | `test_embedding_func_reads_current_key` | Phase 5 (7122b8a) |
| `tests/unit/test_lightrag_embedding_rotation.py` | `test_single_key_fallback` | Phase 5 (7122b8a) |
| `tests/unit/test_lightrag_embedding_rotation.py` | `test_round_robin_two_keys` | Phase 5 (7122b8a) |
| `tests/unit/test_lightrag_embedding_rotation.py` | `test_429_failover_within_single_call` | Phase 5 (7122b8a) |
| `tests/unit/test_lightrag_embedding_rotation.py` | `test_both_keys_429_raises` | Phase 5 (7122b8a) |
| `tests/unit/test_lightrag_embedding_rotation.py` | `test_non_429_error_does_not_rotate` | Phase 5 (7122b8a) |
| `tests/unit/test_lightrag_embedding_rotation.py` | `test_empty_backup_env_var_treated_as_no_backup` | Phase 5 (7122b8a) |
| `tests/unit/test_siliconflow_balance.py` | `test_check_siliconflow_balance_success` | Phase 13 (f62d94a) |
| `tests/unit/test_siliconflow_balance.py` | `test_authorization_header_sent` | Phase 13 (f62d94a) |
| `tests/unit/test_text_first_ingest.py` | `test_parent_ainsert_content_has_references_not_descriptions` | Phase 10 area |

## Rationale for Deferral

- CLAUDE.md Surgical Changes rule: fix only orphans caused by the current task's changes.
- Plan 19-00 scope: dependency pin + 3 RED test stubs. No production code touched.
- Phase 19 scope: SCR-01..07, SCH-01..02 — none of the above 12 tests relate to scraper or schema.
- All 12 failures pre-date Phase 19 commits `784f740`, `88c2e3e`, `6f56d93` (confirmed via `git log`).

## Next Steps

- Not a Phase 19 concern. Surface to future quick-task or phase owner during a green-baseline sweep.
- If any of these start masking real Phase 19 regressions, escalate via a `/gsd:quick` task.
