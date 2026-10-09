# VX-005B — 已确认的失败请求只重入一次

**Parent:** VX-005 / #94。  
**Blocked by:** VX-005A（真实运行与共享写范围）。  
**Status:** proposed / ready-for-review；待执行。  
**Risk / worker:** M / 6.1-Sol。

**What to build:** 维护者的reconcile假成功修正可以请求一次重试，普通failed不会无限重入，成功与异来源记录仍排除。

- [ ] 明确retry_requested默认0、仅受控reconcile置1；保留failed、旧版本与记录ID，不用负版本/伪skipped/删行解锁。
- [ ] 初始化失败不消费请求，正文尝试前原子消费；再失败不自动重复，重复申请幂等。
- [ ] 双来源同ID、正常ok/stale skipped合同及fixture schema不回归，迁移先于代码且可重跑。
- [ ] 先离线入口红绿，再一条明确可恢复记录实际读回；历史258 failed不全量重放。

**Implementation reference:** [三模块规格](../../spec/VITAX_THREE_MODULE_EXECUTION_SPEC.md) / [计划 R2](../../superpowers/plans/2026-10-02-vitax-three-module-execution.md)。精确文件、接口、红绿命令在计划中；本票只声明可验收行为和blocking。

仅写主控派工范围，保留数据/WIP，执行前刷新事实/工具面。无自动commit/push、fallback或孙代理；两次同分支失败停下，结果使用STATUS/CHANGES/EVIDENCE/RISKS/NEXT。

