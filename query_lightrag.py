import os

import asyncio
import sys
from lightrag.lightrag import LightRAG, QueryParam
from config import RAG_WORKING_DIR, load_env

# Phase 7 D-09: embedding_func now lives in lib/; root shim re-exports for back-compat.
from lib import embedding_func
# Quick 260509-s29 Wave 3: route via OMNIGRAPH_LLM_PROVIDER dispatcher
# (defaults to deepseek; Plan 05-00c Task 0c.3 routing preserved as default).
from lib.llm_complete import get_llm_func

# Force standard Gemini API mode (not Vertex AI)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"

# Initialize environment
load_env()
# Phase 7: GEMINI_API_KEY still used for EMBEDDING (via lib.embedding_func) —
# LLM completion now uses DEEPSEEK_API_KEY via lightrag_llm.

async def query_and_synthesize(query_text: str):
    """Initializes LightRAG and performs a query to synthesize a markdown response."""
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=get_llm_func(),
        embedding_func=embedding_func,
        llm_model_name="deepseek-v4-flash",
    )
    
    # Ensure storages are initialized (for newer versions of LightRAG)
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
        
    # Query using 'hybrid' mode for a balanced global and local context synthesis
    # Mode options: "local", "global", "hybrid", "naive", "mix"
    param = QueryParam(mode="hybrid")
    
    response = await rag.aquery(query_text, param=param)
    return response

async def main():
    if len(sys.argv) < 2:
        print("Usage: python query_lightrag.py \"<your query>\"")
        sys.exit(1)
        
    query = sys.argv[1]
    
    try:
        print(f"--- Querying LightRAG ---\nQuery: {query}\n")
        response = await query_and_synthesize(query)
        print("\n--- Synthesized Response ---\n")
        print(response)
    except Exception as e:
        print(f"Error during query: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
