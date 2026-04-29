import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Base paths
BASE_DIR = Path.home() / ".hermes" / "omonigraph-vault"
RAG_WORKING_DIR = BASE_DIR / "lightrag_storage"
BASE_IMAGE_DIR = BASE_DIR / "images"
SYNTHESIS_OUTPUT = BASE_DIR / "synthesis_output.md"
ENTITY_BUFFER_DIR = BASE_DIR / "entity_buffer"
CANONICAL_MAP_FILE = BASE_DIR / "canonical_map.json"

CDP_URL = os.environ.get("CDP_URL", "http://localhost:9223")
FIRECRAWL_API_KEY=os.environ.get("FIRECRAWL_API_KEY", "")

# Phase 7 D-04 + BLOCKER 2 resolution:
#   GEMINI_API_KEY / GEMINI_API_KEY_BACKUP module attributes removed.
#   Access keys via lib.current_key(); lib.api_keys.load_keys() reads
#   OMNIGRAPH_GEMINI_KEYS / OMNIGRAPH_GEMINI_KEY / GEMINI_API_KEY_BACKUP /
#   GEMINI_API_KEY env vars (precedence order) on first call.

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

# Phase 7 Amendment 3 (Wave 4 Task 4.7): D-11 model-constant shims + gemini_call
# were deleted here. All callers now import INGESTION_LLM / VISION_LLM / generate_sync
# directly from lib/. config.py owns paths + env loading only; model selection and
# LLM execution live in lib/models.py + lib/llm_client.py.

# Master switch. Per D-07 this is always True in production; the key exists
# so that individual invocations can set ENRICHMENT_ENABLED=0 to bypass.
ENRICHMENT_ENABLED = os.environ.get("ENRICHMENT_ENABLED", "1") != "0"

# Article character threshold below which extraction is skipped (enriched=-1).
ENRICHMENT_MIN_LENGTH = 2000

# Maximum questions per article.
ENRICHMENT_MAX_QUESTIONS = 3

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

# Phase 7 Amendment 3 sweeper: gemini_call + _GeminiCallResponse deleted here.
# All LLM calls go through lib.generate / lib.generate_sync / lib.aembed with
# uniform rate limiting (aiolimiter), retry (tenacity), and key rotation.
