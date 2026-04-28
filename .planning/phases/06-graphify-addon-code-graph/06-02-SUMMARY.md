---
plan: 06-02
phase: 06-graphify-addon-code-graph
wave: 3
status: complete
completed: 2026-04-28
---

# Plan 06-02 Summary — Graph Seed via Hermes

## Outcome: PASS

Graph seed executed by Hermes on the remote PC following `docs/testing/06-graph-seed-task.md`.

## Results

| Metric | Value |
|--------|-------|
| graph.json present | yes (41.8 MB) |
| Node count | **28,459** |
| Edge count | 88,568 |
| Communities | 1 (community detection returned single cluster — all assigned community -1; needs re-run with tuned params) |
| GRAPH_REPORT.md present | yes |

Node count 28,459 >> 100 minimum. REQ precondition met for Plan 06-04 cron.

## Procedure summary (from runbook)

1. `.graphifyignore` updated to exclude additional openclaw non-core dirs (extensions/, apps/, Swabble/, ui/, scripts/)
2. File detection: 4,687 files · ~2,692,482 words (4,495 code + 192 docs)
3. Part A — AST extraction: 4,495 code files → tree-sitter → 28,441 nodes, 91,861 edges (no API cost, ~90s)
4. Part B — Semantic extraction: 48 priority docs → Gemini 2.5-flash-lite; 17 succeeded (191 nodes, 196 edges); 31 skipped (429/503 — backup key 20 RPD exhausted)
5. Merged AST + semantic → community detection → graph.json written

Wall-clock time: not recorded in runbook; estimated ~30–60 min based on 17 successful LLM calls.

## Deviations

- Semantic pass ran on 48 priority docs, not all 192 (non-priority SKILL.md files deferred to `graphify update`)
- Community detection returned single cluster (community -1) — all AST nodes treated as one community; needs re-run with corrected parameters. Does NOT block demos — graph.json is queryable.
- Backup Gemini key used (primary key RPD not available at time of run); 20 RPD exhausted on flash-lite. Use primary key or flash (250 RPD) for future runs.

## Acceptance Criteria

- [x] `docs/testing/06-graph-seed-runbook.md` exists, 43 lines (≥ 30)
- [x] `grep -q "/graphify" docs/testing/06-graph-seed-runbook.md` — PASS
- [x] Node count ≥ 100 in runbook — 28,459 ✓
- [x] Remote `graph.json` has 28,459 nodes, 88,568 edges — confirmed via SSH
- [x] `GRAPH_REPORT.md` present on remote
- [x] No credentials/hostnames in runbook

## Notes for Plan 06-04 (cron)

- `graphify update .` (AST-only refresh) will be fast: no LLM cost, reuses cache
- Community detection issue should resolve on next full build with corrected Leiden parameters
- Primary Gemini key should be used for future semantic passes (higher RPD)
