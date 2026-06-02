# CUTOVER-01 — Aliyun systemd deploy + enable evidence

Phase: aim-3 (cutover)
REQ: CUTOVER-01

## Deploy-start ISO (UTC)

2026-05-24T14:57:27Z

## File counts on Aliyun

- `/etc/systemd/system/omnigraph-*.service`: 13 (required: 13) — PASS
- `/etc/systemd/system/omnigraph-*.timer`: 13 (required: 13) — PASS

## Deviation: OnCalendar UTC suffix fix (auto-fixed, Rule 1 — Bug)

**Found during Task 1 verification:** Aliyun runs Asia/Shanghai (CST = UTC+8). The initial
timer files were missing the `UTC` suffix on `OnCalendar=`, causing systemd to interpret the
schedules as CST local time (8 hours early).

**Fix:** Added ` UTC` suffix to all 13 `OnCalendar=` lines in `deploy/aliyun/systemd/*.timer`.
Re-deployed with second tarball (`aim-3-2-units-v2.tar.gz`), re-ran daemon-reload, re-enabled
all 13 timers. Idempotent — no harm from already-enabled timers.

**Evidence (CST display = UTC+8):**

- `rss-fetch.timer`: Before fix NEXT = 09:00 CST = 01:00 UTC (WRONG)
- `rss-fetch.timer`: After fix NEXT = 17:00 CST = 09:00 UTC (CORRECT)

## daemon-reload

`systemctl daemon-reload` exit code: **0**

## enable --now results (per unit)

All 13 timers enabled --now on first deploy (initial enable loop). Second deploy after
UTC suffix fix showed all 13 already-enabled symlinks confirmed (idempotent re-enable).

```
--- omnigraph-afternoon-ingest.timer ---
Created symlink /etc/systemd/system/timers.target.wants/omnigraph-afternoon-ingest.timer → /etc/systemd/system/omnigraph-afternoon-ingest.timer.
exit=0
--- omnigraph-daily-digest.timer ---
Created symlink /etc/systemd/system/timers.target.wants/omnigraph-daily-digest.timer → /etc/systemd/system/omnigraph-daily-digest.timer.
exit=0
--- omnigraph-daily-ingest.timer ---
Created symlink /etc/systemd/system/timers.target.wants/omnigraph-daily-ingest.timer → /etc/systemd/system/omnigraph-daily-ingest.timer.
exit=0
--- omnigraph-evening-ingest.timer ---
Created symlink /etc/systemd/system/timers.target.wants/omnigraph-evening-ingest.timer → /etc/systemd/system/omnigraph-evening-ingest.timer.
exit=0
--- omnigraph-kol-classify.timer ---
Created symlink /etc/systemd/system/timers.target.wants/omnigraph-kol-classify.timer → /etc/systemd/system/omnigraph-kol-classify.timer.
exit=0
--- omnigraph-kol-enrich.timer ---
Created symlink /etc/systemd/system/timers.target.wants/omnigraph-kol-enrich.timer → /etc/systemd/system/omnigraph-kol-enrich.timer.
exit=0
--- omnigraph-kol-scan.timer ---
Created symlink /etc/systemd/system/timers.target.wants/omnigraph-kol-scan.timer → /etc/systemd/system/omnigraph-kol-scan.timer.
exit=0
--- omnigraph-kol-zombie-cleanup.timer ---
Created symlink /etc/systemd/system/timers.target.wants/omnigraph-kol-zombie-cleanup.timer → /etc/systemd/system/omnigraph-kol-zombie-cleanup.timer.
exit=0
--- omnigraph-reconcile.timer ---
Created symlink /etc/systemd/system/timers.target.wants/omnigraph-reconcile.timer → /etc/systemd/system/omnigraph-reconcile.timer.
exit=0
--- omnigraph-rss-fetch.timer ---
Created symlink /etc/systemd/system/timers.target.wants/omnigraph-rss-fetch.timer → /etc/systemd/system/omnigraph-rss-fetch.timer.
exit=0
--- omnigraph-rss-layer2-classify.timer ---
Created symlink /etc/systemd/system/timers.target.wants/omnigraph-rss-layer2-classify.timer → /etc/systemd/system/omnigraph-rss-layer2-classify.timer.
exit=0
--- omnigraph-rss-rescrape.timer ---
Created symlink /etc/systemd/system/timers.target.wants/omnigraph-rss-rescrape.timer → /etc/systemd/system/omnigraph-rss-rescrape.timer.
exit=0
--- omnigraph-vertex-probe.timer ---
Created symlink /etc/systemd/system/timers.target.wants/omnigraph-vertex-probe.timer → /etc/systemd/system/omnigraph-vertex-probe.timer.
exit=0
```

## is-enabled

```
omnigraph-afternoon-ingest.timer                        enabled
omnigraph-daily-digest.timer                            enabled
omnigraph-daily-ingest.timer                            enabled
omnigraph-evening-ingest.timer                          enabled
omnigraph-kol-classify.timer                            enabled
omnigraph-kol-enrich.timer                              enabled
omnigraph-kol-scan.timer                                enabled
omnigraph-kol-zombie-cleanup.timer                      enabled
omnigraph-reconcile.timer                               enabled
omnigraph-rss-fetch.timer                               enabled
omnigraph-rss-layer2-classify.timer                     enabled
omnigraph-rss-rescrape.timer                            enabled
omnigraph-vertex-probe.timer                            enabled
```

All 13 = `enabled`. Sort-unique would return: `enabled`

## is-active

```
omnigraph-afternoon-ingest.timer                        active
omnigraph-daily-digest.timer                            active
omnigraph-daily-ingest.timer                            active
omnigraph-evening-ingest.timer                          active
omnigraph-kol-classify.timer                            active
omnigraph-kol-enrich.timer                              active
omnigraph-kol-scan.timer                                active
omnigraph-kol-zombie-cleanup.timer                      active
omnigraph-reconcile.timer                               active
omnigraph-rss-fetch.timer                               active
omnigraph-rss-layer2-classify.timer                     active
omnigraph-rss-rescrape.timer                            active
omnigraph-vertex-probe.timer                            active
```

All 13 = `active`. Sort-unique would return: `active`

## list-timers (next-fire schedule confirmation)

Captured after UTC suffix fix. Aliyun timezone: Asia/Shanghai (CST = UTC+8).
NEXT column shown in CST; UTC equivalent verified in parentheses.

```
NEXT                        LEFT               LAST PASSED UNIT                                ACTIVATES
Mon 2026-05-25 01:00:00 CST 1h 58min left      n/a  n/a    omnigraph-afternoon-ingest.timer    omnigraph-afternoon-ingest.service
Mon 2026-05-25 08:00:00 CST 8h left            n/a  n/a    omnigraph-evening-ingest.timer      omnigraph-evening-ingest.service
Mon 2026-05-25 17:00:00 CST 17h left           n/a  n/a    omnigraph-rss-fetch.timer           omnigraph-rss-fetch.service
Mon 2026-05-25 17:30:00 CST 18h left           n/a  n/a    omnigraph-rss-rescrape.timer        omnigraph-rss-rescrape.service
Mon 2026-05-25 18:55:00 CST 19h left           n/a  n/a    omnigraph-kol-zombie-cleanup.timer  omnigraph-kol-zombie-cleanup.service
Mon 2026-05-25 19:00:00 CST 19h left           n/a  n/a    omnigraph-kol-scan.timer            omnigraph-kol-scan.service
Mon 2026-05-25 19:15:00 CST 20h left           n/a  n/a    omnigraph-kol-classify.timer        omnigraph-kol-classify.service
Mon 2026-05-25 19:20:00 CST 20h left           n/a  n/a    omnigraph-rss-layer2-classify.timer omnigraph-rss-layer2-classify.service
Mon 2026-05-25 19:30:00 CST 20h left           n/a  n/a    omnigraph-kol-enrich.timer          omnigraph-kol-enrich.service
Mon 2026-05-25 20:00:00 CST 20h left           n/a  n/a    omnigraph-daily-ingest.timer        omnigraph-daily-ingest.service
Mon 2026-05-25 20:30:00 CST 21h left           n/a  n/a    omnigraph-daily-digest.timer        omnigraph-daily-digest.service
Mon 2026-05-25 20:30:00 CST 21h left           n/a  n/a    omnigraph-reconcile.timer           omnigraph-reconcile.service
Mon 2026-06-01 19:00:00 CST 1 week 0 days left n/a  n/a    omnigraph-vertex-probe.timer        omnigraph-vertex-probe.service

13 timers listed.
```

### UTC cross-reference (CST → UTC, CST = UTC+8)

| Timer | NEXT (CST) | NEXT (UTC) | OnCalendar (UTC) | Match |
|---|---|---|---|---|
| afternoon-ingest | 01:00 CST Mon | 17:00 UTC Sun | `*-*-* 17:00:00 UTC` | PASS |
| evening-ingest | 08:00 CST Mon | 00:00 UTC Mon | `*-*-* 00:00:00 UTC` | PASS |
| rss-fetch | 17:00 CST Mon | 09:00 UTC Mon | `*-*-* 09:00:00 UTC` | PASS |
| rss-rescrape | 17:30 CST Mon | 09:30 UTC Mon | `*-*-* 09:30:00 UTC` | PASS |
| kol-zombie-cleanup | 18:55 CST Mon | 10:55 UTC Mon | `*-*-* 10:55:00 UTC` | PASS |
| kol-scan | 19:00 CST Mon | 11:00 UTC Mon | `*-*-* 11:00:00 UTC` | PASS |
| kol-classify | 19:15 CST Mon | 11:15 UTC Mon | `*-*-* 11:15:00 UTC` | PASS |
| rss-layer2-classify | 19:20 CST Mon | 11:20 UTC Mon | `*-*-* 11:20:00 UTC` | PASS |
| kol-enrich | 19:30 CST Mon | 11:30 UTC Mon | `*-*-* 11:30:00 UTC` | PASS |
| daily-ingest | 20:00 CST Mon | 12:00 UTC Mon | `*-*-* 12:00:00 UTC` | PASS |
| daily-digest | 20:30 CST Mon | 12:30 UTC Mon | `*-*-* 12:30:00 UTC` | PASS |
| reconcile | 20:30 CST Mon | 12:30 UTC Mon | `*-*-* 12:30:00 UTC` | PASS |
| vertex-probe | 19:00 CST Jun-01 | 11:00 UTC Jun-01 | `*-*-1 11:00:00 UTC` | PASS |

## Sample unit verification (3 services + kol-enrich stub)

### omnigraph-daily-ingest.service

```
# /etc/systemd/system/omnigraph-daily-ingest.service
[Unit]
Description=OmniGraph daily ingest 09:00 ADT (12:00 UTC)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/OmniGraph-Vault
EnvironmentFile=/root/.hermes/.env
ExecStartPre=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/scripts/cleanup_stuck_docs.py --all-failed
ExecStart=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/batch_ingest_from_spider.py --from-db --max-articles 5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Verified:

- `WorkingDirectory=/root/OmniGraph-Vault` — PASS
- `EnvironmentFile=/root/.hermes/.env` — PASS
- `ExecStartPre=...cleanup_stuck_docs.py --all-failed` — PASS
- `ExecStart=...batch_ingest_from_spider.py --from-db --max-articles 5` — PASS

### omnigraph-kol-scan.service

```
# /etc/systemd/system/omnigraph-kol-scan.service
[Unit]
Description=OmniGraph daily KOL scan (WeChat MP API)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/OmniGraph-Vault
EnvironmentFile=/root/.hermes/.env
ExecStart=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/batch_scan_kol.py --daily
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Verified:

- `WorkingDirectory=/root/OmniGraph-Vault` — PASS
- `EnvironmentFile=/root/.hermes/.env` — PASS
- `ExecStart=...batch_scan_kol.py --daily` — PASS

### omnigraph-vertex-probe.service

```
# /etc/systemd/system/omnigraph-vertex-probe.service
[Unit]
Description=OmniGraph monthly Vertex AI live probe (1st of month)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/OmniGraph-Vault
EnvironmentFile=/root/.hermes/.env
ExecStart=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/scripts/vertex_live_probe.py
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Verified:

- `WorkingDirectory=/root/OmniGraph-Vault` — PASS
- `EnvironmentFile=/root/.hermes/.env` — PASS
- `ExecStart=...scripts/vertex_live_probe.py` — PASS

### omnigraph-kol-enrich.service (STUB — FINDING 6)

```
# /etc/systemd/system/omnigraph-kol-enrich.service
# STUB — FINDING 6 gap (aim-3 CONTEXT.md):
# The Hermes "daily-enrich" job uses the `enrich_article` Hermes skill via
# `enrichment/run_enrich_for_id.py`, invoked through the Hermes agent prompt
# layer. There is no standalone batch enrich script in the repo at aim-3 close.
# This unit is enabled so its timer fires (proves the schedule works) and so
# adding a real ExecStart later is a one-line edit. /bin/true exits 0 — no
# false-fail signal in journald.
#
# Pending: derivative milestone OR an ingest-side `--enrich-only` mode flag
# that wires through the same code path. Recorded in CUTOVER-EVIDENCE.md.

[Unit]
Description=OmniGraph kol-enrich (STUB — see FINDING 6)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/OmniGraph-Vault
EnvironmentFile=/root/.hermes/.env
ExecStart=/bin/true
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Verified: `ExecStart=/bin/true` — PASS (stub confirmed deployed as designed)

## Verdict

- PASS: All 13 units deployed, daemon-reload OK, all 13 enabled+active.
- PASS: All 13 timers have a future NEXT fire matching their UTC OnCalendar (verified via CST→UTC conversion table above).
- PASS: Sample ExecStart / EnvironmentFile / WorkingDirectory match aim-3-1 authored values verbatim.

**CUTOVER-01 requirement: MET.**

## Next gate

aim-3-3 — kol_scan.db pre-cutover sync + Hermes jobs disable + CUTOVER-EVIDENCE.md.
DO NOT proceed if any of the three verdict lines above is FAIL — investigate via separate quick first.
