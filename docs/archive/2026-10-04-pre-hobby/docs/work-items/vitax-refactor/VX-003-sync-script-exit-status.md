# VX-003 — 同步脚本失败退出码

**What to build:** rsync 原始错误码记录日志；整体重试耗尽退出 1，全部成功退出 0。

**Blocked by:** None — can start immediately.  
**Responsibility:** coder. **Status:** delivered; local/remote offline accepted.

**Allowed scope:** scripts/sync-from-aliyun.sh、对应离线测试、evidence/VX-003/.  
**Forbidden scope:** 约 930 删除 WIP、运行数据、密钥、客户原始内容、生产切换、服务重启、commit/push；除非主控逐项批准。

## 验收

- [x] rsync 原始错误码记录日志；整体重试耗尽退出 1，全部成功退出 0。
- [KNOWN] 2026-09-09 计划复审纠正文档：不承诺整体进程透传 rsync 原始数值；已有本地 stub 使用 exit 23 并断言整体非零。未改变已部署代码。
- [x] 本地 4 个测试已由主控和 reviewer accepted；Hermes 精确单文件原子替换已完成。
- [x] 原 hash 一致、备份和 installed SHA 已由部署证据记录；远端 fake rsync failure=1、success=0。
- [ ] 真实定时同步不在本工单验收内，仍为未验收。

## 执行附件

```bash
git diff --check -- scripts/sync-from-aliyun.sh tests
bash -n scripts/sync-from-aliyun.sh
```

**Tests:** 已接受的本地 4 tests、远端 bash -n 和 fake rsync failure=1/success=0；不运行真实同步。  
**Evidence:** [部署证据](../../deployments/2026-09-09-sync-exit-fix/DEPLOYMENT_EVIDENCE.md)、主控/reviewer 结论、前后 SHA-256 和原子替换记录。
