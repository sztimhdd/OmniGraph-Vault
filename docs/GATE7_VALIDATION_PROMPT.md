# Gate 7 Validation Prompt

Paste this prompt into Hermes (or Claude Code) on the remote deployment machine after completing the deployment steps in `Deploy.md`.

---

## Kickstart Prompt

```
You are validating the OmniGraph-Vault deployment on this machine. The repo is at
~/OmniGraph-Vault and runtime data is at ~/.hermes/omonigraph-vault/.

Run the Gate 7 validation checklist below. For each check, run the command, report
PASS or FAIL, and note any errors. Do not fix anything — just report results.

## Pre-flight

1. Confirm repo exists and is on main branch:
   cd ~/OmniGraph-Vault && git status --short --branch

2. Confirm venv works:
   cd ~/OmniGraph-Vault && source venv/bin/activate && python -c "import lightrag; import cognee; from google import genai; print('All imports OK')"

3. Confirm GEMINI_API_KEY is set:
   source ~/.hermes/.env && echo "GEMINI_API_KEY=${GEMINI_API_KEY:0:8}..."

4. Confirm runtime data directory exists:
   ls -la ~/.hermes/omonigraph-vault/

## G7-1: Skills registered from repo (not ~/.hermes/skills/)

   hermes skills list | grep omnigraph

   PASS if all 3 skills appear: omnigraph_ingest, omnigraph_query, omnigraph_architect
   FAIL if any skill is missing or sourced from ~/.hermes/skills/ instead of repo

## G7-2: Shell wrappers work from any directory

   cd /tmp && bash ~/OmniGraph-Vault/skills/omnigraph_ingest/scripts/ingest.sh
   cd /tmp && bash ~/OmniGraph-Vault/skills/omnigraph_architect/scripts/architect.sh

   PASS if both exit non-zero with a human-readable usage message (no Python traceback)

## G7-3: Config error guard

   Temporarily unset GEMINI_API_KEY and run:
   (unset GEMINI_API_KEY && bash ~/OmniGraph-Vault/skills/omnigraph_ingest/scripts/ingest.sh "https://test.com")

   PASS if output contains "GEMINI_API_KEY is not set" and exit code is 1

## G7-4: Structural validation (no API calls)

   cd ~/OmniGraph-Vault && source venv/bin/activate
   python skill_runner.py skills/ --validate --test-all

   PASS if all 3 skills show PASS

## G7-5: Full test suite (calls Gemini API — takes ~3 minutes)

   cd ~/OmniGraph-Vault && source venv/bin/activate
   python skill_runner.py skills/ --test-all

   PASS if 30/30 passed (11 architect + 9 ingest + 10 query)

## G7-6: Ingest routing via Hermes

   hermes chat "add this article to my knowledge base"

   PASS if Hermes routes to omnigraph_ingest and asks for URL (guard clause fires)

## G7-7: Query routing via Hermes

   hermes chat "what do I know about LightRAG?"

   PASS if Hermes routes to omnigraph_query and returns a synthesis response

## G7-8: Architect routing via Hermes

   hermes chat "what stack should I use for a solo AI chatbot?"

   PASS if Hermes routes to omnigraph_architect and starts the propose flow
   (default guess + asks project type question)

## G7-9: Cross-article synthesis

   cd ~/OmniGraph-Vault && source venv/bin/activate
   python kg_synthesize.py "Compare the architectures of Hermes Agent and OpenClaw" hybrid

   PASS if response references named entities from 2+ different ingested articles

## G7-10: Architect propose end-to-end

   cd ~/OmniGraph-Vault && source venv/bin/activate
   bash skills/omnigraph_architect/scripts/architect.sh propose "solo dev building an AI RAG chatbot, time-constrained"

   PASS if output contains Stack Recommendation + Don't Use sections with rule citations

## Report

Summarize results as:

   Gate 7 Validation: X/10 PASSED
   Date: YYYY-MM-DD
   Machine: <hostname>
   Branch: <git branch>
   Commit: <git short hash>

   PASS checks: G7-1, G7-2, ...
   FAIL checks: G7-X (reason), ...

If 10/10 PASS: deployment is complete. Ready for production use.
If any FAIL: note the failure reason. Do not attempt fixes — report back.
```

---

## Quick Deploy Checklist (run before validation)

If deploying fresh, run these steps first:

```bash
# 1. Clone
git clone https://github.com/sztimhdd/OmniGraph-Vault.git ~/OmniGraph-Vault
cd ~/OmniGraph-Vault

# 2. Venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Runtime dirs
mkdir -p ~/.hermes/omonigraph-vault/images
mkdir -p ~/.hermes/omonigraph-vault/lightrag_storage

# 4. Env vars (edit with your actual keys)
cat >> ~/.hermes/.env << 'EOF'
GEMINI_API_KEY=your_key_here
APIFY_TOKEN=your_token_here
GITHUB_TOKEN=your_token_here
EOF

# 5. Connect skills to Hermes
hermes config set skills.external_dirs '["~/OmniGraph-Vault/skills"]'
hermes gateway restart

# 6. Verify
hermes skills list | grep omnigraph
```

If updating an existing deployment:

```bash
cd ~/OmniGraph-Vault
git pull --ff-only origin main
source venv/bin/activate
pip install -r requirements.txt
hermes gateway restart
```
