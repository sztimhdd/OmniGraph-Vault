#!/usr/bin/env bash
# deploy.sh — Windows-local → remote WSL sync for Phase 4 dev loop.
#
# Required env vars (set in your shell, NEVER committed):
#   OMNIGRAPH_SSH_HOST   remote hostname (set in your shell; never committed)
#   OMNIGRAPH_SSH_PORT   SSH port (set in your shell; never committed)
#   OMNIGRAPH_SSH_USER   remote username (set in your shell; never committed)
# Optional:
#   OMNIGRAPH_REMOTE_DIR remote repo path (default: ~/OmniGraph-Vault)
#
# Usage:
#   ./deploy.sh            # push local, pull on remote
#   ./deploy.sh --no-push  # skip local push, only pull on remote

set -euo pipefail

: "${OMNIGRAPH_SSH_HOST:?OMNIGRAPH_SSH_HOST not set}"
: "${OMNIGRAPH_SSH_PORT:?OMNIGRAPH_SSH_PORT not set}"
: "${OMNIGRAPH_SSH_USER:?OMNIGRAPH_SSH_USER not set}"
REMOTE_DIR="${OMNIGRAPH_REMOTE_DIR:-OmniGraph-Vault}"

if [[ "${1:-}" != "--no-push" ]]; then
  echo "-> git push (local)"
  git push
fi

echo "-> git pull (remote ${OMNIGRAPH_SSH_HOST}:${OMNIGRAPH_SSH_PORT})"
ssh -p "${OMNIGRAPH_SSH_PORT}" "${OMNIGRAPH_SSH_USER}@${OMNIGRAPH_SSH_HOST}" \
  "cd ${REMOTE_DIR} && git pull --ff-only && git log -1 --oneline"

echo "deploy complete"
