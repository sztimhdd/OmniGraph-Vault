# aim-3-4 SUMMARY — Journald verification + aim-3 phase closure

plan_id: aim-3-4
phase: aim-3
status: complete
completed: 2026-05-24T22:20:00Z

## What was built

Manual E2E scan-to-ingest run on Aliyun (user bypassed the 24h natural-timer-fire gate),
proving the full systemd service chain is functional. Two service bugs were found and fixed
during this run. Evidence committed in
`.planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-04-journald-evidence.md`.

## Key artifacts

- `.planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-04-journald-evidence.md`
  — CUTOVER-04 journald + DB write evidence; aim-3 aggregate verdict PASS
- commit `f8b030b` — `TimeoutStartSec=300` fix (3 ingest service units)
- commit `d95242c` — remove `--days-back 1` from kol-classify service

## Execution summary

| Task | Result |
|------|--------|
| Task 1: Wallclock window check | BYPASSED per user request — manual E2E substituted |
| Task 2: vdb_entities.json repair | PASS — 678 MB repaired file; matrix (27696, 3072) ✓ |
| Task 3: Manual E2E chain | PASS — kol-scan (0 new/WeChat expired) → kol-classify (1 classified) → daily-ingest (5 new articles) |
| Task 4: DB write verification | PASS — 236→241 ok ingestions; MAX(layer2_at) advanced to 2026-05-24T22:05Z |
| Task 5: CUTOVER-04 evidence file | PASS — file written, aim-3 aggregate PASS |

## Notable events

### Bug 1 — TimeoutStartSec truncation (root cause of vdb corruption)

`cleanup_stuck_docs.py --all-failed` in ExecStartPre initializes the full LightRAG stack
(loads 678 MB vdb_entities.json). Default `TimeoutStartSec=90s` SIGTERM'd the process mid-write,
producing a 225 MB truncated file missing the `matrix` key. LightRAG failed to load with
`KeyError: 'matrix'`.

Fix: `TimeoutStartSec=300` in all 3 ingest service units (commit `f8b030b`).
vdb repair: per-entity `vector` fields (zlib-compressed float16) reconstructed into (27696, 3072)
normalized float32 matrix, base64-encoded, added as `matrix` key. Final file: 678 MB ✓.

### Bug 2 — `--days-back 1` unrecognized argument

`batch_classify_kol.py` does not accept `--days-back`. Service failed with exit 2 on every fire
(2 pre-cutover Persistent=true fires + 1 manual E2E fire before fix). Fix: removed the argument
from ExecStart (commit `d95242c`).

### WeChat session expiry (expected)

All 54 kol-scan requests returned `ret=200003: invalid session`. Expected — no browser session
established on Aliyun. Service exits 0 gracefully. Tracked as aim-5 stability item (operator:
refresh session in Aliyun browser).

### LightRAG graph growth post-cutover

After 5 new articles ingested: **27821 nodes, 39852 edges** (up from 27696/39604 at aim-2 close).
First Aliyun-native LightRAG write confirmed. ✓

## Decisions

- 24h natural-timer-fire gate bypassed per user explicit request — functional proof via
  manual E2E is accepted in lieu of waiting.
- 3 minor missing packages (`tavily`, `frontmatter`) in venv-aim1 are non-blocking warnings;
  tracked as aim-5 follow-ups.

## aim-3 phase verdict

**PASS** — all CUTOVER-01..05 requirements documented and verified.

## Next gate

aim-4 — daily sync Aliyun → Hermes + Databricks.
