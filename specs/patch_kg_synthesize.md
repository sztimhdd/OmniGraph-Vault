# OminiGraph-Vault: kg_synthesize.py Patch Specifications

## Goal
Fix Cognee LLM initialization and add rate limiting to prevent 429/503 errors.

## Required Changes
1. **API Initialization**:
   - In `load_env()` after loading, force set `os.environ["COGNEE_LLM_API_KEY"] = os.environ.get("GEMINI_API_KEY")`.
   - Ensure these are set BEFORE `cognee_wrapper` is imported or used.

2. **Rate Limiting & Retries**:
   - In `synthesize_response`:
     - Add `import asyncio` (already there).
     - Add `await asyncio.sleep(2)` before `cognee_wrapper.recall_previous_context` and before `cognee_wrapper.remember_synthesis`.
   - Around `rag.aquery`:
     - Wrap in a retry loop (max 3 retries) with `asyncio.sleep(5)` on failure (429 or 503).

## Context
File to modify: `/home/sztimhdd/OmniGraph-Vault/kg_synthesize.py`
