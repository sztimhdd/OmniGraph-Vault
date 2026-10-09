# VX-004D — 已存正文贯通现有知识生产

**Parent:** VX-004 / 新旧输入交接。  
**Blocked by:** VX-009C（复用明确的只读原文函数）。  
**Status:** code slice accepted / live BLOCKED — 原Markdown输入与来源规则通过；原生生成运行面未配置。  
**Risk / worker:** M / 6.1-Sol。

**What to build:** 从已存原文选1–2个来源，通过明确stored-markdown输入进入现有producer，生成有精确引用的文章解读及跨来源Wiki，避免全量重抓。

- [ ] 原始Markdown字节/hash、来源表ID/快照、时间unknown与representation保存时间分开；不伪造HTML capture。
- [ ] 标准paragraph/hash/revision与quote逐字校验；code、未知时间、错误hash和越界拒绝，既有HTML合同不回归。
- [ ] 只读原body，不拿译文/body_rewritten充原文；Hermes最终32KiB上限拒绝超限而不截断，完整资料仍保全。
- [ ] 复用article/wiki stage、accepted合并和usage；一新来源解读+另一个已接受来源Wiki真实成立，旧95基线保留。
- [ ] 显式小批、source hash/recipe重用已接受输出；不宣称所有旧文已重新加工或自动公开。

**Implementation reference:** [三模块规格](../../spec/VITAX_THREE_MODULE_EXECUTION_SPEC.md) / [计划 R8](../../superpowers/plans/2026-10-02-vitax-three-module-execution.md)。精确文件、接口、红绿命令在计划中；本票只声明可验收行为和blocking。

仅写主控派工范围，保留数据/WIP，执行前刷新事实/工具面。无自动commit/push、fallback或孙代理；两次同分支失败停下，结果使用STATUS/CHANGES/EVIDENCE/RISKS/NEXT。


本轮状态以[执行报告](../../deployments/2026-10-02-plan-execution/REPORT.md)及其定时/数据库收据为准；历史配置或测试不作未观察运行门的PASS。
