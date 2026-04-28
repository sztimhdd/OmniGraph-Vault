"""Cognee memory-layer wrapper.

Plan 05-00c Task 0c.5 — Cognee binding decision: KEEP ON GEMINI.

Rationale (see .planning/phases/05-pipeline-automation/05-00c-audit.md §3):
1. Cognee's generate_content volume is tiny — entity disambiguation uses
   few-token prompts per entity, nothing like LightRAG's chunk summarization.
2. Key rotation already propagates to Cognee via Phase 7 D-04 mechanism:
   lib.api_keys.rotate_key() writes os.environ['COGNEE_LLM_API_KEY'] inline,
   and lib.api_keys.refresh_cognee() invalidates Cognee's @lru_cache'd config.
3. Swapping Cognee to DeepSeek would require changing Cognee's internal model
   registry (litellm-based), risking token-budget / tokenizer mismatches for a
   negligible quota win.

This file is intentionally NOT modified by Plan 05-00c.
"""
import os
import sys
import asyncio
import logging
from pathlib import Path

# 1. Environment Configuration

ENV_PATH = Path.home() / ".hermes" / ".env"
if ENV_PATH.exists():
    with open(ENV_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip().strip("'").strip('"')

# Phase 7: key sourcing centralized in lib/. rotate_key() writes os.environ["COGNEE_LLM_API_KEY"]
# inline (Amendment 4) — no bridge module. Long-running processes additionally call
# refresh_cognee() at loop entry to invalidate Cognee's @lru_cache.
from lib import INGESTION_LLM, current_key

_initial_key = current_key()
os.environ["COGNEE_LLM_API_KEY"] = _initial_key
os.environ["LITELLM_API_KEY"] = _initial_key
os.environ["OPENAI_API_KEY"] = _initial_key
os.environ["LLM_API_KEY"] = _initial_key        # Cognee 1.0 unified key

# Cognee handshake env mutations (NOT Gemini API auth — these configure Cognee's LLM backend)
os.environ["LLM_PROVIDER"] = "gemini"
os.environ["LLM_MODEL"] = INGESTION_LLM
os.environ["EMBEDDING_PROVIDER"] = "gemini"
os.environ["EMBEDDING_MODEL"] = "gemini-embedding-2"
os.environ["EMBEDDING_DIMENSIONS"] = "768"
os.environ["COGNEE_SKIP_CONNECTION_TEST"] = "true"
# Cognee 1.0: disable multi-user access control (single-user personal tool)
os.environ["ENABLE_BACKEND_ACCESS_CONTROL"] = "false"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cognee_wrapper")

try:
    import cognee
    # Enforce configuration at the module level — use LLMConfig singleton directly.
    # Amendment 4: rotation propagates via os.environ["COGNEE_LLM_API_KEY"] set inside
    # rotate_key(); the initial llm_api_key assignment is still needed because
    # get_llm_config() was already @lru_cache'd before this import.
    from cognee.infrastructure.llm.config import get_llm_config
    llm_config = get_llm_config()
    llm_config.llm_api_key = current_key()
    llm_config.llm_provider = "gemini"
    llm_config.llm_model = INGESTION_LLM
except ImportError:
    logger.error("Cognee not found in wrapper.")
    cognee = None

# Local cache for disambiguation
_disambiguation_cache = {}

_COGNEE_TIMEOUT = 30.0  # remember() runs add()→cognify() internally, ~15-30s on first call

async def remember_synthesis(query: str, synthesis_result: str):
    if not cognee: return None
    try:
        await asyncio.wait_for(
            cognee.remember(f"Query: {query}\nResult: {synthesis_result}", self_improvement=False),
            timeout=_COGNEE_TIMEOUT
        )
        return True
    except asyncio.TimeoutError:
        logger.warning("remember_synthesis timed out (Cognee embeddings unavailable on free tier)")
        return None
    except Exception as e:
        logger.warning(f"remember_synthesis error: {e}")
        return None

async def recall_previous_context(query: str):
    if not cognee: return []
    try:
        results = await asyncio.wait_for(cognee.search(query), timeout=_COGNEE_TIMEOUT)
        return results if results else []
    except asyncio.TimeoutError:
        logger.warning("recall_previous_context timed out (Cognee embeddings unavailable on free tier)")
        return []
    except Exception as e:
        logger.warning(f"recall error: {e}")
        return []

_ARTICLE_DATASET = "ingested_articles"


async def remember_article(
    title: str,
    url: str,
    entities: list[str],
    summary_gist: str = "",
) -> bool:
    """Store article metadata in Cognee episodic memory (fire-and-forget).

    Per 2026 RAG best practices: dual-store at ingestion time.
    LightRAG stores the full semantic content; Cognee stores episodic metadata
    so queries like "what have I read about X?" can surface relevant articles.

    Uses Cognee 1.0 remember() — times out at _COGNEE_TIMEOUT seconds.
    Never raises — always returns bool.
    """
    if not cognee:
        return False
    try:
        entity_str = ", ".join(entities[:15]) if entities else "none extracted"
        gist = summary_gist[:500] if summary_gist else ""
        text = (
            f"Article: {title}\n"
            f"URL: {url}\n"
            f"Key entities: {entity_str}\n"
            + (f"Summary: {gist}" if gist else "")
        )
        await asyncio.wait_for(
            cognee.remember(
                text,
                dataset_name=_ARTICLE_DATASET,
                self_improvement=False,
                run_in_background=True,   # fire-and-forget: returns immediately
            ),
            timeout=5.0,                   # only waiting for queue, not processing
        )
        logger.info("remember_article stored: %s", title[:80])
        return True
    except asyncio.TimeoutError:
        logger.debug("remember_article timed out (non-blocking, ok)")
        return False
    except Exception as e:
        logger.debug("remember_article skipped: %s", e)
        return False


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
    except Exception as e:
        logger.debug(f"log_query_pattern failed: {e}")
