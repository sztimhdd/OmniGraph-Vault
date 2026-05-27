---
phase: 16-vertex-ai-design
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - docs/VERTEX_AI_MIGRATION_SPEC.md
autonomous: true
requirements:
  - VERT-01
must_haves:
  truths:
    - "docs/VERTEX_AI_MIGRATION_SPEC.md exists and has exactly five top-level sections"
    - "Spec documents GCP project setup, OAuth2 token management, pricing comparison, code integration roadmap, migration timeline"
    - "Spec contains no real credentials — only YOUR_PROJECT_ID and PLACEHOLDER_* markers where secrets would appear"
    - "Spec references omnigraph-embedding-sa and omnigraph-llm-sa naming per PRD §B5.1"
  artifacts:
    - path: "docs/VERTEX_AI_MIGRATION_SPEC.md"
      provides: "Full migration spec — GCP setup, OAuth2, pricing, code roadmap, timeline"
      contains: "## GCP Project Setup"
      min_lines: 120
  key_links:
    - from: "docs/VERTEX_AI_MIGRATION_SPEC.md"
      to: "lib/api_keys.py"
      via: "§ Code Integration Roadmap references api_keys.py fallback-chain touchpoint"
      pattern: "lib/api_keys\\.py"
    - from: "docs/VERTEX_AI_MIGRATION_SPEC.md"
      to: "scripts/estimate_vertex_ai_cost.py"
      via: "§ Pricing Comparison links to cost script for budget planning"
      pattern: "estimate_vertex_ai_cost\\.py"
---

<objective>
Write the Vertex AI migration specification document — the canonical reference for operators who will later execute the actual migration.

Purpose: Operator can follow this spec to (1) provision GCP projects, (2) create service accounts, (3) understand cost implications, (4) locate future integration points in `lib/api_keys.py`, and (5) decide when to trigger migration. Zero code changes — pure documentation artifact.

Output: `docs/VERTEX_AI_MIGRATION_SPEC.md` with five top-level (`##`) sections exactly: GCP Project Setup, OAuth2 Token Management, Pricing Comparison, Code Integration Roadmap, Migration Timeline & Trigger Criteria.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@.planning/phases/16-vertex-ai-design/16-CONTEXT.md
@.planning/MILESTONE_v3.2_REQUIREMENTS.md
@CLAUDE.md
@lib/api_keys.py

<interfaces>
From CLAUDE.md § "Phase 7 scoped env vars":
- Preferred key var: `OMNIGRAPH_GEMINI_KEY` (namespaced)
- Rotation pool: `OMNIGRAPH_GEMINI_KEYS` (comma-separated)
- Per-model RPM caps: `OMNIGRAPH_RPM_*`
- Fallback retained: `GEMINI_API_KEY`

From lib/api_keys.py (current fallback chain precedence):
1. OMNIGRAPH_GEMINI_KEYS (comma-separated pool)
2. OMNIGRAPH_GEMINI_KEY and/or GEMINI_API_KEY_BACKUP combined
3. GEMINI_API_KEY (single-key fallback)
4. RuntimeError

Future Vertex AI adapter should slot in BEFORE step 1 (try Vertex AI OAuth2 → fall back to Gemini API key chain).
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write VERTEX_AI_MIGRATION_SPEC.md with all five required sections</name>
  <files>docs/VERTEX_AI_MIGRATION_SPEC.md</files>
  <read_first>
    - .planning/phases/16-vertex-ai-design/16-CONTEXT.md (§ decisions → VERTEX_AI_MIGRATION_SPEC.md)
    - .planning/MILESTONE_v3.2_REQUIREMENTS.md lines 239-305 (§B5 requirements verbatim)
    - lib/api_keys.py (understand current fallback chain for § Code Integration Roadmap)
    - CLAUDE.md § "Phase 7 scoped env vars" (align with existing OMNIGRAPH_* naming)
  </read_first>
  <action>
Create `docs/VERTEX_AI_MIGRATION_SPEC.md` with the structure below. All five `##` headings are MANDATORY and must appear in this order (planner's locked decision).

Use this exact skeleton. Fill in the content as described under each heading — write real working `gcloud` commands, real IAM role names, real file:line references to `lib/api_keys.py`, and real pricing numbers (2026-04 GCP published rates):

```markdown
# Vertex AI Migration Specification

**Status:** Design artifact — no code changes implemented as of v3.2 Phase 16.
**Operator action required:** This is the canonical reference for executing the migration when batch load exceeds Gemini API free-tier quotas. See § Migration Timeline & Trigger Criteria for when to act.

**Related artifacts:**
- `credentials/vertex_ai_service_account_example.json` — service account key schema template
- `scripts/estimate_vertex_ai_cost.py` — monthly cost estimator
- `CLAUDE.md § Vertex AI Migration Path` — quick reference for contributors
- `Deploy.md § Recommended Upgrade Path` — production rollout guidance

---

## GCP Project Setup

### Required APIs

Enable these APIs in each target GCP project:

- `aiplatform.googleapis.com` (Vertex AI API) — embedding + LLM endpoints
- `generativelanguage.googleapis.com` (Generative Language API) — fallback for direct Gemini calls via Vertex routing

Enable via gcloud:

```bash
gcloud services enable aiplatform.googleapis.com generativelanguage.googleapis.com \
  --project=YOUR_PROJECT_ID
```

### Project Split Strategy

**Decision (PRD §B5.1): Option A — Two projects.**

| Project | Purpose | Service Account |
|---|---|---|
| `omnigraph-embedding-prod` | Embedding requests only (isolated quota pool) | `omnigraph-embedding-sa@omnigraph-embedding-prod.iam.gserviceaccount.com` |
| `omnigraph-llm-prod` | LLM generation requests (separate quota pool) | `omnigraph-llm-sa@omnigraph-llm-prod.iam.gserviceaccount.com` |

Rationale: Vertex AI enforces per-project quota. Splitting embedding and LLM into distinct projects prevents a single service's 429 from killing the entire batch — the exact failure mode that motivates this migration.

### Service Account Creation

```bash
# Embedding project
gcloud iam service-accounts create omnigraph-embedding-sa \
  --display-name="OmniGraph-Vault Embedding Service Account" \
  --project=omnigraph-embedding-prod

# LLM project
gcloud iam service-accounts create omnigraph-llm-sa \
  --display-name="OmniGraph-Vault LLM Service Account" \
  --project=omnigraph-llm-prod
```

### IAM Roles

Bind the minimum roles required:

| Role | Scope | Why |
|---|---|---|
| `roles/aiplatform.user` | Project-level | Call Vertex AI endpoints (embedding + predict) — minimum required |
| `roles/aiplatform.admin` | Project-level | Only if this SA will also manage custom endpoints — otherwise omit |

```bash
gcloud projects add-iam-policy-binding omnigraph-embedding-prod \
  --member="serviceAccount:omnigraph-embedding-sa@omnigraph-embedding-prod.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding omnigraph-llm-prod \
  --member="serviceAccount:omnigraph-llm-sa@omnigraph-llm-prod.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

---

## OAuth2 Token Management

### Initial Key Creation

Service account keys are long-lived secrets. Create one JSON key per SA and store under `credentials/` (gitignored except for the template):

```bash
gcloud iam service-accounts keys create credentials/omnigraph-embedding-sa.json \
  --iam-account=omnigraph-embedding-sa@omnigraph-embedding-prod.iam.gserviceaccount.com

gcloud iam service-accounts keys create credentials/omnigraph-llm-sa.json \
  --iam-account=omnigraph-llm-sa@omnigraph-llm-prod.iam.gserviceaccount.com
```

Template schema: `credentials/vertex_ai_service_account_example.json` (tracked in git with placeholder values only).

### Automatic Token Refresh

The Vertex AI Python SDK (`google-cloud-aiplatform`) handles OAuth2 token refresh automatically:

- At init time the SDK reads the SA JSON key and exchanges it for a short-lived OAuth2 access token (1 hour TTL).
- Before each API call the SDK checks token TTL and refreshes transparently if expiry is within 5 minutes.
- Operator code does not call the OAuth2 refresh endpoint directly.

### Refresh Failure Fallback

If Vertex AI is unreachable or the SA key is revoked, the future integration must fall back gracefully to the existing Gemini API key chain. Design sketch (see § Code Integration Roadmap below):

1. Catch `google.auth.exceptions.RefreshError` from the Vertex AI client.
2. Log a structured error (`logger.error("Vertex AI refresh failed; falling back to Gemini API key", exc_info=True)`).
3. Route the request through the current `lib.api_keys.load_keys()` chain.

### Key Rotation Policy

Per Google's security guidance, rotate SA keys every **90 days**. Procedure:

1. Create new key: `gcloud iam service-accounts keys create credentials/omnigraph-embedding-sa-new.json ...`
2. Update deployment to point at new file.
3. Verify traffic flows on new key (inspect GCP audit logs for the old key ID).
4. Delete the old key: `gcloud iam service-accounts keys delete {OLD_KEY_ID} --iam-account=...`

---

## Pricing Comparison

All prices in 2026-04 published rates. Rerun `scripts/estimate_vertex_ai_cost.py` after any rate change.

### Gemini API Free Tier (current)

| Service | Quota | Caveat |
|---|---|---|
| Embedding | 100 RPM | Shared with LLM → one 429 kills batch |
| Vision | 500 RPD | Very restrictive for batch ingestion |
| LLM | 1M tok/min | Generous but shares project quota pool |

### Vertex AI Paid Tier (target)

| Service | Rate (2026-04) | Notes |
|---|---|---|
| Embedding (gemini-embedding-004) | $0.00002 per 1k characters | Pay-per-request, no hard quota cap until you hit billing limits |
| Vision (Vertex AI multimodal) | See GCP pricing page; generally higher than SiliconFlow | Not recommended — use SiliconFlow instead |
| LLM (gemini-2.5-flash via Vertex) | Per-request; see GCP pricing | Consider DeepSeek for on-prem LLM |

### Recommendation

- **Vision → SiliconFlow Qwen3-VL-32B (¥0.0013/image).** Cheapest reliable option; no GCP dependency.
- **Embedding → Gemini API free tier until 429 ceiling hit, then Vertex AI.** 100 RPM is enough for ~3k-article batches over hours. When batches scale beyond, flip to Vertex AI.
- **LLM → DeepSeek.** On-prem, no GCP dependency, cheap.

Run `scripts/estimate_vertex_ai_cost.py --articles {N} --avg-images-per-article {M}` to project monthly cost.

---

## Code Integration Roadmap

Code integration is **deferred to post-v3.2**. This section documents the plan so the future implementer can execute without re-designing.

### New Module: `lib/vertex_ai_client.py`

Proposed interface (not yet implemented):

```python
def init_vertex_ai(
    project_id: str,
    location: str = "us-central1",
    service_account_path: str | None = None,
) -> "VertexAIClient":
    """Initialize Vertex AI client with OAuth2 SA auth.

    If service_account_path is None, falls back to Application Default Credentials.
    Returns a client wrapper exposing embed() and generate() with the same
    signatures as the existing Gemini client wrappers in lib/llm_client.py.
    """
```

### Backward-Compat Touchpoints

**File:** `lib/api_keys.py` (current fallback chain at lines 28-60)

The future `vertex_ai_client` should plug in as step 0 of the chain, BEFORE the existing `OMNIGRAPH_GEMINI_KEYS` lookup:

```
0. Try Vertex AI via `OMNIGRAPH_VERTEX_SA_PATH` → return Vertex-backed client
1. OMNIGRAPH_GEMINI_KEYS (pool) → rotate Gemini API keys
2. OMNIGRAPH_GEMINI_KEY + GEMINI_API_KEY_BACKUP
3. GEMINI_API_KEY
4. RuntimeError
```

**File:** `lib/llm_client.py` (current LLM client factory)

Add a new factory function `get_vertex_backed_client(project_id, location)` parallel to the existing Gemini factory. The routing decision lives in `api_keys.py`, not in `llm_client.py`.

### Environment Variables (future)

Follow the existing `OMNIGRAPH_*` naming convention (per CLAUDE.md § "Phase 7 scoped env vars"):

| Variable | Purpose |
|---|---|
| `OMNIGRAPH_VERTEX_SA_PATH` | Absolute path to SA JSON key file |
| `OMNIGRAPH_VERTEX_EMBEDDING_PROJECT` | GCP project ID for embedding calls |
| `OMNIGRAPH_VERTEX_LLM_PROJECT` | GCP project ID for LLM calls (if split) |
| `OMNIGRAPH_VERTEX_LOCATION` | Default `us-central1`; override if data residency required |

---

## Migration Timeline & Trigger Criteria

### When to Migrate

Migrate from Gemini API free tier to Vertex AI paid when **any** of these conditions become routinely true:

- Batch ingestion hits **>100 RPM embedding** ceiling (observed 429s on embedding endpoint)
- Batch ingestion hits **>500 RPD vision** ceiling (observed daily quota exhaustion on vision)
- Single 429 on one service repeatedly kills the full batch (quota coupling pain becomes blocking)

Run `scripts/estimate_vertex_ai_cost.py` with projected volume to decide whether the cost is justified.

### Phased Rollout (5 steps)

1. **Provision GCP infra** (this spec as runbook): enable APIs, create projects, create SAs, create keys.
2. **Add `lib/vertex_ai_client.py`** per the Code Integration Roadmap sketch.
3. **Wire into `lib/api_keys.py` fallback chain** as step 0 (Vertex AI first, Gemini API key chain as fallback).
4. **Shadow-run validation:** run a known-good fixture through Vertex AI path, compare embeddings/outputs against Gemini API path for drift (>1% cosine distance on embeddings = investigate).
5. **Flip primary:** remove `OMNIGRAPH_VERTEX_SA_PATH=None` fallback from production config; Vertex AI becomes the default path.

### Rollback Plan

If Vertex AI migration fails post-flip:
- Set `OMNIGRAPH_VERTEX_SA_PATH=` (empty) to force fallback to Gemini API key chain.
- Observe logs for `Vertex AI refresh failed; falling back` — if sustained, investigate SA key, IAM roles, API enablement.
- Full rollback: revert the `lib/api_keys.py` change; code reverts to pre-migration behavior transparently.
```

After writing the file, verify structure:

```bash
test -f docs/VERTEX_AI_MIGRATION_SPEC.md
grep -c '^## ' docs/VERTEX_AI_MIGRATION_SPEC.md    # must return 5
grep -q 'GCP Project Setup' docs/VERTEX_AI_MIGRATION_SPEC.md
grep -q 'OAuth2 Token Management' docs/VERTEX_AI_MIGRATION_SPEC.md
grep -q 'Pricing Comparison' docs/VERTEX_AI_MIGRATION_SPEC.md
grep -q 'Code Integration Roadmap' docs/VERTEX_AI_MIGRATION_SPEC.md
grep -q 'Migration Timeline' docs/VERTEX_AI_MIGRATION_SPEC.md
grep -q 'lib/api_keys.py' docs/VERTEX_AI_MIGRATION_SPEC.md
grep -q 'omnigraph-embedding-sa' docs/VERTEX_AI_MIGRATION_SPEC.md
```

Do NOT include any real credentials. Every email must use `YOUR_PROJECT_ID` or a plausible public project name (`omnigraph-embedding-prod`). Every key ID must be omitted or shown as `{OLD_KEY_ID}`.
  </action>
  <verify>
    <automated>test -f docs/VERTEX_AI_MIGRATION_SPEC.md && [ "$(grep -c '^## ' docs/VERTEX_AI_MIGRATION_SPEC.md)" -ge 5 ] && grep -q 'GCP Project Setup' docs/VERTEX_AI_MIGRATION_SPEC.md && grep -q 'OAuth2 Token Management' docs/VERTEX_AI_MIGRATION_SPEC.md && grep -q 'Pricing Comparison' docs/VERTEX_AI_MIGRATION_SPEC.md && grep -q 'Code Integration Roadmap' docs/VERTEX_AI_MIGRATION_SPEC.md && grep -q 'Migration Timeline' docs/VERTEX_AI_MIGRATION_SPEC.md && grep -q 'lib/api_keys.py' docs/VERTEX_AI_MIGRATION_SPEC.md && grep -q 'omnigraph-embedding-sa' docs/VERTEX_AI_MIGRATION_SPEC.md</automated>
  </verify>
  <acceptance_criteria>
    - `test -f docs/VERTEX_AI_MIGRATION_SPEC.md` exits 0
    - `grep -c '^## ' docs/VERTEX_AI_MIGRATION_SPEC.md` returns an integer ≥ 5
    - Each of these `grep -q` commands exits 0: 'GCP Project Setup', 'OAuth2 Token Management', 'Pricing Comparison', 'Code Integration Roadmap', 'Migration Timeline'
    - `grep -q 'lib/api_keys.py' docs/VERTEX_AI_MIGRATION_SPEC.md` exits 0 (code integration references are concrete)
    - `grep -q 'omnigraph-embedding-sa' docs/VERTEX_AI_MIGRATION_SPEC.md` exits 0 (naming convention per PRD §B5.1)
    - File does NOT contain real credentials: `grep -E 'AIza[0-9A-Za-z_-]{35}' docs/VERTEX_AI_MIGRATION_SPEC.md` returns empty (no Google API key pattern)
    - File length is ≥ 120 lines (`wc -l docs/VERTEX_AI_MIGRATION_SPEC.md` returns ≥ 120)
  </acceptance_criteria>
  <done>Spec file written with all five mandated sections, references to `lib/api_keys.py` for future integration, SA naming per PRD §B5.1, zero real credentials, ≥120 lines.</done>
</task>

</tasks>

<verification>
Manually skim the spec once to confirm readability. Spot-check that `gcloud` commands are syntactically valid (no missing flags).
</verification>

<success_criteria>
- [ ] `docs/VERTEX_AI_MIGRATION_SPEC.md` exists with exactly 5 `##` sections
- [ ] All five mandated section names present (grep-verified)
- [ ] References to `lib/api_keys.py` and future `lib/vertex_ai_client.py` included
- [ ] SA naming follows `omnigraph-embedding-sa` / `omnigraph-llm-sa` convention
- [ ] Zero real credentials committed (grep for Google API key pattern returns empty)
</success_criteria>

<output>
After completion, create `.planning/phases/16-vertex-ai-design/16-01-SUMMARY.md` summarizing what was written.
</output>
