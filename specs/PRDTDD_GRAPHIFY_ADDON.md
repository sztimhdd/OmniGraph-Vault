# OMNIGRAPH_PRD_v3.0.md

> **产品形态：Skill（Hermes + OpenClaw），非 MCP**
> **受众：** Claude Code — implement from this document as single source of truth.
> **仓库：** [OmniGraph-Vault](https://github.com/sztimhdd/OmniGraph-Vault)
> **状态：** Design complete — ready for Week 1 implementation.

---

## 1. Product Overview

### 1.1 What This Is

OmniGraph-Vault 交付两个 **Skill**，运行在 **Hermes** 和 **OpenClaw** 平台上。它们回答：

> *"我知道 OpenClaw 为什么设计了 streaming tool output（来自知识层的微信文章）。现在给我看它怎么实现的——具体函数、调用者、依赖链。"*

### 1.2 两个核心 Skill

```
┌─────────────────────────────────────────────────┐
│                                                 │
│   graphify_skill                 omnigraph_search│
│   ─────────────                  ─────────────── │
│   平台：Hermes + OpenClaw        平台：Hermes+OpenClaw│
│   来源：Graphify 原生 install    来源：自研（唯一新开发）│
│   工作量：零                     工作量：需开发       │
│   功能：代码图谱查询              功能：知识层查询      │
│   · 调用链                       · 设计意图          │
│   · 依赖关系                     · 使用指南          │
│   · 节点详情                     · 最佳实践          │
│   · 最短路径                     · 踩坑经验          │
│   后端：Graphify 图谱引擎         后端：RAG Engine     │
│                                  Corpora (Agent     │
│                                  Engine)           │
└─────────────────────────────────────────────────┘
```

### 1.3 Target User

**用户：Hermes / OpenClaw 平台上的 AI Agent。** 典型终端用户是开发者，但直接调用 Skill 的是 Agent 本身——Agent 自主决策调用 `graphify_skill` 还是 `omnigraph_search`（或者两者组合），然后合成答案返回给开发者。

### 1.4 Competitive Positioning

| Competitor | What It Offers | OmniGraph Advantage |
|------------|---------------|---------------------|
| **Context7** | API docs lookup | + 微信文章的设计意图 + 图结构因果推理 |
| **Tavily** | Web search | 微信封闭生态——内容仅通过我们的手动摄入可获得 |
| **Sourcegraph Cody** | Code search + jump-to-def | + 跨项目语义匹配 + 文章→代码桥接 |

**USP：** 当 Agent 收到 "OpenClaw 的 streaming tool output 怎么实现" 时，它从两个 Skill 获得四层信息：(a) 设计理由（领域文章），(b) 精确函数签名（代码图谱），(c) 调用链遍历，(d) 跨项目对比（OpenClaw vs Hermes）。无竞品能组合这四层。

### 1.5 Core Metric

**Agent 在 OpenClaw/Hermes 实现任务上的代码质量提升**——定性衡量：架构一致性、API 行为幻觉减少、集成模式正确。

---

## 2. Architecture

### 2.1 Dual-Graph / Dual-Skill Design

```
           Hermes / OpenClaw Agent
           /                      \
    graphify_skill          omnigraph_search
    (Graphify 原生)         (自研，RAG Engine 后端)
         │                        │
┌────────┴────────┐      ┌────────┴────────┐
│   Code Graph     │      │  Domain Graph    │
│  (Graphify JSON) │      │  (Agent Engine   │
│                  │      │   RAG Corpora)   │
│ • Function nodes │      │                  │
│ • Class hierarchy│      │ • Design intent  │
│ • Call chains    │      │ • Usage guides   │
│ • Module deps    │      │ • Best practices │
│ • Import graphs  │      │ • Pitfalls       │
└─────────────────┘      │ • Concept links  │
                          └──────────────────┘
                                   │
                          ┌────────┴────────┐
                          │  Bridge Nodes    │
                          │  (future Phase)  │
                          │  pre-link domain │
                          │  concepts → code │
                          │  entities        │
                          └─────────────────┘
```

### 2.2 Why Two Skills, Not One

| Decision | Reasoning |
|----------|-----------|
| **Separate storage** | 领域实体（观点、论据）和代码实体（函数、类）使用不同的语法空间。合并产生语义噪音。 |
| **Separate skills** | Agent 为不同任务选择正确的 skill。混合查询由 Agent 组合完成，不经我们的管线。 |
| **Physical separation** | Graphify 输出 graph.json；RAG Engine 管理 Corpora。无共享数据库，无耦合。 |

### 2.3 Agent Autonomous Routing Logic

```
用户在 Hermes/OpenClaw 中：
"openclaw streaming tool output 怎么实现"
    ↓
Agent 自主决策调用：
  graphify_skill    → 代码结构/调用链（语法层）
  omnigraph_search  → 设计意图/最佳实践（语义层）
    ↓
合并两路结果 → 回答
```

**具体推理链：**

```
1. "我需要设计理由" → omnigraph_search("streaming tool output 设计")
   → 返回：解释 AsyncGenerator 选择、性能权衡的微信文章
2. "已有设计。找实现" → graphify_skill.get_node("stream_query")
   → 返回：函数签名、文件路径、docstring
3. "谁调用了这个？" → graphify_skill.get_neighbors("stream_query")
   → 返回：调用者（agent_loop, router）+ 被调用者（token_stream, response_builder）
4. 综合 → Agent 用 Rust/Tokio 实现
```

---

## 3. Skill Specifications

### 3.1 `graphify_skill`（Graphify 原生，零开发）

**安装方式：**
```bash
# 在 Hermes 上
graphify install --platform hermes

# 在 OpenClaw 上
graphify install --platform claw
```

**暴露的查询能力：**

| Capability | Description | Agent Use Case |
|-----------|-------------|----------------|
| `query_graph` | 自然语言图谱搜索 | "找所有 auth 相关函数" |
| `get_node` | 按 ID 获取单个节点 | "stream_query 的签名是什么" |
| `get_neighbors` | 入边 + 出边 | "谁调用了 stream_query，它调用了谁" |
| `shortest_path` | 两点间 BFS | "auth 怎么连到 agent loop" |

**Node Schema (from Graphify output):**

```json
{
  "id": "openclaw::router::Router::route",
  "type": "function",
  "name": "route",
  "file": "src/router.ts",
  "line": 145,
  "signature": "async route(request: Request): Promise<Response>",
  "docstring": "Routes incoming tool requests to registered handlers.",
  "language": "typescript",
  "parent": "openclaw::router::Router"
}
```

**Edge Schema:**

```json
{
  "source": "openclaw::agent_loop::execute",
  "target": "openclaw::router::Router::route",
  "type": "calls"
}
```

### 3.2 `omnigraph_search` Skill（自研，需开发）

**唯一需要新写的 skill。** 后端对接 RAG Engine Corpora（Agent Engine）。

**SKILL.md 骨架：**

```markdown
---
name: omnigraph_search
description: Search OmniGraph domain knowledge — design intent, guides, best practices, pitfalls for OpenClaw/Hermes development.
platforms: [hermes, openclaw]
---

# OmniGraph Search

Query OmniGraph-Vault's domain knowledge graph for design rationale,
usage patterns, and implementation guidance.

## When to Use

Use this skill when the user asks:
- "Why was X designed this way?"
- "What's the best practice for Y?"
- "How does OpenClaw handle Z?"
- "What are the pitfalls when integrating A with B?"

## Behavior

1. Accept a natural-language query from the user/agent.
2. Call the RAG Engine Corpora API:
   POST /api/v1/rag/search
   { "query": "<query>", "top_k": 5 }
3. Return the top 5 results with source attribution (WeChat article title, date, URL).
4. For cross-article questions, compose a synthesis from multiple sources.

## Integration

This skill is called by the Hermes/OpenClaw agent autonomously.
The agent may also call `graphify_skill` in the same session for
code-structure queries.
```

**RAG Engine API Contract:**

```
POST /api/v1/rag/search
Content-Type: application/json

{
  "query": "streaming tool output design rationale",
  "top_k": 5,
  "mode": "hybrid"
}

Response:
{
  "results": [
    {
      "score": 0.89,
      "content": "OpenClaw 选择 AsyncGenerator...",
      "source": {
        "title": "OpenClaw 架构深度解析",
        "url": "https://mp.weixin.qq.com/s/...",
        "date": "2026-03-15"
      },
      "entities": ["AsyncGenerator", "streaming", "tool output"]
    }
  ]
}
```

---

## 4. Data Design

### 4.1 Storage Layout

```
~/.hermes/omonigraph-vault/
├── graphify/                    # Graphify working directory
│   ├── repos/                   # Cloned T1 repositories
│   │   ├── openclaw/           # git clone cache
│   │   └── claude-code/        # git clone cache
│   └── graph.json               # Built code graph
│
├── lightrag_storage/            # Existing (LightRAG → migrating to
│                                 # Agent Engine RAG Corpora)
├── enrichment/                  # Existing: Zhihu enrichment
└── images/                      # Existing: Article images
```

### 4.2 T1 Repository Scope

| Repository | URL | Reason | Priority |
|-----------|-----|--------|:--------:|
| openclaw | `https://github.com/openclaw/openclaw` | Core framework — Rust fork's primary reference | P0 |
| claude-code | `https://github.com/anthropics/claude-code` | Claude Code internals | P0 |

**Expansion rule:** Add only when Agent manually searches source ≥3 times in one session. Never pre-emptively add T3 repos — marginal utility → 0.

### 4.3 Update Strategy

```
cron: 0 3 * * 0  (weekly Sunday 3am)
command: graphify refresh && graphify build
```

- **Frequency:** 5-10 commits/week. Weekly captures feature changes without excessive compute.
- **Atomic swap:** Build to `graph.json.tmp` → validate → `mv graph.json.tmp graph.json`.

---

## 5. Implementation Plan

### 5.1 Week 1 Deliverables

| # | Deliverable | Verification |
|---|------------|-------------|
| 1 | `graphify install --platform hermes` 跑通 | Hermes `skills list` 显示 `graphify` |
| 2 | `graphify install --platform claw` 跑通 | OpenClaw `skills list` 显示 `graphify` |
| 3 | `omnigraph_search` SKILL.md 骨架 | Skill 文件存在，Agent 可发现 |
| 4 | `omnigraph_search` 调用 RAG Engine API | `/api/v1/rag/search` 返回结果 |
| 5 | 端到端测试：用户提问 → Agent 调用两个 skill → 合并回答 | 用 Demo 1 场景验证 |

### 5.2 Phase 1: Graphify Skill Installation (Week 1, Day 1-2)

```bash
# Step 1: Build code graph for T1 repos
graphify clone https://github.com/openclaw/openclaw
graphify clone https://github.com/anthropics/claude-code
graphify build                          # → graph.json

# Step 2: Install as Hermes skill
graphify install --platform hermes

# Step 3: Install as OpenClaw skill
graphify install --platform claw

# Step 4: Verify
hermes skills list | grep graphify       # Expected: graphify_skill | enabled
claw skills list | grep graphify         # Expected: graphify_skill | enabled
```

### 5.3 Phase 2: omnigraph_search Skill (Week 1, Day 3-4)

**唯一的新开发工作。** 创建 `skills/omnigraph_search/SKILL.md` 和关联的 API 适配器。

| # | Task | File | Verify |
|---|------|------|--------|
| 1 | 创建 SKILL.md | `skills/omnigraph_search/SKILL.md` | 语法检查通过 |
| 2 | 创建 API 适配器 | `skills/omnigraph_search/search.py` | 独立脚本可调 RAG Engine |
| 3 | Skill 注册 | 按 Hermes/OpenClaw skill 注册流程 | `skills list` 可见 |
| 4 | 单元测试 | `tests/test_omnigraph_search.py` | pytest 通过 |

### 5.4 Phase 3: Weekly Cron (Week 2)

| # | Task | Verify |
|---|------|--------|
| 1 | 创建 `scripts/graphify-refresh.sh` | `bash -n` 通过 |
| 2 | 注册 cron job | `crontab -l` 可见 |
| 3 | 模拟刷新 | 手动跑脚本，验证 graph.json 时间戳更新 |

### 5.5 Phase 4: Bridge Nodes (Future — Not In Scope Now)

当领域图谱实体引用了具体代码符号（如微信文章讨论 `OpenClaw.Router`），预计算跨图谱链接：

```
Domain Graph                          Code Graph
─────────────                         ──────────
Entity: "Router"  ────bridge────→    Node: openclaw::router::Router
  metadata: {                           type: class
    code_ref: "openclaw::router::Router"
  }
```

桥接节点消除 Agent 在两个 skill 间路由时的猜测成本。延期至 Phase 1-2 验证通过后实施。

---

## 6. Integration Details

### 6.1 Skill Registration

`graphify_skill` 和 `omnigraph_search` 按各平台的 Skill 注册流程安装：

```
# Hermes
skills:
  external_dirs:
    - /path/to/graphify/skills          # graphify install 自动配置
    - /home/sztimhdd/OmniGraph-Vault/skills   # omnigraph_search

# OpenClaw
claw skills register /path/to/graphify/claw-skill
claw skills register /home/sztimhdd/OmniGraph-Vault/skills/omnigraph_search
```

### 6.2 Weekly Cron Job

```bash
# scripts/graphify-refresh.sh
#!/bin/bash
set -euo pipefail

GRAPHIFY_DIR="$HOME/.hermes/omonigraph-vault/graphify"
cd "$GRAPHIFY_DIR"

# Refresh git clones
for repo in repos/*/; do
    (cd "$repo" && git pull --ff-only) || echo "WARN: $repo pull failed, using stale"
done

# Rebuild graph (atomic)
graphify build --output graph.json.tmp
python3 -c "
import json
with open('graph.json.tmp') as f:
    g = json.load(f)
assert len(g['nodes']) > 100, 'Graph too small, refusing to swap'
"
mv graph.json.tmp graph.json
```

### 6.3 Cron Registration

```bash
(crontab -l 2>/dev/null; echo "0 3 * * 0 $HOME/OmniGraph-Vault/scripts/graphify-refresh.sh") | crontab -
```

---

## 7. Test & Acceptance Strategy

### 7.1 Unit Tests

`omnigraph_search` skill 的 API 适配器需要 pytest 覆盖：
- RAG Engine API 调用（mock 响应）
- 结果格式化（entity 字段、source 引用）
- 错误处理（API 不可用时的降级）

### 7.2 Demo Scenario 1: Streaming Tool Output

> **Task:** Implement OpenClaw-style streaming tool output in the Rust fork.

```yaml
setup:
  - omnigraph_search has WeChat articles about OpenClaw architecture
  - graphify_skill installed with fresh graph.json

expected_agent_behavior:
  1. "I need context" → calls omnigraph_search("streaming tool output design")
  2. "I have the why. Now the how" → calls graphify_skill.get_node("stream_query")
  3. "Who interacts with this?" → calls graphify_skill.get_neighbors("stream_query")
  4. Combines results → produces Rust/Tokio implementation consistent with OpenClaw's design

acceptance:
  - Code structure mirrors OpenClaw (AsyncGenerator → Tokio Stream)
  - No hallucinated API signatures (all from get_node output)
  - Integration points correct (from get_neighbors call-chain)
```

### 7.3 Demo Scenario 2: Self-Evolution Integration

> **Task:** Add Hermes-style self-evolution to the Rust fork.

```yaml
expected_agent_behavior:
  1. calls omnigraph_search("hermes self evolution genetic optimizer prompt")
     → Returns: article about optimizer selection, parameter tuning, pitfalls
  2. calls graphify_skill.query_graph("evolution optimizer")
     → Returns: genetic_optimizer, prompt_evaluator modules
  3. calls graphify_skill.shortest_path("genetic_optimizer", "agent_loop")
     → Returns: exact files and interfaces to modify for integration
  4. Implements with knowledge of: which libraries, how to integrate, what to avoid

acceptance:
  - Uses libraries recommended in articles (not arbitrarily chosen)
  - Integration follows shortest_path output (modifies correct files)
  - Avoids documented pitfalls (e.g., "don't use population_size > 50" from article)
```

### 7.4 Acceptance Gate

```
[ ] graphify_skill installed and functional on Hermes
[ ] graphify_skill installed and functional on OpenClaw
[ ] omnigraph_search SKILL.md exists and skill is discoverable
[ ] omnigraph_search calls RAG Engine API and returns results
[ ] Agent autonomously uses both skills in Demo 1 (streaming output)
[ ] Agent autonomously uses both skills in Demo 2 (self-evolution)
[ ] Code output architecturally consistent with OpenClaw/Hermes
[ ] Weekly cron successfully rebuilds graph.json
```

---

## 8. Design Decisions Log

| ID | Decision | Rationale |
|----|----------|-----------|
| D-G01 | Skill over MCP | Hermes/OpenClaw 原生支持 skill；消除 MCP wrapper 维护负担。 |
| D-G02 | graphify_skill zero-code | Graphify 原生 `install --platform hermes/claw` 无需任何适配。 |
| D-G03 | Separate storage from domain graph | 代码和领域实体使用不同语法；合并产生噪音。 |
| D-G04 | T1 only (openclaw + claude-code) | T2/T3 的边际效用接近零。Agent 很少查询它们。 |
| D-G05 | Weekly cron, not per-commit | 每周 5-10 次提交足够跟踪 feature。逐次提交的 rebuild 浪费算力。 |
| D-G06 | Atomic graph swap (tmp → rename) | 防止 skill 读到半写状态的 graph.json。 |
| D-G07 | Bridge nodes deferred to Phase 3 | Agent 在 Phase 1-2 中自主路由；桥接节点是优化项而非硬需求。 |
| D-G08 | No Rust fork in graph | Fork 是正在构建的产品，不是知识来源。图谱只涵盖参考实现。 |
| D-G09 | omnigraph_search 对接 RAG Engine | Agent Engine Corpora 已经是知识层存储；不重复建设。 |
| D-S10 | OpenClaw as first-class platform | 与 Hermes 地位等同。skill 注册流程双平台兼容。 |

---

## 9. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|:----------:|:------:|------------|
| Graphify skill 接口不稳定 | Low | Skill 失效 | Pin Graphify 版本 |
| Weekly cron 静默失败 | Medium | 过期图谱 | Refresh 脚本加最小节点数断言 |
| Agent 不自主同时使用两个 skill | Medium | 丧失跨图谱优势 | Demo 场景测试；必要时加桥接节点 |
| openclaw/claude-code 仓库改名/迁移 | Low | `git pull` 断 | Cron 容忍 pull 失败，保留旧图谱 |
| Graph JSON 超出 skill context | Low | 查询超时 | 监控文件大小；>10MB 加节点过滤 |
| RAG Engine API 不可用 | Low | omnigraph_search 返回空 | Skill 返回错误提示，不阻塞 Agent |

---

## 10. Appendix: Graphify Quick Reference

```bash
# 安装
pip install graphify

# 克隆 + 建图
graphify clone https://github.com/openclaw/openclaw
graphify clone https://github.com/anthropics/claude-code
graphify build                          # → graph.json

# 安装为 Skill
graphify install --platform hermes      # 一键安装到 Hermes
graphify install --platform claw        # 一键安装到 OpenClaw

# 更新
graphify refresh                        # git pull 所有克隆
graphify build                          # 重建图谱
```

**graphify_skill 能力：** `query_graph`, `get_node`, `get_neighbors`, `shortest_path`

---

*Document version: 3.0 · 2026-04-27*
*产品形态：Skill（Hermes + OpenClaw），非 MCP*
