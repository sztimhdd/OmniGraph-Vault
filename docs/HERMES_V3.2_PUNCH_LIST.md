# Hermes v3.2 Punch List

**Created:** 2026-05-01 by Claude autonomous executor
**Head commit:** `2c9d310`
**Hermes action required:** 1 blocking, 2 verification-only, 1 advisory

---

## P0 — BLOCKING: Regression fixture scraping (Plan 14-01)

**Why Hermes:** Cisco Umbrella proxy blocks real scraping + WeChat QR login is operator-specific. Plan explicitly marked `autonomous: false`.

**Full instructions:** `.planning/phases/14-regression-fixtures/14-01-STUB-PUNCH.md`

**Quick form:**

```bash
cd ~/OmniGraph-Vault && git pull --ff-only
source venv/bin/activate

# Scrape 4 articles (URLs from your shortlist):
#   sparse_image     — DeepSeek-V4 深度解读 (~3 imgs, ~8000 chars)
#   dense_image      — DeepSeek-V4 开源实测 (~45 imgs, ~2000 chars)
#   text_only        — QCon 复盘                (0 imgs, ~3000 chars)
#   mixed_quality    — MiniCPM-o 4.5            (~15 imgs, ~5000 chars)
for URL in ...; do python ingest_wechat.py "$URL"; done

# Copy scraped artifacts into test/fixtures/*_article/
# Corrupt 2-3 images in mixed_quality_article/images/
# Generate 4× metadata.json with PRD §B3.2 schema (8 fields)
```

**Acceptance:** Running `python scripts/validate_regression_batch.py --fixtures test/fixtures/{gpt55,sparse_image,dense_image,text_only,mixed_quality}_article --output batch_validation_report.json` exits 0 (closes Gate 3).

**Expected time on Hermes:** ~15 minutes (respect WeChat 50-article throttle).

---

## P1 — E2E regression run (Plan 14-03)

**Why Hermes:** depends on P0 fixtures + real DeepSeek + real SiliconFlow + Phase 12/13 integration verified under real provider load.

**Full instructions:** `.planning/phases/14-regression-fixtures/14-03-STUB-PUNCH.md`

**One-liner** (after P0 fixtures exist):

```bash
python scripts/checkpoint_reset.py --all --confirm
python scripts/validate_regression_batch.py \
  --fixtures test/fixtures/{gpt55,sparse_image,dense_image,text_only,mixed_quality}_article \
  --output batch_validation_report.json && echo "v3.2 Gate 3 PASS"
```

**Expected output:** `aggregate.batch_pass: true`, `provider_usage.gemini < 10%` of total images.

If any fixture FAILs, investigate per `docs/OPERATOR_RUNBOOK.md` § Failure Scenarios & Recovery.

**Closes:** Gate 3 of Milestone v3.2.

---

## P2 — Production smoke test for Phase 13 Vision Cascade

**Why Hermes:** Phase 13 cascade + circuit breaker tested only at HTTP mock layer on dev machine. First real-world smoke against live SiliconFlow / OpenRouter / Gemini happens on Hermes.

**What to look for:**

1. Normal batch run → `05_vision/*.json` files contain `provider: "siliconflow"` for most images (healthy state)
2. Inject a SiliconFlow 503 by temporarily revoking the key → observe cascade to OpenRouter (next `05_vision/*.json` has `provider: "openrouter"`)
3. After 3 consecutive siliconflow failures → `checkpoints/_batch/provider_status.json` shows `"siliconflow": {"circuit_open": true}`
4. Restore the key → next batch run's first image fires a recovery attempt; circuit closes on success

**Artifacts to capture:**

- `checkpoints/_batch/provider_status.json` (per-provider state)
- Any `05_vision/*.json` showing non-siliconflow provider
- `batch_validation_report.json` `provider_usage` field

**Closes:** Gate 2 at the production layer (code layer already green via 13-03 integration tests).

---

## P3 — Advisory: 10 pre-existing test failures on HEAD

Phase 13 + 17 subagents ran the full repo test suite and found **10 pre-existing failures** unrelated to v3.2:

| Count | Suite | Likely owner | Notes |
|---|---|---|---|
| 3 | `tests/unit/test_models.py` | Phase 7 (model constants) | Suspect model-name drift in `lib/models.py` between Phase 7 closure and v3.2 baseline |
| 7 | `tests/unit/test_lightrag_embedding*.py` | Phase 16 (Vertex AI embedding signature) | Vertex AI embedding function signature shift in `lib/lightrag_embedding.py`; v3.1 closure also touched this |
| 3 | `tests/unit/test_bench_harness.py` | Phase 11 (balance precheck) | Failures confirmed present on HEAD BEFORE Phase 13 touched anything (`git stash` verified) |

None of these were caused by v3.2 work — all confirmed pre-existing. But they should be triaged before closing the milestone so the `pytest tests/unit/ -q` signal is clean for Phase 5 Wave 1+.

**Suggested triage path:**

```bash
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest \
  tests/unit/test_models.py \
  tests/unit/test_lightrag_embedding.py \
  tests/unit/test_bench_harness.py \
  -v
# Look at first failure; decide: update test vs fix underlying drift.
```

Phase 13 subagent filed the Phase 13-specific view in `.planning/phases/13-vision-cascade/deferred-items.md`.

---

## Sign-off checklist when Hermes is done

- [ ] P0 complete: 4 new fixtures on disk + metadata.json for each
- [ ] P1 complete: `batch_validation_report.json` shows `aggregate.batch_pass: true`
- [ ] P2 complete: circuit breaker observed firing + recovering under live provider traffic
- [ ] P3 triaged: 10 pre-existing failures either fixed or explicitly deferred with owning-phase tickets
- [ ] `docs/MILESTONE_v3.2_CLOSURE.md` written following v3.1 closure pattern
- [ ] `.planning/ROADMAP.md` — v3.2 moved from Planned to Done with closure commit hash

Unblocks Phase 5 Wave 1+ (RSS pipeline, daily digest, cron).
