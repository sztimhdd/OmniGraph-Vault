# 文档索引

## 当前入口

- [本地真实知识生产](LOCAL_REAL_PRODUCTION.md)：两份真实HTML到Hermes知识包、跨来源Wiki与同版公开读库，已完成本地候选切片验收

- [本地公开知识读库](LOCAL_PUBLIC_KNOWLEDGE.md)：首个新合同构建/读取组件与可重放示例

- [ADR0004：最小知识产品](adr/0004-minimal-knowledge-product.md)：KG/Wiki/可选AgentRAG边界与组件裁决

- [产品架构与执行重排](superpowers/plans/2026-09-09-vitax-product-architecture.md)：当前主线，按 ponytail 收敛并实施；组件按实际收益准入
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
