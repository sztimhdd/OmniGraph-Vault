# Phase 13: Vision Cascade with Circuit Breaker (B2) - Context

**Gathered:** 2026-04-30
**Revised:** 2026-05-01 based on v3.1 closure (commit 2b38e98). Changes: (1) v3.1 Phase 8/10 dependencies updated from "pending" to "closed @ 2b38e98"; (2) **New locked decision D-BENCH-PRECHECK: Bench script precheck env-read bug fix** — absorbs v3.1 closure Finding 2 (`scripts/bench_ingest_fixture.py::_balance_precheck()` emits `balance_precheck_skipped` because its local `os.environ.get("SILICONFLOW_API_KEY")` fires before `~/.hermes/.env` is loaded into the process; the production Vision path reads the key correctly, verified by 28/28 SiliconFlow successes in the same Hermes run). See `docs/HERMES_E2E_VERIFICATION_v3.1_20260501.md` §5.
**Status:** Ready for planning
**Source:** PRD Express Path (`.planning/MILESTONE_v3.2_REQUIREMENTS.md` §B2) + v3.1 closure Finding 2 (routed per `docs/MILESTONE_v3.1_CLOSURE.md` §6.2)

<domain>
## Phase Boundary

**Delivers:** A resilient Vision pipeline that cascades through three providers (SiliconFlow → OpenRouter → Gemini) with per-provider state tracking, circuit breaker logic, and SiliconFlow balance monitoring. Core artifacts:
1. **`lib/vision_cascade.py`** — cascade orchestrator, provider state machine, circuit breaker
2. **`lib/siliconflow_balance.py`** (or similar) — balance check + estimation logic
3. **Integration into `image_pipeline.py`** — replace current cascade with new logic
4. **`provider_status` persistence** — piggy-backs on Phase 12 checkpoint dir (`~/.hermes/omonigraph-vault/checkpoints/_batch/provider_status.json`) so circuit state survives batch restarts

**Does NOT deliver:**
- Changes to single-image filtering logic (v3.1 Phase 8 IMG-01 — `min(w,h) >= 300`)
- Checkpoint infrastructure itself (Phase 12)
- Regression fixture to validate cascade (Phase 14)
- Operator runbook text (Phase 15)
- OpenRouter or Gemini client changes beyond wiring them into the cascade

**Dependencies:**
- Phase 12 (checkpoint directory structure + atomic writes) — `provider_status.json` persists under the checkpoint dir.
- v3.1 Phase 8 (`describe_images` / `filter_images` in `image_pipeline.py`) — **closed 2026-05-01 @ commit 2b38e98** (see `docs/MILESTONE_v3.1_CLOSURE.md` §4 Phase 8 scorecard: IMG-01..IMG-04 delivered).
- v3.1 Phase 10 async `_vision_worker_impl` and text-first `ainsert()` — **closed 2026-05-01 @ commit 2b38e98** (ARCH-01..ARCH-04 delivered).

**Current state (to be replaced):**
- `image_pipeline.py` currently cascades Gemini → SiliconFlow → OpenRouter (wrong order, per PRD)
- No per-provider failure tracking
- Single 503 from any provider propagates as exception, blocking article
- `scripts/bench_ingest_fixture.py::_balance_precheck()` (v3.1 artifact) has env-read bug — see D-BENCH-PRECHECK below

### D-BENCH-PRECHECK (2026-05-01): Bench precheck delegates to lib module (absorbs v3.1 Finding 2)

**Problem:** `scripts/bench_ingest_fixture.py::_balance_precheck()` at line ~253 reads `os.environ.get("SILICONFLOW_API_KEY", "").strip()` directly. When bench runs without `~/.hermes/.env` pre-loaded into the process env (e.g., fresh shell invocation), this returns empty → precheck returns `balance_precheck_skipped` even though the key exists in `~/.hermes/.env`. Confirmed by Hermes 2026-05-01 E2E run: 28/28 SiliconFlow Vision succeeded (production code-path loads key correctly) while precheck skipped.

**Locked decision:**
- `lib/siliconflow_balance.check_siliconflow_balance()` (new in 13-01) is the SOURCE OF TRUTH for balance checks. It uses the same env-loading mechanism as `config.py` — import `config` at module load so `~/.hermes/.env` is auto-sourced into `os.environ` before any key reads.
- `scripts/bench_ingest_fixture.py::_balance_precheck()` is refactored to DELEGATE to `lib.siliconflow_balance.check_siliconflow_balance()` — no direct `os.environ` reads, no re-implementation of the HTTP call, no duplication of error classification. The bench script keeps its four branches (`balance_precheck_skipped`, `balance_warning status=ok`, `balance_warning status=insufficient_for_batch`, `balance_precheck_failed`) as a thin mapper over the lib call.
- Regression test: run `DEEPSEEK_API_KEY=dummy SILICONFLOW_API_KEY=<test> python scripts/bench_ingest_fixture.py --fixture test/fixtures/gpt55_article/` with `~/.hermes/.env` absent — precheck MUST return `balance_warning` (not `balance_precheck_skipped`). Without the env loaded, the process env fallback should still resolve the key passed on the command line.
- **Correct-by-construction guarantee:** since `lib.siliconflow_balance` imports `config` (which loads `~/.hermes/.env`), any caller of `check_siliconflow_balance()` automatically gets the env loaded. Future callers cannot reproduce this bug unless they bypass the lib module.

</domain>

<pre_execution_checks>
## Pre-execution Checks (operational prerequisites — NOT code/plan constraints)

These are operator responsibilities that must be satisfied before `/gsd:execute-phase 13` begins. They don't appear as plan tasks because they're account/billing state, not software.

### SiliconFlow balance — MUST be ≥ ¥100 before execute kicks off

**Current state (2026-05-01, pre-execute):** `chargeBalance = -¥56.07` (overdrawn). Verified via direct `curl https://api.siliconflow.cn/v1/user/info` in Hermes v3.1 E2E (see `docs/HERMES_E2E_VERIFICATION_v3.1_20260501.md` §5).

**Why it matters for Phase 13:**
- Circuit-breaker regression tests (13-03) deliberately exercise 503/429/timeout paths to validate cascade fallback. If SiliconFlow is in a real quota-exhaustion state due to negative balance, the test will hit the **billing** edge instead of the **circuit-breaker** edge, invalidating the test signal.
- CASC-06 balance-monitoring code paths need a FUNCTIONING account to exercise — not a depleted one.
- The fix-by-construction in D-BENCH-PRECHECK solves the env-read bug; it does NOT solve "account is overdrawn".

**Required action before execute:**
1. Top up SiliconFlow account to ≥ ¥100 (covers 5× full regression run at ¥0.0013/image × ~28 images/article × 5 fixtures ≈ ¥0.18 per dry run, with headroom for accidental batch triggers during integration testing).
2. Verify: `curl -s https://api.siliconflow.cn/v1/user/info -H "Authorization: Bearer $SILICONFLOW_API_KEY" | jq '.data.chargeBalance'` returns positive float.
3. Document the top-up date/amount in `.planning/phases/13-vision-cascade/13-VERIFICATION.md` (phase 13 verification log) at execute-phase kickoff.

**If skipped:** 13-03 integration tests will emit false-positive circuit-breaker hits. The cascade itself will work in production (falls through to OpenRouter + Gemini fallbacks) but the test evidence will be noisy — expect re-runs.

</pre_execution_checks>

<decisions>
## Implementation Decisions (from PRD §B2)

### Cascade Order (CASC-01) — LOCKED VERBATIM

1. **Primary:** SiliconFlow Qwen3-VL-32B (¥0.0013/image, reliable paid tier, best quality open-source)
2. **Fallback 1:** OpenRouter GLM-4.5V ($0.0001/image, cheapest backup)
3. **Fallback 2:** Gemini Vision (free tier with key rotation, 500 RPD; LAST resort when paid services fail/depleted)

**Rationale:** SiliconFlow = paid + reliable → primary; OpenRouter = paid + cheap → cost-effective fallback; Gemini = free but rate-limited → last-resort when paid providers exhausted.

### Provider State Tracking (CASC-02) — LOCKED

**Schema:**
```python
provider_status = {
    "siliconflow": {
        "failures": 0,                    # Consecutive failure count (reset on success)
        "last_error": "...",              # Last error message (for observability)
        "circuit_open": False,            # True = skip this provider for rest of batch
        "next_retry_at": None,            # datetime for recovery retry (None = never scheduled)
        "total_attempts": 0,              # Cumulative for batch-end report
        "total_successes": 0,
        "total_failures": 0,
    },
    "openrouter": { ... },
    "gemini": { ... },
}
```

**Persistence:**
- Saved to `~/.hermes/omonigraph-vault/checkpoints/_batch/provider_status.json` at batch start
- Atomic writes (reuse `lib/checkpoint.py::_atomic_write` from Phase 12)
- Reset to defaults on new batch run
- Loaded at batch start IF file exists (for resume scenario) — per-batch semantics, not per-article

### Circuit Breaker Logic (CASC-03) — LOCKED

- **Trigger:** 3 consecutive 503/timeout errors from one provider → `circuit_open = True`
- **Action while open:** Skip that provider; fall through to next in cascade
- **Recovery probe:** After **10 images skipped** from a provider, attempt ONE retry image; if it succeeds, reset `circuit_open = False` and `failures = 0`
- **Fallback chain terminus:** If all 3 providers have `circuit_open = True`, the LAST resort is Gemini (never give up on user data — even if counter says open, try once anyway with Gemini on the final image)

### Error Code Classification (CASC-04) — LOCKED

| HTTP / Exception | Circuit counter | Cascade action |
|---|---|---|
| `429 Quota exhausted` | YES (counts as failure) on SiliconFlow / OpenRouter; on all-429 → stop batch with warning | Immediately try next provider |
| `503 Service unavailable` | YES (counts as failure) | Try next provider |
| `Timeout` (network or server) | YES (counts as failure) | Try next provider |
| `4xx Auth/validation` (401, 403, 422) | NO (don't count as circuit failure — permanent) | Log permanent error; try next provider; log to batch report |
| Other exceptions | NO (log only) | Try next provider |
| `200 success` | Reset `failures = 0` | Return description |

**Special rule:** If all 3 providers return 429 in sequence on the SAME image, stop the batch entirely with a clear warning + trigger a balance check (CASC-06).

### Logging Format (CASC-05) — LOCKED

**Per-image log (structured, one line):**
```
image_id=img_007 provider=siliconflow attempt=1/3 result=503 latency_ms=2340 msg="upstream timeout"
image_id=img_007 provider=openrouter attempt=2/3 result=200 latency_ms=1230 desc_chars=180
```

**Per-batch aggregate (at batch end):**
```
VISION CASCADE SUMMARY
  total_images: 282
  described:    275 (97.5%)
  failed:       7 (2.5%)
  providers:
    siliconflow: 250 (88.7%)  attempts=252 successes=250 failures=2
    openrouter:  23 (8.2%)    attempts=32  successes=23  failures=9
    gemini:      2 (0.7%)     attempts=3   successes=2   failures=1
  circuit_opens: openrouter=1 (recovered after 12 skipped images)
```

**Alerts:**
- If Gemini used for >5% of images → warn "upstream provider issues detected" (signal)
- If any provider circuit still `open` at batch end → warn "transient or quota problem, review provider_status.json"

### SiliconFlow Balance Management (CASC-06) — LOCKED

**Balance API:** `GET https://api.siliconflow.cn/v1/user/info` with `Authorization: Bearer $SILICONFLOW_API_KEY` → JSON with `data.balance` field (CNY)

**Pre-batch check:**
- Fetch balance at batch start
- Estimate per-image cost: `estimated_cost = remaining_articles × avg_images_per_article × 0.0013`
- If `balance < estimated_cost` → structured warning "SiliconFlow balance ¥X.XX insufficient for ¥Y.YY estimated spend; top up or expect fallback to OpenRouter"

**Mid-batch monitoring:**
- Every 10 images, re-fetch balance (light HTTP call)
- If trajectory predicts depletion before batch end → warn
- If `balance < ¥0.05` → switch ALL subsequent images to OpenRouter (avoid partial batch where half images have SiliconFlow descriptions and half have OpenRouter)

**Quota exhaustion handling:**
- If SiliconFlow returns 429 AND balance < ¥0.05 → mark circuit open for SiliconFlow; continue batch on OpenRouter only

### Integration into `image_pipeline.py` (Claude's Discretion on line-level edits)

**Current call signature (approximate):** `describe_image(url: str, image_bytes: bytes, providers: list[str]) -> str`

**New signature (proposed):**
```python
def describe_image_cascade(
    image_id: str,
    image_bytes: bytes,
    cascade: VisionCascade,  # stateful; tracks provider_status
) -> CascadeResult:
    """
    Returns:
        CascadeResult(description: str, provider_used: str, attempts: list[AttemptRecord])
    """
```

Planner decides final signature; key constraints:
- Cascade state is PASSED IN (not module-global); cascade instance is constructed per batch
- Description returned along with metadata (provider used, attempt log) for per-image structured log
- No exceptions escape the cascade — all errors caught, logged, and either resolved by fallback or reported as `failed=True`

### Claude's Discretion

- **Internal abstractions** in `lib/vision_cascade.py` — state machine, Result dataclasses
- **HTTP client library** — stick with existing (`requests`, `httpx`, or whatever is in project); don't introduce new deps
- **Balance-check cadence** — PRD says "every 10 images"; planner can tune if evidence suggests otherwise
- **Recovery probe cadence** — PRD says "after 10 images skipped"; planner can tune
- **Test structure** — mock each provider to simulate 503/429/timeout sequences

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source of Truth
- `.planning/MILESTONE_v3.2_REQUIREMENTS.md` §B2 — verbatim requirements
- `.planning/MILESTONE_v3.2_REQUIREMENTS.md` §Acceptance Criteria Gate 2 — end-to-end acceptance

### Dependency Interfaces
- Phase 12 `lib/checkpoint.py` — `_atomic_write()` helper + checkpoint directory root
- v3.1 Phase 8 `image_pipeline.describe_images()` / `filter_images()` — current cascade entry point (to be replaced)
- v3.1 Phase 10 `_vision_worker()` — async worker that calls describe function

### External APIs (planner researches)
- https://docs.siliconflow.cn/api — Vision endpoint + user/info endpoint
- https://openrouter.ai/docs — GLM-4.5V model endpoint
- Existing `lib/api_keys.py` + `lib/llm_client.py` — Gemini key rotation patterns (reuse for Gemini Vision as last-resort)

### Existing Files to Read
- `image_pipeline.py` (full file — current cascade; flagged by CLAUDE.md as buggy order)
- `lib/api_keys.py` — OMNIGRAPH_GEMINI_KEY + rotation patterns
- `lib/llm_client.py` — existing Gemini client wrapping
- `lib/rate_limit.py` — existing AsyncLimiter per-model singletons (may wire SiliconFlow/OpenRouter in too)

</canonical_refs>

<specifics>
## Specific Ideas

### Cascade State Machine (illustrative, planner refines)

```python
class VisionCascade:
    def __init__(self, providers_in_order: list[str], checkpoint_dir: Path):
        self.providers = providers_in_order  # ["siliconflow", "openrouter", "gemini"]
        self.status = self._load_or_init_status(checkpoint_dir)
        self.checkpoint_dir = checkpoint_dir
        self.skipped_since_last_probe = {p: 0 for p in providers_in_order}

    def describe(self, image_id: str, image_bytes: bytes) -> CascadeResult:
        attempts = []
        for provider in self.providers:
            if self.status[provider]["circuit_open"]:
                self.skipped_since_last_probe[provider] += 1
                if self.skipped_since_last_probe[provider] >= 10:
                    # Recovery probe
                    self.skipped_since_last_probe[provider] = 0
                    if self._probe(provider):
                        self.status[provider]["circuit_open"] = False
                        self.status[provider]["failures"] = 0
                    else:
                        continue  # stay open, skip
                else:
                    continue

            result = self._call_provider(provider, image_bytes)
            attempts.append(AttemptRecord(provider, result))
            if result.is_success:
                self.status[provider]["failures"] = 0
                self.status[provider]["total_successes"] += 1
                self._persist()
                return CascadeResult(description=result.description, provider_used=provider, attempts=attempts)
            elif result.is_circuit_failure:
                self.status[provider]["failures"] += 1
                if self.status[provider]["failures"] >= 3:
                    self.status[provider]["circuit_open"] = True
                self._persist()

        # All providers failed or circuit-open
        return CascadeResult(description=None, provider_used=None, attempts=attempts, failed=True)
```

### Balance Check Reference

```python
def check_siliconflow_balance() -> Decimal:
    resp = requests.get(
        "https://api.siliconflow.cn/v1/user/info",
        headers={"Authorization": f"Bearer {os.environ['SILICONFLOW_API_KEY']}"},
        timeout=5.0,
    )
    resp.raise_for_status()
    return Decimal(resp.json()["data"]["balance"])
```

### Acceptance Check Commands (for Phase 14 to encode as fixtures)

```bash
# 1. Mock SiliconFlow to return 503; cascade uses OpenRouter
# Expected: 200 success via OpenRouter, attempts=[siliconflow→503, openrouter→200]

# 2. Three consecutive 503s from SiliconFlow → circuit opens; subsequent images skip SiliconFlow
# Expected: 4th+ images attempts=[openrouter→200]

# 3. Balance < estimated cost → warning emitted pre-batch
grep "SiliconFlow balance" logs/batch.log

# 4. provider_status.json persisted
cat ~/.hermes/omonigraph-vault/checkpoints/_batch/provider_status.json
```

</specifics>

<deferred>
## Deferred Ideas (out of scope)

- **Dynamic provider addition** (e.g., adding a 4th Vision provider later) — YAGNI; 3 providers is the design
- **Multi-tenant balance monitoring** (separate budgets per pipeline) — single operator, single balance
- **Automated top-up** (trigger SiliconFlow refill via API) — manual operator task
- **Vision description quality scoring / A/B comparison** across providers — not in this phase; descriptions are trusted as-is
- **Retry backoff tuning** per provider (exponential vs linear) — simple 3-strike rule is the design
- **Provider-specific prompt tuning** — each provider gets the same Vision prompt; differential prompting deferred

</deferred>

---

*Phase: 13-vision-cascade*
*Context gathered: 2026-04-30 via PRD Express Path*
