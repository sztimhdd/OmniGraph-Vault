# Phase 10 — Deferred Items

Pre-existing failures discovered during Plan 10-00 execution that are OUT OF
SCOPE (no files from these test targets were modified). Logged for future phases.

## Pre-existing unit test failures (10 total — confirmed pre-existing on clean HEAD)

All failures exist on baseline HEAD prior to Plan 10-00 edits. They trace to
earlier unrelated work (model constant rename, Gemini embedding key rotation
refactor) and are NOT regressions caused by this plan.

### `tests/unit/test_lightrag_embedding.py` — 1 failure
- `test_embedding_func_reads_current_key`

### `tests/unit/test_lightrag_embedding_rotation.py` — 6 failures
- `test_single_key_fallback`
- `test_round_robin_two_keys`
- `test_429_failover_within_single_call`
- `test_both_keys_429_raises`
- `test_non_429_error_does_not_rotate`
- `test_empty_backup_env_var_treated_as_no_backup`

### `tests/unit/test_models.py` — 3 failures
- `test_ingestion_llm_is_pure_constant` — expects `gemini-2.5-flash-lite`, got `gemini-2.5-flash`
- `test_vision_llm_is_pure_constant` — similar constant drift
- `test_no_model_env_override` — similar constant drift

**Root cause (tentative):** `lib/models.py` model name constants appear to have
drifted from what the tests encode. This is Phase 7 territory (model-key management).

**Recommendation:** Address in a dedicated `tests/unit` rebase plan (maybe
Phase 7 cleanup or a Phase 10 tail plan) that either
  (a) updates the tests to reflect the current canonical model names, or
  (b) reverts `lib/models.py` to match the tested contract.

Plan 10-00 explicitly DID NOT touch any of these files — scope boundary upheld.
