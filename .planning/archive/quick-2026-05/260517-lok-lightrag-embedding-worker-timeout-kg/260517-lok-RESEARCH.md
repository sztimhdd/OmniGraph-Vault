# Quick 260517-lok — LightRAG Embedding Worker Timeout Research

**Researched:** 2026-05-17
**Domain:** LightRAG internal worker / timeout config (cross-border Aliyun→GCP-Singapore embedding bottleneck)
**Confidence:** HIGH (source-code verified, log signature matches exactly)

---

## Summary

LightRAG 1.4.15 exposes the embedding-side timeout as a **single** kwarg `default_embedding_timeout` (or env var `EMBEDDING_TIMEOUT`). Worker timeout and Health Check timeout are NOT independently settable — they are derived inside `lightrag/utils.py:680-689` as `worker = func * 2` and `health = func * 2 + 15`. Setting `default_embedding_timeout=90` yields the triple `Func=90 / Worker=180 / Health Check=195`, which is essentially the target shape (90:180:225 was just an estimate; LightRAG's hardcoded `+15` instead of an explicit ratio means we land at 195 not 225 — fine, since Worker is the gate that's actually firing).

**Primary recommendation:** Pass `default_embedding_timeout=90` as a kwarg to `LightRAG()` in `kg_synthesize.py:106`. One-line change. No env var, no monkey-patch.

---

## 1. LightRAG Version

```text
lightrag-hku 1.4.15  (from venv/Lib/site-packages/lightrag-hku-1.4.15.dist-info)
```

Pinned in `requirements.txt` line 15 as `lightrag-hku` (no version constraint — Aliyun and local should track latest, but bug log signature `(Timeouts: Func: 30s, Worker: 60s, Health Check: 75s)` matches v1.4.15 exactly so prod is on the same version).

---

## 2. API Findings

### Embedding-side timeout — single kwarg controls all three

**File:** `venv/Lib/site-packages/lightrag/lightrag.py:393-395`

```python
default_embedding_timeout: int = field(
    default=int(os.getenv("EMBEDDING_TIMEOUT", DEFAULT_EMBEDDING_TIMEOUT))
)
```

- Default value `DEFAULT_EMBEDDING_TIMEOUT = 30` is defined at `venv/Lib/site-packages/lightrag/constants.py:101`.
- Wired at `lightrag.py:631-636` into the worker decorator:

  ```python
  wrapped_func = priority_limit_async_func_call(
      self.embedding_func_max_async,
      llm_timeout=self.default_embedding_timeout,
      queue_name="Embedding func",
  )(self.embedding_func.func)
  ```

### Worker / Health Check are auto-derived (NOT independent)

**File:** `venv/Lib/site-packages/lightrag/utils.py:680-689`

```python
if llm_timeout is not None:
    nonlocal max_execution_timeout, max_task_duration
    if max_execution_timeout is None:
        max_execution_timeout = (
            llm_timeout * 2          # <-- Worker = Func * 2
        )
    if max_task_duration is None:
        max_task_duration = (
            llm_timeout * 2 + 15     # <-- Health Check = Func * 2 + 15
        )
```

So with `default_embedding_timeout=30` → Worker=60, Health=75 (matches log).
With `default_embedding_timeout=90` → Worker=180, Health=195.
With `default_embedding_timeout=120` → Worker=240, Health=255.

**LightRAG does NOT pass `max_execution_timeout` or `max_task_duration` from the LightRAG dataclass — they are auto-computed.** No clean way to set them independently from the constructor.

### Concurrency knob (separate)

`embedding_func_max_async` at `lightrag.py:375-377` (env: `EMBEDDING_FUNC_MAX_ASYNC`, default 8 — matches "8 new workers initialized" in the log).

---

## 3. Source-Code Evidence (log line emission)

**File:** `venv/Lib/site-packages/lightrag/utils.py:920-922`

```python
logger.info(
    f"{queue_name}: {workers_needed} new workers initialized {timeout_str}"
)
```

Built from `timeout_info` list at lines 909-918, which uses the locals `llm_timeout`, `max_execution_timeout`, `max_task_duration` populated above.

**Worker-timeout warning** (the line that fires every 60s in prod):

- `utils.py:759-761`:

  ```python
  logger.warning(
      f"{queue_name}: Worker timeout for task {task_id} after {max_execution_timeout}s"
  )
  ```

  Fires from `await asyncio.wait_for(func(*args, **kwargs), timeout=max_execution_timeout)` at line 747-749.

**Caller swallows the timeout** at `venv/Lib/site-packages/lightrag/operate.py:3637-3655`:

```python
try:
    all_embeddings = await actual_embedding_func(
        texts_to_embed, _priority=5
    )
    ...
except Exception as e:
    logger.warning(f"Failed to batch pre-compute embeddings: {e}")
# query proceeds with query_embedding=None / ll_embedding=None / hl_embedding=None
```

This is exactly why the wrapper sees `markdown_len=0` — LightRAG silently degrades to "no embeddings → no vdb retrieval → empty context → empty answer".

### LLM-side reference (for ratio sanity)

**File:** `lightrag.py:431-433`

```python
default_llm_timeout: int = field(
    default=int(os.getenv("LLM_TIMEOUT", DEFAULT_LLM_TIMEOUT))   # DEFAULT_LLM_TIMEOUT = 180
)
```

Wired at `lightrag.py:743-746` exactly the same way → 180/360/375 in the log. Confirms the embedding side will follow the same Func×2 / Func×2+15 derivation.

---

## 4. Recommended Change

### Concrete diff for `kg_synthesize.py:106`

```python
# BEFORE (current)
async def synthesize_response(query_text: str, mode: str = "hybrid"):
    rag = LightRAG(working_dir=RAG_WORKING_DIR, llm_model_func=get_llm_func(), embedding_func=embedding_func)

# AFTER (recommended)
async def synthesize_response(query_text: str, mode: str = "hybrid"):
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=get_llm_func(),
        embedding_func=embedding_func,
        # Cross-border Aliyun→GCP-Singapore embedding via WireGuard takes
        # 15-25s per Vertex call. Hybrid query batches 3 texts (query/ll/hl)
        # which loops 3 sequential Vertex calls inside ONE worker invocation
        # (lib/lightrag_embedding.py:207 `for text in texts`). 90s Func →
        # 180s Worker (utils.py:680-685 auto-derives Worker = Func * 2),
        # comfortably accommodates 3 × 25s + jitter. Default 30/60/75 was
        # built for same-region deploys and is too tight for cross-border.
        default_embedding_timeout=int(os.environ.get("LIGHTRAG_EMBEDDING_TIMEOUT", "90")),
    )
```

### Recommended values

| Setting | Value | Yields (Func / Worker / Health) | Rationale |
|---|---|---|---|
| **Recommended** | `default_embedding_timeout=90` | 90 / 180 / 195 | 3× default; survives 3× 25s sequential calls + jitter |
| Conservative | `default_embedding_timeout=120` | 120 / 240 / 255 | 4× default; matches `KB_SYNTHESIZE_TIMEOUT=240` outer budget exactly at Worker level |
| Aggressive | `default_embedding_timeout=60` | 60 / 120 / 135 | 2× default; risky if any single Vertex call hits 30s |

I recommend **90s** as the primary value, env-overridable via `LIGHTRAG_EMBEDDING_TIMEOUT` for tuning without redeploy.

---

## 5. Open Questions / Risks

### Q1: Interaction with `KB_SYNTHESIZE_TIMEOUT=240` outer wrapper budget

The wrapper kills the call after 240s wall-clock. With Worker=180s, the wrapper's outer budget can absorb ONE worker timeout firing (180s elapsed) + maybe a partial retry — but a SECOND worker timeout would exceed 240s. Hybrid query does ONE pre-compute batch (3 texts inside one worker call), so this is fine: max one timeout per query.

**Risk if `default_embedding_timeout=120`:** Worker=240s exactly equals the outer budget, leaving zero margin for the LLM synthesis call that runs AFTER embedding. Recommend staying at 90 unless 120 is operationally needed.

### Q2: Does LightRAG retry embedding worker timeouts?

**No retry inside the wrapper.** `utils.py:1067-1069` — `WorkerTimeoutError` propagates as `TimeoutError` to the caller (`operate.py:3654`), which catches it as a generic `Exception` and logs warning, then proceeds with all embeddings = None. So a 180s timeout does NOT inflate to 360s via retry. Single-shot per query.

### Q3: Does `embedding_func_max_async` (default 8) help cross-border?

Marginally. The 8 workers process the queue concurrently, but **each query's pre-compute path is one batch call** (`operate.py:3639` packs query/ll/hl into one call). Higher concurrency would only help if multiple queries fire simultaneously. For a single user-driven synthesize call, it doesn't change the per-query latency. Leave default 8.

### Q4: Should the LLM-side timeout (180s) also be raised?

**No (per bug context).** DeepSeek calls go via default eth0 inside China — no cross-border path. Current 180/360/375 is fine for DeepSeek. Out of scope for this quick.

### Q5: Why is our `lib/lightrag_embedding.py` looping `for text in texts` when LightRAG batches?

Because Vertex's `embed_content` API takes one input per call (line 166-170 of `lib/lightrag_embedding.py`). LightRAG hands us 3 texts, we issue 3 sequential Vertex calls. **This is structurally correct for Gemini/Vertex** — each text needs its own request because of the async image-fetch sidecar at `_build_contents` (line 94-114). True per-batch parallelism would require re-shaping that to use `asyncio.gather` over texts. Out of scope for this quick (would be a v1.0.y candidate if 90s still isn't enough). Mentioned for the planner's awareness.

### Q6: Env var name conflict?

Setting raw env var `EMBEDDING_TIMEOUT=90` in systemd would also work without code change (LightRAG reads it directly at `lightrag.py:394`). **But** that env var is process-global and applies to ANY LightRAG instance in the process (e.g., if `batch_ingest_from_spider.py` ever runs in the same process — it doesn't currently, but defensively). The constructor kwarg is more surgical: only affects the synthesize-side rag instance. **Recommend constructor kwarg over env var.**

---

## 6. Source-Code Evidence Index

| What | File:Line | Verified |
|---|---|---|
| `default_embedding_timeout` LightRAG constructor field | `venv/Lib/site-packages/lightrag/lightrag.py:393-395` | yes |
| `DEFAULT_EMBEDDING_TIMEOUT = 30` constant | `venv/Lib/site-packages/lightrag/constants.py:101` | yes |
| Wiring into `priority_limit_async_func_call` | `venv/Lib/site-packages/lightrag/lightrag.py:631-636` | yes |
| Worker auto-derivation `Func * 2` | `venv/Lib/site-packages/lightrag/utils.py:680-685` | yes |
| Health Check auto-derivation `Func * 2 + 15` | `venv/Lib/site-packages/lightrag/utils.py:686-689` | yes |
| Log line emission "X new workers initialized (Timeouts: ...)" | `venv/Lib/site-packages/lightrag/utils.py:920-922` | yes |
| Worker timeout warning emission | `venv/Lib/site-packages/lightrag/utils.py:759-761` | yes |
| Caller silently swallows timeout | `venv/Lib/site-packages/lightrag/operate.py:3637-3655` | yes |
| LLM-side parallel ref (180s default) | `venv/Lib/site-packages/lightrag/lightrag.py:431-433` + `constants.py:100` | yes |
| Env var name `EMBEDDING_TIMEOUT` | `venv/Lib/site-packages/lightrag/lightrag.py:394` | yes |

---

## RESEARCH COMPLETE

**File:** `c:/Users/huxxha/Desktop/OmniGraph-Vault/.planning/quick/260517-lok-lightrag-embedding-worker-timeout-kg/260517-lok-RESEARCH.md`

**Key finding:** Single kwarg `default_embedding_timeout` controls all three timeouts (Func / Worker / Health Check) — set to **90** to deliver Func=90 / Worker=180 / Health=195. One-line change to `kg_synthesize.py:106`. No monkey-patch, no vendor edit, no env var required (constructor kwarg is more surgical).
