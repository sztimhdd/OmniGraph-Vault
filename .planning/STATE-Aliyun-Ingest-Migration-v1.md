---
gsd_state_version: 1.0
milestone: Aliyun-Ingest-Migration-v1
milestone_name: — Migrate ingest pipeline Hermes → Aliyun ECS as new authoritative ingest node
status: execution-active
stopped_at: "aim-3 plan-phase ✅ DONE 2026-05-24 — 4/4 plans checker PASS; next: /gsd:execute-phase aim-3"
last_updated: "2026-05-24T00:00:00Z"
last_activity: "2026-05-24 — aim-2 CLOSED PASS + aim-3 plan-phase complete; 4 PLAN.md + CONTEXT.md written"
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 4
  completed_plans: 4
---

# Project State — Aliyun-Ingest-Migration-v1 (parallel)

## Project Reference

See: `.planning/PROJECT-Aliyun-Ingest-Migration-v1.md` (this milestone)
Parent project: `.planning/PROJECT.md`
Roadmap: `.planning/ROADMAP-Aliyun-Ingest-Migration-v1.md`
Requirements: `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md`

## Current Position

Milestone: Aliyun-Ingest-Migration-v1 (parallel-track to v3.4 / v3.5-Ingest-Refactor / Agentic-RAG-v1)
Phase: aim-1 ✅ DONE — aim-2 next
Plan: pending — `/gsd:plan-phase aim-0` after upgrade complete
Status: chartered; all Q1-Q6 decisions logged in PROJECT-Aliyun-Ingest-Migration-v1.md §3-§4
Last activity: 2026-05-20 evening — milestone files written; main PROJECT.md updated

### Phase plan

| Phase | Goal | REQs | T-shirt | Status |
| ----- | ---- | ---- | ------- | ------ |
| aim-0 | Readiness verification on upgraded Aliyun ECS (disk / RTT / mem peak / smoke) | 4 | S | ✅ DONE — commit f3cd667 / 2026-05-21 |
| aim-1 | Code + env deploy (git clone + venv + provider keys + local_e2e smoke) | 4 | S | ✅ DONE — commit 718c52d / 2026-05-23 |
| aim-2 | LightRAG storage full migration (Hermes pause + tar.gz + scp + sha256 + count verify) | 5 | M | blocked by aim-1 |
| aim-3 | Cutover (systemd timer + kol_scan.db handoff + Hermes crontab clear + journald) | 5 | M | ✅ DONE — commit aim-3-4 evidenced / 2026-05-24 |
| aim-4 | Daily sync Aliyun → Hermes + Databricks (consumer-side cron + retry + journald) | 4 | S | blocked by aim-3 |
| aim-5 | 7-day stability (systemd / reconcile / daily sync — all 7d zero-failure) | 5 | S (7-day wall-clock) | blocked by aim-4 |

Total: 27 REQs across 6 phases, 0 orphans expected.

### Immediate next step

**Aliyun ECS upgrade to 8 vCPU / 16 GB RAM** is the gating event (decided 2026-05-20 Q6). User reports 24h ETA; expected 2026-05-21 evening or 2026-05-22.

Once upgrade is verified (`free -h`, `nproc` show new spec), invoke `/gsd:plan-phase aim-0` to produce aim-0 PLAN.md. Hermes still serves ingest cron in parallel during this window — no time pressure.

## Parallel-Track Boundary

This STATE file tracks Aliyun-Ingest-Migration-v1 ONLY. v3.4 progress remains in `.planning/STATE.md`. v3.5-Ingest-Refactor in `.planning/STATE-v3.5-Ingest-Refactor.md`. Agentic-RAG-v1 in `.planning/STATE-Agentic-RAG-v1.md`.

The four milestones share:

- The same git working tree (commits land on `main`)
- The same code repository deployed to multiple consumers (Hermes, Aliyun, Databricks, local `.dev-runtime/`)
- The `omnigraph_search.query.search()` cross-milestone contract (KG-stable; this migration does not touch query-side semantics)

The four milestones do NOT share:

- Phase numbering (v3.4 = 19-22; Agentic-RAG-v1 = `ar-N`; v3.5 = `ir-N`; **this = `aim-N`**)
- Sibling planning files
- Execute gates / blockers (this milestone's blocker is Aliyun ECS upgrade; v3.5 is post-deploy 24h audit; etc.)

## Cross-milestone contract

**Ingest substrate moves; query API contract unchanged.**

- `omnigraph_search.query.search(query_text, mode)` signature stable (Agentic-RAG-v1 contract honored)
- kb-api on Aliyun stays read-only SSG + DB (no `/api/synthesize` — owned by Agentic-RAG-v1, not this milestone) — Decision 4 / Q5c
- LightRAG storage on-disk format unchanged; only its physical location moves Hermes → Aliyun
- Wiki source-of-truth = repo (Decision 1); during migration period commits remain manual; auto-write-back deferred to LLM-Wiki-Integration-P2 milestone (Q4c)
- Daily sync Aliyun → Hermes + Databricks subsumes the standalone cold-backup milestone (Decision 5); RPO ≤ 24h is acceptable per user

## Hermes Operational State at Migration Start (2026-05-20 baseline)

Source: `~/.hermes/cron/jobs.json` registry on Hermes (`ohca.ddns.net`-side). 3 active ingest crons confirmed via STATE-v3.5-Ingest-Refactor.md (post-ir-4 deploy 2026-05-20):

| Cron | Schedule (ADT) | Notes |
| --- | --- | --- |
| daily-ingest | 09:00 | confirmed via ir-4 Step 8 resume |
| afternoon-ingest | 14:00 | confirmed via ir-4 Step 8 resume |
| evening-ingest | 21:00 | confirmed via ir-4 Step 8 resume |

These are the 3 ingest-loop crons. Plus 8 supporting jobs (`每日KOL扫描`, `KOL扫描前健康检查`, `rss-fetch`, `daily-digest`, `vertex-probe-monthly`, etc. — see STATE-v3.5-Ingest-Refactor.md). Total 11 ingest-related cron-side jobs to retire at aim-3 cutover (per PROJECT §5 In Scope #4 + #7 + Success Criterion #2 — `crontab -l | grep -E "ingest|kol_scan|rss" | wc -l == 0`).

**Hermes will gain 1 new daily-pull cron at aim-4** (consumer-side `scripts/sync-from-aliyun.sh`). Net: 11 → 1 cron on Hermes post-migration.

## Aliyun ECS Operational State at Migration Start (2026-05-20 baseline)

Source: `aliyun_vitaclaw_ssh.md` memory + STATE.md current observations.

| Component | State |
| --- | --- |
| Spec | Pre-upgrade (TBD vCPU / RAM) — upgrading to 8C/16G in 24h per Q6 |
| Role | read-only consumer (Caddy + kb-api SSG + `/api/articles` + `/api/article/{hash}`) |
| LightRAG storage | NONE on Aliyun (1.6 GB at Hermes is sole copy); aim-2 migrates it over |
| Daily cron | NONE on Aliyun (all ingest cron on Hermes); aim-3 installs systemd timer |
| LLM API keys | Vertex SA only (kb-api consumer use); aim-1 deploys DeepSeek + SiliconFlow keys |
| Disk free | TBD ≥5 GB required per aim-0 READY-01 |
| `kol_scan.db` | read-only copy via prior sync; aim-3 cutover changes write source to Aliyun |

## Operator Channel

User has Aliyun root SSH (alias `aliyun-vitaclaw` per memory). Most aim-0..aim-5 work runs as direct ops via Aliyun SSH — agent does NOT SSH to Aliyun for mutating ops; agent writes Aliyun operator prompts (parallel to Hermes-prompt pattern).

Read-only diagnostics (`free`, `df`, `systemctl status`, `journalctl --no-pager`) MAY be run by the agent via Bash when explicitly authorized per query, matching the Hermes pattern in PRINCIPLE 5.

## Accumulated Context

### Roadmap Evolution

- 2026-05-20 evening — Milestone Aliyun-Ingest-Migration-v1 chartered. Q1-Q6 decided; sibling-files layout (`PROJECT-Aliyun-Ingest-Migration-v1.md` etc.) chosen mirroring the v3.5-Ingest-Refactor / Agentic-RAG-v1 precedent. Phase prefix `aim-N` chosen.

### Decisions

Per PROJECT-Aliyun-Ingest-Migration-v1.md §3 (Decisions 1-5) + §4 (Q1-Q6 all closed):

- **Decision 1** — Wiki source-of-truth = repo (Hermes / Databricks / local pull only; Aliyun pushes increments)
- **Decision 2** — Sync script `sync-from-aliyun.sh` deferred until aim-4 (no transitional `sync-from-hermes.sh`)
- **Decision 3** — Migration trigger = "Hermes cron stable" (verified 2026-05-20 evening per user judgment)
- **Decision 4** — kb-api unchanged; query API ownership stays with Agentic-RAG-v1 milestone
- **Decision 5** — Daily sync Aliyun → Hermes + Databricks subsumes standalone cold-backup milestone
- **Q1a** — Simple cutover, accept 1-day data loss
- **Q2a** — Full tar.gz migration + 3 hard constraints (Hermes pause ≥30min / sha256 + entity·relation·chunk count ±0% / Hermes 30-day read-only retention)
- **Q3** — Hermes "retire" = stop 11 ingest crons + read-only + 1 new daily-pull cron
- **Q4c** — Manual wiki commit during migration; auto-hook deferred to LLM-Wiki-Integration-P2
- **Q5c** — kb-api scope unchanged; Agentic-RAG-v1 owns query API
- **Q6** — Aliyun ECS upgrade to 8 vCPU / 16 GB RAM 24h after charter
- **2026-05-21 — Gate 1 CLOSED (path correction)** — SSH-probed Aliyun ECS post aim-0 PASS (data captured in `.scratch/` session log). kb-api already running on `/root/OmniGraph-Vault/` + `/root/.hermes/.env`; HEAD=`4eaef45` (2026-05-16 v1.0.x; working tree dirty from manual SCP); no `daily_rebuild.sh`. **Verdict: NOT supersede** (kb-4 owns DEPLOY-04 + DEPLOY-05 work aim-N doesn't cover). Execution order = **kb-4-lite first → aim-N second** (Option A). **aim-1 ROADMAP path revised at plan-phase time**: target deploy = `/root/OmniGraph-Vault/` (in-place, NOT `/opt/omnigraph-vault/`); env file = extend `/root/.hermes/.env` (NOT replace with `/etc/omnigraph/.env mode 600`). The original `/opt/omnigraph-vault` + `/etc/omnigraph/.env` plan would create dual repo trees / dual SQLite DBs / dual env files conflicting with the running kb-api. RUNBOOK to be updated alongside aim-N plan-phase. **Gate 1 deferred-action block (lines 140-153) superseded by this closure.**

### Pending Todos

- aim-0 PASS recorded 2026-05-21 (commit f3cd667; READY-01 INFO / READY-02 WARN-Vertex / READY-03 PASS / READY-04 PASS).
- aim-1 plan-phase complete 2026-05-21 — 4 plans (aim-1-1..aim-1-4) ready for execute-phase, queued behind kb-4-lite (Gate 1 Option A order, STATE:132-133).
- Next: `/gsd:execute-phase aim-1` AFTER kb-4-08 verification closes.
- aim-1 execute ✅ DONE 2026-05-23 (commit 718c52d); UAT 7/7 PASS; aim-1-UAT.md; next: /gsd:plan-phase aim-2
- aim-2 execute ✅ DONE 2026-05-23 (commits: STORAGE-01..04 prior waves; STORAGE-05 commit 3b2ebad); Q2a (a)(b)(c) all PASS; backup at lightrag_storage.aliyun-pre-aim2-bak-20260523T231949Z; next: /gsd:plan-phase aim-3
- aim-3 plan-phase ✅ DONE 2026-05-24; 4 PLAN.md (aim-3-1..4) + CONTEXT.md (13-job SSH audit); plan-checker PASS; next: /gsd:execute-phase aim-3
- Hermes lightrag_storage cold-backup retention deadline: 2026-06-22 (set by aim-2-5; cleanup at aim-5 close or later)

**On aim-0 PASS — deferred actions (registered 2026-05-21; do NOT act before aim-0 verdict = PASS):**

1. **Gate 1 — kb-4 vs aim-1 overlap audit (HARD-STOP, P3)**

   Before invoking `/gsd:plan-phase aim-1`, STOP and resolve:
   - Q1: Is kb-4 (KB-v2 ROADMAP last unstarted phase — Ubuntu ingest cron deploy) naturally superseded by aim-1 (same Aliyun ECS host, same OmniGraph-Vault deploy, same cron)?
   - Q2: If yes → mark `kb-4 SUPERSEDED-BY aim-1` in `.planning/ROADMAP-KB-v2.md`; do not execute kb-4 standalone.
   - Q3: If no (kb-4 has scope aim-1 doesn't cover — e.g., Hermes-side cron handoff or grayscale rollback) → enumerate diffset → decide order (aim-1 first / kb-4 first / parallel).

   Procedure (executed by orchestrator at PASS time):
   1. Read `.planning/ROADMAP-KB-v2.md` kb-4 segment (Goal + Success Criteria)
   2. Read `.planning/ROADMAP-Aliyun-Ingest-Migration-v1.md` aim-1 segment (same fields)
   3. `AskUserQuestion` with 3 options (supersede / parallel / serial) + the diffset
   4. Only after user decision: invoke the chosen `/gsd:plan-phase` command

   Red line: do NOT silently advance to `/gsd:plan-phase aim-1`. This is a milestone-topology decision, not a plan-phase decision.

2. **Memo 2 — v2.2-future improvement registration (P4, register-only)**

   Append 1 line to `.planning/STATE-KB-v2.md` under "v2.2-future / 已识别但未排期" section (create the section if missing):

   - `translate_kb.py` incremental `apply.sql` flush + resume guard (source: kb-v2.2-7 Phase 5 backfill single-batch risk, recorded in `.scratch/translate-backfill-260520.md`)
   - Trigger to upgrade to phase: next translation backfill > 500 rows **OR** retry budget < current 4-call (either condition).

   Forward-only edit; no PLAN, no ROADMAP-KB-v2 phase-table entry, no phase scaffolding. This memo only ensures the design risk doesn't rot in `.scratch/`.

Red lines for both:
- Gate 1 is a hard-stop. aim-0 PASS does NOT auto-flow into aim-1 — Q1/Q2/Q3 must be answered first.
- Memo 2 modifies only the future-improvements section of STATE-KB-v2.md; forward-only, no overwrite of existing content.
- Strictly do not opportunistically expand scope to draft kb-4 / aim-1 plans together while resolving Gate 1.

### Blockers/Concerns

- **Aliyun ECS spec upgrade** — gating event for aim-0. ETA ~2026-05-21 evening per user.
- **Hermes cron continues running during aim-0..aim-1** — provides candidate-pool freshness during prep. Stops only at aim-3 cutover (per Q1a simple-cutover decision).
- **Migration window risk** (Q2a constraint #1) — Hermes cron MUST be paused ≥30min during aim-2 tar.gz + scp + verify; agent prompt for Hermes pause must be coordinated with Aliyun extract step.
- **Daily sync v1 = full pull** — known limitation, not optimized; performance follow-up tracked as `Aliyun-Sync-v2` derivative milestone (PROJECT §8) — not blocking this milestone.
- **P2 wiki write-back ssh deploy key** — needed for LLM-Wiki-Integration-P2 milestone's auto-hook; OUT of scope for this migration. Tracked in §8 derivatives.

## Performance Metrics

(populated as phases complete)

Expected baselines after aim-0 readiness (per PROJECT §6 risk mitigation):

- LightRAG ainsert peak memory < 16 GB (vs. ~2 GB on Hermes; 8x headroom expected on upgraded Aliyun)
- DeepSeek + SiliconFlow + Vertex RTT from Aliyun (cn-east-mainland) — expected ≤ Hermes (corp network) for SiliconFlow; comparable for Vertex; comparable for DeepSeek
- Monthly cost = upgraded ECS baseline + LLM API spend (target: same envelope as Hermes-side baseline, $1-5/day)

**aim-1 actuals (2026-05-23):** aim-1-4 smoke: batch_elapsed=778.44s / budget=28800s (2.7%); 85 nodes / 93 edges; SiliconFlow 38/38 vision OK; venv-aim1 py3.11.0rc1 153 pkgs

## Session Continuity

Last session: 2026-05-20T22:00:00Z
Stopped at: 4 sibling planning docs written + PROJECT.md pointer added; milestone chartered
Resume file: None
Next command: `/gsd:plan-phase aim-2`
