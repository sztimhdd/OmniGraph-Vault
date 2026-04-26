import os
import cognee_wrapper

import asyncio
import sys
import numpy as np
from lightrag.lightrag import LightRAG, QueryParam
from lightrag.llm.gemini import gemini_model_complete, gemini_embed
from lightrag.utils import wrap_embedding_func_with_attrs
from config import RAG_WORKING_DIR, load_env

# Force standard Gemini API mode (not Vertex AI)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"

# Initialize environment
load_env()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
    """Wrapper for Gemini LLM model completion."""
    return await gemini_model_complete(
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
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
async def embedding_func(texts: list[str], **kwargs) -> np.ndarray:
    """Wrapper for Gemini embedding function."""
    return await gemini_embed.func(
        texts, api_key=GEMINI_API_KEY, model="gemini-embedding-001",
        embedding_dim=768,
    )

async def query_and_synthesize(query_text: str):
    """Initializes LightRAG and performs a query to synthesize a markdown response."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in environment.")

    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        llm_model_name="gemini-2.5-flash-lite",
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
