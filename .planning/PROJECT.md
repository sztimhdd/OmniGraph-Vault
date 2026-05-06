# OmniGraph-Vault

## What This Is

A local, graph-based personal knowledge base that gives Hermes Agent (and OpenClaw)
persistent memory. The primary pipeline: **scan WeChat KOL accounts → classify articles
by topic via LLM → ingest into LightRAG knowledge graph → synthesize on demand**.

All article and entity metadata is persisted in a single SQLite database
(`data/kol_scan.db`), enabling repeated classification runs without re-scanning.

## Core Pipeline

```
batch_scan_kol.py ──→ articles in SQLite
        ↓
batch_classify_kol.py ──→ classifications in SQLite (DeepSeek or Gemini)
        ↓
batch_ingest_from_spider.py --from-db ──→ LightRAG knowledge graph
        ↓
kg_synthesize.py ──→ Markdown synthesis report
```

**Key capability:** scan once (120 days, 54 accounts), classify many times with different
topics. No re-scraping needed to re-classify.

## Validated (what works)

- WeChat article scraping: Apify (primary) → CDP fallback → MCP fallback
- Image download + Gemini Vision description
- LightRAG graph insertion + hybrid retrieval
- Cognee async entity canonicalization (DB-first, file fallback)
- Entity extraction → entity_buffer + SQLite dual-write (Phase 2)
- Canonical entity map in SQLite `entity_canonical` table (Phase 2)
- Gemini and DeepSeek classifiers with 15 RPM rate limiting
- PDF ingestion with embedded image extraction
- Synthesis engine generating Markdown reports
- Local image HTTP server (port 8765)
- 4 Hermes skills: ingest, query, architect, claude-code-bridge
- Skill runner with test suites

## Tech Stack

- Python 3.11+, LightRAG (kuzu), Cognee
- Gemini 2.5 Flash (LLM + Vision + Embedding)
- DeepSeek (classification), `google-genai` SDK
- SQLite (article/entity persistence)
- Apify + Playwright CDP (scraping)
- BeautifulSoup + html2text (content extraction)

## Constraints

- **Privacy:** All data local; only Gemini API + Apify make external calls
- **Platform:** Windows-primary (Edge for CDP); WSL for git/github
- **Single user:** No auth, no isolation
- **Runtime data:** `~/.hermes/omonigraph-vault/` (typo is intentional, baked into config.py)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| SQLite for KOL pipeline | One-scan-many-classify; dedup by URL UNIQUE | Good |
| Entity dual-write (file + DB) | No migration risk; file stays primary during transition | In progress |
| Cognee decoupled from ingestion fast-path | Async path preserves <200ms target | Good |
| DeepSeek default classifier, Gemini free option | Cost optimization; fail-open on both | Good |
| Two Skills (ingest + query) not one unified | Clearer intent mapping | Working |

## Current Milestone: v3.4 RSS-KOL Alignment

**Goal:** 让 RSS 管线与 KOL 管线架构对齐 — RSS 文章走完 scrape → full-body classify → multimodal ingest 的完整流程（只排除知乎好问增厚），消除"纯 summary + 纯文字"的残缺入库；通用 scraper 默认带完整 cascade；ingest 失败残留的 stuck doc 有运维工具可清理，不污染 LightRAG 检索质量。

**Background (why now):** 2026-05-03 E2E pre-flight 暴露 RSS 管线是 KOL 管线的"残缺版"，缺 3/6 核心环节（全文抓取、全文+关键词二次筛、多模态 chunk embedding）。若按现状放 Day-2 rollout，~20 篇/天 RSS 会以"纯 summary + 纯文字"入库，479+ 残缺 doc 污染 LightRAG 检索。Day-2 cutover 已暂停，等 v3.4 完工后再 cutover。

**Target features (waves):**

- **Wave 1 — 通用 scraper 模块抽象（cascade by default）**：从 `ingest_wechat.py` 抽出通用 URL → (markdown, images, metadata) 接口；cascade (Apify → CDP → MCP → UA → fallback) 是**默认行为，不是 optional**（Phase 10 D-10.01 UA-only 对 WeChat 被 block 是常态，RSS 的 Substack/Medium/Arxiv/个人博客多源会更严重）；新增 RSS-adapted scraper 处理非 WeChat 站点格式
- **Wave 2 — RSS 全文分类 + 多模态 ingest 重写**：`rss_ingest.py` 重写为 scrape → full-body classify（port Phase 10 D-10.02 `_build_fullbody_prompt`）→ image pipeline Vision cascade → multimodal LightRAG ainsert（`_build_contents` localhost 正则 + 3072-dim 多模态向量）
- **Wave 3 — E2E 回归 + backlog re-ingest + cron cutover + stuck-doc 运维工具**：新建 `test/fixtures/rss_sample_article/` E2E fixture；**新增 stuck-doc 清理工具/脚本**（运维必备，每次 ingest 失败都可能留 stuck doc）；Hermes 真实批量 smoke；冻结的 1020 rss_articles 分批重跑；`register_phase5_cron.sh` body cutover 到 orchestrate step_7

**Success criteria:**

1. 10 篇随机 RSS 全流程通过（scrape → full-body classify → multimodal ingest，LightRAG 中文内容 + 图片语义可检索）
2. orchestrate step_7 双臂 KOL+RSS 各 5 篇成功
3. 新 fixture `test/fixtures/rss_sample_article/` 支撑 E2E 回归
4. ≥800 docs re-ingest（~20% 容忍失败）
5. **Post-rollout observation window (Day-1/2/3 after cutover)** — cron 稳定运行，RSS digest 条目质量 ≥ KOL 条目质量（检索 sample query 返回 RSS 内容与 KOL 内容一样有深度）
6. 失败 ingest 后的 stuck doc 不会污染后续 batch（stuck-doc 清理工具 + E2E 回归证明：故意制造一次失败，验证后续 batch 不受干扰）

**Key open decisions (research must lock as D-level, write into phase CONTEXT.md):**

- **D-RSS-SCRAPER-SCOPE**：新通用 scraper 仅 RSS 使用（B），还是 KOL `_classify_full_body` 也切过去（A）？背景：Day-1 pre-flight 发现 `batch_ingest_from_spider.py:940` 的 KOL scrape-on-demand 路径同样是 UA-only（Phase 10 D-10.01 遗留），article 1 scrape fail 就是这样挂的。User 倾向 A（cascade 写一次两侧都用，KOL 回归与 RSS 一起在 Wave 3 做）；research 必须给 A vs B 的理由 + 代价。
- **D-STUCK-DOC-IDEMPOTENCY**：stuck-doc 清理工具在 LightRAG 运行中还是停机后才安全执行？涉及的存储层（NanoVectorDB / KV store / entity graph）有无并发写保护？决定 Wave 3 交付物是 **CLI 工具** 还是 **cron pre-hook**。

**Hard constraints:**

- **Execute 阶段阻塞到 Day-1/2/3 baseline 完成**（~2026-05-04 → 2026-05-06 ADT）；research + planning 阶段可并行
  - Tuning 决策（subprocess timeout、max-articles cap、concurrency）需要真实数据
  - 验证 Day-1 KOL 流水线在新 code path（Vertex fix 后）稳定

**Explicit carve-outs (out of scope):**

- 知乎好问增厚 for RSS（D-07 REVISED 永久排除）
- Option D RSS classifier batch refactor（已用 `OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP=500` 兜底；v3.4 完工后若仍有性能问题再起独立 quick）
- DeepSeek merge phase 600s timeout（Day-1 E2E 发现，Phase 17 遗留，follow-up quick）
- WeChat CDP cron-env robustness（Phase 5 Wave 1 KOL 侧遗留，非 RSS 对齐）
- Day-1/2/3 baseline 窗口主动干预（仅观察）

**Closed milestone history (summary):**

- v3.1 — Single-Article Ingest Stability ✅ (phases 8-11, 26 REQs)
- v3.2 — Batch Reliability + Infra ✅ (phases 12-17)
- v3.3 — Pipeline Automation: RSS Fetch + Daily Digest + Cron ✅ (phase 18 + Wave 2 tasks 6.1)

## Parallel Milestone: Agentic-RAG-v1

Initialized 2026-05-06, runs alongside v3.4 KG main-line work. Internalizes the
agentic RAG flow as `lib/research/` + skill `omnigraph_research`, removing the
Hermes-runtime dependency for non-Hermes consumers.

**Sibling planning files** (not in this PROJECT.md):

- `.planning/PROJECT-Agentic-RAG-v1.md` — milestone scope + locked architecture
- `.planning/REQUIREMENTS-Agentic-RAG-v1.md` — REQ-IDs (LIB / ORCH / TOOL / SKILL / CLI / CONFIG / TEST / CONTRACT)
- `.planning/ROADMAP-Agentic-RAG-v1.md` — `ar-N` phase decomposition
- `.planning/STATE-Agentic-RAG-v1.md` — milestone state (separate from v3.4)
- `.planning/phases/ar-N-*/` — phase work directories

**Cross-milestone contract** (the only KG-side dependency): KG team must keep
`omnigraph_search.query.search(query_text: str, mode: str = "hybrid") -> str` stable.
Everything else inside LightRAG (version, embeddings, canonical map, retrieval
algorithm, prompts) is free to evolve.

**Locked design:** `docs/design/agentic_rag_internal_api.md` (10 reqs + 10 axes
closed; no further re-derivation).

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

*Last updated: 2026-05-06 — Milestone v3.4 active, Phase 19 verified at 5-article scale on Hermes; 5 v3.4-prep follow-up fixes shipped & verified (8ac3cb1 / 5c602a3 / 359058b / ecaa2df / af01315); execute gate for Phase 20-22 remains BLOCKED until 2026-05-07 06:00 ADT first automated cron run observed positive.*
