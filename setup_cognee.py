import os
import sys

# Load API Key from .env BEFORE importing cognee
env_path = os.path.expanduser("~/.hermes/.env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            if "GEMINI_API_KEY" in line:
                key = line.split("=")[1].strip()
                os.environ["LLM_API_KEY"] = key
                os.environ["GOOGLE_API_KEY"] = key
                os.environ["GEMINI_API_KEY"] = key

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
