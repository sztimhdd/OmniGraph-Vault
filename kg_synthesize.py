import os
import json
import cognee
import asyncio
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import time

from config import RAG_WORKING_DIR, load_env, CANONICAL_MAP_FILE
load_env()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not found.")
    sys.exit(1)

# FORCE CONFIGURATION
cognee.config.llm_api_key = GEMINI_API_KEY
cognee.config.llm_provider = "gemini"
cognee.config.llm_model = "gemini-2.5-flash"
cognee.config.structured_output_backend = "gemini"
os.environ["COGNEE_LLM_API_KEY"] = GEMINI_API_KEY
os.environ["LITELLM_API_KEY"] = GEMINI_API_KEY

print(f"Cognee Status: Provider={cognee.config.llm_provider}, Model={cognee.config.llm_model}")

import cognee_wrapper
from lightrag.lightrag import LightRAG, QueryParam
from lightrag.llm.gemini import gemini_model_complete, gemini_embed
from lightrag.utils import wrap_embedding_func_with_attrs

# Constants
from config import RAG_WORKING_DIR
MODEL_NAME = "gemini-2.5-flash" 

async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
    return await gemini_model_complete(
        prompt, system_prompt=system_prompt, history_messages=history_messages,
        api_key=GEMINI_API_KEY, model_name=MODEL_NAME, **kwargs,
    )

@wrap_embedding_func_with_attrs(embedding_dim=768, send_dimensions=True, max_token_size=2048, model_name="gemini-embedding-001")
async def embedding_func(texts: list[str], **kwargs) -> np.ndarray:
    return await gemini_embed.func(texts, api_key=GEMINI_API_KEY, model="gemini-embedding-001", embedding_dim=768)

async def synthesize_response(query_text: str, mode: str = "hybrid"):
    rag = LightRAG(working_dir=RAG_WORKING_DIR, llm_model_func=llm_model_func, embedding_func=embedding_func, llm_model_name=MODEL_NAME)
    if hasattr(rag, "initialize_storages"): await rag.initialize_storages()
        
    await asyncio.sleep(2)
    # Apply canonical mapping if exists
    map_file = str(CANONICAL_MAP_FILE)
    if os.path.exists(map_file):
        try:
            with open(map_file, "r") as f:
                canonical_map = json.load(f)
            # Simple text replace for exact matches - robust mapping logic
            for raw, canonical in canonical_map.items():
                if raw in query_text:
                    query_text = query_text.replace(raw, canonical)
        except Exception as e:
            print(f"Warning: Failed to load canonical map: {e}")

    past_context = []
    try:
        past_context = await cognee_wrapper.recall_previous_context(query_text)
    except Exception as e:
        print(f"Warning: Cognee recall failed: {e}")
    
    historical_context_str = "\n### Historical Context from Past Queries:\n" + "\n".join([str(c) for c in past_context]) + "\n" if past_context else ""
    custom_prompt = f"You are a knowledge synthesizer for OminiGraph-Vault. Answer the query based on the graph context.\n{historical_context_str}\nUser Query: {query_text}"

    param = QueryParam(mode=mode, response_type="Detailed Markdown Article with Inline Images")
    
    response = None
    for i in range(3):
        try:
            response = await rag.aquery(custom_prompt, param=param)
            break
        except Exception as e:
            print(f"Query attempt {i+1} failed: {e}")
            if i < 2: await asyncio.sleep(5)
            else: raise e

    if response:
        await asyncio.sleep(2)
        try: await cognee_wrapper.remember_synthesis(query_text, response)
        except Exception as e: print(f"Warning: Cognee remember failed: {e}")
    return response

async def main():
    if len(sys.argv) < 2:
        print("Usage: python kg_synthesize.py \"<your query>\" [mode]")
        sys.exit(1)
    query, mode = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "hybrid"
    from config import SYNTHESIS_OUTPUT
    try:
        response = await synthesize_response(query, mode=mode)
        if response:
            output_file = SYNTHESIS_OUTPUT
            with open(output_file, "w", encoding="utf-8") as f: f.write(response)
            print(f"Response saved to {output_file}")
    except Exception as e:
        import traceback; traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
