# PROJECT-Ingest-Refactor-v3.5 — Research Artifact (NOT a milestone charter)

> Design discussion output. 读 `.planning/MILESTONE_v3.5_CANDIDATES.md` Section 1
> 并基于 2026-05-07 早晨 cron 灾难后讨论形成。**仅研究材料，不进入 ROADMAP。**

Created: 2026-05-07

---

## 1. Incident Postmortem

2026-05-07 06:00–09:30 ADT cron window，0 篇文章入库。根因：Quick 260506-se5 (c786a83) 将
`classifications` 的 UNIQUE 约束从 `(article_id, topic)` 改为 `(article_id)` —
每个 article 只允许 1 行。但 cron 命令仍是老的 5-topic 循环（`--topic Agent --topic LLM
--topic RAG --topic NLP --topic CV`），每轮 `ON CONFLICT(article_id) DO UPDATE SET
topic=...` 覆盖前一轮的 topic 字段。最后一轮 CV 赢，全表 653 行 topic='CV'。
后续 ingest cron 的 `--topic-filter agent,hermes,openclaw,harness` 无匹配 → 0 入库。
本地测试用 mock-only 单元测试，未在 production-shape DB 上验证 cron 多 topic 循环兼容性。

---

## 2. Target Architecture

Section 1 的 4-stage 理想流：

```
SCAN     | cheap, no LLM    | RSS/KOL fetch + dedup hash + write articles.* row
SCRAPE   | paid Apify       | scrape + atomic write articles.body
CLASSIFY | 1 LLM call       | full-body, multi-topic single response, UPSERT
INGEST   | 1 LLM call       | LightRAG ainsert (entity extract inside LightRAG)
```

### User-validated assessment

**AGREE: 4-stage 比当前正确，但 Section 1 的 change log 需要微调：**

| What changes | Section 1 claim | User-locked decision (2026-05-07) |
|-------------|-----------------|----------------------------------|
| Drop graded probe | "accept irreducible Apify cost" | **保留为 `--cheap-mode` opt-in flag，默认关闭** (`OMNIGRAPH_GRADED_CLASSIFY=0`)。日常 cron 不开；成本敏感场景（Phase 22 BKF backlog re-ingest）显式开。理由：5-article test 里正确过滤 26+ off-topic；但默认开会增加维护成本 + topic_filter 泄漏风险。 |
| Move entity extract inside LightRAG | "remove buffer" | **保留 entity_buffer，decouple 但不移**。Phase 2 architecture decision，改 LightRAG 内部需 upstream 变更，超出 v3.5 scope。 |
| Resolve Cognee inline | "fix routing OR delete" | **删，async-only via cognee_batch_processor.py**。LiteLLM → AI-Studio routing 此生不对齐；修路由 = 修上游库，删 8 行代码 ROI 更高。Phase 20 COG-03 已落地此方向。 |
| Schema for classifications | "ON CONFLICT(article_id)" | **回退 migration 004，保留 multi-row `UNIQUE(article_id, topic)`**。Migration 004 的 article_id 单列索引与多 topic 循环不兼容，是今天的根因。migration 005 显式 DROP INDEX idx_classifications_article_id。原始 multi-topic-per-article 设计本身正确，无需强行迁到单行 + JSON。 |

### Key insight: `_classify_full_body` already IS the target pattern

`batch_ingest_from_spider.py:1009` 的 `_build_fullbody_prompt(title, body, topic_filter=...)`
已经实现了 "1 LLM call → multi-topic single response"。surgical fix 不是重写 pipeline，
而是 **把 cron classify step 从多 topic 循环改为单 call**，并用 `_classify_full_body`
里已经验证的 prompt + UPSERT pattern。

---

## 3. Transition Path (Draft Phases — revised order per user 2026-05-07: A→D→B+C)

### Phase A: Schema Audit + Migration 005 — DROP UNIQUE(article_id) (2-3 tasks, immediately)

- **A1**: 确认 `classifications` 当前状态（migration 004 加了 `idx_classifications_article_id` UNIQUE INDEX，与表级 `UNIQUE(article_id, topic)` 冲突）
- **A2**: Migration 005: `DROP INDEX IF EXISTS idx_classifications_article_id` — 回退 004 的单列唯一约束，恢复 multi-topic-per-article 兼容性
- **A3**: DB backup → apply migration → verify `SELECT topic, COUNT(*) FROM classifications GROUP BY topic` 无异常
- **A4**: 文档化：`docs/schema/classifications.md` 记录当前表结构 + migration history

### Phase D: Production-Shape Local Test (2-3 tasks, 最高优先级)

**Phase D 提到 B 之前 — 这是今天 cron 灾难暴露的真正缺口。没有 production-shape local test，Phase B 就是 "再次祈祷生产环境跟本地一致"。**

- **D1**: Snapshot production DB → `tests/fixtures/production_snapshot_20260507.db`
- **D2**: Write `tests/unit/test_cron_loop_equivalence.py` — 在 snapshot 上跑：old 5-topic 循环 → 记录 classifications 分布，new single-call → 对比 topic coverage、depth 分布等
- **D3**: Write `tests/unit/test_classify_topic_filter_no_cv.py` — 断言：任何 classify run 的 topic 字段 ≠ 'CV'（除非用户显式请求 topic='CV'）

### Phase B: Cron classify → Single-Call (3-4 tasks, 等 v3.4 Phase 22 cutover 完成)

- **B1**: 改 `batch_classify_kol.py:run()` — 去掉 `--topic` 多参数循环，改为接受 `--topic-filter`（逗号分隔），单次 LLM call 覆盖所有 topic
- **B2**: 复用 `_build_fullbody_prompt`（import from `batch_classify_kol` 的已有函数，不是 copy）
- **B3**: INSERT 保留 multi-row 模型：每 article × topic 一行 `ON CONFLICT(article_id, topic) DO UPDATE SET ...`（与 Phase A 回退后的 schema 兼容）
- **B4**: 更新 cron job `daily-classify-kol` 的 command

### Phase C: Candidate SQL → json_each() (1-2 tasks, 与 Phase B 一起做)

- **C1**: candidate SQL 从 `classifications.topic LIKE '%x%'` 改为 `json_each()` 展开 — 支持多 topic 且避免 LIKE hack 的边界 case
- **C2**: 确认 `batch_ingest_from_spider.py` 的 candidate query 兼容新 multi-row 模型

### Phase E: Reliability Test + Cron Cutover (2 tasks)

- **E1**: 5-article reliability test with new single-call classify
- **E2**: 更新 `cronjob update` 命令 + Day-1 observation

---

## 4. Testing Strategy

**Production-Shape Local Snapshot**: 今天 rollback 后的生产 DB 备份（`data/kol_scan.db.backup-pre-rollback-20260506-104420`，13.6 MB）做为本地 test fixture。保留了 ~768 行历史 classifications + 全量 articles/st accounts。

**Cron Loop Simulator**: 新的 `test_cron_loop_equivalence.py` 在 snapshot 上跑：
1. 建 5 个 topic 的列表
2. 对每个 topic 单独调用 `run()`（模拟旧 cron）
3. 记录每条 article 最终 topic（应该是最后一个 topic = CV）
4. 与 new single-call 的结果对比（topic coverage 应覆盖更多）

**Guards**: 在生产 DB 上测试前先 `cp backup`，测试完 `cp backup back`。

**Candidate SQL json_each 展开**: 正确性 > 性能。`LIKE '%"agent"%'` 的边界 case（substring matching、JSON encoding、index 利用）全躲不开。`json_each()` 是 SQLite 默认开的扩展，~600 行表 EXISTS subquery <10ms。Query 形如：

```sql
SELECT a.* FROM articles a
WHERE EXISTS (
  SELECT 1 FROM classifications c
  JOIN json_each(c.topics) je
  WHERE c.article_id = a.id
  AND je.value IN ('agent', 'hermes', 'openclaw', 'harness')
)
```

---

## 5. Cognee Integration Direction

**User-locked decision: 删 inline，async-only via `cognee_batch_processor.py`。**

- LiteLLM → AI-Studio routing 422 是冰山一角 — `gemini-embedding-2` 只在 Vertex 上可用，而 Cognee 通过 LiteLLM 用 API key 路由，此生不对齐
- 当前 `OMNIGRAPH_COGNEE_INLINE=0` 已经 gated off，production 不触发
- Phase 20 COG-03 retire env gate 落地的方向就是 async-only
- 修 LiteLLM 路由 = 修上游库；删 inline = 删 `_cognee_inline_enabled` helper + 1 call site + 1 env var。ROI 完全不是一个量级
- Phase 20 Wave 3 Step 2 完成后执行：删 `batch_ingest_from_spider.py` 里的 inline 分支 + `cognee_wrapper.remember_article` inline call + CLAUDE.md env var table 行

---

## 6. Schema Evolution — Multi-row Retained

**User-locked decision: 回退 migration 004，保留 `UNIQUE(article_id, topic)` 多行模型。**

Migration 004 的 `idx_classifications_article_id` UNIQUE INDEX 是 260506-se5 的设计错误 — 它假设 classifications 每 article 只 1 行，但这与 multi-topic 循环不兼容，且今天早晨的 cron 灾难直接由此引起。

Migration 005 动作：`DROP INDEX IF EXISTS idx_classifications_article_id` — 回退 004，恢复原始 `UNIQUE(article_id, topic)` 表约束。

表结构保持为：`(article_id, topic, depth_score, relevant, excluded, reason, depth, topics, rationale, classified_at)` — 其中 `topics` 是 JSON 列（`batch_ingest_from_spider.py:1039` 写入），`topic` 是首 topic 的 legacy 列，`depth` / `rationale` 是 Phase 10 加的新列。

| 维度 | Multi-row (restored) |
|------|---------------------|
| 1 article × 5 topics | 5 rows, 1 per topic |
| cron 兼容性 | 多 topic 循环每圈插一行（ON CONFLICT(article_id, topic)） |
| ingest candidate SQL | `WHERE topic IN (SELECT value FROM json_each(?))` |
| 未来扩展 | N topics × M runs → N×M rows，但 natural dedup via classified_at |

---

## 7. When to Charter

**在 v3.4 收尾后 charter。Phase A 可立刻并行（read-only）。**

- **Phase A (schema audit + migration 005)**: 这周内完成，read-only audit + 1 行 SQL migration，不影响 v3.4
- **Phase D (production-shape local test)**: Phase A 完成后立刻起
- **Phase B+C (classify + candidate query)**: 等 v3.4 Phase 22 cutover 完成 + Day-1/2/3 观察期通过（~2.5 周后）。理由：Phase 22 本身要修改 cron 命令，跟 B4 改动撞；v3.4 milestone gate 要求 RSS digest 质量 ≥ KOL，测试期间不应叠加 classify 变更
- **Agentic-RAG-v1**: 并行 milestone，不应被 ingest refactor 阻断

---

## 8. Five User-Locked Decisions (2026-05-07)

| ID | Decision | Rationale |
|----|---------|-----------|
| D-3.5-GRADED | Graded probe = `--cheap-mode` opt-in，default off | 正确但增加维护成本；cost-sensitive 场景显式开 |
| D-3.5-SCHEMA | 回退 migration 004: DROP UNIQUE(article_id)，保留 multi-row | 004 的 article_id 单列索引 = 今天 cron 灾难根因；原始设计正确 |
| D-3.5-COGNEE | 删 inline，async-only via cognee_batch_processor.py | LiteLLM routing 此生不对齐；删 8 行代码 ROI > 修上游库 |
| D-3.5-SQL | Candidate SQL 用 `json_each()` 展开 | 正确性 > 性能；LIKE hack 有边界 case |
| D-3.5-SCHEDULE | Phase order: A → D → B+C（D 提到 B 之前） | 没有 production-shape local test，Phase B 就是在祈祷 |

**Verdict: Surgical fix，不是重写。**`_classify_full_body` 的 pattern 已证明正确 — 主要工作是把 cron classify step 从旧的 multi-topic 循环迁到 single-call multi-topic，以及 schema 稳定化和测试加固。

---

## 9. Approval & Next Steps

**Current state**: Research artifact — 5 D-decisions locked by user on 2026-05-07.
**NOT a milestone charter.** Does NOT enter ROADMAP "Next" yet.

**Next actions**:
1. Phase A (schema audit + migration 005) — 可立刻起 quick 任务
2. Phase D (production-shape local test) — 等 Phase A 完成后
3. Phase B+C (classify + candidate query refactor) — 等 v3.4 Phase 22 cutover 完成（~2.5 周）
4. Phase E (reliability test + cron cutover) — 等 Phase B+C 完成

**Charter decision point**: v3.4 milestone close 时 review 本文档，决定是否
`/gsd:new-milestone v3.5-Ingest-Refactor`。

**File**: `.planning/PROJECT-Ingest-Refactor-v3.5.md`
**Git**: NOT staged. Commit + push after user sign-off.

---

*Research artifact closed 2026-05-07. No follow-on implementation — design discussion complete.*
