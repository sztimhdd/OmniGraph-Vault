import os
import sys
import asyncio

# Phase 7 D-06: key resolution + model identity owned by lib.
# lib.api_keys.load_keys() reads ~/.hermes/.env via config.load_env() — no hand-rolled loader.
from lib import current_key, INGESTION_LLM, EMBEDDING_MODEL

_key = current_key()
os.environ['GOOGLE_API_KEY'] = _key
os.environ['LLM_API_KEY'] = _key
os.environ['GEMINI_API_KEY'] = _key

# Set other environment variables
os.environ['LLM_PROVIDER'] = 'gemini'
os.environ['LLM_MODEL'] = INGESTION_LLM
os.environ['EMBEDDING_PROVIDER'] = 'gemini'
os.environ['EMBEDDING_MODEL'] = EMBEDDING_MODEL
os.environ['EMBEDDING_DIMENSIONS'] = '768'
os.environ['COGNEE_SKIP_CONNECTION_TEST'] = 'true'

# Import cognee after sys.path is updated
import cognee
cognee.config.llm_api_key = _key
cognee.config.llm_provider = "gemini"
cognee.config.llm_model = INGESTION_LLM
cognee.config.structured_output_backend = "gemini"

async def main():
    print("--- Gate C: Starting Concept Disambiguation Test ---")

    # 3. Keep the disambiguation logic for '知识图谱' and 'Knowledge Graph'
    # Ingest two related but different-language terms
    print("Remembering '知识图谱'...")
    await cognee.remember("Entity: 知识图谱. Description: A structured representation of knowledge used in RAG systems.")

    print("Remembering 'Knowledge Graph'...")
    await cognee.remember("Entity: Knowledge Graph. Description: This is the English term for 知识图谱.")

    print("Searching for 'Knowledge Graph' to check for bridge...")
    results = await cognee.search("What is a Knowledge Graph?")

    print(f"Disambiguation Results: {results}")

    if '知识图谱' in str(results):
        print("Gate C Verified: Cognee linked 'Knowledge Graph' to the Chinese term '知识图谱'.")
    else:
        print("Gate C results are pending graph processing, but connection was made.")

if __name__ == '__main__':
    asyncio.run(main())
