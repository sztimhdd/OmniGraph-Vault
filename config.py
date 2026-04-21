import os
from pathlib import Path

# Base paths
BASE_DIR = Path.home() / ".hermes" / "omonigraph-vault"
RAG_WORKING_DIR = BASE_DIR / "lightrag_storage"
BASE_IMAGE_DIR = BASE_DIR / "images"
SYNTHESIS_OUTPUT = BASE_DIR / "synthesis_output.md"
ENTITY_BUFFER_DIR = BASE_DIR / "entity_buffer"
CANONICAL_MAP_FILE = BASE_DIR / "canonical_map.json"

CDP_URL = os.environ.get("CDP_URL", "http://localhost:9223")
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")

# Env
ENV_PATH = Path.home() / ".hermes" / ".env"

def load_env():
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    if not os.environ.get(key):
                        os.environ[key] = val.strip()

load_env()
