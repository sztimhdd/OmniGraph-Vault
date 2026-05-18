# ARCHITECTURE-AUDIT-Ingest-Pipeline-v1

> **Audit target:** `.planning/ARCHITECTURE-ANALYSIS-Ingest-Pipeline-v1.md` (519 lines, 2026-05-17)
> **Audit type:** Adversarial — verify each claim against actual code, push back where the doc overstates
> **Auditor:** architect agent (independent, code-evidence only)
> **Audit date:** 2026-05-17

---

## Verdict (TL;DR)

The analysis doc is **directionally interesting but substantially overstates** the architectural sickness.

| Defect | Doc claims | Audit finding |
|---|---|---|
| 1. Monolith / 402 kills batch | Cascading abort | **DISPUTED** — per-article try/except at `batch_ingest_from_spider.py:428` already isolates failures; one bad article never kills the batch |
| 2. No backpressure | 99% candidates discarded as waste | **PARTIAL** — Layer 1 verdict caching + checkpoint skip already filter most of the "discarded" rows; only MAX_ARTICLES is a real cap |
| 3. Dual-write inconsistency | 106 mystery rows | **VERIFIED symptom, DISPUTED fix** — real issue at 0.5% rate; bidirectional reconcile is the right fix, not making `doc_status` SoT |
| 4. Tight coupling | All APIs share retry/timeout/handler | **PARTIAL** — each provider already has own timeout / retry / circuit-breaker; only per-article sequencing is coupled |
| 5. Batch-only / no incremental | Re-classify 219/day | **DISPUTED** — Layer 1 caches verdicts under `layer1_prompt_version`; only re-runs on prompt bump (`batch_ingest_from_spider.py:1514-1516, 1535-1537`) |

**Verdict on the proposed 5-day rewrite:** **Disproportionate.** Three of five defects don't survive a code reading; the proposed target architecture has unaddressed design problems (in-process LightRAG cross-process locking, capacity math wrong, removing MAX_ARTICLES is a SiliconFlow cost regression, breaking `skip_reason_version` cohort gate). Project gravity has shifted to kb-v2.x / kdb / agentic-rag-v1 — ingest is in v1.0 stable maintenance mode. Spending 5 engineer-days on a stable subsystem during active product expansion is the wrong allocation.

**Recommendation:** **Do not do the 5-day migration.** Ship 2-3 surgical patches in ~1 day (detail in §3 below).

---

## 1. Per-defect findings

### Defect 1 — Monolith / "402 kills entire batch"

**Status: DISPUTED**

**Code evidence:**
- `batch_ingest_from_spider.py:428-432` — top-level per-article `try/except Exception` wraps `ingest_article`; on any failure (including DeepSeek 402 RuntimeError) it logs "Ingest failed" and the loop continues to the next article. Returns `(False, wall, False)`, not a raise.
- `batch_ingest_from_spider.py:931-944` — the batch loop accepts `success/wall/doc_confirmed`, writes `status='failed'` to summary, then continues. It does NOT abort.
- `batch_ingest_from_spider.py:354-358` docstring explicitly says: "Per-article try/except isolates failures — one bad article never kills the batch."
- `lib/llm_deepseek.py:56-63` raises `RuntimeError` only on missing key. There is no global "DeepSeek 402 → process exit" path.

**Where the doc gets it wrong:** §2 Defect 1's cascade diagram ("402 → Classify fails → Extract fails → Image Vision succeeds → Merge fails → ENTIRE BATCH ABORTED") is fictional. In actual code:
1. A 402 from DeepSeek raises inside `ingest_wechat.ingest_article`
2. The outer `await ingest_article(...)` (line 394-397) catches it via the except at 428
3. Marks that single article failed and continues

The doc also conflates **batch-level Layer 1 classify** (which DOES happen for a slice of articles via `layer1_pre_filter` — a 402 here would short-circuit Layer 1 work for that batch slice) with **per-article entity extraction inside `ingest_article`** (which is fully isolated). Within a single article, a 402 mid-LightRAG-extract DOES kill that one article's downstream image-vision because they run sequentially inside the same async coroutine — but this is *per-article* coupling, not "all stages in same process".

**Severity (May 2026): LOW.** No documented production incident matches the cascade scenario. Memory `project_v1_0_x_closure_260516.md` confirms v1.0.x closed stable with surgical fixes only.

**Blocks current work?** No. Current work (kb-v2.x, kdb, agentic-rag) does not touch ingest decomposition.

---

### Defect 2 — Push model / no backpressure

**Status: PARTIAL**

**Code evidence:**
- `batch_ingest_from_spider.py:1496-1539` — candidate SELECT uses `NOT IN (SELECT article_id FROM ingestions WHERE status='ok' OR (status='skipped' AND skip_reason_version=?))` AND `layer1_verdict IS NULL OR layer1_prompt_version IS NOT ? OR layer1_verdict='candidate'`. So "99% of candidates discarded daily" is misleading — most rows are already filtered out at SQL level before MAX_ARTICLES sees them.
- `batch_ingest_from_spider.py:903-915` — `has_stage(ckpt_hash, "text_ingest")` checkpoint skip prevents re-ingesting articles already done.
- `MAX_ARTICLES` cap is real but not the only flow control — `total_batch_budget` (BTIMEOUT-01..04 from Phase 17) provides per-batch timeout-based termination.

**Where the doc gets it wrong:** "99% discarded each day" mixes three populations: (a) Layer 1 rejects (correctly filtered as off-topic), (b) checkpoint skips (already ingested — that's correctness, not waste), and (c) MAX_ARTICLES cap. Only (c) is a true throughput cap; (a) and (b) are deliberate filtering. The metric table at §1.3 lacks columns to disambiguate, which inflates the "waste" narrative.

**Severity: LOW-MEDIUM.** Throughput is genuinely ~3-7/day per cron, but this is partly intentional (image-heavy articles use 1170s budget per memory `project_t1_b1_validated_260513.md`). New article volume per day is also small relative to candidate pool. No production complaint about throughput backlog.

**Blocks current work?** No. kb-v2.x / kdb don't depend on ingest throughput.

---

### Defect 3 — Dual-write inconsistency

**Status: VERIFIED (symptom) but DISPUTED on the proposed fix**

**Code evidence:**
- `ingest_wechat.py:77-199` — `_verify_doc_processed_or_raise` (commit `949e3f4`) is the bridge between LightRAG async pipeline and `ingestions` table. Quick `260511-lmc` added stable-state re-poll (Option A) and error_msg guard (Option B).
- 7 INSERT sites in `batch_ingest_from_spider.py` (1681, 1806, 1879, 1929, 1941, 1959, 1983) all write to `ingestions`. The hot path (success ack) lives in the main loop.
- Memory `project_ghost_success_observed_260514.md`: production ghost-success rate **0.5%** (1/188), not "106 mystery rows in 10 days" with no comparison baseline. Memory `project_v1_0_x_closure_260516.md` confirms 5 ghost successes were reconciled and the two-layer timeout fix shipped (commits `bd67f06`, `4eaef45`).

**Where the doc gets it wrong:** The 106 figure is contextless — out of how many ingestions over the same window? Memory says rate is ~0.5%. The proposal to make LightRAG `doc_status` "the single source of truth" misunderstands the design:
- `ingestions` carries the **SQLite-side workflow state** — `status='skipped'` for Layer 1/2 rejects, `'failed'` for hard errors, retry tracking via `skip_reason_version`
- LightRAG `doc_status` only knows "is this doc in the graph?" — it has no concept of "we decided to skip this for off-topic reasons" or "scrape failed before we got to LightRAG"

Making `doc_status` the SoT and turning `ingestions` into a derived view would require LightRAG to learn workflow semantics it doesn't have. The correct fix (already partially shipped) is **bidirectional reconcile** + tightening `_verify_doc_processed_or_raise` budget.

**Severity: MEDIUM (live, but under control).** Memory `project_v1_0_x_closure_260516.md` notes reconcile bidirectional scope extension is queued for v1.0.y. `OMNIGRAPH_PROCESSED_RETRY=300` (600s budget) deployed.

**Blocks current work?** No. Ghost successes don't affect KB site or Databricks app deploy.

---

### Defect 4 — Tight coupling

**Status: PARTIAL**

**Code evidence:**
- `lib/llm_deepseek.py:74-99` — DeepSeek has its own `OMNIGRAPH_DEEPSEEK_TIMEOUT` (300s default), separate `AsyncOpenAI` client with own timeout.
- `lib/lightrag_embedding.py:212-235` — Vertex embedding has its own RuntimeError handling and key rotation.
- `lib/vision_cascade.py` (per Phase 13) — Vision has its own cascade + circuit breaker independent of LLM.

**Where the doc gets it wrong:** §2 Defect 4's table claims "all share same retry/timeout/error handler" with current handling shown as "Retry 3x in-process". This is fictional. Each provider already has:
- Own timeout (DeepSeek 300s, vision 30s/image, embedding worker 180s after `260517-lok`)
- Own retry strategy (DeepSeek tenacity, Vision cascade with 3-failure circuit breaker, Embedding key rotation)
- Own error classification (vision cascade falls through on 429; DeepSeek raises; embedding rotates keys)

What IS coupled: per-article sequential execution. A DeepSeek hang inside `ingest_article` does block that one article's image vision (because they run sequentially in one async coroutine). But that's per-article, not "all stages in same process".

**Severity: LOW.** No production incident matches the doc's failure scenario.

**Blocks current work?** No.

---

### Defect 5 — Batch-only / no incremental model

**Status: DISPUTED — defect already addressed**

**Code evidence:**
- `lib/article_filter.py:762-806` — `persist_layer1_verdicts` writes `layer1_verdict / layer1_reason / layer1_at / layer1_prompt_version` columns to `articles`. Already-classified articles are NOT re-classified.
- `batch_ingest_from_spider.py:1514-1516` and `1535-1537` — candidate SELECT predicate: `WHERE a.layer1_verdict IS NULL OR a.layer1_prompt_version IS NOT ? OR a.layer1_verdict = 'candidate'`. Translation: skip any row where Layer 1 already evaluated under the current prompt version and it's not a candidate. The "LF-1.8 prompt-version bump" is the incremental cache invalidation mechanism.
- `batch_ingest_from_spider.py:907-908` — `has_stage(ckpt_hash, "text_ingest")` checkpoint skip.
- `batch_ingest_from_spider.py:1507-1513` — anti-join on `ingestions WHERE status='ok' OR (status='skipped' AND skip_reason_version=?)`.

**Where the doc gets it wrong:** Just plain wrong. The claim "Every day at 09:00, the pipeline loads ALL articles from SQLite, re-classifies them all" is factually false. Layer 1 verdicts are cached per prompt version; re-classification only happens when `PROMPT_VERSION_LAYER1` is bumped (a deliberate cache invalidation). The diagram "DAY N+1: Load 219 → Classify 219 → Ingest 5 → Discard 214" doesn't match how the SQL works.

The "1095 wasted DeepSeek calls" math is fictional unless the prompt has been bumped 5 times in 5 days, which it hasn't.

**Severity: LOW (non-issue).**

**Blocks current work?** No.

---

## 2. Issues with the proposed target architecture

The doc's §3 "Target Architecture" has unaddressed design problems:

### 2.1 In-process LightRAG cross-process collision

§3.1 and §3.6 propose 4 independent worker subprocesses (Classify / Extract / Image / Merge). LightRAG storages (`kv_store_doc_status.json`, `vdb_entities.json`, GraphML, NanoVectorDB) are file-backed and NOT designed for cross-process concurrent writes. Memory `project_t1_b1_validated_260513.md` and the `_drain_vision_tasks` mechanism assume one in-process LightRAG instance.

The proposal would require either:
- (a) a process-level lock — serializes the workers, defeating the parallelism goal
- (b) a network-fronted LightRAG server — massive scope creep
- (c) per-stage storage shards — breaks queryability of the single graph

The doc proposes none of these.

### 2.2 Capacity math is wrong

§3.6: "5 articles/tick × 6 ticks/hour × 24 hours = 720 articles/day".

Per memory `project_t1_b1_validated_260513.md`, image-heavy articles use 1170s budget. Per CLAUDE.md "v1.0.x patches" T1 entry, a 51-image article hit 900s. One tick (10 min = 600s) cannot finish even 1 such article, much less 5.

The tick math also ignores that 4 stages multiply elapsed time per article (Classify + Extract + Image + Merge). Real ceiling is closer to 30-50 articles/day if all stages pipeline cleanly — almost identical to today's saturation point on ~3-7 articles/day.

### 2.3 `ingestions`-as-derived-view breaks `skip_reason_version` semantics

§3.3 claims `ingestions` becomes `SELECT article_id, MAX(doc_status.status) FROM lightrag_doc_status GROUP BY article_id`. But `ingestions` carries `status='skipped'` for Layer 1 / Layer 2 rejects (articles that NEVER enter LightRAG and have no `doc_status` row). Quick `260509-s29` Wave 2's `skip_reason_version` cohort gate (`batch_ingest_from_spider.py:1511-1512`) depends on this. The proposal silently breaks reject-cohort retry.

### 2.4 Pull-model "no MAX_ARTICLES needed" ignores cost ceiling

§3.5 claims backpressure from queue depth replaces MAX_ARTICLES. But MAX_ARTICLES today is also a SiliconFlow ¥-budget governor and a Vertex AI embedding RPM governor. Removing it without an explicit per-day cost budget is a regression — see CLAUDE.md "SiliconFlow Balance Management" section.

### 2.5 §4 risk labels minimize migration cost

"Phase 1: Risk Low. Logic unchanged." Splitting a 2188-line file into 5 worker scripts AND introducing a scheduler IS a large refactor regardless of whether per-line semantics are preserved. The state-machine migration in Phase 2 has to handle 106+ in-flight rows that sit between two state stores; that's not "Risk Medium", that's the hardest single piece of the proposal.

### 2.6 "564 commits" data basis only roughly verifiable

Actual count: `git log --since=2026-05-01 --until=2026-05-16 | wc -l = 539` repo-wide. Within ~5% of the doc's claim, so not implausible — but the doc never sources the figure. The "12 cron run logs" figure also isn't sourced.

---

## 3. Recommendation: 3 surgical patches in ~1 day, NOT a 5-day rewrite

Three reasons not to do the 5-day migration:

1. **Project gravity is elsewhere.** `STATE.md` shows current focus is `kdb-1.5` (Databricks adapter) + KB-v2 (kb-3 in progress, kb-4 queued) + agentic-rag-v1. Ingest is in v1.0 stable maintenance mode. Spending 5 engineer-days on a stable subsystem during active product expansion is the wrong allocation.

2. **Three of five defects don't survive code reading.** Defects 1, 4, 5 are factually contradicted by current code. Defect 2 is partially mitigated by Layer 1 caching + checkpoint skip. Only Defect 3 is a live, measured issue — and at 0.5% rate.

3. **Surgical patches solve the real bits.** Concretely:

### Patch 1 — Bidirectional reconcile (½ day) — addresses real Defect 3
- Already queued for v1.0.y per memory `project_v1_0_x_closure_260516.md`
- Scope: extend reconcile from `ingestions.status='ok' → doc_status.processed` (current) to also catch `ingestions.status='failed' AND doc_status.processed` (ghost success) and `ingestions.status='ok' AND doc_status.pending|failed` (ghost failure)
- Surfaces both directions; closes Defect 3 properly without re-platforming

### Patch 2 — DeepSeek 402 graceful degrade (¼ day) — addresses real fragment of Defect 1
- Add `try/except RuntimeError` around DeepSeek calls inside `ingest_wechat.ingest_article` such that a 402 in entity extraction degrades to "text-only ingest, no entities" rather than failing the whole article
- Closes the legitimate per-article failure-mode-coupling complaint inside Defect 1 without splitting the process

### Patch 3 — Document MAX_ARTICLES as cost-governor (¼ day)
- CLAUDE.md update: clarify that MAX_ARTICLES serves both throughput AND SiliconFlow cost AND Vertex RPM governance
- If/when ingest volume grows, promote to per-stage cost budgets — not now

### When to revisit the full rewrite

If at some future point ingest volume genuinely justifies decomposition (e.g., 100+ articles/day sustained, or LightRAG migrates to a network-fronted backend that resolves the in-process lock issue), revisit this analysis — but with a more honest defect inventory and a capacity model that accounts for image-heavy articles.

---

## 4. Cross-references

- Original analysis: `.planning/ARCHITECTURE-ANALYSIS-Ingest-Pipeline-v1.md`
- v1.0 stability: `CLAUDE.md` § "Release Status"; memory `project_v1_0_final_declared_260513.md`, `project_v1_0_x_closure_260516.md`
- Ghost-success rate: memory `project_ghost_success_observed_260514.md`
- Image-heavy budget: memory `project_t1_b1_validated_260513.md`
- Active phases: `.planning/STATE.md`, `.planning/ROADMAP.md`
- Key code paths: `batch_ingest_from_spider.py:428` (per-article isolation), `:1514-1516` + `:1535-1537` (Layer 1 verdict caching), `lib/llm_deepseek.py:74-99` (DeepSeek own timeout), `lib/article_filter.py:762-806` (verdict persistence)
