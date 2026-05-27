# Phase 16: Vertex AI Infrastructure Preparation (B5) - Context

**Gathered:** 2026-04-30
**Status:** Ready for planning
**Source:** PRD Express Path (`.planning/MILESTONE_v3.2_REQUIREMENTS.md` §B5)

<domain>
## Phase Boundary

**Delivers:** Design-and-documentation artifacts for migrating from Gemini API free tier to Vertex AI OAuth2 with cross-project quota isolation. **No production code changes.** Four artifacts:
1. `docs/VERTEX_AI_MIGRATION_SPEC.md` — GCP project setup, SA naming, OAuth2 token management, pricing comparison, backward-compat design sketch
2. `credentials/vertex_ai_service_account_example.json` — schema-only template, no real credentials
3. `scripts/estimate_vertex_ai_cost.py` — cost estimation CLI (works standalone, no network calls)
4. `CLAUDE.md` + `Deploy.md` updates (§ "Vertex AI Migration Path" in CLAUDE.md, § "Recommended Upgrade Path" in Deploy.md — coordinated with Phase 15)

**Does NOT deliver:**
- Any Vertex AI SDK integration into `lib/api_keys.py` or `lib/llm_client.py` — deferred to post-v3.2
- Real service account credentials — template only (placeholders like `YOUR_PROJECT_ID`)
- GCP project provisioning or IAM role changes — operator runs those manually using the spec
- Integration tests against Vertex AI API — no live API calls from this phase's artifacts

**Independence:** This phase has zero code dependencies and can run fully in parallel with Phase 12-15. Artifacts are purely additive (new files + CLAUDE.md/Deploy.md append-only edits).

</domain>

<decisions>
## Implementation Decisions (from PRD §B5)

### VERTEX_AI_MIGRATION_SPEC.md (VERT-01) at `docs/VERTEX_AI_MIGRATION_SPEC.md`

**Sections (MANDATORY):**

1. **GCP Project Setup**
   - Required APIs to enable: Vertex AI API, Generative Language API (aiplatform.googleapis.com, generativelanguage.googleapis.com)
   - Service account creation workflow via `gcloud iam service-accounts create`
   - IAM roles required: `roles/aiplatform.user` (minimum) + `roles/aiplatform.admin` (if managing endpoints)
   - Naming convention:
     - `omnigraph-embedding-sa@{project}.iam.gserviceaccount.com` (for embeddings)
     - `omnigraph-llm-sa@{project}.iam.gserviceaccount.com` (for LLM calls, if split)
   - Recommended project split: **Option A** — Two projects (embedding + LLM), each with isolated quota pool

2. **OAuth2 Token Management**
   - How to create initial service account JSON key (`gcloud iam service-accounts keys create`)
   - How Vertex AI SDK (`google-cloud-aiplatform`) auto-refreshes OAuth2 tokens from SA key
   - Refresh failure fallback: log error, fall back to Gemini API key if available (backward-compat)
   - Key rotation policy: rotate SA keys every 90 days per Google security guidance

3. **Pricing Comparison**
   - Gemini API free tier: 100 RPM embedding, 500 RPD vision, 1M tok/min LLM (shared GCP project quota pool)
   - Vertex AI paid: per-request billing (see GCP pricing pages for exact ¥/request)
   - Recommendation: SiliconFlow for Vision (¥0.0013/img, cheapest reliable), Vertex AI for embedding (if 100 RPM insufficient), DeepSeek for LLM (on-prem, no GCP dependency)

4. **Code Integration Roadmap (deferred)**
   - Sketch of `lib/vertex_ai_client.py` with `init_vertex_ai(project_id, location, service_account_path)` → returns OAuth2-backed client
   - Backward-compat: `lib/api_keys.py` tries Vertex AI first, falls back to Gemini API key if SA key missing or invalid
   - Modification touchpoints in existing code (file:line references where adapter would plug in)

5. **Migration Timeline & Trigger Criteria**
   - When to migrate: batch growth beyond 100 RPM embedding OR 500 RPD vision
   - Phased rollout: (1) provision GCP + SA, (2) add `lib/vertex_ai_client.py`, (3) wire into `lib/api_keys.py` fallback chain, (4) validate via shadow run, (5) flip primary

### SA Template (VERT-02) at `credentials/vertex_ai_service_account_example.json`

Schema verbatim from PRD §B5.2:
```json
{
  "type": "service_account",
  "project_id": "YOUR_PROJECT_ID",
  "private_key_id": "PLACEHOLDER_KEY_ID",
  "private_key": "-----BEGIN PRIVATE KEY-----\nPLACEHOLDER\n-----END PRIVATE KEY-----\n",
  "client_email": "omnigraph-embedding-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com",
  "client_id": "PLACEHOLDER_CLIENT_ID",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/PLACEHOLDER"
}
```

**Guard:** `credentials/` directory MUST be gitignored (check `.gitignore`; add if missing). Template contains NO real credentials — only `PLACEHOLDER_*` strings and the literal `YOUR_PROJECT_ID` marker.

### Cost Estimation Script (VERT-04) at `scripts/estimate_vertex_ai_cost.py`

**CLI signature:**
```bash
python scripts/estimate_vertex_ai_cost.py --articles 282 --avg-images-per-article 25
```

**Output format (verbatim from PRD §B5.4):**
```
Estimated cost for 282 articles with 25 images/article:
- Embedding (Vertex AI): ¥xxx/month (vs ¥0 free tier)
- Vision (SiliconFlow): ¥xxx/month
- LLM (DeepSeek): ¥xxx/month
- Total: ¥xxx/month
```

**Assumptions (HARDCODED constants, documented at top of script):**
- Vertex AI embedding: $0.00002/1k chars (gemini-embedding-004), avg 1500 chars/chunk, 30 chunks/article
- SiliconFlow Qwen3-VL-32B: ¥0.0013/image
- DeepSeek chat: ¥0.0014/1k input + ¥0.0028/1k output tokens; avg 4000 input + 800 output per classification + chunk extraction
- USD→CNY: 7.2 (constant; document in script header)
- All numbers are ESTIMATES for budget planning, not invoices

**No network calls.** Script runs offline with hardcoded rates; operator re-runs it if rates change.

### CLAUDE.md & Deploy.md Additions (VERT-03)

Coordinated with Phase 15 (owns docs authorship). This phase provides the **content** for two sections:

**CLAUDE.md § "Vertex AI Migration Path"** (after "Lessons Learned"):
- Problem statement (quota coupling causes batch kills)
- Recommendation: SiliconFlow for Vision, Gemini API key for embedding until 429 ceiling, then migrate
- Pointer: "See `docs/VERTEX_AI_MIGRATION_SPEC.md` for full spec"

**Deploy.md § "Recommended Upgrade Path"** (new section at end):
- Production should use Vertex AI OAuth2 + cross-project quota isolation
- Dev/test: current API key is fine
- Cost estimate template: `python scripts/estimate_vertex_ai_cost.py --articles {N} --avg-images-per-article {M}`

### Claude's Discretion
- **Actual pricing numbers** in cost estimation — planner uses current published GCP rates (2026-04); if rates change, operator re-runs script after editing constants at top
- **Markdown structure** inside `VERTEX_AI_MIGRATION_SPEC.md` — planner picks section ordering as long as all 5 required sections exist
- **Example commands** in spec (e.g., specific `gcloud` commands) — planner writes working examples from Google docs

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source of Truth
- `.planning/MILESTONE_v3.2_REQUIREMENTS.md` §B5 — verbatim requirements
- `.planning/MILESTONE_v3.2_REQUIREMENTS.md` §B4 — coordination with Phase 15 docs updates

### GCP / Vertex AI External Docs (planner researches)
- https://cloud.google.com/vertex-ai/docs/authentication — OAuth2 patterns
- https://cloud.google.com/vertex-ai/pricing — current pricing
- https://cloud.google.com/sdk/docs/install-sdk — gcloud install

### Existing Files to Read
- `lib/api_keys.py` — current key management pattern (future Vertex AI adapter plugs here)
- `lib/llm_client.py` — current LLM client (future Vertex AI adapter wraps)
- `.gitignore` — verify `credentials/` is excluded
- `CLAUDE.md` § "Phase 7 scoped env vars" — existing env var naming pattern for coherence

</canonical_refs>

<specifics>
## Specific Ideas

### Script Skeleton (`scripts/estimate_vertex_ai_cost.py`)

```python
"""Estimate monthly cost for batch ingestion with Vertex AI + SiliconFlow + DeepSeek.

Standalone: no network calls, no imports of project modules. Rates hardcoded at top.
Rerun after editing rates if GCP/DeepSeek/SiliconFlow pricing changes.
"""

import argparse

# Pricing constants (2026-04 rates)
VERTEX_EMBEDDING_PER_1K_CHARS_USD = 0.00002
SILICONFLOW_PER_IMAGE_CNY = 0.0013
DEEPSEEK_INPUT_PER_1K_TOKENS_CNY = 0.0014
DEEPSEEK_OUTPUT_PER_1K_TOKENS_CNY = 0.0028
USD_TO_CNY = 7.2

# Workload assumptions
AVG_CHARS_PER_CHUNK = 1500
AVG_CHUNKS_PER_ARTICLE = 30
AVG_INPUT_TOKENS_PER_CLASSIFICATION = 4000
AVG_OUTPUT_TOKENS_PER_CLASSIFICATION = 800


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--articles", type=int, required=True)
    parser.add_argument("--avg-images-per-article", type=int, required=True)
    args = parser.parse_args()

    embedding_cost = (
        args.articles * AVG_CHUNKS_PER_ARTICLE * AVG_CHARS_PER_CHUNK
        * VERTEX_EMBEDDING_PER_1K_CHARS_USD / 1000 * USD_TO_CNY
    )
    vision_cost = args.articles * args.avg_images_per_article * SILICONFLOW_PER_IMAGE_CNY
    llm_cost = args.articles * (
        AVG_INPUT_TOKENS_PER_CLASSIFICATION * DEEPSEEK_INPUT_PER_1K_TOKENS_CNY / 1000
        + AVG_OUTPUT_TOKENS_PER_CLASSIFICATION * DEEPSEEK_OUTPUT_PER_1K_TOKENS_CNY / 1000
    )
    total = embedding_cost + vision_cost + llm_cost

    print(f"Estimated cost for {args.articles} articles with {args.avg_images_per_article} images/article:")
    print(f"- Embedding (Vertex AI): ¥{embedding_cost:.2f}/month (vs ¥0 free tier)")
    print(f"- Vision (SiliconFlow): ¥{vision_cost:.2f}/month")
    print(f"- LLM (DeepSeek): ¥{llm_cost:.2f}/month")
    print(f"- Total: ¥{total:.2f}/month")


if __name__ == "__main__":
    main()
```

### Acceptance Check Commands

```bash
# Template JSON is valid JSON
python -c "import json; json.load(open('credentials/vertex_ai_service_account_example.json'))"

# Script runs and produces expected format
python scripts/estimate_vertex_ai_cost.py --articles 282 --avg-images-per-article 25 | grep -E '^(Estimated|- (Embedding|Vision|LLM|Total))'

# Spec exists with all 5 required sections
grep -c '^## ' docs/VERTEX_AI_MIGRATION_SPEC.md  # should return 5

# CLAUDE.md has migration path section
grep -q 'Vertex AI Migration Path' CLAUDE.md

# Deploy.md has upgrade path section
grep -q 'Recommended Upgrade Path' Deploy.md

# .gitignore excludes credentials (but keeps example)
grep -qE 'credentials/.*' .gitignore && grep -qv 'credentials/vertex_ai_service_account_example.json' .gitignore
```

</specifics>

<deferred>
## Deferred Ideas (explicitly post-v3.2)

- **Actual `lib/vertex_ai_client.py` implementation** — spec documents the sketch, code lives in future phase
- **Service account provisioning automation** (Terraform, Pulumi) — operator runs `gcloud` manually per spec
- **OAuth2 token refresh integration into `lib/api_keys.py`** — fallback chain design documented, code change deferred
- **Quota monitoring dashboard** (Grafana, CloudWatch) — operator checks GCP Console manually for now
- **Migration runbook** (step-by-step flip from Gemini API key to Vertex AI) — post-v3.2 deliverable once code integration phase runs

</deferred>

---

*Phase: 16-vertex-ai-design*
*Context gathered: 2026-04-30 via PRD Express Path*
