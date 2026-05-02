---
phase: 14-regression-fixtures
plan: 03
status: stub-punch-to-hermes
stub_reason: "depends on Plan 14-01 fixtures existing + real DeepSeek/SiliconFlow credentials + Phase 12/13 implementations merged — must run on Hermes prod host after 14-01 lands"
punch_target: hermes
depends_on: ["14-01", "14-02 ✅", "12 ✅", "13 ✅ (pending Hermes verification)"]
created: 2026-05-01
---

## What Claude did

**Nothing directly.** Plan 14-03 is an end-to-end validation run that requires:
1. All 5 fixtures present (Plan 14-01 — needs Hermes scraping)
2. Real LightRAG + DeepSeek + SiliconFlow access (Cisco Umbrella blocks both locally; R4 environment ceiling)
3. Phase 12 + Phase 13 real implementations (12 merged; 13 was dispatched to subagent in parallel — verify all 4 plans on Hermes)

## What Hermes needs to do

### After 14-01 fixtures land

```bash
cd ~/OmniGraph-Vault
git pull --ff-only
source venv/bin/activate

# Fresh run: make sure no stale checkpoints
python scripts/checkpoint_reset.py --all --confirm

# Run the full regression batch
python scripts/validate_regression_batch.py \
  --fixtures test/fixtures/gpt55_article \
             test/fixtures/sparse_image_article \
             test/fixtures/dense_image_article \
             test/fixtures/text_only_article \
             test/fixtures/mixed_quality_article \
  --output batch_validation_report.json

# Exit code 0 = all 5 PASS, closes Gate 3 of Milestone v3.2
echo "exit=$?"
cat batch_validation_report.json | python -m json.tool | head -40
```

### Expected output shape

```json
{
  "batch_id": "regression_2026-05-0X_HHMMSS",
  "timestamp": "2026-05-0XT..Z",
  "articles": [
    {"fixture": "gpt55_article", "status": "PASS", ...},
    {"fixture": "sparse_image_article", "status": "PASS", ...},
    {"fixture": "dense_image_article", "status": "PASS", ...},
    {"fixture": "text_only_article", "status": "PASS", ...},
    {"fixture": "mixed_quality_article", "status": "PASS", ...}
  ],
  "aggregate": {
    "total_articles": 5,
    "passed": 5,
    "failed": 0,
    "total_wall_time_s": <~72 based on PRD estimate>,
    "batch_pass": true
  },
  "provider_usage": {
    "siliconflow": <~110 per PRD — sum of all images Vision-described>,
    "openrouter": <0-5 — fallback only if siliconflow 503>,
    "gemini": <0-3 — last resort only>
  }
}
```

### If any fixture FAILs

Refer to `docs/OPERATOR_RUNBOOK.md` § Failure Scenarios & Recovery. Most likely causes:
- `dense_image_article`: narrow-banner filter produced different count than metadata predicted → either metadata needs updating or Phase 8 IMG-01 regressed
- `mixed_quality_article`: Phase 13 cascade consumed too many Gemini calls (check `provider_usage.gemini > 10%` → investigate SiliconFlow balance)
- `text_only_article`: Vision code path accidentally invoked on zero-image article → Phase 10 ARCH-04 regression

### Closing v3.2

Once `aggregate.batch_pass: true` is observed on Hermes:
1. Commit `batch_validation_report.json` to the repo as the v3.2 baseline
2. Update `.planning/ROADMAP.md` — move Milestone v3.2 from "Planned" to "Done" section with closure commit hash
3. Write `docs/MILESTONE_v3.2_CLOSURE.md` following the pattern from `docs/MILESTONE_v3.1_CLOSURE.md`
4. Revise E2E-02 gate if Hermes baseline differs from the <600s ceiling inherited from v3.1

### Commit suggestion for Hermes

```
feat(14-03): v3.2 regression batch PASSES — 5/5 fixtures green

batch_validation_report.json: {total=5, passed=5, failed=0,
total_wall_time_s=XXX, batch_pass=true}
provider_usage: {siliconflow=N, openrouter=M, gemini=K}

Closes Milestone v3.2 Gate 3.
```

## Why this cannot run locally

- Cisco Umbrella proxy blocks `api.deepseek.com` TLS → real LightRAG classify path fails
- Cisco Umbrella proxy blocks `api.siliconflow.cn` TLS → Phase 13 Vision cascade cannot hit primary provider
- Plan 14-01 fixtures do not yet exist (pending Hermes scrape)

Plan `14-03` is the final Hermes-side verification gate for Milestone v3.2.
