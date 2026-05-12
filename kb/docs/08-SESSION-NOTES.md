# 知识库 v2 讨论纪要

> 本文档记录了vitaclaw-site Sisyphus orchestrator session中关于知识库v2的完整讨论历程。
> OmniGraph agent请务必阅读 `00-KB-KICKOFF-PROMPT.md` 作为开发启动指令，本文档提供补充上下文。

---

## 1. 项目起源

用户要求：**"帮我起一个ULW把部署在阿里云上的omnigraph项目吃透，阅读我们项目的全部文档理解我们下一步的集成目标 - 建立Agent框架的SEO吸铁石 高质量内容知识库。输出完整的milestone PRD，计划，知识库Web设计"**

核心理念：**"我们刮削下来的文章全部本地化编纂成文集作为SEO磁铁，同时提供一个RAG问答引擎吸引技术用户"**

知识库 = 两个产品合为一体：
1. **SEO吸铁石文集** — 搜索引擎可爬取的静态文集，吸引搜索流量
2. **RAG问答引擎** — 互动式知识图谱问答，展示技术深度

---

## 2. 关键讨论决策过程

### 2.1 技术栈选择
- **否决方案：** Astro / Next.js / Vite SPA扩展 — 原因：复杂度高，与现有Python生态脱节
- **采纳方案：** Python Jinja2 SSG + FastAPI — 原因：极简MVP，假设零流量，与OmniGraph代码无缝集成

### 2.2 项目位置
- **否决方案：** 在vitaclaw-site仓库内创建kb/子目录 — 原因：不同技术栈（Python vs TypeScript），不同构建流程
- **否决方案：** 独立仓库 — 原因：需要直接import OmniGraph的kg_synthesize、omnigraph_search等模块
- **采纳方案：** OmniGraph-Vault仓库内kb/目录 — 原因：直接import现有模块，同一仓库同一分支（master）

### 2.3 Q&A引擎方案
- **否决方案：** 新写RAG引擎 — 原因：重复造轮子，kg_synthesize已生产验证
- **采纳方案：** 包装现有`kg_synthesize.synthesize_response()` — 只需~50行Python

### 2.4 搜索架构
- **双入口设计（D-11）：**
  - **快速检索：** SQLite FTS5，<10ms响应，默认模式
  - **深度问答：** kg_synthesize（LightRAG图谱检索+DeepSeek综合），3-10秒，异步模式
  - 两者独立，不合并

### 2.5 部署架构
- FastAPI uvicorn :8766，Caddy反向代理
- 与OmniGraph同ECS（Hermes服务器 ohca.ddns.net）
- 图片服务通过FastAPI StaticFiles（取代python -m http.server 8765）

### 2.6 Hermes依赖讨论
用户和OmniGraph agent曾讨论是否需要Hermes服务器作为必要条件。结论：**知识库代码不依赖Hermes运行才能开发，但部署需要Hermes。开发可以在本地进行（SQLite + lightrag_storage都在本地）。**

### 2.7 Git策略
- kb/目录全量新增文件，不修改OmniGraph现有代码
- 直接提交到master分支，不创建新分支
- 零合并冲突风险

---

## 3. 与OmniGraph Agent的协调

### 4个契约（不可单方面修改）

| # | 契约 | 位置 | 说明 |
|---|-------|------|------|
| 1 | `kg_synthesize.synthesize_response(query_text, mode)` 签名 | `kg_synthesize.py` | KB API调用此函数进行深度问答 |
| 2 | `omnigraph_search.query.search(query_text, mode)` 签名 | `omnigraph_search/query.py` | KB API调用此函数进行LightRAG搜索 |
| 3 | `kol_scan.db` 表结构 | `data/kol_scan.db` | articles, classifications, extracted_entities, entity_canonical, ingestions |
| 4 | `images/{hash}/final_content.md` + `metadata.json` 路径与命名 | `~/.hermes/omonigraph-vault/images/` | 文章富内容文件路径 |

如果OmniGraph agent必须修改某个契约，commit message必须包含 `BREAKING: kb-contract-X` 以便KB代码可以相应更新。

### 本次提交说明

本次提交**仅新增文件**（kb/docs/），**不修改任何现有OmniGraph代码**。KB的实现代码将在后续提交中逐步加入kb/目录。

---

## 4. 数据源验证结果

在vitaclaw-site session中实际验证了本地开发环境的数据可用性：

| 数据 | 路径 | 状态 | 数量 |
|------|------|------|------|
| SQLite数据库 | `data/kol_scan.db` | ✅ 本地存在 | 756篇KOL文章，1687篇RSS文章 |
| 高质量文章(L2=ok) | articles表 | ✅ 可查询 | 81篇 |
| 有body的文章 | articles表 | ✅ 可查询 | 283篇(body>200字)，437篇RSS |
| 实体关联 | extracted_entities表 | ✅ 可查询 | 5201条 |
| 规范化实体 | entity_canonical表 | ✅ 可查询 | 13条 |
| 分类数据 | classifications表 | ✅ 可查询 | 756条 |
| 图片哈希目录 | `~/.hermes/omonigraph-vault/images/` | ✅ 本地存在 | 221个目录 |
| LightRAG知识图谱 | `~/.hermes/omonigraph-vault/lightrag_storage/` | ✅ 本地存在 | 784MB |
| content_hash字段 | articles.content_hash | ⚠️ 仅10/756有值 | 需在export时从body计算fallback |

### 已知数据问题
1. **content_hash覆盖率低**：仅10/756篇有预计算content_hash（D-20决策：URL使用md5[:10]）。export脚本需从body内容计算MD5[:10]作为fallback。
2. **entity_buffer本地仅1个JSON文件**：export脚本应主要从SQLite的`extracted_entities`和`entity_canonical`表获取实体数据。
3. **canonical_map.json不在本地仓库**：不在开发环境，使用`entity_canonical`表替代。

---

## 5. 设计风格

继承vitaclaw-site暗色主题：
- 背景：#0f172a（深蓝黑）
- 卡片：#1e293b
- 文字：#f0f4f8
- 强调蓝：#3b82f6
- 强调绿：#22d3a0
- 字体：Inter + Noto Sans SC
- 风格：Minimalism & Swiss Style

卡片样式：`rounded-2xl border border-card-border bg-card p-6 hover:border-accent/30 transition-all duration-300`
CTA按钮：蓝色glow（`.glow`）或绿色glow（`.glow-green`）

---

## 6. 文档索引

| 编号 | 文件 | 内容 |
|------|------|------|
| 00 | `KB-KICKOFF-PROMPT.md` | **开发启动提示词**（给新session的第一条消息） |
| 01 | `PRD.md` | 完整产品需求文档（689行） |
| 02 | `DECISIONS.md` | 20项架构决策记录（D-01~D-20） |
| 03 | `ARCHITECTURE.md` | 系统架构图+数据流+API+页面布局+UX设计 |
| 04 | `KB1-EXPORT-SSG.md` | Phase 1：SSG导出脚本+Jinja2模板 |
| 05 | `KB2-ENTITY-SEO.md` | Phase 2：实体索引+JSON-LD+sitemap |
| 06 | `KB3-API-QA.md` | Phase 3：FastAPI后端+React问答UI |
| 07 | `KB4-DEPLOY.md` | Phase 4：部署+上线 |
| 08 | `SESSION-NOTES.md` | 本文档 — 完整讨论纪要 |

---

## 7. 下一步行动

本session（vitaclaw-site planning）的工作已全部完成。以下是OmniGraph agent接手后的执行顺序：

1. **阅读 `00-KB-KICKOFF-PROMPT.md`** — 这是开发启动的完整指令
2. **创建kb/目录结构** — pyproject.toml, config.py, templates/, static/, output/
3. **KB-1: SSG导出脚本** — export_knowledge_base.py + Jinja2模板
4. **KB-2: 实体索引+SEO** — 实体页面, JSON-LD, sitemap.xml
5. **KB-3: FastAPI后端+问答UI** — api.py + React island
6. **KB-4: 部署上线** — systemd, Caddy, cron

每个里程碑完成后停下来汇报验证。