# Phase 6 — Graph Seed Runbook (Executed 2026-04-28)

## Pre-conditions

- Plan 01 complete: graphify skill installed on remote
- T1 repos cloned under ~/.hermes/omonigraph-vault/graphify/repos/
- .graphifyignore written (node_modules, dist, tests, extensions, apps, Swabble, ui, scripts excluded)
- Backup Gemini key used for semantic pass (embedding quota: 0/1,000 RPD fresh)

## Procedure (executed)

1. Strengthened .graphifyignore → 4,687 files · ~2,692,482 words
2. Part A (AST): 4,495 code files → tree-sitter → 28,441 nodes, 91,861 edges (no API cost)
3. Part B (Semantic): 8 core architecture docs → Gemini 2.5-flash + 3.1-flash-lite
   - VISION.md: 6n/5e
   - SECURITY.md: 8n/8e  
   - CONTRIBUTING.md: 8n/0e
   - AGENTS.md, README.md, CLAUDE.md (from earlier pass): 185n/191e
   - Total semantic: 207 nodes, 204 edges
4. Model switch mid-run: 3.1-flash-lite-preview → 2.5-flash (3.1 experienced 503 overload)
5. Merged AST + semantic → build → 28,475 nodes, 88,576 edges

## Verification

- graphify-out/graph.json present: yes
- Node count: 28,475
- Edge count: 88,576
- Communities: 0 (community detection failed on node ID format — graph data intact, fix deferred)
- GRAPH_REPORT.md present: yes
- File size: 41.8 MB

## Deviations from plan

- Semantic extraction scoped to 8 core architecture docs (not all 192) — Rust fork CTO doesn't need 170+ individual skill SKILL.md files
- 3.1-flash-lite-preview hit 503 overload → switched to 2.5-flash for remaining docs
- Community detection returned empty set (node ID hashability issue) — graph structure is valid, re-clustering can be done post-hoc

## Lessons Learned

- 2.5-flash-lite (20 RPD) is unsuitable for batch workloads — use 2.5-flash (250 RPD) or 3.1-flash-lite-preview (1,500+ RPD)
- 3.1-flash-lite-preview is fast but experiences 503 spikes during high demand
- AST extraction (tree-sitter) is the heavy lifter — 28K nodes from 4.5K files with zero API cost
- Semantic pass on 8 core docs is sufficient for architectural understanding; 170+ skill files add noise

## Reproducibility notes

- Working directory: ~/.hermes/omonigraph-vault/graphify
- T1 repos: openclaw/openclaw (core src/) + anthropics/claude-code
- .graphifyignore: node_modules, dist, test*, fixtures, vendor, extensions, apps, Swabble, ui, scripts, docs, images
- AST: `graphify.extract.extract()` on detected code files (~90s for 4,495 files)
- Semantic: Gemini generate_content on individual .md files, 3s inter-call delay
