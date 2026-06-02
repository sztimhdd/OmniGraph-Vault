# v1.1 Phase 0 — Web Research

**Theme:** KB Query Quality — Modernize KG Retrieval to 2026 RAG Mainstream
**Date:** 2026-05-26
**Method:** 7 brave-search queries × 8 results each (corp-network safe; WebSearch returns 400)
**Worktree:** `plan/v1.1-roadmap` — read-only research, no upstream code touched

---

## 1. Top 3 Mainstream RAG Patterns (2026)

| # | Pattern | What it is | Citation |
|---|---|---|---|
| 1 | **Two-stage retrieval (vector → cross-encoder reranker)** | Retrieve top-K (20–100) by embedding similarity, then rerank with a cross-encoder to top-N (3–10). Baseline of every production RAG in 2026. | [MachineLearningMastery 2026](https://machinelearningmastery.com/top-5-reranking-models-to-improve-rag-results/), [FutureAGI 2026](https://futureagi.com/blog/evaluating-cohere-rerank-rag-2026/) |
| 2 | **Hybrid retrieval + reranking + metadata-enriched chunks** | Dense + sparse + KG signals fed into reranker; chunks carry source metadata for deterministic citation. Microsoft Azure 2026 calls this the "production-grade" line. | [Microsoft Azure: 10 RAG Shifts 2026](https://medium.com/microsoftazure/10-rag-shifts-redefining-production-ai-in-2026-7acbdd66076c), [Tensorlake citation-aware RAG](https://www.tensorlake.ai/blog/rag-citations) |
| 3 | **Agentic / iterative retrieval (Claude-Code style)** | Tool-use model issues `grep`/`glob`/file-read calls instead of vector search; iterative refinement. Anthropic replaced their RAG pipeline with this for Claude Code. | [Anthropic: Agentic Search](https://open.substack.com/pub/robertheubanks/p/anthropic-replaced-their-rag-pipeline), [Anthropic 2026 doubled-limits](https://www.dotzlaw.com/insights/anthropic-2026-code-with-claude/) |

**Verdict for OmniGraph-Vault:** Pattern 2 is the baseline target. Pattern 1 is necessary subset. Pattern 3 is a legitimate "deep research" mode but not a replacement for KG retrieval in a 30k-entity corpus.

---

## 2. LightRAG 1.4 Features Applicable to v1.1

LightRAG 1.4.16 already exposes the mainstream toolkit — we currently use almost none of it.

| Feature | API surface | Status today | v1.1 target |
|---|---|---|---|
| `mode='mix'` query mode | `QueryParam(mode='mix')` | unused — using `mode='hybrid'` (kg_synthesize.py:199) | switch default to `mix` (P3) |
| Reranker injection | `LightRAG(rerank_model_func=...)` + `RERANK_BINDING={cohere,jina,aliyun,null}` | not configured | enable Cohere or BGE-v2-m3 (P2) |
| `MIN_RERANK_SCORE` filter | env var, post-rerank score floor | n/a | tune to 0.3–0.5 after eval |
| `chunk_top_k` post-rerank | `QueryParam(chunk_top_k=N)` | default | tune as part of P2 eval |
| `only_context=True` | `QueryParam(only_context=True)` | unused | candidate for P1 deterministic-cite path |
| Chunk metadata (`full_doc_id`) | populated by ainsert | verified 100% present (1967/1967 in arx-3 Q1) | foundation for P1 |

**Cited recipe** (LightRAG README, 2026): *"Configuring a Reranker model can significantly enhance LightRAG's retrieval performance. When a Reranker model is enabled, it is recommended to set the 'mix mode' as the default query mode."* — [HKUDS/LightRAG](https://github.com/hkuds/lightrag)

**Implication:** P2 (reranker) and P3 (`mix` mode) are paired by upstream design — shipping one without the other is suboptimal per the project authors themselves.

---

## 3. Reranker Cost / Quality Table

| Model | Type | Multilingual | Cost basis | OmniGraph fit | Source |
|---|---|---|---|---|---|
| **Cohere Rerank 3.5** | API cross-encoder | yes (incl. zh-CN) | $1/1k searches (Cohere pricing) | ✅ strongest default; lowest activation cost | [BSWEN 2026 best-rerankers](https://docs.bswen.com/blog/2026-02-25-best-reranker-models/), [FutureAGI](https://futureagi.com/blog/evaluating-cohere-rerank-rag-2026/) |
| **BGE-reranker-v2-m3** | open-source cross-encoder | ✅ strong zh-CN+en | self-host GPU/CPU | ✅ no external API; aligns with on-prem DeepSeek path | [BSWEN 2026](https://docs.bswen.com/blog/2026-02-25-best-reranker-models/), [Medium reranking guide](https://medium.com/@vaibhav-p-dixit/reranking-in-rag-cross-encoders-cohere-rerank-flashrank-c7d40c685f6a) |
| ms-marco-MiniLM-L-6-v2 | open-source cross-encoder | ❌ English-only | self-host CPU | ❌ corpus is bilingual | BSWEN 2026 |
| ZeroEntropy zerank-2 | API | yes | API-based | maybe — newer; less battle-tested | BSWEN 2026 |
| ❌ BGE-M3 (bi-encoder) | bi-encoder, NOT a reranker | yes | — | **anti-pattern** — produces no improvement when used as reranker | [Reddit r/Rag](https://www.reddit.com/r/Rag/comments/1s8j0im/reranker_worsening_rag_retrieval_results/) |

**Recommendation for P2:** Default = **BGE-reranker-v2-m3 self-hosted** (zh-CN/en multilingual, no external API, fits OmniGraph privacy constraint). Cohere Rerank 3.5 as fallback if self-host latency unacceptable. Both are LightRAG-supported via `RERANK_BINDING={cohere,vllm}`.

---

## 4. Deterministic Citation Injection — Validates P1

**Finding (Tensorlake 2026):** *"This approach adds minimal overhead to the chunk text while still letting the retriever and LLM map answers back to exact locations in the source. It's all you need in the preprocessing stage to enable citation-aware RAG."* — [Tensorlake citation-aware RAG](https://www.tensorlake.ai/blog/rag-citations)

**Finding (aarontay.substack 2025):** *"LLMs do not naturally cite the text chunks they retrieve, and even if they did, how do you guard against cases where they don't"* — [Ghost References post](https://aarontay.substack.com/p/why-ghost-references-still-haunt)

**Implication:** the arx-3 bug 2c symptom (LLM compliance fragility across DeepSeek + Vertex Gemini + Databricks Claude on `_resolve_sources_from_markdown`) is a **known anti-pattern in 2026 literature**. Deterministic injection from chunk metadata (full_doc_id → article_hash → URL) is the validated fix. P1 plan is on-mainstream.

---

## 5. Agentic RAG Patterns + ARAG Salvage Feasibility

| Signal | Source | Implication for ARAG |
|---|---|---|
| Anthropic replaced Claude Code's embedding-RAG with agentic search (grep/glob/iterative tool-use) | [Substack: Anthropic agentic search](https://open.substack.com/pub/robertheubanks/p/anthropic-replaced-their-rag-pipeline) | Agentic deep-research is a legit 2026 product mode, NOT a fad. |
| Anthropic 2026: doubled limits + infinite context — "value of clever summarizer drops to zero" | [Dotzlaw: 2026 Code with Claude](https://www.dotzlaw.com/insights/anthropic-2026-code-with-claude/) | Some ARAG harness logic may be overkill. Audit Reasoner+Synthesizer for components that only existed to fight 200k context. |
| Claude tool-use orchestration patterns (parallelization, routing, multi-step) | [Anthropic Academy](https://www.scrumlaunch.com/blog/what-is-anthropic-academy) | ARAG's Reasoner pattern aligns; surface as user-facing "deep research" mode (P4). |
| "RAG is dead — long live context engineering" | [Callstack 2026](https://www.callstack.com/blog/rag-is-dead-long-live-context-engineering-for-llm-systems) | Polemical — applies to small corpora only. OmniGraph-Vault has 30k entities + 39k relations; RAG layer remains load-bearing. |

**ARAG salvage verdict:** **Feasible and on-mainstream.** Wire `/api/research` as a user-visible "deep research" tab (P4). Do NOT scrap the Reasoner+Synthesizer code — its tool-use pattern is exactly what 2026 agentic-RAG literature endorses. Audit for any components whose only purpose was fighting the 200k context window — those can be removed (Anthropic 2026 explicit advice).

---

## 6. FastAPI Lifespan-Pinned Singleton Pattern (for P5)

**Canonical pattern** (FastAPI official docs):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.lightrag = await build_lightrag()  # heavy init at startup
    yield
    await app.state.lightrag.finalize_storages()  # graceful shutdown

app = FastAPI(lifespan=lifespan)
```

— [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)
— [Stack Overflow: Optimal way to initialize heavy services once](https://stackoverflow.com/questions/67663970/optimal-way-to-initialize-heavy-services-only-once-in-fastapi)
— [SitePoint FastAPI common problems](https://www.sitepoint.com/problems-and-solutions-with-fast-api-servers/) — confirms `app.state` is lifespan-scoped per worker; the canonical place for heavy resources.

**Constraint:** lifespan-scoped state is **per worker process**. If kb-api ever runs `--workers > 1`, each worker gets its own LightRAG instance + own embedding cache. For v1.1, single-worker is fine (current Aliyun + Databricks deploy both single-worker).

**P5 risk flagged by literature:** async safety — LightRAG ops must be safe for concurrent `aquery()` calls on a shared instance. arx-3 bug 2c showed Worker 360s + Health 375s timeouts; need to verify the singleton handles N concurrent queries without deadlock.

---

## 7. Risks / Pitfalls Flagged in Literature

| Risk | Source | v1.1 mitigation |
|---|---|---|
| Bi-encoder misused as reranker → zero gain | [Reddit r/Rag](https://www.reddit.com/r/Rag/comments/1s8j0im/reranker_worsening_rag_retrieval_results/) | P2: BGE-reranker-v2-m3 (cross-encoder) NOT BGE-M3 |
| Reranker can hurt recall on weak retriever | [Medium reranking guide](https://medium.com/@akanshak/the-critical-role-of-rerankers-in-rag-98309f52abe5) | P2 needs eval harness with token-overlap & answer-quality metrics |
| Document-Level Retrieval Mismatch (DRM) | [arxiv 2603.19251](https://arxiv.org/html/2603.19251v1) | Metadata enrichment (P1's chunk_full_doc_id approach) directly addresses this |
| Vector-dim mismatch (storage vs runtime) | LightRAG PyPI: *"vector dimension must be defined upon initial table creation. when changing embedding models, it is necessary to delete the existing vector-related tables"* | **HARD CONSTRAINT** — Vertex 3072-dim is locked; storage rebuild = milestone-scale, NOT v1.1 scope |
| Reranker latency at scale | [BSWEN 2026](https://docs.bswen.com/blog/2026-02-25-best-reranker-models/) | P2 eval must include p95 latency; budget 200–500ms reranker overhead |
| Citation hallucination under LLM-compliance citation patterns | [Ghost References](https://aarontay.substack.com/p/why-ghost-references-still-haunt) | P1 eliminates LLM-compliance dep — deterministic only |
| KG community-detection overhead (Microsoft GraphRAG pattern) | [Salfati Group Graph RAG Guide](https://salfati.group/topics/graph-rag) | LightRAG already handles this; P3 (`mix` mode) leverages existing community summaries |
| `app.state` not concurrent-safe by default | [SitePoint FastAPI](https://www.sitepoint.com/problems-and-solutions-with-fast-api-servers/) | P5 must explicitly verify async-safety of LightRAG instance under N concurrent queries |

---

## 8. Phase Confidence After Research

| Phase | Pre-research confidence | Post-research confidence | Notes |
|---|---|---|---|
| P1 K2 chunk-metadata citation | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Tensorlake + arxiv DRM directly endorse |
| P2 Reranker | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | LightRAG README explicitly recommends paired with mix mode |
| P3 `mode='mix'` | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | LightRAG authors recommend mix is default once reranker enabled |
| P4 ARAG salvage | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Anthropic 2026 trend supports; audit ARAG for context-window-fighting bloat |
| P5 LR-singleton | ⭐⭐ (perf only) | ⭐⭐⭐ | Async-safety concern surfaced; not blocker but adds verification step |
| P6 Fixture drift | ⭐⭐ | ⭐⭐ | Housekeeping; no research needed |
| P7 Pydantic mode-arg | n/a | n/a | 1-line side bug |

**Net effect of research:** No phases dropped. P3 strengthened (now mainstream-default per upstream). P5 gains an async-safety verification gate. ARAG salvage stays in scope — agentic deep-research is endorsed by 2026 literature.

---

## 9. Recommended Wave Ordering Adjustment Based on Findings

**Original candidate order** (from orchestrator prompt):

- Wave 1: P5 + P1 → Wave 2: P3 + P2 → Wave 3: P4 → Wave 4: P6

**Research-informed adjustment:** keep order but **bind P2+P3 tightly** in Wave 2 — LightRAG upstream guidance is "rerank + mix mode together"; shipping P3 alone without reranker enabled gives marginal gain. Treat P2 and P3 as a single deployable unit where possible.

P5 still goes first (faster cold-start unblocks P1-P4 iteration). P1 second (real bug 2c fix, mainstream-aligned). Wave 2 paired (P2+P3). Wave 3 P4 (separate UI surface). Wave 4 P6.

---

## 10. References Index (all citations used above)

1. https://github.com/hkuds/lightrag — LightRAG README (rerank + mix mode recommendation)
2. https://github.com/HKUDS/LightRAG/blob/main/env.example — RERANK_BINDING env vars
3. https://lightrag.github.io/ — hybrid mode description
4. https://docs.bswen.com/blog/2026-02-25-best-reranker-models/ — reranker comparison
5. https://futureagi.com/blog/evaluating-cohere-rerank-rag-2026/ — Cohere Rerank 3.5 eval
6. https://machinelearningmastery.com/top-5-reranking-models-to-improve-rag-results/ — top-5 rerankers 2026
7. https://www.reddit.com/r/Rag/comments/1s8j0im/reranker_worsening_rag_retrieval_results/ — bi-encoder anti-pattern
8. https://medium.com/@vaibhav-p-dixit/reranking-in-rag-cross-encoders-cohere-rerank-flashrank-c7d40c685f6a — reranker types
9. https://medium.com/@akanshak/the-critical-role-of-rerankers-in-rag-98309f52abe5 — reranker risks
10. https://www.tensorlake.ai/blog/rag-citations — citation-aware RAG (P1 validation)
11. https://aarontay.substack.com/p/why-ghost-references-still-haunt — LLM citation hallucination
12. https://arxiv.org/html/2603.19251v1 — Document-Level Retrieval Mismatch (DRM)
13. https://medium.com/microsoftazure/10-rag-shifts-redefining-production-ai-in-2026-7acbdd66076c — 2026 RAG shifts
14. https://medium.com/graph-praxis/graph-rag-in-2026-a-practitioners-guide-to-what-actually-works-dca4962e7517 — Graph RAG 2026 practitioner guide
15. https://salfati.group/topics/graph-rag — Graph RAG architecture guide
16. https://medium.com/@tongbing00/graphrag-in-2026-what-to-use-when-to-use-it-and-what-to-watch-out-for-a1fa1c283023 — GraphRAG 2026 tooling comparison
17. https://open.substack.com/pub/robertheubanks/p/anthropic-replaced-their-rag-pipeline — Anthropic agentic search
18. https://www.dotzlaw.com/insights/anthropic-2026-code-with-claude/ — Anthropic 2026 doubled limits
19. https://www.scrumlaunch.com/blog/what-is-anthropic-academy — Anthropic agent patterns
20. https://www.callstack.com/blog/rag-is-dead-long-live-context-engineering-for-llm-systems — context engineering trend
21. https://fastapi.tiangolo.com/advanced/events/ — FastAPI lifespan official
22. https://stackoverflow.com/questions/67663970/optimal-way-to-initialize-heavy-services-only-once-in-fastapi — heavy-service init
23. https://www.sitepoint.com/problems-and-solutions-with-fast-api-servers/ — app.state lifespan scope
24. https://github.com/HKUDS/LightRAG/discussions/2535 — mix vs hybrid combined empirical finding
25. https://pypi.org/project/lightrag-hku/ — vector-dim lock constraint

---

## HALT POINT — Phase 0 Complete

Awaiting user "go phase 1" before drafting `ROADMAP.md`. If running unattended, will proceed after 10-min idle (per orchestrator instructions).
