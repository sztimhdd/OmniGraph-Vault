"""LightRAG hybrid-mode query wrapper for the omnigraph_search skill.

Trimmed copy of query_lightrag.py — returns raw LightRAG retrieval text only,
no synthesis layer, no memory layer (per PRD D-G09). See
.planning/phases/06-graphify-addon-code-graph/06-RESEARCH.md §Pattern 3 for
the rationale and line-level source lineage.

Phase 5 alignment: uses the shared lightrag_embedding.py module (gemini-embedding-2,
3072 dims) so it reads the same NanoVectorDB index as all other query paths.
"""

from __future__ import annotations

import asyncio
import os
import sys

from lightrag.lightrag import LightRAG, QueryParam

from config import RAG_WORKING_DIR, load_env
from lightrag_embedding import embedding_func as _embedding_func
# Quick 260509-s29 Wave 3: route via OMNIGRAPH_LLM_PROVIDER dispatcher
# (defaults to deepseek; Plan 05-00c Task 0c.3 routing preserved as default).
from lib.llm_complete import get_llm_func

# Force standard Gemini API mode (not Vertex AI) — matches query_lightrag.py.
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"

load_env()
# GEMINI_API_KEY is still required for EMBEDDING (_embedding_func). LLM now
# uses DEEPSEEK_API_KEY, validated at lib.llm_deepseek import time.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


async def search(query_text: str, mode: str = "hybrid") -> str:
    """Query LightRAG at RAG_WORKING_DIR and return the raw retrieval text.

    Args:
        query_text: Natural-language question.
        mode: LightRAG retrieval mode — one of 'naive', 'local', 'global',
            'hybrid' (default), 'mix'.

    Returns:
        Response string from LightRAG.aquery.

    Raises:
        ValueError: If GEMINI_API_KEY is not present in the environment
            (required for the embedding path).
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in environment.")

    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=get_llm_func(),
        embedding_func=_embedding_func,
        llm_model_name="deepseek-v4-flash",
    )
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
    return await rag.aquery(query_text, param=QueryParam(mode=mode))


def main() -> None:
    """CLI entry point invoked by skills/omnigraph_search/scripts/query.sh."""
    if len(sys.argv) < 2:
        print(
            "Usage: python -m omnigraph_search.query '<question>' [mode]",
            file=sys.stderr,
        )
        sys.exit(1)
    question = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "hybrid"
    try:
        print(asyncio.run(search(question, mode=mode)))
    except Exception as exc:  # noqa: BLE001 - surface all errors to caller
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
