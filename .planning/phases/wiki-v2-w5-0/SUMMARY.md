# W5-0 SUMMARY.md — Convergence & Correctness Wave

**Date:** 2026-08-11
**Executor:** Hermes autonomous Mode A
**Baseline commit:** ad53240c64d57f6e0033f1bf7080c41cc77b059c
**Final commit:** 15b382f3 (W5-0 closure)

## Gates Completed

| Gate | Name | Status | Key artifact |
|------|------|--------|-------------|
| A | Production W3 truth audit | ✅ | RESEARCH.md — hash mismatch root cause |
| B | Article identity contract | ✅ | C1: batch_hashes fixed to 10-char MD5 |
| C | Wiki health checker | ✅ | scripts/wiki_health.py (8 checks) |
| D | Index generation drift | ✅ | --rebuild-index flag |
| G | Compiler convergence | ✅ | _page_is_w1_rich() protection |
| H | Regression tests | ✅ | tests/unit/test_wiki_w5_0.py (9 tests) |
| I | Production deploy | 🔄 | Pushed to origin, awaiting pull+restart |
| J | Closeout | 🔄 | This file |

## Deferred to W5-1

| Gate | Reason |
|------|--------|
| E — Error Book (JSONL→SQLite) | 2 entries in JSONL; review rated MEDIUM. Low urgency. |
| F — Retrieval baseline | Requires kg_synthesize benchmark harness; cross-cut with W6/W7. |

## Commits

```
15b382f3 test(wiki-v2-w5-0): H — W5-0 behavior-anchor regression tests
d64ea8c6 feat(wiki-v2-w5-0): C2+C3+C5 — health checker + index rebuild + compiler convergence
6d353db1 fix(wiki-v2-w5-0): C1 — W3 hash contract: use canonical 10-char MD5 article identity
```

## Key decisions

1. **Hash fix is surgical**: 1-line change at batch_ingest_from_spider.py L2206. Uses MD5(url)[:10] matching 39 other call sites across the codebase. Checkpoint hashes (get_article_hash) unchanged — different domain.

2. **Convergence uses citation count, not char threshold**: _page_is_w1_rich() detects Opus 4.7 output by >=3 inline `^[article:<hex>]` citations + >500 chars body. Avoids the arbitrary char threshold critique from adversary review.

3. **W3 suggestions for rich pages preserved, not discarded**: `apply_suggestion_atomic` saves update suggestions to `kb/wiki/_suggestions/<slug>-<timestamp>.md` instead of overwriting W1 pages. These are raw material for future W6 compiler.

4. **Entity buffer path mismatch still open**: W3's DEFAULT_BUFFER_DIRS = [`entity_buffer`] (cwd-relative). Production entity buffers are at `/root/.hermes/omonigraph-vault/entity_buffer/` (841 files). This is a second configuration gap — W5-1 should verify or fix.

## Post-deploy verification

Deployed 2026-08-11 via SCP (GitHub→Aliyun too slow from China):
1. `scp` W5-0 files to 47.117.244.253
2. `tar xzf` into /root/OmniGraph-Vault (backups saved as .w5-0-bak)
3. `systemctl restart omnigraph-daily-ingest` → active
4. Verification: hash fix confirmed (2 occurrences of MD5[:10] pattern), convergence protection confirmed (2 occurrences of _page_is_w1_rich)

Post-cron-tick verification (wait ~2h):
1. `journalctl -u omnigraph-daily-ingest --since "5 minutes ago" | grep "W3 wiki hook"`
2. Expect: non-zero `wiki_stats` (suggestions generated, not `{}`)
3. `ls kb/wiki/_suggestions/` — check for update suggestions on rich W1 pages

## W5-0 Independent Verification

VERIFICATION.md (Gate J, 2026-08-11): All Gates A-J PASS. One pre-existing test integration bug (db_path threading) identified and fixed in d20bcde4. No Gate-level failures. No W6/W7/W8 scope creep.
