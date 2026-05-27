---
phase: 18-daily-ops-hygiene
plan: 01
subsystem: image-cap
tags: [wave1, ingest, image, cap, hyg-02]
status: complete
created: 2026-05-03
completed: 2026-05-03
---

# Plan 18-01 SUMMARY — N-image cap for 118-image edge case

**Status:** Complete
**Wave:** 1
**Requirements:** HYG-02
**Depends on:** —

---

## 1. What shipped

| Artifact | Change | Purpose |
|---|---|---|
| `ingest_wechat.py` | `+38 lines` (constant + helper), `+5 lines` (flow wiring + manifest tag) | Hard cap on kept images per article; env-overridable |
| `tests/unit/test_image_cap.py` | 105 lines, 8 tests | Under/at/over/env-override/order/logging/empty-dropped coverage |

Tests: **8/8 pass**. No regression in `tests/unit/test_image_pipeline.py` (22/22 still green).

---

## 2. Decision locked

**Option A (N-image cap).** Default `MAX_IMAGES_PER_ARTICLE = 60`.

Rationale (carried from 18-01-PLAN `<objective>`):
- Wave 0 kept-image distribution: median ~10–15, p95 ~40. 60 = ~2× p95 — generous headroom without opening the door to the long tail.
- 118-image article was the single outlier in a 67-article batch (1.5%). Losing images #61–118 for that one outlier is acceptable; the first 60 already carry the article's visual argument.
- Simple to reason about, trivial to unit-test, reversible via env var.

Options (b) timeout extension and (c) both were considered and rejected for this plan. If post-cap articles still hit Phase 9's 600s LLM timeout, reopen as 18-01b with (b).

---

## 3. Where the cap lives

```
download_images(unique_img_urls)        [existing]
    ↓
filter_small_images(url_to_path, min_dim=300)   [existing Phase 8]
    ↓
_apply_image_cap(url_to_path, MAX_IMAGES_PER_ARTICLE)   [NEW]
    ↓
manifest build — entries not in url_to_path but in dropped_by_cap
                 get filter_reason="over_cap"
    ↓
write_stage(ckpt_hash, "image_download", manifest)
```

Checkpoint semantic: the manifest records all `unique_img_urls` with accurate `filter_reason`. On resume, the manifest-reload branch already rebuilds `url_to_path` from entries with `filter_reason=None`, so capped-out URLs are correctly NOT re-downloaded (matches the desired idempotent behavior).

---

## 4. Acceptance criteria reconciliation

| Criterion | Status |
|---|---|
| `grep -q "MAX_IMAGES_PER_ARTICLE"` | ✅ 3 occurrences (constant + flow + function arg) |
| `grep -q "OMNIGRAPH_MAX_IMAGES_PER_ARTICLE"` | ✅ 1 occurrence (env read) |
| `grep -q "over_cap"` | ✅ 2 occurrences (flow + manifest tag) |
| `grep -q "_apply_image_cap"` | ✅ 2 occurrences (defn + call site) |
| 5+ pytest tests pass | ✅ 8/8 pass |
| test file ≥ 90 lines | ✅ 105 lines |
| No regression in existing image_pipeline tests | ✅ 22/22 green |

---

## 5. Known follow-ups (non-blocking)

- **Post-cap performance observation.** Wave 0 observed the 118-image hang in LightRAG entity-merge. A real-batch run after this ship will confirm whether the hang was actually bounded by image count or by something else (e.g., entity-merge cost per unique entity). If a 40-image article still hangs post-cap, the entity-merge path needs separate attention — escalates to v3.4 scope, not v3.3.
- **Static scanning of the 67-article Wave 0 sample.** To retroactively count how many articles would have been capped, scan the manifests in `~/.hermes/omonigraph-vault/checkpoints/*/03_image_download.json` on Hermes — operator exercise, not a code task.

---

## 6. Commits

1. `feat(18-00): vertex live-probe + monthly Hermes cron (HYG-01)` — previous plan
2. (this plan) — `feat(18-01): cap kept images per article at 60 (HYG-02)`

---

## 7. Hand-off

Plan 18-01 complete. Plan 18-02 (Cognee → JSONL history replacement) starts next.
