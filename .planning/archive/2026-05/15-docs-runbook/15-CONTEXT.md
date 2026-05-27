# Phase 15: Documentation & Operator Runbook (B4) - Context

**Gathered:** 2026-04-30
**Status:** Ready for planning
**Source:** PRD Express Path (`.planning/MILESTONE_v3.2_REQUIREMENTS.md` §B4)

<domain>
## Phase Boundary

**Delivers:** Three documentation artifacts that let a human operate the batch pipeline without reading code:
1. **CLAUDE.md additions** — project-level memory for future Claude Code sessions (Checkpoint Mechanism, Vision Cascade, SiliconFlow Balance, Batch Execution, Known Limitations)
2. **`docs/OPERATOR_RUNBOOK.md`** — operator-facing runbook (Pre-Batch Checklist, Batch Execution commands, Failure Scenarios table, Manual Intervention, Monitoring Points)
3. **`Deploy.md` updates** — SiliconFlow vs Gemini trade-off table + "Recommended Upgrade Path" section linking to Vertex AI spec

**Does NOT deliver:**
- Any code changes (this is pure docs)
- The CLAUDE.md sections for features that don't exist yet — docs must be drafted in parallel with Phase 12-13 implementation BUT final merge into CLAUDE.md waits on stable APIs from those phases
- SKILL.md updates (those live under `skills/` and follow OpenClaw/Hermes skill conventions — out of scope)
- The Vertex AI spec itself (that's Phase 16; this phase only LINKS to it)

**Dependency hook:** Phase 15 can draft immediately using the frozen PRD as source of truth. Final merge MUST happen after Phase 12 (checkpoint API) + Phase 13 (cascade API) stabilize to avoid documenting stale function signatures.

</domain>

<decisions>
## Implementation Decisions (from PRD §B4)

### CLAUDE.md Additions (DOC-01)
- **Checkpoint Mechanism** section: stage boundaries, checkpoint dir layout, resume semantics, manual reset commands
- **Vision Cascade** section: fallback order (SiliconFlow→OpenRouter→Gemini), circuit breaker thresholds (3 consecutive failures), per-provider balance alerts
- **SiliconFlow Balance Management** section: pre-batch check + mid-batch monitoring + depletion scenario
- **Batch Execution** section: checkpoint-resume vs full-restart commands
- **Known Limitations** section: Gemini 500 RPD ceiling, WeChat throttle (50/batch + cooldown), Vertex AI future migration path pointer

### OPERATOR_RUNBOOK.md (DOC-02) — new file at `docs/OPERATOR_RUNBOOK.md`

**Sections (MANDATORY):**
1. **Pre-Batch Checklist** — verbatim bullet list from PRD §B4.2:
   - SiliconFlow balance ≥ ¥1.00
   - DEEPSEEK_API_KEY set and valid
   - OMNIGRAPH_GEMINI_KEY set and valid (Gemini fallback)
   - SILICONFLOW_API_KEY set and valid
   - OPENROUTER_API_KEY set and valid (optional)
   - `test/fixtures/` validated with `validate_regression_batch.py`
   - Previous batch checkpoint cleaned (if full restart desired)
2. **Batch Execution** — commands verbatim:
   - `python batch_ingest_from_spider.py --topics ai --depth 2 --reset-checkpoint` (full from scratch)
   - `python batch_ingest_from_spider.py --topics ai --depth 2` (resume from checkpoint)
   - `watch -n 5 'python scripts/checkpoint_status.py | tail -20'` (monitor)
3. **Failure Scenarios & Recovery** — 6-row Markdown table (PRD §B4.2 §Failure Scenarios): SiliconFlow 503, SiliconFlow balance depleted, DeepSeek 429, single article timeout, network failure during image download, LightRAG ainsert crash
4. **Manual Intervention** — inspect checkpoint via `scripts/checkpoint_status.py`, skip article via `scripts/checkpoint_reset.py --hash {hash}`, force full re-scrape via `rm -rf checkpoints/{hash}`
5. **Monitoring Points** — real-time (`watch`), per-batch (`batch_validation_report.json` provider_usage), post-batch (`validate_regression_batch.py`)

### Deploy.md Updates (DOC-03)

Add sections:
- **SiliconFlow Paid Tier vs Gemini Free** — trade-off table: cost, reliability, error mode, balance handling
- **Vertex AI Infrastructure Plan (Milestone B.5)** — current state (Gemini API key free tier), problem (quota coupling), solution design (Vertex AI migration), timeline (deferred to post-B5)
- **Recommended Upgrade Path** — production deployments should use Vertex AI OAuth2 + cross-project quota isolation; dev/test current API key is fine; links to `docs/VERTEX_AI_MIGRATION_SPEC.md`

### Claude's Discretion

- **File placement** for OPERATOR_RUNBOOK.md: `docs/OPERATOR_RUNBOOK.md` (confirmed in PRD §B4.2)
- **Runbook walkthrough evidence** for gate-passing: a human operator confirms no questions remain after reading the runbook and walking through one failure scenario; evidence = signed-off note in `.planning/phases/15-docs-runbook/15-VERIFICATION.md`
- **Section ordering** within each document (planner picks)
- **Markdown formatting conventions** (tables vs bullets vs code blocks) — follow existing CLAUDE.md and Deploy.md style

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source of Truth
- `.planning/MILESTONE_v3.2_REQUIREMENTS.md` §B4 — verbatim requirements for all three docs
- `.planning/MILESTONE_v3.2_REQUIREMENTS.md` §B1 — Checkpoint mechanism (to document in CLAUDE.md + OPERATOR_RUNBOOK)
- `.planning/MILESTONE_v3.2_REQUIREMENTS.md` §B2 — Vision Cascade (to document in CLAUDE.md + OPERATOR_RUNBOOK)
- `.planning/MILESTONE_v3.2_REQUIREMENTS.md` §B5 — Vertex AI design (linked from Deploy.md)

### Existing Files to Modify
- `CLAUDE.md` (project root) — follow existing section style; insertion point after "Lessons Learned" section
- `Deploy.md` (project root) — append new sections at end; follow existing Markdown style

### Existing Files to Read for Style
- `.planning/phases/07-model-key-management/07-CONTEXT.md` — recent phase context example
- `.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md` — another recent phase example

### Cross-Phase Dependency Signals (wait for stable API before final merge)
- `lib/checkpoint.py` (to be created by Phase 12) — checkpoint reset/status scripts
- `lib/vision_cascade.py` or similar (to be created by Phase 13) — cascade provider state tracking
- `scripts/checkpoint_reset.py`, `scripts/checkpoint_status.py` (Phase 12)
- `scripts/estimate_vertex_ai_cost.py` (Phase 16)

</canonical_refs>

<specifics>
## Specific Ideas

### CLAUDE.md Section Templates (copy verbatim from PRD §B4.1)

Every section should include:
- **One-paragraph summary** of what this mechanism does
- **Code reference** (file:line) where the logic lives (populate after Phase 12/13 implementations merge)
- **Operator-facing commands** (checkpoint reset, balance check)
- **Known pitfalls** (e.g., "balance ¥5.43 insufficient for 263 articles; top up to ≥¥10 before batch")

### OPERATOR_RUNBOOK.md Boilerplate

Start with:
```markdown
# OmniGraph-Vault Batch Operator Runbook

**Audience:** Operators running large-scale KOL batch ingestion without reading the code.
**Prerequisites:** SSH access to production host with `~/.hermes/.env` configured.
**Last Updated:** 2026-05-XX
```

### Failure Scenarios Table (VERBATIM from PRD §B4.2)

| Scenario | Signal | Recovery |
|----------|--------|----------|
| SiliconFlow 503 (transient) | Vision provider cascade log shows fallback | Auto-recovers; monitor balance next |
| SiliconFlow balance depleted mid-batch | Balance warning + all Vision→Gemini | Accept degradation or pause batch for top-up |
| DeepSeek 429 (quota) | Classification fails | Pause 60s, retry; if persistent, contact DeepSeek support |
| Single article timeout (1200s kill) | `asyncio.wait_for` timeout error | Article marked failed in checkpoint; batch continues |
| Network failure during image download | `RequestsException` | Auto-retry; if persists, checkpoint saved at `03_manifest`; resume skips re-download |
| LightRAG ainsert crash | Corrupted graph state | `scripts/checkpoint_reset.py --hash {hash}` to force re-ingest; check LightRAG logs |

### Deploy.md Trade-Off Table Template

| Provider | Cost | Reliability | Error Mode | Balance |
|----------|------|-------------|-----------|---------|
| SiliconFlow Qwen3-VL-32B | ¥0.0013/img | High (paid tier) | 503 (server issue) | Hard cap — must refill |
| Gemini Vision free tier | ¥0 | Medium (free tier 500 RPD) | 429 (quota exhausted) | Soft cap — waits for daily reset |
| Vertex AI paid (future) | ¥ per usage | High (paid SLA) | Billing error only | Linked to GCP billing |

</specifics>

<deferred>
## Deferred Ideas

- **Skill README updates** for `omnigraph_ingest` / `omnigraph_query` skills — not in scope (skills are under `skills/` with their own conventions)
- **In-product tutorial / walkthrough UI** — no UI in this project; runbook is the interface
- **Structured log schema** for batch runs — `batch_validation_report.json` schema is Phase 14 concern, this phase only documents how to READ it
- **Automated alerting** (Slack, email) on balance depletion — runbook documents manual monitoring, automated alerts deferred to post-v3.2

</deferred>

---

*Phase: 15-docs-runbook*
*Context gathered: 2026-04-30 via PRD Express Path*
