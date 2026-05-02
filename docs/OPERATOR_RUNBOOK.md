# OmniGraph-Vault Batch Operator Runbook

**Audience:** Operators running large-scale KOL batch ingestion without reading the code.
**Prerequisites:** SSH access to the production host with `~/.hermes/.env` configured.
**Last Updated:** 2026-04-30

This runbook is the authoritative reference for starting, monitoring, and recovering batch runs of `batch_ingest_from_spider.py`. If a scenario is not covered here, escalate — do not improvise against production.

---

## Pre-Batch Checklist

Before starting any batch, confirm EVERY item. An unchecked item is a blocking issue.

- [ ] SiliconFlow balance ≥ ¥1.00 (covers ~770 images; budget ≥ ¥10 for a 263-article batch)
- [ ] `DEEPSEEK_API_KEY` set and valid in `~/.hermes/.env`
- [ ] `OMNIGRAPH_GEMINI_KEY` set and valid (Gemini fallback at end of Vision Cascade)
- [ ] `SILICONFLOW_API_KEY` set and valid (primary Vision provider)
- [ ] `OPENROUTER_API_KEY` set and valid (optional, secondary Vision provider; leave unset to skip)
- [ ] `test/fixtures/` validated with `python scripts/validate_regression_batch.py` — exit code 0
- [ ] Previous batch checkpoint directory cleaned (if a full restart is desired; otherwise resume is the default)

**How to check SiliconFlow balance:** log in to the SiliconFlow dashboard (console.siliconflow.cn) → Billing → Current Balance. There is no CLI check; the pre-batch structured warning from the cascade layer is a secondary safety net, not a substitute for this dashboard check.

---

## Batch Execution

Three canonical commands govern all batch runs.

```bash
# Full batch from scratch (wipes all checkpoints first, re-downloads all images)
python batch_ingest_from_spider.py --topics ai --depth 2 --reset-checkpoint

# Resume from last checkpoint (DEFAULT — skips already-completed stages per article)
python batch_ingest_from_spider.py --topics ai --depth 2

# Monitor progress (refreshes every 5 seconds; Ctrl+C to stop monitoring — batch continues)
watch -n 5 'python scripts/checkpoint_status.py | tail -20'
```

**When to use which command:**

| Command | Use when |
|---------|----------|
| `--reset-checkpoint` | Fixture logic or ingestion logic changed; you want a clean baseline for a regression run |
| Resume (no flag) | Interrupted batch, transient failure recovered, mid-batch top-up completed |
| `watch ... checkpoint_status.py` | Running alongside an active batch; does not interfere |

**Never run two batches concurrently on the same host.** Checkpoint writes are atomic per article but not across concurrent processes.

---

## Failure Scenarios & Recovery

When a batch misbehaves, match the signal below to a row and follow the Recovery column.

| Scenario | Signal | Recovery |
|----------|--------|----------|
| SiliconFlow 503 (transient) | Vision provider cascade log shows fallback | Auto-recovers; monitor balance next |
| SiliconFlow balance depleted mid-batch | Balance warning + all Vision→Gemini | Accept degradation or pause batch for top-up |
| DeepSeek 429 (quota) | Classification fails | Pause 60s, retry; if persistent, contact DeepSeek support |
| Single article timeout (1200s kill) | `asyncio.wait_for` timeout error | Article marked failed in checkpoint; batch continues |
| Network failure during image download | `RequestsException` | Auto-retry; if persists, checkpoint saved at `03_manifest`; resume skips re-download |
| LightRAG ainsert crash | Corrupted graph state | `scripts/checkpoint_reset.py --hash {hash}` to force re-ingest; check LightRAG logs |

**If none of these match:** capture the full stack trace and the contents of `checkpoints/{article_hash}/metadata.json` for the affected article, then pause the batch and escalate. Do NOT delete checkpoints without capturing state first.

---

## Manual Intervention

Three flows cover every manual operation on a batch.

**Inspect a checkpoint (read-only, safe during active batch):**

```bash
ls -la checkpoints/{article_hash}/
cat checkpoints/{article_hash}/metadata.json
```

The `metadata.json` file shows the last completed stage and the last-updated timestamp. Use this to diagnose stuck articles before taking any action.

**Skip one article (makes the batch proceed past a poisoned article):**

```bash
python scripts/checkpoint_status.py                   # find the article_hash
python scripts/checkpoint_reset.py --hash {hash}     # remove its checkpoint
# Then resume the batch normally — the article will re-try from stage 01
```

**Force full re-scrape of one article (rarely needed; respects WeChat throttle so no speedup):**

```bash
rm -rf checkpoints/{article_hash}
# Then resume the batch normally
```

Never delete the top-level `checkpoints/` directory while a batch is running — concurrent atomic writes to `metadata.json` files will corrupt in-flight articles.

---

## Monitoring Points

Three monitoring surfaces, each with a different cadence and purpose.

**Real-time (seconds):**

```bash
watch -n 5 'python scripts/checkpoint_status.py | tail -20'
```

Lists in-flight articles + their current stage. Use during the first 30 minutes of a batch to confirm articles are progressing through stages (not stuck at stage 01).

**Per-batch (after batch completes):**

Check `batch_validation_report.json` for the `provider_usage` field. A healthy batch shows Gemini usage below 10% of total Vision calls. If Gemini usage is above 10%, investigate SiliconFlow balance and OpenRouter health before the next batch.

**Post-batch (regression catch):**

```bash
python scripts/validate_regression_batch.py --fixtures test/fixtures --output batch_validation_report.json
```

Runs the five regression fixtures against the current pipeline and writes a structured JSON report. Exit code 0 means no regression; exit code 1 means at least one fixture failed — open the report and diagnose before starting the next production batch.

---

*For architectural context on the Checkpoint Mechanism, Vision Cascade, and SiliconFlow balance semantics, see `CLAUDE.md`. For deployment and upgrade-path concerns (Vertex AI migration), see `Deploy.md` § Recommended Upgrade Path.*
