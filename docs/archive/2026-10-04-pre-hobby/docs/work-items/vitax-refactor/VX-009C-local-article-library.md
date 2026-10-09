# VX-009C — 已存原文与译文在本地网页完整可读

**Parent:** VX-009 / #99。  
**Blocked by:** None — 不依赖RAG、Wiki、公开accepted或云发布。  
**Status:** local accepted — 完整10,103条私有文章镜像/网页；自动日更未交付。  
**Risk / worker:** L / 6.1-Sol票级主控。

**What to build:** 同一个VitaX应用显式读取完整私有文章SQLite，维护者从列表/搜索打开原文或已有译文，分页到全部记录并看缺失状态。

- [x] 来源+record_id及当次完整数据库receipt可对账；Layer2 reject/failed/无ingestion均可读，缺正文仍可列出。
- [x] 过滤先于分页，稳定排序与第100条之后续读、原文/译文详情及同ID异来源正确；列表不含全文。
- [x] 默认公开模式私有API/页面404，local opt-in限定loopback与真实peer；MCP六工具和public bootstrap不扩私有范围。
- [x] 未配置公共知识DB仍可本地阅读，不创建伪release；正常镜像/receipt同目录提升读新ID并清旧视图，原地未完成更新拒绝旧ID，不要求人工重启。
- [x] 私有页面runtime读取，React文本渲染，公开DB/HTML/JS无private sentinel；不全量重导/翻译。
- [x] 针对HTTP/路由检查与真实本地浏览器主路径、刷新、手机视口通过；不把旧验收当本轮PASS。

**Implementation reference:** [三模块规格](../../spec/VITAX_THREE_MODULE_EXECUTION_SPEC.md) / [计划 R3](../../superpowers/plans/2026-10-02-vitax-three-module-execution.md)。精确文件、接口、红绿命令在计划中；本票只声明可验收行为和blocking。

仅写主控派工范围，保留数据/WIP，执行前刷新事实/工具面。无自动commit/push、fallback或孙代理；两次同分支失败停下，结果使用STATUS/CHANGES/EVIDENCE/RISKS/NEXT。

本轮状态以[执行报告](../../deployments/2026-10-02-plan-execution/REPORT.md)及其定时/数据库收据为准；历史配置或测试不作未观察运行门的PASS。
