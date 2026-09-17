# VitaX 重构工单

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
| [VX-009](VX-009-real-site-and-fts.md) | 站点和共享HTTP/MCP查询 | VX-007读库；真实内容验收需VX-004，不依赖云发布 | queued |
| [VX-010](VX-010-byollm-agentrag.md) | 工具取证修正；BYOLLM研究 | 内部修正无依赖；公共产品需VX-009 | partial (internal text retrieval accepted) |
| [VX-008](VX-008-versioned-cloud-publication.md) | 云端完整版本发布 | VX-007完整包、VX-004/009验收＋目标核实 | queued |
| [VX-011](VX-011-scheduling-pause-resume.md) | 单调度与日更 | 本地随VX-004；生产依赖VX-008 | queued |
| [VX-012](VX-012-single-writer-cutover.md) | 导入和单云切换 | 导入012A→B→C；切换需008/010/011＋恢复与现场证据 | inventory complete；migration queued |

[INFERRED] 依赖按子切片解释：VX-007读库→VX-009本地站点→VX-007完整包→VX-008云发布，不形成“必须先云发布才能开发站点”的循环。依赖不要求编号大小排序。组件质量/资源对照嵌入实际产品切片，不单独建benchmark平台。

当前写范围和验收见根目录 EXECUTION.md；前三阶段及Wiki历史证据不作废，但不再追加旧入口合成probe。

## 下一轮子票（2026-09-10规划）

| 子票 | 独立交付 | Blocking edges |
| --- | --- | --- |
| [VX-012A](VX-012A-legacy-first-record.md) | 一篇旧文章保全转换、新库可读 | 无，可开始 |
| [VX-012B](VX-012B-legacy-batch.md) | 20篇零LLM导入、全量质量预览、逐条对账 | VX-012A |
| [VX-012C](VX-012C-full-candidate.md) | 同入口全量隔离候选、恢复清单与对账 | VX-012B；不依赖云发布 |
| [VX-009A](VX-009A-reader-slice.md) | ZIP真实文章/Wiki/证据浏览 | 无，用已接受两源可开始 |
| [VX-009B](VX-009B-legacy-search-mcp.md) | 旧知识与新Wiki统一站点搜索/HTTP/MCP | VX-012B＋VX-009A |

[INFERRED] 本轮只读导出与候选导入，未授权执行生产切换；父票不因子票完成而自动关闭。子票为现有tracker的执行细分，不另建工作流。

[INFERRED] 资源顺序：下一大块仅012A/B，之后009A/B与012C，再010、完整发布/日更、最终切换。009A无技术阻塞不代表本轮必须并发扩展前端。
