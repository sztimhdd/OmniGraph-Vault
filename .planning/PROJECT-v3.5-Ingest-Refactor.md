# OmniGraph-Vault — Milestone: v3.5-Ingest-Refactor

> Sibling milestone running parallel to v3.4 (RSS-KOL Alignment, Phases 20-22)
> and Agentic-RAG-v1. Main project context lives in `PROJECT.md`. This file
> scopes v3.5-Ingest-Refactor only. Phase directories use the `ir-N-*` prefix
> to avoid collision with v3.4 (19-22) and Agentic-RAG-v1 (`ar-N`).

## What This Milestone Is

Replace the current 4-LLM-gate classify pipeline (independent classify cron
writing rows to `classifications`, then ingest cron filtering off those rows)
with **runtime-decision two-layer LLM filtering inside the ingest run itself**.
No standalone classify cron. No metadata persistence as a separate stage.
Each ingest run decides what to scrape (Layer 1) and what to ainsert (Layer 2)
on the fly using small per-batch LLM calls; verdicts are persisted on the
source tables (`articles` + `rss_articles`) for re-use.

**Trigger:** 2026-05-07 06:00–09:00 ADT cron disaster — Quick 260506-se5
(`c786a83`) added a single-column UNIQUE on `classifications.article_id` and
switched INSERT to `ON CONFLICT(article_id) DO UPDATE SET topic=excluded.topic`.
Each cron iteration of the existing 5-topic loop overwrote the prior iteration's
topic field; the last-written topic ('CV') won and all 653 rows ended up
`topic='CV'`. Downstream ingest cron filtered on `agent,hermes,openclaw,harness`
→ zero candidates → zero ingest. Hot-fix `428b16f` reverted to the multi-row
`ON CONFLICT(article_id, topic)` pattern, but the underlying architecture is
fragile by design: state lives in two tables across two cron processes, and any
schema change requires reasoning about both. Replacing it with single-process
runtime filtering is the structural fix. Postmortem in
[`260507-ent-SUMMARY.md`](quick/260507-ent-cron-mass-classify-cv-bug-revert-upsert-/260507-ent-SUMMARY.md).

**Locked design references:**

- `.planning/PROJECT-Ingest-Refactor-v3.5.md` — earlier research artifact (Hermes
  authored 2026-05-07 morning; portions superseded by 6 D-decisions below but
  retained as design context)
- `.planning/MILESTONE_v3.5_CANDIDATES.md` § Section 1 — fragility inventory
  + 4-stage idealized flow that motivates this redesign
- `.scratch/layer1-validation-20260507-151608.md` — Layer 1 v0 prompt validated
  on 30 random articles (15 WeChat + 15 RSS): 21 reject / 9 candidate / 0 误杀 /
  0 漏放, 8.0s wall-clock, gemini-3.1-flash-lite-preview

## Goal

A `lib/article_filter.py` module + ingest-loop wiring that takes a batch of
unscraped articles and returns the subset worth scraping (Layer 1), then takes
each scraped article's full body and decides whether to ainsert (Layer 2). Real
LLM-backed filters replace the always-pass placeholders shipped by Foundation
Quick 260507-lai. Verdicts persist on source tables so a partially-failed batch
can resume without re-spending LLM cost.

Single user-facing capability: **"daily-ingest cron runs end-to-end with no
classify gate and no zero-candidate failure modes."** Internal stages
(layer1_pre_filter / scrape / layer2_full_body_score / ainsert) are NEVER
exposed as separate skills — that's the omnigraph_ingest skill's internal
pipeline, indistinguishable from the operator's perspective.

## 6 User-Locked D-Decisions (2026-05-07)

| ID | Decision |
|----|----------|
| **D-LF-1** | Layer 1 接入位置: **ingest pipeline 最前面** (scrape 之前). The standalone `daily-classify-kol` cron is permanently removed; classification is no longer a separate concern from ingest. |
| **D-LF-2** | 持久化: `articles` + `rss_articles` each gain 4 new columns: `layer1_verdict`, `layer1_reason`, `layer1_at`, `layer1_prompt_version`. Migration 006 is **additive only** — no existing data touched. Layer 2 follows the same shape (migration 007: `layer2_verdict`, `layer2_reason`, `layer2_at`, `layer2_prompt_version`). |
| **D-LF-3** | Batch size: Layer 1 = **30 articles per batch** (Gemini Flash Lite, validated by spike). Layer 2 = **5–10 articles per batch** (DeepSeek-Chat, sized by full-body token cost). |
| **D-LF-4** | Failure mode: when an LLM batch call fails (timeout, non-JSON, partial JSON), **all verdicts in that batch stay `NULL`**. The next ingest run will re-evaluate them on the next cron tick. **No max-retry counter, no permanent-fail flag** (YAGNI — operator can grep for stuck-NULL articles if a regression appears). |
| **D-LF-5** | Trigger: Layer 1 + Layer 2 are **inline stages of the daily-ingest cron run** — no new cron job, no async worker. The pipeline `Layer 1 → scrape → Layer 2 → ainsert` is one synchronous run per ingest invocation. |
| **D-LF-6** | Scope: **WeChat (KOL) path first, RSS path second**. `lib/article_filter.py` is source-agnostic by design (`articles` and `rss_articles` columns mirror), but the wiring lands in `batch_ingest_from_spider.py` (KOL) before `rss_ingest.py` (RSS). RSS path integration is Phase ir-4 (optional, after the 1-week observation window). |

## Layer 1 v0 Prompt (validated, locked verbatim)

The Layer 1 prompt is the contract this milestone consumes. Validated 2026-05-07
on 30 random articles across both sources; 21 reject / 9 candidate / 0 误杀 /
0 漏放. Phase ir-1 wires this verbatim, no edits without re-running the spike.

```text
你是一个文章 pre-filter,任务是 reject 明显不需要进入知识库的文章。
知识库的核心兴趣是:**agent / LLM / RAG / prompt 工程 / AI 工程实践**。
非此核心的内容,即便挂着 "AI" 招牌,也要 reject。

REJECT(verdict="reject")的判断顺序(命中任一立刻 reject,不要再找 keep 理由):

1. **多模态 / 视觉 / 视频 / 语音 模型本身** ⚠️ 高频漏放点:
   主题是 image generation、video generation、ASR / TTS、CV 论文(CVPR/ICCV/ECCV/NeurIPS 视觉方向)、
   视频生成 scaling、视觉偏好优化、图像编辑、视频剪辑工具、语音识别模型 ——
   **即使提到 "LLM / 大模型 / Scaling Law / 偏好优化 / RLHF" 也 reject**。
   仅当主题是 "agent 用多模态做任务"(VLM Agent、视觉 Agent、Browser-use、Computer-use)才 keep。

2. **AI 产品发布 / 工具体验软文** ⚠️ 高频漏放点:
   "X 公司发布 Y 模型 / 工具"、"我花了 N 分钟体验了一下"、"开源说话就能 X" ——
   即使产品是 AI 的也 reject。**仅当文章真的拆解实现 / 架构 / 工程细节**(系统设计、源码解读、推理优化)才 keep。
   判断窍门:看 summary 是否给出技术 mechanism;只描述 capability / 卖点 = reject。

3. **明显新闻 / 公司动态**:发布会、招聘、活动通知、融资消息、转发声明、"X 公司大手笔" / "Y 王炸登场" 此类标题党。

4. **主题完全不沾边**:具身智能、机器人、生物医学、金融、宠物、美食、旅游、
   娱乐八卦、政治新闻、体育、汽车、Rust / Git / 编译器 / 搜索引擎 / HTTP 等纯传统软件话题。

5. **长度明确不足**:content_length 已知且 < 1000。WeChat content_length 为 null 时跳过此项。

KEEP(verdict="candidate")只在以下情况:
- agent / LLM / RAG / prompt / Claude / DeepSeek / Gemini / Hermes / OpenClaw / Harness / 智能体 /
  大模型 / 工具调用 — 且不踩上面任何一条 reject。
- AI 工程实践、agent 框架对比、LLM 应用案例、MLOps、prompt 工程、推理优化(投机解码、KV cache 等)、
  agent 安全 / 评估 / benchmark / 编排、长上下文 / 上下文工程。
- 长度未知(WeChat scrape 前 content_length=null)不能作为 reject 理由。

**冲突处理**:文章同时挂 "agent / LLM" 招牌但实质是规则 1 / 2 命中 → REJECT 优先级高于 KEEP。
**保守原则**:reject 边界吃不准时,倾向 reject(后续还有 Layer 2 兜底)。

输入是 30 篇文章的 metadata 列表。
输出**严格 JSON 数组**,每篇文章对应 1 个对象。
```

Output schema (one object per input article):

```json
[{"id": <id>, "source": "<wechat|rss>", "verdict": "<candidate|reject>", "reason": "<≤30字中文>"}]
```

Model: `gemini-3.1-flash-lite-preview` (validated). Wall-clock budget: ≤ 15s
per 30-article batch.

## Layer 2 Prompt Design Principles (NOT yet spiked)

Layer 2 receives 5–10 articles each carrying `(title, full_body)` and must
return a per-article JSON verdict. Prompt design is deferred to Phase ir-2
plan-phase; the principles below are the contract Phase ir-2 must satisfy:

- Input: 5–10 articles, each `{id, source, title, body}`
- Task per article: judge (a) `depth_score: 1|2|3` for technical-mechanism
  density, (b) `relevant: bool` against the same agent/LLM/RAG/prompt scope as
  Layer 1
- Output: strict JSON array, 1:1 with input
- Model: `deepseek-chat` (default LLM, on-prem, no GCP coupling)
- Failure mode same as Layer 1 (whole-batch NULL on bad/missing JSON; no retry
  counter)

A separate validation spike (sibling to the Layer 1 spike at
`.scratch/layer1-validation-20260507-151608.md`) will land before Phase ir-2
wraps and produce `.scratch/layer2-validation-<ts>.md`.

## Success Criteria

1. **Cost** — measured monthly LLM cost for ingest filtering < ¥10/month
   (current pre-refactor: ~¥210/month from `_classify_full_body` runs over the
   full candidate pool). Measured at end of Phase ir-3 1-week observation
   window from real Hermes data.
2. **Stability** — zero cron failures over the 1-week observation window
   (Phase ir-3). A "failure" is any cron run that produces zero ingested
   articles when the candidate pool was non-empty.
3. **Recall** — zero 误杀 in operator audit of a 30-article sample drawn
   uniformly from a real cron run (sample drawn at end of observation window).
   "误杀" = an article that should have been kept but was rejected.
4. **Reject rate** — Layer 1 reject rate falls in 50–70% (matches spike
   observation; outside that band signals prompt drift or candidate-pool
   shift).
5. **Throughput** — end-to-end ingest pass rate ≥ 90% for articles that pass
   Layer 1 + Layer 2 (i.e., once an article reaches scrape + ainsert, it
   succeeds; counts only operational failures, excludes scrape-throttle waits).

## Cross-Milestone Contract

This milestone is **KG-side ingest only**. It does NOT touch:

- `omnigraph_search.query.search(query_text, mode)` — the Agentic-RAG-v1
  contract. Query side is unaffected.
- `lib/research/` — Agentic-RAG-v1's package. v3.5 ingest changes are invisible
  to research-side consumers; they read whatever ainsert produced.
- `omnigraph_query` / `omnigraph_research` skills — operator-facing skills are
  unchanged.

The only file that can affect Agentic-RAG-v1 is the schema migration (006/007)
adding `articles.layer1_*` / `layer2_*` columns. Migrations are additive;
existing rows + columns stay untouched.

## Out of Scope (do NOT include in any phase)

| Item | Why excluded |
|------|--------------|
| `unified_articles` schema unification | v3.6 candidate; v3.5 keeps the two-table split. `lib/article_filter.py` is source-agnostic by abstraction, not by schema. |
| Cognee inline retire (COG-03) | Already deferred to Phase 20 Wave 3 SSH operator gate; not blocked by v3.5 and not blocking v3.5. |
| Graded probe revival as default | Today's CV bug invalidates the assumption that classify-as-cron is robust; even as `--cheap-mode` opt-in (D-3.5-GRADED in research artifact), graded probe stays disabled until Phase ir-3 observation window passes. |
| Reject-reason versioning | v3.5 candidate (Section 2 of MILESTONE_v3.5_CANDIDATES.md); not blocking. |
| Embed worker timeout proportional scaling | Same — Section 2 candidate, not blocking. |
| systemd timer migration for Hermes cron | Operational hardening, not architectural — runs in parallel to v3.5 if user prioritizes. |
| Eval framework for filter recall | Hobby project; rely on operator-audit sample at Phase ir-3 close. |
| Test infrastructure for cron-loop simulation (Lesson 6) | Tracked as v3.5 candidate; not blocking the milestone. |

## Tech Stack (additions only)

Existing: see main `PROJECT.md`.

**No new runtime deps.** Layer 1 reuses `lib/vertex_gemini_complete.py` for
Gemini calls; Layer 2 reuses `lib/llm_deepseek.py`. Both already exist and are
exercised by other phases.

**Schema additions** (additive, no destructive migrations):

- Migration 006: `articles.layer1_*` + `rss_articles.layer1_*` (4 cols × 2
  tables = 8 columns)
- Migration 007: `articles.layer2_*` + `rss_articles.layer2_*` (4 cols × 2
  tables = 8 columns)
- Migration 008 (optional, ir-4): drop empty `classifications` +
  `rss_classifications` tables once `_classify_full_body` is fully retired.

## Naming Map

| Object | Name |
|--------|------|
| Milestone | **v3.5-Ingest-Refactor** |
| Python module path | `lib/article_filter.py` (already scaffolded by Foundation Quick 260507-lai placeholder) |
| Phase dirs | `.planning/phases/ir-N-*/` |
| Sibling planning files | `.planning/{PROJECT,REQUIREMENTS,ROADMAP,STATE}-v3.5-Ingest-Refactor.md` |

## Parallel-Track Constraint

This milestone runs alongside v3.4 (Phases 20-22) and Agentic-RAG-v1 (`ar-N`):

- **v3.4 KG main-line** — free to evolve LightRAG / embeddings / canonical map.
  v3.5 only touches `articles` + `rss_articles` columns + the ingest-loop
  control flow.
- **Agentic-RAG-v1** — query side; cross-milestone contract on
  `omnigraph_search.query.search(...)` stays stable. Zero overlap.
- Resources (operator attention, Hermes test slots) coordinated by hand via
  GSD state files; v3.5's STATE-v3.5-Ingest-Refactor.md evolves independently.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):

1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to D-decisions table
5. "Goal" still accurate? → Update if drifted

**After milestone close** (via `/gsd:complete-milestone`):

1. Full review of all sections
2. 1-week observation window pass-or-not — captured in closure doc
3. Audit Out of Scope — reasons still valid?
4. Update main `PROJECT.md` to fold validated capabilities into project record

---
*Last updated: 2026-05-07 — milestone chartered after CV mass-classify postmortem; 6 D-decisions locked; Layer 1 v0 prompt validated on 30-article spike.*
