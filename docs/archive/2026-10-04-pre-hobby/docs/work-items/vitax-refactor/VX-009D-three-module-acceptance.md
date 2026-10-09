# VX-009D — 同一来源的三模块闭环本地收口

**Parent:** VX-009 / 三模块汇总门。  
**Blocked by:** VX-005A、VX-005B、VX-009C、VX-009B1、VX-004A/B/C/D的本地切片门、VX-012D；公众号自然全周期观察另列，不伪称已通过。  
**Status:** proposed / ready-for-review；待执行。  
**Risk / worker:** M / Sol主控、Luna确定性断言。

**What to build:** 维护者能跟踪同一真实新来源从抓取到本地原文、知识/图/Wiki和同版HTTP/MCP/网页；各阶段分别有收据。

- [ ] 新来源+第二Wiki来源的identity/body hash→DB→私有阅读→processed/引用→Wiki变化→accepted→新release逐段可核。
- [ ] 所有有正文来源逐ID有本地去向，缺正文/缺译文/超限单列，不以公开资格阻挡本地阅读。
- [ ] 一次真实browser主路径/刷新/移动、SDK MCP/HTTP同query/同release/同JSON；坏输入保前版，private sentinel不出包。
- [ ] 发现前票缺陷回所属票最小修复，仅重跑受影响路径；不新增benchmark/UAT平台。
- [ ] scope/fixed point/WIP/证据/限制/next有checkpoint，子代理终态关闭；本地接受不关闭云/日更/BYOLLM/最终切换父票。

**Implementation reference:** [三模块规格](../../spec/VITAX_THREE_MODULE_EXECUTION_SPEC.md) / [计划 R9](../../superpowers/plans/2026-10-02-vitax-three-module-execution.md)。精确文件、接口、红绿命令在计划中；本票只声明可验收行为和blocking。

仅写主控派工范围，保留数据/WIP，执行前刷新事实/工具面。无自动commit/push、fallback或孙代理；两次同分支失败停下，结果使用STATUS/CHANGES/EVIDENCE/RISKS/NEXT。
