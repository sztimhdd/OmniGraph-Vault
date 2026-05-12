---
gsd_state_version: 1.0
milestone: KB-v2
milestone_name: — KB-v2 (parallel-track)
status: defining-requirements
last_updated: "2026-05-12T15:30:00Z"
last_activity: "2026-05-12 — PROJECT-KB-v2.md committed; ready for REQUIREMENTS gather"
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State — KB-v2 (parallel)

## Project Reference

- This milestone: `.planning/PROJECT-KB-v2.md`
- Parent project: `.planning/PROJECT.md`
- Design docs: `kb/docs/01-PRD.md` (§4 SEO 章节作废) + `kb/docs/02-DECISIONS.md`
  (D-01 ~ D-20) + `kb/docs/03-ARCHITECTURE.md` + `kb/docs/09-AGENT-QA-HANDBOOK.md`
- Roadmap: `.planning/ROADMAP-KB-v2.md` (TBD — Step 10)
- Requirements: `.planning/REQUIREMENTS-KB-v2.md` (TBD — Step 9)

## Current Position

Milestone: KB-v2 (parallel-track to v3.4 / v3.5 / Agentic-RAG-v1)
Phase: Not started — defining requirements
Plan: —
Status: Defining requirements (Step 9 of `/gsd:new-milestone` workflow)
Last activity: 2026-05-12 — PROJECT-KB-v2.md committed; goal + locked decisions captured

### Immediate next step

Step 9 — Generate `.planning/REQUIREMENTS-KB-v2.md` with KB-* REQ-IDs grouped by
category (UI / DATA / API / SEARCH / QA / DEPLOY / I18N), then Step 10 — spawn
gsd-roadmapper to derive `kb-1 / kb-3 / kb-4` phases.

## Parallel-Track Boundary

This STATE file tracks **KB-v2 ONLY**. v3.4 / v3.5 / Agentic-RAG-v1 progress remain
in their own STATE files.

The KB-v2 milestone shares with the parent project:

- The same git working tree (commits land on `main`)
- The same Ubuntu deployment target (single server, KB will run alongside any other
  services there — but does NOT depend on Hermes agent runtime)
- The 4 cross-milestone contracts C1-C4 (see PROJECT-KB-v2.md "Cross-Milestone Contracts")

The KB-v2 milestone does NOT share with sibling milestones:

- Phase numbering — KB uses `kb-N-*` prefix, separate from main `19/20/21/22` and
  from `ar-N-*` (Agentic-RAG-v1)
- REQ-ID namespace — KB uses `KB-*` / `UI-*` / `I18N-*` / etc., separate from
  v3.4's `SCR-* / RIN-* / ...`
- Planning files — KB has its own `PROJECT-KB-v2.md` / `REQUIREMENTS-KB-v2.md` /
  `ROADMAP-KB-v2.md` / `STATE-KB-v2.md` (parallel-track suffix pattern)

## Accumulated Context (for resumption)

### What's locked (do not re-discuss)

- **Goal:** bilingual (zh-CN / en) Agent-tech content site, Ubuntu deploy, public
  zero-login access, no SEO framing
- **Tech stack:** Python 3.11+ / FastAPI + uvicorn / Jinja2 SSG / SQLite FTS5 trigram
- **Bilingual:** UI chrome 双语 + 文章原文不翻译 + cookie/query lang 切换
- **Search:** SQLite FTS5 trigram (built-in 3.34+, 中英通杀)
- **Q&A:** kg_synthesize 包装,KB 层注入 lang directive,**不破契约 C1**
- **URL:** `/article/{md5[:10]}` content_hash 运行时计算 (K-2)
- **Deploy:** Ubuntu systemd unit + Caddy 反代,**不依赖 Hermes agent runtime**
- **File pattern:** parallel-track suffix files (PROJECT-KB-v2.md etc.)
- **Out of scope:** 内容自动翻译 / 跨语言搜索 / KB-2 实体页 / Databricks 部署 /
  rate limiting / Repository 抽象 / SEO 推送
- **No research step** — kb/docs/ 已有完整设计,research 跳过

### What's open

- All REQ-IDs (Step 9) — grouped by category with owners + acceptance criteria
- Phase decomposition (Step 10) — 3 phases (kb-1 / kb-3 / kb-4) per PRD §6
- Per-phase success criteria (Step 10)

### Things to remember when resuming

1. **kb/docs/01-PRD.md §4 SEO 章节、所有 SEO-* / PAGE-* / LINK-* REQs 整组废止** —
   实施时按本 milestone 定义的 scope 走。但保留 web 礼仪基线(sitemap.xml / robots.txt
   / og:tags / JSON-LD,含 inLanguage 字段)
2. **数据现状(本地 dev)**:KOL 4/653 篇有 content_hash(0.6%)— 运行时 fallback;
   RSS 1600/1600 全有完整 md5(截取 [:10]);entity_canonical 仅 13 行(撑不起 KB-2)
3. **`articles.lang` / `rss_articles.lang` 列不存在** — kb-1 phase 第一步就是一次性
   migration + detect 脚本,**这是 schema-extending non-breaking 改动**(C3 不破)
4. **vitaclaw-site brand assets 复用**:logo `VitaClaw-Logo-v0.png` / favicon
   `favicon.svg` / 品牌色 `#0f172a` / 品牌名"企小勤"(英文辅助"VitaClaw")
5. **失败降级策略**:/synthesize 失败 → FTS5 top-3 摘要拼接 + 置信度标记,**不返 500**
