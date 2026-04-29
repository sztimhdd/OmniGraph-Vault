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
