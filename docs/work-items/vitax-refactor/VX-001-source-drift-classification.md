# VX-001 — 三环境源码漂移分类

**What to build:** 逐文件给出保留、回收、替换或 UNKNOWN，避免覆盖有效生产补丁。

**Blocked by:** None — can start immediately.  
**Responsibility:** explorer. **Status:** partial evidence.

**Allowed scope:** 只读源码和 docs/deployments/2026-09-09/；仅本工单及 evidence/VX-001/.  
**Forbidden scope:** 约 930 删除 WIP、运行数据、密钥、客户原始内容、生产切换、服务重启、commit/push；除非主控逐项批准。

## 验收

- [ ] 分类候选已存在；继续逐文件给出保留、回收、替换或 UNKNOWN，避免覆盖有效生产补丁。
- [ ] 记录来源、SHA/比较依据、处置和未决所有者。
- [ ] 单列 lib/vision_cascade.py DeepSeek Vision 漂移；无源码或远端写入。

## 执行附件

```bash
mkdir -p docs/work-items/vitax-refactor/evidence/VX-001
jq -r '.[]? | select(type == "object") | [.path // .file // "", .status // ""] | @tsv' docs/deployments/2026-09-09/code-comparison.json | LC_ALL=C sort -u
git status --short
```

**Tests:** test -s docs/work-items/vitax-refactor/evidence/VX-001/drift-classification.tsv && git diff --check -- docs/work-items/vitax-refactor/  
**Evidence:** 现有分类候选、输入 JSON SHA-256、有界 status；尚非全差异结案。
