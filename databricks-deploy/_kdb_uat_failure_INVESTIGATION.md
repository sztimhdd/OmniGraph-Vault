---
investigation_id: kdb-uat-260521
title: KDB UAT Failure Investigation — 3 issues post kdb-images fix #3 deployment
date: 2026-05-21
deployment_under_test: 01f15515ff9a1b5ebd305b68ad98f792
app_url: https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com/
status: investigation-complete-pending-fix
related_commits:
  - aafdaf4   # kdb-images fix #3 — wipe /tmp before hydrate (Issue #1 partial fix only)
  - bec8811   # kb-v2.2-7-phase5-backfill — Tavily-driven translation, NEVER deployed to UC Volume
related_docs:
  - databricks-deploy/_kdb_images_fix_VERIFICATION.md
---

# UAT Failure 调查 — 三个并发问题

## 用户截图反馈(原话)

> 1. 截图2和3:App部署成功 但根本没有解决我们的图片问题,所有文章仍然缺图,
>    而且存在大量微信的外链图片无法显示,而这些图片我们肯定在刮削时本地存了一份。
>    唯一正常显示的文章图片是RSS文章外链的web图片
> 2. 截图1:我们已经完成了230多篇文章的翻译工作,为什么首页看到的文章标题
>    还是中文的,点进去也是中文正文,是否没有上线最新的代码和文章数据?
> 3. 截图1:如截图所示,首页的文章卡片排版有明显的bug

## TL;DR

| Issue | 表面现象 | 真根因 | 修复 scope |
|---|---|---|---|
| #1 images | 微信外链图全部 404 | 双因素:scrape data gap (27/30 hash 在 volume 里根本不存在) + SSG body 重写漏 mmbiz URL | (a) 重跑 image 抓取 27 hash;(b) 给 `_rewrite_image_paths` 加 mmbiz→local hash 映射 |
| #2 translations | 首页全中文 | 三因素:本地 DB 只有 1 篇翻译(不是 230+);部署的 UC Volume DB **完全没有 translated_* 列**;index.html/articles_index.html snippet 没 dual-span 包裹 | (a) 把 `bec8811` 的 schema migration + 翻译数据真正部署到 UC Volume;(b) 给 4 个 template 加 dual-span;(c) 实际跑完 230+ 翻译 |
| #3 card layout | 卡片显示乱七八糟 metadata | `_make_snippet()` 不剥离 WeChat scraper preamble (URL/Time/title-dup/reader-bait/author-dup) | 改 `kb/export_knowledge_base.py:135` 加正则剥离 7 个 boilerplate 模式 |

CSS 是对的,grid 布局是对的,部署 image hydration 也已经修过了。**这三个 bug 都不是部署 infra 问题,是 application-layer 数据/模板/字符串处理问题。**

## 调查方法

通过 PowerShell + Databricks CLI U2M OAuth token 直接访问部署:

1. `databricks auth token --host ...` → 拿到 836-byte JWT (3600s expiry)
2. `databricks fs cp dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/data/kol_scan.db .scratch/uat-investigation/kol_scan_DEPLOYED.db` → 拉部署的 SQLite (842 articles)
3. `curl -H "Authorization: Bearer $TOKEN" https://...azuredatabricksapps.com/` → 拉部署的 homepage HTML (69095 bytes, 20 article cards)
4. `WorkspaceClient.files.list_directory_contents` → 列 volume 的 images dir (254 hash dirs)
5. `git log --oneline -10` 检查 schema migration commit `bec8811` 是否真的部署

参考:`.scratch/uat-investigation/` 目录下所有 evidence 文件。

---

## Issue #1 — 微信图片 404

### 现象

所有 `mmbiz.qpic.cn` 外链图片 broken;只有 RSS 外链 web 图正常显示。

### Pre-investigation 状态

`aafdaf4` (kdb-images fix #3) 已经修了 `_db_bootstrap.py` 的 image hydration:
- 把 `/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/images/` 复制到 `/tmp/omnigraph_vault/images/`
- 部署后 ls 确认 254 hash dirs 都在
- localhost:8766 本地部署 100% 正常

但 UAT 还是失败。所以是部署后的 application-layer 问题。

### 根因双层结构

#### Layer A — Scrape data gap (27/30 articles)

部署主页的 30 个 wechat 卡片 sample,逐个 HEAD 请求 volume 路径:

```
/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/images/<content_hash>/
```

**27 个 hash 在 volume 里根本不存在**:

```
0121beaf39, 0a758378e8, 1f9f7bec3d, 23e8769bfc, 34c6c0e522,
3bf67d2526, 4f8c76b972, 5a26fee489, 5d8c70b58d, 61fc48cae6,
64fe9001a5, 66686a3a38, 805773ee29, 82539b4eed, 8a5dcf88bb,
8ccbf7f4a9, 907911fbc9, 9cbd555c68, 9e9a058478, acf27c2e5b,
b53958cac2, b75ac3d32c, bed6688316, c94352c89c, cf3c70ce0f,
d0558b8303, e7bfd8f28e
```

这些文章的 image 抓取阶段从来没成功过。Container 里的 hydrate 自然 hydrate 不出来。

#### Layer B — SSG body 重写 gap (3/30 articles)

3 篇 hash (`28c974c2cd`, `9f75b25295`, `c7fb080361`) 在 volume 里 **有** 本地图片 mirror,但部署的 article HTML body 里仍然是 raw `https://mmbiz.qpic.cn/...` URL。

根因:`kb/data/article_query.py:_rewrite_image_paths()` 只处理两种已知格式:
- `http://localhost:8765/<hash>/<n>.jpg` → `/static/img/<hash>/<n>.jpg`
- 裸的 `/static/img/...` 前缀

**它没有把 `mmbiz.qpic.cn/...` 映射回本地 hash。** 所以即使本地 mirror 存在,body markdown 里残留的 mmbiz URL 也不会被替换为 `/static/img/<hash>/<n>.jpg`。

加上 WeChat 的 hotlink protection (Referer 不是 WeChat 就 reject),浏览器看到的就是全部 broken image。

### 修复

```
F1.1 (data) — 对 27 个 hash 重跑 image 抓取
   流程:对每个 article 跑 single-URL `ingest_wechat.py` 的 image-only 模式,
        拉到 /Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/images/<hash>/
   预估:~ 30 min(WeChat throttle 50/batch + cooldown)+ ¥0.04 × 27 ≈ ¥1.1 vision

F1.2 (code) — kb/data/article_query.py:_rewrite_image_paths
   新增第三种格式映射:扫描 body 找所有 mmbiz.qpic.cn URL,
   按出现顺序映射到 /static/img/<article_hash>/<idx>.jpg(idx 从 0 开始,
   匹配 ingest_wechat.py 下载阶段的 metadata.json 顺序)。
   要求:有本地 mirror 的才映射;没 mirror 的保留原 URL(浏览器可能 SSR cache)。
   测试:tests/unit/ 加一个 test_rewrite_mmbiz_url 用 28c974c2cd 实例。

F1.3 (data) — 重跑 SSG export(make pass-0c kb_export)
   需要 F1.2 修完 + F1.1 完成后才有意义。
```

### 不变量

- F1.1 不需要碰 LightRAG storage(只补 images,不重新 ainsert)
- F1.2 是纯 application code 修改,无 schema 影响
- 所有改动应当 commit 但 **不 push**(用户约束)

---

## Issue #2 — 230+ 篇翻译没上线

### 用户预期 vs 实际

用户说 "已完成 230+ 篇翻译",首页看到的标题应该是英文(浏览器语言或用户偏好 = en)。
实际看到全是中文。

### 三层根因

#### A. Local DB 翻译数据严重缺(1 not 230)

```
$ sqlite3 .dev-runtime/data/kol_scan.db
> SELECT COUNT(*) FROM articles WHERE body_translated IS NOT NULL;
1
> SELECT COUNT(*) FROM articles WHERE title_translated IS NOT NULL;
1
> SELECT COUNT(*) FROM articles WHERE layer1_verdict='candidate';
233
```

230+ 这个数对应的是 **layer1=candidate 的 233 篇**(本应翻译的池子),
不是已翻译的篇数。`bec8811` commit message 写 "234/238 translated $0" 但
**实际执行过的翻译没成功落库**(或落库后被覆盖、回滚、丢失)。

需要确认:
- `bec8811` 当时执行 `apply.sql` 的目标 DB 是哪个
- 是不是只写到 SCP 中转层但 deploy 到 Volume 这步没接上

#### B. 部署 UC Volume DB schema 完全没有 translated_* 列

把部署的 DB 拉下来 `PRAGMA table_info(articles)`:

```
[c for c in cols if 'translat' in c.lower()] = []  ← 空
```

部署 DB 列结构:
```
id, account_id, title, url, digest, update_time, scanned_at,
content_hash, enriched, body, layer1_verdict, layer1_reason,
layer1_at, layer1_version, layer2_verdict, layer2_reason,
layer2_at, layer2_version, image_count
```

**完全没有 title_translated / body_translated / translated_lang / translated_at 列。**

意味着 `bec8811` 的 schema migration 从来没在 UC Volume DB 上跑过。
即使 application code 引用 `article.title_translated`,SQL 会直接报
`no such column`,SSG render 也会 fall back 到 zh title。

#### C. Template bilingual-wrap gap (4 个文件)

| 文件 | 行 | 问题字段 | 影响 |
|---|---|---|---|
| `kb/templates/index.html` | 103 | `article.snippet` 直接 plain text 渲染,**没 dual-span** | 即使有翻译数据,snippet 永远显示中文 |
| `kb/templates/articles_index.html` | 98 | 同上 | 同上 |
| `kb/templates/topic.html` | 97-99 | `article.title` + `article.snippet` 都是单语;EN page 也渲染 zh title | EN 页面显示中文 |
| `kb/templates/entity.html` | 89-91 | `a.title` + `a.snippet` 同上 | 同上 |

`article.html` 的 body 本身是对的(L122-127 双 `<article class="article-body lang-block" data-lang="zh|en">` siblings),
**只有 list-page 上的 card 和某些 cross-page link title 有 gap**。

### 修复

```
F2.1 (schema migration) — 在 UC Volume DB 上 ALTER TABLE
   把 bec8811 commit 的 migration SQL 真的跑一遍:
   ALTER TABLE articles ADD COLUMN title_translated TEXT;
   ALTER TABLE articles ADD COLUMN body_translated TEXT;
   ALTER TABLE articles ADD COLUMN translated_lang TEXT;
   ALTER TABLE articles ADD COLUMN translated_at TEXT;
   通过 databricks fs cp DB → 本地 SQLite 操作 → cp 回 Volume,
   或者用 databricks-mcp execute_sql 在 Delta 表上跑(取决于 Volume DB 是
   SQLite 直连还是 Unity Catalog 表 — 需要先确认存储格式)。

F2.2 (data backfill) — 对 233 篇 candidate 跑翻译
   重新执行 bec8811 commit 描述的 Tavily-driven backfill,
   写入 UC Volume 的 DB(F2.1 完成后)。
   预算:Tavily $0(free tier 内)+ Gemini Flash 230 articles × ~3000 token avg ≈ $0.30。

F2.3 (template) — kb/templates/ 4 个文件加 dual-span
   - index.html L103:
       {% if article.snippet %}
       <p class="article-card-snippet">
         <span data-lang="zh">{{ article.snippet }}</span><span data-lang="en">{{ article.snippet_translated or article.snippet }}</span>
       </p>
       {% endif %}
   - articles_index.html L98:同上
   - topic.html L97-99:同上 + title 也包(因为 topic.html 是 per-lang 渲染但
                       未来切到 dual-span,需要 article 数据本身带翻译)
   - entity.html L89-91:同上
   注意:需要在 kb/export_knowledge_base.py 的 _record_to_dict 阶段
        额外计算 snippet_translated(用 body_translated 跑同一个 _make_snippet)。

F2.4 (regen) — make pass-0c kb_export 重出 SSG,部署
```

### 不变量

- F2.1 是 schema 改动,需要 backup DB 后再操作
- F2.2 跑前要先在 local DB 验证 row count;不要双写
- F2.3 + F2.4 是纯 frontend/SSG 改动,不影响 ingest pipeline

---

## Issue #3 — 卡片排版"看起来坏了"

### 现象

部署主页 article-card 卡片显示乱七八糟,内容看起来 broken / 重复 / metadata leakage。
样例(从 deployed homepage HTML 第一张卡 snippet 字段):

```
我来预测下一代企业数字化架构:系统CLI化、流程Skill化、员工Agent化
URL: https://mp.weixin.qq.com/s/759TfOdXch5zWrT4Yo42xA
Time: 2026-05-16 23:13:16
我来预测下一代企业数字化架构:系统CLI化、流程Skill化、员工Agent化
原创 詹老师 詹老师 詹生Talk
;) ______
在小说阅读器读本章
去…
```

### 根因

**CSS 是对的。Grid 是对的。Box layout 是对的。**

- `kb/static/style.css:644-732` `.article-card` + `.article-list`:1/2/3 列响应式 grid 正确
- `.article-card-snippet` 有 `-webkit-line-clamp: 3` 三行截断
- 媒体查询 768px / 1024px 都正确

**根因是 snippet 内容污染:** `kb/export_knowledge_base.py:135 _make_snippet()`
只剥离 markdown markup(code fence、inline code、image syntax、link、heading、
HTML tag、emphasis、list bullet),但是 **不剥离 WeChat scraper 注入的 boilerplate**。

#### 污染源 #1 — `ingest_wechat.py:1303`

```python
full_content = f"# {title}\n\nURL: {url}\nTime: {publish_time}\n\n{markdown}"
```

每篇通过 `ingest_wechat.py` 单 URL 入口的文章,body 头都强制塞:
- `# {title}` 行
- 空行
- `URL: <url>` 行
- `Time: <publish_time>` 行
- 空行
- 接 markdown(markdown 自己又开始 `# {title}` — 产生 title duplicate)

`_make_snippet` 把 `# Title` 当 markdown heading 剥了(line 146),
但 **`URL:` 和 `Time:` 既不是 heading 也不是 list bullet,所以没被剥**。

#### 污染源 #2 — WeChat 原文的 reader-bait 模板

WeChat scrape 进来的 markdown body 本身在 article author block 之后通常带:

```
原创 詹老师 詹老师 [ 詹生Talk ](javascript:void\(0\);)

______

在小说阅读器读本章

去阅读

在小说阅读器中沉浸阅读

**点击上方"Deephub Imba",关注公众号,好文章不错过 !**
```

这一段所有微信文章共享。`_make_snippet` 不剥它。

#### 污染源 #3 — `;)` emoticon prefix

部分微信变体在 `______` 前加 `;) ` emoticon prefix(例如截图 sample),
也是 boilerplate。

### 修复

`kb/export_knowledge_base.py:_make_snippet` 在最早的 markdown 处理 **之前**
加一组 boilerplate-stripping 正则:

```python
def _make_snippet(body_md: str, max_chars: int = 200) -> str:
    if not body_md:
        return ""

    text = body_md

    # F3.1 strip ingest_wechat.py:1303 preamble (URL: + Time: lines)
    text = re.sub(r"^URL:\s*https?://\S+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^Time:\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s*$", "", text, flags=re.MULTILINE)

    # F3.2 strip WeChat reader-bait boilerplate
    # Match: optional ";) " prefix + bare ______ separator + the 3 reader-redirect lines
    text = re.sub(
        r"(;\)\s+)?_{3,}\s*\n+\s*在小说阅读器读本章\s*\n+\s*去阅读\s*\n+\s*在小说阅读器中沉浸阅读",
        "",
        text,
    )
    # Strip standalone marker lines that often survive scrape merge
    text = re.sub(r"^在小说阅读器(读本章|中沉浸阅读)\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^去阅读\s*$", "", text, flags=re.MULTILINE)

    # F3.3 strip "click-to-follow public account" CTA banner
    text = re.sub(r"\*\*点击上方[""''""]?[^""''""]+?[""''""]?,?关注公众号[^*]*\*\*", "", text)

    # F3.4 collapse author-name duplicates (WeChat 原创 X X pattern)
    # "原创 詹老师 詹老师 詹生Talk" → "原创 詹老师 詹生Talk"
    # Conservative: only collapse when same 2-4 char name repeats consecutively
    text = re.sub(r"(原创\s+)([一-龥\w]{2,5})\s+\2\b", r"\1\2", text)

    # F3.5 strip duplicated leading title (ingest_wechat.py:1303 prefix +
    # markdown's own # heading often produces title-duplicate-title pattern)
    # Apply AFTER preamble strip — by then `# Title\n\n# Title` has the URL/Time
    # gone in between, so only consecutive duplicate Heading-1 lines remain.
    lines = text.split("\n")
    out = []
    last_h1 = None
    for line in lines:
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            this_h1 = m.group(1).strip()
            if this_h1 == last_h1:
                continue  # skip immediate duplicate
            last_h1 = this_h1
        out.append(line)
    text = "\n".join(out)

    # === ORIGINAL markdown markup stripping (unchanged) ===
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"^[#>\-\*\+]+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"
```

### 测试

```python
# tests/unit/test_make_snippet_boilerplate.py
import pytest
from kb.export_knowledge_base import _make_snippet

def test_strips_url_time_preamble():
    body = "# Title\n\nURL: https://mp.weixin.qq.com/s/X\nTime: 2026-05-16 23:13:16\n\n# Title\n\nReal content here."
    snippet = _make_snippet(body)
    assert "URL:" not in snippet
    assert "Time:" not in snippet
    assert "Real content here" in snippet
    # title 也只出现一次
    assert snippet.count("Title") == 1

def test_strips_reader_bait():
    body = "# Article\n\n;) ______\n\n在小说阅读器读本章\n\n去阅读\n\n在小说阅读器中沉浸阅读\n\nReal body."
    snippet = _make_snippet(body)
    assert "在小说阅读器" not in snippet
    assert "______" not in snippet
    assert "Real body" in snippet

def test_strips_follow_cta():
    body = '**点击上方"Deephub Imba",关注公众号,好文章不错过 !** Real content.'
    snippet = _make_snippet(body)
    assert "关注公众号" not in snippet
    assert "Real content" in snippet

def test_collapses_author_dup():
    body = "原创 詹老师 詹老师 詹生Talk\n\n实际正文。"
    snippet = _make_snippet(body)
    assert snippet.count("詹老师") == 1
    assert "詹生Talk" in snippet

def test_idempotent_on_clean_body():
    body = "Just a normal markdown body with **bold** and `code`."
    snippet = _make_snippet(body)
    assert "Just a normal markdown body" in snippet
    assert "**" not in snippet
    assert "`" not in snippet
```

### 不变量

- `_make_snippet` 是纯函数,无 IO,改动不影响 ingest pipeline
- 改动只影响 snippet 字段(card preview),不动 body 本身
- 所有原有 markdown 剥离规则保留
- 4 个新增 strip 规则在 markdown 剥离 **之前**(line ordering 重要)

---

## 部署计划(forward-only,不 push,本地 commit)

```
Step 1 (Issue #3 — 最快、最孤立、最低风险)
  - 改 kb/export_knowledge_base.py:_make_snippet
  - 加 tests/unit/test_make_snippet_boilerplate.py
  - venv/Scripts/python.exe -m pytest tests/unit/test_make_snippet_boilerplate.py -v
  - git add kb/export_knowledge_base.py tests/unit/test_make_snippet_boilerplate.py
  - git commit -m "fix(kb-snippet): strip WeChat scraper preamble + reader-bait
    in _make_snippet (Issue #3 card layout)"
  - make pass-0c kb_export(本地)→ 验证生成的 index.html snippet 不再泄露
    URL/Time/title-dup
  - make deploy(PowerShell + databricks CLI,我自己跑)→ 部署
  - 浏览器 UAT 截图 → .scratch/uat-investigation/issue3-after.png

Step 2 (Issue #2 — template bilingual-wrap;不依赖 schema 修复就能立即上)
  - 改 4 个 template 文件
  - 给 kb/export_knowledge_base.py:_record_to_dict 加 snippet_translated 计算
  - tests/unit/ 加 test_record_to_dict_snippet_translated
  - git add ... && git commit -m "fix(kb-i18n): wrap card snippet/title in
    dual-span across index/articles_index/topic/entity (Issue #2 template gap)"
  - make pass-0c kb_export
  - make deploy
  - 没有翻译数据时 EN snippet 会 fallback 到 ZH(因为 `or article.snippet`),
    部分修但不破坏

Step 3 (Issue #1 SSG rewrite gap — 3 articles)
  - 改 kb/data/article_query.py:_rewrite_image_paths 加 mmbiz→local hash 映射
  - tests/unit/ 加 test_rewrite_mmbiz_url_to_local
  - git commit && make deploy

Step 4 (Issue #2 schema + data backfill — 真正修翻译数据)
  - 先在 local DB 做完整 dry-run:
      cp kol_scan.db kol_scan.db.backup-$(date)
      在 local DB 跑 ALTER TABLE migration
      跑 233-article translation backfill
      验证 row count + sample 翻译质量
  - 把验证后的 local DB 推送到 UC Volume:databricks fs cp ... dbfs:/Volumes/...
  - make deploy(重启 app picks up new DB hydrate)
  - 浏览器 UAT 验证翻译显示

Step 5 (Issue #1 scrape data gap — 27 articles)
  - 这是最贵的一步,留到最后
  - 跑 scripts/.../single-url-image-rescrape 对 27 个 hash
  - 推送到 UC Volume images dir
  - make deploy 触发 image hydrate
  - 浏览器 UAT
```

总预算:~$1.5(Gemini Flash 翻译 + 27 articles vision)+ ~30 min wallclock

## 风险

1. **F2.1 schema migration** 取决于 UC Volume kol_scan.db 是 SQLite 文件 还是
   Unity Catalog Delta 表。需要先 `databricks fs ls dbfs:/Volumes/.../data/`
   确认。如果是 SQLite 文件,流程是 fs cp out → ALTER → fs cp back;
   如果是 Delta 表,要用 ALTER TABLE 通过 Databricks SQL warehouse。

2. **F2.2 翻译数据量大** — 233 篇 × ~5K token / 篇 ≈ 1.2M token Gemini Flash。
   ~$0.30 cost,~10 分钟 wallclock。失败可以续跑(idempotent ON CONFLICT update)。

3. **F1.1 vision rescrape 27 articles** — WeChat throttle 50/batch + cooldown,
   实际是 30 min wallclock。SiliconFlow 余额 check 必须在跑前确认 ≥¥1.

4. **不要 git push** — 全部本地 commit。push 由用户后续决定。

## Evidence files

```
.scratch/uat-investigation/
├── kol_scan_DEPLOYED.db        # 842 articles, 0 translation columns
├── index_DEPLOYED.html         # 69095 bytes, 20 article-card blocks
├── first_card.html             # snippet leakage sample
├── volume_images_listing.txt   # 254 hash dirs in volume
├── 27_missing_hashes.txt       # scrape data gap list
└── 3_ssg_rewrite_gap.txt       # body-still-mmbiz list
```

## 后续

修完三个 issue 各自的 commit + deploy + 浏览器 UAT 验证后,把本文档 frontmatter 的
`status` 改为 `deployed-and-verified`,引用 commit/deployment ID 列表。
模仿 `_kdb_images_fix_VERIFICATION.md` 的格式。
