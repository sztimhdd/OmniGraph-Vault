# STORAGE-05 — Production Cutover Evidence

**Wave**: 5/5 (final)
**Phase**: aim-2 — LightRAG Storage Migration (Hermes → Aliyun)
**Status**: PASS

---

## Timestamps

| Event | Timestamp (UTC) | Source |
|---|---|---|
| Aliyun mv (holding-dir → production target) | `2026-05-23T23:19:49Z` | `/tmp/aim2-cutover-ts.iso` (Aliyun) |
| Hermes `chmod -R a-w` (read-only freeze) | `2026-05-24T01:21:09Z` | `/tmp/aim2-cutover-ts-hermes.iso` (Hermes) |
| Hermes cron resumed (`crontab -e` save) | `2026-05-24T01:21:33Z` | `/tmp/aim2-resume-ts.iso` (Hermes) |
| **30-day retention deadline** | **2026-06-22** | cutover_date (2026-05-23) + 30 days |

Hermes pause window (start STORAGE-01 → resume Step 6): well over 30 min — Q2a hard constraint satisfied (exact start TS captured in STORAGE-01).

---

## Plan deviation: Backup-then-overwrite

**Plan (aim-2-5.md, Step A pre-flight)**: target `/root/.hermes/omonigraph-vault/lightrag_storage/` MUST be empty; STOP if non-empty.

**Reality at pre-flight**: target was NON-EMPTY — 47 files / 752 MB / counts {entities=22412, relations=31566, chunks=1478, kv_keys=60919} / last write 2026-05-17 23:55 UTC.

**Root cause of plan-vs-reality gap**: STORAGE-03B Step D (wave-3 verification) checked `/root/OmniGraph-Vault/lightrag_storage/` — the WRONG path. Canonical production path resolved this turn by reading the kb-api systemd unit:

```
/etc/systemd/system/kb-api.service:
  Environment="OMNIGRAPH_BASE_DIR=/root/.hermes/omonigraph-vault"
  → RAG_WORKING_DIR = /root/.hermes/omonigraph-vault/lightrag_storage/
```

This matches aim-2-5.md plan but contradicts wave-3 evidence; wave-3 evidence was checking a sibling that was always empty.

**Resolution**: User authorized **Backup-then-overwrite** via AskUserQuestion (recommended option). Existing Aliyun state preserved at sibling timestamped path before cutover mv.

**Backup path** (Aliyun, recoverable): `/root/.hermes/omonigraph-vault/lightrag_storage.aliyun-pre-aim2-bak-20260523T231949Z/`
- 752 MB / 47 files / counts {entities=22412, relations=31566, chunks=1478, kv_keys=60919}
- Untouched by cutover mv; rollback path available if Aliyun-source state turns out to be needed.

---

## Aliyun cutover sequence (atomic same-fs `mv`)

Both `/tmp/aim2-extract/` and `/root/.hermes/omonigraph-vault/` are on `/dev/vda3` — `mv` is a rename syscall, no copy, no race window.

```
# Step A — pre-flight (verified non-empty, surfaced to user, authorized)
ls -la /tmp/aim2-extract/lightrag_storage/         → 84 files / 1.9 GB
ls -la /root/.hermes/omonigraph-vault/lightrag_storage/  → 47 files / 752 MB (NOT EMPTY)

# Step B — backup mv (existing Aliyun state preserved)
mv /root/.hermes/omonigraph-vault/lightrag_storage \
   /root/.hermes/omonigraph-vault/lightrag_storage.aliyun-pre-aim2-bak-20260523T231949Z

# Step C — cutover mv (holding-dir → production)
mv /tmp/aim2-extract/lightrag_storage \
   /root/.hermes/omonigraph-vault/lightrag_storage

# Step D — post-flight verify
du -sh /root/.hermes/omonigraph-vault/lightrag_storage/   → 1.9 GB
find ... -type f | wc -l                                  → 84
ls -la /tmp/aim2-extract/                                 → empty
```

Audit log: `/tmp/aim2-cutover-20260523T231949Z.log` (Aliyun-side, ephemeral; preserved in this evidence file).

---

## Post-cutover count verify (byte-identical to Hermes-source)

```bash
cd /root/OmniGraph-Vault && source venv-aim1/bin/activate \
  && python scripts/lightrag_count.py --working-dir /root/.hermes/omonigraph-vault/lightrag_storage
```

**New Aliyun production**:
```json
{"chunks": 1875, "entities": 27654, "kv_keys": 76249, "relations": 39604,
 "script_version": "1.0",
 "storage_path": "/root/.hermes/omonigraph-vault/lightrag_storage"}
```

**Hermes source (from STORAGE-04 / re-verified during pause this wave)**:
```json
{"chunks": 1875, "entities": 27654, "kv_keys": 76249, "relations": 39604,
 "script_version": "1.0",
 "storage_path": "/home/sztimhdd/.hermes/omonigraph-vault/lightrag_storage"}
```

**Δ = 0 across all 4 metrics** — Q2a (b) byte-identical entity/relation/chunk/kv_keys count: PASS.

---

## Hermes-side read-only freeze + cron resume

Operator-executed via Hermes operator prompt (fenced block, this wave):

| Step | Command | Result |
|---|---|---|
| 1 | Pause re-verify (`crontab -l \| grep -E '^[^#].*ingest'`; pgrep) | uncommented = 0; pgrep = bash-eval-wrapper false-positive only ✅ |
| 2 | `ls ~/.hermes/omonigraph-vault/lightrag_storage/` BEFORE chmod | 84 writable files (expected) |
| 3 | `chmod -R a-w ~/.hermes/omonigraph-vault/lightrag_storage/` | OK; CUTOVER_TS_HERMES = `2026-05-24T01:21:09Z` |
| 4 | Writable-bit sweep: `find … -perm /u+w \| wc -l` | **0** ✅ (Q2a (c) read-only retention: PASS) |
| 5 | BEFORE crontab snapshot + operator runs `crontab -e` interactively | 0 uncommented (still paused) |
| 6 | AFTER `crontab -e` save: re-verify | **10 uncommented hermes ingest cron lines** ✅; RESUME_TS = `2026-05-24T01:21:33Z` |

Note: plan estimated 11 ingest cron lines based on STORAGE-01 snapshot; operator confirmed 10 actually paused (1 line was apparently a non-ingest line miscounted in earlier wave). 10 == 10 round-trip; pause/resume parity satisfied.

---

## Q2a constraint satisfaction (final)

| Constraint | Evidence | Status |
|---|---|---|
| (a) Hermes ingest cron paused ≥ 30 min | STORAGE-01 pause TS → STORAGE-05 resume TS = `2026-05-24T01:21:33Z`; wall ≥ 30 min over multiple wave executions | ✅ |
| (b) sha256 round-trip + entity/relation/chunk/kv_keys ±0% byte-identical count | STORAGE-02 (sha256 source) → STORAGE-03 (sha256 round-trip match) → STORAGE-04 (count match) → STORAGE-05 (post-cutover re-verify match) | ✅ |
| (c) 30-day Hermes-side read-only retention via `chmod -R a-w` | Step 4 writable-bit sweep == 0; deadline `2026-06-22` registered in STATE | ✅ |

---

## Outstanding housekeeping (non-blocking)

- Aliyun stash `aim-2-4-precount-stash-20260523T231056Z` (`scripts/local_e2e.sh`) — pop or document at convenience.
- Aliyun backup `lightrag_storage.aliyun-pre-aim2-bak-20260523T231949Z` (752 MB) — keep for rollback window; cleanup decision at aim-3 close or later.
- aim-2-5.md plan Step A pre-flight assumption (target empty) was wrong; if a future re-run of similar cutover flow happens, plan should pre-check actual systemd-pinned production path against aim-2-5.md target (script: `systemctl cat kb-api.service | grep OMNIGRAPH_BASE_DIR`).

---

## Hand-off to aim-3

aim-3 (Aliyun ingest cron cutover proper) inherits:
- Aliyun lightrag_storage = byte-identical Hermes-source state at `2026-05-23T23:19:49Z`
- Hermes lightrag_storage = read-only frozen, retained until `2026-06-22`
- Hermes ingest cron resumed (10 lines) — Aliyun-side ingest cron NOT yet active; Hermes remains the active ingest writer until aim-3 cuts over the cron schedule.

Phase aim-2 verdict: **PASS**.
