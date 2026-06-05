# State: v1.1 KB Query Quality

**Milestone:** v1.1-roadmap
**Created:** 2026-05-28
**Current status:** IN-PROGRESS — Wave 0 closed; Wave 1: P5 ✅ CLOSED (2026-05-29); P1 deferred (PARKED v1.2 2026-06-01 — overtaken by client-side qa.js sweep). Wave 2: P2-3 ✅ DEPLOYED-ENABLED via perf-fix-A 2026-05-31; perf-fix-B 📋 CODE-SHIPPED + ALIYUN-DEPLOY-DEFERRED 2026-06-01 (HT-4 systemd drift halt → folded into qdrant-migration). **qdrant-migration phase (P0) ✅ CLOSED 2026-06-05** — Wave 1 ✅ Wave 2 ✅ Wave 3 ✅ (Aliyun in-place 5/30-archive transplant + v3 orjson 287s rels fire; final state chunks 3294 / ents 51632 / rels 71773) Wave 4 ✅ (T10 N=4 lock-break PASS, T11 hydrate ×3 PASS mean 13.1s, HC-6 dual-station rerank parity verified; T12 converter+systemd defects fixed via `4d5e6ef` + `56a4112`).

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
| P2-3-perf-fix-B | 2 | 📋 CODE-SHIPPED + ALIYUN-DEPLOY-DEFERRED 2026-06-01 (FOLDED into qdrant-migration #25 as of 2026-06-01) | Aliyun Vertex Gemini batch JSON rerank parity — code shipped, Aliyun deploy halted at HT-4 substantive systemd drift. **5 commits T1-T5 on `main`** (`e01f874` `1fda8bb` `df29852` `cc78c5d` `62fc544`); +154 net LoC. **SC results:** SC#3 (cite-A), SC#4 (lifespan layer + per-request layer), SC#5 (0 kb/static touches), SC#7 (force-fail compat) **PASS**; SC#1-Aliyun, SC#2-Aliyun, SC#6 smoke verification **DEFERRED** — 2026-06-01 orchestrator decision FOLDED reconcile work into qdrant-migration phase (Wave 2 T7 single restart ships Qdrant cutover + rerank env + structural hydrate fix together, minimizing #27 hydrate-throttle blast radius). HT-6 N=4 lock-break verification transferred A→B→#26→qdrant-migration Wave 4 T10. **Tests:** 12/12 unit pass; 1/1 deterministic integration pass; 4 lifespan tests skip-graceful. No standalone reconcile phase will run — see qdrant-migration row below. ISSUES.md row #22 + #26 annotated. See [P2-3-perf-fix-B/P2-3-perf-fix-B-VERIFICATION.md](P2-3-perf-fix-B/P2-3-perf-fix-B-VERIFICATION.md). |
| qdrant-migration | 2 | ✅ CLOSED 2026-06-05 | Aliyun ingest OOM structural fix + Aliyun rerank parity (folded #26 from perf-fix-B) + #27 hydrate throttle structural fix. **ISSUES.md #25 #26 #27 #22 RESOLVED** (R24-R27). PR #4 `ops/qdrant-migration` extended via plan-phase. **Wave 1 ✅ CLOSED 2026-06-01** (6 commits `8a9abf3` T1 env-driven vector_storage 3 sites + `a3b08eb` T2 converter + roundtrip test + `b015dbd` T3 systemd snapshot timer + override.conf examples + reingest wrapper + `dceaec3` T4 N=4 lock-break test + `400e97f`/`36ed5ad` 2 frontmatter LoC patches; +781 LoC code/config vs PLAN +443; HT-* 0 fired; details in [qdrant-migration/PLAN.md](qdrant-migration/PLAN.md) drift log). **Wave 2 ✅ CLOSED 2026-06-02** (T5/T6/T7/T8 Aliyun ssh ops; Qdrant docker run :6333; override.conf 11→13 lines; kb-api hydrate `wall_s=15.18` ← 14min historical = 55× faster; first snapshot 3 valid empty NanoVDB JSONs; `qdrant-snapshot.timer` enabled; 2 PLAN-defect repo-syncs `0cd7a0b` T2 graceful-empty + `18903ca` defect A QDRANT_URL env). **Wave 3 ✅ REAL CLOSE 2026-06-05** (truth-vs-T9 reconciliation — original T9 FAILED 06-02 was wrapper self-exit at 6h11min on fresh-ingest path through stale Vertex/RPD; the **real successful path** was Aliyun in-place 2026-05-30 archive transplant fired 06-05 by orchestrator delegate: chunks ✅ + ents ✅ in 5min, rels v1 ijson stuck → v3 orjson 287s → 45839 imported, final state chunks **3294** / ents **51632** / rels **71773** including 5/30 archive + 5/30-6/5 cron incremental). **Wave 4 ✅ CLOSED 2026-06-05** (T10 N=4 lock-break PASS — pytest exit-1 was test artifact `s.get("markdown")` reading top-level instead of `result.markdown`, but lock contract verified by serialized wall_s {40.94/68.5/147.81/154.3} + 4 distinct response bodies + DEEPSEEK marker in answer; T11 hydrate ×3 PASS {13.77/12.73/12.85}s mean 13.1s well under 30s gate; HC-6 dual-station rerank parity — Aliyun fresh-verify `provider=vertex_gemini` ×3 + Databricks Haiku already verified per perf-fix-A; T12 converter + systemd defects fixed today: `4d5e6ef` T2 NAMESPACE_TO_QDRANT_COLLECTION map missed LightRAG `_gemini_embedding_2_3072d` suffix → 49-byte placeholder, `56a4112` T8 systemd `TimeoutStartSec=600`→`1800` because relationships dump alone needs ~5-8min on 71773 points; orchestrator-triggered snapshot.service produced real 3-collection dump verifying T12). **Hermes detour postmortem:** initial fresh-ingest T9 path burned 4h scp-back-and-forth (2026-05-30 archive Aliyun → Hermes → Aliyun); the right path was always Aliyun in-place. Lesson: distinguish "transplant existing" from "re-fresh-ingest"; ISSUES #34 captures. See [qdrant-migration/PLAN.md](qdrant-migration/PLAN.md) + `aliyun-evidence/` (n4-lock-break.log + hydrate-3-restarts.log + aliyun-rerank-evidence.log + databricks-rerank-evidence.log). |
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

### 2026-06-01 — qdrant-migration phase (P0) folded #25 + #26 + #27 structural fix

ISSUES.md #25 (Aliyun all-in-one + LightRAG nano-vectordb full-load = OOM root cause) promoted P3→P0 per orchestrator decision; #26 (perf-fix-B reconcile follow-up) FOLDED into #25 acceptance criteria (rerank env block + HT-6 N=4 verification); structural fix path for #27 (kb-api restart triggers ~8min Aliyun public network throttle, hydrate 56min) also folded — single Aliyun kb-api restart at Wave 2 T7 ships all 3 changes together, minimizing #27 hydrate-throttle blast radius vs running 3 separate restarts. Cross-station design decision LOCKED to **Path 2 (Aliyun dual-write — Qdrant + nano-vectordb JSON snapshot, cron 6h regenerates vdb_*.json for Databricks/Hermes consumption)** per [.planning/quick/260601-qdrant-research/RESEARCH.md](../../quick/260601-qdrant-research/RESEARCH.md) — Path 1 (LightRAG QdrantVectorDBStorage local file mode) BLOCKED by hardcoded `url=` parameter + qdrant-client SQLite single-writer lock incompatible with Aliyun multi-process layout; Path 3 (Databricks HTTP → Aliyun Qdrant) rejected for cross-border RTT 150-200ms × N chunks + 18min Aliyun public throttle reproduces Path 1 outage on Databricks long_form. Wave 1+2 evidence shipped 2026-06-01/02, Wave 3 failure 2026-06-02 02:12 ADT post-mortem ongoing.

---

### 2026-06-01 — Wave 2 hydrate measurement: SC#9 already 1/3 PASS (15.18s vs 14min historical)

Wave 2 T7 cutover restart measured `lightrag_singleton_ready wall_s=15.18` against historical 14min full nano-vectordb load — **55× faster**, well under SC#9 ≤30s ceiling. This is the structural close of #27 hydrate throttle (Qdrant mmap eliminates Python heap full-vdb load). Wave 4 T11 will measure 2 more restarts to formally close SC#9 (PLAN spec requires N=3 measurement series). PLAN frontmatter LoC band patched twice during Wave 1 execution (390-430 → 570-750 → 700-900) per drift log section in PLAN.md, honoring transparency-over-silent-debt precedent set in `400e97f`.

---

### 2026-06-01 — long_form UI fix series shipped 11 qa.js commits + 2 ISSUES docs

Parallel to Wave 1+2 execution, separate fix series shipped client-side qa.js sanitizer for LLM-emitted citation orphans + References dedupe + dead-link demotion. Series: `a71741f` (path) → `df0c87d` (orphan + img) → `0eb3603` (title labels) → `c71e66b` (dead-link sanitize) → `6d692c2` (bold-heading + img remove) → `146b16e` (score-based dedupe) → `6af0735` (widen orphan regex) → `8342d3d` (end-anchored href) → `2157a20` (strip ALL LLM References) → `2eb7290` (truncate verbose labels) → `d5113c6` (bare brackets to markdown link). Plus `ecd2076` server-side prompt template tightening. Single kb-api restart total (just `ecd2076`); subsequent 10 commits hot-patch via Caddy static swap, zero hydrate disruption. ISSUES.md #28 (DeepSeek image-emit gap, downgraded P1→P2 after user counter-example screenshot proved capability exists, intermittent NOT systematic) + #29 (server-side citation rewrite carry-over) filed for follow-up. P1 K2 (ROADMAP §5 SC#1 deterministic citation) PARKED v1.2 — overtaken by client-side sweep covering ~80% of P1 K2 promised value; user has not raised citation accuracy as a complaint.

---

## Cross-References

- **Roadmap:** `ROADMAP.md` (Wave structure, LoC budget, mainstream alignment scores)
- **Research:** `RESEARCH.md` (10 sections, 25 references, P1 confidence ⭐⭐⭐⭐⭐)
- **P5 Branch A:** `docs/quick-260527-swt/` + commit `6f4ce13`
- **P5 plan-phase artifacts:** `P5/PLAN.md` + `P5/RESEARCH.md` (commit `de36db9`)
- **P5 verification:** `P5/P5-VERIFICATION.md` (Track 1-4 evidence on Databricks deployments `01f15aeb`/`01f15af3`)
- **Bug 2c context (closed 2026-05-26):** `.planning/phases/arx-3/DECISION.md` §1.7 (Q1 lock — vdb_chunks.json full_doc_id 1967/1967)
- **qdrant-migration plan-phase artifacts:** `qdrant-migration/PLAN.md` (commit `d0d82b1` + revise `21bc69a`) + `.planning/quick/260601-qdrant-research/RESEARCH.md` (untracked, queued for commit)
- **qdrant-migration Wave 1 commits:** `8a9abf3` `a3b08eb` `b015dbd` `400e97f` `dceaec3` `36ed5ad`
- **qdrant-migration Wave 2 commits:** `0cd7a0b` (T2 graceful-empty fix) + `18903ca` (defect A repo sync) — Aliyun ssh ops T5/T6/T7/T8 are state mutations, no commit
- **qdrant-migration Wave 3 evidence (pending commit):** `.scratch/wave3-postmortem-260602.md` (post-mortem agent in flight) + Aliyun journal references
- **ISSUES.md row #25 (P0 Aliyun OOM root + folded #26 #27):** `.planning/ISSUES.md`
- **long_form UI fix series:** commits `ecd2076` `a71741f` `df0c87d` `0eb3603` `c71e66b` `6d692c2` `146b16e` `6af0735` `8342d3d` `2157a20` `2eb7290` `d5113c6` (server-side prompt + 11 client-side qa.js); ISSUES.md #28 #29 filed
