---
quick_id: 260520-rou
date: 2026-05-20
status: complete
commit: 01a34a2c64785b67ac2cee5f32f661637545be2f
deployment_id: 01f154a03185105ba90b9dda5e78792f
---

# Quick Task 260520-rou — Summary

## 结果

✅ **DEPLOYED, hydration log 显示 4127 文件 / 1.0 GB hydrate 成功**。最终的
浏览器侧 visual UAT 由 operator 截图 relay。

## 修复内容

Commit `01a34a2`(本地,**未 push**,符合 operator constraint):

| 文件 | 改动 |
| --- | --- |
| `databricks-deploy/app.yaml` | +10 LOC — 追加 2 个 env var:`KB_VOLUME_IMAGES_DIR`(UC volume 源路径)+ `KB_IMAGES_DIR`(container `/tmp` 目标路径) |
| `databricks-deploy/_db_bootstrap.py` | +95 LOC — 新增 `hydrate_images_dir(src_dir, dst_dir)` 函数(`ThreadPoolExecutor(max_workers=16)` 并发拷贝),`main()` 在 LightRAG hydrate 后追加 images hydrate 步骤,degrade-gracefully(rc!=0 仅 logger.warning,不 abort boot) |

完整 diff:`git show 01a34a2`。

## 部署

```
Method:        databricks apps deploy --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb
Tool:          PowerShell(per CLAUDE.md principle #7,Git Bash 路径 bug 已避开)
Deploy ID:     01f154a03185105ba90b9dda5e78792f
Status:        SUCCEEDED
Started:       2026-05-20 23:05:42 UTC
Completed:     2026-05-20 23:06:29 UTC
```

## Boot Log 关键证据

```
2026-05-20 23:07:54Z  _db_bootstrap  INFO   Hydrating images from /Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/images to /tmp/omnigraph_vault/images
2026-05-20 23:08:11Z  _db_bootstrap  INFO   Image hydration complete: 4127 files, 1.0 GB total
```

LightRAG hydration 在同一 boot 周期独立完成(无回归)。Uvicorn 启动后
`StaticFiles(directory='/tmp/omnigraph_vault/images', check_dir=False)` 指向
4127 实际文件。

## 决策点

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 修复点 | `_db_bootstrap.py` hydrate(不动 `kb/api.py`) | `kb/api.py` 已用 env-aware 路径,本身正确 —— 容器里 path 不存在才是 root cause。改 bootstrap 是最小改动。 |
| 并发 | `ThreadPoolExecutor(max_workers=16)` | 比 LightRAG storage 多 ~10× 文件量(4127 vs ~400),需要并发否则冷启动 >2min。实测 16 worker = ~17 秒。 |
| 失败模式 | Degrade gracefully(rc!=0 仅 warning) | 图片缺失不影响 KB 主功能(search / article browsing)。Strict mode 留作未来。 |
| 容器路径 | `/tmp/omnigraph_vault/images`(非持久化) | Databricks Apps 容器 `/tmp` 是 ephemeral —— 但每次 SNAPSHOT 部署都跑 hydrate,没有持久化需求。 |
| 命名 | 保留 `omonigraph`(typo) | Canonical,见 `feedback` memory 和 CLAUDE.md project summary。 |

## Constraints 合规清单

- ✅ 未 `git push`(commit 01a34a2 留在本地 main,ahead 5 of origin)
- ✅ 未 `pull / rebase / merge / stash / checkout` 已修改文件
- ✅ 未触动其他 agent 的 in-progress M 文件(`kb/api_routers/*`、`kb/export_knowledge_base.py`、`kb/locale/*`、`kb/templates/base.html`、`kb/services/search_index.py` 等全部保持原样)
- ✅ `app.yaml` 是 read + diff 后**追加**(未 reorder / clobber 现有 env)
- ✅ Databricks CLI 全部走 PowerShell(避免 Git Bash 路径转换 bug)
- ✅ 未写任何 secret 进 commit(SSH host/port/user / Databricks PAT 无)
- ✅ 用 `logger`,不用 `print()`

## Pending

- 🟡 Operator 浏览器 visual UAT(截图 relay):`https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/articles/<任意 hash>.html` 是否正常显示图片
- 🟡 推送时机由 operator 决定(本任务结束时仍未 push)

## 文件

- `databricks-deploy/_kdb_images_fix_VERIFICATION.md`(verification report)
- `.planning/quick/260520-rou-kdb-agent-fix-databricks-apps-broken-ima/260520-rou-PLAN.md`
- `.planning/quick/260520-rou-kdb-agent-fix-databricks-apps-broken-ima/260520-rou-SUMMARY.md`(本文件)
- `.planning/STATE.md`(Quick Tasks Completed 表追加 1 行)
