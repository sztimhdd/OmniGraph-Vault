---
gsd_state_version: 1.0
milestone: KB-v2
milestone_name: — KB-v2 (parallel-track)
status: kb-2-complete-ready-for-kb-3
last_updated: "2026-05-13T18:00:00Z"
last_activity: "2026-05-13 — kb-2 fully complete: 10 plans across 5 waves with full Skill discipline (ui-ux-pro-max=5, frontend-design=5, python-patterns=2, writing-tests=2); 12/12 REQs (TOPIC-01..05 + ENTITY-01..04 + LINK-01..03); 31 :root vars unchanged (kb-1 token baseline preserved); CSS 1979 LOC (+42 over 1937 budget — UI-SPEC §3.2/3.3/3.4 verbatim retained per design discipline); fixture-driven export produces 5 topic HTMLs + 6 entity HTMLs + sitemap auto-extends to 22 URLs; 58 new integration tests covering all 37 UI-SPEC §8 acceptance grep patterns; 12/12 Playwright UAT viewports (topic-agent / entity-openai / home-extended / article-with-aside × 375/768/1280) zero horizontal scroll. Deferred: cross-test fixture pollution + dev-runtime DB schema mismatch (documented in kb-2/deferred-items.md). Phase kb-2 ready to close."
progress:
  total_phases: 3
  completed_phases: 2
  total_plans: 21
  completed_plans: 20
---

# Project State — KB-v2 (parallel)

## Project Reference

- This milestone: `.planning/PROJECT-KB-v2.md`
- Parent project: `.planning/PROJECT.md`
- Design docs: `kb/docs/01-PRD.md` (§4 SEO 章节作废) + `kb/docs/02-DECISIONS.md`
  (D-01 ~ D-20) + `kb/docs/03-ARCHITECTURE.md` + `kb/docs/09-AGENT-QA-HANDBOOK.md`
- Roadmap: `.planning/ROADMAP-KB-v2.md`
- Requirements: `.planning/REQUIREMENTS-KB-v2.md`

## Current Position

Milestone: KB-v2 (parallel-track to v3.4 / v3.5 / Agentic-RAG-v1)
Phase: **kb-1 ✅ complete** — 10/10 plans + gap-closure (kb-1-10) + HUMAN-UAT 3/4 PASS
Plan: 10/10 executed and verified
Status: Ready for `/gsd:plan-phase kb-3`
Last activity: 2026-05-13 — kb-1 fully verified end-to-end. 1800 article HTMLs generated against production `.dev-runtime/data/kol_scan.db`; Playwright MCP automated browser UAT confirmed bilingual UI + content-language badges + cookie persistence + responsive viewports.

### Phase plan

| Phase | Goal | REQs | T-shirt | Plans | Status |
|-------|------|------|---------|-------|--------|
| kb-1 | SSG Export + i18n Foundation (data layer + Jinja2 + bilingual chrome) | 27 | L+0.5d redesign | 10+1 (kb-1-10 gap) + redesign-quick | ✅ **COMPLETE pre-redesign** (26/27 codebase-satisfied; UI-04 logo deferred to kb-4); UI redesign quick task in progress 2026-05-13 to close design-dimension audit |
| **kb-2** | Topic Pillar + Entity Pages + Cross-Link Network | **12** | M (1.5-2d) | TBD | **NEW 2026-05-13** — revived from "skipped" after Hermes prod data verification |
| kb-3 | FastAPI Backend + Bilingual API + Search + Q&A | 18 | L | TBD | not started |
| kb-4 | Ubuntu Deploy + Cron + Smoke Verification | 5 | S | TBD | not started (UI-04 carry-forward gate) |

Total: **62/62 v2.0 REQs** mapped (was 50; +12 from kb-2 revival). kb-1: 26/27 satisfied + 1 deferred-by-approval (UI-04). kb-2/3/4: 35 REQs pending.

> **Note:** kb-2 (Topic Pillar + Entity pages + cross-link) **revived 2026-05-13**. Hermes prod has `classifications` 3945 rows + `extracted_entities` 5257 rows / 91 entities at ≥5-article frequency — sufficient for v2.0 scope. v2.1 dependencies (CANON-* LLM canonicalize, TYPED-* entity_type, TOPIC-HIER-* taxonomy) remain deferred and won't block v2.0.

### kb-1 Verification Summary (2026-05-13)

| Source | Result |
|---|---|
| `kb-1-VERIFICATION.md` (gsd-verifier, 2026-05-13 13:00 UTC) | gaps_found → complete after kb-1-10 |
| `kb-1-10-final-verification` (post-gap-closure) | 4/8 truths VERIFIED + 4 human-verifiable |
| `kb-1-HUMAN-UAT.md` (Playwright MCP, 2026-05-13 17:00 UTC) | 3/4 PASS (UAT 1+2+3) + 1 deferred (UAT 4 logo PNG → kb-4) |
| Real-DB SSG run | 1800 articles HTML, 0 errors, idempotency byte-match verified |
| Test count | 73/73 passing (was 71/71 pre-gap-closure) |
| Score | 26/27 REQs (was 22/27 pre-gap-closure) |

### Immediate next step

`/gsd:plan-phase kb-3` — plan FastAPI :8766 backend (18 REQs across API/SEARCH/QA/CONFIG categories).

Use `/clear` first for fresh context window. The data layer functions (`list_articles`, `get_article_by_hash`, `resolve_url_hash`, `get_article_body`) shipped in kb-1-06 are ready for HTTP wrapping.

After kb-3 ships: plan kb-4 (Ubuntu deploy + Caddy + cron + 3 smoke scenarios + UI-04 logo PNG sourcing).

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

### Roadmap Evolution

- 2026-05-12 — Milestone KB-v2 initialized parallel to v3.4 / v3.5 / Agentic-RAG-v1.
  Sibling-files layout chosen; `kb-N` phase prefix; design docs (`kb/docs/01-09`)
  treated as final, no research stage spawned.
- 2026-05-12 — REQUIREMENTS-KB-v2.md committed. 9 categories: I18N (8), DATA (6),
  EXPORT (6), UI (7), API (8), SEARCH (3), QA (5), DEPLOY (5), CONFIG (2) —
  total 50 REQs (REQUIREMENTS-KB-v2.md header text says "37" but that is stale;
  category breakdown sums to 50).
- 2026-05-12 — ROADMAP-KB-v2.md created by `gsd-roadmapper`. Decomposition:
  layered foundation → service → ops across 3 phases (kb-1 / kb-3 / kb-4),
  explicit kb-2 skip. All 50 REQs mapped, no orphans, no duplicates. Traceability
  table in REQUIREMENTS file populated.

### Decisions

Decisions are logged in `PROJECT-KB-v2.md` § "Locked Architectural Choices" and
in `kb/docs/02-DECISIONS.md` (D-01 ~ D-20).

This-session decisions:

- 2026-05-12 — Sibling-files layout (`PROJECT-KB-v2.md` etc.) chosen over
  subdirectory or worktree, preserving v3.4 / v3.5 / Agentic-RAG-v1 GSD tooling
  untouched
- 2026-05-12 — Phase prefix `kb-N` chosen over continuing `23+` numbering, to
  preserve cross-reference compatibility with `kb/docs/04-KB1` / `06-KB3` /
  `07-KB4` execution specs
- 2026-05-12 — Research stage skipped — `kb/docs/01-09` covers design end-to-end
  per user instruction; no `gsd-project-researcher` agents spawned
- 2026-05-12 — **Layered foundation → service → ops decomposition** chosen over
  vertical-slice MVP-first. Three drivers: (1) data-shape risks (lang IS NULL
  rows, KOL-vs-RSS hash format divergence, body fallback chain) are concentrated
  in the data layer; layered surfaces them all in kb-1; (2) the SSG export is
  itself the natural end-to-end thin slice — no further verticalization needed;
  (3) kb-3 only adds HTTP semantics on top of a working data layer, kb-4 is pure
  ops — sequential dependency is honest. Full rationale in ROADMAP-KB-v2.md
  § "Phase decomposition rationale".
- 2026-05-12 — **3 phases**, with kb-2 explicitly skipped. kb-2 (entity pages +
  topic Pillar pages) deferred to v2.1 because only 13 canonical entities exist
  today, can't support a real entity-page surface (per PROJECT-KB-v2.md "Out of
  Scope" + `kb/docs/09-AGENT-QA-HANDBOOK.md` Q3 K-3).
- **2026-05-13 — REVISED to 4 phases.** kb-2 un-skipped after SSH verification against Hermes prod DB found:
  - `classifications` table: 3945 rows (5 topics × 789 articles) — local dev DB had 0 rows, leading to wrong "deferred" judgment
  - `extracted_entities`: 5257 rows / 3319 distinct names; 91 entities at ≥5-article freq, 26 at ≥10-article freq
  - kb-2 viable today using raw `extracted_entities` + frequency threshold (skip canonicalization). v2.1 dependencies (CANON-* / TYPED-* / TOPIC-HIER-*) remain deferred.
  - 12 new REQs: TOPIC-01..05 + ENTITY-01..04 + LINK-01..03. Total 62/62. T-shirt M (1.5-2 days).
  - **Lesson captured in memory `feedback_parallel_track_gates_manual_run.md`:** always verify against Hermes prod data before deferring scope — local dev DB is sparse and misleading.

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
6. **REQUIREMENTS-KB-v2.md header text says "37 REQs"; actual count is 50.**
   Roadmap and traceability use 50. Header is stale; reconciliation is a
   separate doc-fix task.

### Pending Todos

None tracked. Awaiting `/gsd:discuss-phase kb-1` or `/gsd:plan-phase kb-1`
invocation.

### Blockers/Concerns

- **None for milestone init or roadmap.** All 4 cross-milestone contracts (C1-C4)
  are read-only; the only schema change (DATA-01 nullable `lang` column) is
  C3-additive non-breaking.
- **Operator-side dependencies** (deferred to kb-4): Ubuntu host with SQLite
  ≥ 3.34 (FTS5 trigram tokenizer support); Caddy installed; cron available;
  optional `KB_DB_PATH` / `KB_IMAGES_DIR` overrides if not deploying same-host
  with `~/.hermes/omonigraph-vault/`. None of these block kb-1 or kb-3
  development.

## Performance Metrics

(populated as plans complete)

## Session Continuity

Last session: 2026-05-12T18:00:00Z
Stopped at: Roadmap committed; 50/50 REQs mapped; phase plan locked at kb-1, kb-3, kb-4 (kb-2 explicitly skipped)
Resume file: None
Next command: `/gsd:discuss-phase kb-1` (preferred) or `/gsd:plan-phase kb-1`
