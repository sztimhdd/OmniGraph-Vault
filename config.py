import os
import time
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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_API_KEY_BACKUP = os.environ.get("GEMINI_API_KEY_BACKUP", "")

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
# 2026-04-27: Switched to 3.1-flash-lite (5,000 RPD, 30 RPM) for all enrichment.
ENRICHMENT_LLM_MODEL = os.environ.get("ENRICHMENT_LLM_MODEL", "gemini-3.1-flash-lite-preview")

# LLM for the ingest path: LightRAG entity extraction + image-vision in
# ingest_wechat.py / image_pipeline.py. Separate from ENRICHMENT_LLM_MODEL
# so either path can be tuned independently.
INGEST_LLM_MODEL = os.environ.get("INGEST_LLM_MODEL", "gemini-3.1-flash-lite-preview")

# Model for image descriptions in image_pipeline. 3.1-flash-lite confirmed
# Vision-capable 2026-04-27.
IMAGE_DESCRIPTION_MODEL = os.environ.get("IMAGE_DESCRIPTION_MODEL", "gemini-3.1-flash-lite-preview")

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
#  Gemini API wrapper with key fallback, retry, and RPM guard
# ═══════════════════════════════════════════════════════════════════════

# Global state for cross-call RPM enforcement (process-wide).
_last_gemini_call_ts = 0.0

# 3.1-flash-lite-preview: 30 RPM → minimum 2.0s between calls.
# Image pipeline's D-15 4s sleep also applies per-image, so 2s here is a
# safety net for call sites that don't have their own sleep (extract_questions,
# LightRAG entity extraction, etc.).
_RPM_GUARD_INTERVAL = float(os.environ.get("GEMINI_RPM_GUARD_INTERVAL", "2.0"))


def rpm_guard():
    """Block until at least _RPM_GUARD_INTERVAL seconds have elapsed since the
    last call to rpm_guard(). Call BEFORE every Gemini API request."""
    global _last_gemini_call_ts
    elapsed = time.time() - _last_gemini_call_ts
    if elapsed < _RPM_GUARD_INTERVAL:
        time.sleep(_RPM_GUARD_INTERVAL - elapsed)
    _last_gemini_call_ts = time.time()


def gemini_call(
    model: str = "gemini-3.1-flash-lite-preview",
    contents=None,
    config=None,
    primary_key: str | None = None,
    backup_key: str | None = None,
    max_429_retries: int = 1,
    max_503_retries: int = 3,
    base_delay: float = 5.0,
):
    """Single Gemini API call with RPM guard, key fallback, and retry.

    Args:
        model: Model name.
        contents: genai content (text, PIL.Image, or list thereof).
        config: Optional genai.types.GenerateContentConfig (for grounding etc.).
        primary_key: Override default GEMINI_API_KEY.
        backup_key: Override default GEMINI_API_KEY_BACKUP.
        max_429_retries: Max retries with backup key on 429 (default 1).
        max_503_retries: Max exponential-backoff retries on 503/504.
        base_delay: Starting delay for 503 backoff (doubles each retry).

    Returns:
        genai GenerateContentResponse.

    Raises:
        RuntimeError: All keys exhausted or non-retryable error.
    """
    from google import genai

    if primary_key is None:
        primary_key = GEMINI_API_KEY
    if backup_key is None:
        backup_key = GEMINI_API_KEY_BACKUP

    attempt = 0
    current_key = primary_key

    while True:
        rpm_guard()

        try:
            client = genai.Client(api_key=current_key)
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            return response
        except Exception as e:
            status_str = str(e)

            # 401: auth failure → don't retry
            if "401" in status_str or "UNAUTHENTICATED" in status_str:
                raise RuntimeError(
                    f"Gemini auth failed with key {'primary' if current_key == primary_key else 'backup'}: {e}"
                ) from e

            # 429: quota exhausted → swap to backup (once)
            if ("429" in status_str or "RESOURCE_EXHAUSTED" in status_str) and current_key == primary_key:
                if backup_key and max_429_retries > 0:
                    logger.warning("Gemini 429 on primary key — switching to backup")
                    current_key = backup_key
                    max_429_retries -= 1
                    continue
                else:
                    raise RuntimeError(
                        f"Gemini 429 exhausted — no backup key available: {e}"
                    ) from e

            # 503 / 504: server overload → exponential backoff
            if "503" in status_str or "504" in status_str or "UNAVAILABLE" in status_str:
                attempt += 1
                if attempt <= max_503_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "Gemini %s on attempt %d/%d — retrying in %.1fs",
                        "503" if "503" in status_str else "504",
                        attempt, max_503_retries, delay,
                    )
                    time.sleep(delay)
                    continue
                else:
                    raise RuntimeError(
                        f"Gemini 503/504 after {max_503_retries} retries: {e}"
                    ) from e

            # Unknown error → don't retry
            raise RuntimeError(f"Gemini unrecoverable error: {e}") from e
