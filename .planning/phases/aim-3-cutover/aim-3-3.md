---
plan_id: aim-3-3
phase: aim-3
wave: 3
depends_on:
  - aim-3-2
requirements_addressed:
  - CUTOVER-02
  - CUTOVER-03
  - CUTOVER-05
files_modified:
  - .planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-EVIDENCE.md
autonomous: false
t_shirt: M
---

# aim-3-3 — kol_scan.db pre-cutover sync + Hermes jobs disable + CUTOVER-EVIDENCE.md

## Goal

Three couples requirements that must execute in this order to preserve correctness:

1. **CUTOVER-02 part 1** — Final pre-cutover sync of `data/kol_scan.db` from Hermes to Aliyun (operator-side scp from Hermes, agent verifies arrival on Aliyun). This guarantees Aliyun's DB is current at the cutover boundary; any rows Hermes wrote between aim-2 close and this sync are captured.
2. **CUTOVER-03** — Disable all 13 Hermes ingest jobs in `~/.hermes/cron/jobs.json` via Hermes operator prompt. After disable, no Hermes-side ingest writes happen and Aliyun's systemd timers (enabled at aim-3-2) become the sole writer.
3. **CUTOVER-02 part 2 + CUTOVER-05** — Record cutover-window timestamps and the count of "missed-window" articles (Q1a accepted 1-day data loss, no backfill).

The last task writes the consolidated `CUTOVER-EVIDENCE.md` file referenced by §7 SC #2 and §7 SC #5.

**Note on §7 SC #2 invariant:** Per FINDING 2, Hermes `crontab -l | grep -E "ingest|kol_scan|rss" | wc -l` is ALREADY 0 (Hermes ingest jobs live in jobs.json, not crontab). The §7 SC #2 invariant is trivially satisfied; this plan captures the agent-verified output as evidence.

**Pre-condition:** aim-3-2 EVIDENCE shows verdict PASS (all 13 timers enabled+active on Aliyun). If aim-3-2 is FAIL, do NOT execute this plan — Aliyun cannot become sole writer until its timers are healthy.

## Acceptance criteria

1. SSH `aliyun-vitaclaw stat -c %Y /root/OmniGraph-Vault/data/kol_scan.db` returns a UNIX mtime ≥ the operator-reported scp time on Hermes side.
2. SSH `aliyun-vitaclaw sqlite3 /root/OmniGraph-Vault/data/kol_scan.db "SELECT COUNT(*) FROM articles"` returns a row count ≥ the Hermes-side row count captured in operator output (sync transferred ≥ as many rows as Hermes had).
3. SSH `aliyun-vitaclaw sqlite3 /root/OmniGraph-Vault/data/kol_scan.db "SELECT MAX(layer2_at) FROM articles"` returns a non-null timestamp ≤ now.
4. Operator-pasted `cat ~/.hermes/cron/jobs.json | python3 -c "..."` output (per the Hermes operator prompt) shows ALL 13 omnigraph-related jobs with `enabled: false` (or equivalent — operator paste shows job-name → False mapping).
5. Hermes-side `crontab -l | grep -E "ingest|kol_scan|rss" | wc -l` = `0` (FINDING 2 — already satisfied; captured as agent-verified evidence via SSH read-only).
6. `EVIDENCE/CUTOVER-EVIDENCE.md` exists, committed locally, contains:
   - Hermes-side scp source ISO timestamp + Aliyun-side received ISO timestamp (the cutover-window START).
   - Hermes-side jobs.json post-disable verbatim output.
   - Hermes-side `crontab -l` output (for §7 SC #2 invariant).
   - Aliyun-side DB row count + MAX(layer2_at) verification.
   - The 13-row Hermes-disabled-jobs table cross-referenced against the 13 systemd timers from aim-3-2.
   - The Q1a 1-day-data-loss window: `cutover_window_start` (Hermes last write before disable) → `cutover_window_end` (Aliyun first natural timer fire — placeholder until aim-3-4 captures it).
   - Estimated count of "missed-window" articles (extrapolated from 24h scan rate).

## Task list

### Task 1 — Operator scp's data/kol_scan.db from Hermes to Aliyun

**`<read_first>`**

- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` line 62 (CUTOVER-02 wording — the DB lives at repo root `data/kol_scan.db`, NOT under `~/.hermes/omonigraph-vault/`)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-3-cutover\aim-3-CONTEXT.md` FINDING 10 (final sync from Hermes is needed to capture rows written between aim-2 close and aim-3-3 cutover)
- Memory `aliyun_vitaclaw_ssh.md` (Aliyun connection details — operator uses SSH alias on Hermes side)

**`<acceptance_criteria>`**

- Operator returns: Hermes-side `~/OmniGraph-Vault/data/kol_scan.db` row count and MAX(layer2_at), captured BEFORE scp.
- Operator returns: scp wallclock duration (file is small — ~tens of MB — should be seconds).
- Operator returns: Aliyun-side `stat` and `sqlite3 SELECT COUNT(*)` post-scp.

**`<action>`**

Agent writes the following operator prompt and asks user to forward to Hermes verbatim:

```hermes-operator-prompt
You are operating the Hermes production host (家用 PC, WSL2). This is the aim-3-3 final pre-cutover sync of data/kol_scan.db. Run these commands in a single SSH session and paste the FULL output back to the local Claude Code session.

Step 1 — capture Hermes-side baseline (read-only):

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ" | tee /tmp/aim3-3-sync-start.iso

cd ~/OmniGraph-Vault
ls -la data/kol_scan.db
sha256sum data/kol_scan.db | tee /tmp/aim3-3-hermes-db.sha256
echo "=== Hermes row count ==="
sqlite3 data/kol_scan.db "SELECT COUNT(*) AS articles FROM articles;"
sqlite3 data/kol_scan.db "SELECT MAX(layer2_at) AS max_layer2_at FROM articles;"
sqlite3 data/kol_scan.db "SELECT COUNT(*) AS rss_articles FROM rss_articles;"
```

Step 2 — confirm no in-flight Hermes ingest is writing the DB right now (avoid scp'ing a half-written file). The Hermes ingest jobs are scheduled at fixed times; if you scp during an active ingest window, the DB may be locked.

```bash
pgrep -af batch_scan_kol || echo "NONE"
pgrep -af batch_classify_kol || echo "NONE"
pgrep -af batch_ingest_from_spider || echo "NONE"
pgrep -af rss_classify || echo "NONE"
pgrep -af rss_fetch || echo "NONE"
```

If ANY of those returns a process, sleep 60 and re-check until all are NONE. Do NOT proceed to scp while any ingest is running.

Step 3 — scp data/kol_scan.db to Aliyun. The Aliyun host has the SSH alias `aliyun-vitaclaw` from your local machine; replicate it on Hermes if not already configured. Connection details for Aliyun are in your local notes — do NOT paste them into the response.

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
echo "=== scp data/kol_scan.db ==="
time scp data/kol_scan.db aliyun-vitaclaw:/root/OmniGraph-Vault/data/kol_scan.db
echo "scp_exit=$?"
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

Step 4 — confirm Hermes-side DB is unchanged after scp (sanity that no race wrote during transfer):

```bash
sha256sum data/kol_scan.db
diff <(cat /tmp/aim3-3-hermes-db.sha256) <(sha256sum data/kol_scan.db) && echo "SHA matches pre-scp" || echo "SHA DIFFERS — investigate"
```

Paste the FULL output of all four steps. Do NOT abbreviate. The agent needs the row counts + ISO timestamps + scp wallclock duration verbatim.

```

After receiving operator output, the agent moves to Task 2.

### Task 2 — Agent verifies kol_scan.db arrived on Aliyun

**`<read_first>`**
- Operator response from Task 1 (Hermes-side baseline counts + sha256)

**`<acceptance_criteria>`**
- Aliyun-side sha256 matches Hermes-side sha256 byte-for-byte.
- Aliyun-side `sqlite3 SELECT COUNT(*) FROM articles` matches Hermes-side count.
- Aliyun-side `sqlite3 SELECT MAX(layer2_at) FROM articles` matches Hermes-side value.

**`<action>`**

```bash
ssh aliyun-vitaclaw bash -c "'
set -e
cd /root/OmniGraph-Vault

echo \"=== Aliyun-side post-scp ===\"
date -u +\"%Y-%m-%dT%H:%M:%SZ\"
ls -la data/kol_scan.db
sha256sum data/kol_scan.db

echo \"=== Aliyun row count ===\"
sqlite3 data/kol_scan.db \"SELECT COUNT(*) AS articles FROM articles;\"
sqlite3 data/kol_scan.db \"SELECT MAX(layer2_at) AS max_layer2_at FROM articles;\"
sqlite3 data/kol_scan.db \"SELECT COUNT(*) AS rss_articles FROM rss_articles;\"
'"
```

Capture output to `.scratch/aim-3-3-aliyun-verify-<TS>.log`.

Compare line-by-line with Hermes-side output from Task 1. If anything mismatches, abort plan; investigate (most likely scp partially failed or a race wrote between Hermes Step 1 and Step 3).

### Task 3 — Operator disables all 13 omnigraph jobs in Hermes jobs.json

**`<read_first>`**

- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-3-cutover\aim-3-CONTEXT.md` lines 25-44 (the 13 Hermes job names — agent must list them in the operator prompt verbatim)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-3-cutover\aim-3-CONTEXT.md` line 184-188 (jobs.json verify command)

**`<acceptance_criteria>`**

- Operator returns: Hermes-side jobs.json post-disable showing all 13 omnigraph-related jobs with `enabled: false`.
- Operator returns: Hermes-side `crontab -l` post-disable (FINDING 2 — should already be clean of ingest entries; captured for §7 SC #2 invariant evidence).
- Operator returns: Hermes-side `pgrep -af batch_ingest_from_spider | batch_scan_kol | rss_*` after the next scheduled fire window passes — should remain empty (proves disable took effect).

**`<action>`**

Agent writes the following operator prompt:

```hermes-operator-prompt
You are operating the Hermes production host. This is the aim-3-3 cutover step that hands off ingest authority from Hermes to Aliyun. After this step, Hermes will NOT write to kol_scan.db or LightRAG storage anymore.

Step 1 — capture pre-disable jobs.json (read-only):

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ" | tee /tmp/aim3-3-disable-start.iso

echo "=== jobs.json BEFORE disable (omnigraph-related only) ==="
cat ~/.hermes/cron/jobs.json | python3 -c "
import json, sys
jobs = json.load(sys.stdin).get('jobs', [])
keep = []
for j in jobs:
    name = j.get('name', '')
    prompt = j.get('prompt', '')
    if 'omnigraph' in name.lower() or any(x in prompt for x in ['ingest','scan','classify','enrich','reconcile','digest','rss-fetch','rss-rescrape','vertex-probe','rss_classify','rss_ingest','batch_scan_kol','batch_ingest_from_spider','batch_classify','clean_lightrag_zombies']):
        keep.append({'name': name, 'enabled': j.get('enabled'), 'cron': j.get('cron','')})
print(json.dumps(keep, indent=2, ensure_ascii=False))
"

echo "=== crontab -l BEFORE (FINDING 2: should already be clean of ingest) ==="
crontab -l
echo "=== crontab grep ==="
crontab -l | grep -E "ingest|kol_scan|rss" | wc -l
```

Step 2 — DISABLE all 13 omnigraph-related jobs. The 13 jobs to disable are (from Hermes jobs.json):

1. KOL扫描前健康检查 (07:55 ADT)
2. 每日KOL扫描 (08:00 ADT)
3. daily-classify-kol (08:15 ADT)
4. daily-enrich (08:30 ADT)
5. rss-fetch (06:00 ADT)
6. rss-rescrape-bodies (06:30 ADT)
7. daily-classify-rss-layer2 (08:20 ADT)
8. daily-ingest (09:00 ADT)
9. daily-digest (09:30 ADT)
10. reconcile-ingestions (09:30 ADT)
11. daily-ingest-afternoon (14:00 ADT)
12. daily-ingest-evening (21:00 ADT)
13. vertex-probe-monthly (08:00 ADT, 1st of month)

Use the Hermes agent (its own /jobs UI or the equivalent shell command) to set `enabled: false` on each of those 13 jobs. Do NOT delete them — set to `enabled: false` so they can be re-enabled if cutover rolls back.

Step 3 — confirm post-disable state:

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ" | tee /tmp/aim3-3-disable-confirmed.iso

echo "=== jobs.json AFTER disable (omnigraph-related — expect all enabled=false) ==="
cat ~/.hermes/cron/jobs.json | python3 -c "
import json, sys
jobs = json.load(sys.stdin).get('jobs', [])
for j in jobs:
    name = j.get('name', '')
    prompt = j.get('prompt', '')
    if 'omnigraph' in name.lower() or any(x in prompt for x in ['ingest','scan','classify','enrich','reconcile','digest','rss-fetch','rss-rescrape','vertex-probe','rss_classify','rss_ingest','batch_scan_kol','batch_ingest_from_spider','batch_classify','clean_lightrag_zombies']):
        print(f\"{name:50s} enabled={j.get('enabled')}\")"

echo "=== crontab -l AFTER ==="
crontab -l
echo "=== crontab grep (must equal 0) ==="
crontab -l | grep -E "ingest|kol_scan|rss" | wc -l

echo "=== running ingest workers (must be empty) ==="
pgrep -af batch_ingest_from_spider; echo "exit=$?"
pgrep -af batch_scan_kol; echo "exit=$?"
pgrep -af batch_classify_kol; echo "exit=$?"
pgrep -af rss_fetch; echo "exit=$?"
pgrep -af rss_classify; echo "exit=$?"
pgrep -af reconcile_ingestions; echo "exit=$?"
```

Paste the FULL output of all three steps. The agent needs the verbatim jobs.json mapping AND the disable-confirmed ISO timestamp.

```

After receiving operator output, the agent records the disable-confirmed timestamp as `cutover_window_start` (the moment Hermes is no longer authoritative).

### Task 4 — Compute Q1a missed-window article estimate (CUTOVER-05)

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` line 65 (CUTOVER-05 wording — accept 1-day data loss, record window + count, no mitigation)
- aim-3-2 evidence file `EVIDENCE/CUTOVER-01-deploy-evidence.md` (UTC schedule of all 13 timers — used to determine the next-fire wallclock = `cutover_window_end_estimate`)

**`<acceptance_criteria>`**
- `cutover_window_start` ISO recorded (= Hermes disable-confirmed timestamp from Task 3).
- `cutover_window_end_estimate` ISO recorded (= the next-fire wallclock of `omnigraph-rss-fetch.timer` OR `omnigraph-kol-scan.timer`, whichever comes first after `cutover_window_start`).
- `missed_window_hours` = (end_estimate - start) in hours, rounded to one decimal.
- `estimated_missed_articles` = a rough number (compute from 24h scan rate × missed_window_hours / 24). For Hermes baseline 24h scan rate, query Aliyun-side `data/kol_scan.db` for the past 7 days of `scanned_at` row counts (it has the migrated history from aim-2). If unavailable, document `estimated_missed_articles = "unknown — see notes"` and proceed.

**`<action>`**

```bash
ssh aliyun-vitaclaw bash -c "'
cd /root/OmniGraph-Vault
echo \"=== 7-day scan rate (rows/day from articles.scanned_at) ===\"
sqlite3 data/kol_scan.db \"
  SELECT date(scanned_at) AS day, COUNT(*) AS rows
  FROM articles
  WHERE scanned_at >= date(\\\"now\\\", \\\"-7 days\\\")
  GROUP BY day
  ORDER BY day DESC;
\"
echo \"=== average articles/24h ===\"
sqlite3 data/kol_scan.db \"
  SELECT AVG(daily_count) FROM (
    SELECT date(scanned_at) AS day, COUNT(*) AS daily_count
    FROM articles
    WHERE scanned_at >= date(\\\"now\\\", \\\"-7 days\\\")
    GROUP BY day
  );
\"

echo \"=== 7-day RSS fetch rate (rss_articles.fetched_at) ===\"
sqlite3 data/kol_scan.db \"
  SELECT date(fetched_at) AS day, COUNT(*) AS rows
  FROM rss_articles
  WHERE fetched_at >= date(\\\"now\\\", \\\"-7 days\\\")
  GROUP BY day
  ORDER BY day DESC;
\" 2>/dev/null || echo \"(rss_articles table may not have fetched_at; skip)\"
'"
```

Capture output to `.scratch/aim-3-3-missed-window-<TS>.log`.

Compute `estimated_missed_articles = average_articles_per_24h × (missed_window_hours / 24)`. Round up. Record in evidence.

### Task 5 — Write CUTOVER-EVIDENCE.md and commit

**`<read_first>`**

- All operator outputs from Tasks 1 + 3
- All `.scratch/aim-3-3-*.log` from Tasks 2 + 4
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-3-cutover\aim-3-CONTEXT.md` FINDING 6 (kol-enrich gap — must be documented in CUTOVER-EVIDENCE.md)

**`<acceptance_criteria>`**

- File `.planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-EVIDENCE.md` exists.
- Sections (all required): "kol_scan.db sync evidence" (CUTOVER-02), "Hermes jobs.json post-disable" (CUTOVER-03), "Hermes crontab post-disable" (CUTOVER-03 §7 SC #2 invariant), "Cutover window + missed-window estimate" (CUTOVER-05), "FINDING 6 kol-enrich gap" (carried over from CONTEXT — visible in cutover ledger), "13-row Hermes-job → Aliyun-timer cross-reference table".
- Single forward-only commit on `main` via explicit `git add`.

**`<action>`**

Use the Write tool to create `EVIDENCE/CUTOVER-EVIDENCE.md`. Skeleton (agent fills in `[paste ...]` placeholders verbatim):

```markdown
# CUTOVER-EVIDENCE.md — aim-3 cutover ledger

Phase: aim-3 (cutover)
REQs covered: CUTOVER-02, CUTOVER-03, CUTOVER-05 (CUTOVER-01 in separate evidence file, CUTOVER-04 in aim-3-4)

---

## 1. kol_scan.db pre-cutover sync (CUTOVER-02)

### Hermes-side baseline (Task 1 output)

- Sync-start ISO: [paste from /tmp/aim3-3-sync-start.iso]
- Hermes `data/kol_scan.db` size + sha256: [paste]
- Hermes `articles` row count: [paste]
- Hermes `MAX(layer2_at)`: [paste]
- Hermes `rss_articles` row count: [paste]
- Hermes scp duration (wallclock): [paste from `time scp` output]

### Aliyun-side post-scp (Task 2 output)

- Aliyun `data/kol_scan.db` sha256: [paste]
- Aliyun `articles` row count: [paste — must equal Hermes]
- Aliyun `MAX(layer2_at)`: [paste — must equal Hermes]
- Aliyun `rss_articles` row count: [paste — must equal Hermes]
- sha256 byte-match: [PASS / FAIL]

---

## 2. Hermes jobs.json post-disable (CUTOVER-03)

Disable-confirmed ISO: [paste from /tmp/aim3-3-disable-confirmed.iso]

### Hermes jobs.json — omnigraph-related entries AFTER disable

```

[paste verbatim Step 3 jobs.json python output — 13 lines, all enabled=false]

```

### 13-row Hermes-job → Aliyun-timer cross-reference

| # | Hermes job (jobs.json) | Aliyun systemd timer | UTC schedule |
|---|---|---|---|
| 1 | KOL扫描前健康检查 | omnigraph-kol-zombie-cleanup.timer | `*-*-* 10:55:00` |
| 2 | 每日KOL扫描 | omnigraph-kol-scan.timer | `*-*-* 11:00:00` |
| 3 | daily-classify-kol | omnigraph-kol-classify.timer | `*-*-* 11:15:00` |
| 4 | daily-enrich | omnigraph-kol-enrich.timer | `*-*-* 11:30:00` |
| 5 | rss-fetch | omnigraph-rss-fetch.timer | `*-*-* 09:00:00` |
| 6 | rss-rescrape-bodies | omnigraph-rss-rescrape.timer | `*-*-* 09:30:00` |
| 7 | daily-classify-rss-layer2 | omnigraph-rss-layer2-classify.timer | `*-*-* 11:20:00` |
| 8 | daily-ingest | omnigraph-daily-ingest.timer | `*-*-* 12:00:00` |
| 9 | daily-digest | omnigraph-daily-digest.timer | `*-*-* 12:30:00` |
| 10 | reconcile-ingestions | omnigraph-reconcile.timer | `*-*-* 12:30:00` |
| 11 | daily-ingest-afternoon | omnigraph-afternoon-ingest.timer | `*-*-* 17:00:00` |
| 12 | daily-ingest-evening | omnigraph-evening-ingest.timer | `*-*-* 00:00:00` |
| 13 | vertex-probe-monthly | omnigraph-vertex-probe.timer | `*-*-1 11:00:00` |

---

## 3. Hermes crontab AFTER disable (§7 SC #2 invariant)

```

[paste verbatim crontab -l output from Task 3 Step 3]

```

`crontab -l | grep -E "ingest|kol_scan|rss" | wc -l` = `[N]` (required: 0)

(FINDING 2 — Hermes crontab held only `cognee_batch_processor` + `graphify-refresh.sh` pre-cutover; the §7 SC #2 invariant is trivially satisfied because Hermes ingest jobs lived in jobs.json, not crontab.)

---

## 4. Cutover window + missed-window estimate (CUTOVER-05)

- `cutover_window_start` (Hermes disable-confirmed): [paste ISO]
- `cutover_window_end_estimate` (next Aliyun timer fire — typically `omnigraph-rss-fetch.timer` at next 09:00 UTC OR `omnigraph-kol-scan.timer` at next 11:00 UTC, whichever comes first): [paste ISO]
- `missed_window_hours`: [N.N]
- `estimated_missed_articles`: [N] (extrapolated from 7-day Hermes scan rate of [X] articles/day)
- 7-day scan rate raw query output: [paste from .scratch log Task 4]

**Q1a acceptance:** Articles whose Layer-1 candidate window falls entirely inside [cutover_window_start, cutover_window_end_estimate] are NOT re-evaluated. No mitigation, no backfill. This is the explicit decision per PROJECT §3 Decision Q1a.

---

## 5. FINDING 6 carry-over — kol-enrich stub gap

The Hermes "daily-enrich" job uses the `enrich_article` Hermes skill via `enrichment/run_enrich_for_id.py`. There is no standalone batch enrich script in the repo at aim-3 close. The Aliyun systemd unit `omnigraph-kol-enrich.service` is therefore deployed as a stub (`ExecStart=/bin/true`).

This is a CUTOVER-01 gap that does NOT block aim-3 closure (12 of 13 units functional). Resolution path:

- A derivative milestone OR an ingest-side `--enrich-only` mode flag wires the same code path
- When the real ExecStart is authored, edit `omnigraph-kol-enrich.service` and `systemctl daemon-reload && systemctl restart omnigraph-kol-enrich.timer`

This is a deliberate aim-3 deferral; not in scope for this cutover.

---

## 6. Verdict

- [PASS / FAIL] kol_scan.db Aliyun-side row counts match Hermes-side (CUTOVER-02 part 1)
- [PASS / FAIL] All 13 Hermes jobs disabled in jobs.json (CUTOVER-03)
- [PASS / FAIL] §7 SC #2 invariant: `crontab -l | grep -E ... | wc -l` == 0 (CUTOVER-03)
- [recorded — no PASS/FAIL] Cutover window + missed-window estimate (CUTOVER-05; this is documentation, not a gate)

If any [PASS/FAIL] above is FAIL, do NOT proceed to aim-3-4. Investigate via separate quick.

## 7. Next gate

aim-3-4 — verify journald output after first natural timer fire (CUTOVER-04). The fire schedule is in row 4 above. The earliest natural fire after `cutover_window_start` is the soonest UTC OnCalendar.
```

Then commit:

```bash
git add .planning/phases/aim-3-cutover/EVIDENCE/CUTOVER-EVIDENCE.md
git status   # confirm only this file staged
git commit -m "docs(aim-3): record CUTOVER-02/03/05 cutover evidence (kol_scan.db sync + Hermes disable + missed-window)"
git log -1 --name-only
```

## Abort/rollback protocol

| Condition | Action |
| --- | --- |
| Hermes-side `pgrep` shows in-flight ingest before scp | Wait per operator prompt; do NOT scp during active write. If still in-flight after 60 min, abort plan + investigate (cron may not be pausing). |
| Aliyun-side post-scp sha256 ≠ Hermes-side sha256 | scp partially failed OR Hermes raced. Abort. Operator re-runs Task 1 entirely. |
| Aliyun-side row count < Hermes-side row count | Same as above — abort + re-scp. |
| Operator reports any of 13 jobs still `enabled=true` after Task 3 | Re-run Task 3 — operator missed a job. The 13-row table in this plan is canonical. |
| Hermes `crontab -l | grep -E "ingest|kol_scan|rss" | wc -l` returns > 0 | Per FINDING 2 this should never happen. If it does, an unrelated cron entry has matched the regex (e.g., a script named `rss_*.sh`). Capture full crontab in evidence and document why the count is non-zero (e.g., "1 hit is `cognee_batch_processor` matching 'ingest' substring — unrelated"). |
| Operator dropped session mid-prompt | Re-run from Step 1 of the dropped prompt; previous output is invalidated. |
| Need to re-enable a Hermes job because aim-3-4 fails | Operator-side: flip `enabled: true` on the affected job in jobs.json. Aliyun-side: `systemctl disable --now omnigraph-<name>.timer`. Forward-only; do NOT amend this plan's commit. |

## Evidence to capture

- `EVIDENCE/CUTOVER-EVIDENCE.md` — committed locally
- `.scratch/aim-3-3-*.log` — uncommitted, agent-side reference

aim-3-4 will append a "First-fire journald evidence" section to CUTOVER-EVIDENCE.md OR create a separate `EVIDENCE/CUTOVER-04-journald-evidence.md` (aim-3-4 plan decides).
