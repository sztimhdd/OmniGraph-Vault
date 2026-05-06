# Agent 框架对比 — Brave Search 答案 (A/B 对照实验)

**问题**：Hermes、OpenClaw、Claude Code、LangGraph 这些 agent 框架在架构设计上的核心差异是什么?各自最适合什么场景?请引用具体的技术细节,例如工具调用机制、上下文管理、状态持久化、harness/skill 系统等。

**方法**：Claude (Sonnet) + Brave Search MCP, 不查询本地 KG,仅基于 web 公开文档/博客/论文综合。

**对照对象**：[`agent_frameworks_comparison_2026_05_06.md`](./agent_frameworks_comparison_2026_05_06.md) (KG 合成版)

**生成时间**：2026-05-06

---

四个框架代表了 agent 工程的三种根本不同的设计哲学:**底层引擎**(LangGraph)、**生产化应用**(Claude Code)、**安全运行时**(OpenClaw)、**自进化助手**(Hermes)。它们并非完全替代关系,而是在抽象层级和优化目标上各占一个生态位。

## 一、四框架核心架构对比

### 1. LangGraph (LangChain Inc.) — 底层图编排引擎

**架构哲学**:Agent 执行被建模为 directed state graph。节点是 Python 函数,边定义状态转移,State schema 通过 TypedDict 或 Pydantic 严格类型化。

- **工具调用**:通过 `ToolNode`,LangChain 标准 `@tool` decorator 装饰函数。Tool calling 作为 graph 中的一个节点执行,LLM 输出结构化 JSON 选择工具。
- **上下文管理**:State 字典按节点流动,reducers 决定如何合并(replace / append / custom)。每个节点接收当前 state,返回 partial update。
- **状态持久化**:**核心特性**。内置 `Checkpointer` 接口,支持 SQLite / PostgreSQL / Memory backends。每个 graph step 后状态被持久化,支持任意检查点恢复 + human-in-the-loop。
- **Skill 系统**:**无原生 skill 概念**。开发者自己定义节点和 tools。

> 来源: [LangChain LangGraph Overview](https://docs.langchain.com/oss/python/langgraph/overview), [Mastering LangGraph State Management 2025](https://sparkco.ai/blog/mastering-langgraph-state-management-in-2025)

### 2. Claude Code (Anthropic) — 生产级编码 Harness

**架构哲学**:核心执行模型是 iterative agent loop:`Gather context → Take action → Verify result → [Done or loop back]`。harness 层做了大量工程化封装。

- **工具调用**:Anthropic 标准 tool use API。内置工具 (Bash / Edit / Read / Write / Grep / Glob 等)。每次调用前可经 user permission check (settings 配置)。
- **上下文管理**:通过 `CLAUDE.md` 注入项目级指令、`Hooks/Permissions/Sandbox` 控制行为、`Skills` 提供按需扩展。`/compact` 命令在长会话压缩历史。
- **状态持久化**:Session-level 通过 `.claude/sessions/`,memory 通过 `~/.claude/projects/.../memory/` 跨会话持久化。Git worktree 原生并行支持。
- **Skill 系统**:**Skills 是含 SKILL.md + references/ + scripts/ 的目录**。Progressive disclosure 三层加载:Level 0 仅 name+description,Level 1 加载完整 SKILL.md,Level 2 按需读 references。SkillTool 元工具按需注入 skill 指令。
- **Hooks 系统**:源码定义 27 个 hook events,覆盖工具授权、session 生命周期、用户交互、subagent 协调、context 管理等。Hooks **保证执行**,prompts 不保证 — 用 hooks 做必须每次跑的 lint/format/security 检查。

> 来源: [Dive into Claude Code (arxiv 2604.14228)](https://arxiv.org/html/2604.14228v1), [You Don't Know Claude Code (Tw93)](https://tw93.fun/en/2026-03-12/claude.html), [Claude Code CLI Complete Guide](https://blakecrosley.com/guides/claude-code), [Anthropic Hooks Doc](https://platform.claude.com/docs/en/agent-sdk/hooks)

### 3. OpenClaw — 安全可控的本地优先 Agent Runtime

**架构哲学**:Gateway-centric architecture,以**安全边界 + sandbox**为第一要务。Trust boundaries 严格区分 trusted vs constrained sessions(远程 integration / plugin / non-main 进 sandbox)。

- **工具调用**:通过 Gateway 编排,strict loopback binding + 认证模型访问。Tool execution 默认 sandbox 内。第三方 skills "天生不可信",通过 sandbox + 受控执行约束。
- **上下文管理**:Skills 加载本身是**上下文过滤机制**——根据环境/配置/依赖筛选信息。
- **状态持久化**:对 memory 态度克制——视为"可替换能力位",提供基础实现允许用户自定义(实践中常出"不理我昨天说了什么"问题)。
- **Skill 系统**:Skills 定位为人写的指令 + 规则,边界由系统设定,Agent 在框架内执行。
- **运行时**:Node 24 (推荐) 或 Node 22.14+。`clawdbot daemon install/start/status` 服务化运行。

> 来源: [OpenClaw Security Docs](https://docs.openclaw.ai/gateway/security), [Build Secure Local-First Agent Runtime (MarkTechPost)](https://www.marktechpost.com/2026/04/11/how-to-build-a-secure-local-first-agent-runtime-with-openclaw-gateway-skills-and-controlled-tool-execution/), [Snyk Sandbox Bypass Research](https://labs.snyk.io/resources/bypass-openclaw-security-sandbox/), [arXiv Security Taxonomy](https://arxiv.org/html/2603.27517v1), [openclaw GitHub](https://github.com/openclaw/openclaw/blob/main/AGENTS.md)

### 4. Hermes Agent — 自进化的个人助手

**架构哲学**:面向个人助手场景,核心是"让 Agent 长本事"——通过持续交互、经验沉淀、自动学习构建越用越懂用户的 AI 助理。被定位为 OpenClaw 的"非平替"路径。

- **工具调用**:通过 Harness runtime 管理。**执行后端可切换**(本地 / VPS / Serverless)。集成 MCP 协议扩展工具能力,支持连接 MCP 服务器,能将多步 pipeline 合并为单次推理调用。
- **上下文管理**:**完整记忆体系** — 内置 `MEMORY.md` + `USER.md` + external memory provider + session search。先**检索**再处理,而不是一股脑塞回。包含 `honcho_context` (上下文增强)、`honcho_profile` (用户画像)、`honcho_search` (历史交互搜索) 等工具。
  - 上下文压缩:`compression.threshold=0.50` 在限制 50% 时触发,`summary_model: google/gemini-3-flash-preview`。
- **状态持久化**:**学习闭环** — 静默 Mini Agent 审查会话,提取经验沉淀为 Skill 或 Memory。`/insights` 命令出"周报"。跨平台对话连续(Telegram → Discord 切换不丢上下文)。
- **Skill 系统**:与 OpenClaw 共享 SKILL.md + progressive disclosure 标准。**关键不同**:Skill 是学习闭环产生的(Agent 自己决定何时生成新 skill / 更新旧 skill),不是人写的。
- **CLI**:`hermes`、`hermes model`、`hermes tools`、`hermes config`、`hermes gateway`、`hermes setup`、`hermes claw migrate`、`hermes update`、`hermes doctor`。

> 来源: [知乎 Hermes Agent 全面调研](https://zhuanlan.zhihu.com/p/2022015752258027715), [Hermes Agent Harness 解析 (虎嗅)](https://www.huxiu.com/article/4854618.html), [取代龙虾的爱马仕 (36氪)](https://36kr.com/p/3764418640003840), [自进化深度解析 (腾讯新闻)](https://view.inews.qq.com/a/20260424A029SY00), [Hermes Self-Evolution (cnblogs)](https://www.cnblogs.com/itech/p/19867914), [菜鸟教程 Hermes Agent](https://www.runoob.com/ai-agent/hermes-agent.html)

## 二、核心差异对比表

| 特性 | LangGraph | Claude Code | OpenClaw | Hermes |
|------|-----------|-------------|----------|--------|
| **抽象层级** | 底层引擎 | 应用级(编码场景) | 应用级(Local-First Runtime) | 应用级(个人助手) |
| **核心哲学** | 图编排、状态机 | 工具即流程、agent loop 工程化 | 安全可控、sandbox first | 自进化、学习闭环 |
| **工具调用** | ToolNode 节点 + state | Anthropic API + permission check | Gateway + Sandbox | Harness runtime + MCP 集成 |
| **上下文管理** | State schema + reducers | CLAUDE.md + /compact + Skills | Skills 作为上下文过滤 | 完整记忆体系 + 检索优先 |
| **状态持久化** | Checkpointer (核心特性) | sessions/ + memory/ + git worktree | 可替换能力位(克制) | 学习闭环自动沉淀 |
| **Skill 系统** | 无 | SKILL.md + progressive disclosure | 人写指令 + 边界 | Agent 自动生成 + 优化 |
| **典型 backend** | 多 LLM 通用 | Claude (Anthropic) | 多 LLM,Node 24 推荐 | Nous Portal/OpenRouter/GLM/Kimi/MiniMax/OpenAI |
| **Hooks/Events** | 无原生 | 27 hook events | 通过 daemon/gateway | cron 调度器 |

## 三、应用场景

- **LangGraph**:研发团队从零搭建定制 agent,需要细粒度控制 graph 拓扑、状态合并、checkpointing。**最适合复杂多步任务、多 agent 协调**。LangGraph 也常被作为底层引擎 — 例如 Deep Agents 在其上加封装。
- **Claude Code**:**编码任务的最优解**。代码生成、项目构建、终端开发任务。harness 工程化程度高,subagents/skills/hooks 让你专注 prompt 而非工程。
- **OpenClaw**:**企业级、强安全合规需求**。需要受控 agent 行为、限定权限、运行 self-hosted。CVE/sandbox bypass 已被研究,需要 hardening。
- **Hermes**:**长期个人助手**,需要跨平台连续对话、自动 skill 演化、记忆驱动个性化。CLI 优先,集成 Telegram/Discord/Slack 等。

## 四、决策路径

1. **是否纯代码任务?** → **Claude Code**
2. **是否需要严格安全沙箱、企业合规?** → **OpenClaw**
3. **是否需要长期跨平台个人助手?** → **Hermes**
4. **是否需要细粒度图状态控制 / 复杂多 agent 协调?** → **LangGraph (或 Deep Agents)**

## 五、源数据可信度声明

- **LangGraph**:LangChain 官方文档 + 多个第三方分析,信息密集且最新(2025-2026)。
- **Claude Code**:arxiv 论文 (2604.14228) + Anthropic 官方 + 多个独立技术博客,有可靠源代码级别细节(27 hooks 等)。
- **OpenClaw**:GitHub repo + 官方文档 + 安全研究论文 (Snyk + arXiv 2603.27517) — 安全角度信息丰富。
- **Hermes**:中文技术博客 (知乎/虎嗅/36氪/腾讯新闻) + 菜鸟教程 + 百度百科 — 信息相对**新但分散**,部分内容可能反映 4 万 stars 项目的近期增长。

## 六、答案局限性

- 公开 web 信息**广**但**未必深** — 一些内部架构细节可能仅在团队设计文档/付费咨询中。
- 中文资料覆盖好,英文 OpenClaw 安全研究详细,但**Hermes 的英文深度内容稀少**。
- 没有访问到团队具体的设计文档、commit history、benchmark 数据。
- Time-of-search 效应:今天搜的是 2026-05 上半年最新讨论,半年前可能是不同结论。

---

*基于 Brave Search 公开 web 综合,无 KG 辅助。*
