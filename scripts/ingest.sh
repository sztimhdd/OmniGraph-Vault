#!/usr/bin/env bash
# Single-article ingest wrapper — always launches in detached tmux.
# Hermes terminal tool has 900s ceiling; single ingest takes 8-15 min.
#
# Usage:
#   scripts/ingest.sh "https://mp.weixin.qq.com/s/..."
#   scripts/ingest.sh "/path/to/file.pdf"

set -euo pipefail

URL="${1:-}"
if [ -z "$URL" ]; then
    echo "Usage: ingest.sh <wechat-url|pdf-path>" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Clear stale pycache after LightRAG upgrades (prevents dataclass replace() TypeError)
find "$PROJECT_ROOT" -path "*__pycache__*lightrag*" -delete 2>/dev/null
find "$PROJECT_ROOT" -path "*__pycache__*embedding*" -delete 2>/dev/null

# Generate a short slug from the URL
SLUG=$(echo "$URL" | md5sum | cut -c1-8)
SESSION="ingest-${SLUG}"
LOGFILE="/tmp/ingest-$(date +%Y%m%d-%H%M%S)-${SLUG}.log"

# Prevent double-launch
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Session $SESSION already running. Monitor: tmux capture-pane -t $SESSION -p | tail -30"
    exit 0
fi

# Use multimodal_ingest.py for PDFs, ingest_wechat.py for URLs
if [[ "$URL" == *.pdf ]]; then
    CMD="cd '$PROJECT_ROOT' && PYTHONPATH=. venv/bin/python multimodal_ingest.py '$URL' 2>&1 | tee '$LOGFILE'; echo 'EXIT='\$?"
else
    CMD="cd '$PROJECT_ROOT' && PYTHONPATH=. venv/bin/python ingest_wechat.py '$URL' 2>&1 | tee '$LOGFILE'; echo 'EXIT='\$?"
fi

tmux new-session -d -s "$SESSION" "$CMD"

echo "tmux session $SESSION launched"
echo "Log: $LOGFILE"
echo "Monitor: tmux capture-pane -t $SESSION -p | tail -30"
