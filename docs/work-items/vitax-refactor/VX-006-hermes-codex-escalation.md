# VX-006 — Hermes 到 Codex 修复升级

**What to build:** 合成故障包可经本机 Codex CLI 获得独立验证。

**Blocked by:** None — can start immediately.
**Responsibility:** coder + uat. **Status:** functional accepted (synthetic handoff only) — 原始失败保留；修正实验仅对合成算术的 Codex/Hermes/tool-handoff 功能通过，不能表述为自动故障修复完成。

**Allowed scope:** 隔离 harness、evidence/VX-006/ 和经批准源码.
**Forbidden scope:** 约 930 删除 WIP、运行数据、密钥、客户原始内容、生产切换、服务重启、commit/push；除非主控逐项批准。

## 验收

- [x] 修正实验的合成算术可经 Codex/Hermes/tool-handoff 获得功能验证；这不是完整故障包修复。
- [ ] 合成故障包可经本机 Codex CLI 获得独立验证。
- [ ] 登录与文本响应不能通过。
- [ ] 四类动作拒绝；额度耗尽不得触发升级绕额度。
- [ ] 以请求关联的账本证据解析 resolved Codex model、physical attempts 与 fallback；当前均为 **UNKNOWN**。

## 执行附件

```bash
ssh OHPC '/home/sztimhdd/.local/bin/codex exec --help | sed -n "1,120p"'
test -d docs/work-items/vitax-refactor/evidence/VX-006
```

**Tests:** 原始失败与修正实验均保留；修正实验只证明合成算术的功能路径，不能代替完整故障修复或保护动作拒绝断言。
**Evidence:** [原始探针报告](../../deployments/2026-09-09-agent-handoff-probe/REPORT.md)、脱敏故障包、关联 ID、独立验证、拒绝记录。resolved Codex model、attempt 与 fallback 未从请求关联账本取得，保持 **UNKNOWN**。
