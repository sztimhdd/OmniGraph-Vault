#!/usr/bin/env bash
# delegate.sh — Preflight and context-assembly wrapper for the
# hermes_claude_code_bridge skill.
#
# Usage:
#   scripts/delegate.sh preflight "<task>" "<low|medium|high>"
#   scripts/delegate.sh context "<query>"

set -euo pipefail

OMNIGRAPH_ROOT="${OMNIGRAPH_ROOT:-$HOME/OmniGraph-Vault}"

if [[ -f "$HOME/.hermes/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$HOME/.hermes/.env"
  set +a
fi

MODE="${1:-}"

# ── preflight: validate environment and output delegation plan ──────────
preflight() {
  local TASK="${1:-}"
  local COMPLEXITY="${2:-medium}"

  echo "=== Hermes-Claude Code Bridge — Preflight ==="
  echo ""

  # 1. Check claude CLI
  if ! command -v claude &>/dev/null; then
    echo "⚠️  claude CLI not found on PATH."
    echo "   Install: npm install -g @anthropic-ai/claude-code"
    exit 1
  fi
  echo "✅ claude CLI found: $(which claude)"

  # 2. Check git availability
  if ! command -v git &>/dev/null; then
    echo "⚠️  git not found on PATH."
    exit 1
  fi
  echo "✅ git found"

  # 3. Load budget config
  local BUDGET_FILE="$HOME/.hermes/budget.json"
  local MAX_TURNS=""
  if [[ -f "$BUDGET_FILE" ]]; then
    MAX_TURNS=$(python3 -c "
import json
cfg = json.load(open('$BUDGET_FILE'))
turns = cfg.get('claude_code_bridge', {}).get('default_max_turns', {})
print(turns.get('$COMPLEXITY', turns.get('medium', 20)))
" 2>/dev/null || true)
  fi
  if [[ -z "$MAX_TURNS" || "$MAX_TURNS" == "0" ]]; then
    case "$COMPLEXITY" in
      low)    MAX_TURNS=10 ;;
      medium) MAX_TURNS=20 ;;
      high)   MAX_TURNS=30 ;;
      *)      MAX_TURNS=20 ;;
    esac
  fi

  echo "✅ Budget cap: ${MAX_TURNS} turns (complexity: $COMPLEXITY)"

  # 4. Scope boundary warning
  echo ""
  echo "─── Scope Boundary Reminder ───"
  echo "Claude Code MUST NOT touch:"
  echo "  ❌ skills/        (Hermes territory)"
  echo "  ❌ config.py      (Hermes territory)"
  echo "  ❌ .env files      (Hermes territory)"
  echo "  ❌ KG pipeline     (kg_synthesize.py, ingest_wechat.py, etc.)"
  echo "  ❌ .planning/      (Hermes territory)"
  echo ""
  echo "Claude Code MAY touch: source code, tests, spiders/, docs/, non-KG json schemas"
  echo ""

  # 5. Print delegation snippet
  echo "─── Delegation Command ───"
  echo "delegate_task("
  echo "    goal=\"<assembled goal>\""
  echo "    context=\"<KG context + file contents>\""
  echo "    acp_command=\"claude\""
  echo "    acp_args=[\"--acp\", \"--stdio\", \"--max-turns\", \"${MAX_TURNS}\"]"
  echo ")"
  echo ""
  echo "─── Before Delegating ───"
  echo "1. Query the KG: scripts/delegate.sh context \"$TASK\""
  echo "2. Read relevant source files with Hermes' file tools"
  echo "3. Assemble full context into the delegation goal"
  echo "4. Announce budget and estimated cost to the user"
  echo "5. Delegate with delegate_task(...)"
  echo ""
  echo "=== Preflight complete ==="
}

# ── context: query the knowledge graph for relevant prior context ───────
context() {
  local QUERY="${1:-}"
  if [[ -z "$QUERY" ]]; then
    echo "Usage: delegate.sh context \"<query>\"" >&2
    exit 1
  fi

  if [[ ! -d "$OMNIGRAPH_ROOT" ]]; then
    echo "⚠️ OmniGraph-Vault not found at $OMNIGRAPH_ROOT" >&2
    exit 1
  fi

  # Activate venv
  if [[ -f "$OMNIGRAPH_ROOT/venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$OMNIGRAPH_ROOT/venv/bin/activate"
  elif [[ -f "$OMNIGRAPH_ROOT/venv/Scripts/activate" ]]; then
    # shellcheck disable=SC1091
    source "$OMNIGRAPH_ROOT/venv/Scripts/activate"
  else
    echo "⚠️ venv not found" >&2
    exit 1
  fi

  cd "$OMNIGRAPH_ROOT"

  echo "=== Knowledge Graph Context for: $QUERY ==="
  echo ""
  python kg_synthesize.py \
    "FACTUAL QUERY — return only what you know from the knowledge graph. $QUERY" \
    hybrid 2>/dev/null || echo "⚠️ KG query failed — proceed without KG context"
}

# ── dispatch ────────────────────────────────────────────────────────────
case "$MODE" in
  preflight)
    preflight "${2:-}" "${3:-medium}"
    ;;
  context)
    context "${2:-}"
    ;;
  *)
    echo "Usage: delegate.sh <preflight|context> <args...>" >&2
    exit 1
    ;;
esac
