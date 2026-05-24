# Aliyun systemd ingest units

These 13 service+timer pairs replace the Hermes agent-cron entries that
formerly drove KOL scan / classify / RSS fetch / ingest / reconcile /
digest / vertex-probe on the Hermes box. They are deployed to the
Aliyun ECS at `/etc/systemd/system/` as part of aim-3 cutover
(CUTOVER-01 requirement in `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md`).

All units use the ingest venv at `/root/OmniGraph-Vault/venv-aim1/` (Python 3.11,
created in aim-1 DEPLOY-02). The kb-api venv at `/root/OmniGraph-Vault/venv/`
(Python 3.10) must NOT be used for any of these units.

## Deployment

Copy the unit files to `/etc/systemd/system/` and enable the timers:

```bash
# From the Aliyun ECS root:
cp /root/OmniGraph-Vault/deploy/aliyun/systemd/omnigraph-*.service /etc/systemd/system/
cp /root/OmniGraph-Vault/deploy/aliyun/systemd/omnigraph-*.timer   /etc/systemd/system/

# Reload systemd to pick up new units
systemctl daemon-reload

# Enable and start all 13 timers
systemctl enable --now omnigraph-kol-zombie-cleanup.timer
systemctl enable --now omnigraph-kol-scan.timer
systemctl enable --now omnigraph-kol-classify.timer
systemctl enable --now omnigraph-kol-enrich.timer
systemctl enable --now omnigraph-rss-fetch.timer
systemctl enable --now omnigraph-rss-rescrape.timer
systemctl enable --now omnigraph-rss-layer2-classify.timer
systemctl enable --now omnigraph-daily-ingest.timer
systemctl enable --now omnigraph-daily-digest.timer
systemctl enable --now omnigraph-reconcile.timer
systemctl enable --now omnigraph-afternoon-ingest.timer
systemctl enable --now omnigraph-evening-ingest.timer
systemctl enable --now omnigraph-vertex-probe.timer
```

## Verify timers are active

```bash
systemctl list-timers 'omnigraph-*'
```

Expected: 13 rows, each with a NEXT trigger time. STATUS column should show `active`.

To check the last run of a specific service:

```bash
journalctl -u omnigraph-daily-ingest.service --since today
```

## Schedule table (ADT -> UTC)

All times are UTC. ADT = UTC-3 (add 3h to convert Hermes ADT schedule to UTC).

| Unit | ADT (Hermes original) | UTC OnCalendar |
|---|---|---|
| omnigraph-kol-zombie-cleanup | 07:55 daily | `*-*-* 10:55:00` |
| omnigraph-kol-scan | 08:00 daily | `*-*-* 11:00:00` |
| omnigraph-kol-classify | 08:15 daily | `*-*-* 11:15:00` |
| omnigraph-kol-enrich | 08:30 daily | `*-*-* 11:30:00` |
| omnigraph-rss-fetch | 06:00 daily | `*-*-* 09:00:00` |
| omnigraph-rss-rescrape | 06:30 daily | `*-*-* 09:30:00` |
| omnigraph-rss-layer2-classify | 08:20 daily | `*-*-* 11:20:00` |
| omnigraph-daily-ingest | 09:00 daily | `*-*-* 12:00:00` |
| omnigraph-daily-digest | 09:30 daily | `*-*-* 12:30:00` |
| omnigraph-reconcile | 09:30 daily | `*-*-* 12:30:00` |
| omnigraph-afternoon-ingest | 14:00 daily | `*-*-* 17:00:00` |
| omnigraph-evening-ingest | 21:00 daily | `*-*-* 00:00:00` |
| omnigraph-vertex-probe | 08:00 1st of month | `*-*-1 11:00:00` |

Note: `omnigraph-daily-digest` and `omnigraph-reconcile` share the same OnCalendar
(`*-*-* 12:30:00`). They will fire at the same wall-clock second; systemd dispatches
them concurrently, which is the same behavior as on Hermes (both were at `30 9 * * *`).

## Known gap — kol-enrich stub (FINDING 6)

`omnigraph-kol-enrich.service` has `ExecStart=/bin/true` (exits 0 immediately — no
false-fail in journald). This is intentional.

**Why:** The Hermes `daily-enrich` job invokes the `enrich_article` Hermes skill via
the Hermes agent prompt layer (`enrichment/run_enrich_for_id.py`). There is no
standalone batch enrich script that can be called from a systemd ExecStart line at
aim-3 close. Implementing one is deferred.

**What the stub provides:** The timer fires on schedule, giving the operator a
slot in the daily timeline that is easy to activate. When a batch enrich script is
added to the repo, `ExecStart=/bin/true` becomes a one-line edit to point at it.

**Resolution path:** A derivative milestone (or an `--enrich-only` mode flag on
`batch_ingest_from_spider.py`) will provide the real ExecStart. Track in
`.planning/phases/aim-3-cutover/CUTOVER-EVIDENCE.md`.

## Ingest units — cleanup pre-step

The three ingest units (`omnigraph-daily-ingest`, `omnigraph-afternoon-ingest`,
`omnigraph-evening-ingest`) include:

```ini
ExecStartPre=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/scripts/cleanup_stuck_docs.py --all-failed
```

This mirrors the `cleanup_stuck_docs.py --all-failed` call that was the first step
in `scripts/cron_daily_ingest.sh` on Hermes. It resets articles stuck in
`status='processing'` back to `status='candidate'` before each ingest run, preventing
stale checkpoints from blocking the batch.

## kol_scan.db handoff

`data/kol_scan.db` is the shared SQLite database holding WeChat article metadata,
KOL candidate rows, and ingestion state. At aim-2 close, Aliyun already has a
byte-identical copy of the DB migrated from Hermes (aim-2 STORAGE-05).

Before enabling these timers (aim-3-2), aim-3-3 performs a final pre-cutover sync
of `kol_scan.db` from Hermes to Aliyun to capture any new rows written by Hermes
jobs that fired after aim-2. After aim-3 cutover, Aliyun owns writes to this DB.
Hermes jobs are disabled (via Hermes operator prompt) before the timers are enabled,
preventing concurrent writes.

## EnvironmentFile

All 13 `.service` files reference `EnvironmentFile=/root/.hermes/.env`. This is the
same env file used by the ingest pipeline on Hermes (aim-1 DEPLOY-03). It must exist
on Aliyun before the services can start. Key variables it must contain include:
`DEEPSEEK_API_KEY`, `APIFY_TOKEN`, `GOOGLE_APPLICATION_CREDENTIALS`, and all other
variables documented in `CLAUDE.md` § Environment Variables.

## No tmux

None of these unit files use tmux. On Hermes, `cron_daily_ingest.sh` wraps the
ingest invocation in a tmux session to bypass Hermes agent's 900s inactivity ceiling.
systemd has no such ceiling — it is the process manager. Direct Python invocation is
the correct pattern.

## References

- `.planning/phases/aim-3-cutover/aim-3-CONTEXT.md` — Full FINDINGS 1-10 from Hermes SSH audit, ExecStart equivalents, UTC schedule table
- `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` — CUTOVER-01..05 requirement bodies
- `.planning/ROADMAP-Aliyun-Ingest-Migration-v1.md` — aim-3 milestone overview
- `scripts/cron_daily_ingest.sh` — The tmux wrapper these units replace (do NOT copy its pattern)
