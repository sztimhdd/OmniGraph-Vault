# Milestone v1.1 Roadmap — KB Query Quality

**Status:** DRAFT (Phase 1 of v1.1 planning workflow)
**Branch:** `plan/v1.1-roadmap` · worktree `../OmniGraph-Vault-v1.1-plan/`
**Author:** v1.1 standalone planning agent · 2026-05-26
**Companion docs:** [RESEARCH.md](RESEARCH.md) · stub files (Phase 2, pending)

---

## 1. Theme

**Modernize OmniGraph-Vault's KG retrieval pipeline to 2026 RAG mainstream.**

v1.1 takes the v1.0 ingestion baseline (stable since 2026-05-13) and rebuilds the **query side** to match what production Graph-RAG systems look like in 2026: deterministic citation injection from chunk metadata, a cross-encoder reranker paired with LightRAG's `mix` query mode, a lifespan-pinned LightRAG singleton for sub-30s cold-start, and an agentic "deep research" mode that finally surfaces the dormant ARAG pipeline to the user. Everything is in service of one thing — **answers that cite real sources, retrieved by mainstream techniques, returned fast enough that users iterate on them.**

---

## 2. Why Now

**Triggered by 2026-05-26 closure of arx-3 bug 2c.** Today's diagnostic on long-form synthesis revealed:

- The current `_resolve_sources_from_markdown` regex-grep on LLM output is **fundamentally fragile** — it failed identically across DeepSeek, Vertex Gemini, and Databricks Claude. arx-3 G-remove + K1 patches are tactical (1 line + ~15 LoC FTS5 fallback); they do not fix the **2024-era Basic-GraphRAG pattern** underneath.
- LightRAG 1.4.16 has supported **`mode='mix'`, `rerank_model_func`, `chunk_top_k`, `only_context`** for months. We use **none** of them. Per the project authors themselves: *"When a Reranker model is enabled, it is recommended to set the 'mix mode' as the default query mode."* ([HKUDS/LightRAG README](https://github.com/hkuds/lightrag), cited in [RESEARCH.md §2](RESEARCH.md))
- **2026 RAG literature converges** on three patterns: two-stage retrieval (vector → reranker), metadata-enriched chunks for deterministic citation, and agentic retrieval for deep-research surfaces. OmniGraph-Vault is missing all three. ([RESEARCH.md §1](RESEARCH.md))
- The **ARAG milestone** built a Reasoner+Synthesizer pipeline with 41 REQs + 165 tests — and never wired it to the frontend. TEST-05 is 4/5 unfilled. Zero user-visible value despite the engineering investment. The 2026 agentic-RAG trend ([Anthropic agentic search](https://open.substack.com/pub/robertheubanks/p/anthropic-replaced-their-rag-pipeline)) endorses surfacing this pattern as a product mode, not deleting it.
- **LR-singleton architectural debt** (cold-start 60–350s on non-tmpfs) was filed today from arx-3 STEP 4. Independent of quality work, it caps iteration speed for every other v1.1 phase.

The window is open: ingestion is frozen (Hermes RO until 2026-06-22, [project_aim2_closed_260524.md](../../../.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/project_aim2_closed_260524.md)), and the 2026 mainstream is mature enough that we can adopt patterns straight from upstream LightRAG docs and Microsoft Azure RAG guidance without inventing anything new.

---

## 3. Phase Table

| # | Phase | Wave | LoC | Risk | Mainstream | Deps | Goal (1 sentence) |
|---|---|---|---|---|---|---|---|
| **P6.0** | `body_cleaned` schema fix (Wave 1 unblocker) | 0 | 5–15 | Low | ⭐ | — | Repair `kb/data/article_query.py:326` schema reference + `tests/unit/_ingest_fixtures.py` `CREATE TABLE` drift so Wave 1 testing has green fixtures to build on. |
| **P1** | K2 chunk-metadata citation injection | 1 | 30–50 | Low | ⭐⭐⭐⭐⭐ | P6.0 | Replace LLM-output regex citation with deterministic source extraction from LightRAG chunk metadata (`full_doc_id` → article URL). |
| **P5** | LR-singleton + async-safety | 1 | 50–80 | Medium | ⭐⭐ | P6.0 | Pin LightRAG to `app.state` via FastAPI lifespan and verify concurrent-query safety; cold-start drops from 60–350s to sub-30s. |
| **P2-3** | Reranker (BGE-v2-m3, in-process) + `mix` mode (**paired**) | 2 | 40–60 | Medium | ⭐⭐⭐⭐⭐ | P1, P5 | Load `BAAI/bge-reranker-v2-m3` in-process via `sentence-transformers.CrossEncoder` at uvicorn startup **and** switch default query mode to `mix` — paired per upstream guidance, identical deploy on Aliyun + Databricks. |
| **P4.0** | ARAG audit (read-only) | 3 | 0 (doc only) | Low | ⭐⭐⭐⭐ | P1, P2-3 | Produce `P4-AUDIT.md` cataloging every `lib/research/*` file + function with verdict (KEEP / REWRITE / DELETE / WIRE-TO-FRONTEND); resolve TEST-05 4/5 root cause (200k-era bug or real). |
| **P4.1** | ARAG salvage (mutating) | 3 | phase-scale | High | ⭐⭐⭐⭐ | P4.0 + user approval | Execute `P4-AUDIT.md` verdicts as atomic commits per cluster; build the frontend "Deep Research" tab + wire `/api/research` end-to-end. |
| **P6.1** | Full fixture drift audit | 4 | 1–2 days | Low | ⭐⭐ | — | Resolve remaining fixture drift ERRORs + `test_search_kg_job_completes` mock-rewire stale + remaining drift listed in audit. |
| **P7** | `/api/search/kg` Pydantic mode-arg fix | side | 1 line | Low | — | fold-or-park | Pydantic schema accepts `mode` arg but silently ignores it — 1 LoC + 1 test, decide at Wave 1 close: fold into P1 or park as standalone `v1.1.x` quick. |

**LoC totals:** ~125–205 LoC core code + 1–2 days fixture cleanup + 1 phase-scale ARAG/UI surface. Right-Size discipline (Principle #8) applies per phase — each picks `/gsd:fast` / `/gsd:quick` / `/gsd:plan-phase` after Phase 1 DECIDE produces actual LoC count.

---

## 4. Wave Ordering Rationale

### Wave 0 — Blocker Fix (P6.0, must precede Wave 1)

**Test fixture drift on `body_cleaned` is a hard prereq for Wave 1 testing.** `kb/data/article_query.py:326` references a column the test fixtures don't create; running P1 unit tests against this drift gives false RED. Fix this first as a `/gsd:quick` (~1–2h, 5–15 LoC). Mainstream alignment is housekeeping-tier (⭐) but it gates everything else, so it runs **before** Wave 1 starts. Splitting P6 at this seam also keeps the original Wave 4 P6.1 housekeeping job atomic and unrushed.

### Wave 1 — Foundation (P1 + P5, parallel, both depend on P6.0)

**Run P1 and P5 in parallel — they touch disjoint code paths.**

- **P5 first principle:** singleton refactor unblocks faster iteration on every other phase. Cold-start of 60–350s on local NTFS makes UAT loops painful; once kb-api boots once and stays warm, P1/P2-3/P4 testing cycles drop from minutes to seconds. P5 is **enabling infrastructure, not user-visible quality**.
- **P1 in parallel:** K2 chunk-metadata citation is the **real fix for bug 2c**. arx-3 G-remove + K1 patches were tactical; P1 eliminates the LLM-compliance dependency entirely. Mainstream alignment ⭐⭐⭐⭐⭐ ([Tensorlake citation-aware RAG](https://www.tensorlake.ai/blog/rag-citations), [arxiv 2603.19251 DRM paper](https://arxiv.org/html/2603.19251v1)). It's the highest-priority quality phase.
- **Why parallel:** P5 touches `kg_synthesize.py:146-153` + `kb/api.py` lifespan. P1 touches `kb/services/synthesize.py` + `kb/api_routers/search.py`. No file overlap. They land independently.
- **Wave 1 close gate:** both must deploy to Aliyun + Databricks with parity verification ([feedback_kb_local_uat_mandatory.md](../../../.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/feedback_kb_local_uat_mandatory.md)) before Wave 2 starts.

### Wave 2 — Quality (P2-3 paired)

**P2 and P3 ship together as a single phase.** [RESEARCH.md §2](RESEARCH.md) cites the LightRAG README directly: *"When a Reranker model is enabled, it is recommended to set the 'mix mode' as the default query mode."* Shipping P3 (`mix` mode) without a reranker gives marginal gain; shipping P2 (reranker) without `mix` mode runs against upstream design. Pair them:

- **Hosting model: `sentence-transformers.CrossEncoder` in-process at uvicorn startup** — no vLLM, no TEI, no external rerank service. Model loads alongside LightRAG in the same Python process. Memory footprint ~500MB; pairs naturally with P5's lifespan-pinned LightRAG (one process, both heavy resources). Identical deploy on Aliyun + Databricks (same `requirements.txt` + same model checkpoint, no infra-side service to provision).
- **Why in-process not vLLM:** simpler ops (one binary), no extra container, no service discovery, no external network call from kb-api → reranker. Aligns with on-prem privacy posture (chunks never leave the kb-api process for reranking).
- **Why not Cohere API:** privacy concern — sending chunks to api.cohere.com leaks corpus content outside the 境内 boundary. Cohere fallback retained ONLY if BGE in-process is fundamentally blocked (e.g., insufficient memory headroom).
- **Why NOT BGE-M3:** BGE-M3 is a bi-encoder, not a cross-encoder; using it as a reranker is a known anti-pattern ([RESEARCH.md §3](RESEARCH.md), [Reddit r/Rag](https://www.reddit.com/r/Rag/comments/1s8j0im/reranker_worsening_rag_retrieval_results/)).
- **Latency budget:** CPU-only rerank on N=20 chunks ≈ 1–4s per query. Acceptable for synthesize/long_form; flagged for monitoring on `/api/search/kg`.
- One source change: `kg_synthesize.py:199` switches default `mode='hybrid'` → `mode='mix'`.
- One config change: pass `rerank_model_func` into LightRAG init.
- One eval harness: token-overlap + answer-quality metrics on a held-out QA set, before/after.
- **Depends on P1 + P5:** reranker output flows through P1's deterministic citation path (running Wave 2 before P1 = citation surgery twice); reranker model lives in the same singleton process as LightRAG (running Wave 2 before P5 = per-request 500MB allocation, untenable).

### Wave 3 — Advanced (P4.0 → P4.1, sequential within wave)

**Split into a read-only audit phase and a mutating salvage phase.** P4.0 produces `P4-AUDIT.md` (no file mutations); user reviews verdicts; P4.1 then executes them as atomic commits. This guarantees the destructive work has explicit user sign-off on every cluster (deletes, rewrites, frontend-wires) before any line of `lib/research/*` is touched.

**P4.0 — ARAG audit (read-only):**
- Catalog every file + function under `lib/research/*` with verdict: KEEP / REWRITE / DELETE / WIRE-TO-FRONTEND.
- **Audit criterion:** anything authored as a 200k-context-window-era workaround = DELETE candidate. Reference [Anthropic 2026 doubled-limits](https://www.dotzlaw.com/insights/anthropic-2026-code-with-claude/) — *"the value of having written a clever summarizer drops to zero."* Modern Claude Sonnet 4.6 (1M context) + Vertex Gemini 2.5 (1M context) eliminate most pre-2026 summarizer scaffolding.
- **Resolve TEST-05 4/5 root cause:** classify as "200k-era constraint bug (delete the test)" or "real regression (real fix needed)". This must be resolved before P4.1 picks up the test.
- Output: `.planning/phases/v1.1-roadmap/P4-AUDIT.md` with verdict table + line-level rationale.
- Zero file mutations.

**P4.1 — ARAG salvage (mutating):**
- **Depends on P4.0 + explicit user approval of every verdict.**
- Executes verdicts as atomic commits per cluster: deletes-cluster, rewrites-cluster, wire-to-frontend-cluster.
- New product surface: frontend "Deep Research" tab in `kb/static/qa.*` consuming `/api/research`.
- 1 user UAT pass on the new tab — closes the long-standing TEST-05 4/5 gap with screenshot evidence per Principle #6.
- **Depends on P1 + P2-3 stability:** the deep-research path reuses P1's citation pipeline and P2-3's retrieval substrate; running P4.1 before those stabilize = rework.

### Wave 4 — Housekeeping (P6.1 full fixture drift audit)

**Last because regression-pure.** No user-visible value; runs after Wave 1–3 stabilize so fixture work is against the final v1.1 contract, not a moving target. Scope is the original P6 minus what P6.0 already fixed: remaining drift ERRORs, `test_search_kg_job_completes` mock-rewire stale, and any new fixture drift introduced by P1 / P2-3 / P4.1.

### P7 — Side Decision (fold or park)

At end of Wave 1 (when P1 commits land), decide:
- **Fold into P1:** if P1 atomic commit window is still open and the Pydantic fix is touching the same `kb/api_routers/search.py` file → 1 extra LoC, no separate phase overhead.
- **Park as `v1.1.x` quick:** if P1 is already shipped → file as standalone `/gsd:quick` for next available window.

Either is correct. Decide based on P1 commit timing, not LoC.

---

## 5. Success Criteria — v1.1 Done When

1. **`/api/synthesize` long_form** returns deterministic source chips populated from chunk metadata, not LLM-generated regex matches. Zero LLM-compliance dependency. Verified by unit test pinning observable output across DeepSeek + Vertex Gemini + Databricks Claude providers.
2. **`/api/search/kg`** returns KG-quality results that beat the FTS5 baseline on a held-out QA set, measured by token-overlap with ground-truth answers + qualitative review on 10 sample queries.
3. **Cold-start** of `kb-api` to first `/api/synthesize` response is sub-30s on local NTFS (down from current 60–350s). Steady-state per-query latency unchanged or better.
4. **Deep Research mode** is shipped end-to-end: frontend tab → `/api/research` → Reasoner+Synthesizer → user-visible answer with citations. 1 user UAT pass with screenshot evidence in VERIFICATION.md per Principle #6.
5. **Pytest baseline** stays clean — current 953-test floor (per most recent CI green run) does not regress. Each phase adds tests for its own contract.
6. **Aliyun + Databricks deploy parity** verified after each phase ships — both environments return byte-identical (or semantically-equivalent) responses for the same query set.

---

## 6. Hard Constraints (preserved from CLAUDE.md + project memory)

These are non-negotiable for v1.1. Any phase plan that violates one of these is a BLOCKED plan that must be revised.

| # | Constraint | Source |
|---|---|---|
| HC-1 | **Never bypass LightRAG core asset.** No DeepSeek-only or FTS5-only long_form paths. Fix infrastructure, do not skip the substrate. | [feedback_lightrag_is_core_asset_no_bypass.md](../../../.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/feedback_lightrag_is_core_asset_no_bypass.md) · CLAUDE.md HARD CONSTRAINT 8 |
| HC-2 | **Vertex embedding 3072-dim is LOCKED.** Switching embedding model = storage rebuild = milestone-scale, NOT v1.1 scope. | [project_aim2_closed_260524.md](../../../.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/project_aim2_closed_260524.md) · LightRAG PyPI vector-dim caveat |
| HC-3 | **`omonigraph` typo is canonical.** Do not "fix" it without a coordinated migration. | CLAUDE.md Lessons Learned · `config.py` |
| HC-4 | **LightRAG 1.4.16 stays unless a phase explicitly upgrades.** No silent version drift mid-milestone. | Pinned in `requirements.txt` |
| HC-5 | **ARAG salvage must preserve cross-milestone API contract.** `omnigraph_search.query.search` is consumed by Hermes — Hermes is frozen RO until 2026-06-22, so the contract MUST NOT break. | [project_agentic_rag_v1_closed_260524.md](../../../.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/project_agentic_rag_v1_closed_260524.md) |
| HC-6 | **Aliyun + Databricks deploy parity required.** Every phase ships to both. | [feedback_aim1_agent_is_operator.md](../../../.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/feedback_aim1_agent_is_operator.md) · [claude_databricks_deployment_autonomous.md](../../../.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/claude_databricks_deployment_autonomous.md) |
| HC-7 | **Hermes is frozen RO until 2026-06-22.** v1.1 cannot touch Hermes-side code, env, or runtime data. | [project_aim2_closed_260524.md](../../../.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/project_aim2_closed_260524.md) |
| HC-8 | **KB Local UAT mandatory** before any phase marked complete. `local_serve.py` + browser session + curl smoke + `<phase>-VERIFICATION.md` evidence. | CLAUDE.md Principle #6 · [feedback_kb_local_uat_mandatory.md](../../../.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/feedback_kb_local_uat_mandatory.md) |
| HC-9 | **Right-Size GSD Ceremony.** Each phase, after Phase 1 DECIDE produces a numeric LoC estimate, picks: ≤5 LoC = direct edit, no GSD; 5–50 LoC = `/gsd:quick`; >50 LoC or multi-subsystem = `/gsd:plan-phase`. Inverse trigger: a `/gsd:quick` that expands past 50 LoC mid-task halts and escalates. | CLAUDE.md Principle #8 |

---

## 7. Out of v1.1 Scope (explicit exclusions)

| # | Out of scope | Why |
|---|---|---|
| OOS-1 | New ingestion features. v1.0 KB ingest is stable; scope unchanged. | v1.1 is query-side; ingestion stability is a stability win to preserve, not extend. |
| OOS-2 | Multi-language entity extraction beyond zh-CN/en. | Corpus is currently bilingual; broader language work is a separate milestone. |
| OOS-3 | Storage rebuild / new embedding model. | Milestone-scale (HC-2). 3072-dim Vertex Gemini embedding stays locked. |
| OOS-4 | Hermes-side changes. | Frozen RO until 2026-06-22 (HC-7). |
| OOS-5 | Switching off LightRAG. | Core asset (HC-1). v1.1 modernizes how we **use** LightRAG, not whether. |
| OOS-6 | Migrating from DeepSeek to a different default LLM provider. | Provider-agnostic compliance is the v1.1 *property*, not a target. arx-3 already proved swap path works; further provider work is post-v1.1. |
| OOS-7 | Major refactor of `kb/` directory layout. | Surgical Changes principle (#3). v1.1 modifies in place; layout refactor is post-v1.1 if ever. |
| OOS-8 | **v1.2-frontend-modernize** — SSG bake complexity (Makefile 4-pass sed flip for lang + brand, `_ssg/` staging subtree, bake-time re-render on content change) is real tech debt but NOT v1.1 retrieval-quality scope. **Park as v1.2 candidate.** Recommended approach: HTMX + FastAPI/Jinja server-render (delete `_ssg/`, runtime lang/brand switch, drop all sed passes); fallback CSR + JSON API. **Trigger:** v1.1 retrieval modernization done + bake complexity remains a development bottleneck. Filed by orchestrator 2026-05-26 after seeing `make deploy` Pass 0/0b/0c/0d in arx-3 Task 4. | Frontend-stack scope, not retrieval-quality scope. |

---

## 8. Memory Reference Index (next-session continuity)

When the next session picks this work up, these memory slugs are load-bearing:

- `feedback_lightrag_is_core_asset_no_bypass` — HC-1 origin
- `feedback_kb_local_uat_mandatory` — HC-8 origin
- `project_agentic_rag_v1_closed_260524` — ARAG REQ list, TEST-05 4/5 unfilled gap
- `project_aim2_closed_260524` — Hermes RO freeze + 3072-dim lock
- `claude_databricks_deployment_autonomous` — Principle #7 deploy ownership
- `feedback_aim1_agent_is_operator` — Aliyun direct-SSH lane for v1.1 deploy
- `databricks_apps_logs_websocket` — `make logs` for Databricks log fetch
- `databricks_sdk_query_no_timeout_kwarg` — SDK v0.108.0 quirk for any Databricks Claude calls
- `corp_pem_rebuild_pattern` — local cert tree health for Vertex calls
- `feedback_pending_symptom_check_dim_first` — debug heuristic if v1.1 storage hydrate flips weird
- `aliyun_oauth_pin` — `/etc/hosts` pin for Vertex token refresh on Aliyun
- `feedback_dont_outsource_ssh` (Principle #5) and `feedback_aim1_agent_is_operator` jointly govern who runs SSH per environment

---

## 9. Phase Sequencing Diagram (text)

```
WAVE 0 ──────────────────────────────────────────────  (blocker)
   ┌── P6.0 body_cleaned schema fix (1-2h quick) ──┐
   └────────────────────────────────────────────────┘
                          │
                          ▼
WAVE 1 ──────────────────────────────────────────────  (parallel)
   ┌── P1 K2 deterministic citation ──┐
   │                                  │
   ├── P5 LR-singleton + async-safety ┤
   └──────────────────────────────────┘
           Aliyun + Databricks deploy parity gate
                          │
                          ▼
WAVE 2 ──────────────────────────────────────────────  (paired)
   ┌── P2-3 BGE-v2-m3 in-process + mix mode ──────┐
   └──────────────────────────────────────────────┘
           Aliyun + Databricks deploy parity gate
                          │
                          ▼
WAVE 3 ──────────────────────────────────────────────  (sequential)
   ┌── P4.0 ARAG audit (read-only, P4-AUDIT.md) ──┐
   │              user approval gate              │
   └── P4.1 ARAG salvage + Deep Research tab ─────┘
           Aliyun + Databricks deploy parity gate
                          │
                          ▼
WAVE 4 ──────────────────────────────────────────────  (housekeeping)
   ┌── P6.1 full fixture drift audit ──┐
   └────────────────────────────────────┘

  P7 (Pydantic mode-arg) — folded into P1 or parked as v1.1.x quick
                          decided at Wave 1 close
```

---

## 10. Open Questions — Resolved (2026-05-26)

| # | Question | Resolution |
|---|---|---|
| Q1 | BGE reranker hosting model | **In-process via `sentence-transformers.CrossEncoder`** at uvicorn startup. Same model on Aliyun + Databricks, identical deploy. Cohere fallback retained ONLY if BGE in-process is fundamentally blocked (privacy concern: Cohere API leaks chunks outside 境内 boundary). Memory ~500MB; pairs with P5 singleton process. |
| Q2 | P5 worker model | **Confirmed single-worker** on both deploy targets. Multi-worker scale-out is v1.2+ scope, NOT v1.1. P5 stub success criteria includes "single-worker uvicorn assumed; multi-worker safety = v1.2 scope". |
| Q3 | P4 ARAG audit scope | **Split P4 into P4.0 (read-only audit producing `P4-AUDIT.md`) → user approval → P4.1 (mutating salvage).** Audit criterion = anything authored as 200k-context-window-era workaround = DELETE candidate. Resolves TEST-05 4/5 root cause (200k-era bug or real regression). |
| Q4 | P6 timing | **Split P6 into P6.0 (body_cleaned schema fix, Wave 0 blocker) and P6.1 (full fixture drift audit, Wave 4).** P6.0 unblocks Wave 1 testing; P6.1 stays last as housekeeping. |

---

## HALT POINT — Phase 1 Revision Complete

ROADMAP.md now reflects all Q1-Q4 answers + Wave 0 blocker + P4 split + P6 split. Proceeding to Phase 2 stub generation per user "go phase 2" directive.
