"""OmniGraph-Vault shared library. Internal-only; not a skill.

Asymmetric wrapping rationale (Hermes amendment 6):
LLM calls are wrapped from outside LightRAG's ``gemini_model_complete`` (a thin
proxy — we layer rate limiting, retry, and key rotation around it via
``lib.generate``).
Embeddings are owned entirely by ``lib.lightrag_embedding.embedding_func``
because LightRAG's embedding contract requires in-band multimodal logic (image
fetching, task prefix injection, ``types.Part.from_bytes``) that cannot be
layered externally.
"""
from .models import (
    INGESTION_LLM,
    VISION_LLM,
    SYNTHESIS_LLM,
    GITHUB_INGEST_LLM,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    EMBEDDING_MAX_TOKENS,
    RATE_LIMITS_RPM,
)

__all__ = [
    "INGESTION_LLM",
    "VISION_LLM",
    "SYNTHESIS_LLM",
    "GITHUB_INGEST_LLM",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "EMBEDDING_MAX_TOKENS",
    "RATE_LIMITS_RPM",
]
