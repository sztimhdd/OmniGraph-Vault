# 知识库 v2 架构图

> 极简MVP架构。2026-05-11 定稿。

---

## 整体架构

```
┌──────────────────────────────────────────────────────────┐
│                  OmniGraph-Vault (数据生产者)              │
│                                                           │
│  Daily Cron Pipeline                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                │
│  │ 抓取/分类 │→│ LightRAG │→│ 实体提取 │                │
│  │ (新内容)  │  │  Ingest  │  │          │                │
│  └──────────┘  └──────────┘  └──────────┘                │
│                                                           │
│  Data Assets:                                             │
│  ├─ SQLite: articles, classifications, ingestions         │
│  ├─ entity_buffer/: 每篇文章的实体提取结果                 │
│  ├─ canonical_map.json: 实体别名归一化                     │
│  ├─ lightrag_storage/: ~700MB 知识图谱                     │
│  └─ images/: 文章图片                                      │
└──────────────────────┬───────────────────────────────────┘
                       │ 只读消费
                       ▼
┌──────────────────────────────────────────────────────────┐
│             export_knowledge_base.py (构建时)              │
│                                                           │
│  1. 读取 SQLite → articles → Jinja2 → HTML               │
│  2. 读取 entity_buffer + canonical_map → 实体索引 → HTML  │
│  3. 生成 sitemap.xml                                      │
│  4. 生成 JSON-LD 结构化数据                               │
│  5. 输出到 kb/output/                                     │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│               kb/output/ (纯静态HTML)                      │
│                                                           │
│  ├── index.html             首页                          │
│  ├── topics/                主题Pillar页                   │
│  ├── articles/              文章详情页                     │
│  ├── entities/              实体集合页                     │
│  ├── ask/index.html         问答入口页                     │
│  ├── assets/                CSS/JS                         │
│  ├── sitemap.xml                                          │
│  └── robots.txt                                           │
└──────────────────────┬───────────────────────────────────┘
                       │ Caddy serve
                       ▼
┌──────────────────────────────────────────────────────────┐
│  用户浏览器 ←→ Caddy (443/80)                             │
│                  │                                        │
│                  ├── /* → kb/output/ (静态文件)             │
│                  ├── /images/* → localhost:8765 (图片)     │
│                  └── /api/kb/* → Express:3001 (问答API)    │
│                                     │                     │
│                          ┌──────────┘                     │
│                          ▼                                │
│                    kb_api.py (~50行)                       │
│                    synthesize_response(query)              │
│                    → LightRAG 深度检索+合成                 │
└──────────────────────────────────────────────────────────┘
```

---

## 数据流

### 构建时（cron每日触发）

```
OmniGraph SQLite
  │
  ▼
export_knowledge_base.py
  ├─ .read articles WHERE curationStatus='passed'
  ├─ .read entity_buffer/*.json
  ├─ .read canonical_map.json
  │
  ├─ 生成 /articles/*.html    (Jinja2模板)
  │   ├─ 面包屑: 首页 > 主题 > 文章
  │   ├─ 正文: AI摘要
  │   ├─ 侧边栏: 实体卡片(链接到实体页)
  │   ├─ 底部: 相关推荐
  │   └─ head: JSON-LD + OG tags
  │
  ├─ 生成 /entities/*.html    (Jinja2模板)
  │   ├─ 正文: 实体描述
  │   ├─ 列表: 关联文章(链接到文章页)
  │   └─ 侧边栏: 相关实体
  │
  ├─ 生成 /topics/*.html      (Jinja2模板)
  │   ├─ Pillar: 主题概览
  │   └─ 列表: 所有子文章
  │
  ├─ 生成 /ask/index.html     (React岛屿容器)
  │
  ├─ 生成 sitemap.xml
  └─ 生成 robots.txt
```

### 运行时（用户触发）

```
用户在 ask 页提问
  ↓
React岛屿 → Express POST /api/kb/ask { question: "..." }
  ↓
subprocess/child_process → python kb_api.py
  ↓
synthesize_response(question)
  ├─ LightRAG hybrid retrieval
  ├─ canonical entity mapping
  ├─ IMAGE_URL_DIRECTIVE (保图)
  └─ DeepSeek synthesis
  ↓
Markdown 答案
  ↓
Express → 返回 { answer_md, sources, entities }
  ↓
React岛屿 → Markdown渲染 → 图文显示 → 来源链接(→文章页)
```

---

## 页面内部链接地图

```
首页 (index.html)
  ├→ /topics/ai-agent/          ← 5个主题卡片
  ├→ /articles/*                ← 最新文章列表
  ├→ /entities/openclaw/        ← 实体标签云
  └→ /ask/                      ← 问答入口

文章页 (/articles/xxx)
  ├→ /topics/ai-agent/          ← 面包屑: 回到主题
  ├→ /entities/langchain/       ← 侧边栏: 3-5个实体卡片
  ├→ /articles/related-yyy      ← 相关推荐
  └→ /ask/                      ← "有疑问" CTA

实体页 (/entities/xxx)
  ├→ /articles/article1         ← 所有关联文章
  ├→ /articles/article2
  └→ /entities/related-ent      ← 相关实体

每页面底部
  └→ https://qixiaoqin.com/     ← 转化CTA (企小勤官网)

平均每页内部链接数: 6-12 个
```

---

## SEO结构化数据策略

| 页面类型 | Schema类型 | 关键字段 |
|---------|-----------|---------|
| 首页 | `CollectionPage` + `WebSite` | name, description, url, potentialAction(SearchAction) |
| 文章页 | `Article` | headline, author(publisher), datePublished, image, keywords, inLanguage=zh-CN |
| 主题页 | `CollectionPage` + `BreadcrumbList` | name, description, numberOfItems, itemListElement |
| 实体页 | `Thing` | name, alternateName, description, sameAs |
| 问答页 | `FAQPage` (热门问题) + `WebApplication` | mainEntity[Question/Answer], name, applicationCategory |

---

## 双搜索/问答入口交互设计

### 入口1: 快速检索过滤

**本质:** 目录索引 + 前端即时过滤（零后端依赖，毫秒级响应）

**用户在入口1的典型路径:**

```
场景A: 按主题浏览
首页 → 点击AI智能体主题卡片
    → /topics/ai-agent/ (Pillar页, 含12篇文章列表+子主题)
    → 点击文章标题 → /articles/langgraph-vs-crewai/ (文章详情页)
    → 侧边栏实体[LangChain] → /entities/langchain/ (实体集合页)
    → 列表显示18篇关联文章

场景B: 搜索
用户输入 "eBPF"
    → 前端即时显示:
      ├─ 文章 (3个结果)
      │   · eBPF可观测性实战
      │   · eBPF安全底座
      └─ 实体 (1个结果)
          · [eBPF]
    → 点击结果 → 对应页面

场景C: 实体发现
首页 → 实体标签云 → 点击[LightRAG]
    → /entities/lightrag/
    ├─ 实体描述 (LightRAG是什么)
    ├─ 关联文章 (8篇)
    └─ 相关实体 ([LightRAG] [Cognee] [GraphRAG])
```

**入口1的UI组件（所有页面通用）:**

```
┌──────────────────────────────────────────────────┐
│  ☰ [企小勤知识库]     🔍 [搜文章、实体、主题...] │ ← 全局搜索栏
├──────────────────────────────────────────────────┤
│                                                  │
│  首页: 主题卡片 + 最新文章 + 实体标签云          │
│  文章页: 面包屑 + 正文 + 侧栏实体卡片            │
│  实体页: 描述 + 关联文章列表 + 相关实体            │
│  主题页: 概览 + 文章列表 + 子主题                  │
```

### 入口2: 深度图文问答

**本质:** RAG深度检索 + DeepSeek图文合成（3-10秒，有LLM成本）

**用户在入口2的典型路径:**

```
场景A: 从首页提问
首页 → 问答入口框/按钮
    → /ask/ (问答独立页面)
    → 输入 "AI Agent和RPA有什么区别？"
    → 发送 → 等待3-10秒
    → 显示:
      🤖 AI Agent和RPA的核心区别在于自主性和决策能力...
      📎 来源: [文章1] [文章2] [文章3]
      🔗 实体: [RPA] [AI Agent] [UiPath]
      🖼️ [架构对比图]
      👍 有帮助  👎 没帮助

场景B: 从文章页触发
文章详情页 → 底部 "对这篇文章有疑问？问AI →"
    → /ask/ (自动带入: "关于[文章标题]的问题：...")
    → 用户补充问题 → 发送

场景C: 从实体页触发
实体集合页 → "向AI提问: [实体名]和XX有什么区别？"
    → /ask/ → 发送
```

**入口2的UI组件:**

```
┌──────────────────────────────────────────────────┐
│  🤖 AI知识智能问答                                │
│                                                  │
│  ┌──────────────────────────────────────────┐    │
│  │ 💬 输入你的问题，AI基于知识库为你解答...   │    │ ← 文本框
│  └──────────────────────────────────────────┘    │
│                       [🤖 深度问答]               │ ← 按钮
│                                                  │
│  🔥 热门问题                                     │ ← 预置列表
│  1. AI Agent和RPA有什么区别？                     │
│  2. MCP协议是什么？                               │
│                                                  │
│  ── 回答区域 ──                                  │
│  🤖 回答内容... （Markdown渲染）                   │ ← 动态加载
│  📎 来源文章  🔗 相关实体  🖼️ 图片                │
│  ⚠️ 免责声明                                      │
│  👍 有帮助  👎 没帮助                              │ ← 反馈
│                                                  │
│  ── 底部CTA ──                                   │
│  🏢 试试企小勤 不改系统一周上线                   │
│  [免费试点]  [预约演示]                            │
└──────────────────────────────────────────────────┘
```

### 双入口在页面上的实际位置

```
首页 (/)
├── 🔍 [全局搜索栏] ──────────── 入口1
├── 📂 热门主题卡片 ──────────── 入口1
├── 🔥 最新文章列表 ──────────── 入口1
├── 💡 实体标签云 ────────────── 入口1
├── 🤖 [试试智能问答] ────────── 入口2 (缩短版)
└── 🏢 转化CTA

文章页 (/articles/xxx)
├── 🔍 [全局搜索栏] ──────────── 入口1
├── 正文
├── 侧栏: 📌 相关实体 ────────── 入口1 (点击→实体页)
├── 侧栏: 📄 相关文章 ────────── 入口1
├── 底部: 🤖 [有疑问？问AI →] ── 入口2
└── 底部: 🏢 转化CTA

实体页 (/entities/xxx)
├── 🔍 [全局搜索栏] ──────────── 入口1
├── 实体描述
├── 关联文章列表 ──────────────── 入口1
├── 相关实体 ──────────────────── 入口1
├── 底部: 🤖 [向AI提问: 实体...] ─ 入口2
└── 底部: 🏢 转化CTA

问答页 (/ask/)
├── 💬 [问题输入框 + 深度问答按钮] ─ 入口2 (核心)
├── 🔥 热门问题 ────────────────── 入口2
├── 🤖 回答 ────────────────────── 入口2
├── 📎 来源 → 文章页 ──────────── 入口1 (交叉链接)
├── 🔗 实体 → 实体页 ──────────── 入口1 (交叉链接)
└── 🏢 转化CTA
```

### 入口定位原则

```
入口1（快速检索）: 让用户 "查得到"
  → SEO价值最高，页面本身被搜索引擎索引
  → 无LLM成本，可无限量使用
  → 适合: 明确知道要找什么文章/实体的用户

入口2（深度问答）: 让用户 "问得透"
  → 展示企小勤AI能力，是最好的产品demo
  → 有LLM成本（每次~¥0.01-0.05）
  → 适合: 有具体疑问需要解答的技术用户

交叉链接: 答案中的来源→文章页, 实体→实体页
  → 双入口互相导流
  → 内部链接网络增强SEO权重
```

### ui-ux-pro-max 设计系统推荐

**命令执行结果:**
- Pattern: FAQ/Documentation Landing
- 首屏: 搜索栏突出 + 热门分类 + FAQ
- 转化: 未解决提问转联系CTA
- 风格: Minimalism & Swiss Style（暗色适配版）
- 字体: 推荐 Plus Jakarta Sans（但保留项目现有 Inter + Noto Sans SC）
- 颜色: 推荐 #475569 primary（但保留项目现有 #0f172a 暗色）

---

## 后端API架构 (FastAPI on Hermes)

### 总体拓扑

```
                                                                              ┌────────────────┐
                         开发者 SSH -L 8766                                     │  Aliyun ECS    │
                         ─────────────────────────                              │  (Hermes)      │
                         │                                                    │                │
┌────────────┐           ▼                               ┌──────────────────┐ │  ┌────────┐    │
│ 浏览器     │ ─── HTTPS ───→ Caddy (443)                 │  Hermes 服务群   │ │  │ :8765  │    │
│ (用户)     │                │                            │                  │ │  │ image  │    │
└────────────┘                ├── / → vitaclaw-site (旧)   │  ┌────────────┐ │ │  │ server │    │
                              │                            │  │ FastAPI    │ │ │  └────────┘    │
                              ├── /kb/* → :8766 (知识库)   │  │ :8766      │ │ │       ↓       │
                              │                            │  │            │ │ │ (下线)        │
                              └── /static/img/* → :8766    │  │  GET /articles        │             │
                                                            │  │  GET /article/{hash}  │             │
                                                            │  │  GET /search          │             │
                                                            │  │  POST /synthesize     │             │
                                                            │  │  GET /synthesize/{id} │             │
                                                            │  └───────┬────────────┘              │
                                                            │          │                           │
                                                            │  ┌───────▼────────────┐              │
                                                            │  │ ~/.hermes/         │              │
                                                            │  │   omonigraph-vault/│              │
                                                            │  │   ├─ images/       │              │
                                                            │  │   ├─ lightrag_     │              │
                                                            │  │   │   storage/     │              │
                                                            │  │   └─ data/        │              │
                                                            │  │       kol_scan.db │              │
                                                            │  └──────────────────┘              │
                                                            └─────────────────────────────────────┘
```

### FastAPI端点详表

| 方法 | 路径 | 参数 | 返回 | 数据源 | 备注 |
|------|------|------|------|--------|------|
| GET | /articles | ?page=1&limit=50&source=&enriched=&layer1= | `{items[], total, page}` | SQLite | 列表+分页+多维过滤 |
| GET | /article/{hash} | hash (md5[:10]) | `{hash, title, body_md, images[], source, enriched}` | 先文件系统 → fallback SQLite | body含图片URL重写 |
| GET | /search | ?q=&mode=&source= | `{results[], total, mode}` | 默认FTS5 → ?mode=kg走LightRAG | FTS5 <10ms, KG 5-30s |
| POST | /synthesize | `{question, mode}` | `202 {job_id}` | BackgroundTasks | 异步30s+ |
| GET | /synthesize/{job_id} | — | `{status, result_md?, images?}` | 内存/Redis | 轮询直到done |
| GET | /entities | ?q= | `{items[]}` | SQLite entity_canonical | 实体索引 |
| GET | /entity/{name} | name | `{name, aliases, articles[]}` | SQLite | 实体详情+关联文章 |

### SQLite FTS5搜索

```sql
-- 建表（一次性）
CREATE VIRTUAL TABLE articles_fts USING fts5(
    title, body, content='articles', content_rowid='id'
);

-- 搜索（<10ms）
SELECT a.id, a.title, a.content_hash, a.update_time,
       substr(a.body, 1, 200) AS snippet
FROM articles_fts f
JOIN articles a ON a.id = f.rowid
WHERE articles_fts MATCH ?
ORDER BY rank
LIMIT 20;

-- 重建索引（cron或每天一次）
INSERT INTO articles_fts(articles_fts) VALUES('rebuild');
```

### 文章详情页数据流

```
用户 GET /article/{hash}
  │
  ▼
路由: 查 hash → article_id
  │  SELECT id FROM articles WHERE content_hash = ?
  │
  ▼
get_article_body(hash, id):
  ├── 检查 IMAGES_DIR/{hash}/final_content.enriched.md → 存在? → source="vision_enriched"
  ├── 不存在? → 检查 IMAGES_DIR/{hash}/final_content.md → 存在? → source="vision_enriched"
  └── 不存在? → SELECT body FROM articles WHERE id=? → source="raw_markdown"
  │
  ▼
图片URL重写: re.sub(r'localhost:8765', '/static/img', md)
  │
  ▼
返回: { hash, title, body_md, images, source, enriched, layer1, layer2 }
```

### 搜索数据流

```
用户 GET /search?q=AI+Agent+框架&mode=default
  │
  ▼
FTS5 MATCH 'AI Agent 框架'
  │  < 10ms
  ▼
返回: [{id, title, hash, snippet, source, layer1}]
  │
  ┌─── 如果 mode=kg ──→ POST /synthesize { question, mode:"kg" }
  │                      ├── kg_synthesize.synthesize_response("AI Agent 框架")
  │                      │     ├── LightRAG hybrid检索
  │                      │     ├── entity canonical mapping
  │                      │     └── DeepSeek合成
  │                      └── 返回 job_id → 轮询结果
  │
  直接返回搜索结果列表
```

### 静态图片服务

```python
from fastapi.staticfiles import StaticFiles
from config import BASE_DIR

IMAGES_DIR = BASE_DIR / "images"  # ~/.hermes/omonigraph-vault/images/

app.mount("/static/img", StaticFiles(directory=str(IMAGES_DIR)), name="images")
```

一行代码替换整个 `python -m http.server 8765`。Caddy只需配置:
```
ohca.ddns.net {
    reverse_proxy /static/img/* localhost:8766
    reverse_proxy /kb/* localhost:8766    
    reverse_proxy /* localhost:3001  # 现有vitaclaw-site
}
```
