# Phase 11 PRD — E2E Verification Gate

**Milestone:** v3.1 Single-Article Ingest Stability — **FINAL GATE**
**Requirements covered:** E2E-01, E2E-02, E2E-03, E2E-04, E2E-05, E2E-06, E2E-07 (7 REQs)
**Dependencies:** Phase 8 + Phase 9 + Phase 10 (all complete — 22 REQs delivered, 61/61 unit tests green)

---

## Goal

Prove the Phase 8-10 rebuilt pipeline works end-to-end on the GPT-5.5 fixture (`test/fixtures/gpt55_article/`):

- **Text ingest < 2min** wall-clock (E2E-02 gate — the ONE hard quantitative criterion)
- **`aquery("GPT-5.5 benchmark results")` returns at least one chunk from this article** (E2E-04 semantic sanity)
- **Zero crashes** (E2E-06)
- **Structured `benchmark_result.json`** (E2E-07 — machine-readable for CI regression)
- **SiliconFlow balance precheck** (E2E-05 — non-fatal warning)
- **Stage-level timing report** (E2E-03 — scrape/classify/image-download/text-ingest/async-vision-start)

Milestone v3.1 closes when the benchmark writes `{"gate_pass": true}`.

---

## Locked Decisions (acceptance criteria)

### E2E-01 — Local CLI that reads from disk fixture
New script (suggested location: `scripts/bench_ingest_fixture.py`) accepts a fixture path (default `test/fixtures/gpt55_article/`) and runs the full ingest pipeline WITHOUT WeChat network scrape. Reads `article.md` + `metadata.json` + `images/` directly from disk.

### E2E-02 — <2 min wall-clock for text ingest
Measured from the moment the script starts the `ingest_article` call to the moment `ainsert(full_content)` returns (text-first ingest). Does NOT include async Vision worker completion. Script fails loud (exit 1 + `gate_pass: false`) if exceeded.

### E2E-03 — Five stage timings
- `scrape_ms`: fixture read + metadata parse (should be negligible, <100ms)
- `classify_ms`: DeepSeek full-body classify call
- `image_download_ms`: copying fixture images to runtime image dir (or file existence check if already there)
- `text_ingest_ms`: `ainsert(full_content, ids=[doc_id])` — the gate-bearing measurement
- `async_vision_start_ms`: time to spawn the background Vision task (should be milliseconds — just task creation)

### E2E-04 — Semantic query validation
After text ingest returns, call `await rag.aquery(query="GPT-5.5 benchmark results", param=QueryParam(mode="hybrid", top_k=3))`. Parse response; assert at least 1 chunk's `file_path` matches the ingested doc OR chunk text contains signature fragments from the fixture article.

### E2E-05 — SiliconFlow balance precheck
Call `GET https://api.siliconflow.cn/v1/user/info` with `Authorization: Bearer $SILICONFLOW_API_KEY`. Parse `balance`. If below estimated cost (default: 1 × ¥0.036/article = ¥0.036), emit structured warning line:
```json
{"event": "balance_warning", "provider": "siliconflow", "balance_cny": 5.43, "estimated_cost_cny": 0.036, "status": "ok"}
```
OR if below: `"status": "insufficient_for_batch"`. Non-fatal for single-article v3.1 gate (this single article costs ~¥0.04 which is within the ¥5.43 balance).

### E2E-06 — Zero crashes
No unhandled exceptions from start to finish. Final exit status 0 on success, 1 on gate fail.

### E2E-07 — benchmark_result.json schema
Written to `test/fixtures/gpt55_article/benchmark_result.json` (or `benchmark_results/<timestamp>.json` — planner's call) with exact schema:
```json
{
  "article_hash": "...",
  "fixture_path": "test/fixtures/gpt55_article/",
  "timestamp_utc": "2026-05-01T12:34:56Z",
  "stage_timings_ms": {
    "scrape": 50,
    "classify": 3200,
    "image_download": 12,
    "text_ingest": 98000,
    "async_vision_start": 5
  },
  "counters": {
    "images_input": 28,
    "images_kept": 28,
    "images_filtered": 0,
    "chunks_extracted": 15,
    "entities_ingested": 50
  },
  "gate": {
    "text_ingest_under_2min": true,
    "aquery_returns_fixture_chunk": true,
    "zero_crashes": true
  },
  "gate_pass": true,
  "warnings": [
    {"event": "balance_warning", "provider": "siliconflow", "balance_cny": 5.43, "estimated_cost_cny": 0.036, "status": "ok"}
  ],
  "errors": []
}
```

---

## Tactical enabler (Phase 11 local change — NOT v3.3 full migration)

### Vertex AI opt-in conditional in `lib/lightrag_embedding.py`

**Problem:** Gemini free tier = 2000 RPD total across 2 keys. Single GPT-5.5 article produces ~1800 embed calls (15 chunks + 300+ entity merges). Free tier is mathematically inadequate for even ONE heavy article within a 2-min budget (RPM ceiling = 100 × 2 keys = 200 embeds/min → at minimum 9 min for 1800 embeds, far above <2min gate).

**Solution:** tiny env-triggered conditional in `lib/lightrag_embedding.py` that switches `genai.Client` to Vertex AI mode when `GOOGLE_APPLICATION_CREDENTIALS` + `GOOGLE_CLOUD_PROJECT` are both set. Preserves the existing free-tier path as default. Model name gets `-preview` suffix for Vertex AI per memory finding.

**Lines of code:** ~8-12 lines conditional in `_embed_once`.

**Scope justification (to prevent v3.3 encroachment):**
- This is an ENABLER for the benchmark, not the v3.3 migration
- Production code path default unchanged (without env vars, uses free tier as before)
- v3.3 will do the REAL migration: remove all Gemini Developer API code paths, standardize on Vertex AI, add billing monitoring, etc.
- Phase 11 just adds a *toggle* so the benchmark has a way to pass its gate on the developer's actual machine

**User has already validated** the SA JSON + project + Vertex AI API works (memory: `vertex_ai_smoke_validated.md`).

---

## Out of Scope (explicit)

- Running the benchmark against WeChat remote scrape (fixture is the ONLY path)
- Batch-scale benchmarking (multiple articles) — single article only
- Vertex AI production migration (v3.3 — this phase only adds the opt-in conditional)
- Automated Hermes deployment of benchmark results (v3.2+)
- Benchmark CI integration (v3.2 regression fixtures)

---

## Success Criteria for Phase 11 = Success Criteria for Milestone v3.1

1. `scripts/bench_ingest_fixture.py` exists and runs against `test/fixtures/gpt55_article/` without network WeChat scrape
2. `gate_pass: true` in `benchmark_result.json` after a successful run
3. `text_ingest` stage < 120000 ms
4. `aquery` returns ≥ 1 chunk from the fixture
5. All prior regression tests still green (Phase 8: 22, Phase 9: 12, Phase 10: 27) = 61/61
6. Phase 11 new tests pass (harness + JSON schema + stage timing + balance precheck)
7. Vertex AI conditional in `lib/lightrag_embedding.py` works with and without `GOOGLE_APPLICATION_CREDENTIALS` (both paths tested)

---

## Key files planner should read

- `ingest_wechat.py` (post-Phase-10 — now returns `asyncio.Task | None`)
- `batch_ingest_from_spider.py` (post-Phase-10 — has vision task drain)
- `lib/lightrag_embedding.py` (post-Phase-9 — current hardcoded `vertexai=False`)
- `image_pipeline.py` (post-Phase-8 — has JSON logging + emit_batch_complete)
- `test/fixtures/gpt55_article/` — the fixture
- `~/.claude/projects/.../memory/vertex_ai_smoke_validated.md` — Vertex AI model name findings (referenced for `-preview` suffix)

---

## Implementation Notes (planner discretion)

- Fixture ingest path: read `article.md` directly, use its content + metadata.json URL/title as the "ingested article". Use `scripts/bench_ingest_fixture.py` as the new CLI entry. It should instantiate `rag = await get_rag(flush=True)`, then call a version of `ingest_article` that takes article content directly (maybe extract a helper `_ingest_from_text(rag, url, title, markdown, images)` from ingest_wechat for this).

- Vertex AI conditional pattern:
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

- Benchmark harness should emit the same JSON-lines format from Phase 8 (`_emit_log`) so logs are consistent.

- Balance precheck: use stdlib `urllib.request` + `json` — don't import `requests` just for this if it's avoidable. But if `requests` is already imported (via `image_pipeline`), reuse.
