import os
import sys
import asyncio
import logging
from pathlib import Path

# 1. Environment Configuration
# Setup sys.path for the specific venv site-packages
VENV_SITE_PACKAGES = "/home/sztimhdd/.hermes/kg-vault/lightrag/venv/lib/python3.11/site-packages"
if VENV_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_SITE_PACKAGES)

# Load API key from ~/.hermes/.env
ENV_PATH = Path.home() / ".hermes" / ".env"
if ENV_PATH.exists():
    try:
        with open(ENV_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip().strip("'").strip('"')
                        if key.strip() == "GEMINI_API_KEY":
                            os.environ["GOOGLE_API_KEY"] = value.strip().strip("'").strip('"')
                            os.environ["LLM_API_KEY"] = value.strip().strip("'").strip('"')
    except Exception as e:
        print(f"Warning: Could not load .env file: {e}")

# Set Gemini LLM/Embedding env vars for Cognee 1.0.1
os.environ["LLM_PROVIDER"] = "gemini"
os.environ["LLM_MODEL"] = "gemini/gemini-1.5-pro"
os.environ["EMBEDDING_PROVIDER"] = "gemini"
os.environ["EMBEDDING_MODEL"] = "gemini/text-embedding-004"
os.environ["EMBEDDING_DIMENSIONS"] = "768"
os.environ["COGNEE_SKIP_CONNECTION_TEST"] = "true"

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cognee_wrapper")

try:
    import cognee
except ImportError:
    logger.error("Cognee not found in the specified venv path. Please ensure it is installed.")
    cognee = None

async def remember_synthesis(query: str, synthesis_result: str):
    """Stores the query and its answer in Cognee for long-term memory."""
    if not cognee: return None
    try:
        content = f"Query: {query}\nSynthesis Result: {synthesis_result}"
        # Using the new 1.0.1 remember API
        await cognee.remember(content)
        return True
    except Exception as e:
        logger.error(f"Error in remember_synthesis: {e}")
        return None

async def recall_previous_context(query: str):
    """Searches Cognee for related past queries or synthesis results."""
    if not cognee: return []
    try:
        # Using the new 1.0.1 search/recall API
        results = await cognee.search(query)
        return results if results else []
    except Exception as e:
        logger.error(f"Error in recall_previous_context: {e}")
        return []

async def disambiguate_entities(entity_list: list):
    """
    Takes a list of raw entity names and returns canonicalized names 
    by resolving them against Cognee's entity graph.
    """
    if not cognee: return entity_list
    try:
        # Canonicalization via remember with ontology grounding is a background process.
        # For an immediate wrapper, we check past memory.
        canonical_entities = []
        for entity in entity_list:
            search_results = await cognee.search(f"Canonical name for entity: {entity}")
            if search_results and len(search_results) > 0:
                 # Logic for extraction from result objects
                 canonical_entities.append(str(search_results[0]))
            else:
                canonical_entities.append(entity)
        return canonical_entities
    except Exception as e:
        logger.error(f"Error in disambiguate_entities: {e}")
        return entity_list

async def log_query_pattern(query: str, mode: str, was_successful: bool):
    """Logs query routing patterns and outcomes to Cognee."""
    if not cognee: return None
    try:
        log_entry = f"System Log - Query: {query}, Mode: {mode}, Success: {was_successful}"
        await cognee.remember(log_entry)
        return True
    except Exception as e:
        logger.error(f"Error in log_query_pattern: {e}")
        return None

if __name__ == "__main__":
    print("Cognee Wrapper module ready.")
