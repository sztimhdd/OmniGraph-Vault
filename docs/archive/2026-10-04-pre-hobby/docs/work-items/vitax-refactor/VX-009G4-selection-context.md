# 选读筛选与同源归组

**Status:** proposed / 待执行。本轮只授权体验登记与规划。  
**Blocked by:** 复用G3片段；其他可先做。  
**Risk / controller:** M / 可写6.1-Sol票级主控；先核工具面，按AGENTS派工，无孙代理。

**What to build:** 选读筛选与同源归组。关联权威issues #102, #104, #112。

**候选范围（不是源码根因结论）：** export_vitax_library.py、私有读库/API、现有列表卡片；核已有元信息。

**接受门：**

- [ ] #102：重复来源以一组展示，可展开两条原始记录/版本；不同URL同标题不误合并。

- [ ] #104：卡片有具体来源和标明含义的时间，原文/译文语言清楚；支持日期顺序，不能把收录或release时间伪作文章发布日期。

- [ ] #112：两个具体来源/日期边界/仅有译文可组合，返回后保留；未知日期不被伪分类。

**保持：** 原文/译文与既有数据可恢复，公私边界、原始引文和相关WIP不变。不自动commit/push或改生产。

**验证：** 先最小失败用例，再最小实现、定向回归和真实浏览器样本复验；不增框架，不清库/重算，不做深问API/MCP。

[开发计划](../../superpowers/plans/2026-10-03-vitax-reader-experience.md) / [浏览器证据](../../research/2026-10-03-vitax-reader-audit/REPORT.md)。派工前asd-ste100 Strict，结果STATUS/CHANGES/EVIDENCE/RISKS/NEXT；执行前核对既有授权范围与剩余额度，不要求重复批准已授权动作。
