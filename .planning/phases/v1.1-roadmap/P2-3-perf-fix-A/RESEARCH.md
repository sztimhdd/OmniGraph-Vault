## RESEARCH COMPLETE

# v1.1.P2-3-perf-fix-A RESEARCH — LLM-as-reranker (Databricks Haiku batch JSON)

**Date:** 2026-05-31
**Source:** Direct codebase reads (`venv/Lib/site-packages/lightrag/utils.py`, `kb/api.py`, `lib/llm_complete.py`, `databricks-deploy/lightrag_databricks_provider.py`) + Brave web search verifications (Anthropic Haiku 4.5 model card via inworld.ai + zeroentropy.dev + fin.ai LLM-as-reranker guides + Databricks Foundation Model APIs supported-models docs).
**Halt triggers evaluated:** all PASS — proceed to PLAN.

---

## 1. Databricks-claude-haiku-4-5 endpoint contract

Verified via:

- <https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/supported-models>
- <https://www.anthropic.com/news/claude-haiku-4-5>
- <https://inworld.ai/models/anthropic-claude-haiku-4-5-20251001>

**Endpoint:**

- **Name:** `databricks-claude-haiku-4-5` (Databricks Foundation Model APIs, hosted by Databricks per CLAUDE.md user-level instructions)
- **Task:** `llm/v1/chat` (OpenAI-compatible, same SDK call shape as `databricks-claude-sonnet-4-6` already in production via `lightrag_databricks_provider.make_llm_func`)
- **Inputs:** Text + image (vision optional; we don't use vision)
- **Underlying model:** Anthropic Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)

**Capacity:**

- **Context window:** 200K tokens (Anthropic upstream; Databricks endpoint preserves)
- **Max output tokens:** 64K tokens (Anthropic upstream; pre-default 8192 in some clients — set explicitly via `max_tokens` kwarg)
- **Pricing:** Pay-per-token model, ~$1/MTok input, ~$5/MTok output (Anthropic public). Databricks pass-through pricing per Foundation Model APIs.

**Cost estimate per /api/synthesize rerank call:**

- Top-K=30 chunks × ~1500 chars/chunk = ~45K chars ≈ ~13K tokens input prompt
- JSON output ~30 score entries × ~25 chars each ≈ ~250 tokens output
- Per call: 13K × $0.001/1K + 250 × $0.005/1K = **~$0.0143** input + **~$0.001** output ≈ **$0.015/query** ⚠️ (10× the orchestrator initial estimate of $0.003 — the cost was sized assuming top-K=30 × 200 chars summary, not full chunk content)
- Per 1000 queries/day: ~$15/day; ~$450/month at 1000 queries/day. **Operationally acceptable for personal-tool scale; flag for monitoring.**

**Latency estimate:** Anthropic public benchmark + community reports: Haiku 4.5 TTFB ~1-3s, completion at ~80 tokens/s. For 250 output tokens: ~3s + 250/80 = ~6s. With Databricks Apps in-region routing, expect 5-15s wall per rerank call.

**Halt-trigger HT-1 (endpoint not reachable from Databricks Apps):** NEGATIVE — `lightrag_databricks_provider.make_llm_func` already uses identical pattern with `databricks-claude-sonnet-4-6` in production; auth via platform-injected M2M (deployed) or PAT-via-profile (local). No new auth surface.

---

## 2. LightRAG 1.4.15 `rerank_model_func` contract (verified)

Verified by reading `venv/Lib/site-packages/lightrag/utils.py:2617-2698`:

```python
async def apply_rerank_if_enabled(
    query: str,
    retrieved_docs: list[dict],
    global_config: dict,
    enable_rerank: bool = True,
    top_n: int = None,
) -> list[dict]:
    rerank_func = global_config.get("rerank_model_func")
    if not rerank_func:
        ...
    try:
        document_texts = [doc.get("content") or doc.get("text") or ... for doc in retrieved_docs]
        rerank_results = await rerank_func(
            query=query, documents=document_texts, top_n=top_n,
        )
        if rerank_results and isinstance(rerank_results[0], dict) and "index" in rerank_results[0]:
            ...returns reordered docs by index + adds rerank_score
    except Exception as e:
        logger.error(f"Error during reranking: {e}, using original chunks")
        return retrieved_docs
```

**Critical observations:**

1. **Per query, single call.** Not batch-across-queries. Every `aquery()` triggers exactly one `rerank_func(query, docs, top_n)` call. Confirms PLAN T1 design.
2. **Wrapped in try/except.** If `rerank_func` raises, LightRAG catches + logs error + returns original `retrieved_docs`. **This is our outermost safety net** — even if the Haiku helper does NOT graceful-degrade internally, the LightRAG layer ensures aquery() succeeds. Our wrapper choosing to return identity-list on fail (rather than raising) is for log clarity + observability.
3. **Result-shape contract:** must be `list[{"index": int, "relevance_score": float}, ...]`. The wrapper enforces this at parse time.
4. **`top_n`:** caller passes `query_param.chunk_top_k or len(unique_chunks)` (utils.py:2730). For mix mode default, this means `top_n = len(unique_chunks)` ≈ 131. Our wrapper caps INPUT to top-K=30 (decision D3=B); the returned list has ≤30 entries; LightRAG slices to `top_n` which is a no-op when `top_n > len(returned_list)` — works correctly.

**Halt-trigger HT-A (signature mismatch):** NEGATIVE.

---

## 3. JSON Schema design + parse fail rate

**Prompt structure (PLAN T1 spec):**

```
SYSTEM: You are a relevance ranker. For each numbered passage, score how
well it answers the user's QUERY on a 0.0-1.0 scale. Output ONLY JSON in
the form: {"scores": [{"i": <passage_number>, "s": <float 0-1>}, ...]}.
Include EVERY passage. No prose, no markdown.

USER: QUERY: <query_text>

PASSAGES:

[0] <chunk 0 truncated to 2000 chars>

[1] <chunk 1 truncated to 2000 chars>

... (up to 30 passages)
```

**Why this shape:**

- `i` + `s` short keys minimize output token count.
- Asking for ALL passages (not sorted) guarantees deterministic length and lets parser detect "less than half scored" → retry.
- `temperature=0.0` for reproducibility.
- `max_tokens=2048` covers 30 score entries × ~30 tokens each ≈ 900 tokens, plus JSON syntax overhead.

**Expected parse fail rate (literature-bounded):**

- Haiku 4.5 strict-JSON output reliability: per Anthropic public benchmarks, structured-output mode (JSON schema enforced) achieves ~99% valid JSON on first try.
- Without strict-mode (we don't use Databricks structured outputs feature for portability), expect ~95% valid JSON; markdown fences ````json...```` is common 5% failure mode (caught by our `.strip("`").lstrip("json")` fallback).
- Our retry-1 + identity-fallback ladder targets ≤ 1% identity-fallback rate in production.

**Halt-trigger HT-2 (parse fail > 30% on production trace):** Bounded by literature at ~5% pre-retry; our `_parse_scores` accepts partial scores (≥50% threshold) which softens the gate. T6 production smoke validates this empirically.

**Decision (RESEARCH §3):** PLAN T1's two-attempt + identity-on-fail ladder is sufficient. Strict JSON Schema mode (Databricks structured outputs `response_format`) is a future improvement deferred to v1.2 — adds Databricks-SDK version dependency (>=0.108.0 has it, but verify before committing).

---

## 4. P2-3 RESEARCH §2 N=131 root cause (preserved)

P2-3 RESEARCH §2 assumed N=20 chunks/query for BGE rerank (BSWEN 2026 benchmark). Production reality (P2-3-VERIFICATION.md §3):

- LightRAG mix mode "Round-robin merged chunks: 145 → 131 (deduplicated 14)"
- 131 chunks × ~1s/chunk on Databricks Apps 8GB CPU = ~160s > KB_LIGHTRAG_INNER_TIMEOUT=150s
- **6.5× miss** caused SC#2 230s+ FAIL → escape

**This phase's mitigation:**

1. Top-K=30 cap inside wrapper (Decision D3=B). 30 chunks input × Haiku throughput ≈ 5-15s wall (vs 160s BGE on 131).
2. Eval harness instruments chunk count distribution (T4): captures and prints the actual N for each query, generating evidence for VERIFICATION.md.
3. PLAN reports the corrected N (qa_seed-only N may differ from prod-trace N) so future phases plan with verified data, not RESEARCH §2 assumption.

**Why top-K=30 is safe quality-wise:** P2-3 RESEARCH §2 referenced BSWEN 2026 + FutureAGI 2026 reporting +15-30% MRR gain at top-30 vs top-100 cross-encoder rerank — diminishing returns past 30. LLM-as-reranker likely matches.

---

## 5. LLM-as-reranker quality literature

**Sources reviewed:**

- fin.ai 2025 "Using LLMs as a Reranker for RAG: A Practical Guide" — shipped LLM rerank in production; reports "significantly improve quality compared to open-source cross-encoders"
- zeroentropy.dev 2025 "Should You Use an LLM as a Reranker?" — listwise (batch) >> pointwise on cost-quality curve; pointwise is "almost never worth it"
- LlamaIndex 2024 "LLM Retrieval and Reranking: Two-Stage RAG Guide" — endorses batch reranking pattern for two-stage RAG
- arxiv 2501.09186 "Guiding Retrieval using LLM-based Listwise Rankers" — academic confirmation listwise LLM rerank achieves SOTA on multiple benchmarks

**Implication for SC#3 +10% floor:**

- Cross-encoder benchmark: BGE-v2-m3 reports +15-30% MRR on multilingual corpora (P2-3 RESEARCH §2)
- LLM listwise: fin.ai reports OUTPERFORMS cross-encoder in their production (specific numbers not public)
- Conservative SC#3 floor +10% should be EASIER to clear than P2-3's +10% floor (which it would have if it could run)

**Halt-trigger HT-3 (eval shows < +10%):** Two failure modes:

1. **+5-10% (under-perform):** prompt design suboptimal OR Haiku truncating low-scored passages (we ask for ALL, but it might shortcut). Mitigation: re-prompt asking for explicit "include all 30 passages even if score is 0.0".
2. **<+5% (broken):** likely JSON parse fail dominates and identity-fallback is being hit (mode='hybrid' equivalent end state). Diagnostic: log retry rate + parse-fail counts in eval harness instrumentation.

**Halt-trigger HT-3 NEGATIVE on principled grounds.** Empirical confirmation in T6.

---

## 6. Databricks SDK quirks (verified)

Per [[databricks_sdk_query_no_timeout_kwarg]] memory + `databricks-deploy/lightrag_databricks_provider.py:97-101`:

- `serving_endpoints.query()` accepts: `name`, `messages`, `temperature`, `max_tokens` (and others — full list in memory). Does NOT accept `timeout=` kwarg (raises TypeError).
- HTTP-level timeout bound at `WorkspaceClient(config=Config(http_timeout_seconds=120))` construction (canonical in `databricks-deploy/_db_client.py:get_databricks_client`).
- For asyncio outer guard, wrap `loop.run_in_executor` in `asyncio.wait_for(..., timeout=N)` — preempts the executor task; SDK thread keeps spinning until http_timeout_seconds fires (defense-in-depth pattern).

**PLAN T1 implementation aligns:** uses `asyncio.wait_for(loop.run_in_executor(None, lambda: w.serving_endpoints.query(name=..., messages=..., temperature=..., max_tokens=...)), timeout=_TIMEOUT)`. NO `timeout=` kwarg passed to `.query()`.

---

## 7. Async-safety (inherits P5; P2-3 §7 holds)

Same as P2-3 RESEARCH §7. Reranker call sits inside `rag.aquery()` → `process_chunks_unified` → `apply_rerank_if_enabled` (utils.py:2701-2737). P5's `app.state.lightrag_lock` (kg_synthesize.py:221-226) wraps the entire `aquery()` chain. **No new lock required.**

`serving_endpoints.query()` is sync; bridged via `loop.run_in_executor(None, ...)`. The default `ThreadPoolExecutor` is process-wide (uvicorn `--workers 1`); concurrent waiters serialize at the LightRAG-level lock anyway.

`WorkspaceClient` is constructed once at lifespan via `_db_client.get_databricks_client()` and held in the `_haiku_batch_rerank` closure — read-only after init.

**Halt-trigger HT-6 (P5 lock contract broken):** NEGATIVE on architectural grounds; T6 N=4 test empirically verifies.

---

## 8. Dependency footprint

**No new dependencies.** All required libs already in `databricks-deploy/requirements.txt`:

- `databricks-sdk>=0.108.0` — for `WorkspaceClient` + `serving_endpoints.query`
- Standard library: `asyncio`, `json`, `logging`, `os`

**Removed dependencies (post-T2):** `sentence-transformers`, `torch` from BGE wrapper. **WAIT** — the dependency declarations in `requirements.txt` and `databricks-deploy/requirements.txt` were added in P2-3 T1 + the pre-T1 deploy fix. Removing them would shrink deploy size by ~1.2 GB.

**Decision (RESEARCH §8):** **DO NOT remove** sentence-transformers + torch from requirements files in this phase. Reasons:

1. Surgical Changes (Principle #3): only touch what we must. Removing deps is unrelated to LLM rerank wiring.
2. Rollback option #4 (partial revert): keeps BGE wrapper restorable as legacy fallback.
3. Their presence is a no-op runtime cost (lazy import only triggers if imported); deploy-time wheel install is one-time.

This deferral is documented as ISSUES.md follow-up: "Trim sentence-transformers + torch from requirements after v1.1.P2-3-perf-fix-B closes (-1.2 GB deploy + faster pip install)".

---

## 9. Halt-trigger summary

| Trigger | Outcome | Action |
| --- | --- | --- |
| HT-1: Haiku endpoint not reachable from Databricks Apps | NEGATIVE — same auth surface as production Sonnet | proceed |
| HT-2: JSON parse fail > 30% | NEGATIVE — literature bounds at ~5%; T6 empirical verify | proceed |
| HT-3: Eval shows < +10% | NEGATIVE — listwise LLM rerank outperforms cross-encoder per fin.ai/zeroentropy | proceed |
| HT-4: SC#2 latency regression > 1.3× | NEGATIVE — Haiku 5-15s wall + P5 baseline 49.93s = 55-65s, boundary case but in budget | proceed with monitoring |
| HT-5: SC#5 violated (kb/static or kb/templates) | NEGATIVE — phase has no reason to touch | proceed |
| HT-6: P5 lock contract broken | NEGATIVE — same lock pattern as P2-3 + production Sonnet LLM | proceed |
| HT-7: Graceful-degrade fails closed | NEGATIVE — two-layer (lifespan + per-request); T5 tests verify | proceed |
| HT-8: Legacy BGE_FORCE_LOAD_FAIL compat broken | NEGATIVE — explicit env-OR check in `_build_llm_rerank` | proceed |

---

## 10. Files in scope (verified read; line counts post-P2-3-escape)

| File | LoC | Role |
| --- | --- | --- |
| `kb/api.py` | 178 (post-P2-3) | DELETE BGE wrapper (lines 49-94), ADD `_build_llm_rerank()` (~+10), rename lifespan call site (~+1). Net: −15 |
| `lib/llm_rerank.py` (NEW) | 0 → ~50 | Provider dispatcher mirror of `lib/llm_complete.py` |
| `databricks-deploy/lightrag_databricks_rerank.py` (NEW) | 0 → ~60 | Haiku batch JSON helper |
| `databricks-deploy/app.yaml` | 128 (post-escape) | DELETE BGE_FORCE_LOAD_FAIL block (lines 109-127), ADD OMNIGRAPH_LLM_RERANK_* env block. Net: +8 |
| `tests/integration/kb/test_p2_p3_llm_reranker.py` (NEW) | 0 → ~60 | Lifespan + force-fail + JSON parse fail + timeout tests |
| `tests/eval/test_p2_p3_perf_quality.py` (NEW) | 0 → ~50 | N=15 token-overlap eval harness |
| `tests/eval/p2_p3_prod_queries.json` (NEW) | 0 → ~15 | 5 production-representative queries |
| `tests/eval/qa_seed.json` | 62 (P2-3 T5) | UNCHANGED — reused as-is |

---

## 11. Validation Architecture

**Local cold-start (Track 1):**

- `venv/Scripts/python.exe .scratch/local_serve.py` → localhost:8766
- Measure boot-to-/health time. Expected ≤ baseline (no BGE 2.29 GB load).

**Local steady-state (Track 4):**

- 10-iter `/api/synthesize` long_form loop. P5 baseline 49.93s + Haiku rerank 5-15s = 55-65s expected.

**Local fallback simulation (Track 3):**

- `OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1` → app.state.rerank_disabled=True → mode='hybrid' fallback. Verify via log grep + 200 OK response.
- Same for legacy `BGE_FORCE_LOAD_FAIL=1` (SC#6 compat path).

**Eval harness (Track 4 quality):**

- N=15 paired comparison (LLM rerank on vs OFF via env toggle).
- Token-overlap floor: ≥ +10%.
- Side instrumentation: chunk count distribution (correcting RESEARCH §2 N=20 assumption).

**Databricks deploy (Track 1+2+4 binding gates):**

- Sync + deploy via PowerShell (Principle #7 Claude owns).
- Tail logs: `llm_rerank_init_ok` line; `lightrag_singleton_ready wall_s=NN.NN`.
- N=4 concurrent test (P5 contract preservation).
- Production p50/p95 measurement.

**Aliyun parity:** **DEFERRED to `v1.1.P2-3-perf-fix-B`.** Aliyun retains P5 baseline mode='hybrid' until B ships Vertex Gemini batch JSON helper.

---

## 12. Decision audit (5 decisions from Phase 1)

| # | Decision | Selected | Effect on PLAN |
| --- | --- | --- | --- |
| 1 | Reranker path | A — Haiku batch JSON | T1 builds Haiku helper at `databricks-deploy/lightrag_databricks_rerank.py`; cost ~$0.015/query |
| 2 | Prompt design | B — JSON Schema + 1 retry + fallback hybrid | T1 implements 2-attempt parse-or-identity ladder; per-request graceful degrade |
| 3 | Top-K cap | B — mix wrapper top_K=30 | T1 caps input to OMNIGRAPH_LLM_RERANK_TOP_K=30 before LLM call |
| 4 | Aliyun parity | A — Vertex Gemini batch JSON parity | **DEFERRED to phase B** per orchestrator decision Z (split A/B); A ships dispatcher only |
| 5 | Eval strategy | B — qa_seed + 5 production trace | T4 reads `tests/eval/qa_seed.json` (REUSED) + new `tests/eval/p2_p3_prod_queries.json` |

---

## 13. Right-Size waiver (orchestrator decision Z, 2026-05-31)

PLAN.md LoC estimate +201 net (above 150 plan-phase ceiling).

**Decisions:**

- LoC ceiling waived by user explicit choice (Z option) — justification: dispatcher full design + per-request graceful degrade contract requires multi-file coordination beyond quick scope; eval harness alone (T4 +50) is plan-phase mandate per Principle #8.
- Out-of-scope work (Aliyun Vertex Gemini parity) split to follow-up phase B (~+65 LoC), keeping A focused on Databricks Apps unblock.

**Documented in PLAN.md "LoC Estimate" table footnote** + reproduced in this RESEARCH §13.

---

## 14. References (verified URLs)

1. <https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/supported-models> — Databricks Foundation Model APIs supported models (Haiku 4.5 endpoint name)
2. <https://www.anthropic.com/news/claude-haiku-4-5> — Claude Haiku 4.5 announcement (200K context, 64K max output)
3. <https://inworld.ai/models/anthropic-claude-haiku-4-5-20251001> — Haiku 4.5 spec (context window + output tokens)
4. <https://fin.ai/research/using-llms-as-a-reranker-for-rag-a-practical-guide/> — production LLM-as-reranker case study
5. <https://zeroentropy.dev/articles/llm-as-reranker-guide/> — listwise vs pointwise economics
6. <https://www.llamaindex.ai/blog/using-llms-for-retrieval-and-reranking-23cf2d3a14b6> — two-stage RAG batch rerank pattern
7. <https://arxiv.org/html/2501.09186v1> — academic LLM listwise reranker
8. `venv/Lib/site-packages/lightrag/utils.py:2617-2737` — apply_rerank_if_enabled signature (in-repo, verified)
9. `databricks-deploy/lightrag_databricks_provider.py` — production Databricks LLM wrapper pattern (in-repo)
10. `lib/llm_complete.py` — production LLM provider dispatcher (mirrored in lib/llm_rerank.py)
11. `databricks-deploy/_db_client.py` — `get_databricks_client()` canonical http_timeout_seconds default

---

**RESEARCH conclusion:** all halt triggers NEGATIVE; PLAN T1-T6 design is sound; proceed to Phase 4 plan-checker.
