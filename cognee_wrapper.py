import os
import sys
import asyncio
import logging
from pathlib import Path

# 1. Environment Configuration
VENV_SITE_PACKAGES = "/home/sztimhdd/OmniGraph-Vault/venv/lib/python3.12/site-packages"
if VENV_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_SITE_PACKAGES)

ENV_PATH = Path.home() / ".hermes" / ".env"
if ENV_PATH.exists():
    with open(ENV_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip().strip("'").strip('"')

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
os.environ["COGNEE_LLM_API_KEY"] = GEMINI_API_KEY
os.environ["LITELLM_API_KEY"] = GEMINI_API_KEY
os.environ["OPENAI_API_KEY"] = GEMINI_API_KEY

os.environ["LLM_PROVIDER"] = "gemini"
os.environ["LLM_MODEL"] = "gemini-2.5-flash"
os.environ["EMBEDDING_PROVIDER"] = "gemini"
os.environ["EMBEDDING_MODEL"] = "gemini-embedding-001"
os.environ["EMBEDDING_DIMENSIONS"] = "768"
os.environ["COGNEE_SKIP_CONNECTION_TEST"] = "true"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cognee_wrapper")

try:
    import cognee
    # Enforce configuration at the module level
    cognee.config.llm_api_key = GEMINI_API_KEY
    cognee.config.llm_provider = "gemini"
    cognee.config.llm_model = "gemini-2.5-flash"
    cognee.config.structured_output_backend = "gemini"
except ImportError:
    logger.error("Cognee not found in wrapper.")
    cognee = None

# Local cache for disambiguation
_disambiguation_cache = {}

async def remember_synthesis(query: str, synthesis_result: str):
    if not cognee: return None
    try:
        await cognee.remember(f"Query: {query}\nResult: {synthesis_result}", self_improvement=False)
        return True
    except Exception as e:
        logger.error(f"remember_synthesis error: {e}")
        return None

async def recall_previous_context(query: str):
    if not cognee: return []
    try:
        results = await cognee.search(query)
        return results if results else []
    except Exception as e:
        logger.error(f"recall error: {e}")
        return []

async def disambiguate_entities(entity_list: list):
    if not cognee: return entity_list
    canonical_entities = []
    for entity in entity_list:
        if entity in _disambiguation_cache:
            canonical_entities.append(_disambiguation_cache[entity])
            continue
        try:
            # Short timeout, check memory
            search_results = await asyncio.wait_for(cognee.search(f"Canonical name for: {entity}"), timeout=2.0)
            if search_results:
                canonical = str(search_results[0])
                _disambiguation_cache[entity] = canonical
                canonical_entities.append(canonical)
            else:
                _disambiguation_cache[entity] = entity
                canonical_entities.append(entity)
        except (asyncio.TimeoutError, Exception):
            _disambiguation_cache[entity] = entity
            canonical_entities.append(entity)
    return canonical_entities

async def log_query_pattern(query: str, mode: str, was_successful: bool):
    if not cognee: return None
    try:
        await cognee.remember(f"Log - Q: {query}, M: {mode}, S: {was_successful}", self_improvement=False)
    except: pass
