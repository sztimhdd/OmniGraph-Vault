# VitaX 重构工单

## 2026-10-03 读者体验后续（proposed，未实施）

[浏览器报告](../../research/2026-10-03-vitax-reader-audit/REPORT.md) / [开发计划](../../superpowers/plans/2026-10-03-vitax-reader-experience.md)。#100–#114在`.planning/ISSUES.md`登记；复用VX-009父票，不另建tracker。G1格式/链接 → G2阅读链/返回/跨范围 → G3搜索解释 → G4选读/归组 → G5 Wiki人类呈现 → G6实体定位。续读/复制引用为P3。用户本轮仅授权调查与落文档。

- [VX-009G1：原文和译文可读且链接指向正确](VX-009G1-readable-formats-links.md)（M，proposed）
- [VX-009G2：跨范围往返阅读不丢上下文](VX-009G2-reading-search-context.md)（L，proposed）
- [VX-009G3：技术词检索相关且解释可见](VX-009G3-explainable-search.md)（M，proposed）
- [VX-009G4：选读筛选与同源归组](VX-009G4-selection-context.md)（M，proposed）
- [VX-009G5：Wiki与证据适合普通阅读](VX-009G5-human-wiki.md)（M，proposed）
- [VX-009G6：实体关系区分并就地查看](VX-009G6-entity-navigation.md)（M，proposed）


## 当前三模块执行（2026-10-02）

[实施计划](../../superpowers/plans/2026-10-02-vitax-three-module-execution.md) / [规格](../../spec/VITAX_THREE_MODULE_EXECUTION_SPEC.md)。下表为Matt纵向切片，权威issue仍在`.planning/ISSUES.md`；不重新建tracker；当前事实见[执行报告](../../deployments/2026-10-02-plan-execution/REPORT.md)，未观察的真实运行门仍保留。

| 工作票 | 独立交付 | Blocking | 状态 |
| --- | --- | --- | --- |
| [R1 VX-005A](VX-005A-ingest-init-pressure.md) | 当前ingestion跨过初始化并完成真实批次 | None — 执行批准后可开始 | partial；5/6 GiB、启动/初始化已过；全批门待验 |
| [R2 VX-005B](VX-005B-failed-reentry.md) | 已确认的失败请求只重入一次 | VX-005A（真实运行与共享写范围） | blocked；R1运行门未过 |
| [R3 VX-009C](VX-009C-local-article-library.md) | 已存原文与译文在本地网页完整可读 | None — 不依赖RAG、Wiki、公开accepted或云发布 | local accepted；完整私有文章库 |
| [R4 VX-004A](VX-004A-rss-source-and-body.md) | RSS来源与正文结果可对账 | None（主ingestion真实验收使用VX-005A运行门） | partial；源码/源32部署，新正文L2ok |
| [R5 VX-004B](VX-004B-wechat-coverage.md) | 公众号按目标周期轮转覆盖 | None — 默认沿现有周期与单次预算 | deployed / coverage-watching；未额外付费扫 |
| [R6 VX-012D](VX-012D-storage-convergence.md) | 同版图/KV与向量副本可验证并回滚 | 决策03、VX-005A；生产提升还需具体目标/静止窗授权 | blocked；决策03/运行门/窗口 |
| [R7 VX-004C](VX-004C-wiki-evolution.md) | 一条Wiki建议形成实质正文更新 | VX-005A（稳定来源/批次边界）；离线演示可先做 | blocked；R1运行门未过 |
| [R8 VX-004D](VX-004D-stored-source-production.md) | 已存正文贯通现有知识生产 | VX-009C（复用明确的只读原文函数） | code accepted / native-runtime BLOCKED |
| [R9 VX-009D](VX-009D-three-module-acceptance.md) | 同一来源的三模块闭环本地收口 | VX-005A、VX-005B、VX-009C、VX-009B1、VX-004A/B/C/D、VX-012D | blocked；全链前置门未齐 |

复用009B1/B2/B3、008/011，不重复开票；旧表的历史partial/queued保留。存储012D还需[只读取证决策03](decisions/03-storage-snapshot-promotion.md)，单云仍需既有[主机决策01](decisions/01-single-cloud-host.md)。本地原文读取不受公开accepted门约束，默认公众号预算沿现状；完整数据源/允许变更和具体红绿命令见计划。

[KNOWN] 用户已授权重新规划并开始实施。按[当前计划](../../superpowers/plans/2026-09-09-vitax-product-architecture.md)和[ADR0004](../../adr/0004-minimal-knowledge-product.md)推进；`.planning/ISSUES.md`为权威backlog，本目录是对应执行说明。复用VX编号，不新增tracker。局部accepted不等于整项完成。

| ID | 当前工作 | 依赖与定位 | 状态 |
| --- | --- | --- | --- |
| [VX-001](VX-001-source-drift-classification.md) | 所涉远端源码核对 | 在具体远端变更前检查，不追全量漂移闭合 | partial evidence |
| [VX-002](VX-002-environment-verification.md) | 目标环境核实 | 历史preflight保留；远端动作刷新 | accepted historical preflight |
| [VX-003](VX-003-sync-script-exit-status.md) | 同步失败退出码 | 历史必要修复，不扩大旧同步 | local/remote offline accepted |
| [VX-004](VX-004-isolated-single-article-flow.md) | 真实来源→知识/Wiki/选图→公开投影 | 两源候选已接受，代表样本另验收 | partial；两源切片accepted |
| [VX-005](VX-005-startup-cleanup-retry.md) | 旧链必要保护 | 只处理仍影响现网问题，不阻塞新产品 | partial；不扩展恢复 |
| [VX-006](VX-006-hermes-codex-escalation.md) | Hermes→Codex→通知 | 合成证据保留，随真实故障完善 | partial functional evidence |
| [VX-007](VX-007-publication-contract.md) | 公开读库；之后完整包 | 首片无依赖；完整包需VX-004/009产物 | partial (local read model accepted) |
| [VX-009](VX-009-real-site-and-fts.md) | 站点和共享HTTP/MCP查询 | VX-007读库；真实内容验收需VX-004，不依赖云发布 | partial；本地Reader accepted，MCP后续 |
| [VX-010](VX-010-byollm-agentrag.md) | 工具取证修正；BYOLLM研究 | 内部修正无依赖；公共产品需VX-009 | partial (internal text retrieval accepted) |
| [VX-008](VX-008-versioned-cloud-publication.md) | 云端完整版本发布 | VX-007完整包、VX-004/009验收＋目标核实 | queued |
| [VX-011](VX-011-scheduling-pause-resume.md) | 单调度与日更 | 本地随VX-004；生产依赖VX-008 | queued |
| [VX-012](VX-012-single-writer-cutover.md) | 导入和单云切换 | 导入012A→B→C；切换需008/010/011＋恢复与现场证据 | 012A accepted；012B private pilot accepted/公开待验；012C queued |

[INFERRED] 依赖按子切片解释：VX-007读库→VX-009本地站点→VX-007完整包→VX-008云发布，不形成“必须先云发布才能开发站点”的循环。依赖不要求编号大小排序。组件质量/资源对照嵌入实际产品切片，不单独建benchmark平台。

当前写范围和验收见根目录 EXECUTION.md；前三阶段及Wiki历史证据不作废，但不再追加旧入口合成probe。

## 当前 Sprint（2026-09-20）：Reader + Safe Public Knowledge

[INFERRED] 按[规格](../../spec/VITAX_READER_SAFE_PUBLIC_SPEC.md)和[实施计划](../../superpowers/plans/2026-09-20-vitax-reader-safe-public-sprint.md)，首个产品 Sprint 只完成安全公开知识、真实读者站和本地浏览器验收。VX-007A 与 VX-009A1 可并行，VX-009A2 汇合；不混入全量迁移、云部署或 BYOLLM。

| 子票 | 独立交付 | Blocking edges | 状态 |
| --- | --- | --- | --- |
| [VX-007A](VX-007A-safe-public-knowledge.md) | accepted knowledge/Wiki 与必要摘录的安全公开切片 | 无 | 2026-10-01 local accepted |
| [VX-009A1](VX-009A1-real-reader-site.md) | 两来源真实读者站，无 mock | 无 | 2026-10-01 local accepted |
| [VX-009A2](VX-009A2-local-release-uat.md) | 最小 release 目录与浏览器/隐私验收 | VX-007A＋VX-009A1 | 2026-10-01 local accepted（零图片） |

## 迁移后续票（2026-09-10规划，保留）

| 子票 | 独立交付 | Blocking edges |
| --- | --- | --- |
| [VX-012A](VX-012A-legacy-first-record.md) | 一篇旧文章保全转换、新库可读 | 无，可开始 |
| [VX-012B](VX-012B-legacy-batch.md) | 20篇零LLM私有导入、幂等/保全已通过；公开资格待验 | VX-012A；当前partial |
| [VX-012C](VX-012C-full-candidate.md) | 同入口全量隔离候选、恢复清单与对账 | VX-012B；不依赖云发布 |
| [VX-009A](VX-009A-reader-slice.md) | ZIP真实文章/Wiki/证据浏览 | 无，用已接受两源可开始 |
| [VX-009B](VX-009B-legacy-search-mcp.md) | 旧知识与新Wiki统一站点搜索/HTTP/MCP | VX-012B＋VX-009A |

[INFERRED] 本轮只读导出与候选导入，未授权执行生产切换；父票不因子票完成而自动关闭。子票为现有tracker的执行细分，不另建工作流。

[INFERRED] 资源顺序以10/1核心计划为准：本地Reader门已关闭；后续单云候选→日更，旧知识导入/高级检索只按真实需求推进；最终切换单独验收。012B的20篇私有导入不重做。

## 下一阶段草案（2026-10-01）

[计划](../../superpowers/plans/2026-10-01-vitax-reviewed-content-sprint.md) / [TDD](../../spec/VITAX_REVIEWED_CONTENT_TDD.md)为现有VX-009B的收尾切片，不另建tracker。所有票当前proposed，不代表已授权实施。

| 子票 | 行为与blocking |
| --- | --- |
| [VX-009B1](VX-009B1-cjk-lexical-search.md) | 中文短词在站点/HTTP/MCP一致命中；无未完成前置 |
| [VX-009B2](VX-009B2-reviewed-legacy-replay.md) | 审核绑定接受、原语言与基线保全、可重放CLI；无B1依赖 |
| [VX-009B3](VX-009B3-reviewed-content-batch.md) | 最多5个旧文章解读/Wiki候选、至少各1新增合格知识及证据闭环；依赖B1+B2 |
