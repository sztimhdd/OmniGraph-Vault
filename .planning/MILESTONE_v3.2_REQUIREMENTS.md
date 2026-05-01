# Milestone v3.2 — Batch Reliability + Infra (Milestone B + C)

**Revision history:** v1 (2026-04-30, initial plan commit 0bdec26) → **v2 (2026-05-01, post v3.1 closure alignment):** absorbed v3.1 closure findings + baseline. Specific changes:
- Predecessor status: "must be gate-passing first" → "closed 2026-05-01 @ commit 2b38e98 (26/26 REQs delivered; E2E-02 gate revised <120s → <600s based on real baseline)"
- Phase 17 default BATCH_TIMEOUT 3600s → 28800s (8h); worked example rewritten with 441s/article Hermes baseline
- Phase 12: added locked decision D-SUBDOC — sub-doc lifecycle moves into checkpoint state machine (absorbs v3.1 closure Finding 1: `vision_worker_drain_timeout=120s` insufficient, only 2/7 sub-doc chunks completed in Hermes prod run)
- Phase 13: added locked decision D-BENCH-PRECHECK — `lib/siliconflow_balance.py` imports `config` at module load; `scripts/bench_ingest_fixture.py::_balance_precheck()` delegates to lib (absorbs v3.1 closure Finding 2: env-read bug in bench precheck)
- Phase 14-02 validate script: drain timeout formula aligned with Phase 9, error renamed `VisionDrainTimeout` → `SubDocDrainTimeout`

## Overview

**Milestone Goal:** Enable Phase 5 Wave 1 (RSS + KOL batch ingestion, 56+ articles) to complete reliably with partial failure recovery, intelligent fallback, comprehensive regression validation, and long-term infrastructure for quota isolation.

**Predecessor:** Milestone v3.1 (Single-Article Ingest Stability) — **closed 2026-05-01 @ commit 2b38e98** (see `docs/MILESTONE_v3.1_CLOSURE.md`). 26/26 REQs delivered on both dev and production stacks; E2E-02 gate revised to <600s based on real Hermes DeepSeek baseline of 441s/article.

**Success Criteria:**
- 56+ article batch completes with zero unhandled exceptions
- Transient failures (Vision 503, network timeouts) are auto-recovered without re-scraping prior articles
- 3–5 regression fixtures (multi-image, sparse-image, text-only profiles) all pass
- CLAUDE.md and operator runbook document deployment, monitoring, and manual intervention steps
- SiliconFlow balance warnings trigger at key checkpoints
- Vertex AI SA credentials prepared and quota isolation design documented (implementation deferred to post-Milestone B)

---

## Context from Hermes Diagnostic

**Phase 5 Wave 0b Current State:**
- 56/282 KOL articles killed by embedding 429 quota exhaustion
- Single article killed at 1882s, batch timeout at 1200s
- Batch ingestion has no recovery path — one 503 kills entire batch
- No staged checkpoint — re-running batch always re-scrapes and re-processes from scratch

**Hermes Recommendation:**
- Decouple Milestone A (single-article stability) from Milestone B (batch reliability)
- Batch reliability depends on Milestone A being gate-passing first
- Checkpoint/resume is the single highest-leverage feature for batch reliability

---

## Scope

### B1 — Checkpoint/Resume Mechanism

**Objective:** Persist article ingestion state at stage boundaries so transient failures can resume without re-scraping or re-processing prior stages.

**Requirements:**

1. **Stage Boundaries** (5 checkpoints per article):
   - `scrape` → HTML cached at `~/.hermes/omonigraph-vault/checkpoints/{article_hash}/01_scrape.html`
   - `classify` → Classification result (depth, topics, rationale) cached at `{article_hash}/02_classify.json`
   - `image_download` → Local images cached at `{article_hash}/03_images/` + manifest at `03_manifest.json`
   - `text_ingest` → LightRAG ainsert completion flag at `04_text_ingest.done`
   - `vision_worker` → Per-image Vision descriptions cached at `05_vision/{image_id}.json` (no `.done` needed — async worker, fire-and-forget)

2. **Checkpoint Format:**
   ```
   checkpoints/
   ├── {article_hash}/
   │   ├── metadata.json          # {url, title, created_at, updated_at}
   │   ├── 01_scrape.html
   │   ├── 02_classify.json       # {depth, topics, rationale, model, timestamp}
   │   ├── 03_images/
   │   │   ├── img_000.jpg
   │   │   ├── img_001.png
   │   │   └── manifest.json      # [{url, local_path, dimensions, filter_reason}]
   │   ├── 04_text_ingest.done
   │   └── 05_vision/
   │       ├── img_000.json       # {provider, description, latency_ms, timestamp}
   │       └── img_001.json
   ```

3. **Resume Logic:**
   - On `ingest_article(url, rag=rag)` call: check if `checkpoints/{article_hash}/` exists
   - If exists, load `metadata.json`:
     - If `04_text_ingest.done` exists → article already ingested; skip to Vision worker cleanup
     - If only up to `03_manifest.json` exists → resume from text_ingest step; skip scrape + classify + image-download
     - If only up to `02_classify.json` exists → resume from image-download step; skip scrape + classify
     - If only up to `01_scrape.html` exists → resume from classify step; skip scrape
   - If checkpoint dir missing → start fresh (full 5-stage pipeline)

4. **Atomicity:**
   - Each checkpoint file written atomically: write to `.tmp`, then `os.rename()` (same pattern as `canonical_map.json`)
   - Checkpoint directory creation is safe (idempotent)
   - No cleanup between retry attempts — reuse checkpoints for fast resume

5. **Manual Reset:**
   - `python scripts/checkpoint_reset.py --hash {article_hash}` removes checkpoint dir for that article (force re-run all stages)
   - `python scripts/checkpoint_reset.py --all` removes entire `checkpoints/` directory (full batch restart)
   - `python scripts/checkpoint_status.py` lists all in-flight checkpoints and their current stage

---

### B2 — Vision Cascade with Circuit Breaker

**Objective:** Intelligent fallback from SiliconFlow → OpenRouter → Gemini (last-resort) with per-provider failure tracking and circuit breaker logic.

**Current State (Milestone A):**
- Image pipeline cascades Gemini → SiliconFlow → OpenRouter (wrong order)
- No failure tracking per provider
- Single 503 from any provider propagates as exception, blocking entire article

**Requirements:**

1. **Cascade Order (corrected):**
   - **Primary:** SiliconFlow Qwen3-VL-32B (¥0.0013/image, best quality open-source)
   - **Fallback 1:** OpenRouter GLM-4.5V ($0.0001/image, cheapest)
   - **Fallback 2:** Gemini Vision (free tier with key rotation, 500 RPD; last resort when paid services fail/depleted)

2. **Provider State Tracking:**
   ```python
   # Persist per-batch:
   provider_status = {
       "siliconflow": {"failures": 0, "last_error": "...", "circuit_open": False, "next_retry_at": None},
       "openrouter": {"failures": 0, "last_error": "...", "circuit_open": False, "next_retry_at": None},
       "gemini": {"failures": 0, "last_error": "...", "circuit_open": False, "next_retry_at": None},
   }
   # Save to batch_run_state.json at batch start
   ```

3. **Circuit Breaker Logic per Provider:**
   - **Trigger:** 3 consecutive 503/timeout errors from one provider → `circuit_open = True`
   - **Action:** Skip that provider for all subsequent images in this batch
   - **Recovery:** After 10 images skipped from a provider, attempt one retry image; if succeeds, reset `circuit_open = False`
   - **Fallback chain:** If all providers open, final image uses Gemini (never give up on user data)

4. **Error Codes Handled:**
   - `429 (Quota exhausted)` → If SiliconFlow, try next provider immediately; if all 429, stop batch with warning + balance check
   - `503 (Service unavailable)` → Count as circuit breaker failure; cascade to next
   - `Timeout` → Count as circuit breaker failure; cascade to next
   - `4xx (Auth/validation)` → Don't count as circuit failure; log as permanent error; cascade to next
   - Other exceptions → Log, cascade to next

5. **Logging & Monitoring:**
   - Per-image log: `{image_id} {provider} attempt 1/3 → 503 → trying next provider`
   - Per-batch aggregate: `{total_images} described: SiliconFlow=X, OpenRouter=Y, Gemini=Z (circuit_opens=M)`
   - Alert if Gemini is used >5% of images (signals upstream provider issues)
   - Alert if any provider circuit still open at batch end (transient issue or quota problem)

6. **SiliconFlow Balance Management:**
   - Before batch starts: `GET /v1/user/info` → parse `balance`
   - Estimate per-image cost: `balance ÷ (avg_images_per_article × remaining_articles)` → warn if <¥0.10 per image
   - After every 10 images: re-check balance, warn if trajectory predicts depletion before batch end
   - If balance drops below ¥0.05: switch to OpenRouter for remaining images (avoid partial batch)

---

### B3 — Regression Test Fixtures

**Objective:** Validate batch pipeline against 3–5 distinct article profiles to catch regressions in image handling, timeout, and state management.

**Requirements:**

1. **Fixture Profiles** (in addition to existing `test/fixtures/gpt55_article/`):
   
   | Name | Image Count | Text Length | Characteristics | Hermes Issue Covered |
   |------|------------|------------|-----------------|-------------------|
   | `gpt55` | 28 | 4574 chars | Complex (baseline, from Milestone A) | — |
   | `sparse_image` | 3 | 8000 chars | Few images, long text (timeout @ LLM path) | Original #5, New #2 |
   | `dense_image` | 45 | 2000 chars | Many small images (<300px filter) | Original #2, #6, New #1 |
   | `text_only` | 0 | 3000 chars | No images (skip Vision entirely) | Edge case |
   | `mixed_quality` | 15 | 5000 chars | Mix of JPEG/PNG, some corrupted (fallback) | Vision cascade coverage |

2. **Fixture Location & Schema:**
   ```
   test/fixtures/
   ├── gpt55_article/
   │   ├── metadata.json
   │   ├── article.md
   │   └── images/
   ├── sparse_image_article/
   ├── dense_image_article/
   ├── text_only_article/
   └── mixed_quality_article/
   
   Each fixture/{metadata.json}:
   {
     "title": "...",
     "url": "...",
     "text_chars": 0000,
     "total_images_raw": 00,
     "images_after_filter": 00,
     "expected_chunks": 00,
     "expected_entities": 00,
     "notes": "..."
   }
   ```

3. **Batch Validation Script:**
   ```bash
   python scripts/validate_regression_batch.py \
     --fixtures test/fixtures/gpt55_article \
                 test/fixtures/sparse_image_article \
                 test/fixtures/dense_image_article \
                 test/fixtures/text_only_article \
     --output batch_validation_report.json
   ```

4. **Validation Report Schema:**
   ```json
   {
     "batch_id": "regression_2026-05-01_001",
     "timestamp": "2026-05-01T14:30:00Z",
     "articles": [
       {
         "fixture": "gpt55_article",
         "status": "PASS|FAIL|TIMEOUT",
         "timings_ms": {
           "scrape": 0,
           "classify": 1234,
           "image_filter": 45,
           "text_ingest": 12345,
           "vision_worker_start": 100
         },
         "counters": {
           "images_input": 28,
           "images_kept": 22,
           "chunks": 15,
           "entities": 47
         },
         "errors": []
       }
     ],
     "aggregate": {
       "total_articles": 5,
       "passed": 5,
       "failed": 0,
       "total_wall_time_s": 72,
       "batch_pass": true
     },
     "provider_usage": {
       "siliconflow": 110,
       "openrouter": 0,
       "gemini": 0
     }
   }
   ```

5. **CI Integration Readiness:**
   - Script returns exit code 0 on all-pass, 1 on any failure
   - Can be run in CI/CD after each phase
   - `batch_validation_report.json` saved to repo for trend analysis

---

### B5 — Vertex AI Infrastructure Preparation

**Objective:** Design and document the migration path from Gemini API free tier (quota coupling risk) to Vertex AI OAuth2 with optional cross-project quota isolation, so 429 errors in one service don't cascade to another.

**Context:**
- **Current Problem:** Embedding + LLM share same GCP project quota pool → one service's 429 kills entire batch
- **Long-term Solution:** Vertex AI paid tier with cross-project isolation
- **Milestone B Scope:** Design & documentation only; code integration deferred to post-Milestone B

**Requirements:**

1. **Migration Specification Document** (`docs/VERTEX_AI_MIGRATION_SPEC.md`):
   - **GCP Project Setup:**
     - List all required APIs to enable (Vertex AI, Generative AI)
     - Service account creation workflow (with IAM roles: `vertexai.editor`, `vertexai.admin`)
     - Naming convention: `omnigraph-embedding-sa`, `omnigraph-llm-sa` (if split projects)
   - **OAuth2 Token Management:**
     - How to obtain initial service account key and convert to OAuth2 token
     - Refresh token strategy (Vertex AI SDK handles auto-refresh)
     - Fallback plan if Vertex AI unavailable (stay on Gemini API key)
   - **Pricing Comparison:**
     - Gemini API free tier: 100 RPM embedding, 500 RPD vision, unlimited 1M tok/min LLM (but shared quota pool)
     - Vertex AI paid: ¥per-embedding, ¥per-vision (no quotas, just billing)
     - Recommendation: SiliconFlow for Vision (¥0.0013/img) + Vertex AI for embedding (if 100 RPM insufficient)
   - **Code Integration Roadmap** (deferred):
     - Sketch: `lib/vertex_ai_client.py` with `init_vertex_ai(project_id, location, service_account_path)` → returns OAuth2-backed client
     - Backward-compat: `lib/api_keys.py` tries Vertex AI first, falls back to Gemini API key

2. **Service Account Template** (`credentials/vertex_ai_service_account_example.json`):
   ```json
   {
     "type": "service_account",
     "project_id": "YOUR_PROJECT_ID",
     "private_key_id": "...",
     "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
     "client_email": "omnigraph-embedding-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com",
     "client_id": "...",
     "auth_uri": "https://accounts.google.com/o/oauth2/auth",
     "token_uri": "https://oauth2.googleapis.com/token",
     "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
     "client_x509_cert_url": "..."
   }
   ```
   Note: Template only (no real credentials).

3. **Documentation Updates:**
   - **CLAUDE.md § "Vertex AI Migration Path":**
     - Explain the free-tier quota coupling problem
     - Point to `docs/VERTEX_AI_MIGRATION_SPEC.md` for setup
     - Recommend: Use SiliconFlow for Vision (paid, no limits) + Gemini API key for embedding (free 100 RPM) until batch hits 429 ceiling
     - When to upgrade: If batch grows beyond 100 RPM embedding or 500 RPD vision, migrate to Vertex AI paid
   - **Deploy.md § "Recommended Upgrade Path":**
     - Production deployments should use Vertex AI OAuth2 + cross-project quota isolation
     - Dev/test: current API key is fine
     - Cost: estimate ¥/month for expected article volume

4. **Cost Estimation Tool** (`scripts/estimate_vertex_ai_cost.py`):
   ```bash
   python scripts/estimate_vertex_ai_cost.py --articles 282 --avg-images-per-article 25
   # Output: Estimated cost for 282 articles with 25 images/article:
   # - Embedding (Vertex AI): ¥xxx/month (vs ¥0 free tier)
   # - Vision (SiliconFlow): ¥xxx/month
   # - LLM (DeepSeek): ¥xxx/month
   # - Total: ¥xxx/month
   ```

---

### B4 — Documentation & Operator Runbook

**Objective:** Document deployment, recovery procedures, and monitoring points so humans can operate the batch pipeline without reading code.

**Requirements:**

1. **CLAUDE.md Additions** (project-level):
   - **Checkpoint Mechanism:** Explain stage boundaries, how to interpret checkpoint directory state, manual reset commands
   - **Vision Cascade:** Documented fallback order, circuit breaker thresholds, provider balance alerts
   - **SiliconFlow Balance Management:** Pre-batch checks, mid-batch monitoring, depletion scenario (what happens if balance hits 0 mid-batch)
   - **Batch Execution:** How to run batch with checkpoint resume vs. full restart
   - **Known Limitations:** Gemini 500 RPD limit, WeChat account throttle (50/batch + cooldown), Vertex AI future migration path

2. **Operator Runbook** (`docs/OPERATOR_RUNBOOK.md`):
   - **Pre-Batch Checklist:**
     ```
     [ ] SiliconFlow balance >= ¥1.00 (budget for 20+ images)
     [ ] DEEPSEEK_API_KEY set and valid
     [ ] OMNIGRAPH_GEMINI_KEY set and valid (Gemini fallback)
     [ ] SILICONFLOW_API_KEY set and valid
     [ ] OPENROUTER_API_KEY set and valid (optional, for fallback)
     [ ] test/fixtures/ validated with `validate_regression_batch.py`
     [ ] Previous batch checkpoint cleaned (if full restart desired)
     ```

   - **Batch Execution:**
     ```bash
     # Full batch from scratch
     python batch_ingest_from_spider.py --topics ai --depth 2 --reset-checkpoint
     
     # Resume from last checkpoint
     python batch_ingest_from_spider.py --topics ai --depth 2
     
     # Monitor progress
     watch -n 5 'python scripts/checkpoint_status.py | tail -20'
     ```

   - **Failure Scenarios & Recovery:**
     | Scenario | Signal | Recovery |
     |----------|--------|----------|
     | SiliconFlow 503 (transient) | Vision provider cascade log shows fallback | Auto-recovers; monitor balance next |
     | SiliconFlow balance depleted mid-batch | Balance warning + all Vision→Gemini | Accept degradation or pause batch for top-up |
     | DeepSeek 429 (quota) | Classification fails | Pause 60s, retry; if persistent, contact DeepSeek support |
     | Single article timeout (1200s kill) | `asyncio.wait_for` timeout error | Article marked failed in checkpoint; batch continues |
     | Network failure during image download | `RequestsException` | Auto-retry; if persists, checkpoint saved at `03_manifest`; resume skips re-download |
     | LightRAG ainsert crash | Corrupted graph state | `scripts/checkpoint_reset.py --hash {hash}` to force re-ingest; check LightRAG logs |

   - **Manual Intervention:**
     - To skip an article: `scripts/checkpoint_status.py` → find article_hash → `scripts/checkpoint_reset.py --hash {hash}` → re-run batch
     - To inspect checkpoint: `ls -la checkpoints/{article_hash}/` → read `metadata.json` to see last completed stage
     - To force full re-scrape: `rm -rf checkpoints/{article_hash}` → re-run (but respects WeChat throttle, so no speedup)

   - **Monitoring Points:**
     - Real-time: `watch 'python scripts/checkpoint_status.py'` (list in-flight articles + current stage)
     - Per-batch: Check `batch_validation_report.json` provider usage (% Gemini > 10% = issue)
     - Post-batch: Run `validate_regression_batch.py` to catch new regressions

3. **Deploy Context** (in Deploy.md or `docs/DEPLOY.md`):
   - **SiliconFlow Paid Tier vs Gemini Free:**
     - SiliconFlow: ¥0.0013/image, reliable, no 429 on paid tier
     - Gemini Vision: 500 RPD free (≈8.3 req/sec), 429 after exhaustion, infinite with paid Vertex AI
     - Trade-off: SiliconFlow is 50-100x cheaper per image but requires balance; Gemini free tier is capped but never errors on balance
   - **Vertex AI Infrastructure Plan (Milestone B.5):**
     - **Current State:** Gemini API key (free tier, 100 RPM embedding + 500 RPD vision, shared GCP project)
     - **Problem:** Embedding 429 couples with LLM 429 in same GCP project quota pool → batch killed
     - **Solution Design (no code changes in this milestone):**
       1. Create GCP Vertex AI project(s):
          - Option A (Recommended): Two projects: one for embedding (gemini-embedding-2), one for LLM (DeepSeek stays on-prem)
          - Option B: One Vertex AI project with separate service accounts for embedding vs. LLM with isolated quota
       2. Migrate from `OMNIGRAPH_GEMINI_KEY` (API key) to Vertex AI OAuth2 token
       3. Update `lib/api_keys.py` + `lib/llm_client.py` to support Vertex AI endpoint + service account rotation
       4. Backward-compat: Keep Gemini API key as fallback if Vertex AI unavailable
     - **Acceptance Criteria for this Milestone:**
       - [ ] `.planning/VERTEX_AI_MIGRATION_SPEC.md` documents: GCP project setup steps, service account naming convention, OAuth2 token refresh pattern, cost estimation per tier
       - [ ] `credentials/vertex_ai_service_account_example.json` template provided (no real creds in repo)
       - [ ] CLAUDE.md § "Vertex AI Migration Path" explains trade-off (free tier vs paid tier, per-project quota isolation vs cost)
       - [ ] Deploy.md links to migration spec as "Recommended Upgrade Path" for production deployments
     - **Timeline:** Vertex AI code integration deferred to post-Milestone B; design document + setup guide only for this milestone

---

## Acceptance Criteria

### Gate 0: Vertex AI Infrastructure Design Complete
- [ ] `docs/VERTEX_AI_MIGRATION_SPEC.md` documents GCP project setup, OAuth2 token management, pricing comparison
- [ ] `credentials/vertex_ai_service_account_example.json` template provided
- [ ] CLAUDE.md includes "Vertex AI Migration Path" section with problem statement + recommendation
- [ ] Deploy.md updated with upgrade path and cost estimation
- [ ] `scripts/estimate_vertex_ai_cost.py` script works (estimates cost for expected batch sizes)
- [ ] **No code changes required;** design is complete and documented

### Gate 1: Checkpoint/Resume Works End-to-End
- [ ] Single article with injected failure at stage 3 (image-download) resumes correctly at stage 4 (text-ingest)
- [ ] Checkpoint files are atomically written (no corrupted `.tmp` left behind on crash)
- [ ] `checkpoint_reset.py --hash` deletes checkpoint and full re-run succeeds
- [ ] Manual inspection of `checkpoint/{article_hash}/` matches documented schema

### Gate 2: Vision Cascade with Circuit Breaker
- [ ] SiliconFlow 503 → auto-cascade to OpenRouter without exception
- [ ] After 3 consecutive SiliconFlow 503s, circuit opens and SiliconFlow skipped for remaining images in batch
- [ ] Gemini is used only if both SiliconFlow and OpenRouter circuit-open
- [ ] `batch_validation_report.json` provider_usage reflects cascade attempts (e.g., `{"siliconflow": 110, "openrouter": 5, "gemini": 0}`)
- [ ] SiliconFlow balance warning triggers when balance < estimated remaining cost

### Gate 3: Regression Fixtures Pass
- [ ] All 5 fixtures complete without exception
- [ ] `batch_validation_report.json` shows `batch_pass: true`
- [ ] `dense_image_article` (45 images) successfully filters to expected count and all survive Vision
- [ ] `text_only_article` (0 images) skips Vision pipeline entirely (no null pointer errors)
- [ ] `mixed_quality_article` handles both JPEG and PNG without errors

### Gate 4: Documentation Complete
- [ ] CLAUDE.md contains Checkpoint Mechanism + Vision Cascade + SiliconFlow sections
- [ ] `docs/OPERATOR_RUNBOOK.md` covers Pre-Batch Checklist, Batch Execution, Failure Scenarios, Manual Intervention
- [ ] `docs/DEPLOY.md` updated with SiliconFlow paid tier notes and Vertex AI forward-looking section
- [ ] Runbook tested by operator (human walkthrough of at least one failure scenario recovery)

---

## Implementation Dependencies

```
Milestone A (Single-Article Ingest Stability) [PREREQUISITE — closed 2026-05-01 @ commit 2b38e98]
  ↓
Milestone B (Batch Reliability + Infra)
  ├─ B5 Vertex AI Infrastructure Prep [CAN RUN IN PARALLEL WITH B1–B4 — design/doc only]
  │   ↓ (no code changes; outputs: spec doc, template, cost estimation tool)
  ├─ B1 Checkpoint/Resume
  │   ↓ (data structure + resume logic)
  ├─ B2 Vision Cascade + Circuit Breaker
  │   ↓ (provider state tracking, uses checkpoint infrastructure)
  ├─ B3 Regression Fixtures + Validation Script
  │   ↓ (validation depends on B1 + B2 working correctly)
  └─ B4 Documentation
      ↓ (documents all of B1–B3, includes B5 links)

Logical order (sequential): B1 → B2 → B3 → B4
B5 can start immediately in parallel (documentation/design work)
B1 is lowest-level infrastructure; B2 builds on B1; B3 validates B1+B2; B4 documents all; B5 prepares future upgrade path
```

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| SiliconFlow balance insufficient for 56+ article batch (need ¥9.5, have ¥5.43) | Batch stops mid-way; user must top up or wait | Pre-batch balance check + warning; support resuming after top-up via checkpoint |
| Checkpoint directory corruption (disk I/O error, OOM) | Resume broken; force restart loses progress | Atomic writes (tmp → rename); validation script checks checkpoint integrity before resume |
| LightRAG graph state inconsistency after timeout+rollback (Milestone A residual) | Graph has orphan nodes from partial ingests | Phase 9 of Milestone A implements rollback; this milestone assumes it works |
| Circuit breaker too aggressive (opens on single transient 503) | Provider skipped unnecessarily | Threshold set to 3 consecutive failures, not 1 |
| Gemini free tier hits 500 RPD mid-batch (second fallback also fails) | Article fails with no vision description | Document as unrecoverable in that batch; user can retry after 1-hour cooldown or upgrade to Vertex AI |
| Manual operator forgets to check balance before batch | Batch fails silently 30 articles in | Runbook pre-batch checklist + automated balance check in batch_ingest_from_spider.py entry point |
| Vertex AI migration deferred indefinitely | 429 quota coupling remains a production risk | MILESTONE_v3.2 design is complete + documented; operator has clear upgrade path; can be implemented on-demand post-Milestone B |

---

## Success Metrics (Post-Implementation)

- **Batch Completion Rate:** 56+ article batch completes with 0 unhandled exceptions
- **Resume Efficiency:** If batch interrupted at article 30/56, resume from article 30 takes < 5 min overhead (no re-scrape)
- **Provider Diversity:** Batch log shows SiliconFlow used for 95%+ of images (circuit breaker only triggered on explicit failures)
- **Operator Confidence:** Runbook walkthrough completes without questions; operator can interpret checkpoint state & recover from failure manually
- **Regression Coverage:** All 5 fixtures pass; CI pipeline gates on regression report

---

## v3.2 READINESS CHECKLIST (2026-05-01)

Before entering `/gsd:execute-phase` on any v3.2 phase, confirm all boxes are checked. Each box has a grep-verifiable evidence anchor.

- [x] **Phase 12 absorbs drain_timeout finding (v3.1 closure §6.1)** — sub-doc lifecycle is a checkpoint stage, not a drain-timer bounded task
  - Evidence: `grep -q "06_sub_doc_ingest" .planning/phases/12-checkpoint-resume/12-CONTEXT.md` passes
  - Evidence: `grep -q "D-SUBDOC" .planning/phases/12-checkpoint-resume/12-CONTEXT.md` passes
  - Evidence: `grep -q "sub_doc_ingest" .planning/phases/12-checkpoint-resume/12-02-ingest-integration-PLAN.md` passes
  - Evidence: `grep -q "list_vision_markers" .planning/phases/12-checkpoint-resume/12-00-checkpoint-lib-PLAN.md` passes

- [x] **Phase 13 absorbs balance precheck env-read finding (v3.1 closure §6.2)** — bench script delegates to lib.siliconflow_balance; lib imports config
  - Evidence: `grep -q "D-BENCH-PRECHECK" .planning/phases/13-vision-cascade/13-CONTEXT.md` passes
  - Evidence: `grep -q "test_bench_precheck_delegation" .planning/phases/13-vision-cascade/13-01-siliconflow-balance-PLAN.md` passes
  - Evidence: Task 3 exists in `.planning/phases/13-vision-cascade/13-01-siliconflow-balance-PLAN.md` with scripts/bench_ingest_fixture.py in files_modified

- [x] **All gate numbers aligned to 441s / <600s baseline** — no stale 120s / <2min / 60s-avg-article references in v3.2 gate context
  - Evidence: `grep -rn "avg.*60s.*article\|60s.*avg.*article" .planning/phases/1[2-7]*/` returns 0 hits OR only historical-context mentions
  - Evidence: Phase 17 default BATCH_TIMEOUT is 28800 in 17-CONTEXT.md / 17-00 PLAN / 17-02 PLAN
  - Evidence: Worked examples in 17-CONTEXT.md and 17-00 PLAN use 441s/article baseline

- [x] **Phase 14 fixture profiles — all 4 types present** (sparse_image / dense_image / text_only / mixed_quality)
  - Evidence: `grep -c "sparse_image_article\|dense_image_article\|text_only_article\|mixed_quality_article" .planning/phases/14-regression-fixtures/14-01-fixture-creation-PLAN.md` returns ≥4
  - Evidence: Phase 14 scope unchanged — fixture profiles from original plan preserved

- [x] **v3.1 dependency annotations updated from "pending" to "closed @ 2b38e98"** in all phase CONTEXTs
  - Evidence: `grep -rn "must be gate-passing first" .planning/phases/1[2-7]*/ .planning/MILESTONE_v3.2_*.md` returns 0 hits (replaced with "closed 2026-05-01")
  - Evidence: Phase 12 and Phase 13 CONTEXTs explicitly reference commit `2b38e98`

### Pre-execute sanity run

Before running `/gsd:execute-phase` on any v3.2 phase, operator should run:

```bash
# Confirm v3.1 closure is on main and merged
git log --oneline -1 | grep "v3.1.*close\|2b38e98"

# Confirm v3.2 planning artifacts are present + revision-marked
grep -l "Revised 2026-05-01\|revised:.*2026-05-01" .planning/phases/12-checkpoint-resume/*.md \
    .planning/phases/13-vision-cascade/*.md \
    .planning/phases/14-regression-fixtures/14-02-validate-script-PLAN.md \
    .planning/phases/17-batch-timeout-management/*.md

# Confirm findings are absorbed
grep -q "D-SUBDOC" .planning/phases/12-checkpoint-resume/12-CONTEXT.md
grep -q "D-BENCH-PRECHECK" .planning/phases/13-vision-cascade/13-CONTEXT.md

# Confirm Phase 17 default is 28800
grep -q "default 28800" .planning/phases/17-batch-timeout-management/17-00-design-doc-PLAN.md
```

All four checks must pass before execute-phase kicks off.

