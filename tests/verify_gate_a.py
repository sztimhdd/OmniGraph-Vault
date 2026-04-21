import os
import sys
import asyncio

os.environ['GOOGLE_API_KEY'] = os.getenv('GEMINI_API_KEY')
os.environ['LLM_API_KEY'] = os.getenv('GEMINI_API_KEY')
os.environ['GEMINI_API_KEY'] = os.getenv('GEMINI_API_KEY')
os.environ['LLM_PROVIDER'] = 'gemini'
os.environ['LLM_MODEL'] = 'gemini-2.5-flash'
os.environ['EMBEDDING_PROVIDER'] = 'gemini'
os.environ['EMBEDDING_MODEL'] = 'gemini-embedding-001'
os.environ['EMBEDDING_DIMENSIONS'] = '768'
os.environ['COGNEE_SKIP_CONNECTION_TEST'] = 'true'

import cognee
cognee.config.llm_api_key = os.getenv('GEMINI_API_KEY')
cognee.config.llm_provider = "gemini"
cognee.config.llm_model = "gemini-2.5-flash"
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
