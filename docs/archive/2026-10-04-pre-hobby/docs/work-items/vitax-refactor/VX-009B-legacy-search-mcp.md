# VX-009B — 旧知识与新Wiki在站点和MCP中统一检索

**Parent:** VX-009。
**Blocked by:** VX-012B、VX-009A。
**Status:** partial（2026-10-01：本地已审旧知识/关系及MCP共享读取accepted；更广内容/词法质量另验收）。

**What to build:** 读者和MCP客户端在同一release中检索导入旧知识与新Wiki，按名称定位关系并查看证据。

- [ ] 使用包含真实旧知识的合格公开候选，不用原两源样本替代迁移验收；公开不合格记录在站点/API/MCP均不可见。
- [ ] HTTP/MCP调用同一查询函数，共用visibility、limit和release_id；MCP使用实际协议客户端验证，不以直接调Python函数代替。
- [ ] 基于真实内容测试中文词、英文专名、缩写和版本表达；仅修实际词法检索缺口，不预装分词/向量服务。
- [ ] 用户能由知识页面或实体名称找到related，不必猜entity_id；关系与证据可追溯。旧缺证据关系仍待核，不补造。
- [ ] 浏览器搜索命中至少一条真实旧知识，详情与私有导入资产的来源映射一致；Wiki可读取。HTTP/MCP同query结果语义一致、同版且非空。
- [ ] 负向覆盖未知ID、非法路径/URL、超限参数、私有哨兵、危险正文；页面/搜索/证据不能混release。

**Scope:** 保留一种查询实现，扩展已有SDK薄适配；不做BYOLLM、AgentRAG、登录管理、云发布或生产切换。
**Verification:** 真实旧知识候选库＋HTTP/MCP契约＋确定性浏览器UAT＋独立代码与产品验收；分别报告结构迁移、公开资格与语义审核，不能混称“全部知识已验收”。

## 2026-10-01实际执行

[旧资产迁移与读库接入报告](/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/legacy-migration-20261001T162719/REPORT.md)。原Reader前置门已关闭；严格引用/语义审核后，新增1旧英文Wiki片段、2实体、1关系，保留原基线。5组浏览器通过；无MCP实现或协议PASS，不将整票关闭。

## MCP阻塞解除（2026-10-01）

用户明确授权Sol/Luna接手，已复用单一ReadModel挂同FastAPI的MCP六只读工具。21项小检查及实际ClientSession/StreamableHTTP同版同JSON通过；两P2复审关闭。见[MCP验收](/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/legacy-migration-20261001T162719/MCP-REPORT.md)。原无代码499阻塞记录作为历史保留，不再表示当前本地MCP未实现。

## 当前待规划项已落票（2026-10-01）

剩余词法/内容可用性按[B1](VX-009B1-cjk-lexical-search.md)、[B2](VX-009B2-reviewed-legacy-replay.md)、[B3](VX-009B3-reviewed-content-batch.md)推进，状态均proposed；详见[阶段计划](../../superpowers/plans/2026-10-01-vitax-reviewed-content-sprint.md)与[TDD](../../spec/VITAX_REVIEWED_CONTENT_TDD.md)。不重做已接受MCP、迁移或云端整票。

用户同意补入旧文章解读：B2区分单源article与跨来源wiki，B3最多5候选覆盖两类，目标各至少1新增合格项；原文/译文仍私有。此前仅旧Wiki的小批范围由此修正，缺已有解读列待生产，不自动重写全部历史文章。
