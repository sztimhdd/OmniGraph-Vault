# VX-009B — 旧知识与新Wiki在站点和MCP中统一检索

**Parent:** VX-009。
**Blocked by:** VX-012B、VX-009A。
**Status:** blocked-by-VX-012B-and-VX-009A。

**What to build:** 读者和MCP客户端在同一release中检索导入旧知识与新Wiki，按名称定位关系并查看证据。

- [ ] 使用包含真实旧知识的合格公开候选，不用原两源样本替代迁移验收；公开不合格记录在站点/API/MCP均不可见。
- [ ] HTTP/MCP调用同一查询函数，共用visibility、limit和release_id；MCP使用实际协议客户端验证，不以直接调Python函数代替。
- [ ] 基于真实内容测试中文词、英文专名、缩写和版本表达；仅修实际词法检索缺口，不预装分词/向量服务。
- [ ] 用户能由知识页面或实体名称找到related，不必猜entity_id；关系与证据可追溯。旧缺证据关系仍待核，不补造。
- [ ] 浏览器搜索命中至少一条真实旧知识，详情与私有导入资产的来源映射一致；Wiki可读取。HTTP/MCP同query结果语义一致、同版且非空。
- [ ] 负向覆盖未知ID、非法路径/URL、超限参数、私有哨兵、危险正文；页面/搜索/证据不能混release。

**Scope:** 保留一种查询实现，扩展已有SDK薄适配；不做BYOLLM、AgentRAG、登录管理、云发布或生产切换。
**Verification:** 真实旧知识候选库＋HTTP/MCP契约＋确定性浏览器UAT＋独立代码与产品验收；分别报告结构迁移、公开资格与语义审核，不能混称“全部知识已验收”。
