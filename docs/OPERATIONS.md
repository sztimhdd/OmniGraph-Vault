# VitaX 运维入口

主机与运行目录见 [部署档案](deployments/VITAX_DEPLOYMENT_BASELINE.md)，操作前核对目标和实际服务状态。
批次状态查询见 [管家报告](deployments/2026-10-04-pipeline-steward-check/REPORT.md)。

- 查最近批次的成功、失败、积压和首个错误。服务active不等于任务完成。
- 使用已有日志、SQLite查询与timer；不为检查健康重跑采集或调用模型。
- 普通故障按已有授权自动处理，恢复失败再报警。扫码、预算不足或无法恢复时告诉用户最小动作。
- 保留原文、缓存和已发生费用；发布失败继续服务上一版。不要为了恢复服务清空数据库。
- 模型、入口与费用以当前配置和 [批处理方案](spec/VITAX_HOBBY_TDD.md) 为准，不沿用旧Gemini/Claude默认值。
- 使用 `.venv/bin/python`；`config.py`默认读Hermes环境，离线检查设置 `OMNIGRAPH_LOAD_ENV=0`，并使用测试数据。

## 当前部署（10/9快照）

- 主站：http://47.103.73.20:8767/；`vitax-reader-port.service`原生映射到内部8788。旧`omni-mcp`已禁用，未来MCP另选端口。
- 网站机ack-node-1：`vitax-reader`，数据/站点在`/root/vitax-mvp/current`，媒体在`/root/vitax-mvp/media`。
- 采集机ack-node-2：`vitax-producer.timer`调用同一producer，缓存/账本在`/root/.vitax-local-automation/producer-root`；Mac只镜像。旧Pro翻译timer禁用。
- 本次已修免费辅助进程启动及Qdrant默认5秒期限；新客户端30秒，旧在途实例不变。重装依赖需重应用[补丁](../deploy/lightrag-qdrant-timeout.patch)。
- 未关票：完整自然批次、Wiki积压、KG引用直达原文、域名/HTTPS。以[执行报告](deployments/2026-10-09-mvp/REPORT.md)和[issues](../.planning/ISSUES.md)的实际结果为准。

业务配置和调度不因文档更新自动重启。运行数据、凭据和原始日志不入Git；本仓库保存代码、计划和总结。
