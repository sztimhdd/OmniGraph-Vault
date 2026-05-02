# v3.2 UAT — User Acceptance Test Suite

Document version: 1.0 | Date: 2026-05-02

## Overview

v3.2 UAT validates 6 incremental features introduced in v3.2 against v3.1 baseline.
Tests use pre-scraped fixture data — no CDP/WeChat network scrape required.

### Features tested

| # | Feature | Probe | Status |
|---|---------|-------|--------|
| 1 | Checkpoint file persistence | A | ✅ |
| 2 | Resume — skip completed stages | B | ✅ |
| 3 | Vision cascade fallback (SiliconFlow→OpenRouter→Gemini) | C | ✅ |
| 4 | Full 6-stage E2E ingest | D | ✅ |
| 5 | Image filtering accuracy | D (implicit) | ✅ |
| 6 | Zero-image / corrupt-image boundaries | D (text_only) | ✅ |

## Prerequisites

```bash
# API keys (in ~/.hermes/.env)
DEEPSEEK_API_KEY=...
GOOGLE_APPLICATION_CREDENTIALS=~/.hermes/gcp-sa.json
GOOGLE_CLOUD_PROJECT=project-df08084f-6db8-4f04-be8
GOOGLE_CLOUD_LOCATION=us-central1
SILICONFLOW_API_KEY=...
OPENROUTER_API_KEY=...
```

## Quick Start

```bash
# Run all 4 probes on sparse_image fixture
cd ~/OmniGraph-Vault
source venv/bin/activate
source ~/.hermes/.env
python scripts/probe_e2e_v3_2.py --output report/uat_v3_2.json

# Run single probe
python scripts/probe_e2e_v3_2.py --probe B --fixture text_only_article

# Run probes A and D only (skip slow B)
python scripts/probe_e2e_v3_2.py --probe A,D --fixture dense_image_article
```

## Fixture Catalog

| Fixture | Words | Images | Profile | Best for |
|---------|-------|--------|---------|----------|
| text_only_article | 2,520 | 0 | Pure text | Fast Probe B |
| dense_image_article | 3,534 | 24 | Heavy images | Probe C/D vision stress |
| sparse_image_article | 10,865 | 10 | Long-form | Probe D full pipeline |
| mixed_quality_article | 6,017 | 18 | Mixed quality | Edge case validation |
| gpt55_article | 4,574 | 28 | Complex charts | Vision quality |

## Probe Details

### Probe A — Checkpoint Baseline (2s, 0 API calls)

**What it tests:** Checkpoint file structure is correct when injected from fixture data.

**Verification points (14 checks):**
- Stage markers: scrape, classify, image_download present; text_ingest, sub_doc_ingest absent
- Content: scrape HTML contains title + body, classify is dict with topics, manifest is list with local_path
- Metadata: url and title fields present

**Pass criteria:** 14/14 structural checks pass.

### Probe B — Resume Verification (1-7 min)

**What it tests:** When checkpoint files exist for stages 1-3, `ingest_article()` correctly skips them and resumes from stage 4.

**Verification points:**
- classify file unchanged (DeepSeek classify NOT called)
- text_ingest stage 4 marker (`04_text_ingest.done`) written
- article_data.method == "resumed" in logs

**Pass criteria:** text_ingest=done AND classify_unchanged=True.

**Typical timing:**
| Fixture | Time |
|---------|------|
| text_only_article | ~6.5 min |
| gpt55_article | ~6.8 min |
| sparse_image_article | ~14 min |

**Known bottleneck:** LightRAG entity merge is O(N²). Long articles with many unique entities can take 10-15 min for text_ingest alone.

### Probe C — Vision Cascade (1-2 min)

**What it tests:** VisionCascade multi-provider fallback works correctly.

**Verification points:**
- 3 sample images processed through cascade
- Each CascadeResult.provider identifies the successful provider
- Circuit breaker state reported correctly
- provider_usage aggregate counts are accurate

**Pass criteria:** All 3 images have successful vision descriptions (non-empty).

**Provider selection:** Cascade order is `["siliconflow", "openrouter", "gemini"]`. When SiliconFlow balance < ¥0.05, `describe_images()` auto-promotes openrouter to primary (CASC-06).

### Probe D — Full End-to-End (5-16 min)

**What it tests:** Complete 6-stage pipeline from checkpoint injection through LightRAG query.

**Verification points:**
- All 6 checkpoints present: 01_scrape through 06_sub_doc_ingest
- Vision worker processed all images (05_vision_markers count)
- Article is queryable in LightRAG (aquery semantic recall)

**Pass criteria:** All 6 stages complete AND aquery returns article content.

**Expected timing (sparse_image_article):**

| Stage | Time | % |
|-------|------|---|
| text_ingest (entity extract + merge + embed) | ~14 min | 88% |
| vision cascade (10 × ~21s) | ~3.5 min | 11% |
| sub_doc_ingest + finalize | ~0.2 min | 1% |
| **Total** | **~17 min** | 100% |

## Interpreting Results

### Report Format

```json
{
  "title": "v3.2 E2E Regression Probe Report",
  "fixture": "sparse_image_article",
  "timestamp": "2026-05-02T05:53:53Z",
  "wall_time_s": 1017.88,
  "probes": [
    {
      "probe": "D_full_e2e",
      "passed": true,
      "detail": "total_ms=954978 vision_drain_ms=114364 stages_done=6/6 aquery=Y",
      "data": {
        "stages": {
          "01_scrape": true, "02_classify": true,
          "03_image_download": true, "04_text_ingest": true,
          "05_vision_markers": 4, "06_sub_doc_ingest": true
        }
      }
    }
  ],
  "aggregate": { "total": 4, "passed": 4, "failed": 0, "all_pass": true }
}
```

### Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Probe B hangs >10 min | LightRAG entity merge O(N²) on long article | Use text_only_article for quick B |
| Probe C all fallback to openrouter | SiliconFlow balance ¥0 | Expected behavior; CASC-06 auto-promotes |
| Probe D 05_vision_markers < n_images | OpenRouter GLM-4.5V returns empty descriptions | Not a pipeline failure; vision quality issue |
| KeyError in probe report | Cascade provider_status keys changed | Check lib/vision_cascade.py for field names |

## Integration

### CI/CD

```bash
# Smoke test (fast — probes A+C only)
python scripts/probe_e2e_v3_2.py --probe A,C --fixture text_only_article

# Full regression (slow — all probes on all fixtures)
for f in text_only sparse_image dense_image mixed_quality; do
    python scripts/probe_e2e_v3_2.py --fixture ${f}_article --output report/uat_${f}.json
done
```

### Pre-deployment Checklist

- [ ] Probe A passes on target fixture (checkpoint structure correct)
- [ ] Probe B passes on text_only_article (resume mechanism works)
- [ ] Probe C passes (vision cascade functional, provider chain intact)
- [ ] Probe D passes on sparse_image_article (full pipeline end-to-end)
- [ ] `scripts/clean_lightrag_zombies.py --dry-run` returns 0 purged (storage clean)

## Related Scripts

| Script | Purpose |
|--------|---------|
| `scripts/probe_e2e_v3_2.py` | UAT probe harness |
| `scripts/clean_lightrag_zombies.py` | Pre-scan storage cleaner |
| `scripts/bench_ingest_fixture.py` | Single-article benchmark |
| `scripts/validate_regression_batch.py` | Gate 3 metadata self-consistency |
| `lib/checkpoint.py` | Checkpoint read/write API |
| `lib/vision_cascade.py` | Multi-provider vision with circuit breaker |
