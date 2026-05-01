---
revised: "2026-05-01 — v3.1 closure alignment (commit 2b38e98). Default BATCH_TIMEOUT 3600 → 28800 across code fallback, CLI help, and assertions. Tests that set explicit total_budget=3600 (metric-emission tests) retained — they probe metric shape at an arbitrary budget, not the default."
phase: 17-batch-timeout-management
plan: 02
type: execute
wave: 2
depends_on: [17-01]
files_modified:
  - batch_ingest_from_spider.py
  - tests/unit/test_batch_timeout_instrumentation.py
autonomous: true
requirements: [BTIMEOUT-01, BTIMEOUT-03, BTIMEOUT-04]

must_haves:
  truths:
    - "OMNIGRAPH_BATCH_TIMEOUT_SEC env var (default 28800) + --batch-timeout CLI flag are read at batch start"
    - "Batch loop tracks batch_start via time.time() before first article"
    - "Each article timeout is clamped via clamp_article_timeout(single, remaining_budget)"
    - "Completed article wall-clock time is appended to completed_article_times list"
    - "Timeout histogram buckets each completed article time into 0-60/60-300/300-900/900s+"
    - "At batch end, batch_timeout_metrics dict is emitted (stdout log + JSON file)"
    - "Checkpoint flush happens OUTSIDE asyncio.wait_for (post-TimeoutError code path)"
  artifacts:
    - path: "batch_ingest_from_spider.py"
      provides: "Instrumented batch loop emitting batch_timeout_metrics"
      contains: "from lib.batch_timeout import"
    - path: "tests/unit/test_batch_timeout_instrumentation.py"
      provides: "Unit tests for env-var read + metric emission helpers"
      min_lines: 60
  key_links:
    - from: "batch_ingest_from_spider.py::ingest_article"
      to: "lib/batch_timeout.clamp_article_timeout"
      via: "imported call"
      pattern: "clamp_article_timeout\\("
    - from: "batch_ingest_from_spider.py"
      to: "OMNIGRAPH_BATCH_TIMEOUT_SEC env var"
      via: "os.environ.get with fallback"
      pattern: "OMNIGRAPH_BATCH_TIMEOUT_SEC"
    - from: "batch_ingest_from_spider.py"
      to: "batch_timeout_metrics.json output file"
      via: "json.dump at batch end"
      pattern: "batch_timeout_metrics"
---

<objective>
Wire the batch-timeout interlock into `batch_ingest_from_spider.py`: read
`OMNIGRAPH_BATCH_TIMEOUT_SEC` / `--batch-timeout`, track batch_start + completed_article_times,
clamp per-article timeouts via `lib.batch_timeout.clamp_article_timeout`, bucket wall-clock
times into a timeout histogram, and emit a `batch_timeout_metrics` dict at batch end (both
via logger and as a standalone `batch_timeout_metrics.json` file alongside the run summary).

Purpose: Make Phase 17 observable. No changes to ingestion semantics beyond clamping and
metric collection. Design doc (17-00) is the contract; helper (17-01) does the math; this
plan adds the instrumentation call-site and output side.

Output:
1. `batch_ingest_from_spider.py` — modified to import + call `clamp_article_timeout`,
   track metrics, emit `batch_timeout_metrics` at batch end
2. `tests/unit/test_batch_timeout_instrumentation.py` — unit tests for the new pure
   helpers (bucket function, env-var read, metric dict shape)

**Scope boundary (DO NOT expand):**
- No refactor of existing batch loop structure
- No changes to scraping, classification, or ingest_wechat.py
- Checkpoint flush wiring assumes Phase 12 `flush_partial_checkpoint` signature — if
  Phase 12 not yet merged, guard the import with `try/except ImportError` so this plan
  remains mergeable standalone
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/17-batch-timeout-management/17-CONTEXT.md
@.planning/phases/17-batch-timeout-management/17-00-design-doc-PLAN.md
@.planning/phases/17-batch-timeout-management/17-01-clamp-helper-PLAN.md
@.planning/phases/09-timeout-state-management/09-00-SUMMARY.md
@batch_ingest_from_spider.py
@lib/batch_timeout.py

<interfaces>
From `lib/batch_timeout.py` (created in 17-01):
```python
BATCH_SAFETY_MARGIN_S: int = 60
def clamp_article_timeout(single_timeout: int, remaining_budget: float, safety_margin: int = 60) -> int
def get_remaining_budget(batch_start: float, total_batch_budget: int) -> float
```

From `batch_ingest_from_spider.py` (existing Phase 9 / 10 code — do NOT modify signatures):
```python
# Lines 134-157: existing budget helper (keep as-is)
_SINGLE_CHUNK_FLOOR_S = 900

def _compute_article_budget_s(full_content: str) -> int: ...

# Line 160: existing async def — modify to accept `effective_timeout` parameter
async def ingest_article(url: str, dry_run: bool, rag) -> bool: ...

# Line 194-197: existing wait_for call — replace hardcoded _SINGLE_CHUNK_FLOOR_S
await asyncio.wait_for(
    ingest_wechat.ingest_article(url, rag=rag),
    timeout=_SINGLE_CHUNK_FLOOR_S,  # <-- clamp this
)
```

From Phase 12 `lib/checkpoint.py` (may or may not exist at merge time):
- `get_article_hash(url: str) -> str`
- `flush_partial_checkpoint(article_hash: str) -> None` (hypothetical; may be `finalize_stage` or similar)

Env var pattern from Phase 7 (from CLAUDE.md):
- `os.environ.get("OMNIGRAPH_BATCH_TIMEOUT_SEC", str(args.batch_timeout or 28800))`
- Namespaced `OMNIGRAPH_*`; env wins if both env and CLI set.
- Default 28800s (8h) covers 56-article batch at 441s/article Hermes baseline (v3.1 closure §3).
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add batch-budget tracking + clamp call + metric collection to batch_ingest_from_spider.py</name>
  <files>batch_ingest_from_spider.py</files>
  <read_first>
    - batch_ingest_from_spider.py (full file — understand `run()` and `ingest_from_db()` structure at lines 555-695 and 781-903)
    - .planning/phases/17-batch-timeout-management/17-CONTEXT.md § Monitoring Metrics (BTIMEOUT-04) — exact JSON schema
    - .planning/phases/17-batch-timeout-management/17-CONTEXT.md § Reference Pseudocode — integration pattern
    - lib/batch_timeout.py (just created — imports)
    - .planning/phases/09-timeout-state-management/09-00-SUMMARY.md (to avoid breaking Phase 9 contracts)
  </read_first>
  <action>
    Make the following surgical edits to `batch_ingest_from_spider.py`. Touch ONLY what is
    listed; do NOT reformat or refactor adjacent code.

    **Edit 1 — Add import (after line 56, with other `lib` imports):**

    ```python
    from lib import INGESTION_LLM, generate_sync  # existing line 57 — leave as-is
    from lib.batch_timeout import (
        BATCH_SAFETY_MARGIN_S,
        clamp_article_timeout,
        get_remaining_budget,
    )
    ```

    **Edit 2 — Add histogram bucket helper + metric-emission helper (after line 157, after `_compute_article_budget_s`):**

    ```python
    # --- Phase 17 (BTIMEOUT-04): batch-timeout metrics helpers ---

    _HISTOGRAM_BUCKETS: tuple[tuple[str, float], ...] = (
        ("0-60s", 60.0),
        ("60-300s", 300.0),
        ("300-900s", 900.0),
        # Anything above 900s falls into "900s+"
    )


    def _bucket_article_time(seconds: float) -> str:
        """Classify an article wall-clock time into a histogram bucket (BTIMEOUT-04)."""
        for label, upper in _HISTOGRAM_BUCKETS:
            if seconds < upper:
                return label
        return "900s+"


    def _resolve_batch_timeout(cli_value: int | None) -> int:
        """Resolve the total batch budget (OMNIGRAPH_BATCH_TIMEOUT_SEC wins over CLI).

        Phase 7 env var idiom: namespaced OMNIGRAPH_* prefix. If env unset, use CLI
        value; if CLI also None, default to 28800 (8h — covers 56-article batch at 441s
        Hermes baseline per v3.1 closure §3).
        """
        env_val = os.environ.get("OMNIGRAPH_BATCH_TIMEOUT_SEC")
        if env_val:
            try:
                return int(env_val)
            except ValueError:
                logger.warning(
                    "OMNIGRAPH_BATCH_TIMEOUT_SEC=%r is not an int — falling back", env_val
                )
        return int(cli_value) if cli_value else 28800


    def _build_batch_timeout_metrics(
        total_budget: int,
        batch_start: float,
        completed_times: list[float],
        total_articles: int,
        timed_out: int,
        clamped_count: int,
        safety_margin_triggered: bool,
        histogram: dict[str, int],
    ) -> dict:
        """Assemble the batch_timeout_metrics dict per design § Monitoring Metrics (BTIMEOUT-04)."""
        elapsed = time.time() - batch_start
        completed_count = len(completed_times)
        not_started = total_articles - completed_count - timed_out
        avg_article_time = (
            sum(completed_times) / completed_count if completed_count > 0 else None
        )
        return {
            "total_batch_budget_sec": total_budget,
            "total_elapsed_sec": round(elapsed, 2),
            "batch_progress_vs_budget": round(elapsed / total_budget, 4) if total_budget > 0 else None,
            "total_articles": total_articles,
            "completed_articles": completed_count,
            "timed_out_articles": timed_out,
            "not_started_articles": max(0, not_started),
            "avg_article_time_sec": round(avg_article_time, 2) if avg_article_time else None,
            "timeout_histogram": dict(histogram),
            "clamped_timeouts": clamped_count,
            "safety_margin_triggered": safety_margin_triggered,
        }
    ```

    **Edit 3 — Modify `ingest_article` signature to accept `effective_timeout` param
    (replace existing signature at line 160 and the wait_for at line 194-197):**

    Change:
    ```python
    async def ingest_article(url: str, dry_run: bool, rag) -> bool:
        # ...docstring (keep as-is)...
        if dry_run:
            logger.info("  [dry-run] would ingest: %s", url)
            return True

        import hashlib
        import ingest_wechat

        article_hash = hashlib.md5(url.encode()).hexdigest()[:10]

        try:
            await asyncio.wait_for(
                ingest_wechat.ingest_article(url, rag=rag),
                timeout=_SINGLE_CHUNK_FLOOR_S,   # <-- old
            )
            return True
        except asyncio.TimeoutError:
            logger.warning("TIMEOUT (%ds) — skipping: %s", _SINGLE_CHUNK_FLOOR_S, url[:80])
            # ... (existing rollback block, keep as-is)
    ```

    To:
    ```python
    async def ingest_article(
        url: str,
        dry_run: bool,
        rag,
        effective_timeout: int | None = None,
    ) -> tuple[bool, float]:
        """...existing docstring... Phase 17: returns (success, wall_clock_seconds).

        Phase 17 addition: if ``effective_timeout`` is provided (from the batch
        interlock via ``clamp_article_timeout``), use it. Otherwise fall back to
        Phase 9's ``_SINGLE_CHUNK_FLOOR_S`` (900s) for backward compatibility.
        """
        if dry_run:
            logger.info("  [dry-run] would ingest: %s", url)
            return True, 0.0

        import hashlib
        import ingest_wechat

        article_hash = hashlib.md5(url.encode()).hexdigest()[:10]
        timeout_s = effective_timeout if effective_timeout is not None else _SINGLE_CHUNK_FLOOR_S

        t_start = time.time()
        try:
            await asyncio.wait_for(
                ingest_wechat.ingest_article(url, rag=rag),
                timeout=timeout_s,
            )
            return True, time.time() - t_start
        except asyncio.TimeoutError:
            wall = time.time() - t_start
            logger.warning("TIMEOUT (%ds) — skipping: %s", timeout_s, url[:80])
            doc_id = ingest_wechat.get_pending_doc_id(article_hash)
            if doc_id and rag is not None:
                try:
                    logger.info("  Rolling back partial doc_id=%s (STATE-02)", doc_id)
                    await rag.adelete_by_doc_id(doc_id)
                    logger.info("  Rollback complete — graph consistent (STATE-02)")
                except Exception as rb_exc:
                    logger.error(
                        "  Rollback FAILED for doc_id=%s: %s — graph may be inconsistent",
                        doc_id, rb_exc,
                    )
                finally:
                    ingest_wechat._clear_pending_doc_id(article_hash)
            # Phase 17 BTIMEOUT-03: checkpoint flush runs OUTSIDE wait_for (already
            # past it in this except branch). If Phase 12 checkpoint infra is merged,
            # this is where flush_partial_checkpoint would be called. Guarded with
            # try/ImportError so this plan merges standalone.
            try:
                from lib.checkpoint import flush_partial_checkpoint  # type: ignore
                await flush_partial_checkpoint(article_hash)
            except ImportError:
                pass  # Phase 12 not yet merged; skip silently.
            except Exception as flush_exc:
                logger.warning("Checkpoint flush failed: %s", flush_exc)
            return False, wall
        except Exception as exc:
            wall = time.time() - t_start
            logger.warning(
                "Ingest failed (%s): %s — skipping: %s",
                exc.__class__.__name__, exc, url[:80],
            )
            return False, wall
    ```

    **Edit 4 — Thread batch-budget state through `run()` (modify the existing Phase 3
    loop at lines 626-667):**

    Replace the section starting at `# Phase 3: Ingest survivors` through the `finally:` block
    with:

    ```python
    # Phase 3: Ingest survivors
    rag = None
    if not dry_run and passed:
        from ingest_wechat import get_rag
        logger.info("Initializing fresh LightRAG instance (flush=True; STATE-01)...")
        rag = await get_rag(flush=True)

    # Phase 17 BTIMEOUT-01: batch-budget state
    total_batch_budget = _resolve_batch_timeout(kwargs.get("batch_timeout"))
    batch_start = time.time()
    completed_times: list[float] = []
    timeout_histogram: dict[str, int] = {label: 0 for label, _ in _HISTOGRAM_BUCKETS}
    timeout_histogram["900s+"] = 0
    timed_out_count = 0
    clamped_count = 0
    safety_margin_triggered = False

    try:
        total = len(passed)
        for i, article in enumerate(passed, 1):
            title = article.get("title", "(no title)")
            url = article.get("url", "")
            account_name = article.get("account", "?")

            logger.info("[%d/%d] [%s] %s", i, total, account_name, title)

            if not url:
                logger.warning("  Skipping — no URL")
                summary.append({
                    "account": account_name,
                    "title": title,
                    "url": "",
                    "status": "skipped_no_url",
                })
                continue

            # Phase 17 BTIMEOUT-02: clamp per-article timeout to batch budget.
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
                if wall >= effective_timeout:  # heuristic for wait_for kill
                    timed_out_count += 1
                    timeout_histogram["900s+"] += 1

            summary.append({
                "account": account_name,
                "title": title,
                "url": url,
                "status": status,
            })

            processed += 1
            if not dry_run and processed < total:
                logger.info("  Sleeping %ds (DeepSeek LLM + dual-key Gemini rotation)...", SLEEP_BETWEEN_ARTICLES)
                await asyncio.sleep(SLEEP_BETWEEN_ARTICLES)

            # Phase 17 BTIMEOUT-01: early-exit if budget fully exhausted.
            if get_remaining_budget(batch_start, total_batch_budget) <= 0:
                logger.warning(
                    "Batch budget exhausted (%ds elapsed >= %ds) — stopping loop; "
                    "remaining %d article(s) will show as not_started in metrics.",
                    int(time.time() - batch_start), total_batch_budget, total - i,
                )
                break
    finally:
        if rag is not None:
            await _drain_pending_vision_tasks()
            logger.info("Finalizing LightRAG storages (flushing vdb + graphml)...")
            await rag.finalize_storages()

        # Phase 17 BTIMEOUT-04: emit metrics (always, even on early exit).
        metrics = _build_batch_timeout_metrics(
            total_budget=total_batch_budget,
            batch_start=batch_start,
            completed_times=completed_times,
            total_articles=len(passed),
            timed_out=timed_out_count,
            clamped_count=clamped_count,
            safety_margin_triggered=safety_margin_triggered,
            histogram=timeout_histogram,
        )
        logger.info("batch_timeout_metrics: %s", json.dumps(metrics))
        metrics_path = PROJECT_ROOT / "data" / f"batch_timeout_metrics_{timestamp}.json"
        metrics_path.parent.mkdir(exist_ok=True)
        metrics_path.write_text(
            json.dumps({"batch_timeout_metrics": metrics}, indent=2),
            encoding="utf-8",
        )
        logger.info("Metrics written to %s", metrics_path)
    ```

    **Edit 5 — Add `--batch-timeout` CLI flag in `main()` (after `--classifier` at line 916):**

    Add:
    ```python
    parser.add_argument(
        "--batch-timeout", type=int, default=None,
        help="Total batch budget in seconds (default 28800 = 8h, covers 56-article batch at 441s/article Hermes baseline; overridden by OMNIGRAPH_BATCH_TIMEOUT_SEC env var)",
    )
    ```

    And thread `batch_timeout=args.batch_timeout` into both the `run(...)` call (line 934)
    and `ingest_from_db(...)` call if that path also needs it (optional for v1 — document as
    deferred in SUMMARY).

    **Edit 6 — Same block in `ingest_from_db()` (lines 841-903) — mirror the budget tracking.**

    Apply the same pattern (batch_start, completed_times, histogram, metrics emission in
    finally block, clamp call, early-exit guard) to the `ingest_from_db()` batch loop. Thread
    `batch_timeout` through the `ingest_from_db` signature. Keep the schema and code layout
    identical to `run()` so both entry points produce the same metrics JSON shape.

    **Do NOT:**
    - Rename any existing variable / function
    - Reorder existing imports
    - Touch scraping / classification / ingest_wechat.py
    - Add new external dependencies
  </action>
  <verify>
    <automated>python -c "import batch_ingest_from_spider as b; assert callable(b._bucket_article_time) and b._bucket_article_time(30) == '0-60s' and b._bucket_article_time(150) == '60-300s' and b._bucket_article_time(1200) == '900s+' and b._resolve_batch_timeout(None) == 28800; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'from lib.batch_timeout import' batch_ingest_from_spider.py` passes
    - `grep -q 'clamp_article_timeout(' batch_ingest_from_spider.py` passes
    - `grep -q '_bucket_article_time' batch_ingest_from_spider.py` passes
    - `grep -q '_resolve_batch_timeout' batch_ingest_from_spider.py` passes
    - `grep -q 'OMNIGRAPH_BATCH_TIMEOUT_SEC' batch_ingest_from_spider.py` passes
    - `grep -q '"batch_timeout_metrics"' batch_ingest_from_spider.py` passes
    - `grep -q 'argparse.*--batch-timeout\|"--batch-timeout"' batch_ingest_from_spider.py` passes
    - `DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import batch_ingest_from_spider; print('OK')"` passes (import smoke)
    - Bucket function smoke passes: `python -c "import batch_ingest_from_spider as b; assert b._bucket_article_time(30) == '0-60s' and b._bucket_article_time(1200) == '900s+'"`
    - `_resolve_batch_timeout` fallback: `python -c "import batch_ingest_from_spider as b; assert b._resolve_batch_timeout(None) == 28800 and b._resolve_batch_timeout(7200) == 7200"`
    - Existing Phase 8 regression tests still green: `DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_image_pipeline.py -v` (22 passed)
    - Existing Phase 9 tests still green: `DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_timeout_budget.py tests/unit/test_lightrag_timeout.py tests/unit/test_lightrag_llm.py -v`
  </acceptance_criteria>
  <done>
    `batch_ingest_from_spider.py` imports `lib.batch_timeout`, tracks batch-budget state in both
    `run()` and `ingest_from_db()`, clamps each article's timeout via `clamp_article_timeout`,
    buckets wall-clock times into a histogram, and emits `batch_timeout_metrics` at batch end
    (log + JSON file). `--batch-timeout` CLI flag + `OMNIGRAPH_BATCH_TIMEOUT_SEC` env var both
    work (env wins). Phase 8/9 regression tests remain green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Unit-test the new pure helpers (_bucket_article_time, _resolve_batch_timeout, _build_batch_timeout_metrics)</name>
  <files>tests/unit/test_batch_timeout_instrumentation.py</files>
  <behavior>
    - `_bucket_article_time(0) == '0-60s'`
    - `_bucket_article_time(59.9) == '0-60s'`
    - `_bucket_article_time(60) == '60-300s'`
    - `_bucket_article_time(299.9) == '60-300s'`
    - `_bucket_article_time(300) == '300-900s'`
    - `_bucket_article_time(899.9) == '300-900s'`
    - `_bucket_article_time(900) == '900s+'`
    - `_bucket_article_time(5000) == '900s+'`
    - `_resolve_batch_timeout(None)` returns `28800` when env unset
    - `_resolve_batch_timeout(7200)` returns `7200` when env unset (CLI used)
    - `_resolve_batch_timeout(7200)` returns env value when `OMNIGRAPH_BATCH_TIMEOUT_SEC=1800` set (env wins)
    - `_resolve_batch_timeout(None)` returns `28800` when env is invalid (`"not-an-int"`)
    - `_build_batch_timeout_metrics` with zero completed articles → `avg_article_time_sec is None`
    - `_build_batch_timeout_metrics` with 3 articles completed → `avg_article_time_sec` matches mean
    - `_build_batch_timeout_metrics` emits all 11 top-level keys from the locked schema
  </behavior>
  <read_first>
    - batch_ingest_from_spider.py (the edits from Task 1)
    - .planning/phases/17-batch-timeout-management/17-CONTEXT.md § Monitoring Metrics (BTIMEOUT-04) — schema keys
    - tests/unit/test_batch_timeout.py (17-01 test style reference)
  </read_first>
  <action>
    Create `tests/unit/test_batch_timeout_instrumentation.py` with EXACTLY the following
    content. Use monkeypatch for env-var isolation (pytest built-in fixture).

    ```python
    """Phase 17 unit tests for batch_ingest_from_spider.py instrumentation helpers.

    Tests the three pure helpers added in plan 17-02:
      - _bucket_article_time
      - _resolve_batch_timeout (env override behavior)
      - _build_batch_timeout_metrics (output schema shape)
    """
    import time

    import pytest

    import batch_ingest_from_spider as b


    # --- _bucket_article_time ---------------------------------------------------

    @pytest.mark.parametrize("seconds,expected", [
        (0, "0-60s"),
        (30, "0-60s"),
        (59.9, "0-60s"),
        (60, "60-300s"),
        (200, "60-300s"),
        (299.9, "60-300s"),
        (300, "300-900s"),
        (500, "300-900s"),
        (899.9, "300-900s"),
        (900, "900s+"),
        (5000, "900s+"),
    ])
    def test_bucket_article_time(seconds: float, expected: str) -> None:
        assert b._bucket_article_time(seconds) == expected


    # --- _resolve_batch_timeout -------------------------------------------------

    def test_resolve_batch_timeout_default(monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OMNIGRAPH_BATCH_TIMEOUT_SEC", raising=False)
        assert b._resolve_batch_timeout(None) == 28800  # 8h — v3.1 closure §3 Hermes baseline × 56 + headroom


    def test_resolve_batch_timeout_cli_override(monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OMNIGRAPH_BATCH_TIMEOUT_SEC", raising=False)
        assert b._resolve_batch_timeout(7200) == 7200


    def test_resolve_batch_timeout_env_wins_over_cli(monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMNIGRAPH_BATCH_TIMEOUT_SEC", "1800")
        assert b._resolve_batch_timeout(7200) == 1800


    def test_resolve_batch_timeout_invalid_env_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMNIGRAPH_BATCH_TIMEOUT_SEC", "not-an-int")
        assert b._resolve_batch_timeout(None) == 28800
        assert b._resolve_batch_timeout(5400) == 5400


    # --- _build_batch_timeout_metrics -------------------------------------------

    _EXPECTED_KEYS = {
        "total_batch_budget_sec",
        "total_elapsed_sec",
        "batch_progress_vs_budget",
        "total_articles",
        "completed_articles",
        "timed_out_articles",
        "not_started_articles",
        "avg_article_time_sec",
        "timeout_histogram",
        "clamped_timeouts",
        "safety_margin_triggered",
    }


    def test_metrics_has_all_11_top_level_keys() -> None:
        metrics = b._build_batch_timeout_metrics(
            total_budget=3600,
            batch_start=time.time() - 100,
            completed_times=[50.0, 60.0, 70.0],
            total_articles=5,
            timed_out=1,
            clamped_count=2,
            safety_margin_triggered=False,
            histogram={"0-60s": 1, "60-300s": 2, "300-900s": 0, "900s+": 0},
        )
        assert set(metrics.keys()) == _EXPECTED_KEYS


    def test_metrics_avg_article_time_is_null_when_zero_completed() -> None:
        metrics = b._build_batch_timeout_metrics(
            total_budget=3600,
            batch_start=time.time() - 10,
            completed_times=[],
            total_articles=5,
            timed_out=0,
            clamped_count=0,
            safety_margin_triggered=False,
            histogram={"0-60s": 0, "60-300s": 0, "300-900s": 0, "900s+": 0},
        )
        assert metrics["avg_article_time_sec"] is None
        assert metrics["completed_articles"] == 0


    def test_metrics_avg_article_time_matches_mean() -> None:
        metrics = b._build_batch_timeout_metrics(
            total_budget=3600,
            batch_start=time.time() - 100,
            completed_times=[50.0, 60.0, 70.0],
            total_articles=3,
            timed_out=0,
            clamped_count=0,
            safety_margin_triggered=False,
            histogram={"0-60s": 1, "60-300s": 2, "300-900s": 0, "900s+": 0},
        )
        assert metrics["avg_article_time_sec"] == 60.0
        assert metrics["completed_articles"] == 3
        assert metrics["not_started_articles"] == 0


    def test_metrics_not_started_computed_correctly() -> None:
        # 10 total, 5 completed, 2 timed out → 3 not_started
        metrics = b._build_batch_timeout_metrics(
            total_budget=3600,
            batch_start=time.time() - 100,
            completed_times=[10.0] * 5,
            total_articles=10,
            timed_out=2,
            clamped_count=0,
            safety_margin_triggered=False,
            histogram={"0-60s": 5, "60-300s": 0, "300-900s": 0, "900s+": 2},
        )
        assert metrics["not_started_articles"] == 3


    def test_metrics_safety_margin_triggered_flag_preserved() -> None:
        metrics = b._build_batch_timeout_metrics(
            total_budget=3600,
            batch_start=time.time() - 100,
            completed_times=[50.0],
            total_articles=1,
            timed_out=0,
            clamped_count=1,
            safety_margin_triggered=True,
            histogram={"0-60s": 1, "60-300s": 0, "300-900s": 0, "900s+": 0},
        )
        assert metrics["safety_margin_triggered"] is True
        assert metrics["clamped_timeouts"] == 1
    ```
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_batch_timeout_instrumentation.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `test -f tests/unit/test_batch_timeout_instrumentation.py` passes
    - `DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_batch_timeout_instrumentation.py -v` → all tests pass (≥ 18 tests incl. parametrized bucket cases)
    - `grep -q 'from batch_ingest_from_spider' tests/unit/test_batch_timeout_instrumentation.py` passes OR `grep -q 'import batch_ingest_from_spider' tests/unit/test_batch_timeout_instrumentation.py` passes
    - `grep -q '_bucket_article_time' tests/unit/test_batch_timeout_instrumentation.py` passes
    - `grep -q '_resolve_batch_timeout' tests/unit/test_batch_timeout_instrumentation.py` passes
    - `grep -q '_build_batch_timeout_metrics' tests/unit/test_batch_timeout_instrumentation.py` passes
  </acceptance_criteria>
  <done>
    Unit tests for all three instrumentation helpers pass; bucket boundaries parametrized;
    env-var precedence verified with monkeypatch; metric schema shape asserted against all 11
    top-level keys; avg-article-time null/positive branches both covered.
  </done>
</task>

</tasks>

<verification>
```bash
# 17-02 new tests pass
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_batch_timeout_instrumentation.py -v

# 17-01 helper tests still pass (regression guard)
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_batch_timeout.py -v

# Phase 8/9 regression gates
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest \
    tests/unit/test_image_pipeline.py \
    tests/unit/test_timeout_budget.py \
    tests/unit/test_lightrag_timeout.py \
    tests/unit/test_lightrag_llm.py -v

# Batch module still imports cleanly
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import batch_ingest_from_spider; print('OK')"

# CLI flag parses
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe batch_ingest_from_spider.py --help 2>&1 | grep -- '--batch-timeout'
```
</verification>

<success_criteria>
- `batch_ingest_from_spider.py` imports `clamp_article_timeout` + `get_remaining_budget` + `BATCH_SAFETY_MARGIN_S` from `lib.batch_timeout`
- Three new helpers (`_bucket_article_time`, `_resolve_batch_timeout`, `_build_batch_timeout_metrics`) added as pure functions
- `ingest_article` signature extended with `effective_timeout: int | None = None` and returns `tuple[bool, float]` (adds wall-clock time)
- Both `run()` and `ingest_from_db()` loops: track batch_start, clamp timeouts per article, append completed wall-clocks, bucket into histogram
- At batch end (in `finally:` block): emit `batch_timeout_metrics` via logger AND write `batch_timeout_metrics_<ts>.json` under `data/`
- `--batch-timeout` CLI flag added; `OMNIGRAPH_BATCH_TIMEOUT_SEC` env var wins if both set
- Phase 12 checkpoint flush wiring is `try/except ImportError`-guarded so this plan merges standalone even if Phase 12 not yet merged
- Unit tests: 18+ cases across bucket boundaries, env precedence, and metric schema
- No Phase 8 / 9 / 10 regression test fails
</success_criteria>

<output>
After completion, create `.planning/phases/17-batch-timeout-management/17-02-SUMMARY.md`.
</output>
