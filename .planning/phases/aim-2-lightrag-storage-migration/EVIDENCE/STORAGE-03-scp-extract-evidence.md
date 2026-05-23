# STORAGE-03 — scp Hermes→Aliyun + sha256 round-trip + extract Evidence

**Phase:** aim-2-lightrag-storage-migration
**Task:** STORAGE-03 (wave-3 — scp transfer, round-trip integrity, extract to holding dir)
**Operator channel:** Mixed
- Hermes-side scp push: agent direct via SSH (one-time, user-authorized exception — Hermes-agent policy was blocking outbound transfers)
- Aliyun-side rehash + extract: agent direct via `ssh aliyun-vitaclaw` (aim-2 agent IS operator on Aliyun side per phase contract)
**Captured:** 2026-05-23 (UTC)

---

## STORAGE-03A — Hermes-side scp Push

### Pre-scp pause re-verify (Step 1)

| Check | Threshold | Actual | Result |
|---|---|---|---|
| crontab ingest-line count | 0 | 0 | ✅ |
| pgrep batch_ingest_from_spider | none | exit 1 (no match) | ✅ |
| pgrep batch_scan_kol | none | exit 1 (no match) | ✅ |
| pgrep rss_ingest | none | exit 1 (no match) | ✅ |

Pause held active going into scp.

### Source self-check (Step 2)

| Check | Expected | Actual | Result |
|---|---|---|---|
| archive present | `/tmp/lightrag_storage_aim2_20260523T141829Z.tar.gz` | exists | ✅ |
| size_local | 1,339,799,750 | 1,339,799,750 | ✅ |
| companion .sha256 present | yes | yes | ✅ |
| sha256sum -c local | OK | OK | ✅ |

### scp wallclocks (Step 3)

| Transfer | Start (UTC) | End (UTC) | Elapsed | Exit |
|---|---|---|---|---|
| tar.gz → root@101.133.154.49:/tmp/ | 22:56:06Z | 22:59:09Z | 3 m 02.939 s | 0 |
| .sha256 companion | 22:59:09Z | 22:59:15Z | 5.715 s | 0 |

Key: `~/.ssh/vitaclaw_aliyun_ed25519` (Hermes-side). Destination: `root@101.133.154.49:/tmp/` (direct IP — `aliyun-vitaclaw` ssh-config alias not present on Hermes side).

### Post-scp pause re-verify (Step 4)

| Check | Threshold | Actual | Result |
|---|---|---|---|
| crontab ingest-line count | 0 | 0 | ✅ |
| 3× pgrep ingest workers | all exit 1 | all exit 1 | ✅ |

Pause STILL ACTIVE post-scp.

---

## STORAGE-03B — Aliyun-side Rehash + Extract

### Archive landed (Step A)

| Check | Expected | Actual | Result |
|---|---|---|---|
| archive present at /tmp/ | yes | yes | ✅ |
| size_remote | 1,339,799,750 | 1,339,799,750 | ✅ (size_match=YES) |

### Round-trip sha256 (Step B)

| Field | Value |
|---|---|
| expected | `6408674f143fe84d4f3763b9fef900c0a46c53671eb0acf9a56226b873afdbe8` |
| aliyun_recompute | `6408674f143fe84d4f3763b9fef900c0a46c53671eb0acf9a56226b873afdbe8` |
| round_trip_match | ✅ YES (byte-identical) |
| rehash wallclock | ~14 s |

### Companion self-check (Step C)

`sha256sum -c /tmp/lightrag_storage_aim2_20260523T141829Z.tar.gz.sha256` → **OK** ✅

### Production-path conflict pre-check (Step D)

| Check | Result |
|---|---|
| `/root/OmniGraph-Vault/lightrag_storage/` exists? | NO ✅ (clean — wave-5 will create via mv) |

### Holding dir prep + disk headroom (Step E)

| Check | Value |
|---|---|
| `mkdir -p /tmp/aim2-extract` | created clean |
| df -h /tmp (mount /dev/vda3) | 99 G total / 30 G used / 65 G free / 32 % |

### Extract (Step F)

| Field | Value |
|---|---|
| command | `tar -xzf /tmp/lightrag_storage_aim2_20260523T141829Z.tar.gz -C /tmp/aim2-extract/` |
| start (UTC) | 23:00:10Z |
| end (UTC) | 23:00:40Z |
| wallclock | 29.1 s |
| exit | 0 ✅ |

### Extracted tree (Step G)

| Field | Value |
|---|---|
| holding root | `/tmp/aim2-extract/lightrag_storage/` |
| owner | 1000:1000 |
| total size | 1.9 GB |
| total file count | 84 |
| notable contents | `graph_chunk_entity_relation.graphml` (32 MB), `kv_store_doc_status.json` (430 KB), `.backup_20260503_rss_clean/` subdir, multiple `kv_store_doc_status.json.bak-*` historical backups |

---

## Validation Summary

| Gate | Result |
|---|---|
| pause held pre-scp | ✅ |
| Hermes source self-check | ✅ |
| scp tar exit | 0 ✅ |
| scp companion exit | 0 ✅ |
| pause held post-scp | ✅ |
| size match (Hermes vs Aliyun) | ✅ 1,339,799,750 == 1,339,799,750 |
| sha256 round-trip | ✅ byte-identical |
| companion .sha256 self-check on Aliyun | ✅ OK |
| production-path clean | ✅ NO pre-existing storage |
| disk headroom for holding dir | ✅ 65 G free |
| tar extract exit | 0 ✅ |
| extracted file count plausible | ✅ 84 files / 1.9 GB |

All gates green. Holding dir is the rollback breakpoint — production swap is deferred to wave-5 (post wave-4 count verify).

---

## Q2a Clock Update

| Marker | Timestamp (UTC) |
|---|---|
| Pause-confirmed (STORAGE-01) | 2026-05-23T14:09:41Z |
| Tar archive ts (STORAGE-02) | 2026-05-23T14:18:29Z |
| scp tar start | 2026-05-23T22:56:06Z |
| scp tar end | 2026-05-23T22:59:09Z |
| Aliyun extract end | 2026-05-23T23:00:40Z |
| Q2a 30-min "minimum" floor (STORAGE-01 + 30 min) | 2026-05-23T14:39:41Z |

**Q2a clarification (recorded earlier):** the 30-min figure is the MINIMUM pause duration, not a deadline ceiling. Longer pause = more compliant. Pause has now been active ≈ 8h 51m as of extract-done — well above the 30-min floor.

---

## Hand-off → Wave 4

**Wave-4 inputs:**
- Hermes source: `~/.hermes/omonigraph-vault/lightrag_storage/` (untouched, read-only by Hermes pause)
- Aliyun extracted holding dir: `/tmp/aim2-extract/lightrag_storage/`
- Both sides will be queried for: entity count, relation count, chunk count, kv_keys count
- Pass criterion: all four counts byte-identical

**Holding-dir invariant:**
- `/tmp/aim2-extract/lightrag_storage/` is NOT production
- Wave-5 atomic `mv` to `/root/OmniGraph-Vault/lightrag_storage/` only after wave-4 verify passes
- If wave-4 fails: abort + Hermes operator cron-resume + retain holding dir for forensics (do NOT auto-cleanup)

**Hermes pause status:** STILL ACTIVE — must remain so through wave-4 (count verify is read-only on Hermes side, but production cron must not write while reference counts are being computed).

---

## Ready for Wave-4

`ready_for_wave_4 = true`
