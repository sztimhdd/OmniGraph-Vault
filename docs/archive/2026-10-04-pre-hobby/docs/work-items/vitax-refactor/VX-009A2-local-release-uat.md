# VX-009A2 — 本地 release 集成与浏览器验收

**Parent:** VX-009A  
**Blocked by:** VX-007A、VX-009A1  
**Status:** local-accepted（2026-10-01；当前零图片切片）

## 独立交付

一个可重复构建并在本机启动的最小 release 目录，包含公开 SQLite、站点、白名单图片和 manifest；浏览器真实路径与隐私负向验收通过。

## 验收

- [ ] 构建输出只有本 release 使用的公开文件，并记录文件 hash、时间和 `release_id`。
- [ ] 页面、HTTP、SQLite 与 manifest 使用同一 `release_id`；失败构建不覆盖已有包。
- [ ] 浏览器完成列表→文章→证据、Wiki→两来源、关键词搜索和刷新直达。
- [ ] 真实 404、空态、错误态、图片失败、移动端和键盘路径通过。
- [ ] 私有 sentinel、完整原文/译文不能从 SQLite、HTTP、HTML、JS 数据或静态资源取得。
- [ ] 验收目录结构可直接作为后续云端复制输入，但没有远端写入或生产声明。
- [ ] 独立审阅无 P1/P2；本 Sprint 引入的失败已修复。

## 测试

确定性集成测试、构建产物扫描、HTTP 黑盒测试、浏览器 DOM/网络/可访问性证据。历史通过结果不替代本次证据。

## 非目标

不实现云端 symlink 切换、回滚、定时日更、BYOLLM、全量迁移或生产切换。

## 2026-10-01验收记录

[2026-10-01本地验收](/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/reader-release-20261001/REPORT.md)。复用既有WIP与当前针对性检查；当前零图片release，错误503/缺图为受控浏览器路径。下方/上方检查表保留为原计划，实际执行证据以本次报告为准，未扩为云端/全量迁移验收。
