# 单调度本地网页自动更新发布

**Status:** ready-for-agent / authorized。  
**Blocked by:** VX-004E、VX-009E、VX-004F。  
**Risk / controller:** L / 可写6.1-Sol票级主控，Luna定向取证/测试、Sol复审，无孙。

**What to build:** 日程接续已有采集/加工结果，原子发布完整文章镜像与知识版本到本地网页，所有内部链接同版可用。

- [ ] 只有验证过的manifest/SQLite/site可提升，坏包保旧并如实失败
- [ ] 一个入口一个scheduler，正文私有、公开知识接受边界保持
- [ ] 同一真实源完整链到本地页面，下一次/重跑能自动更新且不重复加工
- [ ] 自动发布不依赖主控在线，状态/日志/备份/回滚明确；深问API/MCP不在范围

实施接缝/命令见[本轮计划](../../superpowers/plans/2026-10-02-vitax-local-automation.md)，范围与接受边界见[规格](../../spec/VITAX_LOCAL_AUTOMATION_SPEC.md)。关联既有#93–#99、VX-004/005/009/011；不再新建同义问题。用户已授权规划后执行，遵守同branch两失败与10%预算，结果STATUS/CHANGES/EVIDENCE/RISKS/NEXT。
