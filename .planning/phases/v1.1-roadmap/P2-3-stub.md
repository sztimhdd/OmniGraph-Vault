# P2-3 — Reranker (BGE-v2-m3 in-process) + `mix` mode (paired)

**Wave:** 2 (paired deployable unit)
**LoC estimate:** 40–60 (core integration) + benchmark harness
**Risk:** Medium (latency + memory budget; reranker tuning)
**Mainstream alignment:** ⭐⭐⭐⭐⭐ (LightRAG README explicitly recommends rerank + mix paired; [Microsoft Azure 2026 RAG shifts](https://medium.com/microsoftazure/10-rag-shifts-redefining-production-ai-in-2026-7acbdd66076c))
**Dependencies:** P1 (citation pipeline must be deterministic before reranker output flows through it), P5 (singleton process to host reranker model alongside LightRAG)
**Recommended GSD ceremony:** `/gsd:plan-phase` (model integration + benchmark + dual-deploy)

## Goal

Ship a two-stage retrieval pipeline as a single deployable unit: load `BAAI/bge-reranker-v2-m3` in-process via `sentence-transformers.CrossEncoder` at uvicorn startup (no vLLM, no TEI, no external rerank service), and switch the LightRAG default query mode from `hybrid` → `mix`. Per [LightRAG README](https://github.com/hkuds/lightrag): *"When a Reranker model is enabled, it is recommended to set the 'mix mode' as the default query mode."* Shipping these two changes paired is upstream-recommended; shipping either alone is suboptimal. The reranker model lives in the same Python process as the lifespan-pinned LightRAG (P5), so one cold-start covers both heavy resources. Identical deploy on Aliyun + Databricks (same `requirements.txt`, same model checkpoint download at first boot — no infra-side service to provision).

## File-touch list (best guess; verified at /gsd:plan-phase time)

- `requirements.txt` — pin `sentence-transformers>=3.x` (verify version compatibility with current torch / transformers in the venv)
- `kb/api.py` — extend `lifespan` to load `CrossEncoder('BAAI/bge-reranker-v2-m3')` into `app.state.reranker` after LightRAG init
- `lib/rerank_bge.py` — NEW: `rerank_model_func(query: str, chunks: list[Chunk], top_n: int) -> list[Chunk]` adapter conforming to LightRAG's `rerank_model_func` signature
- `kg_synthesize.py:199` — switch `mode='hybrid'` → `mode='mix'`; pass `rerank_model_func` to LightRAG init
- `kb/services/synthesize.py` — pass `rerank_model_func` to LightRAG init; handle empty-after-rerank case (post-`MIN_RERANK_SCORE` filter may zero out)
- `databricks-deploy/app.yaml` + Aliyun `app.yml` — add env: `RERANK_MIN_SCORE`, `RERANK_TOP_N`, `LIGHTRAG_QUERY_MODE=mix`
- `tests/integration/kb/test_rerank.py` — NEW: golden-set rerank ordering test
- `tests/integration/kb/test_mix_mode.py` — NEW: assert `mode='mix'` returns both KG context + chunks
- `scripts/eval_retrieval_quality.py` — NEW: held-out QA set (~30 queries) with token-overlap + answer-quality metrics, before/after rerank+mix

## Success criteria

1. `/api/search/kg` results beat the FTS5 baseline on a held-out QA set, measured by token-overlap with ground-truth answers + qualitative review of 10 sample queries
2. Reranker model loads at uvicorn startup (single CrossEncoder instance shared across requests); first-query overhead from rerank model load = 0 (paid at startup)
3. CPU rerank latency on N=20 chunks ≤ 4s p95 (acceptable for synthesize/long_form; flagged for monitoring on `/api/search/kg`)
4. Memory footprint of reranker model in process ≤ 600MB (~500MB target + 100MB headroom)
5. Aliyun + Databricks deploy parity: same `requirements.txt`, same model checkpoint, byte-identical or semantically-equivalent rerank output on a fixed query set
6. `MIN_RERANK_SCORE` tuned to 0.3–0.5 with eval-driven justification in `P2-3-VERIFICATION.md` (not a guess)
7. Local UAT per Principle #6: 3 sample queries before/after, side-by-side, with screenshots in `P2-3-VERIFICATION.md`

## Hosting model rationale (cite RESEARCH.md §3)

- **In-process via `sentence-transformers.CrossEncoder`** — chosen over vLLM/TEI for ops simplicity (one binary, one process, no service discovery, no extra container)
- **NOT Cohere API** — privacy: chunks would leave the 境内 boundary on every query. Cohere fallback retained ONLY if BGE in-process is fundamentally blocked (e.g., insufficient memory headroom on Databricks Apps tier)
- **NOT BGE-M3** — bi-encoder, anti-pattern when used as reranker ([Reddit r/Rag](https://www.reddit.com/r/Rag/comments/1s8j0im/reranker_worsening_rag_retrieval_results/), [RESEARCH.md §3](RESEARCH.md))
- **NOT ms-marco-MiniLM** — English-only; OmniGraph corpus is bilingual (zh-CN + en)

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| BGE rerank worsens result vs hybrid+no-rerank ([Medium reranker risks](https://medium.com/@akanshak/the-critical-role-of-rerankers-in-rag-98309f52abe5)) | Eval harness measures before/after on held-out set; if regression, investigate `MIN_RERANK_SCORE` tuning, top-K input size, or rollback to `hybrid` mode |
| Memory pressure on Databricks Apps tier (process killed by OOM) | Verify Databricks App memory limit pre-deploy; if too tight, reranker becomes opt-in via env flag; Cohere fallback path documented |
| `mode='mix'` returns more tokens (KG context + chunks) → LLM context-budget pressure | Adjust `chunk_top_k` post-rerank to compensate; current 1M-context Claude/Gemini have headroom |
| First-load CrossEncoder download from HuggingFace at deploy time blocked by corp egress | Pre-bake model into deploy image OR pin model to local artifact store (depends on Aliyun + Databricks egress policy — verify at /gsd:plan-phase time) |

## Deferred decisions (resolve at /gsd:plan-phase time)

- Exact `chunk_top_k` post-rerank (LightRAG default vs tuned)
- `MIN_RERANK_SCORE` value (0.3 vs 0.5 — eval-driven)
- Whether to load reranker on CPU only or auto-detect GPU on hosts that have one (current Aliyun + Databricks are CPU-only; YAGNI for v1.1)

---

**Execution detail TBD at `/gsd:plan-phase v1.1.P2-3` time.**
