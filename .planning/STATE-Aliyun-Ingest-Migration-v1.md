---
gsd_state_version: 1.0
milestone: Aliyun-Ingest-Migration-v1
milestone_name: — Migrate ingest pipeline Hermes → Aliyun ECS as new authoritative ingest node
status: planning
stopped_at: "Milestone chartered 2026-05-20 evening; PROJECT-Aliyun-Ingest-Migration-v1.md fully patched with Q1-Q6 decisions. Awaiting Aliyun ECS upgrade to 8 vCPU / 16 GB RAM (24h after 2026-05-20) before Phase aim-0 (Readiness) execution."
last_updated: "2026-05-20T22:00:00Z"
last_activity: "2026-05-20 — Milestone Aliyun-Ingest-Migration-v1 chartered; sibling planning files (PROJECT / REQUIREMENTS / ROADMAP / STATE) created; Q1-Q6 all decided; main PROJECT.md updated with parallel milestone pointer."
progress:
  total_phases: 6
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State — Aliyun-Ingest-Migration-v1 (parallel)

## Project Reference

See: `.planning/PROJECT-Aliyun-Ingest-Migration-v1.md` (this milestone)
Parent project: `.planning/PROJECT.md`
Roadmap: `.planning/ROADMAP-Aliyun-Ingest-Migration-v1.md`
Requirements: `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md`

## Current Position

Milestone: Aliyun-Ingest-Migration-v1 (parallel-track to v3.4 / v3.5-Ingest-Refactor / Agentic-RAG-v1)
Phase: aim-0 (Readiness) — NOT STARTED, awaiting Aliyun ECS 8C/16G upgrade (2026-05-21+)
Plan: pending — `/gsd:plan-phase aim-0` after upgrade complete
Status: chartered; all Q1-Q6 decisions logged in PROJECT-Aliyun-Ingest-Migration-v1.md §3-§4
Last activity: 2026-05-20 evening — milestone files written; main PROJECT.md updated

### Phase plan

| Phase | Goal | REQs | T-shirt | Status |
| ----- | ---- | ---- | ------- | ------ |
| aim-0 | Readiness verification on upgraded Aliyun ECS (disk / RTT / mem peak / smoke) | 4 | S | NOT STARTED — awaits 8C/16G upgrade |
| aim-1 | Code + env deploy (git clone + venv + provider keys + local_e2e smoke) | 4 | S | blocked by aim-0 |
| aim-2 | LightRAG storage full migration (Hermes pause + tar.gz + scp + sha256 + count verify) | 5 | M | blocked by aim-1 |
| aim-3 | Cutover (systemd timer + kol_scan.db handoff + Hermes crontab clear + journald) | 5 | M | blocked by aim-2 |
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

### Pending Todos

None tracked. Awaiting Aliyun ECS upgrade verification, then `/gsd:plan-phase aim-0`.

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

## Session Continuity

Last session: 2026-05-20T22:00:00Z
Stopped at: 4 sibling planning docs written + PROJECT.md pointer added; milestone chartered
Resume file: None
Next command: `/gsd:plan-phase aim-0` (after Aliyun ECS upgrade verified, ~2026-05-21+)
