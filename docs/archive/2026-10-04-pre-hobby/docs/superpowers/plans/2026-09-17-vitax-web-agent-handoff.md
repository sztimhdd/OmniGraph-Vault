# VitaX 重构项目 → Web 侧 ChatGPT Agent 交接提示词

2026-09-17 生成。用途：Codex 额度恢复前，让只能读取 GitHub 的 Web 侧 Agent 理解项目
现状，并产出一份可执行的实现路线图。以下"提示词正文"整段可直接复制粘贴。

---

## 使用前提（重要，先读）

[KNOWN] VitaX 重构产物已推送到 GitHub 分支 **`vitax-refactor-snapshot`**（2026-09-17）。
Web 侧 Agent 必须先切到该分支，不要读 `main`：

- `main`（`dca7c772a8c95125d275ec50b2944ff00713667a`，2026-09-03）= **重构前的历史基线**。
  只有旧 ingest pipeline、`kb/` 站点、`omnigraph_search/`、`deploy/` 与 `databricks-deploy/`。
- `vitax-refactor-snapshot` = **重构现状快照**，包含 ADR 0001–0004、18 张 VX 工单、
  `vitax/` 代码包（knowledge / legacy_migration / production）、`EXECUTION.md` 执行账本、
  `AGENTS.md`、`CONTEXT.md`、`docs/spec/VITAX_REFACTOR_SPEC.md`、四份调研报告、
  部署证据与新增测试。

**推送前已完成的审计（可作为可信度参考）：**

- 待提交内容共计约 1,084 项变更：77 个 Markdown、36 个 JSON、31 个 Python、3 个 systemd unit，
  其余为 txt/toml/sh/.gitignore。无二进制、无数据库、无模型权重。
- 内容级凭据扫描（AWS/GCP/OpenAI/GitHub/Slack key 与私钥块）**零命中**。
- 930 个删除项是 `docs/PROJECT_CLEANUP.md` 记录的有意归档清理；这些文件在推送前仍由
  `origin/main` 的 HEAD 树完整保存，可随时用
  `git show dca7c772:<path>` 取回。

**注意一处已知缺口：** `docs/PROJECT_CLEANUP.md` 提到的本地备份目录
`VitaX-backup-20260909` 现已不存在。归档内容的可恢复性依赖 Git 历史，而非该备份。
如果后续要做不可逆操作，应先重建备份。

---

## 提示词正文（复制以下全部内容给 Web 侧 Agent）

```
你是我的远程架构与路线图顾问。我只能通过 GitHub 给你访问权限，无法给你 SSH 或本机文件系统。
你的任务是：通读仓库，理解 VitaX 重构的真实状态，然后产出一份分阶段的实现路线图。

请不要写代码，也不要提议立即部署。这一轮的交付物是一份路线图文档 + 关键决策清单，
用来在本地 Codex 额度恢复后直接拆票执行。

=== 一、项目身份 ===

[KNOWN] 仓库：sztimhdd/OmniGraph-Vault（GitHub）。本地目录名是 VitaX，这不是 Python 包改名，
只是工作目录名。产品对外名称将使用 VitaX。

[KNOWN] 这是一个个人知识库产品，不是通用平台：文章采集 → 清洗翻译 → 知识图谱/Wiki 生产 →
公开发布 → 网站与 MCP 检索。原仓库有较长历史，经历了多轮 ingest 重构、KB v2、Agentic-RAG
等里程碑。

[KNOWN] 请先 `git checkout vitax-refactor-snapshot`，再开始阅读。请在阅读时把"历史实现"与"目标架构"明确分开。旧 pipeline 是素材，不是兼容规范。
用户明确反对为了与旧实现保持一致而耗费重构成本。

=== 二、先读这些文件（按顺序） ===

1. `README.md` — 仓库定位、环境、验证入口
2. `AGENTS.md` — 协作与安全边界、模型路由约束（这份规则约束你提出的任何建议）
3. `CONTEXT.md` — 项目词汇表
4. `docs/README.md` — 文档索引
5. `docs/adr/0001-pc-production-cloud-serving.md`
6. `docs/adr/0002-autonomous-repair-authority.md`
7. `docs/adr/0003-product-architecture-over-legacy-parity.md`
8. `docs/adr/0004-minimal-knowledge-product.md`
9. `docs/superpowers/plans/2026-09-09-vitax-product-architecture.md` — **核心计划，最重要**
10. `docs/spec/VITAX_REFACTOR_SPEC.md` — 重构规格
11. `docs/work-items/vitax-refactor/README.md` — 18 张 VX 工单索引与依赖
12. `EXECUTION.md` — 执行账本（真实进展与断点）
13. `.planning/ISSUES.md` — 权威 backlog（顶部有 VitaX 当前队列表）
14. `vitax/` — 新代码包：`knowledge.py`（公开读模型）、`legacy_migration.py`（旧资产导入）、`production.py`
15. `docs/research/2026-09-09-vitax-*.md` — 四份调研（当前架构、检索格局、综合、评审跟进）
16. `docs/deployments/` — 部署证据与基线

[KNOWN] 以上路径全部位于分支 `vitax-refactor-snapshot`。请先切换分支再阅读，切勿依据 `main`
给出结论——`main` 是重构前基线，会得出完全相反的判断。

=== 三、目标架构（已定稿的合同，不要重新论证） ===

[KNOWN] 拓扑：Hermes PC 是知识生产唯一写入端（扫描、清洗、翻译、知识加工、Wiki 更新）；
一台阿里云承载公开发布、MCP、已发布知识副本和私有备份；vitaclaw-site 保持独立站点边界，
不视为 VitaX 站点的替代品。

[KNOWN] 发布节奏：每天 08:00 Asia/Shanghai 提升一个已验证 release；失败继续服务前一版。
匿名浏览和关键词检索免费；复杂问题走 BYOLLM（访客自带 key）深度研究。

[KNOWN] 四个逻辑对象（不要用四个服务实现）：
- SourceDocument：稳定来源身份、原/规范 URL 与别名；抓取事件可多次
- DocumentRevision：内容版本 + hash + 解析配方 + 段落/页/图定位；来源发布时间与抓取时间分开
- KnowledgeRevision：实际接受的解读、Wiki、主张、关系与引用；保留人工改动与模型配方
- PublishedRelease：不可变公开快照 + manifest；每个请求固定一个 release

[KNOWN] 公开边界：默认公开已接受解读/Wiki/必要引用摘录/按价值选取的图片（带出处 caption）。
完整原文、全文翻译、原始 HTML/PDF、账户、Agent 轨迹、日志、凭据一律不公开。
已知知识/关系引用缺失或指向私有证据时拒绝发布，不得静默删引用制造无来源答案。

=== 四、明确不引入的组件（不要重新提议） ===

[KNOWN] 当前决定不新增：Neo4j、Postgres/pgvector、Cognee、RAGFlow、LangChain/LangGraph、
Temporal、Celery/Redis、事件总线、实时复制、通用插件层。Prefect 已从"优先实验"降级为
"只有能替代明确重复调度代码才考虑"。

[KNOWN] LightRAG 与现有 Qdrant/embedding 路径保留为隔离对照，不默认接入新公网，也不预定删除。
sqlite-vec/FastEmbed 延后到有质量与资源证据时再评估。

[KNOWN] 决策原则：每引入一个组件，必须说明它替代了什么、节省了什么；能复用现有代码或标准库
就不新增依赖。

=== 五、当前真实进展（截至 2026-09-10，以 EXECUTION.md 与 .planning/ISSUES.md 为准） ===

[KNOWN] 已完成并有独立审阅的本地切片：
- VX-007 公开读模型：本地切片已接受
- VX-010 内部取证修正：本地切片已接受（公开 BYOLLM 尚未开始）
- VX-004 真实知识生产：两源切片已接受（7 条解读 + 1 篇跨来源 Wiki、14 实体、11 关系、50 证据，
  同版 SQLite 与独立审阅通过）；整项仍 partial
- VX-002/003：环境核实与同步退出码，历史本地/远端已接受

[KNOWN] VX-012 旧资产导入：
- 只读盘点：三机成功入库文章按 source+URL 去重共 1,257 篇；1,216 份数据库原文、1,203 份全文译文；
  41 篇缺数据库正文
- VX-012A 单篇零 LLM 闭环已通过
- VX-012B 20 篇（wechat 15 + rss 5）导入 20/20 成功，重跑 20/20 skipped；13 条完整译文
  quality passed，7 条无全文译文 needs-review；20 条全部保持 private，公开投影为空
- 候选已升级为 generation 目录 + 单一 `current` 指针，含 manifest 哈希校验
- 41 篇缺正文恢复审计：29 篇可由 URL-hash 在 Hermes vault 找到 `final_content.md` + `metadata.json`，
  12 篇在限定路径内无确定性匹配；本轮未恢复、未写回
- 状态：迁移/保全/幂等部分通过；"旧知识公开可搜索"未验收，因为未授权自动公开旧内容

[KNOWN] 尚未开始：VX-009A/009B 真实站点与旧知识检索、VX-012C 全量候选、VX-010 公开 BYOLLM、
VX-008 云发布、VX-011 日更调度、VX-012 生产切换。

=== 六、约束（会否决不合规建议） ===

[KNOWN] 安全与数据边界：
- 私有正文、凭据、cookie、PII 绝不进入外部模型提示词或公开仓库
- 默认不新增付费资源；额度耗尽时暂停相关模型工作，不自动换付费路线
- 不自动 commit/push；不做不可逆迁移或生产变更

[KNOWN] 证据标准：
- 历史 release 报告、部署 runbook、UI 状态、模型自述都不构成现网事实
- 必须区分"本地通过""云端运行态""正式 UAT"三层证据
- 不得用 HTTP 200、toast、revision 号或自报成功替代真实内容验收

[KNOWN] 三台环境（macOS SSH alias）：OHPC = Hermes 192.168.4.100；ack-node-2 = pipeline
47.117.244.253；ack-node-1 = MCP 47.103.73.20。每次连接必须核实 hostname。
生产与本地 main 不同；保留 pipeline fork、远端 WIP 与 worktree，不做整目录覆盖部署。

=== 七、你要交付的内容 ===

请产出一份 Markdown 路线图，包含：

1. **现状判定**：你读到的与"本地已完成"叙述之间的差距；明确指出哪些说法你无法从仓库证实。
2. **关键路径**：从现在到"阿里云上可公开访问的 VitaX 知识站点 + MCP 检索 + 08:00 日更"的
   最短依赖链。标出每一段的阻塞边。
3. **阶段划分**：每阶段给出可验收交付、依赖、退出条件、明确不在本阶段做的事。
   请复用现有 VX 编号，不要新建 tracker 或重命名工单。
4. **风险清单**：按"最可能导致失败"排序，每条给出识别信号与最小验证方式。
5. **最多三个决定性实验**：每个实验要写清假设、通过/否决条件、需要的最小样本。
6. **对现有计划的反对意见**：如果你认为某个 ADR、工单边界或技术选型有问题，直接说，
   给出理由与替代方案。不要为了配合既有决定而附和。
7. **需要我（人类）先做的动作**：例如推送分支、提供仓库权限、开放某个环境。

写作要求：结论先行；区分 [KNOWN] 训练事实 / [COMPUTED] 计算 / [INFERRED] 推断 / [GUESS] 猜测；
不确定就说不确定，不要编造仓库内容。不要输出代码补丁。

=== 八、分支与基线约定 ===

- 重构现状分支：`vitax-refactor-snapshot`
- 重构前基线：`main @ dca7c772`（2026-09-03），仅用于对比"改了什么"，不作为事实来源
- `vitax-refactor-snapshot` 尚未合并入 `main`，也未部署到任何生产环境。它是快照，不是发布。
- 目标架构、已定稿的四个逻辑对象、公开边界、不引入组件清单、当前进展与约束：见上文第三、四、五、六节。
```

---

## 备注

- 提示词故意要求 Web 侧给出"反对意见"，因为它只能读 GitHub、无法运行验证，其独立视角的
  价值主要在架构质疑与依赖排序，而不是代码正确性。
- 若本地后续把重构推到分支，建议同时把该分支设为只读参考，避免 Web 侧基于过期
  `main` 给出冲突结论。
