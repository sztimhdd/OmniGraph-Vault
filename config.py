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

# D-11: Phase 7 model constants delegated to lib.models. These shims preserve
# the public API (`from config import INGEST_LLM_MODEL` etc.) while making
# lib.models the single source of truth. Callers migrate at their own pace.
# Amendment 3: shims are TEMPORARY — Wave 4 Task 4.7 is the atomic sweeper
# that deletes them after every caller has migrated.
from lib.models import INGESTION_LLM, VISION_LLM

# Master switch. Per D-07 this is always True in production; the key exists
# so that individual invocations can set ENRICHMENT_ENABLED=0 to bypass.
ENRICHMENT_ENABLED = os.environ.get("ENRICHMENT_ENABLED", "1") != "0"

# Article character threshold below which extraction is skipped (enriched=-1).
ENRICHMENT_MIN_LENGTH = 2000

# Maximum questions per article.
ENRICHMENT_MAX_QUESTIONS = 3

# D-11 shims (TEMPORARY — deleted by Wave 4 Amendment 3 sweeper).
# Intentional R3 GA migration: old default gemini-3.1-flash-lite-preview now
# maps to gemini-2.5-flash-lite (lib.INGESTION_LLM / VISION_LLM GA).
# Rollback: edit lib/models.py (Amendment 1 — pure constants; git-as-deploy IS the rollback).
ENRICHMENT_LLM_MODEL = INGESTION_LLM       # D-11 shim (TEMPORARY — deleted by Wave 4 Amendment 3 sweeper)
INGEST_LLM_MODEL = INGESTION_LLM           # D-11 shim (TEMPORARY — deleted by Wave 4 Amendment 3 sweeper)
IMAGE_DESCRIPTION_MODEL = VISION_LLM       # D-11 shim (TEMPORARY — deleted by Wave 4 Amendment 3 sweeper)

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


# ═══════════════════════════════════════════════════════════════════════
#  Phase 7 D-11: gemini_call shim — delegates to lib.generate_sync
# ═══════════════════════════════════════════════════════════════════════
# Previous implementation (~90 lines) handled RPM guard, key fallback, and
# 429/503 retry inline. All of that is now owned by lib.llm_client.generate
# (tenacity @retry + aiolimiter + rotate_key). rpm_guard() is removed; callers
# should migrate to lib.get_limiter + lib.generate/generate_sync directly.
# This shim is TEMPORARY — deleted by Wave 4 Amendment 3 sweeper.


class _GeminiCallResponse:
    """Back-compat wrapper so legacy callers can still access ``response.text``."""
    __slots__ = ("text",)

    def __init__(self, text: str):
        self.text = text


def gemini_call(model, prompt=None, contents=None, config=None, **kwargs):
    """DEPRECATED Phase 7 D-11 shim: delegates to lib.generate_sync.

    The original retry + rpm_guard + 429/503 loop is now handled by
    lib.llm_client.generate (tenacity @retry + aiolimiter + rotate_key).
    Returns a thin wrapper with a ``.text`` attribute for back-compat with
    pre-Phase-7 callers (enrichment.extract_questions, ingest_wechat.extract_entities).
    Remove after all callers migrate (Wave 4 Amendment 3 sweeper).
    """
    from lib import generate_sync

    # Historical callers passed content list via ``contents=[prompt, img]``;
    # lib.generate_sync accepts ``(model, prompt, **kwargs)``. Map accordingly:
    if contents is not None and prompt is None:
        prompt = contents[0] if contents else ""
        extra_contents = contents[1:]
        if extra_contents:
            kwargs.setdefault("contents", extra_contents)
    if config is not None:
        kwargs["config"] = config
    text = generate_sync(model, prompt, **kwargs)
    return _GeminiCallResponse(text=text)
