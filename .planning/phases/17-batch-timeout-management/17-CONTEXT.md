# Phase 17: Batch Timeout Management - Context

**Gathered:** 2026-04-30
**Status:** Ready for planning
**Source:** PRD supplement (user-provided Phase 12 from v3.2 prompt, labeled Phase 17 in roadmap)

<domain>
## Phase Boundary

**Delivers:** Extension of v3.1 Phase 9's per-article `asyncio.wait_for` budget to BATCH-level: dynamic remaining-budget calculation, single-article/batch interlock, checkpoint-flush interaction semantics, and monitoring metrics.

**Two scopes in this phase:**

1. **DESIGN SCOPE** (mandatory for v3.2 gate):
   - Formal design document `docs/BATCH_TIMEOUT_DESIGN.md` covering:
     - Dynamic remaining-budget formula (batch level)
     - Single-article / batch budget interlock rules
     - Checkpoint-flush interaction with timeouts
     - Monitoring metrics specification
   - Design validated against Phase 12 checkpoint API + Phase 9 single-article timeout formula
   - Inclusion of a reference pseudocode sketch

2. **IMPLEMENTATION SCOPE** (conditional on context budget; mark deferrable if planner decides):
   - Instrumentation hooks in `batch_ingest_from_spider.py`: track `avg_article_time`, `batch_progress_vs_budget`, `timeout_histogram`
   - Budget clamping helper function `clamp_article_timeout(single_timeout, remaining_batch_budget, safety_margin) -> int`
   - Log emission for monitoring metrics at batch end

**Does NOT deliver:**
- Changes to v3.1 Phase 9's single-article `max(120 + 30*chunk_count, 900)` formula — that stays as-is
- Batch restart / recovery orchestration (Phase 12 checkpoint infra handles that)
- Alerting on timeout metrics (runbook operator tasks; Phase 15 docs)
- Distributed batch coordination across machines

**Dependencies:**
- v3.1 Phase 9 (`asyncio.wait_for` wrapping, single-article timeout formula) — MUST be stable
- Phase 12 (`lib/checkpoint.py`) — checkpoint flush on timeout interaction is designed here
- v3.1 Phase 11 `benchmark_result.json` schema — monitoring metrics in this phase mirror the stage_timings structure

</domain>

<decisions>
## Implementation Decisions

### Single-Article Timeout (INHERITED from v3.1 Phase 9, not re-designed)

Formula: `single_article_timeout = max(120 + 30 * chunk_count, 900)` seconds

This phase does NOT change this formula. It only COMPOSES with it.

### Batch-Level Budget (BTIMEOUT-01) — NEW DESIGN

**Total batch budget:**
- Configurable via CLI flag `--batch-timeout` on `batch_ingest_from_spider.py`, default `3600` (1 hour)
- Environment override: `OMNIGRAPH_BATCH_TIMEOUT_SEC` (same fallback pattern as `OMNIGRAPH_RPM_*` from Phase 7)

**Remaining budget calculation:**
```python
batch_start = time.time()
def get_remaining_budget() -> float:
    elapsed = time.time() - batch_start
    return max(0, total_batch_budget - elapsed)
```

**Average article time tracking:**
```python
avg_article_time = sum(completed_article_times) / len(completed_article_times)
# Use this to predict whether remaining articles fit in remaining budget
predicted_end_time = batch_start + elapsed + (remaining_articles * avg_article_time)
```

### Single-Article / Batch Interlock (BTIMEOUT-02) — NEW DESIGN

**Rule:** Per-article timeout clamped to `min(single_article_timeout, remaining_batch_budget - safety_margin)`

```python
def clamp_article_timeout(single_timeout: int, remaining_budget: float, safety_margin: int = 60) -> int:
    """
    Clamp per-article timeout so total batch budget is respected.
    safety_margin: 60 seconds — reserved for checkpoint flush + final report emission
    """
    effective_budget = remaining_budget - safety_margin
    if effective_budget <= 0:
        # Batch out of budget; next article gets minimum viable 60s timeout
        # (if it times out, so be it — batch ends gracefully)
        return max(60, int(single_timeout * 0.5))  # fallback to half-timeout
    return min(single_timeout, int(effective_budget))
```

**Semantics:**
- Early in batch: article gets its full computed timeout (no clamp effect)
- Late in batch: article timeout shrinks to fit; if article needs longer, it gets `TimeoutError` and checkpoint preserves state for next batch run
- Safety margin (60s default) reserves time for checkpoint flush + final monitoring report

### Checkpoint-Flush Interaction (BTIMEOUT-03) — NEW DESIGN

**Rule:** When `asyncio.wait_for` kills an article, the checkpoint-flush + rollback bookkeeping runs OUTSIDE the article's timeout budget.

**Rationale:** If checkpoint flush counts against per-article timeout, a late-stage timeout could cascade into a second timeout during the flush itself (recursive failure). Design assumes checkpoint flush takes <5s (small JSON writes per Phase 12).

**Implementation pattern:**
```python
async def ingest_with_timeout(url: str, timeout_sec: int, rag) -> ArticleResult:
    try:
        return await asyncio.wait_for(ingest_article(url, rag=rag), timeout=timeout_sec)
    except asyncio.TimeoutError:
        # Checkpoint flush is NOT wrapped in wait_for — it's allowed to complete
        # regardless of article timeout being hit
        await flush_partial_checkpoint(get_article_hash(url))
        raise  # re-raise so batch loop records the timeout
```

**Monitoring hook:** Emit `timeout_with_checkpoint_flush_duration_ms` metric to verify checkpoint flush stays fast.

### Monitoring Metrics (BTIMEOUT-04) — NEW DESIGN

**Metrics emitted at batch end:**

```json
{
  "batch_timeout_metrics": {
    "total_batch_budget_sec": 3600,
    "total_elapsed_sec": 2850,
    "batch_progress_vs_budget": 0.79,
    "total_articles": 56,
    "completed_articles": 52,
    "timed_out_articles": 3,
    "not_started_articles": 1,
    "avg_article_time_sec": 54.8,
    "timeout_histogram": {
      "0-60s":     12,
      "60-300s":   28,
      "300-900s":  12,
      "900s+":     3
    },
    "clamped_timeouts": 2,
    "safety_margin_triggered": false
  }
}
```

**Integration:** Append `batch_timeout_metrics` to the existing `batch_validation_report.json` (Phase 14) under a new top-level key.

### Design Document Structure (MANDATORY)

`docs/BATCH_TIMEOUT_DESIGN.md` sections (ALL required):

1. **Problem Statement** — why per-article timeout alone is insufficient at batch scale
2. **Single-Article Timeout (Inherited)** — quick recap of Phase 9 formula
3. **Batch Budget Model** — total budget + remaining budget + avg article time tracking
4. **Interlock Formula** — `clamp_article_timeout()` with worked examples
5. **Checkpoint-Flush Interaction** — why flush is outside budget + risk analysis
6. **Monitoring Metrics** — schema for `batch_timeout_metrics`
7. **Edge Cases**:
   - Batch budget exhausted before all articles processed → graceful exit with status report
   - Single article needs longer than remaining budget → clamp kicks in; article preserved in checkpoint for next batch
   - Checkpoint flush itself exceeds safety margin → warn (should never happen per design assumption)
   - Zero articles completed → avg_article_time undefined; use `single_article_timeout` as estimate
8. **Future Work** — adaptive budget adjustment based on observed article characteristics (deferred)

### Claude's Discretion

- **Implementation split**: Planner decides how many plans (1 or 2). Recommendation: 1 plan for design doc + instrumentation (~1 day); 2nd plan only if implementation is heavy
- **Safety margin value**: 60s default; planner can tune
- **Histogram bucket boundaries**: Current proposal `0-60 / 60-300 / 300-900 / 900+`; planner can refine
- **Whether to make `total_batch_budget` configurable** at batch start or hardcoded — recommendation: env var + CLI flag, env var wins if both set

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source of Truth
- `.planning/MILESTONE_v3.2_REQUIREMENTS.md` (ROADMAP Phase 17 block) — requirements (BTIMEOUT-01..04)
- v3.1 Phase 9 plans — single-article timeout formula + `asyncio.wait_for` wrapping pattern

### Dependency Interfaces
- v3.1 Phase 9: `max(120 + 30 * chunk_count, 900)` formula in `ingest_wechat.py` or similar
- Phase 12 `lib/checkpoint.py` — checkpoint flush API used in timeout cleanup
- Phase 14 `batch_validation_report.json` schema — monitoring metrics appended here

### Existing Files to Read
- `batch_ingest_from_spider.py` — current batch entry point (to add budget tracking + metric emission)
- `ingest_wechat.py` — current `ingest_article` with `asyncio.wait_for` wrapping (from Phase 9)
- `lib/` package (for Phase 7-style env var patterns if adding `OMNIGRAPH_BATCH_TIMEOUT_SEC`)

</canonical_refs>

<specifics>
## Specific Ideas

### Worked Example (for design doc)

**Scenario:** 56-article batch, total budget 3600s, avg article takes 60s.

| Article # | Elapsed | Remaining | single_timeout | clamped_timeout | Actual time | Note |
|-----------|---------|-----------|----------------|-----------------|-------------|------|
| 1 | 0s | 3600s | 900s | 900s (no clamp) | 45s | OK |
| 20 | 1200s | 2400s | 900s | 900s (no clamp) | 70s | OK |
| 40 | 2600s | 1000s | 900s | 900s (no clamp) | 55s | Still OK |
| 50 | 3200s | 400s | 900s | **340s (clamped)** | 340s (TIMEOUT) | Safety margin 60s preserved |
| 51 | 3540s | 60s | 900s | **0s (budget out)** | 60s (fallback timeout) | Checkpoint captures state |

### Reference Pseudocode (for design doc)

```python
# batch_ingest_from_spider.py (pseudocode)

BATCH_TIMEOUT = int(os.environ.get("OMNIGRAPH_BATCH_TIMEOUT_SEC", args.batch_timeout or 3600))
SAFETY_MARGIN = 60

batch_start = time.time()
completed_times = []
timeout_histogram = defaultdict(int)

for url in urls:
    elapsed = time.time() - batch_start
    remaining_budget = max(0, BATCH_TIMEOUT - elapsed)

    chunks = count_chunks(url)  # cheap pre-estimate
    single_timeout = max(120 + 30 * chunks, 900)
    effective_timeout = clamp_article_timeout(single_timeout, remaining_budget, SAFETY_MARGIN)

    try:
        article_start = time.time()
        result = await asyncio.wait_for(ingest_article(url, rag=rag), timeout=effective_timeout)
        article_time = time.time() - article_start
        completed_times.append(article_time)
        timeout_histogram[_bucket(article_time)] += 1
    except asyncio.TimeoutError:
        await flush_partial_checkpoint(get_article_hash(url))
        timeout_histogram["900s+"] += 1
        logger.warning(f"Article {url} timed out after {effective_timeout}s")

emit_batch_timeout_metrics(...)
```

### Acceptance Check Commands

```bash
# 1. Design document exists with all 8 required sections
grep -c '^## ' docs/BATCH_TIMEOUT_DESIGN.md  # should return >= 8

# 2. clamp_article_timeout helper function exists
grep -q 'def clamp_article_timeout' lib/*.py || grep -q 'def clamp_article_timeout' batch_ingest_from_spider.py

# 3. Batch timeout metrics in report
python scripts/validate_regression_batch.py --fixtures test/fixtures/gpt55_article --output /tmp/report.json
jq '.batch_timeout_metrics' /tmp/report.json  # should print non-null object
```

</specifics>

<deferred>
## Deferred Ideas (out of scope, possibly post-v3.2)

- **Adaptive budget** (adjust `total_batch_budget` mid-batch based on observed avg_article_time) — static budget is simpler and explicit
- **Per-article priority** (skip low-value articles if budget pressure) — all articles equal priority
- **Parallel batch execution** with shared budget — single-threaded batch is the design
- **Budget forecasting dashboard** — metrics are emitted at batch end only; live dashboard out of scope
- **Recovery orchestration** (automatic batch restart if budget exhausted) — manual operator task via runbook
- **Cross-batch budget pooling** — each batch is independent

</deferred>

---

*Phase: 17-batch-timeout-management*
*Context gathered: 2026-04-30 via PRD Express Path*
