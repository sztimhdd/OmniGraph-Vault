# 2026-05-08 Cron 入库失败诊断报告

> 写给 Claude Code — 请先读完全文再动手，问题之间有因果链。

## 一、症状总览

| 指标 | 值 |
|------|-----|
| 日期 | 2026-05-08 |
| Cron 阶段 | 09:00 daily-ingest |
| 候选文章 | 23 (进入 pipeline) → 11 (Layer1) → 3 (Layer2) |
| 实际入库 | 1 篇（但 content_hash 未写入，未最终验证） |
| 废热时间 | ~600s 浪费在 Apify/CDP/MCP 必然失败路径上 |
| 超时截断 | 900s 终端超时，剩余 2 篇未处理 |
| 最终结果 | **0 篇完成**（第 1 篇 96 实体/103 关系写入图但被超时截断） |

## 二、时间线（精确到秒）

```
09:00:38  Cron 启动，model=gemini-2.5-flash
09:00:44  Layer1 batch: 23→11 candidates, 12 rejected [4s]
           拒绝原因：营销/招聘/视觉/CV/具身智能 方向
09:00:48  LightRAG init: 5643 nodes, 7292 edges [7s]
09:00:55  开始 Layer2 抓取 (5篇, scrape-first)
09:00:55    [1/5] 叶小钗 "画布Agent" — Apify❌ CDP❌ MCP❌ UA✅ (13imgs)
09:01:32    [2/5] AI前线 "Anthropic黑箱" — Apify❌ CDP❌ MCP❌ UA✅ (15imgs)
09:02:08    [3/5] AI前线 "Vercel Open Agents" — Apify❌ CDP❌ MCP❌ UA✅ (7imgs)
09:02:50    [4/5] 字节笔记本 "Obsidian+CodingAgent" — Apify❌ CDP❌ MCP❌ UA✅ (5imgs)
09:03:24    [5/5] AINLP "DeepSeek-V4并行策略" — Apify❌ CDP❌ MCP❌ UA✅ (11imgs)
09:04:26  Layer2 done: 3 ok, 2 reject [3.5min]
           拒绝：id=831 RunningHub产品软文, id=850 视觉图像处理
09:04:26  开始入库 #1: "Anthropic最新论文撬开大模型黑箱"
            ┣ Chunks: 5 — 提取 96实体 + 103关系
            ┣ Merge Phase1 (96实体): 09:08:51-09:09:56 [65s]
            ┣ Merge Phase2 (103关系): 09:09:22-09:09:56 [34s]
            ┣ Merge Phase3 (写图): 09:09:56-09:10:28 [32s]
            ┣ Vision Cascade: 20张 SiliconFlow [09:10:28-09:15:21, ~5min]
            ┗ ✅ 第1篇 LightRAG 完成，图增长 5706 nodes, 7394 edges
09:15:21  等待 Vision 异步子 doc 写回...
09:15:46  ⏰ 终端 900s 超时 — 进程被强杀
          剩余 #2 "Vercel Open Agents" 和 #3 "Obsidian+CodingAgent" 未处理
```

## 三、根因分析（按影响排序）

### 🔴 R1: 抓取级联无断路器 — 浪费 ~600s

**现状:** `lib/scraper.py:_scrape_wechat()` 对每篇文章固定走四级级联：

```
Apify (30s timeout) → CDP (30s timeout) → MCP (30s × 2次 retry) → UA scrape
```

**问题:** 当 Apify 账号余额/配置异常时，**所有 5 篇文章**全部返回同样的错误：

```
Apify scraping failed: Maximum charged results must be greater than zero
```

CDP 端口 9223 可达（WebSocket 连通），但 browser context 不可用：

```
Failed to connect to CDP: BrowserType.connect_over_cdp: Timeout 30000ms exceeded.
```

MCP 返回空（0 chars）：

```
MCP returned unparseable result (0 chars)
```

UA scrape 作为最后兜底 **100% 成功**。

**浪费计算:**
- Apify 失败: ~30s × 5 = 150s
- CDP 超时: 30s × 5 = 150s
- MCP 双次 retry: 30s × 2 × 5 = 300s
- **合计: ~600s（占 900s 总预算的 67%）**

**期望行为:** Apify 连续 3 次同错误 → 跳过 Apify（批内）。CDP connect_over_cdp 失败 → 跳过 CDP。MCP 连续 3 次空返回 → 跳过 MCP。这些检查应该在**批次开始前**做一次探测，而不是每篇文章都重试。

### 🔴 R2: 终端超时 900s 不匹配批处理需求

**现状:** Cron job `2b7a8bee53e0` 的 prompt 是：

```
run batch_ingest_from_spider.py --from-db --max-articles 10
```

terminal tool 默认 timeout=900s，覆盖整个批处理。

**单篇耗时（实测）:**
- UA scrape: <5s
- LightRAG 实体提取+合并: ~6min (96实体/103关系)
- Vision 异步描述: ~5min (20张图 @ SiliconFlow ~15s/张)
- **合计: ~11 min/篇**

**批处理需求:**

| 文章数 | 耗时估计 |
|--------|----------|
| 3 篇 | 33 min (含 cascade 浪费 ~43 min) |
| 5 篇 | 55 min |
| 10 篇 | 110 min |

900s 只够处理 1 篇（在 cascade 浪费 600s 后只剩 300s 给 LightRAG）。

**注意:** `batch_ingest_from_spider.py` 内部已有 `LLM_TIMEOUT=600`（LightRAG func 超时），但终端级超时是独立的上限。Script 本身调好了，cron 外壳没跟上。

### 🟡 R3: Cron 模型选错 — Gemini 2.5 Flash 替代 DeepSeek

**现状:** Cron session dump 显示：

```json
"model": "gemini-2.5-flash",
"base_url": "http://127.0.0.1:8787/openai/v1/"
```

这意味着所有 LightRAG LLM 调用（实体提取、合并、摘要）全部通过 Hermes gateway 代理走了 Gemini 2.5 Flash（250 RPD 上限）。

**对比基准:**

| LLM 后端 | 单篇耗时 | RPD 限制 | 批处理风险 |
|----------|---------|---------|-----------|
| DeepSeek chat | ~7.4 min | 无 | 安全 |
| Gemini 2.5 Flash | ~11 min | 250 | 429 风险（批内 ~80-120 次 LLM 调用） |

**为什么这很重要:** `batch_ingest_from_spider.py` 的 LightRAG config 使用 `lib/models.py` 中的 `SYNTHESIS_LLM`，但 cron 的模型层覆盖了它。Cron prompt 里没有指定模型 → cron 继承了 Hermes gateway 的默认配置。

**Fix 方向:**
- 方案A: Cron 指定 `model: deepseek-chat`（不依赖 gateway）
- 方案B: Cron 使用 `workdir` 内的项目配置覆盖（如果有项目级 AGENTS.md 模型声明）
- 方案C: Batch script 内部强制 LLM_PROVIDER 环境变量

### 🟡 R4: Vision 异步子进程吞噬超时预算

**现状:** Vision cascade 是异步后台 worker，在 LightRAG 主流程完成后才开始消费。第 1 篇 20 张图的 vision 花了 09:10:28-09:15:21（~5min），刚好在 900s 边界上。此时如果还有剩余文章，vision worker 的 drain 会进一步挤压预算。

**注意:** Vision 本身没问题 — SiliconFlow 20/20 成功，质量正常。问题在于它在时序上"压线"了。

### 🟢 R5: 健康检查 QR 超时 → 扫描降级（非直接原因但上下文相关）

**现象:** 07:55 健康检查发现 WeChat 会话过期 → 启动 QR 登录流程 → 5 分钟无人扫码 → 超时。

**恢复:** 08:00 扫描 cron 通过**账号密码回退登录**成功（浏览器保存了密码），绕过了 QR 流程。扫描本身成功：50/54 账户，22 篇新文章。

**无关入库**，但说明了 QR 流程在 cron 上下文中不可行。账号密码回退是正确路径。

## 四、修复方案建议

### P0: 抓取级联断路器

**位置:** `lib/scraper.py:_scrape_wechat()`

**逻辑:**
```python
# 批次开始前探测
if not self._apify_available():
    self._skip_apify = True  # "Max charged results > 0" → 跳过
if not self._cdp_available():
    self._skip_cdp = True    # CDP connect_over_cdp timeout → 跳过
if not self._mcp_available():
    self._skip_mcp = True    # MCP 返回空 → 跳过
```

**或更简单:** 环境变量控制级联深度：

```bash
SCRAPE_CASCADE=ua           # 只用 UA（cron 默认）
SCRAPE_CASCADE=apify,ua     # Apify + UA fallback
SCRAPE_CASCADE=full         # 全四级（调试用）
```

### P0: 终端超时提升

**位置:** Cron job `2b7a8bee53e0` 配置或 batch_ingest 调用方式

**选项:**
- A. Cron job 加 `timeout=3600` 参数（需 Hermes cron 支持）
- B. `batch_ingest_from_spider.py` 添加 `--wall-timeout 3600` 参数，script 内自管理
- C. 改为 tmux 模式运行（绕过 Hermes terminal tool 的 900s 限制）

**推荐 C（tmux）** — 这是已验证的模式：

```bash
tmux new-session -d -s daily-ingest \
  "cd ~/OmniGraph-Vault && \
   PYTHONPATH=. /usr/bin/time -v venv/bin/python batch_ingest_from_spider.py \
     --from-db --max-articles 10 \
     2>&1 | tee /tmp/daily-ingest-$(date +%Y%m%d-%H%M).log; \
   echo 'EXIT='\$?"
```

Cron prompt 改为 monitor-only（tail log, check DB, check tmux alive）。

### P1: 模型修正

**位置:** Cron job `2b7a8bee53e0` config

直接指定 DeepSeek：

```json
"model": {"provider": "deepseek", "model": "deepseek-chat"}
```

（当前 cron job 的 model/provider 字段为 null，继承 Hermes gateway 默认 → gemini-2.5-flash）

### P2: Apify 配置修复

排查 Apify token 余额/权限。若暂时无法修复 → 通过 P0 的级联控制跳过 Apify（不影响功能，UA scrape 兜底）。

## 五、验证标准

修复后的期望行为：

1. Layer2 抓取阶段 Apify/CDP/MCP 跳过（1 次探测，非每篇重试）
2. 5 篇文章 UA scrape 在 <30s 内完成（vs 当前 3.5min）
3. 900s 内能完成至少 5 篇完整入库（vs 当前 0-1 篇）
4. `content_hash` 写入正常，`kv_store_full_docs.json` 增长
5. Cron 日志干净：无 Apify/CDP/MCP 重复失败噪音

## 六、相关文件

| 文件 | 作用 |
|------|------|
| `batch_ingest_from_spider.py` | 主入口，Layer1/2/Ingest 循环 |
| `lib/scraper.py:_scrape_wechat()` | 四级抓取级联（需修） |
| `lib/models.py` | LLM 模型选择常量 |
| `lib/vision_cascade.py` | Vision 异步 worker |
| `lib/lightrag_embedding.py` | LightRAG embedding（2-key rotation） |
| `ingest_wechat.py` | 单篇入库（实体提取→LightRAG insert） |
| `cron job 2b7a8bee53e0` | daily-ingest cron 配置 |
| `cron job df7dc3fa0390` | daily-scan cron（参考） |
| `data/kol_scan.db` | 全量状态 DB |

## 七、完整日志

Cron session dump: `~/.hermes/sessions/session_cron_2b7a8bee53e0_20260508_090038.json`

关键日志行（从 session 中提取）：

```
09:00:44 Layer1 batch: 23→11 candidates, 12 rejected
09:00:55 [1/5] 叶小钗 "画布Agent" — cascade: Apify❌ CDP❌ MCP❌ UA✅ 13imgs
09:04:26 Layer2 done: 3 ok (id=831 reject, id=850 reject)
09:04:26 LightRAG ingest #1: 5 chunks, 96 entities, 103 relations
09:10:28 Vision cascade: 20/20 SiliconFlow success
09:15:21 TIMEOUT after 900s — killed mid-vision-drain
```
