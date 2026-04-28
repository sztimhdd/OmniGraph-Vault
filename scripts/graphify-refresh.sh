#!/bin/bash
# scripts/graphify-refresh.sh
# Weekly cron refresh of the code graph. Runs ONLY on remote WSL2 (Linux) PC.
# Local Windows dev should not invoke this — crontab does not exist there.
#
# Why `graphify update` (and NOT the non-existent `build` or `refresh` subcommands):
#   - The `build` and `refresh` subcommands do NOT exist in the Graphify CLI (0.5.3).
#   - `graphify update <path>` does AST-only re-extraction and merges into an
#     existing graph.json. The to_json() writer has a built-in shrink guard
#     (v0.5.0+) that refuses to overwrite with a smaller graph, so atomic
#     swap is handled for us — no custom tmp-rename needed.
#   - LLM-driven doc/semantic changes are flagged via `graphify check-update`
#     and require a human-in-loop Hermes session (Plan 02's runbook).
#
# See .planning/phases/06-graphify-addon-code-graph/06-RESEARCH.md §Code
# Examples §4 and §State of the Art for the rationale.

set -euo pipefail

GRAPHIFY_ROOT="$HOME/.hermes/omonigraph-vault/graphify"
LOG_FILE="$HOME/.hermes/omonigraph-vault/graphify-refresh.log"
GRAPH_JSON="$GRAPHIFY_ROOT/graphify-out/graph.json"

# Ensure log dir exists
mkdir -p "$(dirname "$LOG_FILE")"

# Halt if the existing graph.json is missing — cron is a refresh mechanism,
# not a bootstrap. Bootstrap is handled by Plan 02's human-in-loop runbook.
if [[ ! -f "$GRAPH_JSON" ]]; then
    echo "ERROR: graph.json missing at $GRAPH_JSON — run the Plan 02 seed runbook first" >> "$LOG_FILE"
    exit 1
fi

cd "$GRAPHIFY_ROOT"

# 1. Pull latest for each T1 repo; keep stale on pull failure (per risk register).
for repo_dir in repos/*/*/; do
    if [[ -d "$repo_dir/.git" ]]; then
        (cd "$repo_dir" && git pull --ff-only) 2>&1 | tee -a "$LOG_FILE" \
            || echo "WARN: $repo_dir git pull failed — keeping stale checkout" >> "$LOG_FILE"
    fi
done

# 2. AST-only rebuild (no LLM). Halt-and-preserve on error (set -e above).
#    graphify update's shrink guard preserves the existing graph.json if the
#    rebuild would produce a smaller result — this is the atomic-swap behavior.
source "$HOME/OmniGraph-Vault/venv/bin/activate"
graphify update . 2>&1 | tee -a "$LOG_FILE"

# 3. Min-node assertion (additional sanity on top of shrink guard).
NODES=$(python -c "import json; print(len(json.load(open('$GRAPH_JSON'))['nodes']))")
if (( NODES < 100 )); then
    echo "WARN: graph too small ($NODES nodes) — investigate" >> "$LOG_FILE"
fi

# 4. Report non-code changes that need a human-in-loop /graphify --update
#    inside a Hermes session to re-run semantic extraction. Purely advisory.
graphify check-update . 2>&1 | tee -a "$LOG_FILE"

echo "=== $(date -Is) refresh complete (nodes=$NODES) ===" >> "$LOG_FILE"
