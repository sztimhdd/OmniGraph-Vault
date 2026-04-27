import os
import json
import sqlite3
import sys
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from config import RAG_WORKING_DIR, load_env, CANONICAL_MAP_FILE
load_env()
DB_PATH = Path(__file__).parent / "data" / "kol_scan.db"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

import asyncio
import numpy as np
import time

# Set Cognee env vars BEFORE import so LLMConfig() picks them up at construction
os.environ["COGNEE_LLM_API_KEY"] = GEMINI_API_KEY
os.environ["LITELLM_API_KEY"] = GEMINI_API_KEY
os.environ["LLM_API_KEY"] = GEMINI_API_KEY  # Cognee 1.0 unified key

import cognee
if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not found.")
    sys.exit(1)

# FORCE CONFIGURATION (runtime, in case env didn't set it on LLMConfig singleton)
from cognee.infrastructure.llm.config import get_llm_config
llm_config = get_llm_config()
llm_config.llm_api_key = GEMINI_API_KEY
llm_config.llm_provider = "gemini"
llm_config.llm_model = "gemini-2.5-flash-lite"

print(f"Cognee Status: Provider={llm_config.llm_provider}, Model={llm_config.llm_model}")

import cognee_wrapper
from lightrag.lightrag import LightRAG, QueryParam
from lightrag.llm.gemini import gemini_model_complete, gemini_embed
from lightrag.utils import wrap_embedding_func_with_attrs

# Constants
from config import RAG_WORKING_DIR
MODEL_NAME = "gemini-2.5-flash-lite" 

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
    # Apply canonical mapping if exists (DB-first, JSON fallback)
    canonical_map = {}
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            rows = conn.execute("SELECT raw_name, canonical_name FROM entity_canonical").fetchall()
            conn.close()
            canonical_map = dict(rows)
        except Exception as e:
            print(f"Warning: Failed to load canonical map from DB: {e}")
    if not canonical_map:
        map_file = str(CANONICAL_MAP_FILE)
        if os.path.exists(map_file):
            try:
                with open(map_file, "r") as f:
                    canonical_map = json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load canonical map: {e}")
    for raw, canonical in canonical_map.items():
        if raw in query_text:
            query_text = query_text.replace(raw, canonical)

    past_context = []
    try:
        past_context = await cognee_wrapper.recall_previous_context(query_text)
    except Exception as e:
        print(f"Warning: Cognee recall failed: {e}")
    
    historical_context_str = "\\n### Historical Context from Past Queries:\\n" + "\\n".join([str(c) for c in past_context]) + "\\n" if past_context else ""
    custom_prompt = f"""You are a knowledge synthesizer for OminiGraph-Vault. Answer the query based on the graph context.
{historical_context_str}
### Instructions:
1. Output a detailed Markdown article with inline images.
2. When the context contains image URLs (http://localhost:8765/...), include them as ![description](url) inline in the text near the relevant description.
3. Preserve original image URLs from the context — do NOT remove or replace them.
4. Organize with clear headings, descriptions, and references.

User Query: {query_text}"""

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
