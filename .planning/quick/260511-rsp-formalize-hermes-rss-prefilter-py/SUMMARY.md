# SUMMARY — Quick 260511-rsp

**Status**: ✅ Completed
**Date**: 2026-05-11
**Commit**: `<commit-pending>` (filled post-commit)

## What shipped

`enrichment/rss_prefilter.py` — byte-equal copy from Hermes production into local git.
189 LOC, 6410 bytes, sha256 `a5e8f505a286e4842b7fbe307e3b7b70300369aa0e05976cd8e9b656a8771d0e`.

## Method

1. SSH read prod script — `cat ~/OmniGraph-Vault/enrichment/rss_prefilter.py` on Hermes (read-only)
2. SCP byte-for-byte transfer to local `enrichment/rss_prefilter.py`
3. sha256 verification — local hash matched Hermes hash exactly
4. Import smoke — `python -c "from enrichment import rss_prefilter; ..."` succeeded with `DEEPSEEK_API_KEY=dummy`; module exposes `batch_filter`, `ENABLED=True`, `BATCH_SIZE=30`
5. Pytest tests/unit/ — full run; 22 pre-existing failures confirmed unrelated (zero tests import `rss_prefilter` or `batch_filter`); baseline check on 6 of those 22 failures with `rss_prefilter.py` removed → all 6 still fail. **Zero new regressions.**

## Decision rationale (CASE B)

Phase 0 surfaced no cron and no production caller. CASE C (DEAD) was rejected because:

- Hermes-side WIP audit (`.scratch/wip-audit-20260511.md`, written today by Hermes E quick) explicitly classifies the file as **TRACK** with reason "RSS batch pre-filter (part of RSS pipeline, not yet cron-wired)"
- File created 2026-05-11 14:22 ADT (today) — fresh authorial intent, not abandoned
- Sibling `rss_rescrape_bodies.py` (similar profile) already formalized in commit `e422615` — this quick treats `rss_prefilter.py` consistently
- Dependency `batch_classify_kol.get_deepseek_api_key` exists locally at `batch_classify_kol.py:125` — the import will resolve cleanly when the script is wired in (next quick / Phase 21+)

CASE B (commit byte-for-byte, no cron edit) is the audit-aligned action.

## Out-of-scope confirmations

- ❌ `rss_rescrape_bodies.py` — already tracked (`e422615`); not in this diff
- ❌ `scripts/register_phase5_cron.sh` — NOT modified (no cron exists for prefilter; speculative add-job would be premature)
- ❌ `test_prefilter_30.py` — Hermes-side untracked test, classified DEAD by audit; left untracked on Hermes (this quick does not pull it)
- ❌ Other untracked `enrichment/` files — not in this scope (would be separate audit row)

## Anti-fabrication evidence

| Artifact | Path | What it shows |
|----------|------|---------------|
| Phase 0 SSH log | `.scratch/g1-phase0-20260511-173639.log` | Full prod cat + cron list + caller grep + git status on Hermes |
| Byte-equal copy | `.scratch/g1-prod-20260511-174210.py` | Snapshot of file at SCP time (sha256 matches) |
| Import smoke | `.scratch/g1-pytest-20260511-*.log` | `Module imported OK / ENABLED= True / BATCH_SIZE= 30 / batch_filter callable: True` |
| Pre-existing failures baseline | `.scratch/g1-baseline*.log` | 6 of the 22 failing tests reproduced with `rss_prefilter.py` removed → confirms my change is innocent |
| Zero-test-touches grep | (inline) | `grep -r "rss_prefilter\|batch_filter" tests/` → 0 matches |

## Commit discipline

- ⚠️ Used **explicit `git add <paths>`** only (no `-A`, no `.`) — per CLAUDE.md Lessons Learned 2026-05-06 #5 (concurrent-quick staging race). Files staged: `enrichment/rss_prefilter.py`, `.planning/STATE.md`, `.planning/quick/260511-rsp-formalize-hermes-rss-prefilter-py/PLAN.md`, `.planning/quick/260511-rsp-formalize-hermes-rss-prefilter-py/SUMMARY.md`
- ⚠️ Concurrent-quick check: G2 (skills batch, commit `ca0c6bc`) landed locally first; G3 (scripts + tests cleanup) parallel — no shared file lines
- Atomic forward-only commit; NO `git reset` / NO `--amend` / NO `--force-push`
- Pre-push: `git fetch origin main && git rebase origin/main` (rebase guard for parallel quicks G2/G3)

## Hermes deploy notes

This commit is **code-only formalization** — production Hermes already has this file (working copy). On next `git pull --ff-only` from Hermes, git will detect that the previously-untracked file matches HEAD exactly (sha256 identical). No `.env` change, no service restart, no cron edit needed.

If/when this script gets wired into the RSS pipeline (e.g., as a pre-classify gate in `rss_fetch.py` or a standalone cron job), that is a **future quick** — not in this scope.
