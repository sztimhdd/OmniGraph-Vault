# VX-005 — 启动清理移出关键路径并可重试

**What to build:** 启动关键路径不对 processing 执行 adelete 或启动前重活。

**Blocked by:** None — can start immediately.
**Responsibility:** Pascal. **Status:** partial (local read-only slice accepted; recovery incomplete; not deployed) — 三份 service 的 first slice 已本地实现；整项故障恢复尚未完成。

**Allowed scope:** deploy/aliyun/systemd/omnigraph-daily-ingest.service、deploy/aliyun/systemd/omnigraph-afternoon-ingest.service、deploy/aliyun/systemd/omnigraph-evening-ingest.service、tests/unit/test_ingest_prestart_read_only.py、离线测试和 evidence/VX-005/。
**Forbidden scope:** 约 930 删除 WIP、运行数据、密钥、客户原始内容、生产切换、服务重启、commit/push；除非主控逐项批准。

## 验收

- [x] service 模板 dry-run 证明第一切片的启动前置读路径；未在线修改 systemd。
- [x] 新的 test_ingest_prestart_read_only.py 覆盖只读启动前置行为；与 cleanup 单测的组合离线运行记录为 14 passed。
- [ ] 本切片不改 cleanup_stuck_docs.py 删除行为，不构成完整故障恢复；不得以 TimeoutStartSec 加长作为根治。

## 执行附件

```bash
rg -n 'ExecStartPre|cleanup_stuck_docs|all-failed|processing|TimeoutStartSec' deploy/aliyun/systemd/omnigraph-daily-ingest.service deploy/aliyun/systemd/omnigraph-afternoon-ingest.service deploy/aliyun/systemd/omnigraph-evening-ingest.service
OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -m pytest tests/unit/test_ingest_prestart_read_only.py -q
```

**Tests:** service template dry-run 与 `test_ingest_prestart_read_only.py`、`test_cleanup_stuck_docs.py` 的组合离线测试；不得在线修改 systemd。
**Evidence:** [首波证据](../../deployments/2026-09-09-first-wave/vitax-prestart-test-evidence.md) 记录 ExecStartPre 读路径、离线断言和未改 cleanup 删除行为的 diff；完整残留恢复留待后续工单。

## 第二阶段执行

补充本地清理拒绝切片；不等于共享锁或故障恢复完成，不部署。见[第二阶段报告](../../deployments/2026-09-09-second-wave/SECOND-WAVE.md)。
