---
status: accepted
---

# PC 负责知识生产，单台云主机负责公开服务

[KNOWN] 用户确认以长期在线且具备本地 CDP、网络与计算资源优势的 Hermes PC 承担知识生产，以一台阿里云主机承载 MCP、VitaX、知识数据副本及 vitaclaw-site。PC 是生产数据唯一写入端，云端提供发布与查询；选择这一分工以替代两台云机重复部署，代价是需要处理 PC 离线和跨环境发布一致性。

[KNOWN] Codex 通过 SSH 管理项目变更，Hermes Agent 承担智能任务及获准的运行期自动修复，权限见 [ADR 0002](0002-autonomous-repair-authority.md)；用户要求自主加工和自动发布。具体模型分工和恢复目标仍待设计，云端服务副本不等于经过恢复验证的历史备份。
