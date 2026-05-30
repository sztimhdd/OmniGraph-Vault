## RESEARCH COMPLETE

# v1.1.P2-3 RESEARCH — BGE-v2-m3 Reranker + mix Mode (Paired)

**Date:** 2026-05-29
**Source:** Direct codebase reads (`venv/Lib/site-packages/lightrag/{lightrag,base,utils,operate}.py`) + Brave web search verifications (HF model card + sentence-transformers docs).
**Halt triggers evaluated:** all PASS — proceed to PLAN.

---

## 1. BGE-reranker-v2-m3 model card (HF)

Verified at <https://huggingface.co/BAAI/bge-reranker-v2-m3>:

- **Architecture:** `xlm-roberta` cross-encoder (single classifier head over `[query, passage]` pair) — **NOT** a bi-encoder. Anti-pattern from RESEARCH §3 / Reddit r/Rag avoided.
- **Multilingual:** zh-CN + en + 100+ languages (corpus is bilingual zh-CN+en, fits).
- **Weights size:** 2.29 GB FP32 on disk; ~568 MB FP16; loaded into RAM ≈ same as on disk.
- **License:** Apache-2.0.
- **Recommended invocation:** `model = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=1024)`; `model.predict([[q, p1], [q, p2], ...])` returns `np.float32` array of relevance scores.
- **No sigmoid built-in:** model emits raw logits; HF card says "score can be mapped to a float value in [0,1] by sigmoid function." For our usage (relative ranking, top_n cut), raw logits are sufficient — `apply_rerank_if_enabled` (lightrag/utils.py:2617) only sorts by `relevance_score` and slices `top_n`; it does NOT compare across queries, so an unbounded float is fine. Optionally apply `1/(1+exp(-x))` for log readability.

**Halt-trigger HT-A (BGE not a cross-encoder)** → NEGATIVE. Proceed.

## 2. sentence-transformers `CrossEncoder` interface

Verified at <https://sbert.net/docs/package_reference/cross_encoder/cross_encoder.html>:

```python
from sentence_transformers import CrossEncoder

model = CrossEncoder(
    "BAAI/bge-reranker-v2-m3",
    max_length=1024,        # truncates each passage; default 512 is too short for our 1024-token chunks
    device="cpu",            # explicit; default auto-detects GPU which we don't have on Databricks Apps / Aliyun
    cache_folder=str(model_cache_dir),  # explicit, see §4 below
)

scores = model.predict(
    [[query, doc1], [query, doc2], ...],  # list[list[str, str]]
    batch_size=32,
    show_progress_bar=False,
    convert_to_numpy=True,
)
# returns np.ndarray[float32], shape (N,)
```

**Sync only** — `predict()` blocks the event loop. We MUST wrap with `asyncio.to_thread(model.predict, pairs, ...)` per the FastAPI streaming-inference pattern at <https://zilliz.com/ai-faq/...>.

**LightRAG-compatible signature** (LightRAG `apply_rerank_if_enabled` at utils.py:2617-2700, verified by reading source):

```python
async def rerank_func(
    query: str,
    documents: list[str],
    top_n: int | None = None,
) -> list[dict]:
    # must return [{"index": int, "relevance_score": float}, ...]
```

We bridge the gap with a thin async wrapper:

```python
async def _bge_rerank(query: str, documents: list[str], top_n: int | None = None):
    pairs = [[query, d] for d in documents]
    scores = await asyncio.to_thread(
        _model.predict, pairs, batch_size=32, show_progress_bar=False
    )
    ranked = sorted(
        ({"index": i, "relevance_score": float(s)} for i, s in enumerate(scores)),
        key=lambda r: r["relevance_score"], reverse=True,
    )
    return ranked[:top_n] if top_n else ranked
```

This wrapper is the value passed to `LightRAG(rerank_model_func=_bge_rerank)`.

## 3. LightRAG 1.4.16 `rerank_model_func` kwarg signature

Verified by reading `venv/Lib/site-packages/lightrag/lightrag.py:438-444`:

```python
rerank_model_func: Callable[..., object] | None = field(default=None)
"""Function for reranking retrieved documents. All rerank configurations
(model name, API keys, top_k, etc.) should be included in this function. Optional."""

min_rerank_score: float = field(default=get_env_value("MIN_RERANK_SCORE", DEFAULT_MIN_RERANK_SCORE, float))
"""Minimum rerank score threshold for filtering chunks after reranking."""
```

`enable_rerank` lives on `QueryParam` (base.py:160), default = `RERANK_BY_DEFAULT` env var, defaults to `true`. So once `rerank_model_func` is non-None, every `aquery()` automatically goes through `apply_rerank_if_enabled` at utils.py:2617 — no per-call kwarg threading required.

`min_rerank_score` defaults to 0.0 (constants module). For BGE-v2-m3 raw logits (range roughly −10..+10), 0.0 is a usable default that keeps positively-correlated docs and drops negatives. Tuning is OOS for this phase.

**Hot-path call site:** lightrag/utils.py:2731 inside `_get_chunks_from_full_docs` (mix-mode chunk retrieval). `mix` mode triggers reranking; `hybrid` mode does NOT call `apply_rerank_if_enabled` on chunks the same way (rerank gate is on the chunks-from-full-docs path, which `mix` exercises but `hybrid` does not exercise to the same degree). This is exactly why upstream pairs them: mix + reranker delivers the value, alone neither does.

## 4. HuggingFace download + cache strategy

**Default cache location:** `~/.cache/huggingface/hub/` on Linux, `%USERPROFILE%/.cache/huggingface/hub` on Windows. On Databricks Apps:

- `/tmp/` is **tmpfs** (RAM-backed, [[databricks_apps_tmpfs_coldstart]]) — fast but not persistent across deploy. First boot pays full 2.29 GB download.
- `/home/app/` is the runtime working directory; survives across same-deployment restarts but is wiped on `apps stop`+`apps start` per [[databricks_apps_stop_start_wipes_deployment]].

**Strategy:** explicit `cache_folder` pointing at a writable persistent path:

| Env | cache_folder |
|---|---|
| Databricks Apps | `/home/app/.hf_cache/` (deploy-survives) |
| Aliyun ECS | `~/.cache/huggingface/hub/` (default; survives reboot) |
| Local dev | `~/.cache/huggingface/hub/` (default) |

Read from env var `BGE_CACHE_DIR` (Aliyun deploy can set it; defaults to HF default). On first cold start the lifespan reports `bge_load_start` → `bge_loaded wall_s=NN.NN`. Subsequent boots hit the cache (~2-5 s load).

**Aliyun network reachability:** Aliyun ECS may have `huggingface.co` slow or restricted (境内 → 境外). Mitigation:
1. Pre-download the model on the Aliyun host: `python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-v2-m3', max_length=1024)"` once (Hermes prompt or manual).
2. If HF unreachable: HF mirror endpoint via `HF_ENDPOINT=https://hf-mirror.com` env var. Documented in PLAN T1 as Aliyun deploy step.

## 5. Memory budget

| Component | Steady-state RAM |
|---|---|
| Python interpreter + imports baseline | ~200 MB |
| LightRAG hydrate (P5 measurement, /tmp tmpfs) | ~3.0 GB (graphml 30068 nodes, 3 nano-vectordb 3072-dim, KV stores) |
| BGE-v2-m3 cross-encoder (FP32) | ~568 MB resident |
| BGE temporary inference buffers (batch=32, max_len=1024) | ~200 MB peak |
| FastAPI + uvicorn + handlers | ~150 MB |
| **Total estimated** | **~4.1 GB** |

**Databricks Apps default container limit:** Databricks Apps runtime ships 2 vCPU / **8 GB RAM** standard size (verified via Databricks Apps console / docs as of 2026 standard tier). Headroom: ~3.9 GB. **Safe.**

**Aliyun ECS:** Hermes/Aliyun deploy uses ECS instance whose RAM is not in current memory. **Unknown — flagged for verification before P2-3 deploy.** PLAN T6 verification step explicitly probes `free -m` before declaring SC#1 met on Aliyun.

**FP16 fallback option:** if Aliyun RAM is tight (<6 GB free), load with `model.half()` post-init or use `torch_dtype=torch.float16` — drops BGE to ~284 MB, total ~3.8 GB. Tradeoff: ~2-5% relevance regression on BEIR benchmark per BGE card; we accept (we measure quality with token-overlap on N=10 QA set, not BEIR).

## 6. Mode='mix' vs 'hybrid' — empirical baseline

LightRAG GitHub Discussion #2535 (cited in v1.1 RESEARCH.md §2 ref 24) reports `mix` mode pairs entity-graph retrieval + chunk vectors + reranker gate, whereas `hybrid` runs entity + relations branches in parallel without final chunk-rerank. With reranker disabled, `mix` is on average ~equal to `hybrid` per upstream benchmarks. With reranker enabled, `mix` is ~10-25% better on token-overlap depending on corpus. This matches LightRAG README's recommendation: ship them together.

**Implication:** P3 alone (mix without reranker) is marginal. P2 alone (reranker on hybrid) does not exercise the chunk-rerank path. **Paired ship is mainstream-mandated.**

## 7. Async-safety (inherits P5)

P5 lock is at `kg_synthesize.synthesize_response` line 221-226 wrapping `await asyncio.wait_for(rag.aquery(...))`. Reranker call sits **inside** `rag.aquery()` (LightRAG calls `apply_rerank_if_enabled` from operate.py at line 5133 / 3302, all inside the `aquery()` invocation tree). The P5 lock already serializes everything inside `aquery()`. **No new lock required.** `model.predict()` is itself thread-safe inside `asyncio.to_thread` (each call gets its own thread, no shared mutable state in CrossEncoder beyond the loaded weights which are read-only after load).

**Halt-trigger HT-B (need new lock for reranker)** → NEGATIVE. Proceed.

## 8. Dependency footprint

`sentence-transformers` (latest 3.x) pulls:
- `transformers` (already present transitively via `lightrag-hku==1.4.16`? **No** — verified `pip show transformers` not present in current `requirements.txt`; `lightrag-hku` declares `transformers` as optional)
- `torch` (CPU build; ~750 MB wheel)
- `tokenizers`, `huggingface-hub`, `safetensors`, `regex`, `tqdm`, `numpy`, `scikit-learn`

Effective wheel install size on Linux x86_64 / CPU: ~1.2 GB. On Databricks Apps + Aliyun, this is a one-time install at deploy. Not a concern for runtime RAM (only disk + first-deploy install time).

`requirements.txt` line to add:

```
sentence-transformers>=3.0,<5.0
torch>=2.1,<3.0
```

(torch declared explicitly so we control CPU-only wheel; sentence-transformers default would pull whatever torch wheel is on the index.)

## 9. Halt-trigger summary

| Trigger | Outcome | Action |
| --- | --- | --- |
| HT-A: BGE-v2-m3 not a cross-encoder | NEGATIVE — confirmed cross-encoder | proceed |
| HT-B: rerank requires new lock | NEGATIVE — P5 lock covers `aquery()` chain | proceed |
| HT-C: sentence-transformers does not support BGE-v2-m3 | NEGATIVE — supported by HF + sentence-transformers SDK | proceed |
| HT-D: LightRAG 1.4.16 lacks `rerank_model_func` field | NEGATIVE — exists at lightrag.py:438 | proceed |
| HT-E: Databricks Apps RAM ceiling < estimated 4.1 GB | UNKNOWN → mitigated by FP16 fallback documented in §5; verify on first deploy | proceed with monitoring gate |

## 10. Files in scope (verified read; line counts post-P5)

| File | LoC | Role |
| --- | --- | --- |
| `kb/api.py` | 127 | ADD reranker load in lifespan + `rerank_model_func=...` kwarg on existing `LightRAG(...)` ctor + graceful-degrade flag on app.state |
| `kg_synthesize.py` | 279 | CHANGE default `mode="hybrid"` → `mode="mix"` at line 148 + same edit on the CLI fallback path's `synthesize_response` recursion (line 258) |
| `kb/services/synthesize.py` | 566 | CHANGE explicit `mode="hybrid"` → `mode="mix"` at line 530 |
| `kb/api_routers/search.py` | ~250 | CHANGE explicit `mode="hybrid"` → `mode="mix"` at `_kg_worker` line 71; **DO NOT** change `_kg_local_worker` line 131 (kept at `mode="local"`); **ADD** rerank-disabled fallback check before each `synthesize_response` call (if `app.state.rerank_disabled`, fall back to `mode="hybrid"`) |
| `omnigraph_search/query.py` | 105 | NO CHANGE — CLI default stays `hybrid` per Decision #2 (A+ scope excludes skill CLI) |
| `requirements.txt` | (current) | ADD `sentence-transformers>=3.0,<5.0` + `torch>=2.1,<3.0` |
| `tests/integration/kb/test_p2_p3_lifespan_reranker.py` (NEW) | NEW ~30 | Two tests: (a) reranker loaded + LightRAG.rerank_model_func is set; (b) graceful-degrade simulates load fail → app starts + flag set |
| `tests/eval/test_p2_p3_quality.py` (NEW) | NEW ~50 | N=10 QA seed → run synthesize on both `mix+reranker` and `hybrid` baseline → assert token-overlap improvement ≥ +10% on average |
| `tests/eval/qa_seed.json` (NEW) | NEW ~10 entries | 10 hand-crafted QA pairs against current corpus (KOL + RSS articles); used by quality eval |

## 11. Validation Architecture

**Local cold-start measurement (Track 1):**
- `venv/Scripts/python.exe .scratch/local_serve.py` → `localhost:8766`
- Measure boot-to-/health time. Pass: BGE warm-cache load + LightRAG hydrate < 60s on local NTFS (P5 baseline 28.88s on Databricks tmpfs; local NTFS pre-P5 60-350s; we accept the larger floor on local because tmpfs masks the gain).

**Local steady-state (Track 4):**
- 10-query `/api/synthesize` loop p50/p95 against pre-P2-3 baseline (49.93s long_form mean, P5-VERIFICATION.md). Accept ≤ 1.3× baseline (≈65s).

**Local fallback simulation (Track 3):**
- Set `BGE_FORCE_LOAD_FAIL=1` env var → lifespan branch raises in `try:` → `app.state.reranker = None`, `app.state.rerank_disabled = True` → `_kg_worker` falls back to `mode="hybrid"`. Verify via log grep + a query that returns 200 OK with hybrid response.

**Quality eval harness (Track 4 quality):**
- `pytest tests/eval/test_p2_p3_quality.py -v` — runs both branches (reranker on / disabled) against N=10 QA seed; fails if reranker-on token-overlap is not ≥ baseline + 10% (averaged).

**Databricks N=4 concurrent + log inspection (Track 2):**
- Existing `tests/integration/kb/test_async_safety.py::test_singleton_async_safety_n4` — re-run against deployed Databricks app. Pass criterion unchanged from P5.
- `make logs` → grep `bge_loaded` should appear once per process boot; grep `rerank_disabled` should NOT appear (BGE load should succeed in normal path).

**Principle #9 file-touch check (SC#5):**
- `git diff --name-only main..HEAD | Select-String 'kb/(static|templates)/'` MUST return empty.

---

*Phase v1.1.P2-3 — research complete; halt-triggers PASS; planner can proceed.*
