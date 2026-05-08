# LLM Routing Audit — 2026-05-08

Read-only audit of every LLM call site in the codebase. Goal: ground-truth which paths honor `OMNIGRAPH_LLM_PROVIDER` (the dispatcher env var) vs. hardcode a provider, and what that means for local-dev reachability under the corp network (Vertex ✅ / DeepSeek ❌ / SiliconFlow ❌ / OpenRouter ❌).

## TL;DR

- **Dispatcher coverage is partial and fragmented.** `lib/llm_complete.get_llm_func()` exists but only **one production path** uses it (`ingest_wechat.py:241`, inherited by `batch_ingest_from_spider.py` via `get_rag()`). All other LightRAG call sites hardcode `deepseek_model_complete`.
- **3 inline duplicates of the dispatcher logic** — `batch_classify_kol.py:281`, `batch_ingest_from_spider.py:1290`, `lib/llm_complete.py:34`. Same pattern, three implementations, only one of them callable as a function.
- **Layer 1 / Layer 2 are explicitly contract-pinned** — Layer 1 hardcoded to Vertex Gemini, Layer 2 hardcoded to DeepSeek. Per design (`lib/article_filter.py:392-396` LF-1.3 deviation note), `OMNIGRAPH_LLM_PROVIDER` deliberately does NOT control Layer 1/2.
- **Locally-runnable stages (post audit, full happy path with corp network):** ingest_wechat (with provider=vertex_gemini), batch_ingest_from_spider (inherits ingest_wechat path), batch_classify_kol (with provider=vertex_gemini), graded probe in batch_ingest_from_spider (with provider=vertex_gemini), Vision cascade fallback to Gemini Vision (Vertex auto-detected from SA env), Layer 1 (Vertex hardcoded — works locally).
- **Corp-blocked stages (DeepSeek hardcoded, no env override):** Layer 2 (`lib/article_filter.py:520`), `enrichment/rss_classify.py`, `enrichment/rss_ingest.py:367` LightRAG, `kg_synthesize.py:107` LightRAG, `multimodal_ingest.py:60` LightRAG, `query_lightrag.py:26` LightRAG, `omnigraph_search/query.py:54` LightRAG, `ingest_github.py:53` LightRAG, the post-ingest entity extraction call at `ingest_wechat.py:835` (in-process, separate from the LightRAG instance), and `batch_ingest_from_spider.py:1020` (`from batch_classify_kol import _call_deepseek_fullbody`).
- **Hardcoded `deepseek_model_complete` LightRAG call sites:** **6** (ingest_github, kg_synthesize, multimodal_ingest, query_lightrag, omnigraph_search/query, enrichment/rss_ingest) + 1 dispatcher-respecting (ingest_wechat). Plus 1 in `scripts/wave0c_smoke.py` (out-of-prod test scaffold).
- **Phase 5 cross-coupling is real and unfixed** — `lib/__init__.py:35` eagerly imports `lib.llm_deepseek`, which calls `_require_api_key()` at module level (`lib/llm_deepseek.py:87`). This means **importing anything from `lib/` fails at import time without `DEEPSEEK_API_KEY` set**, regardless of whether DeepSeek is the active provider.

## Q1: Where is `OMNIGRAPH_LLM_PROVIDER` read?

Five Python read sites (excluding tests, planning docs, and one spike fixture):

| # | File:line | What it does with the value |
|---|---|---|
| 1 | `lib/llm_complete.py:34` | Central dispatcher `get_llm_func()`. Returns `deepseek_model_complete` (default) or `vertex_gemini_model_complete`. Raises `ValueError` on unknown values. **The "official" dispatcher.** |
| 2 | `batch_classify_kol.py:281` | Inline dispatch in `_call_fullbody_llm`. Same shape as #1 but uses `requests.post` for DeepSeek (not the OpenAI SDK in `lib.llm_deepseek`) and `_asyncio.run(vertex_gemini_model_complete(prompt))` for Vertex. Does NOT call `get_llm_func()`. **Duplicate.** |
| 3 | `batch_ingest_from_spider.py:1290` | Inline dispatch in graded-probe path. Routes to `_graded_probe_vertex` or `_graded_probe_deepseek` (both private to this module, both built around the same prompt template). Does NOT call `get_llm_func()`. **Duplicate.** |
| 4 | `ingest_wechat.py:85` (comment) | Doc-only reference — line 89 imports `get_llm_func` from `lib.llm_complete`. The actual env read happens inside the dispatcher function (#1). |
| 5 | `lib/article_filter.py:43, 394` (comment) | Documentation-only. Layer 1/2 explicitly **opt out** of dispatcher routing per LF-1.3 / LF-2.3 contract pin (Layer 1 = Vertex always, Layer 2 = DeepSeek always). |

Test-only references (not counted): `tests/unit/test_llm_complete.py:20-44`, `tests/unit/test_graded_classify_prompt_quality.py:78`, `tests/unit/test_local_e2e_sh.py:141`.

Spike fixture: `.planning/quick/260506-pa7-phase-21-stk-01-nanovectordb-cleanup-spi/spike_cleanup_probe.py:31` sets `OMNIGRAPH_LLM_PROVIDER=deepseek` via `setdefault` for a fixture; not a production read.

## Q2: Is `lib/llm_complete.py` a real dispatcher? Who calls it?

**Yes, it is a working dispatcher** but **only one production caller** wires it into LightRAG.

Dispatcher implementation (`lib/llm_complete.py:30-45`):

```python
def get_llm_func() -> Callable:
    provider = os.environ.get("OMNIGRAPH_LLM_PROVIDER", "deepseek").strip() or "deepseek"
    if provider == "deepseek":
        from lib.llm_deepseek import deepseek_model_complete
        return deepseek_model_complete
    if provider == "vertex_gemini":
        from lib.vertex_gemini_complete import vertex_gemini_model_complete
        return vertex_gemini_model_complete
    raise ValueError(...)
```

Provider set: `("deepseek", "vertex_gemini")` — closed enum (`lib/llm_complete.py:27`).

**Callers in production code:**

- `ingest_wechat.py:89` (import) → `ingest_wechat.py:241` (`llm_model_func=get_llm_func()` inside `get_rag()`)

That's it for production. `batch_ingest_from_spider.py` inherits this routing because its ingest path calls `from ingest_wechat import get_rag` (`batch_ingest_from_spider.py:772, 1478`) and uses the returned LightRAG instance directly.

**Test callers:** `tests/unit/test_llm_complete.py:21, 29, 37, 45, 58`.

**Hardcoded LightRAG `llm_model_func=deepseek_model_complete` (bypasses dispatcher):** 6 production files + 1 test scaffold:

| File:line | LightRAG-using script |
|---|---|
| `ingest_github.py:53` | GitHub ingest |
| `kg_synthesize.py:107` | KG synthesis (read-side) |
| `multimodal_ingest.py:60` | PDF/multimodal ingest |
| `query_lightrag.py:26` | Direct LightRAG query (debug) |
| `omnigraph_search/query.py:54` | Search skill backend |
| `enrichment/rss_ingest.py:367` | **RSS ingest** ← critical for current local-dev gap |
| `scripts/wave0c_smoke.py:68` | Wave 0c smoke (test scaffold) |

## Q3: How do `lib/article_filter.py` Layer 1 and Layer 2 route LLM?

Both are **hardcoded, by design** — explicit LF-contract pin documented in the source.

### Layer 1 (`layer1_pre_filter`, lib/article_filter.py:336)

- LLM client init: **lazy import inside the call site** at `lib/article_filter.py:399-400`:
  ```python
  from lib.vertex_gemini_complete import vertex_gemini_model_complete
  raw = await vertex_gemini_model_complete(prompt)
  ```
- Calls dispatcher? **No.**
- Honors `OMNIGRAPH_LLM_PROVIDER`? **No** — explicitly opted out per the inline comment at `lib/article_filter.py:392-396`:
  > "LF-1.3 deviation: production has only Vertex Gemini; the 'legacy gemini_model_complete' branch in plan drafts has no real symbol in lib/. We always route through Vertex. OMNIGRAPH_LLM_PROVIDER still controls the project-wide LightRAG LLM dispatcher (lib.llm_complete.get_llm_func) which is unaffected by this module."
- **Conclusion:** Layer 1 is Vertex-only. Locally reachable (Vertex SA works through corp proxy per script docstring caveats).

### Layer 2 (`layer2_full_body_score`, lib/article_filter.py:458)

- LLM client init: **lazy import inside the call site** at `lib/article_filter.py:520-524`:
  ```python
  from lib.llm_deepseek import deepseek_model_complete
  raw = await asyncio.wait_for(
      deepseek_model_complete(prompt),
      timeout=LAYER2_TIMEOUT_SEC,
  )
  ```
- Calls dispatcher? **No.**
- Honors `OMNIGRAPH_LLM_PROVIDER`? **No** — pinned to DeepSeek per LF-2.3. Source docstring at `lib/article_filter.py:461-468`:
  > "Real DeepSeek batch full-body filter (LF-2.1 / LF-2.2 / LF-2.3). Routed through `lib.llm_deepseek.deepseek_model_complete` which honors the project-wide `DEEPSEEK_MODEL` env (default `deepseek-v4-flash`)."
- **Conclusion:** Layer 2 is DeepSeek-only. Locally **unreachable** under corp network — `api.deepseek.com` blocked.

## Q4: LightRAG `llm_model_func` across ingest entry points — unified or not?

**Not unified. Three different stories.**

| Entry point | LightRAG instantiation | `llm_model_func=` | Honors dispatcher? |
|---|---|---|---|
| `ingest_wechat.py` | `get_rag()` at `ingest_wechat.py:216-250`, instance at line 239 | `get_llm_func()` (line 241) | ✅ Yes |
| `batch_ingest_from_spider.py` | `from ingest_wechat import get_rag` at `batch_ingest_from_spider.py:772, 1478`; uses returned instance via `ingest_wechat.ingest_article(url, rag=rag)` (line 299) | inherited from ingest_wechat → `get_llm_func()` | ✅ Yes (transitively) |
| `enrichment/rss_ingest.py` | `LightRAG(...)` at `enrichment/rss_ingest.py:365` | `deepseek_model_complete` (line 367) | ❌ No, hardcoded |

**INCONSISTENCY** — flagged explicitly per audit instructions. `rss_ingest.py` is the outlier; it's a younger module than `ingest_wechat.py` but did not adopt the dispatcher migration (LDEV-04 in quick task 260504-g7a only touched ingest_wechat per `ingest_wechat.py:84-89` comment).

Also note: there is a **second LLM call inside `ingest_wechat.py` itself** at `ingest_wechat.py:835` (`response_text = await deepseek_model_complete(prompt)` — entity extraction post-LightRAG-insert). That call is hardcoded DeepSeek, NOT routed through `get_llm_func`. So even within `ingest_wechat.py` the routing is **not internally consistent**: LightRAG instance honors dispatcher, but the post-insert entity extraction does not. The comment at `ingest_wechat.py:87-88` acknowledges this: "Direct deepseek_model_complete call at line ~750 is unchanged — this only rewires the LightRAG instance."

## Q5: `lib/__init__.py:35` — what gets eagerly imported, why DeepSeek key required at import?

```python
# lib/__init__.py:35
from .llm_deepseek import deepseek_model_complete
```

This eagerly imports `lib.llm_deepseek`, which executes module-level code:

```python
# lib/llm_deepseek.py:73-99
_load_hermes_env()

def _require_api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is not set. Add it to ~/.hermes/.env; "
            "required for all LightRAG LLM calls in Phase 5+."
        )
    return key

# Module-level singletons — read env once at import.
_API_KEY = _require_api_key()
_MODEL = os.environ.get("DEEPSEEK_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
_DEEPSEEK_TIMEOUT_S = 120.0
_client: AsyncOpenAI = AsyncOpenAI(api_key=_API_KEY, base_url=_DEEPSEEK_BASE_URL, timeout=_DEEPSEEK_TIMEOUT_S)
```

**Architectural fact this reflects:**

1. `lib/__init__.py` re-exports `deepseek_model_complete` (`lib/__init__.py:35, 59`) as a convenience alias — `from lib import deepseek_model_complete` is a documented import shape (used in `enrichment/rss_ingest.py:42`).
2. To make that re-export work, `lib.llm_deepseek` must be imported when `lib/` is first imported.
3. `lib.llm_deepseek` was designed to **fail-fast at import** if `DEEPSEEK_API_KEY` is unset — see the docstring at `lib/llm_deepseek.py:31-33` ("fails fast — better to blow up at startup than silently attempt API calls with no credentials").
4. Net effect: **any `from lib import X` (for any X, even `from lib import current_key`) requires `DEEPSEEK_API_KEY` to be set, even if the caller never uses DeepSeek.**

This is the documented "Phase 5 cross-coupling" bug. CLAUDE.md notes it as a "future Phase 5 follow-up, not a Phase 7 fix." `lib/llm_complete.py:9-13` docstring acknowledges the design pressure: "Import-on-demand: provider modules are imported INSIDE `get_llm_func` so DeepSeek-only callers do not pay the google-genai import cost, and vertex-only callers do not need `DEEPSEEK_API_KEY` at import time (preserves option for Phase 5 DeepSeek soft-fail follow-up...)" — but that import-on-demand is bypassed for any caller that imports anything else from `lib/`, because `lib/__init__.py:35` runs first.

The harness's `DEEPSEEK_API_KEY=dummy` env default exists exactly to satisfy this validation gate, not to enable real calls.

## Q6: Vision cascade — hardcoded order or env-driven?

**Order is hardcoded; provider drop-list is env-driven; Gemini Vision auto-detects Vertex vs. dev API by env presence.**

### Cascade order (hardcoded)

`lib/vision_cascade.py:31`:
```python
DEFAULT_PROVIDERS: tuple[str, ...] = ("siliconflow", "openrouter", "gemini")
```

Marked `CASC-01 LOCKED -- do not reorder` in the source comment (`lib/vision_cascade.py:29-30`).

The only runtime reorder happens in `image_pipeline.py:472-476` when SiliconFlow balance is below threshold — flips to `["openrouter", "gemini"]`. This is **not env-driven**, it is balance-driven (`should_switch_to_openrouter` from `lib.siliconflow_balance`).

### Provider drop-list (env-driven)

`image_pipeline.py:481-486`:
```python
_skip_raw = os.environ.get("OMNIGRAPH_VISION_SKIP_PROVIDERS", "").strip()
if _skip_raw:
    _skip_set = {tok.strip() for tok in _skip_raw.split(",") if tok.strip()}
    if _skip_set:
        logger.info("LDEV-06: dropping vision providers per env: %s", _skip_set)
        providers = [p for p in providers if p not in _skip_set]
```

Local-dev typical value (per CLAUDE.md "Local dev env vars" table): `OMNIGRAPH_VISION_SKIP_PROVIDERS=siliconflow,openrouter` → cascade collapses to `["gemini"]`.

### Gemini Vision route — Vertex AI vs. dev API auto-detected

`image_pipeline.py:319-339` — auto-detects Vertex when both `GOOGLE_APPLICATION_CREDENTIALS` and `GOOGLE_CLOUD_PROJECT` are set:
```python
use_vertex = bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")) and \
    bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))
if use_vertex:
    from google import genai
    client = genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )
    model = os.environ.get("OMNIGRAPH_VISION_MODEL", "gemini-3.1-flash-lite-preview")
    ...
# else free-tier fallback via lib.generate_sync(VISION_LLM, ...) at line 343
```

**For local dev under corp network:** harness sets `GOOGLE_APPLICATION_CREDENTIALS` but does NOT set `GOOGLE_CLOUD_PROJECT`. Without the second env var, `use_vertex` evaluates `False` and the fallback `lib.generate_sync(VISION_LLM, ...)` path runs — that path uses the dev-API key (`OMNIGRAPH_GEMINI_KEY` / `GEMINI_API_KEY`) via `lib.generate_sync`. **This is a likely silent gap:** local Vision smoke through Gemini will hit the dev API path (which may also be reachable, but is NOT what the harness intends per the docstring "Vision cascade falls through to Gemini Vision (Vertex)" claim).

**FLAG for follow-up:** the harness's docstring claims "Vision cascade falls through to Gemini Vision (Vertex) which IS reachable" but the harness does NOT set `GOOGLE_CLOUD_PROJECT`. Either the claim is inaccurate, or the SA env automatically loads project from the JSON (needs verification — out of scope for this audit). This is a candidate "known unknown" for ir-4 plan-phase.

## Path maturity matrix

| Stage | Provider | Hardcoded? | Honors `OMNIGRAPH_LLM_PROVIDER`? | Locally runnable (corp net)? | Cite |
|---|---|---|---|---|---|
| Layer 1 (`layer1_pre_filter`) | Vertex Gemini | yes (lazy import) | no — by-design opt-out | ✅ yes | `lib/article_filter.py:399-400` |
| Layer 2 (`layer2_full_body_score`) | DeepSeek | yes (lazy import) | no — LF-2.3 contract pin | ❌ no (api.deepseek.com blocked) | `lib/article_filter.py:520-524` |
| LightRAG via `batch_ingest_from_spider` | dispatcher | no | ✅ yes (transitive via ingest_wechat.get_rag) | ✅ yes (with provider=vertex_gemini) | `batch_ingest_from_spider.py:772, 1478`; `ingest_wechat.py:241` |
| LightRAG via `enrichment/rss_ingest` | DeepSeek | yes | ❌ no | ❌ no | `enrichment/rss_ingest.py:367` |
| LightRAG via `ingest_wechat` | dispatcher | no | ✅ yes | ✅ yes (with provider=vertex_gemini) | `ingest_wechat.py:241` |
| LightRAG via `kg_synthesize` | DeepSeek | yes | ❌ no | ❌ no | `kg_synthesize.py:107` |
| LightRAG via `multimodal_ingest` | DeepSeek | yes | ❌ no | ❌ no | `multimodal_ingest.py:60` |
| LightRAG via `query_lightrag` | DeepSeek | yes | ❌ no | ❌ no | `query_lightrag.py:26` |
| LightRAG via `omnigraph_search/query` | DeepSeek | yes | ❌ no | ❌ no | `omnigraph_search/query.py:54` |
| LightRAG via `ingest_github` | DeepSeek | yes | ❌ no | ❌ no | `ingest_github.py:53` |
| `enrichment/rss_classify.py` | DeepSeek | yes | ❌ no | ❌ no | `enrichment/rss_classify.py:1, 51-60, 129` |
| `batch_classify_kol._call_fullbody_llm` | dispatcher (inline duplicate) | no | ✅ yes | ✅ yes (with provider=vertex_gemini) | `batch_classify_kol.py:281, 311-315` |
| `batch_ingest_from_spider._graded_probe` | dispatcher (inline duplicate) | no | ✅ yes | ✅ yes (with provider=vertex_gemini) | `batch_ingest_from_spider.py:1290-1303` |
| `ingest_wechat._extract_entities` (line 835) | DeepSeek | yes | ❌ no | ❌ no | `ingest_wechat.py:835` |
| Vision cascade primary (SiliconFlow) | SiliconFlow | yes | n/a (separate VISION_PROVIDER cascade) | ❌ no (api.siliconflow.cn blocked) | `image_pipeline.py:379-388` |
| Vision cascade #2 (OpenRouter) | OpenRouter | yes | n/a | ❌ no (openrouter.ai blocked) | `image_pipeline.py:352-377` |
| Vision cascade fallback (Gemini Vision) | Vertex (if GOOGLE_CLOUD_PROJECT set) else dev API | env-detected | n/a | ⚠ depends on `GOOGLE_CLOUD_PROJECT` env presence (see Q6 FLAG) | `image_pipeline.py:319-349` |

## v3.6 dispatcher unification — scope estimate

**T-shirt size: M** (single-day quick task, ~150 LOC across ~9 files).

If the goal is "every LightRAG `llm_model_func=` honors `OMNIGRAPH_LLM_PROVIDER`":

| Change | File | LOC | Notes |
|---|---|---|---|
| `from lib.llm_complete import get_llm_func; ... llm_model_func=get_llm_func()` | `enrichment/rss_ingest.py` | ~3 | Critical for ir-4 retire-rss_classify path |
| same | `kg_synthesize.py` | ~3 | Read-side; less urgent but symmetric |
| same | `multimodal_ingest.py` | ~3 | |
| same | `query_lightrag.py` | ~3 | |
| same | `omnigraph_search/query.py` | ~3 | |
| same | `ingest_github.py` | ~3 | |
| Replace inline dispatch with `get_llm_func()` call | `batch_classify_kol.py:281-322` | ~30 (delete 30 lines, add 5) | Removes duplicate provider-resolution logic |
| Replace inline dispatch with `get_llm_func()` call | `batch_ingest_from_spider.py:1289-1303` | ~15 (similar) | Removes second duplicate; `_graded_probe_vertex` and `_graded_probe_deepseek` may need to stay since they wrap different prompts/timeouts — review needed |
| Migrate `ingest_wechat.py:835` `_extract_entities` to dispatcher | `ingest_wechat.py:835` | ~3 | Only if we want full provider consistency within ingest_wechat |
| Phase 5 cross-coupling soft-fail | `lib/__init__.py:35`, `lib/llm_deepseek.py:87` | ~10 | Make `_API_KEY = _require_api_key()` lazy via property/sentinel; remove eager `_client` build at module load |
| Tests | `tests/unit/test_*` | ~50 (8-10 new tests for the migrated call sites + 1 import-time test for soft-fail) | |

**Out of scope for v3.6 (deliberate):**
- Layer 1 / Layer 2 contract pin — these are documented design decisions (LF-1.3 / LF-2.3), not bugs. Touching them is a separate REQ change.
- Vision cascade — orthogonal to LLM dispatcher (uses VISION_PROVIDER axis, not LLM provider). Already env-driven via `OMNIGRAPH_VISION_SKIP_PROVIDERS` and balance-driven reorder.
- `enrichment/rss_classify.py` — slated for retirement in ir-4 per CLAUDE.md / `.planning/` notes; no migration value.

## Input for ir-4 plan-phase

**ir-4 should:**

1. **Migrate `enrichment/rss_ingest.py:367` to use `get_llm_func()`.** This is the highest-ROI change touching the RSS path — without it, even after retiring `rss_classify.py`, the `rss_ingest` LightRAG instance still hardcodes DeepSeek and remains corp-blocked. Single 3-line change. Exact diff:
   ```diff
   -from lib import deepseek_model_complete
   +from lib.llm_complete import get_llm_func
   ...
   -    llm_model_func=deepseek_model_complete,
   +    llm_model_func=get_llm_func(),
   ```
   This unblocks the entire RSS local-dev e2e once `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` is set.

2. **NOT touch Layer 1 / Layer 2 routing.** These are contract-pinned (LF-1.3 / LF-2.3). The Layer 2 corp-block is by-design; rerouting Layer 2 to Vertex would violate the LF-2.3 amendment. ir-4 should explicitly note this as accepted technical debt.

3. **Verify the `ingest_wechat.py:835` `_extract_entities` DeepSeek call is still needed.** This is the post-LightRAG-insert entity-list extraction. If it's a redundant pass (LightRAG already extracted entities during `ainsert`), it can be deleted. If it's load-bearing, route it through `get_llm_func()` for consistency. Add this to ir-4's audit checklist.

**ir-4 should NOT:**

- Refactor the 3 inline duplicate dispatchers into `get_llm_func()` calls — this is a v3.6 milestone task. Doing it inside ir-4 risks scope creep and conflicts with the LR-classify retire work.
- Touch `lib/__init__.py:35` Phase 5 cross-coupling. Soft-fail belongs in v3.6.
- Migrate `kg_synthesize` / `multimodal_ingest` / `query_lightrag` / `omnigraph_search/query` / `ingest_github` LightRAG sites. These are not on the RSS/KOL ingest critical path; bundling them into ir-4 dilutes the goal.

## Surprises during audit (ranked by load-bearing)

1. **Three inline dispatcher duplicates — only one is `get_llm_func()`.** The function `get_llm_func` exists and is fully tested (`tests/unit/test_llm_complete.py`), but `batch_classify_kol.py:281` and `batch_ingest_from_spider.py:1290` both reimplement the same `provider = os.environ.get("OMNIGRAPH_LLM_PROVIDER", "deepseek").strip() or "deepseek"; if provider == ...` pattern inline. v3.6 unification is mostly about deduping these.
2. **`ingest_wechat.py` is internally inconsistent** — its LightRAG instance honors the dispatcher, but a separate post-ingest DeepSeek call at line 835 does not. This is acknowledged in a code comment but easy to miss when reasoning about "does ingest_wechat honor `vertex_gemini`?".
3. **Vision cascade Vertex auto-detect requires `GOOGLE_CLOUD_PROJECT`, not just SA path.** The harness ships `GOOGLE_APPLICATION_CREDENTIALS` but not `GOOGLE_CLOUD_PROJECT`, so local Vision smoke will fall back to the dev-API path even though the harness docstring claims it will use Vertex. Either the claim is wrong or the SA JSON parsing handles project lookup elsewhere — needs a 5-min verification, not in this audit's scope.
