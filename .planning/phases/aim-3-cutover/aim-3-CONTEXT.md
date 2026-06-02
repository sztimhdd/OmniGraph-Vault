# Phase aim-3: Cutover — Context

**Gathered:** 2026-05-24
**Status:** Ready for planning
**Source:** Direct SSH audit of Hermes jobs.json + repo inspection

---

<domain>
## Phase Boundary

Convert 13 enabled Hermes agent-cron jobs to 13 Aliyun systemd `.service` + `.timer` pairs.
Disable all Hermes jobs. Hand off `kol_scan.db` write authority to Aliyun. Collect journald
evidence after first natural timer fires.

**Not in scope:** kol session renewal (separate ops concern), aim-4 daily sync scripts.

</domain>

<decisions>
## Critical Findings from Hermes SSH Audit (2026-05-24)

### FINDING 1 — 13 enabled jobs, NOT 11 (ROADMAP says 11)

Actual Hermes jobs.json (enabled=True):

| Job name | Hermes schedule (ADT) | Equivalent Aliyun ExecStart |
|---|---|---|
| KOL扫描前健康检查 | `55 7 * * *` | `venv-aim1/bin/python scripts/clean_lightrag_zombies.py` |
| 每日KOL扫描 | `0 8 * * *` | `venv-aim1/bin/python batch_scan_kol.py --daily` |
| daily-classify-kol | `15 8 * * *` | `venv-aim1/bin/python batch_classify_kol.py --topic Agent --topic LLM --topic RAG --topic NLP --topic CV --min-depth 2 --days-back 1` |
| daily-enrich | `30 8 * * *` | TBD — uses `enrich_article` Hermes skill; planner must resolve to direct script call (check `enrichment/enrich_article.py` or `batch_enrich_vision.py`) |
| rss-fetch | `0 6 * * *` | `venv-aim1/bin/python enrichment/rss_fetch.py` |
| rss-rescrape-bodies | `30 6 * * *` | `venv-aim1/bin/python enrichment/rss_rescrape_bodies.py` |
| daily-classify-rss-layer2 | `20 8 * * *` | `venv-aim1/bin/python batch_classify_rss_layer2.py` |
| daily-ingest | `0 9 * * *` | `venv-aim1/bin/python batch_ingest_from_spider.py --from-db --max-articles 5` |
| daily-digest | `30 9 * * *` | `venv-aim1/bin/python enrichment/daily_digest.py` |
| reconcile-ingestions | `30 9 * * *` | `venv-aim1/bin/python scripts/reconcile_ingestions.py --auto-patch` |
| daily-ingest-afternoon | `0 14 * * *` | `venv-aim1/bin/python batch_ingest_from_spider.py --from-db --max-articles 5` |
| daily-ingest-evening | `0 21 * * *` | `venv-aim1/bin/python batch_ingest_from_spider.py --from-db --max-articles 5` |
| vertex-probe-monthly | `0 8 1 * *` | `venv-aim1/bin/python scripts/vertex_live_probe.py` |

**batch-watchdog** (`every 10m`, enabled=False) — intentionally disabled; do NOT migrate.

### FINDING 2 — Hermes crontab is ALREADY CLEAN

`crontab -l` on Hermes returns only 2 entries (cognee_batch_processor + graphify-refresh.sh).
`crontab -l | grep -E "ingest|kol_scan|rss" | wc -l` already returns 0.

§7 SC #2 invariant is TRIVIALLY SATISFIED — the Hermes crontab never held ingest jobs.
The real "clearing" is **disabling jobs in ~/.hermes/cron/jobs.json via Hermes agent**.

### FINDING 3 — batch_scan_kol.py exists at repo root; uses cookie-based HTTP (no CDP browser)

`batch_scan_kol.py` calls `spiders/wechat_spider.py` via `list_articles_with_digest()`.
This is HTTP-based (WeChat MP API cookies), NOT CDP-based. Aliyun can run it directly.
kol_config.py holds WeChat session cookies. The Hermes job currently fails with "invalid session"
because the cookies are expired — **this is a credentials issue, not an architecture blocker**.
The systemd unit should be written as if credentials are valid; session renewal is separate ops.

### FINDING 4 — daily-ingest uses tmux wrapper (cron_daily_ingest.sh)

Hermes uses tmux to bypass Hermes agent's 900s inactivity ceiling.
On Aliyun with systemd, there is no inactivity ceiling — systemd IS the process manager.
**Do NOT use tmux in systemd ExecStart.** Call `batch_ingest_from_spider.py` directly.
The cleanup step (`cleanup_stuck_docs.py --all-failed`) should be `ExecStartPre`.

### FINDING 5 — KOL扫描前健康检查 includes CDP browser check

The original prompt checks CDP browser at `localhost:9223`. Aliyun has no local CDP browser.
Systemd unit should OMIT the CDP browser check; retain only `clean_lightrag_zombies.py`.
Health check function is effectively the zombie cleanup.

### FINDING 6 — daily-enrich uses `enrich_article` Hermes skill

Planner must inspect the repo for `enrich_article.py` or equivalent direct script.
If no direct script exists, this job may need to be deferred or implemented as part of
the batch ingest `--enrich-only` flag (if it exists).

### FINDING 7 — venv path on Aliyun

Ingest venv: `/root/OmniGraph-Vault/venv-aim1/` (Python 3.11.0rc1, per aim-1 deviation)
KB-api venv: `/root/OmniGraph-Vault/venv/` (Python 3.10.12) — do NOT use for systemd units

### FINDING 8 — Aliyun systemd unit directory

All units under `/etc/systemd/system/omnigraph-*.{service,timer}` (CUTOVER-01 requirement).

### FINDING 9 — Hermes job disable is operator-channel (Hermes prompt)

Disabling jobs in `~/.hermes/cron/jobs.json` on Hermes is done via Hermes prompt (user forwards).
Plans must write a Hermes operator prompt for the job-disable step.
SSH read-only diagnostics (crontab -l, journalctl) are agent-executable.

### FINDING 10 — kol_scan.db sync before write-authority handoff

`data/kol_scan.db` lives at repo root on Aliyun. At aim-2 close, Aliyun has the migrated DB
from Hermes (aim-2 STORAGE-05 included the DB). A final pre-cutover sync verifies the DB is
current before Hermes jobs are disabled. After disable, Aliyun timers take over writes.

</decisions>

<canonical_refs>

## Canonical References

- `.planning/ROADMAP-Aliyun-Ingest-Migration-v1.md` — Phase aim-3 goal + 5 REQs (CUTOVER-01..05)
- `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` — CUTOVER-N requirement bodies
- `.planning/STATE-Aliyun-Ingest-Migration-v1.md` — Hermes operational state + operator channel
- `batch_scan_kol.py` — KOL scan script (HTTP-based, no browser needed)
- `batch_ingest_from_spider.py` — Core ingest orchestrator
- `scripts/cron_daily_ingest.sh` — Current tmux wrapper (do NOT copy to systemd; use direct call)
- `scripts/reconcile_ingestions.py` — Reconcile script
- `enrichment/rss_fetch.py` — RSS fetch script
- `enrichment/rss_rescrape_bodies.py` — RSS rescrape script
- `batch_classify_kol.py` — KOL classifier
- `batch_classify_rss_layer2.py` — RSS Layer 2 classifier
- `enrichment/daily_digest.py` — Daily digest
- `scripts/vertex_live_probe.py` — Vertex AI probe

</canonical_refs>

<specifics>
## Specific Implementation Notes

### systemd Unit Template (service)

```ini
[Unit]
Description=OmniGraph <job-name>
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/OmniGraph-Vault
EnvironmentFile=/root/.hermes/.env
ExecStart=/root/OmniGraph-Vault/venv-aim1/bin/python <script-and-args>
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### systemd Unit Template (timer)

```ini
[Unit]
Description=OmniGraph <job-name> timer
Requires=omnigraph-<name>.service

[Timer]
OnCalendar=<ADT schedule converted to UTC>
Persistent=true

[Install]
WantedBy=timers.target
```

**ADT → UTC conversion:** ADT = UTC-3. 09:00 ADT = 12:00 UTC. Apply +3h to all schedules.

### All 13 timers + UTC schedules

| Unit name | OnCalendar (UTC) |
|---|---|
| omnigraph-kol-zombie-cleanup | `*-*-* 10:55:00` |
| omnigraph-kol-scan | `*-*-* 11:00:00` |
| omnigraph-kol-classify | `*-*-* 11:15:00` |
| omnigraph-kol-enrich | `*-*-* 11:30:00` |
| omnigraph-rss-fetch | `*-*-* 09:00:00` |
| omnigraph-rss-rescrape | `*-*-* 09:30:00` |
| omnigraph-rss-layer2-classify | `*-*-* 11:20:00` |
| omnigraph-daily-ingest | `*-*-* 12:00:00` |
| omnigraph-daily-digest | `*-*-* 12:30:00` |
| omnigraph-reconcile | `*-*-* 12:30:00` |
| omnigraph-afternoon-ingest | `*-*-* 17:00:00` |
| omnigraph-evening-ingest | `*-*-* 00:00:00` |
| omnigraph-vertex-probe | `*-*-1 11:00:00` |

### ExecStartPre for ingest units

```ini
ExecStartPre=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/scripts/cleanup_stuck_docs.py --all-failed
```

### Hermes job-disable operator prompt structure

```
Hermes, disable ALL 13 omnigraph ingest jobs in your cron scheduler:
[list of job IDs with disable command]
After disabling, confirm with: cat ~/.hermes/cron/jobs.json | python3 -c "import json,sys; jobs=json.load(sys.stdin)['jobs']; [print(j['name'], j.get('enabled')) for j in jobs if 'omnigraph' in j.get('name','').lower() or any(x in j.get('prompt','') for x in ['ingest','scan','classify','enrich','reconcile','digest','fetch','layer2','vertex','rescrape'])]"
```

</specifics>

<deferred>
## Deferred

- `daily-enrich` script resolution (planner must inspect repo and determine direct script; if none exists, document as CUTOVER-01 gap and defer to aim-3 follow-up)
- WeChat session renewal (separate ops, not a CUTOVER blocker)
- `KOL扫描前健康检查` CDP browser check (omit from systemd unit; Aliyun has no local browser)

</deferred>
