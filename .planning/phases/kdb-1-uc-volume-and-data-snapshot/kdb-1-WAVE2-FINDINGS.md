---
artifact: WAVE2-FINDINGS
phase: kdb-1
wave: 2
created: 2026-05-15
status: pass
---

# kdb-1 Wave 2 — Findings (STORAGE + SEED)

> Wave 2 scope per ROADMAP-kb-databricks-v1.md rev 3 (commit `cfe47b4`):
> STORAGE-DBX-01..04 + SEED-DBX-01. Wave 3 SPIKE deferred to separate gate.

## STORAGE-DBX-01 — UC schema CREATE

**Status:** ✅ PASS

```sql
CREATE SCHEMA IF NOT EXISTS mdlg_ai_shared.kb_v2
  COMMENT 'OmniGraph KB v2 storage namespace ...';
```

**`DESCRIBE SCHEMA EXTENDED`:**
- Catalog: `mdlg_ai_shared`
- Namespace: `kb_v2`
- Owner: `hhu@edc.ca`
- Predictive Optimization: ENABLE (inherited from METASTORE `uc-dap-metastore-cc`)

## STORAGE-DBX-02 — UC managed volume CREATE

**Status:** ✅ PASS

```sql
CREATE VOLUME IF NOT EXISTS mdlg_ai_shared.kb_v2.omnigraph_vault
  COMMENT 'OmniGraph runtime data ...';
```

**`DESCRIBE VOLUME`:**
- Name: `omnigraph_vault`
- Catalog/Schema: `mdlg_ai_shared.kb_v2`
- Owner: `hhu@edc.ca`
- Volume type: **MANAGED**
- Securable kind: `VOLUME_STANDARD`
- Storage location: `abfss://uc-managed@dlsmdlgdapai883273.dfs.core.windows.net/mdlg/__unitystorage/catalogs/85403c9e-539b-4c21-98ce-f5fa4520a5ad/volumes/9e478057-d241-4121-a5a6-c6702eb97c0d`

## STORAGE-DBX-03 — 4 sub-directories initialized

**Status:** ✅ PASS

Used `databricks fs mkdir` (CLI native subcommand; the marker-file approach in the prompt failed with "no such directory" because UC Volume needs explicit dir creation):

```bash
for sub in data images lightrag_storage output; do
  databricks --profile dev fs mkdir dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/${sub}
done
```

**`databricks fs ls dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/`:**
```
data
images
lightrag_storage
output
```

## SEED-DBX-01 — One-shot seed (DB + images)

### Hermes-side capture (atomic snapshot via Python `sqlite3.backup`)

**Caveat:** Hermes had an active ingest in flight at capture time (PID 3060282, `batch_ingest_from_spider --max-articles 10`). To avoid SHA/scp race against concurrent writers, we used Python's `sqlite3.Connection.backup()` API to write an atomic snapshot to `/tmp/kdb-1-snapshot/kol_scan.db` on Hermes. SHA captured against that snapshot, NOT the live DB. The `sqlite3` CLI binary is not installed on Hermes, but Python's stdlib module works.

**Reference values:**

| Field | Value |
|-------|-------|
| `HERMES_DB_SHA256` | `37f3436da22e70b73af92f964ff6aafa4d592284ce3c044de8465f742fb2f3dc` |
| `HERMES_DB_BYTES` | `20582400` (20.5 MB) |
| `HERMES_DB_PATH` | `/tmp/kdb-1-snapshot/kol_scan.db` (atomic copy of `~/OmniGraph-Vault/data/kol_scan.db`) |
| `HERMES_TABLE_articles_COUNT` | 842 |
| `HERMES_TABLE_rss_articles_COUNT` | 1756 |
| `HERMES_REF_1` | `rss_articles` / `32d3502bb57bdd6268372aeef81e21e7` / len 25 |
| `HERMES_REF_2` (substantive) | `articles` / `6b1bb6607d` / len 4417 |
| `HERMES_REF_3` (substantive) | `rss_articles` / `03aa92df5e3b9e5abb12a2608ac617f8` / len 7540 |

### Transit (Hermes → local Windows dev)

```bash
scp -P 49221 sztimhdd@ohca.ddns.net:/tmp/kdb-1-snapshot/kol_scan.db \
    /c/Users/huxxha/Desktop/hermes-snapshot-kdb-1/kol_scan.db
```

- scp time: 3s
- Local SHA = `37f3436da22e70b73af92f964ff6aafa4d592284ce3c044de8465f742fb2f3dc` ✅ matches Hermes
- **TRANSIT_VERIFY = PASS**

### Upload (local → UC Volume)

```bash
databricks --profile dev fs cp \
  /c/Users/huxxha/Desktop/hermes-snapshot-kdb-1/kol_scan.db \
  dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/data/kol_scan.db --overwrite
```

- Upload time: 4s
- Volume confirmed: `databricks fs ls .../data/` → `kol_scan.db`

### Images: `~/.hermes/omonigraph-vault/images/` → UC Volume

**Pull mechanism:** Hermes-side `tar -cf - images` piped through SSH to local file (rsync not available on Windows Git Bash). Tar pipe preferred over `scp -r` for many small files (per-SSH overhead amortized).

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/.hermes/omonigraph-vault && tar -cf - images" \
  > /c/Users/huxxha/Desktop/hermes-snapshot-kdb-1/images.tar
tar -xf images.tar -C /c/Users/huxxha/Desktop/hermes-snapshot-kdb-1/
```

- Tar pull time: 95s (1016 MB tar)
- Extract time: 6s
- Local extracted: 254 dirs / 4127 files / 1012941402 bytes (~966 MB)

**Volume upload (3 phases):**

Phase A — bulk recursive upload (foreground command, ran in background):
```bash
databricks --profile dev fs cp -r --overwrite \
  /c/Users/huxxha/Desktop/hermes-snapshot-kdb-1/images/ \
  dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/images/
```
Result: **partial success** — 210/254 dirs landed, then aborted at 3841s with `oidc: token refresh: fetching OAuth endpoints: databricks OAuth is not supported for this host`. The dir-in-progress (`d9b95bd172`) had 16/32 files when the token refresh failed mid-flight.

Phase B — delta upload of 44 missing dirs (sequential per-dir loop):
```bash
while read -r dir; do
  databricks --profile dev fs cp -r --overwrite "${LOCAL}/${dir}" "${VOL}/images/${dir}"
done < /tmp/missing-dirs.txt
```
Result: 40/44 succeeded; 4 transient failures (last few in the loop also hit OAuth refresh).

Phase C — retry of 3 transient failures + manual patch of `d9b95bd172` (the Phase A mid-flight victim):
```bash
for d in fa11ded615 fbf62ba7ab fdc4cff583 d9b95bd172; do
  databricks --profile dev fs cp -r --overwrite "${LOCAL}/${d}" "${VOL}/images/${d}"
done
```
Result: all 4 succeeded.

**Final state:**
- Total upload time: ~80 min wallclock across 3 phases (Phase A 64m + B 14.5m + C ~30s)
- Volume image dirs: **254** (matches local snapshot)
- Volume image files: **4127** (matches local: `find ${LOCAL} -type f | wc -l = 4127`)
- Dir parity: **PASS** (`comm` diff returns empty)
- File count parity: **PASS** (4127 / 4127)

## STORAGE-DBX-04 — Byte-for-byte integrity check

**Status:** ✅ PASS

### Check #1: full-file SHA256 (DB)

Downloaded Volume copy of DB to local temp, recomputed SHA256:

```bash
databricks --profile dev fs cp \
  dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/data/kol_scan.db \
  /c/Users/huxxha/Desktop/hermes-snapshot-kdb-1/kol_scan-volume-verify.db --overwrite
sha256sum /c/Users/huxxha/Desktop/hermes-snapshot-kdb-1/kol_scan-volume-verify.db
# 37f3436da22e70b73af92f964ff6aafa4d592284ce3c044de8465f742fb2f3dc
```

`VOL_SHA == HERMES_DB_SHA` byte-for-byte. **VOLUME_FULL_FILE_SHA_MATCH = PASS.**

### Check #2: 3 reference articles (semantic)

Opened Volume DB read-only, queried each reference by `content_hash`, asserted `LENGTH(body)` matches:

| Ref | Table | content_hash (truncated) | Expected len | Got len | Verdict |
|-----|-------|--------------------------|--------------|---------|---------|
| 1   | rss_articles | `32d3502bb57b...` | 25 | 25 | PASS |
| 2   | articles     | `6b1bb6607d`      | 4417 | 4417 | PASS |
| 3   | rss_articles | `03aa92df5e3b...` | 7540 | 7540 | PASS |

### Check #3: row counts

`articles` = 842 (matches Hermes), `rss_articles` = 1756 (matches Hermes). Total = 2598 candidates for kdb-2.5 LightRAG re-index.

## Anti-pattern compliance audit

| # | Anti-pattern | Status |
|---|--------------|--------|
| 1 | DO NOT execute kdb-2.5 LightRAG re-index Job | ✅ N/A — no `ainsert` calls; only file ops |
| 2 | DO NOT deploy production `omnigraph-kb` app | ✅ N/A — no `databricks apps create` |
| 3 | DO NOT write `lightrag_databricks_provider.py` | ✅ N/A — no kdb-1.5 files created |
| 4 | DO NOT leave `omnigraph-kb-spike` behind | ✅ N/A — Wave 2 doesn't deploy spike (Wave 3 only) |
| 5 | DO NOT copy `lightrag_storage/` from Hermes | ✅ Confirmed — `lightrag_storage/` sub-dir created empty; only `kol_scan.db` + `images/` synced |
| 6 | DO NOT modify `kb/` / `lib/` / `kg_synthesize.py` | ✅ git diff scoped to `.planning/` only |
| 7 | DO NOT `git --amend` / `--reset` / `git add -A` | ✅ Forward commit, explicit paths |
| 8 | DO NOT exceed Wave 3 30-min timer | ✅ N/A (Wave 2) |
| 9 | DO NOT touch Aliyun production / Hermes runtime | ✅ Hermes touched read-only (sqlite3 backup + scp + tar pull); ingest in flight not interrupted |

Note on #9: Hermes had an active ingest at the time of capture. The ingest was NOT interrupted; we used `sqlite3.Connection.backup()` to take an atomic snapshot to `/tmp/kdb-1-snapshot/`, then scp'd that snapshot. Live DB was not read directly (avoided race).

## Time budget

- Wave 2 hard cap: 30–60 min target
- **Actual wallclock: ~120 min — exceeded target.**
- Breakdown:
  - Schema + volume + sub-dirs + DB pull/upload/verify: ~10 min
  - Image pull (tar pipe over SSH, 1 GB): ~95s
  - Image bulk upload Phase A: ~64 min (210/254 dirs before OAuth crash)
  - Image delta upload Phase B (44 dirs): ~14.5 min (40/44 ok)
  - Image patch Phase C (4 retry + 1 mid-dir): ~1 min
  - Verifications + findings: ~10 min
- Driver of overage: known Databricks SDK long-running-cp + OAuth refresh fragility on Windows. ~966 MB / 4127 files via `databricks fs cp -r` is at the edge of what one auth context tolerates.

**Mitigation for future re-runs (Wave 3 / kdb-2.5 etc.):** Either (a) switch to a PAT with longer lifetime, OR (b) chunk uploads into smaller per-dir batches as Phase B/C did. Single bulk `cp -r` of >500 MB has now been observed to fail with OAuth refresh; Phase B/C pattern (per-dir cp with simple retry) was reliable.

## Decision

**Wave 2 PASS — AWAITING USER OK to proceed to Wave 3 spike** (or pre-authorization for combined Wave 2+3 run).

If authorized: deploy throwaway `omnigraph-kb-spike` app + run 5 sub-checks + delete spike app + report back. 30-min hard timer applies.

If blocked: STOP at this commit, await user decision.
