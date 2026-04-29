"""Central Gemini model registry.

Post-Hermes-Review Amendment 1 (D-02 SUPERSEDED): model names are pure string
constants. Single-user + git-as-deploy means ``git revert && push && pull-on-remote``
IS the rollback mechanism; env overrides were speculative future-proofing.
D-08 (OMNIGRAPH_RPM_<MODEL>) remains — that is for future paid-tier upgrade
and lives in lib/rate_limit.py.
"""

INGESTION_LLM    = "gemini-2.5-flash"
VISION_LLM       = "gemini-3.1-flash-lite-preview"
SYNTHESIS_LLM    = "gemini-2.5-flash-lite"
# D-05: GitHub ingestion preserves preview model.
GITHUB_INGEST_LLM = "gemini-3.1-flash-lite-preview"

# D-10: matches production reality (lightrag_embedding.py is already on -2).
EMBEDDING_MODEL    = "gemini-embedding-2"
EMBEDDING_DIM      = 3072   # full-capacity dim for gemini-embedding-2
EMBEDDING_MAX_TOKENS = 8192

# Free-tier RPM caps verified 2026-04-28. Override per model via env
# OMNIGRAPH_RPM_<MODEL_UPPER_UNDERSCORED> (D-08 retained — paid-tier upgrade).
# D-10: both embedding-001 (legacy) and embedding-2 (current prod) kept for back-compat.
RATE_LIMITS_RPM: dict[str, int] = {
    "gemini-2.5-pro":                5,
    "gemini-2.5-flash":              10,
    "gemini-2.5-flash-lite":         15,
    "gemini-3.1-flash-lite-preview": 30,
    "gemini-embedding-001":          60,
    "gemini-embedding-2":            100,
}

# Phase 5-00b R2 regression guard. Free-tier requests-per-DAY caps verified
# 2026-04-29. A Phase 7 lib/models.py edit silently swapped INGESTION_LLM +
# VISION_LLM to flash-lite (20 RPD) — killing 5-hr batches on the 5th article.
# tests/test_models_rpd_floor.py asserts production LLMs stay above the floor.
RATE_LIMITS_RPD: dict[str, int] = {
    "gemini-2.5-pro":                 50,
    "gemini-2.5-flash":              250,
    "gemini-2.5-flash-lite":          20,    # ⚠ below PRODUCTION_RPD_FLOOR — do NOT use for ingestion/vision
    "gemini-3.1-flash-lite-preview": 1500,
    "gemini-embedding-001":         1000,
    "gemini-embedding-2":           1000,
}

# Minimum RPD for a model to be allowed on the ingestion hot path (INGESTION_LLM,
# VISION_LLM). 250 reflects "can process a ~200-article batch in one day with
# room for retries". Enforced by tests/test_models_rpd_floor.py.
PRODUCTION_RPD_FLOOR: int = 250
