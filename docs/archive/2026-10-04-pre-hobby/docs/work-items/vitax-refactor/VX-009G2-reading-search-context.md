# 跨范围往返阅读不丢上下文

**Status:** proposed / 待执行。本轮只授权体验登记与规划。  
**Blocked by:** 正文验收依赖G1；导航映射可先做。  
**Risk / controller:** L / 可写6.1-Sol票级主控；先核工具面，按AGENTS派工，无孙代理。

**What to build:** 跨范围往返阅读不丢上下文。关联权威issues #105, #106, #109。

**候选范围（不是源码根因结论）：** routes.ts、Header.tsx、KnowledgeDetailPage.tsx、LocalArticlesPage.tsx；必要的私有只读来源映射。

**接受门：**

- [ ] #105：从一篇解读能读本地原文/译文再返回；存在相关Wiki时可达；public-only部署不暴露私有内容。

- [ ] #106：文章/知识两条路径返回保留q、kind/source、has_body和offset；刷新、直达URL有合理回退，返回参数不能指向站外。

- [ ] #109：TLA公开零结果能一击查看原文结果；上下文仍可筛文章/Wiki；public-only没有私有检索入口。

**保持：** 原文/译文与既有数据可恢复，公私边界、原始引文和相关WIP不变。不自动commit/push或改生产。

**验证：** 先最小失败用例，再最小实现、定向回归和真实浏览器样本复验；不增框架，不清库/重算，不做深问API/MCP。

[开发计划](../../superpowers/plans/2026-10-03-vitax-reader-experience.md) / [浏览器证据](../../research/2026-10-03-vitax-reader-audit/REPORT.md)。派工前asd-ste100 Strict，结果STATUS/CHANGES/EVIDENCE/RISKS/NEXT；执行前核对既有授权范围与剩余额度，不要求重复批准已授权动作。
