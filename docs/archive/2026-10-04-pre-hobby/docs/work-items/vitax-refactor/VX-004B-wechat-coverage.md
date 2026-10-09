# VX-004B — 公众号按目标周期轮转覆盖

**Parent:** VX-004 / #95。  
**Blocked by:** None — 默认沿现有周期与单次预算。  
**Status:** deployed / coverage-watching — 保持周预算，真实无API预演通过；首次真实扫描10/4待验。  
**Risk / worker:** M / 6.1-Sol。

**What to build:** 明确运行名单中的公众号，包括零历史ingestion成功的来源，都能在约定周期内得到扫描尝试；零新增、失败及成功分开对账。

- [ ] 先核配置与DB差异形成源码外目标名单，只输出计数/hash；默认最多20号/每号最多2页、现行周期，不自动扩大额度。
- [ ] 最久未attempted优先，实际请求stamp attempted，成功/零新增才stamp scanned；失败可轮转且不伪造成功。
- [ ] 用户已选择保持预算；合成每run无重复、一个约定周期全部目标至少尝试一次，既有last_scanned_at成功语义及限流停止不变。
- [ ] 两页不能覆盖上次成功时间窗则准确报告coverage_gap，历史未知记unknown，不自动增加页数或把账号覆盖说成文章无遗漏。
- [ ] 一次真实预算内扫描对账，后续约定周期验证全目标；若每日扫描，执行前明确日预算再改原timer，不起第二扫描者。

代码/仿真和一次真实入口组成可交付本地切片；周周期完整现实覆盖继续coverage-watching/#95 partial，不以仿真关闭全部覆盖，不占一个controller在线等待数周，不阻塞R9单来源链的验收。

**Implementation reference:** [三模块规格](../../spec/VITAX_THREE_MODULE_EXECUTION_SPEC.md) / [计划 R5](../../superpowers/plans/2026-10-02-vitax-three-module-execution.md)。精确文件、接口、红绿命令在计划中；本票只声明可验收行为和blocking。

仅写主控派工范围，保留数据/WIP，执行前刷新事实/工具面。无自动commit/push、fallback或孙代理；两次同分支失败停下，结果使用STATUS/CHANGES/EVIDENCE/RISKS/NEXT。

本轮状态以[执行报告](../../deployments/2026-10-02-plan-execution/REPORT.md)及其定时/数据库收据为准；历史配置或测试不作未观察运行门的PASS。
