# Phase aim-5: 7-day stability watch — Context

**Gathered:** 2026-05-25
**Status:** Ready for planning
**Source:** ROADMAP-Aliyun-Ingest-Migration-v1.md §"Phase aim-5" (lines 174-198) +
REQUIREMENTS-Aliyun-Ingest-Migration-v1.md STAB-01..05 (lines 76-84) +
PROJECT-Aliyun-Ingest-Migration-v1.md §7 SC #1/#4/#5/#6/#8 + STATE-Aliyun-Ingest-Migration-v1.md

+ aim-4-CONTEXT.md (template) + memory pointers (aliyun_vitaclaw_ssh.md, hermes_ssh.md)

---

<domain>
## Phase Boundary

7-day wall-clock observation window over the post-cutover Aliyun ingest substrate.
**No code work.** Operator-side audit only. End-state: 7 consecutive days where
(a) Aliyun systemd ingest timers fire zero-fail, (b) bidirectional reconcile ghost
rate < 1%, (c) Hermes daily-pull cron + Databricks `git pull` succeed zero-fail,
(d) kb-api on Aliyun shows no behavioral regression, (e) Vertex AI quota usage
stays within projected envelope. Milestone Aliyun-Ingest-Migration-v1 closes only
after aim-5 passes.

**In scope:**

- Daily checklist runs against 5 STAB REQs (STAB-01..05)
- `OBSERVATION.md` scaffold the operator updates day-by-day for 7 days
- Closure of the 4-item TODO checklist deferred from aim-4-4-EVIDENCE PARTIAL
  (per STATE-Aliyun-Ingest-Migration-v1.md:143)
- Hermes lightrag_storage cold-backup retention reminder (deadline 2026-06-22 per
  STATE:144) — surface to operator at aim-5 close (cleanup itself is post-milestone)
- Failure-day handling protocol: any failure-day on STAB-01/03 OR threshold-bust
  on STAB-02/05 OR regression on STAB-04 → aim-5 does NOT close, follow-up commit
  lands as a new fix, 7-day window restarts from the day the fix lands

**Not in scope:**

- ANY code changes (a code change becomes a regression on aim-1..4, not part of aim-5)
- kb-api `/api/synthesize` introduction (Decision 4 / Q5c — owned by Agentic-RAG-v1)
- Wiki write-back automation (Q4c — owned by LLM-Wiki-Integration-P2)
- Hermes lightrag_storage cleanup itself (out of scope — calendar reminder only)
- Performance tuning / sync-v2 optimization (Aliyun-Sync-v2 derivative)
- Aliyun ECS spec re-evaluation (the 8C/16G upgrade is locked at aim-0)

</domain>

<decisions>
## Critical Findings

### FINDING 1 — Failure-day tolerance is asymmetric across the 5 STAB REQs

| REQ | Pass shape | Failure-day tolerance |
| --- | ---------- | --------------------- |
| STAB-01 (systemd timers) | 7 consecutive days zero unit failures | **0** — single failed-fire restarts window |
| STAB-02 (reconcile) | ghost_success rate < 1% rolling 7-day | threshold-based; single day ≥ 1% triggers operator review (NOT auto-restart unless migration-related) |
| STAB-03 (daily sync) | 7 consecutive days zero failures | **0** — any 3-retry-exhausted OR 48h marker-trigger restarts window |
| STAB-04 (kb-api regression) | curl probes match pre-migration baseline | continuous — one regression breaks PASS |
| STAB-05 (Vertex quota) | 7-day Aliyun spend × ~4.3 ≤ Hermes prior monthly | threshold-based; > 20% over linear projection triggers operator review |

Planner must split daily-watch tasks (STAB-01/02/03) from one-shot probes (STAB-04
single-pass curl baseline + post-7d re-curl; STAB-05 7-day window quota readout).

### FINDING 2 — Hermes WSL2 TZ deviation surfaced at aim-4-3 G5 — affects sync-watch journal queries

Hermes WSL2 host TZ = America/Halifax (NOT UTC as the plan README originally
assumed). The aim-4-3 fix landed `OnCalendar=*-*-* 05:00:00 UTC` with explicit
UTC suffix on the systemd timer, but **journal queries still need careful
`--since` handling**: `journalctl --since "7 days ago"` runs in the host's
local TZ (America/Halifax = ADT, UTC-3), so a 7-day window starting "now" pulls
events from 7×24h ago in ADT, which is correct for daily-pull cron coverage but
should be sanity-checked when the operator switches between local time and
UTC interpretation in OBSERVATION.md entries.

Planner: include a one-line `date -u; date` at the head of each daily check
script so OBSERVATION.md captures both clocks side-by-side and removes
TZ-interpretation ambiguity post-hoc.

### FINDING 3 — STAB-02 ghost_success rate must distinguish migration-related from pre-existing v1.0.x noise floor

`feedback_contract_shape_change_full_audit.md` lineage notes the bidirectional
reconcile scope was extended in v1.0.y closure (commit `587fa85`) and the
historical noise floor was 1/188 = 0.5% over the v1.0 production day-1 window.
STAB-02 fail-criterion is "any single day ≥ 1% AND root cause is migration-related"
— ambiguous "is it migration?" judgments default to operator review, not auto-restart.

Planner: include a column in OBSERVATION.md daily entries for `ghost_success_count`

+ a comment field for root-cause hypothesis (e.g., "1 ghost on aim-N article-id=XXX,
LightRAG ainsert finished after `OMNIGRAPH_PROCESSED_RETRY=300` budget exhausted —
NOT migration-related, classify as v1.0.x noise floor"). Decision rule documented
inline: `if migration_related: restart; else: log + continue`.

### FINDING 4 — Vertex baseline for STAB-05 = pre-migration Hermes monthly Vertex spend

Per REQUIREMENTS:84, the pass criterion is "7-day Aliyun spend × ~4.3 ≤ Hermes
prior monthly Vertex spend". This requires:

1. Pre-aim-5 capture: pull Hermes-side Vertex spend from GCP "Quotas & System Limits"
   dashboard for a representative pre-migration month (e.g., 2026-04 Hermes-only
   month) — record in OBSERVATION.md baseline section
2. Daily capture during aim-5: same dashboard, project = Aliyun's GCP project,
   record running 7-day total
3. Day-7 verdict: `7d_aliyun × 4.3 ≤ baseline_hermes_monthly` PASS, else `> 20% over`
   triggers operator review (PROJECT §6 Risk row 6 cost-up alarm)

Planner: STAB-05 plan includes the dashboard URL pattern and a snapshot capture
discipline (one screenshot per day under `aim-5-EVIDENCE/vertex-quota-day-N.png`).

### FINDING 5 — STAB-04 baseline = pre-migration kb-api responses; capture once at aim-5 day-0

Per REQUIREMENTS:83, the verification probes are:

- `curl -s http://<aliyun>/api/articles | jq '. | length'` → matches pre-migration
  count (or grows monotonically as Aliyun ingest adds articles)
- `curl -s http://<aliyun>/api/article/<known-hash>` → 200 with same body shape
- `curl -s http://<aliyun>/api/search?mode=fts&q=<known>` → expected hit

"Pre-migration count" needs an anchor: at aim-5 day-0 (= aim-4 close + 1 day grace,
= ~2026-05-25), capture current kb-api `/api/articles` count + select 3 known
article hashes + 1 known FTS query as the **frozen baseline**. Re-run at day-3,
day-7. Monotonic growth is acceptable; shape regression is not.

Planner: STAB-04 plan freezes the baseline file at
`aim-5-EVIDENCE/kb-api-baseline-day0.json` (curl outputs piped to jq + saved) and
asserts day-7 against it.

**Decision 4 / Q5c discipline:** STAB-04 also probes `curl -s http://<aliyun>/api/synthesize`
→ expected `404` (or equivalent "endpoint not found"). If it returns 200, the kb-api
scope was violated — Agentic-RAG-v1 milestone leaked into Aliyun-Ingest-Migration-v1.
Hard fail.

### FINDING 6 — STAB-01 covers 3 ingest-loop timers, NOT all 11 retired Hermes crons

Per REQUIREMENTS:80, the 3 daily ingest-loop equivalents are
`omnigraph-daily-ingest.timer` (09:00 ADT), `omnigraph-afternoon-ingest.timer`
(14:00 ADT), `omnigraph-evening-ingest.timer` (21:00 ADT). The other 8 supporting
jobs (kol_scan health-check, rss-fetch, daily-digest, vertex-probe-monthly, etc.)
are tracked under CUTOVER-04 (aim-3) journald evidence sampling, not STAB-01
zero-fail discipline.

This is intentional: STAB-01 disciplines the 3 highest-cost ingest loops daily;
the supporting 8 jobs have lower fire frequency and looser pass criteria (per-fire
journald entry, not per-day zero-fail).

Planner: STAB-01 plan filter is `omnigraph-(daily|afternoon|evening)-ingest.service`
specifically, NOT `omnigraph-*.service` wildcard.

### FINDING 7 — STAB-03 = Hermes daily-pull (SYNC-02) AND Databricks `git pull` BOTH must pass

Per REQUIREMENTS:82, STAB-03 covers two consumers:

- Hermes-side `omnigraph-daily-pull.service` (systemd, fires 02:00 ADT = 05:00 UTC)
  — verified via `journalctl -u omnigraph-daily-pull.service` showing `sync OK on
  attempt N` daily, no 48h marker file `/tmp/aliyun-sync-failed-*` aged > 48h
- Databricks-side `git pull` consumer — verified via day-7 spot-check
  `cd <databricks-repo>; git log -1 kb/wiki/` shows commit timestamp ≥ aim-4 deploy
  (per FINDING 8 of aim-4-CONTEXT.md, this depends on Aliyun manual wiki commit
  cadence per Q4c — operator-driven during aim-5)

Planner: STAB-03 plan has TWO daily checks (Hermes systemd journal probe + marker-file
probe) and ONE day-7 check (Databricks git log). Failure-day tolerance is 0 across
both consumers.

### FINDING 8 — aim-4-4-EVIDENCE PARTIAL 4-item TODO carry-over closure

Per STATE:143, aim-4-4 deferred a 4-item TODO checklist to aim-5 STAB checkpoint.
The exact items are NOT in STATE; planner must read aim-4-4-EVIDENCE.md to
enumerate them, then assign each item to whichever STAB plan is the natural
checkpoint (most likely STAB-03 daily-pull validation closure since aim-4-4 was
the SYNC-03 Databricks verification + Aliyun manual wiki commit guide plan).

Planner step: at planning time, `Read .planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md`,
extract the 4-item TODO checklist verbatim, distribute across STAB plans where
appropriate, and document the routing in CONTEXT.md or the relevant plan's
acceptance criteria.

### FINDING 9 — Read-only diagnostics are agent-runnable; mutating ops are operator-only

Per STATE:108, the agent does NOT SSH to Aliyun for mutating ops. Read-only
diagnostics (`free`, `df`, `systemctl status`, `journalctl --no-pager`, `curl`)
MAY be run by the agent via Bash when explicitly authorized per query. This
matches the aim-1+ agent IS the operator memory pointer (`feedback_aim1_agent_is_operator.md`).

For aim-5 specifically: ALL daily checks are read-only diagnostics. Agent CAN
SSH Aliyun + Hermes via Bash to gather check outputs and write them into
OBSERVATION.md daily entries. Mutating operations (e.g., restarting a failed
systemd unit, clearing a stale marker file, updating env vars) ARE operator-driven
and require an Aliyun/Hermes operator prompt.

Planner: each STAB plan's daily-check section labels probes as `[agent-runnable]`
or `[operator-only]` so the executor knows where to draw the line.

### FINDING 10 — OBSERVATION.md scaffold is the central artifact

Per ROADMAP §aim-5 Notes: "Phase plan is a checklist + an OBSERVATION.md scaffold
that operator updates daily." This is the closure artifact for aim-5 — without
7 days of OBSERVATION.md entries, aim-5 does not close.

Schema:

```markdown
# Aliyun-Ingest-Migration-v1 / aim-5 / OBSERVATION

## Baseline (captured day-0)
- Aliyun kb-api article count: <N>
- Hermes pre-migration Vertex monthly spend: $<X>
- Known kb-api article hashes for STAB-04 probe: [<h1>, <h2>, <h3>]
- Known FTS query for STAB-04 probe: "<term>"
- aim-4-4-EVIDENCE TODO carry-over (4 items): [verbatim from aim-4-4-EVIDENCE.md]

## Day 1 (YYYY-MM-DD ADT / YYYY-MM-DD UTC)
### STAB-01 (systemd ingest timers)
- daily-ingest 09:00 ADT: ✅/❌ (Last triggered: ..., journal grep result: ...)
- afternoon-ingest 14:00 ADT: ✅/❌ (...)
- evening-ingest 21:00 ADT: ✅/❌ (...)
### STAB-02 (reconcile ghost_success)
- ghost_success_count: N
- total_ingestions: M
- rate: N/M = X.X%
- root-cause hypothesis (if any ghost): "..."
- migration-related? Y/N
### STAB-03 (Hermes daily-pull + Databricks git pull)
- Hermes journal: "sync OK on attempt N" present? ✅/❌
- Marker file age: <h
- Databricks git log probe (day-7 only): N/A on day 1
### STAB-04 (kb-api regression — day-7 only spot-check, day-0 baseline)
- N/A daily; record full results at day-0 baseline + day-7 verdict
### STAB-05 (Vertex quota)
- 1-day Aliyun spend: $<x>
- running 7-day total: $<X>
- screenshot: aim-5-EVIDENCE/vertex-quota-day-1.png

## Day 2..7 (same schema)

## Day-7 verdict
- STAB-01: PASS / RESTART (any single failure-day → RESTART)
- STAB-02: PASS / OPERATOR-REVIEW
- STAB-03: PASS / RESTART
- STAB-04: PASS / FAIL (curl probes match baseline + /api/synthesize → 404)
- STAB-05: PASS / OPERATOR-REVIEW (7d × 4.3 ≤ baseline check)
- aim-4-4 TODO carry-over: 4/4 closed? Y/N
- Hermes lightrag_storage retention reminder surfaced to operator (deadline 2026-06-22)? Y/N
- aim-5 milestone close: PASS / RESTART
```

</decisions>

<canonical_refs>

## Canonical References

### Planning artifacts (read first)

- `.planning/ROADMAP-Aliyun-Ingest-Migration-v1.md` (lines 174-198) — Phase aim-5 goal + 5 STAB REQs success criteria + open notes
- `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` (lines 76-84) — STAB-01..05 verbatim
- `.planning/STATE-Aliyun-Ingest-Migration-v1.md` (lines 41-43, 108, 122-126, 143-144) — milestone state, agent boundary, decisions, aim-4-4 TODO carry-over, retention deadline
- `.planning/PROJECT-Aliyun-Ingest-Migration-v1.md` §7 SC #1/#4/#5/#6/#8 + §3 Decision 4 + §6 Risk rows 6/8 — pass criteria + cost/sync risk anchors
- `.planning/phases/aim-3-cutover/` (any EVIDENCE files) — for STAB-01 timer naming + journald baseline patterns
- `.planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md` — for the 4-item TODO carry-over enumeration (PLANNER: read at plan time)

### Memory pointers (do NOT cite verbatim — verify before asserting)

- `aliyun_vitaclaw_ssh.md` — Aliyun host (read-only diagnostics OK)
- `hermes_ssh.md` — Hermes host (read-only diagnostics OK)
- `feedback_contract_shape_change_full_audit.md` — STAB-02 reconcile scope lineage
- `feedback_aim1_agent_is_operator.md` — agent-as-operator override for aim-N phases (read-only ops)

### Reference patterns

- `aim-4-CONTEXT.md` — structural template (this file mirrors its `<domain>` / `<decisions>` / `<canonical_refs>` / `<specifics>` / `<deferred>` / `<plan_skeleton_hint>` shape)
- aim-3 systemd timer + journald evidence patterns — STAB-01 borrows the journal grep recipe verbatim

</canonical_refs>

<specifics>
## Specific Implementation Notes

### Daily check command checklist (planner bake into each STAB plan)

#### STAB-01 — Aliyun systemd ingest timers (3 timers)

```bash
# Run on Aliyun via SSH (read-only — agent-runnable)
ssh aliyun-vitaclaw '
  date -u; date
  for unit in omnigraph-daily-ingest omnigraph-afternoon-ingest omnigraph-evening-ingest; do
    echo "=== $unit ==="
    systemctl status ${unit}.timer --no-pager | head -10
    echo "--- last 24h journal ---"
    journalctl -u ${unit}.service --since "24 hours ago" --no-pager | grep -E "Failed|exit-code|Started|Stopped" || echo "(empty)"
  done
  echo "=== 7d failure grep ==="
  journalctl -u "omnigraph-*-ingest.service" --since "7 days ago" --no-pager | grep -E "Failed|exit-code" | wc -l
'
```

Pass criterion: `Last triggered` advances daily for each of the 3 timers AND
the 7d failure grep returns `0`.

#### STAB-02 — Reconcile ghost_success rate

```bash
# Run on Aliyun via SSH (read-only — agent-runnable)
ssh aliyun-vitaclaw '
  date -u; date
  cd /root/OmniGraph-Vault
  source venv-aim1/bin/activate 2>/dev/null || source venv/bin/activate
  python -c "
import sqlite3
conn = sqlite3.connect(\"data/kol_scan.db\")
c = conn.cursor()
# 24h ghost rate (status=ok in ingestions but missing in LightRAG kv_store)
# OR status=failed but present in LightRAG kv_store (bidirectional scope)
c.execute(\"SELECT COUNT(*) FROM ingestions WHERE status IN (\\\"ok\\\", \\\"failed\\\") AND ingested_at >= datetime(\\\"now\\\", \\\"-24 hours\\\")\")
total = c.fetchone()[0]
print(f\"total_24h={total}\")
"
  # Then run reconcile script (whatever the prod path is — planner: confirm)
  ls scripts/ | grep -E "reconcile|ghost" || echo "(no reconcile script — operator-side run)"
'
```

Pass criterion: `ghost_success_count / total_24h < 0.01` (1%) for each daily
window. Threshold bust → operator review (NOT auto-restart unless migration-related
per FINDING 3).

#### STAB-03 — Hermes daily-pull + Databricks git pull

```bash
# Run on Hermes via SSH (read-only — agent-runnable)
ssh -p 49221 sztimhdd@ohca.ddns.net '
  date -u; date
  echo "=== last 24h omnigraph-daily-pull journal ==="
  journalctl -u omnigraph-daily-pull.service --since "24 hours ago" --no-pager | grep -E "sync OK|sync attempt|ERROR|Failed" || echo "(empty)"
  echo "=== marker file age ==="
  ls -la /tmp/aliyun-sync-failed-* 2>/dev/null | head -5 || echo "(no marker — good)"
  echo "=== timer next fire ==="
  systemctl list-timers omnigraph-daily-pull.timer --no-pager
'

# Day-7 only — run from Databricks repo checkout (operator-driven OR agent if databricks workspace SSH available)
# (Databricks does not have a stable SSH alias; planner: emit operator prompt for day-7 git log probe)
```

Pass criterion: Hermes journal shows `sync OK on attempt N` daily, NO marker
file aged > 48h. Day-7 Databricks `git log -1 kb/wiki/` timestamp ≥ aim-4 deploy
timestamp. Failure-day tolerance: 0.

#### STAB-04 — kb-api regression probes (day-0 baseline + day-7 verdict)

```bash
# Day-0 baseline capture (ONE-TIME at aim-5 start)
curl -s http://<aliyun-host>/api/articles | jq '. | length' > .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/kb-api-baseline-day0.json
# Pick 3 known hashes from the response, save them
curl -s http://<aliyun-host>/api/articles | jq '.[0:3] | map(.hash)' >> .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/kb-api-baseline-day0.json

# Day-7 verdict
for h in $(jq -r '.[]' .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/known-hashes.json); do
  curl -s -o /dev/null -w "%{http_code}" http://<aliyun-host>/api/article/$h  # expect 200
done
curl -s "http://<aliyun-host>/api/search?mode=fts&q=<known>" | jq '. | length'  # expect ≥ 1

# Decision 4 / Q5c discipline
curl -s -o /dev/null -w "%{http_code}" http://<aliyun-host>/api/synthesize   # expect 404 — kb-api scope unchanged
```

Pass criterion: article count grows monotonically OR matches baseline; all 3
known-hash probes return 200; FTS query returns ≥ 1 hit; `/api/synthesize` returns
404 (or 405 / equivalent "not implemented" — anything OTHER than 200).

#### STAB-05 — Vertex AI quota readout

```text
# Manual operator step (no SSH automation — GCP dashboard is browser-side)
# URL pattern: https://console.cloud.google.com/iam-admin/quotas?project=<aliyun-gcp-project-id>
# Filter: Service = "Vertex AI API"; Metric = "Generate content requests" + "Embed content requests"
# Capture: daily total → screenshot → save to aim-5-EVIDENCE/vertex-quota-day-N.png
# Day-0 baseline: same dashboard but for Hermes-side GCP project, prior month total ($)
```

Pass criterion: `7d_aliyun × 4.3 ≤ baseline_hermes_monthly`. Threshold > 20% over
linear projection → operator review (PROJECT §6 Risk row 6).

### OBSERVATION.md scaffold path

`.planning/phases/aim-5-stability-watch/OBSERVATION.md` — created at aim-5 plan-execute
day-0; filled in daily by operator (or agent on operator's behalf for read-only
sections); reviewed at day-7 to compute milestone close verdict.

### Evidence directory

`.planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/`

- `kb-api-baseline-day0.json` (STAB-04 frozen baseline)
- `vertex-quota-day-1.png` ... `vertex-quota-day-7.png` (STAB-05 daily screenshots)
- `daily-checks-day-N.log` (concatenated stdout from STAB-01/02/03 ssh probes per day)

### aim-4-4 TODO carry-over closure procedure

At planning time, planner must:

1. `Read .planning/phases/aim-4-daily-sync/aim-4-4-EVIDENCE.md`
2. Locate the 4-item TODO checklist (deferred to aim-5 per STATE:143)
3. Reproduce the 4 items verbatim in `aim-5-CONTEXT.md` Findings OR in a dedicated
   plan's acceptance criteria (most likely STAB-03 since aim-4-4 was the SYNC-03
   verification + Aliyun manual wiki commit guide)
4. Add a day-7 verdict row to OBSERVATION.md schema: `aim-4-4 TODO carry-over closure: 4/4 / 3/4 / ...`

### Hermes lightrag_storage retention reminder (calendar-only)

Per STATE:144, the Hermes-side `~/.hermes/omonigraph-vault/lightrag_storage/`
read-only retention deadline is 2026-06-22 (set by aim-2-5 at storage migration
close). Cleanup itself is OUT of aim-5 scope, but at aim-5 day-7 close, OBSERVATION.md
must surface this deadline to operator with a one-line note: "Hermes lightrag_storage
read-only retention deadline = 2026-06-22 (~28 days post-aim-5 close); operator
to schedule cleanup post-milestone."

</specifics>

<deferred>
## Deferred (out of aim-5 scope)

- **Hermes lightrag_storage cleanup itself** — calendar reminder only at aim-5
  close; cleanup is post-milestone operator task (deadline 2026-06-22)
- **Wiki write-back automation** (Q4c → LLM-Wiki-Integration-P2 milestone)
- **Sync v2 incremental optimization** (Aliyun-Sync-v2 derivative)
- **kb-api `/api/synthesize` introduction** (Decision 4 / Q5c → Agentic-RAG-v1 milestone) —
  STAB-04 actively verifies this stays out of scope
- **Code changes during aim-5** — any code change becomes a regression on
  aim-1..4 and restarts the 7-day window
- **Aliyun ECS spec re-evaluation** — 8C/16G is locked at aim-0
- **Reconcile scope further extension** — current bidirectional scope from
  v1.0.y closure (commit 587fa85) is sufficient for STAB-02; further extension
  is v1.x candidate

</deferred>

<plan_skeleton_hint>

## Suggested Plan Decomposition (planner is free to adjust)

Suggested 5 plans + 1 scaffolding plan, all parallel (no inter-plan dependencies
since they observe independent subsystems):

1. **aim-5-1** — STAB-01 daily systemd ingest timer watch (3 timers × 7 days)
   - Daily SSH probe to Aliyun: `systemctl status` + `journalctl` grep for the
     3 ingest-loop services
   - Files written: `aim-5-EVIDENCE/daily-checks-day-N.log` (STAB-01 section)
   - Acceptance: 7 consecutive days zero failures; failure-day tolerance 0
   - REQs: STAB-01

2. **aim-5-2** — STAB-02 daily reconcile ghost_success rate watch (7 days)
   - Daily SSH probe to Aliyun: SQL on `kol_scan.db` ingestions table + reconcile
     script run; compute rate; classify migration-related Y/N if ghost present
   - Files written: `aim-5-EVIDENCE/daily-checks-day-N.log` (STAB-02 section)
   - Acceptance: rate < 1% rolling 7-day; threshold-based handling per FINDING 3
   - REQs: STAB-02

3. **aim-5-3** — STAB-03 Hermes daily-pull + Databricks git-pull watch (7 days +
   day-7 spot-check) + aim-4-4 TODO carry-over closure
   - Daily SSH probe to Hermes: journal grep + marker file age check
   - Day-7 only: Databricks `git log -1 kb/wiki/` (operator prompt OR agent if SSH path)
   - aim-4-4-EVIDENCE 4-item TODO checklist closure (planner enumerates at plan time)
   - Files written: `aim-5-EVIDENCE/daily-checks-day-N.log` (STAB-03 section)
   - Acceptance: 7 consecutive days zero failures; tolerance 0; aim-4-4 TODO 4/4 closed
   - REQs: STAB-03

4. **aim-5-4** — STAB-04 kb-api regression probes (day-0 baseline + day-7 verdict)
   - Day-0: capture article count, 3 known hashes, 1 known FTS query → freeze in
     `aim-5-EVIDENCE/kb-api-baseline-day0.json`
   - Day-7: re-curl all probes; compare against baseline; assert `/api/synthesize`
     returns 404 (Decision 4 / Q5c discipline)
   - Files written: `aim-5-EVIDENCE/kb-api-baseline-day0.json`,
     `aim-5-EVIDENCE/kb-api-day7-verdict.md`
   - Acceptance: monotonic article count, all probes 200, `/api/synthesize` ≠ 200
   - REQs: STAB-04

5. **aim-5-5** — STAB-05 Vertex AI quota readout (7-day window) + Hermes baseline
   capture
   - Day-0: capture Hermes-side GCP project prior month Vertex spend → freeze baseline
   - Daily: GCP dashboard screenshot for Aliyun project Vertex spend
   - Day-7: compute `7d_aliyun × 4.3` vs `baseline_hermes_monthly`
   - Files written: `aim-5-EVIDENCE/vertex-quota-day-N.png` (×7),
     `aim-5-EVIDENCE/vertex-baseline.md`
   - Acceptance: `7d × 4.3 ≤ baseline`; > 20% over → operator review
   - REQs: STAB-05

6. **aim-5-6** — OBSERVATION.md scaffold + day-7 close verdict
   - Day-0: instantiate `OBSERVATION.md` per schema in FINDING 10; capture
     baseline section (kb-api article count, Hermes Vertex baseline, known hashes,
     known FTS query, aim-4-4 TODO carry-over verbatim)
   - Day-1..7: append daily entries (compiled from aim-5-1..5 outputs)
   - Day-7: compute close verdict; surface Hermes lightrag_storage retention
     deadline reminder; emit `aim-5-VERIFICATION.md`
   - Files written: `OBSERVATION.md` (canonical), `aim-5-VERIFICATION.md`
   - Acceptance: 7 days populated; all 5 STAB verdicts recorded; aim-4-4 TODO
     4/4 closed; Hermes retention deadline surfaced
   - REQs: (cross-cutting — closes aim-5)

Wave structure:

- Wave 1 (day-0): aim-5-4 baseline capture, aim-5-5 baseline capture, aim-5-6
  OBSERVATION.md scaffold instantiation — ALL parallel
- Wave 2 (day-1..7): aim-5-1, aim-5-2, aim-5-3, aim-5-5 daily probes — ALL parallel
  (daily independent observations, no inter-day dependency until day-7)
- Wave 3 (day-7): aim-5-4 verdict, aim-5-5 verdict, aim-5-3 Databricks spot-check,
  aim-5-6 close verdict — sequential within day-7 (close verdict depends on
  the others completing)

Planner is free to merge aim-5-4 + aim-5-5 baseline captures into aim-5-6 day-0
scaffold, OR consolidate aim-5-1/2/3 daily probes into a single aim-5-daily-watch
plan with 3 sections. The above is one decomposition that maps cleanly 1:1 to STAB
REQs; alternative consolidations are fine if they preserve REQ coverage.

</plan_skeleton_hint>
