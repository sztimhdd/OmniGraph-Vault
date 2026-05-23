# STORAGE-01 — Hermes Ingest Cron Pause Evidence

**Plan:** aim-2-1 (STORAGE-01)
**Phase:** aim-2-lightrag-storage-migration
**Wave:** 1
**Captured:** 2026-05-23

---

## Pause Timestamps

| Field | ISO 8601 (UTC) |
| --- | --- |
| pause-start (operator initiated) | `2026-05-23T14:08:47Z` |
| pause-confirmed (operator output received) | `2026-05-23T14:09:41Z` |

The **Q2a 30-min freshness window** starts at `2026-05-23T14:09:41Z`.
Q2a deadline: `2026-05-23T14:39:41Z` (T+30min from pause-confirmed).

---

## Crontab State Post-Pause

**Crontab:** clean — only `cognee` + `graphify-refresh` remain active. **Zero ingest lines uncommented.**

**Hermes crons paused (10 entries — verbatim from operator):**

1. daily-ingest (09:00)
2. daily-ingest-afternoon (14:00)
3. daily-ingest-evening (21:00)
4. rss-fetch (06:00)
5. rss-rescrape-bodies (06:30)
6. 每日KOL扫描 (08:00)
7. KOL扫描前健康检查 (07:55)
8. daily-classify-kol (08:15)
9. daily-classify-rss-layer2 (08:20)
10. reconcile-ingestions (09:30)

**Gate:** `uncommented_ingest_lines == 0` → **GREEN** ✅

---

## Workers State Post-Pause

| Worker | State |
| --- | --- |
| `batch_ingest_from_spider` | NONE ✅ |
| `batch_scan_kol` | NONE ✅ |
| `rss_ingest` | NONE ✅ |

**`pgrep` false-positive:** bash eval wrapper detected — harmless, not an ingest worker.

---

## MCP-Server-SQLite PID Whitelist

The following 6 PIDs may appear in Hermes process listings but are **NOT** ingest workers — they are benign read-only `mcp-server-sqlite` `uvx` daemons providing DB-read access to other Hermes tools. Whitelisted for the duration of the pause window:

```
882, 965, 37374, 37417, 59338, 59374
```

These PIDs MUST NOT be killed during STORAGE-02 / STORAGE-03 / STORAGE-04. They do not write to LightRAG storage, KV stores, or candidate-pool DBs.

---

## Documentation Drift Note (Forward-Only)

STATE.md (pre-execution) predicted **11** ingest cron entries to be paused. Operator reports **10**. The 1-entry difference is benign:

- Likely cause: `vertex-probe-monthly` is monthly-cadence (not daily) and/or one or two name-string mismatches between STATE.md prediction and live crontab.
- **Gate criterion** is `uncommented_ingest_lines == 0`, which is satisfied — the count delta does not affect gate state.
- **Correction policy:** STATE.md edits are owned by **wave-5** (closure wave). This wave does NOT modify STATE.md. The drift is recorded here for the wave-5 reconciler to absorb forward-only.

---

## Resume Protocol

The pause holds until **one** of the following orchestrator messages is delivered to Hermes:

1. **Success path:** `"STORAGE-04 verify passed, you may resume"` — re-enables all 10 paused crons
2. **Abort path:** `"abort, please resume Hermes"` — same re-enable, but signals migration aborted (no `aim-2-2` storage swap)

Until either message is delivered, **no ingest cron may be re-enabled** and **no manual ingest invocation may be triggered** on Hermes.

---

## Red Lines Honored

- ✅ No SSH to Hermes from this executor (operator-channel only)
- ✅ No `git add -A` (this commit will stage only this file explicitly)
- ✅ No `--amend` / no `--force`
- ✅ Forward-only — STATE.md not modified in this wave

---

**Wave-1 STORAGE-01 status:** EVIDENCE CAPTURED. Ready for wave-2 (STORAGE-02 tar + sha256 on Hermes).
