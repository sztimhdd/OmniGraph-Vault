# 技术词检索相关且解释可见

**Status:** proposed / 待执行。本轮只授权体验登记与规划。  
**Blocked by:** None；跨范围接续归G2。  
**Risk / controller:** M / 可写6.1-Sol票级主控；先核工具面，按AGENTS派工，无孙代理。

**What to build:** 技术词检索相关且解释可见。关联权威issues #110, #111。

**候选范围（不是源码根因结论）：** vitax/local_articles.py、knowledge.py现有查询与站点列表；先核FTS能力，不加搜索服务。

**接受门：**

- [ ] #110：TLA/TLA+能找到目标而不因gitlab.com误入；上下文、C++等不退化；实际匹配正文仍可检索，无新搜索服务或每次LLM调用。

- [ ] #111：ELF等正文命中有可解释片段；全站统计与结果统计分开；有下一页时明确还有更多，不能伪称本页数为全部数。

**保持：** 原文/译文与既有数据可恢复，公私边界、原始引文和相关WIP不变。不自动commit/push或改生产。

**验证：** 先最小失败用例，再最小实现、定向回归和真实浏览器样本复验；不增框架，不清库/重算，不做深问API/MCP。

[开发计划](../../superpowers/plans/2026-10-03-vitax-reader-experience.md) / [浏览器证据](../../research/2026-10-03-vitax-reader-audit/REPORT.md)。派工前asd-ste100 Strict，结果STATUS/CHANGES/EVIDENCE/RISKS/NEXT；执行前核对既有授权范围与剩余额度，不要求重复批准已授权动作。
