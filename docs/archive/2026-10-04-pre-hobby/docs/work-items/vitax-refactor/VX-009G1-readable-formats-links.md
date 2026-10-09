# 原文和译文可读且链接指向正确

**Status:** proposed / 待执行。本轮只授权体验登记与规划。  
**Blocked by:** None。  
**Risk / controller:** M / 可写6.1-Sol票级主控；先核工具面，按AGENTS派工，无孙代理。

**What to build:** 原文和译文可读且链接指向正确。关联权威issues #100, #101。

**候选范围（不是源码根因结论）：** localArticles.ts、LocalArticlesPage.tsx、links.tsx；先追展示链与已有格式能力。

**接受门：**

- [ ] #100：原文与译文的标题、段落、列表、代码、链接和已可用图片正常展示；TLA+符号保留，原文hash不变，HTML脚本和危险URL不执行。

- [ ] #101：相邻Markdown链接独立；中文/英文标点不进入href；Wikipedia括号URL仍完整；两种语言样本都实际点击或核对目标。

**保持：** 原文/译文与既有数据可恢复，公私边界、原始引文和相关WIP不变。不自动commit/push或改生产。

**验证：** 先最小失败用例，再最小实现、定向回归和真实浏览器样本复验；不增框架，不清库/重算，不做深问API/MCP。

[开发计划](../../superpowers/plans/2026-10-03-vitax-reader-experience.md) / [浏览器证据](../../research/2026-10-03-vitax-reader-audit/REPORT.md)。派工前asd-ste100 Strict，结果STATUS/CHANGES/EVIDENCE/RISKS/NEXT；执行前核对既有授权范围与剩余额度，不要求重复批准已授权动作。
