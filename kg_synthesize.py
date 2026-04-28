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

# Phase 7: centralized model selection + key management (must load before cognee import
# so its LLMConfig singleton sees COGNEE_LLM_API_KEY on first construction).
from lib import SYNTHESIS_LLM, current_key, get_limiter

import asyncio
import time

# Set Cognee env vars BEFORE import so LLMConfig() picks them up at construction.
# Amendment 4: rotate_key() will write os.environ["COGNEE_LLM_API_KEY"] inline on
# rotation; Wave 3 adds refresh_cognee() at loop entry to invalidate @lru_cache.
_initial_key = current_key()
os.environ["COGNEE_LLM_API_KEY"] = _initial_key
os.environ["LITELLM_API_KEY"] = _initial_key
os.environ["LLM_API_KEY"] = _initial_key  # Cognee 1.0 unified key

import cognee

# FORCE CONFIGURATION (runtime, in case env didn't set it on LLMConfig singleton)
from cognee.infrastructure.llm.config import get_llm_config
llm_config = get_llm_config()
llm_config.llm_api_key = current_key()
llm_config.llm_provider = "gemini"
llm_config.llm_model = SYNTHESIS_LLM

print(f"Cognee Status: Provider={llm_config.llm_provider}, Model={llm_config.llm_model}")

import cognee_wrapper
from lightrag.lightrag import LightRAG, QueryParam
from lightrag.llm.gemini import gemini_model_complete

# Phase 7 D-09: embedding_func now lives in lib/; root shim re-exports for back-compat.
from lib import embedding_func

# Constants
from config import RAG_WORKING_DIR

async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
    """LightRAG LLM wrapper with Phase 7 lib/ rate limiting and key rotation."""
    async with get_limiter(SYNTHESIS_LLM):
        return await gemini_model_complete(
            prompt, system_prompt=system_prompt, history_messages=history_messages,
            api_key=current_key(), model_name=SYNTHESIS_LLM, **kwargs,
        )

async def synthesize_response(query_text: str, mode: str = "hybrid"):
    rag = LightRAG(working_dir=RAG_WORKING_DIR, llm_model_func=llm_model_func, embedding_func=embedding_func, llm_model_name=SYNTHESIS_LLM)
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
