# VX-012D — 同版图/KV与向量副本可验证并回滚

**Parent:** VX-012 / #98。  
**Blocked by:** 决策03、VX-005A；生产提升还需具体目标/静止窗授权。  
**Status:** proposed / ready-for-review；待执行。  
**Risk / worker:** L / 6.1-Sol票级主控。

**What to build:** 旧KG使用者读取一份一致存储副本；新增、修改和删除由候选完整快照体现，原目标历史数据保留，提升和回滚均有证据。

- [ ] 源权威、实际writer/consumer绑定、版本/拓扑/空间和静止窗先由决策03确定，不凭多余ID删除目标历史集合。
- [ ] SQLite/graph/KV/chunks与三个Qdrant集合同窗快照，新目录/新集合恢复；原生功能先验证，不重embedding，不强杀活动writer。
- [ ] 核身份/引用闭包、增改删样本及真实consumer新增资料检索；count更大或sync exit0不是充分证明。
- [ ] 只有准确绑定与回滚成立才受控提升并fresh读回；候选接受≠生产已服务，能力/数据归属不清即BLOCKED。
- [ ] 先量完整周期成本，未证明不够用不造watermark/tombstone平台；无实际KG consumer的Hermes镜像不强搬全图。

**Implementation reference:** [三模块规格](../../spec/VITAX_THREE_MODULE_EXECUTION_SPEC.md) / [计划 R6](../../superpowers/plans/2026-10-02-vitax-three-module-execution.md)。精确文件、接口、红绿命令在计划中；本票只声明可验收行为和blocking。

仅写主控派工范围，保留数据/WIP，执行前刷新事实/工具面。无自动commit/push、fallback或孙代理；两次同分支失败停下，结果使用STATUS/CHANGES/EVIDENCE/RISKS/NEXT。

