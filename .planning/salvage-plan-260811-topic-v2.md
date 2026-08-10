# 打捞计划 — 近 3 个月被弃文章（含 452 篇补录重筛）

**状态:** ACTIVE（2026-08-11, quick topic-v2 子任务）
**背景:** 旧分类（Agent/LLM/RAG/NLP/CV）错杀大量高价值 Agent 工程文章。新 topic 表
（config/topic_keywords_2026.json, 7 topics）已落地 + `PROMPT_VERSION_LAYER1`
bump 至 `layer1_v2_20260810` → 旧 verdict 全部失效，重筛机制就绪。

## 数据全景（kol_scan.db）

| 区间 | total | candidate | reject |
|---|---|---|---|
| 2026-05 | 569 | 170 | 399 |
| 2026-06 | 774 | 198 | 576 |
| 2026-07 | 1235 | 268 | 967 |
| 2026-08 (dajiala 补录) | 452 | 127 | 325 |

近 3 个月（5/11–8/11）reject 合计 ≈ 2267 篇。
reject 中标题命中新关键词（Harness/Loop/Memory/Skill/MCP/GraphRAG/智能体等）:
- 全历史: 479 篇
- 近 3 月: 433 篇  ← 打捞目标池

## 打捞方案（三层，按优先级）

### 第 1 层 — 452 篇补录全量重筛（最高优先，用户点名）
- **为什么自动生效:** classify 的 `NOT IN (SELECT article_id FROM classifications WHERE topic=?)`
  按 (article_id, topic) 判断；旧 5 topic 与新 7 topic 名完全不同
  （Harness ≠ LLM, MemorySystem ≠ RAG …）→ 每个新 topic 的 NOT IN 均为空 → 452 篇全部重筛。
- **动作:** `batch_classify_kol.py --topic-file config/topic_keywords_2026.json --min-depth 2`
  （或手动 `systemctl start omnigraph-kol-classify.service`，ExecStart 已更新）
- **成本:** 7 topics × 452 篇 × DeepSeek 批调用 ≈ 60min，无 API 现金成本（DeepSeek 按量，已有配额）。
- **验证:** classifications 表新增 7×452 行（topic ∈ 新 7），旧 5 topic 行保留（历史）。

### 第 2 层 — 433 篇 reject 标题命中重筛（近 3 月）
- **机制同第 1 层**（新 topic 名 → NOT IN 为空 → 重筛）。
- **注意:** 标题命中 ≠ 真相关；LLM 会按新 prompt 判 depth/relevant。预期部分仍 reject（正常）。
- **动作:** 第 1 层跑完后，对近 3 月 reject 中标题命中 433 篇执行同一 classify。
  （全量 2267 篇跑一遍也可——成本 60min×5 ≈ 5h，分批；先 433 精准池。）

### 第 3 层 — 存量 candidate 不受影响
- 已有 candidate verdict（旧分类）不会被删除；ingest 候选池 SELECT 条件
  （layer1_verdict='candidate' 或 NULL 或 version≠CURRENT）对新旧 candidate 一视同仁。
- 旧 candidate 若与新 topic 无关，重筛后可能变 reject —— 这是**期望行为**（降噪）。

## 执行顺序
1. [x] 新 topic 表 + prompt + 版本号 bump（完成）
2. [x] 验证测试 8/8（完成）
3. [ ] 跑 classify 重筛 452 篇（第 1 层）
4. [ ] 验证重筛结果（candidate 数对比旧 127；抽样看捞回文章）
5. [ ] 433 篇精准池重筛（第 2 层）
6. [ ] ingest 消化新 candidate（并发/超时已修）

## 已知风险
- DeepSeek 批调用 100 行/批（KOL_CLASSIFY_BATCH_SIZE 默认），452 篇 ≈ 5 批/topic × 7 = 35 次调用。
- 重筛后 ingest 候选池变大 → daily-ingest 消化时间延长（BACKOFF 30s 已覆盖，无卡死风险）。
- 旧 classifications 行保留 → 不影响历史统计（classifications 表无唯一约束冲突，ON CONFLICT DO UPDATE 按新 topic 新增）。

## 完成标准
- 452 篇新 topic classify 全跑完（classifications 有 7 新 topic 行）
- 新 candidate 池 ≥ 旧 127 且包含旧分类错杀的高价值文章（Harness/Loop/Memory 标题）
- ingest 一轮跑通 ≥ 5 篇无 failed（非误杀）
