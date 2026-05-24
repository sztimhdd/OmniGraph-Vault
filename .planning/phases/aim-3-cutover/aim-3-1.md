---
plan_id: aim-3-1
phase: aim-3
wave: 1
depends_on: []
requirements_addressed:
  - CUTOVER-01
files_modified:
  - deploy/aliyun/systemd/omnigraph-kol-zombie-cleanup.service
  - deploy/aliyun/systemd/omnigraph-kol-zombie-cleanup.timer
  - deploy/aliyun/systemd/omnigraph-kol-scan.service
  - deploy/aliyun/systemd/omnigraph-kol-scan.timer
  - deploy/aliyun/systemd/omnigraph-kol-classify.service
  - deploy/aliyun/systemd/omnigraph-kol-classify.timer
  - deploy/aliyun/systemd/omnigraph-kol-enrich.service
  - deploy/aliyun/systemd/omnigraph-kol-enrich.timer
  - deploy/aliyun/systemd/omnigraph-rss-fetch.service
  - deploy/aliyun/systemd/omnigraph-rss-fetch.timer
  - deploy/aliyun/systemd/omnigraph-rss-rescrape.service
  - deploy/aliyun/systemd/omnigraph-rss-rescrape.timer
  - deploy/aliyun/systemd/omnigraph-rss-layer2-classify.service
  - deploy/aliyun/systemd/omnigraph-rss-layer2-classify.timer
  - deploy/aliyun/systemd/omnigraph-daily-ingest.service
  - deploy/aliyun/systemd/omnigraph-daily-ingest.timer
  - deploy/aliyun/systemd/omnigraph-daily-digest.service
  - deploy/aliyun/systemd/omnigraph-daily-digest.timer
  - deploy/aliyun/systemd/omnigraph-reconcile.service
  - deploy/aliyun/systemd/omnigraph-reconcile.timer
  - deploy/aliyun/systemd/omnigraph-afternoon-ingest.service
  - deploy/aliyun/systemd/omnigraph-afternoon-ingest.timer
  - deploy/aliyun/systemd/omnigraph-evening-ingest.service
  - deploy/aliyun/systemd/omnigraph-evening-ingest.timer
  - deploy/aliyun/systemd/omnigraph-vertex-probe.service
  - deploy/aliyun/systemd/omnigraph-vertex-probe.timer
  - deploy/aliyun/systemd/README.md
autonomous: true
t_shirt: M
---

# aim-3-1 — Author 13 systemd unit files (CUTOVER-01 part 1/2)

## Goal

Author all 26 systemd unit files (13 `.service` + 13 `.timer`) into `deploy/aliyun/systemd/` in the repo, plus a README.md describing deployment usage. These are the canonical, version-controlled unit definitions. aim-3-2 will copy them to Aliyun and enable them.

The 13 units convert the 13 enabled Hermes agent-cron jobs to Aliyun systemd. ADT schedules from Hermes are converted to UTC (ADT+3h) for `OnCalendar=`. All ExecStart lines use `/root/OmniGraph-Vault/venv-aim1/bin/python` (Python 3.11 ingest venv from aim-1 DEPLOY-02), NOT the kb-api `venv/`.

This plan is autonomous (agent-only): no operator prompt, no Aliyun SSH. It produces files in the local repo and commits them. The actual `cp /etc/systemd/system/...` + `systemctl enable` happens in aim-3-2.

## Acceptance criteria

1. All 26 unit files exist under `deploy/aliyun/systemd/` matching `files_modified` list.
2. Every `.service` file contains the canonical `[Unit] / [Service] / [Install]` blocks per CONTEXT.md template.
3. Every `.timer` file contains `[Unit] / [Timer] / [Install]` with `OnCalendar=` matching the UTC schedule table (CONTEXT.md §3 / §4).
4. All ExecStart lines reference `/root/OmniGraph-Vault/venv-aim1/bin/python` (NOT `venv/bin/python`).
5. The 3 ingest-loop services (`omnigraph-daily-ingest.service`, `omnigraph-afternoon-ingest.service`, `omnigraph-evening-ingest.service`) include the `ExecStartPre=` line invoking `cleanup_stuck_docs.py --all-failed`.
6. `omnigraph-kol-enrich.service` is a stub (`ExecStart=/bin/true`) with a leading comment block explaining the FINDING 6 gap (no standalone batch enrich script in the repo).
7. README.md at `deploy/aliyun/systemd/README.md` exists and documents: where to copy, how to enable, how to verify, and the kol-enrich gap.
8. No tmux invocation appears anywhere in any unit file (`grep -r tmux deploy/aliyun/systemd/` returns 0 lines).
9. `EnvironmentFile=/root/.hermes/.env` appears in every `.service` file (matches aim-1 DEPLOY-03 decision).
10. Files committed locally to `main` via explicit `git add` (no `-A`), single forward-only commit.

## Task list

### Task 1 — Author all 13 .service files

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-3-cutover\aim-3-CONTEXT.md` lines 122-181 (systemd templates + 13-row schedule table + ExecStartPre snippet)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` lines 60-65 (CUTOVER-01..05 wording)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\scripts\cron_daily_ingest.sh` (study what NOT to copy — tmux wrapper, pycache cleanup, MAX_ARTICLES default of 10. The systemd unit replaces this entirely with a direct python call and `--max-articles 5`.)

**`<acceptance_criteria>`**
- 13 `.service` files exist under `deploy/aliyun/systemd/`.
- Every file: `[Unit]`, `[Service]`, `[Install]` blocks. `Type=simple`, `User=root`, `WorkingDirectory=/root/OmniGraph-Vault`, `EnvironmentFile=/root/.hermes/.env`, `StandardOutput=journal`, `StandardError=journal`, `WantedBy=multi-user.target`.
- ExecStart values match the table in this plan (Section "ExecStart matrix" below).
- The 3 ingest services include `ExecStartPre=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/scripts/cleanup_stuck_docs.py --all-failed`.
- `omnigraph-kol-enrich.service` ExecStart = `/bin/true` and a comment block explains the gap.

**`<action>`**

Use the Write tool to create each `.service` file. Below is the canonical content for each.

**ExecStart matrix (memorize before authoring):**

| Unit | ExecStart |
|---|---|
| omnigraph-kol-zombie-cleanup | `/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/scripts/clean_lightrag_zombies.py` |
| omnigraph-kol-scan | `/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/batch_scan_kol.py --daily` |
| omnigraph-kol-classify | `/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/batch_classify_kol.py --topic Agent --topic LLM --topic RAG --topic NLP --topic CV --min-depth 2 --days-back 1` |
| omnigraph-kol-enrich | `/bin/true` (stub — see FINDING 6) |
| omnigraph-rss-fetch | `/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/enrichment/rss_fetch.py` |
| omnigraph-rss-rescrape | `/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/enrichment/rss_rescrape_bodies.py` |
| omnigraph-rss-layer2-classify | `/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/batch_classify_rss_layer2.py` |
| omnigraph-daily-ingest | `/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/batch_ingest_from_spider.py --from-db --max-articles 5` |
| omnigraph-daily-digest | `/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/enrichment/daily_digest.py` |
| omnigraph-reconcile | `/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/scripts/reconcile_ingestions.py --auto-patch` |
| omnigraph-afternoon-ingest | `/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/batch_ingest_from_spider.py --from-db --max-articles 5` |
| omnigraph-evening-ingest | `/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/batch_ingest_from_spider.py --from-db --max-articles 5` |
| omnigraph-vertex-probe | `/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/scripts/vertex_live_probe.py` |

**Canonical .service template (use for 12 of 13 — exclude `omnigraph-kol-enrich`):**

```ini
[Unit]
Description=OmniGraph <DESCRIPTION>
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/OmniGraph-Vault
EnvironmentFile=/root/.hermes/.env
ExecStart=<EXECSTART FROM MATRIX>
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Ingest-service variant** (for `omnigraph-daily-ingest`, `omnigraph-afternoon-ingest`, `omnigraph-evening-ingest`) — adds ExecStartPre between `EnvironmentFile=` and `ExecStart=`:

```ini
ExecStartPre=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/scripts/cleanup_stuck_docs.py --all-failed
ExecStart=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/batch_ingest_from_spider.py --from-db --max-articles 5
```

**Stub variant for `omnigraph-kol-enrich.service`:**

```ini
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

Description suggestions per unit (use any clear human-readable string — these are journal labels, not parsed):

- `omnigraph-kol-zombie-cleanup`: `OmniGraph kol zombie cleanup (pre-scan health check)`
- `omnigraph-kol-scan`: `OmniGraph daily KOL scan (WeChat MP API)`
- `omnigraph-kol-classify`: `OmniGraph daily KOL Layer-1 classify (5 topics)`
- `omnigraph-kol-enrich`: `OmniGraph kol-enrich (STUB — see FINDING 6)`
- `omnigraph-rss-fetch`: `OmniGraph daily RSS fetch`
- `omnigraph-rss-rescrape`: `OmniGraph daily RSS body rescrape`
- `omnigraph-rss-layer2-classify`: `OmniGraph daily RSS Layer-2 classify`
- `omnigraph-daily-ingest`: `OmniGraph daily ingest 09:00 ADT (12:00 UTC)`
- `omnigraph-daily-digest`: `OmniGraph daily digest`
- `omnigraph-reconcile`: `OmniGraph reconcile ingestions (bidirectional)`
- `omnigraph-afternoon-ingest`: `OmniGraph afternoon ingest 14:00 ADT (17:00 UTC)`
- `omnigraph-evening-ingest`: `OmniGraph evening ingest 21:00 ADT (00:00 UTC next day)`
- `omnigraph-vertex-probe`: `OmniGraph monthly Vertex AI live probe (1st of month)`

### Task 2 — Author all 13 .timer files

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-3-cutover\aim-3-CONTEXT.md` lines 161-176 (UTC schedule table)
- systemd.time(7) man page, OnCalendar syntax. Format `*-*-* HH:MM:SS` = every day at HH:MM:SS UTC. Format `*-*-1 HH:MM:SS` = on the 1st of every month at HH:MM:SS UTC.

**`<acceptance_criteria>`**
- 13 `.timer` files exist under `deploy/aliyun/systemd/`.
- Every file has `[Unit]`, `[Timer]`, `[Install]`.
- Every `Requires=` line references the matching `.service` filename (e.g., `omnigraph-kol-scan.timer` requires `omnigraph-kol-scan.service`).
- `OnCalendar=` values match the UTC schedule table exactly (no copy-paste of an ADT time):

| Timer | OnCalendar (UTC) |
|---|---|
| omnigraph-kol-zombie-cleanup.timer | `*-*-* 10:55:00` |
| omnigraph-kol-scan.timer | `*-*-* 11:00:00` |
| omnigraph-kol-classify.timer | `*-*-* 11:15:00` |
| omnigraph-kol-enrich.timer | `*-*-* 11:30:00` |
| omnigraph-rss-fetch.timer | `*-*-* 09:00:00` |
| omnigraph-rss-rescrape.timer | `*-*-* 09:30:00` |
| omnigraph-rss-layer2-classify.timer | `*-*-* 11:20:00` |
| omnigraph-daily-ingest.timer | `*-*-* 12:00:00` |
| omnigraph-daily-digest.timer | `*-*-* 12:30:00` |
| omnigraph-reconcile.timer | `*-*-* 12:30:00` |
| omnigraph-afternoon-ingest.timer | `*-*-* 17:00:00` |
| omnigraph-evening-ingest.timer | `*-*-* 00:00:00` |
| omnigraph-vertex-probe.timer | `*-*-1 11:00:00` |

- `Persistent=true` on every `.timer` (so a missed fire during reboot/maintenance fires on next available wallclock window).
- `WantedBy=timers.target` in every `[Install]`.

**`<action>`**

Use the Write tool to create each `.timer` file using this canonical template:

```ini
[Unit]
Description=OmniGraph <DESCRIPTION> timer
Requires=<SERVICE FILENAME>

[Timer]
OnCalendar=<UTC SCHEDULE>
Persistent=true

[Install]
WantedBy=timers.target
```

Description suggestions: same as the matching .service Description with " timer" appended.

### Task 3 — Author deploy/aliyun/systemd/README.md

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-3-cutover\aim-3-CONTEXT.md` (full file — to write the gap section accurately)

**`<acceptance_criteria>`**
- `deploy/aliyun/systemd/README.md` exists and contains:
  - Purpose and scope (CUTOVER-01 of aim-3 milestone)
  - Deployment command (target dir `/etc/systemd/system/`)
  - Enable command pattern (`systemctl enable --now omnigraph-*.timer`)
  - Verify command (`systemctl list-timers omnigraph-*`)
  - The 13-row table mapping each unit → ADT schedule → UTC schedule (so the on-host operator can check at a glance)
  - The FINDING 6 kol-enrich gap (stub `/bin/true`, real ExecStart pending)
  - The kol_scan.db handoff note (this dir contains the systemd units; the DB sync happens in aim-3-3)
  - Pointer back to `.planning/phases/aim-3-cutover/aim-3-CONTEXT.md`

**`<action>`**

Use the Write tool to create the README. Suggested skeleton (agent should expand/edit as needed for clarity, but the listed sections must all appear):

```markdown
# Aliyun systemd ingest units

These 13 service+timer pairs replace the Hermes agent-cron entries that
formerly drove KOL scan / classify / RSS fetch / ingest / reconcile /
digest / vertex-probe on the Hermes box. They are deployed to the
Aliyun ECS at `/etc/systemd/system/` as part of aim-3 cutover.

## Deployment

(Step-by-step: scp the unit files to /etc/systemd/system/, daemon-reload,
enable --now, verify list-timers.)

## Schedule table (ADT → UTC)

| Unit | ADT | UTC OnCalendar |
| --- | --- | --- |
| omnigraph-kol-zombie-cleanup | 07:55 | `*-*-* 10:55:00` |
... (all 13 rows)

## Known gap — kol-enrich stub (FINDING 6)

(Explain the gap and the deferred resolution.)

## kol_scan.db handoff

(One-paragraph pointer: aim-3-3 syncs the DB from Hermes to Aliyun
before the timers are enabled; thereafter Aliyun owns writes.)

## References

- `.planning/phases/aim-3-cutover/aim-3-CONTEXT.md`
- `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` (CUTOVER-01..05)
```

### Task 4 — Local sanity check + commit

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\CLAUDE.md` — Lessons Learned 2026-05-06 #5 + 2026-05-15 #1 (forward-only commits, explicit `git add`, never `-A`)
- Memory `feedback_git_add_explicit_in_parallel_quicks.md`

**`<acceptance_criteria>`**
- Sanity grep on `deploy/aliyun/systemd/` returns expected counts (see action below).
- Single forward-only commit on `main` containing all 27 files (26 unit files + README.md).
- Commit message follows conventional commits format (`docs(aim-3): ...` or `feat(aim-3): ...`).
- `git status` clean post-commit.

**`<action>`**

```bash
# Sanity checks (PowerShell-friendly via bash tool)
ls deploy/aliyun/systemd/ | wc -l   # expect 27 (26 unit files + README.md)
grep -l "venv/bin/python" deploy/aliyun/systemd/   # expect 0 (everything must use venv-aim1)
grep -l "venv-aim1/bin/python" deploy/aliyun/systemd/   # expect 12 (all .service except kol-enrich stub)
grep -r "tmux" deploy/aliyun/systemd/   # expect 0
grep -lE "OnCalendar=" deploy/aliyun/systemd/*.timer | wc -l   # expect 13
grep -lE "EnvironmentFile=/root/\.hermes/\.env" deploy/aliyun/systemd/*.service | wc -l   # expect 13
grep -lE "ExecStartPre=" deploy/aliyun/systemd/*ingest*.service | wc -l   # expect 3 (daily, afternoon, evening)

# Commit (explicit add, no -A)
git add deploy/aliyun/systemd/
git status   # confirm only deploy/aliyun/systemd/* staged
git commit -m "feat(aim-3): author 13 systemd unit files for Aliyun ingest cutover (CUTOVER-01)"
git log -1 --name-only
```

If any sanity check returns the wrong count, fix the offending file(s) BEFORE committing.

## Abort/rollback protocol

| Condition | Action |
| --- | --- |
| Any sanity grep returns wrong count | Fix the offending file(s) before commit. Do not commit half-correct units — bug ships to Aliyun in aim-3-2. |
| Accidental `git add -A` would absorb other working-tree changes | Run `git status` before `git add`. If working tree is dirty with unrelated files, stash them first OR use `git add deploy/aliyun/systemd/<each-file>` to be safe. |
| Need to redo a unit file after commit | Forward-fix: edit + new commit. Do NOT amend (per `feedback_no_amend_in_concurrent_quicks.md`). |

## Evidence to capture

- 26 unit files + README under `deploy/aliyun/systemd/`
- One forward-only commit on `main` with all files
- No EVIDENCE/ markdown for this plan (the unit files themselves are the evidence; aim-3-2 evidence captures their actual deployment + enable on Aliyun)
