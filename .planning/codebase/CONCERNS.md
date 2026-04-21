# Codebase Concerns

**Analysis Date:** 2026-04-21

## Tech Debt

### Hardcoded Absolute Paths (High Priority)

**Issue:** Multiple files contain hardcoded absolute paths specific to developer machine (`/home/sztimhdd/`), making the codebase non-portable and breaking on other systems.

**Files affected:**
- `cognee_batch_processor.py` (lines 9, 30, 35, 36)
- `cognee_wrapper.py` (line 8)
- `ingest_wechat.py` (lines 279, 280, 368)
- `init_cognee.py` (line 5, 23)
- `kg_synthesize.py` (line 50)
- `list_entities.py` (line 5)
- `query_lightrag.py` (line 12)
- `tests/verify_gate_a.py` (lines 6, 7)
- `tests/verify_gate_b.py` (line 6)
- `tests/verify_gate_c.py` (line 33)
- `setup_cognee.py` (line 23)

**Impact:** 
- Code cannot run on any machine except the original developer's system
- Blocks distribution, containerization, and CI/CD deployment
- Makes testing impossible in isolated environments

**Fix approach:**
- Centralize all paths in `config.py`
- Use `pathlib.Path` and environment-variable-based overrides
- Replace `/home/sztimhdd/` with `Path.cwd()` or `os.environ.get("PROJECT_ROOT", Path.cwd())`
- For entity buffer, use `config.ENTITY_BUFFER_DIR` (new constant)
- For canonical map, use `config.CANONICAL_MAP_FILE` (new constant)

### Inconsistent Path Resolution Across Modules

**Issue:** Some modules use `Path.home() / ".hermes"` while others use hardcoded `/home/sztimhdd/`. This creates dual path resolution paths that can drift.

**Files:**
- `config.py` (line 5): Uses `Path.home() / ".hermes" / "omonigraph-vault"` correctly
- `ingest_wechat.py` (line 279): Uses hardcoded `/home/sztimhdd/OmniGraph-Vault/entity_buffer`
- `kg_synthesize.py` (line 50): Uses hardcoded `/home/sztimhdd/OmniGraph-Vault/canonical_map.json`

**Impact:**
- Entity buffer and canonical map paths don't follow the same pattern as configured runtime dirs
- Difficult to change data location without auditing entire codebase

**Fix approach:**
- Export `ENTITY_BUFFER_DIR`, `CANONICAL_MAP_FILE` from `config.py`
- Update `ingest_wechat.py`, `cognee_batch_processor.py`, `kg_synthesize.py` to import and use these constants

### Missing JSON Import in kg_synthesize.py

**Issue:** `kg_synthesize.py` uses `json.load()` at line 54 but does not import `json`.

**Files:**
- `kg_synthesize.py` (line 54): `canonical_map = json.load(f)` but no `import json`

**Impact:**
- Code will crash at runtime with `NameError: name 'json' is not defined` when canonical map exists and is loaded
- This bug only manifests after first ingestion (when canonical_map.json is created)

**Fix approach:**
- Add `import json` at top of file

### Bare `except` Clauses (Code Smell)

**Issue:** Two instances of bare `except:` which catches all exceptions including `SystemExit` and `KeyboardInterrupt`, masking real errors.

**Files:**
- `cognee_wrapper.py` (line 94): `except: pass` after `cognee.remember()` call
- `ingest_wechat.py` (line 158): `except: pass` after `page.inner_text("#publish_time")`

**Impact:**
- Silent failures hide bugs and make debugging difficult
- Silently catches unintended exceptions (not just the ones being handled)
- No logging of what went wrong

**Fix approach:**
- Replace with specific exception types: `except Exception as e:` followed by logging
- For ingest_wechat.py line 158, catch only `asyncio.TimeoutError` or `AttributeError`
- For cognee_wrapper.py line 94, catch only `Exception` and log with `logger.debug()`

## Known Bugs

### PDF Ingestion References Undefined Variables

**Issue:** In `ingest_wechat.py` function `ingest_pdf()`, lines 366-369 reference variables `url`, `article_hash`, and `full_content` that are not defined in that scope.

**Symptoms:** 
- Code will crash with `NameError` if `ingest_pdf()` is called
- Variables are defined in `ingest_article()` but not in `ingest_pdf()`

**Files:** `ingest_wechat.py` (lines 365-372)

**Trigger:** Call `ingest_pdf()` function directly; it's defined but not called by main script

**Workaround:** None; function is currently unreachable from `__main__`

**Fix approach:**
- Replace `url` with `file_path`
- Replace `full_content` with `full_text` (the correct variable name in that function)
- Add `article_hash` computation from `file_hash` (already computed at line 317)
- Create entity buffer directory before attempting to write

### Missing Async/Await Consistency in ingest_pdf()

**Issue:** `ingest_pdf()` is defined as `async` but never awaited. The function calls async operations like `extract_entities()` and `rag.ainsert()` but does not store or return the coroutine results properly.

**Files:** `ingest_wechat.py` (lines 307-372)

**Impact:**
- Function exists but is never called in `__main__`
- If called, async operations might not complete before function returns

**Fix approach:**
- Ensure all `await` statements are present for async operations
- Function should be called with `await ingest_pdf(file_path)` from async context

### Loose Error Handling in Image Download Loop

**Issue:** In `ingest_wechat.py` lines 250-269, image download errors are caught and logged but don't fail gracefully if all images fail. The loop continues silently and the article is indexed regardless of image processing success.

**Files:** `ingest_wechat.py` (lines 250-269)

**Impact:**
- Articles with broken image URLs still get indexed but with descriptions like "Error describing image: ..."
- No indication to user that image extraction failed
- Misleading content in knowledge graph

**Fix approach:**
- Add counter for successful vs failed images
- Log warning if image success rate < 50%
- Consider option to halt ingestion if critical images fail

## Security Considerations

### API Key Exposure in Multiple Locations

**Issue:** `GEMINI_API_KEY` is loaded, set, and reassigned in multiple modules in different ways, creating redundant points where credentials could leak.

**Files:**
- `cognee_wrapper.py` (line 22): Sets via `os.environ`
- `ingest_wechat.py` (line 33): Loads via `os.environ`
- `kg_synthesize.py` (line 16): Sets via both `cognee.config` and `os.environ`
- `config.py` (line 12): Defines loading mechanism but doesn't execute it

**Current mitigation:** 
- Credentials stored in `~/.hermes/.env` (outside repo)
- `.env` file in root is in `.gitignore`

**Recommendations:**
- Consolidate key loading into `config.py` and import from there
- Avoid setting the same key into multiple places (redundancy increases leak surface)
- Add startup validation: `config.py` should verify all required secrets are loaded

### Environment File Parsing is Unsafe

**Issue:** Manual `.env` file parsing in `config.py`, `cognee_wrapper.py`, and others uses `split("=", 1)` without validation, potentially leading to injection attacks if `.env` file is maliciously edited.

**Files:**
- `config.py` (lines 15-24)
- `cognee_wrapper.py` (lines 14-19)
- Other modules repeat same pattern

**Current mitigation:** 
- `.env` file is outside repo and not user-editable via API
- System is single-user

**Recommendations:**
- Use `python-dotenv` library (already in `requirements.txt`) instead of manual parsing
- Validate `.env` keys against a whitelist

### Cognee API Key Assigned Without Validation

**Issue:** In `kg_synthesize.py` lines 15-22, Cognee configuration is forced with API key without checking if it's empty or None. This could cause confusing errors later.

**Impact:** 
- If `GEMINI_API_KEY` is empty, Cognee will be misconfigured silently
- Errors will appear later during actual inference, not at initialization

**Fix approach:**
- Add assertion in `config.py`: `assert GEMINI_API_KEY, "GEMINI_API_KEY must be set"`
- Validate at import time, not at first use

## Performance Bottlenecks

### Image Downloading Blocks Ingestion on Slow Networks

**Issue:** In `ingest_wechat.py` lines 250-269, images are downloaded sequentially (one at a time) with a 10-second timeout each. On networks with many images or slow connections, this can exceed the NFR-1 target (200ms ingestion).

**Problem:**
- 10 images × (download + vision API call) = potentially 100+ seconds
- No concurrent downloads or parallel processing

**Files:** `ingest_wechat.py` (line 253): `requests.get(img_url, timeout=10)`

**Cause:** Sequential loop, no asyncio.gather() or thread pooling

**Improvement path:**
- Use `asyncio.gather()` with semaphore to limit concurrent downloads (e.g., 3-5 concurrent)
- Set lower timeout for image downloads (5 seconds)
- Consider deferring image description to async Cognee batch processor instead of inline

### Cognee Batch Processor Runs Sequentially

**Issue:** In `cognee_batch_processor.py` line 87-89, entities are processed one file at a time. If buffer grows to 100+ files, processing becomes slow and blocks memory.

**Files:** `cognee_batch_processor.py` (lines 81-89)

**Cause:** No concurrent processing or batching

**Improvement path:**
- Use `asyncio.gather()` to process multiple files concurrently
- Add batch size limit (e.g., process max 10 files per run)
- Consider using `multiprocessing` instead of asyncio if I/O-bound assumption changes

### Query Mode Hard-Coded to "naive" in kg_synthesize.py

**Issue:** Default query mode is set to "naive" (line 93), but LightRAG supports "hybrid" which is faster and more accurate. The README recommends "hybrid" but code defaults to slower mode.

**Files:** `kg_synthesize.py` (line 93): `mode = sys.argv[2] if len(sys.argv) > 2 else "naive"`

**Impact:** 
- Users get slower, less accurate results unless they explicitly pass "hybrid"
- Contradicts README guidance

**Fix approach:**
- Change default to `"hybrid"`
- Document mode choices in help text

## Fragile Areas

### Dual Scraping Fallback Has Timing Issues

**Issue:** `ingest_wechat.py` scraping logic (lines 202-224) tries Apify first with 300-second timeout, then falls back to CDP. No mechanism to detect if Apify is in a bad state (e.g., returning verification pages).

**Files:** `ingest_wechat.py` (lines 90-169)

**Why fragile:**
- Apify timeout is very long (300s); user might think it's hung
- Detection of verification pages (line 213) is regex-based and brittle
- CDP fallback assumes Windows Edge is running at `CDP_URL`; if not available, fails silently

**Safe modification:**
- Add shorter health check before attempting Apify (5s timeout)
- Make verification-page detection configurable
- Test CDP availability at startup, warn if unavailable

**Test coverage:** No unit tests for fallback logic

### Knowledge Graph Index Rebuild on Every Ingest

**Issue:** Every call to `ingest_wechat.py` or `multimodal_ingest.py` creates a new LightRAG instance. If LightRAG rebuilds the graph index on each `ainsert()`, performance degrades with corpus size.

**Files:**
- `ingest_wechat.py` (line 273): `rag = await get_rag()`
- `multimodal_ingest.py` (line 154): `rag = await get_rag()`
- `query_lightrag.py` (line 63-72): Creates new instance per query

**Impact:**
- Unknown if index rebuilds are happening; depends on LightRAG internals
- Could cause quadratic performance degradation (O(n²) for n ingestions)

**Safe modification:**
- Profile with `get_rag()` calls; log if index rebuild occurs
- Consider singleton pattern to reuse RAG instance across calls
- Document LightRAG index persistence guarantees

**Test coverage:** No performance benchmarks

### Canonical Map String Replacement is Simplistic

**Issue:** In `kg_synthesize.py` lines 55-58, canonical mapping uses simple string replacement: `query_text.replace(raw, canonical)`. This can cause unintended replacements.

**Example:**
- Canonical map: `{"AI": "Artificial Intelligence"}`
- Query: "Is AI AI Agent a thing?" → "Is Artificial Intelligence Artificial Intelligence Agent a thing?" (wrong)

**Files:** `kg_synthesize.py` (lines 56-58)

**Why fragile:**
- No word-boundary checking
- Could replace entity names inside other words or phrases
- Mapping order matters if entities overlap

**Safe modification:**
- Use regex with word boundaries: `r'\b' + re.escape(raw) + r'\b'`
- Sort mappings by length (longest first) to avoid partial replacements
- Add unit tests for edge cases

**Test coverage:** No tests for canonical map replacement

## Scaling Limits

### Single-Process Bottleneck

**Current capacity:**
- Entity buffer can store unlimited JSON files but batch processor only processes them sequentially
- With 100 articles/day × 50 entities each = 5000 entity files/day
- Sequential processing @ ~100ms per file = ~8 minutes to process daily batch

**Scaling path:**
- Add concurrent batch processing (limit to 3-5 concurrent tasks)
- Implement worker pool pattern or Celery for distributed processing
- Add metrics/monitoring to track backlog growth

### Memory Usage During Large PDF Ingest

**Issue:** `ingest_wechat.py` and `multimodal_ingest.py` load entire PDFs into memory, then build full text string before indexing.

**Files:**
- `ingest_wechat.py` (line 313-329): Loads full PDF via PyMuPDF
- `multimodal_ingest.py` (line 110-150): Same pattern

**Limit:** Unknown; depends on PDF size. Large PDFs (100+ MB) could exhaust memory.

**Scaling path:**
- Process PDFs in chunks (e.g., 10 pages at a time)
- Stream text to LightRAG instead of concatenating in memory
- Add max file size validation with user-friendly error

### No Rate Limiting on Gemini API Calls

**Issue:** Image description loop (lines 250-269) calls Gemini Vision for every image without rate limiting or batching.

**Files:** `ingest_wechat.py` (line 259): `describe_image(img_path)` called in tight loop

**Limit:** Unknown; depends on Gemini API quotas and project settings

**Scaling path:**
- Implement exponential backoff for API rate limit errors
- Batch image descriptions into single Gemini request (if API supports it)
- Add configurable max images per ingest (e.g., max 10 images)

## Dependencies at Risk

### Cognee Integration is Loosely Coupled and Fragile

**Issue:** Cognee is imported and configured in multiple files, but failures are mostly silently caught. If Cognee library changes API or breaks, code might continue running with degraded functionality.

**Files:**
- `cognee_wrapper.py` (lines 36-45): Import wrapped in try/except with `cognee = None`
- `kg_synthesize.py` (lines 2, 15-19): Direct config manipulation
- `ingest_wechat.py` (line 16): Imported but error handling unclear

**Current mitigation:**
- Cognee operations wrapped in try/except; failures don't block ingestion

**Risk:**
- Silent degradation; users won't know if Cognee is working

**Mitigation:** 
- Add startup health check for Cognee availability
- Log Cognee status (enabled/disabled) at startup
- Document which features require Cognee

### LightRAG API Assumptions

**Issue:** Code assumes LightRAG has methods `ainsert()`, `aquery()`, and optional `initialize_storages()`. If library updates change API, code breaks.

**Files:**
- `ingest_wechat.py` (line 286): `await rag.ainsert(full_content)`
- `query_lightrag.py` (line 78): `await rag.aquery(query_text, param=param)`

**Current mitigation:**
- Version pinning in `requirements.txt` (implicit; no version specified)

**Risk:**
- `pip install` could pull incompatible version

**Recommendations:**
- Pin LightRAG version in `requirements.txt` (e.g., `lightrag==0.x.y`)
- Add integration tests that verify API surface

### Playwright Version Pinning

**Issue:** `requirements.txt` does not pin Playwright version. Browser automation code is brittle across versions.

**Files:** `ingest_wechat.py` (line 9): `from playwright.async_api import async_playwright`

**Risk:**
- New Playwright version could change CDP connection handling
- Browser behavior changes across versions

**Recommendations:**
- Pin `playwright` to specific version (e.g., `playwright==1.40.0`)
- Document browser version tested (e.g., "Tested with Chromium 120")

## Missing Critical Features

### No Retry Logic for Transient Failures

**Issue:** Network calls (Apify, Gemini, image downloads) can fail transiently but are not retried systematically.

**What's missing:**
- Retry on 429 (rate limit) responses
- Exponential backoff for transient errors
- Jitter to avoid thundering herd

**Impact:**
- A single network hiccup causes entire ingestion to fail
- User must manually re-run command

**Fix approach:**
- Implement `@retry(max_attempts=3, backoff='exponential')` decorator
- Apply to: Apify calls, Gemini Vision calls, image downloads

### No Deduplication Logic

**Issue:** If same URL is ingested twice, content is added to KG again, creating duplicates.

**Files:** `ingest_wechat.py` (line 202-306)

**Impact:**
- Same knowledge appears twice in graph
- Query results repeat content
- Entity canonicalization may create duplicates

**Fix approach:**
- Add URL hash deduplication in `ingest_article()`: check if hash already exists before inserting
- Maintain `ingested_urls.json` manifest or query LightRAG for existing content

### No Health Check / Monitoring

**Issue:** No built-in way to verify system health: Is LightRAG working? Is Cognee working? How much data is stored?

**Missing:**
- CLI command to check status of all components
- Log of ingestion success/failure rates
- Metrics on graph size, entity count

**Fix approach:**
- Add `health_check.py` that verifies: LightRAG accessibility, Cognee memory, API keys, disk space
- Add metrics export (JSON or CSV)

## Test Coverage Gaps

### No Unit Tests for Configuration Module

**Issue:** `config.py` is core to the system but has no tests. Path resolution bugs could go undetected.

**Files:** `config.py`

**What's not tested:**
- `.env` file loading
- Path construction
- Fallback to default values

**Risk:** Medium - Path bugs only surface at runtime on different machines

**Priority:** Medium

### No Integration Tests for Scraping Fallback

**Issue:** Dual-path scraping (Apify → CDP) is complex but has no integration tests.

**Files:** `ingest_wechat.py` (lines 90-169)

**What's not tested:**
- Apify success path
- Apify timeout and fallback to CDP
- CDP failure handling
- Verification page detection

**Risk:** High - Scraping is core feature; bugs here block ingestion entirely

**Priority:** High

### No Tests for Entity Disambiguation

**Issue:** Entity canonicalization logic in `cognee_wrapper.py` has no tests.

**Files:** `cognee_wrapper.py` (lines 68-88)

**What's not tested:**
- Cache hit/miss behavior
- Timeout handling
- Empty entity list

**Risk:** Medium - Entity duplication could degrade query quality

**Priority:** Medium

### No Tests for Canonical Map Application

**Issue:** Canonical mapping in `kg_synthesize.py` has no tests.

**Files:** `kg_synthesize.py` (lines 56-58)

**What's not tested:**
- Simple replacement (already noted as fragile)
- Edge cases (empty query, missing map file, map load failure)

**Risk:** Medium - Wrong entity normalization could produce nonsense results

**Priority:** Medium

### No End-to-End Tests

**Issue:** No complete integration test that:
1. Ingests a test article
2. Verifies it's in LightRAG
3. Queries for expected results
4. Checks entity buffer was created
5. Runs batch processor
6. Verifies canonical map was updated

**Impact:** Regressions in full pipeline not caught

**Priority:** High - This is the core user flow

---

*Concerns audit: 2026-04-21*
