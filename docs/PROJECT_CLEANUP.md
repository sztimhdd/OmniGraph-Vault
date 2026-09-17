# VitaX 整理与恢复记录

日期：2026-09-09。范围：本地源码工作区整理。

## 基线与结果

- GitHub 插件核对 main，并通过完整 Git clone 验证：`dca7c772a8c95125d275ec50b2944ff00713667a`，提交日期 2026-09-03。
- 原 `OmniGraph-Vault-code` HEAD 为 `b786d19`，`git merge-base --is-ancestor b786d19 HEAD` 返回 0。原已跟踪源码没有未提交修改，因此没有旧代码需要反向覆盖主线。
- `omnigraph` 只有说明与 code/vault 符号链接；`omonigraph-vault` 指向外部 `~/.hermes/omonigraph-vault`。未遍历、复制或修改该外部运行数据。
- VitaX 现在直接包含完整 Git 仓库、origin、最新源码、测试、技能、迁移与部署源码。
- 930 个上游历史文件移出工作区：旧 `.planning`（保留 ISSUES.md）、`.scratch` 中旧实验、复制文章、选定历史交接／里程碑／验收报告。根 README 和 Claude 入口改为简洁的当前工作说明。
- 保留 `test/fixtures`，因为基准脚本确实依赖它；保留部署目录和 migrations，未凭文件年龄删除运行代码。
- 新增 AGENTS.md、docs/README.md、此记录与执行计划；扩展 .gitignore，避免旧环境、缓存、数据副本重新进入源码。
- 保留文件中的 Markdown 链接经过已归档路径检查：没有匹配到需要重写的链接。历史正文里的裸路径通过以下 Git 历史读取方法恢复。

## 备份

备份目录：`/Users/hai/Projects/ohpc-migration/VitaX-backup-20260909`（目录权限 0700）。

- `original/`：原工作区全部入口，包含旧 Git 仓库、忽略／未跟踪文件、环境和原始符号链接。
- `original-manifest.json`：59,367 个文件／链接的 SHA-256 或链接目标；普通文件合计 2,253,856,258 字节。移动前后重新读取校验一致。
- `upstream-archived/`：本次移出的上游历史内容，以及修改前 README.md、CLAUDE.md。
- `removed-paths.json`：930 个移出工作区的路径清单。
- `source-verification.json`：保留源码的字节与语法校验结果。

这是可恢复清理，备份仍占磁盘空间，并非永久释放相同大小的磁盘容量。
备份内旧相对链接和虚拟环境仅作恢复材料，不是新的运行入口。

## 恢复历史内容

读取任意原主线文件（不会改变工作区）：

```bash
git show dca7c772a8c95125d275ec50b2944ff00713667a:.planning/STATE.md
```

恢复单个历史文件时，从 `upstream-archived/` 复制到对应路径，先检查目标是否存在。
完整回退时先将当前 VitaX 内容保存到另一个目录，再将 `original/` 的四个原始入口移回 VitaX；
不要覆盖新增工作，不要直接使用 `git reset --hard` 或 `git clean`。
原入口保持原来的相对布局后，原符号链接可恢复解析；外部 vault 目标始终未变更。

## 本次验证

- 原目录移动前后：逐文件 SHA-256／symlink 目标一致。
- 保留的非 Markdown 文件（.gitignore 除外）：与上游 HEAD 逐字节一致。
- 447 个保留 Python 文件：AST 语法解析全部通过，无运行时导入。
- `git fsck --no-reflogs`：退出 0。
- `git diff --check`：退出 0。
- `.venv/bin/python -m pytest tests/unit/test_mcp_healthcheck_alert_label.py -q`：**2 passed**。
- 新 `.venv` 使用 Python 3.12，仅安装 pytest、pytest-asyncio 及其传递依赖；完整应用依赖未安装。

## 已知限制

- `tests/integration/kb/test_kb3_e2e.py` 引用 `.planning/phases/kb-3-fastapi-bilingual-api` 中 PLAN/SUMMARY 文件，但该目录在原始上游 HEAD 已不存在（git ls-tree 确认）。这是原有集成测试输入缺失，本次未改写测试或伪造规划文件。
- 旧 Wiki lint 路径仍在代码中用于日志／迁移兼容；上游没有对应未迁移 JSONL，已有 `.jsonl.migrated` 属于历史归档。本次未改代码路径契约。
- 全套单元／集成测试、技能模型评测、服务启动、部署、采集和正式 UAT 均未执行。
- 保留运维文档可能包含历史主机、模型和部署断言；源代码或新证据优先。
- 修改保留为本地未提交 diff；未提交或推送 GitHub，未更改 Codex 全局配置或接入远程运行环境。
