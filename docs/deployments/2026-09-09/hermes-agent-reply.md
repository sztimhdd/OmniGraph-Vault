# Hermes Agent 背景回复

Session: `20260804_142454_aacd1b`。来源：Hermes CLI 单次文字询问；属于 Agent 历史陈述，实时事实仍以 SSH 证据为准。CLI 正常退出 0。

STATUS

1. `deploy/sync_kq_to_new.py` 的已知职责只有：
   - 旧机 Qdrant → 新机：同步缺失点；
   - 旧机 SQLite → 新机：`.backup`、SCP、原子替换。  
   未见 graphml、`kv_store_*`、images 的持续同步实现。对应路径均为 `~/.hermes/omonigraph-vault/`。新机相关 `.bak` 最后约停在 2026-07-28；是否经批准主动接受，UNKNOWN。

2. 明确有意的生产漂移只有旧机 `lib/vision_cascade.py`：2026-08-23 切换为 DeepSeek Vision，禁止回滚。T2/T4/T5/T6/T8 等部分文件曾按批准方案逐文件部署。旧机约 23 个文件的整体 fork 漂移并未被整体批准回收；没有完整、获批准的当前文件清单。

3. WSL 的 `scripts/wiki_evolve.py`、`tests/unit/test_wiki_w5b_bootstrap.py` 是保留的他人未提交 W5B 工作区改动；具体负责人和剩余任务 UNKNOWN。`omnigraph-w5b-t2..t8` 是 W5B 分工 worktree；已知 T2/T4/T5/T6/T8 形成提交，T7/T9 完成部署，但每个 worktree 的残留内容、归属和是否仍活跃 UNKNOWN。

4. 关键依赖还包括：
   - 旧机采集依赖 WSL 的 CDP/Playwright MCP 反向隧道；
   - 两机依赖 BGE-M3 embed-server `:7997`；
   - 新机 MCP/KB 查询依赖旧机同步；
   - DeepSeek、dajiala、微信 Cookie/CDP 均是外部依赖；
   - 新机为查询节点，无采集 timer；旧机承担采集、ingest、同步和健康检查。
   - 旧机 `qdrant-snapshot` 曾因 IO 风险失败/停用；已知备份包括旧机部署备份及 2026-06-10 异地备份，但近期 graphml、kv_store、images 的完整自动备份覆盖 UNKNOWN。

CHANGES

none。未调用工具，未修改任何外部状态。

EVIDENCE

- `docs/HERMES-OMNIGRAPH-OPERATIONS-HANDOFF-20260822.md`
- `docs/DSH-MASTER-HANDOFF-20260822.md`
- `docs/OPERATIONS.md`
- `BGE_M3_MIGRATION.md`
- `INVENTORY.md`
- 2026-09-03 T2/T4/T5/T6/T8/T9 历史部署记录
- 2026-09-09 三环境审计摘要

RISKS

- 新机数据可能长期停留在 7 月快照；
- 旧机 drift fork 与 main 无法安全自动合并；
- W5B worktree 可能存在未提交、未归属代码；
- graphml/kv_store/images 没有已证实的跨机同步或近期完整备份。

NEXT

Codex 应先只读确认：同步脚本完整内容、两机 timer/service、所有 W5B worktree 的 `git status`/分支/最后提交、旧机生产文件 SHA 清单，以及最新备份覆盖范围；在建立 manifest 前不要回收 drift、删除 worktree 或补同步。
