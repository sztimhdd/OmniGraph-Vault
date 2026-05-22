#!/usr/bin/env bash
# research.sh — Wrapper for the OmniGraph agentic-RAG research pipeline.
#
# SKILL-01..05: thin wrapper around `python -m omnigraph.research`.
# All logic lives in lib/research/. This script ONLY:
#   1. Validates the query argument
#   2. Resolves repo root and venv (Windows Git Bash + POSIX)
#   3. Sources ~/.hermes/.env so GEMINI_API_KEY etc. are available
#   4. Forwards to `python -m omnigraph.research "$query"`
#   5. Propagates exit code via `exec`
#
# Usage:
#   scripts/research.sh "<natural-language query>"
#   scripts/research.sh "深度解析 Hermes Harness"

set -euo pipefail

# ── 1. Validate query argument ────────────────────────────────────────────
if [[ $# -lt 1 ]]; then
    echo "⚠️ Usage: research.sh '<query>'" >&2
    echo "   Example: research.sh 'deep dive on Hermes Harness'" >&2
    exit 1
fi

QUERY="$1"

# ── 2. Resolve repo root via BASH_SOURCE so this works regardless of CWD ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# skills/omnigraph_research/scripts/research.sh → ../../.. = repo root
OMNIGRAPH_ROOT="${OMNIGRAPH_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"

if [[ ! -d "$OMNIGRAPH_ROOT" ]]; then
    echo "⚠️ Setup error: OmniGraph-Vault repo not found at $OMNIGRAPH_ROOT" >&2
    exit 2
fi

# ── 3. Source shared env vars if available ────────────────────────────────
if [[ -f "$HOME/.hermes/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$HOME/.hermes/.env"
    set +a
fi

# ── 4. Pick the right venv python (Windows Git Bash vs POSIX) ─────────────
if [[ -x "$OMNIGRAPH_ROOT/venv/Scripts/python.exe" ]]; then
    PY="$OMNIGRAPH_ROOT/venv/Scripts/python.exe"
elif [[ -x "$OMNIGRAPH_ROOT/venv/bin/python" ]]; then
    PY="$OMNIGRAPH_ROOT/venv/bin/python"
else
    echo "⚠️ Setup error: venv not found at $OMNIGRAPH_ROOT/venv" >&2
    echo "   Run: cd $OMNIGRAPH_ROOT && python -m venv venv && pip install -e ." >&2
    exit 2
fi

# ── 5. Run from repo root so `python -m omnigraph.research` resolves ──────
cd "$OMNIGRAPH_ROOT"
exec "$PY" -m omnigraph.research "$QUERY"
