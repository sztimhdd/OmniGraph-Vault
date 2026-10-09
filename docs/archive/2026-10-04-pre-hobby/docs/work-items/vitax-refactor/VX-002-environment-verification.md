# VX-002 — 三环境环境核实

**What to build:** 带时间戳记录主机、服务、数据责任和调度事实。

**Blocked by:** None — can start immediately.  
**Responsibility:** uat. **Status:** accepted (preflight).

**Allowed scope:** 只读最小化 SSH；仅本工单及 evidence/VX-002/.  
**Forbidden scope:** 约 930 删除 WIP、运行数据、密钥、客户原始内容、生产切换、服务重启、commit/push；除非主控逐项批准。

## 验收

- [x] 带时间戳记录主机、服务、数据责任和调度事实。
- [ ] 核实持续同步分量；无证据写 UNKNOWN。
- [ ] Hermes 仅文本 PASS、Codex 仅 login，均不可作为工具/自治验收。

## 执行附件

```bash
for target in OHPC ack-node-2 ack-node-1; do ssh "$target" 'hostname; date -u +%FT%TZ; systemctl list-timers --all --no-pager | rg "omnigraph|omni|kb" || true'; done
```

**Tests:** rg -n 'UNKNOWN|PASS|login|hostname' docs/work-items/vitax-refactor/evidence/VX-002/*.md && git diff --check -- docs/work-items/vitax-refactor/  
**Evidence:** 最小化 SSH 输出、UTC 时间、主机名对照；资源与部署适配仍待实测。
