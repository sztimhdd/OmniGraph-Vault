# Phase 17: Batch Timeout Management — Design

**Status:** Design-locked 2026-04-30
**Requirements covered:** BTIMEOUT-01, BTIMEOUT-02, BTIMEOUT-03, BTIMEOUT-04
**Implementation plan:** 17-01 (helper) + 17-02 (instrumentation)

## Problem Statement

v3.1 Phase 9 gave every article its own `asyncio.wait_for` budget, computed from
`max(120 + 30 * chunk_count, 900)` seconds. That formula is correct in isolation —
it guarantees a single article has enough time to finish even the slowest
DeepSeek chunk — but it says nothing about the batch as a whole.

Concrete failure mode: a 56-article batch runs on an overnight cron slot.
Articles 20-30 happen to contain large image galleries + long merge-phase entity
work, so each takes ~700s instead of the baseline 441s. The remaining articles
still request their full 900s budget, and total wall-clock pushes past the
operator's tolerance (e.g., the 8-hour overnight window). Result: the batch is
killed externally by `systemd` / Task Scheduler / the cron wrapper, with no
graceful shutdown. The LightRAG storages are left mid-flush, the checkpoint
infra holds partial state, and the batch_validation report never gets emitted
— so the next morning's operator has no metrics, no clean resume point, and no
clue which articles completed.

Phase 17 introduces a batch-level budget that CLAMPS individual article
timeouts when the batch is approaching its deadline. Every article still gets
at least enough time to complete a stage cleanly (60s minimum floor), and the
batch always exits gracefully with a final metrics report, even when budget is
exhausted mid-run. Phase 12 checkpoint state is preserved so subsequent batch
runs resume where this one stopped.

## Single-Article Timeout (Inherited)

Recap only. Do NOT redesign. Quote the formula and its call site verbatim from
`batch_ingest_from_spider.py` lines 134-157:

```python
single_article_timeout = max(120 + 30 * chunk_count, 900)  # seconds
# chunk_count = max(1, len(full_content) // 4800)
# Implemented as _compute_article_budget_s() in batch_ingest_from_spider.py
```

At the url-only call site in `ingest_article()`, the floor (900s) is used
because `full_content` is unknown pre-scrape. Phase 17 COMPOSES with this
formula — it does not replace it. The inner per-chunk LLM_TIMEOUT=600s
(D-09.01) remains in effect inside LightRAG; Phase 17 only operates on the
outer per-article budget used at `asyncio.wait_for` call sites.

## Batch Budget Model

Phase 17 introduces three quantities (BTIMEOUT-01):

- **Total batch budget** — controlled by the `OMNIGRAPH_BATCH_TIMEOUT_SEC` env
  var (default `28800` seconds — 8 hours, sized to cover a 56-article batch at
  the 441s/article Hermes DeepSeek baseline from `docs/MILESTONE_v3.1_CLOSURE.md`
  §3 with ~17% safety headroom; for exploratory 8-article runs operators may
  set `--batch-timeout 3600` to get the original tight-clamp behavior).
  Overridable by the `--batch-timeout` CLI flag on
  `batch_ingest_from_spider.py`. Env var wins if both are set (same precedence
  as `OMNIGRAPH_RPM_*` from Phase 7).

- **Remaining budget** — computed dynamically at the top of each article's
  loop iteration:

  ```python
  batch_start = time.time()
  def get_remaining_budget(total_batch_budget: int) -> float:
      elapsed = time.time() - batch_start
      return max(0, total_batch_budget - elapsed)
  ```

- **Average article time** — rolling mean of the wall-clock times of articles
  that have already finished successfully:

  ```python
  avg_article_time = sum(completed_article_times) / len(completed_article_times)
  ```

`avg_article_time` is used to predict whether the remaining articles fit:
`predicted_remaining_s = remaining_articles * avg_article_time`. When
`predicted_remaining_s > remaining_budget`, the interlock (next section) begins
to clamp per-article timeouts so the batch exits gracefully within budget.

## Interlock Formula

`clamp_article_timeout()` is the pure helper that turns a Phase 9 single-article
budget into a batch-aware effective timeout (BTIMEOUT-02):

```python
def clamp_article_timeout(single_timeout: int, remaining_budget: float, safety_margin: int = 60) -> int:
    """
    Clamp per-article timeout so total batch budget is respected.
    safety_margin: 60 seconds — reserved for checkpoint flush + final report emission.
    """
    effective_budget = remaining_budget - safety_margin
    if effective_budget <= 0:
        # Batch out of budget; article gets half-timeout fallback.
        # If it times out, so be it — batch ends gracefully.
        return max(60, int(single_timeout * 0.5))
    return min(single_timeout, int(effective_budget))
```

**Worked example — production 56-article batch, 28,800s budget, 441s baseline:**

| Article # | Elapsed | Remaining | single_timeout | clamped_timeout | Actual time | Note |
|-----------|---------|-----------|----------------|-----------------|-------------|------|
| 1 | 0s | 28,800s | 900s | 900s (no clamp) | 441s | OK — baseline |
| 20 | 8,820s | 19,980s | 900s | 900s (no clamp) | 450s | OK |
| 40 | 17,640s | 11,160s | 900s | 900s (no clamp) | 430s | OK |
| 56 | 25,332s | 3,468s | 900s | 900s (no clamp) | 441s | OK — finishes at ~25,773s, well under budget |

**Baseline context:** 56 articles × 441s = 24,696s ≈ 6.86h on Hermes DeepSeek
(v3.1 closure §3). The 28,800s budget provides ~17% headroom, so the clamp
only fires on degraded batches where avg article time climbs above ~500s. This
is intentional: the 28,800s default is a safety ceiling, not a tight budget.

**Alternative scenario — exploratory 8-article batch, operators set `--batch-timeout 3600`:**

| Article # | Elapsed | Remaining | single_timeout | clamped_timeout | Actual time | Note |
|-----------|---------|-----------|----------------|-----------------|-------------|------|
| 1 | 0s | 3,600s | 900s | 900s (no clamp) | 441s | OK |
| 6 | 2,646s | 954s | 900s | 894s (just-clamped) | 441s | OK, margin preserved |
| 8 | 3,528s | 72s | 900s | **12s (budget out)** | 12s (fallback timeout) | TIMEOUT — checkpoint captures state for next batch |
| 20 | 1200s | 2400s | 900s | 900s (no clamp) | 70s | OK |
| 40 | 2600s | 1000s | 900s | 900s (no clamp) | 55s | Still OK |
| 50 | 3200s | 400s | 900s | **340s (clamped)** | 340s (TIMEOUT) | Safety margin 60s preserved |
| 51 | 3540s | 60s | 900s | **0s (budget out)** | 60s (fallback timeout) | Checkpoint captures state |

**Arithmetic proof:**

- `clamp_article_timeout(900, 500, 60)` → `effective_budget = 500 - 60 = 440` → `min(900, 440) = 440`. ✅
- `clamp_article_timeout(900, 30, 60)` → `effective_budget = 30 - 60 = -30 ≤ 0` → half-timeout branch → `max(60, int(900 * 0.5)) = max(60, 450) = 450`. ✅

## Checkpoint-Flush Interaction

Rule (BTIMEOUT-03): when `asyncio.wait_for` fires a `TimeoutError`, the
checkpoint-flush + rollback bookkeeping MUST run OUTSIDE the article's timeout
budget. Rationale: if the flush itself counted against the per-article timeout,
a late-stage timeout would cascade into a second timeout during the flush
(recursive failure), leaving the checkpoint in a worse state than a clean
timeout would.

Pseudocode (verbatim from 17-CONTEXT.md § Checkpoint-Flush Interaction):

```python
async def ingest_with_timeout(url: str, timeout_sec: int, rag) -> ArticleResult:
    try:
        return await asyncio.wait_for(ingest_article(url, rag=rag), timeout=timeout_sec)
    except asyncio.TimeoutError:
        # Checkpoint flush is NOT wrapped in wait_for — it's allowed to complete
        # regardless of article timeout being hit.
        await flush_partial_checkpoint(get_article_hash(url))
        raise  # re-raise so batch loop records the timeout
```

**Risk analysis:** Phase 12 checkpoint writes are small JSON files (<5s flush
assumption, per `12-CONTEXT.md` § Atomicity — atomic `.tmp` + rename per
stage). If flush ever exceeds the `safety_margin` of 60s, the batch metrics
emit `safety_margin_triggered: true` — a Phase 15 runbook action item pointing
the operator at either disk I/O contention or unexpectedly large vision-stage
files (`05_vision/` subdir size). A 60s+ flush is pathological by design and
should never happen in normal operation.

## Monitoring Metrics

Schema (BTIMEOUT-04) — copied verbatim from 17-CONTEXT.md § Monitoring Metrics:

```json
{
  "batch_timeout_metrics": {
    "total_batch_budget_sec": 28800,
    "total_elapsed_sec": 2850,
    "batch_progress_vs_budget": 0.79,
    "total_articles": 56,
    "completed_articles": 52,
    "timed_out_articles": 3,
    "not_started_articles": 1,
    "avg_article_time_sec": 54.8,
    "timeout_histogram": {"0-60s": 12, "60-300s": 28, "300-900s": 12, "900s+": 3},
    "clamped_timeouts": 2,
    "safety_margin_triggered": false
  }
}
```

**Integration:** the metrics dict is emitted at batch end by
`batch_ingest_from_spider.py` via both (a) a single `logger.info` line for
log-scraping tools and (b) a standalone `data/batch_timeout_metrics_<ts>.json`
file next to the run summary. When the batch is running as part of a regression
fixtures run (Phase 14), the same dict is also appended to the existing
`batch_validation_report.json` under a new top-level key
`batch_timeout_metrics`.

**Histogram bucket boundaries:** `0-60`, `60-300`, `300-900`, `900+` seconds.
These match logical groupings of short / medium / long / pathological article
times. The Hermes DeepSeek baseline (441s) falls cleanly in the `300-900s`
bucket — at production baseline, most articles should land there, with the
`900s+` bucket entries being the anomalies worth investigating (stuck entity
merge, LLM quota pause, network retry exhaustion). An unusual flood into
`0-60s` / `60-300s` suggests silent-failure regressions (cf. v3.1 closure
§8.1).

## Edge Cases

1. **Batch budget exhausted before all articles processed** — the loop exits
   cleanly after the current article finishes (either success or timeout).
   Final metrics are emitted in the `finally:` block; remaining unprocessed
   articles appear in the metrics as `not_started_articles`. The operator
   re-runs the batch; Phase 12 checkpoint state ensures each article resumes
   from its last completed stage instead of re-scraping / re-classifying from
   scratch.

2. **Single article needs longer than remaining budget** —
   `clamp_article_timeout` returns a shorter effective timeout →
   `asyncio.wait_for` fires a `TimeoutError` inside that smaller window → the
   Phase 12 `lib.checkpoint` infrastructure preserves stage state (text_ingest
   marker, image manifest, vision JSON). The next batch run resumes that
   article from its last completed stage. `clamped_timeouts` counter in the
   metrics is incremented once per article that saw a clamp.

3. **Checkpoint flush itself exceeds safety margin** — should never happen per
   Phase 12 design assumption (checkpoint writes are sub-5s JSON). If
   observed, the batch metrics set `safety_margin_triggered: true`. Runbook
   action: investigate disk I/O contention (slow SMB share?), inspect
   `05_vision/` subdir size, confirm no large files were accidentally dumped
   into a checkpoint stage. This flag is sticky: once set within a batch, it
   stays set in the final metrics emission.

4. **Zero articles completed** — `avg_article_time` is undefined (division by
   zero in the naive mean). Fallback: emit `avg_article_time_sec: null` and
   use `_SINGLE_CHUNK_FLOOR_S` (900s from Phase 9) as the placeholder estimate
   for any remaining-budget prediction logic. The null value is explicit so
   downstream dashboards can distinguish "no data" from "fast batch".

## Future Work

- **Adaptive budget** (deferred) — dynamically adjust `total_batch_budget`
  mid-batch based on observed `avg_article_time`. The static budget is simpler,
  more explicit, and easier to reason about for v3.2.
- **Per-article priority** (deferred) — skip low-value articles when under
  budget pressure. All articles are currently treated equal-priority.
- **Parallel batch execution with shared budget** (deferred) — the current
  design is strictly single-threaded batch; parallel batches with a shared
  budget pool would require coordination primitives out of scope for v3.2.
- **Live dashboard** (deferred) — metrics are emitted at batch end only. Live
  dashboarding (Prometheus / Grafana integration) is a Phase 15 runbook item,
  not a design-time concern.
- **Cross-batch budget pooling** (deferred) — each batch run is independent;
  unused budget from batch N does not carry over to batch N+1.
