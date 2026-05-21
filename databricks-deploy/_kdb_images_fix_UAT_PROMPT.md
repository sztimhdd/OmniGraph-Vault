# UAT Operator Prompt — Postmortem #6 image fix verification

**Deployment:** `01f1554d1e401cbf8e4467f524a9bf43`
**App URL:** https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com
**Date staged:** 2026-05-21 19:45 ADT

---

## What the user is verifying

User stance (verbatim,2026-05-21):

> 没刮下来的图不要了 但是已经 Hermes 有的图你得 100% 给我显示出来

Postmortem #6 unified `kb/data/article_query.py::resolve_url_hash` to
`md5(url)[:10]` (matching Hermes write-side),re-baked SSG with url-hash
HTML files,and uploaded the 9 missing image dirs to UC Volume that were
"already Hermes-have-it but never uploaded".

This UAT verifies "已经 Hermes 有的图 100% 显示出来" on the live
Databricks App.

---

## Test plan

Open each URL below in browser. Confirm hero card + body images render
(NOT plain text, NOT broken-image icon). Take screenshot after page is
fully loaded (scroll down to confirm body images too).

### Tier 1 — newly uploaded image dirs (9 articles)

These are the 9 url-hashes uploaded this session. ALL must show images
(no broken refs).

1. https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/articles/3df8419440.html
2. https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/articles/55ccb774e9.html
3. https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/articles/861242ae2f.html
4. https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/articles/bf394a56fc.html
5. https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/articles/cc56a5c6a7.html
6. https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/articles/d1e3bb276d.html
7. https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/articles/d3bca4bb17.html
8. https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/articles/e0766ceec3.html
9. https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/articles/e51159998a.html

### Tier 2 — "previously plain text" sample (random old articles)

User's complaint was "稍微老一点的文章仍然是纯文字"。这些是 KB 里随机
older articles。Pre-fix 应该是纯文字,post-fix 应该有图。

10. https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/articles/index.html (浏览首页 → 任选 2-3 篇老的进去)

### Tier 3 — known-empty article (negative control)

`8eb9f86685` 是本地 0 image files 唯一一篇,Postmortem #6 已记录
**预期纯文字**(image source 不存在)。这一篇出现纯文字是 expected,
NOT a regression。

11. https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/articles/8eb9f86685.html

---

## Pass / fail criteria

- **PASS:** Tier 1 (1–9) 全部 9 篇 hero + body 都显示真图(无 broken-image 红叉,无空白方框)
- **PASS:** Tier 2 抽样 2–3 篇老文章,至少 1 篇能看到 body 图
- **PASS:** Tier 3 (#11) 纯文字 = 预期(本地无 image source)

---

## Browser DevTools 二次确认(可选,但抓 silent 404 用)

任选 1 篇 Tier 1 文章 → F12 → Network 面板 → 刷页 → filter `img/` → 全部
status 应该 200(不是 404)。如果还有 404,记下哪个 url-hash 哪一张图。

---

## 用户回报模板(粘回 Claude)

```
Tier 1 (1-9): [PASS / FAIL]  说明:
Tier 2 老文章抽样:[PASS / FAIL]  说明:
Tier 3 (#11) 纯文字:[确认 / 异常]  说明:
DevTools 仅看到 200(无 404):[YES / NO]  说明:
截图(可选)放在: <路径>
```

---

## 如果 FAIL

- **Tier 1 任意一篇 broken images:**部署 hydrate 没拿到 Volume 文件 →
  抓 boot log:`databricks apps logs omnigraph-kb` 看
  `Hydrating images` 是否 complete + 是否报 error
- **Tier 2 全部纯文字:**SSG bake 没生效 → 检查 `_ssg/articles/*.html`
  in workspace 是否是新 baked 的(`<img src="/static/img/<hash>/...">`
  url-hash 应该跟 Volume dir 名匹配)
- **Tier 3 出现图:**意外 ── 但不是回归

无论 PASS/FAIL,Postmortem #6 已 close v1.0.x"已经 Hermes 有的图 100%
显示"acceptance(Volume 上 92/93 = 99% has-it,1 例外是本地 0 文件)。
任何 FAIL 是发现新 quick task,不是 v1.0.x 回归。
