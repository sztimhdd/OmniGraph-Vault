# Phase 8 — Image Pipeline Correctness · CONTEXT

**Milestone:** v3.1 — Single-Article Ingest Stability
**Phase goal:** Deterministic, observable image filter + description pipeline on `test/fixtures/gpt55_article/`
**Requirements covered:** IMG-01, IMG-02, IMG-03, IMG-04

---

## Canonical refs

Documents and code paths that downstream agents MUST read:

- `.planning/REQUIREMENTS.md` — REQ IMG-01..04 (full spec)
- `.planning/ROADMAP.md` — Phase 8 entry + success criteria
- `.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md` — **D-15** (describe_images batch-style contract) + **D-16** (image_pipeline golden-file + pytest regression gate)
- `docs/diagnostic-20260430-batch-ingestion.md` — Hermes's 7 issues, §「问题 2: 图片尺寸过滤 Bug」and §「新问题 #1: describe_images() 零日志」 drive this phase
- `test/fixtures/gpt55_article/` — e2e fixture (28 images, metadata.json; all ≥300px per current filter)
- `image_pipeline.py` — existing module (D-15 refactor)
- `ingest_wechat.py:627-649` — current inline filter (to be extracted per GA1)

No external specs / ADRs beyond these. All decisions traceable to the above.

---

## Decisions (locked)

### D-08.01 — Filter function住所 = `image_pipeline.filter_small_images()` (GA1)

**Decision:** New function `filter_small_images(url_to_path: dict[str, Path], *, min_dim: int = 300) -> tuple[dict[str, Path], FilterStats]` added to `image_pipeline.py`. `ingest_wechat.ingest_article` (and future Zhihu/GitHub callers) call it explicitly; `describe_images()` stays single-purpose (Vision calls only).

**Return contract:**
- `filtered_map`: subset of input dict containing only images where `min(w,h) >= min_dim` (mathematically equivalent to current `or` logic, but explicit)
- `FilterStats`: `{input: int, kept: int, filtered_too_small: int, size_read_failed: int, timings_ms: {total_read: int}}`

**PIL open failure degrades to KEEP** (don't drop images we can't measure; log reason).

**Rationale:**
- D-15 already established "pipeline owns batch logic" pattern
- Returning stats tuple feeds IMG-04 aggregate counts directly (no log scraping)
- Single-responsibility: filter is content-type classification, describe is I/O-bound Vision call — separate lifecycle

**Impact:** caller pattern changes from inline dict-mutation to `map, stats = filter_small_images(url_to_path); log.info(stats); url_to_path = map`. 3-5 line delta in `ingest_wechat.py`.

### D-08.02 — Log format = JSON-lines per image (GA2)

**Decision:** Each image processed emits a single-line JSON object to stderr by default; `VISION_LOG_PATH` env var can redirect to a file (benchmark tooling consumes it).

**Schema (exact fields, all required except where noted):**

```json
{
  "event": "image_processed",
  "ts": "2026-04-30T12:34:56.789Z",
  "url": "http://mmbiz.qpic.cn/...",
  "local_path": "~/.hermes/omonigraph-vault/images/<hash>/0.jpg",
  "dims": "800x600",
  "bytes": 140589,
  "provider": "siliconflow" | "openrouter" | "gemini" | null,
  "ms": 1234,
  "outcome": "success" | "download_failed" | "filtered_too_small" | "size_read_failed" | "vision_error" | "timeout",
  "error": "HTTP 503: ..." | null
}
```

- `provider` is `null` when outcome is `download_failed` / `filtered_too_small` / `size_read_failed` (Vision never invoked)
- `ms` measures wall-clock of the STAGE that owns this event (download for `download_failed`, filter for `filtered_too_small`, vision for success / vision_error / timeout)
- `error` only populated on non-success outcomes

**Aggregate line (fires once at end of batch, IMG-04):**

```json
{
  "event": "image_batch_complete",
  "ts": "...",
  "counts": {"input": 39, "kept": 28, "filtered_too_small": 11, "download_failed": 0, "size_read_failed": 0, "vision_success": 27, "vision_error": 1, "vision_timeout": 0},
  "total_ms": 14532,
  "provider_mix": {"siliconflow": 27, "openrouter": 0, "gemini": 0}
}
```

**Implementation:** helper `_emit_log(event_dict: dict) -> None` in `image_pipeline.py` does `print(json.dumps(event_dict), file=sys.stderr)` unless `VISION_LOG_PATH` is set (then `open(path, 'a').write(...)`, atomic append).

**Rationale:** E2E-07 benchmark_result.json is composed directly from these lines; JSON-lines is trivial to tail + aggregate. Human readability sacrificed on purpose — if debugging is needed, pipe stderr through `jq`.

### D-08.03 — Threshold = kwarg `min_dim: int = 300` + env override in caller (GA3)

**Decision:**
- `filter_small_images(url_to_path, *, min_dim: int = 300)` — kwarg is authoritative
- `ingest_wechat.ingest_article` reads env at call site: `min_dim = int(os.environ.get("IMAGE_FILTER_MIN_DIM", 300))`, passes to function

**Rationale:**
- kwarg default 300 matches Hermes's empirical finding (21.4% of 1317 images <300px are junk)
- env override lets ops tune for different corpora (academic papers, screenshot archives) without code change
- Test isolation: unit tests call with explicit `min_dim=` (no monkeypatching env)

### D-08.04 — Inter-image sleep = 0 default, env override (IMG-02)

**Decision:** `_DESCRIBE_INTER_IMAGE_SLEEP_SECS = 0` (down from current `2`). `VISION_INTER_IMAGE_SLEEP` env var allows caller to restore non-zero value if a provider develops RPM issues.

**Rationale:**
- SiliconFlow Qwen3-VL-32B has no RPM cap (verified in Hermes's cascade)
- OpenRouter GLM-4.5V has per-key limits but they're generous
- 28-image fixture × 2s = 56s pure waste (documented in Hermes diagnostic §6)
- env escape hatch covers a future provider change

### D-08.05 — Outcome taxonomy = 6 values (Claude's Discretion)

**Decision:** `success / download_failed / filtered_too_small / size_read_failed / vision_error / timeout`

`vision_error` covers Gemini/SiliconFlow/OpenRouter API-level failures (4xx/5xx/quota); `timeout` is specifically asyncio/request timeout hits; `size_read_failed` is PIL open failures (image bytes corrupt / unsupported format).

No `cache_hit` (no per-image Vision cache in v3.1 scope) — deferred to v3.2.

### D-08.06 — PIL sync vs async = sync (Claude's Discretion)

**Decision:** `PILImage.open(path).size` called synchronously in-process.

**Rationale:**
- 28 images × ~30ms/open = <1s — invisible in a 90-120s article budget
- Async wrapping adds complexity without measurable win at single-article scale
- If v3.2 batch scale makes this measurable, wrap in `asyncio.to_thread` at that point

### D-08.07 — D-15/D-16 回归 gate (carried forward from Phase 4)

**D-16 from Phase 4 still applies:** any `image_pipeline.py` change must pass:

1. **Pytest unit tests** — new `tests/unit/test_image_pipeline.py::test_filter_small_images_*`:
   - Keeps 800×600 ✓
   - Filters 100×800 (narrow banner — the bug Hermes originally flagged) ✓
   - Filters 300×299 (just below threshold) ✓
   - Keeps 300×300 exactly ✓
   - Filters 299×300 (just below threshold on one axis) ✓
   - `min_dim=100` kwarg keeps 150×150 ✓
   - `IMAGE_FILTER_MIN_DIM=100` env read by ingest_wechat (integration test via subprocess OR caller mock)
2. **Golden-file diff** — 2-3 already-cached WeChat articles run through updated pipeline; `final_content.md` structural diff (image count, local URL format preserved); image descriptions may drift 1 line
3. **No regression** on existing pytest suite

Merge blocker per D-16.

---

## Folded Todos

None — no pending todo list items matched Phase 8 scope at init.

---

## Deferred Ideas (surfaced during discussion, out of scope for v3.1)

- **Per-image Vision cache** — skip describing identical image bytes across articles (v3.2 Batch Reliability — Checkpoint/resume relates)
- **Image cost tracking in log** — add `estimated_cost_yuan` field to per-image JSON (nice for billing dashboards, not critical for Phase 8 correctness)
- **Log shipper integration** — structlog / OTel / Datadog. Makes sense once observability stack exists; not a Phase 8 concern
- **Batch-aware filter** — if the same article is re-ingested, reuse filter decisions (v3.2 Checkpoint/resume)

---

## Specifics

- User explicitly preferred JSON-lines over key=value despite the human-readability penalty — rationale: benchmark_result.json composition (E2E-07) benefits from direct tail-and-parse; debugging can pipe through `jq`
- User's SiliconFlow is the primary Vision provider; Gemini Vision stays as last-resort fallback (per Hermes feedback in REQUIREMENTS.md Out of Scope)
- The "AND bug" Hermes named in `docs/diagnostic-20260430-batch-ingestion.md §问题 2` is actually an `or` in current code (commit `af8f82b`) — mathematically equivalent to `min(w,h) < 300`. This phase REPLACES the inline call site with an explicit `filter_small_images()` function call for clarity, modularity, and test targetability — not to fix a live bug. The REQ text phrasing will be preserved as-is; code comment will note the pre-fix history

---

## Next

- `/gsd:plan-phase 8` — break this phase into atomic plans (expect 2-3 plans: one for filter + one for logging, possibly merged if small enough)
- Downstream agents will read this CONTEXT.md to derive research / plan tasks
