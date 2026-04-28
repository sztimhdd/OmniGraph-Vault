import os
import cognee_wrapper

import asyncio
import sys
from lightrag.lightrag import LightRAG, QueryParam
from lightrag.llm.gemini import gemini_model_complete
from config import RAG_WORKING_DIR, load_env

# Phase 7 D-09: embedding_func now lives in lib/; root shim re-exports for back-compat.
from lib import embedding_func

# Phase 7: centralized model selection + key management.
from lib import SYNTHESIS_LLM, current_key, get_limiter

# Force standard Gemini API mode (not Vertex AI)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"

# Initialize environment
load_env()
# Phase 7: GEMINI_API_KEY now accessed via lib.current_key() — supports rotation.

async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
    """Wrapper for Gemini LLM model completion (Phase 7 lib/ rate limiting + rotation)."""
    async with get_limiter(SYNTHESIS_LLM):
        return await gemini_model_complete(
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=current_key(),
            model_name=SYNTHESIS_LLM,
            **kwargs,
        )

async def query_and_synthesize(query_text: str):
    """Initializes LightRAG and performs a query to synthesize a markdown response."""
    # Phase 7: key validation happens lazily in lib.current_key() via llm_model_func.
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        llm_model_name=SYNTHESIS_LLM,
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
