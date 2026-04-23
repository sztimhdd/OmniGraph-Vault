#!/usr/bin/env bash
# architect.sh — Mode-dispatch wrapper for the /architect skill.
#
# Usage:
#   scripts/architect.sh propose "<question>"
#   scripts/architect.sh query "<question>"
#   scripts/architect.sh ingest "<github-url>"

set -euo pipefail

# ── 1. Resolve project root ────────────────────────────────────────────────
OMNIGRAPH_ROOT="${OMNIGRAPH_ROOT:-$HOME/Desktop/OmniGraph-Vault}"

if [[ ! -d "$OMNIGRAPH_ROOT" ]]; then
  echo "⚠️ Setup error: OmniGraph-Vault repo not found at $OMNIGRAPH_ROOT" >&2
  echo "   Set the OMNIGRAPH_ROOT environment variable to the correct path and retry." >&2
  exit 1
fi

# ── 2. Validate arguments ─────────────────────────────────────────────────
MODE="${1:-}"
INPUT="${2:-}"

if [[ -z "$MODE" ]]; then
  echo "Usage: architect.sh <propose|query|ingest> <input>" >&2
  exit 1
fi

if [[ -z "$INPUT" ]]; then
  echo "⚠️ Missing input argument for mode '$MODE'" >&2
  echo "Usage: architect.sh <propose|query|ingest> <input>" >&2
  exit 1
fi

# ── 3. Validate required env vars ─────────────────────────────────────────
if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "⚠️ Configuration error: GEMINI_API_KEY is not set." >&2
  echo "   Add it to ~/.hermes/.env and restart." >&2
  exit 1
fi

# ── 4. Activate venv ──────────────────────────────────────────────────────
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

# ── 5. Run from project root ─────────────────────────────────────────────
cd "$OMNIGRAPH_ROOT"

# ── 6. Mode dispatch ─────────────────────────────────────────────────────
case "$MODE" in
  propose)
    if [[ ! -f "rules_engine.json" ]]; then
      echo "⚠️ Setup error: rules_engine.json not found at $OMNIGRAPH_ROOT" >&2
      exit 1
    fi
    RULES=$(python -c "
import json
rules = json.load(open('rules_engine.json'))
for r in rules:
    print(f\"[{r['id']}] (weight {r['weight']}) {r['recommendation']} | dont_use: {', '.join(r.get('dont_use', []))}\")
")
    python kg_synthesize.py "ARCHITECTURE RULES CONTEXT (solo-dev rules engine):
$RULES

USER ARCHITECTURE QUESTION: $INPUT

INSTRUCTIONS: Use the rules above to generate a stack recommendation. Output format:
## Stack Recommendation (3-5 bullets, highest-weight matching rules)
## Don't Use (3-5 bullets from dont_use fields, cite rule IDs)
## TDD Quick Start (one concrete command sequence for the recommended stack)" hybrid
    ;;
  query)
    python kg_synthesize.py "$INPUT" hybrid
    ;;
  ingest)
    if [[ ! "$INPUT" =~ github\.com ]]; then
      echo "⚠️ Ingest mode only accepts GitHub repository URLs (github.com/owner/repo)" >&2
      exit 1
    fi
    python ingest_github.py "$INPUT"
    ;;
  *)
    echo "⚠️ Unknown mode: '$MODE'" >&2
    echo "Usage: architect.sh <propose|query|ingest> <input>" >&2
    exit 1
    ;;
esac
