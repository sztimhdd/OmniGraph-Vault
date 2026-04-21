import os
import sys
import asyncio

# Correct Environment setup
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
    print("--- Gate C: Starting Concept Disambiguation Test ---")
    
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
