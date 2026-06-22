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

# Embedding auth: lib.lightrag_embedding runs in Vertex-SA mode when
# GOOGLE_APPLICATION_CREDENTIALS is set (SA JSON auth, api_key unused) and in
# free-tier mode when only GEMINI_API_KEY is set. The guard below accepts
# EITHER — requiring GEMINI_API_KEY unconditionally was a stale check that
# wrongly blocked the Databricks deploy (Vertex SA + databricks_serving Claude,
# no GEMINI_API_KEY). LLM uses OMNIGRAPH_LLM_PROVIDER (deepseek/databricks/vertex).
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# Mirror lib.lightrag_embedding._is_vertex_mode() — SA mode needs no api key.
_VERTEX_SA_MODE = bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))


async def search(
    query_text: str,
    mode: str = "hybrid",
    only_context: bool = False,
    rag: LightRAG | None = None,
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
            (kb/api_routers/search.py, lib/research/stages/reasoner.py)
            keep their LLM-synthesized behavior unchanged.

    Returns:
        Response string from LightRAG.aquery.

    Raises:
        ValueError: If GEMINI_API_KEY is not present in the environment
            (required for the embedding path).
    """
    if not GEMINI_API_KEY and not _VERTEX_SA_MODE:
        raise ValueError(
            "No embedding auth: set GEMINI_API_KEY (free-tier) or "
            "GOOGLE_APPLICATION_CREDENTIALS (Vertex SA mode)."
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
    return await rag.aquery(
        query_text,
        param=QueryParam(mode=mode, only_need_context=only_context),
    )


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
