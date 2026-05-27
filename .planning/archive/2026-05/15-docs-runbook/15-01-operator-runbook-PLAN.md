---
phase: 15-docs-runbook
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - docs/OPERATOR_RUNBOOK.md
autonomous: true
requirements:
  - DOC-02
must_haves:
  truths:
    - "New file exists at docs/OPERATOR_RUNBOOK.md"
    - "Runbook has section 'Pre-Batch Checklist' with 7 checklist items"
    - "Runbook has section 'Batch Execution' with the 3 canonical commands"
    - "Runbook has section 'Failure Scenarios & Recovery' with a 6-row Markdown table"
    - "Runbook has section 'Manual Intervention' with 3 named sub-flows"
    - "Runbook has section 'Monitoring Points' listing real-time, per-batch, and post-batch points"
    - "A human operator can run a batch and recover from any of the 6 failure scenarios without reading source code"
  artifacts:
    - path: docs/OPERATOR_RUNBOOK.md
      provides: Operator-facing runbook for batch ingestion without reading code
      min_lines: 80
      contains: "# OmniGraph-Vault Batch Operator Runbook"
  key_links:
    - from: docs/OPERATOR_RUNBOOK.md § Failure Scenarios
      to: scripts/checkpoint_reset.py
      via: LightRAG ainsert crash recovery command
      pattern: "checkpoint_reset\\.py --hash"
    - from: docs/OPERATOR_RUNBOOK.md § Monitoring Points
      to: batch_validation_report.json
      via: provider_usage field reference
      pattern: "provider_usage"
    - from: docs/OPERATOR_RUNBOOK.md § Pre-Batch Checklist
      to: ~/.hermes/.env env vars
      via: required env var list (DEEPSEEK, OMNIGRAPH_GEMINI, SILICONFLOW, OPENROUTER)
      pattern: "DEEPSEEK_API_KEY.*SILICONFLOW_API_KEY"
---

<objective>
Create the new file `docs/OPERATOR_RUNBOOK.md` — a standalone, operator-facing runbook for running large-scale batch ingestion against production without reading source code.

Purpose: An operator with SSH access to production and a configured `~/.hermes/.env` can start a batch, monitor it, and recover from any of the six documented failure scenarios using only the commands in this runbook.

Output: A new Markdown file at `docs/OPERATOR_RUNBOOK.md` with five mandatory sections (Pre-Batch Checklist, Batch Execution, Failure Scenarios & Recovery, Manual Intervention, Monitoring Points) containing content verbatim from PRD §B4.2.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/15-docs-runbook/15-CONTEXT.md
@.planning/MILESTONE_v3.2_REQUIREMENTS.md
@Deploy.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create docs/OPERATOR_RUNBOOK.md with all five mandatory sections</name>

  <files>docs/OPERATOR_RUNBOOK.md</files>

  <read_first>
    - .planning/MILESTONE_v3.2_REQUIREMENTS.md §B4.2 (lines 320–363) — verbatim checklist, commands, failure table, manual intervention list, monitoring points.
    - .planning/phases/15-docs-runbook/15-CONTEXT.md § specifics — boilerplate header template and verbatim Failure Scenarios table.
    - Deploy.md § 7 "Gate 7 Validation Checklist" (lines ~310–326) — style reference for operator-facing Markdown tables and command blocks in this repo.
    - Deploy.md § 9 "Troubleshooting" (lines ~343–353) — style reference for "Problem / Cause / Fix" table layout; use similar tone and density.
  </read_first>

  <action>
Create a new file at `docs/OPERATOR_RUNBOOK.md` (the `docs/` directory already exists). Write the file with EXACTLY the content below — do not add, remove, or rephrase content. Do NOT add emojis.

```markdown
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
```

After writing, verify the file passes ALL acceptance_criteria grep/wc commands below. Do NOT create any other files.
  </action>

  <verify>
    <automated>test -f docs/OPERATOR_RUNBOOK.md &amp;&amp; grep -q '^## Pre-Batch Checklist' docs/OPERATOR_RUNBOOK.md &amp;&amp; grep -q '^## Batch Execution' docs/OPERATOR_RUNBOOK.md &amp;&amp; grep -q '^## Failure Scenarios &amp; Recovery' docs/OPERATOR_RUNBOOK.md &amp;&amp; grep -q '^## Manual Intervention' docs/OPERATOR_RUNBOOK.md &amp;&amp; grep -q '^## Monitoring Points' docs/OPERATOR_RUNBOOK.md</automated>
  </verify>

  <acceptance_criteria>
    - `test -f docs/OPERATOR_RUNBOOK.md` returns 0 (file exists)
    - `wc -l docs/OPERATOR_RUNBOOK.md` returns a value ≥ 80 (non-empty, substantive runbook)
    - `grep -q '^# OmniGraph-Vault Batch Operator Runbook' docs/OPERATOR_RUNBOOK.md` returns 0 (title present)
    - `grep -q '^## Pre-Batch Checklist' docs/OPERATOR_RUNBOOK.md` returns 0
    - `grep -q '^## Batch Execution' docs/OPERATOR_RUNBOOK.md` returns 0
    - `grep -q '^## Failure Scenarios & Recovery' docs/OPERATOR_RUNBOOK.md` returns 0
    - `grep -q '^## Manual Intervention' docs/OPERATOR_RUNBOOK.md` returns 0
    - `grep -q '^## Monitoring Points' docs/OPERATOR_RUNBOOK.md` returns 0
    - `grep -c '^- \[ \]' docs/OPERATOR_RUNBOOK.md` returns 7 (exactly 7 pre-batch checklist items)
    - `grep -c '^| SiliconFlow 503' docs/OPERATOR_RUNBOOK.md` returns 1 (failure scenarios table row present)
    - `grep -c '^| ' docs/OPERATOR_RUNBOOK.md` returns a value ≥ 9 (6 failure-scenarios rows + header + "when to use which" table rows)
    - `grep -q 'DEEPSEEK_API_KEY' docs/OPERATOR_RUNBOOK.md` returns 0
    - `grep -q 'SILICONFLOW_API_KEY' docs/OPERATOR_RUNBOOK.md` returns 0
    - `grep -q 'OMNIGRAPH_GEMINI_KEY' docs/OPERATOR_RUNBOOK.md` returns 0
    - `grep -q 'OPENROUTER_API_KEY' docs/OPERATOR_RUNBOOK.md` returns 0
    - `grep -q 'batch_ingest_from_spider.py --topics ai --depth 2 --reset-checkpoint' docs/OPERATOR_RUNBOOK.md` returns 0 (full-restart command verbatim)
    - `grep -q "watch -n 5 'python scripts/checkpoint_status.py" docs/OPERATOR_RUNBOOK.md` returns 0 (monitor command verbatim)
    - `grep -q 'checkpoint_reset.py --hash' docs/OPERATOR_RUNBOOK.md` returns 0 (skip-article flow documented)
    - `grep -q 'provider_usage' docs/OPERATOR_RUNBOOK.md` returns 0 (per-batch monitoring documented)
    - `grep -q 'validate_regression_batch.py' docs/OPERATOR_RUNBOOK.md` returns 0 (post-batch monitoring documented)
  </acceptance_criteria>

  <done>
    `docs/OPERATOR_RUNBOOK.md` exists with all five mandatory sections, exact verbatim commands from PRD §B4.2, 6-row failure scenarios table, 7-item pre-batch checklist, and all three manual-intervention sub-flows. All acceptance criteria pass.
  </done>
</task>

</tasks>

<verification>
Run all acceptance_criteria grep/wc/test commands. Read the file top-to-bottom and confirm a human operator could execute a batch from it without referencing code or the PRD.
</verification>

<success_criteria>
- File exists at `docs/OPERATOR_RUNBOOK.md`
- All five mandatory sections present with required content
- Line count ≥ 80
- All acceptance_criteria grep/wc commands pass
</success_criteria>

<output>
After completion, create `.planning/phases/15-docs-runbook/15-01-operator-runbook-SUMMARY.md` documenting: final line count, table row counts verified, and a short note on any phrasing deviations from the PRD (should be none).
</output>
