# VX-004A — RSS来源与正文结果可对账

**Parent:** VX-004 / #96、#97。  
**Blocked by:** None（主ingestion真实验收使用VX-005A运行门）。  
**Status:** partial — failure reporting及feed32已部署，一新正文/L2ok；旧候选失败、其余来源及自然日程待验。  
**Risk / worker:** M / 6.1-Sol。

**What to build:** 有效RSS源按原日程进入文章库，部分源/正文失败准确报告，选定一旧一新候选有真实正文和全文分类结果。

- [ ] 只处理明确需保留的失效源及首失败类型，已有原始记录保留；不关闭TLS、新增访问fallback或无界重抓。
- [ ] fetch/正文summary区分完整成功、部分失败与全失败，部分失败非零；成功部分仍持久化，告警未核不声称缺失。
- [ ] 正文补抓每候选/运行最多一次；一旧一新原文hash、持久化和Layer2结果闭环，失败有明确处置。
- [ ] 现有相关小检查和下一原RSS日程结果可审阅；抓源成功不冒充全文或ingestion成功。

**Implementation reference:** [三模块规格](../../spec/VITAX_THREE_MODULE_EXECUTION_SPEC.md) / [计划 R4](../../superpowers/plans/2026-10-02-vitax-three-module-execution.md)。精确文件、接口、红绿命令在计划中；本票只声明可验收行为和blocking。

仅写主控派工范围，保留数据/WIP，执行前刷新事实/工具面。无自动commit/push、fallback或孙代理；两次同分支失败停下，结果使用STATUS/CHANGES/EVIDENCE/RISKS/NEXT。


本轮状态以[执行报告](../../deployments/2026-10-02-plan-execution/REPORT.md)及其定时/数据库收据为准；历史配置或测试不作未观察运行门的PASS。
