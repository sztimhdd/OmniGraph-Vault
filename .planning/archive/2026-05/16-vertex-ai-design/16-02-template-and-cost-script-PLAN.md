---
phase: 16-vertex-ai-design
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - credentials/vertex_ai_service_account_example.json
  - scripts/estimate_vertex_ai_cost.py
  - .gitignore
autonomous: true
requirements:
  - VERT-02
  - VERT-04
must_haves:
  truths:
    - "credentials/vertex_ai_service_account_example.json is valid JSON with all 10 required fields and only placeholder values"
    - ".gitignore excludes credentials/ but keeps vertex_ai_service_account_example.json tracked"
    - "scripts/estimate_vertex_ai_cost.py runs standalone (no project imports) and produces the exact PRD §B5.4 output format"
    - "Cost script accepts --articles and --avg-images-per-article as required CLI args"
    - "Cost script makes zero network calls; all pricing is hardcoded constants"
  artifacts:
    - path: "credentials/vertex_ai_service_account_example.json"
      provides: "Schema template for SA JSON key, placeholders only"
      contains: "service_account"
    - path: "scripts/estimate_vertex_ai_cost.py"
      provides: "Monthly cost estimator CLI"
      contains: "argparse"
      min_lines: 40
    - path: ".gitignore"
      provides: "Guard against committing real SA keys while keeping template tracked"
      contains: "credentials/"
  key_links:
    - from: ".gitignore"
      to: "credentials/vertex_ai_service_account_example.json"
      via: "negation rule (!credentials/vertex_ai_service_account_example.json) keeps template tracked despite credentials/ exclusion"
      pattern: "!credentials/vertex_ai_service_account_example\\.json"
    - from: "scripts/estimate_vertex_ai_cost.py"
      to: "PRD §B5.4 output format"
      via: "print statements match verbatim: 'Estimated cost for ...', '- Embedding (Vertex AI): ¥...', etc."
      pattern: "Estimated cost for"
---

<objective>
Create three small artifacts: (1) the SA JSON template with placeholders, (2) the standalone offline cost estimation script, (3) the `.gitignore` guard that excludes real keys but keeps the template tracked.

Purpose: Operator has a copy-paste SA template to fill in after `gcloud iam service-accounts keys create`, and a budget-planning CLI that works without any API credentials or network access.

Output:
- `credentials/vertex_ai_service_account_example.json` (placeholder values only)
- `scripts/estimate_vertex_ai_cost.py` (argparse CLI, hardcoded pricing constants)
- `.gitignore` updated with `credentials/` + negation for the example file
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@.planning/phases/16-vertex-ai-design/16-CONTEXT.md
@.planning/MILESTONE_v3.2_REQUIREMENTS.md
@.gitignore
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create credentials/ directory, SA template JSON, and .gitignore guard</name>
  <files>credentials/vertex_ai_service_account_example.json, .gitignore</files>
  <read_first>
    - .planning/phases/16-vertex-ai-design/16-CONTEXT.md (§ decisions → SA Template (VERT-02))
    - .gitignore (current state — note: `credentials/` is NOT yet listed)
  </read_first>
  <action>
**Step 1: Create the `credentials/` directory and template JSON.**

Write `credentials/vertex_ai_service_account_example.json` with exactly this content (verbatim from PRD §B5.2 schema):

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

All real-secret fields (`private_key_id`, `private_key`, `client_id`, `client_x509_cert_url` tail) use the literal strings `PLACEHOLDER`, `PLACEHOLDER_KEY_ID`, `PLACEHOLDER_CLIENT_ID`. The `project_id` and SA email use the literal marker `YOUR_PROJECT_ID`.

**Step 2: Update `.gitignore` to exclude real keys but track the template.**

The current `.gitignore` does NOT mention `credentials/`. Append these lines at the end of the file (preserve all existing content — surgical change):

```
# Vertex AI service account keys — directory excluded, template tracked
credentials/
!credentials/vertex_ai_service_account_example.json
```

Rationale: git applies the first rule to ignore all of `credentials/`, then the `!` negation re-includes the example file. Order matters — the negation MUST come after the directory exclusion.

**Step 3: Verify.**

```bash
# Template is valid JSON
python -c "import json; json.load(open('credentials/vertex_ai_service_account_example.json'))"

# Template has all 10 required fields
python -c "import json; d = json.load(open('credentials/vertex_ai_service_account_example.json')); required = {'type','project_id','private_key_id','private_key','client_email','client_id','auth_uri','token_uri','auth_provider_x509_cert_url','client_x509_cert_url'}; assert required.issubset(d.keys()), f'missing: {required - d.keys()}'"

# Template contains only placeholders
grep -q 'YOUR_PROJECT_ID' credentials/vertex_ai_service_account_example.json
grep -q 'PLACEHOLDER' credentials/vertex_ai_service_account_example.json

# .gitignore has credentials/ exclusion
grep -q '^credentials/$' .gitignore
grep -q '^!credentials/vertex_ai_service_account_example\.json$' .gitignore

# The example file is NOT ignored by git (verify negation works)
git check-ignore credentials/vertex_ai_service_account_example.json ; [ $? -eq 1 ]  # exit 1 = not ignored ✓
# A hypothetical real key SHOULD be ignored
echo '{}' > credentials/test_real_key.json
git check-ignore credentials/test_real_key.json ; RC=$? ; rm credentials/test_real_key.json ; [ $RC -eq 0 ]  # exit 0 = ignored ✓
```
  </action>
  <verify>
    <automated>python -c "import json; d = json.load(open('credentials/vertex_ai_service_account_example.json')); required = {'type','project_id','private_key_id','private_key','client_email','client_id','auth_uri','token_uri','auth_provider_x509_cert_url','client_x509_cert_url'}; assert required.issubset(d.keys())" && grep -q 'YOUR_PROJECT_ID' credentials/vertex_ai_service_account_example.json && grep -q 'PLACEHOLDER' credentials/vertex_ai_service_account_example.json && grep -q '^credentials/$' .gitignore && grep -q '^!credentials/vertex_ai_service_account_example\.json$' .gitignore</automated>
  </verify>
  <acceptance_criteria>
    - `python -c "import json; json.load(open('credentials/vertex_ai_service_account_example.json'))"` exits 0 (valid JSON)
    - All 10 required fields present (type, project_id, private_key_id, private_key, client_email, client_id, auth_uri, token_uri, auth_provider_x509_cert_url, client_x509_cert_url)
    - `grep -q 'YOUR_PROJECT_ID' credentials/vertex_ai_service_account_example.json` exits 0
    - `grep -q 'PLACEHOLDER' credentials/vertex_ai_service_account_example.json` exits 0
    - No real Google API key pattern: `grep -E 'AIza[0-9A-Za-z_-]{35}' credentials/vertex_ai_service_account_example.json` returns empty
    - `grep -q '^credentials/$' .gitignore` exits 0
    - `grep -q '^!credentials/vertex_ai_service_account_example\.json$' .gitignore` exits 0
    - `git check-ignore credentials/vertex_ai_service_account_example.json` exits 1 (NOT ignored — template stays tracked)
  </acceptance_criteria>
  <done>Template JSON valid, placeholders verified, `.gitignore` guard in place, example file remains tracked while any other file under `credentials/` is excluded.</done>
</task>

<task type="auto">
  <name>Task 2: Write standalone cost estimation script</name>
  <files>scripts/estimate_vertex_ai_cost.py</files>
  <read_first>
    - .planning/phases/16-vertex-ai-design/16-CONTEXT.md (§ specifics → script skeleton with all constants)
    - .planning/MILESTONE_v3.2_REQUIREMENTS.md lines 295-303 (§B5.4 output format verbatim)
  </read_first>
  <action>
Create `scripts/estimate_vertex_ai_cost.py` with exactly this content. The script is standalone — no imports from `lib.*`, `config`, or any other project module. All pricing is hardcoded as module-level constants. No network calls anywhere:

```python
"""Estimate monthly cost for batch ingestion with Vertex AI + SiliconFlow + DeepSeek.

Standalone: no network calls, no imports of project modules. Rates hardcoded at top.
Rerun after editing rates if GCP / DeepSeek / SiliconFlow pricing changes.

Usage:
    python scripts/estimate_vertex_ai_cost.py --articles 282 --avg-images-per-article 25

Output format is pinned verbatim to MILESTONE_v3.2_REQUIREMENTS.md §B5.4. All ¥ values
are ESTIMATES for budget planning, not invoices.
"""
from __future__ import annotations

import argparse

# ---------------------------------------------------------------------------
# Pricing constants (2026-04 published rates). Edit and re-run if rates change.
# ---------------------------------------------------------------------------

# Vertex AI embedding (gemini-embedding-004): $0.00002 per 1k characters
VERTEX_EMBEDDING_PER_1K_CHARS_USD: float = 0.00002

# SiliconFlow Qwen3-VL-32B: ¥0.0013 per image
SILICONFLOW_PER_IMAGE_CNY: float = 0.0013

# DeepSeek chat pricing (CNY per 1k tokens)
DEEPSEEK_INPUT_PER_1K_TOKENS_CNY: float = 0.0014
DEEPSEEK_OUTPUT_PER_1K_TOKENS_CNY: float = 0.0028

# USD → CNY conversion rate (update manually on material FX moves)
USD_TO_CNY: float = 7.2

# ---------------------------------------------------------------------------
# Workload assumptions (observed averages from v3.1 batches)
# ---------------------------------------------------------------------------

AVG_CHARS_PER_CHUNK: int = 1500
AVG_CHUNKS_PER_ARTICLE: int = 30
AVG_INPUT_TOKENS_PER_CLASSIFICATION: int = 4000
AVG_OUTPUT_TOKENS_PER_CLASSIFICATION: int = 800


def estimate_embedding_cost_cny(articles: int) -> float:
    """Vertex AI embedding cost in CNY for N articles (30 chunks x 1500 chars/chunk)."""
    total_chars = articles * AVG_CHUNKS_PER_ARTICLE * AVG_CHARS_PER_CHUNK
    cost_usd = (total_chars / 1000.0) * VERTEX_EMBEDDING_PER_1K_CHARS_USD
    return cost_usd * USD_TO_CNY


def estimate_vision_cost_cny(articles: int, images_per_article: int) -> float:
    """SiliconFlow vision cost in CNY for N articles with M images each."""
    return articles * images_per_article * SILICONFLOW_PER_IMAGE_CNY


def estimate_llm_cost_cny(articles: int) -> float:
    """DeepSeek LLM cost in CNY for classification + chunk extraction per article."""
    input_cost = (AVG_INPUT_TOKENS_PER_CLASSIFICATION / 1000.0) * DEEPSEEK_INPUT_PER_1K_TOKENS_CNY
    output_cost = (AVG_OUTPUT_TOKENS_PER_CLASSIFICATION / 1000.0) * DEEPSEEK_OUTPUT_PER_1K_TOKENS_CNY
    return articles * (input_cost + output_cost)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estimate monthly ingestion cost with Vertex AI + SiliconFlow + DeepSeek."
    )
    parser.add_argument("--articles", type=int, required=True, help="Number of articles per month")
    parser.add_argument(
        "--avg-images-per-article",
        type=int,
        required=True,
        help="Average number of images per article",
    )
    args = parser.parse_args()

    embedding = estimate_embedding_cost_cny(args.articles)
    vision = estimate_vision_cost_cny(args.articles, args.avg_images_per_article)
    llm = estimate_llm_cost_cny(args.articles)
    total = embedding + vision + llm

    # Output format MUST match PRD §B5.4 verbatim.
    print(
        f"Estimated cost for {args.articles} articles with {args.avg_images_per_article} images/article:"
    )
    print(f"- Embedding (Vertex AI): ¥{embedding:.2f}/month (vs ¥0 free tier)")
    print(f"- Vision (SiliconFlow): ¥{vision:.2f}/month")
    print(f"- LLM (DeepSeek): ¥{llm:.2f}/month")
    print(f"- Total: ¥{total:.2f}/month")


if __name__ == "__main__":
    main()
```

Verify the script runs and produces the exact expected lines:

```bash
python scripts/estimate_vertex_ai_cost.py --articles 282 --avg-images-per-article 25

# Expected output (numbers will reflect the hardcoded constants):
# Estimated cost for 282 articles with 25 images/article:
# - Embedding (Vertex AI): ¥1.83/month (vs ¥0 free tier)
# - Vision (SiliconFlow): ¥9.17/month
# - LLM (DeepSeek): ¥2.21/month
# - Total: ¥13.20/month
#
# (Exact values are not part of the acceptance — only the format is pinned.)
```

Confirm no project-module imports:

```bash
grep -E '^from (lib|config)|^import (lib|config)' scripts/estimate_vertex_ai_cost.py  # must return NOTHING
```

Confirm no network calls (no requests/httpx/urllib/socket):

```bash
grep -E '^(from|import) (requests|httpx|urllib|socket|aiohttp)' scripts/estimate_vertex_ai_cost.py  # must return NOTHING
```
  </action>
  <verify>
    <automated>python scripts/estimate_vertex_ai_cost.py --articles 282 --avg-images-per-article 25 | grep -q 'Total: ¥' && python scripts/estimate_vertex_ai_cost.py --articles 282 --avg-images-per-article 25 | grep -q 'Estimated cost for 282 articles with 25 images/article:' && python scripts/estimate_vertex_ai_cost.py --articles 282 --avg-images-per-article 25 | grep -q 'Embedding (Vertex AI): ¥' && python scripts/estimate_vertex_ai_cost.py --articles 282 --avg-images-per-article 25 | grep -q 'Vision (SiliconFlow): ¥' && python scripts/estimate_vertex_ai_cost.py --articles 282 --avg-images-per-article 25 | grep -q 'LLM (DeepSeek): ¥'</automated>
  </verify>
  <acceptance_criteria>
    - `python scripts/estimate_vertex_ai_cost.py --articles 282 --avg-images-per-article 25` exits 0
    - Output contains the line starting with `Estimated cost for 282 articles with 25 images/article:`
    - Output contains a line matching `- Embedding (Vertex AI): ¥` followed by a number and `/month (vs ¥0 free tier)`
    - Output contains a line matching `- Vision (SiliconFlow): ¥` followed by a number and `/month`
    - Output contains a line matching `- LLM (DeepSeek): ¥` followed by a number and `/month`
    - Output contains a line matching `- Total: ¥` followed by a number and `/month`
    - Running without required args (`python scripts/estimate_vertex_ai_cost.py`) exits non-zero (argparse enforces required args)
    - Running with `--help` exits 0 (smoke test argparse integration)
    - Zero project-module imports: `grep -E '^from (lib|config)|^import (lib|config)' scripts/estimate_vertex_ai_cost.py` returns empty
    - Zero network libraries: `grep -E '^(from|import) (requests|httpx|urllib|socket|aiohttp)' scripts/estimate_vertex_ai_cost.py` returns empty
    - File length ≥ 40 lines (`wc -l scripts/estimate_vertex_ai_cost.py` returns ≥ 40)
  </acceptance_criteria>
  <done>Script runs standalone (no project imports, no network), accepts required args, produces PRD §B5.4 verbatim format. Pricing constants are editable at the top of the file.</done>
</task>

</tasks>

<verification>
Both tasks can run in parallel within this plan (no shared files). Final smoke test: run cost script with two different inputs to confirm output scales with arg values.
</verification>

<success_criteria>
- [ ] SA template JSON exists, valid, placeholders only
- [ ] `.gitignore` excludes `credentials/` except the example file
- [ ] Cost script runs standalone offline and prints PRD §B5.4 verbatim format
- [ ] No real credentials anywhere; no network calls in the script
</success_criteria>

<output>
After completion, create `.planning/phases/16-vertex-ai-design/16-02-SUMMARY.md` recording: template field list, `.gitignore` diff, cost script constants as of this date.
</output>
