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
import logging
import os
import sys
import time

from lightrag.lightrag import LightRAG, QueryParam

from config import RAG_WORKING_DIR
from lib.cli_bootstrap import bootstrap_cli

bootstrap_cli()

from lightrag_embedding import embedding_func as _embedding_func
# Quick 260509-s29 Wave 3: route via OMNIGRAPH_LLM_PROVIDER dispatcher
# (defaults to deepseek; Plan 05-00c Task 0c.3 routing preserved as default).
from lib.llm_complete import get_llm_func

_log = logging.getLogger(__name__)

# Embedding auth (260819 de-Google): the primary path is local BGE-M3
# (OMNIGRAPH_LOCAL_EMBED=1 — Aliyun embed-server or its authenticated WAN
# proxy; no credential file). Legacy Gemini/Vertex modes are still accepted
# for pre-260819 deployments. LLM uses OMNIGRAPH_LLM_PROVIDER
# (deepseek/databricks/vertex) independently of the embedding side.
_LOCAL_EMBED_MODE = os.environ.get("OMNIGRAPH_LOCAL_EMBED") == "1"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# Mirror lib.lightrag_embedding._is_vertex_mode() — SA mode needs no api key.
_VERTEX_SA_MODE = bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))

# This caps graph/entity and vector-chunk retrieval candidates for explicit,
# bounded wrapper calls. It does not bound the size of LightRAG's returned
# context.
MAX_TOP_K = 10


async def search(
    query_text: str,
    mode: str = "hybrid",
    only_context: bool = False,
    rag: LightRAG | None = None,
    *,
    top_k: int | None = None,
) -> str:
    """Query LightRAG at RAG_WORKING_DIR and return the retrieval text.

    Args:
        query_text: Natural-language question.
        mode: LightRAG retrieval mode — one of 'naive', 'local', 'global',
            'hybrid' (default), 'mix'.
        only_context: When True, skip the LLM synthesis layer and return the
            raw retrieved context (entities + relations + chunks +
            reference list, with embedded ``file_path`` markers carrying the
            10-char hex article hash). When False (default), return the
            LLM-synthesized answer text. Additive — pre-existing callers
            callers that omit the flag keep their LLM-synthesized behavior;
            the internal reasoner explicitly requests raw context.
        top_k: Optional maximum number of graph/entity and vector-chunk
            retrieval candidates. When supplied, it is passed as both
            LightRAG ``top_k`` and ``chunk_top_k``; when omitted, preserve
            LightRAG's standard QueryParam defaults. Supplied values must be
            a non-bool integer from 1 through ``MAX_TOP_K``. This does not
            constrain total returned-context size.

    Returns:
        Response string from LightRAG.aquery.

    Raises:
        ValueError: If GEMINI_API_KEY is not present in the environment
            (required for the embedding path).
    """
    if not _LOCAL_EMBED_MODE and not GEMINI_API_KEY and not _VERTEX_SA_MODE:
        raise ValueError(
            "No embedding auth: set OMNIGRAPH_LOCAL_EMBED=1 (local BGE-M3, "
            "primary), or GEMINI_API_KEY / GOOGLE_APPLICATION_CREDENTIALS "
            "(legacy Gemini modes)."
        )

    if top_k is not None and (
        type(top_k) is not int or not 1 <= top_k <= MAX_TOP_K
    ):
        raise ValueError(
            f"top_k must be an integer from 1 to {MAX_TOP_K}"
        )

    if rag is None:
        # CLI fallback (skill_runner / `python -m omnigraph_search.query`):
        # build a one-shot LightRAG. Production callers (kb-api routers) reach
        # LightRAG via synthesize_response which holds the lifespan-pinned lock.
        rag = LightRAG(
            working_dir=RAG_WORKING_DIR,
            llm_model_func=get_llm_func(),
            embedding_func=_embedding_func,
        )
        if hasattr(rag, "initialize_storages"):
            await rag.initialize_storages()
    param_kwargs = {"mode": mode, "only_need_context": only_context}
    if top_k is not None:
        param_kwargs["top_k"] = top_k
        param_kwargs["chunk_top_k"] = top_k
    return await rag.aquery(query_text, param=QueryParam(**param_kwargs))


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
