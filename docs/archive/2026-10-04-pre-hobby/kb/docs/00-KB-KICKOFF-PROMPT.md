# 知识库 v2 开发启动提示词

> **给新 OpenCode Session 的 GSD 风格指令。** 复制本文档内容作为新 Session 的第一条消息。

---

## 你是谁

你是 **知识库 v2 实现者**。你要在 `/home/sztimhdd/OmniGraph-Vault/kb/` 目录下从零构建一个 **SEO吸铁石文集 + RAG问答引擎** 的极简MVP。

## 项目背景

企小勤（VitaClaw）是一个企业级AI数字员工产品。OmniGraph是它的数据管道，每天刮削微信KOL、知乎、RSS内容，经过LLM分类+实体规范化+LightRAG入库，产出高质量中文AI领域内容。

**知识库的目标：** 把这些内容变成SEO可爬取的静态文集（吸引搜索流量）+ 一个RAG问答引擎（展示产品技术深度）。两者共同把访客转化为企小勤用户。

## 核心设计决策（已锁定，不可修改）

| ID | 决策 | 详情 |
|----|------|------|
| D-01 | 极简MVP | 假设零流量，1周验证，亏也只亏1周 |
| D-04 | Q&A复用kg_synthesize | 调用现有`kg_synthesize.synthesize_response()`，不写新RAG引擎 |
| D-05 | kb/在OmniGraph-Vault仓库内 | 独立Python项目，同仓库同分支（master） |
| D-08 | Python Jinja2 SSG | 不用Astro/Next.js，纯Python+Jinja2生成静态HTML |
| D-11 | 双独立入口 | 快速检索(FTS5, <10ms) + 深度问答(kg_synthesize, 3-10s) |
| D-13 | 部署在Hermes | 同ECS，uvicorn :8766，Caddy反代 |
| D-14 | 混合内容源 | SQLite列表查询，final_content.md优先，articles.body fallback |
| D-15 | FastAPI :8766 | 4个核心endpoint约束 |
| D-18 | 默认FTS5搜索 | ?mode=kg 才走LightRAG |
| D-20 | URL用content_hash | md5[:10]作为URL标识符，没有预计算hash的从body内容计算 |

## 仓库结构（创建后）

```
/home/sztimhdd/OmniGraph-Vault/kb/
├── pyproject.toml          # 独立Python项目配置
├── requirements.txt        # FastAPI, Jinja2, uvicorn, python-markdown等
├── config.py               # KB配置（路径、端口、DB路径等）
├── export_knowledge_base.py  # KB-1: SSG导出脚本
├── api.py                  # KB-3: FastAPI后端
├── templates/              # Jinja2 HTML模板
│   ├── base.html           # 基模板：顶栏+导航+页脚+CTA
│   ├── index.html          # 首页：主题卡片+最新文章+实体云+问答CTA
│   ├── article.html        # 文章详情：面包屑+内容+侧栏+AI问答CTA
│   ├── topic.html          # 主题Pillar页
│   ├── entity.html         # 实体页：描述+关联文章+相关实体
│   └── ask.html            # 问答页：React岛屿容器
├── static/                 # CSS/JS静态资源（后复制到output/）
│   └── style.css
├── output/                 # SSG构建产出（Caddy直接serve）
│   ├── index.html
│   ├── articles/{hash}.html
│   ├── topics/{slug}.html
│   ├── entities/{slug}.html
│   ├── ask/index.html
│   ├── assets/style.css
│   ├── sitemap.xml
│   └── robots.txt
└── README.md               # 项目说明
```

## 数据源（已验证可用）

### SQLite: `OmniGraph-Vault/data/kol_scan.db`

关键统计：
| 表 | 记录数 | 说明 |
|----|--------|------|
| articles | 756 | KOL文章，283篇body>200字 |
| articles (L2=ok) | 81 | 最高质量文章 |
| articles (L1=candidate) | 110 | 候选文章 |
| rss_articles | 1687 | RSS源文章，437篇body>200字 |
| extracted_entities | 5201 | 文章-实体关联 |
| entity_canonical | 13 | 规范化实体 |
| classifications | 756 | 主题分类 |

**articles表关键列：** id, account_id, title, url, digest, update_time, content_hash, enriched, body, layer1_verdict, layer1_reason, layer2_verdict, layer2_reason

**内容选择逻辑：** `layer2_verdict='ok'` 优先，其次 `layer1_verdict='candidate' AND body IS NOT NULL AND length(body)>200`

### 知识图谱: `~/.hermes/omonigraph-vault/lightrag_storage/` (784MB)

### 图片: `~/.hermes/omonigraph-vault/images/` (221个hash目录)

部分hash目录内有 `final_content.md` 或 `final_content.enriched.md`，这些是最高质量的脱稿内容。

### 图片URL重写规则

内容中的 `http://localhost:8765/` 替换为 `/static/img/`：
```python
content = re.sub(r'http://localhost:8765/', '/static/img/', content)
```

## API设计（FastAPI :8766）

| Method | Path | 说明 | 数据源 |
|--------|------|------|--------|
| GET | /articles | 文章列表（分页+筛选） | SQLite |
| GET | /article/{hash} | 文章详情（MD body） | filesystem → SQLite fallback |
| GET | /search?q=&mode= | 搜索（默认FTS5，?mode=kg走LightRAG） | FTS5 / LightRAG |
| POST | /synthesize | 深度问答 | BackgroundTasks → kg_synthesize |
| GET | /synthesize/{job_id} | 问答结果轮询 | in-memory |
| GET | /entities | 实体列表 | SQLite entity_canonical |
| GET | /entity/{name} | 实体详情+关联文章 | SQLite |

### 搜索实现

默认FTS5（<10ms）：
```sql
CREATE VIRTUAL TABLE articles_fts USING fts5(title, body, content='articles', content_rowid='id');
SELECT a.id, a.title, a.content_hash FROM articles_fts f
JOIN articles a ON a.id=f.rowid
WHERE articles_fts MATCH ? ORDER BY rank LIMIT 20;
```

?mode=kg时调用 `omnigraph_search.query.search(query_text, mode="hybrid")`

### 问答实现

异步模式：
- POST /synthesize → 创建BackgroundTask → 返回 202 + job_id
- GET /synthesize/{job_id} → {status: "running"|"done"|"failed", result}
- 内部调用 `kg_synthesize.synthesize_response()`，传入IMAGE_URL_DIRECTIVE

### 图片服务

```python
from fastapi.staticfiles import StaticFiles
IMAGES_DIR = Path.home() / ".hermes" / "omonigraph-vault" / "images"
app.mount("/static/img", StaticFiles(directory=str(IMAGES_DIR)), name="images")
```

### 文章详情逻辑

```python
def get_article_body(hash, article_id):
    for path in [IMAGES_DIR/hash/"final_content.enriched.md",
                 IMAGES_DIR/hash/"final_content.md"]:
        if path.exists():
            md = path.read_text()
            md = re.sub(r'http://localhost:8765/', '/static/img/', md)
            return md, "vision_enriched"
    body = db.execute("SELECT body FROM articles WHERE id=?", [article_id]).fetchone()
    return body[0], "raw_markdown"
```

## 设计Token（继承vitaclaw-site暗色主题）

```css
:root {
  --bg: #0f172a;
  --bg-card: #1e293b;
  --text: #f0f4f8;
  --text-secondary: #94a3b8;
  --accent: #3b82f6;
  --accent-green: #22d3a0;
  --border: rgba(255, 255, 255, 0.1);
  --font-sans: 'Inter', 'Noto Sans SC', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}
```

设计风格：Minimalism & Swiss Style，暗色主题。

卡片样式：`rounded-2xl border border-card-border bg-card p-6 hover:border-accent/30 transition-all duration-300`
CTA按钮：蓝色glow（`.glow`）或绿色glow（`.glow-green`）

## HTML模板规范

- `<html lang="zh-CN">`
- 每页：og:title, og:description, og:image, og:type
- 文章页：JSON-LD Article schema + BreadcrumbList
- 主题页：CollectionPage schema
- 实体页：Thing schema
- 问答页：FAQPage schema
- 引号：`&ldquo;` / `&rdquo;` HTML实体

## 要import的现有模块（契约）

开发时你需要从OmniGraph-Vault根目录import以下模块。**不要修改它们的签名：**

1. `kg_synthesize.synthesize_response(query_text, mode)` — 问答引擎核心
2. `omnigraph_search.query.search(query_text, mode)` — LightRAG检索
3. `config.py` → BASE_DIR, RAG_WORKING_DIR, BASE_IMAGE_DIR — 路径配置
4. `images/{hash}/final_content.md` + `metadata.json` — 内容文件路径和命名约定

如果必须修改这些契约，commit message必须包含 `BREAKING: kb-contract-X`。

## 实施阶段（按顺序执行）

### KB-1: 导出脚本 + Jinja2模板（2天）

**目标：** 构建 `export_knowledge_base.py`，读取SQLite生成静态HTML到 `kb/output/`。

**里程碑检查点：**
- [ ] `python kb/export_knowledge_base.py` 成功运行，生成 `kb/output/index.html` + 至少81篇文章页
- [ ] 每篇文章URL格式为 `/articles/{content_hash}.html`（content_hash为md5[:10]，无hash的从body计算）
- [ ] 图片URL已重写（`http://localhost:8765/` → `/static/img/`）
- [ ] 页面设计符合暗色主题Token
- [ ] JSON-LD Article schema出现在文章页
- [ ] 本地 `python -m http.server 8080 -d kb/output` 可以正常浏览首页和文章页

### KB-2: 实体索引 + SEO（2天）

**目标：** 构建实体→文章索引，生成JSON-LD、sitemap.xml、robots.txt。

**里程碑检查点：**
- [ ] 实体页 `/entities/{slug}.html` 生成完毕
- [ ] 主题Pillar页 `/topics/{slug}.html` 生成完毕
- [ ] sitemap.xml 包含所有文章+实体+主题URL
- [ ] robots.txt 正确配置
- [ ] 内部链接网络完整：article↔entity↔topic
- [ ] JSON-LD结构化数据出现在每种页面类型

### KB-3: FastAPI后端 + 问答UI（2天）

**目标：** 构建FastAPI :8766后端和React问答UI岛屿。

**里程碑检查点：**
- [ ] `uvicorn kb.api:app --port 8766` 成功启动
- [ ] GET /articles 返回文章列表（分页）
- [ ] GET /article/{hash} 返回文章详情（含MD内容）
- [ ] GET /search?q=test&mode=fts FTS5搜索正常返回（<10ms）
- [ ] GET /search?q=test&mode=kg LightRAG搜索正常返回
- [ ] POST /synthesize 返回202 + job_id
- [ ] GET /synthesize/{job_id} 轮询正常
- [ ] 图片通过 /static/img/ 正常访问
- [ ] 问答页UI正常：输入→loading→Markdown答案→源文章链接

### KB-4: 部署上线（1天）

**目标：** 部署到Hermes ECS，配置Caddy，设置cron。

**里程碑检查点：**
- [ ] FastAPI systemd service 运行正常
- [ ] Caddy反代 /kb/* → :8766 正常
- [ ] Caddy反代 /static/img/* → :8766 正常
- [ ] 每日cron任务触发export重建
- [ ] 浏览器访问 https://ohca.ddns.net/kb/ 正常显示首页
- [ ] 搜索功能正常
- [ ] 问答功能正常

## 关键文件路径

| 文件 | 路径 | 说明 |
|------|------|------|
| PRD | `/home/sztimhdd/vitaclaw-site/.planning/MILESTONE-v2-KNOWLEDGEBASE-PRD.md` | 完整产品需求文档 |
| 架构 | `/home/sztimhdd/vitaclaw-site/.sisyphus/notepads/knowledge-base-v2/architecture.md` | 数据流+API+页面布局 |
| 决策 | `/home/sztimhdd/vitaclaw-site/.sisyphus/notepads/knowledge-base-v2/decisions.md` | D-01~D-20所有决策 |
| KB-1 Prompt | `/home/sztimhdd/vitaclaw-site/.planning/v2-knowledgebase/KB-1-PROMPT.md` | 导出脚本详细规格 |
| KB-2 Prompt | `/home/sztimhdd/vitaclaw-site/.planning/v2-knowledgebase/KB-2-PROMPT.md` | 实体索引+SEO规格 |
| KB-3 Prompt | `/home/sztimhdd/vitaclaw-site/.planning/v2-knowledgebase/KB-3-PROMPT.md` | FastAPI+问答UI规格 |
| KB-4 Prompt | `/home/sztimhdd/vitaclaw-site/.planning/v2-knowledgebase/KB-4-PROMPT.md` | 部署规格 |
| SQLite DB | `/home/sztimhdd/OmniGraph-Vault/data/kol_scan.db` | 文章+分类+实体数据 |
| kg_synthesize | `/home/sztimhdd/OmniGraph-Vault/kg_synthesize.py` | 问答引擎核心 |
| 搜索模块 | `/home/sztimhdd/OmniGraph-Vault/omnigraph_search/query.py` | LightRAG检索 |
| 配置 | `/home/sztimhdd/OmniGraph-Vault/config.py` | 路径配置(BASE_DIR等) |
| 图片目录 | `~/.hermes/omonigraph-vault/images/` | 文章图片(221个hash目录) |
| LightRAG | `~/.hermes/omonigraph-vault/lightrag_storage/` | 知识图谱(784MB) |

## 需要注意的数据问题

1. **content_hash覆盖率低**：仅10/756篇articles有预计算content_hash。对于没有hash的文章，export脚本需要从body内容计算MD5[:10]作为fallback。
2. **entity_buffer本地仅1个文件**：export脚本应主要从SQLite的`extracted_entities`和`entity_canonical`表获取实体数据，不依赖entity_buffer JSON文件。
3. **canonical_map.json不在本地repo**：不在本地开发环境。使用`entity_canonical`表替代。
4. **layer2_verdict='ok'仅有81篇**：这是最高质量内容，首页优先展示。但也应展示`layer1_verdict='candidate'`且有body的文章。

## 不要做的事

- ❌ 不要修改OmniGraph-Vault仓库中kb/以外的任何文件
- ❌ 不要调用Cognee（已废弃）
- ❌ 不要创建tailwind.config.js
- ❌ 不要用TypeScript/React/Vite/Astro——这是纯Python项目
- ❌ 不要构建企业平台架构（微服务、消息队列等）
- ❌ 不要实现登录/注册/权限系统（完全公开，零门槛D-07）
- ❌ 不要在新Session开始时重新做规划——规划已锁定，直接实现
- ❌ 不要用`as any`、`@ts-ignore`、`@ts-expect-error`
- ❌ 不要复制图片到kb/目录——通过FastAPI StaticFiles直接serve

## 第一步行动

1. `cd /home/sztimhdd/OmniGraph-Vault && mkdir -p kb/{templates,static,output/articles,output/topics,output/entities,output/ask,output/assets}`
2. 创建 `kb/config.py` — 配置常量（DB路径、图片路径、输出路径等）
3. 创建 `kb/export_knowledge_base.py` — SSG导出脚本（KB-1）
4. 创建 `kb/templates/base.html` — Jinja2基模板
5. 验证：运行export脚本，确认output/生成正确

**开始吧。从KB-1开始，按顺序实现。每个里程碑完成后停下来汇报。**