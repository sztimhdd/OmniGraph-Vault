# Aliyun systemd ingest units

These 13 service+timer pairs replace the Hermes agent-cron entries that
formerly drove KOL scan / classify / RSS fetch / ingest / reconcile /
digest / vertex-probe on the Hermes box. They are deployed to the
Aliyun ECS at `/etc/systemd/system/` as part of aim-3 cutover
(CUTOVER-01 requirement in `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md`).

All units use the ingest venv at `/root/OmniGraph-Vault/venv-aim1/` (Python 3.11,
created in aim-1 DEPLOY-02). The kb-api venv at `/root/OmniGraph-Vault/venv/`
(Python 3.10) must NOT be used for any of these units.

## Current authoritative ingest scheduler contract (2026-08-13)

The three-ingest-unit schedule below has been consolidated. Authoritative contract:

- `omnigraph-daily-ingest.timer` is the **sole recurring ingest scheduler**
  (`OnCalendar=*-*-* 00/2:00:00 UTC`, every 2h, `Persistent=true`).
- `omnigraph-afternoon-ingest.timer` and `omnigraph-evening-ingest.timer` are
  **DISABLED** on production (`systemctl disable --now`); their files remain for
  history only. Do not re-enable them.
- The daily ingest service uses `Restart=no`. A later timer fire — not a systemd
  auto-restart — is the retry mechanism.
- The application receives a cooperative budget via `--batch-timeout 6300`
  (105 min) on `ExecStart`; it stops itself normally around that budget.
- `RuntimeMaxSec=14400` (4h) in the daily-ingest drop-in is an **emergency safety
  wall only**, intentionally larger than the 2h timer interval. It must not be
  used as the normal scheduling mechanism.
- `TimeoutStopSec=300`: on stop, SIGTERM escalates to SIGKILL after 5min.

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

## omnigraph-wiki-evolve.service — W5B normal evolution worker (no timer yet)

`omnigraph-wiki-evolve.service` is a **standalone oneshot worker** for W5B wiki
suggestion evolution. It is NOT part of the 13 ingest service+timer pairs above.

**(a) Scope — normal autonomous suggestion evolution only.** The unit runs the
worker in its normal mode: deterministic scan of `kb/wiki/_suggestions/*.json`,
source-aware local hydration of article evidence (read-only SQLite, never the
network), and exactly **one DeepSeek call per due suggestion** (`--limit 10`
caps eligible attempts). No timer file exists for this unit yet — the service
is started manually (or by the T9 timer, once selected).

**(b) Historical bootstrap is NEVER a systemd unit.** `--bootstrap-existing`
is a manual, rollout-only mode (denominator/buffer/LightRAG-graph accounting,
fallback LLM pass, exit codes 0/1/2 for operators). It is intentionally absent
from `ExecStart` and must not be added: bootstrap is a one-time migration tool,
not an autonomous routine.

**(c) Timer schedule intentionally NOT created here.** No
`omnigraph-wiki-evolve.timer` exists in this directory. The schedule is
selected and deployed in T9, after live production recon (queue volume,
provider latency) — do not invent a cadence before then.

**TimeoutStartSec=3600 (1h) — evidence basis (measured 2026-08-14, isolated
temp wiki root + temp DB copy, real DeepSeek):** one attempt (hydration +
single evaluator call, ~19.6K-char page + ~15K-char evidence prompt) measured
10.8 s and 6.1 s wall-clock (mean ~8.4 s). `--limit 10` ⇒ typical run ~1–2
min. Provider ceiling per attempt: 300 s client timeout
(`OMNIGRAPH_DEEPSEEK_TIMEOUT` default) × (1 + 2 SDK retries) ≈ 900 s, so the
full-run pathological ceiling is ~9,000 s. 3600 s ≈ 33× the measured typical
run, ≈ 4× a single fully-wedged attempt, and 0.4× the pathological ceiling —
a hung run is killed at 1 h instead of hanging ~2.5 h. No `Restart=` directive:
a later timer fire (T9) is the retry mechanism, matching the ingest contract.

## References

- `.planning/phases/aim-3-cutover/aim-3-CONTEXT.md` — Full FINDINGS 1-10 from Hermes SSH audit, ExecStart equivalents, UTC schedule table
- `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` — CUTOVER-01..05 requirement bodies
- `.planning/ROADMAP-Aliyun-Ingest-Migration-v1.md` — aim-3 milestone overview
- `scripts/cron_daily_ingest.sh` — The tmux wrapper these units replace (do NOT copy its pattern)
