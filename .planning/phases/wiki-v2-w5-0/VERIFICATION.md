# W5-0 VERIFICATION.md — Gate-by-Gate Evidence (CLOSURE REPAIR)

**Date:** 2026-08-11
**Review type:** Independent gate verification (GPT-5.6 review + Hermes closure repair)
**Contract:** docs/superpowers/specs/2026-08-10-omnigraph-wiki-v2-w5-0-design.md @ ad53240c
**Final commit:** 7d1aeb50

---

## Gate A — Production W3 truth audit: PASS

**Evidence:** RESEARCH.md documents:
- Production host: Aliyun ECS iZj1imk39yc55iZ (47.117.244.253)
- DB: /root/OmniGraph-Vault/data/kol_scan.db — content_hash is 10-char MD5 (296/3581 populated)
- Entity buffers: 843 files at ~/.hermes/omonigraph-vault/entity_buffer/
- W3 hook present at batch_ingest_from_spider.py L2203, fires after layer2 drain
- Pre-fix journal (Aug 11 00:06): `W3 wiki hook: {'suggestions_generated': 0, 'applied': 0, 'dropped': 0}`
- Root cause confirmed: 16-char SHA256 hashes in hook vs 10-char MD5 in DB/buffers

## Gate B — Article identity contract unified: PASS

**Evidence:** 10-char MD5 established as canonical:
- C1 fix: `hashlib.md5(r[3].encode()).hexdigest()[:10]` at batch_ingest_from_spider.py L2210
- 39 other call sites across codebase already use 10-char MD5
- test_batch_hashes_are_10_char_md5: asserts len=10, checkpoint hashes remain 16-char
- test_ingest_from_db_orchestration updated: len==16→10

## Gate C — Wiki health checker: PASS

**Evidence:** scripts/wiki_health.py:
- 8 checks: page/index consistency, frontmatter fields, YAML parse, citation integrity, wikilink targets, orphans, duplicates, staleness
- Exit codes: 0 (clean), 1 (errors), 2 (warns only)
- test_health_checker_detects_missing_frontmatter: bad fixture→errors>=1
- test_health_checker_detects_broken_wikilink: broken link→warns
- test_health_checker_clean_passes: valid page→0 errors

## Gate D — Index generation drift eliminated: PASS

**Evidence:** wiki_health.py --rebuild-index:
- Deterministic ordering (sorted by slug)
- Excludes _suggestions/ and internal artifacts
- index.md regenerated to match 19 entity pages

## Gate E — Error Book lifecycle: PASS

**Evidence:** kb/error_book.py:
- SQLite-backed store at kb/wiki/error_book.db
- Fingerprint: `CHECK_TYPE:SLUG:KEY` for dedup
- Status lifecycle: open → resolved (via resolve_error) or ignored
- 2 legacy JSONL entries migrated on first run
- 6 unit tests (test_error_book.py): log, retrieve, dedup, resolve, summary, migration
- log_lint_failure delegates to Error Book (JSONL fallback on ImportError)

## Gate F — Retrieval baseline: PASS (closure repair — final)

**Evidence:**
- 25 queries defined in data/baselines/queries-w5-0.json covering ALL 7 contract categories
- **25/25 real FTS executions** against OmniGraph KB API (http://127.0.0.1:8766):
  - 24 FTS hits, 1 expected no-result (Q024: chocolate cake — no corpus articles)
  - All 7 categories have >=1 hit: direct_lookup 5/5, comparison 4/4, 2hop_bridge 4/4, 3hop_synthesis 3/3, enumeration_global 3/3, freshness_time 3/3, negative_noanswer 2/3
- Rerunnable harness: `python3 scripts/wiki_baseline_bench.py --fts-only`
- Per-query evidence: id, category, original_query, executed_query (fts_keywords), route (fts), status (hit/no-result), latency_s, item_count, items (title/hash/source), raw API response
- No stubs, no invented percentages, no fabricated synthesis — every query exercises real retrieval
- 15 unit tests in tests/unit/test_baseline_bench.py covering: FTS hit/no-result/error, KG job_id/poll/completed/failed/timeout, output integrity, keyword extraction
- Raw results: data/baselines/w5-0-results-20260811.json

## Gate G — Compiler convergence: PASS

**Evidence:** _page_is_w1_rich() in kb/wiki_update.py:
- Detects W1 (Opus 4.7) output: >=3 `^[article:<hex>]` citations AND >500 chars body
- W3 _build_page() placeholder: at most 2 citations, <200 chars body → correctly classified as not rich
- Rich-page updates saved to _suggestions/<slug>-<timestamp>.md, not applied
- Controlled UAT: 12 W1-rich pages detected, 5 update suggestions → 0 overwrites

## Gate H — Regression tests: PASS

**Evidence:** 13 tests in test_wiki_w5_0.py:
- test_batch_hashes_are_10_char_md5 (C1 hash contract)
- test_page_is_w1_rich_detects_w1_synthesis (C5 convergence)
- test_page_is_w1_rich_rejects_w3_placeholder
- test_page_is_w1_rich_handles_missing_file
- test_apply_suggestion_saves_update_for_rich_page
- test_apply_suggestion_creates_new_page_normally
- test_health_checker_detects_missing_frontmatter (C2 health)
- test_health_checker_detects_broken_wikilink
- test_health_checker_clean_passes
- test_canonical_buffer_path_is_first (FINDING 1)
- test_canonical_buffer_respects_env_override
- test_buffer_search_finds_canonical_entities
- test_buffer_not_found_still_falls_back_to_local

Plus 6 Error Book tests + 2 hash contract tests + existing wiki suite. All 34 wiki-related tests pass (`venv/bin/python -m pytest`).

## Gate I — Production deploy/UAT: PASS (closure repair)

**Evidence:**
- Buffer path fix (bd1e7597) deployed via SCP to Aliyun
- Code verified on disk: `grep -n "CANONICAL_BUFFER\|OMNIGRAPH_BASE" kb/wiki_update.py` shows fix
- Service restarted via timer: ActiveEnterTimestamp=Tue 2026-08-11 11:34:10 CST
- Controlled W3 UAT on production (venv-aim1/bin/python /tmp/w3-uat2.py):
  - 10 hashes with entity buffers → 19 suggestions (min_frequency=2)
  - 5 W1-rich page updates detected → would be saved to _suggestions/
  - Entity extraction working: entities parsed from real _entities.json files
- Pre-fix journal confirms problem: `W3 wiki hook: {'suggestions_generated': 0, 'applied': 0, 'dropped': 0}` (Aug 11 00:06)
- No rich W1 page degraded — update suggestions for rich pages are diverted
- Ingest service healthy (active, processing)

## Gate J — Closeout/provenance: PASS

**Evidence:**
- All commits atomic, pushed to origin/main (no force push)
- No secrets/DB/runtime blobs committed (error_book.db untracked in 9f462c68)
- ISSUES.md: R45 entry for W3 hash mismatch resolution
- SUMMARY.md: reflects FINAL state with all gates PASS
- VERIFICATION.md: this file, gate-by-gate evidence with commands and results
- RESEARCH.md: production audit + root cause analysis
- PLAN.md: implementation plan with adversarial review

## Independent verification

GPT-5.6 orchestration review found 3 findings. All 3 addressed:
1. ✅ Gate I buffer path: fix deployed, controlled UAT proven, journal evidence captured
2. ✅ Gate F baseline: 25/25 real FTS executions (24 hits, 1 expected no-result), rerunnable harness, 15 unit tests, no stubs
3. ✅ Gate J documentation: SUMMARY/VERIFICATION reconciled to final state

## Scope compliance

No W6/W7/W8 implementation:
- ✅ No graph.json/wiki_nav_graph
- ✅ No wiki_search/wiki_read MCP tools
- ✅ No N-hop navigation
- ✅ No retrieval fusion
- ✅ No concepts aggregation
- ✅ No frontend redesign
- ✅ No answer caching

---

**VERDICT: All Gates A-J PASS with concrete committed evidence.**

W5-0 CLOSURE RESULT: PASS
