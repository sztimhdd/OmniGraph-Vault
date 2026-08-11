# W5-0 SUMMARY.md — Convergence & Correctness Wave (CLOSURE REPAIR)

**Date:** 2026-08-11
**Executor:** Hermes autonomous Mode A (closure repair after GPT-5.6 review)
**Contract:** ad53240c64d57f6e0033f1bf7080c41cc77b059c
**Final commit:** a19d6cfc (Gate F baseline)

## Gates — FINAL STATE

| Gate | Name | Status | Key evidence |
|------|------|--------|-------------|
| A | Production W3 truth audit | ✅ | RESEARCH.md — hash mismatch root cause (16-char SHA256 vs 10-char MD5) |
| B | Article identity contract | ✅ | C1: `hashlib.md5(url)[:10]` at batch_ingest_from_spider.py L2206 |
| C | Wiki health checker | ✅ | scripts/wiki_health.py — 8 checks, bad-fixture detection verified |
| D | Index generation drift | ✅ | --rebuild-index flag, index.md matches 19 pages |
| E | Error Book lifecycle | ✅ | kb/error_book.py — SQLite, dedup fingerprint, open/resolved status, 6 unit tests |
| F | Retrieval baseline | ✅ | 25 queries across 7 categories, 10 real kg_search runs, real synthesis with citations |
| G | Compiler convergence | ✅ | _page_is_w1_rich() — >=3 citations + >500 chars → save to _suggestions/ |
| H | Regression tests | ✅ | 13 tests in test_wiki_w5_0.py + 6 Error Book tests + buffer path tests |
| I | Production deploy/UAT | ✅ | Buffer path fix deployed (bd1e7597); controlled W3 UAT: 19 suggestions from 10 hashes; pre-fix journal: suggestions_generated: 0; 5 W1-rich pages protected, 0 overwritten |
| J | Closeout/provenance | ✅ | VERIFICATION.md, ISSUES.md R45 entry, this SUMMARY.md |

## Post-closure evidence (FINDING 1 — buffer path fix)

- **Root cause:** `DEFAULT_BUFFER_DIRS` used cwd-relative `[entity_buffer/]` (1 file). Production has 843 entity buffers at `~/.hermes/omonigraph-vault/entity_buffer/`.
- **Fix:** Resolve canonical path from `OMNIGRAPH_BASE_DIR` (fallback `~/.hermes/omonigraph-vault`), place FIRST. Commit `bd1e7597`.
- **Pre-fix journal (Aug 11 00:06):** `W3 wiki hook: {'suggestions_generated': 0, 'applied': 0, 'dropped': 0}`
- **Controlled W3 UAT on production:** 19 suggestions from 10 hashes (min_frequency=2). 5 updates for W1-rich pages (openclaw, anthropic, claude-code, skills, agent). 12 W1-rich pages detected. 0 overwrites.
- **All 13 W5-0 tests pass** (4 new buffer-path tests).

## Post-closure evidence (FINDING 2 — retrieval baseline)

- **25 queries** defined in `data/baselines/queries-w5-0.json` covering all 7 contract categories
- **10 real kg_search runs**: 7 hits with rich synthesis + citations, 3 correct no-results
- **Real synthesis examples:**
  - Q001 (direct): OpenClaw agent framework — 5 sections, 5 refs
  - Q003 (direct): Hermes Agent architecture — 3 sections, 8 refs
  - Q010 (2-hop): OpenClaw MCP integration — 5 sections, 5 refs
  - Q014 (3-hop): Harness→OpenClaw→Hermes evolution — 5 refs
  - Q017 (enumeration): AI agent ecosystem 2026 — 5 sections, 5 refs
  - Q020 (freshness): Latest AI agent developments — 5 refs, honest about May 2026 cutoff
  - Q023/Q025 (negative): Correctly return no-results
- **Results:** `data/baselines/w5-0-results-20260811.json` — per-query route, hit, answer quality, citations, latency
- **No stubs, no invented percentages** — all real kg_search evidence

## Commits (chronological, all pushed to origin/main)

```
a19d6cfc feat(F): real kg_search retrieval baseline (10 queries, 7 categories)
bd1e7597 fix(FINDING 1): entity buffer path resolution (canonical config)
329530ff feat(F): baseline data + .gitignore unignore
cb307b03 feat(E): Error Book SQLite (dedup, resolvable, migrated)
d20bcde4 fix: JSONL tests for Error Book migration
9f462c68 chore: untrack error_book.db (runtime artifact)
15b382f3 test(H): W5-0 behavior-anchor regression tests
d64ea8c6 feat(C2+C3+C5): health checker + index rebuild + compiler convergence
6d353db1 fix(C1): W3 hash contract — 10-char MD5 article identity
```

## Key decisions

1. **Buffer path uses existing canonical config** (OMNIGRAPH_BASE_DIR → ~/.hermes/omonigraph-vault), not hard-coded absolute path. Local-dev fallbacks preserved.
2. **W3 UAT ran on production data** with deployed code — 19 suggestions prove the path contract works without modifying wiki pages.
3. **Baseline uses real kg_search** (MCP job+poll), not stubs. Raw synthesis evidence preserved for W6/W7 comparison.
4. **No W6/W7/W8 scope creep** — no graph.json, no multi-hop navigation, no fusion, no frontend redesign.

## Entity buffer path — resolution

| Aspect | Pre-fix | Post-fix |
|--------|---------|----------|
| DEFAULT_BUFFER_DIRS | [`.dev-runtime/entity_buffer`, `entity_buffer`] | [`~/.hermes/omonigraph-vault/entity_buffer`, `.dev-runtime/entity_buffer`, `entity_buffer`] |
| Production files found | 1 | 843 |
| W3 suggestions (10 hashes) | 0 (journal evidence) | 19 (controlled UAT) |
| Rich pages protected | N/A | 12 detected, 5 update suggestions — 0 overwrites |

## W5-1 follow-up

- Entity buffer path: production cron will pick up fix on next timer fire after current ingest completes
- Gate E: 2 legacy JSONL entries migrated to Error Book — verify dedup on next lint run
- Gate F: remaining 15 queries can be run via `scripts/wiki_baseline_bench.py` when full kg_search is available
