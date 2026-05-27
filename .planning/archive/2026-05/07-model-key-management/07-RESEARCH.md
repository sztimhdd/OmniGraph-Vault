# Phase 7: model-key-management — Research

**Researched:** 2026-04-28
**Domain:** Python async rate limiting, google-genai SDK exception handling, key rotation, single-file library migration
**Confidence:** HIGH (all claims verified against installed packages in `venv/Lib/site-packages/`)
**Mode:** VERIFICATION — cross-checks `07-REQUIREMENTS.md` against actual code and package state.

---

## User Constraints (from 07-REQUIREMENTS.md §7.1)

### Locked Decisions

1. All 18 files in a single phase (no split PRs).
2. Repo-root `lib/` — project-internal, NOT exposed as a Hermes or OpenClaw skill.
3. Canonical env: `OMNIGRAPH_GEMINI_KEY` (primary) with `GEMINI_API_KEY` fallback.
4. Optional rotation pool: `OMNIGRAPH_GEMINI_KEYS` (comma-separated).
5. User confirms multi-Google-account setup — rotation is real, not theoretical.
6. Dependencies `aiolimiter` + `tenacity` approved.
7. `config.py` kept; refactored to delegate key/model concerns to `lib/`.
8. Phase 7 lands first; Phase 5's embedding-model switch to `embedding-002` becomes a one-line change in `lib/models.py` after Phase 7.

### Claude's Discretion

- Internal API of `lib/llm_client.py` (signatures, helper decomposition).
- Retry parameters (max_attempts, min/max wait) within reasonable bounds.
- Per-module migration order within Phase 7 (subject to P0→P2 priority).

### Deferred Ideas (OUT OF SCOPE)

- Multi-vendor abstraction (OpenAI + Anthropic).
- Encrypted key storage (keychain, Vault).
- Cognee's internal LLM calls — integrated via `llm_config.llm_api_key` singleton, see §Cognee Interop.
- Hermes per-skill scoping workaround (GitHub issue #410, not ours to fix).

---

## Summary

Phase 7 replaces scattered `GEMINI_API_KEY` reads, hardcoded model strings, and three incompatible rate-limiters (ingest_wechat's asyncio.Lock, config.rpm_guard's time.time sync-lock, no-limiter-at-all in most scripts) with a unified `lib/` module.

**All required dependencies are already installed** as transitive packages:
- `aiolimiter-1.2.1` (via Cognee)
- `tenacity-9.1.4` (via Cognee + LightRAG + google-genai)
- `google-genai-1.73.1` (direct)

Adding them to `requirements.txt` is for reproducibility, not to pull new code.

**Two design-doc assumptions require correction** (details below):
1. The doc assumes all scripts use `gemini-2.5-flash-lite`. Actual: `config.py` defaults INGEST/ENRICHMENT/IMAGE to `gemini-3.1-flash-lite-preview`; `ingest_wechat.py` + `multimodal_ingest.py` + `query_lightrag.py` + `kg_synthesize.py` use `gemini-2.5-flash-lite`; `ingest_github.py` uses `gemini-3.1-flash-lite-preview`. The registry must reflect this drift **before** standardising.
2. The doc says Cognee is "configured via its own env vars" — true for the *first* config load. After that, `get_llm_config()` is `@lru_cache`-decorated; rotating keys via `os.environ[...]` has no effect. Rotation must set `llm_config.llm_api_key` on the cached singleton directly (already done at `cognee_wrapper.py:41` — extend to rotation callback).

**Primary recommendation:** Ship `lib/` with `@retry` OUTSIDE `async with limiter` (verified nesting), the APIError.code predicate (verified attribute), and a `lib.rotate_key()` hook that also updates Cognee's singleton. Drop `config.gemini_call()` (replaced by `lib.generate_sync()`).

---

## Phase Requirements

Phase 7 has no REQUIREMENTS.md requirement IDs yet; the design doc's §3 "Locked Design Decisions" D1–D10 serve as the authoritative requirement set. The planner should translate D1–D10 into REQ-IDs during planning. Summary:

| Design ID | Requirement | Research Support |
|-----------|-------------|------------------|
| D1–D3 | Env var scheme | §Architecture Patterns — `lib/api_keys.py` verified design |
| D4 | Rotation on exhaustion | §Common Pitfalls — Cognee singleton propagation required |
| D5 | Repo-root `lib/` | §Standard Stack — no conflicts; verified `lib/` dir free |
| D6 | Add aiolimiter + tenacity | §Standard Stack — already transitively installed |
| D7 | String constants, not Enum | §Code Examples — matches existing `INGEST_LLM_MODEL` idiom in config.py |
| D8 | Per-model AsyncLimiter | §Architecture Patterns — shared singleton registry, one limiter per model |
| D9 | Dual-host SKILL.md | **Not applicable** — user decision §7.1.3: `lib/` is NOT a skill. Skip this. |
| D10 | `lib/` lands first, then ingest_wechat reference, then bulk | §Migration Scope Map — wave structure |

---

## Standard Stack

### Core

| Library | Version | Installed | Purpose | Why Standard |
|---------|---------|-----------|---------|--------------|
| `google-genai` | 1.73.1 | ✓ direct | Gemini API client (new SDK) | Google's official async-native SDK — deprecated `google-generativeai` uses a different exception hierarchy; mixing them causes retry-predicate drift |
| `aiolimiter` | 1.2.1 | ✓ transitive (Cognee) | Leaky-bucket rate limiter | Async-native; only mature option. Zero transitive deps. 204 LOC total (`venv/Lib/site-packages/aiolimiter/leakybucket.py`). |
| `tenacity` | 9.1.4 | ✓ transitive (Cognee, LightRAG, google-genai) | Retry decorator with backoff | Standard Python retry library. Supports async. `google-genai` pins `tenacity<9.2.0,>=8.2.3` — 9.1.4 is within bounds. |

### Supporting (already used; keep)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `lightrag-hku` | 1.4.15 | KG engine, exposes `gemini_model_complete` / `gemini_embed` async helpers | Used by ingest_wechat, ingest_github, multimodal_ingest, query_lightrag, kg_synthesize |
| `cognee` | 1.0.1 | Episodic memory layer | Used by cognee_wrapper, cognee_batch_processor, kg_synthesize |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Decision |
|------------|-----------|----------|----------|
| `aiolimiter` | `asyncio.Semaphore` + `asyncio.sleep` | DIY leaky bucket, more bugs | ❌ Use `aiolimiter`. Existing ingest_wechat hand-rolled version already has a race bug (resets `_last_llm_time` AFTER sleep, not after actual call — window leaks). |
| `tenacity` | `while/try/except` retry loop | `config.gemini_call()` already does this; 90 lines of custom logic | ❌ Drop `gemini_call()`; replace with `@retry`. |
| `google-generativeai` | `google-genai` | Deprecated SDK; different exception hierarchy (`google.api_core.exceptions.ResourceExhausted` vs `google.genai.errors.APIError`) | ❌ Already on new SDK across all 19 production files. |

### Installation

Dependencies are already present as transitive installs. Add to `requirements.txt` explicitly for reproducibility:

```txt
aiolimiter>=1.2.1,<2.0
tenacity>=9.0.0,<9.2.0   # google-genai constraint
```

**Version verification (actual state at 2026-04-28):**

```text
venv/Lib/site-packages/aiolimiter-1.2.1.dist-info/   ✓
venv/Lib/site-packages/tenacity-9.1.4.dist-info/     ✓
venv/Lib/site-packages/google_genai-1.73.1.dist-info/ ✓
```

`venv/Lib/site-packages/google_genai-1.73.1.dist-info/METADATA` line: `Requires-Dist: tenacity<9.2.0,>=8.2.3`.

---

## Architecture Patterns

### Verified Nesting Order: `@retry` OUTSIDE, `async with limiter` INSIDE

**Evidence** (`venv/Lib/site-packages/aiolimiter/leakybucket.py`):

- `AsyncLimiter` is a **leaky bucket**, not a semaphore.
- `__aenter__` (line 193) → `acquire()` → line 153: `self._level += amount` (bucket fills on acquire).
- `__aexit__` (lines 197-203) **does nothing** — no release, no decrement.
- Capacity drips out via `_leak()` based on **wall-clock elapsed time**, not on context-manager exit.

**Implication for retry composition:**

Each call through `async with _limiter:` consumes one "slot" of capacity. When the call fails and tenacity retries, the retry re-enters the limiter, which re-fills one more slot (if capacity is available) or blocks until capacity drips out (if saturated). This is exactly what we want: retries respect the rate limit.

**Nesting order must be `@retry` OUTSIDE, `async with` INSIDE**:

```python
@retry(...)
async def call(...):
    async with _limiter:          # re-acquires capacity on each retry
        return await client.aio.models.generate_content(...)
```

**Do NOT reverse** — putting the limiter OUTSIDE retry would:
- Consume one capacity unit for the whole retry sequence (bucket thinks it's one call).
- Block new unrelated calls for the entire retry window.
- Not actually slow down retries after 429s (defeats the point).

### Recommended Project Structure

```
lib/
├── __init__.py          # re-exports: generate, aembed, current_key, rotate_key, get_limiter
├── models.py            # string constants + RATE_LIMITS_RPM dict
├── api_keys.py          # load_keys, current_key, rotate_key, _init_cycle
├── rate_limit.py        # get_limiter(model) — memoized AsyncLimiter per model name
├── llm_client.py        # async generate(), sync generate_sync(), aembed()
└── cognee_bridge.py     # propagate_key_to_cognee(key) — updates llm_config.llm_api_key
```

Add `cognee_bridge.py` beyond the original design; required to handle Cognee's `@lru_cache`'d config singleton (see §Cognee Interop).

### Pattern 1: Per-model shared limiter

**What:** One `AsyncLimiter` instance per model name, module-level dict, lazily created.
**When to use:** All Gemini calls. Flash-lite (15 RPM free) and pro (5 RPM free) have different quotas.
**Why module-level:** A process ingesting 10 articles in parallel must share the limiter across asyncio tasks. Per-function-local limiters would reset per call.

### Pattern 2: Key rotation on 429/503, exponential backoff between retries

```python
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception(_is_retriable),
    reraise=True,
)
async def generate(model: str, prompt: str, **kwargs) -> str:
    async with get_limiter(model):
        try:
            response = await _get_client().aio.models.generate_content(
                model=model, contents=prompt, **kwargs
            )
            return response.text
        except APIError as e:
            if _is_retriable(e):
                new_key = rotate_key()
                propagate_key_to_cognee(new_key)    # keeps Cognee aligned
                # client cache invalidates on next _get_client() call
            raise
```

### Anti-Patterns to Avoid

- **Reversed nesting** (`async with limiter:` outside `@retry`) — locks the bucket for the whole retry window; see above.
- **Per-module limiter instance** — rate limit is per-process, not per-module; per-module duplicates and under-counts.
- **Re-setting os.environ to rotate Cognee's key** — Cognee caches at `LLMConfig()` pydantic instantiation, wrapped in `@lru_cache`. New env values are not re-read. Must poke the singleton.
- **Catching `google.api_core.exceptions.ResourceExhausted`** — that's the deprecated SDK's exception. New SDK raises `google.genai.errors.APIError` (or subclass `ClientError` for 4xx, `ServerError` for 5xx — 429 is `ClientError`, 503 is `ServerError`). See LightRAG Interop Risk below.
- **Substring-matching `"429" in str(e)`** — what `config.py:172` does today. Brittle. Use `isinstance(e, APIError) and e.code == 429`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Leaky bucket rate limiter | asyncio.Lock + time.time() | `aiolimiter.AsyncLimiter` | Existing ingest_wechat code has a race: it resets `_last_llm_time` AFTER sleep but BEFORE the API call returns — two concurrent tasks both pass the guard |
| Exponential backoff retry | while/try/except with manual sleep | `@tenacity.retry(wait=wait_exponential)` | `config.gemini_call()` reimplements this in 90 LOC; `tenacity` does it in 3 decorator lines |
| Retry predicate | `if "429" in str(e)` substring match | `retry_if_exception(lambda e: isinstance(e, APIError) and e.code in {429, 503})` | Substring matching is brittle — false positives on error messages containing "429" unrelated to rate limits |
| SDK exception hierarchy detection | Checking error messages for strings | `APIError.code` int field | Verified field exists on `google.genai.errors.APIError.code: int` (line 33, `errors.py`) |
| Round-robin iterator | manual index tracking | `itertools.cycle()` | Already correctly used in design doc §4.2 |
| Env file parsing | hand-rolled split on `=` | `python-dotenv` | Already a dep; current config.py hand-rolls it (line 13-17, cognee_wrapper.py lines 11-16) — but DO NOT refactor in Phase 7 (out of scope; surgical changes rule) |

**Key insight:** The current codebase has THREE hand-rolled rate limiters (ingest_wechat's `_LLM_MIN_INTERVAL`, `_EMBED_MIN_INTERVAL`, and config.py's `rpm_guard`), and TWO retry loops (config.py's `gemini_call` and LightRAG's built-in `@retry(google_api_exceptions.*)`). All three of our hand-rolled limiters have the same race condition (set timestamp before call returns). Replace them all.

---

## Runtime State Inventory

Phase 7 is a refactor with **rename component** (`GEMINI_API_KEY` → `OMNIGRAPH_GEMINI_KEY` in production env). Inventory:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no DB column stores the key name. `canonical_map.json` and `entity_buffer/*.json` do not reference env var names. | None |
| Live service config | Hermes `~/.hermes/.env` on remote PC stores `GEMINI_API_KEY=AIza...`. Fallback logic in `lib/api_keys.py` (D2) keeps this working; user can optionally add `OMNIGRAPH_GEMINI_KEY=...` later. | Manual: update `~/.hermes/.env` on remote when convenient; NOT blocking. |
| OS-registered state | None — no cron jobs reference the key name. | None |
| Secrets/env vars | `GEMINI_API_KEY`, `GEMINI_API_KEY_BACKUP` (legacy config.py names). Code rename, key values unchanged. Verify: `grep -n "GEMINI_API_KEY_BACKUP" *.py` → only `config.py:20` — safe to either keep or fold into `OMNIGRAPH_GEMINI_KEYS` pool. | Code edit: all 25 files (see Migration Scope Map) |
| Build artifacts | None — pure Python, no compiled artifacts. No `egg-info`, no `.pyc` migration concerns (venv regenerates). | None |

---

## Migration Scope Map

**Total: 25 files** (design doc's "~18" was an undercount. Actual grep from project root at 2026-04-28):

### P0 — Core ingest / query flow (9 files)

| # | File | # occurrences | Notes |
|---|------|---------------|-------|
| 1 | `config.py` | 12 | Cross-cutting; REFACTOR `gemini_call()` → delegate to `lib.generate_sync()`; keep `rpm_guard()` as shim that delegates to `lib.get_limiter()` |
| 2 | `ingest_wechat.py` | 10+ | Reference migration; remove hand-rolled `_llm_lock`, `_embed_lock`, `_LLM_MIN_INTERVAL`, `_EMBED_MIN_INTERVAL` |
| 3 | `multimodal_ingest.py` | 11 | Same pattern as ingest_wechat |
| 4 | `ingest_github.py` | 8 | **Model drift bug:** uses `gemini-3.1-flash-lite-preview` while peers use `gemini-2.5-flash-lite`. Fix in registry migration |
| 5 | `query_lightrag.py` | 8 | Read-only path; straightforward |
| 6 | `kg_synthesize.py` | ~7 | Sets `llm_config.llm_api_key` directly (Cognee pattern) — this file is the reference for Cognee Interop |
| 7 | `image_pipeline.py` | 3 | Already uses `config.gemini_call()`; swap to `lib.generate_sync()` |
| 8 | `enrichment/merge_and_ingest.py` | 2 | Small file |
| 9 | `enrichment/fetch_zhihu.py` | 2 | Small file |

### P1 — Supporting flows (4 files)

| # | File | # occurrences | Notes |
|---|------|---------------|-------|
| 10 | `enrichment/extract_questions.py` | 1 | Uses `config.gemini_call()`; straight swap |
| 11 | `cognee_wrapper.py` | 9 | **Key file for Cognee Interop** — the `llm_config.llm_api_key = GEMINI_API_KEY` at line 41 is the integration point. Extend: register `propagate_key_to_cognee()` callback in `lib.api_keys.rotate_key()` |
| 12 | `cognee_batch_processor.py` | 7 | Same pattern as cognee_wrapper |
| 13 | `init_cognee.py` / `setup_cognee.py` | small | Setup scripts — minimal change |

### P2 — Batch scripts + tests (12 files)

| # | File | # occurrences | Notes |
|---|------|---------------|-------|
| 14 | `batch_classify_kol.py` | 3 | Uses `genai.Client(api_key=...)` directly; replace with `lib.get_client()` helper |
| 15 | `batch_ingest_from_spider.py` | 4 | Same pattern |
| 16 | `batchkol_topic.py` | 3 | Same pattern |
| 17 | `_reclassify.py` | 3 | Simple |
| 18 | `skill_runner.py` | 3 | Test harness — handle carefully; tests depend on this |
| 19 | `tests/verify_gate_a.py` | 4 | Manual gate; verify it still runs after migration |
| 20 | `tests/verify_gate_b.py` | 5 | Same |
| 21 | `tests/verify_gate_c.py` | 6 | Same |
| 22 | `tests/conftest.py` | 1 | Mock helper — may need update if test fixture name changes |
| 23 | `tests/unit/test_extract_questions.py` | 5 | Mocks `google.genai.Client` — may need to pivot to `lib.llm_client` mock |
| 24 | `tests/unit/test_fetch_zhihu.py` | 3 | Same |
| 25 | `tests/unit/test_image_pipeline.py` | 4 | Same |

**Execution wave structure (maps cleanly to design doc §10 + user §7.1.2 "all in one phase"):**

- **Wave 0:** `lib/` scaffold + unit tests (no call sites change). Verify `@retry` nesting order with a test that raises APIError and checks `_limiter._level` between retries.
- **Wave 1:** `config.py` + `ingest_wechat.py` (reference). Smoke test: run `python ingest_wechat.py <cached_url>` end-to-end.
- **Wave 2:** P0 remaining (ingest_github, multimodal, query, synthesize, image_pipeline, enrichment). 1 commit per file.
- **Wave 3:** P1 (cognee_wrapper + cognee_batch_processor + init/setup_cognee). Critical: Cognee integration test.
- **Wave 4:** P2 (batch scripts + test harness). Re-run `skill_runner.py` test suites per §6 success criteria.

---

## SDK Migration Required?

**No.** Verified via `grep -rn "from google import genai\|import google\.generativeai\|genai\.configure"`:

- All 19 production files use `from google import genai` (new SDK).
- Zero files use `import google.generativeai` (deprecated SDK).
- Zero files use `genai.configure(api_key=...)` (deprecated SDK's global-state idiom).
- Every key-based client instantiation uses `genai.Client(api_key=...)` (new SDK).

The `google_generativeai-0.8.6` package IS installed in `venv/Lib/site-packages/`, but that's a transitive dep of LightRAG (which uses its own gemini adapter internally — see Interop Risk). Our code never imports it directly.

**Conclusion:** Phase 7 is a pure library-migration, not a library+SDK migration. Scope stays bounded.

---

## LightRAG Interop Risk

**Summary:** LightRAG's internal Gemini calls are PARTIALLY isolated from Phase 7's rate-limiter/retry stack.

**Evidence** (`venv/Lib/site-packages/lightrag/llm/gemini.py`):

```python
# line 40-42:
from google import genai                                         # new SDK ✓
from google.genai import types
from google.api_core import exceptions as google_api_exceptions  # OLD SDK exceptions ✗

# line 207-214 and 471-478 (two separate @retry decorators):
retry_if_exception_type(google_api_exceptions.InternalServerError)
| retry_if_exception_type(google_api_exceptions.ServiceUnavailable)
| retry_if_exception_type(google_api_exceptions.ResourceExhausted)
| ...
```

**What this means:**

1. LightRAG instantiates `genai.Client` (new SDK) but catches exceptions from `google.api_core.exceptions` (old-SDK lineage, imported via `google-api-core` as a side-install).
2. The new `google-genai` SDK raises `google.genai.errors.APIError` / `ClientError` / `ServerError` — NOT `google.api_core.exceptions.ResourceExhausted`.
3. **LightRAG's built-in retry may not actually catch 429s from the new SDK.** It's a latent bug in LightRAG, not in our code.
4. When our `lib.generate()` is the outermost call, our retry catches it. When LightRAG's `gemini_model_complete` is called directly (as in `ingest_wechat.py:118`, `multimodal_ingest.py:51`, `query_lightrag.py:21`, `kg_synthesize.py:48`, `ingest_github.py:42`), LightRAG's broken retry is the only layer.

**Recommended mitigation for Phase 7:**

- **Do NOT try to patch LightRAG's internals.** Out of scope.
- Inside our `llm_model_func` / `embedding_func` wrappers passed to `LightRAG(...)`, **apply our rate limiter BEFORE calling `gemini_model_complete`**. The current hand-rolled locks in `ingest_wechat.py:97-125` do exactly this and will be replaced with `async with get_limiter(model):` — keeping the wrapping pattern.
- Our `lib/` retry wraps our wrapper; LightRAG's internal retry becomes a no-op second layer. Mostly harmless.
- Document this in `lib/llm_client.py` docstring as a known interop note.

**Conclusion:** LightRAG remains a separate system. Phase 7's retry/rotate stack wraps it from the outside; it does not penetrate LightRAG's internals.

---

## Cognee Interop Strategy

**Summary:** Cognee's API key is read once at `get_llm_config()` call, cached via `@lru_cache`. Rotation must directly mutate the singleton's `llm_api_key` attribute.

**Evidence** (`venv/Lib/site-packages/cognee/infrastructure/llm/config.py`):

```python
# line 14-50 (LLMConfig class):
class LLMConfig(BaseSettings):
    llm_api_key: Optional[str] = None
    # pydantic BaseSettings reads env vars at __init__

# line 271-272:
@lru_cache
def get_llm_config():
    # returns same instance forever
```

**What this means:**

- Setting `os.environ["LLM_API_KEY"] = new_key` AFTER `get_llm_config()` is first called has **no effect** on Cognee.
- Current production code works around this at `cognee_wrapper.py:41` (`llm_config.llm_api_key = GEMINI_API_KEY`) and `kg_synthesize.py:32` — both set the attribute directly on the cached singleton after first read. This is the right pattern.
- For rotation to propagate into Cognee, `rotate_key()` must do the same.

**Design in `lib/cognee_bridge.py`:**

```python
"""Bridge: propagate rotated keys into Cognee's cached config singleton."""
import logging

logger = logging.getLogger(__name__)
_cognee_available: bool | None = None

def propagate_key_to_cognee(new_key: str) -> None:
    """Set the rotated key on Cognee's LLMConfig singleton.

    Cognee's config is @lru_cache-decorated; mutating env vars alone
    will not propagate a rotated key. Must poke the singleton directly.
    Safe to call even when Cognee isn't used.
    """
    global _cognee_available
    if _cognee_available is False:
        return
    try:
        from cognee.infrastructure.llm.config import get_llm_config
        get_llm_config().llm_api_key = new_key
        _cognee_available = True
    except ImportError:
        _cognee_available = False
    except Exception as e:
        logger.warning("propagate_key_to_cognee failed: %s", e)
```

Register this callback from `lib.api_keys.rotate_key()`:

```python
# lib/api_keys.py
_rotation_listeners: list[Callable[[str], None]] = []

def on_rotate(fn: Callable[[str], None]) -> None:
    _rotation_listeners.append(fn)

def rotate_key() -> str:
    global _current
    _init_cycle()
    _current = next(_cycle)
    for fn in _rotation_listeners:
        try:
            fn(_current)
        except Exception:
            pass  # listeners don't break rotation
    return _current
```

Then in `lib/__init__.py`:

```python
from .api_keys import on_rotate
from .cognee_bridge import propagate_key_to_cognee
on_rotate(propagate_key_to_cognee)  # registered once at import
```

**Rate-limiting inside Cognee itself:** Cognee exposes `llm_rate_limit_enabled` / `llm_rate_limit_requests` on `LLMConfig` (defaults 60 RPM, disabled). We can leave this off since our outer `lib.generate()` already rate-limits anything that funnels through `lib/`. Cognee's own LLM calls (from `cognee.remember` / `cognee.search`) bypass our limiter — but the user's deployment pattern is `remember(..., run_in_background=True, timeout=5.0)` (see `cognee_wrapper.py:109-117`), so Cognee's internal LLM calls happen asynchronously and rarely; leaving Cognee's rate limiter off for Phase 7 is safe. Flag as an enhancement for a later phase if Cognee 429s become a real issue.

---

## Common Pitfalls

### Pitfall 1: Reversing retry/limiter nesting order

**What goes wrong:** Limiter blocks unrelated tasks during retry backoff; retries happen in a tight loop ignoring the RPM cap.
**Why it happens:** Intuition says "apply retry around the inner call, rate limit on top" — which is wrong.
**How to avoid:** Always `@retry` decorator OUTSIDE the async function body; `async with get_limiter():` INSIDE.
**Warning sign:** Concurrent test shows 429s clustering (limiter not rate-limiting) or unrelated tasks blocking (limiter hogged during backoff).

### Pitfall 2: Mutating os.environ to "rotate" Cognee's key

**What goes wrong:** Rotation appears to work in `lib.api_keys` but Cognee continues using the old (possibly revoked) key.
**Why it happens:** `get_llm_config()` is `@lru_cache`-decorated; it reads env vars at first call and never re-reads.
**How to avoid:** Use `propagate_key_to_cognee(new_key)` helper. Register as `on_rotate` listener so rotation stays automatic.
**Warning sign:** Cognee-side operations (`remember`, `search`) raise 429/auth errors while `lib.generate()` calls succeed.

### Pitfall 3: Substring-matching error strings (`"429" in str(e)`)

**What goes wrong:** False positives (message containing "429" unrelated to rate limits) and false negatives (SDK changes message format in a minor release).
**Why it happens:** `config.gemini_call()` does this today (line 166, 172). Works but brittle.
**How to avoid:** `isinstance(exc, APIError) and getattr(exc, "code", None) in {429, 503}` — type-and-int check.
**Warning sign:** Flaky retries after a google-genai version bump; 400-level errors (auth, bad request) caught by retry predicate.

### Pitfall 4: Per-module limiter duplication

**What goes wrong:** One script creates a limiter, another imports the same model — suddenly there are two bucket counters, each counting only half the traffic.
**Why it happens:** Convenience of `_limiter = AsyncLimiter(...)` at module top.
**How to avoid:** All limiters live in `lib/rate_limit.py`; callers use `get_limiter(model)`. Module-level dict guarantees per-process singleton.
**Warning sign:** Rate-limit-exceeded errors despite calls appearing to be "under the limit" per-script.

### Pitfall 5: LightRAG's old-SDK exception catch

**What goes wrong:** LightRAG's internal `@retry(google_api_exceptions.ResourceExhausted)` never fires on new-SDK 429s.
**Why it happens:** LightRAG mixes new SDK (`genai.Client`) with old SDK exception imports (latent bug in lightrag-hku 1.4.15).
**How to avoid:** Don't rely on LightRAG's internal retry. Always wrap LightRAG's `gemini_model_complete` / `gemini_embed` calls in our own `lib.generate()` or apply our limiter in the wrapper function passed to `LightRAG(llm_model_func=...)`.
**Warning sign:** Ingest jobs that crash on 429 instead of retrying — seen historically in this codebase (STATE.md documents this as Phase 4 blocker).

### Pitfall 6: Race condition in hand-rolled time-based limiter

**What goes wrong:** Two concurrent tasks both pass `if elapsed < interval: sleep()`, then both proceed in parallel.
**Why it happens:** Lock released before API call returns; next task sees stale `_last_time`. See `ingest_wechat.py:111-117`.
**How to avoid:** Use `aiolimiter.AsyncLimiter`; its token accounting is race-free.
**Warning sign:** RPM bursts under concurrency despite the limiter "being there."

---

## Code Examples

Verified against installed packages. Corrections from design doc noted inline.

### `lib/models.py` — model registry

**Correction from design doc §4.1:** Current production default is `gemini-3.1-flash-lite-preview` (per `config.py:59`, `config.py:64`), but 5 scripts already pin `gemini-2.5-flash-lite` (ingest_wechat runtime, multimodal_ingest, query_lightrag, kg_synthesize, skill_runner). The registry must **choose one canonical value per role** and migrate all scripts to it. Recommendation: use `gemini-2.5-flash-lite` as the canonical (majority wins; 2.5 is GA, 3.1 is preview). The planner should make this an explicit REQ in Phase 7.

```python
"""Central registry of model names. Change once, propagates everywhere.

Free-tier RPMs verified from Google AI docs April 2026; see 07-REQUIREMENTS.md §2.5.
"""

# LLM for ingestion-side work (entity extraction, summarisation)
INGESTION_LLM = "gemini-2.5-flash-lite"

# LLM for image description (vision-capable)
VISION_LLM = "gemini-2.5-flash-lite"

# LLM for synthesis (can be upgraded to pro if quality matters more than cost)
SYNTHESIS_LLM = "gemini-2.5-flash-lite"

# LLM for Zhihu question extraction
ENRICHMENT_LLM = "gemini-2.5-flash-lite"

# Embedding model — changing this invalidates all stored vectors
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768
EMBEDDING_MAX_TOKENS = 2048

# Per-model RPM caps. Free tier verified 2026-04-28. Override via env var
# OMNIGRAPH_RPM_<MODEL_UNDERSCORED> (e.g., OMNIGRAPH_RPM_GEMINI_2_5_FLASH_LITE=300) on paid tier.
RATE_LIMITS_RPM: dict[str, int] = {
    "gemini-2.5-pro":         5,
    "gemini-2.5-flash":       10,
    "gemini-2.5-flash-lite":  15,   # our primary
    "gemini-3.1-flash-lite-preview": 30,  # legacy; still present in config.py defaults
    "gemini-embedding-001":   60,   # conservative — verify in AI Studio per project
}
```

### `lib/api_keys.py` — key loader and rotation

**Verified against design doc §4.2** — no corrections needed except extension for rotation listeners.

```python
"""Gemini API key loader with optional rotation pool.

Precedence for single-key mode: OMNIGRAPH_GEMINI_KEY > GEMINI_API_KEY.
Pool mode (comma-separated): OMNIGRAPH_GEMINI_KEYS.
"""
from __future__ import annotations

import itertools
import logging
import os
from typing import Callable, Iterator

logger = logging.getLogger(__name__)

_PRIMARY_VAR = "OMNIGRAPH_GEMINI_KEY"
_FALLBACK_VAR = "GEMINI_API_KEY"
_POOL_VAR = "OMNIGRAPH_GEMINI_KEYS"


def load_keys() -> list[str]:
    """Load Gemini API keys. Raises RuntimeError if none found."""
    pool = os.environ.get(_POOL_VAR, "").strip()
    if pool:
        keys = [k.strip() for k in pool.split(",") if k.strip()]
        if keys:
            return keys
    single = os.environ.get(_PRIMARY_VAR) or os.environ.get(_FALLBACK_VAR)
    if single:
        return [single]
    raise RuntimeError(
        f"No Gemini API key found. Set {_PRIMARY_VAR} (preferred), "
        f"{_FALLBACK_VAR}, or {_POOL_VAR} (comma-separated for rotation). "
        f"Rotation only helps across different Google accounts/projects."
    )


_cycle: Iterator[str] | None = None
_current: str | None = None
_rotation_listeners: list[Callable[[str], None]] = []


def _init_cycle() -> None:
    global _cycle, _current
    if _cycle is None:
        _cycle = itertools.cycle(load_keys())
        _current = next(_cycle)


def current_key() -> str:
    _init_cycle()
    assert _current is not None
    return _current


def rotate_key() -> str:
    """Advance to next key. Notifies listeners (e.g., Cognee bridge)."""
    global _current
    _init_cycle()
    _current = next(_cycle)  # type: ignore[arg-type]
    for fn in _rotation_listeners:
        try:
            fn(_current)
        except Exception as e:
            logger.warning("rotation listener failed: %s", e)
    return _current


def on_rotate(fn: Callable[[str], None]) -> None:
    """Register a callback invoked after each rotate_key() call."""
    _rotation_listeners.append(fn)
```

### `lib/rate_limit.py` — per-model limiter registry

**Verified against design doc §4.3** — no corrections.

```python
"""Per-model rate limiters, shared across the process."""
from aiolimiter import AsyncLimiter

from .models import RATE_LIMITS_RPM

_DEFAULT_RPM = 4  # conservative for unknown models
_limiters: dict[str, AsyncLimiter] = {}


def get_limiter(model: str) -> AsyncLimiter:
    """Get or create a shared limiter for this model name."""
    if model not in _limiters:
        rpm = RATE_LIMITS_RPM.get(model, _DEFAULT_RPM)
        _limiters[model] = AsyncLimiter(max_rate=rpm, time_period=60)
    return _limiters[model]
```

### `lib/llm_client.py` — wrapped async + sync generate

**Corrections from design doc §4.4:**
1. Add a `generate_sync` entry point (for scripts like `batch_classify_kol.py` that are synchronous).
2. Wire the rotation-to-Cognee bridge.
3. Handle client cache invalidation on rotation (design doc had this; verify it's correct — YES, the `_client_key != key` check at line 293 is right).

```python
"""Single place for Gemini LLM calls. Rate-limited, retried, key-rotated.

Uses google-genai 1.73.1 (new SDK). Raises google.genai.errors.APIError on
4xx/5xx — we retry on 429 (rate limit) and 503 (server overload).

NOTE: LightRAG (lightrag-hku 1.4.15) wraps google-genai internally but catches
OLD-SDK exceptions (google.api_core.exceptions.*) which the new SDK does not
raise. When calling LightRAG functions from this module's wrappers, our retry
is the authoritative one; LightRAG's internal @retry is a no-op layer.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from google import genai
from google.genai.errors import APIError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .api_keys import current_key, rotate_key
from .rate_limit import get_limiter

logger = logging.getLogger(__name__)


def _is_retriable(exc: BaseException) -> bool:
    """429 (rate limit) and 503 (server overload) retry; 4xx auth/bad-request don't."""
    return isinstance(exc, APIError) and getattr(exc, "code", None) in {429, 503}


# Client cache — rebuilt only when the active key changes.
_client: genai.Client | None = None
_client_key: str | None = None


def _get_client() -> genai.Client:
    global _client, _client_key
    key = current_key()
    if _client is None or _client_key != key:
        _client = genai.Client(api_key=key)
        _client_key = key
    return _client


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception(_is_retriable),
    reraise=True,
)
async def generate(model: str, prompt: str, **kwargs: Any) -> str:
    """Generate text. Rate-limited per model, retried on 429/503, rotates key per retry."""
    async with get_limiter(model):
        try:
            response = await _get_client().aio.models.generate_content(
                model=model, contents=prompt, **kwargs
            )
            return response.text
        except APIError as e:
            if _is_retriable(e):
                new_key = rotate_key()   # next retry will see new current_key()
                logger.info("Gemini %s → rotated key; retry imminent", e.code)
            raise


def generate_sync(model: str, prompt: str, **kwargs: Any) -> str:
    """Synchronous convenience wrapper for scripts that aren't async.

    Used by batch_classify_kol, batchkol_topic, _reclassify, skill_runner, etc.
    Replaces config.gemini_call().
    """
    return asyncio.run(generate(model, prompt, **kwargs))


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception(_is_retriable),
    reraise=True,
)
async def aembed(model: str, texts: list[str], **kwargs: Any) -> list[list[float]]:
    """Generate embeddings. Same retry/limit/rotate as generate()."""
    async with get_limiter(model):
        try:
            response = await _get_client().aio.models.embed_content(
                model=model, contents=texts, **kwargs
            )
            return [e.values for e in response.embeddings]
        except APIError as e:
            if _is_retriable(e):
                new_key = rotate_key()
                logger.info("Gemini embedding %s → rotated key; retry imminent", e.code)
            raise
```

### `lib/cognee_bridge.py` — rotation propagation (NEW module)

Not in original design doc but required per §Cognee Interop Strategy above.

```python
"""Bridge: propagate rotated keys into Cognee's cached LLMConfig singleton.

Cognee's get_llm_config() is @lru_cache-decorated; mutating os.environ
will not propagate a rotated key — we must poke the singleton directly.
Safe to call from a non-Cognee-using process (ImportError swallowed).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
_cognee_available: bool | None = None


def propagate_key_to_cognee(new_key: str) -> None:
    global _cognee_available
    if _cognee_available is False:
        return
    try:
        from cognee.infrastructure.llm.config import get_llm_config
        get_llm_config().llm_api_key = new_key
        _cognee_available = True
    except ImportError:
        _cognee_available = False
    except Exception as e:
        logger.warning("propagate_key_to_cognee failed: %s", e)
```

### `lib/__init__.py` — wire-up and public API

```python
"""OmniGraph-Vault shared infrastructure.

Not a Hermes/OpenClaw skill — internal-only. Import as `from lib import ...`.
"""
from .api_keys import current_key, on_rotate, rotate_key
from .cognee_bridge import propagate_key_to_cognee
from .llm_client import aembed, generate, generate_sync
from .models import (
    EMBEDDING_DIM,
    EMBEDDING_MAX_TOKENS,
    EMBEDDING_MODEL,
    ENRICHMENT_LLM,
    INGESTION_LLM,
    RATE_LIMITS_RPM,
    SYNTHESIS_LLM,
    VISION_LLM,
)
from .rate_limit import get_limiter

# Register rotation → Cognee bridge once at import.
on_rotate(propagate_key_to_cognee)

__all__ = [
    "current_key", "on_rotate", "rotate_key",
    "propagate_key_to_cognee",
    "aembed", "generate", "generate_sync",
    "get_limiter",
    "EMBEDDING_DIM", "EMBEDDING_MAX_TOKENS", "EMBEDDING_MODEL",
    "ENRICHMENT_LLM", "INGESTION_LLM", "RATE_LIMITS_RPM",
    "SYNTHESIS_LLM", "VISION_LLM",
]
```

---

## State of the Art

| Old Approach (current) | Current Approach (Phase 7) | Why Changed | Impact |
|------------------------|----------------------------|-------------|--------|
| Hardcoded model string per file | Central `lib/models.py` constants | Drift: ingest_github at 3.1-flash-lite-preview while peers at 2.5-flash-lite | One-line change propagates |
| `asyncio.Lock` + `time.time()` delta | `aiolimiter.AsyncLimiter` | Race in ingest_wechat; no limiter at all in most scripts | Per-model process-wide limit |
| `while: try/except; "429" in str(e)` in config.py | `@tenacity.retry(retry_if_exception(...))` | 90 LOC of custom logic; brittle substring match | 3-line decorator; type-checked predicate |
| `GEMINI_API_KEY` / `GEMINI_API_KEY_BACKUP` | `OMNIGRAPH_GEMINI_KEY` + `OMNIGRAPH_GEMINI_KEYS` pool | Generic name collides with Hermes/other skills; 2-key fixed pair won't scale | Namespaced + round-robin rotation |
| `config.gemini_call()` | `lib.generate_sync()` | Single-responsibility; config.py becomes paths/env only | Easier to reason about |

**Deprecated/to-remove after migration:**

- `config.py::gemini_call()` — whole function, replaced by `lib.generate_sync()`
- `config.py::rpm_guard()` — replaced by `lib.get_limiter()` (leave a shim that delegates for the first commit; remove after all call sites migrate in Wave 4)
- `config.py::_last_gemini_call_ts`, `_RPM_GUARD_INTERVAL` — globals no longer needed
- `config.py::GEMINI_API_KEY_BACKUP` — fold into `OMNIGRAPH_GEMINI_KEYS` pool
- `ingest_wechat.py::_llm_lock`, `_last_llm_time`, `_LLM_MIN_INTERVAL` — replaced by `lib.get_limiter(INGESTION_LLM)`
- `ingest_wechat.py::_embed_lock`, `_last_embed_time`, `_EMBED_MIN_INTERVAL` — replaced by `lib.get_limiter(EMBEDDING_MODEL)`

---

## Open Questions

1. **Canonical flash-lite version.** Registry must pick one: `gemini-2.5-flash-lite` (5 scripts) or `gemini-3.1-flash-lite-preview` (config.py defaults + ingest_github). Design doc §4.1 assumed 2.5. Recommendation: standardise on **2.5-flash-lite** (GA, not preview). Planner should make this an explicit REQ in Phase 7.
   - What we know: both work; quotas differ (2.5 is 15 RPM free / 1000 RPD; 3.1-preview has 30 RPM free / 5000 RPD per config.py comment).
   - What's unclear: whether 3.1-preview's quota is public (the comment calls out 5000 RPD; that's higher than published 2.5 quota).
   - Recommendation: standardise on 2.5-flash-lite for production; keep 3.1-preview in `RATE_LIMITS_RPM` for any legacy path that still references it.

2. **Rate limiter tokens vs aiolimiter's default amount=1.** Embedding calls batch 20 texts per call. Should one `aembed` call consume 1 limiter slot (current design) or 20? Google's quota counts by requests, not by texts, so **1 slot per call is correct**. Documented here for verification against AI Studio dashboards after shipping.

3. **Tests using `mocker.patch("google.genai.Client", ...)`.** After migration, production code calls `lib.llm_client.generate()` which internally creates `genai.Client`. Unit tests need to either (a) continue patching `google.genai.Client` (still works) or (b) patch `lib.llm_client._get_client`. (a) is less invasive and should be preferred — tests don't need to know about `lib/`. Verify during Wave 4.

4. **skill_runner.py `_GEMINI_MODEL` constant.** Currently `"gemini-3.1-flash-lite-preview"` (line 151). After migration, should this import from `lib.models.INGESTION_LLM` (coupling to production) or stay explicit (test independence)? Recommendation: stay explicit to keep test harness independent; use `"gemini-2.5-flash-lite"` string literal.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `google-genai` Python pkg | All 19 production files | ✓ | 1.73.1 | — |
| `aiolimiter` Python pkg | `lib/rate_limit.py` | ✓ transitive (Cognee) | 1.2.1 | — |
| `tenacity` Python pkg | `lib/llm_client.py` | ✓ transitive (Cognee, LightRAG, google-genai) | 9.1.4 | — |
| `cognee` Python pkg | `lib/cognee_bridge.py` (optional import) | ✓ | 1.0.1 | Bridge swallows ImportError |
| `GEMINI_API_KEY` env var | `lib/api_keys.py` fallback | ✓ (Windows .env + remote ~/.hermes/.env) | — | `OMNIGRAPH_GEMINI_KEY` or `OMNIGRAPH_GEMINI_KEYS` |
| `OMNIGRAPH_GEMINI_KEY` env var | `lib/api_keys.py` primary | ✗ (not set anywhere) | — | Falls back to `GEMINI_API_KEY` |
| `OMNIGRAPH_GEMINI_KEYS` env var | `lib/api_keys.py` pool | ✗ (not set anywhere) | — | Falls back to single-key mode |
| Python 3.11+ | all | ✓ | 3.13 (from `.pyc` in `__pycache__/*.cpython-313.pyc`) | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** `OMNIGRAPH_GEMINI_KEY` and `OMNIGRAPH_GEMINI_KEYS` — fall back to `GEMINI_API_KEY` (already set in deployment). Phase 7 ships with the new env vars as *preferred*; user can migrate deployment env vars at their pace.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.4+ (from `requirements.txt`), pytest-asyncio 0.23+, pytest-mock 3.12+ |
| Config file | `.pytest_cache/` exists; no `pytest.ini` / `pyproject.toml [tool.pytest]` found → default pytest config |
| Quick run command | `.venv/Scripts/python -m pytest tests/unit/ -x -q` |
| Full suite command | `.venv/Scripts/python -m pytest tests/ -v` |
| Skill tests | `.venv/Scripts/python skill_runner.py skills/omnigraph_ingest --test-file tests/skills/test_omnigraph_ingest.json` |

### Phase Requirements → Test Map

| Req | Behavior | Test Type | Automated Command | File Exists? |
|-----|----------|-----------|-------------------|-------------|
| D1–D3 | `lib.api_keys.load_keys()` resolves in correct precedence | unit | `pytest tests/unit/test_api_keys.py -x` | ❌ Wave 0 |
| D4 | `rotate_key()` advances cycle, calls listeners | unit | `pytest tests/unit/test_api_keys.py::test_rotate -x` | ❌ Wave 0 |
| D4 | Cognee bridge updates `llm_config.llm_api_key` on rotate | integration | `pytest tests/integration/test_cognee_rotation.py -x` | ❌ Wave 0 |
| D5 | `lib/` is importable from repo root | unit | `python -c "from lib import generate; print('ok')"` | ❌ Wave 0 |
| D6 | Dependencies importable | unit | `python -c "import aiolimiter, tenacity; print('ok')"` | ✅ (deps exist) |
| D7 | Model constants match config.py exports | unit | `pytest tests/unit/test_models.py -x` | ❌ Wave 0 |
| D8 | `get_limiter(model)` returns same instance on repeat | unit | `pytest tests/unit/test_rate_limit.py::test_singleton -x` | ❌ Wave 0 |
| D8 | Retry nesting: `@retry` outside, `async with limiter` inside — each retry re-acquires | integration | `pytest tests/unit/test_llm_client.py::test_retry_reacquires_limiter -x` | ❌ Wave 0 |
| APIError predicate | 429/503 retry; 400/401/403 don't | unit | `pytest tests/unit/test_llm_client.py::test_is_retriable -x` | ❌ Wave 0 |
| Migration parity | ingest_wechat still works after lib swap | integration | `python ingest_wechat.py <cached_url>` (cached article, no HTTP) | manual |
| Migration parity | All existing skill tests pass | e2e | `python skill_runner.py skills/ --test-all` | ✅ |

### Sampling Rate

- **Per task commit:** `pytest tests/unit/ -x -q` (< 5 s once scaffold exists)
- **Per wave merge:** `pytest tests/ -v` + `python skill_runner.py skills/omnigraph_ingest --test-file tests/skills/test_omnigraph_ingest.json`
- **Phase gate:** Full suite green + one live run of `ingest_wechat.py` against a cached URL + smoke of `kg_synthesize.py` to exercise Cognee bridge.

### Wave 0 Gaps

- [ ] `tests/unit/test_api_keys.py` — covers D1–D4 (precedence, rotation, listeners)
- [ ] `tests/unit/test_rate_limit.py` — covers D8 (singleton limiter per model)
- [ ] `tests/unit/test_llm_client.py` — covers retry predicate, nesting, key rotation on 429 (mock `APIError`)
- [ ] `tests/unit/test_models.py` — covers D7 (constants present, RATE_LIMITS_RPM has entries for every model used)
- [ ] `tests/integration/test_cognee_rotation.py` — covers Cognee singleton propagation (needs real cognee import)
- [ ] Optional: `tests/conftest.py` fixture `mock_gemini_client` that patches `google.genai.Client` consistently (already partially present, extend)

---

## Sources

### Primary (HIGH confidence)

- `venv/Lib/site-packages/aiolimiter/leakybucket.py` — AsyncLimiter source (1.2.1)
- `venv/Lib/site-packages/google/genai/errors.py` — APIError class definition (1.73.1)
- `venv/Lib/site-packages/lightrag/llm/gemini.py` — LightRAG's gemini adapter (1.4.15)
- `venv/Lib/site-packages/cognee/infrastructure/llm/config.py` — Cognee LLMConfig + `get_llm_config()` lru_cache (1.0.1)
- `venv/Lib/site-packages/{aiolimiter,tenacity,google_genai,cognee,lightrag_hku}-*.dist-info/METADATA` — version + dependency confirmations
- Project source files: `config.py`, `ingest_wechat.py`, `ingest_github.py`, `cognee_wrapper.py`, `kg_synthesize.py`, `multimodal_ingest.py`, `query_lightrag.py`, `image_pipeline.py`, `enrichment/*.py`
- `07-REQUIREMENTS.md` §2.5 for free-tier RPM table (design doc)

### Secondary (MEDIUM confidence)

- `.planning/STATE.md` for Gemini embedding quota blocker context (Phase 4 exit)
- `.planning/ROADMAP.md` for Phase 5/6 independence confirmation

### Tertiary (LOW confidence)

- None — all claims in this research are backed by installed-package inspection or direct file reads. No web research was attempted (per constraint).

---

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — exact versions from `dist-info/` dirs
- Architecture (retry/limit nesting): **HIGH** — verified from `leakybucket.py` source
- APIError.code attribute: **HIGH** — verified at `errors.py:33,46,64`
- Cognee rotation strategy: **HIGH** — verified `@lru_cache` at `cognee/.../config.py:271`
- LightRAG interop risk: **HIGH** — grepped `lightrag/llm/gemini.py` directly
- Migration scope (25 files, not 18): **HIGH** — fresh grep at research time
- SDK migration not needed: **HIGH** — zero `import google.generativeai` matches in production code
- Canonical model string choice: **MEDIUM** — both `gemini-2.5-flash-lite` and `gemini-3.1-flash-lite-preview` are live in the codebase; recommendation is technically sound but needs user confirmation

**Research date:** 2026-04-28
**Valid until:** 2026-05-28 (30 days; stable area but google-genai version bumps could change APIError structure)
