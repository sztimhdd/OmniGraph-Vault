#!/usr/bin/env bash
# Quick 260508-ev2 F2: tmux helper for daily-ingest cron.
#
# Bypasses the Hermes terminal-tool 900s ceiling by launching the long-running
# batch_ingest_from_spider.py inside a detached tmux session. The cron prompt
# becomes monitor-only (tail log + check tmux + check DB row count) instead of
# blocking on the python process.
#
# Usage:
#   ./scripts/cron_daily_ingest.sh [MAX_ARTICLES]   # default 10
#
# Pre-flight: cleanup_stuck_docs.py --all-failed clears any FAILED / PROCESSING
# residue from the prior run before the new ingest acquires LightRAG locks.
#
# Exit codes:
#   0  tmux session launched (or smoke-mode equivalent)
#   1  same-day session already running — refuse to double-launch

set -euo pipefail

MAX_ARTICLES="${1:-10}"
SESSION_NAME="daily-ingest-$(date +%Y%m%d)"
LOG_FILE="/tmp/daily-ingest-$(date +%Y%m%d-%H%M).log"

# Step A — refuse to clobber a same-day session that is still alive; reap
# dead panes so a crash doesn't permanently block the next cron tick.
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    if tmux list-panes -t "$SESSION_NAME" >/dev/null 2>&1; then
        echo "ERROR: session $SESSION_NAME already running" >&2
        exit 1
    fi
    tmux kill-session -t "$SESSION_NAME" || true
    echo "Killed stale dead pane for $SESSION_NAME"
fi

# Step B — clear any cross-day stale daily-ingest sessions so list-sessions
# stays readable.
for stale in $(tmux list-sessions -F '#S' 2>/dev/null | grep '^daily-ingest-' || true); do
    if [ "$stale" != "$SESSION_NAME" ]; then
        tmux kill-session -t "$stale" || true
        echo "Killed cross-day stale session: $stale"
    fi
done

# Step C — build the chained shell command and launch detached.
# All variables are host-evaluated (parameter expansion), no $(...) inside the
# tmux body, so single quotes / escaping are not needed. && chains short-
# circuit on the first failure (cleanup → ingest), so a stuck-doc cleanup
# error halts before paid scrape calls fire.
CMD="cd $HOME/OmniGraph-Vault && \
venv/bin/python scripts/cleanup_stuck_docs.py --all-failed && \
PYTHONPATH=. /usr/bin/time -v venv/bin/python batch_ingest_from_spider.py \
    --from-db --max-articles ${MAX_ARTICLES} \
    2>&1 | tee ${LOG_FILE}"

tmux new-session -d -s "$SESSION_NAME" "$CMD"

echo "tmux session $SESSION_NAME launched, log: $LOG_FILE"
