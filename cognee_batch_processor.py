import os
import json
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Ensure environment is loaded and Cognee is configured properly
VENV_SITE_PACKAGES = "/home/sztimhdd/.hermes/kg-vault/venv/lib/python3.11/site-packages"
import sys
if VENV_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_SITE_PACKAGES)

ENV_PATH = Path.home() / ".hermes" / ".env"
if ENV_PATH.exists():
    with open(ENV_PATH, "r") as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip().strip("'").strip('"')

# Use Gemini Flash Lite as requested for cost-efficiency
os.environ["COGNEE_LLM_API_KEY"] = os.environ.get("GEMINI_API_KEY", "")
import cognee
cognee.config.llm_provider = "gemini"
cognee.config.llm_model = "gemini-2.5-flash-lite"

logger = logging.getLogger("cognee_batch")
logger.setLevel(logging.INFO)
handler = logging.FileHandler("/home/sztimhdd/OmniGraph-Vault/cognee_batch.log")
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

BUFFER_DIR = "/home/sztimhdd/OmniGraph-Vault/entity_buffer"
MAP_FILE = "/home/sztimhdd/OmniGraph-Vault/canonical_map.json"

async def process_buffer_file(filepath):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        raw_entities = data.get("raw_entities", [])
        if not raw_entities:
            logger.info(f"No raw entities in {filepath}")
            return
            
        logger.info(f"Processing {len(raw_entities)} entities from {filepath}")
        # Note: we need the cognee_wrapper here for disambiguate_entities
        import cognee_wrapper
        canonical_entities = await cognee_wrapper.disambiguate_entities(raw_entities)
        
        # Load existing map
        canonical_map = {}
        if os.path.exists(MAP_FILE):
            with open(MAP_FILE, 'r') as f:
                canonical_map = json.load(f)
                
        # Update map
        updates = 0
        for raw, canonical in zip(raw_entities, canonical_entities):
            if raw != canonical and raw not in canonical_map:
                canonical_map[raw] = canonical
                updates += 1
                
        # Atomic save
        if updates > 0:
            tmp_file = MAP_FILE + ".tmp"
            with open(tmp_file, 'w') as f:
                json.dump(canonical_map, f, indent=2)
            os.rename(tmp_file, MAP_FILE)
            logger.info(f"Updated canonical_map with {updates} new entries.")
        
        # Mark as processed
        os.rename(filepath, filepath + ".processed")
        logger.info(f"Successfully processed and renamed {filepath}")
        
    except Exception as e:
        logger.error(f"Error processing {filepath}: {e}")

async def run_batch():
    os.makedirs(BUFFER_DIR, exist_ok=True)
    files = [f for f in os.listdir(BUFFER_DIR) if f.endswith('_entities.json')]
    if not files:
        return
    logger.info(f"Found {len(files)} files to process in batch.")
    for file in files:
        filepath = os.path.join(BUFFER_DIR, file)
        await process_buffer_file(filepath)

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_batch())