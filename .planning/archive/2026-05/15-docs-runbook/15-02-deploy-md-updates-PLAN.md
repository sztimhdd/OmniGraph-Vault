---
phase: 15-docs-runbook
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - Deploy.md
autonomous: true
requirements:
  - DOC-03
must_haves:
  truths:
    - "Deploy.md has a new '## SiliconFlow Paid Tier vs Gemini Free' section with a 3-row trade-off table"
    - "Deploy.md has a new '## Vertex AI Infrastructure Plan (Milestone B.5)' section documenting current state, problem, solution design, and timeline"
    - "Deploy.md has a new '## Recommended Upgrade Path' section linking to docs/VERTEX_AI_MIGRATION_SPEC.md"
    - "All three new sections appended at END of Deploy.md (after existing section 9 Troubleshooting)"
    - "Existing Deploy.md content above section 9 is not modified"
  artifacts:
    - path: Deploy.md
      provides: Trade-off rationale + forward-looking Vertex AI upgrade plan
      contains: "## SiliconFlow Paid Tier vs Gemini Free, ## Vertex AI Infrastructure Plan (Milestone B.5), ## Recommended Upgrade Path"
  key_links:
    - from: Deploy.md § SiliconFlow Paid Tier vs Gemini Free
      to: cost/reliability/error-mode/balance trade-off
      via: 3-row Markdown table
      pattern: "SiliconFlow.*Gemini.*Vertex AI"
    - from: Deploy.md § Recommended Upgrade Path
      to: docs/VERTEX_AI_MIGRATION_SPEC.md (Phase 16 deliverable)
      via: forward link
      pattern: "VERTEX_AI_MIGRATION_SPEC\\.md"
    - from: Deploy.md § Vertex AI Infrastructure Plan
      to: CLAUDE.md § Known Limitations (Vertex AI migration path)
      via: back-reference to project-memory doc
      pattern: "CLAUDE\\.md|Known Limitations"
---

<objective>
Append three new top-level sections to the END of `Deploy.md` documenting the SiliconFlow-vs-Gemini trade-off, the deferred Vertex AI infrastructure plan, and the recommended upgrade path for production deployments.

Purpose: Operators deciding between SiliconFlow (paid tier) and Gemini (free tier) for production understand the reliability, cost, and error-mode trade-offs. Future engineers planning the Milestone B.5 Vertex AI migration have a frozen design reference to implement against.

Output: `Deploy.md` with three new sections appended after the existing "## 9. Troubleshooting" section (currently the final section). No other edits.
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
  <name>Task 1: Append three new sections to end of Deploy.md</name>

  <files>Deploy.md</files>

  <read_first>
    - Deploy.md — confirm the file currently ends at line 353 with "## 9. Troubleshooting" as the final section. Append new sections below the last row of that section's table.
    - .planning/MILESTONE_v3.2_REQUIREMENTS.md §B4.3 (lines 364–385) — verbatim requirements for SiliconFlow-vs-Gemini trade-off, Vertex AI Infrastructure Plan (current state, problem, solution design, timeline), and Recommended Upgrade Path.
    - .planning/MILESTONE_v3.2_REQUIREMENTS.md §B5 — full Vertex AI design context (the detail that the new "Vertex AI Infrastructure Plan" section links to).
    - .planning/phases/15-docs-runbook/15-CONTEXT.md § specifics — verbatim Deploy.md trade-off table template (3 rows: SiliconFlow Qwen3-VL-32B, Gemini Vision free tier, Vertex AI paid (future)).
    - Deploy.md lines 13–80 (Environment Variables section) — style reference: trade-off tables, note blocks, existing treatment of Hermes FLAG 1/2. Match this density and tone.
  </read_first>

  <action>
Open `Deploy.md` and append the following three sections at the END of the file, immediately after the final row of the section 9 Troubleshooting table (currently line 353, which ends with `| \`rules_engine.json\` not found | architect propose mode fails | Ensure file exists at repo root (28 rules) |`).

Insert a blank line first, then a horizontal rule (`---`), then a blank line, then paste the following content verbatim. Do NOT add emojis. Do NOT modify any existing content above section 9.

```markdown
## SiliconFlow Paid Tier vs Gemini Free

OmniGraph-Vault's Vision pipeline can run on either SiliconFlow Qwen3-VL-32B (paid tier) or the Gemini Vision free tier. Each has distinct cost, reliability, error-mode, and balance-handling trade-offs. The three-provider cascade in `lib/vision_cascade.py` uses both in order (SiliconFlow primary, Gemini fallback) so every production batch touches both at some volume.

| Provider | Cost | Reliability | Error Mode | Balance |
|----------|------|-------------|-----------|---------|
| SiliconFlow Qwen3-VL-32B | ¥0.0013/img | High (paid tier) | 503 (server issue) | Hard cap — must refill |
| Gemini Vision free tier | ¥0 | Medium (free tier 500 RPD) | 429 (quota exhausted) | Soft cap — waits for daily reset |
| Vertex AI paid (future) | ¥ per usage | High (paid SLA) | Billing error only | Linked to GCP billing |

**Operational implications:**

- **SiliconFlow** is roughly 50–100× cheaper per image than a Vertex-AI paid tier, but requires you to watch the balance and refill before it hits zero. A depleted balance cascades all subsequent images onto Gemini.
- **Gemini free tier** never errors on balance (there is no balance), but its 500-RPD ceiling is shared across the whole GCP project. A single large batch that falls through to Gemini can exhaust the day's quota and cause downstream embedding calls to 429.
- **Vertex AI (future)** trades a higher per-image cost for predictable billing-backed reliability + per-project quota isolation. See the "Vertex AI Infrastructure Plan" section below for the migration design.

---

## Vertex AI Infrastructure Plan (Milestone B.5)

This section freezes the design for migrating production deployments from the Gemini API key (free tier) to Vertex AI (paid tier, OAuth2). Code migration is deferred — the design is complete, and no code changes are in scope for the current milestone.

**Current State**

- Authentication: single `OMNIGRAPH_GEMINI_KEY` (free-tier API key) in `~/.hermes/.env`
- Quota: 100 RPM embedding + 500 RPD vision, **shared across the same GCP project**
- Scope: fine for dev/test and small batches; production batches routinely brush the shared-quota ceiling

**Problem**

Embedding 429 and LLM 429 share the same GCP project quota pool. When a batch pushes embedding calls toward the 100-RPM ceiling, subsequent LLM calls on the same key also start 429-ing — a single embedding spike can kill a batch mid-ingest. There is no way to isolate the quotas within one API key.

**Solution Design (deferred to post-Milestone B — no code changes this milestone)**

1. Create GCP Vertex AI project(s):
   - **Option A (Recommended):** Two projects — one for embedding (`gemini-embedding-2`), one for LLM. DeepSeek stays on-prem. Per-project quota isolation means embedding 429 cannot affect LLM calls.
   - **Option B:** One Vertex AI project with separate service accounts for embedding vs. LLM, each with its own isolated quota allocation.
2. Migrate from `OMNIGRAPH_GEMINI_KEY` (API key) to a Vertex AI OAuth2 token.
3. Update `lib/api_keys.py` + `lib/llm_client.py` to support the Vertex AI endpoint + service-account rotation.
4. Backward-compat: keep the Gemini API key as fallback if Vertex AI is unavailable (dev machines, quick tests).

**Acceptance Criteria for Milestone B.5 (design-only)**

- `docs/VERTEX_AI_MIGRATION_SPEC.md` documents GCP project setup steps, service-account naming convention, OAuth2 token refresh pattern, and cost estimation per tier
- `credentials/vertex_ai_service_account_example.json` template exists (no real credentials in repo)
- `CLAUDE.md § Known Limitations` references the Vertex AI migration path (done in DOC-01)
- `Deploy.md § Recommended Upgrade Path` (below) links to `docs/VERTEX_AI_MIGRATION_SPEC.md`
- `scripts/estimate_vertex_ai_cost.py` estimates the cost for expected batch sizes

**Timeline**

Design + setup guide land in Milestone B.5. Code integration (the `lib/api_keys.py` + `lib/llm_client.py` changes) is deferred to post-Milestone B so the current milestone stays docs-only.

---

## Recommended Upgrade Path

**For production deployments**, migrate to Vertex AI OAuth2 with cross-project quota isolation. This eliminates the shared-quota coupling that causes embedding 429s to cascade into LLM 429s, and provides paid-tier SLA for Vision throughput.

See `docs/VERTEX_AI_MIGRATION_SPEC.md` (Milestone B.5 deliverable) for:
- GCP project setup steps (Option A vs Option B)
- Service-account naming convention + OAuth2 token refresh pattern
- Cost estimation per expected batch size (via `scripts/estimate_vertex_ai_cost.py`)
- Backward-compat strategy (Gemini API key fallback)

**For dev/test deployments**, the current `OMNIGRAPH_GEMINI_KEY` (free tier) is sufficient. No action required — rate limits are documented in `CLAUDE.md § Known Limitations`.

**Upgrade decision matrix:**

| Deployment | Recommendation | Rationale |
|------------|----------------|-----------|
| Production (daily batches ≥ 50 articles) | Vertex AI OAuth2 (Option A) | Per-project quota isolation eliminates embedding-LLM coupling |
| Production (occasional batches) | Vertex AI OAuth2 (Option B) | Single project, isolated service accounts — simpler ops, still quota-isolated |
| Dev / Test / CI | Gemini API key (current) | Free tier sufficient; migration cost not justified |
```

After appending, verify with the acceptance_criteria commands. Do NOT touch any other section of `Deploy.md`.
  </action>

  <verify>
    <automated>grep -q '^## SiliconFlow Paid Tier vs Gemini Free' Deploy.md &amp;&amp; grep -q '^## Vertex AI Infrastructure Plan (Milestone B.5)' Deploy.md &amp;&amp; grep -q '^## Recommended Upgrade Path' Deploy.md</automated>
  </verify>

  <acceptance_criteria>
    - `grep -q '^## SiliconFlow Paid Tier vs Gemini Free' Deploy.md` returns 0
    - `grep -q '^## Vertex AI Infrastructure Plan (Milestone B.5)' Deploy.md` returns 0
    - `grep -q '^## Recommended Upgrade Path' Deploy.md` returns 0
    - `grep -n '## 9. Troubleshooting' Deploy.md` line number is LESS than `grep -n '## SiliconFlow Paid Tier vs Gemini Free' Deploy.md` (appended at end, not inserted mid-file)
    - `grep -c '^| SiliconFlow Qwen3-VL-32B' Deploy.md` returns 1 (trade-off table row present)
    - `grep -c '^| Gemini Vision free tier' Deploy.md` returns 1
    - `grep -c '^| Vertex AI paid (future)' Deploy.md` returns 1
    - `grep -q 'docs/VERTEX_AI_MIGRATION_SPEC.md' Deploy.md` returns 0 (forward link to Phase 16 spec present)
    - `grep -q '¥0.0013/img' Deploy.md` returns 0 (verbatim cost figure from PRD)
    - `grep -q '500 RPD' Deploy.md` returns 0 (verbatim Gemini free-tier limit)
    - `grep -q 'Option A' Deploy.md` returns 0 AND `grep -q 'Option B' Deploy.md` returns 0 (both migration options documented)
    - `grep -c '^## ' Deploy.md` returns exactly 3 more than the pre-edit count (3 sections added, no other ## lines renamed/removed)
  </acceptance_criteria>

  <done>
    `Deploy.md` has three new sections at the end with verbatim content from PRD §B4.3 + §B5. All existing content above section 9 unchanged. All acceptance criteria pass.
  </done>
</task>

</tasks>

<verification>
Run acceptance_criteria grep commands. Open `Deploy.md`, scroll to end, confirm ordering: section 9 Troubleshooting → `---` → SiliconFlow Paid Tier vs Gemini Free → Vertex AI Infrastructure Plan → Recommended Upgrade Path. Read the new sections top-to-bottom to confirm they match PRD §B4.3 + §B5 content.
</verification>

<success_criteria>
- Three new sections appended at end of Deploy.md
- No edits to existing sections 1–9
- Forward link to `docs/VERTEX_AI_MIGRATION_SPEC.md` present
- All acceptance_criteria grep commands pass
</success_criteria>

<output>
After completion, create `.planning/phases/15-docs-runbook/15-02-deploy-md-updates-SUMMARY.md` documenting: lines appended, sections added, grep-verified row counts for each table, and confirmation that no pre-existing content was modified (git diff shows additions only).
</output>
