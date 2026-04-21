#!/usr/bin/env bash
# ingest.sh — Wrapper for the OmniGraph-Vault ingestion pipeline.
#
# Resolves project root from OMNIGRAPH_ROOT env var so this script works
# correctly from any working directory (required for Hermes invocation).
#
# Usage:
#   scripts/ingest.sh "<wechat-url>"
#   scripts/ingest.sh "<local-file.pdf>"

set -euo pipefail

# ── 1. Resolve project root ────────────────────────────────────────────────
OMNIGRAPH_ROOT="${OMNIGRAPH_ROOT:-$HOME/Desktop/OmniGraph-Vault}"

if [[ ! -d "$OMNIGRAPH_ROOT" ]]; then
  echo "⚠️ Setup error: OmniGraph-Vault repo not found at $OMNIGRAPH_ROOT" >&2
  echo "   Set the OMNIGRAPH_ROOT environment variable to the correct path and retry." >&2
  exit 1
fi

# ── 2. Validate required argument ─────────────────────────────────────────
TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  echo "⚠️ Usage: ingest.sh <wechat-url-or-pdf-path>" >&2
  exit 1
fi

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

# ── 6. Dispatch based on input type ───────────────────────────────────────
if [[ "$TARGET" == *.pdf ]] || [[ "$TARGET" == *.PDF ]]; then
  echo "Starting PDF ingestion — this may take 30–120 seconds..."
  python multimodal_ingest.py "$TARGET"
else
  echo "Starting ingestion — this may take 30–120 seconds..."
  python ingest_wechat.py "$TARGET"
fi
