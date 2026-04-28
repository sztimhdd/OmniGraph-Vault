# Graphify Addon：代码图谱实施计划

> 目标：为 Claude Code 提供 OpenClaw/Hermes 的代码结构查询能力
> 策略：零代码集成 — Graphify 原生 MCP + LightRAG MCP 双 tool 架构
> 用户：Claude Code（AI coding agent），非人类开发者

---

## 架构

```
Claude Code
    │
    ├── search_knowledge ──→ LightRAG MCP  ──→ 领域图谱
    │   (设计意图/指南/最佳实践/概念关系)
    │
    └── lookup_code ───────→ Graphify MCP  ──→ 代码图谱
        (函数调用链/继承/模块依赖)
```

**双 tool 路由逻辑（Claude Code 自主决策）：**

```
"streaming tool output 怎么实现"
  → search_knowledge("streaming tool output 设计") → 拿到设计意图
  → lookup_code get_node("stream_query")           → 拿到具体实现
  → 合并回答
```

---

## Phase 1：T1 覆盖（本周）

### 覆盖仓库

| 仓库 | 原因 | 优先级 |
|------|------|:---:|
| `openclaw/openclaw` | 核心框架，Rust fork 的参照源 | T1 |
| `anthropics/claude-code` | Claude Code 自身架构（理解调用端） | T1 |

### 步骤

```
1. 安装 Graphify
   pip install graphify

2. 克隆 T1 仓库
   graphify clone https://github.com/openclaw/openclaw
   graphify clone https://github.com/anthropics/claude-code

3. 建图
   graphify build

4. 启动 MCP server
   python -m graphify.serve graphify-out/graph.json

5. 注册到 Claude Code（.mcp.json）
   {
     "mcpServers": {
       "lookup_code": {
         "type": "stdio",
         "command": "python3",
         "args": ["-m", "graphify.serve", "graphify-out/graph.json"]
       }
     }
   }

6. 同时注册 LightRAG MCP（已有）
   search_knowledge → OmniGraph-Vault MCP server
```

---

## 暴露的 Tool

### lookup_code（Graphify MCP）

| Tool | 功能 | Claude Code 用在哪 |
|------|------|------|
| `query_graph` | 自然语言查询 | "auth 相关的所有函数" |
| `get_node` | 获取单个节点 | "stream_query 的签名" |
| `get_neighbors` | 相邻节点 | "谁调用了 stream_query" |
| `shortest_path` | 最短路径 | "A 到 B 的调用链" |

### search_knowledge（LightRAG MCP — 已有）

| Tool | 功能 | Claude Code 用在哪 |
|------|------|------|
| 语义搜索 | 在图谱中搜索概念 | "streaming output 的设计理念" |
| 交叉引用 | 关联微信文章 | "有没有文章讨论过这个设计" |

---

## 更新策略

```
cron(weekly): graphify refresh → 重建代码图谱
```

OpenClaw/Hermes 每周发 5-10 个 commit，一周一次的更新频率足够跟踪 feature 变化。

---

## 验证场景

### Demo 1: Streaming Tool Output 实现

> 任务：在我的 Rust fork 里实现类似 OpenClaw 的 streaming tool output

```
Claude Code 自主调用链：
1. search_knowledge("streaming tool output 设计")
   → 返回微信文章：设计决策、为什么用 AsyncGenerator、性能考虑
2. lookup_code.get_node("stream_query")
   → 返回函数签名 + 所在文件
3. lookup_code.get_neighbors("stream_query")
   → 返回调用者/被调用者
4. 综合以上信息，用 Rust/Tokio 实现等价功能
```

**验收标准：** Claude Code 写出的 Rust 代码架构与 OpenClaw 一致，不是盲目翻译。

### Demo 2: Self-Evolution 集成

> 任务：给 Rust fork 加上 Hermes 的 self-evolution 能力

```
Claude Code 自主调用链：
1. search_knowledge("hermes self evolution 自学习 遗传算法 优化提示词")
   → 返回文章：实现方案对比、踩坑经验、参数推荐
2. lookup_code.query_graph("evolution optimization")
   → 返回相关模块：genetic_optimizer, prompt_evaluator
3. lookup_code.shortest_path("genetic_optimizer", "agent_loop")
   → 返回集成路径：需要改哪些文件
4. 综合实现
```

**验收标准：** Claude Code 知道用哪些库、怎么集成到 agent loop、避过已知坑点。比 Context7 给的纯 API docs 深度高一个数量级。

---

## 成功标准

| 维度 | 标准 |
|------|------|
| 深度 | Claude Code 能回答"为什么这么设计"（来自文章），不限于"怎么调用"（来自 API docs） |
| 广度 | 跨项目对比（OpenClaw vs Hermes 的 tool routing 差异）由 Agent 自主完成 |
| 可用性 | 零 wrapper 代码，Graphify MCP 原生集成，一行注册 |
| 用户感知 | 使用 search_knowledge + lookup_code 的 Claude Code 比只用 Context7 的，在 OpenClaw/Hermes 相关问题上**明显更准确、少幻觉** |

---

## 后续扩展（按需触发）

| 仓库 | 触发条件 |
|------|------|
| `nousresearch/hermes-agent` | 需要跟踪类似 Hermes 核心变化 |
| `HKUDS/LightRAG` | 连续 3 次手动翻 LightRAG 源码后加 |
| T3 及以下 | 永远不建（边际效用趋零） |
