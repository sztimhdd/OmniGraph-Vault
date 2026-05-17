---
phase: 260517-riq
plan: 01
type: execute
wave: 1
date: 2026-05-17
status: shipped
---

# Quick 260517-riq (260517-rgd) — v1.0.y Closure Trio Summary

## Overview

Three atomic surgical patches shipped to close out v1.0.y per audit `.planning/ARCHITECTURE-AUDIT-Ingest-Pipeline-v1.md` §3. The audit evaluated the prior `.planning/ARCHITECTURE-ANALYSIS-Ingest-Pipeline-v1.md` adversarially and concluded that 3 of 5 claimed defects don't survive a code reading; only Defect 3 (dual-write inconsistency, 0.5% ghost rate) is a live measured issue, plus a per-article fragment of Defect 1 (DeepSeek 402 coupling). Audit recommended 3 surgical patches over the proposed 5-day decomposition rewrite. v1.0.y closure ships exactly that.

## Per-patch summary

### Patch 1 — Bidirectional reconcile (`2a1d3ac`, 260517-rgd-1)

**Files touched:**
- `scripts/reconcile_ingestions.py` — extended `--auto-patch` block to track `mystery_ingestion_ids` alongside existing `ghost_ingestion_ids` and added a second UPDATE clause flipping `ok → failed` with `skip_reason_version = COALESCE(skip_reason_version, 0) + 1`. Updated --auto-patch help text to reflect bidirectional behavior. Combined `patched_count` = `ghost_patched_count + mystery_patched_count` for stdout summary. Exit code logic now checks `unresolved_mystery > 0 OR unresolved_ghost > 0`.
- `tests/unit/test_reconcile_rss.py` — extended `tmp_db` fixture's `CREATE TABLE ingestions` to add `skip_reason_version INTEGER DEFAULT 0` (preserves all 20 existing tests' behavior identical via DEFAULT 0). Added 3 new tests with EXACT names per spec.

**Tests added:**
- `test_ghost_failure_ok_in_db_pending_in_kv_auto_patches` — ghost-failure detected and patched (`ok → failed` + `skip_reason_version=1`); exit 0
- `test_ghost_failure_off_by_default_preserves_status` — without `--auto-patch`, mystery row stays `ok` (back-compat)
- `test_bidirectional_both_directions_patched_same_run` — single auto-patch run handles both ghost-success AND ghost-failure; combined `patched 2`

**Test gate:** `DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_reconcile_rss.py -v` → **23 passed in 1.00s** (20 existing + 3 new). Note: plan's commit message references "26" but actual count is 23; verbatim message kept as user instructed.

### Patch 2 — DeepSeek 402 graceful degrade (`95bcbba`, 260517-rgd-2)

**Files touched:**
- `ingest_wechat.py` — added `from lib.checkpoint import ... get_checkpoint_dir`; added new helper `_write_degraded_marker(ckpt_hash, doc_id, *, reason)` writing JSON sidecar at `checkpoints/{ckpt_hash}/degraded.json`; added new async helper `_ainsert_with_402_fallback(rag, doc_id, content, ckpt_hash) -> bool` wrapping `rag.ainsert` with selective 402 detection (string-pattern match on `"402"` / `"insufficient"` for defensive matching across SDK versions); wired the helper into both ainsert call sites (cache-hit path :1118, main path :1380). On 402 returns `False` (degrade); on non-402 RuntimeError re-raises; on success returns `True`.
- `tests/unit/test_ingest_402_degrade.py` — new test file with 3 tests using `OMNIGRAPH_CHECKPOINT_BASE_DIR` env override to redirect sidecar markers to `tmp_path` (no pollution of `~/.hermes/omonigraph-vault/checkpoints/`).

**Tests added (verbatim names per spec):**
- `test_402_falls_back_to_text_only` — 402 RuntimeError → returns False, sidecar marker written, payload contains doc_id + reason + timestamp
- `test_non_402_runtime_error_still_propagates` — `Connection timed out` RuntimeError → propagates, no marker created
- `test_402_marker_visible_to_reconcile` — marker payload validates as the distinguishing artifact (test reads marker directly to keep Patch 2 independent of Patch 1)

**Test gate:** `pytest tests/unit/ -k "ingest_wechat or 402 or degrade"` → **7 passed** (3 new + 4 existing ingest_wechat tests). `pytest tests/unit/test_reconcile_rss.py` → **23 passed** (no Patch 1 regression).

**Pre-existing flaky test discovered (NOT a regression):** `tests/unit/test_text_first_ingest.py::test_vision_worker_spawn_order_after_parent_ainsert` fails on both pre-Patch-2 code and post-Patch-2 code (verified via `git stash` round-trip). Out of scope per critical rules.

### Patch 3 — MAX_ARTICLES tri-governor doc (`fd7cc74`, 260517-rgd-3)

**Files touched:**
- `CLAUDE.md` — new "MAX_ARTICLES is a tri-governor" subsection inserted between "Batch Execution" and "Known Limitations". Documents 3 governors: throughput cap, SiliconFlow ¥-budget governor (~¥0.04/article × 30 imgs), Vertex AI embedding RPM governor (100-300 calls/article entity-rich). Cross-references existing "SiliconFlow Balance Management" and "Vertex AI Migration Path" sections.

**Tests added:** None (doc-only patch).

**Test gate:** `pytest tests/unit/` regression suite — confirmed via per-patch tests above (Patch 1 + Patch 2 both pass post-Patch-3-CLAUDE.md edit).

**Attribution drift (FYI, not actionable):** `fd7cc74` inadvertently bundled a parallel-track `kb-v2.2-1-lightrag-storage-sync-PLAN.md` addendum (working-tree modified concurrently by another agent). Per `feedback_no_amend_in_concurrent_quicks.md`, no `--amend`/`reset` allowed on shared HEAD; commit is forward-only and the bundled file content is correct (just attributed to the wrong commit message). Same pattern as `6c93d67` swept-up plan-phase files documented in `STATE-kb-databricks-v1.md`.

## Memory file written

- Memory: `C:/Users/huxxha/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/project_v1_0_y_closure_260517.md`
- MEMORY.md index: 1 link line appended

Memory file mirrors the structure of `project_v1_0_x_closure_260516.md`. Contains:
- 3-patch summary with commit hashes
- Full v1.0.y commit list table (bd67f06 / 4eaef45 / 1b74fc1 / 9c4fc5e / 6c93d67 / 2a1d3ac / 95bcbba / fd7cc74)
- Audit decision context (why 5-day rewrite rejected)
- Out-of-scope items deferred to v1.0.z (Vertex 429 research, 4-worker rewrite, schema migration, MAX_ARTICLES default change)
- Patch 3 attribution drift note (forward-only, not actionable)

## STATE.md update

- `.planning/STATE.md` "Last activity" line updated
- New row appended to "Quick Tasks Completed" table for `260517-riq` with all 3 commit hashes

## Out-of-scope items refused

None encountered. The plan's out-of-scope guard list (batch_ingest_from_spider.py, lib/lightrag_embedding.py, MAX_ARTICLES default, Vertex 429, 4-worker rewrite, schema migration, pre-existing flaky test fix) was respected throughout — the only flaky test encountered (`test_vision_worker_spawn_order_after_parent_ainsert`) was confirmed pre-existing via `git stash` round-trip and left untouched.

## Self-Check: PASSED

**Files exist:**
- `scripts/reconcile_ingestions.py` (modified) — verified
- `tests/unit/test_reconcile_rss.py` (modified, fixture extended + 3 tests added) — verified
- `ingest_wechat.py` (modified, helper added + 2 call sites wired) — verified
- `tests/unit/test_ingest_402_degrade.py` (new file, 3 tests) — verified
- `CLAUDE.md` (new tri-governor section) — verified
- `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/project_v1_0_y_closure_260517.md` (new memory file) — verified
- `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/MEMORY.md` (1 link line appended) — verified
- `.planning/STATE.md` (Last activity + new table row) — verified

**Commits exist (`git log --oneline -5`):**
- `fd7cc74 docs(claude): MAX_ARTICLES is tri-governor (260517-rgd-3)`
- `95bcbba feat(ingest): 402 fallback to text-only ingest (260517-rgd-2)`
- `2a1d3ac feat(reconcile): bidirectional ghost-failure detection (260517-rgd-1)`

## Hermes Deployment Prompt

Paste the following directly to Hermes (production OmniGraph-Vault on the remote PC):

```
v1.0.y closure trio 部署 + smoke

cd ~/OmniGraph-Vault
git pull --ff-only origin main 2>&1 | tail -3
git log --oneline -5
# 期望前 3 条是 260517-rgd-3 / -2 / -1 (hashes: fd7cc74 / 95bcbba / 2a1d3ac)

source venv/bin/activate
DEEPSEEK_API_KEY=dummy python -m pytest tests/unit/test_reconcile_rss.py tests/unit/test_timeout_budget.py -v 2>&1 | tail -10
# 期望: 23 reconcile + 26 timeout = 49 passed, 0 failed (允许 xfailed/xpassed)
# (注: plan 写的 "26 reconcile" 是 verbatim 但实际 count 23 — 20 + 3 new)

# 验证 cron 已用 --auto-patch (9c4fc5e 已加,这里只 confirm)
crontab -l | grep reconcile

# Optional 主动测 Patch 2 (可选,等自然触发也行):
# DEEPSEEK_API_KEY=invalid python ingest_wechat.py "<a known short article URL>"
# 期望:article 进 kv_store,日志看到 "degraded_extraction" marker
# Marker 会写到 ~/.hermes/omonigraph-vault/checkpoints/{ckpt_hash}/degraded.json

把 git pull 输出 + pytest tail + crontab grep 三段贴回来。

接下来等 5/18 06:00 ADT cron 自然 reconcile run,贴 ghost / mystery /
patched counts。
```

## Cross-references

- Audit: `.planning/ARCHITECTURE-AUDIT-Ingest-Pipeline-v1.md` §3 (3 surgical patches recommendation)
- Original analysis (rejected): `.planning/ARCHITECTURE-ANALYSIS-Ingest-Pipeline-v1.md`
- v1.0.x context: memory `project_v1_0_x_closure_260516.md`
- Ghost-success rate baseline: memory `project_ghost_success_observed_260514.md`
- Concurrent-quick safety lessons: `feedback_git_add_explicit_in_parallel_quicks.md`, `feedback_no_amend_in_concurrent_quicks.md`
- Plan: `260517-riq-PLAN.md` (this directory)
