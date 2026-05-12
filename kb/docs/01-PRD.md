# 企小勤知识库 Milestone v2 — 产品需求文档 (PRD)

**版本:** 2.0 Draft
**日期:** 2026-05-11
**状态:** 待审阅 — 用户决策门
**作者:** Sisyphus orchestrator，基于 omniscient context synthesis

---

## 0. 核心愿景

> **"我们刮削下来的文章全部本地化编纂成文集作为SEO磁铁，同时提供一个RAG问答引擎吸引技术用户。"**

知识库是**两个产品合为一体**：

| 产品 | 目标用户 | 核心价值 | 技术形态 |
|------|---------|---------|---------|
| **SEO吸铁石文集** | 企业决策者、业务负责人 | 搜索到高质量AI+自动化内容 → 建立品牌信任 → 转化为企小勤试用期 | SSG静态页面，搜索引擎可爬取 |
| **RAG问答引擎** | 开发者、AI工程师、技术决策者 | 输入问题 → 获得OmniGraph知识图谱增强的深度回答 → 体验产品能力 | 动态API + 交互UI，演示企小勤的智能 |

---

## 1. 产品定位

### 1.1 一句话描述

**企小勤知识库** — AI数字员工领域的高质量中文知识平台，以精心编纂的行业文集吸引搜索流量，以RAG问答引擎展示技术深度，两者共同把访客转化为企小勤用户。

### 1.2 为什么是SEO吸铁石

- OmniGraph每天刮削微信KOL、知乎、RSS内容，经过LLM分类+实体规范化，天然产出高质量、结构化的中文AI领域内容
- 市场上缺乏系统性、有深度的中文AI Agent/企业自动化知识库（飞书/钉钉帮助中心是产品文档，不是知识百科）
- 每篇文章都有原始来源+AI摘要+实体关联+主题标签 = 搜索引擎高价值信号
- 企小勤定位"不改系统，一周上线"，知识库内容与产品主张形成闭环

### 1.3 为什么需要RAG引擎

- 技术用户搜索"LightRAG vs Cognee"或"企业RPA安全合规"时，不只是想看文章，更想直接问问题
- RAG引擎演示了企小勤底层能力（知识提取→智能回答），本身就是最好的产品demo
- Agentic-RAG v1 mileston已经规划了 `lib/research/research()` 的HTTP暴露，知识库是第一个消费者

### 1.4 不是什么

- ❌ 不是通用搜索引擎（只搜索企小勤知识库内容）
- ❌ 不是OmniGraph前端管理界面（不暴露管道配置、爬虫控制）
- ❌ 不是CMS后台（内容由OmniGraph管道产出，不手工编辑）
- ❌ 不是SaaS仪表板（面向公网访客，不是企业内部门户）

---

## 2. 内容架构

### 2.1 信息架构

```
知识库首页 (kb.qixiaoqin.com 或 /knowledge)
├── 主题集群 (Topic Clusters)
│   ├── /ai-agent          AI智能体
│   │   ├── 概览页          Pillar Page
│   │   ├── /ai-agent/what-is-ai-agent          什么是AI智能体
│   │   ├── /ai-agent/agent-framework-comparison  智能体框架对比
│   │   ├── /ai-agent/mcp-protocol             MCP协议解析
│   │   └── ...
│   ├── /enterprise-automation 企业流程自动化
│   │   ├── 概览页
│   │   ├── /enterprise-automation/rpa-vs-ai-agent  RPA vs AI Agent
│   │   ├── /enterprise-automation/approval-automation 审批自动化
│   │   └── ...
│   ├── /ai-security       AI安全与合规
│   │   ├── 概览页
│   │   ├── /ai-security/ebpf-observability     eBPF可观测性
│   │   ├── /ai-security/nhi-identity           非人身份管理
│   │   └── ...
│   ├── /industry-cases    行业案例
│   │   ├── /industry-cases/banking              银行业
│   │   ├── /industry-cases/manufacturing        制造业
│   │   └── ...
│   └── /tech-deep-dive    技术深潜
│       ├── /tech-deep-dive/lightrag              LightRAG原理
│       ├── /tech-deep-dive/knowledge-graph       知识图谱
│       └── ...
├── 实体百科 (Entity Pages)
│   ├── /entity/openai                 OpenAI
│   ├── /entity/langchain              LangChain
│   ├── /entity/lightrag              LightRAG
│   └── ...
├── 来源索引 (Source Index)
│   ├── /sources                        所有来源列表
│   ├── /source/wechat-公众号名         微信来源页
│   └── /source/zhihu-专栏名            知乎来源页
└── RAG问答 (Q&A Engine)
    ├── /ask                             问答入口
    ├── /ask/answer?q=...               问答结果页
    └── /ask/popular                    热门问题
```

### 2.2 主题集群策略

基于OmniGraph现有分类标签和企小勤目标关键词，定义以下主题集群：

| 集群ID | 主题 | Pillar关键词 | 目标SEO关键词 | 文章来源 |
|--------|------|-------------|--------------|---------|
| `ai-agent` | AI智能体 | AI Agent, 智能体 | 什么是AI智能体, AI Agent框架, 智能体开发 | Layer1/2 KOL文章 |
| `enterprise-automation` | 企业流程自动化 | 自动化, RPA | 企业自动化, RPA替代, 审批自动化 | 产品文档+KOL |
| `ai-security` | AI安全与合规 | 安全, 合规 | AI安全, 企业AI合规, 数据安全 | Layer1专业性文章 |
| `industry-cases` | 行业案例 | 行业方案 | AI银行, AI制造, AI政务 | Layer2实践类 |
| `tech-deep-dive` | 技术深潜 | 技术解析 | LightRAG, 知识图谱, RAG技术 | Layer1技术类 |

### 2.3 页面类型

| 页面类型 | URL模式 | 内容来源 | 渲染方式 | SEO价值 |
|---------|---------|---------|---------|---------|
| **Pillar Page** | `/topic/{slug}` | OmniGraph分类+人工审核 | SSG | 极高 — 主题权威信号 |
| **文章页** | `/article/{slug}` | OmniGraph文章+AI摘要 | SSG | 极高 — 原创内容+长尾词 |
| **实体页** | `/entity/{slug}` | OmniGraph实体规范化 | SSG | 高 — 实体权威+内部链接 |
| **来源页** | `/source/{slug}` | OmniGraph来源注册表 | SSG | 中 — 来源权威信号 |
| **问答页** | `/ask/answer?id={hash}` | 动态生成 | SSR/CSR | 中 — 长尾问题+结构化数据 |
| **首页** | `/` | 汇总+最新+热门 | SSG | 极高 — 品牌入口 |

### 2.4 内部链接策略

```
Pillar Page ←→ Article Pages (双向链接)
     ↕
Article Page ←→ Entity Pages (引用实体)
     ↕               ↕
Entity Pages ←→ Other Entity Pages (相关实体)
     ↕
Source Pages (来源聚合)
```

- 每篇文章标注3-5个相关实体，实体页链接回文章
- Pillar Page链接到所有子文章，子文章链接回Pillar
- "相关推荐" 侧边栏：基于实体共现关系
- 面包屑导航：首页 > 主题 > 子主题 > 文章

---

## 3. 技术架构

### 3.1 架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| **前端框架** | Python Jinja2 CLI生成HTML | SSG, 零JS, 零框架学习成本, 1周上线 |
| **交互组件** | React CDN岛屿 (仅问答页) | 只有问答需要JS |
| **数据源** | 构建时导出 + API动态 | 文章/实体/主题=构建时JSON；问答=运行时API |
| **API后端** | Hermes同机FastAPI :8766 | 独立轻量FastAPI服务，与现有Express解耦，端口:8766 |
| **RAG引擎** | OmniGraph `omnigraph_search.query.search()` | 已存在、已验证，hybrid模式检索 |
| **部署** | Aliyun ECS + Caddy | 与现有vitaclaw-site同服务器，Caddy反向代理 |
| **域名** | `kb.qixiaoqin.com` 或 `qixiaoqin.com/knowledge` | 子域名方案SEO独立权重更好 |
| **构建** | GitHub Actions (手动触发) | 与现有deploy.yml一致 |

### 3.2 为什么是Python+Jinja2不是Astro/Next.js

| 维度 | Python+Jinja2 | Astro | Next.js | 判定 |
|------|--------------|-------|---------|------|
| 学习成本 | 零（Python内置） | 需学习岛屿架构 | 需SSR/RSC | **Python胜** |
| SEO | 纯HTML，无需优化 | 零JS默认 | 需要SSR | **Python≈Astro** |
| 部署 | 直接读目录 | 需要Node/Adapter | 需要Node | **Python胜** |
| 维护 | 1个脚本 | npm生态+插件 | npm生态 | **Python胜** |
| 动态交互 | React CDN | 岛屿React | 原生React | 平手 |
| 快速迭代 | 改模板→rerun→刷新 | npm build→deploy | npm build→deploy | **Python胜** |
| 扩展性 | 模板引擎极限 | 优秀 | 优秀 | Astro/Next胜 |

**结论:** MVP阶段Python+Jinja2是最优选择。达到日UV500+后迁移到Astro。

### 3.3 数据流架构

```
┌──────────────────────────────────────────────────────┐
│                    OmniGraph-Vault                   │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐ │
│  │ SQLite   │  │ LightRAG │  │ entity_buffer     │ │
│  │ kol_scan │  │ Storage  │  │ + canonical_map   │ │
│  │ .db      │  │ ~700MB   │  │                   │ │
│  └────┬─────┘  └────┬─────┘  └────────┬──────────┘ │
│       │              │                 │             │
└───────┼──────────────┼─────────────────┼─────────────┘
        │              │                 │
   ┌────▼──────┐  ┌────▼──────┐   ┌─────▼──────┐
   │ export_   │  │ kg_synth- │   │ entity_    │
   │ knowledge_│  │ esize     │   │ index      │
   │ base.py   │  │ .synthes- │   │ builder    │
   │           │  │ ize_resp- │   │            │
   │ → Jinja2  │  │ onse()    │   │ → 实体→    │
   │ → HTML    │  │           │   │ 文章映射   │
   └────┬──────┘  └────┬─────┘   └─────┬──────┘
        │              │               │
════════╪══════════════╪═══════════════╪════ 构建时/运行时边界
        │              │               │
   ┌────▼──────┐  ┌────▼──────┐   ┌────▼──────┐
    │ kb/output/│  │ FastAPI   │   │ Caddy     │
    │ (SSG      │  │ :8766     │   │ /kb/*     │
    │ 静态HTML)  │  │ /search   │   │ → :8766   │
   └────┬──────┘  └────┬─────┘   └────┬──────┘
        │              │              │
   ┌────▼──────────────▼──────────────▼──────┐
   │        用户浏览器 (Caddy serve)           │
   │                                          │
   │  ┌─────────┐  ┌─────────┐ ┌──────────┐ │
   │  │ 文章页   │  │ 实体页   │ │ RAG问答  │ │
   │  │ (Jinja2 │  │ (Jinja2 │ │ (React   │ │
   │  │ 纯HTML) │  │ 纯HTML) │ │ 岛屿)    │ │
   │  └─────────┘  └─────────┘ └──────────┘ │
   └──────────────────────────────────────────┘
```

### 3.4 构建时数据导出 (SSG内容)

```python
# 新增: OmniGraph导出脚本
# scripts/export_knowledge_base.py

def export_articles():
    """从SQLite导出所有已分类文章 → JSON → Astro content collection"""
    # SELECT title, url, body, digest, topic, source, published_at
    # FROM articles WHERE classification_status = 'passed'

def export_entities():
    """从entity_canonical表导出实体 → JSON → Astro content collection"""
    # SELECT canonical_name, entity_type, aliases, description, related_articles
    # FROM entity_canonical

def export_topic_clusters():
    """从分类标签生成主题集群 → JSON → Astro content collection"""
    # 基于classifications.topic聚合

def export_source_index():
    """从kol_registry生成来源索引 → JSON"""
    # 来源(微信公众号/知乎专栏/RSS源) → 文章数量 → 最新文章
```

### 3.5 运行时API (动态问答)

FastAPI应用 (`kb_api.py`) 运行于Hermes :8766：

```python
# kb_api.py — FastAPI 端点定义

# 知识库搜索 (默认FTS5, ?mode=kg → LightRAG)
GET /search?q={query}&mode={fts5|kg}
  → FTS5: { results: ArticleMeta[], total: number, time_ms: number }
  → LightRAG: { status: "running" | "done", job_id?: string }

# 文章列表+分页
GET /articles?page=1&per_page=20&topic={topic}&source={source}
  → { articles: ArticleMeta[], total: number, page: number }

# 文章详情 (filesystem final_content.md → SQLite body)
GET /article/{hash}
  → { content: string, format: "vision_enriched" | "raw_markdown", meta: ArticleMeta }

# 知识库深度研究 (异步)
POST /synthesize
  → 请求: { question: string }
  → 响应: 202 { job_id: string }

GET /synthesize/{job_id}
  → 轮询: { status: "running" | "done" | "failed", result?: SynthesisResult }

# 实体列表+详情
GET /entities → { entities: EntityMeta[] }
GET /entity/{name} → EntityDetail

# 图片服务 (FastAPI StaticFiles mount)
GET /static/img/{path} → 图片文件
```

### 3.6 Hermes部署架构

```
知识库后端部署在Hermes同机（阿里云ECS），与OmniGraph pipeline共存：

FastAPI :8766
├── GET /articles       → SQLite (列表+分页+过滤)
├── GET /article/{hash} → final_content.md优先 → articles.body回退
├── GET /search?q=       → 默认FTS5 <10ms, ?mode=kg → LightRAG 5-30s异步
├── POST /synthesize    → BackgroundTasks + 轮询GET /synthesize/{job_id}
├── GET /entities       → SQLite entity_canonical
├── GET /entity/{name}  → SQLite
└── /static/img/*       → StaticFiles mount (替代:8765图片服务器)

Caddy 443:
├── /kb/*              → :8766 (知识库API)
├── /static/img/*      → :8766 (图片)
└── /*                 → :3001 (现有vitaclaw-site)

开发期: SSH -L 8766:localhost:8766
生产: ohca.ddns.net DDNS + Caddy HTTPS
```

### 3.7 项目结构

```
kb/                          # 知识库Astro项目 (与vitaclaw-site并列)
├── astro.config.mjs
├── package.json
├── src/
│   ├── content/
│   │   ├── config.ts            # Astro content collection schema
│   │   ├── articles/            # 文章MD/MDX (构建时从OmniGraph生成)
│   │   │   ├── ai-agent-what-is.md
│   │   │   ├── agent-framework-comparison.md
│   │   │   └── ...
│   │   ├── entities/            # 实体页 (构建时从OmniGraph生成)
│   │   │   ├── openai.md
│   │   │   ├── langchain.md
│   │   │   └── ...
│   │   └── topics/              # 主题集群定义
│   │       ├── ai-agent.md
│   │       ├── enterprise-automation.md
│   │       └── ...
│   ├── layouts/
│   │   ├── BaseLayout.astro      # 基础布局 (SEO head, nav, footer)
│   │   ├── ArticleLayout.astro   # 文章页布局 (面包屑, 侧边栏, CTA)
│   │   ├── EntityLayout.astro    # 实体页布局
│   │   ├── TopicLayout.astro     # 主题集群布局 (pillar page)
│   │   └── AskLayout.astro       # 问答页布局
│   ├── components/
│   │   ├── SearchWidget.tsx      # React island: 搜索框
│   │   ├── QAEngine.tsx          # React island: RAG问答引擎
│   │   ├── RelatedArticles.astro # 相关文章推荐
│   │   ├── EntityCard.astro      # 实体卡片
│   │   ├── BreadcrumbNav.astro  # 面包屑导航
│   │   ├── TopicGrid.astro       # 主题网格
│   │   ├── ArticleCard.astro    # 文章卡片
│   │   └── CTABanner.astro      # 转化CTA横幅
│   ├── pages/
│   │   ├── index.astro          # 知识库首页
│   │   ├── topic/[slug].astro   # 主题集群页
│   │   ├── article/[slug].astro # 文章页
│   │   ├── entity/[slug].astro  # 实体页
│   │   ├── source/[slug].astro  # 来源页
│   │   ├── ask/index.astro      # 问答入口
│   │   └── ask/answer.astro     # 问答结果
│   └── styles/
│       └── global.css            # 继承vitaclaw-site设计语言
├── scripts/
│   └── export_knowledge_base.py # OmniGraph→Content Collections 导出
└── public/
    ├── robots.txt
    ├── sitemap.xml              # 构建时生成
    └── favicon.ico
```

---

## 4. SEO策略

### 4.1 百度优化（中国SEO核心）

| 维度 | 策略 | 具体做法 |
|------|------|---------|
| **域名/服务器** | 中国大陆服务器 | 已有阿里云ECS (101.133.154.49)，无需变更 |
| **ICP备案** | 必须备案 | 域名需备案才能被百度正常收录 |
| **HTTPS** | 必须HTTPS | Caddy自动TLS (需域名指向) |
| **URL结构** | 短且含关键词 | `/ai-agent/what-is-ai-agent` 而非 `/post?id=123` |
| **Sitemap** | 自动生成 | Astro @astrojs/sitemap 集成 |
| **结构化数据** | Schema.org | 每篇文章 `Article`, `FAQPage`; 实体页 `Thing`; 面包屑 `BreadcrumbList` |
| **百度推送** | 主动推送API | 新内容发布后推送URL到百度 |
| **关键词密度** | 自然分布 | 标题含1次核心词，正文分布2-3%，不堆砌 |
| **原创标记** | 原创内容声明 | `<meta name="original-source" content="...">` + 百度原创推送 |

### 4.2 Google优化

| 维度 | 策略 |
|------|------|
| **结构化数据** | `Article`, `HowTo`, `FAQPage`, `BreadcrumbList`, `Organization` |
| **OG Tags** | 每页面完整 `og:title`, `og:description`, `og:image`, `og:type` |
| **页面速度** | Astro零JS默认 + 岛屿按需加载 → 极快的LCP |
| **移动适配** | 移动优先设计，`viewport` + 响应式 |
| **Core Web Vitals** | LCP < 2.5s, FID < 100ms, CLS < 0.1 (Astro天然达标) |

### 4.3 关键词矩阵

| 类型 | 示例关键词 | 目标页面 | 月搜索量预估 |
|------|----------|---------|------------|
| 核心词 | AI智能体, AI Agent | /ai-agent pillar | 5000-10000 |
| 核心词 | 企业自动化, RPA | /enterprise-automation pillar | 3000-5000 |
| 长尾词 | LightRAG原理, 知识图谱RAG | /tech-deep-dive 文章 | 500-1000 |
| 长尾词 | 银行AI审批案例 | /industry-cases/banking | 200-500 |
| 品牌词 | 企小勤, VitaClaw | 首页+CTA | 500-2000 |
| 问题词 | AI Agent怎么选型 | /ask 问答页 | 200-1000 |

### 4.4 结构化数据示例

```json
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "2026年AI智能体框架对比：LangGraph vs CrewAI vs AutoGen",
  "author": {
    "@type": "Organization",
    "name": "企小勤知识库"
  },
  "publisher": {
    "@type": "Organization",
    "name": "企小勤 VitaClaw",
    "logo": { "@type": "ImageObject", "url": "https://kb.qixiaoqin.com/logo.png" }
  },
  "datePublished": "2026-05-11",
  "dateModified": "2026-05-11",
  "description": "深度对比LangGraph、CrewAI、AutoGen三大AI智能体框架...",
  "keywords": ["AI Agent", "LangGraph", "CrewAI", "AutoGen", "智能体框架"],
  "inLanguage": "zh-CN",
  "isPartOf": { "@type": "CollectionPage", "url": "https://kb.qixiaoqin.com/ai-agent" }
}
```

---

## 5. UX设计

### 5.1 设计语言延续

与vitaclaw-site保持一致的视觉体系：

| 属性 | vitaclaw-site | 知识库 |
|------|--------------|--------|
| 背景 | `#0f172a` | `#0f172a` (一致) |
| 文字 | `#f0f4f8` | `#f0f4f8` (一致) |
| 强调蓝 | `#3b82f6` | `#3b82f6` (一致) |
| 强调绿 | `#22d3a0` | `#22d3a0` (一致) |
| 字体 | Inter + Noto Sans SC | Inter + Noto Sans SC (一致) |
| 卡片 | `rounded-2xl border border-card-border bg-card` | 一致 |
| 风格 | 暗色科技风 | 暗色百科风 (增加阅读优化) |

### 5.2 首页布局

```
┌────────────────────────────────────────────────┐
│  🏠 企小勤知识库    [搜索框...]    [问AI] [首页→] │ ← 复用导航设计
├────────────────────────────────────────────────┤
│                                                │
│  🧠 AI智能体的企业实践百科                       │ ← H1 hero
│  深度文章 · 实体百科 · 智能问答                 │ ← 副标题
│  [开始探索]  [问个问题]                          │ ← 双CTA
│                                                │
├────────────────────────────────────────────────┤
│  📂 主题集群                                    │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐           │
│  │AI智能│ │企业自动│ │AI安全│ │行业案例│           │
│  │  体  │ │  化  │ │与合规│ │      │           │
│  └──────┘ └──────┘ └──────┘ └──────┘           │
│     12篇      15篇     8篇     6篇               │
├────────────────────────────────────────────────┤
│  🔥 最新文章                                    │
│  ┌─────────────────────────────────────────┐   │
│  │ LangGraph vs CrewAI: 2026框架对比        │   │
│  │ 来源：机器之心 · 2026-05-10 · AI智能体    │   │
│  │ AI Agent框架选型是每个技术团队的必经之路...│   │
│  └─────────────────────────────────────────┘   │
│  ┌───────────────────────────┐ ┌─────────────┐│
│  │ 银行审批自动化实践          │ │ RPA安全的...│ │
│  └───────────────────────────┘ └─────────────┘│
├────────────────────────────────────────────────┤
│  💡 热门实体                                   │
│  OpenAI · LangChain · LightRAG · Cognee · ... │
├────────────────────────────────────────────────┤
│  🤖 试试智能问答                                │
│  ┌─────────────────────────────────────────┐   │
│  │ 问: AI Agent和RPA有什么区别？             │   │
│  │ 答: AI Agent和RPA的核心区别在于...         │   │
│  │     [查看完整回答 →]                      │   │
│  └─────────────────────────────────────────┘   │
│  [立即提问 →]                                   │
├────────────────────────────────────────────────┤
│  🏢 开始使用企小勤                              │ ← 转化CTA
│  不改系统，一周上线 · 免费试点                   │
│  [免费试点]  [预约演示]                          │
└────────────────────────────────────────────────┘
```

### 5.3 文章页布局

```
┌────────────────────────────────────────────────┐
│ 首页 > AI智能体 > 框架对比                       │ ← 面包屑
├──────────────────────────┬─────────────────────┤
│                          │                     │
│  LangGraph vs CrewAI:    │ 📌 侧边栏          │
│  2026智能体框架对比       │                     │
│                          │ 相关实体             │
│  来源：机器之心           │ · LangChain          │
│  2026-05-10 · 8min阅读   │ · OpenAI             │
│                          │ · AutoGen             │
│  [AI智能体] [框架对比]    │                     │
│                          │ 相关文章              │
│  ---正文---              │ · Agent选型指南       │
│                          │ · MCP协议解析         │
│                          │                     │
│                          │ 转化CTA              │
│                          │ ┌───────────────┐    │
│                          │ │ 试试企小勤     │    │
│                          │ │ 免费 · 一周上线│    │
│                          │ └───────────────┘    │
│                          │                     │
├──────────────────────────┴─────────────────────┤
│  🤖 对这篇文章有疑问？ [问AI →]                  │ ← 底部CTA
└────────────────────────────────────────────────┘
```

### 5.4 RAG问答页布局

```
┌────────────────────────────────────────────────┐
│  企小勤知识问答                                  │
│  基于OmniGraph知识图谱的智能问答                 │
│                                                │
│  ┌────────────────────────────────────────┐    │
│  │ 💬 输入你的AI、自动化相关问题...        │    │
│  └────────────────────────────────────────┘    │
│                                                │
│  热门问题：                                     │
│  · AI Agent和RPA有什么区别？                    │
│  · 企业如何选择AI智能体框架？                    │
│  · 银行审批自动化怎么做？                       │
│  · 什么是MCP协议？                              │
│                                                │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                │
│  提问: "AI Agent和RPA有什么区别？"              │
│                                                │
│  AI Agent和RPA的核心区别在于自主性和决策能力... │
│                                                │
│  📎 来源文章：                                  │
│  · [RPA vs AI Agent对比分析]                   │
│  · [企业自动化2026趋势]                         │
│                                                │
│  🔗 相关实体：                                  │
│  · [RPA]  [AI Agent]  [UiPath]                │
│                                                │
│  ⚠️ AI生成内容仅供参考，建议阅读原始文章获取完整 │
│  上下文。                                       │
│                                                │
│  🏢 [免费试用企小勤] [预约演示]                  │ ← 转化CTA
└────────────────────────────────────────────────┘
```

---

## 6. 里程碑分期

### Milestone v2.0: 知识库MVP (SEO文集 + 基础问答)

**目标**: 上线最小可用版本，验证SEO效果和用户反馈

| Phase | 内容 | 交付物 | 预估 |
|-------|------|--------|------|
| **KB-1** | Export脚本 | `export_knowledge_base.py`, 4个Jinja2模板 (首页/文章/实体/主题), SQLite→HTML管道 | 2天 |
| **KB-2** | 实体索引+SEO | entity_buffer实体→文章索引, JSON-LD, sitemap.xml, 面包屑导航, 内部链接 | 2天 |
| **KB-3** | RAG问答API | `kb_api.py` (~50行FastAPI包装synthesize_response), React问答岛屿组件, Caddy图片代理 | 2天 |
| **KB+N-IMG-4** | 部署+上线 | Caddy配置, cron每日重建脚本, GitHub Actions手动触发, 上线验证 | 1天 |

### Milestone v2.1: SEO增强 + 问答优化

| Phase | 内容 | 交付物 |
|-------|------|--------|
| **2.1-1** | 搜索引擎 | 站内全文搜索（Pagefind或FlexSearch） |
| **2.1-2** | 百度站长工具 | 百度统计、搜索资源平台验证、主动推送API |
| **2.1-3** | 文章增强 | 相关推荐算法优化，实体自动标注 |
| **2.1-4** | 问答优化 | 问答历史，热门问题页，来源引用改进 |

### Milestone v2.2: 深度集成

| Phase | 内容 | 交付物 |
|-------|------|--------|
| **2.2-1** | Agentic-RAG集成 | 等Agentic-RAG v1 HTTP端点就绪后接入`/api/kb/research` |
| **2.2-2** | 自动内容更新 | OmniGraph cron触发知识库重建 |
| **2.2-3** | 分析仪表板 | 访问量、搜索词、转化率追踪 |
| **2.2-4** | A/B测试 | CTA文案、布局变体测试 |

---

## 7. 成功指标

| 指标 | v2.0目标 (3个月内) | v2.1目标 (6个月内) | 衡量工具 |
|------|-------------------|-------------------|---------|
| **有机搜索流量** | 500 UV/日 | 2000 UV/日 | 百度统计 |
| **百度收录页面** | 50+ | 200+ | site:搜索 |
| **关键词排名** | 5个词进前3页 | 15个词进前3页 | 百度站长工具 |
| **问答使用** | 50次/日 | 200次/日 | 日志统计 |
| **转化率** | 2%访客→CTA | 5%访客→CTA | 事件追踪 |
| **页面速度** | LCP < 2.5s | LCP < 2s | Lighthouse |

---

## 8. 需求列表 (REQ)

### 基础设施 (INFRA)

- [ ] **INFRA-01**: 创建独立Astro 5项目`kb/`，与`vitaclaw-site/`并列存放
- [ ] **INFRA-02**: Astro配置Content Collections：`articles`、`entities`、`topics`三个集合
- [ ] **INFRA-03**: 配置`@astrojs/sitemap`自动生成`sitemap.xml`
- [ ] **INFRA-04**: 配置`@astrojs/react`实现岛屿交互
- [ ] **INFRA-05**: 设计语言继承：复用vitaclaw-site的#0f172a配色、Inter+Noto Sans SC字体、卡片样式
- [ ] **INFRA-06**: Caddy反向代理配置：`kb.qixiaoqin.com` → Astro SSG + FastAPI :8766
- [ ] **INFRA-07**: GitHub Actions CI/CD：手动触发部署到阿里云ECS

### 数据导出 (EXPORT)

- [ ] **EXPORT-01**: `export_knowledge_base.py`脚本从OmniGraph SQLite导出已分类文章到JSON
- [ ] **EXPORT-02**: 文章JSON包含：slug, title, summaryZh, bodyMarkdown, sourceName, sourceDomain, sourceUrl, publishedAt, collectedAt, topicTags, entityReferences, layer
- [ ] **EXPORT-03**: 导出实体规范化数据到JSON（canonical_name, entity_type, aliases, description, related_article_slugs）
- [ ] **EXPORT-04**: 导出主题集群定义到JSON（topic_id, nameZh, nameEn, slug, pillar_keywords, subtopic_slugs）
- [ ] **EXPORT-05**: 导出来源索引到JSON（source_id, name, platform, article_count, latest_articles）
- [ ] **EXPORT-06**: 构建时将JSON转换为Astro Content Collections Markdown文件

### SEO (SEO)

- [ ] **SEO-01**: 每篇文章页面包含`Article` Schema.org结构化数据（headline, author, datePublished, keywords）
- [ ] **SEO-02**: 每个主题页面包含`CollectionPage` + `BreadcrumbList`结构化数据
- [ ] **SEO-03**: 每个实体页面包含`Thing`结构化数据
- [ ] **SEO-04**: 所有页面包含完整OG元标签（title, description, image, type, url）
- [ ] **SEO-05**: URL结构：`/topic/{slug}`, `/article/{slug}`, `/entity/{slug}`, `/source/{slug}`
- [ ] **SEO-06**: 生成`robots.txt`允许全站爬取，指向sitemap
- [ ] **SEO-07**: 所有页面`hreflang="zh-CN"`，`<html lang="zh-CN">`
- [ ] **SEO-08**: 百度主动推送API集成（新内容发布后自动推送URL）
- [ ] **SEO-09**: 每篇文章底部包含"原文来源"链接和"AI生成摘要仅供参考"声明

### 页面模板 (PAGE)

- [ ] **PAGE-01**: 知识库首页展示：主题集群卡片、最新文章、热门实体、问答入口、转化CTA
- [ ] **PAGE-02**: 文章详情页布局：标题+元数据+正文+相关实体+相关文章+侧边栏CTA
- [ ] **PAGE-03**: 主题Pillar页面：概览+子文章列表+面包屑导航
- [ ] **PAGE-04**: 实体页面：实体描述+关联文章列表+相关实体
- [ ] **PAGE-05**: 来源页面：来源信息+该来源下所有文章
- [ ] **PAGE-06**: 每个页面包含面包屑导航：首页 > 主题 > 子主题 > 文章
- [ ] **PAGE-07**: 全站导航：首页、主题、实体、来源、问答、回到企小勤官网

### 内部链接 (LINK)

- [ ] **LINK-01**: 文章页侧边栏显示3-5个相关实体卡片，每个链接到实体页
- [ ] **LINK-02**: 文章页底部显示"相关推荐"文章列表（基于实体共现关系）
- [ ] **LINK-03**: 实体页展示所有引用该实体的文章
- [ ] **LINK-04**: Pillar Page链接到所有子文章，子文章链接回Pillar
- [ ] **LINK-05**: 每个页面底部包含"试试企小勤"CTA横幅，链接到vitaclaw-site主页

### RAG问答 (QA)

- [ ] **QA-01**: 新增`GET /search?q=&mode=`端点（FastAPI :8766），默认FTS5，?mode=kg走LightRAG
- [ ] **QA-02**: 新增`POST /synthesize` + `GET /synthesize/{job_id}`异步研究端点，复用kg_synthesize.synthesize_response()
- [ ] **QA-03**: 问答页面包含搜索框、热门问题、回答结果、来源文章链接、相关实体链接
- [ ] **QA-04**: 问答页面底部包含"AI生成内容仅供参考"免责声明
- [ ] **QA-05**: 问答回答中的来源文章链接指向知识库文章页（内部链接增强）
- [ ] **QA-06**: 拒绝模式：继承vitaclaw-assistant的拒绝模式，扩展至知识库敏感查询

### 内容安全 (SAFE)

- [ ] **SAFE-01**: 所有导出内容标注`curationStatus: "passed"`，只展示OmniGraph审核通过的文章
- [ ] **SAFE-02**: 每篇AI生成摘要标注AI生成标识和原始来源链接
- [ ] **SAFE-03**: 问答引擎拒绝敏感查询（密钥、密码、注入攻击等）
- [ ] **SAFE-04**: 不暴露OmniGraph原始存储路径、管道配置、API密钥
- [ ] **SAFE-05**: 构建时内容审核：人工review标记的内容不进入知识库

### 部署 (DEPLOY)

- [ ] **DEPLOY-01**: Caddy配置：`kb.qixiaoqin.com`路由到Astro SSG + FastAPI :8766
- [ ] **DEPLOY-02**: HTTPS：Caddy自动TLS（需域名DNS指向）
- [ ] **DEPLOY-03**: FastAPI `/kb/*` 路由通过Caddy反向代理 :8766，与vitaclaw-site :3001 共存
- [ ] **DEPLOY-04**: GitHub Actions手动触发构建+部署
- [ ] **DEPLOY-05**: 内容更新流程：OmniGraph cron → export脚本 → Astro rebuild → 部署

---

## 9. 风险分析

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| **百度不收录** | 中 | 高 | ICP备案+百度站长验证+主动推送+原创标记；初期大量提交URL |
| **内容质量不足** | 中 | 高 | 只展示`curationStatus: passed`文章；人工审核关键内容 |
| **LightRAG查询慢** | 中 | 中 | SSG内容不依赖运行时查询；问答API加缓存+超时 |
| **域名DNS问题** | 低 | 高 | 子目录方案备选：`qixiaoqin.com/knowledge/` |
| **内容重复（搜索惩罚）** | 中 | 高 | 每篇摘要必须原创改写，不直接复制原文；canonical URL |
| **RAG回答幻觉** | 高 | 中 | 引用来源文章；无来源时拒绝回答；免责声明 |
| **OmniGraph数据管道故障** | 中 | 中 | 构建时失败不更新（保留上次）；运维告警 |
| **Agentic-RAG v1延迟** | 中 | 低 | v2.0用现有`omnigraph_search.query.search()`；v2.2再接Agentic-RAG |
| **kg_synthesize图片依赖** | 中 | 中 | FastAPI StaticFiles挂载:8766/static/img/；Caddy反向代理确保公网可访问 |

---

## 10. 已定决策 (2026-05-11 讨论确认)

| # | 决策 | 结论 | 理由 |
|---|------|------|------|
| D-01 | 部署方式 | 子域名`kb.qixiaoqin.com`或子目录`/knowledge/` | **待定**，取决于ICP备案进度 |
| D-02 | 内容来源范围 | 仅Layer1/2 curationStatus:passed | 质量优先 |
| D-03 | 文章内容形式 | AI摘要+原文链接 | 版权安全 |
| D-04 | 问答后端 | `kg_synthesize.synthesize_response()` (~50行包装) | 已有生产验证，不等Agentic-RAG |
| D-05 | 项目结构 | 独立Python项目同仓库 | 与vitaclaw-site并列 |
| D-06 | 图片服务 | FastAPI StaticFiles挂载 :8766/static/img/ | FastAPI统一管理，删除独立的:8765图片服务器 |
| D-07 | 问答登录 | 完全公开 | 降低门槛 |
| D-08 | 框架 | Python Jinja2（不是Astro/Next.js） | 极简MVP，1周上线 |
| D-09 | 更新频率 | 每日cron自动重建 | 内容新鲜度=SEO信号 |
| D-10 | 设计语言 | 继承#0f172a暗色主题 | 品牌一致 |

---

## 11. 与现有milestone的关系

| Milestone | 当前状态 | 与v2的关系 |
|-----------|---------|-----------|
| VitaClaw-site v1.0 | ✅ 已部署 | 知识库复用设计语言，CTA链回官网 |
| VitaClaw-site v1.1 | ✅ 已部署 | Agent News导出合同可扩展为完整知识库导出 |
| VitaClaw-site v1.2 | ✅ 本地验证 | 问答架构复用现有Express+DeepSeek（vitaclaw-assistant保留） |
| OmniGraph v3.4 | ✅ 已完成 | RSS管道提供内容来源 |
| OmniGraph Agentic-RAG v1 | 📋 规划中 | v2.2接入其HTTP API |
| Knowledge Base v2.0 | **📌 本文档** | 新里程碑 |

---

## 12. 名词表

| 术语 | 定义 |
|------|------|
| **SEO吸铁石** | 通过高质量内容吸引搜索引擎流量的知识库网站 |
| **Pillar Page** | 主题集群的核心页面，覆盖一个大主题的所有子话题 |
| **LightRAG** | OmniGraph使用的知识图谱引擎，支持hybrid/local/global检索模式 |
| **实体规范化** | OmniGraph将不同名字的同一实体统一为规范名称（如"OpenAI"和"openai"→"OpenAI"） |
| **Content Collections** | Astro的内容管理系统，支持Markdown/MDX内容集合的schema验证 |
| **岛屿架构** | Astro的交互组件加载模式，只有需要JS的组件才加载React |
| **SSG** | Static Site Generation，构建时生成HTML，SEO最优 |
| **CTA** | Call To Action，转化行动号召（如"免费试点"、"预约演示"） |