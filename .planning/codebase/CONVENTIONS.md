# Coding Conventions

**Analysis Date:** 2026-04-21

## Naming Patterns

**Files:**
- Module scripts: lowercase with underscores (`cognee_wrapper.py`, `multimodal_ingest.py`, `kg_synthesize.py`)
- Configuration: `config.py`
- Test verification scripts: `verify_gate_*.py` (e.g., `verify_gate_a.py`)

**Functions:**
- Async functions: lowercase with underscores, descriptive names (`disambiguate_entities`, `ingest_pdf`, `synthesize_response`, `query_and_synthesize`)
- Helper functions: lowercase with underscores (`load_env`, `describe_image`, `llm_model_func`, `embedding_func`)
- Main entry points: `main()` in `if __name__ == "__main__"` blocks

**Variables:**
- Constants: UPPERCASE with underscores (`GEMINI_API_KEY`, `RAG_WORKING_DIR`, `BASE_IMAGE_DIR`, `VENV_SITE_PACKAGES`)
- Local variables: lowercase with underscores (`query_text`, `response`, `canonical_map`, `pdf_path`)
- Cache/state: prefixed with underscore for internal use (`_disambiguation_cache`)

**Types:**
- Type hints used in function signatures: `list[str]`, `np.ndarray`, `dict`
- Return types documented in async functions: `async def function_name(...) -> ReturnType:`

## Code Style

**Formatting:**
- No explicit formatter configured (black/ruff not detected)
- Manual formatting conventions observed:
  - 4-space indentation (standard Python)
  - Line length varies, no strict limit enforced
  - Function definitions followed by docstrings (inconsistent)

**Linting:**
- No `.eslintrc`, `.pylintrc`, or similar configuration found
- No linting tool requirements detected in `requirements.txt`
- Manual code review likely the primary quality control

## Import Organization

**Order:**
1. Standard library imports (`os`, `sys`, `asyncio`, `json`, `logging`, etc.)
2. Third-party imports (`pathlib`, `google.genai`, `PIL`, `numpy`, etc.)
3. Local imports (`from config import ...`, `import cognee_wrapper`, etc.)

**Examples from codebase:**

From `multimodal_ingest.py`:
```python
import os
import hashlib
import asyncio
import nest_asyncio
import fitz
from google import genai
from PIL import Image
import numpy as np
import sys
import json
```

From `config.py`:
```python
import os
from pathlib import Path
```

**Path Aliases:**
- None detected. Full module paths used throughout (`from lightrag.lightrag import LightRAG`).
- Local modules imported directly by name (`import cognee_wrapper`).

## Error Handling

**Patterns:**

1. **Broad Exception Catching (Common):**
   ```python
   # From cognee_wrapper.py:50-57
   try:
       await cognee.remember(f"Query: {query}\nResult: {synthesis_result}", self_improvement=False)
       return True
   except Exception as e:
       logger.error(f"remember_synthesis error: {e}")
       return None
   ```

2. **Specific Exception Types:**
   ```python
   # From cognee_wrapper.py:85-87
   except (asyncio.TimeoutError, Exception):
       _disambiguation_cache[entity] = entity
       canonical_entities.append(entity)
   ```

3. **Bare Except (Anti-pattern - Present):**
   ```python
   # From cognee_wrapper.py:94
   except: pass
   
   # From ingest_wechat.py:158
   except: pass
   ```

4. **ImportError Handling:**
   ```python
   # From multimodal_ingest.py:13-19
   try:
       from lightrag.lightrag import LightRAG
       from lightrag.llm.gemini import gemini_model_complete, gemini_embed
   except ImportError as e:
       print(f"Import error: {e}")
       sys.exit(1)
   ```

5. **Retry Loops:**
   ```python
   # From kg_synthesize.py:74-81
   for i in range(3):
       try:
           response = await rag.aquery(custom_prompt, param=param)
           break
       except Exception as e:
           print(f"Query attempt {i+1} failed: {e}")
           if i < 2: await asyncio.sleep(5)
           else: raise e
   ```

**Return Patterns on Error:**
- Return `None` on non-critical failures: `cognee_wrapper.py` functions
- `sys.exit(1)` on critical startup failures (missing API keys, imports)
- Print warnings and continue on recoverable errors

## Logging

**Framework:** `logging` module (Python standard library)

**Patterns:**
- Module-level logger: `logger = logging.getLogger("module_name")`
- Levels used: `INFO`, `ERROR`, `WARNING`
- Basic configuration: `logging.basicConfig(level=logging.INFO)`
- File handlers for batch processes: `logging.FileHandler("/path/to/logfile.log")`

**Examples from `cognee_batch_processor.py`:**
```python
logger = logging.getLogger("cognee_batch")
logger.setLevel(logging.INFO)
handler = logging.FileHandler("/home/sztimhdd/OmniGraph-Vault/cognee_batch.log")
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
```

**Print Statements:**
- Heavy use of `print()` for console output (not using logging in all cases)
- Examples: `query_lightrag.py`, `multimodal_ingest.py` use both print and logging
- Convention: Use `print()` for user-facing output, `logger` for operational logs

## Comments

**When to Comment:**
- Inline comments for non-obvious logic (rare in this codebase)
- TODO/FIXME comments: None detected
- Configuration comments: Yes (e.g., "Force standard Gemini API mode")

**JSDoc/Docstrings:**
- Minimal docstrings present
- Examples:
  ```python
  # From query_lightrag.py:18-19
  def load_env():
      """Load environment variables from ~/.hermes/.env if they are not already set."""
  ```
  ```python
  # From query_lightrag.py:35-36
  async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
      """Wrapper for Gemini LLM model completion."""
  ```
- Not consistently applied across all functions

## Function Design

**Size:**
- Functions range from 5 lines to 50+ lines
- Typical: 15-35 lines for business logic
- Larger functions: `ingest_pdf()` (~55 lines), `ingest_wechat()` (~150 lines)

**Parameters:**
- Use keyword arguments with defaults: `mode: str = "naive"`
- Environment-based configuration common (from `os.environ`)
- Async functions accept `**kwargs` for flexibility

**Return Values:**
- Early returns on error conditions
- Multiple return paths (success/failure):
  ```python
  # From cognee_wrapper.py
  if not cognee: return None
  try:
      # operation
      return results
  except Exception as e:
      logger.error(...)
      return []  # or None
  ```

## Module Design

**Exports:**
- No explicit `__all__` definitions detected
- Functions defined at module level are importable
- Internal module state: `_disambiguation_cache = {}`

**Barrel Files:**
- Not used. Each module is self-contained.
- `config.py` serves as shared configuration module.

**Environment Configuration:**
- Configuration loaded at module import time (top-level code execution)
- Example from `cognee_wrapper.py` (lines 7-45): Environment variables, logging setup, and module imports all happen at import time
- This means configuration is not testable without modifying environment

## Async Patterns

**Framework:** Native `asyncio`

**Pattern:**
```python
# From multimodal_ingest.py:173-182
if __name__ == "__main__":
    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY not found in environment.")
        sys.exit(1)
    if len(sys.argv) < 2:
        print("Usage: python multimodal_ingest.py <pdf_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    asyncio.run(ingest_pdf(pdf_path))
```

**Concurrency Helpers:**
- `nest_asyncio.apply()` used to allow nested event loops (development/Jupyter compatibility)

## Antipatterns Observed

1. **Bare except clauses** (`except: pass`) - `cognee_wrapper.py:94`, `ingest_wechat.py:158`
2. **No type hints on many functions** - Inconsistent use
3. **Print statements mixed with logging** - Both used throughout
4. **Environment configuration at import time** - Makes testing difficult
5. **Hardcoded paths** - `/home/sztimhdd/...` hardcoded in multiple files
6. **No constants module** - Magic strings scattered in code

---

*Convention analysis: 2026-04-21*
