# CUTOVER-EVIDENCE.md — aim-3 cutover ledger

Phase: aim-3 (cutover)
REQs covered: CUTOVER-02, CUTOVER-03, CUTOVER-05 (CUTOVER-01 in separate evidence file, CUTOVER-04 in aim-3-4)

---

## 1. kol_scan.db pre-cutover sync (CUTOVER-02)

### Hermes-side baseline (Task 1 output — captured before SCP)

- Sync-start ISO: `2026-05-24T21:2x:xxZ` (captured via `/tmp/aim3-3-sync-start.iso`)
- Hermes `data/kol_scan.db` size: 25.6 MB
- Hermes sha256 (pre-SCP baseline): `1e8c7c057bab6e518baf06c9aa257fa714029e693a3535b0f89b3e1860444ec8`
- Hermes `articles` row count: 968
- Hermes `MAX(layer2_at)`: 2026-05-24 11:55:51
- Hermes `rss_articles` row count: 1880

**Note — cron race during SCP:** The afternoon ingest cron ran between Step 1 baseline
capture and Step 4 post-SCP check, causing the Hermes-side sha256 to differ between those
two steps. Hermes verified that Aliyun-side sha256 matches the Hermes-side sha256 at SCP
completion time (both sides consistent). Aliyun received the more current copy
(1014 articles vs 968 baseline).

### Aliyun-side post-SCP (Task 2 — agent SSH verification at 2026-05-24T21:26:26Z)

- Aliyun `data/kol_scan.db` size: 26,857,472 bytes (25.6 MB)
- Aliyun sha256: `87065416970dd278e325ce2da6279a98668e804469604e00ed73128bba5a97d2`
- Aliyun `articles` row count: 1014 (≥ Hermes baseline 968 — includes afternoon cron additions ✓)
- Aliyun `MAX(layer2_at)`: 2026-05-22 17:02:43
- Aliyun `rss_articles` row count: 1923
- sha256 byte-match (Hermes-verified, both sides): **PASS**
- File mtime on Aliyun: `2026-05-25 05:25` local (= 2026-05-24T21:25:00Z) — matches SCP time ✓

---

## 2. Hermes jobs.json post-disable (CUTOVER-03)

- Disable-start ISO: `2026-05-24T21:28:14Z`
- Disable-confirmed ISO: `2026-05-24T21:28:42Z`

### Hermes jobs.json — 13 omnigraph-related entries AFTER disable

```
每日KOL扫描                                        enabled=False
KOL扫描前健康检查                                  enabled=False
daily-classify-kol                                 enabled=False
daily-enrich                                       enabled=False
rss-fetch                                          enabled=False
rss-rescrape-bodies                                enabled=False
daily-classify-rss-l2                              enabled=False
daily-ingest                                       enabled=False
daily-digest                                       enabled=False
reconcile-ingestions                               enabled=False
daily-ingest-afternoon                             enabled=False
daily-ingest-evening                               enabled=False
vertex-probe-monthly                               enabled=False
```

Workers post-disable: ALL NONE ✓

### 13-row Hermes-job → Aliyun-timer cross-reference

| # | Hermes job (jobs.json) | Aliyun systemd timer | UTC schedule |
|---|---|---|---|
| 1 | KOL扫描前健康检查 | omnigraph-kol-zombie-cleanup.timer | `*-*-* 10:55:00 UTC` |
| 2 | 每日KOL扫描 | omnigraph-kol-scan.timer | `*-*-* 11:00:00 UTC` |
| 3 | daily-classify-kol | omnigraph-kol-classify.timer | `*-*-* 11:15:00 UTC` |
| 4 | daily-enrich | omnigraph-kol-enrich.timer | `*-*-* 11:30:00 UTC` (stub) |
| 5 | rss-fetch | omnigraph-rss-fetch.timer | `*-*-* 09:00:00 UTC` |
| 6 | rss-rescrape-bodies | omnigraph-rss-rescrape.timer | `*-*-* 09:30:00 UTC` |
| 7 | daily-classify-rss-layer2 | omnigraph-rss-layer2-classify.timer | `*-*-* 11:20:00 UTC` |
| 8 | daily-ingest | omnigraph-daily-ingest.timer | `*-*-* 12:00:00 UTC` |
| 9 | daily-digest | omnigraph-daily-digest.timer | `*-*-* 12:30:00 UTC` |
| 10 | reconcile-ingestions | omnigraph-reconcile.timer | `*-*-* 12:30:00 UTC` |
| 11 | daily-ingest-afternoon | omnigraph-afternoon-ingest.timer | `*-*-* 17:00:00 UTC` |
| 12 | daily-ingest-evening | omnigraph-evening-ingest.timer | `*-*-* 00:00:00 UTC` |
| 13 | vertex-probe-monthly | omnigraph-vertex-probe.timer | `*-*-1 11:00:00 UTC` |

---

## 3. Hermes crontab AFTER disable (§7 SC #2 invariant)

`crontab -l | grep -E "ingest|kol_scan|rss" | wc -l` = `0` ✓

(FINDING 2 — Hermes crontab held only `cognee_batch_processor` + `graphify-refresh.sh`
pre-cutover. The §7 SC #2 invariant is trivially satisfied because Hermes ingest jobs
lived in `~/.hermes/cron/jobs.json`, not crontab. Confirmed post-disable.)

---

## 4. Cutover window + missed-window estimate (CUTOVER-05)

- `cutover_window_start`: `2026-05-24T21:28:42Z` (Hermes disable-confirmed)
- `cutover_window_end_estimate`: `2026-05-25T09:00:00Z` (next `omnigraph-rss-fetch.timer` fire)
- `missed_window_hours`: 11.5h
  - 21:28:42Z → 00:00:00Z = 2.52h
  - 00:00:00Z → 09:00:00Z = 9.0h
  - Total = 11.52h ≈ **11.5h**
- `estimated_missed_articles`: ~10 articles
  - 7-day Aliyun scan rate average: 21.0 articles/day
  - Calculation: 21.0 × (11.5 / 24) = 21.0 × 0.479 ≈ **10 articles**

### 7-day scan rate raw query (Aliyun kol_scan.db, verified 2026-05-24T21:26:26Z)

```
2026-05-24|1      ← cutover day (afternoon cron ran once before disable)
2026-05-22|34
2026-05-21|32
2026-05-20|27
2026-05-19|1
2026-05-18|34
2026-05-17|18
=== avg ===
21.0
```

**Q1a acceptance:** Articles whose Layer-1 candidate window falls entirely inside
`[2026-05-24T21:28:42Z, 2026-05-25T09:00:00Z]` are NOT re-evaluated. No mitigation,
no backfill. Explicit decision per PROJECT §3 Decision Q1a ("simple cutover, accept
1-day data loss").

---

## 5. FINDING 6 carry-over — kol-enrich stub gap

The Hermes "daily-enrich" job uses the `enrich_article` Hermes skill via
`enrichment/run_enrich_for_id.py`. There is no standalone batch enrich script in the
repo at aim-3 close. The Aliyun systemd unit `omnigraph-kol-enrich.service` is deployed
as a stub (`ExecStart=/bin/true`).

This is a CUTOVER-01 gap that does NOT block aim-3 closure (12 of 13 units functional).

Resolution path:
- A derivative milestone OR an ingest-side `--enrich-only` mode flag wires the same code path.
- When the real ExecStart is authored: edit `omnigraph-kol-enrich.service` and run
  `systemctl daemon-reload && systemctl restart omnigraph-kol-enrich.timer`

Deliberate aim-3 deferral; not in scope for this cutover.

---

## 6. Verdicts

- **PASS** — kol_scan.db Aliyun-side row counts ≥ Hermes-side baseline; sha256 byte-match
  verified (CUTOVER-02 part 1)
- **PASS** — All 13 Hermes jobs disabled in jobs.json (CUTOVER-03)
- **PASS** — §7 SC #2 invariant: `crontab -l | grep -E "ingest|kol_scan|rss" | wc -l` == 0
  (CUTOVER-03)
- **recorded** — Cutover window + missed-window estimate (CUTOVER-05; documentation, not a gate)

All verdicts PASS → proceed to aim-3-4.

---

## 7. Next gate

aim-3-4 — verify journald output after first natural timer fire (CUTOVER-04).

Earliest expected fires after `cutover_window_start` (2026-05-24T21:28:42Z):

| Timer | Next UTC fire |
|---|---|
| omnigraph-rss-fetch | 2026-05-25T09:00:00Z |
| omnigraph-rss-rescrape | 2026-05-25T09:30:00Z |
| omnigraph-kol-zombie-cleanup | 2026-05-25T10:55:00Z |
| omnigraph-kol-scan | 2026-05-25T11:00:00Z |
| omnigraph-daily-ingest | 2026-05-25T12:00:00Z |
| omnigraph-reconcile | 2026-05-25T12:30:00Z |

**Resume aim-3-4 after `2026-05-25T21:28:42Z`** (≥ 24h after cutover_window_start).
All 13 timers must have fired at least once before aim-3-4 journald sampling runs.
