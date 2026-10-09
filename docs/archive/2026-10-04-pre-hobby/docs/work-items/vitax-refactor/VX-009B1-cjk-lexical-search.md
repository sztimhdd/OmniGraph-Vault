# VX-009B1 — 中文短词在站点与MCP中一致可查

**Parent:** VX-009B。  
**Blocked by:** None；当前Reader/MCP本地前置已完成。  
**Status:** local accepted — CJK7条，真实HTTP/MCP一致。  

## 可验收交付

维护者输入“上下文”等标题/正文中实际存在的中文短词，Reader、HTTP、MCP、现有页面都能返回同一公开结果；kind和limit不丢失，英文检索保持原路线。

- [x] 先证明现有合成红例与本地实测的中文漏检，不用改mock制造成功。
- [x] 共享查询接缝采用TDD字面子串合同，过滤先于limit、排序稳定；不分别重写网站/MCP。
- [x] 私有字段、特殊查询字符和旧参数限制不回归；英文FTS检查保持。
- [x] 小检查及真实HTTP/MCP同query读回通过，保存结果与剩余扫描上限。

精确路径、接口、SQL边界和测试名称：[TDD](../../spec/VITAX_REVIEWED_CONTENT_TDD.md#31-中文查询) / [计划Task 1](../../superpowers/plans/2026-10-01-vitax-reviewed-content-sprint.md#task-1--vx-009b1-中文字面检索)。只处理实际词法缺口，不引入向量/分词服务，不改变公开集合或迁移数据。

本轮状态以[执行报告](../../deployments/2026-10-02-plan-execution/REPORT.md)及其定时/数据库收据为准；历史配置或测试不作未观察运行门的PASS。
