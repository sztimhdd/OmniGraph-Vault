import os
import sys
import asyncio

sys.path.append('/home/sztimhdd/.hermes/kg-vault/lightrag/venv/lib/python3.11/site-packages')
os.environ['GOOGLE_API_KEY'] = os.environ.get('GEMINI_API_KEY', '')
os.environ['LLM_PROVIDER'] = 'gemini'
os.environ['LLM_MODEL'] = 'gemini/gemini-1.5-pro'
os.environ['EMBEDDING_PROVIDER'] = 'gemini'
os.environ['EMBEDDING_MODEL'] = 'gemini/text-embedding-004'
os.environ['EMBEDDING_DIMENSIONS'] = '768'
os.environ['COGNEE_SKIP_CONNECTION_TEST'] = 'true'

import cognee

async def f():
    print("Building Cognee graph (Cognify)...")
    await cognee.remember('Initialization data', self_improvement=False)
    await cognee.cognify()
    print("Cognify complete.")

if __name__ == '__main__':
    asyncio.run(f())
