---
phase: 11-e2e-verification-gate
plan: 00
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/bench_ingest_fixture.py
  - tests/unit/test_bench_harness.py
autonomous: true
requirements: [E2E-01, E2E-03, E2E-05, E2E-07]

must_haves:
  truths:
    - "Benchmark CLI exists at scripts/bench_ingest_fixture.py and accepts --fixture + --output args"
    - "Benchmark harness reads test/fixtures/gpt55_article/article.md + metadata.json WITHOUT making any HTTP scrape calls"
    - "Benchmark emits 5 stage timings (scrape, classify, image_download, text_ingest, async_vision_start) as ints in milliseconds"
    - "Benchmark calls SiliconFlow /v1/user/info and emits a structured balance_warning in warnings[]"
    - "benchmark_result.json is written atomically (tmp → rename) with the exact PRD schema"
    - "Missing SILICONFLOW_API_KEY does not crash the benchmark — emits balance_precheck_skipped warning"
  artifacts:
    - path: "scripts/bench_ingest_fixture.py"
      provides: "CLI entry point + harness skeleton + schema builder + balance precheck"
      min_lines: 250
    - path: "tests/unit/test_bench_harness.py"
      provides: "Unit tests for schema shape, stage timings, balance precheck branches"
      min_lines: 150
  key_links:
    - from: "scripts/bench_ingest_fixture.py"
      to: "test/fixtures/gpt55_article/"
      via: "fixture path arg + article.md + metadata.json read"
      pattern: "Path\\(.*fixture.*\\) / \"article.md\""
    - from: "scripts/bench_ingest_fixture.py"
      to: "https://api.siliconflow.cn/v1/user/info"
      via: "urllib.request.urlopen with Authorization: Bearer header"
      pattern: "siliconflow.cn/v1/user/info"
    - from: "scripts/bench_ingest_fixture.py"
      to: "benchmark_result.json"
      via: "atomic write — open(.tmp), json.dump, os.rename"
      pattern: "os\\.rename\\(.*tmp.*benchmark_result"
---

<objective>
Build the benchmark harness skeleton at `scripts/bench_ingest_fixture.py`: CLI args, fixture
reader, 5-stage timing scaffold, SiliconFlow balance precheck, exact PRD-schema JSON writer,
atomic-write pattern. The LightRAG invocation itself is stubbed in this plan (mocked in tests);
the real LightRAG run lives in Plan 11-02.

Purpose: de-risk the schema + timing + fixture-read + balance-check logic in isolation with
fast mocked unit tests BEFORE spending real DeepSeek / Gemini / SiliconFlow quota on the
integration run. Every field in the PRD JSON schema is covered by a test here.

Output: a working CLI that produces a valid `benchmark_result.json` with stubbed LightRAG
(gate_pass=false because text_ingest is a no-op stub) but a PRD-compliant schema.
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
@test/fixtures/gpt55_article/metadata.json
@ingest_wechat.py
@image_pipeline.py
@CLAUDE.md

<interfaces>
<!-- Key contracts the executor needs. Extract from codebase rather than re-deriving. -->

Fixture metadata.json shape (test/fixtures/gpt55_article/metadata.json):
```json
{
  "title": "GPT-5.5来了！全榜第一碾压Opus 4.7，OpenAI今夜雪耻",
  "url": "http://mp.weixin.qq.com/s?__biz=...",
  "text_chars": 4574,
  "total_images_raw": 39,
  "images_after_filter": 28
}
```
Fixture article.md is 119 lines of markdown. Fixture images/ has 28 pre-filtered image files.

Relevant existing imports from ingest_wechat.py (for helper reuse if needed):
- `from lib import embedding_func` — current embedding func
- `from lightrag_llm import deepseek_model_complete` — LLM
- `from image_pipeline import describe_images, emit_batch_complete, get_last_describe_stats,
  download_images, localize_markdown, filter_small_images`
- `from ingest_wechat import get_rag, _vision_worker_impl, ingest_article` (plan 11-02 uses these)

JSON log pattern from image_pipeline.py (lines 83-100 region — `emit_batch_complete` uses
`_emit_log(event, payload)` which json.dumps to stdout). Reuse this pattern for the benchmark's
own warning lines.

PRD JSON schema (EXACT — from 11-PRD.md lines 53-84):
```json
{
  "article_hash": "...",
  "fixture_path": "test/fixtures/gpt55_article/",
  "timestamp_utc": "2026-05-01T12:34:56Z",
  "stage_timings_ms": {"scrape": 50, "classify": 3200, "image_download": 12,
                       "text_ingest": 98000, "async_vision_start": 5},
  "counters": {"images_input": 28, "images_kept": 28, "images_filtered": 0,
               "chunks_extracted": 15, "entities_ingested": 50},
  "gate": {"text_ingest_under_2min": true, "aquery_returns_fixture_chunk": true,
           "zero_crashes": true},
  "gate_pass": true,
  "warnings": [{"event": "balance_warning", "provider": "siliconflow",
                "balance_cny": 5.43, "estimated_cost_cny": 0.036, "status": "ok"}],
  "errors": []
}
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Build benchmark harness skeleton with fixture reader, CLI, schema, and atomic write</name>
  <files>scripts/bench_ingest_fixture.py, tests/unit/test_bench_harness.py</files>
  <behavior>
    Test 1 — CLI arg parsing:
      - Running `python scripts/bench_ingest_fixture.py --fixture <path> --output <path>` parses
        both args; defaults are `test/fixtures/gpt55_article/` and
        `test/fixtures/gpt55_article/benchmark_result.json`.

    Test 2 — Fixture read:
      - `_read_fixture(fixture_path)` returns a dict with keys `title`, `url`, `markdown`,
        `image_paths`, `text_chars`, `total_images_raw`, `images_after_filter`.
      - `markdown` is the article.md contents as str.
      - `image_paths` is a list[Path] to each file in `<fixture>/images/`.
      - No network calls issued (mock `urllib.request.urlopen` and `requests.get` — assert never called).

    Test 3 — Article hash computation:
      - `_compute_article_hash(url)` returns md5(url.encode())[:10] — matches ingest_wechat:689 shape.

    Test 4 — Schema builder:
      - `_build_result_json(article_hash, fixture_path, timings, counters, gate_flags,
        warnings, errors)` returns a dict EXACTLY matching PRD schema.
      - `timestamp_utc` ISO 8601 with "Z" suffix (e.g. "2026-05-01T12:34:56Z"; no `+00:00`).
      - `gate_pass` computed as `all(gate_flags.values())`.
      - All 5 stage_timings_ms keys present.
      - All 5 counters keys present.
      - All 3 gate keys present.

    Test 5 — Atomic write:
      - `_write_result(path, result_dict)` writes `<path>.tmp` first, then os.rename to `<path>`.
      - On mid-write exception, `<path>.tmp` is cleaned up AND `<path>` is NOT modified.

    Test 6 — Exit code:
      - `main()` returns 0 iff `gate_pass is True` in the result dict.
      - Returns 1 otherwise (includes the stub-mode "text_ingest was not actually run" path).
  </behavior>
  <action>
    Create `scripts/bench_ingest_fixture.py`:

    1. Imports: `argparse`, `hashlib`, `json`, `logging`, `os`, `sys`, `time`, `urllib.request`,
       `urllib.error`, `asyncio` (for later plans), `datetime.datetime/timezone`, `pathlib.Path`.
       Add `logger = logging.getLogger(__name__)` at module top.

    2. Constants (module level):
       - `DEFAULT_FIXTURE = Path("test/fixtures/gpt55_article")`
       - `DEFAULT_OUTPUT = DEFAULT_FIXTURE / "benchmark_result.json"`
       - `ESTIMATED_COST_CNY = 0.036`  # PRD-specified single-article estimate
       - `SILICONFLOW_URL = "https://api.siliconflow.cn/v1/user/info"`
       - `BALANCE_TIMEOUT_S = 10.0`

    3. Helper functions (pure — all unit-testable):
       - `_read_fixture(fixture_path: Path) -> dict`: reads `article.md`, `metadata.json`,
         lists `images/*`. Returns dict.
       - `_compute_article_hash(url: str) -> str`: returns `hashlib.md5(url.encode()).hexdigest()[:10]`.
       - `_utc_now_iso() -> str`: returns `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")`.
       - `_build_result_json(article_hash, fixture_path, timings, counters, gate_flags,
         warnings, errors) -> dict`: assembles the exact PRD schema.
         gate_pass = `all(gate_flags.values())`.
       - `_write_result(path: Path, result: dict) -> None`: writes to `path.with_suffix('.json.tmp')`,
         os.rename to `path`. Wrap in try/except — on error, unlink tmp if exists.

    4. Balance precheck (D-11.05):
       - `_balance_precheck() -> dict`: reads `SILICONFLOW_API_KEY` env var; if unset, returns
         `{"event": "balance_precheck_skipped", "provider": "siliconflow", "reason": "api_key_unset"}`.
       - Else: `urllib.request.Request` with Authorization header, `urlopen(..., timeout=10)`.
       - On success: parse `json.loads(resp.read())`, extract balance from
         `data.get("data", {}).get("balance", 0)` (field path may vary — check response shape;
         add TODO comment if live response differs).
       - On success with balance >= ESTIMATED_COST_CNY: return
         `{"event": "balance_warning", "provider": "siliconflow", "balance_cny": balance,
           "estimated_cost_cny": 0.036, "status": "ok"}`.
       - On success with balance < ESTIMATED_COST_CNY: same shape but `"status": "insufficient_for_batch"`.
       - On exception (timeout, HTTPError, JSONDecodeError): return
         `{"event": "balance_precheck_failed", "provider": "siliconflow", "error": str(exc)}`.

    5. Stage timing scaffold:
       - Use a context manager or simple `perf_counter` wrap pattern. Suggested:
         ```python
         def _time_stage(name: str, timings: dict):
             class _Ctx:
                 def __enter__(self): self.t0 = time.perf_counter(); return self
                 def __exit__(self, *a): timings[name] = int((time.perf_counter() - self.t0) * 1000)
             return _Ctx()
         ```
       - Scaffold the 5 stages in a `_run_benchmark(fixture_path: Path) -> dict` async function
         but make the inner work a stub — either a no-op or `asyncio.sleep(0)`. Real LightRAG
         call is Plan 11-02.
       - Example:
         ```python
         timings = {}
         with _time_stage("scrape", timings):
             fixture = _read_fixture(fixture_path)
         with _time_stage("classify", timings):
             pass  # STUB — Plan 11-02 calls DeepSeek classifier
         # ... etc for image_download, text_ingest, async_vision_start
         ```

    6. `main()` function:
       - Parse args.
       - Call `asyncio.run(_run_benchmark(args.fixture))` wrapping in try/except.
       - Build result dict via `_build_result_json(...)`.
       - Write atomically.
       - Return 0 if `result["gate_pass"]` else 1.

    7. `if __name__ == "__main__": sys.exit(main())` at bottom.

    Create `tests/unit/test_bench_harness.py`:

    1. pytest + pytest-asyncio as appropriate (most tests are sync here — harness skeleton is sync helpers).
    2. Fixtures: `tmp_path` for each test that writes JSON; synthetic minimal fixture dir
       (create `article.md`, `metadata.json`, `images/img_000.jpg` with a blank/tiny file).
    3. Test 1: invoke `main()` via `subprocess.run([sys.executable, "scripts/bench_ingest_fixture.py",
       "--fixture", str(tmp_fixture), "--output", str(tmp_out)])` OR directly via
       `from scripts.bench_ingest_fixture import main; main(["--fixture", ...])` if main accepts argv.
       Recommend the latter — add `def main(argv=None): args = parser.parse_args(argv); ...`.
       Assert exit returns 1 (stub mode → gate_pass=false) AND `benchmark_result.json` exists
       AND is valid JSON matching PRD shape.
    4. Test 2: `_read_fixture(synthetic_fixture)` returns expected dict; mock urllib/requests globally
       and assert NOT called.
    5. Test 3: `_compute_article_hash("http://test.example/foo")` returns 10-char hex string.
    6. Test 4: Call `_build_result_json(...)` with hand-crafted inputs, assert every key matches
       PRD shape. Assert `gate_pass=True` iff all gate_flags values are True. Use
       `datetime.fromisoformat(result["timestamp_utc"].replace("Z", "+00:00"))` to verify the
       timestamp is round-trippable.
    7. Test 5: `_write_result(tmp_path / "out.json", {"a": 1})` → assert file exists with content;
       assert `tmp_path / "out.json.tmp"` does NOT exist after success.
    8. Test 6 (balance — 4 sub-tests):
       - (a) env var unset → `_balance_precheck()` returns `event="balance_precheck_skipped"`.
       - (b) monkeypatch `urllib.request.urlopen` to return a MagicMock with `.read()` →
         `json.dumps({"data": {"balance": 5.43}}).encode()` → assert `balance_cny=5.43`,
         `status="ok"`.
       - (c) same but balance=0.001 → `status="insufficient_for_batch"`.
       - (d) urlopen raises `urllib.error.URLError("boom")` → `event="balance_precheck_failed"`,
         `error` contains "boom".

    Compliance:
    - Windows paths via `pathlib.Path` (no hardcoded forward slashes in string concatenation).
    - Use `logging.getLogger(__name__)` for diagnostics; `print()` only for CLI user-facing output
      (per CLAUDE.md convention).
    - Type hints on ALL function signatures (rules/python/coding-style.md).
    - Secrets via env vars only (rules/python/security.md).
    - `DEEPSEEK_API_KEY=dummy` in pytest env for tests that transitively import ingest modules.
    - Helper functions are pure / side-effect-scoped — makes mocking unnecessary in most tests.

    Implements decisions per D-11.01 (CLI + fixture read), D-11.03 (5 stage timings),
    D-11.05 (balance precheck), D-11.07 (exact JSON schema).
  </action>
  <verify>
    <automated>set DEEPSEEK_API_KEY=dummy && venv\Scripts\python -m pytest tests/unit/test_bench_harness.py -x -v</automated>
  </verify>
  <done>
    - `scripts/bench_ingest_fixture.py` exists, runs standalone with `--help` showing `--fixture` and `--output` args
    - `tests/unit/test_bench_harness.py` has ≥ 9 tests, all passing
    - Running the script against the real fixture produces a syntactically-valid JSON file with
      all required PRD keys (even if `gate_pass=false` due to stubbed text_ingest)
    - Zero regressions — all 61 prior unit tests still green
    - No `requests` import added solely for balance precheck (uses stdlib `urllib`)
  </done>
</task>

</tasks>

<verification>
Phase-level checks for this plan:

1. `python scripts/bench_ingest_fixture.py --help` prints usage with `--fixture` and `--output`
2. `python scripts/bench_ingest_fixture.py --fixture test/fixtures/gpt55_article/ --output /tmp/out.json`
   exits cleanly (exit 1 is ACCEPTABLE here — stub text_ingest → gate_pass=false). The JSON MUST exist and parse.
3. `python -c "import json; d=json.load(open('/tmp/out.json')); assert set(d.keys()) == {'article_hash','fixture_path','timestamp_utc','stage_timings_ms','counters','gate','gate_pass','warnings','errors'}"`
4. `set DEEPSEEK_API_KEY=dummy && venv\Scripts\python -m pytest tests/unit/test_bench_harness.py -v` → 9+ tests passing
5. `set DEEPSEEK_API_KEY=dummy && venv\Scripts\python -m pytest tests/unit/ -x` → 61+9 = 70+ tests passing, zero regressions
</verification>

<success_criteria>
- CLI entry point exists and is importable as a module (for unit testing `main(argv=None)` pattern)
- Fixture reader produces a clean dict from `article.md` + `metadata.json` + `images/` WITHOUT network I/O
- Stage timing scaffold produces all 5 stage keys with int millisecond values
- Balance precheck handles all 4 branches (missing key, ok, insufficient, failed)
- JSON writer is atomic (tmp → rename) and produces PRD-exact schema
- Zero prior-test regressions (61 tests remain green)
</success_criteria>

<output>
After completion, create `.planning/phases/11-e2e-verification-gate/11-00-SUMMARY.md` following the
standard plan summary template.
</output>
