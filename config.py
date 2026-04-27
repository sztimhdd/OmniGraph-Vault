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

# Force Gemini API mode — the env may have GOOGLE_GENAI_USE_VERTEXAI=true
# which routes all genai.Client calls to Vertex AI (requires billing)
os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
os.environ.pop("GOOGLE_CLOUD_LOCATION", None)

# === Phase 4: Knowledge Enrichment ===
# Master switch. Per D-07 this is always True in production; the key exists
# so that individual invocations can set ENRICHMENT_ENABLED=0 to bypass.
ENRICHMENT_ENABLED = os.environ.get("ENRICHMENT_ENABLED", "1") != "0"

# Article character threshold below which extraction is skipped (enriched=-1).
ENRICHMENT_MIN_LENGTH = 2000

# Maximum questions per article.
ENRICHMENT_MAX_QUESTIONS = 3

# LLM for extract_questions. D-12-REVISED: flash (250/day), not flash-lite
# (20/day). Live E2E test 2026-04-27 proved flash-lite quota insufficient.
ENRICHMENT_LLM_MODEL = os.environ.get("ENRICHMENT_LLM_MODEL", "gemini-2.5-flash")

# LLM for the ingest path: LightRAG entity extraction + image-vision in
# ingest_wechat.py / image_pipeline.py. Separate from ENRICHMENT_LLM_MODEL
# so either path can be tuned independently. D-12-REVISED: flash default.
INGEST_LLM_MODEL = os.environ.get("INGEST_LLM_MODEL", "gemini-2.5-flash")

# Enable google_search grounding tool on the extract_questions call (D-12).
ENRICHMENT_GROUNDING_ENABLED = True

# Per-question 好问 search timeout (PRD §8).
ENRICHMENT_HAOWEN_TIMEOUT = 120

# Per-question Zhihu source-article fetch timeout (PRD §8).
ENRICHMENT_ZHIHU_FETCH_TIMEOUT = 60

# Artifact root (D-03). Hermes skill writes per-question subdirs here.
ENRICHMENT_BASE_DIR = BASE_DIR / "enrichment"

# Hermes skill name for Zhihu 好问 (referenced by the top-level skill body).
ZHIHAO_SKILL_NAME = "zhihu-haowen-enrich"

# Local image server (reused for Zhihu article images).
IMAGE_SERVER_BASE_URL = "http://localhost:8765"
