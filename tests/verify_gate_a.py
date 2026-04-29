import os
import sys
import asyncio

# Phase 7 D-06: key resolution + model identity owned by lib.
# Cognee handshake env vars mirror cognee_wrapper.py Wave 3 configuration.
from lib import current_key, INGESTION_LLM, EMBEDDING_MODEL

_key = current_key()
os.environ['GOOGLE_API_KEY'] = _key
os.environ['LLM_API_KEY'] = _key
os.environ['GEMINI_API_KEY'] = _key
os.environ['LLM_PROVIDER'] = 'gemini'
os.environ['LLM_MODEL'] = INGESTION_LLM
os.environ['EMBEDDING_PROVIDER'] = 'gemini'
os.environ['EMBEDDING_MODEL'] = EMBEDDING_MODEL
os.environ['EMBEDDING_DIMENSIONS'] = '768'
os.environ['COGNEE_SKIP_CONNECTION_TEST'] = 'true'

import cognee
cognee.config.llm_api_key = _key
cognee.config.llm_provider = "gemini"
cognee.config.llm_model = INGESTION_LLM
cognee.config.structured_output_backend = "gemini"


async def main():
    # Prints cognee version
    version = getattr(cognee, "__version__", "unknown")
    print(f"Cognee version: {version}")

    try:
        # Calls 'await cognee.remember("Gate A validation test")'
        await cognee.remember("Gate A validation test")
        # Prints 'Gate A Verified' if successful
        print("Gate A Verified")
    except Exception as e:
        print(f"Gate A Validation Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
