---
phase: 16-vertex-ai-design
plan: 02
status: complete
completed: 2026-05-01
key-files:
  created:
    - credentials/vertex_ai_service_account_example.json
    - scripts/estimate_vertex_ai_cost.py
  modified:
    - .gitignore
---

## What was built

Three artifacts:
1. **credentials/vertex_ai_service_account_example.json** — schema template with all 10 required SA fields, placeholder values only (`YOUR_PROJECT_ID`, `PLACEHOLDER_*`).
2. **scripts/estimate_vertex_ai_cost.py** — standalone cost estimator CLI with hardcoded 2026-04 pricing constants, argparse-required `--articles` + `--avg-images-per-article`.
3. **.gitignore** — appended `credentials/` exclusion + `!credentials/vertex_ai_service_account_example.json` negation so the template stays tracked but real SA keys never get committed.

## Acceptance criteria

All 11 checks pass:
- JSON valid and all 10 required SA fields present (type, project_id, private_key_id, private_key, client_email, client_id, auth_uri, token_uri, auth_provider_x509_cert_url, client_x509_cert_url)
- Only placeholder values — no real Google API key pattern match
- `.gitignore` has both `credentials/` exclusion and template negation
- `python scripts/estimate_vertex_ai_cost.py --articles 282 --avg-images-per-article 25` runs clean, output matches PRD §B5.4 format verbatim:
  - `Estimated cost for 282 articles with 25 images/article:`
  - `- Embedding (Vertex AI): ¥1.83/month (vs ¥0 free tier)`
  - `- Vision (SiliconFlow): ¥9.16/month`
  - `- LLM (DeepSeek): ¥2.21/month`
  - `- Total: ¥13.20/month`
- Zero project-module imports (no `lib.*` / `config` imports)
- Zero network libraries imported

## Deviations

None. All three artifacts match plan verbatim.

## Notes

Cost constants frozen at 2026-04 rates in module-level `UPPER_CASE` constants — edit at top of file if GCP / DeepSeek / SiliconFlow rates move.
