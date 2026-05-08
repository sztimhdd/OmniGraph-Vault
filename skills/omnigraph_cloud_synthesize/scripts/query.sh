#!/usr/bin/env bash
# query.sh - no-Gemini cloud synthesis over already-ingested OmniGraph docs.

set -euo pipefail

OMNIGRAPH_ROOT="${OMNIGRAPH_ROOT:-$HOME/OmniGraph-Vault}"
QUERY="${1:-}"

if [[ -z "$QUERY" ]]; then
  echo "Usage: query.sh '<question>' [--top-k N]" >&2
  exit 1
fi

if [[ -f "$HOME/.hermes/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$HOME/.hermes/.env"
  set +a
fi

if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "Configuration error: DEEPSEEK_API_KEY is not set in ~/.hermes/.env" >&2
  exit 1
fi

if [[ ! -d "$OMNIGRAPH_ROOT" ]]; then
  echo "Setup error: OmniGraph-Vault repo not found at $OMNIGRAPH_ROOT" >&2
  exit 1
fi

if [[ -f "$OMNIGRAPH_ROOT/venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$OMNIGRAPH_ROOT/venv/bin/activate"
elif [[ -f "$OMNIGRAPH_ROOT/venv/Scripts/activate" ]]; then
  # shellcheck disable=SC1091
  source "$OMNIGRAPH_ROOT/venv/Scripts/activate"
else
  echo "Setup error: venv not found at $OMNIGRAPH_ROOT/venv" >&2
  exit 1
fi

cd "$OMNIGRAPH_ROOT"
python scripts/cloud_synthesize_no_gemini.py "$@"
