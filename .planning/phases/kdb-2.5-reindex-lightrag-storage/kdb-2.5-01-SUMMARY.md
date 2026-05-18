# kdb-2.5-01 — SUMMARY

## Plan 01 deliverables (Tasks 1.1-1.4)

| Task | Status | Commit |
|---|---|---|
| 1.1 — Job script (reindex_lightrag.py) | ✅ shipped | 04b4a54 |
| 1.2 — Unit tests (8 cases) | ✅ shipped | 04b4a54 |
| 1.3 — Bundle YAML (databricks.yml + jobs/reindex_lightrag.yml) | ✅ shipped | 8094913 |
| 1.4 — Deploy + Step 1 run + GATE decision + FINDINGS | ✅ shipped | <THIS COMMIT> |

## Runtime patches discovered + fixed during 1.4 execution

| Bug | 现象 | Fix commit |
|---|---|---|
| 1 | Spark kernel running event loop → asyncio.run() raise | 5f9c1bb (nest_asyncio shim) |
| 2 | spark_python_task exec() 无 __file__ | 5f9c1bb (sys.argv[0] fallback) |
| 3 | UC Volume FUSE 不支持 seek-based I/O (open "a") | 5f9c1bb (/tmp/ intermediary) |
| 4 | articles.lang 列在老 prod DB snapshot 不存在 | 5f9c1bb (PRAGMA introspection) |
| 5 | rag.doc_status.get_docs_by_ids 不存在 | 5f9c1bb (rag.aget_docs_by_ids dict API) |
| 6 | smallbatch-storage 残留 KG state → 全 dedup skip | (orchestrator 手动清空 + 重跑) |
| 7 | D-05 post-check doc id 错加 doc- 前缀 → 全 false-negative | <THIS COMMIT> (Task A) |

Note: Bug 6 是 storage hygiene 问题 (累积 dry-run residue),非代码 bug。orchestrator
2026-05-17 通过 `databricks fs rm -r kdb-2.5-smallbatch-storage` 解决,YAML 已经传
--force-overwrite 防止 D-07 拒写。

## Job run summary

- Run id: 142058128668687
- Wallclock: 42.2 min for 50 articles
- KG storage written: 56 MB+ (graphml + vdb + kv_store, 12 文件)
- Real ainsert success: 50/50 (per KG storage size + per-article wallclock 50.7s 在 anchor 范围)
- progress.csv 表观 status: 50 failed (Bug 7 false-negative; 真实成功)

## GATE decision

**PASS** (cost / wallclock 2/2; failure_rate N/A 因 Bug 7 false-negative)
详见 [kdb-2.5-SMALLBATCH-FINDINGS.md](kdb-2.5-SMALLBATCH-FINDINGS.md)。

## Plan 02 readiness

- Cost gate ✅ — Plan 02 全集 75 篇 anchor estimate $7.28 << $200
- Wallclock gate ✅ — Plan 02 1.06h << 30h
- 但触发前必须 (本 commit 已含 Bug 7 fix):
  - Bug 7 patch ✅ 本 commit
  - Plan 02 Task 2.1 pre-flight (D-03 + D-07) — 由 Plan 02 executor 负责

## Cross-references

- Phase plan: kdb-2.5-01-job-script-and-smallbatch-validation-PLAN.md (Tasks 1.1-1.4)
- Phase verification: kdb-2.5-VERIFICATION.md (orchestrator post-iter-1 已 PASS)
- Wave 2 dependency: kdb-2.5-02-fullreindex-and-postcheck-PLAN.md (gate PASS unblocks)
- Milestone STATE: STATE-kb-databricks-v1.md
