---
phase: 15-docs-runbook
plan: 00
type: execute
wave: 1
depends_on: []
files_modified:
  - CLAUDE.md
autonomous: true
requirements:
  - DOC-01
must_haves:
  truths:
    - "CLAUDE.md has a new '## Checkpoint Mechanism' section after 'Lessons Learned'"
    - "CLAUDE.md has a new '## Vision Cascade' section"
    - "CLAUDE.md has a new '## SiliconFlow Balance Management' section"
    - "CLAUDE.md has a new '## Batch Execution' section"
    - "CLAUDE.md has a new '## Known Limitations' section"
    - "All five sections are inserted between the 'Lessons Learned' section and the '<!-- GSD:project-start -->' marker"
    - "Existing CLAUDE.md content is not modified (surgical insertion only)"
  artifacts:
    - path: CLAUDE.md
      provides: Five new top-level sections for project-level memory on batch operations
      contains: "## Checkpoint Mechanism, ## Vision Cascade, ## SiliconFlow Balance Management, ## Batch Execution, ## Known Limitations"
  key_links:
    - from: CLAUDE.md § Checkpoint Mechanism
      to: scripts/checkpoint_reset.py + scripts/checkpoint_status.py
      via: operator-facing command references
      pattern: "checkpoint_(reset|status)\\.py"
    - from: CLAUDE.md § Vision Cascade
      to: SiliconFlow → OpenRouter → Gemini fallback chain
      via: documented cascade order + circuit breaker threshold
      pattern: "SiliconFlow.*OpenRouter.*Gemini"
    - from: CLAUDE.md § Known Limitations
      to: Phase 16 Vertex AI migration plan
      via: forward reference to Deploy.md "Recommended Upgrade Path"
      pattern: "Vertex AI"
---

<objective>
Insert five new top-level sections into `CLAUDE.md` documenting the batch-ingestion mechanisms added in Milestone v3.2 (Checkpoint, Vision Cascade, SiliconFlow Balance Management, Batch Execution, Known Limitations).

Purpose: Future Claude Code sessions loading `CLAUDE.md` as project memory get accurate operator-level knowledge of checkpoint/resume semantics, vision-provider fallback order, balance monitoring, batch commands, and known quota ceilings — without re-reading the PRD.

Output: `CLAUDE.md` with five new sections inserted immediately after the existing "Lessons Learned" section and before the `<!-- GSD:project-start source:PROJECT.md -->` marker. No other edits.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/15-docs-runbook/15-CONTEXT.md
@.planning/MILESTONE_v3.2_REQUIREMENTS.md
@CLAUDE.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Insert five new sections into CLAUDE.md after "Lessons Learned"</name>

  <files>CLAUDE.md</files>

  <read_first>
    - CLAUDE.md — confirm exact line number of "## Lessons Learned" heading (currently line 384) and the `<!-- GSD:project-start source:PROJECT.md -->` marker (currently line 390). Insert new content between the last bullet of Lessons Learned and the GSD marker.
    - .planning/MILESTONE_v3.2_REQUIREMENTS.md §B4.1 (lines 313–319) — verbatim requirements for each of the five CLAUDE.md sections.
    - .planning/phases/15-docs-runbook/15-CONTEXT.md — locked decisions for section scope (Checkpoint, Vision Cascade, SiliconFlow Balance, Batch Execution, Known Limitations).
    - CLAUDE.md lines 340–388 — style reference: look at "Remote Hermes Deployment" and "Lessons Learned" for heading hierarchy, paragraph density, code-block conventions.
  </read_first>

  <action>
Open `CLAUDE.md` and locate the line `<!-- GSD:project-start source:PROJECT.md -->` (currently line 390). Insert the following five sections IMMEDIATELY BEFORE that marker (and after the last bullet of "Lessons Learned"). Preserve the blank line above the GSD marker.

Copy-paste the following content verbatim. Do NOT add any emojis. Do NOT edit existing content above line 390 or below the GSD marker.

```markdown
## Checkpoint Mechanism

The batch ingestion pipeline uses a per-article checkpoint directory to make long-running batches resumable without re-doing expensive work (scraping, image download, vision description, LightRAG ainsert).

**Stage boundaries** — each article progresses through ordered stages; a completed stage writes a marker file into `checkpoints/{article_hash}/`:
- `01_scrape` — raw HTML + markdown extracted from WeChat / Apify / CDP
- `02_filter` — small/boilerplate images filtered (Phase 8 rule)
- `03_manifest` — image download manifest (URLs + local paths)
- `04_vision` — per-image descriptions from the Vision Cascade
- `05_ingest` — LightRAG `ainsert()` committed
- `metadata.json` — current stage + last-updated timestamp

**Resume semantics** — on batch restart, each article's checkpoint dir is inspected; the pipeline skips stages whose marker file exists and resumes at the first missing stage. Checkpoint writes are atomic (`.tmp` then `os.rename()`), so a crash mid-write never leaves corrupted partial files.

**Operator commands:**
- `python scripts/checkpoint_status.py` — list all in-flight articles and their current stage
- `python scripts/checkpoint_reset.py --hash {article_hash}` — remove one article's checkpoint dir to force full re-ingest
- `rm -rf checkpoints/{article_hash}` — same as above, manual form (respects WeChat throttle, so no speedup)
- `python batch_ingest_from_spider.py --reset-checkpoint` — wipe all checkpoints and start a full batch from scratch

**Known pitfall:** removing `checkpoints/` mid-batch while the process is running can corrupt in-flight `metadata.json` writes — always stop the batch first.

## Vision Cascade

Per-image description uses a three-provider cascade with automatic failover and a per-provider circuit breaker. The goal is that a single provider 503/429 never kills an article.

**Fallback order** (hard-coded, not env-overridable):
1. **SiliconFlow Qwen3-VL-32B** (primary; ¥0.0013/image, paid tier)
2. **OpenRouter** (secondary; free-tier fallback)
3. **Gemini Vision** (last resort; 500 RPD free-tier ceiling)

**Circuit breaker** — after **3 consecutive failures** of the same provider within a batch, `circuit_open = True` for that provider and it is skipped for subsequent images until a recovery retry succeeds. A 429 cascades immediately to the next provider. 4xx auth errors do NOT count toward the circuit breaker (fixing auth requires operator action, not automatic fallback).

**Per-provider balance alerts** — pre-batch, the cascade layer emits a structured warning to stderr if `SiliconFlow balance < estimated remaining cost`. Estimated cost is `¥0.0013 × expected_image_count`.

**Cascade evidence** — `batch_validation_report.json` records `provider_usage` (per-provider attempt count + success count). A healthy batch shows Gemini usage below 10%; if Gemini usage is >10%, investigate SiliconFlow + OpenRouter health before the next batch.

## SiliconFlow Balance Management

SiliconFlow is a paid-tier provider with a hard balance cap. Running out of balance mid-batch does NOT hang the pipeline (the cascade falls through to OpenRouter + Gemini), but it does shift all remaining images onto the 500-RPD Gemini free tier, which can exhaust quota in a single batch.

**Pre-batch check** — before starting any batch, verify SiliconFlow balance covers the expected image count at ¥0.0013/image. Rule of thumb: **¥1.00 covers ~770 images**. For a 263-article batch averaging 10 images/article (~2,630 images), budget **≥ ¥10** before starting.

**Mid-batch monitoring** — `watch -n 30 'python scripts/checkpoint_status.py | tail -20'` shows in-flight articles; if the Vision provider flips to Gemini for more than a handful of consecutive images, check the balance.

**Depletion scenario** — when balance hits 0:
1. Cascade logs a structured warning per image: `SiliconFlow balance depleted; cascading to OpenRouter/Gemini`
2. Subsequent images auto-route to OpenRouter (if available) and Gemini
3. Gemini 500-RPD quota will exhaust within one batch of any scale — either **pause the batch + top up**, or **accept the degraded run** and treat the resulting Gemini-heavy articles as lower-fidelity

**Top-up flow** — topping up mid-batch is safe: pause batch (Ctrl+C — checkpoints are atomic), top up on the SiliconFlow dashboard, then resume with the same command (no `--reset-checkpoint`).

## Batch Execution

Two canonical commands govern all batch runs:

```bash
# Full batch from scratch (wipes all checkpoints first)
python batch_ingest_from_spider.py --topics ai --depth 2 --reset-checkpoint

# Resume from last checkpoint (the default — skips already-completed stages)
python batch_ingest_from_spider.py --topics ai --depth 2

# Monitor progress (refreshes every 5s)
watch -n 5 'python scripts/checkpoint_status.py | tail -20'
```

**When to use which:**
- **Resume** (default) — interrupted batch, transient failure, mid-batch top-up; safe to run repeatedly
- **`--reset-checkpoint`** — you have changed fixture logic, ingestion logic, or want a clean baseline for a regression run; this wipes ALL checkpoints and re-downloads all images

**Never run both simultaneously** — checkpoint writes are atomic per article but not across concurrent processes. One batch at a time per host.

## Known Limitations

- **Gemini 500 RPD ceiling** (free tier) — the Gemini fallback at the end of the Vision Cascade is capped at 500 requests per day across the shared GCP project. A single large batch falling through to Gemini can exhaust this quota and cause Vision to fail for the remainder of the day.
- **WeChat account throttle** — `ingest_wechat.py` enforces **50 articles per batch + cooldown** before the next batch; this is a WeChat-side limit, not configurable. Large batches should be sliced into 50-article chunks with cooldown between chunks.
- **Vertex AI migration path (future)** — the current Gemini API key couples embedding quota with LLM quota in the same GCP project, so an embedding 429 can kill a batch mid-ingest. The **Recommended Upgrade Path** (see `Deploy.md` § Recommended Upgrade Path) migrates production deployments to Vertex AI OAuth2 with per-project quota isolation. Design is frozen (Phase 16 spec); code migration is deferred to post-Milestone B.

```

After pasting, verify the resulting file structure with the acceptance_criteria commands. Do NOT touch any other section of CLAUDE.md.
  </action>

  <verify>
    <automated>grep -q '^## Checkpoint Mechanism' CLAUDE.md &amp;&amp; grep -q '^## Vision Cascade' CLAUDE.md &amp;&amp; grep -q '^## SiliconFlow Balance Management' CLAUDE.md &amp;&amp; grep -q '^## Batch Execution' CLAUDE.md &amp;&amp; grep -q '^## Known Limitations' CLAUDE.md</automated>
  </verify>

  <acceptance_criteria>
    - `grep -q '^## Checkpoint Mechanism' CLAUDE.md` returns 0
    - `grep -q '^## Vision Cascade' CLAUDE.md` returns 0
    - `grep -q '^## SiliconFlow Balance Management' CLAUDE.md` returns 0
    - `grep -q '^## Batch Execution' CLAUDE.md` returns 0
    - `grep -q '^## Known Limitations' CLAUDE.md` returns 0
    - `grep -c '^## ' CLAUDE.md` returns a value exactly 5 greater than the pre-edit count (verifies surgical insertion — no other sections renamed/removed)
    - `grep -n '## Lessons Learned' CLAUDE.md` appears BEFORE `grep -n '## Checkpoint Mechanism' CLAUDE.md` (ordering preserved)
    - `grep -n '<!-- GSD:project-start' CLAUDE.md` appears AFTER `grep -n '## Known Limitations' CLAUDE.md` (insertion before GSD marker)
    - `grep -q 'SiliconFlow.*OpenRouter.*Gemini' CLAUDE.md` returns 0 (cascade order documented)
    - `grep -q 'checkpoint_reset.py' CLAUDE.md` returns 0 (operator command referenced)
    - `grep -q 'Vertex AI' CLAUDE.md` returns 0 (forward reference to Deploy.md)
  </acceptance_criteria>

  <done>
    All five sections present in CLAUDE.md with verbatim content above. Surrounding content (Lessons Learned, GSD:project-start block, Technology Stack) unchanged. Acceptance criteria grep commands all return 0.
  </done>
</task>

</tasks>

<verification>
Run acceptance_criteria grep commands. Open `CLAUDE.md` in the editor and scroll from line ~384 ("## Lessons Learned") to the new "## Known Limitations" section end to visually confirm insertion order and content fidelity against the PRD §B4.1 source.
</verification>

<success_criteria>
- All `must_haves.truths` observable in the file on disk
- No lines outside the insertion window modified
- Acceptance-criteria grep commands pass
</success_criteria>

<output>
After completion, create `.planning/phases/15-docs-runbook/15-00-claude-md-additions-SUMMARY.md` documenting: insertion line number, section count added, file delta (git diff line count), and any deviations from the PRD.
</output>
