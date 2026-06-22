# TASK 1 source-verify surface — 260606-bd-cache-async-quickwin

**Date:** 2026-06-06
**Quick:** `260606-bd-cache-async-quickwin`
**Status:** TASK 1 done — **HALT recommended** before TASK 2/3 ship.
**Reader:** orchestrator + user (decision needed before prod write op).

---

## 1. LightRAG version pinned

`venv/Lib/site-packages/lightrag/_version.py` → `__version__ = "1.4.15"`. Plan's premise of 1.4.16 is wrong by one minor.

## 2. Cache-key reality (B premise — WRONG)

### 2.1 What plan assumed

> "LightRAG 1.4.16 已有 LLM cache (kv_store_llm_response_cache.json) 但 cache key 含 article-internal salt (chunk hash), 导致 article-A 跟 article-B 提到 'OpenAI' entity 时各自调 LLM 一次 describe entity, 不复用. dense topical batches (e.g. AI agent 系列文章) 重复 entity 比例 30-50%."

### 2.2 What the source actually does

`venv/Lib/site-packages/lightrag/utils.py:2037-2102` (function `use_llm_func_with_cache`):

```python
if llm_response_cache:
    prompt_parts = []
    if safe_user_prompt:
        prompt_parts.append(safe_user_prompt)
    if safe_system_prompt:
        prompt_parts.append(safe_system_prompt)
    if history:
        prompt_parts.append(history)
    _prompt = "\n".join(prompt_parts)

    arg_hash = compute_args_hash(_prompt)              # ← KEY = HASH(prompt_text)
    cache_key = generate_cache_key("default", cache_type, arg_hash)
    ...
    if llm_response_cache.global_config.get("enable_llm_cache_for_entity_extract"):
        await save_to_cache(
            llm_response_cache,
            CacheData(
                args_hash=arg_hash,
                content=res,
                prompt=_prompt,
                cache_type=cache_type,
                chunk_id=chunk_id,                     # ← chunk_id stored, NOT hashed
            ),
        )
```

`chunk_id` is **stored alongside** the cache entry for tracking — it is NOT part of the hash. The hash is `compute_args_hash(_prompt)` where `_prompt = user_prompt + system_prompt + history`.

### 2.3 So why doesn't entity-extract cache hit cross-article?

Because the entity-extract user prompt **embeds the chunk content as `input_text`**:

`venv/Lib/site-packages/lightrag/operate.py:2954-2957`:

```python
entity_extraction_user_prompt = PROMPTS["entity_extraction_user_prompt"].format(
    **{**context_base, "input_text": content}     # ← chunk text in prompt
)
```

Each chunk is unique → each prompt is unique → each cache key is unique. The cache only hits on **byte-identical chunk re-ingest** (e.g. retry of the same article).

### 2.4 What about the description-summary path?

`operate.py:362-368` (function `_summarize_descriptions`):

```python
summary, _ = await use_llm_func_with_cache(
    use_prompt,
    use_llm_func,
    llm_response_cache=llm_response_cache,
    cache_type="summary",
)
```

`use_prompt` is built from `description_name` + JSONL of `description_list`. For the same entity name across articles, `description_list` differs (one article's evidence vs another's). Different `description_list` → different prompt → different hash → no cross-article cache hit.

### 2.5 Verdict on B (RECOMMEND HALT)

The B plan as written **cannot be implemented as a transparent wrapper**:

1. The entity-extract LLM call returns *all* entities from one chunk in one call. You can't key it by "entity_name" because you don't know which entities will be returned until the LLM responds.
2. Implementing a true global entity description cache requires changing what's *called*, not what's *cached* — i.e. inserting a "have we already described entity X?" pre-LLM check, then surgically removing X from the entity-extract prompt. This is non-trivial and risks breaking LightRAG's entity-extract output schema.
3. The summary-description path is the most cacheable, but cross-article hit rate is gated by whether `description_list` content overlaps — which it usually doesn't, because each article contributes a *new* description, and the merge step concatenates them.

**Realistic upper bound** of B-as-wrapper: ~0% cross-article hit rate on dense topical batches (because the prompt always changes when a new article adds a description).

Implementation that would actually save Vertex calls requires forking LightRAG's `_merge_nodes_then_upsert` + `_summarize_descriptions` to short-circuit when the merged description is byte-identical to a prior cached one — which is **invasive**, not a 20-LoC wrapper.

## 3. max_async reality (D premise — wrong env names + DANGEROUS)

### 3.1 What plan assumed

> "env-driven config:
> LIGHTRAG_ENTITY_EXTRACT_MAX_ASYNC=16
> LIGHTRAG_RELATION_EXTRACT_MAX_ASYNC=16
> LIGHTRAG_EMBEDDING_FUNC_MAX_ASYNC=16"

### 3.2 What the source actually exposes

`venv/Lib/site-packages/lightrag/lightrag.py:375-376, 423-424, 461-462`:

```python
embedding_func_max_async: int = field(
    default=int(os.getenv("EMBEDDING_FUNC_MAX_ASYNC", 8))    # NOT LIGHTRAG_*
)

llm_model_max_async: int = field(
    default=int(os.getenv("MAX_ASYNC", DEFAULT_MAX_ASYNC))   # NOT LIGHTRAG_*; DEFAULT = 4
)

max_parallel_insert: int = field(
    default=int(os.getenv("MAX_PARALLEL_INSERT", DEFAULT_MAX_PARALLEL_INSERT))
)
```

Three env knobs, all without the `LIGHTRAG_` prefix the plan assumed:

- `MAX_ASYNC` (default **4**, plan said 8) — single knob for ALL LLM calls (entity, relation, summary). There is **no separate entity_extract_max_async / relation_extract_max_async**.
- `EMBEDDING_FUNC_MAX_ASYNC` (default 8)
- `MAX_PARALLEL_INSERT` (defaults to `DEFAULT_MAX_PARALLEL_INSERT`)

`venv/Lib/site-packages/lightrag/constants.py:89` confirms `DEFAULT_MAX_ASYNC = 4`.

### 3.3 But env values don't matter — ingest_wechat hardcodes the ctor kwargs

`ingest_wechat.py:400-428`:

```python
rag = LightRAG(
    working_dir=RAG_WORKING_DIR,
    llm_model_func=get_llm_func(),
    embedding_func=embedding_func,
    # 260601-ipo: halved from 4/4/3 to 2/2/2 after Aliyun OOM postmortem.
    # 4 OOM-kills / 24h on 6/1 (anon-rss peak 11 GB on 15 GB ECS); each
    # async worker holds vdb context (~1-2 GB for 31776×3072 entities).
    # Halving cuts peak RAM ~40-50% with proportional throughput drop.
    # Pair with systemd MemoryMax=4G (deploy/aliyun/systemd/*ingest.service).
    embedding_func_max_async=2,         # ← HARDCODED 2 (NOT 8)
    embedding_batch_num=64,
    llm_model_max_async=2,              # ← HARDCODED 2 (NOT 8)
    max_parallel_insert=2,              # ← HARDCODED 2
    addon_params={"insert_batch_size": 100},
    default_embedding_timeout=int(os.environ.get("LIGHTRAG_EMBEDDING_TIMEOUT", "180")),
    default_llm_timeout=int(os.environ.get("LIGHTRAG_LLM_TIMEOUT", "300")),
    **_vector_storage_kwargs,
)
```

Plan's "default 8" baseline is **off by 4×**. Real production baseline = 2.

### 3.4 The 2 → 16 jump would re-trigger #41-class OOM

Commit `91b33f1` (260601-ipo Aliyun ingest OOM mitigation, 2026-06-01):

> "260601-ipo: halved from 4/4/3 to 2/2/2 after Aliyun OOM postmortem.
> 4 OOM-kills / 24h on 6/1 (anon-rss peak 11 GB on 15 GB ECS); each
> async worker holds vdb context (~1-2 GB for 31776×3072 entities).
> Halving cuts peak RAM ~40-50% with proportional throughput drop.
> Pair with systemd MemoryMax=4G (deploy/aliyun/systemd/*ingest.service)."

Math:

- Halving 4→2 cut peak ~40-50%: 11 GB → ~5.5-6.6 GB anon-rss
- 8× from 2 (i.e. plan's 16) on the same ingest path = ~22-26 GB anon-rss
- ECS RAM total = 15 GB. systemd MemoryMax cap = 4 GB
- Result: instant OOM-kill, every batch, every cron

Open issues already in flight on the same RAM ceiling:

- **#41** `qdrant-snapshot.service` OOM-killed converter on relationships dump (peak RSS ~3-5 GB just for converter, on top of kb-api 2-3 GB + Qdrant 1 GB + system overhead = 14 GB → OOM at ~2h47min wall). 2026-06-05 evening.
- **#42** Same trigger caused 50-80 min Aliyun SLB cross-border throttle.

The 15 GB ECS is already RAM-saturated under stock 2/2/2 ingest concurrency. Bumping to 16 is equivalent to provoking the OOM scenario the team already mitigated.

### 3.5 Verdict on D (RECOMMEND HALT)

D is **not** a "zero-LoC env knob". To actually apply, it requires:

1. **Edit `ingest_wechat.py:414-417`** — change hardcoded ctor kwargs (~3 LoC). Not env-only.
2. **Edit `kg_synthesize.py:161` LightRAG ctor** — same kwargs likely there too (need to verify).
3. **Re-do the OOM postmortem analysis** — prove that paid-tier Vertex throughput won't blow the 15 GB ECS / 4 GB systemd cap. This is non-trivial; the 2026-06-01 author explicitly tied the value to RAM, not throughput.
4. **Coordinate with #41/#42 streaming-write fix** — bumping concurrency before #41 lands compounds the RAM pressure.

The plan claimed "Vertex 100 RPM tier risk: 16 concurrent × N entities/article ~burst 100+ RPM, but LightRAG internal retry self-heals 429" — but the **real** risk is RAM-OOM, not RPM. RPM self-heals; OOM kills the daemon and the systemd `Restart=` policy interacts badly with cron retry windows.

## 4. Open question: kg_synthesize ctor

`kg_synthesize.py:161` and `databricks-deploy/kg_synthesize.py:161` both have `LightRAG(...)` ctors. Need to confirm they hardcode the same `=2` values (likely yes, given symmetry with ingest_wechat). If they do, "env-only" path is broken in two places. If they don't, the synthesize path is using LightRAG defaults (4/8/?) and bumping it independently is more tractable — but synthesize is a query path, not an ingest path, and concurrency there is bounded by user query rate, not batch loop.

## 5. Recommendation

**HALT TASK 2 + TASK 3 + TASK 4.** The plan was written before reading the source, and all three premises are wrong:

| Plan claim | Source reality | Impact |
|---|---|---|
| Cache key chunk-salted, B = wrapper bypass | Cache key is `hash(prompt)`, plan's bypass is architecturally impossible | B unimplementable as 20-LoC wrapper |
| `LIGHTRAG_*_MAX_ASYNC` env vars | Only `MAX_ASYNC` + `EMBEDDING_FUNC_MAX_ASYNC` (no `LIGHTRAG_` prefix) | D env-only path doesn't exist |
| Default 8, raise to 16 | Hardcoded 2/2/2 in ingest_wechat ctor (260601-ipo) | D requires editing ctor, not env |
| 16 concurrent risk = 429 RPM | Real risk = OOM-kill on 15 GB ECS / 4 GB systemd cap | D would re-trigger #41/#42 class incidents |

**Surface to user. Do not commit. Do not push. Do not edit Aliyun .env.**

User decision required:

- **Option A (orchestrator-recommended):** close this quick as "halted on TASK 1 surface; plan premises invalidated by source read", file an ISSUES row capturing the surface, and re-think the speedup path. Realistic options that survive RAM ceiling:
  - **A1.** Vertex paid-tier RAM-aware bump: 2/2/2 → 3/3/3 with concurrent #41 streaming-write fix landing first (`v1.2-qdrant-converter-streaming` from #41 is a prereq). Estimate: 30% throughput improvement, RAM ~6.5-8 GB peak (within 15 GB ECS but above 4 GB systemd cap → also requires `MemoryMax` raise to 6 GB).
  - **A2.** Embedding-only cross-article cache (description text → embedding vector) — this **is** keyable by content (not by chunk), and embedding is the long-tail call (180s timeout, 100 RPM tier). ~50 LoC wrapper around `lib/embedding_func`. Doesn't help LLM-call wall but does help embed-worker queue starvation. Requires verification that LightRAG embedding pipeline is hookable at the lib/ layer.
  - **A3.** PROCESSED-gate budget 150s → 300s **only** (independent of B/D, recommended in u17 already). Pure config bump, no RAM impact, addresses #39 silent-drop.

- **Option B:** insist on shipping D anyway with `=4` (not `=16`) — narrow halving rollback to pre-260601-ipo. ~2-3 LoC ctor edit, RAM stays within OOM-tested band, ~30-50% throughput vs current 2. **Risk:** you're undoing the 260601 mitigation that fixed real OOM-kills; need to verify that the 6/1 conditions (15 GB ECS, 31776×3072 vdb context) still apply. Not recommended without re-running OOM postmortem.

- **Option C:** ignore TASK 1 surface, ship the plan as-written. **Strongly not recommended** — guaranteed Aliyun OOM-kill on next cron, would compound #41/#42.

I am NOT auto-shipping any of A/B/C — surfacing the gap and waiting on user pick.

## 6. Artifacts

- This file: `.planning/quick/260606-bd-cache-async-quickwin/260606-bd-TASK1-SURFACE.md`
- No commits. No pushes. No prod writes.
- Source verified files (read-only):
  - `venv/Lib/site-packages/lightrag/_version.py`
  - `venv/Lib/site-packages/lightrag/utils.py:540-2123`
  - `venv/Lib/site-packages/lightrag/operate.py:2950-3030, 3290-3338`
  - `venv/Lib/site-packages/lightrag/lightrag.py:370-465`
  - `venv/Lib/site-packages/lightrag/constants.py:89-93`
  - `ingest_wechat.py:355-428` (current 2/2/2 hardcode)
  - Commit `91b33f1` (260601-ipo OOM mitigation context)
  - `.planning/ISSUES.md` rows #41, #42 (active OOM incidents on same RAM ceiling)
