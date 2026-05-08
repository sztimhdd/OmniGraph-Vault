# RSS Ingest Flow — 现状梳理 (as of 2026-05-08)

## 背景与约束(从 prompt 复述)

OmniGraph-Vault 刚完成 v3.5-Ingest-Refactor 的 ir-1 (Layer 1 真实 Gemini Flash Lite) + ir-2 (Layer 2 真实 DeepSeek)。两层 LLM filter 已经替代旧的 `_classify_full_body` 路径(KOL 分支)。当前在 ir-4 准备阶段:RSS 集成 + cleanup。

架构原则(用户 confirm): RSS 与 KOL 是双表设计 (`articles` + `rss_articles`),但所有下游逻辑必须复用,不分岔 — `batch_ingest_from_spider.py` 应该 iterate 两张表都用同一份 Layer 1 / Layer 2 / scrape / ingest 逻辑。

报告基于纯阅读,零代码改动。所有结论标注 file:line 引用。

---

## Q1: enrichment/rss_ingest.py 是否使用 Layer 1/2

**Verdict: ❌ uses old path — 完全没有 import 或调用 lib/article_filter.py**

证据(`enrichment/rss_ingest.py:40-52` import 块):

```python
import image_pipeline
from config import BASE_DIR, RAG_WORKING_DIR
from lib import deepseek_model_complete
from lib.checkpoint import (...)
from lib.lightrag_embedding import embedding_func
from lib.scraper import scrape_url
```

注意没有 `from lib.article_filter import ...`。Grep `lib.article_filter` 在 `enrichment/rss_ingest.py` 整个文件零命中。

当前的 RSS 入库筛选机制(`enrichment/rss_ingest.py:225-234`)是 Phase 20 RIN-02 的"depth gate":

```python
# ----- Stage 02: classify gate (depth set by rss_classify; we just gate) -----
if not has_stage(article_hash, "classify"):
    depth = row.get("depth")
    if depth is None:
        logger.info("id=%s: depth NULL — rss_classify must run first; skipping", aid)
        return False
    if int(depth) < MIN_DEPTH_GATE:  # MIN_DEPTH_GATE = 2 at line 60
        logger.info("id=%s: depth=%s < %s gate; skipping", aid, depth, MIN_DEPTH_GATE)
        return False
```

也就是说 RSS 入库的 KEEP/REJECT 决策完全依赖 `rss_articles.depth`(由 `enrichment/rss_classify.py` 的旧 full-body LLM 写入)。**v3.5 的 Layer 1 / Layer 2 列对 RSS 入库路径毫无影响。** 即使 migration 006/007 给 `rss_articles` 加了 layer1_*/layer2_* 列(见 Q2),这些列在 RSS 入库逻辑里完全没人读。

时序印证:

- `enrichment/rss_ingest.py` 最后修改 `0ebd191` (Phase 20 RIN-01..06,2026-05-04 之前)
- `lib/article_filter.py` 创建于 ir-1 `cf79840` (2026-05-07) — pre-dates 假设成立

---

## Q2: migration 006/007 是不是双表覆盖

**Verdict: ✅ 双表 — 8 列 × 2 表 全部覆盖,both layer1_* 和 layer2_***

证据 — `migrations/006_layer1_columns.sql:19-27`:

```sql
ALTER TABLE articles      ADD COLUMN layer1_verdict        TEXT NULL;
ALTER TABLE articles      ADD COLUMN layer1_reason         TEXT NULL;
ALTER TABLE articles      ADD COLUMN layer1_at             TEXT NULL;
ALTER TABLE articles      ADD COLUMN layer1_prompt_version TEXT NULL;

ALTER TABLE rss_articles  ADD COLUMN layer1_verdict        TEXT NULL;
ALTER TABLE rss_articles  ADD COLUMN layer1_reason         TEXT NULL;
ALTER TABLE rss_articles  ADD COLUMN layer1_at             TEXT NULL;
ALTER TABLE rss_articles  ADD COLUMN layer1_prompt_version TEXT NULL;
```

证据 — `migrations/007_layer2_columns.sql:19-27`: 完全对称的 pattern(layer2_verdict / reason / at / prompt_version × 2 表)。

证据 — `.py` idempotent 版本 `migrations/006_layer1_columns.py:25` 和 `007_layer2_columns.py:25`:

```python
TABLES: tuple[str, ...] = ("articles", "rss_articles")
```

`lib/article_filter.py:618` + `:665` 也明确把双表 mapping 写入 persist 函数:

```python
table_for: dict[str, str] = {"wechat": "articles", "rss": "rss_articles"}
```

**结论**: schema 端已经完整支持双表。问题只在 producer-consumer 端 — Layer 1/2 的 rss persistence path 在 `lib/article_filter.py` 里有(`source='rss'` branch 写 rss_articles),但**生产代码里没有调用方传 source='rss' 的 ArticleMeta** — 见 Q7 说明。

---

## Q3: enrichment/rss_classify.py 现状

**Verdict: 🟡 脚本仍在,且仍被 orchestrate_daily 调用,但当前 cron 没有直接 fire 它**

证据 — 文件存在: `enrichment/rss_classify.py` (229 行)

证据 — git log:

```
882e322 feat(20-01): upgrade rss_classify to full-body multi-topic classify
d1c044d fix(quick-260504-lt2/enrichment/rss_classify): KOL_SCAN_DB_PATH env override
0fa9674 fix(rss_classify): add OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP env cap
e4b2932 feat(05-03): rss_classify.py with DeepSeek + Chinese-reason prompt
```

最近一次实质改动 `882e322` (Phase 20-01 — full-body multi-topic upgrade)。

Caller 检查:

1. `enrichment/orchestrate_daily.py:82-85`:
   ```python
   def step_2_classify_rss(dry_run: bool) -> StepResult:
       return _run(
           [str(PYTHON), "enrichment/rss_classify.py"], dry_run, critical=False
       )
   ```
   `step_2_classify_rss` 仍然在 9 步 pipeline 里(`enrichment/orchestrate_daily.py:274`)。

2. tests: `tests/unit/test_rss_classify_fullbody.py` 和 `tests/unit/test_rss_classify.py` 仍然存在。

3. **生产 cron**: 直接用 grep `.scratch/hermes_jobs_post_deploy.json` 找不到 `rss_classify` — 与 prompt 描述一致(`rss-classify` cron 已被删除)。

但是:**没有任何当前 active cron 触发 orchestrate_daily.py**。来自 cron snapshot 的 active jobs(见 Q6):

- `rss-fetch` (29c3facf5023): `run enrichment/rss_fetch.py` — 不调用 rss_classify
- `daily-ingest` (2b7a8bee53e0): `run batch_ingest_from_spider.py --from-db` — 不调用 rss_classify
- `daily-digest` (43e85ec247e5): `run enrichment/daily_digest.py` — 不调用 rss_classify

**结论**: rss_classify.py 物理上还在 + orchestrate_daily 仍 import 它,但生产 cron 链没有任何节点会 fire orchestrate_daily,所以 rss_classify **实际上是孤儿**。结果是 rss_articles 表的 depth 列对所有新 RSS 行永远是 NULL → rss_ingest 永远 skip(per Q1 depth gate)。

这就是 1369 篇 0503 backlog 累积的根本原因 — RSS fetch 在写,classify 没人触发,ingest 被 depth=NULL 卡住。 (need verification — 实际行数和 NULL 比例需 SSH 进 Hermes DB 验证;此处仅基于代码路径推断。)

---

## Q6: rss-fetch 下游 cron 接力

**Verdict: ❌ 无接力 — 当前 cron 链有 RSS 入口 (rss-fetch) 但完全没有 RSS 入库 path**

完整 active cron 列表(`.scratch/hermes_jobs_post_deploy.json`,7 个 jobs,5 个 enabled):

| ID | Name | Schedule | Prompt | RSS related? |
|---|---|---|---|---|
| `df7dc3fa0390` | 每日KOL扫描 | `0 8 * * *` | 执行每日 KOL 扫描 (skill omnigraph_scan_kol) | KOL only |
| `e7afccd9931b` | KOL扫描前健康检查 | `55 7 * * *` | 健康检查 (CDP / WeChat session) | KOL only |
| `9a917f7209eb` | batch-watchdog | every 10m | watchdog (PAUSED — `enabled: false`) | KOL only |
| `29c3facf5023` | **rss-fetch** | `0 6 * * *` | `run enrichment/rss_fetch.py` | **RSS — UPSTREAM** |
| `2b7a8bee53e0` | **daily-ingest** | `0 9 * * *` | `run batch_ingest_from_spider.py --from-db` | **见下** |
| `43e85ec247e5` | daily-digest | `30 9 * * *` | `run enrichment/daily_digest.py` | digest only |
| `d6421e78107a` | vertex-probe-monthly | `0 8 1 * *` | vertex 健康探针 | unrelated |

**关键空缺**: `rss-fetch` 06:00 写入 rss_articles 后,只有两个潜在下游 cron:

1. `daily-ingest` (`batch_ingest_from_spider.py --from-db`) — 但 `_build_topic_filter_query` (见 Q7 详述) 只 SELECT FROM `articles`,**完全不碰 `rss_articles`**。
2. `daily-digest` — 只读最近被 ingest 的内容生成 digest,不做入库。

也就是说 rss-fetch → rss_articles 是 sink,目前没有人从 sink 取。

CLAUDE.md 中提到的"`rss-classify` cron 已被删除 (per HERMES jobs.json snapshot)" 的描述与 snapshot 一致 — **但删除时没有用任何替代 cron 接力 rss_classify 的工作,这是 ir-4 必须修复的核心 gap**。

---

## Q7: rss_ingest.py 跟 ingest_wechat.py / batch_ingest_from_spider.py 的关系

### 调用关系图(实际现状)

```
[CRON]
  ├── 06:00 rss-fetch ──> enrichment/rss_fetch.py ──> rss_articles (WRITE)
  │                                                    │
  │                                                    └─ ❌ NO DOWNSTREAM CRON
  │                                                       (1369 articles backlog,
  │                                                        depth=NULL forever)
  │
  └── 09:00 daily-ingest ──> batch_ingest_from_spider.py --from-db
                              │
                              ├── _build_topic_filter_query(topics)
                              │   └── SELECT FROM articles a JOIN accounts ...
                              │       (只 query KOL articles 表 — line 1327-1335)
                              │
                              ├── layer1_pre_filter()  ──> articles.layer1_*
                              ├── _classify_full_body() — DEAD CODE per ir-1 wiring
                              ├── pre-scrape (lib.scraper.scrape_url)
                              └── layer2_full_body_score()  ──> articles.layer2_*
                                  └── rag.ainsert (LightRAG)


[未被触发,但代码仍然存在 / orchestrate_daily 内置]
  enrichment/orchestrate_daily.py
    ├── step_1_fetch_rss   → enrichment/rss_fetch.py
    ├── step_2_classify_rss → enrichment/rss_classify.py (full-body LLM, 写 rss_articles.depth)
    ├── step_3..5          → KOL 分支
    ├── step_6             → run_enrich_for_id.py (KOL only per D-07)
    ├── step_7_ingest_all  → BOTH:
    │                          [str(PYTHON), "batch_ingest_from_spider.py", "--from-db", "--topic-filter", ...]
    │                          [str(PYTHON), "enrichment/rss_ingest.py"]   (line 207)
    ├── step_8             → daily_digest.py
    └── step_9             → telegram alert

  enrichment/rss_ingest.py (5-stage pipeline, fully self-contained):
    ├── stage 01 scrape    → lib.scraper.scrape_url  (复用)
    ├── stage 02 classify gate → reads rss_articles.depth (老路径 — 由 rss_classify 写)
    ├── stage 03 image_download → image_pipeline (复用)
    ├── stage 04 text_ingest → rag.ainsert (复用 LightRAG instance)
    └── stage 05 vision_worker → image_pipeline.describe_images (复用)
```

### 关键发现

1. **rss_ingest.py 不是 batch_ingest_from_spider.py 的子 module**。它是完全独立的 entry point(`__main__` block at line 433-434),自己 init LightRAG (`enrichment/rss_ingest.py:365-374`),自己 init DB connection,自己跑 5 stage pipeline。

2. **`batch_ingest_from_spider.py` 的 `--from-db` 模式当前只 query `articles` 表,不 query 双表**:

   `batch_ingest_from_spider.py:1326-1335`:
   ```python
   sql = """
       SELECT a.id, a.title, a.url, acc.name, a.body, a.digest
       FROM articles a
       JOIN accounts acc ON a.account_id = acc.id
       WHERE a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')
         AND (a.layer1_verdict IS NULL OR a.layer1_prompt_version IS NOT ?)
       ORDER BY a.id
   """
   ```
   后面的 ArticleMeta 构造也写死 `source="wechat"` (line 1416)。

3. **orchestrate_daily.step_7 调用 rss_ingest 是 hardcoded subprocess 调用**(`enrichment/orchestrate_daily.py:207-210`):
   ```python
   rss_cmd = [str(PYTHON), "enrichment/rss_ingest.py"]
   if max_rss is not None:
       rss_cmd += ["--max-articles", str(max_rss)]
   rss_r = _run(rss_cmd, dry_run, critical=False)
   ```
   这与"双表共享 Layer 1/2 逻辑"的架构原则冲突 — rss_ingest 是独立 pipeline,只用 depth gate,根本不跑 Layer 1/2。

4. **`_classify_full_body` (`batch_ingest_from_spider.py:956`) 仍存在但是 dead code**:被 `f1a963b` "bypass _classify_full_body — wire to placeholder Layer 1/2" 绕开。整个 `ingest_from_db` async 函数(line 1338+)的主循环不再调用它,只有单测 (`tests/unit/test_*.py`) 还在 import 它。注释 line 1679 提到 "handled inside _classify_full_body" 是 stale 注释,实际 path 是 `lib.scraper.scrape_url + Layer 2 batch`。

---

## ir-4 工作量预判

| 工作 | 是否需要 | 理由 |
|---|---|---|
| **重写 `_build_topic_filter_query` 双表 UNION** | 必须 | 当前 query 只 hit `articles`,RSS 流量 0% 进入 Layer 1/2 |
| **构造 `ArticleMeta(source='rss')` 候选** | 必须 | `lib.article_filter` 已经有 source 字段 + table_for mapping;调用方目前只传 wechat |
| **删除/退役 `enrichment/rss_classify.py`** | 是 | 一旦 RSS 走 Layer 1/2,`rss_articles.depth` 就不再是 KEEP/REJECT 判据。脚本可降级为 stub 或删除 |
| **删除 `enrichment/rss_ingest.py` Stage 02 depth gate**(或重写整个 rss_ingest) | 是,但取决于策略 | 选项 A: 删除 rss_ingest.py,把 RSS 流量全部 route 进 batch_ingest_from_spider。选项 B: 改 rss_ingest.py 的 depth gate 为 layer2_verdict gate |
| **删除/退役 orchestrate_daily.step_2_classify_rss** | 是 | 已无 rss_classify.py 在新流程中的角色 |
| **新增/修改 cron**: 让 daily-ingest 处理 rss_articles | 必须 | 当前 daily-ingest 9:00 跑 `--from-db` 但只看 KOL。需要改 cron prompt 或改 `--from-db` 实现使其 iterate 双表 |
| **migration 008 (cleanup)**(可选) | 取决于决策 | 如果 ir-4 决定 rss_articles 上的 `depth` / `topics` / `classify_rationale` 列也成为 dead column,可以加一个 migration 标记 deprecated(或直接保留,让 `rss_classify` 写入 stop) |
| **测试更新**: `test_rss_ingest_5stage.py` / `test_rss_classify_*.py` / `test_orchestrate_daily.py` | 必须 | 6 个相关 test 文件,根据策略选择需要重写或删除 |
| **CLAUDE.md / `.planning/PROJECT.md` 更新 RSS flow 说明** | 必须 | 保证下次 forensics 不会被 stale doc 误导 |

**预估**: **重等级**(heavy)。

理由:
- 涉及**至少 5 个 production 文件**修改(`batch_ingest_from_spider.py` query + `ArticleMeta` 构造 / `rss_ingest.py` 行为 / `orchestrate_daily.py` step 顺序 / `rss_classify.py` 退役 / 数据 backlog 处理)
- 涉及**1 个生产 cron**调整(daily-ingest 是否扩到双表,或新增 cron)
- 涉及**双表 1369 条 backlog 数据的处理**(是 truncate-and-rerun 还是渐进式 catch-up,涉及 LLM 配额)
- 涉及**6 个测试文件**的重写或删除
- 是 first-time 的"两条独立 pipeline 收敛为一条"的 refactor,比单表的字段调整复杂得多

**对比基准**: ir-1 (Layer 1) + ir-2 (Layer 2) 各自是中等级(只动 KOL 分支的 query/loop + 一份 lib + 一份 migration + 测试)。ir-4 的工作量约等于 ir-1 + ir-2 之和。

---

## 1369 篇 0503 backlog

(空着,user 在并行 SSH 查 Hermes 上的实际数据)

预期:`SELECT COUNT(*) FROM rss_articles WHERE depth IS NULL` 应该 ≈ 1369。`SELECT MIN(fetched_at), MAX(fetched_at) FROM rss_articles WHERE depth IS NULL` 应该是 2026-05-03 之后(rss-classify cron 删除后所有 fetch 进来的行都没有 depth)。

---

## 给 ir-4 plan-phase 的输入

1. **核心决策点 A — 双表收敛策略**:
   - 选项 1(推荐,符合用户原则): 把 `enrichment/rss_ingest.py` 完全删除,RSS 流量全部 route 到 `batch_ingest_from_spider.py --from-db`。修改 `_build_topic_filter_query` 用 `UNION ALL` 同时 select `articles` + `rss_articles`,在 ArticleMeta 构造时根据来源传 `source='wechat'` / `source='rss'`,`lib.article_filter.persist_layer*_verdicts` 已经支持双表 dispatch。
   - 选项 2: 保留 `rss_ingest.py` 但改其 Stage 02 改用 `layer1_verdict='candidate' AND layer2_verdict='ok'`,然后另起 cron 触发 Layer 1/2 (单独跑一遍 `lib.article_filter` 处理 rss_articles)。这违反"不分岔"原则。
   - **建议: 选项 1**。

2. **核心决策点 B — `rss_classify.py` 处置**: 选项 1 下 rss_classify.py 立刻就是 dead code(它写 `depth` 但没人读)。建议直接退役 → `git rm enrichment/rss_classify.py` + 删除 `enrichment/orchestrate_daily.py:82-85` 的 `step_2_classify_rss` + 删除两个 test 文件(`test_rss_classify*.py`)。

3. **必改文件清单**:
   - `batch_ingest_from_spider.py:1306-1335` — `_build_topic_filter_query` 改双表 UNION ALL,SELECT 增加 source 字段,JOIN/anti-join 也要照顾两个表(注意 `ingestions.article_id` 当前是 articles.id 的 FK,RSS 需要新表或扩 schema)
   - `batch_ingest_from_spider.py:1413-1421` — `ArticleMeta` 构造从 row 拿 source(从 UNION ALL 加的列拿),不再 hardcode `"wechat"`
   - `batch_ingest_from_spider.py:1747-1750` — `layer2_queue` 入队时也要记录 source(目前 row tuple 6 元组,需扩展)
   - `enrichment/orchestrate_daily.py:182-213` — `step_7_ingest_all` 删除 `rss_cmd` subprocess,只保留 `kol_cmd`(此时其实是 unified ingest)
   - `enrichment/orchestrate_daily.py:82-85` — 删除 `step_2_classify_rss`
   - 删除 `enrichment/rss_ingest.py`(选项 1)或大改(选项 2)
   - 删除 `enrichment/rss_classify.py`(选项 1)
   - 测试: 删 `test_rss_ingest_5stage.py` / `test_rss_classify*.py`;新增 `test_from_db_dual_source.py` 验证双表 candidate query

4. **需要新增的 schema 决策**: `ingestions` 表当前 schema 是 `article_id INTEGER NOT NULL REFERENCES articles(id)` (`batch_ingest_from_spider.py:1370-1377`)。RSS 文章 ID 落到这张表会**违反外键约束**。需要 migration 008:
   - 选项 a: 新增 `source TEXT NOT NULL CHECK(source IN ('wechat','rss'))` 列 + 把 UNIQUE 改成 `(source, article_id)` 复合键,FK 从 `REFERENCES articles(id)` 改为应用层校验
   - 选项 b: 新增独立 `rss_ingestions` 表
   - 选项 a 更符合"不分岔"原则。

5. **cron 端**: `daily-ingest` cron 的 prompt 当前是 `run batch_ingest_from_spider.py --from-db`。如果 ir-4 改完 `--from-db` 是双表的,cron prompt **不需要改**(但建议 `daily-ingest` 名字保留,加 last-run 检查或 `--max-articles` flag 用来控制 backlog 消化速度)。

6. **Backlog 数据处理**:1369 篇 RSS 历史文章在新流程下是 layer1_verdict=NULL 的候选 — 会被新双表 query 命中,但同时跑一次 Layer 1 batch (1369 / 30 = 46 batches × 8s = 6 分钟 Gemini 调用) + ~30% 进 Layer 2 + 10-20% 进 ingest,需要 SiliconFlow 余额评估(per CLAUDE.md ¥0.0013/image × est. images)。建议 ir-4 提供一个 dry-run mode 让 user 先看清楚数量级,再决定是 throttle (`--max-articles 50`) 还是一次跑完。

---

## Unknown / Need Verification

- 1369 篇 backlog 的精确数字: 需要 SSH 进 Hermes 跑 `SELECT COUNT(*) FROM rss_articles WHERE depth IS NULL` 验证。本报告基于代码路径推断 backlog 现象,数字假设 1369 是 user 提供。
- `rss_articles` 表 schema 是否还有其他被新流程 deprecate 的列(如 `topics` JSON、`classify_rationale`):本报告未列举。需要查 `enrichment/rss_schema.py` + `migrations/` 链确认。
- `ingestions` 表当前是否有 RSS 行(理论上不应有,但若有 leakage,迁移会更复杂):需要 SSH 验证 `SELECT * FROM ingestions LIMIT 5`。
- `daily_digest.py` 是否当前会读 `rss_articles`:本报告未深入读 daily_digest.py。如果它已经读双表,ir-4 不需要动它;如果只读 articles,需要同步扩。
- "RSS 数据 reach Hermes via 1 cron"(`rss-fetch` 06:00):该 cron 的 last_status 是 "ok",`completed: 2`,但 `created_at: 2026-05-03`,意味着只跑过 2 次 — 而 backlog 是 1369 篇。说明 rss_fetch 一次跑能塞几百行,这个数学上能对上,**但需要 verification — completed=2 vs 1369 行的关系不直观**。
