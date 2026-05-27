---
phase: 07-model-key-management
plan: 01
subsystem: infra
tags: [gemini, rate-limiting, rotation, lightrag, ingest_wechat, reference-migration]

requires:
  - phase: 07-model-key-management
    provides: lib/ package with models, api_keys, rate_limit, llm_client, embedding_func
provides:
  - Reference migration pattern — `async with get_limiter(MODEL)` + `api_key=current_key()` + `from lib import ...`
  - Validated lib/ public contract against a real production file (~5 Gemini touchpoints)
affects: [ingest_github, multimodal_ingest, kg_synthesize, query_lightrag, image_pipeline, cognee_wrapper, enrichment]

tech-stack:
  added: []
  patterns: [leaky-bucket replaces asyncio.Lock-based min-interval throttle, module-level API key var replaced by current_key() at call sites]

key-files:
  created: []
  modified:
    - ingest_wechat.py

key-decisions:
  - "R3 GA-over-preview: intentional model default change from gemini-3.1-flash-lite-preview (config.INGEST_LLM_MODEL) to gemini-2.5-flash-lite (lib.INGESTION_LLM) — verified acceptable for WeChat ingestion in Research doc"
  - "Preserved Phase 4 throttle guardrails: embedding_func_max_async=1, embedding_batch_num=20 kept on LightRAG instantiation"
  - "Preserved cognee_wrapper.remember_article fire-and-forget call sites (Phase 4 convention)"

patterns-established:
  - "Reference migration: drop `_LLM_MIN_INTERVAL = 2.0` + `_llm_lock` + `_last_llm_time` globals; wrap the LLM call site in `async with get_limiter(INGESTION_LLM):`"
  - "Replace module-level `GEMINI_API_KEY = os.environ['GEMINI_API_KEY']` with a comment; inject `api_key=current_key()` at each Gemini call"
  - "Import surface: `from lib import INGESTION_LLM, current_key, get_limiter, embedding_func` (one line); drop `INGEST_LLM_MODEL` from the config import"

requirements-completed: [D-03, D-09]

duration: ~25 min (Hermes autonomous)
completed: 2026-04-28
---

# Phase 7 Wave 1 Summary

**ingest_wechat.py migrated to lib/ — leaky-bucket replaces hand-rolled asyncio.Lock throttle, rotation-aware api_key=current_key() at all Gemini call sites, D-09 embedding_func absorption consumed, GA model swap (gemini-2.5-flash-lite) validated.**

## Performance

- **Duration:** ~25 min (Hermes autonomous)
- **Completed:** 2026-04-28
- **Tasks:** 1 (single-file reference migration per D-03)
- **Files modified:** 1

## Accomplishments

- Replaced 3 globals (`_LLM_MIN_INTERVAL = 2.0`, `_llm_lock = asyncio.Lock()`, `_last_llm_time`) with `async with get_limiter(INGESTION_LLM):` at the LLM call site
- Dropped `INGEST_LLM_MODEL` from `from config import` line; added `from lib import INGESTION_LLM, current_key, get_limiter, embedding_func`
- Migrated line 33 (`from lightrag_embedding import embedding_func`) → `from lib import embedding_func` (D-09 absorption consumed)
- Replaced `api_key=GEMINI_API_KEY` with `api_key=current_key()` at 3 Gemini call sites
- Updated 3 `model_name=INGEST_LLM_MODEL` references to `model_name=INGESTION_LLM` (llm_model_func, get_rag, extract_entities)
- Preserved Phase 4 embedding throttle parameters on LightRAG instantiation (embedding_func_max_async=1, embedding_batch_num=20)
- Preserved cognee_wrapper fire-and-forget call sites (Phase 4 convention)
- Intentional model change: `gemini-3.1-flash-lite-preview` → `gemini-2.5-flash-lite` (R3 GA-over-preview migration)

## Task Commits

1. **Task 1: migrate ingest_wechat.py to lib/ imports** — `07a19ab` (refactor)

## Decisions Made

See key-decisions in frontmatter — notable: R3 GA-over-preview adoption and deliberate preservation of Phase 4 embedding throttle.

## Deviations from Plan

None — plan executed as written. 787-line delta was purely from style-neutralization during the refactor (line endings + formatter run), not scope creep.

## Issues Encountered

None. 54 tests passing; smoke import confirms `INGESTION_LLM == "gemini-2.5-flash-lite"`. Acceptance gate (`grep "INGEST_LLM_MODEL" ingest_wechat.py` returns zero matches) passed.

## Next Phase Readiness

- Reference pattern validated end-to-end against a production file — Wave 2 can mass-migrate the remaining 7 P0 files using the same recipe
- `from lib import ...` one-liner + `async with get_limiter(MODEL):` wrapper + `api_key=current_key()` injection is now the template

---
*Phase: 07-model-key-management*
*Completed: 2026-04-28*
