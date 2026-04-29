import os
import sys
import asyncio

# Environment setup
# Phase 7 D-06: key resolution + model identity owned by lib.
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
    # Gate B Goal: Verify Cognee 'remember' and 'recall' functionality.
    # Fixed: Removed 'metadata' and incorporated query into content.
    await cognee.remember('Query: What is the weather in Shanghai? Synthesis Result: The weather in Shanghai is sunny.')

    # Using recall (New API) or search (V1)
    # The logs suggest remember/recall is the new standard.
    print("Attempting cognee.recall()...")
    result = await cognee.recall('Tell me about Shanghai weather')

    # Print the recall result.
    print(f"Recall Result: {result}")

    # If the result contains 'sunny', print 'Gate B Verified'.
    # Recall result in 1.0.1 might be a list of dicts or objects.
    if 'sunny' in str(result).lower():
        print('Gate B Verified')
    else:
        # Fallback to search if recall is empty or format differs
        print("Recall inconclusive, attempting cognee.search()...")
        search_results = await cognee.search('Shanghai weather')
        print(f"Search Results: {search_results}")
        if 'sunny' in str(search_results).lower():
             print('Gate B Verified (via search)')

if __name__ == '__main__':
    asyncio.run(main())
