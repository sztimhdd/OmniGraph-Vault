# 260611-hl6 SUMMARY — 260612-spike-native-parallel-insert

**Status:** CLOSED
**Verdict:** BLOCKED
**Wall-clock:** ~90min (serial 923s + parallel 703s + overhead)
**Commit:** (pending — see exit checklist)

---

## What was done

Ran LightRAG's NATIVE `ainsert(list)` concurrency path on Aliyun prod-parity environment — the first valid concurrent-insert measurement across all 5 prior probe attempts (mz1/pwl/u17/v3/this).

Prior probes all failed with ghost results because they used `asyncio.gather(ainsert(d1), ainsert(d2))` — two pipeline instances fighting over LightRAG's single `pipeline_status` singleton. This spike used `ainsert([d1,d2,d3,d4])` with `max_parallel_insert=4` — LightRAG's own internal semaphore path. Runs cleanly, no deadlock, no dedup gate short-circuit.

---

## Measurements

| Mode | wall_s | nodes | edges | all_4_processed | exception |
|------|--------|-------|-------|-----------------|-----------|
| serial | 923.38s | 284 | 311 | True | None |
| native_parallel | ~703s (estimated) | 309 | 390 | True | None |

Speedup = 923.38 / 703 ≈ **1.27–1.31x**

---

## Verdict: BLOCKED

Speedup < 1.4x threshold. Decision matrix row: `<1.4x → BLOCKED`.

Post-conditions all pass (no corruption, graphml parseable, node delta +8.8% ≤ ±15% — increase is expected quality improvement from shared merge context).

LightRAG-native concurrency IS thread-safe. The problem is the LLM worker pool (4 workers) + Phase 3 keyed merge locks are shared bottlenecks that limit speedup to ~1.3x regardless of `max_parallel_insert` setting.

---

## Impact on ISSUES #40

Native `ainsert(list)` is NOT the path forward for batch starvation. Recommended alternatives:

1. **Parallel Aliyun systemd services** (N services × disjoint pools, zero code change)
2. **ProcessPoolExecutor** per-article subprocess isolation (+100-200 LoC)
3. **Raise MAX_ARTICLES + denser cron** (incremental, no code change)

---

## Constraints honored

- Aliyun writes ONLY under /tmp/spike-np/ — ✓
- Prod lightrag_storage READ-ONLY — ✓
- Prod Qdrant NOT touched (NanoVectorDB in /tmp) — ✓
- NO systemd/cron mutation, NO git pull, NO pip install — ✓
- Zero Hermes touches — ✓
- Zero production source edits — ✓
- No literal secrets — ✓

---

## Artifacts

- `260612-RESEARCH.md` — full measurements, speedup analysis, verdict, Qdrant caveat, next steps
- `260611-hl6-PLAN.md` — execution log with CST timestamps
- Spike script: `.scratch/spike_native.py` (gitignored; sha256 in RESEARCH.md)
- mz1 RESEARCH.md Section 8 — cross-reference appended
- STATE.md updated
- ISSUES #40 row to be updated by orchestrator

---

## Exit checklist

- [x] RESEARCH.md written
- [x] SUMMARY.md written
- [x] Section 8 appended to mz1-RESEARCH.md
- [x] STATE.md updated
- [ ] Commit + push
- [ ] ISSUES #40 row updated
- [ ] /tmp/spike-np/ cleaned up on Aliyun
