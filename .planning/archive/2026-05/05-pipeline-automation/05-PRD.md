# Phase 5: Pipeline 全自动化 + 精品内容推荐

**版本:** 1.0  
**日期:** 2026-04-27  
**状态:** 设计阶段  
**面向:** Claude Code + GSD (Get Shit Done)  
**依赖:** Phase 4 (knowledge-enrichment-zhihu) 已完成

---

## 1. 产品目标

### 1.1 用户故事

> 每天早上醒来，Telegram 收到一条消息：「今日 AI 精品 3 篇」，附上 Markdown 摘要和原文链接。昨晚睡觉时，Hermes 已经把 56 个微信 KOL 和 92 个 Karpathy RSS 的最新文章扫完、分类、增厚、入库。

### 1.2 核心指标

| 指标 | 目标 |
|------|------|
| 日扫描覆盖率 | 56 KOL + 92 RSS = 148 源全覆盖 |
| 深度文章召回 | 分类器筛选出 depth_score ≥ 2 的文章 |
| 知识增厚触发 | 深度文章自动进入 Phase 4 enrich 流程 |
| 日推送达 | 每日 08:00 前 Telegram 推送「今日精品」 |
| 全自动无人值守 | 0 人工干预，异常通过 Telegram 通知 |

---

## 2. 架构总览

### 2.1 Phase 5 数据流

```
┌─────────────────────────────────────────────────────────────┐
│                      CRON ORCHESTRATOR                       │
│                                                              │
│  06:00  RSS 扫描 ──→ rss_articles 表                         │
│  07:00  RSS 分类 ──→ rss_classifications 表                  │
│  07:55  健康检查 (CDP + 凭证刷新)                              │
│  08:00  KOL 扫描 ──→ articles 表 (已有)                       │
│  08:15  KOL 分类 ──→ classifications 表                       │
│  08:30  统一增厚 ──→ Phase 4 enrich (KOL + RSS 深度文章)    │
│  09:00  统一摄入 ──→ LightRAG                                 │
│  09:30  日推生成 ──→ Telegram「今日精品」                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 与现有架构的关系

```
现有:                            Phase 5 新增:
───────                          ────────────
batch_scan_kol.py ───┐          rss_fetch.py ───┐
batch_classify_kol.py ┤  KOL     rss_classify.py ┤  RSS
batch_ingest_*.py    ┘           rss_ingest.py   ┘
                                 
enrich_article (skill)  ←── 统一增厚层 (新增 orchestrate_daily.py)
                                 
kg_synthesize.py        ←── 不动 (未来 Agentic RAG 重构)
                                 
                             daily_digest.py  ←── 日推生成器 (新增)
```

### 2.3 不做的

- ❌ 图可视化
- ❌ kg_synthesize 重构 (保留给未来的 Agentic RAG 阶段)
- ❌ 多源扩展到 Karpathy RSS 以外的源
- ❌ 实时/流式摄入
- ❌ Web 界面

### 2.4 关键前置: Embedding 模型迁移 (Critical Prerequisite)

Phase 5 的第一件事不是 RSS，而是把 LightRAG 的 embedding 从 `gemini-embedding-001` 迁移到 `gemini-gemini-embedding-2`（多模态）。

**为什么现在做:**

- **Phase 4 出口 blocker**: `embedding-001` free-tier 100 RPM，LightRAG per-doc entity upsert 稳定 429。这是 302 篇存量 KOL 入图的根因。
- **多模态能力解锁**: `gemini-embedding-2` 直接接受 image bytes，可以删掉 `image_pipeline.describe_images()` 的 Gemini Vision 转写步骤，跨模态检索（文本 query → 图片 chunk）自然启用。
- **关键时序（不可调换）**: Phase 4 close → Phase 5 embedding 迁移 → 302 篇 catch-up。**反序执行会浪费 ~$1 + 强制二次 re-embed 800+ docs**（两次嵌入空间不兼容）。

**Scope:**

1. **Spike 先行（先确认可行，再迁移）**: LightRAG 的 `embedding_func` contract 目前是 `(texts: list[str]) -> np.ndarray`。确认可否拓宽签名接受 `images: list[bytes] | None`，或需要 fork/wrap `gemini_embed`。产出: `docs/spikes/gemini-embedding-2-contract.md` — go/no-go 决策。
2. **替换 Vision pass**: `image_pipeline.describe_images()`（Gemini Vision → 文字描述 → 文本 embedding）改为直接将 image bytes 送入 `gemini-embedding-2`。
3. **扩展 embedding_func 签名**: `gemini_embed` 包装器接受 `texts: list[str]` + `images: list[bytes] | None`，内部路由到 `gemini-embedding-2` 多模态接口。
4. **重嵌入存量 18 docs**: 新旧 embedding 维度/语义空间不兼容，复用 Phase 4 D-14 `delete + reinsert` 路径。预计 ~1 min / ~$0.03。
5. **302 篇 KOL catch-up**: 新管线跑存量追赶摄入。预计 ~25 min / 净成本 ≤ embedding-001 情况下的成本（删掉的 Vision pass 抵消新 embedding 溢价）。

**Success criteria:**

| 维度 | 验证方法 |
|------|----------|
| 中文文本检索不退化 | Benchmark 5–10 条 Phase 4 已验证的 query，迁移前后 top-k 结果相似或更好 |
| 跨模态图片检索上线 | 文本 query（「XXX 架构图」「某论文图表」）top-5 中至少 1 条命中含该图片的 chunk |
| 成本中性 | 302 篇 catch-up 总花费 ≤ embedding-001 估算（删掉 Vision pass 抵消溢价） |
| LightRAG 无回归 | 迁移后 `omnigraph_query` / `kg_synthesize.py` / `enrich_article` 正常 |

**为什么不拆成独立 phase**: 迁移是一次性工程 + 一次 catch-up，没有日常运维面。并入 Phase 5 Wave 0，与后续 RSS/orchestrator 共享同一个 embedding 基座，避免「迁移 → RSS」心智切换成本。

---

## 3. 模块设计

### 3.1 RSS 摄入模块

#### 3.1.1 数据源

OPML 文件: `https://gist.github.com/emschwartz/e6d2bf860ccc367fe37ff953ba6de66b`

内容: HN 2025 年度最受欢迎博客 TOP 92（含 RSS/Atom feed），由 Andrej Karpathy 推荐。

代表性源:

| 博客 | RSS URL | 领域 |
|------|---------|------|
| simonwillison.net | `/atom/everything/` | LLM, Python, Datasette |
| gwern.net | `/atom.xml` | AI, 统计学, 心理学 |
| antirez.com | `/atom.xml` | Redis, 系统编程 |
| paulgraham.com | `/rss.xml` | 创业, 随笔 |
| krebsonsecurity.com | `/feed/` | 网络安全 |
| ... | | 共 92 个 |

#### 3.1.2 新增文件

```
enrichment/rss_fetch.py          # OPML 解析 + RSS/Atom 抓取
enrichment/rss_classify.py       # RSS 文章 LLM 深度分类 (复用 batch_classify_kol 模式)
enrichment/rss_ingest.py         # RSS 文章摄入 LightRAG
enrichment/orchestrate_daily.py  # 日度统一编排器
enrichment/daily_digest.py       # 日推生成器
```

#### 3.1.3 RSS 抓取器 (`rss_fetch.py`)

**职责:** 解析 OPML → 抓取每个 feed → 去重 → 写入 SQLite

```
输入: OPML 文件 (本地缓存 or HTTP fetch)
输出: SQLite rss_articles 表 (新增)
```

**技术决策:**

| 决策 | 选择 | 理由 |
|------|------|------|
| RSS 解析库 | `feedparser` (pip) | 标准库，支持 RSS 2.0 + Atom |
| OPML 解析 | `xml.etree.ElementTree` (stdlib) | 无需额外依赖 |
| HTTP 客户端 | `requests` + `User-Agent: OmniGraph-Vault/1.0` | 已在 requirements.txt |
| 去重策略 | `url UNIQUE` 约束 + `content_hash` 字段 | 与 articles 表一致 |
| 频率控制 | Feed 间 2s 延迟 | 尊重源站，92 feeds × 2s ≈ 3min |

**Feed 级别容错:**

```python
# 每个 feed 独立 try/except，单个失败不阻断整体
for feed in feeds:
    try:
        articles = fetch_feed(feed.url)
        insert_articles(articles)
    except (FeedFetchError, ParseError, Timeout) as e:
        logger.warning(f"Feed {feed.name} failed: {e}")
        failed_feeds.append(feed.name)
        continue
```

**内容预筛选（抓取阶段）:**

- 跳过非英文/中文文章（语言检测，`langdetect` 或简单启发式）
- 跳过 < 500 字符的文章（明显非深度内容）

#### 3.1.4 SQLite Schema 扩展

```sql
-- RSS 订阅源注册表
CREATE TABLE IF NOT EXISTS rss_feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,            -- simonwillison.net
    xml_url TEXT NOT NULL UNIQUE,  -- https://simonwillison.net/atom/everything/
    html_url TEXT,                 -- https://simonwillison.net
    category TEXT,                 -- tech / security / ai / ...
    active INTEGER DEFAULT 1,     -- 0=暂停
    last_fetched_at TEXT,
    error_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- RSS 文章表（与 articles 表结构对齐）
CREATE TABLE IF NOT EXISTS rss_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id INTEGER NOT NULL REFERENCES rss_feeds(id),
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    author TEXT,
    summary TEXT,                  -- RSS feed 自带摘要
    content_hash TEXT,
    published_at TEXT,             -- 文章原始发布时间
    fetched_at TEXT DEFAULT (datetime('now', 'localtime')),
    enriched INTEGER DEFAULT 0,   -- 0=待处理, 2=已增厚, -1=跳过(非深度)
    content_length INTEGER        -- 字符数，用于快速过滤
);

-- RSS 分类表（与 classifications 表对齐）
CREATE TABLE IF NOT EXISTS rss_classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES rss_articles(id),
    topic TEXT NOT NULL,
    depth_score INTEGER CHECK(depth_score BETWEEN 1 AND 3),
    relevant INTEGER DEFAULT 0,
    excluded INTEGER DEFAULT 0,
    reason TEXT,
    classified_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(article_id, topic)
);
```

#### 3.1.5 RSS 分类器 (`rss_classify.py`)

> **Superseded by Phase 5 D-07 (2026-04-28):** All RSS articles with depth_score ≥ 2 go through Zhihu 好问 enrichment regardless of language. The "英文 RSS 可能不需要增厚" note below is obsolete.

**复用 `batch_classify_kol.py` 的分类逻辑**，适配 RSS 数据源：

- LLM prompt 调整为英文为主 + 中文兼容
- 分类 topic 与 KOL 共用同一套标签体系（NLP, CV, Agent, LLM, RAG 等）
- depth_score: 1=资讯/快讯, 2=技术教程/分析, 3=深度研究/架构拆解

**分类过滤规则:**

```
depth_score ≥ 2 → 进入增厚/摄入候选
depth_score = 1 → 跳过 (非深度内容)
excluded = 1  → 跳过 (广告/招聘/纯转载)
```

**RSS 文章的增厚适配:**

`extract_questions.py` 需要在 Phase 5 中支持英文输入：
1. 检测输入语言（英文/中文）
2. 如果是英文 → 提取英文问题 → 翻译为中文 → 送入好问
3. 如果是中文 → 原有流程不变

翻译可以在 prompt 中一步完成：要求 Gemini 直接输出中文问题，无需单独的翻译步骤。

**复用 `batch_ingest_from_spider.py` 的摄入逻辑**：

- 对 depth_score ≥ 2 的 RSS 文章，格式化为 Markdown
- 调用 Phase 4 `enrich_article` skill（可选，取决于是否需要知乎增厚）
- 调用 LightRAG `ainsert()` 摄入

注意：英文 RSS 文章同样经过增厚流程。`extract_questions.py` 提取英文问题后，先翻译为中文再送入好问；好问返回的中文综述 + 知乎原答案作为独立段落嵌入英文原文下方。技术问题的语言鸿沟几乎为零——Agent 架构、RAG 模式、Transformer 优化这些概念是语言无关的。

---

### 3.2 统一编排器 (`orchestrate_daily.py`)

**职责:** 按时间窗口串行执行每日全流程，是 Phase 5 的中枢。

```
orchestrate_daily.py
├── Step 1: fetch_rss()          → rss_fetch 模块
├── Step 2: classify_rss()       → rss_classify 模块
├── Step 3: health_check()       → CDP + 凭证验证 (复用 07:55 cron 逻辑)
├── Step 4: scan_kol()           → batch_scan_kol.py --daily
├── Step 5: classify_kol()       → batch_classify_kol.py --topic all
├── Step 6: enrich_deep()        → 对 depth≥2 的 KOL 文章调 enrich_article skill
├── Step 7: ingest_all()         → batch_ingest_from_spider.py --from-db
├── Step 8: generate_digest()    → daily_digest.py
└── Step 9: deliver()            → Telegram
```

**状态机:**

```
每一步返回 (success: bool, summary: str, next_step: str|None)
失败时: 记录错误 → 发送 Telegram 警告 → 继续下一步 (非阻断)
关键步骤失败 (CDP 不可达): 停止 → 通知用户
```

**幂等性保证:**

- RS S文章: `url UNIQUE` → 重复抓取自动跳过
- 分类: `UNIQUE(article_id, topic)` → 重复分类 = no-op
- 摄入: `UNIQUE(article_id)` in ingestions → 重复摄入 = 跳过

---

### 3.3 日推生成器 (`daily_digest.py`)

**职责:** 从当天摄入的深度文章中，选出 TOP N 篇生成「今日精品」Markdown，Telegram 推送。

#### 3.3.1 选文策略

```
候选池: 今天摄入的 depth_score ≥ 2 的文章 (KOL + RSS)
排序: depth_score (降序) → content_length (降序) → classified_at
截断: TOP 5 (可配置)
```

#### 3.3.2 输出格式

```markdown
📰 **OmniGraph-Vault 今日精品** — 2026-04-28

---

**1. [Agent] 万字深研｜Harness 工程实践**  
📎 叶小钗 · WeChat  
指令改变不了 AI 行为（遵从率 ~20%），但机械约束可以（执行率 100%）...  
🔗 [阅读原文](https://mp.weixin.qq.com/s/...)

**2. [LLM] Things we learned about LLMs in 2025**  
📎 simonwillison.net · RSS  
A retrospective on how LLM capabilities evolved, what surprised us...  
🔗 [阅读原文](https://simonwillison.net/2025/...)

**3. [CV] CVPR 2026 Oral | 3D 主动建图长程规划**  
📎 我爱计算机视觉 · WeChat  
让机器人学会"想象"建图...  
🔗 [阅读原文](https://mp.weixin.qq.com/s/...)

---
📊 今日扫描: 56 KOL + 92 RSS | 深度文章: 12 篇 | 已摄入图谱: 12 篇
```

#### 3.3.3 送达方式

| 方式 | 说明 |
|------|------|
| Telegram 推送 | 主要送达渠道，利用现有 `send_message` 工具 |
| 本地存档 | `~/.hermes/omonigraph-vault/digests/2026-04-28.md` |

---

### 3.4 Cron 编排

```
┌──────────┬──────────────────────────────────────┐
│  06:00   │ fetch_rss                            │
│  07:00   │ classify_rss                         │
│  07:55   │ health_check (CDP + 微信凭证刷新)      │
│  08:00   │ scan_kol                             │
│  08:15   │ classify_kol                         │
│  08:30   │ enrich_deep (Phase 4, KOL only)      │
│  09:00   │ ingest_all (RSS + KOL → LightRAG)    │
│  09:30   │ generate_digest → Telegram            │
└──────────┴──────────────────────────────────────┘
```

**Hermes Cron 实现:**

> **Superseded by Phase 4 D-12:** Question extraction uses Gemini 2.5 Flash Lite (with optional grounding). `ENRICHMENT_LLM_MODEL` no longer points at DeepSeek.

不再使用单一大 cron job。改为独立 job + 合理间隔：

```bash
# RSS 链路
hermes cronjob add --name "rss-fetch" --schedule "0 6 * * *" \
  --prompt "run enrichment/rss_fetch.py" --model deepseek-v4-flash
hermes cronjob add --name "rss-classify" --schedule "0 7 * * *" \
  --prompt "run enrichment/rss_classify.py" --model deepseek-v4-flash

# KOL 链路 (已有)
# 07:55 health_check  (已创建: e7afccd9931b)
# 08:00 scan_kol       (已创建: df7dc3fa0390)

# 后处理链路
hermes cronjob add --name "daily-classify-kol" --schedule "15 8 * * *" \
  --prompt "run batch_classify_kol.py --topic Agent --topic LLM --min-depth 2" \
  --model deepseek-v4-flash
hermes cronjob add --name "daily-enrich" --schedule "30 8 * * *" \
  --prompt "run the enrich_article skill for all KOL + RSS articles with depth_score >= 2" \
  --model deepseek-v4-flash
hermes cronjob add --name "daily-ingest" --schedule "0 9 * * *" \
  --prompt "run batch_ingest_from_spider.py --from-db" \
  --model deepseek-v4-flash
hermes cronjob add --name "daily-digest" --schedule "30 9 * * *" \
  --prompt "run enrichment/daily_digest.py" --model deepseek-v4-flash \
  --deliver telegram
```

---

## 4. Claude Code 远程 SSH 验证

### 4.1 环境说明

Hermes Agent 运行在 WSL2 (Ubuntu 24.04) 内部，通过 Windows 宿主机的 Edge CDP 浏览器访问微信和知乎。

```
┌──────────────────────────────────────────────┐
│  Windows 11 宿主机                             │
│  ├─ Edge (CDP port 9223)                     │
│  └─ WSL2 Ubuntu 24.04                        │
│       ├─ Hermes Agent                        │
│       ├─ OmniGraph-Vault (开发仓库)            │
│       └─ ~/.hermes/omonigraph-vault (运行时)   │
└──────────────────────────────────────────────┘
```

### 4.2 SSH 连接配置

Claude Code 运行在远程服务器上，通过 SSH 进入此 WSL 实例执行代码和测试。

**前提条件:**

1. WSL2 已启用 SSH server: `sudo apt install openssh-server && sudo service ssh start`
2. 端口转发 (Windows → WSL):
   ```powershell
   # 在 Windows PowerShell (管理员) 中运行:
   netsh interface portproxy add v4tov4 listenport=2222 connectaddress=127.0.0.1 connectport=22
   ```
3. SSH 密钥已配置: Claude Code 的公钥写入 `~/.ssh/authorized_keys`

**SSH 连接命令 (Claude Code 使用):**

```bash
ssh -p 2222 sztimhdd@<windows-host-ip> "cd ~/OmniGraph-Vault && <command>"
```

### 4.3 验证命令清单

Claude Code 应通过 SSH 运行以下验证序列：

```bash
# === Phase 5 验证门 ===

# Gate 1: 依赖检查
ssh ... "cd ~/OmniGraph-Vault && venv/bin/pip list | grep -E 'feedparser|langdetect'"

# Gate 2: RSS OPML 解析
ssh ... "cd ~/OmniGraph-Vault && venv/bin/python -c '
from enrichment.rss_fetch import parse_opml
feeds = parse_opml(\"data/karpathy_hn_2025.opml\")
assert len(feeds) >= 90, f\"Expected >=90 feeds, got {len(feeds)}\"
print(f\"OK: {len(feeds)} feeds parsed\")
'"

# Gate 3: RSS 抓取 (前 5 个 feed, 干跑)
ssh ... "cd ~/OmniGraph-Vault && venv/bin/python enrichment/rss_fetch.py --max-feeds 5 --dry-run"

# Gate 4: SQLite Schema 迁移
ssh ... "cd ~/OmniGraph-Vault && venv/bin/python batch_scan_kol.py --days-back 0"
# 验证新表存在
ssh ... "cd ~/OmniGraph-Vault && venv/bin/python -c '
import sqlite3; conn = sqlite3.connect(\"data/kol_scan.db\")
tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='\\''table'\\''\")]
assert \"rss_feeds\" in tables
assert \"rss_articles\" in tables
assert \"rss_classifications\" in tables
print(\"OK: RSS tables created\")
'"

# Gate 5: RSS 分类 (单篇文章, 干跑)
ssh ... "cd ~/OmniGraph-Vault && venv/bin/python enrichment/rss_classify.py --article-id 1 --dry-run"

# Gate 6: 日推生成 (干跑)
ssh ... "cd ~/OmniGraph-Vault && venv/bin/python enrichment/daily_digest.py --date 2026-04-27 --dry-run"

# Gate 7: 全流程集成测试 (模拟今日数据)
ssh ... "cd ~/OmniGraph-Vault && venv/bin/python enrichment/orchestrate_daily.py --dry-run --skip-scan"
```

### 4.4 注意事项

1. **CDP 浏览器依赖:** RSS 路径不依赖 CDP (纯 HTTP fetch)，可以在 Claude Code SSH 中独立测试。
   KOL 路径依赖 CDP，Claude Code 远程测试时需确认 Edge CDP 端口可达。

2. **API 密钥:** Claude Code 通过 SSH 执行的命令继承 WSL 的 `.env` 环境。
   确保 `~/.hermes/.env` 中的 `GEMINI_API_KEY`, `DEEPSEEK_API_KEY` 在 SSH session 中可用：
   ```bash
   ssh ... "source ~/.hermes/.env && cd ~/OmniGraph-Vault && venv/bin/python ..."
   ```

3. **Python 环境:** 所有命令使用 `~/OmniGraph-Vault/venv/bin/python`，确保依赖一致。

4. **干跑模式:** `--dry-run` 标志应在所有 Phase 5 模块中实现，允许 Claude Code 全流程验证而不写入生产数据。

---

## 5. 验证策略

### 5.1 单元测试

| 模块 | 测试文件 | 覆盖内容 |
|------|----------|----------|
| rss_fetch | `tests/unit/test_rss_fetch.py` | OPML 解析, feed URL 提取, 去重逻辑 |
| rss_classify | `tests/unit/test_rss_classify.py` | LLM prompt 构造, depth_score 解析, 排除规则 |
| daily_digest | `tests/unit/test_daily_digest.py` | 选文排序, Markdown 渲染, 截断逻辑 |
| orchestrate_daily | `tests/unit/test_orchestrate.py` | 状态机流转, 幂等性, 失败恢复 |

### 5.2 集成测试 (Claude Code 远程)

| Gate | 内容 | 阻塞级 |
|------|------|--------|
| G1 | OPML 解析 ≥ 90 feeds | 🔴 阻塞 |
| G2 | RSS 前 5 feed 抓取成功 | 🔴 阻塞 |
| G3 | SQLite schema 迁移幂等 | 🔴 阻塞 |
| G4 | 单篇 RSS 分类 depth_score 合理 | 🟡 非阻塞 |
| G5 | 干跑全流程不崩溃 | 🔴 阻塞 |

### 5.3 验收标准 (Hermes 本地)

| 标准 | 验证方法 |
|------|----------|
| RSS 92 feeds 全部可解析 | `SELECT COUNT(DISTINCT feed_id) FROM rss_articles` ≥ 80% |
| 深度文章过滤有效 | 日推中 depth_score ≥ 2 的文章，人工抽检 5 篇确认 |
| 英文 RSS 增厚有效 | 抽检 3 篇英文 RSS → 好问返回中文综述 + 知乎原答案 URL 有效 |
| 全流程无人值守 | 连续 3 天观测 Telegram 日推正常送达 |
| 图数据增长 | LightRAG `list_entities.py` 日新增 ≥ 10 entities |

---

## 6. 新增依赖

```
# requirements.txt 新增
feedparser>=6.0        # RSS/Atom 解析
langdetect>=1.0        # 语言检测 (RSS 预筛选)
```

---

## 7. 风险与缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| RSS feed 失效 (404/域名过期) | 20% | 单 feed 容错 + `error_count` 跟踪，连续 7 天失败 → 自动禁用 |
| RSS 内容非技术 (个人随笔/政治) | 15% | LLM 分类器 + excluded 标记 |
| 92 RSS 全量抓取超时 (3-5 min) | 低 | 2s 间隔 + feedparser 超时 30s/feed |
| 好问对英文技术问题的中文综述质量不足 | 15% | 技术概念语言无关；如质量持续差，RSS 可回退到跳过增厚 |
| 日推撞上微信反爬导致 KOL 侧缺数据 | 30% | KOL 和 RSS 独立抓取，一侧失败不影响另一侧 |

---

## 8. 实施计划

### Wave 0: Embedding 模型迁移 + 302 篇 catch-up (2 plans) — **必须最先做**

> **Superseded by Phase 5 D-10 (2026-04-28):** Ingestion filter is keyword match AND depth_score ≥ 2, NOT all 302 articles. Current keyword scope: `{openclaw, hermes, agent, harness}`.

| Plan | 内容 | 产出 |
|------|------|------|
| 05-00 | gemini-embedding-2 spike + embedding_func 扩展 + 18 docs re-embed | `docs/spikes/gemini-embedding-2-contract.md` go/no-go，新 `gemini_embed` 支持 image bytes，18 docs 重嵌完成 |
| 05-00b | 302 篇 KOL 存量 catch-up (新 pipeline) | LightRAG 图谱含全部 KOL 历史文章，benchmark 报告（中文检索不退化 + 跨模态命中）通过 |

**阻塞后续 Wave**: Wave 1 之后的所有 RSS/ingest 代码都假设新的 embedding 基座已就位。Wave 0 未通过 success criteria 前不启动 Wave 1。

### Wave 1: RSS 基础设施 (2-3 plans)

| Plan | 内容 | 产出 |
|------|------|------|
| 05-01 | RSS schema 迁移 + OPML 缓存 | `rss_feeds` `rss_articles` 表，92 feeds 注册 |
| 05-02 | `rss_fetch.py` feed 抓取器 | 可运行的 RSS 抓取 + 去重 |
| 05-03 | `rss_classify.py` 分类器 | 复用 batch_classify 逻辑，适配 RSS |

### Wave 2: 管道集成 (2 plans)

| Plan | 内容 | 产出 |
|------|------|------|
| 05-04 | `orchestrate_daily.py` 编排器 | 全流程状态机 + 干跑模式 |
| 05-05 | `daily_digest.py` 日推生成器 | Telegram Markdown 推送 |

### Wave 3: Cron + 验证 (1 plan)

| Plan | 内容 | 产出 |
|------|------|------|
| 05-06 | Cron 部署 + 端到端验证 | 全部 cron job 就绪，3 天观测 |

---

## 9. 当前 KOL 分类器缺口

`batch_classify_kol.py` 已实现但 `classifications` 表为空。Phase 5 需要先让 KOL 分类跑起来，再把 RSS 分类接上去。

**快速启动分类:**

```bash
# 对过去 7 天未分类的文章批量分类
python batch_classify_kol.py --topic "Agent" --topic "LLM" --topic "RAG" \
  --topic "NLP" --topic "CV" --min-depth 2 --days-back 7
```

---

*文档版本 1.0 — 2026-04-27*
