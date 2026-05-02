# Phase 13 Deferred Items

Out-of-scope failures discovered during Phase 13 execution (2026-05-02). These
existed BEFORE Phase 13 changes and are verified pre-existing (git stash
reproduction against commit 031e045).

## Pre-existing failures

1. `tests/unit/test_models.py::test_ingestion_llm_is_pure_constant`
   `test_vision_llm_is_pure_constant`, `test_no_model_env_override`
   - Expect INGESTION_LLM == "gemini-2.5-flash-lite" but actual value is
     "gemini-2.5-flash". Likely upstream model constant change from a later
     phase not yet reflected in these tests.

2. `tests/unit/test_lightrag_embedding.py::test_embedding_func_reads_current_key`
   `tests/unit/test_lightrag_embedding_rotation.py::test_*` (6 tests)
   - Mock does not accept `vertexai` kwarg added by Phase 16 Vertex migration.
     Test needs `**kwargs` on the mock signature.

## Why deferred

Per Phase 13 scope boundary: these failures are in modules unrelated to vision
cascade + balance checks. Fixing them would violate the surgical-changes
principle. They should be addressed in a targeted Phase 16 or Phase 18
maintenance task.
