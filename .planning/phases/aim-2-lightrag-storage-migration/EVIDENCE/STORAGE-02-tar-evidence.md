# STORAGE-02 — Hermes tar.gz + sha256 Evidence

**Phase:** aim-2-lightrag-storage-migration
**Task:** STORAGE-02 (wave-2 — tar archive + integrity hash on Hermes)
**Operator channel:** Hermes (a04ef71c94f654249)
**Captured:** 2026-05-23 (UTC)

---

## Operator Output (Verbatim)

```
=== ALL STEPS COMPLETE ===

Step 1 (pre-tar):    disk 883GB free ✅ | source exists ✅ | crontab 0 ✅
Step 2 (tar):        1.9G → 1.3G gz (72s) | sha256 verified OK ✅
Step 3 (re-check):   pause still active ✅

Summary:
  ts:              20260523T141829Z
  archive:         /tmp/lightrag_storage_aim2_20260523T141829Z.tar.gz
  size:            1,339,799,750 bytes (~1.3 GB)
  sha256:          6408674f143fe84d4f3763b9fef900c0a46c53671eb0acf9a56226b873afdbe8
  retain_until:    2026-06-22
  pause:           STILL ACTIVE (awaiting STORAGE-04 or abort)
```

---

## Validation

| Check | Threshold | Actual | Result |
|---|---|---|---|
| Archive size sanity floor | ≥ 1,073,741,824 (1 GiB) | 1,339,799,750 | ✅ |
| sha256 self-verify | OK | OK | ✅ |
| gzip compression ratio | Sane (~70%) | 1.9 GB → 1.3 GB (~68%) | ✅ |
| tar wallclock | < 5 min | 72 s | ✅ |
| Pre-tar disk free | > 5 GB headroom | 883 GB | ✅ |
| Pre-tar source path | Must exist | exists | ✅ |
| Pre-tar crontab ingest lines | 0 | 0 | ✅ |
| Pause re-check (post-tar) | STILL ACTIVE | STILL ACTIVE | ✅ |

All checks green.

---

## Q2a Clock (Pause Budget)

| Marker | Timestamp (UTC) |
|---|---|
| Pause-confirmed (STORAGE-01) | 2026-05-23T14:09:41Z |
| Tar archive ts | 2026-05-23T14:18:29Z |
| Elapsed pause → tar-done | ~9 minutes |
| Q2a deadline (30-min cap) | 2026-05-23T14:39:41Z |
| Remaining budget for waves 3+4 | ~21 minutes |

Wave-3 (scp Hermes → Aliyun) + wave-4 (extract + count verify) must complete inside this 21-min window before pause resume / abort decision at wave-5.

---

## Hand-off → Wave 3

**Wave-3 source (on Hermes):**
- Path: `/tmp/lightrag_storage_aim2_20260523T141829Z.tar.gz`
- Size: 1,339,799,750 bytes
- Retain-until: 2026-06-22

**Expected sha256 round-trip target:**
- `6408674f143fe84d4f3763b9fef900c0a46c53671eb0acf9a56226b873afdbe8`
- Aliyun-side recompute MUST match byte-for-byte; mismatch → abort wave-3, do not extract.

**Aliyun destination scope:**
- Extraction holding dir: `/tmp/aim2-extract/` (NOT production path)
- Production swap is wave-5 atomic mv, not wave-4
- Wave-4 is read-only verification (count + sha256 round-trip)

**STATE.md / pause status:**
- Pause STILL ACTIVE per Step 3 re-check
- STATE.md edit deferred to wave-5 (post-validation atomic swap)
- Forward-only edits only

---

## Ready for Wave-3

`ready_for_wave_3 = true`
