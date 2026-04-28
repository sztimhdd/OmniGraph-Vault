# Phase 6 — Graph Seed Runbook (Executed 2026-04-28)

## Pre-conditions

- Plan 01 complete: graphify skill installed on remote
- T1 repos cloned under ~/.hermes/omonigraph-vault/graphify/repos/
- .graphifyignore written (node_modules, dist, tests, docs, extensions, apps, Swabble, ui, scripts excluded)
- Backup Gemini key used (embedding quota: 0/1,000 RPD, 0/100 RPM at start)

## Procedure (executed)

1. Updated .graphifyignore to exclude non-core openclaw dirs (extensions/, apps/, Swabble/, ui/, scripts/)
2. Detected: 4,687 files · ~2,692,482 words (4,495 code + 192 docs)
3. Part A (AST extraction): 4,495 code files → tree-sitter → 28,441 nodes, 91,861 edges (no API cost)
4. Part B (Semantic extraction): 48 priority doc files (README.md, AGENTS.md, CLAUDE.md, etc.) → Gemini 2.5-flash-lite
   - 17 succeeded (191 nodes, 196 edges)
   - 31 skipped due to 429/503 (flash-lite 20 RPD exhausted; 503 server overload on some calls)
5. Merged AST + semantic → build → community detection
6. Output: graph.json (41.8 MB), GRAPH_REPORT.md written

## Verification

- graphify-out/graph.json present: yes
- Node count: 28,459
- Edge count: 88,568
- Communities: 1 (community detection returned single cluster — likely due to graph structure; re-run with tuned parameters)
- GRAPH_REPORT.md present: yes
- File size: 41.8 MB

## Deviations from plan

- Semantic extraction ran on 48 priority docs instead of all 192 — non-priority skill SKILL.md files deferred to `graphify update`
- Community detection needs re-run with correct parameter mapping (all nodes assigned to community -1)
- Backup key exhausted flash-lite 20 RPD quota during semantic pass; primary key availability would have increased throughput

## Reproducibility notes

- Working directory: ~/.hermes/omonigraph-vault/graphify
- T1 repos: openclaw/openclaw (core src/ only) + anthropics/claude-code
- .graphifyignore excludes: node_modules, dist, test*, fixtures, vendor, extensions, apps, Swabble, ui, scripts, docs, images
- AST extraction is deterministic and fast (~90s for 4,495 files) — no API cost
- Semantic extraction uses Gemini 2.5-flash-lite (20 RPD) — consider using flash (250 RPD) or spreading across multiple keys
- Resume from cache: semantic cache stored in graphify-out/cache/
