#!/usr/bin/env bash
# Daily incremental KOL scan — called by Hermes via omnigraph_scan_kol skill.
# Outputs a human-readable summary on stdout. JSON details on stderr for Hermes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PYTHON="$REPO_ROOT/venv/bin/python"
SCAN_SCRIPT="$REPO_ROOT/batch_scan_kol.py"

# --- Session warm-up (Hermes executes this via browser_navigate before calling us) ---
# If session is cold, the Python script will get ret=200013 on the first account.
# Hermes should run: browser_navigate "https://mp.weixin.qq.com" → sleep 3
# before invoking this script.  See SKILL.md decision tree.

# --- Run scan ---
echo "Scanning KOL accounts for new articles..."
# stdout → JSON summary, stderr → logging (discarded in cron, visible in terminal)
SUMMARY_JSON=$("$PYTHON" "$SCAN_SCRIPT" --daily --summary-json --days-back 1 --max-articles 10 2>/dev/null)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "SESSION_ERROR: batch_scan_kol.py exited with code $EXIT_CODE"
    exit 1
fi

# --- Parse JSON ---
NEW=$(echo "$SUMMARY_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['new_articles'])")
SCANNED=$(echo "$SUMMARY_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['scanned'])")
FAILED=$(echo "$SUMMARY_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['failed'])")

if [ "$NEW" -eq 0 ]; then
    echo "No new articles today ($SCANNED accounts scanned, 0 new)."
else
    echo "$NEW new articles found across $SCANNED accounts ($FAILED failed)."
    echo ""
    echo "Top accounts by new articles:"
    echo "$SUMMARY_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
ranked = sorted([a for a in d['by_account'] if a['new'] > 0], key=lambda x: -x['new'])
for a in ranked[:10]:
    print(f\"  {a['name']}: {a['new']} new, {a['skipped']} skipped\")
"
fi
