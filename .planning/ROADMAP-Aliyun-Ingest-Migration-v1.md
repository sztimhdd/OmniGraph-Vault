# Roadmap: Aliyun-Ingest-Migration-v1

**Milestone:** Aliyun-Ingest-Migration-v1 (parallel-track to v3.4 / v3.5-Ingest-Refactor / Agentic-RAG-v1)
**Created:** 2026-05-20 (evening, after Q1-Q6 closed)
**Phase prefix:** `aim-N` (avoids collision with v3.4 phases 19-22 / Agentic-RAG-v1 `ar-N` / v3.5 `ir-N` / KB-v2 `kb-N` / KDB `kdb-N`)
**Granularity:** Standard (6 phases for 27 v1 REQs)
**Coverage:** 27/27 requirements mapped, 0 orphans

> **Locked design:** `.planning/PROJECT-Aliyun-Ingest-Migration-v1.md` — 5 Decisions + Q1-Q6 closed; no further re-derivation.
> **Cross-milestone contract:** `omnigraph_search.query.search(query_text, mode)` stays stable. Ingest substrate moves Hermes → Aliyun; KG-side query API contract unchanged. kb-api on Aliyun stays read-only SSG + DB (no `/api/synthesize` — owned by Agentic-RAG-v1, not this milestone).

---

## Phase decomposition rationale

**Decomposition style chosen: stage-vertical, observation-gated.**

Three reasons drive the choice:

1. **Each phase is a different host-state checkpoint, not a code-feature slice.** aim-0 verifies Aliyun ECS readiness (no code change). aim-1 lays down code + env (no state change yet). aim-2 moves the LightRAG storage in one cutover-style transfer (write-side state change, but Hermes still authoritative). aim-3 swings ingest authority Hermes → Aliyun (the actual cutover). aim-4 installs daily sync (consumer-side cron; no impact on producer). aim-5 is observation-only (7-day wall-clock, no code work). Splitting on host-state boundaries makes rollback semantics explicit per phase: aim-0 rollback is "do nothing on Aliyun", aim-2 rollback is "extract failed → retry from Hermes-side tar.gz", aim-3 rollback is "Hermes crontab restore", etc.
2. **The aim-2 storage migration window is the single biggest atomic risk.** PROJECT §6 Risk row 3 (LightRAG data corruption) + Q2a 3 hard constraints all hinge on a ≥30 min Hermes-pause window during which tar+scp+verify happens. Wrapping that window in a dedicated phase makes the operator-side coordination explicit (Hermes operator prompt drives the pause; agent-side prompts coordinate scp + verify). Folding the storage move into aim-3 cutover would couple two distinct rollback scopes (storage corruption vs cutover roll-forward) and make failure attribution harder.
3. **The 7-day stability window (aim-5) is non-overlapping with code work.** Like ir-3 in the v3.5 milestone, aim-5 is observation-only — systemd timer fires daily for 7 consecutive days, reconcile runs daily, daily sync runs daily, kb-api regression check runs daily. A separate phase makes the gating boundary explicit: aim-5 must pass before milestone close; if observation flags issues, aim-5 stays open while a fix lands as a follow-up commit, and the 7-day window restarts.

**Counter-rationale considered (single-phase "do everything during a 1-day cutover window"):** rejected because (a) Aliyun ECS upgrade gate (Q6, ~24h after charter) is independent of code-deploy work — separating aim-0 lets the 24h wait happen without blocking aim-1 plan + smoke prep, (b) aim-4 daily-sync work is consumer-side (Hermes cron + Databricks git pull) and architecturally separate from aim-3's producer-side cutover.

**Phase count: 6** — below 6 forces aim-2 (storage) to merge into aim-3 (cutover) (couples rollback scopes), or aim-4 (sync) to merge into aim-5 (stability) (sync development blocks observation start, lengthening calendar wall-clock); above 6 creates artificial splits between e.g. systemd-unit creation and crontab-clear (which are tightly coupled within the cutover window).

---

## Phases

- [ ] **Phase aim-0: Readiness verification on upgraded Aliyun ECS** — Verify 8 vCPU / 16 GB RAM upgrade complete; measure DeepSeek + SiliconFlow + Vertex RTT vs Hermes baseline; LightRAG ainsert peak-memory dry-run < 8 GB; 1-2 article smoke ingest E2E to scratch storage (no production contamination).
- [ ] **Phase aim-1: Code + env deploy** — git clone repo to Aliyun; Python 3.11+ venv at `/opt/omnigraph-vault/venv/`; provider keys at `/etc/omnigraph/.env` (mode 600); `local_e2e.sh` smoke modes `layer1 5` + `wechat <url>` pass on Aliyun. Hermes still serves prod cron in parallel during this phase.
- [ ] **Phase aim-2: LightRAG storage full migration** — Hermes ingest crons paused ≥30min; tar.gz of `~/.hermes/omonigraph-vault/lightrag_storage/` + sha256; scp to Aliyun + re-hash verify; entity·relation·chunk·kv_keys count ±0% byte-identical between Hermes-source and Aliyun-extracted; Hermes-side storage frozen read-only for 30-day retention.
- [ ] **Phase aim-3: Cutover** — 11 Hermes crons replaced by 11 Aliyun systemd `.service` + `.timer` pairs; `kol_scan.db` write authority handed off (path `data/kol_scan.db`, repo-root, NOT under `~/.hermes/`); Hermes crontab cleared (`crontab -l | grep -E "ingest|kol_scan|rss" | wc -l == 0`); journald log presence verified on 3 sampled units; Q1a 1-day data loss recorded.
- [ ] **Phase aim-4: Daily sync Aliyun → Hermes + Databricks** — `scripts/sync-from-aliyun.sh` written (rsync over SSH; articles + DB + images + wiki); Hermes-side `daily-pull-from-aliyun` cron @02:00 ADT (Hermes net cron count: 11 → 1); Databricks pulls wiki + DB via `git pull` on existing checkout; retry policy ≤ 3 attempts exp backoff (60s/300s/1800s) + 48h marker file alert.
- [ ] **Phase aim-5: 7-day stability** — systemd ingest timers fire 7 consecutive days zero-fail; reconcile daily ghost_success rate < 1%; daily sync 7d zero-fail; kb-api no behavioral regression (no `/api/synthesize`); Vertex AI quota linear extrapolation ≤ Hermes baseline + 20%.

---

## Phase Details

### Phase aim-0: Readiness verification on upgraded Aliyun ECS

**Goal:** Verify Aliyun ECS upgrade to 8 vCPU / 16 GB RAM is complete and the host can carry the ingest workload before any code is deployed. All measurements written to `.planning/phases/aim-0-*/READINESS.md` for downstream phase reference.

**Depends on:** Aliyun ECS spec upgrade complete (Q6 — user-driven, ETA ~24h after 2026-05-20 evening charter). Hermes still serves production cron during this phase; no time pressure.

**Requirements:** READY-01, READY-02, READY-03, READY-04 (4 REQs)

**Success Criteria** (what must be TRUE):

  1. `nproc` on Aliyun returns ≥ 8; `free -h` shows `Mem total ≥ 15 GiB`; `df -h /` shows ≥ 5 GB free under `/` (READY-01)
  2. DeepSeek + SiliconFlow + Vertex RTT measured (≥5 sequential `curl -w` samples per provider; median + p95 recorded); each provider median RTT ≤ 2× Hermes baseline (same-day baseline measurement) (READY-02)
  3. LightRAG ainsert peak RSS measured via `/usr/bin/time -v` or `psrecord` on a "heavy" representative article (≥10 images, ≥5000 chars body); peak RSS < 8 GB (50% of 16 GB total) (READY-03)
  4. 1-2 article smoke ingest E2E reaches `status='ok'` in `ingestions` table; entities + relations land in **scratch** path `/tmp/aliyun-readiness/lightrag_storage/`, NOT the production storage location (no contamination of the storage that aim-2 will overwrite) (READY-04)

**Plans:** TBD
**T-shirt:** S (1-2 days for measurement + dry-run; bottleneck is the 24h Aliyun upgrade wait, not engineering effort)
**Notes:**

- Hermes baseline RTT measurement (for READY-02) must happen the SAME DAY as the Aliyun measurement to control for transient provider-side latency variation.
- READY-04 smoke uses scratch storage path explicitly to prevent the 1.6 GB Hermes-side storage on Aliyun (which doesn't exist yet — aim-2 hasn't run) from being seeded with READY-04 articles. If READY-04 contaminates production path, aim-2's tar+scp+extract overwrites it — silent data loss is unlikely but the scratch-path discipline closes the gap.
- Articles for READY-04 should come from existing Hermes candidate pool (`articles WHERE layer1_verdict='candidate' AND layer2_verdict='ok'`) — re-using verified candidates avoids Layer 1/2 false-negative noise during readiness measurement.

---

### Phase aim-1: Code + env deploy

**Goal:** Lay down code + Python venv + LLM provider credentials on Aliyun ECS, validated by `local_e2e.sh` smoke modes. End-state: Aliyun has executable code that *could* run the pipeline, but does not (no cron, no systemd timer yet — Hermes still authoritative).

**Depends on:** Phase aim-0 (host must be confirmed at 8C/16G + provider RTT verified before code deploy).

**Requirements:** DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-04 (4 REQs)

**Success Criteria** (what must be TRUE):

  1. Code deployed at `/opt/omnigraph-vault/` (or operator-chosen path; recorded in DEPLOY-NOTES.md); `git status` clean; HEAD commit hash recorded (DEPLOY-01)
  2. Python venv at `/opt/omnigraph-vault/venv/` with Python 3.11+; `pip install -r requirements.txt` succeeds zero errors; `python -c "import lightrag, google.genai, deepseek; print('OK')"` prints OK (DEPLOY-02)
  3. `/etc/omnigraph/.env` exists with mode 600, owned by ingest user; required keys present: `DEEPSEEK_API_KEY`, `SILICONFLOW_API_KEY`, `OMNIGRAPH_VERTEX_SA_JSON_PATH`, `GEMINI_API_KEY`, `APIFY_TOKEN`, `APIFY_TOKEN_BACKUP`; no literal secret committed to repo or any planning doc (DEPLOY-03)
  4. `scripts/local_e2e.sh layer1 5` AND `scripts/local_e2e.sh wechat <url>` both reach completion with no errors in `.scratch/local-e2e-*-<ts>.log`; smoke ingests land in **scratch** storage (production path uncontaminated, same as READY-04 discipline) (DEPLOY-04)

**Plans:** TBD
**T-shirt:** S (1-2 days; mostly ops work — git clone, pip install, env file edit, smoke runs)
**Notes:**

- Hermes pre-cutover constraint (PROJECT §5 In Scope #6) honored: Aliyun smoke ingests stay in scratch storage; production path stays empty until aim-2 ships the 1.6 GB tar.gz over.
- DeepSeek key handling per Phase 5 cross-coupling: `DEEPSEEK_API_KEY=dummy` is acceptable as the import-time defense if a real key is not yet placed; full key required for DEPLOY-04 smoke modes that exercise DeepSeek.
- Operator must place provider credentials via side-channel (NOT in any agent prompt — `feedback_no_literal_secrets_in_prompts.md`).

---

### Phase aim-2: LightRAG storage full migration

**Goal:** Move the 1.6 GB LightRAG storage from Hermes to Aliyun in one cutover-style transfer with strong byte-level integrity checks. End-state: Aliyun production path holds an exact byte-identical copy of Hermes's pre-aim-2 storage; Hermes original is read-only for 30 days as cold backup.

**Depends on:** Phase aim-1 (Aliyun must have executable code + provider env in place; the byte-identical extracted storage must land where aim-3's systemd units will read it).

**Requirements:** STORAGE-01, STORAGE-02, STORAGE-03, STORAGE-04, STORAGE-05 (5 REQs)

**Success Criteria** (what must be TRUE):

  1. Hermes ingest crons paused for the entire tar+scp+verify window ≥ 30 min; pause verified via `pgrep -f batch_ingest_from_spider` (must be empty) (STORAGE-01)
  2. Tar archive on Hermes ≥ 1 GB sanity floor; sha256 file written; both files retained ≥ 30 days post-cutover as cold backup (STORAGE-02)
  3. Tar transferred via `scp` (not rsync `--delete`); Aliyun-side re-computed sha256 matches Hermes-side hash byte-identical; **hard fail** on mismatch — abort, do NOT extract, retry transfer (STORAGE-03)
  4. Entity / relation / chunk / kv_keys count ±0% byte-identical between Hermes-source and Aliyun-extracted storage (queried via small read-only Python script `scripts/lightrag_count.py` or inline equivalent); fail → abort cutover, Hermes resumes, retry from STORAGE-02 (STORAGE-04)
  5. Extracted storage **moved** (not copied) into Aliyun production path `<OMNIGRAPH_BASE_DIR>/lightrag_storage/`; Hermes-side original `~/.hermes/omonigraph-vault/lightrag_storage/` set read-only at FS level (`chmod -R a-w`); Hermes 30-day retention deadline written into STATE-Aliyun-Ingest-Migration-v1.md as calendar reminder (STORAGE-05)

**Plans:** TBD
**T-shirt:** M (1 working day for the actual migration; ≥30min Hermes pause window + ~10-30min scp depending on network + verify is fast)
**Notes:**

- This is the single highest-risk phase of the milestone (LightRAG corruption = KG completely lost). Q2a 3 hard constraints exist specifically to defend against silent corruption: pause ≥30min, sha256 round-trip, count ±0%.
- Hermes-side resume protocol: if STORAGE-04 fails (count mismatch), Hermes operator MUST resume the paused crons before retrying STORAGE-02. Do NOT chain retries while Hermes is still paused — Hermes operational liveness > migration speed.
- The "extracted to holding directory first, NOT directly into production path" pattern (STORAGE-03) means STORAGE-05 is a `mv` operation on Aliyun that runs ONLY after STORAGE-04 verify passes. This is the rollback breakpoint: if anything between STORAGE-03 and STORAGE-04 goes wrong, the holding directory can be `rm -rf`'d and production path stays clean.
- 30-day retention deadline for Hermes-side storage tracked in STATE.md, NOT auto-cleaned. Cleanup is OUT of scope per PROJECT §5 Out of Scope.

---

### Phase aim-3: Cutover

**Goal:** Swing ingest authority from Hermes cron to Aliyun systemd timer in one operation. End-state: Aliyun is the sole ingest writer; Hermes crontab has zero ingest entries; journald has log entries for the first natural fire of every Aliyun timer.

**Depends on:** Phase aim-2 (storage must be on Aliyun before any Aliyun timer fires; otherwise the first ingest writes to an empty graph and corrupts the migration audit trail).

**Requirements:** CUTOVER-01, CUTOVER-02, CUTOVER-03, CUTOVER-04, CUTOVER-05 (5 REQs)

**Success Criteria** (what must be TRUE):

  1. 11 Hermes ingest crons converted to 11 Aliyun systemd `.service` + `.timer` pairs under `/etc/systemd/system/omnigraph-*.{service,timer}`; ExecStart points to Aliyun-deployed binaries; OnCalendar reproduces original Hermes cron schedules (ADT); all units enabled (CUTOVER-01)
  2. `kol_scan.db` write authority handed off to Aliyun; DB lives at `<repo>/data/kol_scan.db` (NOT under `~/.hermes/omonigraph-vault/` — per `project_kol_scan_db_path.md` memory); 24h post-cutover, Aliyun-side DB shows new rows (`SELECT MAX(layer2_at) FROM articles` advances past cutover timestamp) (CUTOVER-02)
  3. Hermes crontab cleared of all 11 ingest entries; §7 SC #2 invariant `crontab -l | grep -E "ingest|kol_scan|rss" | wc -l == 0` verified; output captured in `.planning/phases/aim-3-*/CUTOVER-EVIDENCE.md` (CUTOVER-03)
  4. All Aliyun systemd units log to journald; 3 of 11 units sampled — each `journalctl -u <unit> --since "1 hour ago"` returns non-empty stdout after first natural fire (CUTOVER-04)
  5. Q1a 1-day data loss accepted and recorded; cutover window timestamps + count of "missed-window" articles (estimated from 24h scan rate) recorded in CUTOVER-EVIDENCE.md; no mitigation, no backfill (CUTOVER-05)

**Plans:** TBD
**T-shirt:** M (2-3 days; systemd unit-creation is mechanical but 11 units × OnCalendar parity verification is detailed work; cutover window itself is 1-day wall-clock for first natural fire of each timer)
**Notes:**

- 11 ingest-related cron jobs to retire on Hermes side: 3 ingest-loop crons (daily-ingest 09:00 / afternoon-ingest 14:00 / evening-ingest 21:00 ADT) + 8 supporting jobs (`每日KOL扫描`, `KOL扫描前健康检查`, `rss-fetch`, `daily-digest`, `vertex-probe-monthly`, etc. — see STATE-v3.5-Ingest-Refactor.md § Hermes Operational State).
- Hermes operator prompt drives `crontab -e` edit (CUTOVER-03) — NOT agent-side SSH. Agent-side captures `crontab -l` output post-edit for evidence.
- CUTOVER-02 path discipline: `data/kol_scan.db` repo-root path is non-obvious (CLAUDE.md BASE_DIR convention suggests `~/.hermes/omonigraph-vault/kol_scan.db`, but the production path is repo-root per memory `project_kol_scan_db_path.md`). Any prompt or script touching the DB must reference the correct path.
- CUTOVER-04 sampling: 3 of 11 is sufficient (binomial confidence — if 3 random sampled units all have journald entries, probability of any unit silently failing journald is < 5%). All 11 verified would be exhaustive but operator-time-prohibitive.
- CUTOVER-05 records the data-loss decision but does NOT mitigate it. Q1a is an explicit acceptance, not a regression to be patched.

---

### Phase aim-4: Daily sync Aliyun → Hermes + Databricks

**Goal:** Install consumer-side daily pulls from Aliyun on Hermes and Databricks. End-state: Aliyun is unaware of downstream consumers (pull mode); Hermes net cron count is 11 → 1 (one new daily-pull cron, replacing the 11 ingest crons retired at aim-3); Databricks pulls wiki + DB via existing `git pull` workflow.

**Depends on:** Phase aim-3 (Aliyun must be the authoritative producer before any consumer pulls — pulling from a non-authoritative Aliyun would propagate stale data).

**Requirements:** SYNC-01, SYNC-02, SYNC-03, SYNC-04 (4 REQs)

**Success Criteria** (what must be TRUE):

  1. `scripts/sync-from-aliyun.sh` written and committed; modes: pulls articles JSON / `data/kol_scan.db` / `images/` / `kb/wiki/` from Aliyun via rsync over SSH; idempotent (re-run on same day produces identical local state); exit 0 on success, non-zero on any rsync failure (SYNC-01)
  2. Hermes-side `daily-pull-from-aliyun` cron installed; schedule 02:00 ADT (off-peak, 5h after Aliyun's 21:00-ADT-equivalent evening-ingest finishes); output lands at `~/.hermes/omonigraph-vault/` (read-only refresh — overwrites Hermes's retired storage with Aliyun's daily snapshot); Hermes net cron count: 11 → 1 (SYNC-02)
  3. Databricks consumer pulls wiki + DB via `git pull` on existing repo checkout (no full LightRAG ingest data needed — Databricks serves bilingual SSG + DB-only kb-api); 24h after first SYNC-02 fire, Databricks `git log -1 kb/wiki/` shows commit ≥ aim-4 deploy timestamp (SYNC-03)
  4. SYNC-01 retry policy: ≤ 3 retries with exp backoff (60s / 300s / 1800s); retry attempts logged to journald (`journalctl -u omnigraph-daily-pull.service`); failure beyond 3 retries triggers marker file `/tmp/aliyun-sync-failed-<date>` AND ERROR line to journald; marker older than 48h = §6 Risk row 8 alert criterion met, operator action required; no automated escalation beyond marker + log (SYNC-04)

**Plans:** TBD
**T-shirt:** S (1-2 days; rsync script + Hermes cron install + Databricks git workflow already established)
**Notes:**

- Wiki write-back from Aliyun is OUT of scope per Q4c — manual `git commit` from Aliyun during aim-4..aim-5 is acceptable; auto-hook deferred to LLM-Wiki-Integration-P2 milestone. SYNC-03's Databricks `git log -1 kb/wiki/` check assumes manual commits land on `main`.
- Daily sync v1 = full pull (no incremental optimization). PROJECT §8 derivative `Aliyun-Sync-v2` handles rsync `--partial`, parallel workers, selective sync flags — NOT in this milestone.
- SYNC-02 schedule choice (02:00 ADT) defends against Aliyun-side ingest timing: evening-ingest is 21:00 ADT; by 02:00 ADT the daily ingest has 5h to finish; pulling at 02:00 captures the freshest snapshot.
- Databricks (SYNC-03) does NOT pull `images/` or `lightrag_storage/` — only wiki + DB. Databricks' kb-api is read-only SSG + DB; full ingest data is unnecessary on that consumer.

---

### Phase aim-5: 7-day stability

**Goal:** Observation-only window. End-state: 7 consecutive wall-clock days where Aliyun systemd ingest timers fire zero-fail, daily reconcile ghost rate < 1%, daily sync runs zero-fail, kb-api shows no behavioral regression, Vertex AI quota stays within projected envelope. Milestone closes only after aim-5 passes.

**Depends on:** Phase aim-4 (full producer + consumer wiring must be live; observation of either side alone is incomplete).

**Requirements:** STAB-01, STAB-02, STAB-03, STAB-04, STAB-05 (5 REQs)

**Success Criteria** (what must be TRUE):

  1. 3 Aliyun systemd ingest timers (daily-ingest 09:00 / afternoon-ingest 14:00 / evening-ingest 21:00 ADT, the equivalents from CUTOVER-01) fire 7 consecutive days zero unit-level failures; verified via `systemctl status` + `journalctl -u omnigraph-*.service --since "7 days ago" | grep -E "Failed|exit-code"` returning empty (STAB-01) → §7 SC #1
  2. Reconcile job (bidirectional ghost-success scope per `feedback_contract_shape_change_full_audit.md` lineage) runs daily 7-day window; ghost_success rate (`ghost / total ingestions`) < 1% rolling; failure case: any single day with rate ≥ 1% triggers operator review; if root cause is migration-related, aim-5 restarts (STAB-02) → §7 SC #4
  3. Daily sync (SYNC-02 cron + Databricks `git pull`) succeeds 7 consecutive days zero failures (no 3-retry-exhausted events, no 48h marker triggers from SYNC-04); failure-day tolerance is 0 — single failed day restarts the window (STAB-03) → §7 SC #8
  4. kb-api on Aliyun no behavioral regression: `curl /api/articles | jq '. | length'` matches pre-migration count (or grows monotonically); `curl /api/article/<known-hash>` returns 200 with same body shape; `curl /api/search?mode=fts&q=<known>` returns expected hit; Decision 4 honored (no `/api/synthesize` introduced) (STAB-04) → §7 SC #6
  5. Vertex AI quota in 7-day window: `7-day Aliyun spend × ~4.3 ≤ Hermes-side prior monthly Vertex spend`; measured via GCP "Quotas & System Limits" dashboard; failure case: > 20% over linear projection triggers operator review (PROJECT §6 Risk row 6 cost-up alarm) (STAB-05) → §7 SC #5

**Plans:** TBD
**T-shirt:** S (3 working days for setup + audit; 7 days wall-clock observation is the bottleneck, not engineering effort)
**Notes:**

- aim-5 has no code work — it is observation + operator-side audit. Phase plan is a checklist + an OBSERVATION.md scaffold that operator updates daily.
- If any criterion fails on day N, aim-5 does NOT close — remains open while a fix lands as a follow-up commit (treated as a regression on aim-1..aim-4). The 7-day window restarts from the day the fix lands.
- Milestone close (Aliyun-Ingest-Migration-v1 → DONE) is gated on aim-5 PASS. Until then, milestone status remains `in_progress`.
- Failure-day tolerance is 0 across STAB-01 / STAB-03 (a single unit-level failure or sync failure restarts the window). STAB-02 / STAB-05 use threshold-based pass criteria (rate < 1%, quota ≤ baseline +20%).

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
| ----- | -------------- | ------ | --------- |
| aim-0: Readiness on upgraded Aliyun ECS | — | NOT STARTED — gated on Aliyun upgrade | — |
| aim-1: Code + env deploy | — | blocked by aim-0 | — |
| aim-2: LightRAG storage migration | — | blocked by aim-1 | — |
| aim-3: Cutover | — | blocked by aim-2 | — |
| aim-4: Daily sync | — | blocked by aim-3 | — |
| aim-5: 7-day stability | — | blocked by aim-4 | — |

---

## Coverage validation

**27/27 v1 requirements mapped, no orphans, no duplicates.**

| Phase | Count | REQs |
|-------|-------|------|
| aim-0 | 4 | READY-01, READY-02, READY-03, READY-04 |
| aim-1 | 4 | DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-04 |
| aim-2 | 5 | STORAGE-01, STORAGE-02, STORAGE-03, STORAGE-04, STORAGE-05 |
| aim-3 | 5 | CUTOVER-01, CUTOVER-02, CUTOVER-03, CUTOVER-04, CUTOVER-05 |
| aim-4 | 4 | SYNC-01, SYNC-02, SYNC-03, SYNC-04 |
| aim-5 | 5 | STAB-01, STAB-02, STAB-03, STAB-04, STAB-05 |
| **Total** | **27** | |

By category breakdown (1:1 phase-to-prefix mapping per REQUIREMENTS.md design):

- READY (4): aim-0 has all 4 ✓
- DEPLOY (4): aim-1 has all 4 ✓
- STORAGE (5): aim-2 has all 5 ✓
- CUTOVER (5): aim-3 has all 5 ✓
- SYNC (4): aim-4 has all 4 ✓
- STAB (5): aim-5 has all 5 ✓

PROJECT §7 Success Criteria coverage (8/8 mapped, 0 orphan SC items):

| §7 SC | Phase delivering | REQ |
|-------|------------------|-----|
| #1 systemd 7d zero-fail | aim-5 | STAB-01 |
| #2 `crontab` ingest count == 0 | aim-3 | CUTOVER-03 |
| #3 LightRAG entity·relation count ±0% | aim-2 | STORAGE-04 |
| #4 reconcile ghost < 1% | aim-5 | STAB-02 |
| #5 Vertex quota in budget | aim-5 | STAB-05 |
| #6 kb-api no regression | aim-5 | STAB-04 |
| #7 journald log presence | aim-3 | CUTOVER-04 |
| #8 daily sync 7d zero-fail | aim-5 | STAB-03 |

---

## T-shirt effort estimates

| Phase | T-shirt | Reasoning |
|-------|---------|-----------|
| aim-0 | **S** (1-2 days) | 4 REQs, mostly measurement + dry-run on already-upgraded host. Bottleneck is the 24h Aliyun upgrade wait, not engineering effort. |
| aim-1 | **S** (1-2 days) | 4 REQs, mostly ops work — git clone, pip install, env file edit, smoke runs. No new code. |
| aim-2 | **M** (1 working day for the actual migration) | 5 REQs but tightly serialized: pause Hermes → tar+sha256 → scp → re-hash verify → count verify → move to prod path. Engineering effort modest; **risk is high** (LightRAG corruption = KG lost), so operator coordination dominates. |
| aim-3 | **M** (2-3 days) | 5 REQs; 11 systemd unit-pair authorings + Hermes operator-side crontab clear + journald sampling. First natural fire of each timer needs 1-day wall-clock before CUTOVER-04 can verify. |
| aim-4 | **S** (1-2 days) | 4 REQs; rsync script + Hermes cron install + Databricks git workflow already established. Daily-sync v1 = full pull, no incremental optimization. |
| aim-5 | **S** (3 days setup + 7 days wall-clock) | 5 REQs but no code work — observation + operator-side audit only. 7-day calendar window is the bottleneck. |

**Milestone total: ~6-9 working days, ~3-4 weeks wall-clock** (driven by the 24h Aliyun upgrade gate at start + 7-day aim-5 window at end). Likely longer with operator-side coordination on Hermes pause + Aliyun ops + Databricks git pull verification.

---

## Dependencies

- aim-0 depends on: Aliyun ECS spec upgrade complete (Q6 — user-driven, ETA ~24h after 2026-05-20).
- aim-1 depends on: aim-0 (host must be confirmed at 8C/16G + provider RTT verified before code deploy).
- aim-2 depends on: aim-1 (Aliyun must have executable code + provider env in place; the byte-identical extracted storage must land where aim-3's systemd units will read it).
- aim-3 depends on: aim-2 (storage must be on Aliyun before any Aliyun timer fires).
- aim-4 depends on: aim-3 (Aliyun must be the authoritative producer before any consumer pulls).
- aim-5 depends on: aim-4 (full producer + consumer wiring must be live; observation of either side alone is incomplete).

No phase-internal parallelism is recommended; phases are strictly sequential.

---

## Cross-phase touches

| REQ / discipline | First delivered | Touch-points |
|------------------|----------------|--------------|
| **Scratch-storage discipline** (Aliyun smoke ingests use `/tmp/aliyun-readiness/...`, NOT production path) | aim-0 (READY-04) | aim-1 (DEPLOY-04) honors same discipline until aim-2 ships real storage |
| **Hermes pause coordination** (operator-side `crontab -e` flip + `pgrep -f` verify) | aim-2 (STORAGE-01) | aim-3 (CUTOVER-03) — final Hermes crontab clear |
| **Aliyun systemd unit family** (11 `.service` + `.timer` pairs) | aim-3 (CUTOVER-01) | aim-4 (SYNC-02) adds 1 daily-pull unit on Hermes (different host); aim-5 (STAB-01) observes Aliyun units 7d |
| **`<OMNIGRAPH_BASE_DIR>` config consistency** | aim-1 (DEPLOY-03 env file) | aim-2 (STORAGE-05) extracts to `<OMNIGRAPH_BASE_DIR>/lightrag_storage/`; aim-3 systemd ExecStart references same |
| **Hermes 30-day retention deadline** | aim-2 (STORAGE-05) | Tracked in STATE.md; calendar reminder; cleanup OUT of scope per PROJECT §5 |

---

## Open notes

- **Aliyun upgrade gate uncertainty:** at charter time (2026-05-20 evening) Aliyun ECS upgrade to 8C/16G is user-scheduled with ETA ~24h. aim-0 plan-phase MUST first verify upgrade completion via `nproc` + `free -h` before READY-01..04 can be measured. If upgrade slips beyond 2026-05-22, aim-0 plan-phase remains parked; Hermes serves prod cron in parallel during the wait, no time pressure.
- **aim-2 is the single highest-risk phase** — LightRAG corruption = KG completely lost. The Q2a 3 hard constraints (pause ≥30min / sha256 / count ±0%) are non-negotiable. If any of STORAGE-01..04 fails, abort cutover, Hermes resumes, retry from the appropriate breakpoint (do NOT chain retries while Hermes is paused). The 30-day Hermes-side read-only retention (STORAGE-05) provides an additional cold-backup lifeline.
- **kb-api scope discipline:** STAB-04 explicitly verifies "no `/api/synthesize` introduced". This cross-checks against PROJECT Decision 4 / Q5c — query API ownership stays with Agentic-RAG-v1 milestone, NOT this one. Any drift toward kb-api absorbing query semantics is a milestone-scope violation.
- **Daily sync v1 = full pull.** Performance optimization (rsync `--partial`, parallel workers, selective sync flags) deferred to PROJECT §8 derivative `Aliyun-Sync-v2`. Do NOT optimize during aim-4 — full pull is the simplest correct shape; optimize only after 7-day stability passes and real workload data is available.
- **Wiki write-back automation OUT of scope.** Q4c — manual `git commit` from Aliyun during aim-1..aim-5 is acceptable. SYNC-03's Databricks `git log -1 kb/wiki/` check assumes manual commits land on `main`. Auto-hook deferred to LLM-Wiki-Integration-P2 milestone (which also handles Aliyun ssh deploy key + git config aliyun-bot identity per PROJECT §8 derivatives).
- **Parallel-track coordination with v3.4 (Phase 19-22), v3.5 (`ir-N`), Agentic-RAG-v1 (`ar-N`):** aim-N touches Aliyun ECS + Hermes operator state + `scripts/sync-from-aliyun.sh` + planning artifacts under `.planning/phases/aim-*`. Code-side touch points (`scripts/sync-from-aliyun.sh` is new) are non-overlapping with other milestones. KG-side query API contract (Agentic-RAG-v1) is unchanged — ingest substrate moves, query semantics frozen.
- **Parallel-milestone gates manual-run:** per `feedback_parallel_track_gates_manual_run.md`, `gsd-tools.cjs init` parses only the main `.planning/{PROJECT,REQUIREMENTS,ROADMAP,STATE}.md` files. Parallel-track suffix files (this milestone's `*-Aliyun-Ingest-Migration-v1.md` set) are NOT recognized by tooling — every downstream gate must be hand-driven by the orchestrator.
- **No research stage:** Per locked design (`PROJECT-Aliyun-Ingest-Migration-v1.md` Q1-Q6 all closed) and the existing operator knowledge base (`aliyun_vitaclaw_ssh.md`, `hermes_ssh.md`, `project_kol_scan_db_path.md` memories), `/gsd:plan-phase aim-N` should jump from spec → planning → execute. No `gsd-project-researcher` agents.

---
*Roadmap created: 2026-05-20 (evening, after Q1-Q6 closed).*
*Last updated: 2026-05-20 — initial creation; all 6 phases NOT STARTED, gated on Aliyun ECS 8C/16G upgrade (Q6 — user-driven, ETA ~24h).*
