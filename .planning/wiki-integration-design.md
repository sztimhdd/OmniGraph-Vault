# OmniGraph + LLM Wiki Integration Design

> **Date**: 2026-05-08  
> **Author**: Hai + Hermes (调研 & 方向讨论)  
> **Status**: Draft — 待 OmniGraph Agent 评估实施

---

## 1. 调研背景

### 1.1 什么是 LLM Wiki

源自 [Karpathy 的 LLM Wiki 模式](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)，核心洞察：

> 不做 RAG，做 **compounding artifact**。知识编译一次，持续更新，不每次都重新推导。

**三层架构**：
```
raw/        ← 不可变原始来源
wiki/       ← LLM 维护的合成页面（实体、概念、对比、查询结果）
SCHEMA.md   ← 约定 LLM 的行为规范
```

**三个操作**：
- **Ingest**：读源 → 提取关键信息 → 更新 10-15 个 wiki 页面
- **Query**：查 wiki → 合成答案 → **答案也存回 wiki**
- **Lint**：定期查矛盾、断链、过期、gap

### 1.2 nashsu/llm_wiki

GitHub: https://github.com/nashsu/llm_wiki

本质是一个 Tauri 桌面 App（不是 markdown wiki），其 `llm-wiki.md` 是纯概念文档。我们取的是概念模式而非桌面应用。

### 1.3 Hermes 已有 llm-wiki skill

`~/.hermes/skills/research/llm-wiki/SKILL.md` — 完整的 wiki 构建/维护流程（SCHEMA、index/log、ingest/query/lint 操作）。可直接用于驱动 OpenClaw Agent 维护 wiki。

---

## 2. 当前代码状态

### 2.1 OmniGraph 现有架构

```
用户 (WeChat/Telegram)
  → Hermes Agent
    → omnigraph_query / omnigraph_search (skill 层)
      → kb/api.py (FastAPI, port 8766)
        ├─ /api/search          → FTS5 trigram (kb/services/search_index.py)
        ├─ /api/synthesize      → kg_synthesize (LightRAG + LLM, 异步 job)
        ├─ /api/articles        → 文章列表/详情
        └─ kb/api_routers/*     → 路由
      → kb/templates/*.html      → Jinja2 Web UI
        ├─ entity.html          → 实体页（仅名字+文章列表，无合成内容）
        ├─ topic.html           → 主题页（仅描述+文章列表）
        ├─ index.html           → 首页
        └─ ask.html             → Q&A 界面
```

### 2.2 Wiki 层（新建）

```
~/wiki-omnigraph/
├── SCHEMA.md              ← ✅ 已创建（Agent 行为规范，tag taxonomy）
├── index.md               ← ✅ 已创建（内容目录）
├── log.md                 ← ✅ 已创建（操作日志）
├── entities/
│   └── openclaw.md        ← ✅ 第一页（6篇原文合成，5763 chars）
├── concepts/
├── comparisons/
├── queries/
└── raw/
```

**openclaw.md 内容覆盖**：核心理念、5层架构拆解、vs Hermes 对比表、生态衍生、安全问题、关键版本。全部标注 `^[article:id]` 来源。

### 2.3 数据库状态（2026-05-08）

| 维度 | 数量 |
|------|------|
| KOL 文章总数 | 653 |
| 有 body 文章 | 294 |
| 成功入库 (LightRAG) | 122 |
| 待入库 (有 body 未处理) | 5 |
| 去重机制 | ingestions 表 (article_id)，579条记录 |
| RSS 文章 | 1625 |
| L1 过滤 | 合理（396/399 skipped 为 L1=reject） |
| L2 过滤 | 仅3篇（兜底拦截 L1 误放，无误杀） |

---

## 3. 整合方向

### 3.1 总体架构

```
┌──────────────────────────────────────────────────┐
│                  终端用户 (WeChat/Telegram)          │
└──────────────────────┬───────────────────────────┘
                       │
              ┌────────▼────────┐
              │   Hermes Agent   │
              │  (对话 + 合成)    │
              └───┬─────────┬───┘
                  │         │
        ┌─────────▼──┐  ┌──▼──────────┐
        │ wiki (md)   │  │ OmniGraph   │
        │ 合成知识层   │  │ 原始数据层   │
        │ • entity页   │  │ • articles  │
        │ • concept页  │  │ • entities  │
        │ • compare页  │  │ • LightRAG  │
        │ • query缓存  │  │ • vector搜索 │
        └──────┬──────┘  └──────┬───────┘
               │                │
               └── 交叉引用 ─────┘
               wiki 来源标注 article:id
               graph 补充 wiki 未覆盖的细节
```

**核心设计决策**：wiki 不是替代 OmniGraph，而是它的**编译产物**。Graph = 数据库，Wiki = 视图。

### 3.2 三个整合角度

#### Angle A: 阅读层 — wiki 交付给终端用户

**问题**：用户没有 Obsidian，wiki 页面无法直接消费。

**方案**：
1. `kb/services/wiki.py` — 读/搜索 wiki 页面（~100 LOC）
2. `kb/api_routers/wiki.py` — REST API（~60 LOC）
3. 模板改造：entity.html / topic.html 改为 **wiki-first 渲染**
   - 有 wiki 页 → 先渲染 wiki 合成内容，再列文章
   - 无 wiki 页 → 保持现有文章列表
4. 首页 index.html 加 "知识专题" wiki 模块
5. Hermes 侧：omnigraph_query 先查 wiki 后查 graph

**用户效果**：
```
现在 /entities/OpenClaw        改造后
  实体名                         ┌──────────────┐
  23篇相关文章                    │ wiki 合成内容  │
  · 文章1 ...                    │ 架构/生态/安全  │
                                 └──────────────┘
                                 相关文章 23篇
```

#### Angle B: 查询层 — wiki 和 synthesize 深度整合

**问题**：kg_synthesize 每次从零推导，已有知识不沉淀。

**方案**：
1. **查前注入**：synthesize 前检查 wiki → 注入 wiki 上下文 → LLM 在已有知识上深化
2. **查后存回**：高质量合成结果 → `queries/` 存为 wiki 页（"答案不消失在 chat history"）
3. **wiki lint**：cron 扫描 wiki → 发现 gap → 自动触发 synthesize 生成草稿
4. **Hermes 对话**：每次有价值的对话合成 → 自动建议存入 wiki

**价值**：从"每次重新搜索"变成"wiki 越用越厚，合成质量越来越高"。

#### Angle C: 入库层 — 新文章触发 wiki 更新

**问题**：cron 入库后只存 graph，wiki 不感知。

**方案**：
1. `batch_ingest_from_spider.py` 末尾加 `_wiki_update_check()` hook
2. Hook 逻辑：提取实体/主题 → 查 wiki → 
   - 已有相关 page → 生成更新建议（存入 `_suggestions/`）
   - entity 频率够但无 page → 建议新建
3. 异步执行，不阻塞入库
4. 用户端：cron 完成后收到 "📝 wiki 更新建议"

**价值**：wiki 不只是"手动一本本写"，而是**跟随数据流自动进化**。

---

## 4. 实施路线图

| 优先级 | 角度 | 描述 | 涉及文件 | 代码量 |
|--------|------|------|----------|--------|
| **P0** | A-5 | Hermes omnigraph_query skill 加"先查 wiki" | `.hermes/skills/omnigraph_query/SKILL.md` | ~20 LOC |
| **P1** | A-1~4 | KB Web UI wiki 整合 | `kb/services/wiki.py`, `kb/api_routers/wiki.py`, `kb/api.py`, `entity.html`, `topic.html`, `index.html` | ~217 LOC |
| **P2** | C | 入库 hook | `batch_ingest_from_spider.py` | ~120 LOC |
| **P3** | B-1,2 | synthesize wiki context 注入 | `kb/services/synthesize.py` | ~60 LOC |
| **P4** | B-3 | lint → 自动补全 | 新 script | ~200 LOC |

---

## 5. 待确认问题

1. **wiki 目录位置**：目前 `~/wiki-omnigraph/`。是否应该放在 OmniGraph-Vault 仓库内（方便 git 版本控制 + PR review）？
2. **wiki 更新策略**：Ingest hook 产生的更新建议——是自动应用还是等人工审阅？
3. **KB Web UI 是否对外**：wiki 页面是否需要认证/权限控制？
4. **第一波 wiki 页面**：OpenClaw 之后，优先补哪些？建议：[[hermes-agent]]、[[harness-engineering]]、[[mcp-protocol]]、[[agent-skills]]

---

## 6. 参考

- [Karpathy LLM Wiki Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki)
- `~/.hermes/skills/research/llm-wiki/SKILL.md`
- `~/wiki-omnigraph/` — 已创建的 wiki 实例
