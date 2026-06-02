# State: v1.1 KB Query Quality

**Milestone:** v1.1-roadmap
**Created:** 2026-05-28
**Current status:** IN-PROGRESS — Wave 0 closed; Wave 1: P5 ✅ CLOSED (2026-05-29); P1 deferred. Wave 2: P2-3 ✅ DEPLOYED-ENABLED via perf-fix-A 2026-05-31; perf-fix-B 📋 CODE-SHIPPED + ALIYUN-DEPLOY-DEFERRED 2026-06-01 (HT-4 systemd drift halt — reconcile follow-up filed)

---

## Phase Status

| Phase | Wave | Status | Notes |
|---|---|---|---|
| P6.0 | 0 | ✅ CLOSED PASS | Wave 0 unblocker — `body_cleaned` schema + fixture drift fix. See chain log `.scratch/v1.1-yolo-chain-close-20260527.log`. |
| P5-verify Branch A | 1 | ✅ CLOSED (commit `6f4ce13`) | Singleton race detected on N=4 concurrent `/api/synthesize`; documented in `docs/quick-260527-swt`. Unblocks P5 plan-phase. |
| P1 | 1 | ⏸ DEFERRED (2026-05-28) | See Note below. |
| P5 | 1 | ✅ CLOSED (2026-05-29) | LightRAG singleton + async-safety. 5 commits `315fa79`..`5867a7d` on `main`; verified on Databricks deployments `01f15aeb`/`01f15af3`. See [P5/P5-VERIFICATION.md](P5/P5-VERIFICATION.md): cold-start mean 28.88s (baseline 30.58s, −5.6%); N=4 async-safety 4/4 topic-match no crosstalk; SC#4 finalize via local pytest (Databricks logz/stream platform-limited). |
| P2-3 | 2 | ✅ DEPLOYED-ENABLED via perf-fix-A 2026-05-31 | BGE-v2-m3 reranker + `mix` mode (paired). 7 P2-3 commits + escape `b4f52c5`. Originally **DEPLOYED-DISABLED** via `BGE_FORCE_LOAD_FAIL=1` (62.59s post-escape mode='hybrid'); reactivated 2026-05-31 evening when `v1.1.P2-3-perf-fix-A` shipped LLM-as-reranker (Databricks Haiku batch JSON). BGE `_build_bge_rerank` removed from `kb/api.py`; LLM rerank dispatcher live at `lib/llm_rerank.py`. SC#1-#6 all PASS on `01f15d1bcce2189db0557d701a97bf9f`. See [P2-3-VERIFICATION.md](P2-3/P2-3-VERIFICATION.md) (escape-era) + [P2-3-perf-fix-A/P2-3-perf-fix-A-VERIFICATION.md](P2-3-perf-fix-A/P2-3-perf-fix-A-VERIFICATION.md) (LLM rerank evidence). |
| P2-3-perf-fix-A | 2 | ✅ CLOSED 2026-05-31 | LLM-as-reranker (Databricks Haiku 4.5 batch JSON) — replaces P2-3 BGE wrapper, eliminates CPU rerank latency root cause that triggered escape. 6 commits `6feb210`..T6 on `main`; deployed `01f15d1bcce2189db0557d701a97bf9f`. **All 6 SC PASS**: SC#1 cold-start `lightrag_singleton_ready wall_s=28.15`; SC#2 qa_seed mean 59.43s (max 65.11s) under 65s ceiling, prod-batch mean 21.07s; SC#3 token-overlap 1.00 perfect coverage on 3 KB-grounded queries (+0.15 vs conservative baseline); SC#4 graceful-degrade verified via accidental old-deploy log emitting `llm_rerank_force_fail`; SC#5 0 touches kb/static+templates; SC#6 legacy `BGE_FORCE_LOAD_FAIL=1` covered by single OR-branch. HT-2 parse_fail observed 1/9 = 11% (under 30% gate). Aliyun parity DEFERRED to phase B (HT-6 N=4 also deferred to B). Actual LoC +428 net (PLAN +258, drift derived from PLAN row table underestimating embedded spec — Z waiver in scope). See [P2-3-perf-fix-A/P2-3-perf-fix-A-VERIFICATION.md](P2-3-perf-fix-A/P2-3-perf-fix-A-VERIFICATION.md). |
| P2-3-perf-fix-B | 2 | 📋 CODE-SHIPPED + ALIYUN-DEPLOY-DEFERRED 2026-06-01 | Aliyun Vertex Gemini batch JSON rerank parity — code shipped, Aliyun deploy halted at HT-4 substantive systemd drift. **5 commits T1-T5 on `main`** (`e01f874` `1fda8bb` `df29852` `cc78c5d` `62fc544`); +154 net LoC. **SC results:** SC#3 (cite-A), SC#4 (lifespan layer + per-request layer), SC#5 (0 kb/static touches), SC#7 (force-fail compat) **PASS**; SC#1-Aliyun, SC#2-Aliyun, SC#6 smoke verification **DEFERRED** to reconcile follow-up. **Tests:** 12/12 unit pass (6 new + 6 A regression); 1/1 deterministic integration test pass (`test_dispatcher_unknown_provider_raises`); 4 lifespan tests skip-graceful per `_start_or_skip` env guard. **HT-4 trigger:** live `/etc/systemd/system/kb-api.service` on Aliyun has substantive drift vs repo template (root-user vs kb-user, `/root` vs `/home/kb` paths, `EnvironmentFile=/root/.hermes/.env` unique to live, no sandboxing block in live, Aliyun-only `OMNIGRAPH_LLM_PROVIDER=deepseek` + `OMNIGRAPH_BASE_DIR` Environment= lines). Pre-flight HT-1/HT-2/HT-3 all PASS (SA JSON present, GOOGLE_CLOUD_PROJECT/LOCATION/CREDENTIALS set in `/root/.hermes/.env`, `/etc/hosts` Vertex pin in place). **No production state mutated** — backup `/etc/systemd/system/kb-api.service.bak-pre-perf-fix-B` taken pre-halt; Aliyun kb-api still on pre-B P5 baseline mode='hybrid'. Available drop-in surface discovered: `/etc/systemd/system/kb-api.service.d/override.conf` already used for Aliyun-specific overrides — recommended target for follow-up. **HC-6 (Aliyun parity gate) NOT-CLOSED.** ISSUES.md row #22 (B itself) annotated; new row #26 files the reconcile follow-up + HT-6 N=4 lock-break verification (transferred from A). See [P2-3-perf-fix-B/P2-3-perf-fix-B-VERIFICATION.md](P2-3-perf-fix-B/P2-3-perf-fix-B-VERIFICATION.md) + [aliyun-evidence/systemd-drift-diff.txt](P2-3-perf-fix-B/aliyun-evidence/systemd-drift-diff.txt). |
| P4.0 | 3 | BLOCKED on Wave 1 + 2 | ARAG audit (read-only). Path locked to **C (self-build)** 2026-05-29 — see Note. |
| P4.1 | 3 | BLOCKED on P4.0 + user approval | ARAG salvage + Deep Research UI. Path **C (self-build)** per P4 path lock. |
| P6.1 | 4 | OPEN | Full fixture drift audit. |
| P7 | side | OPEN — fold-or-park | Pydantic `mode` arg silent-ignore; decide at Wave 1 close. |

---

## Notes

### 2026-05-28 — P1 deferred (orchestrator choice γ)

P1 plan-phase HALTED at Phase 0 grounding on 2026-05-27T21:12Z. Halt log: `.scratch/v1.1-P1-plan-phase-halt-20260527T211244Z.log`.

**Defect:** v1.1 agent's Phase 0 sediment proposed extracting `chunk["full_doc_id"]` from `aquery_llm()` return — but reading `venv/Lib/site-packages/lightrag/{operate,utils}.py` confirmed `full_doc_id` is stripped by `_merge_all_chunks` (operate.py:4001-4053) at construction. User-facing chunks expose only `{reference_id, content, file_path, chunk_id}`. arx-3 §1.7 storage-layer Q1 lock still holds; the defect is in the sediment's storage→API mapping assumption.

**Three options surfaced (in halt log):**

- α — Two-step `aquery_llm + rag.text_chunks.get_by_ids(chunk_ids)` to recover full_doc_id from KV. ~+14 LoC vs sediment (73→87 total). Still plan-phase tier.
- β — LightRAG SDK fork PR adding `full_doc_id` to `_merge_all_chunks` + `convert_to_user_format`. ~6-line patch upstream; SDK fork maintenance cost.
- γ — Defer P1; advance Wave 1's P5 instead.

**Decision (2026-05-28, orchestrator):** **γ chosen.**

Rationale (orchestrator):

- P1 引用准确度问题用户尚未抱怨,不阻塞
- P5 cold-start 60–350s → <30s 是当前最大 ROI (本地 UAT 每次都受益)
- P5-verify Branch A 已 close (`6f4ce13`), unblocked
- Wave 1 内 P5 跟 P1 是并行 phase,切换无冲突

**Revisit trigger:** after P5 ships, OR earlier if user citation-accuracy 抱怨触发. α/β decision deferred to that point — fresh SDK 一手数据 (e.g., LightRAG version pin at P5-ship time, any upstream PRs landing for full_doc_id propagation) will inform the choice.

**Preserved artifacts (do NOT delete):**

- `P1-stub.md` (unchanged)
- `.scratch/v1.1-P1-plan-phase-halt-20260527T211244Z.log`
- `.scratch/v1.1-yolo-p1-decide-20260527T233223Z.log` (v1.1 agent sediment)
- `.scratch/v1.1-yolo-chain-close-20260527.log` (Wave 0+1 chain closure)

---

### 2026-05-29 — P4 path locked to C (self-build), MS ai-agents-for-beginners evaluated

User flagged Microsoft's open-source agentic-RAG release ([microsoft/ai-agents-for-beginners](https://github.com/microsoft/ai-agents-for-beginners), lesson 05-agentic-rag, 65919 stars) as potential fork target to replace v1.1 P4 self-build. Background research agent dispatched 2026-05-29 03:30 UTC (task `a14cdb53f569fc8d1`).

**Conclusion: walk path C (self-build per existing ROADMAP). Match score 1/5.**

| Capability | We need | MS provides | Match |
| --- | --- | --- | --- |
| Reasoner (KG agent loop) | LightRAG hybrid + vision_analyze | tool-call on in-memory dict | ✗ |
| Synthesizer (LLM compose + CJK + image embed) | 5-stage pipeline | `print(response)` | ✗ |
| Deep Research UI | frontend tab + `/api/research` wire | none | ✗ |
| LightRAG backend | 1.4.16 + `omnigraph_search.query.search` | Azure AI Search | ✗ |
| DeepSeek/Vertex provider | `cfg.llm_complete` abstraction | Azure OpenAI hard-bound | ✗ |

**Why C, not A (fork):**

- MS repo is a **12-cell Jupyter teaching demo**, not a framework. 05-agentic-rag total ~50 lines of substantive Python in a single `.ipynb`; main artifact is the .NET sample (33 KB).
- **Azure-locked**: `AzureCliCredential` + `agent-framework` SDK + `AZURE_AI_PROJECT_ENDPOINT` mandatory; no DeepSeek/Vertex/Gemini path. EDC corp Cisco Umbrella TLS interception adds further migration cost.
- **Zero KG adaptation**: teaching version uses 4-line dict, production guidance points to Azure AI Search. LightRAG / graphml / hybrid mode is outside MS scope.
- **We are already ahead**: `lib/research/stages/{reasoner,verifier}.py` bounded agent loop + `cfg.llm_complete` abstraction + tool-dispatch is more production-grade than the MS lesson. ar-1 closed 2026-05-24 with 41/41 REQs and 165 tests; A path = throw away closed work to rebuild on Azure-locked SDK = negative ROI.

**Why not B (借鉴) either, beyond a citation:**

- Maker-checker / iterative retrieval **concept** does match our Reasoner+Verifier, but `verifier.py:1-30` already implements bounded agent loop. Borrowing prompt templates ≈ ~50 LoC marginal value with no architectural change.

**P4.0 audit treatment:**

- Cite this evaluation in `P4-AUDIT.md` rationale section (no code import, no dependency add)
- Future fork-target search direction: `LightRAG agentic` / `GraphRAG agent` / `kotaemon` — production frameworks, not teaching repos. Filed for next ARAG research cycle if/when path C delivery hits a wall.

**Cross-reference:** `MEMORY.md` → `feedback_repo_evaluation_stars_vs_substance.md` (evergreen lesson on fork-target screening).

**Preserved artifacts:**

- Research agent transcript: task ID `a14cdb53f569fc8d1` (2026-05-29 03:30 UTC, Sonnet 4.6)

---

## Cross-References

- **Roadmap:** `ROADMAP.md` (Wave structure, LoC budget, mainstream alignment scores)
- **Research:** `RESEARCH.md` (10 sections, 25 references, P1 confidence ⭐⭐⭐⭐⭐)
- **P5 Branch A:** `docs/quick-260527-swt/` + commit `6f4ce13`
- **P5 plan-phase artifacts:** `P5/PLAN.md` + `P5/RESEARCH.md` (commit `de36db9`)
- **P5 verification:** `P5/P5-VERIFICATION.md` (Track 1-4 evidence on Databricks deployments `01f15aeb`/`01f15af3`)
- **Bug 2c context (closed 2026-05-26):** `.planning/phases/arx-3/DECISION.md` §1.7 (Q1 lock — vdb_chunks.json full_doc_id 1967/1967)
