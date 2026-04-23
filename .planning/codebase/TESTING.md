# Testing Patterns

**Analysis Date:** 2026-04-21

## Test Framework

**Status:** Not fully configured

**Runner:**
- No pytest, unittest, or other framework configured
- `requirements.txt` does not include `pytest`, `pytest-asyncio`, or `unittest` 
- No `conftest.py`, `pytest.ini`, `setup.py`, or test configuration files detected

**Assertion Library:**
- Not applicable; no structured testing framework in place

**Run Commands:**
```bash
# Manual test verification scripts (not automated)
python tests/verify_gate_a.py   # Gate A: cognee.remember() functionality
python tests/verify_gate_b.py   # Gate B: cognee.recall() and search
python tests/verify_gate_c.py   # Gate C: entity disambiguation
```

## Test File Organization

**Location:**
- Tests stored in `tests/` directory at project root
- Test files alongside main source code

**Naming:**
- Verification gates: `verify_gate_*.py` (e.g., `verify_gate_a.py`)
- Named by feature/capability, not unit/integration convention

**Structure:**
```
OmniGraph-Vault/
├── tests/
│   ├── verify_gate_a.py
│   ├── verify_gate_b.py
│   └── verify_gate_c.py
├── cognee_wrapper.py
├── config.py
├── multimodal_ingest.py
└── ... (main modules)
```

## Test Structure

**Pattern: Manual Verification Gates**

Tests follow a simple manual verification pattern without a testing framework:

```python
# From tests/verify_gate_a.py (lines 26-40)
async def main():
    # Prints cognee version
    version = getattr(cognee, "__version__", "unknown")
    print(f"Cognee version: {version}")
    
    try:
        # Calls 'await cognee.remember("Gate A validation test")'
        await cognee.remember("Gate A validation test")
        # Prints 'Gate A Verified' if successful
        print("Gate A Verified")
    except Exception as e:
        print(f"Gate A Validation Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

**Patterns:**

1. **Setup Pattern:**
   - Environment configuration duplicated in each test file (lines 5-23)
   - sys.path manipulation to ensure venv packages are accessible
   - Environment variables set explicitly for Cognee/LLM configuration

2. **Assertion Pattern:**
   - String matching in output: `if 'sunny' in str(result).lower()`
   - Print statements for pass/fail indication
   - No structured assertions

3. **Error Handling:**
   ```python
   # From verify_gate_b.py:25-48
   try:
       # test operation
   except Exception as e:
       # handled implicitly
   ```

## Mocking

**Framework:** None detected

**Pattern:** 
- No mocking libraries (`unittest.mock`, `pytest-mock`, `responses`, etc.) in `requirements.txt`
- Tests directly call live APIs (Google Gemini, LightRAG)
- No fixtures or mock data structures

**What IS Mocked:**
- Nothing; all integration is direct

**What SHOULD be Mocked (not currently):**
- External API calls (Google Gemini API, Cognee API)
- File I/O operations
- Database connections (LightRAG)

## Fixtures and Factories

**Test Data:**
- No test data factories or fixtures
- Tests use hardcoded strings:
  ```python
  # From verify_gate_a.py:33
  await cognee.remember("Gate A validation test")
  
  # From verify_gate_c.py:58,61
  await cognee.remember("Entity: 知识图谱. Description: A structured...")
  await cognee.remember("Entity: Knowledge Graph. Description:...")
  ```

**Location:**
- No dedicated test data directory
- Data embedded inline in test files

## Coverage

**Requirements:** None enforced

**View Coverage:**
- No coverage tool configured
- Manual verification only

**Gaps:**
- No unit test coverage for utility functions
- No tests for error conditions
- No tests for configuration loading (`config.py`)
- No tests for batch processing (`cognee_batch_processor.py`)
- No tests for API response parsing

## Test Types

**Unit Tests:**
- Not structured formally
- Could apply to: `config.load_env()`, `cognee_wrapper` functions
- Currently not implemented

**Integration Tests:**
- All three verification gates are integration tests:
  - `verify_gate_a.py`: Tests cognee.remember() + logging
  - `verify_gate_b.py`: Tests cognee.recall() + cognee.search()
  - `verify_gate_c.py`: Tests entity disambiguation across multiple remember() calls
- Tests hit live APIs (Gemini, Cognee)
- Require environment variables set correctly

**E2E Tests:**
- Not implemented
- Would test full workflows: ingest → synthesize → query

## Common Patterns

**Async Testing:**

All test gates are async using native asyncio:

```python
# From verify_gate_b.py:25
async def main():
    await cognee.remember('Query: What is the weather in Shanghai?...')
    result = await cognee.recall('Tell me about Shanghai weather')
    print(f"Recall Result: {result}")

if __name__ == '__main__':
    asyncio.run(main())
```

**Error Testing:**

Tests catch and print exceptions but don't validate error types:

```python
# From verify_gate_a.py:31-37
try:
    await cognee.remember("Gate A validation test")
    print("Gate A Verified")
except Exception as e:
    print(f"Gate A Validation Failed: {e}")
```

Better pattern would be:
```python
# Not currently used
assert "sunny" in str(result).lower(), f"Expected 'sunny' in result, got: {result}"
```

## Environment Setup

**Configuration Duplication:**

Each test file duplicates environment setup (anti-pattern):

```python
# From verify_gate_c.py:6-50 (same in verify_gate_a.py and verify_gate_b.py)
def load_env(file_path):
    expanded_path = os.path.expanduser(file_path)
    if os.path.exists(expanded_path):
        with open(expanded_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

load_env('~/.hermes/.env')

# Environment configuration repeated verbatim across all test files:
os.environ['GOOGLE_API_KEY'] = os.getenv('GEMINI_API_KEY')
os.environ['LLM_API_KEY'] = os.getenv('GEMINI_API_KEY')
os.environ['LLM_PROVIDER'] = 'gemini'
os.environ['LLM_MODEL'] = 'gemini-2.5-flash'
# ... (15+ lines per file)
```

**Recommended Consolidation:**
- Move this to `conftest.py` (pytest) or `tests/__init__.py` (shared fixture)
- Or import from `config.py` if testable

## Issues and Gaps

1. **No Framework:** Manual print-based verification instead of pytest/unittest
2. **No Isolation:** Tests execute with side effects (write to Cognee, modify state)
3. **No Fixtures:** Hardcoded test data and environment configuration
4. **Duplicated Setup:** Each test file repeats env configuration (60+ lines duplication)
5. **Bare Except:** Tests catch all exceptions with no assertion
6. **No Cleanup:** No teardown logic; state persists between test runs
7. **No CI Integration:** Tests not suitable for automated CI/CD pipelines
8. **Missing Coverage:** Many core functions untested:
   - `config.load_env()` - `c:/Users/huxxha/Desktop/OmniGraph-Vault/config.py`
   - `ingest_pdf()` - `c:/Users/huxxha/Desktop/OmniGraph-Vault/multimodal_ingest.py`
   - `disambiguate_entities()` - `c:/Users/huxxha/Desktop/OmniGraph-Vault/cognee_wrapper.py`
   - Batch processing - `c:/Users/huxxha/Desktop/OmniGraph-Vault/cognee_batch_processor.py`

## Hermes Skill Simulator

Because Hermes uses Gemini as its LLM backend — the same model already in this stack — skill execution can be simulated locally with no Hermes installation required.

**Implementation:** `skill_runner.py` at project root.

**What it simulates:**
- Loads `SKILL.md` body as the system prompt
- Optionally injects `references/` files (Level 2 loading)
- Sends a test input message to Gemini API
- Asserts `expect_contains` / `expect_not_contains` against the response
- Tests `scripts/` standalone via `subprocess`

**Test cases:** `tests/skills/test_<skill_name>.json`

**Run commands:**
```bash
# Single skill, single message
python skill_runner.py skills/omnigraph_query "what do I know about LightRAG?"

# Full test suite for one skill
python skill_runner.py skills/omnigraph_query --test-file tests/skills/test_omnigraph_query.json

# Validate all skill structures (no API call)
python skill_runner.py skills/ --validate

# Run all skill test suites
python skill_runner.py skills/ --test-all
```

**Limitations:** Does not validate Hermes-specific tool dispatch or `triggers` auto-matching — those require a live Hermes instance (Gate 7).

## Phase 2 Testing Strategy

**Local E2E without Hermes:**
- Developers run `skill_runner.py` tests locally before committing
- No Hermes installation required; same Gemini backend as Hermes uses
- Tests validate: skill routing, guard clauses, output format, error handling

**Infrastructure Requirements:**
- `skill_runner.py`: Exit codes 0 (pass) / non-zero (fail) for CI compatibility
- No remote MCP blocker: Use local CDP (`http://localhost:9223`) for testing
- Error messages must be human-readable (no Python tracebacks to end users)

**Test Coverage:**
- Happy path: valid skill trigger, expected output
- Wrong-skill redirect: query should route to correct skill, not wrong one
- Guard clause: skill should error cleanly when env var missing or image server down
- Format validation: output matches expected structure (Markdown, JSON, or plain text as defined)

## Recommended Testing Strategy

**Phase 1: Skill simulator** (DONE: existing implementation)
- ✓ `skill_runner.py` implemented using existing `google-genai` dependency
- ✓ Test cases in `tests/skills/` for `omnigraph_ingest` and `omnigraph_query`
- ✓ Run before every commit that touches `skills/`

**Phase 2: Infrastructure hardening** (current milestone)
- Local E2E testing without Hermes (documented above)
- Exit code compliance for CI/CD pipelines
- Human-readable error handling (no tracebacks)
- Installation script with smoke tests

**Phase 3: Establish framework for pipeline code**
- Install `pytest` and `pytest-asyncio`
- Create `conftest.py` with shared env fixture (eliminate the 60-line duplication)
- Refactor verification gates to pytest assertions

**Phase 4: Unit tests**
- `config.load_env()` with mock file I/O
- `cognee_wrapper` functions with mocked Cognee
- Batch processor idempotency (`cognee_batch_processor.py`)

**Phase 5: Automation**
- `python skill_runner.py skills/ --test-all` in GitHub Actions on `skills/**` changes
- Separate unit (fast, no API) from integration (slow, live API) pytest marks

---

*Testing analysis: 2026-04-21*
