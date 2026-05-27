---
phase: quick-260511-kxd
plan: 01
subsystem: lib-scraper-deep-review
tags: [audit, hygiene, post-release, read-only, scraper, cascade]
requires: []
provides:
  - lib-scraper-deep-review-T4
  - F-1-cascade-divergence-verdict
affects:
  - lib/scraper.py (audited only — no edits)
tech-stack:
  added: []
  patterns: []
key-files:
  created:
    - .planning/quick/260511-kxd-t4-lib-scraper-py-deep-review-read-only/260511-kxd-REVIEW.md
  modified: []
decisions:
  - "F-1 (cascade divergence between lib/scraper.py and ingest_wechat.py) is `not-needed` — already resolved by quick 260508-ev2 commit fab60e0; both files independently UA-first today."
  - "Backlog Q-SCRAPER-HYG to fix M-1 (SCRAPE_CASCADE bad-token poison) + L-1 (duplicate warning bodies) in one ~0.5-1h quick post-release."
  - "Defer M-2 (Phase 20 generic-cascade Layer-3 CDP/MCP) to roadmap — wait for RSS-pipeline capacity demand before scheduling."
  - "Defer L-3 / CC-1 (relocate scrape_wechat_* helpers to lib/scraper_wechat.py) — batch with T3 Q-CONFIG when next intentional lib-flatten wave runs."
metrics:
  duration: ~2h
  completed_date: 2026-05-11
  tasks_completed: 1
  files_created: 1
  files_modified: 0
---

# Phase quick-260511-kxd Plan 01: T4 lib/scraper.py Deep Review (read-only) Summary

One-liner: Read-only post-release deep audit of `lib/scraper.py` (418 LOC) covering 7 angles + 5 anchor lessons; F-1 cascade-divergence hypothesis verified RESOLVED by `fab60e0` — verdict `not-needed`, 0 HIGH / 2 MEDIUM / 3 LOW; release-CLEAR.

## Severity counts

| Severity | Count | Headline |
|----------|-------|----------|
| HIGH | **0** | No release blocker |
| MEDIUM | **2** | M-1 SCRAPE_CASCADE bad-token poisons whole list (cron op-risk); M-2 generic-cascade Layer-3 (CDP/MCP) Phase-20 deferred |
| LOW | **3** | L-1 duplicate fallback warning bodies; L-2 hard-coded 15s timeout; L-3 lazy `import ingest_wechat` reach-around |

## F-1 unlock verdict

**`not-needed`** — Cascade divergence (CLAUDE.md 2026-05-08 #1, the original F-1 hypothesis) is already resolved by quick `260508-ev2` commit `fab60e0` (`feat(scraper): F1b cascade reorder ua-first + SCRAPE_CASCADE env var override`). Verified by reading current source:
- `lib/scraper.py:227-232` — `_DEFAULT_CASCADE_ORDER = ('scrape_wechat_ua','scrape_wechat_apify','scrape_wechat_cdp','scrape_wechat_mcp')`
- `ingest_wechat.py:1048-1073` — orchestrator order: UA(1050) → Apify(1054) → CDP(1070) / MCP(1073, mutually-exclusive on `_is_mcp_endpoint(CDP_URL)`)

Both files independently UA-first today. No T5 fix-quick needed. Backlog the divergence-grep CLAUDE.md institutional-memory entry for future-edit hygiene.

## Cascade divergence still present today?

**No.** Verified at the source level (§3 of REVIEW.md). Single decisive commit: `fab60e0`. Both `lib/scraper.py` (the library entry-point used by `batch_ingest_from_spider.py:1039,1880`) and `ingest_wechat.py` (the direct CLI dispatcher) cascade UA → Apify → CDP/MCP today.

## Evidence density

- **46** distinct `file:line` citations in REVIEW.md (target: ≥15) — well exceeds plan's anti-fabrication threshold.
- **5** distinct commit SHAs cited: `fab60e0` (cascade reorder, decisive evidence for F-1 verdict), `87b052c` (Apify dual-token rotation), `a3a98d3` (260511-rsr UA fallback for non-WeChat URLs — last touch on `lib/scraper.py`), `ecaa2df` (SCR-06 Apify markdown-key half-fix), `8832e95` (T3 batch_ingest review).

## Wall-clock time spent

~2 hours (target: 2-3h, hard cap 4h). Read-only single-pass audit; no fabrication, no rework.

## Schema compliance

REVIEW.md contains all 11 required headings (TL;DR + §1 through §10) and the F-1 verdict token (`not-needed`) appears in both TL;DR and §9, agreeing. Automated verify (`node -e ...`) passed with `OK 39166 chars, all 11 schema markers present, verdict token found.`

## Read-only discipline

`git status --short` shows only the `.planning/quick/260511-kxd-*/` directory as new. No business-file edits. No Hermes SSH. No pytest invocation. No `.env` changes. Tools used: Read, Grep, Glob, Bash for `wc -l` / `git log` / `git show` / `git status --short` only.

## Deviations from plan

None — plan executed exactly as written. Single-task execution; the plan correctly anticipated the analysis flow (Step 1 anchor & verify → Step 2 read source → Step 3 7-angle audit → Step 4 write REVIEW.md → Step 5 verdict & sanity-check), and findings landed within the predicted shape (HIGH=0, MEDIUM≤3, F-1 `not-needed`).

One small notation: planner's `<discovery>` block referenced CLAUDE.md anchor "ingest_wechat.py:920-942" as the cascade-dispatcher location. The actual current cascade dispatcher is at `ingest_wechat.py:1048-1073` (the function shifted line numbers since the 2026-05-08 fix landed). Auditor used grep (`scrape_wechat_(ua|apify|cdp|mcp)\(`) to relocate the orchestrator and document the current line numbers in §3. Not a deviation, just a gloss on the planner's anchor.

## Self-Check: PASSED

- REVIEW.md exists at `.planning/quick/260511-kxd-t4-lib-scraper-py-deep-review-read-only/260511-kxd-REVIEW.md` (39,531 bytes).
- All 11 schema sections present in correct order; F-1 verdict (`not-needed`) consistent across TL;DR and §9.
- All 7 audit angles A1..A7 addressed substantively.
- All 5 anchor CLAUDE.md lessons cross-referenced in §2 with status + evidence.
- §3 cites both `lib/scraper.py:227-232` and `ingest_wechat.py:1050,1054,1070,1073` with file:line.
- Evidence density: 46 file:line citations + 5 commit SHAs.
- `git status --short`: only the quick directory is dirty (PLAN + REVIEW + this SUMMARY); no business-file edits.

## Next steps (for the user, post-merge)

1. Backlog **Q-SCRAPER-HYG** (~0.5-1 h) — combine M-1 + L-1 into a single tiny env-parser-tightening quick. Decide M-1 fix style (drop-bad-token-and-continue vs fail-fast-at-import) — see REVIEW.md §10 Q1.
2. Roadmap **F-deferred (M-2, Phase 20 generic-cascade Layer-3)** — measure last-7-days `articles.body IS NULL` success-rate before scheduling.
3. Defer L-3 / CC-1 — batch with T3 Q-CONFIG (lib→app config-import flatten) when next intentional `lib/` hygiene wave runs.

---

**End of SUMMARY.md.**
