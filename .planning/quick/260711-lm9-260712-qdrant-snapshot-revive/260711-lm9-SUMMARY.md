# Quick 260711-lm9 SUMMARY: qdrant-snapshot.timer revived (ISSUES #78 RESOLVED)

**Closed:** 2026-07-11
**Commit (timer):** `dc72a68`
**Status:** ✅ COMPLETE — timer armed + snapshot verified end-to-end + orphan conf cleaned

## What shipped

1. **Timer structural fix** (`dc72a68`): `deploy/aliyun/systemd/qdrant-snapshot.timer`
   monotonic `OnBootSec=15min + OnUnitActiveSec=6h` → wall-clock
   `OnCalendar=*-*-* 03/6:10:00 UTC` (fires 03:10/09:10/15:10/21:10 UTC, same 4×/day cadence).
   Deployed to Aliyun `/etc/systemd/system/` via SCP + daemon-reload + stop/start.
2. **Snapshot verified end-to-end** — manual `systemctl start qdrant-snapshot.service` ran clean.
3. **Orphan conf removed** — `omnigraph-vertex-proxy-env.conf` (retired #75/#76 SOCKS5 drop-in).

## Root cause confirmed (matches #78 filing)

Timer was `active (elapsed)`, `Trigger: n/a`, last real run **2026-06-06**. `OnUnitActiveSec`
re-arms ONLY after a *successful* activation. The 2026-06-17 rebuild's boot+15min fire ran before
docker-ce existed (docker landed 6/23), the `Requires=docker.service` oneshot failed, and
`OnUnitActiveSec` never re-armed → permanently elapsed. `OnCalendar` (wall-clock) structurally
eliminates this: a single failed run no longer disarms the schedule.

## The #41 OOM blocker was already fixed (key finding)

The task hedged on #41 (converter OOM on the relationships dump) as a possible blocker. It's
**already resolved**: `scripts/qdrant_to_nanovdb.py:104-213` streams float32 bytes into one
contiguous `bytearray` (arx-4 Plan 01; explicit "ISSUES #41 fix" peak-RSS note at line 93).
On-disk proof pre-run: `vdb_relationships.json` = 1.42 GB dated 2026-06-25 (a prior full run had
succeeded — NOT the 49-byte OOM-era placeholder). Reviving the timer does **not** regress #41.

## Verification evidence

**Timer armed:**
```
NEXT                        LEFT          UNIT
Sun 2026-07-12 05:10:00 CST 2h 29min left qdrant-snapshot.timer   # = 2026-07-11 21:10 UTC
NextElapseUSecRealtime=Sun 2026-07-12 05:10:00 CST
```
(Note: `systemctl restart` left a stale cached `next_elapse`; a full stop→daemon-reload→start
forced correct recompute. `systemd-analyze calendar` validated the expression independently.)

**Manual service run — exit 0/SUCCESS, Result=success, CPU 3min, wall ~15min:**
```
chunks         4617  pts  dim=3072  wall_s=7.790
entities      72942  pts  dim=3072  wall_s=118.547
relationships 97977  pts  dim=3072  wall_s=768.326
```
RAM peaked **13.6 GB used / 1.18 GB avail** on the relationships dump, dropped to 6.5 GB on exit —
tight but **no OOM** (14 GB box, streaming keeps peak bounded ≈ 1.2 GB buffer + ~1.6 GB transient
b64). Well within `TimeoutStartSec=1800`.

**Artifacts (all fresh 2026-07-12):**
```
vdb_chunks.json          94 MB   02:39:59
vdb_entities.json      1.23 GB   02:41:51
vdb_relationships.json 1.65 GB   02:54:44   (grew from 1.42GB/6-25 as points 82.5k→98k)
```
No `.tmp` orphans (atomic `os.replace` clean). **kb-api `/health` → 200** before, during, and after.

**Orphan conf:** `grep -rl` = zero unit refs (re-confirmed immediately before `rm`), removed +
daemon-reload OK, confirmed gone.

## Hard constraints — all honored

- Touched only `qdrant-snapshot.timer` (repo+Aliyun) + the orphan conf. Zero touches to
  ingest / kb-api / mcp-tunnel units.
- Repo-first → SCP (never reverse). Forward-only commit `dc72a68`, no amend/reset/force-push.
- OOM/30min escalation trigger did NOT fire (run completed clean at ~15min, no OOM).

## Follow-ups / notes

- **No new issues surfaced.** The run cleanly exercised the arx-4 #41 streaming fix at the current
  98k-relationship scale — an incidental production validation of that converter rewrite.
- `init quick` reported `roadmap_exists: false` — the known **#54** false-negative (OmniGraph uses
  suffix ROADMAP files); proceeded per project convention, non-blocking.
- Path X (#44 self-heal) is back online: the 4×/day snapshot resumes bridging Qdrant → on-disk vdb
  for Databricks/Hermes read consumers.
