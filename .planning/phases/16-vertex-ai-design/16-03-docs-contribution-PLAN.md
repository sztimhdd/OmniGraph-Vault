---
phase: 16-vertex-ai-design
plan: 03
type: execute
wave: 2
depends_on:
  - "16-01"
  - "16-02"
files_modified:
  - CLAUDE.md
  - Deploy.md
autonomous: true
requirements:
  - VERT-03
must_haves:
  truths:
    - "CLAUDE.md contains a new section titled 'Vertex AI Migration Path' that points to docs/VERTEX_AI_MIGRATION_SPEC.md"
    - "Deploy.md contains a new section titled 'Recommended Upgrade Path' that references scripts/estimate_vertex_ai_cost.py"
    - "Both sections are append-only — no existing content is rewritten or reformatted"
    - "CLAUDE.md section appears after the 'Lessons Learned' section (per PRD §B5.3)"
  artifacts:
    - path: "CLAUDE.md"
      provides: "§ Vertex AI Migration Path pointing contributors to the full spec"
      contains: "Vertex AI Migration Path"
    - path: "Deploy.md"
      provides: "§ Recommended Upgrade Path with cost estimation command template"
      contains: "Recommended Upgrade Path"
  key_links:
    - from: "CLAUDE.md"
      to: "docs/VERTEX_AI_MIGRATION_SPEC.md"
      via: "link reference in § Vertex AI Migration Path"
      pattern: "docs/VERTEX_AI_MIGRATION_SPEC\\.md"
    - from: "Deploy.md"
      to: "scripts/estimate_vertex_ai_cost.py"
      via: "command template in § Recommended Upgrade Path"
      pattern: "scripts/estimate_vertex_ai_cost\\.py"
---

<objective>
Contribute two append-only documentation sections — one to `CLAUDE.md`, one to `Deploy.md` — that surface the Vertex AI migration path to contributors and operators without requiring them to dig into the full spec.

Purpose: A reader of `CLAUDE.md` should understand WHY quota coupling is a problem and WHERE to find the full spec. A reader of `Deploy.md` should see the production recommendation and have a copy-paste command to estimate cost.

Output:
- `CLAUDE.md` + one new section "Vertex AI Migration Path" (after § "Lessons Learned")
- `Deploy.md` + one new section "Recommended Upgrade Path" (appended)

Depends on Plans 01 and 02 being complete so the referenced artifacts actually exist when contributors click through.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@.planning/phases/16-vertex-ai-design/16-CONTEXT.md
@.planning/MILESTONE_v3.2_REQUIREMENTS.md
@CLAUDE.md
@Deploy.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Append "Vertex AI Migration Path" section to CLAUDE.md</name>
  <files>CLAUDE.md</files>
  <read_first>
    - CLAUDE.md (full file — need to locate the existing "## Lessons Learned" section; new section goes AFTER it)
    - .planning/phases/16-vertex-ai-design/16-CONTEXT.md (§ decisions → CLAUDE.md & Deploy.md Additions (VERT-03))
    - docs/VERTEX_AI_MIGRATION_SPEC.md (written by Plan 01 — confirm path/name before linking)
  </read_first>
  <action>
**Surgical change: append only. Do not modify any existing content in CLAUDE.md.**

1. Open `CLAUDE.md`, locate the existing `## Lessons Learned` section.
2. Immediately after the last bullet of `## Lessons Learned` (and before any subsequent section header, if one exists), insert the following new section:

```markdown
## Vertex AI Migration Path

### Problem: Quota Coupling

All current Gemini API calls (embedding + Vision + LLM) share a single GCP project's free-tier quota pool. When any one service triggers a 429 (rate limit), the entire batch stops — one slow endpoint kills ingestion of unrelated articles. This is the primary motivator for migrating to Vertex AI paid tier with cross-project quota isolation.

### Recommendation (current)

Until batch volume justifies the migration, stay on the split-provider approach:

- **Vision:** SiliconFlow Qwen3-VL-32B (¥0.0013/image, no GCP dependency)
- **Embedding:** Gemini API free tier (100 RPM — sufficient for current batches)
- **LLM:** DeepSeek chat (on-prem, no GCP dependency)

Only Gemini embedding still touches the GCP free-tier quota. If you observe repeated 429 errors on embedding calls during batch runs, it is time to trigger the migration.

### When to Migrate

Trigger the Vertex AI migration when **any** of these become routinely true:
- Batch ingestion regularly hits > 100 RPM embedding ceiling (visible as embedding-only 429s)
- Batch ingestion hits > 500 RPD vision ceiling (only applies if you move Vision back to Gemini — not current config)
- A single 429 on embedding kills the entire batch despite cascade retries

### Full Specification

See `docs/VERTEX_AI_MIGRATION_SPEC.md` for the complete migration runbook: GCP project setup, service account creation, OAuth2 token management, pricing comparison, code integration roadmap, and phased rollout plan.

To estimate monthly cost before migrating, run:

```bash
python scripts/estimate_vertex_ai_cost.py --articles {N} --avg-images-per-article {M}
```
```

3. Verify placement and content:

```bash
# Section header exists
grep -q '^## Vertex AI Migration Path$' CLAUDE.md

# Reference to the spec file is present and correct
grep -q 'docs/VERTEX_AI_MIGRATION_SPEC\.md' CLAUDE.md

# Reference to the cost script is present
grep -q 'scripts/estimate_vertex_ai_cost\.py' CLAUDE.md

# Existing "Lessons Learned" section is still there (regression check — we must not have deleted it)
grep -q '^## Lessons Learned$' CLAUDE.md

# "Vertex AI Migration Path" comes AFTER "Lessons Learned" in the file
awk '/^## Lessons Learned$/{lessons=NR} /^## Vertex AI Migration Path$/{vertex=NR} END{exit !(lessons && vertex && vertex > lessons)}' CLAUDE.md
```

Do NOT reformat or "tidy up" any neighboring content. Every line outside this new section must be byte-identical to its pre-change state.
  </action>
  <verify>
    <automated>grep -q '^## Vertex AI Migration Path$' CLAUDE.md && grep -q 'docs/VERTEX_AI_MIGRATION_SPEC\.md' CLAUDE.md && grep -q 'scripts/estimate_vertex_ai_cost\.py' CLAUDE.md && grep -q '^## Lessons Learned$' CLAUDE.md && awk '/^## Lessons Learned$/{lessons=NR} /^## Vertex AI Migration Path$/{vertex=NR} END{exit !(lessons && vertex && vertex > lessons)}' CLAUDE.md</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q '^## Vertex AI Migration Path$' CLAUDE.md` exits 0
    - `grep -q 'docs/VERTEX_AI_MIGRATION_SPEC\.md' CLAUDE.md` exits 0
    - `grep -q 'scripts/estimate_vertex_ai_cost\.py' CLAUDE.md` exits 0
    - Existing `## Lessons Learned` section still present (regression guard)
    - New section appears AFTER `## Lessons Learned` in file order (awk check exits 0)
    - The key phrases "quota coupling", "SiliconFlow", "DeepSeek", "100 RPM", "500 RPD" all present in the new section (`grep -E 'quota coupling|SiliconFlow|DeepSeek|100 RPM|500 RPD' CLAUDE.md` finds 5+ matches)
  </acceptance_criteria>
  <done>CLAUDE.md has a new § Vertex AI Migration Path after § Lessons Learned, pointing to the spec and cost script; zero edits to existing content.</done>
</task>

<task type="auto">
  <name>Task 2: Append "Recommended Upgrade Path" section to Deploy.md</name>
  <files>Deploy.md</files>
  <read_first>
    - Deploy.md (full file — identify the current last section; new section goes at the end)
    - .planning/phases/16-vertex-ai-design/16-CONTEXT.md (§ decisions → CLAUDE.md & Deploy.md Additions (VERT-03))
    - scripts/estimate_vertex_ai_cost.py (written by Plan 02 — confirm CLI flags before documenting)
  </read_first>
  <action>
**Surgical change: append only. Do not modify any existing content in Deploy.md.**

1. Open `Deploy.md`, navigate to the end of the file.
2. Append the following new section as the last section of the document:

```markdown

## Recommended Upgrade Path

### Production Deployments

Production deployments with sustained batch ingestion volumes should migrate from Gemini API free tier to **Vertex AI OAuth2 with cross-project quota isolation**. This prevents quota coupling — where a 429 in one service (e.g., embedding) kills an otherwise healthy batch that is not touching that service's limit.

Full migration runbook: `docs/VERTEX_AI_MIGRATION_SPEC.md`.

### Dev / Test Deployments

Current `GEMINI_API_KEY` + `OMNIGRAPH_GEMINI_KEYS` rotation pool remains sufficient. No migration needed for single-operator development work against small batches.

### Cost Estimation

Before migrating, estimate monthly spend with the standalone cost calculator:

```bash
python scripts/estimate_vertex_ai_cost.py --articles {N} --avg-images-per-article {M}
```

The script is offline (no GCP credentials needed), uses hardcoded 2026-04 pricing constants (edit at top of script if rates change), and produces a per-service CNY breakdown plus total.

Example:

```bash
python scripts/estimate_vertex_ai_cost.py --articles 282 --avg-images-per-article 25
```

Output lists Embedding (Vertex AI), Vision (SiliconFlow), LLM (DeepSeek) costs and a monthly total.
```

3. Verify:

```bash
# New section header exists
grep -q '^## Recommended Upgrade Path$' Deploy.md

# Cost script reference is present and correct
grep -q 'scripts/estimate_vertex_ai_cost\.py' Deploy.md

# Spec reference is present
grep -q 'docs/VERTEX_AI_MIGRATION_SPEC\.md' Deploy.md

# New section is at the end of the file (no headers after it) — tolerate trailing whitespace
grep -n '^## ' Deploy.md | tail -1 | grep -q 'Recommended Upgrade Path'
```

Do NOT reformat or "tidy up" any existing content. Every line outside this new section must be byte-identical to its pre-change state.
  </action>
  <verify>
    <automated>grep -q '^## Recommended Upgrade Path$' Deploy.md && grep -q 'scripts/estimate_vertex_ai_cost\.py' Deploy.md && grep -q 'docs/VERTEX_AI_MIGRATION_SPEC\.md' Deploy.md && grep -n '^## ' Deploy.md | tail -1 | grep -q 'Recommended Upgrade Path'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q '^## Recommended Upgrade Path$' Deploy.md` exits 0
    - `grep -q 'scripts/estimate_vertex_ai_cost\.py' Deploy.md` exits 0
    - `grep -q 'docs/VERTEX_AI_MIGRATION_SPEC\.md' Deploy.md` exits 0
    - `Recommended Upgrade Path` is the last `## ` heading in the file
    - Both example command lines from the section run if tested: `python scripts/estimate_vertex_ai_cost.py --articles 282 --avg-images-per-article 25` exits 0 (spot-check — Plan 02 already validates the script, this just confirms the doc example is accurate)
  </acceptance_criteria>
  <done>Deploy.md has a new § Recommended Upgrade Path at the end, pointing to the spec and cost script with a working example command; zero edits to existing content.</done>
</task>

</tasks>

<verification>
After both tasks, open `CLAUDE.md` and `Deploy.md` and confirm the new sections read naturally in context. Also confirm `git diff CLAUDE.md Deploy.md` shows only additions (no deletions, no reformatting).
</verification>

<success_criteria>
- [ ] CLAUDE.md has new § Vertex AI Migration Path after § Lessons Learned
- [ ] Deploy.md has new § Recommended Upgrade Path as last section
- [ ] Both sections link to the spec and the cost script
- [ ] No existing content was modified in either file (only additions)
</success_criteria>

<output>
After completion, create `.planning/phases/16-vertex-ai-design/16-03-SUMMARY.md` recording the two new section headers, their link targets, and confirmation that `git diff` shows additions-only.
</output>
