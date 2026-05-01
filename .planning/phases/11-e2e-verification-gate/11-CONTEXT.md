# Phase 11 — Context (locked decisions derived from 11-PRD.md)

**Mode:** PRD express path — discuss-phase skipped per user request.
**Derived from:** `11-PRD.md` (single source of truth for acceptance criteria).
**Date:** 2026-04-29.
**Milestone:** v3.1 Single-Article Ingest Stability — FINAL GATE.

This document codifies the 7 PRD requirements as **locked decisions** (D-11.XX) that plans MUST
reference. Each requirement in the PRD maps 1:1 to a decision below — no interpretation, no
judgment, just a direct restatement for traceability, plus one tactical enabler decision
(D-11.08) that unblocks the E2E-02 <2min gate.

---

## Canonical Refs (MANDATORY)

All plans MUST cross-reference these files when implementing decisions:

| Ref                                                                  | Purpose                                                                   |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `.planning/phases/11-e2e-verification-gate/11-PRD.md`                | Primary source — acceptance criteria + exact JSON schema                  |
| `.planning/REQUIREMENTS.md` (E2E-01..07)                             | Milestone v3.1 traceability matrix                                        |
| `.planning/ROADMAP.md` (Phase 11 entry)                              | Phase-level observable truths                                             |
| `.planning/phases/10-classification-and-ingest-decoupling/10-CONTEXT.md` | Dependency — D-10.05 ingest_article returns `Task \| None` + D-10.09 drain |
| `.planning/phases/10-classification-and-ingest-decoupling/10-02-SUMMARY.md` | Post-Phase-10 state: Vision worker, 61 unit tests green                   |
| `ingest_wechat.py` (lines 667-922: `ingest_article`; 200-274: `_vision_worker_impl`) | ARCH-01/02 integration points — already text-first returning Task     |
| `batch_ingest_from_spider.py` (lines 83-131: `_drain_pending_vision_tasks`) | D-10.09 drain pattern — benchmark may reuse or explicitly await instead  |
| `lib/lightrag_embedding.py` (lines 148-171: `_embed_once`)           | Vertex AI conditional insertion point (D-11.08); currently hardcoded `vertexai=False` |
| `lib/models.py` (EMBEDDING_MODEL constant)                           | Model name resolution — needs `-preview` variant for Vertex AI mode        |
| `image_pipeline.py` (lines 371+: `describe_images`; 83: `emit_batch_complete`) | Structured JSON log format — benchmark reuses `_emit_log` pattern     |
| `test/fixtures/gpt55_article/` — `article.md` + `metadata.json` + `images/` | THE fixture — 39 raw images, 28 after filter, 4574 text chars             |
| `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/vertex_ai_smoke_validated.md` | SA JSON validated + `gemini-embedding-2-preview` discovered for Vertex  |
| `tests/unit/test_lightrag_embedding.py` (fixture patterns + _reset_api_keys_state) | Test pattern template for D-11.08 Vertex conditional tests               |

---

## Locked Decisions

### D-11.01 — Local CLI reads fixture from disk (E2E-01)

- **Decision:** NEW script at `scripts/bench_ingest_fixture.py` accepts a fixture path
  (default `test/fixtures/gpt55_article/`) via `--fixture` CLI arg and runs the full ingest
  pipeline WITHOUT WeChat network scrape. Reads `article.md` + `metadata.json` directly from
  disk; images are already present in `images/` subdir of the fixture.
- **Entry point:** `python scripts/bench_ingest_fixture.py [--fixture <path>] [--output <json_path>]`
- **Implementation constraint:** The script MUST NOT call `scrape_wechat_ua`, `scrape_wechat_apify`,
  or any other scraping path. It reads the fixture, synthesizes the same markdown/metadata shape
  that `ingest_article` produces POST-scrape, and feeds it into a helper that wraps the text-first
  ingest flow (parent `rag.ainsert` + Vision worker spawn).
- **Fixture read contract:** `article.md` contents are the full markdown body; `metadata.json`
  provides `title`, `url`, `text_chars`, `total_images_raw`, `images_after_filter`. Image files
  are read from `<fixture>/images/*.{jpg,png}` directly — no HTTP download stage (copy or
  path-reference into the runtime image dir).
- **Helper extraction:** Planner MAY extract an `_ingest_from_text(rag, url, title, markdown,
  image_paths)` helper from `ingest_wechat.ingest_article` body to share the ainsert + Vision
  worker spawn logic with the benchmark harness. Alternatively, the harness may call a smaller
  helper `_do_text_ingest(rag, full_content, doc_id)` and do the image wiring inline for clarity.
  Planner picks — recommend inline for clarity since this is test/bench-only code.
- **Plan:** 11-00.
- **Verification:** unit test — harness runs end-to-end against the fixture with a mocked
  `rag` (MagicMock with AsyncMock.ainsert) and asserts: (1) no network I/O attempted, (2)
  `rag.ainsert` called at least once with `full_content` containing title + article.md body,
  (3) Vision worker task returned from harness, (4) JSON output written with all required fields.

### D-11.02 — Text ingest <120000 ms gate (E2E-02)

- **Decision:** Measured from the moment the script starts the `ingest_article`-equivalent
  call to the moment `rag.ainsert(full_content, ids=[doc_id])` returns. Does NOT include async
  Vision worker completion. Script fails loud (exit 1 + `gate_pass: false`) if `text_ingest_ms`
  > 120000. Gate threshold is `text_ingest_under_2min: true` when `text_ingest_ms < 120000`.
- **Measurement pattern:** wrap the parent ainsert in `t0 = time.perf_counter()` / `t1 =
  time.perf_counter()` and report `int((t1 - t0) * 1000)` as `stage_timings_ms.text_ingest`.
  Use `time.perf_counter` (monotonic, sub-ms resolution) — NOT `time.time()`.
- **Gate evaluation:** after all stages complete, compute `gate_pass = gate.text_ingest_under_2min
  AND gate.aquery_returns_fixture_chunk AND gate.zero_crashes`. Exit code 0 on `gate_pass=true`,
  exit code 1 otherwise.
- **Plan:** 11-02.
- **Verification:** integration run against real LightRAG + real DeepSeek + real embedding
  (either Gemini free tier rate-limited OR Vertex AI if D-11.08 env active) — passing requires
  `text_ingest_ms < 120000` AND `gate_pass: true` in the output JSON. This REQ is the final
  milestone gate.

### D-11.03 — Five stage timings (E2E-03)

- **Decision:** Benchmark harness emits exactly these 5 stage timings in `stage_timings_ms`:
  - `scrape` — fixture read + metadata parse (expected <100ms; just file I/O + json.load)
  - `classify` — DeepSeek classifier call on full article body (expected 2-5s)
  - `image_download` — copy/link fixture images into runtime `article_dir` (expected <100ms;
    pure local file copy, no HTTP)
  - `text_ingest` — `rag.ainsert(full_content, ids=[doc_id])` duration (THE gate measurement)
  - `async_vision_start` — time to spawn the background Vision task via `asyncio.create_task`
    (expected <10ms — just task creation, not execution)
- **Measurement discipline:** each stage has its own `perf_counter()` delimiters. Stages run
  sequentially; timings are EXCLUSIVE (scrape_ms does not include classify_ms, etc.).
- **Annotation:** `async_vision_start` explicitly is NOT the Vision worker's full duration
  (which depends on external Vision API latency and may exceed the gate budget). It is the
  time-to-spawn only. The Vision worker's `total_ms` (including describe) arrives
  asynchronously in the `emit_batch_complete` log line, separately from the gate measurement.
- **Plan:** 11-00 builds the timing infra; 11-02 runs it.
- **Verification:** unit test — harness invoked with mocked stages that each sleep a known
  amount (10ms, 50ms, 20ms, 100ms, 1ms) — asserts that emitted JSON's `stage_timings_ms` has
  all 5 keys with int values roughly matching the mocks (±5ms tolerance).

### D-11.04 — Semantic aquery validation (E2E-04)

- **Decision:** After text ingest returns, the benchmark calls EXACTLY:
  ```python
  response = await rag.aquery(
      query="GPT-5.5 benchmark results",
      param=QueryParam(mode="hybrid", top_k=3),
  )
  ```
  The query string is LITERAL: `"GPT-5.5 benchmark results"`. No variations. No prompting
  tweaks. Mode=`hybrid`. top_k=3.
- **Pass criteria:** parse `response` and assert at least 1 of the following:
  - LightRAG's response object exposes chunk metadata with a `file_path` field matching the
    ingested doc_id (`f"wechat_{article_hash}"`), OR
  - The response text contains signature fragments from the fixture article (planner picks 2-3
    — suggest `"GPT-5.5"`, `"Opus 4.7"`, `"OpenAI"` all appearing in the fixture title and body)
- **Gate field:** `gate.aquery_returns_fixture_chunk: true` when pass criteria met.
- **Fallback:** if LightRAG `aquery` response format doesn't surface `file_path` directly
  (it's an embedding in the query result), planner falls back to substring matching against
  the response text. This is a practical accommodation — the PRD says "OR chunk text contains
  signature fragments".
- **Plan:** 11-02.
- **Verification:** integration test — after bench runs against fixture, the emitted JSON's
  `gate.aquery_returns_fixture_chunk` MUST be `true`. A negative-control sanity test (optional):
  query for unrelated content (`"elephant migration patterns"`) and verify it does NOT
  falsely match the fixture signature fragments.

### D-11.05 — SiliconFlow balance precheck (E2E-05)

- **Decision:** Benchmark calls `GET https://api.siliconflow.cn/v1/user/info` with
  `Authorization: Bearer $SILICONFLOW_API_KEY`. Parses JSON response for `data.balance` (or
  similar — planner confirms actual field from the live response). If balance < estimated cost
  (hardcoded `0.036` CNY for single article per PRD), emits structured warning with
  `status: "insufficient_for_batch"`. Otherwise `status: "ok"`.
- **Structured warning shape:** appended to `warnings[]` in the output JSON (exact PRD shape):
  ```json
  {"event": "balance_warning", "provider": "siliconflow", "balance_cny": <float>, "estimated_cost_cny": 0.036, "status": "ok" | "insufficient_for_batch"}
  ```
- **Non-fatal for v3.1 gate:** even `insufficient_for_batch` status does NOT fail the gate for
  single-article ingest. The warning is informational — future batch invocations (v3.2) may
  elevate it to fatal.
- **HTTP client:** use stdlib `urllib.request` + `json` (already a project convention for tiny
  API calls). If `requests` is in scope from other imports (via image_pipeline), planner MAY
  reuse it. Do NOT add a new `import requests` solely for this call.
- **Missing API key handling:** if `SILICONFLOW_API_KEY` env var is unset, emit a different
  warning: `{"event": "balance_precheck_skipped", "provider": "siliconflow", "reason":
  "api_key_unset"}`. Still non-fatal.
- **Timeout:** HTTP call timeout 10s; on timeout or 4xx/5xx response, emit warning
  `{"event": "balance_precheck_failed", "provider": "siliconflow", "error": "<exception_str>"}`.
  Still non-fatal.
- **Plan:** 11-00.
- **Verification:** unit test — patch `urllib.request.urlopen` to return a fake JSON blob with
  `balance=5.43`; assert emitted warning has `balance_cny=5.43`, `status="ok"`. Second test:
  patch to return `balance=0.001`; assert `status="insufficient_for_batch"`. Third test: patch
  to raise on urlopen; assert `event=balance_precheck_failed`. Fourth test: unset env var;
  assert `event=balance_precheck_skipped`.

### D-11.06 — Zero crashes (E2E-06)

- **Decision:** From `if __name__ == "__main__"` through final exit, NO unhandled exception may
  propagate. The script's top-level body is wrapped in `try: asyncio.run(main()) except
  Exception as exc: <record to errors[]>`. On any unhandled exception, the script still writes
  `benchmark_result.json` with `gate_pass: false`, `errors: [{"type": ..., "message": ...}]`,
  and exits 1.
- **Graceful degradation:** individual stage failures (classify timeout, image copy error,
  balance precheck failure) append to `errors[]` but do NOT halt subsequent stages IF the stage
  boundary is survivable. Unsurvivable failures (fixture not found, `rag.ainsert` raises
  unrecoverably) halt with exit 1 and gate_pass=false.
- **Gate field:** `gate.zero_crashes: true` iff `errors` array is empty at write time.
- **Plan:** 11-02.
- **Verification:** integration test — delete the fixture dir temporarily, run harness, assert
  JSON is written with `gate_pass: false`, `errors` non-empty, exit code 1. Second test:
  happy-path fixture run → `errors: []`, `gate.zero_crashes: true`.

### D-11.07 — benchmark_result.json exact schema (E2E-07)

- **Decision:** Output written to `test/fixtures/gpt55_article/benchmark_result.json` (overwrites
  prior run). The schema is EXACTLY the PRD-specified shape, reproduced here verbatim:
  ```json
  {
    "article_hash": "<str — md5(url)[:10]>",
    "fixture_path": "test/fixtures/gpt55_article/",
    "timestamp_utc": "<ISO 8601 Z>",
    "stage_timings_ms": {
      "scrape": <int>,
      "classify": <int>,
      "image_download": <int>,
      "text_ingest": <int>,
      "async_vision_start": <int>
    },
    "counters": {
      "images_input": <int>,
      "images_kept": <int>,
      "images_filtered": <int>,
      "chunks_extracted": <int>,
      "entities_ingested": <int>
    },
    "gate": {
      "text_ingest_under_2min": <bool>,
      "aquery_returns_fixture_chunk": <bool>,
      "zero_crashes": <bool>
    },
    "gate_pass": <bool>,
    "warnings": [<warning objs>],
    "errors": [<error objs>]
  }
  ```
- **Field sources:**
  - `article_hash`: md5 of the fixture URL truncated to 10 chars (matches `ingest_wechat` hash shape)
  - `fixture_path`: relative path string (not absolute); planner uses `"test/fixtures/gpt55_article/"` literal or `args.fixture` as-passed
  - `timestamp_utc`: `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")`
  - `counters.images_input`: from `metadata.json.total_images_raw` OR live count of image files
  - `counters.images_kept`: from `metadata.json.images_after_filter` OR post-filter count
  - `counters.images_filtered`: `images_input - images_kept`
  - `counters.chunks_extracted`: planner extracts from LightRAG state after ainsert OR computes
    from `len(full_content) // _CHUNK_SIZE_CHARS`. Exact source planner decides —
    suggest post-ainsert reading `rag.chunks_vdb.client_storage` size delta if accessible,
    else chunk-count heuristic. Annotate in the code which method is used.
  - `counters.entities_ingested`: similar — planner queries LightRAG graph state post-ainsert
    or uses the same chunk-count-based estimate. If neither is clean, emit `-1` sentinel and
    log a warning (not a gate blocker per PRD — counters are informational).
- **Atomic write:** write to `<path>.tmp` then `os.rename`. Matches project convention for
  `canonical_map.json` and test fixtures.
- **Plan:** 11-00 defines the schema builder; 11-02 populates it with live-run data.
- **Verification:** unit test — harness with mocked stages emits JSON; `json.loads` it,
  `jsonschema.validate` or manual `assert` on every key + type matches the PRD shape exactly.

### D-11.08 — Vertex AI opt-in conditional in `lib/lightrag_embedding.py` (tactical enabler — NOT in REQUIREMENTS.md)

- **Decision:** Add a tiny env-triggered conditional to `_embed_once` (and related model-name
  resolution) in `lib/lightrag_embedding.py`. When BOTH `GOOGLE_APPLICATION_CREDENTIALS` AND
  `GOOGLE_CLOUD_PROJECT` env vars are set, `genai.Client` is constructed in Vertex AI mode and
  the embedding model name gets the `-preview` suffix.
- **Why this is a Phase 11 decision and not a v3.3 migration:**
  - Free-tier Gemini = 2000 RPD total / 2 keys → mathematically inadequate for ~1800 embed calls
    per heavy article within the <2min gate (RPM ceiling: 200 embeds/min → 9min for 1800 embeds)
  - Without this, E2E-02 gate cannot pass on local dev machine
  - Change is SURGICAL: ~8-12 lines conditional; default path (no env vars set) IS the current
    free-tier behavior. Production deployments unchanged. v3.3 will do the REAL migration.
- **Implementation sketch (PRD-provided):**
  ```python
  _USE_VERTEX = bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")) and bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))

  def _make_client(api_key: str) -> genai.Client:
      if _USE_VERTEX:
          return genai.Client(
              vertexai=True,
              project=os.environ["GOOGLE_CLOUD_PROJECT"],
              location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
          )
      return genai.Client(api_key=api_key, vertexai=False)

  def _resolve_model(base_model: str) -> str:
      if _USE_VERTEX and base_model == "gemini-embedding-2":
          return "gemini-embedding-2-preview"
      return base_model
  ```
  - `_USE_VERTEX` MUST be evaluated AT CALL TIME (not import time) so tests can monkeypatch
    env vars and see the behavior change. Move to a function `_is_vertex_mode() -> bool` if needed.
- **Scope discipline:**
  - MUST NOT: change any other file in `lib/`, change `EMBEDDING_MODEL` constant, alter rotation
    logic, change dimensionality, modify the `@wrap_embedding_func_with_attrs` decorator
  - MUST: preserve all 14 existing `test_lightrag_embedding.py` + 2 `test_lightrag_embedding_rotation.py`
    tests (16 total — all currently green)
- **Model name finding (from memory `vertex_ai_smoke_validated.md`):** Vertex AI uses
  `gemini-embedding-2-preview` (NOT `gemini-embedding-2` — 404 NOT_FOUND without the suffix).
  This is empirically validated; do NOT deviate.
- **Rotation interaction:** When `_USE_VERTEX` is True, API key rotation via `current_embedding_key()`
  / `rotate_embedding_key()` becomes no-op-ish (Vertex uses SA JSON, not API keys). Planner decides:
  either (a) skip rotation entirely when `_USE_VERTEX` (cleaner) or (b) keep rotation for
  `_ROTATION_HITS` telemetry even though the Vertex client ignores the API key (simpler). Recommend
  (a) — add `if _USE_VERTEX: return vec` short-circuit before the rotation call, so rotation is a
  no-op in Vertex mode. Document in code comment.
- **Plan:** 11-01.
- **Verification:** 3+ unit tests:
  1. No env vars set → `genai.Client` called with `vertexai=False, api_key=<current_key>` AND
     model is `gemini-embedding-2` (current behavior, 0 regressions).
  2. Both env vars set → `genai.Client` called with `vertexai=True, project=<env>, location=<env or us-central1>`
     AND model is `gemini-embedding-2-preview`.
  3. Only `GOOGLE_APPLICATION_CREDENTIALS` set (no `GOOGLE_CLOUD_PROJECT`) → falls back to
     free-tier path (both required; either alone is insufficient).
  4. All 16 existing embedding tests still green (22 Phase 8 + 12 Phase 9 + 27 Phase 10 = 61
     cumulative regression passing).

---

## Out of Scope (defer to later phases)

Per PRD § "Out of Scope":

- Running the benchmark against WeChat remote scrape (fixture is the ONLY path)
- Batch-scale benchmarking (multiple articles) — single article only
- Vertex AI production migration (v3.3 — this phase only adds the opt-in conditional)
- Automated Hermes deployment of benchmark results (v3.2+)
- Benchmark CI integration (v3.2 regression fixtures)
- Circuit-breaker / checkpoint-resume for Vision cascade (v3.2)

---

## Deferred Ideas (for future phases — DO NOT implement in Phase 11 plans)

- Multi-fixture benchmark matrix (text-heavy / image-heavy / mixed) — v3.2 regression fixtures
- Benchmark CI integration (pytest marker + GitHub Action) — v3.2
- Vertex AI migration of all LLM calls (not just embeddings) — v3.3
- Per-article cost tracking in the benchmark result JSON — v3.2
- GCP project isolation between embedding and LLM calls — v3.3
- Replacing `print()` calls in `ingest_wechat.py` with `logger` (noted in CLAUDE.md as existing
  tech debt; NOT blocking the gate)

---

## Claude's Discretion

Decisions intentionally left to the planner/implementer:

1. **Helper extraction strategy (D-11.01):** extract `_ingest_from_text(rag, url, title,
   markdown, image_paths)` from `ingest_wechat.ingest_article` OR implement the text-first
   ingest directly in the harness. Recommend inline in harness — test/bench-only code, no need
   to perturb production module.
2. **`chunks_extracted` / `entities_ingested` counter source (D-11.07):** read from LightRAG
   internal state post-ainsert (preferred if accessible) OR use chunk-count heuristic (fallback)
   OR emit `-1` sentinel. Planner picks and documents in code.
3. **`aquery` pass criteria fallback (D-11.04):** if `file_path` metadata not directly on
   response object, use substring matching against response text. Planner picks 2-3 signature
   fragments from the fixture article.
4. **Vertex AI rotation behavior (D-11.08):** short-circuit rotation when `_USE_VERTEX` is True
   (recommended) OR keep rotation as no-op for telemetry. Planner picks, documents in code.
5. **Output path (D-11.07):** `test/fixtures/gpt55_article/benchmark_result.json` (alongside
   the fixture — recommended) OR `benchmark_results/<timestamp>.json` (historical archive).
   Recommend the former — PRD allows either, alongside fixture is cleaner for v3.1 gate and
   easier for CI to regress against.
6. **Test file organization:** single `tests/unit/test_bench_harness.py` for all 11-00 unit
   tests OR split into `test_bench_schema.py` + `test_balance_precheck.py` + `test_stage_timings.py`.
   Planner picks — recommend single file for Phase 11 since total test count is modest (~10).
7. **Vertex AI integration test (D-11.08):** pure mock-based unit tests (fast, CI-safe) —
   planner does NOT need live Vertex AI invocation as part of Phase 11 tests (that burns SA
   credits unnecessarily; smoke-validation already done per memory).

---

## Success Criteria Reference

All 7 success criteria from `11-PRD.md` § "Success Criteria for Phase 11" are inherited verbatim:

1. `scripts/bench_ingest_fixture.py` exists and runs against `test/fixtures/gpt55_article/`
   without network WeChat scrape (D-11.01 → Plan 11-00)
2. `gate_pass: true` in `benchmark_result.json` after a successful run (D-11.02, D-11.04, D-11.06
   → Plan 11-02 integration run)
3. `text_ingest` stage < 120000 ms (D-11.02 → Plan 11-02)
4. `aquery` returns ≥ 1 chunk from the fixture (D-11.04 → Plan 11-02)
5. All prior regression tests still green (Phase 8: 22, Phase 9: 12, Phase 10: 27 = 61/61)
   (ALL plans — verification gate; 11-01 must not regress any embedding tests)
6. Phase 11 new tests pass (harness unit tests from 11-00; Vertex conditional tests from 11-01)
7. Vertex AI conditional in `lib/lightrag_embedding.py` works with and without
   `GOOGLE_APPLICATION_CREDENTIALS` (both paths tested) (D-11.08 → Plan 11-01)

---

*Generated: 2026-04-29 — PRD express path, autonomous overnight execution.*
