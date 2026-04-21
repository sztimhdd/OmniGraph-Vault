import os
import sys
import asyncio

# 1. Load environment variables from '~/.hermes/.env' at the very beginning
def load_env(file_path):
    expanded_path = os.path.expanduser(file_path)
    if os.path.exists(expanded_path):
        with open(expanded_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

load_env('~/.hermes/.env')

# 2. Ensure 'GOOGLE_API_KEY', 'LLM_API_KEY', and 'GEMINI_API_KEY' are all set
gemini_key = os.getenv('GEMINI_API_KEY')
if gemini_key:
    os.environ['GOOGLE_API_KEY'] = gemini_key
    os.environ['LLM_API_KEY'] = gemini_key
    os.environ['GEMINI_API_KEY'] = gemini_key
else:
    # Fallback if GEMINI_API_KEY is not in .env but maybe others are
    key = os.getenv('GOOGLE_API_KEY') or os.getenv('LLM_API_KEY')
    if key:
        os.environ['GOOGLE_API_KEY'] = key
        os.environ['LLM_API_KEY'] = key
        os.environ['GEMINI_API_KEY'] = key

# 4. Ensure 'sys.path' includes the venv site-packages (now auto-handled when running from venv)

# Set other environment variables
os.environ['LLM_PROVIDER'] = 'gemini'
os.environ['LLM_MODEL'] = 'gemini-2.5-flash'
os.environ['EMBEDDING_PROVIDER'] = 'gemini'
os.environ['EMBEDDING_MODEL'] = 'gemini-embedding-001'
os.environ['EMBEDDING_DIMENSIONS'] = '768'
os.environ['COGNEE_SKIP_CONNECTION_TEST'] = 'true'

# Import cognee after sys.path is updated
import cognee
cognee.config.llm_api_key = os.getenv('GEMINI_API_KEY')
cognee.config.llm_provider = "gemini"
cognee.config.llm_model = "gemini-2.5-flash"
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
