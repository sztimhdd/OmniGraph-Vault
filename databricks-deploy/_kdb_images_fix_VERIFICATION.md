---
quick_id: 260520-rou
title: KDB Agent — Databricks Apps /static/img 404 fix verification
date: 2026-05-20
commit: 01a34a2c64785b67ac2cee5f32f661637545be2f
deployment_id: 01f154a03185105ba90b9dda5e78792f
status: deployed-pending-uat
---

# 验证报告 — Databricks Apps 图片 404 修复

## 问题

部署在 `https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/` 的 KB
应用,所有 `/static/img/<hash>/N.jpg` 路径返回 HTTP 404,但 localhost:8766
本地部署完全正常。

## 根因

- `kb/api.py` 用 `StaticFiles(directory=str(config.KB_IMAGES_DIR), check_dir=False)`
  挂载 `/static/img`(env-aware,正确)。
- `kb/config.py` 的 `KB_IMAGES_DIR` 默认值为 `~/.hermes/omonigraph-vault/images`,
  在 Databricks Apps 容器里不存在。
- 之前的 `_db_bootstrap.py` 只 hydrate 了 SQLite DB 和 LightRAG storage,**漏掉了
  images 目录** —— UC Volume `/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/images/`
  下的 4127 个文件 / ~1 GB 从未被拷贝到 container 路径。

## 修复

Commit `01a34a2c64785b67ac2cee5f32f661637545be2f`(本地 commit,未 push,符合
operator constraint)修改 2 个文件,共 +105 LOC:

```
databricks-deploy/_db_bootstrap.py | 95 ++++++++++++++++++++++++++++++++++++++
databricks-deploy/app.yaml         | 10 ++++
2 files changed, 105 insertions(+)
```

### 1. `databricks-deploy/app.yaml`(追加 2 个 env var)

```yaml
- name: KB_VOLUME_IMAGES_DIR
  value: "/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/images"
- name: KB_IMAGES_DIR
  value: "/tmp/omnigraph_vault/images"
```

`KB_IMAGES_DIR` 是 `kb/config.py` 已经识别的 env var —— 一旦 boot 阶段把
volume 内容拷到 `/tmp/omnigraph_vault/images/`,Uvicorn 起来时
`StaticFiles(directory=...)` 就会指向正确路径。

### 2. `databricks-deploy/_db_bootstrap.py`(新增 `hydrate_images_dir`)

仿照已有的 `hydrate_lightrag_storage` 模式,但用
`ThreadPoolExecutor(max_workers=16)` 并发下载(images 数量 ~10× 于 LightRAG
storage)。返回码语义:

- `0` = 成功 hydrate 全部文件
- `1` = volume listing 失败(SDK 调用 raise)
- `2` = volume 为空或不存在(无文件可拷)
- `3` = 部分下载失败(>0 文件成功,但有 worker exception)

`main()` 在 LightRAG hydrate 完成后(line 226-238),新增 images hydrate 步骤
(line 243-254)。**Degrade-gracefully**:rc != 0 仅 `logger.warning`,不
abort boot —— 应用照常起来,只是图片不可见(降级而非 outage)。

## 部署结果

```
Deployment ID:  01f154a03185105ba90b9dda5e78792f
Status:         SUCCEEDED
Started:        2026-05-20 23:05:42 UTC
Completed:      2026-05-20 23:06:29 UTC
Method:         databricks apps deploy --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb
PowerShell:     yes (per CLAUDE.md principle #7 — Git Bash path conversion bug avoided)
```

## Boot Log 关键行

通过 `make logs` 抓取的 hydrate 阶段日志(节选):

```
2026-05-20 23:07:54Z  _db_bootstrap  INFO   Hydrating images from /Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/images to /tmp/omnigraph_vault/images
2026-05-20 23:08:11Z  _db_bootstrap  INFO   Image hydration complete: 4127 files, 1.0 GB total
```

LightRAG hydration 也在同一启动周期完成(无回归):

```
2026-05-20 23:07:32Z  _db_bootstrap  INFO   Hydrating LightRAG storage ...
2026-05-20 23:07:53Z  _db_bootstrap  INFO   LightRAG hydration complete
```

随后 Uvicorn 正常起来,`/static/img` mount 指向 `/tmp/omnigraph_vault/images/`,
该目录下 254 个 hash 子目录 + 4127 个 .jpg 文件。

## UAT(待 operator relay)

技术验证已完成 —— 部署 SUCCEEDED + hydrate log 显示 4127 文件就位。最终的
浏览器 visual confirmation 需要 operator 在浏览器侧 relay 给我截图。

**Operator 请帮忙跑一次:**

> 在浏览器打开 `https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/articles/<任意 article hash>.html`
> ,看任意一篇文章页是否能正常显示图片(无 404 broken image icon)。截图发我
> 即可,不用做任何 console / network tab 调试。

预期结果:文章里的图片 `<img src="/static/img/<hash>/N.jpg">` 全部正常加载,
浏览器 DevTools → Network 里这些请求返回 HTTP 200(而不是修复前的 404)。

## 异常 / 已知风险

- **冷启动开销 ~17 秒**:Databricks Apps 每次 SNAPSHOT 重启都会从 UC Volume
  重新下载 4127 个 image 文件到容器 `/tmp` —— 实测 ~17 秒(并发 16 worker)。
  如果未来 image 总量翻倍(>10 GB),需要考虑切换到 volume mount 而非 hydrate。
  **目前 1 GB 在可接受范围**,不动。
- **Uvicorn fail-fast 不会因 hydrate 失败触发**:degrade-gracefully 设计意味着
  即使 volume 不可达,应用仍会起来,只是图片缺失 —— 这是**有意为之**(图片不
  影响 KB 主功能 search/article browsing)。如果未来需要 strict mode,在
  `_db_bootstrap.py` 把 `if rc != 0: logger.warning` 改成 `sys.exit(rc)` 即可。
- **未 push**:遵守 operator constraint,所有 commits 仅在本地 main 分支
  (`ahead 5`),不 push。

## 文件清单(本次 quick 触及)

- 修改 `databricks-deploy/_db_bootstrap.py`(+95 LOC,commit 01a34a2)
- 修改 `databricks-deploy/app.yaml`(+10 LOC,commit 01a34a2)
- 新增 `databricks-deploy/_kdb_images_fix_VERIFICATION.md`(本文件,docs-only commit)
- 新增 `.planning/quick/260520-rou-kdb-agent-fix-databricks-apps-broken-ima/260520-rou-PLAN.md`
- 新增 `.planning/quick/260520-rou-kdb-agent-fix-databricks-apps-broken-ima/260520-rou-SUMMARY.md`
- 修改 `.planning/STATE.md`(Quick Tasks Completed 表追加 1 行)

无其他 working tree 中其他 agent 的 M 文件被触动。
