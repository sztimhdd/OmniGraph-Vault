# OmniGraph-Vault — Parallel Milestone: KB-v2 (Knowledge Base)

> Sibling milestone running parallel to v3.4 (closed) / v3.5 (Ingest Refactor) / Agentic-RAG-v1.
> Main project context lives in `PROJECT.md`. This file scopes KB-v2 only.
> Phase directories use the `kb-N-*` prefix to avoid collision with other milestones.

## What This Milestone Is

Build a **public, bilingual (zh-CN / en) Agent-tech content site** on top of OmniGraph's
existing data assets. The site exposes:

1. **Article browse** — list / filter / detail page for KOL + RSS articles
2. **Search** — fast keyword search across both languages
3. **RAG Q&A** — natural-language deep-research backed by the LightRAG knowledge graph
4. **Public access** — zero login, zero auth, runs on a single Ubuntu server

The KB module lives under `kb/` in this repo. It is a **complete sibling module**
(frontend + backend + deploy + maintenance — all our responsibility), not an
integration with an external party. vitaclaw-site supplied the initial design
brief (`kb/docs/00-09`) but the implementation is fully OmniGraph-owned.

**Locked design docs:** `kb/docs/01-PRD.md` (PRD §4 SEO 章节作废 — 见 Goal 调整),
`kb/docs/02-DECISIONS.md` (D-01 ~ D-20),`kb/docs/03-ARCHITECTURE.md`,
`kb/docs/09-AGENT-QA-HANDBOOK.md` (vitaclaw 决策回执)。

## Goal

把 OmniGraph 累积的 KOL/RSS 文章 + LightRAG 知识图谱做成一个 **Agent 技术圈日常用得爽
的中英双语内容站** —— 列表 / 详情 / 搜索 / RAG 问答全站支持中英切换,公开访问零登录,
跑在一台 Ubuntu 服务器上。重要的是**有用、大家需要、爱用**,不是搜索引擎排名。

## Locked Architectural Choices (do NOT re-discuss)

- **Stack:** Python 3.11+ / FastAPI + uvicorn / Jinja2 SSG / SQLite (FTS5) — 不引
  Astro / Next.js / 任何前端 SPA 框架(D-08)
- **Bilingual:**
  - UI chrome 中英双语(~50 strings,dict-based i18n,无 babel/gettext 重型依赖)
  - 文章内容**保留原文不翻译**,UI 标语言 badge("中文" / "English")
  - 语言切换:cookie 持久化 + `?lang=en` 硬切 query param
  - 默认语言:`Accept-Language` 探测,fallback `zh-CN`
- **Search:**
  - 默认 SQLite FTS5 trigram tokenizer(SQLite 3.34+ built-in,无 jieba 依赖,中英通杀)
  - `?mode=kg` 才走 LightRAG hybrid(异步,3-10s)
- **Q&A:**
  - 复用 `kg_synthesize.synthesize_response()`(~50 LOC HTTP 包装,D-04)
  - **不改 kg_synthesize 函数签名**(契约 C1 不破)— 语言 directive 在 KB 层注入到
    query_text 前缀:`"请用中文回答。 / Please answer in English. "`
  - 异步:`POST /synthesize` → 202 + job_id;`GET /synthesize/{job_id}` 轮询(D-19)
  - 失败降级:返回 FTS5 top-3 摘要拼接 + 置信度标记,**不返 500**
- **Article URL:**
  - `/article/{content_hash}` — `content_hash` 是 md5[:10](D-20)
  - 现有数据库 KOL 4/653 篇有 `content_hash`,RSS 1600/1600 都是完整 md5 → KB 层运行时
    截取 `[:10]`;无 `content_hash` 的 KOL 文章从 body 运行时计算 md5[:10](K-2)
- **Content sources:**
  - SQLite `articles` + `rss_articles` 表(列表 / 索引 / 搜索数据源)
  - filesystem `~/.hermes/omonigraph-vault/images/{hash}/final_content.md`(详情页优先)
    fallback `articles.body` / `rss_articles.body`(D-14)
  - LightRAG storage `~/.hermes/omonigraph-vault/lightrag_storage/`(/synthesize 端点)
- **Deploy:** Ubuntu systemd service unit(`kb-api.service`)+ Caddy 反代 + 每日 cron
  触发 SSG 重建。**纯 Python web 栈,不依赖任何 agent runtime**(K-4)
- **Image serving:** FastAPI `StaticFiles` mount `/static/img` → `IMAGES_DIR`
  替代独立 `python -m http.server 8765`(D-15);写入文件中的 `http://localhost:8765/`
  在 KB 层运行时正则重写为 `/static/img/`(D-17)

## Cross-Milestone Contracts

The KB-v2 milestone depends on the existing OmniGraph data layer via **4 stable contracts**.
任何破坏性改动必须在 commit message 含 `BREAKING: kb-contract-X`。

| # | Contract | Location | Status |
|---|---|---|---|
| **C1** | `kg_synthesize.synthesize_response(query_text: str, mode: str = "hybrid")` | [kg_synthesize.py:105](../kg_synthesize.py#L105) | ✅ Verified stable |
| **C2** | `omnigraph_search.query.search(query_text: str, mode: str = "hybrid") -> str` | [omnigraph_search/query.py:35](../omnigraph_search/query.py#L35) | ✅ Verified stable |
| **C3** | `kol_scan.db` 表结构 (articles / classifications / extracted_entities / entity_canonical / ingestions / rss_articles) | `data/kol_scan.db` | ✅ Verified — adding nullable `lang` column is **schema-extending non-breaking** |
| **C4** | `images/{hash}/final_content.md` + `metadata.json` 路径与命名 | `~/.hermes/omonigraph-vault/images/` | ✅ Verified |

KG 团队 / 数据团队 free 改动 LightRAG 版本、embedding 模型、storage backend、ingest 流程,
**只要这 4 个外部接口稳定。**

## Smoke Test (acceptance criterion)

3 个手动验证场景,实施完成后跑(KB-3 完工后):

### Smoke 1 — 双语 UI 切换

1. 浏览器 `Accept-Language: zh-CN` 访问首页 → 默认中文 UI
2. 点击右上角语言切换 → 英文 UI 全站生效(nav / labels / buttons / footer 全英文)
3. 刷新页面 → 偏好通过 cookie 持久化,仍英文 UI
4. 访问 `/?lang=zh` → 硬切回中文,cookie 同步更新

### Smoke 2 — 双语搜索 + 详情页

1. 中文 UI 输入"AI Agent 框架" → 返回 ≥ 3 条中文文章命中
2. 英文 UI 输入"langchain framework" → 返回 ≥ 3 条英文文章命中
3. 点击任一英文文章 → 详情页 `<html lang="en">` + 标"English" badge + 内容原文(英文)
4. 点击任一中文文章 → 详情页 `<html lang="zh-CN">` + 标"中文" badge + 内容原文(中文)
5. 详情页底部 og:image / og:title metadata 正确(分享到 IM 群里有预览)

### Smoke 3 — RAG 问答双语 + 失败降级

1. 中文输入"LangGraph 和 CrewAI 有什么区别?" → 异步 → 中文 markdown 答复 + 来源链接
2. 英文输入"What is the difference between LangGraph and CrewAI?" → 异步 → 英文 markdown
   答复 + 来源链接
3. 模拟 LightRAG 不可用(stop kg backend or block storage path) → /synthesize 降级返回
   FTS5 top-3 摘要拼接 + `confidence: "fts5_fallback"` 标记,**不 500**

**Pass conditions** (all must hold):
- 3 个 smoke 场景全 PASS
- 浏览器 Lighthouse 跑分 LCP < 2.5s / CLS < 0.1(SSG 静态页天然达标)
- 列表页 / 详情页 / 问答页 在桌面 + 移动 viewport 都不溢出
- `articles.lang` + `rss_articles.lang` 100% 覆盖(detect 脚本跑过)
- 部署 systemd service `systemctl status kb-api` 运行正常 + `journalctl` 无 ERROR

## Out of Scope (do NOT include in any phase)

| Item | Why excluded |
|------|--------------|
| **文章内容 LLM 自动翻译** | 成本 + 幻觉风险;v2.0 只做 UI 双语 + 内容原文展示 |
| **跨语言搜索 / 跨语言 Q&A** | 中文 query 映射到 English 文章库 / 反之 — v2.1 |
| **KB-2 实体页 + 主题 Pillar 页** | canonical 实体仅 13 个,撑不起;v2.1 等数据稠密后再做 |
| **Databricks Apps 部署** | 工作区鉴权与公开访问不兼容;v2.1 EDC 内部预览专项 |
| **Rate limiting / Redis 令牌桶** | D-01 假设零流量,不优化假性能瓶颈;v2.1 |
| **Repository 数据层抽象 (Protocol pattern)** | K-3 推迟到 v2.1;v2.0 直接 SQLite + filesystem |
| **百度站长 API / 主动推送 / 关键词矩阵 / SEO 推送** | 项目目标调整 — 做"有用爱用的内容站",不做"SEO 吸铁石" |
| **多用户登录 / 评论 / 订阅 / 用户系统** | D-07 完全公开零门槛 |
| **Astro / Next.js / React SPA 框架迁移** | D-08 极简 MVP 用 Python Jinja2 |
| **CMS 后台 / 内容编辑界面** | 内容由 OmniGraph 管道产出,不手工编辑 |
| **OmniGraph pipeline 配置 / 爬虫控制 UI** | 不暴露上游管道 |
| **HTTPS / TLS 自动续期 / 域名运营** | Caddy 自动 TLS 即可,不在 milestone scope |

## Tech Stack (additions only)

Existing: see main `PROJECT.md`.

**New runtime deps for this milestone (additions to `requirements.txt`):**

- `fastapi>=0.110` — web framework
- `uvicorn[standard]>=0.27` — ASGI server
- `jinja2>=3.1` — SSG templates(已是 LightRAG 间接依赖,但显式 pin)
- `python-multipart>=0.0.6` — FastAPI form support(/synthesize POST)
- `markdown>=3.5` — md → HTML rendering(详情页)
- `pygments>=2.17` — code block 语法高亮

**SQLite 版本要求:** ≥ 3.34(FTS5 trigram tokenizer 支持)。Ubuntu 22.04 LTS 默认 SQLite
是 3.37,满足。Ubuntu 20.04 默认 3.31 不够,部署前需确认。

**No new external services / API keys.** 全部复用现有的:
- `DEEPSEEK_API_KEY`(/synthesize via kg_synthesize)
- `GEMINI_API_KEY` / `OMNIGRAPH_GEMINI_KEY`(LightRAG retrieval LLM,if Vertex 路径)
- `OMNIGRAPH_LLM_PROVIDER={deepseek, vertex_gemini}`(K-1)

## File Pattern (parallel-track convention)

Following the Agentic-RAG-v1 / v3.5-Ingest-Refactor parallel-track precedent:

```
.planning/
├── PROJECT-KB-v2.md         (this file)
├── REQUIREMENTS-KB-v2.md    (next: gathered in Step 9)
├── ROADMAP-KB-v2.md         (next: spawned by gsd-roadmapper in Step 10)
├── STATE-KB-v2.md           (this commit: initial scaffold)
└── phases/
    ├── kb-1-export-ssg/
    ├── kb-3-fastapi-bilingual/
    └── kb-4-deploy/
```

主 `PROJECT.md` / `REQUIREMENTS.md` / `ROADMAP.md` / `STATE.md` 由 v3.4 / v3.5 占用,
**不动**。

## Phase Numbering

KB-v2 phases 用 **`kb-N-*` 前缀**,跟主项目 phase 编号(目前已到 22)解耦。从 `kb-1` 起步:

```
kb-1 → SSG export + Jinja2 + i18n + content_hash 运行时计算 + 一次性 lang detect 脚本
kb-3 → FastAPI :8766 + bilingual API + FTS5 trigram + /synthesize KB-side wrapping
kb-4 → Ubuntu systemd + Caddy 反代 + 每日 cron + smoke 验证
```

(KB-2 跳过,直接 1 → 3 → 4 — 与 PRD §6 Phase 编号一致,易于交叉引用)

## Future Milestones (after KB v2.0)

不锁定时间表,仅记录方向:

- **KB v2.1** — 实体页 + 主题 Pillar 页(canonical 实体增长后)+ Repository 数据层抽象
  + Databricks Apps EDC 内部预览部署 + rate limiting
- **KB v2.2** — 内容 LLM 自动翻译(实验性)+ 跨语言搜索 + 跨语言 Q&A
- **KB v2.3** — Agentic-RAG-v1 接入 `/synthesize` 端点(替代 kg_synthesize 直调)+ 流式响应

## Last Updated

2026-05-12 — Milestone v2.0 initialized via `/gsd:new-milestone kb-v2`. Goal locked
(bilingual Agent-tech content site, Ubuntu deploy, no SEO framing, no Hermes runtime
dependency). Next: Step 9 define `REQUIREMENTS-KB-v2.md`.
