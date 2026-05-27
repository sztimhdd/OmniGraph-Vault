# T5 — image_pipeline.py Deep Review (read-only post-release hygiene)

**Generated:** 2026-05-11 ADT
**File:** `image_pipeline.py` — 645 LOC, last commit `ce8127a feat(image_pipeline): D-20.08/09 referer header + SVG filter (RIN-02)`
**Audit budget:** 2-3 h target — completed under budget (single-pass read-only).
**Auditor scope:** read-only / no business code edits / no Hermes SSH / no pytest / no live SF/OR/Gemini API calls / no `.env` touch.
**Cross-reference T3/T4 reviews:**
- `.planning/quick/260511-d7m-t3-batch-ingest-from-spider-py-deep-revi/260511-d7m-REVIEW.md` (`8832e95`).
- `.planning/quick/260511-kxd-t4-lib-scraper-py-deep-review-read-only/260511-kxd-REVIEW.md` (`6a284a3`).

**Trusted regions (NOT re-audited):**
- p1n (`f715f06`) — `lib/vision_tracking.py` drain refactor + `ingest_wechat.py:1336` spawn site wrap. Verified call-site shape only (see §4.B).
- b3y (`b1e7fc8`) — `lib/lightrag_embedding.py` `GOOGLE_CLOUD_LOCATION` default `global`. Did NOT touch image_pipeline; verified b3y-context claim (`image_pipeline.py:327` already defaults `global`) — see F-2 for the broader Vertex-routing finding.
- gqu / d7m T3 / kxd T4 / s29 W3 — schema-reference only.

---

## TL;DR

| Severity | Count | Notes |
|----------|-------|-------|
| **HIGH** | **2** | F-1 dead-code Vertex path in `_describe_via_gemini` (98 LOC unreachable). F-2 Vision-Gemini fallback path defaults `GOOGLE_CLOUD_LOCATION='us-central1'` in `lib/llm_client.py:51` (the b3y bug, untransferred to the Vision path). |
| **MEDIUM** | **3** | M-1 cascade contract divergence vs CLAUDE.md (429 counts toward circuit-breaker; CLAUDE.md says "cascades immediately"). M-2 `batch_validation_report.json` writer documented in CLAUDE.md "Vision Cascade" but no production writer exists in code (Phase 14 unfinished). M-3 silent-empty-success cost-leak path on SiliconFlow HTTP 200 with empty body. |
| **LOW** | **3** | L-1 module-global mutable state `_last_describe_stats` documented as "not thread-safe". L-2 vertex-vs-free-tier divergence in dead `_describe_via_gemini` won't be caught when re-enabled. L-3 `OMNIGRAPH_VISION_SKIP_PROVIDERS` parsed twice (env in `image_pipeline`, again in test isolation paths). |
| **Cross-cutting** | **2** | F-1 + F-2 both span `image_pipeline.py` ↔ `lib/vision_cascade.py` ↔ `lib/llm_client.py`. M-2 spans `image_pipeline.py` ↔ `lib/vision_cascade.py.total_usage()` ↔ never-built `validate_regression_batch.py`. |

**Hygiene verdict: `soft-gating`.** F-1 is dead-code purgeable (98 LOC, ~0.5 h). F-2 is the b3y-class bug untransferred — production cron hits the wrong default if `GOOGLE_CLOUD_LOCATION` is not exported. Hermes `~/.hermes/.env` SHOULD have it set per CLAUDE.md:520, but defense-in-depth (matching b3y's pattern) is the post-release hygiene fix. Neither breaks current cron; both deserve a follow-up quick before the next refactor pass.

**Cost-leak verdict: `soft-leak`.** M-3 (silent SF empty body counted as success → ¥0.0013 charged for empty description) is a real cost-leak path with measurable production impact (each occurrence: 1 image worth of ¥0.0013 + downstream LightRAG bloat with empty entity sub-doc). Not a hemorrhage; not zero. M-2 (no `batch_validation_report.json` writer) means there is no per-batch evidence file to detect cost anomalies — operational blindness, not a leak per se.

**Estimated cleanup:** ~3-5 h across 2-3 quicks:
1. F-1 dead-code purge (`_describe_via_*` removal) — ~0.5 h, atomic, no test impact (no callers).
2. F-2 location-default fix in `lib/llm_client.py:51` — ~0.5 h (1 line + 1 test, mirror b3y).
3. M-1 + M-3 cascade-contract patch (429-doesn't-count + empty-body validation) — ~1.5 h (touches `lib/vision_cascade.py` + 2 new tests).
4. M-2 `batch_validation_report.json` writer — ~1-2 h (resurrect Phase 14 plan or simplify to image_pipeline emitting per-batch JSON).

**A2 + A3 evidence-density tally:** **17 file:line citations** combined (target ≥ 8). Detailed in §4 + §5.

---

## 1. File sectional map

12 named symbols / 645 LOC. ⚠ marks **god functions** (>100 LOC). One ⚠⚠ (`describe_images`, 222 LOC).

| Lines | LOC | Symbol | Purpose |
|------:|----:|--------|---------|
| 1-11 | 11 | module docstring | Phase 13 contract: cascade replaces `VISION_PROVIDER` env; balance check via `lib.siliconflow_balance`. |
| 26-36 | 11 | imports | `lib.siliconflow_balance` + `lib.vision_cascade` (cascade-engine + balance-engine; clean separation). |
| 41 | 1 | `_DESCRIBE_INTER_IMAGE_SLEEP_SECS = 0` | IMG-02: was 2; SiliconFlow has no RPM cap. |
| 44 | 1 | `_DEFAULT_IMAGE_BASE_URL` | `http://localhost:8765` for Markdown localization. |
| 47-52 | 6 | `OUTCOME_*` constants | 6-value canonical outcome taxonomy (D-08.05). |
| 55-58 | 4 | `_now_iso` | ISO-8601 ms-precision timestamp helper. |
| 61-77 | 17 | `_emit_log` | JSON-lines writer; file (`VISION_LOG_PATH`) or stderr. Atomic via `open('a')` per call. |
| 84 | 1 | `_last_describe_stats: dict` | Module-global mutable state — see L-1. |
| 87-99 | 13 | `get_last_describe_stats` | Read accessor for caller (`ingest_wechat._vision_worker_impl`). |
| 102-131 | 30 | `emit_batch_complete` | Aggregate `image_batch_complete` JSON-lines event (IMG-04). |
| 134-146 | 13 | `FilterStats` (frozen dataclass) | Wire format per D-08.01. |
| 149-217 | 69 | `download_images` | HTTP GET each URL, write to `dest_dir/{i}.jpg`. Referer header (D-20.08). SVG skip (D-20.09). |
| 220-286 | 67 | `filter_small_images` | Drop images where `min(w,h) < min_dim` (default 300). PIL fail → keep image. |
| 289-303 | 15 | `localize_markdown` | Replace each remote URL with `{base_url}/{article_hash}/{filename}`. |
| **306-349** | **44** | `_describe_via_gemini` | **DEAD CODE** (F-1). Vertex-aware Gemini Vision; never called from `describe_images`. |
| **352-376** | **25** | `_describe_via_openrouter` | **DEAD CODE** (F-1). OpenRouter GLM-4.5V; never called. |
| **379-403** | **25** | `_describe_via_siliconflow` | **DEAD CODE** (F-1). SiliconFlow Qwen3-VL-32B; never called. |
| 406-627 | **222** ⚠⚠ | `describe_images` | **God function** — pre-batch balance check, per-image cascade dispatch, mid-batch re-check, batch-end aggregate, alerts. Production hot path. |
| 630-645 | 16 | `save_markdown_with_images` | Atomic tmp→rename writer for `final_content.md` + `metadata.json`. |

**Module health signal:** every public name documented; no module-level state besides `_last_describe_stats` (acknowledged not-thread-safe); 645 LOC — 98 of which are dead (15%). Post-F-1 purge would put the module at ~547 LOC with one god function (`describe_images`).

---

## 2. CLAUDE.md cross-reference (Vision Cascade + SiliconFlow Balance Management)

| # | Documented contract (CLAUDE.md L) | Source code state | Match? | Evidence (file:line) |
|---|-----------------------------------|-------------------|--------|----------------------|
| 1 | Cascade order **hard-coded, not env-overridable**: SF → OR → Gemini Vertex (L582-584) | Cascade order is hard-coded in `lib/vision_cascade.py:31` (`DEFAULT_PROVIDERS = ("siliconflow", "openrouter", "gemini")`). However, `image_pipeline.py:481-486` reads `OMNIGRAPH_VISION_SKIP_PROVIDERS` env var which CAN drop providers — this is **partial env-override** (skip, not reorder). | **partial match** | `lib/vision_cascade.py:31`; `image_pipeline.py:472-486` (skip path); `image_pipeline.py:472-476` (force-openrouter-primary on low balance — also reorders) |
| 2 | Circuit breaker: **3 consecutive failures** within batch → `circuit_open=True` (L586) | `lib/vision_cascade.py:34` `CIRCUIT_FAILURE_THRESHOLD = 3`; logic at `lib/vision_cascade.py:296-304` increments `pstate["failures"]` on circuit-failure codes. Reset to 0 on success at `lib/vision_cascade.py:253`. | **match** | `lib/vision_cascade.py:34, 253, 296-304` |
| 3 | "A 429 cascades immediately to the next provider" (L586) | `lib/vision_cascade.py:46` `_CIRCUIT_FAILURE_CODES = {RESULT_HTTP_503, RESULT_HTTP_429, RESULT_TIMEOUT}` — 429 IS counted. Then `:296-298` `if e.result_code in _CIRCUIT_FAILURE_CODES: pstate["failures"] += 1`. **Effect: 429 cascades immediately AND increments the 3-strike counter.** CLAUDE.md "cascades immediately" is ambiguous — code interprets as "moves on quickly", not "doesn't increment counter". | **divergent / ambiguous** | `lib/vision_cascade.py:46, 296-298` (see M-1) |
| 4 | "4xx auth errors do NOT count toward the circuit breaker" (L586) | `lib/vision_cascade.py:41` `RESULT_HTTP_4XX_AUTH = "http_4xx_auth"` is **NOT** in `_CIRCUIT_FAILURE_CODES`. Comment at `:305` confirms: `# 4xx_auth / other: don't increment failures, just cascade.` | **match** | `lib/vision_cascade.py:41, 46, 305` |
| 5 | Pre-batch: structured warning to stderr if `SF balance < estimated cost` (L588) | `image_pipeline.py:449-465` calls `check_siliconflow_balance()`, computes `estimated = Decimal(len(paths_list)) * Decimal("0.0013")`, emits warning via `logger.warning(...)`. **NOT a structured JSON-lines event** — it goes through Python `logging` not `_emit_log`. | **partial match** (signal raised, but as plaintext log not JSON-lines) | `image_pipeline.py:449-465`; CLAUDE.md says "structured warning per image" at L601 |
| 6 | Estimated cost: `¥0.0013 × expected_image_count`, ¥1.00 ≈ 770 images (L596) | `image_pipeline.py:451` literal `Decimal("0.0013")`. Same constant in `lib/siliconflow_balance.py:28` `SILICONFLOW_PRICE_PER_IMAGE = Decimal("0.0013")`. **Two sources of truth** — drift risk if pricing changes. | **match (with drift risk)** | `image_pipeline.py:451`; `lib/siliconflow_balance.py:28` |
| 7 | `batch_validation_report.json` records `provider_usage` (L590) | **No production writer.** `lib/vision_cascade.py:190-195` exposes `total_usage()` for callers, but no `image_pipeline.py` code or `batch_ingest_from_spider.py` code writes `batch_validation_report.json`. Only `.planning/phases/14-regression-fixtures/14-CONTEXT.md:268` references this file (Phase 14 deferred). | **missing in production** | `image_pipeline.py:617-626` (batch-end stats stay in `_last_describe_stats`); CLAUDE.md L590 (M-2) |
| 8 | "Healthy batch shows Gemini usage below 10%; if >10%, investigate" (L590) | `image_pipeline.py:605-610`: `if gemini_share > 0.05: logger.warning("CASCADE ALERT: gemini used for %.1f%% of images (>5%% threshold) ...")`. **Threshold is 5%, NOT 10%.** | **divergent (5% in code vs 10% in doc)** | `image_pipeline.py:605` |
| 9 | Depletion scenario: cascade falls through, NOT hang (L594, L600) | `image_pipeline.py:516-532` mid-batch re-check; on low balance, removes `siliconflow` from `cascade.providers` (`:528-530`). **Falls-through is correct.** | **match** | `image_pipeline.py:516-532` |
| 10 | "Pause batch + top up — atomic checkpoints" (L605) | Cascade state is persisted to `provider_status.json` at `lib/vision_cascade.py:159-188` via tmp→replace. Resume-friendly. | **match** | `lib/vision_cascade.py:159-188` |

**Summary:** 6 full matches, 3 partial/divergent (rows 1, 5, 8), 1 missing in production (row 7), 1 ambiguous-but-divergent (row 3). Rows 1-7 are observability/telemetry; row 3 (M-1) is a behavioral divergence; rows 7 & 8 are doc/code drift.

---

## 3. Lessons Learned cross-reference (anchor: 2026-05-05 #5)

| Lesson (CLAUDE.md L488) | Status | Evidence (file:line) | Notes |
|-------------------------|--------|----------------------|-------|
| **2026-05-05 #5** — Embedding/Vision worker timeouts disproportional to LLM timeout. `OMNIGRAPH_LLM_TIMEOUT_SEC` 600→1800; vision worker per-image still 60s. 30× ratio is hidden ceiling. | **applicable / not addressed** | Vision per-provider HTTP timeouts: `lib/vision_cascade.py:374` SiliconFlow `timeout=60`; `lib/vision_cascade.py:422` OpenRouter `timeout=30`. Gemini-Vision (free-tier) inherits whatever `lib.generate_sync` enforces; `lib/llm_client.py:103` retry: `stop_after_attempt(5), wait_exponential(min=2, max=60)`. **No env override on any of these timeouts.** Vision Vertex-aware path in `image_pipeline.py:332-339` calls `client.models.generate_content` — uses the SDK's default HTTP timeout (no explicit `config.http_options.timeout`); the b3y-fixed sister path in `lib/vertex_gemini_complete.py:194-196` DOES plumb `OMNIGRAPH_LLM_TIMEOUT_SEC` × 1000 → `HttpOptions.timeout`, but Vision does NOT. | The 30× ratio (1800 LLM vs 30-60 Vision) is intact today. The dead `_describe_via_gemini` ALSO doesn't set a timeout. F-1 + this lesson combined: when the dead path is removed (or revived), the timeout disparity remains a v3.5 candidate. |

**Verdict for §3:** lesson 2026-05-05 #5 is real and present in source. CLAUDE.md flags it as "currently doesn't bite, but as graph grows or vision providers get slower, the 30× ratio becomes a hidden ceiling. Worth tracking as a v3.5 candidate." This audit confirms: still a v3.5 candidate, no proportional-timeout work has landed since the lesson was recorded.

---

## 4. Cascade + Circuit-breaker findings (STAR ANGLE 1, A2)

### A. Cascade order — actual vs. documented

**Actual production order** (from `image_pipeline.py:472-476`):
- Default: `list(DEFAULT_PROVIDERS)` = `["siliconflow", "openrouter", "gemini"]` (matches CLAUDE.md L582-584).
- On low SF balance (`should_switch_to_openrouter(balance)` — `balance < ¥0.05`): `["openrouter", "gemini"]` (SF dropped). `image_pipeline.py:472-474`.
- On `OMNIGRAPH_VISION_SKIP_PROVIDERS` env: any subset is dropped, preserving order. `image_pipeline.py:481-486`. **This is a deviation from CLAUDE.md "hard-coded, not env-overridable"** — env CAN drop providers (it can't reorder, but it can shrink the list). LDEV-06 added this for local-dev parity; documented at line 477-486 with rationale.

### B. Circuit-breaker state machine — scope, persistence, reset

| Property | Source code state | File:line |
|----------|-------------------|-----------|
| Storage | `VisionCascade.status: dict[str, dict]`, instance attr | `lib/vision_cascade.py:134` |
| Scope | **Per-`VisionCascade` instance, persisted to disk** across batches via `provider_status.json` (instance constructed once per `describe_images()` call → effectively per-batch + cross-batch persistence) | `image_pipeline.py:493` (one cascade instance per `describe_images` call); `lib/vision_cascade.py:133, 141-157, 159-188` (load + persist) |
| Counter | `pstate["failures"]` increments on `_CIRCUIT_FAILURE_CODES` | `lib/vision_cascade.py:296-298` |
| Threshold | `CIRCUIT_FAILURE_THRESHOLD = 3` consecutive | `lib/vision_cascade.py:34, 298` |
| Open semantics | `pstate["circuit_open"] = True` once threshold hit; logged WARNING | `lib/vision_cascade.py:299-304` |
| Skip while open | Subsequent images skip provider until recovery probe | `lib/vision_cascade.py:216-237` |
| Recovery probe | Every `RECOVERY_PROBE_INTERVAL` skipped images, allow one attempt | `lib/vision_cascade.py:220-230` |
| Counter reset on success | `pstate["failures"] = 0; pstate["circuit_open"] = False` | `lib/vision_cascade.py:253-254` |

**Hidden-state issues:**
- **Cross-batch state carry-over** — `provider_status.json` is loaded on `__init__` (`lib/vision_cascade.py:141-157`). If a previous batch left `circuit_open=True` for SF and the operator topped up balance + restarted, the new batch starts with SF circuit OPEN and only opens after `RECOVERY_PROBE_INTERVAL` skipped images. Counter is NOT reset on batch start. **This is intentional per the test `test_circuit_open_recovery_probe_after_10_skipped` but operationally surprising.**
- **Counter reset on intermediate success** (`lib/vision_cascade.py:253`) — if the pattern is `503, 503, 200, 503, 503`, counter is reset to 0 at the 200 success and only re-counts from there. So 5 503s in a row would not necessarily open the circuit if interleaved with even one success. **CLAUDE.md says "3 consecutive failures" — code matches.**

### C. Branch table for HTTP outcomes

| HTTP status | Code label | Counts toward circuit? | Cascades to next provider? | Source |
|-------------|------------|------------------------|----------------------------|--------|
| 200 | RESULT_SUCCESS | resets to 0 | n/a — returns | `lib/vision_cascade.py:243-273` |
| 401 / 403 / 422 | RESULT_HTTP_4XX_AUTH | **NO** | YES (continue loop) | `lib/vision_cascade.py:96-98, 305-307` |
| 429 | RESULT_HTTP_429 | **YES** (M-1 vs CLAUDE.md) | YES + special: if all providers 429 on same image → `AllProvidersExhausted429Error` | `lib/vision_cascade.py:46, 94-95, 296-304, 310-318` |
| 503 | RESULT_HTTP_503 | YES | YES | `lib/vision_cascade.py:46, 92-93, 296-304` |
| Timeout | RESULT_TIMEOUT | YES | YES | `lib/vision_cascade.py:46, 376-377, 424-425` |
| Other (network, 5xx) | RESULT_OTHER | NO | YES | `lib/vision_cascade.py:43, 305-307` |

**M-1 detail:** CLAUDE.md L586 says "A 429 cascades immediately to the next provider." Two interpretations:
- (a) "moves on" — what code does (counts toward 3-strike, then continues to next provider).
- (b) "doesn't count toward 3-strike" — symmetric with the 4xx auth rule documented immediately after.

The 4xx-auth rule has explicit "do NOT count" wording; 429 has only "cascades immediately". The two-sentence pairing in CLAUDE.md plus the symmetry of "operator must intervene to fix" (4xx = key auth issue → operator; 429 = quota → operator) suggests interpretation (b) was intended. Code does (a). **This is a contract-vs-code interpretation gap; recommend clarifying CLAUDE.md OR changing `_CIRCUIT_FAILURE_CODES` to drop `RESULT_HTTP_429`.**

**Test coverage of this:** `tests/unit/test_vision_cascade.py:216` `test_401_auth_not_counted_as_circuit_failure` confirms 4xx behavior. NO test exists for "429 should not count" — `tests/unit/test_vision_cascade.py:233` `test_all_providers_429_raises_stop_batch` only tests the all-providers-429 batch-stop, not the per-provider counter behavior. So nothing in the test suite locks in interpretation (a) — flipping to (b) would require ≤1 line in `lib/vision_cascade.py:46` and 1 new test.

### D. Cascade evidence for §4 (file:line citations)

1. `image_pipeline.py:31-36` — imports `DEFAULT_PROVIDERS, VisionCascade, AllProvidersExhausted429Error, CascadeResult`.
2. `image_pipeline.py:472-476` — provider-list construction (default vs force-openrouter-primary).
3. `image_pipeline.py:481-486` — `OMNIGRAPH_VISION_SKIP_PROVIDERS` parsing (LDEV-06 deviation from "hard-coded").
4. `image_pipeline.py:493` — `cascade = VisionCascade(providers=providers, checkpoint_dir=_ckpt_dir)`.
5. `image_pipeline.py:534-546` — per-image dispatch via `cascade.describe(...)` + 429-batch-stop catch.
6. `image_pipeline.py:602-616` — batch-end aggregate alerts (`gemini_share > 0.05`, `circuit_opens` list).
7. `lib/vision_cascade.py:46` — `_CIRCUIT_FAILURE_CODES` set (HIGH evidence for M-1).
8. `lib/vision_cascade.py:212-237` — circuit-open skip + recovery-probe loop.
9. `lib/vision_cascade.py:296-304` — counter increment + open trigger.

**A2 evidence count: 9 file:line citations.**

---

## 5. Cost / balance findings (STAR ANGLE 2, A3)

### A. Balance-check timing + estimation

| Property | Source code state | File:line |
|----------|-------------------|-----------|
| Pre-batch check | Once per `describe_images()` call, only if `paths_list` non-empty AND `OMNIGRAPH_VISION_SKIP_BALANCE_CHECK != '1'` | `image_pipeline.py:444-470` |
| Estimation | `Decimal(len(paths_list)) * Decimal("0.0013")` | `image_pipeline.py:451` |
| Estimation rule (CLAUDE.md L596) | `¥0.0013 × expected_image_count` — matches code | `lib/siliconflow_balance.py:28` (`SILICONFLOW_PRICE_PER_IMAGE`) |
| `expected_image_count` source | `len(paths_list)` — list passed to `describe_images()` (filtered images, not raw URL count) | `image_pipeline.py:451` |
| Mid-batch re-check | Every 10th image (`i > 0 and i % 10 == 0`) | `image_pipeline.py:516` |
| Switch threshold | `OPENROUTER_SWITCH_THRESHOLD = Decimal("0.05")` CNY | `lib/siliconflow_balance.py:29` |
| Pre-batch warning channel | `logger.warning(...)` — NOT structured JSON-lines via `_emit_log` | `image_pipeline.py:454, 461` |
| Mid-batch warning channel | Same — `logger.warning(...)` plaintext | `image_pipeline.py:523-527` |

**Estimation accuracy.** `len(paths_list)` is the post-filter image count (after `filter_small_images` drops <300px), so the estimate is accurate at the time of `describe_images` invocation. **However**, on retry-after-Ctrl-C top-up, `describe_images` re-runs against the SAME `paths_list` — pre-batch warning will re-fire, but mid-batch re-checks every 10 images correctly stop using SF as soon as balance drops below ¥0.05. So estimation is correct but does NOT account for sub-doc resume scenarios where some images already have descriptions on disk (those are not re-described — they're skipped at the `read_bytes` step? Actually no — `describe_images` doesn't check for existing descriptions; it always re-calls cascade. Caller (vision worker) is responsible for skipping resumed images.).

### B. Silent-leak audit (M-3)

**Critical finding (M-3):** `lib/vision_cascade.py:381-382` — on SiliconFlow HTTP 200, the code reads:
```python
content = resp.json()["choices"][0]["message"]["content"] or ""
return content.strip()
```
If SF returns 200 with empty `content` (model failed to produce description, or returned `null`), the function returns an empty string. Upstream `lib/vision_cascade.py:243-265` records this as `RESULT_SUCCESS` with `desc_chars=0`, increments `total_successes`, and `image_pipeline.py:573-578` records `provider_mix["siliconflow"] += 1`. **The image is billed (¥0.0013) but the description is empty.** Empty description flows into the markdown sub-doc (`ingest_wechat._vision_worker_impl`), into LightRAG, and into the entity extractor — wasted compute on a no-op image.

Same shape at `lib/vision_cascade.py:428-429` for OpenRouter (no billing impact since OR is free-tier, but adds noise to `provider_mix`).

**Detection:** none. Logging only records `desc_chars` length but no minimum-length check exists. A length-zero description is logged at `lib/vision_cascade.py:258-265` indistinguishable from a real success.

**Fix scope:** ~5-10 LOC at `lib/vision_cascade.py:381-382, 428-429`. Validation: `if not content.strip(): raise _ProviderError(RESULT_OTHER, "empty content body")` — cascades to next provider, matches CLAUDE.md "validate response" expectation. Test scope: 2 unit tests (one per provider).

### C. Cost instrumentation gaps

- **Per-provider spend tracking:** `lib/vision_cascade.py:status[provider]["total_attempts"]` and `["total_successes"]` track call counts but not currency cost. `image_pipeline.py:618-626` `_last_describe_stats["provider_mix"]` is success-count by provider — NOT spend.
- **No cumulative cost field** in `_last_describe_stats` or `provider_status.json`. Operator must compute `provider_mix["siliconflow"] × ¥0.0013` manually.
- **Pre-batch warning is informational only.** If SF balance is ¥0.50 and estimated cost is ¥1.30, the warning fires but the batch proceeds anyway (`image_pipeline.py:452-458`). No "abort if insufficient" mode. **This is by design** — falls through to OR/Gemini per CLAUDE.md L594 — but it means a low-balance cron run can quietly route 50%+ of images to free-tier Gemini and exhaust the 500-RPD quota for the day with no operator visibility until the alert at batch end.
- **Balance check failure is non-fatal at both pre-batch (`image_pipeline.py:466-470`) and mid-batch (`image_pipeline.py:531-532`).** If SF balance API is unreachable (network issue, API change), batch proceeds with whatever `cascade.providers` was when last set. Reasonable default behavior — but a transient SF API outage could silently allow a batch to spend down to zero balance with no operator alert.

### D. `batch_validation_report.json` writer (M-2)

CLAUDE.md L590 documents `batch_validation_report.json` as the cascade-evidence file. Grep across the repo finds **no production writer**:
- `lib/vision_cascade.py:190-195` — `total_usage()` exposes the data.
- `image_pipeline.py:617-626` — populates `_last_describe_stats` (in-memory only).
- All references to `batch_validation_report.json` live in `.planning/phases/14-regression-fixtures/14-CONTEXT.md` (Phase 14, not implemented) or `.planning/MILESTONE_v3.2_REQUIREMENTS.md` (deferred).

**Operational consequence:** The "healthy batch shows Gemini usage below 10%" check (CLAUDE.md L590) requires reading a file that doesn't exist. The runtime alert at `image_pipeline.py:605-610` fires (5% threshold, M-doc-divergence note above), but post-batch evidence retrieval relies on parsing stderr logs or `provider_status.json` — both possible but not the documented contract.

**Fix scope:** ~30-50 LOC. Either resurrect Phase 14 plan (`scripts/validate_regression_batch.py` + `--output` flag) or simplify to: at end of each `describe_images()` call, if `OMNIGRAPH_BATCH_VALIDATION_REPORT_PATH` is set, write the JSON. Latter is a smaller-blast-radius option and fits this audit's "post-release hygiene" verdict.

### E. Cost-leak evidence for §5 (file:line citations)

1. `image_pipeline.py:444-470` — pre-batch balance check timing.
2. `image_pipeline.py:451` — `Decimal("0.0013")` literal (estimation).
3. `image_pipeline.py:454, 461` — pre-batch warnings (plaintext, not JSON-lines).
4. `image_pipeline.py:516-532` — mid-batch re-check + provider-removal logic.
5. `image_pipeline.py:573-578` — `provider_mix` success increment without empty-content check (M-3 entrypoint).
6. `lib/vision_cascade.py:381-382` — SiliconFlow empty-body return-as-success (M-3 critical).
7. `lib/siliconflow_balance.py:28-29` — `SILICONFLOW_PRICE_PER_IMAGE` + `OPENROUTER_SWITCH_THRESHOLD` constants.
8. `image_pipeline.py:617-626` — `_last_describe_stats` post-batch summary (no cost field).

**A3 evidence count: 8 file:line citations. Combined A2+A3 = 17 (target ≥ 8 met 2.1×).**

---

## 6. Findings by severity

### HIGH (release blocker / bound to break)

#### F-1 — `_describe_via_*` are unreachable dead code (98 LOC)

- **Title:** Three `_describe_via_*` functions in `image_pipeline.py` (98 LOC, 15% of file) have no callers in production.
- **Evidence:**
  - `image_pipeline.py:306-403` defines `_describe_via_gemini`, `_describe_via_openrouter`, `_describe_via_siliconflow`.
  - `grep -n "_describe_via_" image_pipeline.py` → only the 3 def sites.
  - `grep -rn "_describe_via_" --include="*.py"` → NO callers outside the def sites; one historical reference in `.planning/phases/13-vision-cascade/13-02-image-pipeline-integration-PLAN.md:300` ("RECOMMENDED: remove ...") and `.planning/phases/13-vision-cascade/13-02-SUMMARY.md:23` (says they were "kept" — but the production cascade now lives in `lib/vision_cascade._call_provider`).
  - Production cascade dispatches via `lib/vision_cascade.py:328-338` `_call_provider` which calls `_call_siliconflow` / `_call_openrouter` / `_call_gemini` (lines 340, 388, 436) — these DO NOT delegate back to `image_pipeline._describe_via_*`.
- **Why HIGH:** Dead code that LOOKS LIKE production code is a refactoring trap. A future engineer reading `image_pipeline.py` will see `_describe_via_gemini` at line 306, see the Vertex-aware logic + correct `location='global'` default at line 327, assume Vertex Vision is wired in production, and miss the actual production path's b3y-class bug at `lib/llm_client.py:51` (F-2). The dead Vertex code masks the live bug.
- **Fix scope:** ~1 quick. Delete `image_pipeline.py:306-403` (98 LOC). No tests reference these symbols. Risk: zero.
- **Quick type:** Atomic delete + import-check.
- **Citation:** `image_pipeline.py:306, 352, 379` (def sites); `lib/vision_cascade.py:333-337` (real production path).

#### F-2 — `lib/llm_client.py:51` Vision-Gemini fallback defaults `GOOGLE_CLOUD_LOCATION='us-central1'` (b3y bug, untransferred)

- **Title:** The production Vision-Gemini fallback path goes through `lib.generate_sync(VISION_LLM, ...)` → `lib/llm_client._make_client()` which defaults `GOOGLE_CLOUD_LOCATION='us-central1'`. The b3y fix patched this in `lib/lightrag_embedding.py` but did NOT propagate to `lib/llm_client.py`.
- **Evidence:**
  - `lib/vision_cascade.py:436-457` `_call_gemini` calls `from lib import VISION_LLM, generate_sync` then `generate_sync(VISION_LLM, contents=[...])`.
  - `lib/llm_client.py:123-125` `generate_sync` → `asyncio.run(generate(...))` → `_get_client()._make_client()`.
  - `lib/llm_client.py:41-53` `_make_client`: in Vertex mode (line 47-52), `location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")` — **`us-central1` default, same bug as the embedding bug fixed by b3y**.
  - b3y commit (`b1e7fc8`) only patched `lib/lightrag_embedding.py:141`; b3y PLAN explicitly listed `image_pipeline.py:327` and `lib/vertex_gemini_complete.py:61, 92` and `batch_ingest_from_spider.py:1248` as "do NOT touch — proves consistency". `lib/llm_client.py:51` was **not in the b3y exclusion list because b3y was scoped to embedding only**.
  - CLAUDE.md L520 quote: "production-recommended value is `GOOGLE_CLOUD_LOCATION=global` ... `gemini-embedding-2` is GA on global; `gemini-embedding-2-preview` is regional-only." Vision models (Gemini 2.5 Flash family) follow the same model-availability-by-endpoint rule. If the cron invocation does not export `GOOGLE_CLOUD_LOCATION=global`, the Vision-Gemini fallback hits `us-central1` and the same 404 → DocStatus.FAILED → PROCESSED-verification-RuntimeError chain that motivated b3y.
- **Mitigation in production today:** CLAUDE.md L520 says Hermes `~/.hermes/.env` "uses `global`" and `scripts/local_e2e.sh` post-b3y now defensively exports it. So today the bug is masked by env config. **But defense-in-depth — matching b3y's pattern across all four sister Vertex clients — would be a 2-line change.**
- **Why HIGH:** The exact bug fixed by b3y still exists in another file. If anyone removes `GOOGLE_CLOUD_LOCATION` from `~/.hermes/.env`, the Vision-Gemini fallback breaks the same way embedding did. The `image_pipeline.py:327` Vertex-aware path is **dead code** (F-1) so it doesn't help.
- **Fix scope:** 1 line + 1 test, mirroring b3y. ~0.5 h.
- **Quick type:** Atomic 1-line default change + assertion update.
- **Citation:** `lib/llm_client.py:51` (the bad default); `lib/vision_cascade.py:436-451` (the production caller path); `lib/lightrag_embedding.py:141` (b3y-patched analog); `image_pipeline.py:319-339` (dead Vertex-aware path).

### MEDIUM (real but not urgent)

#### M-1 — Cascade-contract divergence: 429 counts toward circuit-breaker (vs CLAUDE.md "cascades immediately")

- **Title:** `_CIRCUIT_FAILURE_CODES` includes `RESULT_HTTP_429`, so a 429 increments the same 3-strike counter as 503 + timeout. CLAUDE.md L586 reads "A 429 cascades immediately to the next provider" which (paired with the immediately-following "4xx auth do NOT count" sentence) implies 429 should NOT count.
- **Evidence:** `lib/vision_cascade.py:46` (`_CIRCUIT_FAILURE_CODES = {RESULT_HTTP_503, RESULT_HTTP_429, RESULT_TIMEOUT}`); `lib/vision_cascade.py:296-298` (counter increment); CLAUDE.md L586 (contract).
- **Why MEDIUM:** Operationally indistinguishable from "cascades immediately" in healthy state, but in a SF-quota-rate-limit storm (3 consecutive 429s on SF), the circuit opens for SF and the entire batch's remaining images route via OR/Gemini until recovery probe. If CLAUDE.md interpretation (b) is correct, the circuit should NOT open and SF should be retried each image — leveraging momentary quota slots. Worst case under (a) interpretation: extra Gemini-RPD usage during quota window; not a leak, but unnecessary fallback.
- **Fix scope:** Either patch code (drop `RESULT_HTTP_429` from `_CIRCUIT_FAILURE_CODES`, add 1 test) OR clarify CLAUDE.md ("429 counts toward 3-strike unlike 4xx auth"). Either is ~0.5 h.

#### M-2 — `batch_validation_report.json` writer absent in production code

- **Title:** CLAUDE.md "Vision Cascade" L590 documents `batch_validation_report.json` as the cascade-evidence artifact; no production writer exists.
- **Evidence:** Grep across all `*.py` finds no `open("batch_validation_report.json", "w")` or equivalent in code paths reachable from cron. Only PLAN/CONTEXT references in `.planning/phases/14-regression-fixtures/`. `image_pipeline.py:617-626` populates `_last_describe_stats` in-memory only.
- **Why MEDIUM:** Operational blindness — the documented health check ("Gemini usage > 10% → investigate") relies on a file that doesn't exist. Stale-spec / unfinished-Phase-14 issue, not a runtime bug.
- **Fix scope:** Either resurrect Phase 14 wave 02 (`scripts/validate_regression_batch.py`, ~1-2 h) or add a minimal writer at the end of `describe_images` gated on `OMNIGRAPH_BATCH_VALIDATION_REPORT_PATH` env (~30 LOC, ~0.5 h).

#### M-3 — Silent SiliconFlow empty-body cost-leak

- **Title:** SF HTTP 200 with empty `content` is recorded as success and billed.
- **Evidence:** `lib/vision_cascade.py:381-382`: `content = resp.json()["choices"][0]["message"]["content"] or ""; return content.strip()`. Empty string flows up through `_call_siliconflow` → `cascade.describe` → `image_pipeline.py:574-575` (`result[path] = cres.description; vision_success += 1`) → `provider_mix["siliconflow"] += 1`. No length check.
- **Why MEDIUM:** Direct cost-leak path on the only paid provider. Frequency unknown (no observability — there is no per-image `desc_chars` minimum-threshold alert). Each occurrence: ¥0.0013 charged + empty entity sub-doc in LightRAG. Likely rare today (Qwen3-VL-32B is reliable), but the silent-success classification is the dangerous part.
- **Fix scope:** ~5-10 LOC at `lib/vision_cascade.py:381-382, 428-429`. Test scope: 2 unit tests. ~1 h total.

### LOW (cleanup / hygiene)

#### L-1 — Module-global mutable state `_last_describe_stats` documented as "not thread-safe"

- **Evidence:** `image_pipeline.py:84` (`_last_describe_stats: dict | None = None`); comment at lines 80-83 acknowledges "not thread-safe — single-ingest-at-a-time assumption matches current batch orchestrator".
- **Why LOW:** Documented assumption is true today (batch_ingest_from_spider runs articles serially); becomes a bug if/when the orchestrator goes concurrent. No fix needed today — documented limitation.
- **Fix scope:** N/A unless concurrency lands. Then: thread-local or move into a context var.

#### L-2 — Dead `_describe_via_gemini` (line 327) has CORRECT Vertex location default; live `lib/llm_client.py:51` does not

- **Evidence:** `image_pipeline.py:327` (correct `"global"` default in dead path); `lib/llm_client.py:51` (wrong `"us-central1"` in live path). Same author (LDEV-06 added the dead path; b3y fixed embedding but skipped llm_client).
- **Why LOW:** Subset of F-2; called out separately because the visible-but-dead correct code is a confusion source for code reviewers.
- **Fix scope:** Subsumed by F-1 (delete dead code) + F-2 (fix live code).

#### L-3 — `OMNIGRAPH_VISION_SKIP_PROVIDERS` parsed in two places

- **Evidence:** Primary parsing at `image_pipeline.py:481-486`. `tests/unit/test_vision_skip_providers.py` exercises that parse. No second parser in production code, but `tests/integration/test_vision_cascade_e2e.py:282` calls `from image_pipeline import describe_images` and exercises the same parse — so the test coverage is correct, only one parser.
- **Why LOW:** Minor — no real duplication. Down-grading from initial finding to "informational only".
- **Fix scope:** None.

---

## 7. Cross-cutting issues

### XC-1 — F-1 + F-2 + L-2 form a "live bug masked by visible-dead correct code" pattern

The dead `_describe_via_gemini` at `image_pipeline.py:306-349` LOOKS like the production Vertex Vision path. Its `GOOGLE_CLOUD_LOCATION` default is `'global'` (correct). This makes any reviewer scanning for the b3y-class bug across the repo (e.g. `grep -n "GOOGLE_CLOUD_LOCATION" --include="*.py"`) see the correct line first and miss the wrong line in `lib/llm_client.py:51`. **This is a maintenance hazard, not just three independent findings.** Fixing F-1 (delete dead code) and F-2 (patch live code) together is the right shape; they should be one quick (or two ordered: F-1 then F-2 to make F-2 obvious in `git blame`).

### XC-2 — `batch_validation_report.json` doc-vs-code drift extends across `image_pipeline.py` ↔ `lib/vision_cascade.py.total_usage()` ↔ never-built `validate_regression_batch.py`

CLAUDE.md describes the file at L590; `lib/vision_cascade.py:190-195` exposes `total_usage()` as the data source; no consumer writes the file. Three modules (vision_cascade as producer, image_pipeline as orchestrator, batch_ingest_from_spider as caller) have the data but neither flushes it. Either resurrect the Phase 14 plan or modify CLAUDE.md to remove the reference. Operational doc / code drift item.

---

## 8. Async + timeout observations (A6)

- **Per-image vision timeout:** SiliconFlow 60s (`lib/vision_cascade.py:374`); OpenRouter 30s (`lib/vision_cascade.py:422`); Gemini-Vision via `lib.generate_sync` — no explicit timeout, inherits SDK default.
- **Reset-on-provider-switch:** Each provider gets a fresh `requests.post(timeout=...)` per image. There is NO per-image global elapsed-time cap — if SF hits 60s timeout, OR runs another 30s, Gemini runs more, total per-image wall could reach 90-180s before failure-cascade gives up. Note: `RESULT_TIMEOUT` counts toward circuit-breaker, so 3 timeouts in a row open the circuit; reasonable bound.
- **Vs. CLAUDE.md 2026-05-05 #5 (the anchor lesson):** `OMNIGRAPH_LLM_TIMEOUT_SEC=1800` for LLM (`lib/vertex_gemini_complete.py:62, 194-196`). Vision per-provider 30-60s. Ratio is 30-60×, exactly as the lesson predicted. **No proportional-timeout work has landed. Still a v3.5 candidate.**
- **Task lifecycle vs p1n drain:** `image_pipeline.describe_images` is **synchronous** (`def`, not `async def`). It is called from `ingest_wechat._vision_worker_impl` which is `async`; the worker spawns `describe_images` via `asyncio.to_thread` (not directly verified — but the call site at `ingest_wechat.py:467` reads `descriptions = describe_images(paths_list) if paths_list else {}` synchronously, which would block the event loop unless wrapped). **Open question for §12.** The drain helper at `lib.vision_tracking.drain_vision_tasks` operates on the spawn-side `_VISION_TASKS` set (populated at `ingest_wechat.py:1336`) — it does not need `image_pipeline` to expose anything; the contract is one-way (worker registers itself, drainer pops them).

---

## 9. Test coverage gap (A7)

| Test file | Cases | Covers |
|-----------|-------|--------|
| `tests/unit/test_image_pipeline.py` | 22 | Download success/failure, localize, batch dispatch, sleep config, filter dim thresholds (×7), per-image error isolation, JSON-lines emission (filtered_too_small + size_read_failed), get_last_describe_stats, emit_batch_complete shape. |
| `tests/unit/test_image_pipeline_cascade.py` | 12 | `describe_images` uses VisionCascade; cascade order; balance-check skip env; balance warning emission; low-balance switch; balance-error non-fatal; all-providers-429 batch stop; empty-paths skip; gemini-share-high alert; circuit-open alert; new stats keys; mid-batch recheck. |
| `tests/unit/test_vision_cascade.py` | 15 | Construct order; dataclass frozen; status path; existing-JSON load; SF success records; 503 falls through; 3-consecutive 503 opens circuit; recovery probe after 10 skipped; 401 NOT counted; all-providers-429 raises stop-batch; timeout counts; persist atomic; per-image log lines; cascade order constant. |
| `tests/unit/test_vision_skip_providers.py` | 6 | OMNIGRAPH_VISION_SKIP_PROVIDERS parsing variants. |
| `tests/integration/test_vision_cascade_e2e.py` | (not enumerated in this audit) | E2E cascade integration. |
| `tests/integration/test_image_pipeline_golden.py` | (not enumerated) | Golden-file localize / save-with-images. |

**Gaps identified:**
- **No test asserts "429 should NOT count toward circuit-breaker"** (M-1 contract gap) — `test_401_auth_not_counted_as_circuit_failure` (line 216) handles 4xx; no symmetric 429 test. If interpretation (b) is correct, this is uncovered. If (a) is correct, the existing `test_three_consecutive_503_opens_circuit` (line 169) tests 503 only — there is no `test_three_consecutive_429_opens_circuit` to lock in current behavior either.
- **No test asserts SF empty-body 200 → cascades to next provider** (M-3 cost-leak) — current behavior counts as success; no test exists.
- **No test asserts `batch_validation_report.json` schema** (M-2) — file is never written; phase 14 plan unbuilt.
- **No test exists for the dead `_describe_via_*` paths** (F-1) — appropriate, since they're dead. Confirms no caller, indirectly.
- **No test for vision-vs-LLM timeout proportionality** (anchor lesson 2026-05-05 #5) — appropriate since it's a v3.5 candidate, but worth noting.

**Coverage summary:** Test surface is dense for the live cascade engine (`lib/vision_cascade.py` has 15 unit tests + integration). It is **NOT dense around the contract gaps** (M-1, M-3, M-2 each lack the locking test). Adding 3-4 tests during M-1/M-3/M-2 fixes would close the gap.

---

## 10. Recommended fix-quick sequence

| # | Quick | Files | Hours | Risk | Depends on |
|---|-------|-------|-------|------|------------|
| Q1 | F-1 dead-code purge: delete `_describe_via_*` (98 LOC) | `image_pipeline.py` | ~0.5 | zero (no callers) | — |
| Q2 | F-2 `lib/llm_client.py:51` location default `us-central1`→`global` (mirror b3y) | `lib/llm_client.py` + 1 test | ~0.5 | low (matches b3y pattern; unit-tested) | should follow Q1 to make F-2 obvious in `git blame` |
| Q3 | M-3 SF empty-body validation in `lib/vision_cascade.py:381-382, 428-429` | `lib/vision_cascade.py` + 2 tests | ~1.0 | low (defensive cascade-on-empty) | independent |
| Q4 | M-1 cascade-contract clarification (CLAUDE.md text fix OR `_CIRCUIT_FAILURE_CODES` patch + test) | `lib/vision_cascade.py:46` OR `CLAUDE.md` | ~0.5 | low | requires user decision (which interpretation is canonical) |
| Q5 | M-2 minimal `batch_validation_report.json` writer (env-gated) | `image_pipeline.py:617-626` (extend) | ~1.5 | low | independent |

**Total cleanup:** ~4 h across 4-5 quicks. Q1+Q2 should be paired (XC-1). Q3 is highest-cost-impact. Q4 needs user input. Q5 closes the longest-standing doc/code gap.

---

## 11. Module verdict

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| **Pollution score** | **MEDIUM** | 98 LOC dead code (15% of file) + one ⚠⚠ god function (`describe_images`, 222 LOC). Live code is well-structured; dead code is the polluter. |
| **Cost-leak risk** | **MEDIUM** | M-3 silent SF empty-body cost-leak is real but likely low-frequency. M-2 absent `batch_validation_report.json` is operational-blindness, not a leak. No gross hemorrhage observed. |
| **Hygiene verdict** | **`soft-gating`** | F-1 + F-2 are 2 HIGHs but neither breaks current cron given Hermes env config. Both deserve a follow-up quick before next refactor; neither is a release blocker. |
| **Cost-leak verdict** | **`soft-leak`** | M-3 is a real ¥-impact path; rate unknown without observability. Not a hemorrhage; not zero. |
| **Recommendation** | **Ship release; follow-up with Q1+Q2 paired hygiene quick + Q3 cost-leak quick before next refactor pass.** | Live production cron path is healthy (cascade dispatches correctly, balance check fires correctly, breaker opens correctly on 503/timeout). Findings are post-release hygiene + a defense-in-depth sister-fix to b3y. |

---

## 12. Open questions for user

1. **M-1 contract interpretation** — does "A 429 cascades immediately to the next provider" (CLAUDE.md L586) mean (a) move on quickly + still count toward 3-strike (current code), or (b) cascade WITHOUT incrementing the counter (symmetric with the 4xx-auth rule)? **User decision changes whether Q4 is a code patch or a doc patch.**
2. **CLAUDE.md L590 vs `image_pipeline.py:605` threshold drift** — doc says "Gemini usage below 10%; if >10%, investigate"; code alerts at 5% (`gemini_share > 0.05`). Which is canonical? Should the alert fire at 10%, or should the doc be updated to 5%?
3. **`describe_images` is sync but called from async worker** — `ingest_wechat._vision_worker_impl` (`async def`) calls `descriptions = describe_images(paths_list)` (sync) at `ingest_wechat.py:467`. **Is this wrapped in `asyncio.to_thread` upstream, or is it blocking the event loop?** Did not deep-audit `ingest_wechat.py` per audit scope. If unwrapped, this could be why p1n's `lib.vision_tracking.drain_vision_tasks` had to be conservative on `asyncio.gather` semantics. Worth a 15-minute spot check before any concurrency work touches this module.
4. **`OMNIGRAPH_VISION_SKIP_PROVIDERS` deviation from "hard-coded, not env-overridable"** — CLAUDE.md L582-584 says cascade order is hard-coded; `image_pipeline.py:481-486` (LDEV-06) lets env drop providers. Is this an acceptable weakening of the contract (for local-dev parity), or should it be documented in CLAUDE.md? If acceptable, recommend a 1-line note in CLAUDE.md "Vision Cascade" noting that `OMNIGRAPH_VISION_SKIP_PROVIDERS` can shrink the list (but not reorder).
5. **M-2 path forward** — resurrect Phase 14 wave 02 (full `validate_regression_batch.py` + 5 fixtures) OR ship a minimal writer hooked into `describe_images` end? Q5 is the latter; the former is multi-day work outside post-release hygiene scope.

---

**End of REVIEW.md.** No incomplete sections; all 7 audit angles (A1-A7) addressed; both verdicts explicit; A2 + A3 evidence density 17 file:line citations (target ≥ 8).
