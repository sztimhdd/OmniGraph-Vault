# Phase 7 Architectural Review — Hermes Pressure Test

**Reviewer:** Hermes (gemini-3.1-flash-lite-preview)
**Date:** 2026-04-28
**Branch:** `main` (post-pull, up to date)
**Phase:** 07-model-key-management (pre-implementation — `lib/` does not exist yet)

> This review pressure-tests the Phase 7 plan against actual code state at `/home/sztimhdd/OmniGraph-Vault`. All claims are grounded in the files read: `lightrag_embedding.py` (133 lines, root), `ingest_wechat.py` (799 lines), `kg_synthesize.py` (133 lines), `config.py` (201 lines), and all 10 planning documents in `.planning/phases/07-model-key-management/`.

---

## D-09: Absorb `lightrag_embedding.py` into `lib/`

**Verdict: ✅ Scope creep is justified. Ship it.**

### Current state
`lightrag_embedding.py` (133 lines, at repo root) is imported by at least 5 files:
- `ingest_wechat.py:33`
- `kg_synthesize.py:42`
- `multimodal_ingest.py` (per migration map)
- `query_lightrag.py` (per migration map)
- `ingest_github.py` (per migration map)

It uses `os.environ.get("GEMINI_API_KEY")` directly and has its own `_DEFAULT_MODEL = "gemini-embedding-2"` constant (line 46).

### Analysis
The alternative — leave at root with `from lib.api_keys import current_key` — creates structural asymmetry: one module at root importing from `lib/`, while everything inside `lib/` imports from siblings. That's worse than moving it in.

Moving it to `lib/lightrag_embedding.py` and having the root `lightrag_embedding.py` become a re-export shim (`from lib.lightrag_embedding import embedding_func`) is the cleanest path. The cost is low: 5 import lines change.

### Missing guardrail
The plan's Wave 0 Task 0.7 has no **output-parity test**. If the refactored internal key access produces a different embedding vector (e.g., wrong key, different model), the bug silently passes Wave 0 tests and only surfaces in Wave 1's smoke test — by which point 5+ other tasks have landed on top.

**Action required:** Add to Wave 0 Task 0.7 acceptance criteria:
- `python -c "from lightrag_embedding import embedding_func as old; from lib import embedding_func as new; assert old is new; print('parity ok')"` — verifies the root shim re-exports the same object

---

## D-02: Hybrid Model Config (constant default + env override)

**Verdict: ⚠️ Overengineered. Ship without model env overrides.**

### Current plan
```python
INGESTION_LLM = os.environ.get("OMNIGRAPH_MODEL_INGESTION_LLM", "gemini-2.5-flash-lite")
VISION_LLM    = os.environ.get("OMNIGRAPH_MODEL_VISION_LLM",    "gemini-2.5-flash-lite")
SYNTHESIS_LLM = os.environ.get("OMNIGRAPH_MODEL_SYNTHESIS_LLM", "gemini-2.5-flash-lite")
EMBEDDING_MODEL = os.environ.get("OMNIGRAPH_MODEL_EMBEDDING",   "gemini-embedding-2")
GITHUB_INGEST_LLM = os.environ.get("OMNIGRAPH_MODEL_GITHUB_INGEST", "gemini-3.1-flash-lite-preview")
```

### Analysis
The justification is "rollback without deploy" — but for a single-user hobbyist tool where code lives on one machine, `git revert` + push IS the rollback. It's faster than SSH-ing in to set an env var, and it leaves a clean audit trail.

The only env override that earns its keep is **D-08 (`OMNIGRAPH_RPM_*`)** — upgrading from free tier (15 RPM) to paid tier (300 RPM) = env change, not code change. That's genuinely useful and forward-compatible.

Every model env override is provisioning overhead that will never be touched:
- When will Hai need to swap `INGESTION_LLM` at runtime without a deploy? Never.
- When will he run `INGESTION_LLM=gemini-2.5-pro` for one script but `gemini-2.5-flash-lite` for another? Never — he's a single-user with one workflow.

**Action required:** Make model constants pure strings:
```python
INGESTION_LLM = "gemini-2.5-flash-lite"
VISION_LLM = "gemini-2.5-flash-lite"
SYNTHESIS_LLM = "gemini-2.5-flash-lite"
EMBEDDING_MODEL = "gemini-embedding-2"
GITHUB_INGEST_LLM = "gemini-3.1-flash-lite-preview"
```
Keep `os.environ.get()` ONLY for `RATE_LIMITS_RPM` overrides (D-08).

---

## Wave Ordering: Task 0.7 Before Wave 1

**Verdict: Ordering is fine, but Wave 0 is too monolithic.**

### Analysis
The sequence (Wave 0 → Wave 1 → Wave 2...) is logically sound. Wave 0 lands the library, Wave 1 does the reference migration against it.

**The real problem is Wave 0's blast radius.** 7+ tasks in one wave = one big commit (per the plan's D-03 "per-wave commits"). If Task 0.7 introduces a subtle embedding regression, it's buried under 6 other tasks. You cannot `git bisect` within a wave.

This contradicts the plan's own philosophy. D-03 says "per-file commits with green tests between" for Waves 1-4, but Wave 0 is treated as a monolith.

**Action required:** Split Wave 0 into per-task commits:

| Commit | Content | Tests |
|--------|---------|-------|
| 1 | `lib/models.py` | `test_models.py` |
| 2 | `lib/api_keys.py` | `test_api_keys.py` |
| 3 | `lib/rate_limit.py` | `test_rate_limit.py` |
| 4 | `lib/llm_client.py` | `test_llm_client.py` |
| 5 | `lib/cognee_bridge.py` | `test_cognee_rotation.py` |
| 6 | Move `lightrag_embedding.py` → `lib/lightrag_embedding.py` + refactor internals | `test_lightrag_embedding.py` + parity assertion |
| 7 | Root `lightrag_embedding.py` shim + `tests/conftest.py` fixtures | Full suite green |

Each commit is independently revertable. Tests green between every commit. This is already consistent with the plan's "per-file commits" philosophy — extend it to Wave 0.

---

## Cognee Bridge: `@lru_cache` Singleton Mutation

**Verdict: 🚩 Would not ship as designed. Overengineered.**

### Current design
The plan's `lib/cognee_bridge.py` is ~35 lines:
```
rotate_key() → on_rotate listener → propagate_key_to_cognee() → mutate cached singleton's llm_api_key
```

### Three problems

1. **Fragile to Cognee updates.** Cognee's `get_llm_config()` returns an `@lru_cache`'d object (verified: `cognee.infrastructure.llm.config:271`). If Cognee changes this to return a frozen/dataclass instance, the field mutation silently fails — `llm_api_key` is set on the object but Cognee reads from a different internal path.

2. **Thread-unsafe by design.** `@lru_cache` + direct field mutation is not atomic. If `rotate_key()` fires while Cognee is mid-call reading `llm_api_key`, you get a torn read. For a single-user synchronous tool this is unlikely, but the architecture encodes a race condition.

3. **It's a hack dressed as architecture.** A formal `cognee_bridge.py` module with listener registration and observer pattern suggests a well-designed integration layer. What it actually does is:
   - Set `os.environ["COGNEE_LLM_API_KEY"] = new_key` (1 line)
   - Set `cached_config.llm_api_key = new_key` (1 line, for already-cached singletons)
   
   That's 2 lines of business logic wrapped in 35 lines of observer-pattern scaffolding.

### Less invasive alternative

Replace the entire `cognee_bridge.py` module with:

```python
# In lib/api_keys.py rotate_key():
def rotate_key() -> str:
    global _current
    _current = next(_cycle)
    os.environ["COGNEE_LLM_API_KEY"] = _current  # All future Cognee reads pick this up
    return _current


def _refresh_cognee():
    """Call after key rotation in long-running processes that use Cognee.
    
    Only needed if Cognee's @lru_cache'd config was loaded before the rotation
    and the process is running long enough to exhaust quota mid-run.
    """
    from cognee.infrastructure.llm.config import get_llm_config
    get_llm_config.cache_clear()
```

That's the entire bridge. No listener registration. No `propagate_key_to_cognee()`. No `on_rotate` callback infrastructure.

Long-running processes (`kg_synthesize.py`, `cognee_batch_processor.py`) call `_refresh_cognee()` at the top of their processing loops. Short-lived scripts never need it — they import Cognee after `lib/` initialization, picking up the correct key from `os.environ`.

**Action required:** Delete `lib/cognee_bridge.py` from the module layout. Replace with 3 lines in `api_keys.py` + 5-line helper. Drop the `on_rotate` listener infrastructure entirely — it's scaffolding for a problem that doesn't exist at this scale.

---

## What's Missing / Would Not Ship

### 1. `config.py` D-11 Shims — Permanent Technical Debt 🚩

The plan: "D-11 config.py shims may remain indefinitely (acceptable per D-11)."

**No.** After Waves 1-4 migrate every caller to `from lib import`, you have `config.py` importing from `lib/` to re-export constants under old names. That's two sources of truth for model names, and `config.py` depends on `lib/` — a structural direction that should flow the other way (application code → lib, not lib → config).

**Action required:** Add a Wave 4 sweeper task: after all callers are migrated (verified via grep acceptance criteria in Waves 1-4), delete:
- `config.INGEST_LLM_MODEL`
- `config.IMAGE_DESCRIPTION_MODEL`
- `config.ENRICHMENT_LLM_MODEL`
- `config.gemini_call()`

The plan already proves they're unused by that point. Delete them.

### 2. `generate_sync()` Doesn't Support Multimodal — Broken Promise 🚩

Wave 2 Task 2.5 (image_pipeline) has a hedge: "if `generate_sync` doesn't support PIL.Image, fall back to direct `genai.Client`."

This means the "single LLM entry point" promise from `lib/llm_client.py` is broken on day one. Image pipeline goes through `genai.Client(api_key=current_key())` directly, while text ingestion goes through `generate_sync()`. Two code paths, two different behaviors under rotation/retry.

**Action required:** Either:
- Make `generate_sync(model, prompt, contents=[...], **kwargs)` accept multimodal contents natively (the `google-genai` SDK supports it — `client.models.generate_content(model=..., contents=[text, image_part])`)
- OR document explicitly in `lib/llm_client.py` that vision calls use `current_key()` + direct `genai.Client`, and `lib/` does NOT claim to cover vision use cases

Pick one. Don't ship a half-truth.

### 3. `OMNIGRAPH_MODEL_*` Env Var Explosion — Delete 🚩

4 model constants × `OMNIGRAPH_MODEL_*` env overrides + `OMNIGRAPH_RPM_*` per model = ~12 env vars a single user will never set.

Every env var is a support vector when something breaks: "Did you set `OMNIGRAPH_MODEL_SYNTHESIS_LLM`? No? Maybe you should try that."

**Action required:** Ship with ZERO model env overrides. Pure constants in `lib/models.py`. Add env overrides only when a real use case emerges based on actual user experience, not speculative future-proofing.

### 4. Asymmetric LLM/Embedding Wrapping — Undocumented

The plan wraps LLM calls via LightRAG's `gemini_model_complete` + `lib.get_limiter` from outside, but redirects `embedding_func` entirely into our own code in `lib/`. Two different wrapping strategies for the same subsystem.

This isn't wrong — it's pragmatic. LightRAG's embedding contract is complex (in-band multimodal, task prefixes, `_priority` kwarg), while its LLM contract is a thin proxy. But nothing in the plan documents WHY they're different.

**Action required:** Add rationale to `lib/__init__.py` or the module docstrings:

> LLM calls are wrapped from outside because LightRAG's `gemini_model_complete` is a thin proxy — we layer rate limiting and key rotation around it. Embeddings are owned by us because LightRAG's embedding contract requires in-band multimodal logic (image fetching, task prefix injection, `types.Part.from_bytes`) that can't be layered externally.

---

## Summary Table

| Decision | Verdict | Action |
|----------|---------|--------|
| D-09 (absorb into lib/) | ✅ Justified | Ship; add output-parity assertion to acceptance criteria |
| D-02 (hybrid env override) | ⚠️ Overengineered | Drop all model env overrides; keep only RPM override (D-08) |
| Wave 0 ordering | ⚠️ Too monolithic | Split into 7 per-task commits, each with green tests |
| Cognee bridge (@lru_cache mutation) | 🚩 Would not ship | Replace with 1-line `os.environ` set + 5-line `_refresh_cognee()` |
| D-11 config.py shims | 🚩 Permanent debt | Add Wave 4 sweeper task to delete them after migration complete |
| `generate_sync()` multimodal gap | 🚩 Broken promise | Either support `contents=[]` natively or document the exception |
| `OMNIGRAPH_MODEL_*` env vars | 🚩 Unused overhead | Delete; ship pure constants |
| Asymmetric wrapping pattern | ⚠️ Undocumented | Add one-paragraph rationale in module docstrings |

### Would Not Ship — The Short List

1. **`lib/cognee_bridge.py`** — 35-line module does 2 lines of real work; replace with inline helper
2. **Model env overrides** — zero use case at single-user scale; pure constants suffice
3. **Permanent D-11 shims** — if migration is complete, delete the dead code

---

*End of Phase 7 architectural review. For Claude Code ingest: this file is at `.planning/phases/07-model-key-management/07-REVIEW-HERMES.md`.*
