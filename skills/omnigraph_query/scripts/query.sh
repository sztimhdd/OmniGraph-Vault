#!/usr/bin/env bash
# query.sh — Wrapper for the OmniGraph-Vault query/synthesis pipeline.
#
# Resolves project root from OMNIGRAPH_ROOT env var so this script works
# correctly from any working directory (required for Hermes invocation).
#
# Usage:
#   scripts/query.sh "<natural language question>"
#   scripts/query.sh "<question>" <mode>   # mode: naive/local/global/hybrid/mix

set -euo pipefail

# ── 1. Resolve project root ────────────────────────────────────────────────
OMNIGRAPH_ROOT="${OMNIGRAPH_ROOT:-$HOME/Desktop/OmniGraph-Vault}"

if [[ ! -d "$OMNIGRAPH_ROOT" ]]; then
  echo "⚠️ Setup error: OmniGraph-Vault repo not found at $OMNIGRAPH_ROOT" >&2
  echo "   Set the OMNIGRAPH_ROOT environment variable to the correct path and retry." >&2
  exit 1
fi

# ── 2. Validate required arguments ────────────────────────────────────────
QUERY="${1:-}"
if [[ -z "$QUERY" ]]; then
  echo "⚠️ Usage: query.sh '<question>' [mode]" >&2
  echo "   mode options: naive | local | global | hybrid | mix (default: hybrid)" >&2
  exit 1
fi

MODE="${2:-hybrid}"

# ── 3. Validate required env vars ─────────────────────────────────────────
if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "⚠️ Configuration error: GEMINI_API_KEY is not set." >&2
  echo "   Add it to ~/.hermes/.env and restart." >&2
  exit 1
fi

# ── 4. Activate venv (Windows Git Bash: Scripts/activate; Unix: bin/activate) ──
if [[ -f "$OMNIGRAPH_ROOT/venv/Scripts/activate" ]]; then
  # shellcheck disable=SC1091
  source "$OMNIGRAPH_ROOT/venv/Scripts/activate"
elif [[ -f "$OMNIGRAPH_ROOT/venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$OMNIGRAPH_ROOT/venv/bin/activate"
else
  echo "⚠️ Setup error: venv not found at $OMNIGRAPH_ROOT/venv" >&2
  echo "   Run: cd $OMNIGRAPH_ROOT && python -m venv venv && pip install -r requirements.txt" >&2
  exit 1
fi

# ── 5. Run from project root so Python imports resolve correctly ───────────
cd "$OMNIGRAPH_ROOT"

# ── 6. Execute synthesis ───────────────────────────────────────────────────
echo "Querying knowledge graph — this may take 15–60 seconds..."
python kg_synthesize.py "$QUERY" "$MODE"
