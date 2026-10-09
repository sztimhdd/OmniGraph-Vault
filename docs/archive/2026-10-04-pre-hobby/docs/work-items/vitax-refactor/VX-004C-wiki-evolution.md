# VX-004C — 一条Wiki建议形成实质正文更新

**Parent:** VX-004 / 既有#5。  
**Blocked by:** VX-005A（稳定来源/批次边界）；离线演示可先做。  
**Status:** proposed / ready-for-review；待执行。  
**Risk / worker:** L / 6.1-Sol票级主控。

**What to build:** 复用既有建议队列和evolution worker，先隔离再实际应用一条有充分来源的建议，并证明正文/证据变化与幂等。

- [ ] dry-run仅核结构，不调用模型；source-aware来源解析成功，缺source/ref保持待核。
- [ ] 隔离副本完成正文、引用、applied state及重复运行无变更；RETRY/REJECT/占位不算成功。
- [ ] 首次真实技术建议limit=1，保留原生usage和业务provider；不全量bootstrap、重审134建议或新增评审链。
- [ ] 涉及kb的本地E2E与相关state/worker检查成立；后续统一调度调用原入口，page applied不自动等于公开accepted。

**Implementation reference:** [三模块规格](../../spec/VITAX_THREE_MODULE_EXECUTION_SPEC.md) / [计划 R7](../../superpowers/plans/2026-10-02-vitax-three-module-execution.md)。精确文件、接口、红绿命令在计划中；本票只声明可验收行为和blocking。

仅写主控派工范围，保留数据/WIP，执行前刷新事实/工具面。无自动commit/push、fallback或孙代理；两次同分支失败停下，结果使用STATUS/CHANGES/EVIDENCE/RISKS/NEXT。

