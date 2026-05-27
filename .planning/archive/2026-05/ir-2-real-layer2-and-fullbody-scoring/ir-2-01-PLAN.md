---
phase: ir-2-real-layer2-and-fullbody-scoring
plan: 01
type: execute
wave: 2
depends_on:
  - "ir-2-00"
files_modified:
  - batch_ingest_from_spider.py
autonomous: true
requirements:
  - LF-3.2
  - LF-3.3

must_haves:
  truths:
    - "Layer 2 wiring restructures the per-candidate iteration to ACCUMULATE 5 successfully-scraped articles into a queue, then drain via batched layer2_full_body_score → persist_layer2_verdicts → per-candidate ainsert. End-of-loop drains the partial-final batch."
    - "Layer 2 verdict='reject' rows write ingestions(status='skipped') without ainsert; reason logged at INFO via [layer2] tag (no ingestions.reason column per ir-1 deviation, preserved here)."
    - "Layer 2 verdict='ok' rows proceed to existing ainsert path (ingest_article)."
    - "Layer 2 verdict=None rows (whole-batch failure) STAY in articles.layer2_verdict=NULL and DO NOT proceed to ainsert this run; next ingest tick will re-batch them. The article body stays in articles.body — scrape work is preserved."
    - "Updated ingest loop log tags: [layer2] batch N n=X ok=Y reject=Z null=W wall_ms=M (per-batch summary). [layer2] reject id=N reason=R (per-row reject)."
    - "--dry-run continues to short-circuit the per-candidate body BEFORE scrape — Layer 2 is NOT invoked under dry-run (LF-3.6 ir-1 design retained; spike report acknowledged this and we keep it for cost discipline)."
    - "Layer 2 batch is invoked SERIALLY inside the per-article loop (not parallel). Each batch call holds the loop until it returns; this matches Layer 1's serial-batch model and avoids interleaving with ainsert side-effects."
    - "Existing batch budget interlock (Phase 17 BTIMEOUT) continues to gate the loop. Layer 2 calls count against the budget; if budget exhausts mid-batch, the loop exits and remaining queue is dropped (rows stay scrape-done but layer2_verdict=NULL — re-evaluated next tick)."
  artifacts:
    - path: "batch_ingest_from_spider.py"
      provides: "Batched Layer 2 wiring inside ingest_from_db. Per-candidate loop accumulates ArticleWithBody after scrape; drains in batches of LAYER2_BATCH_SIZE."
      contains: "from lib.article_filter import"
      contains_must_not_exact: "layer2 = layer2_full_body_score(\n"
  key_links:
    - from: "batch_ingest_from_spider.ingest_from_db"
      to: "lib.article_filter.layer2_full_body_score (async)"
      via: "await call on batch of ≤LAYER2_BATCH_SIZE ArticleWithBody"
      pattern: "await layer2_full_body_score("
    - from: "batch_ingest_from_spider.ingest_from_db"
      to: "lib.article_filter.persist_layer2_verdicts"
      via: "after each batch returns non-all-NULL"
      pattern: "persist_layer2_verdicts(conn, "
---

<objective>
Wave 2: rewire `batch_ingest_from_spider.py` per-candidate Layer 2 placeholder call into a batched async call. Layer 2 batches form AFTER scrape; the loop drains 5 scraped articles at a time through layer2 → persist → ainsert (for non-reject) → ingestions write.

Output: `batch_ingest_from_spider.py` consumes ir-2-00's new contract; existing per-candidate scrape and budget logic is preserved; new `[layer2]` log tags added; dry-run unchanged from ir-1 (skips Layer 2).
</objective>

<execution_context>
@.planning/PROJECT-v3.5-Ingest-Refactor.md
@.planning/REQUIREMENTS-v3.5-Ingest-Refactor.md
@.planning/phases/ir-2-real-layer2-and-fullbody-scoring/ir-2-00-PLAN.md
</execution_context>

<context>
@.planning/STATE-v3.5-Ingest-Refactor.md
@CLAUDE.md
</context>

<interfaces>
<!-- New symbols this plan CONSUMES (from ir-2-00 output). -->

```python
# lib/article_filter.py post ir-2-00:
PROMPT_VERSION_LAYER2 = "layer2_v0_20260507"
LAYER2_BATCH_SIZE = 5
async def layer2_full_body_score(articles: list[ArticleWithBody]) -> list[FilterResult]
def persist_layer2_verdicts(conn, articles, results) -> None
```

<!-- Existing batch_ingest_from_spider.py shape this plan modifies (post ir-1-01). -->

```python
# Current import (line 63-72):
from lib.article_filter import (
    ArticleMeta, ArticleWithBody, FilterResult,
    LAYER1_BATCH_SIZE, PROMPT_VERSION_LAYER1,
    layer1_pre_filter, layer2_full_body_score, persist_layer1_verdicts,
)
# CHANGES: include LAYER2_BATCH_SIZE and persist_layer2_verdicts.

# Current Layer 2 inline call (after scrape, lines ~1525-1556 post-ir-1):
layer2_results = layer2_full_body_score([ArticleWithBody(...)])
layer2 = layer2_results[0]
if layer2.verdict == "reject":
    ...
# CHANGES: this single-article inline call is REPLACED by an accumulator
# pattern. The candidate loop appends (row, body) tuples to a queue;
# whenever the queue reaches LAYER2_BATCH_SIZE the drain helper runs.
```
</interfaces>

<tasks>

<task type="auto" tdd="false">
  <name>Task 2.1: Update import + add layer2 batch accumulator</name>
  <read_first>
    - batch_ingest_from_spider.py lines 63-72 (imports), 1410-1660 (ingest_from_db body — current ir-1 shape)
    - lib/article_filter.py post ir-2-00 (new exports list)
  </read_first>
  <files>batch_ingest_from_spider.py</files>
  <behavior>
    - Import surface adds `LAYER2_BATCH_SIZE` and `persist_layer2_verdicts` from `lib.article_filter`.
    - Inside `ingest_from_db`, AFTER the per-candidate loop's scrape+body-persist phase, REMOVE the existing inline single-article Layer 2 call and the immediate ainsert. Replace with an accumulator pattern:
      1. After each successful scrape (where `body` is non-empty), append `(row, body)` to a `layer2_queue: list[tuple]` local.
      2. When `len(layer2_queue) >= LAYER2_BATCH_SIZE`, call a local `_drain_layer2_queue` helper that:
         a. Builds `articles_with_body = [ArticleWithBody(id=row[0], source="wechat", title=row[1], body=body) for row, body in layer2_queue]`.
         b. Times the call; awaits `layer2_full_body_score(articles_with_body)`.
         c. Logs `[layer2] batch N n=X ok=Y reject=Z null=W wall_ms=M`.
         d. If null_count == len(layer2_queue): log warning; clear queue WITHOUT persist (rows stay layer2_verdict=NULL, re-eval next tick); return early — the batched articles do NOT proceed to ainsert this tick.
         e. Else: call `persist_layer2_verdicts(conn, articles_with_body, results)`.
         f. For each (row, body, result): if verdict=='reject', log `[layer2] reject id=N reason=R`, write `ingestions(status='skipped')`. If verdict=='ok' (or any non-reject non-None — defensive), call existing per-article ainsert path: `success, wall = await ingest_article(url, dry_run, rag, effective_timeout=...)`, write ingestions(status='ok'/'failed'), update completed_times/timeout_histogram/budget tracking.
         g. Clear queue.
      3. After the candidate loop ends: call `_drain_layer2_queue` ONCE MORE to handle any final partial batch (size < LAYER2_BATCH_SIZE).
    - Preserve all existing per-article logic that PRECEDES the Layer 2 call (cap check, checkpoint check, body persist, dry-run short-circuit, graded probe). The accumulator logic only replaces the Layer 2 + ainsert portion.
    - Preserve budget/timeout interlock semantics: the per-batch wait counts against the global batch_start clock. If budget is exhausted DURING `_drain_layer2_queue`, the partial drain still completes (we don't interrupt mid-batch) but no further batches are issued.
  </behavior>
  <action>
**Concrete edit instructions for `batch_ingest_from_spider.py`:**

1. **Update import block** (line ~63-72) to add LAYER2_BATCH_SIZE and persist_layer2_verdicts:

```python
from lib.article_filter import (
    ArticleMeta,
    ArticleWithBody,
    FilterResult,
    LAYER1_BATCH_SIZE,
    LAYER2_BATCH_SIZE,
    PROMPT_VERSION_LAYER1,
    layer1_pre_filter,
    layer2_full_body_score,
    persist_layer1_verdicts,
    persist_layer2_verdicts,
)
```

2. **Identify the ir-1-01 Layer 2 inline block** at approximately:
```python
# v3.5 ir-1 (LF-3.2 / LF-3.3): Layer 2 with new 3-field FilterResult shape.
layer2_results = layer2_full_body_score([
    ArticleWithBody(id=art_id, source="wechat", title=title, body=body or ""),
])
layer2 = layer2_results[0]
if layer2.verdict == "reject":
    logger.info("  [layer2] reject id=%s reason=%s", art_id, layer2.reason)
    conn.execute(
        "INSERT OR REPLACE INTO ingestions(article_id, status) VALUES (?, 'skipped')",
        (art_id,),
    )
    conn.commit()
    continue
```

This block AND the subsequent `ingest_article` invocation + ingestions write + sleep + budget check need to MOVE into the `_drain_layer2_queue` helper. The current structure has all of this happening INSIDE the per-candidate `for` loop body; ir-2-01 lifts it OUT into a helper that runs at batch boundaries.

3. **Initialize `layer2_queue` BEFORE the per-candidate loop**:

After Layer 1 chunk loop completes (around the `[layer1] total inputs=X candidates=Y` log line) and BEFORE the `for i, (...) in enumerate(candidate_rows, 1):` line, add:

```python
# v3.5 ir-2 (LF-3.2): Layer 2 batch accumulator.
# Successfully-scraped candidates queue here; drain at LAYER2_BATCH_SIZE
# boundaries to call the batched DeepSeek Layer 2.
layer2_queue: list[tuple[tuple, str]] = []  # (row_tuple, scraped_body) pairs
layer2_chunk_idx = 0
```

4. **Define `_drain_layer2_queue` as a closure** inside `ingest_from_db` (so it has access to `conn`, `rag`, `dry_run`, `batch_start`, `total_batch_budget`, `completed_times`, `timeout_histogram`, `timed_out_count`, `clamped_count`, `safety_margin_triggered`, `processed`, `max_articles`, etc.). Place it right after the `layer2_queue` init:

```python
async def _drain_layer2_queue() -> None:
    """Drain pending layer2 batch: call layer2_full_body_score, persist
    verdicts, ainsert non-rejected articles. Called when the queue hits
    LAYER2_BATCH_SIZE and once at end-of-loop."""
    nonlocal layer2_chunk_idx, processed, timed_out_count, clamped_count, safety_margin_triggered
    if not layer2_queue:
        return

    queue_snapshot = list(layer2_queue)
    layer2_queue.clear()

    articles_with_body = [
        ArticleWithBody(
            id=row[0],
            source="wechat",
            title=row[1] or "",
            body=body or "",
        )
        for row, body in queue_snapshot
    ]

    t0 = time.monotonic()
    layer2_results = await layer2_full_body_score(articles_with_body)
    wall_ms = int((time.monotonic() - t0) * 1000)

    ok_count = sum(1 for r in layer2_results if r.verdict == "ok")
    rej_count = sum(1 for r in layer2_results if r.verdict == "reject")
    null_count = sum(1 for r in layer2_results if r.verdict is None)

    chunk_idx = layer2_chunk_idx
    layer2_chunk_idx += 1

    if null_count == len(layer2_results):
        err_class = layer2_results[0].reason if layer2_results else "empty_batch"
        logger.warning(
            "[layer2] batch %d NULL reason=%s n=%d wall_ms=%d — "
            "rows stay layer2_verdict=NULL, retry next tick",
            chunk_idx, err_class, len(queue_snapshot), wall_ms,
        )
        return

    logger.info(
        "[layer2] batch %d n=%d ok=%d reject=%d null=%d wall_ms=%d",
        chunk_idx, len(queue_snapshot), ok_count, rej_count, null_count, wall_ms,
    )

    persist_layer2_verdicts(conn, articles_with_body, layer2_results)

    # Per-row processing: reject → skipped, ok → ainsert.
    for (row, body), result in zip(queue_snapshot, layer2_results):
        art_id = row[0]
        url = row[2]

        if result.verdict == "reject":
            logger.info(
                "  [layer2] reject id=%s reason=%s",
                art_id, result.reason,
            )
            conn.execute(
                "INSERT OR REPLACE INTO ingestions(article_id, status) "
                "VALUES (?, 'skipped')",
                (art_id,),
            )
            conn.commit()
            continue

        if result.verdict is None:
            # Mixed-batch: this slot failed but others succeeded. Skip
            # ainsert; row stays layer2_verdict=NULL via persist_layer2 above
            # (which writes whatever the result tuple has, including None).
            # Wait — we already persisted; the row IS now NULL. Next tick
            # will re-evaluate. Don't write ingestions row.
            continue

        # Verdict is 'ok' (or future non-reject value) → proceed to ainsert.
        # Re-apply existing budget interlock + ainsert logic.
        remaining = get_remaining_budget(batch_start, total_batch_budget)
        effective_timeout = clamp_article_timeout(
            _SINGLE_CHUNK_FLOOR_S, remaining, BATCH_SAFETY_MARGIN_S
        )
        if effective_timeout < _SINGLE_CHUNK_FLOOR_S:
            clamped_count += 1
            logger.info(
                "  Clamped article timeout: %ds (remaining=%.0fs, margin=%ds)",
                effective_timeout, remaining, BATCH_SAFETY_MARGIN_S,
            )
        if remaining - BATCH_SAFETY_MARGIN_S <= 0:
            safety_margin_triggered = True

        success, wall = await ingest_article(
            url, dry_run, rag, effective_timeout=effective_timeout
        )
        if dry_run:
            status = "dry_run"
        elif success:
            status = "ok"
            completed_times.append(wall)
            timeout_histogram[_bucket_article_time(wall)] += 1
        else:
            status = "failed"
            if wall >= effective_timeout:
                timed_out_count += 1
                timeout_histogram["900s+"] += 1

        conn.execute(
            "INSERT OR REPLACE INTO ingestions(article_id, status) VALUES (?, ?)",
            (art_id, status),
        )
        conn.commit()

        processed += 1
        if not dry_run:
            logger.info(
                "  Sleeping %ds (DeepSeek LLM + dual-key Gemini rotation)...",
                SLEEP_BETWEEN_ARTICLES,
            )
            await asyncio.sleep(SLEEP_BETWEEN_ARTICLES)
```

5. **REPLACE the existing inline Layer 2 + ainsert block in the per-candidate loop**:

Find the block starting with `# v3.5 ir-1 (LF-3.2 / LF-3.3): Layer 2 with new 3-field FilterResult shape.` and ending with the `ingest_article(...)` invocation + post-ainsert ingestions write + sleep + budget check (~lines 1525-1660 in the post-ir-1 file). REPLACE the entire block with:

```python
# v3.5 ir-2 (LF-3.2): defer Layer 2 + ainsert to batched drain. Each
# successfully-scraped candidate is queued; the queue drains at
# LAYER2_BATCH_SIZE boundaries and once after the candidate loop ends.
if not body:
    # Scrape failed earlier in this iteration; do NOT enqueue. The article
    # has no body to score; skip silently (the next ingest tick will see
    # body=NULL and re-attempt scrape).
    logger.warning(
        "  layer2 enqueue skipped — no body for art_id=%s; will retry next tick",
        art_id,
    )
    continue

layer2_queue.append((row, body))
if len(layer2_queue) >= LAYER2_BATCH_SIZE:
    await _drain_layer2_queue()
    # Budget exhausted check after each drain.
    if get_remaining_budget(batch_start, total_batch_budget) <= 0:
        logger.warning(
            "Batch budget exhausted (%ds elapsed >= %ds) — stopping loop; "
            "remaining %d candidate(s) will show as not_started in metrics.",
            int(time.time() - batch_start), total_batch_budget,
            len(candidate_rows) - i,
        )
        break

# Cap check: if max_articles cap reached, drain remaining queue and break.
if max_articles is not None and processed >= max_articles:
    logger.info(
        "max-articles cap reached (%d) — draining final layer2 queue and stopping.",
        max_articles,
    )
    await _drain_layer2_queue()
    break
```

Note: the original cap-check at the TOP of the loop (around line 1426) should remain — it short-circuits articles that have NOT yet been scraped. The added cap-check ABOVE is post-enqueue, ensuring the queue drains before exiting.

6. **After the candidate loop ends, drain any remaining partial batch**:

Right after `for i, (...) in enumerate(candidate_rows, 1):` block ends (just before `logger.info("Done — ...")`), add:

```python
# Drain final partial batch (size < LAYER2_BATCH_SIZE).
await _drain_layer2_queue()
```

7. **Update the existing `Done — N candidates processed of Y total inputs` log line** to remain accurate:

The existing format is fine — `processed` counter is incremented inside `_drain_layer2_queue` for ok-verdict articles; reject and NULL-verdict do NOT increment. So `processed` reflects "successfully ainserted articles" which matches the log semantics.

8. **HARD CONSTRAINTS:**
- DO NOT change the signatures of `ingest_from_db`, `ingest_article`, `_build_topic_filter_query`.
- DO NOT modify the Layer 1 chunk loop — that landed in ir-1-01 and is unchanged.
- DO NOT change dry-run behavior — dry-run still short-circuits BEFORE scrape (LF-3.6).
- DO NOT add an `ingestions.reason` column — preserved deviation from ir-1.
- DO NOT make Layer 2 calls run in parallel with each other — strict serial drain (matches Layer 1 model).
- DO NOT modify the graded probe block, checkpoint logic, or pre-scrape guard — they remain in place for backwards compatibility.
- Per CLAUDE.md "Surgical Changes": every changed line traces to LF-3.2 / LF-3.3.
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy python -c "import batch_ingest_from_spider; print('imports ok')"</automated>
    <automated>grep -c "layer2_queue" batch_ingest_from_spider.py | grep -qE "^[5-9]$|^1[0-9]$" && echo "queue refs ok"</automated>
    <automated>grep -q "await _drain_layer2_queue" batch_ingest_from_spider.py && echo "drain helper called"</automated>
    <automated>grep -q "persist_layer2_verdicts" batch_ingest_from_spider.py && echo "persist called"</automated>
  </verify>
  <acceptance_criteria>
    - File imports cleanly: `DEEPSEEK_API_KEY=dummy python -c "import batch_ingest_from_spider"` exits 0.
    - File contains literal `await layer2_full_body_score(`.
    - File contains literal `persist_layer2_verdicts(conn, articles_with_body, layer2_results)`.
    - File contains literal `[layer2] batch` log tag (per-batch summary line).
    - File contains literal `[layer2] reject id=` log tag (per-row reject line).
    - File no longer contains the OLD per-article inline call shape: `layer2_results = layer2_full_body_score([` (the bracket form indicates synchronous single-element list call from ir-1-01).
  </acceptance_criteria>
  <done>LF-3.2 (Layer 2 batch wiring + persistence) + LF-3.3 (Layer 2 reject → skipped ingestions) delivered for KOL articles. RSS path remains ir-4 scope.</done>
</task>

</tasks>

<verification>
After Task 2.1 lands:

```bash
DEEPSEEK_API_KEY=dummy python -c "
import batch_ingest_from_spider as bi
import inspect
src = inspect.getsource(bi.ingest_from_db)
assert 'await _drain_layer2_queue' in src
assert 'layer2_queue.append' in src
assert 'persist_layer2_verdicts' in src
print('shape ok')
"
```

The full unit suite minus test_article_filter.py (owned by ir-2-02) should not regress on the v3.4 baseline pass count. test_article_filter.py is expected to FAIL after ir-2-00 because the placeholder shape changed; ir-2-02 fixes that.
</verification>

<commit_message>
feat(ir-2): rewire ingest loop to batched Layer 2

batch_ingest_from_spider.py: replace per-article Layer 2 call with batched
async drain. Successfully-scraped candidates queue into layer2_queue; the
queue drains via _drain_layer2_queue when len reaches LAYER2_BATCH_SIZE
(=5) and once more at end-of-loop for the partial-final batch. Drain calls
layer2_full_body_score (real DeepSeek), persists verdicts atomically,
writes ingestions(status='skipped') for verdict='reject', and runs the
existing ainsert path for verdict='ok'.

Whole-batch NULL on Layer 2 failure (timeout / non-JSON / partial / row
count) leaves rows layer2_verdict=NULL — they re-evaluate on the next
ingest tick. body stays in articles.body (scrape work preserved). Per-row
NULL in mixed batches also skips ainsert without writing ingestions row.

Budget interlock: drain calls count against batch_start clock; budget
exhaust check runs after each drain. max-articles cap drains final queue
before break.

dry-run unchanged from ir-1: short-circuits before scrape, Layer 2 not
invoked under dry-run (LF-3.6 cost discipline retained).

REQs: LF-3.2, LF-3.3
Phase: v3.5-Ingest-Refactor / ir-2 / plan 01
Depends-on: ir-2-00 (lib/article_filter contract, migration 007)
</commit_message>
