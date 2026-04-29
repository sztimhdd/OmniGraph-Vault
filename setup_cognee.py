import os
import sys

# Phase 7: key sourcing via lib/. lib.api_keys.load_keys() reads ~/.hermes/.env
# via config.load_env (or directly via os.environ). rotate_key() writes
# os.environ["COGNEE_LLM_API_KEY"] inline on rotation.
from lib import current_key

_key = current_key()
os.environ["LLM_API_KEY"] = _key
os.environ["GOOGLE_API_KEY"] = _key

os.environ["LLM_PROVIDER"] = "gemini"
os.environ["LLM_MODEL"] = "gemini/gemini-1.5-pro"
os.environ["EMBEDDING_PROVIDER"] = "gemini"
os.environ["EMBEDDING_MODEL"] = "gemini/text-embedding-004"
os.environ["EMBEDDING_DIMENSIONS"] = "768"
os.environ["COGNEE_SKIP_CONNECTION_TEST"] = "true"

import cognee
import asyncio

async def setup():
    # Print Cognee info
    print(f"Cognee Version: {cognee.__version__ if hasattr(cognee, '__version__') else '1.0.1'}")
    
    try:
        from cognee.infrastructure.llm.config import get_llm_config
        llm_config = get_llm_config()
        print(f"LLM Provider: {llm_config.llm_provider}")
        print(f"LLM Model: {llm_config.llm_model}")
        
        # Test connection by doing a simple operation
        print("Attempting cognee.remember()...")
        await cognee.remember("OmniGraph-Vault is a knowledge ingestion system.")
        print("Gate A: Cognee successfully initialized and 'remember' called.")
        
    except Exception as e:
        print(f"Gate A Failed: {e}")
        # import traceback
        # traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(setup())
