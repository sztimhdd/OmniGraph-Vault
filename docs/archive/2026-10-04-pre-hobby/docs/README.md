# 文档索引

## 当前入口

- [管家告警核对与只读进度入口](deployments/2026-10-04-pipeline-steward-check/REPORT.md)：微信/RSS部分失败、入库运行超时与当前落库证据、改写摘要；含管家可复用的journal/metrics/只读SQL说明。

- [Hermes Dot 管家调研与接入边界](research/2026-10-04-hermes-dot-steward/REPORT.md) / [可复制提示词](research/2026-10-04-hermes-dot-steward/PROMPT.md)：服务清单、巡检、有限恢复和人工报警；尚未启用新日程或变更服务。

- [下一阶段总计划（含阿里云部署与内容补全独立轨道）](superpowers/plans/2026-10-04-vitax-next-stage.md)：稳定双轨、多主题生产、100元历史回填、完整阅读与有界恢复；[双机部署调研](research/2026-10-04-aliyun-deployment/REPORT.md)。已留档，未据此部署。


- [读者体验核查：内容、UX、搜索与附加功能](research/2026-10-03-vitax-reader-audit/REPORT.md) / [待执行计划](superpowers/plans/2026-10-03-vitax-reader-experience.md)：浏览器实走后登记#100–#114与6个纵向工单；本轮只落文档，不宣称已修复。

- [本地三模块自动闭环新计划](superpowers/plans/2026-10-02-vitax-local-automation.md) / [规格](spec/VITAX_LOCAL_AUTOMATION_SPEC.md)：新0→10%预算，4个纵向票；深问API/MCP生产化排除，复用旧链/已有产物与本地自动发布。

- [三模块获批执行结果](deployments/2026-10-02-plan-execution/REPORT.md)：完整本地文章库与中文检索已验；RSS/公众号已应用最小修复，内存5/6 GiB及自然运行门、知识生成运行面仍分别待验/阻塞。

- [三模块可执行计划](superpowers/plans/2026-10-02-vitax-three-module-execution.md) / [规格与测试契约](spec/VITAX_THREE_MODULE_EXECUTION_SPEC.md)：Matt纵向工单与blocking、Ponytail精简后9张新票；本地文章阅读不等待建图/公开审核，当前已获批执行；分票状态见执行报告

- [三模块gap核查与统一issue](../.planning/ISSUES.md)：2026-10-02三个独立子代理核查采集/ingestion、storage/processing、VitaX消费入口；新增#93–#99并刷新既有Wiki问题，仅调查登记、尚未修复

- [下一阶段计划：中文检索与旧文章解读/Wiki小批](superpowers/plans/2026-10-01-vitax-reviewed-content-sprint.md) 与 [TDD技术设计/红绿契约](spec/VITAX_REVIEWED_CONTENT_TDD.md)：2026-10-01现状规划，已补入用户同意的旧文章解读接入，3张proposed子票，尚未实施


- [本地真实知识生产](LOCAL_REAL_PRODUCTION.md)：两份真实HTML到Hermes知识包、跨来源Wiki与同版公开读库，已完成本地候选切片验收

- [本地公开知识读库](LOCAL_PUBLIC_KNOWLEDGE.md)：首个新合同构建/读取组件与可重放示例

- [ADR0004：最小知识产品](adr/0004-minimal-knowledge-product.md)：KG/Wiki/可选AgentRAG边界与组件裁决

- [产品架构与执行重排](superpowers/plans/2026-09-09-vitax-product-architecture.md)：当前主线，按 ponytail 收敛并实施；组件按实际收益准入
- [当前 Sprint：Reader + Safe Public Knowledge](superpowers/plans/2026-09-20-vitax-reader-safe-public-sprint.md) 与 [产品规格](spec/VITAX_READER_SAFE_PUBLIC_SPEC.md)：安全公开切片、真实读者站和本地浏览器验收
- [现有架构取证](research/2026-09-09-vitax-current-architecture.md)与[检索项目调研](research/2026-09-09-vitax-retrieval-landscape.md)：源码、当前上游能力及选型依据

- [VitaX 三环境部署档案](deployments/VITAX_DEPLOYMENT_BASELINE.md)：当前接管入口与时间点证据

- [项目说明](../README.md) 与 [Agent 工作规则](../AGENTS.md)
- [已知问题](../.planning/ISSUES.md)：保留上游问题与解决记录
- [本地开发](LOCAL_DEV_SETUP.md)、[测试](e2e-testing.md)、[代码约定](conventions.md)
- [架构](architecture.md)、[技术栈](tech-stack.md)、[KB 接口契约](../kb/README.md)
- [MCP 接入](MCP-QUICKSTART.md)、[运维](OPERATIONS.md)、[操作手册](OPERATOR_RUNBOOK.md)
- [部署说明](../OMNIGRAPH_DEPLOY.md)、[部署流程](../Deploy.md)、[BGE-M3 迁移](../BGE_M3_MIGRATION.md)
- [技能规范](skills/SKILL_STANDARDS.md)
- [本次整理与恢复](PROJECT_CLEANUP.md)
- [VitaX 重构规格](spec/VITAX_REFACTOR_SPEC.md) 与 [执行工单](work-items/vitax-refactor/README.md)

## 阅读优先级

当前源码与可重复验证 > 接口契约 > 运维／设计说明 > 历史报告。
保留的说明仍可能包含旧模型、旧主机和历史部署结果，使用前核对源码与目标环境。
`docs/design/`、`docs/spec/`、`specs/` 等包含设计依据，存在不等于已实现或正式验收。
旧 GSD 规划、阶段总结和选定交接报告已移出工作区；现有 Markdown 链接改为固定提交的 GitHub 地址。
正文中的历史路径可使用整理记录中的 `git show` 方式查阅。
