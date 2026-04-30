# OmniGraph-Vault Batch Ingestion — 完整诊断报告

> **时间范围**: 2026-04-29 23:00 ~ 2026-04-30 22:33 (北京时间)
> **最终更新**: 2026-04-30 23:30
> **目标受众**: Claude Code (结构化分析)
> **测试素材**: `test/fixtures/gpt55_article/` — 全文 + 28 张图，可本地 e2e 复现

---

## 一、时间线与完成进度

### Phase 07-04 收尾 | 04-29 23:00–23:30

| 时间 | 提交 | 内容 |
|---|---|---|
| 23:11 | `b705a14` | refactor: migrate tests to lib/ |
| 23:12 | `4676fb3` | feat: dual-host SKILL.md frontmatter |
| 23:13 | `19ff273` | docs: deploy story — .env.template, Deploy.md |
| 23:14 | `f4fb4e2` | docs: RUNBOOK for manual Hermes-side execution |
| 23:15 | `1f19675` | refactor: migrate extract_entities to lib.generate_sync |
| 23:16 | `8b10e2a` | refactor: SWEEPER — delete config.py D-11 shims |
| 23:20 | `46c2301` | docs: Wave 4 cleanup plan |
| 23:27 | `836829b` | docs: Phase 7 closed — verification 17/17, 109/109 tests |

**完成**: Phase 7 (模型密钥管理) 正式关闭 — 7/8 任务完成。

---

### 凌晨架构重构 | 04-30 01:25–07:10

| 时间 | 提交 | 内容 |
|---|---|---|
| 01:25 | `69d6b88` | docs: CLI gotchas — topic-filter 大小写 + SLEEP 基准 |
| 04:32 | `d5e86c5` | docs: **架构评审** — 子进程根因分析 + 进程内方案 |
| 06:57 | `1048896` | docs: 重构计划 Hermes 反馈 |
| 06:58 | `f670a6b` | refactor: **参数化 rag** — ingest_wechat 接受外部实例 |
| 06:58 | `e2a3369` | refactor: **extract_entities Gemini→DeepSeek** (R4) |
| 07:01 | `b4b39d6` | refactor: **进程内 batch ingest** + KeyboardInterrupt 安全 |
| 07:03 | `7a032bd` | test: RPD floor 回归守卫 |

**核心改动**:
- `batch_ingest_from_spider.py`: 子进程 → asyncio 进程内，消除每篇文章 15-30s LightRAG 初始化开销
- `ingest_wechat.py`: extract_entities 从 Gemini 切到 DeepSeek，解除 Gemini 配额耦合
- `lib/models.py`: 新增 `RATE_LIMITS_RPD` 字典 + `PRODUCTION_RPD_FLOOR=250` 防线

---

### 上午诊断修复 | 04-30 10:52–11:30

| 时间 | 提交 | 内容 |
|---|---|---|
| 10:52 | `e36140a` | docs: **Embedding 429 死亡螺旋诊断** |
| 10:59 | `0564ae2` | fix: **双键 429 时 5 分钟冷却** |
| 11:17 | `af8f82b` | fix: 图片过滤 <150px — 50% 是表情包 |
| 11:19 | `3469833` | fix: 图片过滤提到 300px — 21.4% <300px 是表情 |
| 11:30 | `f5166ec` | feat: **Vision Gemini→GLM-4.5V (OpenRouter)** |

**核心改动**:
- `image_pipeline.py`: 完全重写 `describe_images()`，3 级 Vision fallback
- `lib/lightrag_embedding.py`: 双键都 429 时 5 分钟冷却
- 环境变量 `VISION_PROVIDER` 控制: `auto|gemini|siliconflow|openrouter`

---

### 傍晚自动化执行 | 04-30 18:57–19:00

| 时间 | Cron Job | 结果 |
|---|---|---|
| 18:57 | KOL 健康检查 (`e7afccd9931b`) | ✅ TOKEN=1466571383, _clck: g5m→g5n, _clsk 刷新 |
| 19:00 | KOL 全量扫描 (`df7dc3fa0390`) | ✅ 22/53 账号, 35 篇新文章 |

扫描产出: 知识库总计 357 篇 (4/27 冷启动 268 篇 + 3 天增量)

---

### 晚间 Batch 尝试 | 04-30 19:32–23:30

| 时间 | 事件 | 详情 |
|---|---|---|
| 19:32 | wave0c **run 1** | `VISION_PROVIDER=gemini`, 263 篇 → Gemini 503 → 中断 |
| 19:56 | batch-watchdog 创建 | 每 10 分钟检查 |
| 21:19 | 修改 batch_ingest | **timeout: 600s → 1200s** |
| 21:20 | wave0c **run 2** | `VISION_PROVIDER=siliconflow`, 263 篇 |
| 22:33 | 手动终止 run 2 | 4/263, 1 成功 3 超时 |
| 22:45 | **单篇 benchmark** | GPT-5.5 文章, `LLM_TIMEOUT=600` |
| 23:10 | 手动终止 benchmark | 1882s 未完成 |
| 23:20 | 抓取测试素材 | 全文 + 28 张图, push 到 GitHub |
| 23:30 | 本报告最终更新 | 整合所有发现 |

---

## 二、发现的问题（共 7 类）

### 问题 1: 分类器误判 — digest=N/A 导致深度幻觉 ⚠️ 新发现

- **现象**: GPT-5.5 文章被分类为 depth=3, reason="deep technical paper on multimodal training"
- **实际**: 模型发布新闻稿 + benchmark 图表堆砌，属于 depth=1 的浅层资讯
- **根因**: WeChat digest 为 N/A，分类器仅靠标题 ("GPT-5.5""碾压Opus 4.7") 脑补出深度内容
- **DB 证据**:
  ```
  Title: GPT-5.5来了！全榜第一碾压Opus 4.7，OpenAI今夜雪耻
  Digest: N/A
  Depth: 3, Reason: "deep technical paper on multimodal training and LLM architecture"
  ```
- **影响**: 这类文章被高估深度后进入 ingest 队列，56 张 benchmark 图表全走 Vision，浪费 500s+

**结论: 必须全文分类。** digest 不可靠（N/A、截断、广告文均有发现）。

---

### 问题 2: 图片尺寸过滤 Bug — AND 逻辑过松 ⚠️ 新发现

- **当前逻辑**: `w < 300 and h < 300` — 两个维度**都** <300px 才过滤
- **问题**: 100×800 的窄横幅、800×50 的细分割线全部通过
- **实测**: 改用 `min(w, h) < 300` 后，同一篇文章从 39 张→28 张（多过滤 28%）
- **位置**: `ingest_wechat.py:641`
- **修复**: `if w < _MIN_IMG_DIM and h < _MIN_IMG_DIM` → `if min(w, h) < _MIN_IMG_DIM`

---

### 问题 3: LightRAG 共享实例状态泄漏 ⚠️ 新发现

- **现象**: 单篇 benchmark 启动后，先处理了 11 chunks 的 Hermes 生态系统实体（MEMORY.md, USER.md, Skills...），再处理 GPT-5.5 自己的 15 chunks
- **根因**: `get_rag()` 返回共享 LightRAG 实例，上次 wave0c_run2 的超时文章留下了 39 个 buffered entities
- **影响**: 每次重启都要"还债" ~300s，且越积越多
- **修复**: 每次 batch 跑完或中断后，清除 LightRAG 的异步缓冲队列

---

### 问题 4: Gemini Embedding 双键 429 耗尽

- **现象**: 361 次 entity merge 触发大量嵌入调用 → 双键同时达到 RPD 上限
- **修复**: 5 分钟全局冷却期 (`lib/lightrag_embedding.py`)
- **残留风险**: 冷却期内 Gemini 仍在限流，冷却后的第一波请求仍可能 429

---

### 问题 5: LightRAG LLM func 超时不可控

- **位置**: `lightrag/lightrag.py` — `priority_limit_async_func_call`
- **当前配置**: `llm_timeout=180s`, health_check=375s
- **问题**: DeepSeek 单个 chunk 调用可达 800s+，health check 在 375s 杀掉 → `HealthCheckTimeoutError`
- **实测**: `LLM_TIMEOUT=600` 后此问题缓解，但整体时间仍不可接受

---

### 问题 6: inter-image sleep 纯浪费

- **当前**: `_DESCRIBE_INTER_IMAGE_SLEEP_SECS = 2`
- **SiliconFlow 无 RPM 限制**，2s 完全是保守值
- **实测**: 28 张图 × 2s = 56s 纯等待，本可归零

---

### 问题 7: 图片处理与正文提取串行耦合

- **当前**: 下载图片 → Vision → LightRAG 提取 (串行)
- **问题**: Vision 阶段吃掉 50%+ 时间，正文提取在等
- **方向**: 正文先入 LightRAG，图片异步后补

---

## 三、进行的修改汇总

### 代码层面

| 文件 | 改动 | 影响 |
|---|---|---|
| `batch_ingest_from_spider.py` | 子进程→进程内, timeout 600→1200 | 消除初始化开销，但超时仍不足 |
| `ingest_wechat.py` | rag 参数化, extract_entities→DeepSeek | 解除 Gemini LLM 配额耦合 |
| `image_pipeline.py` | 完全重写, 3 级 Vision fallback | 摆脱 Gemini 500 RPD 天花板 |
| `lib/models.py` | RPD floor 防线 + 常量字典 | 防止 flash-lite(20 RPD) 误用 |
| `lib/lightrag_embedding.py` | 双键 429 → 5min 冷却 | 消除死亡螺旋 |
| `test/fixtures/gpt55_article/` | **测试素材** | 全文+28图, 可本地 e2e |

### 配置层面

| 配置项 | 旧值 | 新值 | 位置 |
|---|---|---|---|
| 单篇 timeout | 600s | 1200s | `batch_ingest_from_spider.py:90` |
| 图片最小尺寸 | 无 → 150px → 300px | **需改为 `min(w,h) < 300`** | `ingest_wechat.py:636-641` |
| Vision 提供商 | Gemini only | Gemini→SiliconFlow→OpenRouter | `VISION_PROVIDER` env |
| WeChat TOKEN | 过期 | 1466571383 | `kol_config.py` |
| Embedding 429 冷却 | 无 | 300s | `lib/lightrag_embedding.py` |
| LightRAG LLM timeout | 180s | 600s | `LLM_TIMEOUT` env |
| inter-image sleep | 4s | 2s | **建议 → 0s** |
| 分类策略 | 标题+摘要 | **→ 全文分类** | `batch_ingest_from_spider.py` |

---

## 四、单篇 Benchmark — GPT-5.5 文章实测

> **测试时间**: 2026-04-30 12:39 UTC-3  
> **文章**: [AINLP] GPT-5.5来了！全榜第一碾压Opus 4.7，OpenAI今夜雪耻  
> **配置**: `LLM_TIMEOUT=600`, `VISION_PROVIDER=siliconflow`  
> **结果**: 运行 **1882s (31.4 分钟)** 后被手动终止，**未完成**

### 文章画像

| 指标 | 旧过滤 (AND) | 新过滤 (min) | 说明 |
|---|---|---|---|
| 正文大小 | 105,418 bytes | 4,574 chars | HTML→text 提取 |
| 原始图片数 | 78 | 39 | 两次抓取数量不同(动态加载) |
| 过滤后图片 | **56** | **28** | `min(w,h)>=300` 多滤掉 50% |
| LightRAG 分块 | 15 chunks | — | 第 2 轮（第 1 轮 11 chunks 是历史残留） |
| 合并操作 | **361 次** | — | entity merge |
| 实际内容 | — | 模型发布新闻稿 + benchmark 图表 | **depth=1，不应 ingest** |

### 阶段耗时估算

| 阶段 | 耗时 | 占比 | 说明 |
|---|---|---|---|
| UA 抓取 | ~1s | <1% | HTTP 200 |
| 图片下载+Vision (56张旧/28张新) | **~500-600s** | **30%** | 含 112s inter-image sleep 纯浪费 |
| LightRAG 历史缓冲回放 | ~300s | 16% | 上次 batch 残留 |
| LightRAG chunk 提取 | ~400s | 21% | DeepSeek LLM |
| LightRAG 合并(361 merges) | ~400s | 21% | 含 Embedding timeout 重试 |
| Embedding 嵌入 | **卡住** | — | Gemini 双键 429 耗尽 |

### 遇到的错误

| 错误 | 次数 | 详情 |
|---|---|---|
| Embedding worker timeout (60s) | 2 | entity upsert 失败重试 |
| Gemini 双键 429 耗尽 | 1 | `All 2 Gemini keys exhausted` |
| LLM 格式错误 | 1 | entity `Search` 缺字段 |

### Benchmark 用新过滤重估

| 优化项 | 节省 | 累积 |
|---|---|---|
| 图片过滤: AND→min(w,h) | 56→28 张 (-50%) | — |
| inter-image sleep: 2s→0s | -56s | — |
| 清除 LightRAG 历史缓冲 | -300s | — |
| **优化后单篇预估** | **~8-10 分钟** | 仍太长 |

### 结论

**单篇 ingest 路径不适用于 batch。** 即使全优化后 10 分钟/篇 × 263 篇 = **44 小时串行**。

---

## 五、分类器质量审计 ⚠️ 新增

### 三篇随机 digest 样本

| # | 标题 | Digest 状态 | 质量 |
|---|---|---|---|
| 1 | OPC接单困境 | 57 字，正常摘要 | ✅ 可用 |
| 2 | 4位CEO同台 | 46 字，被截断 | ⚠️ 不完整 |
| 3 | 2026工业缺陷检测 | 216 字，含广告("联系＋微信") | ❌ 噪音 |

### GPT-5.5 分类失败链路

```
Spider取标题+摘要 → digest=N/A → 分类器仅看标题
  → "GPT-5.5""碾压Opus 4.7" → 脑补"deep technical paper"
  → depth=3 → 进入 ingest 队列
  → 实际: 新闻稿+benchmark图表 → 浪费 500s+ Vision + 31min LightRAG
```

### 建议方案

| 方案 | 描述 | 优缺点 |
|---|---|---|
| A: 两阶段 | 粗筛→抓全文→全文分类→ingest | 安全，但多一次抓取 |
| B: 全量全文 | 直接抓全文→分类→ingest | 最简单，263 篇 × 额外 1 HTTP |
| C: 混合 | digest 存在用摘要，N/A 自动拉全文 | 改动最小 |

---

## 六、核心技术难关

### 难关 1: 单篇 ingest 时间不可控 (P0)
- 图片数量是主导变量：10 张图 ≈ 5 分钟，50 张图 ≈ 25 分钟
- LightRAG entity extraction + merge 是第二变量
- 解决方案: **分离 ingest 和 enrich**

### 难关 2: 分类器不可靠 (P0)
- digest N/A / 截断 / 广告 → 分类失效
- 解决方案: **全文分类**

### 难关 3: Gemini Embedding 配额瓶颈
- 双键 429 在 361 次 merge 时必然触发
- RPD floor 防线只防 flash-lite(20 RPD)，不防高频正常调用

### 难关 4: LightRAG 状态管理
- 共享实例跨文章泄漏状态
- 需增加显式 reset/flush 机制

---

## 七、修正后的下一步行动

| 优先级 | 行动 | 说明 |
|---|---|---|
| **P0** | 改为全文分类 | `batch_ingest_from_spider.py`: 全量抓全文 → DeepSeek 分类 |
| **P0** | 修复图片过滤 `and` → `min(w,h)` | `ingest_wechat.py:641` |
| **P0** | inter-image sleep → 0s | `image_pipeline.py:19` |
| **P0** | 分离 ingest 和 enrich | 正文先入 LightRAG，Vision 异步 |
| P1 | 清除 LightRAG 历史缓冲 | 每次 batch 前 flush |
| P1 | `deepseek_model_complete` 加客户端超时 | 防止单 chunk 800s |
| P2 | Vision provider 熔断 | 连续 3 次失败 → 降级 |
| P2 | batch-watchdog 修正进度查询 | 查实际 article 进度 |

---

## 八、测试素材

**位置**: `test/fixtures/gpt55_article/`

```
test/fixtures/gpt55_article/
├── article.md          # 全文 Markdown (4,574 chars)
├── raw.html            # 原始 HTML (3.2MB)
├── metadata.json       # 文章元数据
└── images/             # 28 张图片 (min(w,h)>=300px, 24.7MB total)
    ├── img_000.jpg
    ├── img_001.png
    └── ...
```

**用途**:
- 本地 e2e 测试：`python ingest_wechat.py` 直接走本地文件，不依赖 WeChat 抓取
- 重复 benchmark：相同文章对比不同配置的耗时
- 分类器测试：全文交给 DeepSeek 分类，验证 depth 判准

---

*报告结束。共 10 个文件变更，7 个 git 提交，3 个 cron 作业，1 个测试素材包。含 Benchmark 实测 + 分类器审计数据。*
