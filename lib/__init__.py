"""OmniGraph-Vault shared library. Internal-only; not a skill.

Asymmetric wrapping rationale (Hermes amendment 6):
LLM calls are wrapped from outside LightRAG's ``gemini_model_complete`` (a thin
proxy — we layer rate limiting, retry, and key rotation around it via
``lib.generate``).
Embeddings are owned entirely by ``lib.lightrag_embedding.embedding_func``
because LightRAG's embedding contract requires in-band multimodal logic (image
fetching, task prefix injection, ``types.Part.from_bytes``) that cannot be
layered externally.

Defect D (quick 260510-l14): ``deepseek_model_complete`` is NOT re-exported
from this package. Importing it eagerly here forced every ``import lib``
caller to require ``DEEPSEEK_API_KEY`` even for Gemini/Vertex-only workloads
(the documented "Phase 5 cross-coupling" / Hermes FLAG 2). Use the full path
instead:
    from lib.llm_deepseek import deepseek_model_complete
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
from .api_keys import (
    current_key,
    rotate_key,
    on_rotate,
    load_keys,
    current_embedding_key,
    rotate_embedding_key,
    load_embedding_keys,
)
from .rate_limit import get_limiter
from .llm_client import generate, generate_sync, aembed
from .lightrag_embedding import embedding_func

__all__ = [
    "INGESTION_LLM",
    "VISION_LLM",
    "SYNTHESIS_LLM",
    "GITHUB_INGEST_LLM",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "EMBEDDING_MAX_TOKENS",
    "RATE_LIMITS_RPM",
    "current_key",
    "rotate_key",
    "on_rotate",
    "load_keys",
    "current_embedding_key",
    "rotate_embedding_key",
    "load_embedding_keys",
    "get_limiter",
    "generate",
    "generate_sync",
    "aembed",
    "embedding_func",
]
