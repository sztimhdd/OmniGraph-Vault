# aim-3-3 SUMMARY — kol_scan.db sync + Hermes jobs disable

plan_id: aim-3-3
phase: aim-3
status: complete
completed: 2026-05-24T21:32:00Z

## What was built

Final pre-cutover sync of `data/kol_scan.db` from Hermes to Aliyun, followed by disable
of all 13 Hermes ingest jobs in `~/.hermes/cron/jobs.json`. Ingest authority has
transferred from Hermes to Aliyun's systemd timers.

## Key artifacts

- `.planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-EVIDENCE.md` — consolidated
  cutover ledger (CUTOVER-02 part 1, CUTOVER-03, CUTOVER-05)
- commit `328246c`

## Execution summary

| Task | Result |
|------|--------|
| Task 1: Hermes SCP kol_scan.db to Aliyun | PASS — sha256 verified, file transferred successfully |
| Task 2: Agent SSH Aliyun verify | PASS — 1014 articles, sha256 match, mtime 21:25 UTC |
| Task 3: Hermes disable 13 jobs.json entries | PASS — all 13 enabled=False at 21:28:42Z |
| Task 4: Missed-window estimate | recorded — 11.5h window, ~10 articles |
| Task 5: CUTOVER-EVIDENCE.md commit | PASS — commit 328246c |

## Notable events

- **Cron race during SCP**: Afternoon ingest cron ran between Hermes baseline capture
  and SCP completion. Hermes-side sha256 changed between Step 1 and Step 4. Both sides
  verified consistent at SCP completion time — Aliyun received the more current copy
  (1014 articles vs 968 baseline). This is expected behavior; no data loss.

- **cutover_window_start**: `2026-05-24T21:28:42Z` — the canonical cutover timestamp.

- **§7 SC #2 trivially satisfied** (FINDING 2): Hermes crontab held no ingest entries
  pre-cutover; ingest lived in jobs.json only. Verified post-disable.

## Decisions

- Q1a accepted: ~10 estimated missed articles in the 11.5h window are not backfilled.
- FINDING 6 kol-enrich stub gap carried forward (not blocking).

## Next gate

aim-3-4 — journald sampling + DB write verification.
Resume at or after `2026-05-25T21:28:42Z` (≥ 24h post-cutover).
