---
phase: 11-e2e-verification-gate
plan: 02
type: execute
wave: 2
depends_on: [11-00, 11-01]
files_modified:
  - scripts/bench_ingest_fixture.py
  - tests/integration/test_bench_integration.py
autonomous: false
requirements: [E2E-02, E2E-04, E2E-06]

must_haves:
  truths:
    - "Benchmark harness invokes real LightRAG — get_rag(flush=True) → real ainsert → real DeepSeek classify → real embedding (Gemini free tier OR Vertex AI per env)"
    - "text_ingest_ms is measured around rag.ainsert(full_content, ids=[doc_id]) only — excludes Vision worker"
    - "async_vision_start_ms is measured as time-to-spawn (asyncio.create_task), not worker completion"
    - "Benchmark calls rag.aquery(query='GPT-5.5 benchmark results', param=QueryParam(mode='hybrid', top_k=3)) after text ingest"
    - "gate.aquery_returns_fixture_chunk is true when response references the ingested article (via file_path OR signature-fragment substring match)"
    - "gate.text_ingest_under_2min is true when text_ingest_ms < 120000"
    - "gate.zero_crashes is true when no unhandled exceptions propagated (errors array is empty)"
    - "On successful run: benchmark_result.json has gate_pass=true AND script exits 0"
    - "On any failure: benchmark_result.json has gate_pass=false, errors[] populated, exit code 1"
    - "Vision worker task is awaited OR drained before script exits — sub-doc ainsert completes or is cancelled cleanly"
  artifacts:
    - path: "scripts/bench_ingest_fixture.py"
      provides: "Full integration harness: real LightRAG, DeepSeek classify, text-first ingest, aquery validation, Vision task drain"
      min_lines: 400
      contains: "rag.aquery|get_rag\\(flush=True\\)"
    - path: "tests/integration/test_bench_integration.py"
      provides: "Integration tests with LightRAG + real embedding (env-gated — skips if env vars unset)"
      min_lines: 100
  key_links:
    - from: "scripts/bench_ingest_fixture.py"
      to: "ingest_wechat.get_rag"
      via: "from ingest_wechat import get_rag; rag = await get_rag(flush=True)"
      pattern: "get_rag\\(flush=True\\)"
    - from: "scripts/bench_ingest_fixture.py"
      to: "rag.ainsert"
      via: "perf_counter-wrapped call with ids=[doc_id] for text-first parent ingest"
      pattern: "rag\\.ainsert\\("
    - from: "scripts/bench_ingest_fixture.py"
      to: "rag.aquery"
      via: "QueryParam(mode='hybrid', top_k=3) with query='GPT-5.5 benchmark results'"
      pattern: "rag\\.aquery\\(.*GPT-5.5 benchmark"
    - from: "scripts/bench_ingest_fixture.py"
      to: "ingest_wechat._vision_worker_impl"
      via: "asyncio.create_task for async_vision_start_ms measurement"
      pattern: "asyncio\\.create_task\\(_vision_worker_impl"
---

<objective>
Wire the 11-00 harness skeleton to real LightRAG, run it against the fixture, and close the
milestone v3.1 gate.

Purpose: replace the stubbed stages in 11-00 with real calls (classify via DeepSeek, text ingest
via `rag.ainsert`, `aquery` validation, Vision task spawn + drain). Produce `benchmark_result.json`
with `gate_pass: true`.

Output: a working benchmark that, when run against `test/fixtures/gpt55_article/` with
appropriate API keys set, completes in <2min text-ingest wall-clock and writes `gate_pass: true`.
This is the milestone v3.1 closing artifact.

Depends on: 11-00 (schema + harness skeleton) AND 11-01 (Vertex AI opt-in — required so free-tier
embed quota doesn't wall the <2min gate on local dev).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/phases/11-e2e-verification-gate/11-PRD.md
@.planning/phases/11-e2e-verification-gate/11-CONTEXT.md
@.planning/phases/11-e2e-verification-gate/11-00-bench-harness-and-schema-PLAN.md
@.planning/phases/11-e2e-verification-gate/11-01-vertex-ai-opt-in-PLAN.md
@.planning/phases/10-classification-and-ingest-decoupling/10-02-SUMMARY.md
@ingest_wechat.py
@batch_ingest_from_spider.py

<interfaces>
<!-- Key contracts the executor needs. -->

From ingest_wechat.py (post-Phase-10, current state):
- `async def get_rag(flush: bool = True) -> LightRAG` — fresh instance per call; flush=True default
- `async def ingest_article(url, rag=None) -> "asyncio.Task | None"` — returns Vision task handle
- `async def _vision_worker_impl(*, rag, article_hash, url_to_path, title, filter_stats,
  download_input_count, download_failed) -> None` — co-located, testable, never raises
- `def _register_pending_doc_id(article_hash, doc_id)` / `def _clear_pending_doc_id(article_hash)`
  — for mid-ainsert rollback; harness uses these around its own ainsert call
- `process_content(html) -> (markdown, img_urls)` — HTML → markdown converter (not needed here;
  fixture provides article.md already)

From batch_ingest_from_spider.py:
- `_drain_pending_vision_tasks()` — 120s drain pattern; harness MAY reuse or explicitly await
  the single Vision task for cleaner test semantics. Recommend explicit `await vision_task`
  since benchmark spawns exactly one; avoids pulling in the whole batch orchestrator module.
- `_classify_full_body(conn, article_id, url, title, body, api_key) -> dict | None` — DeepSeek
  classifier; returns `{depth, topics, rationale}` or None on failure. Requires SQLite conn.
  HARNESS HEURISTIC: don't wire through SQLite — instead, call DeepSeek directly via
  `batch_classify_kol._build_fullbody_prompt` + `_call_deepseek_fullbody`; persist the result
  only to the benchmark JSON, not to kol_scan.db. Keeps the harness side-effect-free re: real
  article data.

From lightrag.QueryParam (external library):
- `QueryParam(mode="hybrid", top_k=3)` — passes to `rag.aquery`

Vision worker task handle behavior: `asyncio.create_task(_vision_worker_impl(...))` returns
immediately (sub-ms). Task completion depends on describe_images latency (~4s/image × 28 images
~= 112s worst-case with Gemini Vision; SiliconFlow is faster). Benchmark MUST NOT block the
gate on Vision worker completion — `async_vision_start_ms` is spawn time only.

Integration test environment:
- `DEEPSEEK_API_KEY` must be set (real key; not 'dummy') for live classify test
- `OMNIGRAPH_GEMINI_KEY` or `GEMINI_API_KEY` must be set for free-tier embedding path
- `GOOGLE_APPLICATION_CREDENTIALS` + `GOOGLE_CLOUD_PROJECT` optionally set for Vertex path
- `SILICONFLOW_API_KEY` optionally set for balance precheck
- Integration test SKIPS if DEEPSEEK_API_KEY is 'dummy' or unset (pytest marker + skipif)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Wire real LightRAG text-ingest flow into harness with aquery validation and Vision task drain</name>
  <files>scripts/bench_ingest_fixture.py, tests/integration/test_bench_integration.py</files>
  <behavior>
    Test 1 (unit-style, mocked rag — covers wiring without burning API credits):
      - Build a MagicMock rag where:
        - `rag.ainsert(AsyncMock)` succeeds in ~100ms (asyncio.sleep simulated)
        - `rag.aquery(AsyncMock)` returns a MagicMock response with text containing "GPT-5.5"
        - `rag.finalize_storages(AsyncMock)` no-ops
      - Mock `get_rag` → returns the MagicMock
      - Mock `_call_deepseek_fullbody` to return `{"depth": 3, "topics": ["AI"], "rationale": "..."}`
      - Invoke `main(argv=["--fixture", str(tmp_fixture)])`
      - Assert:
        - `rag.ainsert` called once with `ids=["wechat_<hash>"]`
        - `rag.aquery` called once with `query="GPT-5.5 benchmark results"` and
          `param.mode == "hybrid"`, `param.top_k == 3`
        - Result JSON has `gate_pass=true`, all 3 gate flags true
        - `stage_timings_ms.text_ingest` is int ≥ 100 (matches sleep)
        - `stage_timings_ms.async_vision_start` is int < 100 (just task creation)
        - Exit code 0

    Test 2 — Vision task is awaited or drained (no leaked tasks):
      - Same mocked setup; after harness returns, use `asyncio.all_tasks()` to inspect.
      - Assert: no pending tasks remain (Vision task either completed or was cancelled).

    Test 3 — text_ingest > 120000ms → gate fails:
      - Mock rag.ainsert to sleep 0.12s but manually set `stage_timings_ms.text_ingest = 120001`
        in the result dict (or monkeypatch perf_counter to produce a >120s reading).
      - Assert `gate.text_ingest_under_2min = false`, `gate_pass = false`, exit 1.

    Test 4 — aquery returns no matching chunk → gate fails:
      - Mock rag.aquery to return response text like "I don't know about that article".
      - Assert `gate.aquery_returns_fixture_chunk = false`, `gate_pass = false`, exit 1.

    Test 5 — Exception in ainsert → captured in errors[], gate_pass=false, exit 1:
      - Mock rag.ainsert to raise RuntimeError("boom").
      - Assert: JSON still written, `errors` contains `{"type": "RuntimeError", "message": "boom",
        "stage": "text_ingest"}`, `gate_pass=false`, exit 1.

    Test 6 — Integration (live, skipped if env vars unset):
      - `@pytest.mark.integration` + `@pytest.mark.skipif(not all required env vars)`
      - Run harness against real fixture with real DeepSeek + real LightRAG
      - Assert: result JSON written, `gate_pass=true`, `text_ingest_ms < 120000`, exit 0
      - This is the ACTUAL milestone v3.1 gate run — gate-closing test
      - Use a tmp_path for `RAG_WORKING_DIR` so we don't pollute the user's real KG
        (set via monkeypatch env `RAG_WORKING_DIR` if module reads it, OR pass working_dir kwarg)
  </behavior>
  <action>
    Edit `scripts/bench_ingest_fixture.py` — replace the stubbed stage bodies from Plan 11-00 with
    real calls. Key changes:

    1. Add imports at top (keep 11-00 imports intact):
       ```python
       # Must be before any LightRAG import chain:
       os.environ.setdefault("LLM_TIMEOUT", "600")

       # Late-import inside _run_benchmark to avoid top-level LightRAG init cost
       # when `--help` is the only invocation.
       ```

    2. `_classify_with_deepseek(title: str, body: str) -> tuple[dict | None, int]`:
       - Pure function — takes title+body, returns (classification_dict, elapsed_ms).
       - Imports inside: `from batch_classify_kol import _build_fullbody_prompt,
         _call_deepseek_fullbody`. (Late-import to avoid import-time side effects.)
       - Reads `DEEPSEEK_API_KEY` env var; returns `(None, elapsed_ms)` if unset.
       - Builds prompt, calls DeepSeek, returns `(result, elapsed_ms)`.
       - Records elapsed via perf_counter.

    3. `_copy_fixture_images(fixture_images_dir: Path, article_hash: str) -> dict[str, Path]`:
       - Creates `<BASE_IMAGE_DIR>/<article_hash>/` (imported from config).
       - For each image file in `fixture_images_dir`, copies to the article dir.
       - Returns `{f"http://localhost:8765/{article_hash}/{name}": Path(dest_file) for ...}` —
         the url_to_path shape that `_vision_worker_impl` expects.

    4. `_ingest_text_first(rag, url, title, markdown, url_to_path, article_hash)`:
       - Synthesizes `full_content` in the shape `ingest_article` produces (line 790-820 of
         ingest_wechat.py):
         ```python
         full_content = f"# {title}\n\nURL: {url}\nTime: \n\n{markdown}"
         # localize_markdown for images
         full_content = localize_markdown(full_content, url_to_path, article_hash=article_hash)
         for i, (url_img, path) in enumerate(url_to_path.items()):
             local_url = f"http://localhost:8765/{article_hash}/{path.name}"
             full_content += f"\n\n[Image {i} Reference]: {local_url}"
         ```
       - Calls `doc_id = f"wechat_{article_hash}"`, `_register_pending_doc_id(article_hash, doc_id)`,
         `await rag.ainsert(full_content, ids=[doc_id])`, `_clear_pending_doc_id(article_hash)`.
       - Returns `(full_content, doc_id)`.

    5. `_spawn_vision_worker(rag, article_hash, url_to_path, title, filter_stats=None,
       download_input_count=0, download_failed=0) -> asyncio.Task`:
       - Simply `return asyncio.create_task(_vision_worker_impl(rag=rag, ...))`.
       - Measured with `perf_counter` from outside — `async_vision_start_ms` is the delta
         between `t_before_create_task` and `t_after_create_task`, NOT task completion.

    6. `_validate_semantic_query(rag, doc_id) -> tuple[bool, int]`:
       - `from lightrag.lightrag import QueryParam` (late import).
       - `t0 = perf_counter()`
       - `response = await rag.aquery(query="GPT-5.5 benchmark results",
          param=QueryParam(mode="hybrid", top_k=3))`
       - `elapsed_ms = int((perf_counter() - t0) * 1000)` (informational only — NOT in
         stage_timings_ms per PRD)
       - Parse response — look for `file_path` metadata matching doc_id OR substring match against
         signature fragments `["GPT-5.5", "Opus 4.7", "OpenAI"]`.
       - Return (passed: bool, elapsed_ms).

    7. Rewrite `_run_benchmark(fixture_path: Path) -> dict`:
       ```python
       async def _run_benchmark(fixture_path: Path) -> dict:
           timings: dict[str, int] = {}
           warnings: list[dict] = []
           errors: list[dict] = []
           gate_flags = {
               "text_ingest_under_2min": False,
               "aquery_returns_fixture_chunk": False,
               "zero_crashes": True,
           }

           # Stage 1: scrape (fixture read)
           with _time_stage("scrape", timings):
               fixture = _read_fixture(fixture_path)
           article_hash = _compute_article_hash(fixture["url"])

           # Balance precheck (not in stage_timings_ms — emits warning only)
           warnings.append(_balance_precheck())

           # Late import — avoid LightRAG init on --help
           from ingest_wechat import get_rag, _vision_worker_impl
           from image_pipeline import localize_markdown

           rag = await get_rag(flush=True)

           vision_task: "asyncio.Task | None" = None
           doc_id = f"wechat_{article_hash}"
           try:
               # Stage 2: classify
               with _time_stage("classify", timings):
                   classify_result, _elapsed = _classify_with_deepseek(
                       fixture["title"], fixture["markdown"]
                   )
                   if classify_result is None:
                       warnings.append({"event": "classify_skipped", "reason": "deepseek_unavailable_or_failed"})

               # Stage 3: image_download (copy from fixture)
               with _time_stage("image_download", timings):
                   url_to_path = _copy_fixture_images(
                       fixture_path / "images", article_hash
                   )

               # Stage 4: text_ingest (THE gate measurement)
               with _time_stage("text_ingest", timings):
                   full_content, doc_id = await _ingest_text_first(
                       rag, fixture["url"], fixture["title"],
                       fixture["markdown"], url_to_path, article_hash
                   )
               gate_flags["text_ingest_under_2min"] = timings["text_ingest"] < 120000

               # Stage 5: async_vision_start (spawn the background worker)
               with _time_stage("async_vision_start", timings):
                   vision_task = asyncio.create_task(
                       _vision_worker_impl(
                           rag=rag,
                           article_hash=article_hash,
                           url_to_path=url_to_path,
                           title=fixture["title"],
                           filter_stats=None,  # no filter stage in bench — fixture pre-filtered
                           download_input_count=len(url_to_path),
                           download_failed=0,
                       )
                   )

               # aquery validation (POST ingest, NOT in stage_timings_ms)
               passed, _q_elapsed = await _validate_semantic_query(rag, doc_id)
               gate_flags["aquery_returns_fixture_chunk"] = passed

           except Exception as exc:
               gate_flags["zero_crashes"] = False
               errors.append({
                   "type": exc.__class__.__name__,
                   "message": str(exc),
                   "stage": "benchmark_run",
               })
               logger.exception("Benchmark run failed")
           finally:
               # Drain the Vision task: gives worker a chance to complete so sub-doc lands.
               # 120s cap (matches D-10.09). On timeout, cancel (does NOT fail gate — Vision
               # failure is D-10.08 non-fatal).
               if vision_task is not None:
                   try:
                       await asyncio.wait_for(vision_task, timeout=120)
                   except asyncio.TimeoutError:
                       vision_task.cancel()
                       try:
                           await vision_task
                       except (asyncio.CancelledError, Exception):
                           pass
                       warnings.append({"event": "vision_worker_drain_timeout", "timeout_s": 120})
                   except Exception as vexc:
                       warnings.append({
                           "event": "vision_worker_exception",
                           "error": f"{vexc.__class__.__name__}: {vexc}",
                       })

               # Finalize storages so any deferred vdb/graphml writes land on disk
               try:
                   await rag.finalize_storages()
               except Exception as fexc:
                   warnings.append({"event": "finalize_storages_failed", "error": str(fexc)})

           # Build counters
           counters = {
               "images_input": fixture.get("total_images_raw", 0),
               "images_kept": fixture.get("images_after_filter", 0),
               "images_filtered": fixture.get("total_images_raw", 0) - fixture.get("images_after_filter", 0),
               "chunks_extracted": max(1, len(fixture["markdown"]) // 4800),  # heuristic per D-11.07
               "entities_ingested": -1,  # sentinel — LightRAG internal state not accessible cleanly
           }

           return _build_result_json(
               article_hash=article_hash,
               fixture_path=str(fixture_path),
               timings=timings,
               counters=counters,
               gate_flags=gate_flags,
               warnings=warnings,
               errors=errors,
           )
       ```

    8. Update `main(argv=None)`:
       - Wrap `asyncio.run(_run_benchmark(...))` in an outer try/except Exception to catch
         anything that somehow escapes the inner handler (fixture-read failure, etc.).
       - On outer exception: build a minimal result dict with `gate_pass=false`,
         `errors=[{"type": ..., "message": ...}]`, write it, return 1.
       - Otherwise: write the result dict, return `0 if result["gate_pass"] else 1`.

    Create `tests/integration/test_bench_integration.py`:
    - (mkdir tests/integration/ + touch __init__.py if missing)
    - Tests 1-5 use mocked rag (`AsyncMock()` with `.ainsert`, `.aquery`, `.finalize_storages`
      as AsyncMocks).
    - Mock `get_rag` via `monkeypatch.setattr("scripts.bench_ingest_fixture.<late_import_target>", ...)`
      — since `get_rag` is imported inside `_run_benchmark`, the monkeypatch path must match
      where `from ingest_wechat import get_rag` lands. Recommended: monkeypatch
      `ingest_wechat.get_rag` directly (returns the mock rag AsyncMock).
    - Mock `_call_deepseek_fullbody` via `monkeypatch.setattr("batch_classify_kol._call_deepseek_fullbody", ...)`.
    - For Test 6 (live integration):
      ```python
      @pytest.mark.integration
      @pytest.mark.skipif(
          not os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") == "dummy",
          reason="requires real DEEPSEEK_API_KEY",
      )
      def test_live_gate_run(tmp_path, monkeypatch):
          # Point RAG_WORKING_DIR at tmp_path so the real KG is not polluted
          monkeypatch.setenv("RAG_WORKING_DIR", str(tmp_path / "rag"))
          # Run harness; assert gate_pass=true, text_ingest_ms<120000
          ...
      ```
      Note: if `config.py`'s `RAG_WORKING_DIR` is resolved at import time (not dynamically),
      this monkeypatch may not take effect. Planner verifies and falls back to pre-import env
      set via `pytest.ini` or conftest if needed. Alternatively skip RAG_WORKING_DIR isolation
      — running against the real working dir is acceptable for a single-article gate if the
      user accepts the data addition (benchmark_result.json records the doc_id for cleanup).

    Compliance:
    - Windows: `set DEEPSEEK_API_KEY=<real_key> && venv\Scripts\python -m pytest tests/integration/test_bench_integration.py -v -m integration`
    - Unit-style tests (tests 1-5) run with `DEEPSEEK_API_KEY=dummy` and pass without network.
    - Type hints on all helper functions.
    - `logger` for diagnostics; no `print` in harness internals; `print` only for final gate
      summary line to stdout (user-facing).
    - No secrets committed — env vars only.
    - Late imports inside `_run_benchmark` — keeps `--help` and `-v` fast.

    Implements decisions per D-11.02 (text_ingest gate), D-11.04 (aquery validation),
    D-11.06 (zero crashes).
  </action>
  <verify>
    <automated>set DEEPSEEK_API_KEY=dummy && venv\Scripts\python -m pytest tests/integration/test_bench_integration.py -x -v -m "not integration"</automated>
  </verify>
  <done>
    - `scripts/bench_ingest_fixture.py` includes real LightRAG calls (get_rag, ainsert, aquery, finalize)
    - Vision task is spawned via `asyncio.create_task(_vision_worker_impl(...))` — NOT `ingest_article`
      (harness handles the text-first flow directly per D-11.01)
    - `rag.aquery` called with exact query string `"GPT-5.5 benchmark results"` + `QueryParam(mode="hybrid", top_k=3)`
    - Vision task drained in finally block with 120s timeout
    - All 5 tests in tests/integration/test_bench_integration.py (unit-mocked) pass with DEEPSEEK_API_KEY=dummy
    - Full regression: 61 (prior) + 9 (plan 11-00) + 6 (plan 11-01) + 5 (this plan) = 81+ unit tests passing
    - Integration test (test 6) SKIPS when DEEPSEEK_API_KEY is dummy; PASSES when real key is present
      and the fixture produces `gate_pass=true` with `text_ingest_ms < 120000`
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: Manual live gate run against real fixture — close milestone v3.1</name>
  <files>test/fixtures/gpt55_article/benchmark_result.json</files>
  <what-built>
    - Full benchmark harness wired to real LightRAG (Plan 11-00 + Plan 11-01 + Plan 11-02 combined)
    - Vertex AI opt-in conditional in `lib/lightrag_embedding.py` (Plan 11-01)
    - SiliconFlow balance precheck in the harness output
    - PRD-exact JSON schema written to `test/fixtures/gpt55_article/benchmark_result.json`
  </what-built>
  <how-to-verify>
    1. Ensure the following env vars are set in `~/.hermes/.env` (or shell env):
       - `DEEPSEEK_API_KEY=<real_key>` (required)
       - `OMNIGRAPH_GEMINI_KEY=<real_key>` OR `GEMINI_API_KEY=<real_key>` (required for free-tier)
       - `GOOGLE_APPLICATION_CREDENTIALS=<path_to_sa.json>` (RECOMMENDED — unblocks <2min gate)
       - `GOOGLE_CLOUD_PROJECT=<project_id>` (required together with credentials)
       - `SILICONFLOW_API_KEY=<real_key>` (optional — enables balance_warning in output)

    2. Run the benchmark:
       ```bash
       venv\Scripts\python scripts\bench_ingest_fixture.py --fixture test\fixtures\gpt55_article\
       ```

    3. Inspect exit code: MUST be 0 for gate pass.

    4. Inspect `test/fixtures/gpt55_article/benchmark_result.json`:
       - `gate_pass: true`
       - `gate.text_ingest_under_2min: true`
       - `gate.aquery_returns_fixture_chunk: true`
       - `gate.zero_crashes: true`
       - `stage_timings_ms.text_ingest < 120000`
       - `errors: []`
       - `warnings` includes either a `balance_warning` with `status: "ok"` OR a
         `balance_precheck_skipped` if SiliconFlow key unset

    5. Inspect stdout — benchmark should print a final summary line indicating PASS/FAIL plus
       the key timings.

    6. If Vertex AI env vars were set: inspect the JSON log output during the run — NO
       "All N Gemini keys exhausted (429)" errors should appear. Text ingest completes in a
       small fraction of the 2min budget.

    7. Verify the sub-doc landed: a follow-up aquery for "image descriptions GPT-5.5" should
       return results (optional, but sanity-checks that D-10.08 Vision worker completed).

    On PASS: milestone v3.1 closes. Update ROADMAP.md Phase 11 checkbox to [x] and the
    milestone status to "COMPLETE".

    On FAIL: read the `errors` array in the JSON. Common failure modes:
      - `text_ingest_ms > 120000`: Vertex AI not active → set both env vars and retry
      - `aquery_returns_fixture_chunk: false`: inspect the actual aquery response text;
        LightRAG may have returned a generic "no knowledge" string. Verify the parent doc
        was actually ingested by running `python list_entities.py` or a direct
        `aquery(..., mode="naive")` probe.
      - `balance_precheck_failed`: SiliconFlow API changed shape OR key invalid — non-fatal
        for gate, proceed if other gate flags are green.
  </how-to-verify>
  <resume-signal>Type "approved" if gate_pass=true, or paste the benchmark_result.json contents
    and describe the failure.</resume-signal>
  <action>See <what-built> above. This is a checkpoint task: the orchestrator runs the benchmark
    command from <how-to-verify>, inspects the resulting benchmark_result.json against the gate
    criteria, and waits for <resume-signal> before concluding the phase. No code changes are
    performed in this task — it is a verification gate only.</action>
  <verify>See <how-to-verify> above — the benchmark_result.json content plus exit code 0 are the
    pass conditions. All 7 numbered steps must be green for "approved".</verify>
  <done>User types the <resume-signal> token "approved" after confirming gate_pass=true in the
    emitted JSON AND all 7 inspection steps pass. On FAIL, the user pastes the JSON and the
    orchestrator diagnoses per the failure-mode guidance in <how-to-verify>.</done>
</task>

</tasks>

<verification>
Phase-level checks for this plan:

1. `set DEEPSEEK_API_KEY=dummy && venv\Scripts\python -m pytest tests/integration/test_bench_integration.py -v -m "not integration"` → 5 unit-style tests passing
2. Full regression: `set DEEPSEEK_API_KEY=dummy && venv\Scripts\python -m pytest tests/unit/ tests/integration/ -x` → 81+ tests passing
3. Live gate run: `venv\Scripts\python scripts\bench_ingest_fixture.py` → exit 0, gate_pass=true in output JSON
4. JSON schema compliance: `python -c "import json; d=json.load(open('test/fixtures/gpt55_article/benchmark_result.json')); assert d['gate_pass'] is True; assert d['stage_timings_ms']['text_ingest'] < 120000"` → exits 0
5. Aquery literal query check: `grep -n "GPT-5.5 benchmark results" scripts/bench_ingest_fixture.py` → exact string present
6. QueryParam mode+top_k check: `grep -n "mode=.hybrid.*top_k=3" scripts/bench_ingest_fixture.py` → present
</verification>

<success_criteria>
- Harness runs end-to-end against the fixture with real LightRAG
- `stage_timings_ms.text_ingest` is measured around `rag.ainsert` only, excludes Vision worker
- `gate.aquery_returns_fixture_chunk` correctly evaluates via file_path OR signature-fragment match
- `gate.text_ingest_under_2min` correctly evaluates the 120000ms threshold
- Vision task is spawned, measured (spawn-time only), and drained in finally block
- Exit code 0 iff gate_pass=true; exit 1 otherwise
- `benchmark_result.json` written atomically with PRD-exact schema
- Milestone v3.1 closes: all 7 Phase 11 REQs delivered, 61+20 = 81+ tests green
</success_criteria>

<output>
After completion, create `.planning/phases/11-e2e-verification-gate/11-02-SUMMARY.md` following the
standard plan summary template. Include the actual `benchmark_result.json` contents from the
live gate run as evidence in the summary.
</output>
