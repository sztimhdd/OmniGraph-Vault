import os
import sys
import asyncio

# Environment setup
sys.path.append('/home/sztimhdd/.hermes/kg-vault/lightrag/venv/lib/python3.11/site-packages')

os.environ['GOOGLE_API_KEY'] = os.getenv('GEMINI_API_KEY')
os.environ['LLM_API_KEY'] = os.getenv('GEMINI_API_KEY')
os.environ['GEMINI_API_KEY'] = os.getenv('GEMINI_API_KEY')
os.environ['LLM_PROVIDER'] = 'gemini'
os.environ['LLM_MODEL'] = 'gemini/gemini-1.5-pro'
os.environ['EMBEDDING_PROVIDER'] = 'gemini'
os.environ['EMBEDDING_MODEL'] = 'gemini/text-embedding-004'
os.environ['EMBEDDING_DIMENSIONS'] = '768'
os.environ['COGNEE_SKIP_CONNECTION_TEST'] = 'true'

import cognee

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
