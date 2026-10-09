# Conventions

> Note: some entries are aspirational (auto-derived from observed patterns) — see CLAUDE.md HIGHEST PRIORITY PRINCIPLES for hard rules.

## Naming Patterns
- Module scripts: lowercase with underscores (`ingest_wechat.py`, `multimodal_ingest.py`, `kg_synthesize.py`)
- Configuration: `config.py`
- Async functions: lowercase with underscores, descriptive names (`disambiguate_entities`, `ingest_pdf`, `synthesize_response`, `query_and_synthesize`)
- Helper functions: lowercase with underscores (`load_env`, `describe_image`, `llm_model_func`, `embedding_func`)
- Main entry points: `main()` in `if __name__ == "__main__"` blocks
- Constants: UPPERCASE with underscores (`GEMINI_API_KEY`, `RAG_WORKING_DIR`, `BASE_IMAGE_DIR`, `VENV_SITE_PACKAGES`)
- Local variables: lowercase with underscores (`query_text`, `response`, `canonical_map`, `pdf_path`)
- Cache/state: prefixed with underscore for internal use (`_disambiguation_cache`)
- Type hints used in function signatures: `list[str]`, `np.ndarray`, `dict`
- Return types documented in async functions: `async def function_name(...) -> ReturnType:`

## Code Style
- No explicit formatter configured (black/ruff not detected)
- Manual formatting conventions observed:
- No `.eslintrc`, `.pylintrc`, or similar configuration found
- No linting tool requirements detected in `requirements.txt`
- Manual code review likely the primary quality control

## Import Organization
- None detected. Full module paths used throughout (`from lightrag.lightrag import LightRAG`).
- Local modules imported directly by name (`import config`, `import lib.scraper`).

## Error Handling
- Return `None` on non-critical failures: helper functions in supporting modules
- `sys.exit(1)` on critical startup failures (missing API keys, imports)
- Print warnings and continue on recoverable errors

## Logging
- Module-level logger: `logger = logging.getLogger("module_name")`
- Levels used: `INFO`, `ERROR`, `WARNING`
- Basic configuration: `logging.basicConfig(level=logging.INFO)`
- File handlers for batch processes: `logging.FileHandler("/path/to/logfile.log")`
- Heavy use of `print()` for console output (not using logging in all cases)
- Examples: `query_lightrag.py`, `multimodal_ingest.py` use both print and logging
- Convention: Use `print()` for user-facing output, `logger` for operational logs

## Comments
- Inline comments for non-obvious logic (rare in this codebase)
- TODO/FIXME comments: None detected
- Configuration comments: Yes (e.g., "Force standard Gemini API mode")
- Minimal docstrings present
- Examples:
- Not consistently applied across all functions

## Function Design
- Functions range from 5 lines to 50+ lines
- Typical: 15-35 lines for business logic
- Larger functions: `ingest_pdf()` (~55 lines), `ingest_wechat()` (~150 lines)
- Use keyword arguments with defaults: `mode: str = "naive"`
- Environment-based configuration common (from `os.environ`)
- Async functions accept `**kwargs` for flexibility
- Early returns on error conditions
- Multiple return paths (success/failure):

## Module Design
- No explicit `__all__` definitions detected
- Functions defined at module level are importable
- Internal module state: `_disambiguation_cache = {}`
- Not used. Each module is self-contained.
- `config.py` serves as shared configuration module.
- Configuration loaded at module import time (top-level code execution)
- Example from `config.py`: Environment variables, logging setup, and module imports all happen at import time
- This means configuration is not testable without modifying environment

## Async Patterns
- `nest_asyncio.apply()` used to allow nested event loops (development/Jupyter compatibility)

## Antipatterns Observed
