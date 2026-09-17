# VX-009 — 真实站点与共享公开查询

**What to build:** 接入用户KB-v2-site.zip，读者可浏览真实解读/Wiki/图片、关键词搜索、查看实体关系与原文证据。VitaX API和MCP复用读逻辑。
**Blocked by:** 本地接口/预览依赖VX-007公开读库子切片；真实内容验收依赖VX-004。公网发布由VX-008负责，不反向阻塞本地实现。
**Status:** queued — ready after VX-007 local slice。

[KNOWN] 2026-09-10拆票：[VX-009A](VX-009A-reader-slice.md)可立即用已接受两源release完成站点读取；[VX-009B](VX-009B-legacy-search-mcp.md)依赖009A与012B，用真实导入旧内容完成统一搜索/HTTP/MCP和浏览器验收。界面联调不等待导入，最终验收不以两篇新样本代替历史内容。

## 验收

- [ ] 审阅ZIP真实源码与依赖，复用其UI；与vitaclaw-site分开。
- [ ] 实际article/wiki详情、引用跳转和related响应都绑定同一release。
- [ ] 可从文章/Wiki或名称/别名定位相关实体，不要求读者或Agent猜entity_id；只在此实际交互需要时扩充首片DTO。
- [ ] 中英专名、短词、缩写和版本号可检索；明确FTS分词限制并修实际缺口。
- [ ] HTTP/MCP使用同一query函数和权限，缺失真实404，不以mock返回成功。
- [ ] 私有数据、管理写接口不出现在公开进程可读范围；路径/URL和渲染输入受验证。
- [ ] 真实浏览器验证搜索→详情→证据，图片caption与资源可读；可索引页面/SEO检查。

**验证：** 真实临时读库、HTTP/MCP契约、私有哨兵负向测试和浏览器端到端；fixture联调不算真实内容验收。

**执行边界：** 只写主控派工的互斥路径；保护原始数据与无关 WIP，不自动 commit/push。远端写入须绑定具体候选/生产任务、当前主机与源码验证，ADR 0002 四类例外始终有效。
