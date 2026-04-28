import os
import cognee_wrapper

import asyncio
import sys
from lightrag.lightrag import LightRAG, QueryParam
from config import RAG_WORKING_DIR, load_env

# Phase 7 D-09: embedding_func now lives in lib/; root shim re-exports for back-compat.
from lib import embedding_func
# Plan 05-00c Task 0c.3: LightRAG LLM routes to Deepseek via shared wrapper.
from lightrag_llm import deepseek_model_complete

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
        llm_model_func=deepseek_model_complete,
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
    
    # Cognee integration: Log query pattern
    try:
        await cognee_wrapper.log_query_pattern(query_text, "hybrid", True)
    except Exception as e:
        print(f"Warning: Cognee logging failed: {e}")
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
