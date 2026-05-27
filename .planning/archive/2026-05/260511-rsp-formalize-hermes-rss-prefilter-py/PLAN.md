# Quick 260511-rsp — Formalize Hermes-authored `enrichment/rss_prefilter.py`

**Status**: ✅ Completed
**Date**: 2026-05-11
**Slug**: `rss-260511-rsp`

## Context

WIP audit (`.scratch/wip-audit-20260511.md` on Hermes, written by Hermes E quick) classified `enrichment/rss_prefilter.py` as **TRACK** (untracked, to commit) — sibling to `enrichment/rss_rescrape_bodies.py` which was already formalized in commit `e422615` (quick 260511-rsb).

This quick brings `rss_prefilter.py` byte-for-byte from production Hermes into git.

## Phase 0 reconnaissance findings

Evidence: `.scratch/g1-phase0-20260511-173639.log`

| Question | Answer |
|----------|--------|
| Does prod script exist? | ✅ Yes, `/home/sztimhdd/OmniGraph-Vault/enrichment/rss_prefilter.py` (189 lines, 6410 bytes) |
| sha256 | `a5e8f505a286e4842b7fbe307e3b7b70300369aa0e05976cd8e9b656a8771d0e` |
| Cron registered? | ❌ NO — verified all 11 active Hermes crons; no entry mentions `prefilter` |
| Hermes-side callers? | Only `test_prefilter_30.py` (also untracked, classified as **DEAD** by audit — "One-off 30-article prefilter test") |
| Local repo callers? | ❌ NONE (grep all `*.py / *.sh / *.md / *.yml` — 0 matches) |
| `rss_fetch.py` integration? | ❌ NO (grep `prefilter|batch_filter` against `~/OmniGraph-Vault/enrichment/rss_fetch.py` — 0 hits) |
| File age on Hermes | Created 2026-05-11 14:22 ADT (today) by user, audited same day |
| Audit verdict | **TRACK** ("part of RSS pipeline, not yet cron-wired") |
| Script docstring intent | "Callers INSERT only keep=true rows" — designed as pre-classification gate before RSS table insert |

## Decision tree → CASE B

- ❌ CASE A: Live + cron — no cron exists
- ✅ **CASE B: Live, no cron, blessed by audit** — script is intentional WIP, audit explicitly says TRACK, dependency `batch_classify_kol.get_deepseek_api_key` exists locally at `batch_classify_kol.py:125`
- ❌ CASE C: Dead — would require ignoring audit verdict; single test caller is itself flagged DEAD, and the script's purpose is articulated in its docstring as a planned RSS pipeline stage

**Decision**: Write byte-for-byte to local. NO cron edit. NO refactor. ONE atomic commit.

## Scope

**Files touched (3):**
- `enrichment/rss_prefilter.py` (new, +189 LOC, byte-equal from prod)
- `.planning/STATE.md` (1 row added to "Quick Tasks Completed", `stopped_at` + `last_activity` updated)
- `.planning/quick/260511-rsp-formalize-hermes-rss-prefilter-py/PLAN.md` + `SUMMARY.md` (planning artifacts, this directory)

**Out of scope (HARD):**
- ❌ NOT touching `rss_rescrape_bodies.py` (already in `e422615`)
- ❌ NOT touching `scripts/register_phase5_cron.sh` (no cron to register — would be speculative)
- ❌ NOT touching other untracked `enrichment/` files
- ❌ NOT touching `tests/unit/test_ainsert_persistence_contract.py` (gkw frozen)
- ❌ NOT refactoring or improving the script (commit-as-is, sha256-verified)
- ❌ NOT pulling `test_prefilter_30.py` from Hermes (audit classifies as DEAD)
- ❌ NO Hermes mutations (read-only SSH only)
