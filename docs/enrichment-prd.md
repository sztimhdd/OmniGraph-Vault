# PRD: 知识增厚模块 (Knowledge Enrichment)

> **目标受众**: Claude Code  
> **仓库**: [OmniGraph-Vault](https://github.com/sztimhdd/OmniGraph-Vault)  
> **状态**: 已验证端到端可行性，进入开发阶段

---

## 1. 模块定位

在现有管线中插入一个环节：

```
WeChat 抓取 → [文本+图片存储] → ★ 知识增厚 ★ → LightRAG 入库
```

**做什么**: 对一篇已抓取的微信文章，用 LLM 提取 3 个原文悬而未答的技术问题 → 知乎好问搜索每个问题得到 AI 综述 → 从综述的引用源中精选 1 篇知乎原答案 → URL 发回 Python 侧抓取全文+图片。最终产出 4 个图文并茂的 Markdown 文件：

```
微信原文 (大幅强化)
    ├── 3 个好问综述追加到原文尾部
    ├── 知乎原答案 A.md  (独立)
    ├── 知乎原答案 B.md  (独立)
    └── 知乎原答案 C.md  (独立)
```

**为什么不是 7 个文件**: 好问综述是 AI 生成的二级内容，不应与原创文章平起平坐。嵌入原文作为扩展章节更准确。

---

## 2. 架构总览

```
┌───────────── Python 模块 (Claude Code 实现) ─────────────┐
│                                                            │
│  orchestrate.py ──→ extract_questions.py ──→ LLM           │
│        │                    │                              │
│        │               [1-3 questions]                     │
│        │                    │                              │
│        │         ┌─────────┘                              │
│        │         ▼                                         │
│        │    for each question:                             │
│        │      call Hermes skill ──→ {summary, source_url}  │
│        │         │                                         │
│        │         ▼                                         │
│        │      fetch_zhihu.py (CDP) ──→ answer.md + images  │
│        │         │                                         │
│        │         ▼                                         │
│        │      image_pipeline.py (共用)                     │
│        │                                                  │
│        ├──→ merge_md.py ──→ 增强版微信原文.md              │
│        └──→ ingest_enriched.py ──→ LightRAG               │
│                                                            │
└────────────────────────────────────────────────────────────┘
          │ 调用
          ▼
┌─── Hermes Skill (Hermes 执行) ───┐
│  zhihu-haowen-enrich              │
│  1. CDP 打开 zhida.zhihu.com     │
│  2. 搜索问题                      │
│  3. 等待 AI 综述生成              │
│  4. 展开源面板 → 选最优卡片       │
│  5. 返回 {summary, source_url}    │
└──────────────────────────────────┘
```

**为什么好问部分用 Hermes Skill 而不是 Python 脚本**: 好问是 React SPA + Draft.js 富文本编辑器 + React Router 路由。选择器写死在 Python 代码里，知乎改版就挂。Hermes 技能用自然语言描述流程，Agent 自适应页面变化。

---

## 3. 数据流

```
输入: 微信文章 MD 路径
  │
  ├─ 1. 读原文纯文本 (strip Markdown)
  │
  ├─ 2. extract_questions.py
  │     LLM 提取 1-3 个待补技术问题
  │     输出: [{question, context}]
  │     跳过条件: 原文 < 2000 字符 → 标记 enriched=-1
  │
  ├─ 3. 循环每个问题:
  │     a. 调 Hermes skill "zhihu-haowen-enrich"
  │        输入: question
  │        输出: {summary: str, source_url: str, source_title: str}
  │        ← 失败处理: 标记该问题 failed，继续下一个
  │     
  │     b. fetch_zhihu.py(source_url)
  │        CDP 打开知乎 URL → scroll 到底 → 提取 article.innerText
  │        → 提取 img[src*="zhimg"] → 过滤 w<100
  │        → image_pipeline.download_images()
  │        → image_pipeline.localize_markdown()
  │        → image_pipeline.describe_images()
  │        输出: answer.md + images/{hash}/ 目录
  │
  ├─ 4. merge_md.py
  │     将 3 个 summary 追加到微信原文 MD 尾部
  │     格式: "## 知识增厚\n\n### Q1: {question}\n{summary}\n---\n..."
  │
  └─ 5. ingest_enriched.py
       4 个 MD → LightRAG upsert
       微信原文 ← references → 3 篇知乎答案
       标记 articles SET enriched=2
```

---

## 4. 数据库 Schema 变更

文件: `kol_scan.db`，在现有 `articles` 和 `ingestions` 表基础上：

```sql
-- articles 表新增
ALTER TABLE articles ADD COLUMN enriched INTEGER DEFAULT 0;
-- 0: 未增厚
-- 1: 增厚进行中
-- 2: 增厚完成
-- -1: 跳过 (文章太短/质量不够)
-- -2: 增厚失败

-- ingestions 表新增
ALTER TABLE ingestions ADD COLUMN enrichment_id TEXT;
-- 批次标识，格式: "enrich_{article_id}_{timestamp}"
```

---

## 5. Deliverables 清单

### 5.1 新增文件

| # | 路径 | 功能 |
|---|------|------|
| 1 | `enrichment/__init__.py` | 包初始化 |
| 2 | `enrichment/extract_questions.py` | LLM 提取待补问题 |
| 3 | `enrichment/fetch_zhihu.py` | CDP 抓知乎原文 + 图片 |
| 4 | `enrichment/merge_md.py` | MD 复写合并 |
| 5 | `enrichment/orchestrate.py` | 主流程编排 |
| 6 | `image_pipeline.py` | 图片下载/本地化/Vision(重构) |
| 7 | `skills/zhihu-haowen-enrich/SKILL.md` | Hermes 好问技能 |

### 5.2 修改文件

| # | 路径 | 改动 |
|---|------|------|
| 8 | `config.py` | 新增配置项 |
| 9 | `ingest_wechat.py` | 加 `--enrich` flag |
| 10 | `skills/omnigraph_ingest/SKILL.md` | 加增厚步骤 |

### 5.3 测试文件

| # | 路径 | 覆盖 |
|---|------|------|
| 11 | `tests/test_extract_questions.py` | 正常/短文本/空文本/低质文本 |
| 12 | `tests/test_fetch_zhihu.py` | mock CDP，验证图片过滤/下载 |
| 13 | `tests/test_merge_md.py` | MD 格式正确性 |
| 14 | `tests/test_orchestrate.py` | 端到端集成 (mock 好问输出) |

---

## 6. 组件详细规格

### 6.1 extract_questions.py

```python
def extract_questions(article_text: str, model: str = "deepseek-v4-flash") -> list[dict]:
    """
    从原文提取 1-3 个作者提到但未充分回答的技术问题。
    
    输入: 微信文章纯文本 (已 strip Markdown 格式和图片引用)
    输出: [{"question": "...", "context": "原文相关段落摘要"}]
    
    规则:
    - 原文 < config.ENRICHMENT_MIN_LENGTH (默认 2000 字) → 返回空列表
    - 每个问题必须是可搜索的自然语言问句，不是关键词
    - 不是实体识别——是判断 "作者抛出了什么但没讲透"
    - 如果原文没有值得深挖的技术缺口 → 返回空列表
    
    LLM Prompt 要点:
    - 角色: 你是技术编辑，正在审阅一篇 AI/Agent 工程文章
    - 任务: 找出 1-3 个原文提到但未充分展开的关键技术问题
    - 负面示例: 不要输出 "什么是 Harness"（原文已经讲清楚了）
    - 正面示例: "长任务中断恢复的工程实践——session 间状态传递的架构模式"
    """
```

### 6.2 fetch_zhihu.py

```python
def fetch_zhihu_article(url: str, article_hash: str) -> dict:
    """
    CDP 抓取知乎专栏文章，下载图片，本地化。
    
    返回: {"md_path": str, "image_dir": str, "title": str, "word_count": int}
    
    图片处理流程 (调 image_pipeline):
    1. 滚到底 → document.querySelectorAll('article img[src*="zhimg"]')
    2. 过滤: naturalWidth < 100 → 跳过 (头像/图标)
    3. 下载到 images/{hash}/{index}.jpg
    4. 替换 MD 中的远程 URL → http://localhost:8765/{hash}/{index}.jpg
    5. Gemini Vision 描述每个图片
    
    知乎 CDN 特性:
    - URL 格式: https://picX.zhimg.com/v2-{md5}_{size}.jpg
    - 无鉴权，不需要 cookie 或 Referer
    - strip _size 后缀得原图
    """
```

### 6.3 merge_md.py

```python
def merge_enrichment(original_md_path: str, enrichments: list[dict]) -> str:
    """
    将好问综述追加到微信原文 MD 尾部。
    
    enrichments: [{"question": str, "summary": str, "source_title": str, "source_url": str}]
    
    追加格式:
    ---
    ## 知识增厚
    
    ### Q1: {question}
    > 来源: [{source_title}]({source_url})
    
    {summary}
    
    ---
    
    ### Q2: ...
    
    返回: 新 MD 路径
    """
```

### 6.4 orchestrate.py

```python
def enrich_article(article_md_path: str, article_id: int = None) -> dict:
    """
    主编排函数。
    
    输入: 微信文章 MD 文件路径
    输出: {"status": "ok"/"partial"/"failed", "enrichment_id": str, "results": [...]}
    
    串行处理每个问题 (非并行——天然反封控):
    for q in questions:
        result = call_hermes_skill("zhihu-haowen-enrich", q.question)
        if result.success:
            answer = fetch_zhihu_article(result.source_url)
        
    merge_md(article_md_path, success_results)
    
    错误隔离: 单个问题失败不阻塞其他
    DB 更新: articles SET enriched=2 或 -2 或 -1
    """
```

### 6.5 image_pipeline.py (重构)

现有 `ingest_wechat.py` 内置了图片处理逻辑。抽取为公共模块，微信和知乎共用：

```python
# 公共 API
def download_images(urls: list[str], target_dir: str) -> dict[str, str]:
    """下载远程图片到本地，返回 {remote_url: local_path} 映射"""

def localize_markdown(md_text: str, mapping: dict[str, str]) -> str:
    """替换 MD 中的远程图片 URL 为本地 URL"""

def describe_images(image_paths: list[str], api_key: str = None) -> dict[str, str]:
    """Gemini Vision 描述图片，返回 {local_path: description}"""

def save_markdown_with_images(md_text: str, image_urls: list[str], 
                               output_dir: str, base_url: str = "http://localhost:8765"):
    """一站式: 下载 → 本地化 → 描述 → 保存 MD + metadata.json"""
```

---

## 7. Hermes Skill 规格

### zhihu-haowen-enrich

**文件**: `skills/zhihu-haowen-enrich/SKILL.md`

**功能**: 使用 CDP 浏览器操作知乎好问 (zhida.zhihu.com)，搜索问题并返回 AI 综述 + 最佳引用源。

**前提条件**:
- CDP 浏览器已连接 (用户 Windows Edge with 知乎登录态)
- `browser_cdp` 工具可用

**流程**:

```
1. browser_navigate → https://zhida.zhihu.com/
2. 找到并点击「搜索」区域 → 打开搜索对话框
3. 在输入框中输入问题 (Draft.js 编辑器)
4. 回车提交搜索
5. 等待 AI 综述生成完成 (观察 "完成回答" 标志出现)
6. browser_console 提取综述全文文本
7. 找到并点击「全部来源 N」按钮 → 展开源面板
8. 从源卡片列表中选最优 (标准: 标题匹配度 + 点赞/关注数)
9. 点击该卡片 → 获取跳转后的 URL (location.href)
10. 返回 {summary, source_url, source_title}
```

**关键风险**:
- Draft.js 编辑器输入可能失败 → 回退: 点击历史记录中的前序搜索
- 源面板 URL 不在 DOM `<a>` 标签 → 需点击后从 `location.href` 获取

---

## 8. 配置项 (`config.py` 增量)

```python
# === 知识增厚配置 ===

# 是否默认启用增厚 (ingest_wechat.py --enrich)
ENRICHMENT_ENABLED = True

# 跳过增厚的文章最短字数
ENRICHMENT_MIN_LENGTH = 2000

# 好问搜索超时 (秒)
ZHIHAO_TIMEOUT = 120

# 知乎文章抓取超时 (秒)
ZHIHU_FETCH_TIMEOUT = 60

# 增厚使用的 LLM 模型 (提取问题阶段)
ENRICHMENT_LLM_MODEL = "deepseek-v4-flash"

# 本地图片服务器地址
IMAGE_SERVER_BASE_URL = "http://localhost:8765"

# 好问技能名称
ZHIHAO_SKILL_NAME = "zhihu-haowen-enrich"
```

---

## 9. 错误处理矩阵

| 环节 | 错误类型 | 处理策略 | enriched 状态 |
|------|----------|----------|:---:|
| 提取问题 | 文章 < 2000 字 | 跳过，不增厚 | -1 |
| 提取问题 | LLM 返回空 | 跳过，无问题可问 | -1 |
| 好问搜索 | 超时 120s | 标记该问题 failed，继续下一个 | — |
| 好问搜索 | 生成失败/返回空 | 标记该问题 failed，继续下一个 | — |
| 好问搜索 | 源面板无合适卡片 | 标记该问题 failed，继续下一个 | — |
| 知乎抓取 | CDP 超时 60s | 标记该问题 failed，继续下一个 | — |
| 知乎抓取 | 图片下载失败 | 跳过该图片，继续 (MD 保留远程 URL) | — |
| 知乎抓取 | CAPTCHA 拦截 | 标记该问题 failed，继续下一个 | — |
| 合并写入 | 磁盘满 | 中止，保留已完成的 | -2 |
| 任意环节 | 3 个问题全部失败 | 整体失败 | -2 |
| 任意环节 | ≥1 个问题成功 | 部分完成，正常入库 | 2 |

---

## 10. 测试策略

| 测试层 | 范围 | 工具 |
|--------|------|------|
| 单元测试 | extract_questions, merge_md | pytest |
| 集成测试 | fetch_zhihu (mock CDP), image_pipeline | pytest + mock |
| 端到端 | orchestrate (mock 好问 skill 输出) | pytest |
| 真机测试 | zhihu-haowen-enrich skill 完整流程 | Hermes 手动执行 |

**关键 Mock 点**:
- `fetch_zhihu.py`: mock `browser_console` 返回值，预置 sample HTML
- `orchestrate.py`: mock `call_hermes_skill()` 返回值，预置固定 summary + URL
- LLM 调用: mock `extract_questions` 的 LLM API 响应

---

## 11. 设计决策笔记 (Why)

### 11.1 为什么好问改成嵌入原文而非独立存

好问综述是 AI 生成的二级内容。它不配和原创知乎答案平起平坐，但作为原文的补充非常合适。存入方式反映内容层级关系。

### 11.2 为什么串行不是并行

1. 同一 CDP 浏览器 tab 不能同时处理 3 个好问搜索
2. 知乎反爬：3 个搜索串行间隔自然，并行容易被识别
3. 代码简单：不需要处理并发失败和状态同步

### 11.3 为什么好问是 Skill 不是 Python 脚本

好问是 React SPA + Draft.js + React Router。CSS class 是自动生成的哈希值，下次部署全变。Hermes 技能的「找到搜索框输入问题」是语义级的，不依赖具体选择器。

### 11.4 为什么图片必须处理

知乎文章的核心信息在图表里——热力图、分类树、dispatch 架构图。纯文本增量只是多了段落，图片才让增厚变成可引用的结构化知识。

### 11.5 为什么主站搜索保留为回退

好问依赖 CDP 浏览器交互，脆弱性高于 API 调用。主站 `zhihu.com/search?q=` 支持 URL 参数，即使好问失效仍可降级运行。

---

## 12. 开发顺序

```
Phase 1: 基础组件
  └── extract_questions.py → merge_md.py → config.py

Phase 2: 图片管线重构
  └── image_pipeline.py (从 ingest_wechat 抽共性)
  └── ingest_wechat.py 改用 image_pipeline

Phase 3: 知乎抓取 + Hermes 技能
  └── fetch_zhihu.py
  └── zhihu-haowen-enrich skill (需 Hermes 联调验证)

Phase 4: 编排 + 入库
  └── orchestrate.py
  └── ingest_enriched.py (LightRAG 集成)

Phase 5: 集成现有流程
  └── ingest_wechat.py --enrich flag
  └── omnigraph_ingest skill 更新
  └── DB migration
```

---

*文档版本: v1.0 · 2026-04-27*
