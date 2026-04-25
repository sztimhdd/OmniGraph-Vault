import os
import json
import logging
import time
from pathlib import Path

ENV_PATH = Path.home() / ".hermes" / ".env"
if ENV_PATH.exists():
    with open(ENV_PATH, "r") as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip().strip("'").strip('"')

# Force Gemini API mode — the env may have GOOGLE_GENAI_USE_VERTEXAI=true
os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
os.environ.pop("GOOGLE_CLOUD_LOCATION", None)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    print("GEMINI_API_KEY not set in ~/.hermes/.env")
    import sys; sys.exit(1)

# Free tier limits for gemini-2.5-flash-lite: 15 RPM, 250K TPM, 1000 RPD
# Use 5s between requests to stay safely under the 15 RPM rolling window
_RATE_LIMIT_SECONDS = 5.0

logger = logging.getLogger("entity_batch")
logger.setLevel(logging.INFO)
handler = logging.FileHandler(str(Path(__file__).resolve().parent / "cognee_batch.log"))
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

from google import genai
from google.genai import types
from config import ENTITY_BUFFER_DIR, CANONICAL_MAP_FILE
BUFFER_DIR = str(ENTITY_BUFFER_DIR)
MAP_FILE = str(CANONICAL_MAP_FILE)

CANONICALIZATION_PROMPT = """You are an entity canonicalization engine. Your job is to merge entity names that
refer to the same real-world thing, even across languages.

Given a list of entity names and an existing canonical map, for EACH entity:
1. If it's already in the canonical map, skip it
2. If it's clearly a variant (translation, abbreviation, alternate spelling) of
   an existing canonical entity, map it to that canonical name
3. If it refers to something new, keep it as-is (it becomes its own canonical)

Rules:
- "LightRAG" and "lightrag" are the same -> canonical is "LightRAG"
- Chinese/English equivalents are the same -> map to existing canonical
- Abbreviations: "RAG" and "Retrieval-Augmented Generation" -> map to existing if present
- Different projects/tools with similar names are NOT merged (e.g., "Hermes Agent" vs "Hermes")
- Be conservative: when unsure, keep the entity as-is

Return ONLY a JSON object with the new mappings. No explanation.
Format: {{"entity_name": "canonical_name", ...}}

Existing canonical map:
{existing_map}

Entities to canonicalize:
{entities}"""

async def process_buffer_file(filepath, gemini_client):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)

        raw_entities = data.get("raw_entities", [])
        if not raw_entities:
            logger.info(f"No raw entities in {filepath}")
            return

        logger.info(f"Processing {len(raw_entities)} entities from {filepath}")

        canonical_map = {}
        if os.path.exists(MAP_FILE):
            with open(MAP_FILE, 'r') as f:
                canonical_map = json.load(f)

        existing_entities = list(canonical_map.keys())
        new_entities = [e for e in raw_entities if e not in canonical_map]

        if not new_entities:
            logger.info("All entities already in canonical map, skipping")
            return

        prompt = CANONICALIZATION_PROMPT.format(
            existing_map=json.dumps({k: canonical_map[k] for k in list(canonical_map.keys())[:50]}),
            entities=json.dumps(new_entities)
        )

        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )

        new_mappings = json.loads(response.text)
        updates = 0
        for raw_name, canonical_name in new_mappings.items():
            if raw_name not in canonical_map and raw_name != canonical_name:
                canonical_map[raw_name] = canonical_name
                updates += 1

        if updates > 0:
            tmp_file = MAP_FILE + ".tmp"
            with open(tmp_file, 'w') as f:
                json.dump(canonical_map, f, indent=2, ensure_ascii=False)
            os.rename(tmp_file, MAP_FILE)
            logger.info(f"Updated canonical_map with {updates} new entries.")
        else:
            logger.info("No new canonical mappings found.")

        os.rename(filepath, filepath + ".processed")
        logger.info(f"Processed and marked {filepath}")

    except Exception as e:
        logger.error(f"Error processing {filepath}: {e}")

async def run_batch():
    os.makedirs(BUFFER_DIR, exist_ok=True)
    files = [f for f in os.listdir(BUFFER_DIR) if f.endswith('_entities.json')]
    if not files:
        logger.info("No new entity files to process.")
        return

    client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info(f"Found {len(files)} files to process in batch.")
    for i, file in enumerate(files):
        filepath = os.path.join(BUFFER_DIR, file)
        if i > 0:
            logger.info(f"Rate limit: waiting {_RATE_LIMIT_SECONDS}s (free tier: 15 RPM)")
            time.sleep(_RATE_LIMIT_SECONDS)
        await process_buffer_file(filepath, client)

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_batch())