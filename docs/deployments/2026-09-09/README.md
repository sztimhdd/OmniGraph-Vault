# 2026-09-09 VitaX 部署审计证据

主报告：[三环境部署档案](../VITAX_DEPLOYMENT_BASELINE.md)。JSON 由只读 SSH 查询、HTTP 元数据请求与本地比较产生；每份采集文件自带时间戳。`source` 只保存代码哈希与包版本，不保存源码全文或密钥。

| 文件 | 内容 |
|---|---|
| [browser-reverse-tunnel-probe.json](browser-reverse-tunnel-probe.json) | 协议、工具发现与有界读查询 |
| [code-comparison.json](code-comparison.json) | 远端与 Mac 源码差异名单 |
| [handoff-source.json](handoff-source.json) | 源码 SHA 或交接文件指纹 |
| [hermes-agent-reply.md](hermes-agent-reply.md) | 指定 Agent 的历史背景答复 |
| [hermes-data.json](hermes-data.json) | 只读 SQL 聚合、业务时间与时区限制 |
| [hermes-detail.json](hermes-detail.json) | 脱敏源码选段、同步合同、进程归属 |
| [hermes-inventory.json](hermes-inventory.json) | 身份、Git、服务、环境键名、数据文件元数据、HTTP/Qdrant 状态 |
| [hermes-schedules.json](hermes-schedules.json) | systemd、crontab、Hermes cron 与 CDP |
| [hermes-source.json](hermes-source.json) | 源码 SHA 或交接文件指纹 |
| [hermes-worktrees-backups.json](hermes-worktrees-backups.json) | 工作树状态与备份目录元数据 |
| [mcp-data.json](mcp-data.json) | 只读 SQL 聚合、业务时间与时区限制 |
| [mcp-detail.json](mcp-detail.json) | 脱敏源码选段、同步合同、进程归属 |
| [mcp-diagnostics.json](mcp-diagnostics.json) | 日志分类、Docker／磁盘检查及其失败边界 |
| [mcp-disk-detail.json](mcp-disk-detail.json) | 磁盘变化、目录用量和有界日志尾部 |
| [mcp-hermes-tunnel-probe.json](mcp-hermes-tunnel-probe.json) | 协议、工具发现与有界读查询 |
| [mcp-inventory.json](mcp-inventory.json) | 身份、Git、服务、环境键名、数据文件元数据、HTTP/Qdrant 状态 |
| [mcp-public-probe.json](mcp-public-probe.json) | 协议、工具发现与有界读查询 |
| [mcp-runtime-checks.json](mcp-runtime-checks.json) | 最新资源／服务状态、1024d 实测与账户可用性 |
| [mcp-schedules.json](mcp-schedules.json) | systemd、crontab、Hermes cron 与 CDP |
| [mcp-source.json](mcp-source.json) | 源码 SHA 或交接文件指纹 |
| [mcp-worktrees-backups.json](mcp-worktrees-backups.json) | 工作树状态与备份目录元数据 |
| [pipeline-data.json](pipeline-data.json) | 只读 SQL 聚合、业务时间与时区限制 |
| [pipeline-detail.json](pipeline-detail.json) | 脱敏源码选段、同步合同、进程归属 |
| [pipeline-diagnostics.json](pipeline-diagnostics.json) | 日志分类、Docker／磁盘检查及其失败边界 |
| [pipeline-inventory.json](pipeline-inventory.json) | 身份、Git、服务、环境键名、数据文件元数据、HTTP/Qdrant 状态 |
| [pipeline-runtime-checks.json](pipeline-runtime-checks.json) | 最新资源／服务状态、1024d 实测与账户可用性 |
| [pipeline-schedules.json](pipeline-schedules.json) | systemd、crontab、Hermes cron 与 CDP |
| [pipeline-source.json](pipeline-source.json) | 源码 SHA 或交接文件指纹 |
| [pipeline-timeout-detail.json](pipeline-timeout-detail.json) | systemd 启动前超时原始消息 |
| [pipeline-worktrees-backups.json](pipeline-worktrees-backups.json) | 工作树状态与备份目录元数据 |

[校验与范围声明](verification.json)。

读取方式：`python3 -m json.tool <文件>`。缺失、拒绝、超时和未执行与成功分开记录；元数据健康不等于业务验收。文件完整性清单见 `SHA256SUMS`。
