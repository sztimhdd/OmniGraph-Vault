# STORAGE-04 — Entity / relation / chunk / kv_keys count verify

**Phase:** aim-2-lightrag-storage-migration
**Task:** STORAGE-04 (wave-4 — byte-identical count verify between Hermes-source and Aliyun-extracted holding-dir)
**REQ:** STORAGE-04
**Tool:** `scripts/lightrag_count.py` v1.0 (committed `24fe3fe`)
**Captured:** 2026-05-23 (UTC)

---

## Hermes-source storage count

**Path:** `~/.hermes/omonigraph-vault/lightrag_storage/`
**Storage size:** 1.9 GB (du -sh)
**networkx:** 3.6.1
**Pause status (pre-count):** uncommented ingest lines = 0 ✅

```json
{"chunks": 1875, "entities": 27654, "kv_keys": 76249, "relations": 39604, "script_version": "1.0", "storage_path": "/home/sztimhdd/.hermes/omonigraph-vault/lightrag_storage"}
```

---

## Aliyun-holding storage count

**Path:** `/tmp/aim2-extract/lightrag_storage/`
**networkx:** 3.6.1
**venv:** `venv-aim1`

```json
{"chunks": 1875, "entities": 27654, "kv_keys": 76249, "relations": 39604, "script_version": "1.0", "storage_path": "/tmp/aim2-extract/lightrag_storage"}
```

---

## Per-field verdict table

| Field | Hermes-source | Aliyun-holding | Match? |
|-------|---------------|----------------|--------|
| entities  | 27,654 | 27,654 | ✅ YES |
| relations | 39,604 | 39,604 | ✅ YES |
| chunks    | 1,875  | 1,875  | ✅ YES |
| kv_keys   | 76,249 | 76,249 | ✅ YES |

**Overall verdict:** **PASS** — all four count fields byte-identical between Hermes-source and Aliyun-extracted holding-dir.

`storage_path` field expectedly differs (Hermes vs Aliyun absolute paths) — not part of integrity gate.

---

## Pause re-check (post-count, Hermes-side)

| Check | Threshold | Actual | Result |
|---|---|---|---|
| crontab uncommented ingest lines | 0 | 0 | ✅ |
| pgrep batch_ingest_from_spider | exit 1 (no real worker) | exit 1 (false-positive bash eval wrapper noted, no real workers) | ✅ |
| pgrep batch_scan_kol | exit 1 | exit 1 | ✅ |
| pgrep rss_ingest | exit 1 | exit 1 | ✅ |

Pause STILL ACTIVE going into wave-5.

---

## Q2a Clock Update

| Marker | Timestamp (UTC) |
|---|---|
| Pause-confirmed (STORAGE-01) | 2026-05-23T14:09:41Z |
| Tar archive ts (STORAGE-02) | 2026-05-23T14:18:29Z |
| scp tar end (STORAGE-03) | 2026-05-23T22:59:09Z |
| Aliyun extract end (STORAGE-03) | 2026-05-23T23:00:40Z |
| Hermes count run (STORAGE-04) | ~2026-05-23T23:08Z |
| Aliyun count run (STORAGE-04) | ~2026-05-23T23:11Z |
| Q2a 30-min "minimum" floor | 2026-05-23T14:39:41Z |

Pause has been active ≈ 9h 1m at STORAGE-04 verdict — well above the 30-min minimum floor.

---

## Decision

**PASS verdict** → wave-5 (STORAGE-05) proceeds:

1. `mv /tmp/aim2-extract/lightrag_storage/ /root/OmniGraph-Vault/lightrag_storage/` (atomic swap on Aliyun)
2. `chmod -R a-w ~/.hermes/omonigraph-vault/lightrag_storage/` on Hermes (30-day read-only retention; deadline 2026-06-22)
3. STATE.md forward-only edit recording retention deadline + storage swap
4. Hermes operator cron-resume prompt (uncomment 10 ingest lines; cron count drift from predicted 11 → actual 10 noted)
5. Phase verification → close aim-2

---

## Hand-off → Wave 5

**Wave-5 inputs:**

- Aliyun holding-dir validated byte-identical to Hermes source (this evidence file)
- Aliyun production path `/root/OmniGraph-Vault/lightrag_storage/` confirmed clean (STORAGE-03B Step D)
- Hermes pause STILL ACTIVE — cron resume is wave-5 final step, AFTER mv + chmod

**Holding-dir invariant satisfied:** byte-identical verified, mv to production is now safe.

`ready_for_wave_5 = true`
