# Repo Cleanup Proposal — 260505-ee5

**Date:** 2026-05-05
**Status:** Awaiting user approval (NO deletions yet)
**Scope:** Repo root + `docs/` + `tests/` + untracked artifacts. `.planning/phases/`, `lib/`, `enrichment/`, `skills/`, `scripts/`, `tests/` (subdirs), `venv/`, `__pycache__/`, `.dev-runtime/` are OFF LIMITS per task constraints.

---

## Bucket counts

```
A 核心保留:        ~24 docs + .planning/ tree (preserved as-is)
B 活代码保留:      ~559 tracked files (untouched; live shims verified)
C 删除候选:         6 files  (5 untracked + 1 tracked)
D 删除候选:         3 files  (all tracked, in docs/)
E 删除候选:         5 files  (all untracked / gitignored artifacts)
F 不确定:           9 files  (need user judgment)
```

---

## Bucket A — Core docs to preserve (no action)

- Root: `CLAUDE.md`, `README.md`, `Deploy.md`, `AGENTS.md`
- `.planning/PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`
- `.planning/MILESTONE_v3.1_*`, `MILESTONE_v3.2_*`, `MILESTONE_v3.3_*` (all referenced by STATE/ROADMAP/REQUIREMENTS)
- `.planning/phases/04-19/**` (current and recent phases — explicit "do not touch" per task)
- `.planning/quick/**` (existing quick-task records, plus the new `260503-lq7-PLAN.md` and `260505-ee5-*` for this run)
- `.planning/research/**`
- `.planning/config.json` (untracked GSD state file, regenerated)
- `.planning/phases/17-batch-timeout-management/17-0[0-2]-SUMMARY.md` (untracked but **new work**, not stale)

---

## Bucket B — Live code to preserve (no action)

All 559 tracked files. Spot-checked the only suspicious-looking root-level shims and confirmed they are **load-bearing back-compat re-exports** (not dead code):

- `lightrag_embedding.py` → `from lib.lightrag_embedding import embedding_func` (Phase 7 D-09 amendment 2 shim; imported by `ingest_wechat.py`, `ingest_github.py`, `multimodal_ingest.py`, `query_lightrag.py`, `omnigraph_search/query.py`, `tests/unit/test_lightrag_embedding.py`, etc.)
- `lightrag_llm.py` → `from lib.llm_deepseek import deepseek_model_complete` (Plan 05-00c shim; imported by `tests/unit/test_lightrag_llm.py`, `scripts/wave0c_smoke.py`)

Both are docstring-marked back-compat shims. **Do not delete.**

`kol_config.py` (root) is gitignored on purpose (`.gitignore:42` — contains WeChat credentials), but actively imported by `batch_scan_kol.py`, `batchkol_topic.py`, `ingest_github.py`, `kol_registry.py`. Untracked-by-design. **Do not touch.**

---

## Bucket C — One-off probe / scratch scripts (DELETE)

All match the "underscore-prefix probe scripts at repo root" pattern from the task spec. Reference scan complete; no live code or core doc imports any of them.

### Untracked (use `rm`)

| File | Size | mtime | Evidence |
|---|---|---|---|
| `_grab_cookies.py` | 4.8 KB | 2026-05-05 00:00 | One-off cookie-grabbing probe; no references in tracked code |
| `_grab_wechat_qr.py` | 7.1 KB | 2026-05-04 23:58 | WeChat QR probe; no references |
| `_mcp_debug.py` | 2.6 KB | 2026-05-04 23:43 | MCP debugging scratch; no references |
| `_probe_wechat.py` | 3.5 KB | 2026-05-04 23:53 | WeChat probe; no references |
| `_screenshot_probe.py` | 4.3 KB | 2026-05-04 23:50 | Screenshot probe; no references |

### Tracked (use `git rm`)

| File | Size | mtime | Evidence |
|---|---|---|---|
| `_reclassify.py` | 6.4 KB | 2026-04-29 12:08 | Standalone reclassify CLI. Only self-reference (its own argparse usage line). All other "matches" are historical Phase 5/7 plan/summary docs that *describe* it, not import it. Functionality has migrated into `enrichment/rss_classify.py` (Phase 5-03) and is no longer needed in the live pipeline. The `tests/unit/test_rss_classify.py` match was a function name collision (`test_reclassify_is_noop_via_unique_constraint`), NOT an import. |

---

## Bucket D — Superseded plan / runbook duplicates (DELETE)

Reference scan: each is referenced ONLY by its own filename in `.planning/phases/05-pipeline-automation/05-00-SUMMARY.md` (i.e. archival mention). The authoritative finalized version is the in-`.planning/` SUMMARY.md.

| File | Size | mtime | Evidence |
|---|---|---|---|
| `docs/phase5-00b-diagnostic-embedding-429.md` | 3.7 KB | 2026-04-30 | Phase 5 wave 00b diagnostic notes from a single-day incident. **No external references** — only self-references. Superseded by Phase 5 SUMMARY. |
| `docs/phase5-00b-refactor-plan.md` | 8.2 KB | 2026-04-29 | Phase 5 wave 00b refactor working draft. Superseded by `.planning/phases/05-pipeline-automation/05-00-SUMMARY.md`. The earlier grep match `tests/unit/test_models_rpd_floor.py` actually refers to `phase5-00b-architecture-review.md` (different file), NOT this one — verified via second-pass grep. |
| `docs/phase5-00c-execution-report.md` | 6.0 KB | 2026-04-29 | Phase 5 wave 00c execution report. **No external references** — only self-references. Superseded by `.planning/phases/05-pipeline-automation/05-00c-SUMMARY.md` (the canonical sibling in `.planning/`). |

> NOTE: `docs/phase5-00b-architecture-review.md` is **NOT** in this bucket — it is referenced by `tests/unit/test_models_rpd_floor.py:8` and `:50` (test docstring + assertion message). Moved to bucket F.

---

## Bucket E — Temp fixtures / debug artifacts (DELETE)

All untracked or gitignored.

| File | Size | mtime | Evidence |
|---|---|---|---|
| `test/fixtures/gpt55_article/vision_probe_openrouter.json` | — | new | Untracked; output from a vision-cascade probe, not a fixture used by tracked tests. The dir's tracked fixtures are `article.md`, `benchmark_result.json`, `images/*`, `metadata.json`, `raw.html` — these probe outputs are extra. |
| `test/fixtures/gpt55_article/vision_probe_siliconflow.json` | — | new | Same as above. |
| `lightrag_storage_v2.0.tar.gz` | 10.2 MB | 2026-04-24 | 10 MB tarball backup of an old LightRAG storage from before the Phase 5 schema migration. Gitignored by `*.tar.gz`. No code reads it. |
| `batch_ingest_github.log` | 3.5 KB | 2026-04-24 | Old run log. Gitignored by `*.log`. |
| `cognee_batch.log` | 4.0 KB | 2026-04-24 | Old run log. Gitignored by `*.log`. |

---

## Bucket F — Uncertain (need user decision — NOT auto-deleting)

| File | Status | Why uncertain |
|---|---|---|
| `test_classifier_mock.py` (root) | tracked, Apr 27 | Looks like a one-off mock test at the wrong location (should be in `tests/`). No references found anywhere in tracked code. **But it was committed deliberately at some point.** Delete or move to `tests/`? |
| `test_cognee_article.py` (root) | tracked, Apr 27 | Same situation as above — one-off Cognee test at root. No references. Delete or move? |
| `test_mcp.py` (root) | tracked, Apr 22 | Standalone MCP-server probe with its own argparse (`python test_mcp.py`). Only self-references. Predates Phase 5. Likely superseded by `test_mcp_approaches.py` and the production MCP path in `ingest_wechat.py`. Delete? |
| `test_mcp_approaches.py` (root) | tracked, May 4 12:12 | **Recent** (May 4). Mentioned in `.planning/quick/260504-g7a-SUMMARY.md` as "MODIFIED (LDEV-10)". Could still be active research/probe. Keep or move to `scripts/`? |
| `wechat_articles_20260423.csv` (root) | tracked, 101 KB, Apr 27 | Old CSV dump of WeChat articles. Referenced in many docs (`KOL_*.md`, etc.) but no live code reads it. Looks like a one-time data export. Delete? Move to `data/`? |
| `entity_registry.json` (root) | tracked, 17 KB, Apr 24 | JSON data file at root. Possibly a runtime artifact accidentally committed. Looks like real data. Move to `data/` or keep at root? |
| `rules_engine.json` (root) | tracked, 29 KB, Apr 23 | Same situation as entity_registry — looks like a config / data file. May be live config. **Do not delete without checking what reads it.** |
| `tests/P1-TODO.txt` | tracked, Apr 22 | Old phase-1 TODO list, predates Phase 5. May still be operationally referenced. Delete or archive? |
| `docs/phase5-00b-architecture-review.md` | tracked, Apr 29 | Originally bucket D, but **`tests/unit/test_models_rpd_floor.py:8,50` references it** in docstring + assertion message. If we delete, those references become dangling. Either: (a) keep, (b) delete + update test references, (c) move ref into a tracked phase doc and then delete. |
| `docs/CTO-CEO_BRIEF.md` | tracked, Apr 28 | Executive summary from before v3.1 closure. No references. Looks superseded by current MILESTONE_v3.2_EXECUTION_REPORT, but it's an exec doc — user may want to retain for paper trail. |
| `docs/HERMES_PHASE5_WAVE0_PUNCH.md` | tracked, May 2 | Operator punch list for Phase 5 wave 0. Phase 5 long shipped. Referenced once by `.planning/phases/05-pipeline-automation/05-00-embedding-migration-and-consolidation-PLAN.md:805` ("operator runbook"). Could be deleted now that Phase 5 closed. |
| `docs/HERMES_V3.2_PUNCH_LIST.md` | tracked, May 1 | v3.2 milestone closed (per STATE.md). Referenced in `.planning/MILESTONE_v3.2_PLAN_PHASE_PROMPT.md`. May still be relevant historical record. |

---

## Hard constraints respected

- [x] No touches to `~/.hermes/` (not in repo)
- [x] No touches to `venv/`, `__pycache__/`, `.dev-runtime/`, `node_modules/`
- [x] No touches to `.planning/phases/XX-*/` contents (current phase dirs)
- [x] No "drive-by" formatting/refactor changes
- [x] All deletions go through `git rm` (tracked) or `rm` (untracked) — no trash/recycle
- [x] No deletions performed yet — proposal only

---

## Approval format

Reply with one of:

- `go all` — delete buckets C, D, E in order (3 separate commits)
- `go C` / `go D` / `go E` — delete only that bucket
- `skip <file>` — keep specific file from a "go" bucket
- `F: keep <file>, delete <file>` — resolve specific F items
- `stop` — abort, delete nothing

After each bucket commit, I will run `git status` and report.
