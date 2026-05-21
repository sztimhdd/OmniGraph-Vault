---
quick_id: 260521-iss2
title: KDB Agent — Issue #2 homepage/articles/topic/entity card titles + snippets bilingual fix verification
date: 2026-05-21
commits:
  - e11b474  # Step-2 deliverables absorbed into concurrent gate-closure commit (attribution drift; see STATE row + below)
deployments:
  - 01f155284b111278b8c03b745eb44758  # 2026-05-21 15:20:55Z, state SUCCEEDED
status: deployed-and-workspace-export-verified
---

# 验证报告 — Issue #2 首页/articles/topic/entity 卡片标题 + snippet 双语化

## 问题

部署在 `https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/`
(KB_DEFAULT_LANG=en) 的 KB 应用,首页文章卡片的标题和 snippet 仍然渲染中文 ——
即便 Hermes 已经在 Phase 5 把 234/238 篇文章的 `title_translated` /
`body_translated` 译完。

UAT 截图来自 user 2026-05-21 早上反馈:"首页文章卡片标题和正文 230 多篇翻译完成
但还是中文"。

## 根因

`kb/templates/{index,articles_index,topic,entity}.html` 4 个模板的文章卡片节
点(`<a class="article-card">`)只输出单一字段 `{{ article.title }}` /
`{{ article.snippet }}`,没有按 kb-v2.2-7 (bilingual-by-site-language) 已确立
的 dual-`<span data-lang>` 静态-双语模式打包 zh + en 两套内容。结果:`lang.js`
runtime 切语言时,卡片节点没有 en sibling 可显示,只能继续显示 zh。

下游的 `kb/export_knowledge_base.py:_record_to_dict` 也只导出 `snippet`
(裸-zh),没有同时导出 `snippet_translated`(从 `body_translated` 经
`rewrite_translated_body` + `_make_snippet` 派生)。

## 修复

### Step 2 deliverables(均落在 concurrent commit `e11b474`)

#### 1. `kb/export_knowledge_base.py:_record_to_dict`(4 行新增)

```python
if body_md is not None:
    out["snippet"] = _make_snippet(body_md)
    out["reading_time"] = _estimate_reading_time(body_md)
    translated_body_md = rewrite_translated_body(rec.body_translated)
    out["snippet_translated"] = (
        _make_snippet(translated_body_md) if translated_body_md else None
    )
```

`rewrite_translated_body` 已是 kb-v2.2-7 现成 helper,空 `body_translated` 安全
返回 `None`,下游模板用 `{{ x_translated or x }}` 兜底。

#### 2. 4 个模板的文章卡片节点

文件: `kb/templates/{index,articles_index,topic,entity}.html`

模式(以 index.html 为例):

```html
<h3 class="article-card-title">
  <span data-lang="zh">{{ article.title }}</span><span data-lang="en">{{ article.title_translated or article.title }}</span>
</h3>
{% if article.snippet %}
<p class="article-card-snippet">
  <span data-lang="zh">{{ article.snippet }}</span><span data-lang="en">{{ article.snippet_translated or article.snippet }}</span>
</p>
{% endif %}
```

`entity.html` 用 `a.` 上下文前缀(因为它的 article cards 来自一个不同的循环
变量),其余 3 个用 `article.`。

`{{ x_translated or x }}` Jinja fallback 是关键设计:即便 production DB 暂时
没有 `body_translated` / `title_translated`(译列 NULL),en span 还是会渲染成
zh 内容,**不会**留空白卡片。

#### 3. Topic cards 不动

`<a class="topic-card">`(用 `t.localized_title` / `t.localized_desc`)是
**单语动态-本地化**节点,不是 article card,有意保留 single-`<span>` 行为。
集成测试 regex 必须 scope 到 `data-source=` 属性以排除 topic cards。

### 集成测试

`tests/integration/kb/test_kb_v2_2_7_bilingual_ssg.py` 加 / 收紧:

```python
article_card_pattern = re.compile(
    r'<a class="article-card"\s+href[^>]*data-source[^>]*>(.*?)</a>',
    re.DOTALL,
)
cards = article_card_pattern.findall(home_html)
```

scope 到 `data-source` 属性(只有 article cards 有,topic cards 用
`data-topic-slug`)。新增 `test_homepage_card_snippets_dual_span` 用真实生成的
SSG 输出验证 zh + en spans 双源都 ≥1 命中。

`pytest tests/integration/kb/test_kb_v2_2_7_bilingual_ssg.py -v` → **16/16
PASS**。

## 部署 + 验证 链

### 1. 本地 SSG 重生成 + 文件 prep

`make` 不在 PATH(Windows dev box 没装 GNU make);Makefile recipe 内联走 bash
(file-prep)+ PowerShell(databricks CLI)拆分:

- **Pass 0** (bash): `rm -rf databricks-deploy/_ssg && cp -R kb/output databricks-deploy/_ssg && rm -f databricks-deploy/_ssg/.gitignore`
- **Pass 0b** (bash): `find databricks-deploy/_ssg -name '*.html' -print0 | xargs -0 sed -i 's|<html lang="zh-CN">|<html lang="en">|g; s|window\.KB_DEFAULT_LANG = "zh-CN"|window.KB_DEFAULT_LANG = "en"|g'`
- **Pass 0c** (bash): cp `kg_synthesize.py` + `config.py` + `lib/` 进 databricks-deploy/(synthesize stage 依赖)
- **Pass 0d** (bash): cp `kb/kb-logo.png` 覆盖 `_ssg/static/VitaClaw-Logo-v0.png` + sed `VitaClaw` / `企小勤` → `EDC Agentic AI Knowledge Base`(占位符 shield 保护 logo 路径) + sed `lang.js` `detectFromBrowser` 内的 zh / en return 改回 `DEFAULT_LANG`

后台 task `btc4fd1wj` exit 0,无报错。

### 2. Pass 1+2 sync(PowerShell)

```powershell
databricks --profile dev sync --full --include "_ssg/**" `
  ./databricks-deploy /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy
databricks --profile dev sync --full `
  ./kb /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy/kb
```

后台 task `bsgii8guj`(Pass 1)+ `b2d4s1iob`(Pass 2)均 "Initial Sync
Complete" exit 0。

### 3. apps deploy(PowerShell)

```powershell
databricks --profile dev apps deploy omnigraph-kb `
  --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy
```

后台 task `bbfltb47q`:`deployment_id 01f155284b111278b8c03b745eb44758`
state=SUCCEEDED 15:20:55Z。

### 4. Workspace artifact verification

App URL `https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/`
返回 HTTP 302 → SSO redirect(预期 — Databricks Apps 公网 SSO,headless curl
无法直接访问)。改用 `databricks workspace export` 拉 immutable SNAPSHOT 路径
下的产物 `_ssg/index.html`:

```
/Workspace/Users/459ebc59-0512-4da7-b962-f639312b8df6/src/01f155284b111278b8c03b745eb44758/_ssg/index.html
```

grep 计数:

- `<html lang="en">`: **1** ✓
- `data-lang="en"`: **157** ✓(20 cards × ~7-8 spans/card)
- `data-lang="zh"`: **157** ✓
- 抽样 grep `article-card-snippet -A3` 看到 `<p class="article-card-snippet"><span data-lang="zh">...</span><span data-lang="en">...</span></p>` 双 span 结构完整

## 行为约束(important caveat)

**production DB 的 `title_translated` / `body_translated` 列暂时 NULL**(挂在
Databricks Apps 上的 DB 是 UC Volume 拷贝,不是 Hermes Phase-5 已 backfill 的
DB)。当前 deploy 的 en spans 通过 `{{ x_translated or x }}` Jinja fallback
**渲染 zh 内容**,即使 lang toggle 切到 en,看到的还是 zh 文字。

这是**预期行为**:模板和 SSG 已经是双语就绪态,数据缺译时 en 兜底回 zh,卡片
不空白。Step 4(UC Volume DB schema migration + 233-article translation
backfill)是真正让 en 卡片显示英文的**内容**unblocker —— 但这不是 Step 2 的
scope。Step 2 修的是**渲染契约**(模板 + 导出 + 测试)。

User 反馈"230 多篇翻译完成但还是中文"的根因是:UAT 看到的 en 卡片显示 zh,
误读为"翻译没生效"。实际是 production DB 与 Hermes Phase-5 backfilled 的 DB 不
同源。

## Commit attribution drift(3rd 占)

Step 2 的 6 个文件:

- `kb/export_knowledge_base.py`(`snippet_translated` 4 行)
- `kb/templates/index.html`(5 行 dual-span)
- `kb/templates/articles_index.html`(5 行)
- `kb/templates/topic.html`(9 行)
- `kb/templates/entity.html`(9 行,`a.` 前缀)
- `tests/integration/kb/test_kb_v2_2_7_bilingual_ssg.py`(regex 收紧 + 新测试)

通过 explicit-path `git add` staged,但在我执行 `git commit -F` 之前,并发的
gate-closure 代理刚好在它的 `git add` window 把 staged 文件全扫进了它自己的
commit `e11b474`(`docs(state): Gate 1 closed — kb-4-lite + aim-N path
correction (Option A)`)。

`git show e11b474 --stat` 验证内容正确落在 HEAD,只是 commit message 与文件
不匹配。

这是这种 failure mode 的**第 3 次发生**:

1. 2026-05-11 — quick `lmc` / `lmx` 互相吞 staged
2. 2026-05-18 — kb-v2.2-1 PLAN.md addendum 被 quick `260517-rgd-3` 吞
3. 2026-05-21 — Step 2 deliverables 被 `e11b474` 吞(本次)

按现有 memory:

- `feedback_git_add_explicit_in_parallel_quicks.md`:用 explicit-path
  `git add`,**不要** `-A`。但即便 explicit-path,只要 staged window 没在
  同一个 atomic chain 里,并发 `git add` 仍能扫进自己的 commit。
- `feedback_no_amend_in_concurrent_quicks.md`:**绝对不要** `git commit
  --amend` / `git reset` 来"修"已 push 的 attribution drift。fix 是
  forward-only 文档(本 VERIFICATION.md + STATE-KB-v2.md row),不是 rewrite
  history。

## Status

- Tests: 16/16 PASS(`tests/integration/kb/test_kb_v2_2_7_bilingual_ssg.py`)
- Deploy: deployment_id `01f155284b111278b8c03b745eb44758` state=SUCCEEDED
- Workspace artifact: 157 en spans + 157 zh spans + 1 `<html lang="en">`
  在 immutable SNAPSHOT 路径
- Behavior: 渲染契约就绪,en 卡片暂用 zh 兜底直到 Step 4 backfill 落 production DB

**Issue #2 渲染契约层已 deployed。内容层(实际显示英文)阻塞在 Step 4
production DB translation backfill。**
