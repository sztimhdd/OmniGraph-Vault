# kdb-2.5 SMALLBATCH-FINDINGS

> Step 1 small-batch validation outcome. Cost gate decision below.
> Authored: 2026-05-17 (kdb-2.5-01 收尾 commit)

## Job run

- Job: kdb_2_5_reindex_smallbatch (job_id=291789802273158)
- Run id: 142058128668687
- Run page: https://adb-2717931942638877.17.azuredatabricks.net/?o=2717931942638877#job/291789802273158/run/142058128668687
- Wallclock: 2026-05-17 21:12:27 → 21:55:43 ADT (= 42.2 min)
- result_state: FAILED (cosmetic — IPython kernel SystemExit:2 副作用; 数据已完整写入 Volume)

## Stats

| Field | Value |
|---|---|
| n_results | 50 |
| n_ok (per progress.csv status field) | 0 |
| n_failed (per progress.csv status field) | 50 |
| **真实 ainsert 成功率** | **50/50 (100%) — 见 KG storage 证据** |
| failure_rate (stats.json) | 1.0 (Bug 7 false-negative — N/A criterion) |
| elapsed_total_s | 2534.09 (= 42.2 min) |
| avg_elapsed_per_article | 50.7s |
| min/max elapsed | 1.7s / 756.8s |
| full_corpus_size (DATA-07 strict) | 75 (Plan 02 全集) |

## Bug 7 — D-05 post-check doc id prefix 错误 (false-negative)

50/50 progress.csv status='failed' 但是**全部 50 篇 ainsert 真实成功**:
- KG storage 56 MB+ 数据写入 (graphml 2.6 MB / vdb_entities 17.8 MB / vdb_relationships 22.5 MB / 等)
- avg per-article wallclock 50.7s 在 RESEARCH anchor 25-35s 范围 (略偏长合理)
- LightRAG entity extraction + embedding + chunking 正常工作

KG storage 实际写入证据 (`dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/output/kdb-2.5-smallbatch-storage/`, mtime 21:54-21:55 ADT):

| File | Size |
|---|---|
| graph_chunk_entity_relation.graphml | 2,634,160 bytes |
| vdb_entities.json | 17,835,458 bytes |
| vdb_relationships.json | 22,553,944 bytes |
| vdb_chunks.json | 1,976,247 bytes |
| kv_store_doc_status.json | 46,373 bytes |
| kv_store_full_docs.json | 619,093 bytes (= 50 docs) |
| kv_store_full_entities.json | 66,084 bytes |
| kv_store_full_relations.json | 191,003 bytes |
| kv_store_text_chunks.json | 732,413 bytes |
| kv_store_entity_chunks.json | 483,246 bytes |
| kv_store_relation_chunks.json | 658,828 bytes |
| kv_store_llm_response_cache.json | 8,603,852 bytes |
| **Total** | **~56 MB / 50 articles** |

根因 (lightrag.py:1395-1415):
- 我们 ainsert(ids=[content_hash]) 显式传 ids
- LightRAG 用裸 hash 作 doc_status key,不加 prefix (line 1412-1415: `contents = {id_: ...}`)
- D-05 post-check 错用 `f"doc-{hash}"` 查 → 永远 unknown → mark failed
- 修法: 同 commit Task A — `doc_id = row.content_hash` (no prefix)

## Per-article token / cost (静态 anchor 估算)

stats.json 没采集真实 token 计数 (n_ok=0 就 short-circuit 了平均统计)。
按 RESEARCH Q3 anchor (Sonnet input $3/1M + output $15/1M + Qwen3 $0.15/1M):

```
cost_per_article ≈ $0.097 (anchor)
50 articles paid ≈ $4.85
75 articles full corpus ≈ $7.28
```

工作区 Billing UI 实际数字可后续手动 backfill 进 SUMMARY,但不影响 GATE 决策
(anchor 估算 ±50% 仍远低于 $200 gate)。

## Wallclock extrapolation

```
per-article avg = 50.7s (sequential, D-04)
75 articles full corpus = 75 × 50.7 = 3802.5s = 63.4 min ≈ 1.06h
```

## Gate decisions

| Criterion | Threshold | Actual | Verdict |
|---|---|---|---|
| 1. cost_extrap < $200 | hard | $7.28 (anchor) | ✅ PASS |
| 2. wallclock_extrap < 30h | hard | 1.06h (75 × 50.7s sequential) | ✅ PASS |
| 3. failure_rate < 5% | hard | 100% per stats but Bug 7 false-negative; real KG storage 50/50 = real success rate 100% | N/A (Bug 7 caveat) |

**GATE: PASS** (with Bug 7 caveat)
→ proceed to Plan 02 fullreindex
→ Bug 7 fix MUST land before Plan 02 trigger (production /lightrag_storage/ resume
relies on doc_status post-check being correct)

## Longest article wallclock (RESEARCH Q8 deliverable)

- max elapsed_s = 756.8s (= 12.6 min)
- 对应 hash: 5a362bf61e (articles, body_len=154372)
- 对应 ntile: 5 (highest body-length stratum)
- 对全集 wallclock 单点贡献 = 756.8 / 3802.5 = 19.9% (单篇占 75 篇 wallclock 1/5)
- 不超 timeout — 7200s smallbatch ceiling 仍 9.5x headroom

## Cost gate FAIL contingency (not triggered)

如 Plan 02 实际跑出 cost_actual > $200 OR wallclock > 30h:
- STOP, escalate to user (D-07 哲学应用到 Plan 02 同样)
- 调查可能原因: full_corpus_size 偏离预期 (currently 75) / Sonnet 长尾输出膨胀 / 网络抖动
- 不要无脑 retry — 修因再跑

## 已付 cost (smallbatch)

```
50 articles × $0.097 anchor ≈ $4.85
```

真实数字可从 Workspace Billing UI 手动取 (Settings → Billing → Model Serving usage,
window: 2026-05-17 21:12-21:56 ADT)

## Plan 02 触发条件清单

GATE PASS 但触发 Plan 02 前必须:
- [ ] Bug 7 fix commit (本 commit 含)
- [ ] (建议) 清空 production /lightrag_storage/ + 删 /output/kdb-2.5-progress.csv
       使 Plan 02 fullreindex 从干净状态开始
- [ ] Plan 02 Task 2.1 pre-flight (D-03 WRITE_VOLUME grant + D-07 empty-target 检查)
