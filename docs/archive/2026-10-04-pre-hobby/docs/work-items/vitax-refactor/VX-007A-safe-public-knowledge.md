# VX-007A — 安全公开知识切片

**Parent:** VX-007  
**Blocked by:** None  
**Status:** local-accepted（2026-10-01；当前零图片切片）

## 独立交付

迁移资产即使拥有 public 标记，也只有显式 accepted 的知识/Wiki及其必要证据摘录能进入公开 SQLite；完整原文和完整译文始终留在私有候选。

## 验收

- [ ] 先用合成 sentinel 证明当前全文译文公开行为会失败，再实施修正。
- [ ] `DocumentRevision` 的 publication/quality/translation 状态不能独立生成公开知识正文。
- [ ] 公开 knowledge/Wiki 必须有 accepted 来源；证据只能来自它们实际引用的摘录，不得按全文逐段生成。
- [ ] 私有原文、完整译文、待核关系、运行字段和未知字段不进入公开 SQLite 字节。
- [ ] fresh process 可读取已接受两来源 release；文章、Wiki、关系、证据和 `release_id` 不回归。
- [ ] 迁移、质量与公开资格继续独立记录；20 篇既有私有导入不被删除或改写。
- [ ] 全程零 LLM、零网络、零远端写入。

## 测试

公开投影构建、失败不覆盖、fresh reader、私有 sentinel 扫描、两来源 release 回归。测试 fixture 不含真实私有正文。

## 非目标

不决定 20 篇旧文的公开资格，不做全量迁移、UI、云发布、向量或图引擎替换。

## 2026-10-01验收记录

[2026-10-01本地验收](/Users/hai/Projects/ohpc-migration/vitax-candidate-runs/reader-release-20261001/REPORT.md)。复用既有WIP与当前针对性检查；当前零图片release，错误503/缺图为受控浏览器路径。下方/上方检查表保留为原计划，实际执行证据以本次报告为准，未扩为云端/全量迁移验收。
