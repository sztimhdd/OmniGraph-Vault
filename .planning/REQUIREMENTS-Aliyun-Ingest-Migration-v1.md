# Requirements: Aliyun-Ingest-Migration-v1

**Defined:** 2026-05-20 (evening, after Q1-Q6 decisions closed)
**Core value:** Migrate authoritative ingest pipeline from Hermes (家用 PC, WSL2) to Aliyun ECS (101.133.154.49, upgrading to 8 vCPU / 16 GB RAM 2026-05-21+); retire Hermes to read-only / dev sandbox; install daily Aliyun → Hermes + Databricks sync (RPO ≤ 24h) replacing the cold-backup milestone.

**Source of truth:**

- `.planning/PROJECT-Aliyun-Ingest-Migration-v1.md` (5 Decisions + Q1-Q6 closed + §5 In Scope + §6 Risk + §7 Success Criteria + §9 Phase table)
- `.planning/STATE-Aliyun-Ingest-Migration-v1.md` (milestone state — phase plan + cross-milestone contract)
- `.planning/PROJECT.md` § "Active Parallel Milestone: Aliyun-Ingest-Migration-v1" (high-level pointer + decision summary)

REQ-IDs use category prefixes mapped 1:1 to phases:

| Phase | Prefix | REQs | Goal |
|-------|--------|------|------|
| aim-0 Readiness | `READY-` | 4 | Aliyun ECS upgraded + provider RTT + LightRAG mem peak + smoke |
| aim-1 Code + env | `DEPLOY-` | 4 | git clone + venv + provider keys + local_e2e smoke |
| aim-2 Storage migration | `STORAGE-` | 5 | Hermes pause + tar.gz + scp + sha256 + count ±0% verify |
| aim-3 Cutover | `CUTOVER-` | 5 | systemd timer + db handoff + Hermes crontab clear + journald |
| aim-4 Daily sync | `SYNC-` | 4 | sync-from-aliyun.sh consumer-side cron + retry + alert |
| aim-5 7-day stability | `STAB-` | 5 | systemd 7d zero-fail + reconcile + sync 7d + no kb-api regression |

**Total: 27 REQs across 6 phases, 0 orphans expected.**

---

## v1 Requirements

### Readiness — aim-0 (READY-N)

Maps PROJECT §5 In Scope #1 + §6 Risk row 1-2 + Q6 (Aliyun upgrade). Phase aim-0 is gated on Aliyun ECS 8 vCPU / 16 GB RAM upgrade complete (~2026-05-21+); these REQs verify the upgraded host can carry the ingest workload before any code is deployed.

- [ ] **READY-01**: Aliyun ECS confirmed at 8 vCPU / 16 GB RAM. Verified via `nproc` (≥8) and `free -h` (`Mem total ≥ 15 GiB`). Disk free under `/` ≥ 5 GB (`df -h /`). Pre-condition: 24h post-charter Aliyun upgrade complete (Q6).
- [ ] **READY-02**: LLM provider RTT measured from Aliyun ECS to each of: DeepSeek (`api.deepseek.com`), SiliconFlow (`api.siliconflow.cn`), Vertex AI (`*-aiplatform.googleapis.com`). Each provider: ≥ 5 sequential `curl -w '%{time_total}'` samples, median + p95 recorded in `.planning/phases/aim-0-*/READINESS.md`. Pass criterion: each provider median RTT ≤ 2× the Hermes baseline median for the same provider (Hermes baseline measured the same day on the same provider).
- [ ] **READY-03**: LightRAG ainsert peak memory dry-run on Aliyun ECS — single representative ingest article (≥10 images, ≥5000 chars body, equivalent to a "heavy" KOL article) ingested via `local_e2e.sh wechat <url>` or equivalent driver. Peak RSS measured via `/usr/bin/time -v` or `psrecord`. Pass criterion: peak RSS < 8 GB (50% of 16 GB total). Documented in `.planning/phases/aim-0-*/READINESS.md`.
- [ ] **READY-04**: 1-2 article smoke ingest E2E on Aliyun ECS reaches `status='ok'` in `ingestions` table. Articles selected from existing Hermes candidate pool (`articles WHERE layer1_verdict='candidate' AND layer2_verdict='ok'`). Smoke uses Aliyun-deployed code at READY-01 commit; entities + relations land in a **scratch** LightRAG storage path (`/tmp/aliyun-readiness/lightrag_storage/`), NOT the production storage location (no contamination of the storage that aim-2 will overwrite).

### Code + env deploy — aim-1 (DEPLOY-N)

Maps PROJECT §5 In Scope #2-#3. Phase aim-1 lays down code + Python venv + LLM provider credentials on Aliyun ECS, validated by `local_e2e.sh` smoke modes.

- [ ] **DEPLOY-01**: Code deployed to Aliyun at a known commit. Path: `/opt/omnigraph-vault/` (or operator-chosen equivalent — recorded in `.planning/phases/aim-1-*/DEPLOY-NOTES.md`). Repo cloned from `git@github.com:sztimhdd/OmniGraph-Vault.git` (or operator's fork). Working tree clean (`git status` empty). HEAD commit hash recorded in deploy notes.
- [ ] **DEPLOY-02**: Python venv created at `/opt/omnigraph-vault/venv/` with Python 3.11+. `pip install -r requirements.txt` succeeds with zero errors. `python -c "import lightrag, google.genai, deepseek; print('OK')"` (or equivalent import smoke) prints OK.
- [ ] **DEPLOY-03**: Provider credentials placed on Aliyun ECS at `/etc/omnigraph/.env` (or operator-chosen path; not committed to git). Required keys: `DEEPSEEK_API_KEY` (real or `dummy` per Phase 5 cross-coupling), `SILICONFLOW_API_KEY`, `OMNIGRAPH_VERTEX_SA_JSON_PATH` (Vertex SA JSON path), `GEMINI_API_KEY` (legacy fallback), `APIFY_TOKEN` + `APIFY_TOKEN_BACKUP`. File mode `600`, owned by ingest user. No literal secrets committed to repo or any planning doc.
- [ ] **DEPLOY-04**: `scripts/local_e2e.sh` smoke modes pass on Aliyun: `layer1 5` (Layer 1 batch on 5 candidates) AND `wechat <url>` (single-URL E2E on a non-corp-restricted target — Aliyun is in cn-east-mainland, all 3 LLM providers reachable). Both runs reach completion with no errors in `.scratch/local-e2e-*-<ts>.log`. The Hermes pre-cutover constraint (PROJECT §5 #6 — Hermes still serves prod cron during this phase) is honored: Aliyun smoke ingests land in **scratch** storage (same as READY-04), not the production path.

### Storage migration — aim-2 (STORAGE-N)

Maps PROJECT §3 Decision 2 (no transitional sync) + Q2a (full tar.gz) + Q2a's 3 hard constraints + §6 Risk row 3 (LightRAG data corruption mitigation). Phase aim-2 moves the 1.6 GB LightRAG storage from Hermes to Aliyun in one cutover-style transfer.

- [ ] **STORAGE-01**: Hermes ingest crons paused for ≥ 30 min during the entire tar + scp + verify window. Pause method: `crontab -e` to comment out the 11 ingest-related entries, OR write a Hermes operator prompt that does the same atomically. Verify cron is actually paused via `pgrep -f batch_ingest_from_spider` (must be empty). Resume only after STORAGE-04 verify passes — if verify fails, Hermes resumes and aim-2 retries.
- [ ] **STORAGE-02**: Tar archive created on Hermes: `tar -czf /tmp/lightrag_storage_aim2_<ts>.tar.gz -C ~/.hermes/omonigraph-vault lightrag_storage/`. Size ≥ 1 GB (sanity floor — current storage is ~1.6 GB at 2026-05-20). sha256 computed: `sha256sum /tmp/lightrag_storage_aim2_<ts>.tar.gz > /tmp/lightrag_storage_aim2_<ts>.tar.gz.sha256`. Both files retained for ≥ 30 days post-cutover (PROJECT §6 Risk row 3 — Hermes side as cold backup).
- [ ] **STORAGE-03**: Tar archive transferred to Aliyun via `scp` (no `rsync --delete`, no resume). On Aliyun: re-compute `sha256sum` and compare to Hermes-side hash. **Hard fail**: if hashes mismatch, abort, do NOT extract, retry transfer. Extracted to a holding directory first (`/tmp/aim2-extract/lightrag_storage/`), NOT directly into the production path.
- [ ] **STORAGE-04**: Entity / relation / chunk count ±0% verify between Hermes-source and Aliyun-extracted storage. Method: query each LightRAG storage's KV-store / vector-DB / graph-DB row counts via small read-only Python script (`scripts/lightrag_count.py` or inline equivalent). Required outputs side-by-side: `entities`, `relations`, `chunks`, `kv_keys`. Pass criterion: **all four counts identical to the byte** (not "approximately equal"). Fail → abort cutover, Hermes resumes, retry from STORAGE-02.
- [ ] **STORAGE-05**: After STORAGE-04 passes, the extracted storage is **moved** (not copied) into the Aliyun production path (`<OMNIGRAPH_BASE_DIR>/lightrag_storage/`, where `OMNIGRAPH_BASE_DIR` matches the Aliyun env config from DEPLOY-03). Hermes-side original `~/.hermes/omonigraph-vault/lightrag_storage/` stays in place AND is set read-only at the filesystem level (`chmod -R a-w`) for ≥ 30-day retention (Q2a constraint #3). Hermes retention deadline written into STATE-Aliyun-Ingest-Migration-v1.md as a calendar reminder.

### Cutover — aim-3 (CUTOVER-N)

Maps PROJECT §5 In Scope #4 + #6 + #7 + Q1a (simple cutover, accept 1-day data loss) + §7 SC #2 (`crontab -l | grep -E "ingest|kol_scan|rss" | wc -l == 0`). Phase aim-3 swings the actual ingest authority from Hermes cron to Aliyun systemd timer.

- [ ] **CUTOVER-01**: 11 Hermes ingest crons converted to Aliyun systemd `.service` + `.timer` pairs under `/etc/systemd/system/omnigraph-*.{service,timer}`. Each pair: ExecStart points to the Aliyun-deployed `batch_ingest_from_spider.py` / `batch_scan_kol.py` / `rss_ingest.py` / reconcile / kol_scan health-check / rss-fetch / daily-digest / vertex-probe equivalents (the 3 ingest-loop crons + 8 supporting jobs enumerated in STATE-Aliyun-Ingest-Migration-v1.md § Hermes Operational State). Each timer's `OnCalendar=` reproduces the original Hermes cron schedule (ADT). All units enabled (`systemctl enable --now omnigraph-*.timer`).
- [ ] **CUTOVER-02**: `kol_scan.db` write authority handed off to Aliyun. The DB lives at `<repo>/data/kol_scan.db` (per `project_kol_scan_db_path.md` memory — NOT under `~/.hermes/omonigraph-vault/`). Method: final Hermes-side sync of `data/kol_scan.db` to Aliyun (post-STORAGE-05, after Hermes ingest paused), then Aliyun systemd timers from CUTOVER-01 take over writes. Hermes-side DB chmod read-only post-handoff. Verify: 24h after cutover, Aliyun-side DB has new rows (`SELECT MAX(layer2_at) FROM articles` advances past the cutover timestamp).
- [ ] **CUTOVER-03**: Hermes crontab cleared of all 11 ingest-related entries. Verify via the §7 SC #2 invariant: `crontab -l | grep -E "ingest|kol_scan|rss" | wc -l` returns `0`. Hermes operator prompt drives this edit; SSH + `crontab -e` is operator-side, not agent-side. Output of `crontab -l` post-edit captured into `.planning/phases/aim-3-*/CUTOVER-EVIDENCE.md`.
- [ ] **CUTOVER-04**: All Aliyun systemd units log to journald. `journalctl -u omnigraph-daily-ingest.service --since "1 hour ago"` returns non-empty stdout after the timer's first natural fire. §7 SC #7 verified by sampling 3 of 11 units — each must have at least one entry per scheduled fire window.
- [ ] **CUTOVER-05**: Q1a 1-day data loss accepted and recorded. Cutover window defined: from "Hermes last ingest cron completes" to "Aliyun first ingest timer fires". Articles whose Layer-1 candidate window falls entirely inside this gap are NOT re-evaluated (acceptance per Q1a). The cutover window timestamps + the count of "missed-window" articles (estimated from 24h of typical scan rate) recorded in `CUTOVER-EVIDENCE.md`. No mitigation, no backfill — this is an explicit decision.

### Daily sync Aliyun → Hermes + Databricks — aim-4 (SYNC-N)

Maps PROJECT §3 Decision 5 (subsumes Aliyun-Hermes-Coldbackup-v1) + §5 In Scope #8 + §6 Risk row 8 (sync failure). Phase aim-4 installs consumer-side cron pulls from Aliyun on Hermes and Databricks; Aliyun is unaware of downstream consumers (pull mode).

- [ ] **SYNC-01**: `scripts/sync-from-aliyun.sh` written and committed to repo. Modes: pulls `articles` JSON / `data/kol_scan.db` / `images/` / `kb/wiki/` from Aliyun via `rsync` over SSH. Single full-pull run (no incremental optimization — that's Aliyun-Sync-v2 derivative per PROJECT §8). Idempotent: re-running on the same day produces identical local state. Exit code 0 on success, non-zero on any rsync failure.
- [ ] **SYNC-02**: Hermes-side `daily-pull-from-aliyun` cron installed (1 entry, replacing 0 of the 11 retired ingest entries — net Hermes cron count: 11 → 1). Schedule: 1 fire per day, 02:00 ADT (off-peak, 5h after Aliyun's 21:00-ADT-equivalent evening-ingest finishes). Output lands at `~/.hermes/omonigraph-vault/` (read-only refresh — Hermes will overwrite its retired storage with Aliyun's daily snapshot).
- [ ] **SYNC-03**: Databricks consumer pulls wiki + DB increments via `git pull` on its existing repo checkout (Databricks does NOT need full LightRAG ingest data — it serves bilingual SSG + DB-only kb-api). Wiki commits land on `main` from Aliyun's auto-commit (deferred to LLM-Wiki-Integration-P2 milestone — during aim-4..7-day-stability, manual `git commit` from Aliyun is acceptable per Q4c). Verify: 24h after first SYNC-02 fire, Databricks `git log -1 kb/wiki/` shows a commit ≥ aim-4 deploy timestamp.
- [ ] **SYNC-04**: SYNC-01 retry policy: ≤ 3 retries with exponential backoff (60s / 300s / 1800s). All retry attempts logged to journald (`journalctl -u omnigraph-daily-pull.service`). Failure beyond 3 retries triggers an alert: write a marker file `/tmp/aliyun-sync-failed-<date>` AND log `ERROR` line to journald. If the marker file is older than 48h (i.e., 2 consecutive sync failures), §6 Risk row 8 alert criterion is met — operator action required. No automated escalation beyond marker + log.

### 7-day stability — aim-5 (STAB-N)

Maps PROJECT §7 Success Criteria #1, #4, #5, #6, #8. Phase aim-5 is a 7-day wall-clock observation window; the milestone is not "done" until this window passes clean.

- [ ] **STAB-01**: Aliyun systemd ingest timers (the 3 ingest-loop equivalents from CUTOVER-01: daily-ingest 09:00 / afternoon-ingest 14:00 / evening-ingest 21:00 ADT) fire 7 consecutive days with **zero** unit-level failures. Verified via `systemctl status omnigraph-*.timer` showing `Last triggered` advancing daily AND `journalctl -u omnigraph-*.service --since "7 days ago" | grep -E "Failed|exit-code"` returning empty. §7 SC #1.
- [ ] **STAB-02**: Reconcile job (the bidirectional ghost-success scope from `feedback_contract_shape_change_full_audit.md` lineage) runs daily for the same 7-day window. ghost_success rate (`ghost / total ingestions`) < 1% across the 7-day rolling window. §7 SC #4. Failure case: any single day with ghost_success ≥ 1% triggers operator review; if root cause is migration-related (vs. pre-existing v1.0.x noise floor), aim-5 restarts.
- [ ] **STAB-03**: Daily sync (SYNC-02 cron on Hermes + Databricks `git pull`) succeeds 7 consecutive days with **zero** failures (no 3-retry-exhausted events, no 48h marker triggers from SYNC-04). §7 SC #8. Failure-day count tolerance is 0 — a single failed day restarts the 7-day window.
- [ ] **STAB-04**: kb-api on Aliyun has no behavioral regression vs. pre-migration baseline. Verify: `curl -s http://<aliyun>/api/articles | jq '. | length'` matches pre-migration count (or grows monotonically as Aliyun ingest adds articles); `curl -s http://<aliyun>/api/article/<known-hash>` returns 200 with same body shape; `curl -s http://<aliyun>/api/search?mode=fts&q=<known>` returns expected hit. §7 SC #6 + Decision 4 (kb-api scope unchanged — no `/api/synthesize` introduced).
- [ ] **STAB-05**: Vertex AI quota usage in the 7-day window does not exceed the pre-migration Hermes-side monthly baseline (extrapolated linearly: 7-day Aliyun spend × ~4.3 ≤ Hermes-side prior monthly Vertex spend). Measured via GCP project's "Quotas & System Limits" dashboard. §7 SC #5. Failure case: quota usage exceeds the linear projection by > 20% triggers operator review (PROJECT §6 Risk row 6 cost-up alarm).

---

## Out-of-scope (deferred to derivative milestones)

The following are explicitly NOT in this milestone (PROJECT §5 Out of Scope + §8 derivative candidates):

- Wiki write-back automation — handled by LLM-Wiki-Integration-P2 milestone (Q4c). Manual `git commit` during aim-1..aim-5 is acceptable.
- kb-api `/api/synthesize` endpoint / direct LightRAG query API — handled by Agentic-RAG-v1 milestone (Q5c, Decision 4).
- Sync incremental optimization (rsync `--partial`, parallel workers, selective sync flags) — handled by Aliyun-Sync-v2 derivative milestone (PROJECT §8).
- Hermes `~/.hermes/omonigraph-vault/lightrag_storage/` 30-day-retention deadline cleanup — out of scope; tracked as a calendar reminder in STATE.md.
- Aliyun-side ssh deploy key + git config aliyun-bot identity (needed for P2 wiki write-back) — handled by LLM-Wiki-Integration-P2 milestone.

## Coverage map (REQ → SC)

| Phase | REQs | Success Criteria mapped |
|-------|------|------|
| aim-0 | READY-01..04 | (gates §6 Risk rows 1-2 — internal pass, not a §7 SC) |
| aim-1 | DEPLOY-01..04 | (precondition for §7 SC #1, #6) |
| aim-2 | STORAGE-01..05 | §7 SC #3 (entity_count + relation_count = ±0%) |
| aim-3 | CUTOVER-01..05 | §7 SC #2 (`crontab` ingest count == 0), §7 SC #7 (journald) |
| aim-4 | SYNC-01..04 | (precondition for §7 SC #8) |
| aim-5 | STAB-01..05 | §7 SC #1, #4, #5, #6, #8 |

All 8 §7 SC items mapped. 0 orphan REQs.
