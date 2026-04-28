"""LightRAG hybrid-mode query wrapper for the omnigraph_search skill.

Trimmed copy of query_lightrag.py — returns raw LightRAG retrieval text only,
no synthesis layer, no memory layer (per PRD D-G09). See
.planning/phases/06-graphify-addon-code-graph/06-RESEARCH.md §Pattern 3 for
the rationale and line-level source lineage.
"""

from __future__ import annotations

import asyncio
import os
import sys

import numpy as np

from lightrag.lightrag import LightRAG, QueryParam
from lightrag.llm.gemini import gemini_model_complete, gemini_embed
from lightrag.utils import wrap_embedding_func_with_attrs

from config import RAG_WORKING_DIR, load_env

# Force standard Gemini API mode (not Vertex AI) — matches query_lightrag.py.
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"

load_env()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


async def _llm_model_func(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list | None = None,
    **kwargs,
) -> str:
    """Gemini LLM completion wrapper — same signature as query_lightrag.py L19."""
    return await gemini_model_complete(
        prompt,
        system_prompt=system_prompt,
        history_messages=list(history_messages or []),
        api_key=GEMINI_API_KEY,
        model_name="gemini-2.5-flash-lite",
        **kwargs,
    )


@wrap_embedding_func_with_attrs(
    embedding_dim=768,
    send_dimensions=True,
    max_token_size=2048,
    model_name="gemini-embedding-001",
)
async def _embedding_func(texts: list[str], **kwargs) -> np.ndarray:
    """Gemini embedding wrapper — same signature as query_lightrag.py L36."""
    return await gemini_embed.func(
        texts,
        api_key=GEMINI_API_KEY,
        model="gemini-embedding-001",
        embedding_dim=768,
    )


async def search(query_text: str, mode: str = "hybrid") -> str:
    """Query LightRAG at RAG_WORKING_DIR and return the raw retrieval text.

    Args:
        query_text: Natural-language question.
        mode: LightRAG retrieval mode — one of 'naive', 'local', 'global',
            'hybrid' (default), 'mix'.

    Returns:
        Response string from LightRAG.aquery.

    Raises:
        ValueError: If GEMINI_API_KEY is not present in the environment.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in environment.")

    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=_llm_model_func,
        embedding_func=_embedding_func,
        llm_model_name="gemini-2.5-flash-lite",
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
