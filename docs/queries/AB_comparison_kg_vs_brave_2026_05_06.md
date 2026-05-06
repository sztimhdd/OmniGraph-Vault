# A/B Comparison: KG Synthesis vs Brave Search — Same Question

**Question**: Hermes / OpenClaw / Claude Code / LangGraph 架构对比 (4 frameworks, 5 dimensions)

**Two answers**:
- **KG**: [`agent_frameworks_comparison_2026_05_06.md`](./agent_frameworks_comparison_2026_05_06.md) — kg_synthesize.py hybrid mode against 116 OK-ingested articles, 5305 nodes / 6829 edges
- **Brave**: [`agent_frameworks_comparison_brave_2026_05_06.md`](./agent_frameworks_comparison_brave_2026_05_06.md) — Claude Sonnet + Brave Search MCP, no KG access

**Test**: Compare answers head-to-head to determine **whether KG provides real incremental value over public web search**.

---

## TL;DR — Honest verdict

**Brave Search 答案略胜或持平,但优势不大。**

- ✅ Brave **更技术深度**(Claude Code 27 hooks 来源、LangGraph Checkpointer/Reducers 细节、OpenClaw 安全研究 CVE)
- ✅ Brave **源可追溯**(cite URL)
- ⚠️ KG **哲学框架更完整**("先把 Agent 管住" vs "先让 Agent 长本事"二元对比)
- ⚠️ KG **某些细节准确**(Hermes 的 honcho_* 工具、`/insights` 命令)— 但 Brave 也搜到了
- ❌ KG **缺英文官方/学术源**(Anthropic paper、Snyk research、GitHub repos 都没在 KG)
- ❌ KG **缺源归属**(说"Hermes 通过 Mini Agent 审查会话" — 这话从哪来的?)
- ❌ KG **0 image references** despite ~331 vector chunks

## 维度对比表

| 维度 | KG 答案 | Brave 答案 | 胜方 |
|------|---------|------------|------|
| **覆盖广度** | 4 框架都有 | 4 框架都有 | 平 |
| **LangGraph 深度** | 弱:仅"底层图编排引擎,被 Deep Agents 用作底层" | 强:State schema + Reducers + Checkpointer + ToolNode | **Brave** |
| **Claude Code 深度** | 中:agent loop、artifact、handoff、200K context | 强:同样 + 27 hooks 计数 + source paper 引用 + skill progressive disclosure | **Brave** |
| **OpenClaw 深度** | 中:Skill 规则、Sandbox、Gateway、克制记忆 | 强:同样 + Snyk sandbox bypass research + Node 24 runtime + arXiv taxonomy | **Brave** |
| **Hermes 深度** | 中-强:Mini Agent、MEMORY.md/USER.md、学习闭环 | 中-强:同样 + honcho_* tools + CLI 命令完整 + cron 调度 + MCP 集成 | **平** |
| **哲学框架** | 强:"管住 vs 长本事"二元化记忆鲜明 | 中:四种哲学并列描述 | **KG** |
| **决策路径** | 5 步 if-then 树 | 4 步 if-then 树 | 平 |
| **源归属** | 0 引用,不知谁说的 | 13 URL 引用,可点开 verify | **Brave** |
| **图片嵌入** | 0(空有 KG 但没用) | 0(N/A,文字答案) | 平 |
| **生成时间** | ~30-60s + 5 LLM call cost | ~3-5 web searches + 1 synthesis | 平 |
| **Vertex/DeepSeek API spend** | 真消耗 | 真消耗 | 平 |

**6/11 Brave 胜,4/11 平,1/11 KG 胜。**

## 关键证据 — KG 缺啥 Brave 有啥

### Claude Code 维度

**KG 答案**:"agent loop、context management、长时任务分工"+"操作前需用户授权"+"通过原生 Git Worktree 支持并行工作"

**Brave 答案**:同上 + 这些 KG 没有的:
- arxiv 论文 [Dive into Claude Code (2604.14228)](https://arxiv.org/html/2604.14228v1) 引用
- "源代码定义 27 hook events,涵盖工具授权 (PreToolUse, PostToolUse, ...) / session lifecycle / user interaction / subagent coordination / context management / workspace events / notifications"
- "`Gather context → Take action → Verify result → [Done or loop back]` ↑ ↓ CLAUDE.md / Hooks / Skills / Tools / Memory" 架构图
- Hooks 保证执行 vs prompts 不保证 — 用 hooks 做 lint/format/security 必跑检查

→ **Brave 有官方 paper + 工程级细节**,KG 没吸收

### LangGraph 维度

**KG 答案**:1 段话,"create_agent 函数构建在 LangGraph 之上,提供简单 ReAct 循环。Deep Agents 进一步封装"

**Brave 答案**:具体技术:
- 状态机模型:`State schema (TypedDict / Pydantic)`
- `Reducers` 决定 state 合并(replace / append / custom)
- `Checkpointer` 接口:SQLite / PostgreSQL / Memory backends
- `ToolNode` 节点 + `@tool` decorator
- LangSmith integration

→ **Brave 有官方文档全面覆盖**,KG 没吸收(因 KG 是 WeChat KOL 文章,主写中文 agent 生态,LangGraph 提及但不深)

### OpenClaw 维度

**KG 答案**:"Sandbox + Gateway 安全运行时" + "Skills 是上下文过滤" + "记忆作为可替换能力位"

**Brave 答案**:同上 + 关键扩展:
- **Snyk 实际 sandbox bypass 研究**(2 个具体 bypass 案例)
- **arXiv 安全分类法 (2603.27517)** — OpenClaw 框架系统性安全分析
- Node 24 推荐运行时
- `clawdbot daemon install/start/status` 服务化命令
- 15 channel adapters / OAuth 2.0 / Webhook HMAC-SHA256 验证

→ **Brave 有英文安全社区研究**,KG 没吸收

### Hermes 维度

**KG 答案**:Mini Agent + 学习闭环 + MEMORY.md + USER.md + 检索优先 + skill 自演化 + 跨平台连续对话

**Brave 答案**:同上 + 这些 KG 没明确说的:
- `honcho_context` / `honcho_profile` / `honcho_search` / `honcho_conclude` 具体工具名(KG 没列)
- `compression.threshold=0.50` + `summary_model: google/gemini-3-flash-preview` 配置细节
- 完整 CLI:`hermes model`, `hermes tools`, `hermes claw migrate`, `hermes doctor` 等
- cron 调度器
- MCP 协议集成 + 多 LLM provider 列表

→ **Brave 有更完整的 CLI/配置层**,KG 偏概念化

## 唯一 KG 真胜的维度:哲学框架

**KG 答案**(开篇就立框架):
> "OpenClaw 的核心哲学是 **'先把 Agent 管住'**" vs "Hermes 的核心哲学是 **'先让 Agent 长本事'**"

这种**两 path 对比叙事**,Brave 答案没有这种深度抽象。KG 合成器(DeepSeek 在 KG 上下文上做 reasoning)产生了这个 framing。

但**值得吗?** 一个抽象哲学框架 vs 大量技术细节缺失,trade-off 不值。

## 为什么 KG 这次没胜

### 数据源决定上限

KG 的 116 OK ingested articles 来自 **Apr 29 mass-scan 的中文 WeChat KOL 文章**:
- ✅ Hermes 的中文社区分析(知乎/虎嗅/36氪/腾讯新闻)— 有覆盖
- ✅ OpenClaw 的中文社区分析 — 有覆盖
- ❌ LangGraph 的英文官方文档 — 没爬过
- ❌ Claude Code 的 arxiv 论文 — 没爬过
- ❌ OpenClaw 的英文安全研究(Snyk + arXiv)— 没爬过
- ❌ GitHub repos 的 README/AGENTS.md — 没爬过

KG 的"知识"上限被 KOL 选择的内容定义。一个**KOL 不报道**的话题(LangGraph 英文官方、Claude Code 学术 paper),KG 永远没有。

### Synthesis 不弥补缺失

LightRAG hybrid 模式从 graph entity+relation 构建答案,**不会去网上找 missing info**。Brave Search 是动态查询,**遇到 gap 自动搜更多**。

KG 在静态图谱上 reason,Brave 在 dynamic web 上 reason。

### 0 images is a real loss

KG 有 331 chunk vectors(包括很多 image-derived 的 sub-doc),但 synthesis 没用。如果 KG synthesizer 主动嵌入图(像论文/截图)Brave 答案永远做不到 — 因为公开 web 不是 image-friendly。**这是 KG 的潜在唯一杀手锏,但今天没发挥**。

## 结论

| 问题类型 | 推荐答案来源 |
|---------|--------------|
| 公开技术对比(本次问题) | **Brave Search 略胜** |
| 中文 KOL 社区氛围/趋势 | **KG 略胜**(KOL 内容是 KG 强项) |
| 内部团队设计文档/未公开决策 | **KG 唯一选择**(如果有索引) |
| 需要图文并茂的可视化分析 | **KG 潜在唯一选择**(if 启用 image embedding) |
| 学术/官方文档/安全研究 | **Brave 唯一选择** |

## 给 KG 的改进建议(基于本次实验)

### 短期(已可实施)

1. **图片嵌入开启**:让 kg_synthesize.py prompt 里加 "若有相关图片,用 `![描述](本地路径)` 嵌入" — 立刻发挥 KG 唯一杀手锏
2. **源归属增强**:每段答案附 chunk_id / article_url 引用,可追溯
3. **混合检索**:用户询问"框架对比"类问题时,KG synthesis + 自动 web search 互补

### 中期 (架构改造)

4. **KG ingest 扩源**:不只 WeChat KOL,也吸纳:
   - GitHub README / AGENTS.md / 官方 docs(英文)
   - arxiv papers (agent 领域)
   - 安全研究 / CVE / blog posts(英文)
5. **多语言 KOL 平衡**:补英文 X / Substack / Medium 的 agent 评测者

### 长期 (战略选择)

KG 的真正价值场景应该聚焦在 **"WeChat KOL 圈层独有 / 公开 web 不易索引"** 的内容:
- 中文 agent 圈层趋势/谣言/社区氛围
- Hermes 团队的中文社区 review (KG 这次答 OK)
- 公开教程很难找的具体配置/调优经验

如果只是答**英文已充分覆盖的技术对比**,KG 难以打过 Brave。

## 数字 vs 数字

```
KG:    7869 bytes, 71 lines, 0 image refs, 0 source URLs
Brave: 8946 bytes, 95 lines, 0 image refs, 13 source URLs

KG cost:    DeepSeek 1 LLM call + Vertex embedding 不少 (~$0.005)
Brave cost: Brave Search 4 calls (~$0) + Sonnet synthesis (~$0.01)
```

**Brave 多 14% 内容 + 13 个可点击源 + 略高深度**。

---

*A/B 实验数据归档于此。下次问"KG 是否有价值",可以引用本文回答:取决于问题类型。本次问题(英文充分覆盖的公开技术对比)→ Brave 略胜。*
