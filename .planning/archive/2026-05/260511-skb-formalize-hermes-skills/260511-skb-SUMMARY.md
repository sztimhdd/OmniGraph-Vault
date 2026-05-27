---
phase: quick-260511-skb
type: docs
status: complete
files_modified:
  - skills/omnigraph_ingest/SKILL.md
  - skills/omnigraph_scan_kol/SKILL.md
  - skills/omnigraph_scan_kol/references/session-refresh.md
files_added:
  - skills/omnigraph_ingest/references/cron-failure-timeline.md
  - skills/omnigraph_ingest/references/cron-monitor-example-20260509.md
  - skills/omnigraph_ingest/references/cron-normal-run-20260510.md
  - skills/omnigraph_ingest/references/db-schema.md
  - skills/omnigraph_ingest/references/h09-smoke-test.md
  - skills/omnigraph_ingest/references/lightrag-health-check.md
  - skills/omnigraph_ingest/references/manual-catch-up-batch.md
  - skills/omnigraph_ingest/references/mystery-row-cleanup.md
  - skills/omnigraph_ingest/references/reconcile-canary.md
  - skills/omnigraph_ingest/references/rss-pipeline-investigation.md
  - skills/omnigraph_ingest/references/scraper-coverage-matrix.md
  - skills/omnigraph_ingest/scripts/daily_ingest_monitor.py
  - skills/omnigraph_query/references/search-discipline.md
  - skills/omnigraph_scan_kol/references/account-login-flow.md
  - skills/omnigraph_scan_kol/references/cron-session-diagnostics.md
---

# Quick 260511-skb — Formalize Hermes-authored skills/ knowledge

## Goal

Pull Hermes-authored operational knowledge under `skills/` into the local repo
byte-for-byte and ship as a single atomic commit. WIP audit (.scratch/wip-audit-202605...)
classified all 18 in-scope files as TRACK ("有价值的运维知识").

## Scope

- 11 new reference docs under `skills/omnigraph_ingest/references/` (cron timelines,
  smoke tests, cleanup runbooks, schema / health-check / coverage matrices)
- 1 new monitor script `skills/omnigraph_ingest/scripts/daily_ingest_monitor.py` (108 LOC)
- 3 new single-doc references (search-discipline, account-login-flow, cron-session-diagnostics)
- 3 modified existing files (2 SKILL.md + session-refresh.md)

Total: 18 files, ~1,685 LOC.

## Method

Phase 0 SSH inventory + tar-pipe transfer from Hermes:

```
ssh hermes 'cd ~/OmniGraph-Vault && tar -cf - <files>' | tar -xvf -
```

Byte-equality verified via `sha256sum` diff (.scratch/local-sha-norm.txt vs
.scratch/hermes-sha-norm.txt) — 18/18 hashes match.

Evidence: .scratch/g2-phase0-20260511-173747.log (file inventory),
.scratch/g2-tar-extract-20260511-173747.log (transfer log),
.scratch/g2-checksums-20260511-173747.log (sha256 verification).

## Verification

- `git diff --stat origin/main..HEAD -- skills/` matches 18-file expected set
- `wc -l` totals match Hermes (1,685 LOC)
- `pytest tests/unit/` unchanged (skills/ docs aren't in pytest scope)
- `git add` used explicit paths only (no `git add -A` — see CLAUDE.md Lesson 2026-05-06 #5)

## Out of scope

- No content refactor (byte-equal copy only)
- No SKILL.md frontmatter / metadata schema edits
- No `enrichment/` (G1 scope)
- No `scripts/` root or `tests/` (G3 scope)
- No new skills, only formalize existing
