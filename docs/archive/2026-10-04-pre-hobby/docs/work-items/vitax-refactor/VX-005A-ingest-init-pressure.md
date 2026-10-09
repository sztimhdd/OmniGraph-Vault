# VX-005A — 当前ingestion跨过初始化并完成真实批次

**Parent:** VX-005 / #93。  
**Blocked by:** None — 执行批准后可开始。  
**Status:** partial — memory5/6 GiB已应用；原18UTC启动/初始化已过；完整批次/下一timer待验收。  
**Risk / worker:** L / 6.1-Sol票级主控。

**What to build:** 从当前候选入口定位初始化资源阻塞，应用证据支持的最小修复，完成真实批次及下一既有timer；保留原库与业务路线。

- [ ] 刷新阶段/pid/cgroup及实际版本，确认阻塞仍成立，分配热点或合法资源不匹配有证据；外部已恢复时不重复改。
- [ ] 真实入口红→绿或owner-native配置验证，保留硬限制、数据、Vision和prestart合同；不是仅加timeout/并发参数。
- [ ] 完整批次新增持久化ok且退出；下一原timer仍通过，单篇成功只记partial。
- [ ] 有具体变更、备份/回滚、针对检查和未验范围；两次同分支失败停止。

**Implementation reference:** [三模块规格](../../spec/VITAX_THREE_MODULE_EXECUTION_SPEC.md) / [计划 R1](../../superpowers/plans/2026-10-02-vitax-three-module-execution.md)。精确文件、接口、红绿命令在计划中；本票只声明可验收行为和blocking。

仅写主控派工范围，保留数据/WIP，执行前刷新事实/工具面。无自动commit/push、fallback或孙代理；两次同分支失败停下，结果使用STATUS/CHANGES/EVIDENCE/RISKS/NEXT。


本轮状态以[执行报告](../../deployments/2026-10-02-plan-execution/REPORT.md)及其定时/数据库收据为准；历史配置或测试不作未观察运行门的PASS。
