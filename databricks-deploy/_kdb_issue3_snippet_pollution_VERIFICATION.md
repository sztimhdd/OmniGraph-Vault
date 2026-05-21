---
quick_id: 260521-iss3
title: KDB Agent — Issue #3 homepage card snippet pollution fix verification
date: 2026-05-21
commits:
  - 0194ccc  # fix(kb-snippet): strip WeChat scraper preamble + reader-bait
deployments:
  - 01f1552275541bc3a1b6381273dfd418  # 2026-05-21 14:36 UTC, status SUCCEEDED
status: deployed-and-curl-verified
---

# 验证报告 — Issue #3 首页文章卡片排版 boilerplate pollution 修复

## 问题

部署在 `https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/` 的 KB
应用,首页文章卡片 snippet 段落里出现 WeChat 刮削 boilerplate:

- `URL: https://mp.weixin.qq.com/s/...` 和 `Time: 2026-05-16 23:13:16` 前缀
- `;) ______` + `在小说阅读器读本章` + `去阅读` + `在小说阅读器中沉浸阅读` reader-bait 段
- `**点击上方"X",关注公众号...**` follow-CTA banner
- 重复作者名(`原创 詹老师 詹老师 詹生Talk` 内 `詹老师` 两次)
- 文章标题被 `<h1>` 重复出现两次

源样本来自 `databricks-deploy/_kdb_uat_failure_INVESTIGATION.md` Issue #3。

## 根因

`kb/export_knowledge_base.py:_make_snippet()` 在 commit `0194ccc` 之前没有任何
strip 阶段,把 WeChat 刮削器(`ingest_wechat.py:1303` 写入)的 raw markdown 前缀
和 reader-bait 直接喂进 SSG 渲染。

## 修复

### Commit `0194ccc`(本地 commit,符合 operator constraint)

`kb/export_knowledge_base.py:_make_snippet` 增加 F3.1-F3.5 五段 strip
pipeline:

- **F3.1**: 去掉 `URL:` / `Time:` preamble 行
- **F3.2**: 去掉 `;) ______` + `在小说阅读器*` + `去阅读` reader-bait 段
  (含无 `;)` 前缀变体,纯 `______` 也命中)
- **F3.3**: 去掉 `**点击上方"X",关注公众号...**` follow-CTA banner
- **F3.4**: 折叠 `原创 X X Y` -> `原创 X Y` 形式的作者重名
- **F3.5**: 去掉与文档第一行 `<h1>` 重复的标题行

### 单元测试 `tests/unit/test_make_snippet_boilerplate.py`

9 个测试覆盖每个 strip 阶段 + 空 body + max_chars cap + idempotence + 真实
prod-pollution 端到端样本。pytest 全绿(9/9)。

## 部署 + 验证 链

### 1. SSG 重新渲染

本地用 `KB_DB_PATH=.dev-runtime/data/kol_scan.db venv/Scripts/python.exe -m
kb.export_knowledge_base` 把 `kb/output/` 重生成。`kb/output/index.html` 0 个
URL: / Time: / 在小说阅读器 / 关注公众号 命中。

### 2. Databricks workspace sync(关键 bug + workaround)

**`databricks sync ./databricks-deploy ...` 默认 honor 项目根目录 .gitignore,
而项目根 .gitignore 包含 `databricks-deploy/_ssg/` 排除规则**。结果 Pass 1
sync 报告 "Initial Sync Complete" 0 错误,但 workspace 里的 `_ssg/` 目录
**完全是空的** —— 整个 200+ 文件的预渲染输出被静默丢弃。

诊断步骤:

1. 第一次 `databricks sync --full ./databricks-deploy ...` exit 0
2. `databricks workspace list .../databricks-deploy/_ssg` -> "Path doesn't exist"
3. `databricks sync --help` 显示 `--include strings` flag 存在
4. `databricks sync --dry-run --include "_ssg/**" ...` 列出 200+ `_ssg/*` 文件
5. `databricks sync --full --include "_ssg/**" ...` 真实 upload 全部 `_ssg/*`

修复:Makefile Pass 1 加 `--include "_ssg/**"` 防止下次 regression(本次同 commit
patch)。

### 3. Apps deploy + curl 验证

- 新 deployment_id: `01f1552275541bc3a1b6381273dfd418`(UTC 2026-05-21 14:36)
- status: SUCCEEDED, app_status: RUNNING
- curl 已部署首页(Bearer PAT auth)抓 69824 字节 HTML
- boilerplate 计数:
  - `URL:` matches = **0**
  - `Time:` matches = **0**
  - `在小说阅读器` matches = **0**
  - `关注公众号` matches = **0**
  - `詹老师 詹老师` matches = **0**

证据文件: `.scratch/uat-investigation/index_AFTER_REDEPLOY.html`(curl 抓取)
和 `.scratch/uat-investigation/index_workspace_post_include.html`(workspace
export,69824 字节同步)。

### 4. 浏览器 UAT(deferred)

Databricks Apps 强制 SSO,headless 浏览器无法绕过(用户 2 小时不在线)。
curl 已用 PAT bearer 抓到完整 HTML,boilerplate 5/5 项 0 命中,Issue #3
判定为 deployed-and-curl-verified。用户回来后可在 Edge 直接访问首页做
visual UAT。

## 文件清单

| 文件 | 改动 |
|------|------|
| `kb/export_knowledge_base.py` | `_make_snippet` 加 F3.1-F3.5 strip pipeline |
| `tests/unit/test_make_snippet_boilerplate.py` | 9 个 unit test 全覆盖 |
| `databricks-deploy/Makefile` | Pass 1 sync 加 `--include "_ssg/**"` |
| `databricks-deploy/_kdb_issue3_snippet_pollution_VERIFICATION.md` | 本文件 |

## 不在本 patch 范围

- Issue #1(图片): 已在 commit `aafdaf4` + `01f15515ff9a1b5ebd305b68ad98f792`
  deployment 修复
- Issue #2(翻译): Step 2 待办 — 4 模板 bilingual-wrap + DB 翻译列回填
- 27 个缺失 mmbiz hash 的 image dir: Step 5 待办 — 重新刮削
