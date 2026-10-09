# VX-009B2 — 已审旧知识可以重放并保留当前基线

**Parent:** VX-009B。  
**Blocked by:** None；已成功的单份接受流程及builder为现有材料。  
**Status:** proposed / ready-for-review（尚未实施）。

## 可验收交付

维护者显式提供旧文章解读/旧Wiki与独立审核记录，通过一个本地CLI形成公开增量；固定输入可重放，原语言保留，已有包和基线不被覆盖。

- [ ] 原artifact与实际标准化/提案双hash绑定；无审核、自报public、高confidence或变化输入均不能自动发布。
- [ ] 单源文章解读有稳定文章身份/修订与准确摘录；Wiki至少两不同来源，不能拿同源多版本凑数；关系端点闭包通过，冲突拒绝。
- [ ] 当前基线五集合逐条保留；英语旧Wiki不被重翻译，新生产中文规则不变。
- [ ] 私有原文/译文/未知字段不进入投影或stdout；输出已存在/构建失败保前版。
- [ ] synthetic单源article/两源wiki接受→fresh SQLite/HTTP可读；单源Wiki拒绝，固定元数据重放及必要红绿检查通过。

精确纯函数/CLI/字段/错误契约：[TDD](../../spec/VITAX_REVIEWED_CONTENT_TDD.md#32-已审核旧知识接受入口拟新增) / [计划Task 2](../../superpowers/plans/2026-10-01-vitax-reviewed-content-sprint.md#task-2--vx-009b2-复用已审核接受流程)。仅抽取已成功流程，不新增审核平台、数据库服务或Web/MCP管理工具；真实资料只在源码外授权候选区。
