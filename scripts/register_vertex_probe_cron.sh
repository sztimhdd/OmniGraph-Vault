#!/usr/bin/env bash
# register_vertex_probe_cron.sh — HYG-01 monthly Vertex catalog probe (Phase 18-00).
#
# Registers one cron job that fires the Vertex embedding model-name live
# probe on day 1 of every month at 08:00 local. Idempotent: re-running
# prints SKIP if the job is already registered.
#
# Rationale: Vertex AI catalog flipped twice within 24h during Wave 0
# Close-Out (2026-05-02 / 05-03). Monthly probe + Telegram alert is the
# minimum cost vs. discovering the flip via in-batch 404 storms.
#
# Usage (on remote Hermes host):
#   ssh <hermes> "cd ~/OmniGraph-Vault && git pull --ff-only && bash scripts/register_vertex_probe_cron.sh"
#
# Per D-16 "Hermes drives": the cron prompt is natural-language; the
# Hermes skill system translates it into the Python subprocess.

set -euo pipefail

EXISTING="$(hermes cron list 2>/dev/null || echo '')"
NAME="vertex-probe-monthly"
SCHEDULE="0 8 1 * *"

if printf '%s\n' "$EXISTING" | grep -qE "\b${NAME}\b"; then
  echo "SKIP ${NAME} (already registered)"
else
  echo "ADD  ${NAME} @ ${SCHEDULE}"
  hermes cron add \
    --name "${NAME}" \
    --workdir "${OMNIGRAPH_ROOT:-$HOME/OmniGraph-Vault}" \
    "${SCHEDULE}" \
    "run scripts/vertex_live_probe.py; on non-zero exit send a Telegram alert with the script stderr output"
fi

echo ""
echo "=== hermes cron list ==="
hermes cron list
