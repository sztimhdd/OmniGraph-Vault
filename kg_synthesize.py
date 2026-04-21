import os

# TRICK: Set environment variables BEFORE importing lightrag or genai
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"
if "GOOGLE_API_KEY" in os.environ:
    os.environ.pop("GOOGLE_API_KEY")

import asyncio
import sys
import numpy as np
from lightrag.lightrag import LightRAG, QueryParam
from lightrag.llm.gemini import gemini_model_complete, gemini_embed
from lightrag.utils import wrap_embedding_func_with_attrs

# Constants
RAG_WORKING_DIR = os.path.expanduser("./data/lightrag_storage")

def load_env():
    """Load environment variables from ~/.hermes/.env if they are not already set."""
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    if not os.environ.get(key):
                        os.environ[key] = val.strip()

# Initialize environment
load_env()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not found in environment.")
    sys.exit(1)

async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
    """Wrapper for Gemini LLM model completion using LightRAG's built-in helper."""
    return await gemini_model_complete(
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        api_key=GEMINI_API_KEY,
        model_name="gemini-2.5-pro",
        **kwargs,
    )

@wrap_embedding_func_with_attrs(
    embedding_dim=3072,
    send_dimensions=True,
    max_token_size=2048,
    model_name="gemini-embedding-001",
)
async def embedding_func(texts: list[str], **kwargs) -> np.ndarray:
    """Wrapper for Gemini embedding function."""
    return await gemini_embed.func(
        texts, api_key=GEMINI_API_KEY, model="gemini-embedding-001"
    )

async def synthesize_response(query_text: str, mode: str = "naive"):
    """Initializes LightRAG and performs a query to synthesize a markdown response."""
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        llm_model_name="gemini-2.5-pro",
    )
    
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
        
    # Custom instructions for synthesis to ensure image links are preserved/used
    custom_prompt = f"""You are a knowledge synthesizer for KG-Vault. 
Your task is to answer the user's query based on the provided knowledge graph context.
The context contains local image links in the format 'http://localhost:8765/hash/index.jpg'.

REALLY IMPORTANT RULES:
1. You MUST include relevant images from the context in your response.
2. Use standard Markdown syntax for images: ![Description](http://localhost:8765/hash/index.jpg)
3. Do NOT change the image URLs.
4. If there are multiple images, place them appropriately in the text where they add value.
5. If the context has [Image Description] tags, use that text as the Alt text for the image.

User Query: {query_text}
"""

    param = QueryParam(
        mode=mode, 
        response_type="Detailed Markdown Article with Inline Images",
    )
    
    response = await rag.aquery(custom_prompt, param=param)
    return response

async def main():
    if len(sys.argv) < 2:
        print("Usage: python kg_synthesize.py \"<your query>\" [mode]")
        sys.exit(1)
        
    query = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "naive"
    
    try:
        print(f"--- Synthesizing Knowledge (Mode: {mode}) ---\nQuery: {query}\n")
        response = await synthesize_response(query, mode=mode)
        print("\n--- Final Markdown Response ---\n")
        print(response)
        
        # Save to a file for review
        output_file = "/home/sztimhdd/.hermes/kg-vault/synthesis_output.md"
        with open(output_file, "w") as f:
            f.write(response)
        print(f"\nResponse saved to {output_file}")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
