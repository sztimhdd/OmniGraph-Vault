---
phase: 17-batch-timeout-management
plan: 00
type: execute
wave: 1
depends_on: []
files_modified:
  - docs/BATCH_TIMEOUT_DESIGN.md
autonomous: true
requirements: [BTIMEOUT-01, BTIMEOUT-02, BTIMEOUT-03, BTIMEOUT-04]

must_haves:
  truths:
    - "docs/BATCH_TIMEOUT_DESIGN.md exists and is readable"
    - "Design doc contains all 8 mandatory section headings"
    - "Design doc recaps (not re-designs) v3.1 Phase 9 single-article formula"
    - "Design doc specifies clamp_article_timeout() with worked examples"
    - "Design doc specifies batch_timeout_metrics JSON schema"
    - "Design doc explains why checkpoint flush is outside per-article budget"
  artifacts:
    - path: "docs/BATCH_TIMEOUT_DESIGN.md"
      provides: "Formal design for Phase 17 batch timeout management (BTIMEOUT-01..04)"
      contains: "## Problem Statement"
  key_links:
    - from: "docs/BATCH_TIMEOUT_DESIGN.md § Single-Article Timeout (Inherited)"
      to: "v3.1 Phase 9 formula max(120 + 30*chunk_count, 900)"
      via: "verbatim quote + reference"
      pattern: "max\\(120 \\+ 30"
    - from: "docs/BATCH_TIMEOUT_DESIGN.md § Interlock Formula"
      to: "clamp_article_timeout function signature"
      via: "Python code block"
      pattern: "def clamp_article_timeout"
    - from: "docs/BATCH_TIMEOUT_DESIGN.md § Checkpoint-Flush Interaction"
      to: "Phase 12 lib/checkpoint.py flush API"
      via: "pseudocode reference"
      pattern: "flush_partial_checkpoint"
    - from: "docs/BATCH_TIMEOUT_DESIGN.md § Monitoring Metrics"
      to: "Phase 14 batch_validation_report.json"
      via: "schema append note"
      pattern: "batch_timeout_metrics"
---

<objective>
Author `docs/BATCH_TIMEOUT_DESIGN.md` — the formal design document for Phase 17. This is the
MANDATORY v3.2 gate deliverable and the single source of truth for how per-article timeouts
compose into batch-level budget tracking, interlock rules, checkpoint-flush semantics, and
monitoring metrics.

Purpose: Lock the batch-timeout design before any implementation touches production code. The
doc is the contract implementation plan 17-01 and 17-02 execute against.

Output: One Markdown file with 8 required top-level `##` sections, worked example table,
reference pseudocode sketch, and edge-case enumeration.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/17-batch-timeout-management/17-CONTEXT.md
@.planning/ROADMAP.md
@.planning/phases/12-checkpoint-resume/12-CONTEXT.md
@.planning/phases/14-regression-fixtures/14-CONTEXT.md
@.planning/phases/09-timeout-state-management/09-00-SUMMARY.md
@batch_ingest_from_spider.py

<interfaces>
Inherited formulas (DO NOT redesign — recap only):

From v3.1 Phase 9 (implemented in `batch_ingest_from_spider.py` lines 134-157):
```python
_CHUNK_SIZE_CHARS = 4800
_BASE_BUDGET_S = 120
_PER_CHUNK_S = 30
_SINGLE_CHUNK_FLOOR_S = 900

def _compute_article_budget_s(full_content: str) -> int:
    chunk_count = max(1, len(full_content) // _CHUNK_SIZE_CHARS)
    return max(_BASE_BUDGET_S + _PER_CHUNK_S * chunk_count, _SINGLE_CHUNK_FLOOR_S)
```

Phase 12 checkpoint interface (to reference in § Checkpoint-Flush Interaction):
- Checkpoint flush writes `<5s` of JSON per stage (atomic `.tmp` + rename)
- Stage files: `01_scrape.html`, `02_classify.json`, `03_images/manifest.json`,
  `04_text_ingest.done`, `05_vision/{id}.json`

Phase 14 report schema (to reference in § Monitoring Metrics):
- `batch_validation_report.json` is written by `scripts/validate_regression_batch.py`
- Phase 17 ADDS a new top-level key `batch_timeout_metrics` to that same file
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write docs/BATCH_TIMEOUT_DESIGN.md with all 8 required sections</name>
  <files>docs/BATCH_TIMEOUT_DESIGN.md</files>
  <read_first>
    - .planning/phases/17-batch-timeout-management/17-CONTEXT.md (full file — the design source of truth)
    - .planning/ROADMAP.md Phase 17 block (lines 216-226 — success criteria)
    - .planning/phases/12-checkpoint-resume/12-CONTEXT.md § Atomicity (CKPT-04) — for flush-time assumption
    - .planning/phases/14-regression-fixtures/14-CONTEXT.md § Report Schema (REGR-04) — to verify where metrics append
    - .planning/phases/09-timeout-state-management/09-00-SUMMARY.md — to quote inherited formula accurately
    - batch_ingest_from_spider.py lines 134-157 — current `_compute_article_budget_s` implementation
  </read_first>
  <action>
    Create `docs/BATCH_TIMEOUT_DESIGN.md` with EXACTLY the following 8 top-level sections (heading text must match for grep gate):

    ```markdown
    # Phase 17: Batch Timeout Management — Design

    **Status:** Design-locked 2026-04-30
    **Requirements covered:** BTIMEOUT-01, BTIMEOUT-02, BTIMEOUT-03, BTIMEOUT-04
    **Implementation plan:** 17-01 (helper) + 17-02 (instrumentation)

    ## Problem Statement

    [Explain why v3.1 Phase 9's per-article `max(120 + 30*chunk_count, 900)` budget is
    insufficient at batch scale. Concrete failure mode: 56-article batch where articles
    20-30 consume outsized time → remaining articles still use their full per-article
    budget → total batch wall-clock exceeds operator tolerance (e.g., overnight cron
    slot) → batch killed externally → no graceful shutdown → checkpoint infra left in
    partial state. Phase 17 introduces a batch-level budget that CLAMPS individual
    article timeouts when the batch is approaching its deadline, so the batch always
    exits gracefully with a final metrics report.]

    ## Single-Article Timeout (Inherited)

    [Recap only. Do NOT redesign. Quote the formula and its call site verbatim from
    `batch_ingest_from_spider.py` lines 134-157:]

    ```python
    single_article_timeout = max(120 + 30 * chunk_count, 900)  # seconds
    # chunk_count = max(1, len(full_content) // 4800)
    # Implemented as _compute_article_budget_s() in batch_ingest_from_spider.py
    ```

    [Note: at the url-only call site in `ingest_article()`, the floor (900s) is used
    because `full_content` is unknown pre-scrape. Phase 17 COMPOSES with this formula
    — does not replace it.]

    ## Batch Budget Model

    [Introduce three quantities (BTIMEOUT-01):]
    - **Total batch budget** — `OMNIGRAPH_BATCH_TIMEOUT_SEC` env var (default 3600s);
      overridable by `--batch-timeout` CLI flag. Env var wins if both set.
    - **Remaining budget** — computed dynamically:
      ```python
      batch_start = time.time()
      def get_remaining_budget(total_batch_budget: int) -> float:
          elapsed = time.time() - batch_start
          return max(0, total_batch_budget - elapsed)
      ```
    - **Average article time** — rolling mean of completed article wall-clock times:
      ```python
      avg_article_time = sum(completed_article_times) / len(completed_article_times)
      ```

    [Use avg_article_time to predict whether remaining articles fit:
    `predicted_remaining_s = remaining_articles * avg_article_time`. If
    `predicted_remaining_s > remaining_budget`, the interlock (next section) begins
    clamping.]

    ## Interlock Formula

    [Present `clamp_article_timeout()` (BTIMEOUT-02) — COPY VERBATIM from 17-CONTEXT.md
    § Single-Article / Batch Interlock:]

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

    [Include the worked example table VERBATIM from 17-CONTEXT.md § Worked Example:]

    | Article # | Elapsed | Remaining | single_timeout | clamped_timeout | Actual time | Note |
    |-----------|---------|-----------|----------------|-----------------|-------------|------|
    | 1 | 0s | 3600s | 900s | 900s (no clamp) | 45s | OK |
    | 20 | 1200s | 2400s | 900s | 900s (no clamp) | 70s | OK |
    | 40 | 2600s | 1000s | 900s | 900s (no clamp) | 55s | Still OK |
    | 50 | 3200s | 400s | 900s | **340s (clamped)** | 340s (TIMEOUT) | Safety margin 60s preserved |
    | 51 | 3540s | 60s | 900s | **0s (budget out)** | 60s (fallback timeout) | Checkpoint captures state |

    [Add a short arithmetic proof that `clamp_article_timeout(900, 500, 60) == 440` and
    `clamp_article_timeout(900, 30, 60) == 450` (half-timeout branch).]

    ## Checkpoint-Flush Interaction

    [Rule (BTIMEOUT-03): When `asyncio.wait_for` fires a TimeoutError, the checkpoint
    flush + rollback bookkeeping runs OUTSIDE the article's timeout budget. Rationale:
    if flush counts against per-article timeout, a late-stage timeout cascades into a
    SECOND timeout during flush itself (recursive failure).]

    [Include pseudocode verbatim from 17-CONTEXT.md § Checkpoint-Flush Interaction:]

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

    [Risk analysis: Phase 12 checkpoint writes are small JSON (<5s flush assumption,
    per 12-CONTEXT.md § Atomicity). If flush exceeds `safety_margin` (60s), monitoring
    emits `safety_margin_triggered: true` — Phase 15 runbook action item. Flush over
    60s is considered pathological and should never happen per design.]

    ## Monitoring Metrics

    [Schema (BTIMEOUT-04) — COPY VERBATIM from 17-CONTEXT.md § Monitoring Metrics:]

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
        "timeout_histogram": {"0-60s": 12, "60-300s": 28, "300-900s": 12, "900s+": 3},
        "clamped_timeouts": 2,
        "safety_margin_triggered": false
      }
    }
    ```

    [Integration: emitted at batch end by `batch_ingest_from_spider.py`; appended to
    the existing `batch_validation_report.json` (Phase 14) under a new top-level key
    `batch_timeout_metrics`. When the batch is NOT running as part of a regression
    fixtures run, write `batch_timeout_metrics.json` standalone next to the run summary.]

    [Histogram bucket boundaries: `0-60`, `60-300`, `300-900`, `900+` (seconds). Matches
    logical grouping of short/medium/long/pathological article times.]

    ## Edge Cases

    [Enumerate all four from 17-CONTEXT.md § Design Document Structure → Edge Cases:]

    1. **Batch budget exhausted before all articles processed** — Loop exits cleanly
       after current article finishes (or times out). Final metrics emitted; remaining
       articles marked `not_started_articles`. Operator re-runs batch; Phase 12
       checkpoint resumes from last completed stage per article.

    2. **Single article needs longer than remaining budget** — `clamp_article_timeout`
       returns a shorter timeout → `asyncio.wait_for` fires → Phase 12 checkpoint
       preserves state → next batch run resumes that article from its last completed
       stage.

    3. **Checkpoint flush itself exceeds safety margin** — Should never happen per
       Phase 12 assumption (flush is <5s JSON writes). If observed, `safety_margin_triggered: true`
       in metrics; runbook action: investigate disk I/O contention or large vision
       stage files (`05_vision/` subdir size).

    4. **Zero articles completed** — `avg_article_time` is undefined (division by
       zero). Fallback: emit `avg_article_time_sec: null` and use
       `_SINGLE_CHUNK_FLOOR_S` (900s from Phase 9) as the estimate for remaining-budget
       predictions.

    ## Future Work

    - **Adaptive budget** (deferred) — adjust `total_batch_budget` mid-batch based on
      observed `avg_article_time`. Static budget is simpler and more explicit for v3.2.
    - **Per-article priority** (deferred) — skip low-value articles under budget pressure.
    - **Parallel batch execution with shared budget** (deferred) — single-threaded batch is the design.
    - **Live dashboard** (deferred) — metrics emitted at batch end only.
    - **Cross-batch budget pooling** (deferred) — each batch is independent.
    ```

    Replace each bracketed `[...]` placeholder with the described content (full
    paragraphs/bullets — not placeholder text). Do NOT add sections beyond the 8
    specified. Do NOT truncate or abbreviate. Target length: 250-400 lines total
    Markdown so grep gate `grep -c '^## '` returns ≥ 8.
  </action>
  <verify>
    <automated>test -f docs/BATCH_TIMEOUT_DESIGN.md && test $(grep -c '^## ' docs/BATCH_TIMEOUT_DESIGN.md) -ge 8 && grep -q '^## Problem Statement' docs/BATCH_TIMEOUT_DESIGN.md && grep -q '^## Single-Article Timeout (Inherited)' docs/BATCH_TIMEOUT_DESIGN.md && grep -q '^## Batch Budget Model' docs/BATCH_TIMEOUT_DESIGN.md && grep -q '^## Interlock Formula' docs/BATCH_TIMEOUT_DESIGN.md && grep -q '^## Checkpoint-Flush Interaction' docs/BATCH_TIMEOUT_DESIGN.md && grep -q '^## Monitoring Metrics' docs/BATCH_TIMEOUT_DESIGN.md && grep -q '^## Edge Cases' docs/BATCH_TIMEOUT_DESIGN.md && grep -q '^## Future Work' docs/BATCH_TIMEOUT_DESIGN.md && grep -q 'def clamp_article_timeout' docs/BATCH_TIMEOUT_DESIGN.md && grep -q 'batch_timeout_metrics' docs/BATCH_TIMEOUT_DESIGN.md && grep -q 'max(120 + 30' docs/BATCH_TIMEOUT_DESIGN.md</automated>
  </verify>
  <acceptance_criteria>
    - `test -f docs/BATCH_TIMEOUT_DESIGN.md` passes
    - `grep -c '^## ' docs/BATCH_TIMEOUT_DESIGN.md` returns ≥ 8
    - Each of the 8 section headings present (grep -q for each)
    - `grep -q 'def clamp_article_timeout' docs/BATCH_TIMEOUT_DESIGN.md` passes (interlock formula embedded)
    - `grep -q 'batch_timeout_metrics' docs/BATCH_TIMEOUT_DESIGN.md` passes (metrics schema embedded)
    - `grep -q 'max(120 + 30' docs/BATCH_TIMEOUT_DESIGN.md` passes (Phase 9 inherited formula quoted)
    - `grep -q 'OMNIGRAPH_BATCH_TIMEOUT_SEC' docs/BATCH_TIMEOUT_DESIGN.md` passes (env var documented)
    - Worked example table present: `grep -q 'Article #' docs/BATCH_TIMEOUT_DESIGN.md` passes
  </acceptance_criteria>
  <done>
    `docs/BATCH_TIMEOUT_DESIGN.md` is committed with 8 required sections, inherited formula
    quoted accurately, interlock Python code block, worked example table, JSON metrics schema,
    all 4 edge cases enumerated. Grep acceptance checks all pass.
  </done>
</task>

</tasks>

<verification>
```bash
# All 8 sections present
test $(grep -c '^## ' docs/BATCH_TIMEOUT_DESIGN.md) -ge 8

# Key content anchors
grep -q 'def clamp_article_timeout' docs/BATCH_TIMEOUT_DESIGN.md
grep -q 'batch_timeout_metrics' docs/BATCH_TIMEOUT_DESIGN.md
grep -q 'max(120 + 30' docs/BATCH_TIMEOUT_DESIGN.md
grep -q 'OMNIGRAPH_BATCH_TIMEOUT_SEC' docs/BATCH_TIMEOUT_DESIGN.md
grep -q 'flush_partial_checkpoint' docs/BATCH_TIMEOUT_DESIGN.md
grep -q 'safety_margin' docs/BATCH_TIMEOUT_DESIGN.md
```
</verification>

<success_criteria>
- `docs/BATCH_TIMEOUT_DESIGN.md` exists on disk and is committed
- All 8 mandatory sections present (Problem Statement, Single-Article Timeout (Inherited),
  Batch Budget Model, Interlock Formula, Checkpoint-Flush Interaction, Monitoring Metrics,
  Edge Cases, Future Work)
- Phase 9 inherited formula `max(120 + 30 * chunk_count, 900)` quoted verbatim (not re-designed)
- `clamp_article_timeout()` Python body embedded
- `batch_timeout_metrics` JSON schema embedded
- Worked example table (5+ rows) embedded
- All 4 edge cases enumerated
- No sections beyond the 8 specified (don't pad)
</success_criteria>

<output>
After completion, create `.planning/phases/17-batch-timeout-management/17-00-SUMMARY.md`.
</output>
