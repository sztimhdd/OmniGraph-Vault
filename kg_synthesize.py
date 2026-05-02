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

import asyncio
import time

from lightrag.lightrag import LightRAG, QueryParam
from lib.llm_deepseek import deepseek_model_complete
from lib.lightrag_embedding import embedding_func

# Phase 5 Wave 0 fix (2026-05-03): SYNTHESIS_LLM was gemini-2.5-flash-lite but
# the routing rule is "ALL LLM → DeepSeek, Gemini ONLY for Vision+Embedding".
# Also: Cognee import was triggering async pipelines at module level (Vertex AI
# 404 cascade), blocking the event loop. Cognee is now lazy-imported only when
# recall/remember succeeds — which it never does on free-tier Vertex AI anyway.


async def synthesize_response(query_text: str, mode: str = "hybrid"):
    rag = LightRAG(working_dir=RAG_WORKING_DIR, llm_model_func=deepseek_model_complete, embedding_func=embedding_func)
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

    # Instruction placed FIRST (before query) so LightRAG's internal template
    # does not overshadow it. Critical: the LLM must inline image URLs as
    # ![](url) markdown — without this, images in the context are dropped.
    custom_prompt = (
        "You are a knowledge synthesizer. "
        "CRITICAL: when the context below contains image URLs like "
        "http://localhost:8765/..., you MUST include them as "
        "![description](url) INLINE in your answer near the relevant text. "
        "Do NOT skip images. Do NOT drop URLs.\n\n"
        f"Query: {query_text}"
    )

    param = QueryParam(mode=mode)
    
    response = None
    for i in range(3):
        try:
            response = await rag.aquery(custom_prompt, param=param)
            break
        except Exception as e:
            print(f"Query attempt {i+1} failed: {e}")
            if i < 2: await asyncio.sleep(5)
            else: raise e

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
            print(f"Response saved to {output_file} ({len(response)} chars)")
        else:
            print("ERROR: empty response from LightRAG")
    except Exception as e:
        import traceback; traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
